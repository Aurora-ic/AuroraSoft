# ============================================================
# GENERADOR DE INFORMES PSICOMÉTRICOS PROFESIONALES - AuroraSoft
# Archivo: core/pdf_generator.py
# ============================================================
#
# Construye el documento a partir de UN dict `contenido` (ver
# modulos/educativo/crud.py:construir_contenido_pdf) que ya distingue las
# tres fuentes de contenido del informe — automático, configurado por la
# prueba/baremo, y escrito por el profesional — y que nunca inventa texto
# clínico que falte en ninguna de las tres (ver "NO INVENTAR CONTENIDO").
#
# Estructura fija (no eliminar la numeración, es parte del contrato con el
# usuario): 1. Filiación, 2. Motivo de consulta, 3. Técnicas e instrumento,
# 4. Observación conductual, 5. Resultados (5.1/5.2/5.3), 6. Conclusiones,
# 7. Recomendaciones, Firma. El CONTENIDO de cada sección cambia según los
# resultados reales; la ESTRUCTURA es estable y reutilizable para cualquier
# prueba futura — nada aquí menciona PHQ-9 ni ningún instrumento concreto.
#
# 🆕 Sección ANEXOS (opcional, tras la firma) — evidencia del expediente
# clínico (EntradaExpediente tipo='evidencia') que el psicólogo marcó para
# incrustarse en ESTE informe (`contenido["anexos"]`, poblado por modulos/
# educativo/crud.py:obtener_anexos_evidencia_informe). Vacío para cualquier
# informe sin evidencia marcada — no cambia nada de lo anterior.

import io
import logging
from functools import partial
from html import escape

logger = logging.getLogger("aurorasoft")

# 🧵 C-10 — Sin matplotlib.pyplot. pyplot mantiene una "figura actual" GLOBAL
# y cada plt.bar()/plt.title() actúa sobre ella: los endpoints síncronos de
# FastAPI corren en un pool de hilos, así que dos informes simultáneos podían
# dibujar uno en la figura del otro. Figure + FigureCanvasAgg dan a cada
# petición su propia figura y su propio renderizador, sin estado compartido.
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from core.url_segura import descargar_logo_seguro

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ============================================================
# TIPOGRAFÍA — Arial cuando esté disponible en el servidor, Helvetica como
# sustituto (métricamente equivalente y el estándar de facto de PDF para
# Arial) cuando no lo esté. Nunca falla el arranque por falta de fuentes:
# un servidor Linux de producción sin Arial instalada sigue generando
# informes correctos, solo que con Helvetica. El registro real vive en
# core/pdf_fuentes.py, compartido con modulos/documentos/pdf_generador.py
# — no duplicar esta lógica si hace falta tocarla.
# ============================================================
from core.pdf_fuentes import registrar_fuentes

FUENTE, FUENTE_BOLD, FUENTE_ITALICA = registrar_fuentes()


# ── PALETA — sobria, de informe clínico formal, no de dashboard ──
DARK = colors.HexColor("#1A1F2B")
PRIMARY = colors.HexColor("#1E3A5F")
GRAY_TEXTO = colors.HexColor("#4A4A4A")
GRAY_L = colors.HexColor("#F4F5F7")
BORDER = colors.HexColor("#D9DCE1")
WHITE = colors.HexColor("#FFFFFF")
ALERTA_FONDO = colors.HexColor("#FBEAEA")
ALERTA_TEXTO = colors.HexColor("#7A1F1F")

_ETIQUETA_ORIGEN_ALERTA = {
    "baremo": "Baremo",
    "regla": "Regla de interpretación",
    "baremo,regla": "Baremo + Regla de interpretación",
}


def formatear_puntaje(valor) -> str:
    """🔢 C-1 — 6.0 -> "6", 5.25 -> "5.25", sin notación científica ni ceros de más."""
    if valor is None:
        return "-"
    try:
        texto = f"{round(float(valor), 4):.4f}"
    except (TypeError, ValueError):
        return str(valor)
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def formatear_fecha(valor) -> str:
    if valor is None:
        return "No registrado"
    if isinstance(valor, str):
        return valor
    try:
        return valor.strftime("%d de %B de %Y").replace(
            "January", "enero").replace("February", "febrero").replace("March", "marzo") \
            .replace("April", "abril").replace("May", "mayo").replace("June", "junio") \
            .replace("July", "julio").replace("August", "agosto").replace("September", "septiembre") \
            .replace("October", "octubre").replace("November", "noviembre").replace("December", "diciembre")
    except AttributeError:
        return str(valor)


