"""Pruebas unitarias — Tope de tamaño del cuerpo ANTES de autenticar (A2 de la
revisión de seguridad previa al piloto).

    python -m tests.test_limite_cuerpo_unitario

Sin BD ni servidor: importa `main.app` (DATABASE_URL/SECRET_KEY dummy, igual
que test_matriz_permisos_unitario) y le habla directo por ASGI, contando
cuántos bytes del cuerpo llega a pedir la app con `receive()`.

El problema que cierra: FastAPI lee el formulario multipart COMPLETO
(`await request.form()`, que Starlette vuelca a un temporal en disco) antes
de resolver `Depends(...)`, o sea antes de saber si hay sesión. El tope de
`core/subida_archivos.leer_archivo_con_limite` corre dentro del endpoint:
llega tarde. Cualquiera, sin iniciar sesión, podía mandar un cuerpo de varios
GB a una ruta de subida y llenar el disco. El middleware
`core/limite_cuerpo.MiddlewareLimiteCuerpo` corta antes de leer:
  - con `Content-Length` declarado mayor al tope: 413 sin leer ni un byte;
  - sin `Content-Length` (chunked): 413 apenas lo leído supera el tope.

Comprueba también que cada ruta con `UploadFile` tenga su tope declarado
(una ruta de subida nueva sin tope hace fallar este test, igual que un
endpoint nuevo hace fallar la matriz de permisos), que ese tope deje pasar
un archivo del tamaño máximo que el propio endpoint acepta, y que las
versiones de starlette/python-multipart sean las que corrigen los avisos de
DoS de sus parsers.
"""

import asyncio
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

import main  # noqa: E402
from fastapi import UploadFile  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

_resultados = []

RUTA_FIRMA = "/api/auth/usuarios/1/firma"
RUTA_JSON = "/api/auth/resetear-password"
BLOQUE = 256 * 1024
MB = 1024 * 1024


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ------------------------------------------------------------------
# Arnés ASGI: manda un cuerpo en bloques y cuenta lo que la app pide.
# ------------------------------------------------------------------
def _multipart(tamano_archivo, boundary="limiteaurora"):
    """Devuelve (cabecera, generador_de_bloques, largo_total) de un multipart
    con un solo campo `archivo` de `tamano_archivo` bytes. El relleno se
    genera por bloques: nunca se arma el cuerpo entero en memoria."""
    inicio = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="archivo"; filename="firma.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode()
    fin = f"\r\n--{boundary}--\r\n".encode()

    def bloques():
        yield inicio
        restante = tamano_archivo
        relleno = b"x" * BLOQUE
        while restante > 0:
            n = min(BLOQUE, restante)
            yield relleno if n == BLOQUE else relleno[:n]
            restante -= n
        yield fin

    return f"multipart/form-data; boundary={boundary}", bloques, len(inicio) + tamano_archivo + len(fin)


