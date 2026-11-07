"""Pruebas unitarias — URL de la firma con token (A3 de la revisión de
seguridad previa al piloto).

    python -m tests.test_firma_token_unitario

Sin BD ni servidor: la sesión de BD y el storage son dobles en memoria, y las
pruebas HTTP le hablan a `main.app` directo por ASGI con `get_db` reemplazado.

El problema que cierra: `GET /api/auth/usuarios/{id}/firma` es público a
propósito (lo pide `descargar_logo_seguro` sin credenciales al generar el
PDF), pero solo pedía el id — correlativo —, así que recorriendo ids se
bajaba la firma escaneada de cada usuario. Ahora la ruta lleva un token
aleatorio que se genera en cada subida y solo se sirve si coincide con el de
`firma_imagen_url` vigente.
"""

import asyncio
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from fastapi import HTTPException  # noqa: E402
from PIL import Image  # noqa: E402

import core.storage as storage_mod  # noqa: E402
from core import branding  # noqa: E402
from core.database import get_db  # noqa: E402
from modulos.auth import crud  # noqa: E402

import main  # noqa: E402

_resultados = []
BASE_PUBLICA = "https://api.aurora.example"


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (30, 10), (0, 0, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------------
# Dobles: usuario, sesión de BD (cuenta consultas) y storage en memoria.
# ------------------------------------------------------------------
class _Usuario:
    def __init__(self, id, firma_imagen_url=None):
        self.id = id
        self.firma_imagen_url = firma_imagen_url


class _Query:
    def __init__(self, db):
        self.db = db

    def filter(self, *a, **k):
        return self

    def first(self):
        return self.db.usuario


class _DB:
    def __init__(self, usuario):
        self.usuario = usuario
        self.consultas = 0

    def query(self, *a, **k):
        self.consultas += 1
        return _Query(self)

    def commit(self):
        pass

    def refresh(self, obj):
        pass


class _Storage:
    def __init__(self):
        self.archivos = {}

    def guardar(self, key, contenido, content_type):
        self.archivos[key] = (contenido, content_type)

    def leer(self, key):
        return self.archivos[key][0]

    def existe(self, key):
        return key in self.archivos


_storage = _Storage()
storage_mod.obtener_storage_service = lambda: _storage
branding.resolver_url_publica = lambda ruta: f"{BASE_PUBLICA}{ruta}"


def _token_de(url):
    return url.rsplit("/", 1)[-1]


class _Respuesta:
    def __init__(self, status_code, headers):
        self.status_code = status_code
        self.headers = headers


def _get(path):
    """GET directo por ASGI a main.app (sin httpx ni red)."""
    mensajes = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(mensaje):
        mensajes.append(mensaje)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
        "query_string": b"", "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 5000), "server": ("testserver", 80),
    }
    asyncio.run(main.app(scope, receive, send))
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in inicio["headers"]}
    return _Respuesta(inicio["status"], headers)


def _404(funcion, *args):
    try:
        funcion(*args)
    except HTTPException as exc:
        return exc.status_code == 404, exc.detail
    return False, None


# ------------------------------------------------------------------
def test_subida_genera_token():
    print("\n[1] Subir la firma genera un token aleatorio en la URL y en la key")
    usuario = _Usuario(7)
    db = _DB(usuario)
    crud.subir_firma_usuario(db, 7, _png(), "firma.png", "application/octet-stream")
    url1 = usuario.firma_imagen_url
    token1 = _token_de(url1)
    comprobar("URL = /api/auth/usuarios/7/firma/{token}",
              re.fullmatch(rf"{re.escape(BASE_PUBLICA)}/api/auth/usuarios/7/firma/[0-9a-f]{{64}}", url1) is not None, url1)
    comprobar("el token va en la key de storage", f"usuarios/7/firma-{token1}.png" in _storage.archivos)
    comprobar("se guarda con el content-type real, no el del cliente",
              _storage.archivos[f"usuarios/7/firma-{token1}.png"][1] == "image/png")
    crud.subir_firma_usuario(db, 7, _png(), "firma.png", "image/png")
    token2 = _token_de(usuario.firma_imagen_url)
    comprobar("otra subida -> otro token", token1 != token2)
    return usuario, db, token1, token2


