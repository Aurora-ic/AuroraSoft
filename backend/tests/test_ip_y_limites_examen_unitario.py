"""Pruebas unitarias — IP real del cliente (M5) y límites del examen pensados
para un colegio detrás de una sola IP (A4), de la revisión de seguridad
previa al piloto.

    python -m tests.test_ip_y_limites_examen_unitario

Sin BD ni servidor: la sesión de BD es un doble que nunca encuentra el token,
y las pruebas HTTP le hablan a `main.app` directo por ASGI. Si hay un Redis en
localhost, prueba también el contador compartido (usa la db 15 y borra solo
sus propias claves).

Lo que cierra:
  - M5: `ip_del_cliente` creía el primer salto de X-Forwarded-For siempre —
    cualquiera podía dejar en la auditoría la IP que quisiera — y el rate
    limit y el captcha usaban otra fuente. Ahora los tres usan
    core/ip_cliente.ip_real, que solo cree la cabecera si la conexión viene
    de un proxy de PROXIES_CONFIABLES.
  - A4: el límite por IP del examen (p. ej. guardar 1500/min) se llenaba con
    ~100 alumnos a la vez detrás de la IP del colegio, y un 429 en /guardar
    le borraba la respuesta al alumno. La enumeración de tokens la frena
    ahora un contador de enlaces INVÁLIDOS por IP; los límites por IP
    generales quedan holgados y el frontend reintenta los 429.
"""

import asyncio
import ipaddress
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core import ip_cliente, limiter as modulo_limiter  # noqa: E402
from core.database import get_db  # noqa: E402
from core.ip_cliente import ip_real  # noqa: E402

import main  # noqa: E402

_resultados = []
RAIZ = Path(__file__).resolve().parent.parent.parent


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _Cliente:
    def __init__(self, host):
        self.host = host


class _Peticion:
    def __init__(self, conexion, xff=None):
        self.client = _Cliente(conexion) if conexion else None
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}


def _redes(texto):
    return ip_cliente._leer_proxies(texto)


# ------------------------------------------------------------------
def test_sin_proxies_se_ignora_la_cabecera():
    print("\n[1] Sin PROXIES_CONFIABLES: X-Forwarded-For no cuenta")
    sin = _redes("")
    comprobar("IP de la conexión", ip_real(_Peticion("200.48.1.7"), sin) == "200.48.1.7")
    comprobar("X-Forwarded-For inventado se ignora",
              ip_real(_Peticion("200.48.1.7", "1.2.3.4"), sin) == "200.48.1.7")
    comprobar("sin conexión -> None (NULL en la auditoría, nunca un dato inventado)",
              ip_real(_Peticion(None, "1.2.3.4"), sin) is None)


def test_con_proxy_confiable():
    print("\n[2] Con un proxy confiable: el último salto que NO es proxy")
    local = _redes("127.0.0.1")
    comprobar("Caddy en la misma máquina -> la IP que agregó el proxy",
              ip_real(_Peticion("127.0.0.1", "190.12.3.4"), local) == "190.12.3.4")
    comprobar("el cliente antepone una IP falsa -> se usa la que agregó el proxy, no la falsa",
              ip_real(_Peticion("127.0.0.1", "8.8.8.8, 190.12.3.4"), local) == "190.12.3.4")
    comprobar("conexión que NO es el proxy -> su cabecera no cuenta",
              ip_real(_Peticion("45.6.7.8", "190.12.3.4"), local) == "45.6.7.8")
    docker = _redes("10.0.0.0/8, 127.0.0.1")
    comprobar("cadena de dos proxies (red CIDR) -> se saltan ambos",
              ip_real(_Peticion("10.0.0.9", "6.6.6.6, 190.12.3.4, 10.0.0.5"), docker) == "190.12.3.4")
    comprobar("proxy confiable sin cabecera -> la propia conexión",
              ip_real(_Peticion("127.0.0.1"), local) == "127.0.0.1")
    comprobar("salto que no es una IP -> None, nunca un texto arbitrario en la auditoría",
              ip_real(_Peticion("127.0.0.1", "<script>"), local) is None)
    comprobar("IPv6 se normaliza",
              ip_real(_Peticion("127.0.0.1", "2001:DB8:0:0::1"), local) == "2001:db8::1")
    comprobar("una entrada inválida en PROXIES_CONFIABLES se ignora (no tumba el arranque)",
              _redes("127.0.0.1, no-es-ip") == (ipaddress.ip_network("127.0.0.1/32"),))