def generar_grafico_barras(puntajes: dict, titulo: str) -> io.BytesIO:
    """Gráfico de barras del perfil de puntajes por dimensión."""
    try:
        etiquetas = list(puntajes.keys())
        valores = [float(v) for v in puntajes.values()]

        figura = Figure(figsize=(6, 3))
        FigureCanvasAgg(figura)          # renderizador propio de esta petición
        ejes = figura.add_subplot(111)

        barras = ejes.bar(etiquetas, valores, color='#1E3A5F', edgecolor='black', linewidth=0.5)
        ejes.set_title(titulo, fontsize=11, fontweight='bold')
        ejes.set_ylabel("Puntaje")
        ejes.grid(axis='y', linestyle='--', alpha=0.5)

        for barra in barras:
            yval = barra.get_height()
            ejes.text(barra.get_x() + barra.get_width() / 2, yval + 0.5,
                      formatear_puntaje(yval), ha='center', va='bottom', fontsize=9)

        buf = io.BytesIO()
        figura.savefig(buf, format='png', bbox_inches='tight', dpi=300)
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Error generando gráfico de barras en PDF: {e}", exc_info=True)
        raise e


# ============================================================
# ENCABEZADO / PIE DE PÁGINA — dibujados directamente sobre el canvas en
# CADA página (no son "flowables": deben repetirse idénticos, no desplazarse
# con el contenido). El aviso de confidencialidad va en el encabezado de
# todas las páginas, no solo la primera.
# ============================================================
def _dibujar_marco_pagina(canvas_obj, doc, nombre_institucion, nombre_prueba):
    canvas_obj.saveState()
    ancho, alto = A4

    canvas_obj.setFont(FUENTE_BOLD, 9)
    canvas_obj.setFillColor(DARK)
    canvas_obj.drawString(2 * cm, alto - 1.3 * cm, nombre_institucion or "AuroraSoft")

    canvas_obj.setFont(FUENTE, 8)
    canvas_obj.setFillColor(GRAY_TEXTO)
    canvas_obj.drawRightString(ancho - 2 * cm, alto - 1.3 * cm, "DOCUMENTO CONFIDENCIAL")

    canvas_obj.setStrokeColor(BORDER)
    canvas_obj.setLineWidth(0.7)
    canvas_obj.line(2 * cm, alto - 1.5 * cm, ancho - 2 * cm, alto - 1.5 * cm)

    canvas_obj.line(2 * cm, 1.6 * cm, ancho - 2 * cm, 1.6 * cm)
    canvas_obj.setFont(FUENTE, 8)
    canvas_obj.setFillColor(GRAY_TEXTO)
    canvas_obj.drawString(2 * cm, 1.2 * cm, f"Informe Psicométrico — {nombre_prueba}")
    canvas_obj.drawRightString(ancho - 2 * cm, 1.2 * cm, f"Página {canvas_obj.getPageNumber()}")

    canvas_obj.restoreState()


# 🆕 FIRMA DEL PSICÓLOGO — no implementada todavía (ver sección 22 del
# encargo). Cuando exista imagen de firma/sello, el lugar natural para
# superponerla es aquí: reemplazar el bloque "FIRMA" de generar_pdf() por un
# reportlab.platypus.Image apuntando al archivo descargado de un
# StorageService (nunca un BLOB en Postgres), con el mismo patrón anti-SSRF
# que ya usa el logo institucional (descargar_logo_seguro).

# ============================================================
# ESTILOS
# ============================================================
def _construir_estilos():
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "TituloInforme", parent=base["Heading1"], fontName=FUENTE_BOLD, fontSize=16,
            textColor=PRIMARY, alignment=TA_CENTER, spaceAfter=4, spaceBefore=0,
        ),
        "subtitulo_centro": ParagraphStyle(
            "SubtituloCentro", parent=base["Normal"], fontName=FUENTE, fontSize=10,
            textColor=GRAY_TEXTO, alignment=TA_CENTER, spaceAfter=2,
        ),
        "seccion": ParagraphStyle(
            "Seccion", parent=base["Heading2"], fontName=FUENTE_BOLD, fontSize=12.5,
            textColor=PRIMARY, spaceBefore=14, spaceAfter=8, keepWithNext=True,
        ),
        "subseccion": ParagraphStyle(
            "Subseccion", parent=base["Heading3"], fontName=FUENTE_BOLD, fontSize=11,
            textColor=DARK, spaceBefore=10, spaceAfter=6, keepWithNext=True,
        ),
        "normal": ParagraphStyle(
            "NormalJustificado", parent=base["Normal"], fontName=FUENTE, fontSize=11,
            leading=15, alignment=TA_JUSTIFY, spaceAfter=8,
        ),
        "normal_izq": ParagraphStyle(
            "NormalIzquierda", parent=base["Normal"], fontName=FUENTE, fontSize=11,
            leading=15, alignment=TA_LEFT, spaceAfter=6,
        ),
        "pendiente": ParagraphStyle(
            "ContenidoPendiente", parent=base["Normal"], fontName=FUENTE_ITALICA, fontSize=10,
            leading=14, alignment=TA_LEFT, textColor=GRAY_TEXTO, spaceAfter=8,
        ),
        "aviso_fuente": ParagraphStyle(
            "AvisoFuente", parent=base["Normal"], fontName=FUENTE_ITALICA, fontSize=8.5,
            leading=11, textColor=GRAY_TEXTO, spaceAfter=10,
        ),
        "dimension_nombre": ParagraphStyle(
            "DimensionNombre", parent=base["Normal"], fontName=FUENTE_BOLD, fontSize=11,
            textColor=DARK, spaceBefore=8, spaceAfter=3,
        ),
        "alerta_banner": ParagraphStyle(
            "AlertaBanner", parent=base["Normal"], fontName=FUENTE_BOLD, fontSize=10.5,
            textColor=ALERTA_TEXTO, backColor=ALERTA_FONDO, alignment=TA_CENTER,
            borderPadding=7, spaceAfter=10,
        ),
        "firma_linea": ParagraphStyle(
            "FirmaLinea", parent=base["Normal"], fontName=FUENTE, fontSize=11,
            alignment=TA_CENTER, spaceAfter=2,
        ),
        "firma_nombre": ParagraphStyle(
            "FirmaNombre", parent=base["Normal"], fontName=FUENTE_BOLD, fontSize=11,
            alignment=TA_CENTER, spaceAfter=1,
        ),
    }


