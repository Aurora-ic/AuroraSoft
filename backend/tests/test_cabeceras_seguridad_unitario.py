"""M2/M3 de la revisión de seguridad (sesión 2026-11-07): cabeceras de
seguridad del backend, /openapi.json apagado fuera de desarrollo y ENTORNO
que ya no falla abierto.

Sin BD ni servidor. Cada escenario importa main.app en un PROCESO HIJO con el
ENTORNO que toca y SIN leer backend/.env (load_dotenv se anula antes de
importar), porque el .env local trae ENTORNO=development y taparía el caso
"la variable falta". Las peticiones van directo por ASGI (sin httpx ni red),
igual que tests/test_firma_token_unitario.py.

    python -m tests.test_cabeceras_seguridad_unitario
"""
import json
import os
import subprocess
import sys

from core import cabeceras_seguridad as cs

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


# Lo que corre dentro del proceso hijo: importa main sin .env y devuelve, en
# JSON, el estado del entorno y las respuestas a una lista fija de peticiones.
SCRIPT_HIJO = r'''
import asyncio, json, sys
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
import main
from fastapi.responses import PlainTextResponse
from core import entorno, sesiones
from core.limite_cuerpo import LIMITE_CUERPO_POR_DEFECTO_BYTES

@main.app.get("/zz-prueba-cache")
def _zz_cache():
    return PlainTextResponse("x", headers={"Cache-Control": "public, max-age=60"})

def llamar(metodo, path, headers=()):
    mensajes = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(m):
        mensajes.append(m)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": metodo, "scheme": "http", "path": path, "raw_path": path.encode(),
             "root_path": "", "query_string": b"",
             "headers": [(b"host", b"testserver")] + [(k.encode(), v.encode()) for k, v in headers],
             "client": ("127.0.0.1", 5000), "server": ("testserver", 80)}
    asyncio.run(main.app(scope, receive, send))
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    cabeceras = {}
    for k, v in inicio["headers"]:
        cabeceras.setdefault(k.decode().lower(), []).append(v.decode())
    return {"status": inicio["status"], "headers": cabeceras}

r = {
    "entorno": entorno.ENTORNO,
    "es_desarrollo": entorno.ES_DESARROLLO,
    "cookie_secure": sesiones.COOKIE_SECURE,
    "openapi_url": main.app.openapi_url,
    "health": llamar("GET", "/health"),
    "openapi": llamar("GET", "/openapi.json"),
    "docs": llamar("GET", "/docs"),
    "no_existe": llamar("GET", "/api/no-existe"),
    "preflight": llamar("OPTIONS", "/api/auth/login", [
        ("origin", "https://app.zz-prueba.pe"), ("access-control-request-method", "POST")]),
    "cuerpo_grande": llamar("POST", "/api/auth/login", [
        ("content-length", str(LIMITE_CUERPO_POR_DEFECTO_BYTES + 1))]),
    "cache_propio": llamar("GET", "/zz-prueba-cache"),
    "por_proxy_http": llamar("POST", "/api/auth/login", [("x-forwarded-proto", "http")]),
    "por_proxy_https": llamar("GET", "/health", [("x-forwarded-proto", "https")]),
}
sys.stdout.write("@@JSON@@" + json.dumps(r))
'''


def correr(entorno):
    """entorno=None → la variable ENTORNO no existe en el proceso hijo."""
    env = {k: v for k, v in os.environ.items() if k != "ENTORNO"}
    env.update({
        "DATABASE_URL": "postgresql://usuario:clave@localhost:1/zz_no_existe",
        "SECRET_KEY": "x" * 64,
        "CORS_ALLOWED_ORIGINS": "https://app.zz-prueba.pe",  # fuera de desarrollo solo https (core/cors.py)
        "PYTHONIOENCODING": "utf-8",
    })
    env.pop("SENTRY_DSN", None)
    if entorno is not None:
        env["ENTORNO"] = entorno
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT_HIJO], env=env, capture_output=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=180,
    )
    salida = proc.stdout.decode("utf-8", "replace")
    if "@@JSON@@" not in salida:
        raise RuntimeError(f"El proceso hijo falló:\n{proc.stderr.decode('utf-8', 'replace')[-3000:]}")
    return json.loads(salida.split("@@JSON@@", 1)[1])


def h(respuesta, nombre):
    valores = respuesta["headers"].get(nombre, [])
    return valores[0] if len(valores) == 1 else (valores or None)