def test_una_sola_fuente():
    print("\n[3] Auditoría, captcha y rate limit usan la MISMA función")
    from core.deps import ip_del_cliente
    from modulos.auth.router import _ip_de

    peticion = _Peticion("200.48.1.7", "1.2.3.4")
    comprobar("ip_del_cliente (auditoría) ya no cree X-Forwarded-For", ip_del_cliente(peticion) == "200.48.1.7")
    comprobar("captcha del login: misma IP", _ip_de(peticion) == "200.48.1.7")
    comprobar("rate limit: la clave de slowapi es core/ip_cliente.clave_ip",
              modulo_limiter.limiter._key_func is ip_cliente.clave_ip)
    comprobar("clave_ip nunca devuelve None (slowapi necesita texto)",
              ip_cliente.clave_ip(_Peticion(None)) == "desconocida")
    fuentes = []
    for carpeta in ("core", "modulos"):
        for archivo in (RAIZ / "backend" / carpeta).rglob("*.py"):
            if archivo.name == "ip_cliente.py":
                continue
            for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
                # Solo código que LEE la IP (no la prosa de un docstring).
                if re.search(r"headers\.get\(\s*['\"]x-forwarded-for|request\.client\.host|"
                             r"import get_remote_address|key_func=get_remote_address", linea, re.I) \
                        and not linea.lstrip().startswith("#"):
                    fuentes.append(f"{archivo.relative_to(RAIZ)}:{n}")
    comprobar("nadie más lee la IP por su cuenta", not fuentes, ", ".join(fuentes))


def test_limites_por_ip_para_un_colegio():
    print("\n[4] Límites por IP dimensionados para ~600 alumnos detrás de una IP")

    def por_minuto(texto):
        cantidad, unidad = texto.split("/")
        assert unidad == "minute"
        return int(cantidad)

    tabla = modulo_limiter.LIMITES_EXAMEN
    comprobar("guardar: 600 alumnos x 30 respuestas/min caben", por_minuto(tabla["guardar"][1]) >= 600 * 30)
    for nombre in ("intake", "asentimiento_texto", "comenzar", "finalizar"):
        comprobar(f"{nombre}: 600 alumnos empezando/terminando en el mismo minuto caben",
                  por_minuto(tabla[nombre][1]) >= 600)
    comprobar("informe_pdf sigue acotado (generar un PDF es caro)", por_minuto(tabla["informe_pdf"][1]) <= 300)
    comprobar("los límites POR TOKEN no cambiaron",
              [tabla[n][0] for n in ("guardar", "comenzar", "finalizar", "informe_pdf")]
              == ["120/minute", "10/minute", "5/minute", "10/minute"])


def test_guardia_en_memoria():
    print("\n[5] Guardia contra enumeración: cuenta solo enlaces inválidos, por IP")
    umbral = modulo_limiter.UMBRAL_ENLACES_INVALIDOS
    modulo_limiter._invalidos_en_memoria.clear()
    ip = "190.0.0.1"
    for _ in range(umbral - 1):
        modulo_limiter.registrar_enlace_invalido(ip)
    comprobar(f"{umbral - 1} inválidos: todavía no bloquea", modulo_limiter.contar_enlaces_invalidos(ip) == umbral - 1)
    modulo_limiter.registrar_enlace_invalido(ip)
    comprobar(f"{umbral} inválidos: llega al umbral", modulo_limiter.contar_enlaces_invalidos(ip) >= umbral)
    comprobar("otra IP no se ve afectada", modulo_limiter.contar_enlaces_invalidos("190.0.0.2") == 0)

    original = modulo_limiter.time.monotonic
    try:
        base = original()
        modulo_limiter.time.monotonic = lambda: base + modulo_limiter.VENTANA_ENLACES_INVALIDOS_SEGUNDOS + 1
        comprobar("pasada la ventana, el contador vuelve a cero", modulo_limiter.contar_enlaces_invalidos(ip) == 0)
    finally:
        modulo_limiter.time.monotonic = original
    modulo_limiter._invalidos_en_memoria.clear()


def test_guardia_en_redis():
    print("\n[6] Guardia con Redis (si hay uno en localhost)")
    try:
        import redis

        cliente = redis.Redis.from_url("redis://localhost:6379/15", socket_connect_timeout=1,
                                       socket_timeout=1, decode_responses=True)
        cliente.ping()
    except Exception:
        print("  (sin Redis en localhost: se omite)")
        return
    original = modulo_limiter.cliente_redis
    ip = f"test-{uuid.uuid4().hex}"
    try:
        modulo_limiter.cliente_redis = lambda: cliente
        for _ in range(5):
            modulo_limiter.registrar_enlace_invalido(ip)
        comprobar("cuenta en Redis", modulo_limiter.contar_enlaces_invalidos(ip) == 5)
        ttl = cliente.ttl(modulo_limiter._clave_invalidos(ip))
        comprobar("la clave vence con la ventana (no se estira con cada intento)",
                  0 < ttl <= modulo_limiter.VENTANA_ENLACES_INVALIDOS_SEGUNDOS, str(ttl))
        comprobar("no tocó el contador en memoria", ip not in modulo_limiter._invalidos_en_memoria)
    finally:
        cliente.delete(modulo_limiter._clave_invalidos(ip))
        modulo_limiter.cliente_redis = original