_ESTILO_CELDA_TABLA = ParagraphStyle(
    "TablaCelda", fontName=FUENTE, fontSize=9, leading=11, textColor=DARK,
)
_ESTILO_ENCABEZADO_TABLA = ParagraphStyle(
    "TablaEncabezado", fontName=FUENTE_BOLD, fontSize=9, leading=11, textColor=WHITE,
)


def _tabla_sobria(filas, col_widths, resaltar_encabezado=True):
    """Tabla genérica (resultados 5.1, orígenes de alerta 5.3, etc.).

    🔧 Cada celda se envuelve en un Paragraph (nunca un string plano): una
    Table de reportlab NO hace word-wrap de strings planos — si el contenido
    no cabe en el ancho de columna, se desborda por encima de la fila
    siguiente en vez de partirse en varias líneas, exactamente el bug
    reportado con los nombres de dimensión largos de CHASIDE ("Intereses —
    H: Humanísticas, Ciencias Jurídicas y Ciencias Sociales"). Con Paragraph,
    reportlab mide el texto, lo envuelve a varias líneas dentro del ancho
    fijo de la columna, y crece la ALTURA de esa fila en consecuencia — las
    filas ya no pueden solaparse entre sí sin importar cuán largo sea el
    texto. escape() por la misma razón que el resto del archivo: el texto
    deja de ser un string plano y pasa a interpretarse como markup limitado.
    """
    filas_envueltas = []
    for num_fila, fila in enumerate(filas):
        estilo_fila = _ESTILO_ENCABEZADO_TABLA if (resaltar_encabezado and num_fila == 0) else _ESTILO_CELDA_TABLA
        filas_envueltas.append([
            Paragraph(escape(str(valor)), estilo_fila) if valor is not None else ""
            for valor in fila
        ])

    estilo = [
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]
    if resaltar_encabezado:
        estilo += [('BACKGROUND', (0, 0), (-1, 0), PRIMARY)]
    tabla = Table(filas_envueltas, colWidths=col_widths)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _bloque_contenido(bloque: dict | None, estilos, placeholder: str) -> list:
    """Renderiza un bloque {"texto":..., "fuente": "profesional"|"configurado"|None}.

    Si viene de configuración (no del profesional), añade un aviso pequeño
    para que nadie lo confunda con algo que el psicólogo escribió a mano —
    ver "FUENTES DE CONTENIDO DEL INFORME". Si no hay texto en ninguna
    fuente, señala explícitamente que falta — nunca se inventa contenido.
    """
    elementos = []
    if not bloque or not bloque.get("texto"):
        elementos.append(Paragraph(escape(placeholder), estilos["pendiente"]))
        return elementos
    texto_seguro = escape(bloque["texto"]).replace("\n", "<br/>")
    elementos.append(Paragraph(texto_seguro, estilos["normal"]))
    if bloque.get("fuente") == "configurado":
        elementos.append(Paragraph(
            "Texto sugerido según la configuración de la prueba. Pendiente de validación profesional.",
            estilos["aviso_fuente"],
        ))
    return elementos


def _encabezado_anexo(anexo: dict, estilos) -> list:
    """Título/fecha/descripción de un anexo de evidencia — compartido por
    el anexo de tipo imagen (se intercala tal cual en el flujo del propio
    documento) y la portada de un anexo tipo PDF (ver _portada_anexo_pdf,
    que arma un PDF de una sola página con exactamente este mismo bloque)."""
    elementos = [Paragraph(escape(anexo.get("titulo") or "Evidencia"), estilos["subseccion"])]
    if anexo.get("fecha"):
        elementos.append(Paragraph(f"Fecha: {formatear_fecha(anexo['fecha'])}", estilos["normal_izq"]))
    if anexo.get("descripcion"):
        elementos.append(Paragraph(escape(anexo["descripcion"]).replace("\n", "<br/>"), estilos["normal"]))
    return elementos


