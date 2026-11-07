"""Pruebas unitarias — Validación del contenido real de las imágenes (A1 de la
revisión de seguridad previa al piloto).

    python -m tests.test_imagen_segura_unitario

Sin BD ni servidor (DATABASE_URL/SECRET_KEY dummy, nunca se conecta).

El problema que cierra: la subida de firma, branding, imagen de sección y
evidencias solo miraba la EXTENSIÓN del nombre y el Content-Type que manda
el cliente. Después, al armar el PDF, Pillow (directo o vía reportlab) abría
esos bytes con TODOS sus formatos y sin tope de píxeles. Ahora
`core/imagen_segura.py` exige PNG/JPEG de verdad, con un tope de píxeles que
se revisa en la cabecera ANTES de decodificar, y lo aplica:
  - al subir (validación completa, content-type del formato real);
  - al dibujar (cabecera; si no pasa, aviso en vez de la imagen), en
    `descargar_logo_seguro` y en los dos renderizadores de anexos de imagen.
"""

import io
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from fastapi import HTTPException  # noqa: E402
from PIL import Image  # noqa: E402

from core import imagen_segura  # noqa: E402
from core.imagen_segura import (  # noqa: E402
    MAXIMO_PIXELES_IMAGEN, dimensiones_imagen_segura, validar_imagen_para_subida,
)

_resultados = []
BACKEND = Path(__file__).resolve().parent.parent


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _imagen(formato, tamano=(40, 30), modo="RGB"):
    buffer = io.BytesIO()
    Image.new(modo, tamano, color=(200, 30, 30) if modo == "RGB" else 1).save(buffer, format=formato)
    return buffer.getvalue()


def _status_de(funcion, *args):
    try:
        funcion(*args)
    except HTTPException as exc:
        return exc.status_code, exc.detail
    return None, None


PNG = _imagen("PNG")
JPEG = _imagen("JPEG")


# ------------------------------------------------------------------
def test_png_y_jpeg_validos_pasan():
    print("\n[1] PNG y JPEG reales pasan, con el content-type del formato real")
    comprobar("PNG con .png -> image/png", validar_imagen_para_subida(PNG, ".png") == "image/png")
    comprobar("JPEG con .jpg -> image/jpeg", validar_imagen_para_subida(JPEG, ".jpg") == "image/jpeg")
    comprobar("JPEG con .jpeg -> image/jpeg", validar_imagen_para_subida(JPEG, ".jpeg") == "image/jpeg")
    comprobar("extensión en mayúsculas se acepta", validar_imagen_para_subida(PNG, ".PNG") == "image/png")


def test_otros_formatos_se_rechazan():
    print("\n[2] Formatos que Pillow SÍ abre pero no aceptamos -> 400 (aunque se llamen .png)")
    for formato in ("GIF", "BMP", "TIFF", "WEBP", "ICO", "PPM"):
        datos = _imagen(formato)
        # Prueba de que el riesgo era real: Pillow sin `formats=` los abre.
        with Image.open(io.BytesIO(datos)) as img:
            abierto_sin_restriccion = img.format
        codigo, _ = _status_de(validar_imagen_para_subida, datos, ".png")
        comprobar(
            f"{formato} disfrazado de .png -> 400 (Pillow sin restricción lo abría como {abierto_sin_restriccion})",
            codigo == 400,
        )
        comprobar(f"{formato}: el PDF lo descarta", dimensiones_imagen_segura(datos) is None)


def test_no_imagenes_se_rechazan():
    print("\n[3] Bytes que no son imagen -> 400")
    casos = {
        "SVG": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "HTML": b"<html><body>hola</body></html>",
        "PDF": b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF",
        "vacío": b"",
        "basura": os.urandom(4096),
    }
    for nombre, datos in casos.items():
        codigo, detalle = _status_de(validar_imagen_para_subida, datos, ".png")
        comprobar(f"{nombre} -> 400", codigo == 400, str(detalle))
        comprobar(f"{nombre}: el PDF lo descarta", dimensiones_imagen_segura(datos) is None)


