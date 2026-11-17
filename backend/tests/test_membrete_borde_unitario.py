"""Pruebas unitarias — membrete y pie de los documentos institucionales
pegados al borde de la hoja (2026-11-17, observación del piloto).

    python -m tests.test_membrete_borde_unitario

Sin BD ni servidor. Dibuja el marco de página sobre un canvas espía (anota
cada drawImage) y genera PDFs reales para confirmar dónde empieza el texto.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from PIL import Image  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402

from modulos.documentos import pdf_generador as g  # noqa: E402

_resultados = []
ANCHO, ALTO = A4
TOL = 0.5  # puntos


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion)))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def _png(w, h):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (20, 60, 140)).save(b, "PNG")
    return b.getvalue()


def _reader(w, h):
    return ImageReader(io.BytesIO(_png(w, h)))


class _CanvasEspia:
    def __init__(self):
        self.imagenes = []

    def saveState(self):
        pass

    def restoreState(self):
        pass

    def drawImage(self, reader, x, y, width, height, **kw):
        self.imagenes.append((x, y, width, height))


def test_membrete_ancho_pegado_arriba():
    print("\nMembrete ancho (banner): a todo el ancho y pegado al borde superior")
    c = _CanvasEspia()
    g._dibujar_marco_pagina(c, None, _reader(2480, 420), None)
    x, y, w, h = c.imagenes[0]
    comprobar("Empieza en el borde izquierdo", abs(x) < TOL, f"x={x}")
    comprobar("Ocupa todo el ancho de la hoja", abs(w - ANCHO) < TOL, f"w={w}")
    comprobar("Su borde superior es el borde de la hoja", abs(y + h - ALTO) < TOL, f"y+h={y + h}")
    comprobar("No se deforma (misma proporción)", abs(w / h - 2480 / 420) < 0.01)


def test_pie_ancho_pegado_abajo():
    print("\nPie ancho: a todo el ancho y pegado al borde inferior")
    c = _CanvasEspia()
    g._dibujar_marco_pagina(c, None, None, _reader(2480, 260))
    x, y, w, h = c.imagenes[0]
    comprobar("Su borde inferior es el borde de la hoja", abs(y) < TOL, f"y={y}")
    comprobar("Ocupa todo el ancho de la hoja", abs(w - ANCHO) < TOL, f"w={w}")


def test_logo_cuadrado_con_tope():
    print("\nLogo cuadrado: pegado arriba, centrado y con tope de alto")
    c = _CanvasEspia()
    g._dibujar_marco_pagina(c, None, _reader(900, 900), None)
    x, y, w, h = c.imagenes[0]
    comprobar("Un logo (no franja) usa el tope de logo: 3 cm", h <= g.ALTO_MAX_LOGO + TOL, f"h={h}")
    comprobar("Pegado al borde superior", abs(y + h - ALTO) < TOL)
    comprobar("Centrado", abs(x + w / 2 - ANCHO / 2) < TOL)


def test_franja_muy_alta_tiene_tope():
    print("\nUna franja ancha pero muy alta no pasa de 4,5 cm")
    c = _CanvasEspia()
    g._dibujar_marco_pagina(c, None, _reader(1800, 590), None)  # 3,05:1 -> 6,7 cm a todo el ancho
    x, y, w, h = c.imagenes[0]
    comprobar("Alto limitado al tope de franja", abs(h - g.ALTO_MAX_MEMBRETE) < TOL, f"h={h}")
    comprobar("Sigue pegada al borde superior", abs(y + h - ALTO) < TOL)


def test_margenes_del_texto():
    print("\nEl texto empieza justo debajo del membrete y termina justo encima del pie")
    enc, pie = _reader(2480, 420), _reader(2480, 260)
    arriba, abajo = g.margenes_por_membrete(enc, pie)
    alto_enc = ANCHO * 420 / 2480
    alto_pie = ANCHO * 260 / 2480
    comprobar("Margen superior = membrete + separación", abs(arriba - (alto_enc + g.SEPARACION_TEXTO)) < TOL, f"{arriba}")
    comprobar("Margen inferior = pie + separación", abs(abajo - (alto_pie + g.SEPARACION_TEXTO)) < TOL, f"{abajo}")
    sin = g.margenes_por_membrete(None, None)
    comprobar("Sin imágenes: margen normal arriba y abajo", sin == (g.MARGEN_SIN_IMAGEN, g.MARGEN_SIN_IMAGEN))
    comprobar("Sin imágenes no se dibuja nada", not (lambda c: (g._dibujar_marco_pagina(c, None, None, None), c.imagenes)[1])(_CanvasEspia()))


def test_pdf_real():
    print("\nPDF real: se genera con membrete, pie y sin ellos")
    from pypdf import PdfReader
    imagenes = {"m": _png(2480, 420), "p": _png(2480, 260)}
    original = g.descargar_logo_seguro
    g.descargar_logo_seguro = lambda url: imagenes.get(url)
    try:
        for etiqueta, inst in [("con membrete y pie", {"logo_url": "m", "logo_pie_pagina_url": "p"}), ("sin imágenes", {})]:
            contenido = {"documento": {"titulo": "Informe"}, "plantilla": {}, "institucion": inst,
                         "secciones": [{"tipo_seccion": "texto_libre", "titulo": "Motivo", "datos": {"texto": "Texto " * 400}}]}
            pdf = PdfReader(g.generar_pdf_documento(contenido))
            texto = " ".join(p.extract_text() for p in pdf.pages)
            comprobar(f"{etiqueta}: el PDF se genera y trae el texto", "MOTIVO" in texto and len(pdf.pages) >= 1)
    finally:
        g.descargar_logo_seguro = original


if __name__ == "__main__":
    test_membrete_ancho_pegado_arriba()
    test_pie_ancho_pegado_abajo()
    test_logo_cuadrado_con_tope()
    test_franja_muy_alta_tiene_tope()
    test_margenes_del_texto()
    test_pdf_real()
    total, ok = len(_resultados), sum(1 for _, b in _resultados if b)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {ok}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(0 if ok == total else 1)
