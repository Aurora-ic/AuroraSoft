# core/pdf_fuentes.py
#
# Registro de tipografía compartido entre los generadores de PDF del
# sistema: core/pdf_generator.py (el informe psicométrico) y
# modulos/documentos/pdf_generador.py (el motor de documentos
# institucionales). Arial cuando esté disponible en el servidor —
# registrada desde los archivos de fuente del sistema operativo — con
# Helvetica como sustituto silencioso (métricamente equivalente, el
# estándar de facto de PDF para Arial) cuando no lo esté. Nunca falla el
# arranque por falta de fuentes.
#
# Extraído de core/pdf_generator.py para que los dos generadores compartan
# exactamente la misma lógica de detección/registro sin duplicarla — todo
# lo demás (estilos, tablas, renderizado por sección, encabezado/pie) sigue
# siendo independiente entre ambos, así que un cambio en uno nunca afecta
# al otro.
import logging
import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger("aurorasoft")

_RUTAS_ARIAL = [
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"),
    ("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
     "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
     "/usr/share/fonts/truetype/msttcorefonts/Arial_Italic.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf", "/Library/Fonts/Arial Italic.ttf"),
]

_cache = None


def registrar_fuentes():
    """Registra Arial si la encuentra en el servidor, con Helvetica como
    sustituto silencioso, y devuelve (fuente_regular, fuente_bold,
    fuente_italica). El registro real en reportlab solo ocurre una vez por
    proceso (resultado cacheado en el módulo) — los dos generadores pueden
    llamarla en su propio import sin volver a tocar el disco ni registrar
    la misma fuente dos veces."""
    global _cache
    if _cache is not None:
        return _cache

    fuente, fuente_bold, fuente_italica = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    try:
        for regular, bold, italica in _RUTAS_ARIAL:
            if os.path.isfile(regular) and os.path.isfile(bold):
                pdfmetrics.registerFont(TTFont("Arial", regular))
                pdfmetrics.registerFont(TTFont("Arial-Bold", bold))
                fuente, fuente_bold = "Arial", "Arial-Bold"
                if os.path.isfile(italica):
                    pdfmetrics.registerFont(TTFont("Arial-Italic", italica))
                    fuente_italica = "Arial-Italic"
                break
    except Exception:
        logger.warning("No se pudo registrar Arial; se usará Helvetica (equivalente métrico).", exc_info=True)

    _cache = (fuente, fuente_bold, fuente_italica)
    return _cache