def test_extension_no_coincide():
    print("\n[4] La extensión del nombre tiene que coincidir con el formato real")
    codigo, detalle = _status_de(validar_imagen_para_subida, PNG, ".jpg")
    comprobar("PNG llamado .jpg -> 400", codigo == 400, str(detalle))
    comprobar("el mensaje dice el formato real y la extensión correcta", "PNG" in str(detalle) and ".png" in str(detalle))
    codigo, _ = _status_de(validar_imagen_para_subida, JPEG, ".png")
    comprobar("JPEG llamado .png -> 400", codigo == 400)


def test_bomba_de_descompresion():
    print("\n[5] Bomba de descompresión: se corta por la cabecera, sin decodificar")
    lado = int(MAXIMO_PIXELES_IMAGEN ** 0.5) + 100  # apenas por encima del tope
    bomba = _imagen("PNG", tamano=(lado, lado), modo="1")
    comprobar(
        f"la bomba pesa poco en disco ({len(bomba) // 1024} KB) y declara {lado}×{lado} px",
        len(bomba) < 3 * 1024 * 1024,
    )
    t0 = time.perf_counter()
    codigo, detalle = _status_de(validar_imagen_para_subida, bomba, ".png")
    duracion = time.perf_counter() - t0
    comprobar("subida -> 400", codigo == 400, str(detalle))
    comprobar("el mensaje habla de megapíxeles", "megapíxeles" in str(detalle))
    comprobar(f"se corta sin decodificar ({duracion * 1000:.0f} ms < 200 ms)", duracion < 0.2)
    comprobar("el PDF la descarta", dimensiones_imagen_segura(bomba) is None)

    justo = int(MAXIMO_PIXELES_IMAGEN ** 0.5) - 10
    en_el_limite = _imagen("PNG", tamano=(justo, justo), modo="1")
    comprobar(f"{justo}×{justo} (bajo el tope) se acepta", validar_imagen_para_subida(en_el_limite, ".png") == "image/png")