# ------------------------------------------------------------------
class _QueryVacia:
    def filter(self, *a, **k):
        return self

    def first(self):
        return None


class _DBSinTokens:
    def query(self, *a, **k):
        return _QueryVacia()


def _get(path, ip, xff=None):
    mensajes = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(mensaje):
        mensajes.append(mensaje)

    cabeceras = [(b"host", b"testserver")]
    if xff:
        cabeceras.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
        "query_string": b"", "headers": cabeceras, "client": (ip, 5000), "server": ("testserver", 80),
    }
    asyncio.run(main.app(scope, receive, send))
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    cuerpo = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body")
    return inicio["status"], cuerpo


def test_guardia_por_http():
    print("\n[7] Por HTTP: el endpoint real del examen cuenta sus 404 y bloquea esa IP")
    umbral = modulo_limiter.UMBRAL_ENLACES_INVALIDOS
    modulo_limiter._invalidos_en_memoria.clear()
    main.app.dependency_overrides[get_db] = lambda: _DBSinTokens()
    try:
        atacante, companero = "200.10.10.10", "200.20.20.20"
        estados = [_get(f"/api/educativo/examen/{uuid.uuid4()}/intake", atacante)[0] for _ in range(umbral)]
        comprobar(f"{umbral} tokens inventados -> {umbral} x 404", estados == [404] * umbral, str(set(estados)))
        estado, cuerpo = _get(f"/api/educativo/examen/{uuid.uuid4()}/intake", atacante)
        comprobar("el siguiente desde esa IP -> 429", estado == 429, str(estado))
        comprobar("con un mensaje en español para el alumno",
                  "enlaces de evaluación inválidos" in json.loads(cuerpo).get("detail", ""))
        estado, _ = _get(f"/api/educativo/examen/{uuid.uuid4()}/estado-resultados", atacante)
        comprobar("bloquea TODOS los endpoints del examen, no solo ese (sin oráculo)", estado == 429, str(estado))
        estado, _ = _get(f"/api/educativo/examen/{uuid.uuid4()}/preguntas", atacante)
        comprobar("…también /preguntas", estado == 429, str(estado))
        estado, _ = _get(f"/api/educativo/examen/{uuid.uuid4()}/intake", atacante, xff="9.9.9.9")
        comprobar("un X-Forwarded-For inventado no lo saca del bloqueo", estado == 429, str(estado))
        estado, _ = _get(f"/api/educativo/examen/{uuid.uuid4()}/intake", companero)
        comprobar("otra IP sigue normal (404 por el token inventado, no 429)", estado == 404, str(estado))
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        modulo_limiter._invalidos_en_memoria.clear()


def test_cada_endpoint_publico_tiene_la_guardia():
    print("\n[8] Cada endpoint público del examen lleva la guardia")
    from fastapi.routing import APIRoute

    publicos = [r for r in main.app.routes if isinstance(r, APIRoute) and "{token}" in r.path
                and ("/examen/" in r.path or "/comenzar-test/" in r.path)]
    comprobar("son 11 endpoints", len(publicos) == 11, str(len(publicos)))
    sin = [f"{sorted(r.methods)} {r.path}" for r in publicos
           if modulo_limiter.guardia_enumeracion not in [d.call for d in r.dependant.dependencies]]
    comprobar("todos con guardia_enumeracion", not sin, ", ".join(sin))


def test_frontend_reintenta_429():
    print("\n[9] El frontend reintenta un 429 en /guardar en vez de borrar la respuesta")
    ruta = RAIZ / "aurora_ui" / "app" / "(examen)" / "examen" / "[token]" / "page.tsx"
    if not ruta.exists():
        # Dentro de la imagen Docker del backend (CI) no viaja el frontend.
        print("  (omitido: el frontend no está junto al backend — p. ej. dentro de la imagen Docker)")
        return
    pagina = ruta.read_text(encoding="utf-8")
    comprobar("guardarRespuestaConReintento maneja status 429",
              re.search(r"err\.status === 429 && intentosRestantes > 0", pagina) is not None)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — IP real del cliente y límites del examen")
    print("=" * 72)
    test_sin_proxies_se_ignora_la_cabecera()
    test_con_proxy_confiable()
    test_una_sola_fuente()
    test_limites_por_ip_para_un_colegio()
    test_guardia_en_memoria()
    test_guardia_en_redis()
    test_guardia_por_http()
    test_cada_endpoint_publico_tiene_la_guardia()
    test_frontend_reintenta_429()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
