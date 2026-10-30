"""🆕 PDF imprimible del MODELO de consentimiento / asentimiento de un colegio
(sesión 2026-10-30) — el documento que se imprime, firma el apoderado (o el
propio alumno, en el asentimiento) y después se sube escaneado como evidencia
del consentimiento (POST /admin/personas/consentimiento/{id}/evidencia, que ya
existía). El texto es el modelo activo que le corresponde al alumno por su
nivel (crud.resolver_texto_consentimiento_activo); los datos del alumno van
precargados y los del apoderado quedan como líneas en blanco para completar
a mano.

Marcadores que el colegio puede escribir dentro de su propio texto y que se
reemplazan aquí con los datos reales (MARCADORES más abajo) — un marcador
desconocido queda tal cual, nunca rompe la generación.
"""
import io
import re
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.pdf_fuentes import registrar_fuentes

FUENTE, FUENTE_BOLD, FUENTE_ITALICA = registrar_fuentes()

PRIMARY = colors.HexColor("#1E3A5F")
GRAY_TEXTO = colors.HexColor("#4A4A4A")
GRAY_L = colors.HexColor("#F4F5F7")
BORDER = colors.HexColor("#D9DCE1")

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Clave del marcador -> clave en `datos`. Documentado también en la pantalla
# de Consentimiento y asentimiento (aurora_ui), para que el colegio los use.
MARCADORES = {
    "alumno": "alumno_nombre",
    "documento_alumno": "alumno_documento",
    "grado_seccion": "grado_seccion",
    "nivel": "nivel",
    "institucion": "institucion_nombre",
    "fecha": "fecha_texto",
}

_PATRON_MARCADOR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def reemplazar_marcadores(texto: str, datos: dict) -> str:
    def _sustituir(m):
        clave = MARCADORES.get(m.group(1))
        if clave is None:
            return m.group(0)
        return str(datos.get(clave) or "________________")
    return _PATRON_MARCADOR.sub(_sustituir, texto)


def generar_pdf_modelo_consentimiento(datos: dict) -> io.BytesIO:
    """`datos`: tipo_texto ("apoderado" | "asentimiento"), version, contenido,
    institucion_nombre, alumno_nombre, alumno_documento, nivel,
    grado_seccion, fecha_texto."""
    es_apoderado = datos["tipo_texto"] == "apoderado"
    titulo = "CONSENTIMIENTO INFORMADO" if es_apoderado else "ASENTIMIENTO INFORMADO"
    subtitulo = (
        "Para la evaluación y el acompañamiento psicológico del estudiante"
        if es_apoderado
        else "Del propio estudiante"
    )

    estilo_inst = ParagraphStyle("inst", fontName=FUENTE_BOLD, fontSize=10, textColor=GRAY_TEXTO, alignment=TA_CENTER)
    estilo_titulo = ParagraphStyle("tit", fontName=FUENTE_BOLD, fontSize=15, textColor=PRIMARY, alignment=TA_CENTER, spaceBefore=4)
    estilo_sub = ParagraphStyle("sub", fontName=FUENTE_ITALICA, fontSize=9.5, textColor=GRAY_TEXTO, alignment=TA_CENTER)
    estilo_cuerpo = ParagraphStyle("cuerpo", fontName=FUENTE, fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
    estilo_celda = ParagraphStyle("celda", fontName=FUENTE, fontSize=9.5, leading=12)
    estilo_celda_b = ParagraphStyle("celdab", fontName=FUENTE_BOLD, fontSize=9.5, leading=12)
    estilo_pie = ParagraphStyle("pie", fontName=FUENTE, fontSize=7.5, textColor=GRAY_TEXTO, alignment=TA_CENTER)
    estilo_firma = ParagraphStyle("firma", fontName=FUENTE, fontSize=9, alignment=TA_CENTER, leading=12)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=2.3 * cm, rightMargin=2.3 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=titulo.title(), author=datos.get("institucion_nombre") or "AuroraSoft",
    )
    el = [
        Paragraph(escape(datos.get("institucion_nombre") or ""), estilo_inst),
        Paragraph(titulo, estilo_titulo),
        Paragraph(subtitulo, estilo_sub),
        Spacer(1, 0.5 * cm),
    ]

    def fila(etiqueta, valor):
        return [Paragraph(escape(etiqueta), estilo_celda_b), Paragraph(escape(valor or "—"), estilo_celda)]

    tabla_alumno = Table(
        [
            fila("Estudiante", datos.get("alumno_nombre")),
            fila("Documento de identidad", datos.get("alumno_documento")),
            fila("Nivel / grado / sección", datos.get("grado_seccion")),
            fila("Fecha", datos.get("fecha_texto")),
        ],
        colWidths=[4.6 * cm, None],
    )
    tabla_alumno.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRAY_L),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el += [tabla_alumno, Spacer(1, 0.55 * cm)]

    # Un párrafo por línea — mismo criterio que la pantalla de edición y el
    # examen público ("Un párrafo por línea").
    contenido = reemplazar_marcadores(datos.get("contenido") or "", datos)
    for linea in contenido.splitlines():
        if linea.strip():
            el.append(Paragraph(escape(linea.strip()), estilo_cuerpo))

    el.append(Spacer(1, 0.4 * cm))

    if es_apoderado:
        # Datos del apoderado: en blanco, se completan a mano al firmar.
        tabla_apoderado = Table(
            [
                fila("Nombres y apellidos del apoderado", ""),
                fila("Documento de identidad", ""),
                fila("Parentesco / relación", ""),
                fila("Teléfono", ""),
            ],
            colWidths=[6 * cm, None],
            rowHeights=[0.85 * cm] * 4,
        )
        tabla_apoderado.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), GRAY_L),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        el += [tabla_apoderado, Spacer(1, 1.6 * cm)]
        firmas = [["", ""], [
            Paragraph("Firma del apoderado", estilo_firma),
            Paragraph("Huella digital", estilo_firma),
        ]]
        anchos = [9 * cm, 4 * cm]
    else:
        el.append(Spacer(1, 1.6 * cm))
        firmas = [["", ""], [
            Paragraph("Firma o nombre del estudiante", estilo_firma),
            Paragraph("Firma del psicólogo(a)", estilo_firma),
        ]]
        anchos = [7 * cm, 7 * cm]

    tabla_firmas = Table(firmas, colWidths=anchos, rowHeights=[1.2 * cm, None], hAlign="CENTER")
    tabla_firmas.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (0, 1), 0.8, colors.black),
        ("LINEABOVE", (1, 1), (1, 1), 0.8, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    el += [tabla_firmas, Spacer(1, 0.9 * cm)]
    el.append(Paragraph(
        escape(
            f"Modelo de {'consentimiento' if es_apoderado else 'asentimiento'} v{datos.get('version')} — "
            "documento generado por AuroraSoft. Una vez firmado, súbalo escaneado como evidencia en la ficha del estudiante."
        ),
        estilo_pie,
    ))

    doc.build(el)
    buffer.seek(0)
    return buffer