def test_imagen_danada():
    print("\n[6] Imagen truncada/dañada -> 400 al subir")
    grande = io.BytesIO()
    Image.effect_noise((600, 600), 80).convert("RGB").save(grande, format="JPEG")
    truncado = grande.getvalue()[: len(grande.getvalue()) // 2]
    codigo, detalle = _status_de(validar_imagen_para_subida, truncado, ".jpg")
    comprobar("JPEG cortado a la mitad -> 400", codigo == 400, str(detalle))

    png_roto = bytearray(_imagen("PNG", tamano=(200, 200)))
    png_roto[60] ^= 0xFF  # dentro del IDAT: falla el CRC
    codigo, _ = _status_de(validar_imagen_para_subida, bytes(png_roto), ".png")
    comprobar("PNG con un byte alterado (CRC) -> 400", codigo == 400)


def test_branding_y_firma():
    print("\n[7] core.branding.validar_imagen_subida (firma y branding)")
    from core import branding
    ext, ct = branding.validar_imagen_subida(JPEG, "membrete.JPG")
    comprobar("devuelve la extensión del nombre y el content-type REAL", (ext, ct) == (".jpg", "image/jpeg"), f"{ext}, {ct}")
    codigo, _ = _status_de(branding.validar_imagen_subida, _imagen("GIF"), "logo.png")
    comprobar("GIF llamado logo.png -> 400", codigo == 400)
    codigo, _ = _status_de(branding.validar_imagen_subida, PNG, "logo.svg")
    comprobar("extensión fuera de la lista blanca -> 400", codigo == 400)
    codigo, _ = _status_de(branding.validar_imagen_subida, b"\0" * (branding.TAMANO_MAXIMO_IMAGEN_BYTES + 1), "x.png")
    comprobar("más de 3 MB -> 400", codigo == 400)

    import inspect
    from modulos.auth import crud as auth_crud
    from modulos.instituciones import crud as inst_crud
    for nombre, funcion in (("subir_firma_usuario", auth_crud.subir_firma_usuario),
                            ("subir_imagen_branding", inst_crud.subir_imagen_branding)):
        fuente = inspect.getsource(funcion)
        comprobar(
            f"{nombre} guarda con el content-type que devuelve la validación",
            "extension, content_type = branding.validar_imagen_subida(contenido, nombre_archivo)" in fuente,
        )


def test_evidencias_y_seccion():
    print("\n[8] Evidencias (consentimiento/expediente) e imagen de sección")
    from modulos.superadmin.crud import _validar_contenido_evidencia
    comprobar(
        "evidencia PNG declarada como application/pdf -> se guarda como image/png",
        _validar_contenido_evidencia(PNG, ".png", "application/pdf") == "image/png",
    )
    codigo, _ = _status_de(_validar_contenido_evidencia, _imagen("BMP"), ".jpg", "image/jpeg")
    comprobar("evidencia BMP llamada .jpg -> 400", codigo == 400)
    # Un .pdf no pasa por la validación de IMAGEN: va a la de PDF (M1,
    # core/pdf_aislado.py — su propio test: test_pdf_aislado_unitario.py).
    from reportlab.pdfgen import canvas as _canvas
    _buffer = io.BytesIO()
    _lienzo = _canvas.Canvas(_buffer)
    _lienzo.showPage()
    _lienzo.save()
    comprobar(
        "evidencia .pdf real -> va por la validación de PDF, no la de imagen",
        _validar_contenido_evidencia(_buffer.getvalue(), ".pdf", "image/png") == "application/pdf",
    )

    import inspect
    from modulos.superadmin import crud as sa_crud
    for nombre in ("guardar_evidencia_consentimiento", "registrar_evidencia_expediente"):
        funcion = getattr(sa_crud, nombre, None)
        if funcion is None:
            candidatas = [n for n, f in inspect.getmembers(sa_crud, inspect.isfunction)
                          if "construir_storage_key_evidencia_expediente" in inspect.getsource(f)]
            funcion = getattr(sa_crud, candidatas[0]) if candidatas else None
            nombre = candidatas[0] if candidatas else nombre
        fuente = inspect.getsource(funcion) if funcion else ""
        comprobar(f"{nombre} valida el contenido antes de guardar",
                  fuente.find("_validar_contenido_evidencia(") != -1
                  and fuente.find("_validar_contenido_evidencia(") < fuente.find(".guardar("))

    from modulos.documentos import crud as doc_crud
    fuente = inspect.getsource(doc_crud.guardar_imagen_seccion)
    comprobar("guardar_imagen_seccion valida el contenido antes de guardar",
              fuente.find("validar_imagen_para_subida(") != -1
              and fuente.find("validar_imagen_para_subida(") < fuente.find(".guardar("))


def test_descarga_de_logo_descarta_no_imagenes():
    print("\n[9] descargar_logo_seguro: el servidor remoto dice image/png, pero los bytes mandan")
    from core import url_segura

    class _Respuesta:
        status = 200

        def __init__(self, cuerpo):
            self._cuerpo = cuerpo

        def getheader(self, nombre):
            return "image/png" if nombre == "Content-Type" else None

        def read(self, n):
            return self._cuerpo[:n]

    class _Conexion:
        def __init__(self, cuerpo):
            self._cuerpo = cuerpo

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return _Respuesta(self._cuerpo)

        def close(self):
            pass

    original = url_segura._abrir_conexion
    resolver = lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))]  # noqa: E731
    try:
        for nombre, cuerpo, esperado in (
            ("PNG real", PNG, PNG),
            ("GIF con Content-Type image/png", _imagen("GIF"), None),
            ("HTML con Content-Type image/png", b"<html></html>", None),
        ):
            url_segura._abrir_conexion = lambda host, ip, timeout, c=cuerpo: _Conexion(c)
            obtenido = url_segura.descargar_logo_seguro("https://logos.example.org/logo.png", resolver=resolver)
            comprobar(f"{nombre} -> {'se usa' if esperado else 'se descarta'}", obtenido == esperado)
    finally:
        url_segura._abrir_conexion = original