def comprobar_cabeceras_base(etiqueta, respuesta, con_hsts):
    comprobar(f"{etiqueta}: X-Content-Type-Options nosniff", h(respuesta, "x-content-type-options") == "nosniff")
    comprobar(f"{etiqueta}: X-Frame-Options DENY", h(respuesta, "x-frame-options") == "DENY")
    comprobar(f"{etiqueta}: Referrer-Policy no-referrer", h(respuesta, "referrer-policy") == "no-referrer")
    comprobar(f"{etiqueta}: CSP default-src 'none' + frame-ancestors 'none'",
              h(respuesta, "content-security-policy") == cs.CSP_API, h(respuesta, "content-security-policy"))
    if con_hsts:
        comprobar(f"{etiqueta}: HSTS presente", h(respuesta, "strict-transport-security") == cs.HSTS)
    else:
        comprobar(f"{etiqueta}: sin HSTS (desarrollo va por http)", h(respuesta, "strict-transport-security") is None)


# ------------------------------------------------------------------
def test_funcion_pura():
    print("\n[1] cabeceras_para(): qué se agrega según ruta y entorno")
    prod = dict(cs.cabeceras_para("/api/x", es_desarrollo=False))
    dev = dict(cs.cabeceras_para("/api/x", es_desarrollo=True))
    comprobar("producción incluye HSTS", b"strict-transport-security" in prod)
    comprobar("desarrollo no incluye HSTS", b"strict-transport-security" not in dev)
    comprobar("/docs en desarrollo va sin CSP (Swagger carga de un CDN)",
              b"content-security-policy" not in dict(cs.cabeceras_para("/docs", True)))
    comprobar("/docs fuera de desarrollo SÍ lleva CSP (la ruta ni existe, pero no se exceptúa)",
              b"content-security-policy" in dict(cs.cabeceras_para("/docs", False)))
    comprobar("una ruta que empieza por /docsx no se exceptúa",
              b"content-security-policy" in dict(cs.cabeceras_para("/docsx", True)))
    comprobar("Cache-Control por defecto = no-store", prod.get(b"cache-control") == b"no-store")


def test_sin_variable():
    print("\n[2] ENTORNO ausente → se comporta como producción (antes: desarrollo)")
    r = correr(None)
    comprobar("core.entorno.ENTORNO == 'production'", r["entorno"] == "production", r["entorno"])
    comprobar("ES_DESARROLLO es False", r["es_desarrollo"] is False)
    comprobar("cookie de sesión Secure por defecto", r["cookie_secure"] is True)
    comprobar("app.openapi_url es None", r["openapi_url"] is None)
    comprobar("GET /openapi.json → 404", r["openapi"]["status"] == 404, r["openapi"]["status"])
    comprobar("GET /docs → 404", r["docs"]["status"] == 404, r["docs"]["status"])
    comprobar_cabeceras_base("/health", r["health"], con_hsts=True)
    return r


def test_valor_desconocido():
    print("\n[3] ENTORNO con un valor mal escrito ('dev') → también producción")
    r = correr("dev")
    comprobar("ES_DESARROLLO es False", r["es_desarrollo"] is False)
    comprobar("GET /openapi.json → 404", r["openapi"]["status"] == 404)


def test_produccion(r):
    print("\n[4] Producción: las cabeceras llegan también a errores, preflight y 413")
    comprobar_cabeceras_base("404 de ruta inexistente", r["no_existe"], con_hsts=True)
    comprobar("preflight CORS → 200", r["preflight"]["status"] == 200, r["preflight"]["status"])
    comprobar("preflight CORS conserva Access-Control-Allow-Origin",
              h(r["preflight"], "access-control-allow-origin") == "https://app.zz-prueba.pe")
    comprobar_cabeceras_base("preflight CORS", r["preflight"], con_hsts=True)
    comprobar("cuerpo demasiado grande → 413", r["cuerpo_grande"]["status"] == 413, r["cuerpo_grande"]["status"])
    comprobar_cabeceras_base("413 del tope de cuerpo", r["cuerpo_grande"], con_hsts=True)
    comprobar("respuesta normal: Cache-Control no-store", h(r["health"], "cache-control") == "no-store")
    comprobar("un Cache-Control puesto por el endpoint se respeta (no se duplica ni se pisa)",
              r["cache_propio"]["headers"].get("cache-control") == ["public, max-age=60"],
              r["cache_propio"]["headers"].get("cache-control"))
    comprobar("ninguna cabecera de seguridad sale duplicada",
              all(len(r["health"]["headers"].get(n, [])) == 1 for n in
                  ("x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy")))