def _elemento_anexo_imagen(anexo: dict, estilos) -> list:
    """Evidencia tipo imagen, embebida directamente en el flujo del propio
    documento — mismo cálculo de aspecto que modulos/documentos/
    pdf_generador.py:_renderizar_imagen_anexo (no duplicar la lógica, solo
    el mismo criterio: PIL para no deformar, con un tamaño fijo de reserva
    si PIL no puede abrir el archivo)."""
    elementos = _encabezado_anexo(anexo, estilos)
    buffer = io.BytesIO(anexo["bytes"])
    try:
        from PIL import Image as PILImage
        with PILImage.open(buffer) as img:
            ancho_px, alto_px = img.size
        buffer.seek(0)
        ancho_max = 15 * cm
        alto = ancho_max * (alto_px / ancho_px) if ancho_px else 10 * cm
        alto_max = 19 * cm
        if alto > alto_max:
            alto = alto_max
            ancho_max = alto_max * (ancho_px / alto_px) if alto_px else ancho_max
        elementos.append(Image(buffer, width=ancho_max, height=alto))
    except Exception:
        buffer.seek(0)
        elementos.append(Image(buffer, width=15 * cm, height=15 * cm))
    return elementos


def _portada_anexo_pdf(anexo: dict) -> io.BytesIO:
    """PDF de una sola página con título/fecha/descripción de un anexo tipo
    'pdf' — se antepone a sus propias páginas cuando se fusiona al final de
    generar_pdf() (ver bloque ANEXOS). Un documento aparte y minúsculo en
    vez de una página más de `elementos`: a diferencia de una imagen, un PDF
    externo no es un flowable de reportlab, se fusiona con pypdf DESPUÉS de
    doc.build() — necesita sus propios bytes de PDF, no puede vivir a mitad
    de la lista `elementos`."""
    estilos = _construir_estilos()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2.3 * cm, bottomMargin=2.3 * cm,
    )
    doc.build(_encabezado_anexo(anexo, estilos))
    buffer.seek(0)
    return buffer


