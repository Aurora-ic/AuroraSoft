"""CORS_ALLOWED_ORIGINS validada al arrancar (sesión 2026-11-07, revisión de
seguridad previa al piloto) — ver core/cors.py. Sin BD ni servidor.

[1] y [2] prueban la función; [3] arranca main.app en procesos hijos (sin
leer el .env) y confirma que un "*" en producción NO arranca, y que con una
lista válida un origen ajeno no recibe permiso con credenciales.

    python -m tests.test_cors_unitario
"""
import json
import os
import subprocess
import sys

from core.cors import OrigenCorsInvalido, origenes_cors

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def rechaza(valor, es_desarrollo):
    try:
        origenes_cors(valor, es_desarrollo)
    except OrigenCorsInvalido as exc:
        return str(exc)
    return None


def test_validos():
    print("\n[1] Valores válidos (se normalizan sin quejarse)")
    comprobar("dos orígenes con espacios", origenes_cors(" https://a.pe , https://b.pe ", False) == ["https://a.pe", "https://b.pe"])
    comprobar("barra final se quita", origenes_cors("https://app.aurorasoft.pe/", False) == ["https://app.aurorasoft.pe"])
    comprobar("host en mayúsculas → minúsculas", origenes_cors("https://App.AuroraSoft.pe", False) == ["https://app.aurorasoft.pe"])
    comprobar("duplicados se cuentan una vez", origenes_cors("https://a.pe,https://a.pe/", False) == ["https://a.pe"])
    comprobar("coma final vacía se ignora", origenes_cors("https://a.pe,", False) == ["https://a.pe"])
    comprobar("puerto se conserva", origenes_cors("https://a.pe:8443", False) == ["https://a.pe:8443"])
    comprobar("desarrollo acepta http://localhost:3000", origenes_cors("http://localhost:3000", True) == ["http://localhost:3000"])
    comprobar("desarrollo sin variable → http://localhost:3000", origenes_cors(None, True) == ["http://localhost:3000"])


def test_invalidos():
    print("\n[2] Valores que detienen el arranque")
    casos = [
        ("'*' en producción", "*", False),
        ("'*' también en desarrollo", "*", True),
        ("'*' mezclado con un origen válido", "https://a.pe,*", False),
        ("'null'", "null", False),
        ("comodín en el host", "https://*.vercel.app", False),
        ("con ruta", "https://a.pe/api", False),
        ("con query", "https://a.pe?x=1", False),
        ("con usuario", "https://user@a.pe", False),
        ("sin esquema", "a.pe", False),
        ("esquema raro", "ftp://a.pe", False),
        ("puerto no numérico", "https://a.pe:abc", False),
        ("http fuera de desarrollo", "http://app.aurorasoft.pe", False),
        ("http://localhost fuera de desarrollo", "http://localhost:3000", False),
        ("vacía fuera de desarrollo", "", False),
        ("sin variable fuera de desarrollo", None, False),
        ("solo comas", " , ,", False),
    ]
    for etiqueta, valor, dev in casos:
        motivo = rechaza(valor, dev)
        comprobar(f"{etiqueta} → no arranca", motivo is not None)
        comprobar(f"{etiqueta}: el mensaje dice qué corregir", bool(motivo) and "CORS" in motivo, motivo)


SCRIPT_HIJO = r'''
import asyncio, json, sys
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
try:
    import main
except Exception as exc:
    sys.stdout.write("@@JSON@@" + json.dumps({"arranca": False, "error": f"{type(exc).__name__}: {exc}"}))
    raise SystemExit(0)

def preflight(origen):
    mensajes = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(m):
        mensajes.append(m)
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "OPTIONS",
             "scheme": "http", "path": "/api/auth/login", "raw_path": b"/api/auth/login", "root_path": "",
             "query_string": b"", "headers": [(b"host", b"t"), (b"origin", origen.encode()),
             (b"access-control-request-method", b"POST")], "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(main.app(scope, receive, send))
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    h = {k.decode().lower(): v.decode() for k, v in inicio["headers"]}
    return {"status": inicio["status"], "allow_origin": h.get("access-control-allow-origin")}

sys.stdout.write("@@JSON@@" + json.dumps({"arranca": True,
    "propio": preflight("https://app.zz-prueba.pe"), "ajeno": preflight("https://atacante.example")}))
'''


def correr(cors, entorno="production"):
    env = {k: v for k, v in os.environ.items() if k not in ("ENTORNO", "SENTRY_DSN")}
    env.update({"DATABASE_URL": "postgresql://u:c@localhost:1/zz", "SECRET_KEY": "x" * 64,
                "ENTORNO": entorno, "CORS_ALLOWED_ORIGINS": cors, "PYTHONIOENCODING": "utf-8"})
    proc = subprocess.run([sys.executable, "-c", SCRIPT_HIJO], env=env, capture_output=True, timeout=180,
                          cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    salida = proc.stdout.decode("utf-8", "replace")
    if "@@JSON@@" not in salida:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-2000:])
    return json.loads(salida.split("@@JSON@@", 1)[1])


def test_arranque_real():
    print("\n[3] main.app real en procesos hijos")
    r = correr("*")
    comprobar("CORS_ALLOWED_ORIGINS='*' en producción → main no arranca", r["arranca"] is False, r)
    comprobar("y el error lo explica", "CORS" in r.get("error", ""), r.get("error"))
    r = correr("http://app.zz-prueba.pe")
    comprobar("origen http en producción → main no arranca", r["arranca"] is False, r)
    r = correr("https://app.zz-prueba.pe/")
    comprobar("lista válida (con barra final) → arranca", r["arranca"] is True, r)
    if r["arranca"]:
        comprobar("el origen propio recibe Access-Control-Allow-Origin",
                  r["propio"]["allow_origin"] == "https://app.zz-prueba.pe", r["propio"])
        comprobar("un origen ajeno NO recibe Access-Control-Allow-Origin",
                  r["ajeno"]["allow_origin"] is None and r["ajeno"]["status"] == 400, r["ajeno"])


if __name__ == "__main__":
    test_validos()
    test_invalidos()
    test_arranque_real()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO CORS VALIDADO AL ARRANCAR: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