def test_renderizadores_de_anexos():
    print("\n[10] Al dibujar el PDF: imagen válida se embebe, inválida deja un aviso")
    from reportlab.platypus import Image as RLImage, Paragraph
    from core import pdf_generator

    estilos = pdf_generator._construir_estilos()
    elementos = pdf_generator._elemento_anexo_imagen({"titulo": "Dibujo", "bytes": PNG}, estilos)
    comprobar("informe: anexo PNG -> Image de reportlab", any(isinstance(e, RLImage) for e in elementos))
    elementos = pdf_generator._elemento_anexo_imagen({"titulo": "Dibujo", "bytes": _imagen("GIF")}, estilos)
    comprobar("informe: anexo GIF -> sin Image, con aviso",
              not any(isinstance(e, RLImage) for e in elementos)
              and any(isinstance(e, Paragraph) and "PNG o JPEG" in e.getPlainText() for e in elementos))

    from modulos.documentos import pdf_generador as doc_pdf
    import core.storage as storage_mod

    class _StorageFalso:
        def __init__(self, datos):
            self.datos = datos

        def leer(self, key):
            return self.datos

    original = storage_mod.obtener_storage_service
    estilos_doc, _, _ = doc_pdf._construir_estilos({})
    try:
        storage_mod.obtener_storage_service = lambda: _StorageFalso(JPEG)
        elementos = doc_pdf._renderizar_imagen_anexo({"storage_key": "x/y.jpg"}, estilos_doc)
        comprobar("documento: sección JPEG -> Image de reportlab", any(isinstance(e, RLImage) for e in elementos))
        storage_mod.obtener_storage_service = lambda: _StorageFalso(_imagen("TIFF"))
        elementos = doc_pdf._renderizar_imagen_anexo({"storage_key": "x/y.png"}, estilos_doc)
        comprobar("documento: sección TIFF (subida antes del cambio) -> aviso, sin Image",
                  not any(isinstance(e, RLImage) for e in elementos)
                  and any("PNG o JPEG" in e.getPlainText() for e in elementos if isinstance(e, Paragraph)))
    finally:
        storage_mod.obtener_storage_service = original


def test_no_queda_image_open_sin_restringir():
    print("\n[11] Ningún Image.open sin formats= en el código de la app")
    sospechosos = []
    for carpeta in ("core", "modulos", "tareas"):
        for archivo in (BACKEND / carpeta).rglob("*.py"):
            for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\bImage\.open\(", linea) and "formats=" not in linea and not linea.lstrip().startswith("#"):
                    sospechosos.append(f"{archivo.relative_to(BACKEND)}:{n}")
    comprobar("cero llamadas sin restricción", not sospechosos, ", ".join(sospechosos))
    comprobar("imagen_segura restringe a PNG/JPEG", imagen_segura.FORMATOS_IMAGEN_PERMITIDOS == ("PNG", "JPEG"))


def test_version_pillow():
    print("\n[12] Pillow en la versión que corrige sus avisos")
    import PIL
    instalada = tuple(int(p) for p in PIL.__version__.split(".")[:2])
    comprobar(f"Pillow instalada >= 13.0 ({PIL.__version__})", instalada >= (13, 0))
    requisitos = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    comprobar("requirements.txt fija pillow==13.0.0", re.search(r"^pillow==13\.0\.0$", requisitos, re.M) is not None)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Contenido real de las imágenes (PNG/JPEG, tope de píxeles)")
    print("=" * 72)
    test_png_y_jpeg_validos_pasan()
    test_otros_formatos_se_rechazan()
    test_no_imagenes_se_rechazan()
    test_extension_no_coincide()
    test_bomba_de_descompresion()
    test_imagen_danada()
    test_branding_y_firma()
    test_evidencias_y_seccion()
    test_descarga_de_logo_descarta_no_imagenes()
    test_renderizadores_de_anexos()
    test_no_queda_image_open_sin_restringir()
    test_version_pillow()

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