async def _enviar(ruta, content_type, bloques, content_length=None, metodo="POST"):
    cabeceras = [(b"content-type", content_type.encode()), (b"host", b"testserver")]
    if content_length is not None:
        cabeceras.append((b"content-length", str(content_length).encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": metodo, "scheme": "http", "path": ruta, "raw_path": ruta.encode(),
        "query_string": b"", "root_path": "", "headers": cabeceras,
        "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
    }
    iterador = iter(bloques())
    estado = {"consumidos": 0, "terminado": False}
    pendiente = [next(iterador, None)]

    async def receive():
        if estado["terminado"]:
            return {"type": "http.disconnect"}
        actual = pendiente[0]
        if actual is None:
            estado["terminado"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        siguiente = next(iterador, None)
        pendiente[0] = siguiente
        estado["consumidos"] += len(actual)
        if siguiente is None:
            estado["terminado"] = True
        return {"type": "http.request", "body": actual, "more_body": siguiente is not None}

    respuesta = {"status": None, "cuerpo": b""}

    async def send(mensaje):
        if mensaje["type"] == "http.response.start":
            respuesta["status"] = mensaje["status"]
        elif mensaje["type"] == "http.response.body":
            respuesta["cuerpo"] += mensaje.get("body", b"")

    await main.app(scope, receive, send)
    return respuesta["status"], estado["consumidos"], respuesta["cuerpo"]


def enviar(*args, **kwargs):
    return asyncio.run(_enviar(*args, **kwargs))


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------
def _rutas_de_subida():
    rutas = set()
    for r in main.app.routes:
        if isinstance(r, APIRoute):
            if any(p.annotation is UploadFile for p in inspect.signature(r.endpoint).parameters.values()):
                rutas.add(r.path)
    return rutas


def test_cada_ruta_de_subida_tiene_su_tope():
    print("\n[1] Cada ruta con UploadFile tiene un tope declarado, derivado del tope del propio endpoint")
    tabla = getattr(main, "LIMITES_SUBIDA_POR_RUTA", None)
    comprobar("main.LIMITES_SUBIDA_POR_RUTA existe", isinstance(tabla, dict))
    if not isinstance(tabla, dict):
        return
    from core.branding import TAMANO_MAXIMO_IMAGEN_BYTES
    from core.limite_cuerpo import MARGEN_MULTIPART_BYTES
    from modulos.documentos.crud import TAMANO_MAXIMO_IMAGEN_SECCION_BYTES
    from modulos.superadmin.crud import TAMANO_MAXIMO_EVIDENCIA_BYTES
    from modulos.superadmin.importacion_estudiantes import TAMANO_MAXIMO_BYTES as TAMANO_MAXIMO_EXCEL

    esperado = {
        "/api/admin/personas/consentimiento/{consentimiento_id}/evidencia": TAMANO_MAXIMO_EVIDENCIA_BYTES,
        "/api/admin/personas/{persona_id}/expediente/evidencia": TAMANO_MAXIMO_EVIDENCIA_BYTES,
        "/api/admin/personas/importar/validar": TAMANO_MAXIMO_EXCEL,
        "/api/admin/personas/importar/confirmar": TAMANO_MAXIMO_EXCEL,
        "/api/auth/usuarios/{usuario_id}/firma": TAMANO_MAXIMO_IMAGEN_BYTES,
        "/api/instituciones/{institucion_id}/branding/{tipo}": TAMANO_MAXIMO_IMAGEN_BYTES,
        "/api/documentos/{documento_id}/secciones/{plantilla_seccion_id}/imagen": TAMANO_MAXIMO_IMAGEN_SECCION_BYTES,
    }
    rutas = _rutas_de_subida()
    comprobar("las rutas con UploadFile son exactamente las 7 conocidas", rutas == set(esperado),
              f"nuevas: {sorted(rutas - set(esperado))} faltan: {sorted(set(esperado) - rutas)}" if rutas != set(esperado) else "")
    comprobar("la tabla cubre exactamente las rutas con UploadFile", set(tabla) == rutas,
              f"sin tope: {sorted(rutas - set(tabla))} sobran: {sorted(set(tabla) - rutas)}" if set(tabla) != rutas else "")
    for ruta, tope_endpoint in esperado.items():
        comprobar(f"tope de {ruta} = tope del endpoint + margen multipart",
                  tabla.get(ruta) == tope_endpoint + MARGEN_MULTIPART_BYTES,
                  f"tabla={tabla.get(ruta)} esperado={tope_endpoint + MARGEN_MULTIPART_BYTES}")


def test_content_length_declarado_se_corta_sin_leer():
    print("\n[2] Sin sesión, Content-Length de 20 MB a la ruta de firma: 413 sin leer el cuerpo")
    ct, bloques, largo = _multipart(20 * MB)
    status, consumidos, cuerpo = enviar(RUTA_FIRMA, ct, bloques, content_length=largo)
    comprobar("responde 413", status == 413, f"status={status}")
    comprobar("la app no pidió ni un byte del cuerpo", consumidos == 0, f"consumidos={consumidos}")
    try:
        detalle = json.loads(cuerpo).get("detail", "")
    except ValueError:
        detalle = ""
    comprobar("el 413 trae un detail en español", "tamaño" in detalle, repr(detalle)[:120])


def test_chunked_se_corta_al_superar_el_tope():
    print("\n[3] Sin sesión y sin Content-Length (chunked), 20 MB: 413 apenas se supera el tope")
    ct, bloques, _ = _multipart(20 * MB)
    status, consumidos, _ = enviar(RUTA_FIRMA, ct, bloques, content_length=None)
    tope = getattr(main, "LIMITES_SUBIDA_POR_RUTA", {}).get("/api/auth/usuarios/{usuario_id}/firma", 0)
    comprobar("responde 413", status == 413, f"status={status}")
    comprobar("leyó como mucho el tope más un bloque", 0 < consumidos <= tope + BLOQUE,
              f"consumidos={consumidos} tope={tope}")


def test_archivo_del_tamano_maximo_pasa_el_middleware():
    print("\n[4] Un archivo del tamaño máximo que acepta el endpoint pasa el middleware (y cae en la autenticación)")
    from core.branding import TAMANO_MAXIMO_IMAGEN_BYTES
    ct, bloques, largo = _multipart(TAMANO_MAXIMO_IMAGEN_BYTES)
    status, consumidos, _ = enviar(RUTA_FIRMA, ct, bloques, content_length=largo)
    comprobar("no es 413: llega al endpoint y la autenticación responde 401", status == 401, f"status={status}")
    comprobar("se leyó el cuerpo entero", consumidos == largo, f"consumidos={consumidos} largo={largo}")


def test_cuerpo_json_tiene_tope_por_defecto():
    print("\n[5] Rutas JSON: tope por defecto")
    try:
        from core.limite_cuerpo import LIMITE_CUERPO_POR_DEFECTO_BYTES
    except ImportError:
        LIMITE_CUERPO_POR_DEFECTO_BYTES = None
    comprobar("tope por defecto = 1 MiB", LIMITE_CUERPO_POR_DEFECTO_BYTES == 1 * MB, f"{LIMITE_CUERPO_POR_DEFECTO_BYTES}")
    grande = b'{"token": "' + b"x" * (2 * MB) + b'"}'
    status, consumidos, _ = enviar(RUTA_JSON, "application/json", lambda: iter([grande]), content_length=len(grande))
    comprobar("JSON de 2 MB -> 413 sin leerlo", status == 413 and consumidos == 0, f"status={status} consumidos={consumidos}")
    chico = b"{}"
    status, _, _ = enviar(RUTA_JSON, "application/json", lambda: iter([chico]), content_length=len(chico))
    comprobar("JSON chico sigue su camino normal (422 de validación)", status == 422, f"status={status}")


def test_content_length_invalido():
    print("\n[6] Content-Length que no es un entero no negativo -> 400")
    for valor in ("abc", "-1"):
        status, consumidos, _ = enviar(RUTA_JSON, "application/json", lambda: iter([b"{}"]), content_length=valor)
        comprobar(f"Content-Length={valor!r} -> 400 sin leer", status == 400 and consumidos == 0,
                  f"status={status} consumidos={consumidos}")


def test_versiones_de_los_parsers():
    print("\n[7] Versiones con los avisos de DoS corregidos")
    from importlib.metadata import version
    from packaging.version import Version
    for paquete, minima in (("starlette", "1.3.1"), ("python-multipart", "0.0.31")):
        instalada = version(paquete)
        comprobar(f"{paquete} >= {minima}", Version(instalada) >= Version(minima), f"instalada={instalada}")
    ruta_req = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "requirements.txt")
    with open(ruta_req, encoding="utf-8") as f:
        req = f.read()
    comprobar("requirements.txt fija starlette==1.3.1", "starlette==1.3.1" in req)
    comprobar("requirements.txt fija python-multipart==0.0.31", "python-multipart==0.0.31" in req)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Tope de tamaño del cuerpo antes de autenticar")
    print("=" * 72)
    test_cada_ruta_de_subida_tiene_su_tope()
    test_content_length_declarado_se_corta_sin_leer()
    test_chunked_se_corta_al_superar_el_tope()
    test_archivo_del_tamano_maximo_pasa_el_middleware()
    test_cuerpo_json_tiene_tope_por_defecto()
    test_content_length_invalido()
    test_versiones_de_los_parsers()

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