def test_solo_sirve_el_token_vigente(usuario, db, token_viejo, token_vigente):
    print("\n[2] Solo se sirve con el token vigente")
    contenido, tipo = crud.leer_firma_usuario(db, 7, token_vigente)
    comprobar("token vigente -> bytes de la firma", contenido == _png() and tipo == "image/png")
    ok, detalle = _404(crud.leer_firma_usuario, db, 7, token_viejo)
    comprobar("token de la firma ANTERIOR -> 404 (aunque su archivo siga en storage)",
              ok and f"usuarios/7/firma-{token_viejo}.png" in _storage.archivos)
    ok_otro, _ = _404(crud.leer_firma_usuario, db, 7, "0" * 64)
    comprobar("token bien formado pero inventado -> 404", ok_otro)
    ok_id, _ = _404(crud.leer_firma_usuario, db, 8, token_vigente)
    comprobar("token vigente con OTRO id en la ruta -> 404", ok_id)


def test_tokens_mal_formados_no_consultan_la_bd():
    print("\n[3] Tokens mal formados -> 404 sin tocar la BD ni el storage")
    for token in ("", "abc", "../../etc/passwd", "A" * 64, "g" * 64, "0" * 63, "0" * 65, ("0" * 64) + "/x"):
        db = _DB(_Usuario(7, f"{BASE_PUBLICA}/api/auth/usuarios/7/firma/{token}"))
        ok, _ = _404(crud.leer_firma_usuario, db, 7, token)
        comprobar(f"{token[:20]!r} -> 404, 0 consultas", ok and db.consultas == 0)


def test_mismo_404_para_todo():
    print("\n[4] Todos los casos de 'no hay' dan el mismo 404")
    token = "a" * 64
    casos = {
        "usuario inexistente": _DB(None),
        "sin firma": _DB(_Usuario(7, None)),
        "firma externa (URL de terceros)": _DB(_Usuario(7, "https://cdn.colegio.example/firma.png")),
        "firma borrada (PATCH con '')": _DB(_Usuario(7, "")),
        "URL vigente con el token pero sin archivo": _DB(_Usuario(7, f"{BASE_PUBLICA}/api/auth/usuarios/7/firma/{token}")),
    }
    detalles = set()
    for nombre, db in casos.items():
        ok, detalle = _404(crud.leer_firma_usuario, db, 7, token)
        detalles.add(detalle)
        comprobar(f"{nombre} -> 404", ok)
    comprobar("el mensaje es idéntico en todos los casos", len(detalles) == 1, str(detalles))


def test_http(usuario, db, token_viejo, token_vigente):
    print("\n[5] Por HTTP: ruta nueva, ruta vieja retirada, cabeceras")
    main.app.dependency_overrides[get_db] = lambda: db
    try:
        r = _get(f"/api/auth/usuarios/7/firma/{token_vigente}")
        comprobar("GET con token vigente -> 200 image/png", r.status_code == 200 and r.headers["content-type"] == "image/png")
        comprobar("Cache-Control: private, no-store", r.headers.get("cache-control") == "private, no-store")
        comprobar("X-Content-Type-Options: nosniff", r.headers.get("x-content-type-options") == "nosniff")
        r = _get(f"/api/auth/usuarios/7/firma/{token_viejo}")
        comprobar("GET con token viejo -> 404", r.status_code == 404)
        r = _get("/api/auth/usuarios/7/firma")
        comprobar("GET a la ruta vieja sin token -> ya no sirve nada", r.status_code in (404, 405), str(r.status_code))
    finally:
        main.app.dependency_overrides.pop(get_db, None)

    rutas = {(m, r.path) for r in main.app.routes if hasattr(r, "methods") for m in r.methods}
    comprobar("existe GET /api/auth/usuarios/{usuario_id}/firma/{token}",
              ("GET", "/api/auth/usuarios/{usuario_id}/firma/{token}") in rutas)
    comprobar("ya no existe GET /api/auth/usuarios/{usuario_id}/firma",
              ("GET", "/api/auth/usuarios/{usuario_id}/firma") not in rutas)
    comprobar("la subida sigue en POST /api/auth/usuarios/{usuario_id}/firma",
              ("POST", "/api/auth/usuarios/{usuario_id}/firma") in rutas)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — URL de la firma con token")
    print("=" * 72)
    usuario, db, token_viejo, token_vigente = test_subida_genera_token()
    test_solo_sirve_el_token_vigente(usuario, db, token_viejo, token_vigente)
    test_tokens_mal_formados_no_consultan_la_bd()
    test_mismo_404_para_todo()
    test_http(usuario, db, token_viejo, token_vigente)

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