def _fusionar_anexos_pdf(buffer_base: io.BytesIO, anexos_pdf: list[dict]) -> io.BytesIO:
    """Agrega, al final del PDF ya construido, cada anexo tipo 'pdf' completo
    (todas sus páginas, precedidas por su propia portada de una página) — la
    única forma de incluir un archivo PDF ajeno dentro de este documento:
    reportlab solo sabe dibujar flowables propios, nunca páginas de otro PDF,
    así que esto corre DESPUÉS de doc.build(), con pypdf, nunca antes."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for pagina in PdfReader(buffer_base).pages:
        writer.add_page(pagina)
    for anexo in anexos_pdf:
        for pagina in PdfReader(_portada_anexo_pdf(anexo)).pages:
            writer.add_page(pagina)
        for pagina in PdfReader(io.BytesIO(anexo["bytes"])).pages:
            writer.add_page(pagina)

    buffer_final = io.BytesIO()
    writer.write(buffer_final)
    buffer_final.seek(0)
    return buffer_final


def generar_pdf(contenido: dict) -> io.BytesIO:
    """Construye el informe psicométrico profesional completo a partir de
    `contenido` (ver modulos/educativo/crud.py:construir_contenido_pdf).

    La ESTRUCTURA (1..7 + firma) es fija y reutilizable para cualquier
    prueba; el CONTENIDO de cada sección varía según los resultados reales
    de cada estudiante — nada de esta función es específico de PHQ-9 ni de
    ningún otro instrumento.
    """
    try:
        institucion = contenido.get("institucion") or {}
        nombre_institucion = institucion.get("nombre")
        nombre_prueba = contenido.get("nombre_prueba") or "Evaluación Psicométrica"
        filiacion = contenido.get("filiacion") or {}
        dimensiones = contenido.get("dimensiones") or []
        analisis_riesgo = contenido.get("analisis_riesgo") or {}
        firma = contenido.get("firma") or {}

        estilos = _construir_estilos()
        elementos = []

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2.3 * cm, bottomMargin=2.3 * cm,
        )

        # ── ENCABEZADO DEL CUERPO (logo + título) ──
        logo_url = institucion.get("logo_url")
        if logo_url:
            logo_bytes = descargar_logo_seguro(logo_url)
            if logo_bytes:
                try:
                    elementos.append(Image(io.BytesIO(logo_bytes), width=2.6 * cm, height=2.6 * cm))
                    elementos.append(Spacer(1, 0.2 * cm))
                except Exception as exc:
                    logger.warning("El logo institucional no es una imagen válida: %s", exc)

        # 🆕 Revisión crítica de contenido (PHQ-9/GAD-7): el subtítulo bajo el
        # título ("Prueba aplicada: X" / "Versión del informe: vN...") se
        # quitó del cuerpo del informe — no es información que deba aparecer
        # ahí, a pedido explícito. El nombre del instrumento sigue presente
        # en la sección "3. TÉCNICAS E INSTRUMENTO APLICADO" (nunca se perdió,
        # solo dejó de duplicarse bajo el título) y en el pie de página de
        # cada hoja (`_dibujar_marco_pagina`, sin cambios). La metadata de
        # versión/reemisión sigue existiendo y siendo consultable — nunca se
        # dejó de registrar, solo se dejó de IMPRIMIR en la cara del PDF — vía
        # `GET /inscripciones/{id}/informe` (el historial de versiones que ya
        # usa el panel "Pruebas aplicadas" de la ficha del alumno, ver
        # docs/informes-psicometricos.md).
        elementos.append(Paragraph("INFORME PSICOMÉTRICO", estilos["titulo"]))
        elementos.append(Spacer(1, 0.4 * cm))

        if analisis_riesgo.get("es_alerta"):
            elementos.append(Paragraph(
                "RESULTADO CON INDICADOR DE ALERTA — REQUIERE REVISIÓN PROFESIONAL",
                estilos["alerta_banner"],
            ))
        if analisis_riesgo.get("estado_interpretacion") == "incompleta":
            elementos.append(Paragraph(
                "INTERPRETACIÓN INCOMPLETA — ESTE RESULTADO NO DEBE LEERSE COMO 'SIN RIESGO'",
                estilos["alerta_banner"],
            ))
        elementos.append(Spacer(1, 0.3 * cm))

        # ── 1. DATOS DE FILIACIÓN ──
        filas_filiacion = [["Campo", "Información"]]
        _no_reg = "No registrado"

        def _v(x):
            return escape(str(x)) if x not in (None, "") else _no_reg

        filas_filiacion.append(["Apellidos y Nombres", _v(filiacion.get("apellidos_nombres"))])
        # 🆕 Informante — None para el autorreporte de siempre (no imprime
        # nada nuevo en ningún informe existente). Cuando la prueba la
        # respondió un padre/madre o un docente ACERCA del estudiante de
        # arriba, el informe debe decirlo explícitamente: nunca puede leerse
        # como si el propio estudiante hubiera contestado.
        if filiacion.get("informante_tipo"):
            etiqueta_informante = (
                "Padre/Madre o apoderado" if filiacion["informante_tipo"] == "padre_madre" else "Docente"
            )
            texto_informante = _v(filiacion.get("informante_nombre"))
            if filiacion.get("informante_relacion"):
                texto_informante += f" ({escape(str(filiacion['informante_relacion']))})"
            filas_filiacion.append([f"Informante ({etiqueta_informante})", texto_informante])
        filas_filiacion.append(["Edad", f"{filiacion['edad']} años" if filiacion.get("edad") is not None else _no_reg])
        filas_filiacion.append(["Grado de instrucción", _v(filiacion.get("grado_instruccion"))])
        filas_filiacion.append(["Ocupación actual", _v(filiacion.get("ocupacion_actual"))])
        filas_filiacion.append(["Vive con", _v(filiacion.get("vive_con"))])
        filas_filiacion.append(["Fecha de evaluación", formatear_fecha(filiacion.get("fecha_evaluacion"))])
        filas_filiacion.append(["Evaluador", _v(filiacion.get("evaluador"))])

        elementos.append(KeepTogether([
            Paragraph("1. DATOS DE FILIACIÓN", estilos["seccion"]),
            _tabla_sobria(filas_filiacion, [6 * cm, 10 * cm]),
        ]))
        elementos.append(Spacer(1, 0.3 * cm))

        # ── 2. MOTIVO DE CONSULTA ──
        elementos.append(KeepTogether(
            [Paragraph("2. MOTIVO DE CONSULTA", estilos["seccion"])]
            + _bloque_contenido(contenido.get("motivo_consulta"), estilos,
                                 "Motivo de consulta no configurado para esta prueba ni registrado por el profesional.")
        ))

        # ── 3. TÉCNICAS E INSTRUMENTO APLICADO ──
        tecnicas = contenido.get("tecnicas") or []
        elementos.append(Paragraph("3. TÉCNICAS E INSTRUMENTO APLICADO", estilos["seccion"]))
        if tecnicas:
            for t in tecnicas:
                elementos.append(Paragraph(f"•  {escape(t)}", estilos["normal_izq"]))
        else:
            elementos.append(Paragraph("Sin técnicas configuradas.", estilos["pendiente"]))

        # ── 4. OBSERVACIÓN CONDUCTUAL ──
        elementos.append(KeepTogether(
            [Paragraph("4. OBSERVACIÓN CONDUCTUAL", estilos["seccion"])]
            + _bloque_contenido(contenido.get("observacion_conductual"), estilos,
                                 "Observación conductual pendiente de registro por el profesional.")
        ))

        # ── 5. RESULTADOS ──
        elementos.append(Paragraph("5. RESULTADOS", estilos["seccion"]))

        # 5.1 Cuantitativos
        elementos.append(Paragraph("5.1. RESULTADOS CUANTITATIVOS", estilos["subseccion"]))
        if len(dimensiones) == 1:
            d = dimensiones[0]
            rango = (
                f"{formatear_puntaje(d.get('rango_minimo'))}–{formatear_puntaje(d.get('rango_maximo'))} puntos"
                if d.get("rango_minimo") is not None and d.get("rango_maximo") is not None else _no_reg
            )
            elementos.append(Paragraph(f"Puntuación Directa (PD): {formatear_puntaje(d.get('puntaje'))} puntos", estilos["normal_izq"]))
            elementos.append(Paragraph(f"Categoría Clínica: {escape(d.get('nivel') or _no_reg)}", estilos["normal_izq"]))
            elementos.append(Paragraph(f"Rango de corte: {rango}", estilos["normal_izq"]))
        elif len(dimensiones) > 1:
            filas = [["Dimensión", "Puntaje", "Nivel", "Rango de corte"]]
            for d in dimensiones:
                rango = (
                    f"{formatear_puntaje(d.get('rango_minimo'))}–{formatear_puntaje(d.get('rango_maximo'))}"
                    if d.get("rango_minimo") is not None and d.get("rango_maximo") is not None else "-"
                )
                filas.append([d["nombre"], formatear_puntaje(d.get("puntaje")), d.get("nivel") or "No definido", rango])
            # Dimensión es, por lejos, la columna con más texto (ej. los
            # nombres largos de CHASIDE: "Intereses — H: Humanísticas,
            # Ciencias Jurídicas y Ciencias Sociales") — se le da la mayor
            # parte del ancho disponible (17cm = A4 menos 2cm de margen por
            # lado); el resto son valores cortos de formato fijo.
            elementos.append(_tabla_sobria(filas, [8 * cm, 2 * cm, 3.5 * cm, 3.5 * cm]))
        else:
            elementos.append(Paragraph("No hay resultados calculados para esta aplicación.", estilos["pendiente"]))

        # 🆕 Código de perfil (p. ej. código Holland de IPIP-RIASEC) — solo
        # aparece cuando la prueba se cargó con `ordenar_dimensiones_por_
        # puntaje=True` (ver crud._calcular_codigo_perfil); para cualquier
        # otra prueba `codigo_perfil` es None y esta línea no se imprime,
        # cero cambio para el resto del catálogo.
        if contenido.get("codigo_perfil"):
            elementos.append(Paragraph(
                f"Código de perfil (3 dimensiones con mayor puntaje): {escape(contenido['codigo_perfil'])}",
                estilos["normal_izq"],
            ))
            elementos.append(Spacer(1, 0.2 * cm))

        # 5.2 Cualitativos — por dimensión, cada una puede tener un texto distinto
        elementos.append(Paragraph("5.2. RESULTADOS CUALITATIVOS", estilos["subseccion"]))

        # 🆕 Agrupado por área (ver Prueba.agrupar_dimensiones_por_area en
        # models.py / crud._agrupar_dimensiones_por_area) — reemplaza el
        # listado plano de siempre por tres bloques: Área de Intereses, Área
        # de Aptitudes y Áreas Vocacionales Compatibles, cada uno mostrando
        # solo las áreas con nivel "Alto". None para cualquier prueba sin
        # ese flag (todo el catálogo existente): cae al listado plano de
        # siempre, sin cambios.
        perfil_vocacional = contenido.get("perfil_vocacional")
        if perfil_vocacional:
            areas_por_nombre = {a["nombre_area"]: a for a in perfil_vocacional.get("areas", [])}

            def _bloque_area(nombre_area: str, lado: str) -> list:
                d = areas_por_nombre[nombre_area][lado]
                bloque = [Paragraph(escape(nombre_area), estilos["dimension_nombre"])]
                if d.get("interpretacion"):
                    bloque.append(Paragraph(escape(d["interpretacion"]).replace("\n", "<br/>"), estilos["normal"]))
                else:
                    bloque.append(Paragraph("Interpretación no configurada para esta área.", estilos["pendiente"]))
                return bloque

            elementos.append(Paragraph("Área de Intereses", estilos["dimension_nombre"]))
            destacadas_interes = perfil_vocacional.get("destacadas_interes") or []
            if destacadas_interes:
                for nombre_area in destacadas_interes:
                    elementos.append(KeepTogether(_bloque_area(nombre_area, "interes")))
            else:
                elementos.append(Paragraph(
                    "No se identificaron áreas de interés claramente predominantes en esta aplicación.",
                    estilos["normal_izq"],
                ))

            elementos.append(Paragraph("Área de Aptitudes", estilos["dimension_nombre"]))
            destacadas_aptitud = perfil_vocacional.get("destacadas_aptitud") or []
            if destacadas_aptitud:
                for nombre_area in destacadas_aptitud:
                    elementos.append(KeepTogether(_bloque_area(nombre_area, "aptitud")))
            else:
                elementos.append(Paragraph(
                    "No se identificaron aptitudes claramente predominantes en esta aplicación.",
                    estilos["normal_izq"],
                ))

            compatibles = perfil_vocacional.get("compatibles") or []
            elementos.append(Paragraph("Áreas Vocacionales Compatibles", estilos["dimension_nombre"]))
            if compatibles:
                for nombre_area in compatibles:
                    elementos.append(Paragraph(f"•  {escape(nombre_area)}", estilos["normal_izq"]))
            else:
                elementos.append(Paragraph(
                    "No se identificó un área vocacional claramente compatible en esta aplicación.",
                    estilos["normal_izq"],
                ))
        else:
            if not dimensiones:
                elementos.append(Paragraph("No hay resultados que interpretar.", estilos["pendiente"]))
            for d in dimensiones:
                bloque = [Paragraph(escape(d["nombre"]), estilos["dimension_nombre"])]
                if d.get("interpretacion"):
                    bloque.append(Paragraph(escape(d["interpretacion"]).replace("\n", "<br/>"), estilos["normal"]))
                elif d.get("sin_baremo"):
                    bloque.append(Paragraph(
                        "No se pudo determinar una interpretación: no hay un baremo aplicable configurado "
                        "para esta dimensión. Este resultado NO debe leerse como 'sin riesgo'.",
                        estilos["pendiente"],
                    ))
                else:
                    bloque.append(Paragraph("Interpretación no configurada para este nivel.", estilos["pendiente"]))
                elementos.append(KeepTogether(bloque))

        # 🆕 Ítems informativos (ver Pregunta.incluir_en_informe en
        # models.py) — no puntúan ninguna dimensión, pero su respuesta se
        # imprime literal aquí bajo la etiqueta configurada, ej. el
        # "Indicador de Disfuncionalidad" del PHQ-9. Genérico: [] para
        # cualquier prueba que no use esta bandera, cero cambio.
        for item in (contenido.get("items_informativos") or []):
            bloque_item = [Paragraph(escape(item["etiqueta"]), estilos["dimension_nombre"])]
            if item.get("respuesta_texto"):
                bloque_item.append(Paragraph(
                    f"Respuesta registrada: “{escape(item['respuesta_texto'])}”.",
                    estilos["normal"],
                ))
            else:
                bloque_item.append(Paragraph("Sin respuesta registrada para este ítem.", estilos["pendiente"]))
            elementos.append(KeepTogether(bloque_item))

        # 5.3 Análisis de riesgo — título/redacción neutral cuando la prueba
        # no tiene, hoy, ningún mecanismo que pueda marcar es_alerta=True
        # (ver crud._prueba_puede_generar_alerta): un instrumento vocacional
        # no clínico (p. ej. IPIP-RIASEC, CHASIDE) no debería imprimir un
        # encabezado de "análisis de riesgo" en el 100% de sus informes.
        # `puede_alertar` por defecto True preserva el título/redacción
        # exactos de siempre para toda prueba ya cargada.
        puede_alertar = analisis_riesgo.get("puede_alertar", True)
        elementos.append(Paragraph(
            "5.3. ANÁLISIS DE RIESGO" if puede_alertar else "5.3. INDICADORES REGISTRADOS",
            estilos["subseccion"],
        ))

        # 🆕 Ítems centinela de seguridad (ReglaInterpretacion ámbito='item',
        # ver crud._resolver_items_monitoreados_riesgo) — se reporta SIEMPRE
        # la respuesta real, dispare o no la regla, ej. "El ítem 9 (ideación
        # autolítica) puntuó 0". Genérico: [] para cualquier prueba sin
        # reglas de ámbito 'item', cero cambio.
        for item in (analisis_riesgo.get("items_monitoreados") or []):
            estado_texto = "requiere revisión profesional" if item.get("disparo") else "no indica riesgo inmediato"
            elementos.append(Paragraph(
                f"•  {escape(item['pregunta_texto'])} — respuesta registrada: "
                f"“{escape(item['respuesta_texto'])}” ({estado_texto}).",
                estilos["normal_izq"],
            ))

        dims_alerta = [d for d in dimensiones if d.get("es_alerta")]
        if dims_alerta:
            filas_riesgo = [["Dimensión", "Origen de la alerta"]]
            for d in dims_alerta:
                filas_riesgo.append([d["nombre"], _ETIQUETA_ORIGEN_ALERTA.get(d.get("alerta_por"), "-")])
            elementos.append(_tabla_sobria(filas_riesgo, [8 * cm, 8 * cm]))
            for d in dims_alerta:
                if d.get("motivo_regla"):
                    elementos.append(Paragraph(
                        f"•  {escape(d['nombre'])} — regla activada: {escape(d['motivo_regla'])}",
                        estilos["normal_izq"],
                    ))
        if analisis_riesgo.get("dimensiones_sin_baremo"):
            elementos.append(Paragraph(
                escape("Sin baremo aplicable: " + ", ".join(analisis_riesgo["dimensiones_sin_baremo"])
                       + ". Este resultado NO debe leerse como 'sin riesgo'."),
                estilos["normal_izq"],
            ))
        if analisis_riesgo.get("reglas_con_error"):
            elementos.append(Paragraph(
                escape("Reglas de interpretación no evaluables: " + "; ".join(analisis_riesgo["reglas_con_error"])
                       + ". Este resultado NO debe leerse como 'sin riesgo'."),
                estilos["normal_izq"],
            ))
        if not dims_alerta and not analisis_riesgo.get("dimensiones_sin_baremo") and not analisis_riesgo.get("reglas_con_error"):
            elementos.append(Paragraph(
                "No se identificaron indicadores de alerta en esta aplicación." if puede_alertar
                else "Esta prueba no clasifica resultados como indicadores de alerta clínica.",
                estilos["normal_izq"],
            ))

        # ── 6. CONCLUSIONES ──
        elementos.append(KeepTogether(
            [Paragraph("6. CONCLUSIONES", estilos["seccion"])]
            + _bloque_contenido(contenido.get("conclusiones"), estilos,
                                 "Conclusión no configurada para este resultado ni registrada por el profesional.")
        ))

        # ── 7. RECOMENDACIONES ──
        elementos.append(KeepTogether(
            [Paragraph("7. RECOMENDACIONES", estilos["seccion"])]
            + _bloque_contenido(contenido.get("recomendaciones"), estilos,
                                 "Recomendación no configurada para este resultado ni registrada por el profesional.")
        ))
        elementos.append(Paragraph(
            "Las recomendaciones anteriores son orientativas y no constituyen, por sí solas, una decisión "
            "clínica definitiva: deben ser validadas por el profesional responsable.",
            estilos["aviso_fuente"],
        ))

        if contenido.get("interpretacion_clinica"):
            elementos.append(Paragraph("Interpretación adicional del profesional", estilos["subseccion"]))
            elementos.append(Paragraph(
                escape(contenido["interpretacion_clinica"]).replace("\n", "<br/>"), estilos["normal"],
            ))

        # ── FIRMA ── Una sola línea para firmar encima — antes, cuando
        # todavía no hay revisor (firma.nombre vacío, el caso normal antes de
        # la primera revisión), se imprimía una SEGUNDA línea de guiones bajos
        # como "nombre" por defecto, dando la impresión de dos líneas de
        # firma superpuestas. Ahora, sin nombre, esa fila simplemente no se
        # imprime — solo queda la línea para firmar y, debajo, el cargo.
        elementos.append(Spacer(1, 1.2 * cm))
        bloque_firma = [Paragraph("_" * 40, estilos["firma_linea"])]
        if firma.get("nombre"):
            bloque_firma.append(Paragraph(escape(firma["nombre"]), estilos["firma_nombre"]))
        bloque_firma.append(Paragraph(escape(firma.get("cargo") or "Psicólogo(a) / Especialidad"), estilos["firma_linea"]))
        # 🆕 DNI del profesional (auditoría de UX, sesión 2026-10-13):
        # editable vía Inscripcion.firma_dni_override — si no se definió,
        # sigue imprimiendo el placeholder en blanco de siempre, para
        # llenar a mano.
        texto_dni = f"DNI: {escape(firma['dni'])}" if firma.get("dni") else "DNI: ____________________"
        bloque_firma.append(Paragraph(texto_dni, estilos["firma_linea"]))
        bloque_firma.append(Spacer(1, 0.6 * cm))
        bloque_firma.append(Paragraph("(Sello)", estilos["firma_linea"]))
        elementos.append(KeepTogether(bloque_firma))

        # ── ANEXOS: evidencia del expediente clínico vinculada a este
        # informe (EntradaExpediente tipo='evidencia', incluir_en_pdf_informe
        # =True — ver modulos/educativo/crud.py:obtener_anexos_evidencia_informe).
        # Los de tipo imagen se intercalan aquí mismo, como un flowable más;
        # los de tipo pdf (un escaneo multipágina ya en PDF) no pueden vivir
        # en `elementos` — se fusionan aparte, después de doc.build().
        anexos = contenido.get("anexos") or []
        anexos_imagen = [a for a in anexos if a.get("tipo") == "imagen"]
        anexos_pdf = [a for a in anexos if a.get("tipo") == "pdf"]
        if anexos_imagen:
            elementos.append(PageBreak())
            elementos.append(Paragraph("ANEXOS: EVIDENCIA COMPLEMENTARIA", estilos["seccion"]))
            elementos.append(Paragraph(
                "Material adicional registrado en el expediente clínico del estudiante, vinculado a esta aplicación.",
                estilos["aviso_fuente"],
            ))
            for anexo in anexos_imagen:
                elementos.append(KeepTogether(_elemento_anexo_imagen(anexo, estilos)))
                elementos.append(Spacer(1, 0.8 * cm))

        marco = partial(_dibujar_marco_pagina, nombre_institucion=nombre_institucion, nombre_prueba=nombre_prueba)
        doc.build(elementos, onFirstPage=marco, onLaterPages=marco)
        buffer.seek(0)

        if anexos_pdf:
            buffer = _fusionar_anexos_pdf(buffer, anexos_pdf)

        logger.info(f"Informe PDF generado para la prueba: {nombre_prueba}")
        return buffer

    except Exception as e:
        logger.error(f"Error generando el informe PDF: {e}", exc_info=True)
        raise e