def test_redireccion_https_pura():
    print("\n[4b] destino_https(): solo lo que llegó por http a través del proxy")
    def scope(headers, path="/api/x", query=b""):
        return {"headers": [(k.encode(), v.encode()) for k, v in headers], "path": path,
                "raw_path": path.encode(), "query_string": query}
    comprobar("X-Forwarded-Proto http → https://mismo-host/ruta?consulta",
              cs.destino_https(scope([("host", "aurorasoft.dpdns.org"), ("x-forwarded-proto", "http")], query=b"a=1"))
              == "https://aurorasoft.dpdns.org/api/x?a=1")
    comprobar("X-Forwarded-Proto https → no redirige",
              cs.destino_https(scope([("host", "a.pe"), ("x-forwarded-proto", "https")])) is None)
    comprobar("sin X-Forwarded-Proto (llamada local, chequeos de piloto.ps1) → no redirige",
              cs.destino_https(scope([("host", "127.0.0.1:8100")])) is None)
    comprobar("varios saltos 'http, https': manda el primero (el del cliente)",
              cs.destino_https(scope([("host", "a.pe"), ("x-forwarded-proto", "http, https")])) == "https://a.pe/api/x")
    comprobar("Host raro (otro sitio con @ o /) → no se arma la redirección",
              cs.destino_https(scope([("host", "a.pe@malo.com"), ("x-forwarded-proto", "http")])) is None
              and cs.destino_https(scope([("host", "malo.com/x"), ("x-forwarded-proto", "http")])) is None)
    comprobar("host con puerto se conserva",
              cs.destino_https(scope([("host", "a.pe:8443"), ("x-forwarded-proto", "http")])) == "https://a.pe:8443/api/x")


def test_redireccion_https_app(r_prod):
    print("\n[4c] Producción: la app redirige lo que entró por http y deja pasar lo demás")
    rh = r_prod["por_proxy_http"]
    comprobar("POST /api/auth/login por http → 308 (no llega al login)", rh["status"] == 308, rh["status"])
    comprobar("Location https://testserver/api/auth/login", h(rh, "location") == "https://testserver/api/auth/login", h(rh, "location"))
    comprobar_cabeceras_base("308 a https", rh, con_hsts=True)
    comprobar("por https → pasa normal (200)", r_prod["por_proxy_https"]["status"] == 200, r_prod["por_proxy_https"]["status"])
    comprobar("local sin proxy (/health) → pasa normal (200)", r_prod["health"]["status"] == 200)


def test_desarrollo():
    print("\n[5] ENTORNO=development → Swagger y openapi siguen disponibles en local")
    r = correr("development")
    comprobar("desarrollo: X-Forwarded-Proto http NO redirige (local va por http)",
              r["por_proxy_http"]["status"] != 308, r["por_proxy_http"]["status"])
    comprobar("ES_DESARROLLO es True", r["es_desarrollo"] is True)
    comprobar("cookie de sesión sin Secure (localhost por http)", r["cookie_secure"] is False)
    comprobar("GET /openapi.json → 200", r["openapi"]["status"] == 200, r["openapi"]["status"])
    comprobar("GET /docs → 200", r["docs"]["status"] == 200, r["docs"]["status"])
    comprobar("/docs sin CSP (si no, Swagger no carga)", h(r["docs"], "content-security-policy") is None)
    comprobar("/docs igual lleva nosniff y X-Frame-Options", h(r["docs"], "x-content-type-options") == "nosniff"
              and h(r["docs"], "x-frame-options") == "DENY")
    comprobar_cabeceras_base("/openapi.json en desarrollo", r["openapi"], con_hsts=False)
    comprobar_cabeceras_base("/health en desarrollo", r["health"], con_hsts=False)


def test_mayusculas_y_espacios():
    print("\n[6] ' Development ' (mayúsculas/espacios) se normaliza a desarrollo")
    r = correr(" Development ")
    comprobar("ES_DESARROLLO es True", r["es_desarrollo"] is True, r["entorno"])


def test_fuentes():
    print("\n[7] Nadie vuelve a leer ENTORNO con 'development' por defecto")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    culpables = []
    for carpeta, _, archivos in os.walk(raiz):
        if any(p in carpeta for p in ("venv", "__pycache__", os.sep + "tests")):
            continue
        for nombre in archivos:
            if nombre.endswith(".py"):
                ruta = os.path.join(carpeta, nombre)
                with open(ruta, encoding="utf-8") as f:
                    if 'getenv("ENTORNO", "development")' in f.read():
                        culpables.append(os.path.relpath(ruta, raiz))
    comprobar("ningún os.getenv(\"ENTORNO\", \"development\") en el backend", not culpables, culpables)


if __name__ == "__main__":
    test_funcion_pura()
    r_prod = test_sin_variable()
    test_valor_desconocido()
    test_produccion(r_prod)
    test_redireccion_https_pura()
    test_redireccion_https_app(r_prod)
    test_desarrollo()
    test_mayusculas_y_espacios()
    test_fuentes()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO CABECERAS DE SEGURIDAD / ENTORNO: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
