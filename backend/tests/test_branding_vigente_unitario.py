"""B6 de la revisión de seguridad (sesión 2026-11-07): el branding servido es
SIEMPRE la última subida — ver core/storage.construir_storage_key_branding_vigente.

Antes la key llevaba la extensión y se servía la primera que existiera en
orden alfabético (.jpeg, .jpg, .png): subir un .png después de un .jpg
dejaba sirviendo el .jpg viejo, en la app y en cada PDF. Sin BD ni servidor:
storage en memoria e institución de mentira, llamando a las funciones reales.

    python -m tests.test_branding_vigente_unitario
"""
import io
import sys
from types import SimpleNamespace

from PIL import Image

import core.storage as storage_mod
from modulos.instituciones import crud

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


class _Storage:
    def __init__(self):
        self.archivos = {}

    def guardar(self, key, contenido, content_type):
        self.archivos[key] = (contenido, content_type)

    def leer(self, key):
        return self.archivos[key][0]

    def existe(self, key):
        return key in self.archivos


class _DB:
    def commit(self):
        pass

    def refresh(self, _obj):
        pass


def imagen(formato, color):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format=formato)
    return buffer.getvalue()


_storage = _Storage()
storage_mod.obtener_storage_service = lambda: _storage
_institucion = SimpleNamespace(id=5, logo_url=None, logo_pie_pagina_url=None, fondo_documento_url=None)
crud.obtener_institucion_por_id = lambda _db, _id: _institucion if _id == 5 else None
DB = _DB()


def test_secuencia_del_bug():
    print("\n[1] .jpg y después .png: se sirve el .png (antes: el .jpg viejo)")
    jpg = imagen("JPEG", "red")
    png = imagen("PNG", "blue")
    crud.subir_imagen_branding(DB, 5, "encabezado", jpg, "logo.jpg", "image/jpeg")
    contenido, tipo = crud.leer_imagen_branding(DB, 5, "encabezado")
    comprobar("tras subir el .jpg se sirve el .jpg", contenido == jpg and tipo == "image/jpeg", tipo)
    crud.subir_imagen_branding(DB, 5, "encabezado", png, "logo.png", "image/png")
    contenido, tipo = crud.leer_imagen_branding(DB, 5, "encabezado")
    comprobar("tras subir el .png se sirve el .png", contenido == png, tipo)
    comprobar("con su tipo real (image/png)", tipo == "image/png", tipo)
    comprobar("una sola key de encabezado en el storage",
              [k for k in _storage.archivos if "/branding/encabezado" in k] == ["instituciones/5/branding/encabezado"],
              list(_storage.archivos))
    crud.subir_imagen_branding(DB, 5, "encabezado", jpg, "logo.JPEG", "image/png")
    contenido, tipo = crud.leer_imagen_branding(DB, 5, "encabezado")
    comprobar("volver a un .jpeg también reemplaza", contenido == jpg and tipo == "image/jpeg", tipo)


def test_compatibilidad():
    print("\n[2] Lo subido antes del cambio (key con extensión) se sigue sirviendo")
    viejo = imagen("PNG", "green")
    _storage.guardar("instituciones/5/branding/pie.png", viejo, "image/png")
    contenido, tipo = crud.leer_imagen_branding(DB, 5, "pie")
    comprobar("pie antiguo (.png) se sirve", contenido == viejo and tipo == "image/png")
    nuevo = imagen("JPEG", "white")
    crud.subir_imagen_branding(DB, 5, "pie", nuevo, "pie.jpg", "image/jpeg")
    contenido, tipo = crud.leer_imagen_branding(DB, 5, "pie")
    comprobar("una subida nueva gana al archivo antiguo", contenido == nuevo and tipo == "image/jpeg", tipo)


def test_otros():
    print("\n[3] Tipos y errores")
    try:
        crud.leer_imagen_branding(DB, 5, "fondo")
        resultado = None
    except Exception as exc:  # noqa: BLE001
        resultado = getattr(exc, "status_code", repr(exc))
    comprobar("tipo sin imagen → 404", resultado == 404, resultado)
    _storage.guardar("instituciones/5/branding/fondo", b"<html>no es imagen</html>", "text/html")
    _, tipo = crud.leer_imagen_branding(DB, 5, "fondo")
    comprobar("bytes que no son imagen → application/octet-stream, nunca text/html",
              tipo == "application/octet-stream", tipo)


if __name__ == "__main__":
    test_secuencia_del_bug()
    test_compatibilidad()
    test_otros()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO BRANDING VIGENTE: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
