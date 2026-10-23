# modulos/documentos/pdf_generador.py
#
# Motor de PDF del sistema de documentos institucionales — independiente de
# core/pdf_generator.py (el informe psicométrico): estructura y contenido
# completamente distintos, tipografía CONFIGURABLE por institución (no fija
# como en el informe), un renderizador propio por cada uno de los 14
# tipo_seccion cerrados. Comparte SOLO el registro de fuentes
# (core/pdf_fuentes.py) — un cambio aquí nunca afecta al generador del
# informe psicométrico, y viceversa (ver Decisión A del Paso 5).
#
# Entrada: generar_pdf_documento(contenido: dict) -> io.BytesIO, donde
# `contenido` es el dict que arma crud.construir_contenido_documento().
import io
import logging
import re
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.pdf_fuentes import registrar_fuentes
from core.url_segura import descargar_logo_seguro

logger = logging.getLogger("aurorasoft")

# "Times-Roman"/"Times-Bold"/"Times-Italic" son de las 14 fuentes base de
# PDF (como Helvetica) — ReportLab las sabe dibujar sin registrar ningún TTF,
# a diferencia de "Arial" (core/pdf_fuentes.registrar_fuentes() busca el TTF
# real en el servidor y cae a Helvetica si no está). "Times New Roman" es el
# nombre que un usuario/plantilla escribiría; se acepta como alias.
_FUENTES_CONOCIDAS = {"Arial", "Helvetica", "Times New Roman", "Times-Roman"}
DARK = colors.HexColor("#0f172a")
GRAY = colors.HexColor("#64748b")
BORDER = colors.HexColor("#cbd5e1")



def _resolver_tipografia(plantilla: dict):
    """Resuelve (fuente, fuente_bold, fuente_italica) de CUERPO para ESTA
    plantilla — a diferencia del informe psicométrico, aquí no hay una
    tipografía fija para todo el sistema: cada institución puede pedir la
    suya (PlantillaDocumento.fuente). Un nombre no registrado nunca revienta
    el renderizado: cae en silencio al sustituto que registrar_fuentes() ya
    resolvió (Arial si el servidor la tiene, Helvetica si no)."""
    fuente_regular, fuente_bold, fuente_italica = registrar_fuentes()
    pedida = (plantilla or {}).get("fuente") or "Arial"
    if pedida not in _FUENTES_CONOCIDAS:
        logger.warning("Plantilla pide fuente '%s' (no soportada); se usa %s.", pedida, fuente_regular)
    elif pedida == "Helvetica":
        fuente_regular, fuente_bold, fuente_italica = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    elif pedida in ("Times New Roman", "Times-Roman"):
        fuente_regular, fuente_bold, fuente_italica = "Times-Roman", "Times-Bold", "Times-Italic"
    # pedida == "Arial": lo que ya devolvió registrar_fuentes() es lo correcto
    # (Arial si está registrada, Helvetica si no).
    return fuente_regular, fuente_bold, fuente_italica


def _construir_estilos(plantilla: dict) -> dict:
    fuente, fuente_bold, fuente_italica = _resolver_tipografia(plantilla)
    tamano = int((plantilla or {}).get("tamano_pt") or 11)
    interlineado = float((plantilla or {}).get("interlineado") or 1.15)
    alineacion = TA_JUSTIFY if (plantilla or {}).get("justificado", True) else TA_LEFT
    leading = tamano * interlineado

    # 🆕 Estilo configurable del título del documento — ver PlantillaDocumento.
    # titulo_negrita/titulo_cursiva/titulo_tamano_pt en models.py. Solo hay 3
    # variantes de fuente registradas (regular/bold/italic — nunca un 4to TTF
    # bold+italic combinado), así que si se piden las dos a la vez, cursiva
    # gana (es la elección más deliberada de las dos cuando ambas están
    # marcadas) — nunca intenta simular "negrita Y cursiva" con una sola
    # variante de fuente.
    titulo_negrita = (plantilla or {}).get("titulo_negrita", True)
    titulo_cursiva = (plantilla or {}).get("titulo_cursiva", False)
    fuente_titulo = fuente_italica if titulo_cursiva else (fuente_bold if titulo_negrita else fuente)
    tamano_titulo = (plantilla or {}).get("titulo_tamano_pt") or (tamano + 5)
    # 🆕 Igual criterio NULL-formula que tamano_titulo — ver
    # PlantillaDocumento.subtitulo_tamano_pt en models.py. El subtítulo
    # sigue siendo SIEMPRE negrita (fuente_bold, nunca configurable).
    tamano_subtitulo = (plantilla or {}).get("subtitulo_tamano_pt") or (tamano + 1)

    return {
        "documento_titulo": ParagraphStyle(
            "documento_titulo", fontName=fuente_titulo, fontSize=tamano_titulo, leading=tamano_titulo * 1.2,
            alignment=TA_CENTER, textColor=DARK, spaceAfter=12,
        ),
        # Línea del año oficial ("AÑO DE LA ESPERANZA...") — va ANTES del
        # título (ver generar_pdf_documento), en cursiva+negrita y
        # entrecomillada, como en el documento de papel real.
        "anio_oficial": ParagraphStyle(
            "anio_oficial", fontName=fuente_italica, fontSize=tamano, leading=leading,
            alignment=TA_CENTER, textColor=DARK, spaceAfter=10,
        ),
        "seccion_titulo": ParagraphStyle(
            "seccion_titulo", fontName=fuente_bold, fontSize=tamano_subtitulo, leading=tamano_subtitulo * 1.2,
            textColor=DARK, spaceBefore=12, spaceAfter=5,
        ),
        "normal": ParagraphStyle("normal", fontName=fuente, fontSize=tamano, leading=leading, alignment=alineacion),
        "etiqueta": ParagraphStyle("etiqueta", fontName=fuente_bold, fontSize=tamano, leading=leading),
        # Línea de viñeta (• texto) dentro de 'texto_libre' — sangría
        # francesa (firstLineIndent negativo) para que el texto que da la
        # vuelta de línea quede alineado bajo el texto, no bajo el punto.
        "vineta": ParagraphStyle(
            "vineta", fontName=fuente, fontSize=tamano, leading=leading, alignment=alineacion,
            leftIndent=14, firstLineIndent=-14, spaceAfter=2,
        ),
        "pendiente": ParagraphStyle("pendiente", fontName=fuente_italica, fontSize=tamano, leading=leading, textColor=GRAY),
        # Bloque de firma — siempre centrado, nunca justificado/izquierda,
        # sin importar lo que pida la plantilla para el cuerpo (ver
        # _renderizar_firma/_renderizar_firma_doble).
        "firma_linea": ParagraphStyle(
            "firma_linea", fontName=fuente, fontSize=tamano, leading=leading, alignment=TA_CENTER,
        ),
        "firma_cargo": ParagraphStyle(
            "firma_cargo", fontName=fuente_bold, fontSize=tamano, leading=leading, alignment=TA_CENTER,
        ),
        "pie": ParagraphStyle("pie", fontName=fuente, fontSize=max(tamano - 3, 7), textColor=GRAY),
        "celda": ParagraphStyle("celda", fontName=fuente, fontSize=max(tamano - 1, 7), leading=(tamano - 1) * 1.2),
        "celda_bold": ParagraphStyle("celda_bold", fontName=fuente_bold, fontSize=max(tamano - 1, 7)),
    }, fuente, fuente_bold


ALTO_BANDA_ENCABEZADO = 2.6 * cm
ALTO_BANDA_PIE = 1.6 * cm


def _dibujar_imagen_contenida(canvas_obj, reader: ImageReader, x: float, y_arriba: float, ancho_max: float, alto_max: float) -> float:
    """Dibuja `reader` ajustada dentro de ancho_max x alto_max SIN
    deformarla (contain-fit), con su borde superior en y_arriba y centrada
    horizontalmente en [x, x+ancho_max]. Devuelve el alto real dibujado."""
    iw, ih = reader.getSize()
    if not iw or not ih:
        return 0.0
    escala = min(ancho_max / iw, alto_max / ih)
    w, h = iw * escala, ih * escala
    canvas_obj.drawImage(
        reader, x + (ancho_max - w) / 2, y_arriba - h, width=w, height=h,
        mask="auto", preserveAspectRatio=True,
    )
    return h


def _dibujar_marco_pagina(
    canvas_obj, doc,
    imagen_encabezado: ImageReader | None, imagen_pie: ImageReader | None,
    imagen_fondo: ImageReader | None = None,
):
    """Membrete/pie de cada página — SOLO las imágenes institucionales,
    sin ningún texto superpuesto (ni nombre de institución, ni rótulo, ni
    número de página): decisión explícita del colegio, el membrete/pie
    tienen que verse exactamente como la imagen que subieron, nada más.
    Si una institución no configuró ninguna de las dos imágenes, esa banda
    simplemente queda en blanco — no hay respaldo de texto.

    `imagen_fondo` (opt-in por plantilla, ver
    PlantillaDocumento.mostrar_fondo_institucion) se dibuja PRIMERO, a
    página completa (cover-fit, puede recortar) — el membrete queda
    siempre encima, nunca tapado por el fondo."""
    canvas_obj.saveState()
    ancho, alto = A4
    margen_x = 2 * cm
    ancho_contenido = ancho - 2 * margen_x

    if imagen_fondo is not None:
        iw, ih = imagen_fondo.getSize()
        if iw and ih:
            escala = max(ancho / iw, alto / ih)
            w, h = iw * escala, ih * escala
            canvas_obj.drawImage(
                imagen_fondo, (ancho - w) / 2, (alto - h) / 2, width=w, height=h, mask="auto",
            )

    if imagen_encabezado is not None:
        _dibujar_imagen_contenida(
            canvas_obj, imagen_encabezado, margen_x, alto - 1.1 * cm, ancho_contenido, ALTO_BANDA_ENCABEZADO,
        )
    if imagen_pie is not None:
        _dibujar_imagen_contenida(
            canvas_obj, imagen_pie, margen_x, 1.1 * cm + ALTO_BANDA_PIE, ancho_contenido, ALTO_BANDA_PIE,
        )

    canvas_obj.restoreState()


def _placeholder(texto: str, estilos: dict) -> Paragraph:
    return Paragraph(escape(texto), estilos["pendiente"])


# ==========================================
# Un renderizador por cada tipo_seccion cerrado — ver el docstring de
# PlantillaSeccion en models.py: a diferencia de TipoDocumento (puro dato),
# esto SÍ necesita código propio por valor.
# ==========================================
def _renderizar_encabezado(datos: dict, estilos: dict) -> list:
    datos = datos or {}
    elementos = []
    if datos.get("correlativo_texto"):
        elementos.append(Paragraph(escape(datos["correlativo_texto"]), estilos["etiqueta"]))
    if datos.get("anio_oficial_texto"):
        elementos.append(Paragraph(escape(datos["anio_oficial_texto"]), estilos["normal"]))
    destinatarios = datos.get("destinatarios") or []
    if destinatarios:
        texto = "PARA: " + "; ".join(
            escape(f"{d.get('nombre', '')} ({d.get('cargo', '')})".strip()) for d in destinatarios
        )
        elementos.append(Paragraph(texto, estilos["normal"]))
    if datos.get("emisor_nombre"):
        cargo = f" — {escape(datos['emisor_cargo'])}" if datos.get("emisor_cargo") else ""
        elementos.append(Paragraph(f"DE: {escape(datos['emisor_nombre'])}{cargo}", estilos["normal"]))
    elementos.append(Spacer(1, 8))
    return elementos


def _renderizar_datos_filiacion(datos: dict, estilos: dict) -> list:
    datos = datos or {}
    if not datos.get("aplica"):
        return [_placeholder(
            "No aplica: esta sección es de identidad individual y el documento no tiene "
            "exactamente un estudiante asociado.", estilos,
        )]
    filas = [
        ("Nombre completo", datos.get("nombre_completo")),
        ("Sexo", datos.get("sexo")),
        ("Fecha de nacimiento", datos.get("fecha_nacimiento")),
        ("Documento de identidad", datos.get("documento_identidad")),
        ("Grado / sección", datos.get("grado_seccion")),
        # 🆕 Propios de ESTE documento (llenados a mano, nunca leídos de
        # Persona) — ver crud._resolver_datos_filiacion.
        ("Hijos", datos.get("hijos")),
        ("Examinadora", datos.get("examinadora")),
        ("Fecha de elaboración", datos.get("fecha_elaboracion")),
        ("Periodo propuesto", datos.get("periodo_propuesto")),
    ]
    elementos = [_fila_etiqueta_valor(e, v, estilos) for e, v in filas if v]
    if not any(v for _, v in filas):
        elementos.append(_placeholder("Sin datos de filiación registrados.", estilos))
    diagnostico = datos.get("diagnostico_presuntivo")
    elementos.append(Spacer(1, 4))
    elementos.append(Paragraph("Diagnóstico presuntivo:", estilos["etiqueta"]))
    elementos.append(Paragraph(escape(diagnostico), estilos["normal"]) if diagnostico
                      else _placeholder("Pendiente de registro.", estilos))
    return elementos


def _fila_etiqueta_valor(etiqueta: str, valor, estilos: dict) -> Paragraph:
    return Paragraph(f"<b>{escape(etiqueta)}:</b> {escape(str(valor))}", estilos["normal"])


def _renderizar_datos_familiares(datos: dict, estilos: dict) -> list:
    datos = datos or {}
    if not datos.get("aplica"):
        return [_placeholder(
            "No aplica: esta sección es de identidad individual y el documento no tiene "
            "exactamente un estudiante asociado.", estilos,
        )]
    elementos = []
    familiares = [
        ("Número de hermanos", datos.get("numero_hermanos")),
        ("Vive con", datos.get("vive_con")),
        ("Lugar de nacimiento", datos.get("lugar_nacimiento")),
        ("Lugar de procedencia", datos.get("lugar_procedencia")),
    ]
    tiene_familiares = any(v not in (None, "") for _, v in familiares)
    elementos.append(Paragraph("Datos familiares", estilos["etiqueta"]))
    if tiene_familiares:
        elementos.extend(_fila_etiqueta_valor(e, v, estilos) for e, v in familiares if v not in (None, ""))
    else:
        elementos.append(_placeholder("Sin datos familiares registrados.", estilos))

    elementos.append(Spacer(1, 4))
    elementos.append(Paragraph("Tratamiento externo y diagnóstico reportado", estilos["etiqueta"]))
    terapia = datos.get("recibe_terapia_psicologica_externa")
    psiquiatria = datos.get("recibe_atencion_psiquiatrica_externa")
    if terapia is None and psiquiatria is None and not datos.get("diagnostico_reportado"):
        elementos.append(_placeholder("Sin antecedentes clínicos registrados.", estilos))
        return elementos

    if terapia is not None:
        texto = "Sí" if terapia else "No"
        if terapia and datos.get("detalle_terapia_psicologica_externa"):
            texto += f" — {datos['detalle_terapia_psicologica_externa']}"
        elementos.append(_fila_etiqueta_valor("Terapia psicológica externa", texto, estilos))
    if psiquiatria is not None:
        texto = "Sí" if psiquiatria else "No"
        if psiquiatria and datos.get("detalle_atencion_psiquiatrica_externa"):
            texto += f" — {datos['detalle_atencion_psiquiatrica_externa']}"
        elementos.append(_fila_etiqueta_valor("Atención psiquiátrica externa", texto, estilos))
    if datos.get("diagnostico_reportado"):
        elementos.append(_fila_etiqueta_valor("Diagnóstico reportado", datos["diagnostico_reportado"], estilos))
    return elementos


_PATRON_LINEA_VINETA = re.compile(r"^\s*[•\-\*]\s+(.*)$")
# 🆕 Negrita manual: **texto** -> <b>texto</b>. Se aplica SIEMPRE sobre la
# línea YA escapada (escape() de html, nunca antes) — una psicóloga no
# puede abrir una etiqueta HTML real escribiendo texto, solo marcar negrita
# con este patrón. No-greedy y sin DOTALL: nunca cruza un salto de línea.
_PATRON_NEGRITA_MANUAL = re.compile(r"\*\*(.+?)\*\*")


def _aplicar_negrita_manual(texto_escapado: str) -> str:
    return _PATRON_NEGRITA_MANUAL.sub(r"<b>\1</b>", texto_escapado)


def _renderizar_texto_libre(datos: dict, estilos: dict) -> list:
    """Texto libre redactado por la psicóloga. Una línea que empieza con
    "•", "-" o "*" (tecleado a mano, o insertado por el botón "+ Viñeta"
    del frontend) se renderiza como punto de viñeta real — con sangría
    francesa, no como el carácter "•" suelto dentro de un párrafo corrido
    — el resto del texto sigue siendo párrafos normales, exactamente como
    antes. Varias líneas de viñeta seguidas salen como varios puntos
    separados, no como un solo párrafo con saltos de línea. Dentro de
    cualquier línea, `**texto**` sale en negrita (ver
    _aplicar_negrita_manual) — la psicóloga decide manualmente qué resaltar,
    el resto del contenido nunca sale en negrita por su cuenta."""
    texto = (datos or {}).get("texto")
    if not texto:
        return [_placeholder("Pendiente de registro.", estilos)]

    elementos = []
    lineas_parrafo: list[str] = []

    def _cerrar_parrafo():
        if lineas_parrafo:
            html = "<br/>".join(_aplicar_negrita_manual(escape(linea)) for linea in lineas_parrafo)
            elementos.append(Paragraph(html, estilos["normal"]))
            lineas_parrafo.clear()

    for linea in texto.split("\n"):
        coincidencia = _PATRON_LINEA_VINETA.match(linea)
        if coincidencia:
            _cerrar_parrafo()
            texto_vineta = _aplicar_negrita_manual(escape(coincidencia.group(1)))
            elementos.append(Paragraph(f"•&nbsp;&nbsp;{texto_vineta}", estilos["vineta"]))
        else:
            lineas_parrafo.append(linea)
    _cerrar_parrafo()

    return elementos or [_placeholder("Pendiente de registro.", estilos)]


def _renderizar_tabla_dinamica(datos: dict, estilos: dict) -> list:
    datos = datos or {}
    columnas = datos.get("columnas") or []
    filas = datos.get("filas") or []
    if not columnas:
        return [_placeholder("Tabla sin columnas configuradas.", estilos)]
    if not filas:
        return [_placeholder("Sin filas registradas todavía.", estilos)]

    encabezado = [Paragraph(escape(str(c)), estilos["celda_bold"]) for c in columnas]
    cuerpo = [[Paragraph(escape(str(celda)) if celda not in (None, "") else "—", estilos["celda"]) for celda in fila]
              for fila in filas]
    tabla = Table([encabezado] + cuerpo, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [tabla]


def _bloque_resultado_prueba(resultado: dict, estilos: dict) -> list:
    """Un bloque de resultado — Instrumento/Fecha + tabla Dimensión/Nivel/
    Interpretación, o el placeholder de retención. Extraído de
    `_renderizar_resultados_prueba` para que esa (un solo resultado) y
    `_renderizar_resultados_prueba_multiple` (una lista) compartan
    EXACTAMENTE el mismo bloque visual, nunca dos copias que puedan
    desincronizarse. `resultado` NUNCA incluye la clave 'aplica' — eso lo
    decide el llamador antes de entrar acá."""
    if resultado.get("retenido"):
        # 🔒 Hallazgo B (ver CLAUDE.md) -- el resultado vinculado todavía
        # está retenido para revisión profesional (o el propio alumno no lo
        # vería): nunca se imprime puntaje/nivel/interpretación reales.
        return [_placeholder(
            "Pendiente de revisión profesional: el resultado de esta evaluación todavía no "
            "ha sido liberado por el psicólogo responsable.", estilos,
        )]
    elementos = [Paragraph(f"<b>Instrumento:</b> {escape(resultado.get('prueba_nombre', ''))}", estilos["normal"])]
    if resultado.get("fecha_evaluacion"):
        elementos.append(Paragraph(f"<b>Fecha de evaluación:</b> {escape(resultado['fecha_evaluacion'])}", estilos["normal"]))
    dimensiones = resultado.get("dimensiones") or []
    if not dimensiones:
        elementos.append(_placeholder("Sin dimensiones interpretadas todavía.", estilos))
        return elementos
    encabezado = [Paragraph(t, estilos["celda_bold"]) for t in ("Dimensión", "Nivel", "Interpretación")]
    cuerpo = [
        [
            Paragraph(escape(d.get("nombre") or ""), estilos["celda"]),
            Paragraph(escape(d.get("nivel") or "—"), estilos["celda"]),
            Paragraph(escape(d.get("interpretacion") or "—"), estilos["celda"]),
        ]
        for d in dimensiones
    ]
    tabla = Table([encabezado] + cuerpo, repeatRows=1, colWidths=[4 * cm, 3 * cm, None])
    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elementos.append(tabla)
    return elementos


def _renderizar_resultados_prueba(datos: dict, estilos: dict) -> list:
    datos = datos or {}
    if not datos.get("aplica"):
        return [_placeholder(
            "No aplica: no hay una aplicación de prueba vinculada a esta sección para el "
            "estudiante de este documento.", estilos,
        )]
    return _bloque_resultado_prueba(datos, estilos)


def _renderizar_resultados_prueba_multiple(datos: dict, estilos: dict) -> list:
    """Varios bloques de resultado, uno por cada Inscripcion que
    `crud.vincular_resultados_prueba_multiple` dejó vinculada a esta
    sección — cada uno respeta el mismo candado de retención que
    `resultados_prueba`, de forma independiente (un instrumento liberado
    puede mostrarse mientras otro, todavía retenido, no). Ver
    PlantillaSeccion.config en models.py para el shape completo."""
    datos = datos or {}
    if not datos.get("aplica"):
        return [_placeholder(
            "No aplica: esta sección es de identidad individual y el documento no tiene "
            "exactamente un estudiante asociado.", estilos,
        )]
    resultados = datos.get("resultados") or []
    if not resultados:
        return [_placeholder("Sin resultados vinculados todavía.", estilos)]
    elementos = []
    for i, resultado in enumerate(resultados):
        if i > 0:
            elementos.append(Spacer(1, 10))
        elementos.extend(_bloque_resultado_prueba(resultado, estilos))
    return elementos


ANCHO_MAXIMO_FIRMA_IMAGEN = 5 * cm
ALTO_MAXIMO_FIRMA_IMAGEN = 2 * cm


def _imagen_firma_ajustada(contenido_imagen: bytes):
    """Firma personal (imagen) ajustada dentro de un rectángulo fijo, sin
    deformarse — mismo contain-fit que las imágenes de membrete/pie, pero
    como flowable de Platypus (va dentro del flujo normal del documento,
    no en el marco de cada página)."""
    reader = ImageReader(io.BytesIO(contenido_imagen))
    iw, ih = reader.getSize()
    if not iw or not ih:
        return None
    escala = min(ANCHO_MAXIMO_FIRMA_IMAGEN / iw, ALTO_MAXIMO_FIRMA_IMAGEN / ih)
    imagen = Image(io.BytesIO(contenido_imagen), width=iw * escala, height=ih * escala)
    imagen.hAlign = "CENTER"
    return imagen


def _bloque_firma(datos: dict, estilos: dict) -> list:
    """Un bloque de firma individual, siempre CENTRADO: la firma personal
    (imagen, si el responsable subió una — ver Usuario.firma_imagen_url) o,
    a falta de ella, la línea de subrayado de siempre; debajo, su nombre
    (propio, nunca "FIRMA" como etiqueta), cargo en negrita, y las líneas
    fijas de la plantilla (departamento, institución) cada una en su propia
    línea — nunca todo junto en un solo renglón. Reutilizado tal cual por
    'firma' (una sola columna) y 'firma_doble' (dentro de cada celda de la
    tabla de dos columnas)."""
    datos = datos or {}
    elementos = []

    imagen_firma = None
    url_firma = datos.get("firma_imagen_url")
    if url_firma:
        contenido_imagen = descargar_logo_seguro(url_firma)
        if contenido_imagen:
            try:
                imagen_firma = _imagen_firma_ajustada(contenido_imagen)
            except Exception as exc:
                logger.warning("Imagen de firma descartada (no es una imagen válida): %s", exc)
    if imagen_firma is not None:
        elementos.append(imagen_firma)
    else:
        elementos.append(Paragraph("_" * 30, estilos["firma_linea"]))

    if datos.get("nombre"):
        elementos.append(Paragraph(escape(datos["nombre"]), estilos["firma_linea"]))
    if datos.get("cargo"):
        elementos.append(Paragraph(escape(datos["cargo"]), estilos["firma_cargo"]))
    for linea in datos.get("lineas_fijas") or []:
        elementos.append(Paragraph(escape(linea), estilos["firma_linea"]))
    if not datos.get("nombre") and not datos.get("cargo") and not datos.get("lineas_fijas"):
        elementos.append(_placeholder("Firma y sello del profesional responsable", estilos))
    return elementos


def _renderizar_firma(datos: dict, estilos: dict) -> list:
    return [Spacer(1, 30)] + _bloque_firma(datos, estilos)


def _renderizar_firma_doble(datos: dict, estilos: dict) -> list:
    """Dos bloques de firma lado a lado y simétricos (misma anchura,
    mismo punto de partida) — ver docstring de PlantillaSeccion.config en
    models.py para el shape de `izquierda`/`derecha`."""
    datos = datos or {}
    izquierda = _bloque_firma(datos.get("izquierda") or {}, estilos)
    derecha = _bloque_firma(datos.get("derecha") or {}, estilos)
    tabla = Table([[izquierda, derecha]], colWidths=["50%", "50%"])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 30), tabla]


def _renderizar_firma_triple(datos: dict, estilos: dict) -> list:
    """Igual que 'firma_doble' (izquierda/derecha lado a lado) más un
    tercer bloque ('centro') debajo, a todo el ancho — nunca dentro de la
    tabla de dos columnas, para que quede realmente centrado en la página
    y no en media columna. Ver docstring de PlantillaSeccion.config en
    models.py para el shape de `izquierda`/`derecha`/`centro`."""
    datos = datos or {}
    izquierda = _bloque_firma(datos.get("izquierda") or {}, estilos)
    derecha = _bloque_firma(datos.get("derecha") or {}, estilos)
    tabla = Table([[izquierda, derecha]], colWidths=["50%", "50%"])
    tabla.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    centro = _bloque_firma(datos.get("centro") or {}, estilos)
    return [Spacer(1, 30), tabla, Spacer(1, 20), *centro]


def _renderizar_grupo_campos(datos: dict, estilos: dict) -> list:
    """Octavo tipo_seccion: pares etiqueta/valor definidos libremente por
    quien arma la plantilla (una entrevista/anamnesis con preguntas propias
    de un colegio, por ejemplo) — ver crud.construir_contenido_documento.
    Un campo sin valor llenado se muestra en blanco, nunca se omite: el
    profesional ve exactamente qué falta responder."""
    campos = (datos or {}).get("campos") or []
    if not campos:
        return [_placeholder("Esta sección no tiene campos configurados.", estilos)]
    return [_fila_etiqueta_valor(c["etiqueta"], c.get("valor") or "—", estilos) for c in campos]


def _linea_en_blanco(etiqueta: str, estilos: dict, ancho_guion: int = 30) -> Paragraph:
    """Una etiqueta + línea para escribir a mano — nunca Unicode de dibujo
    de líneas (riesgo de glifo faltante con Times-Roman/Helvetica), solo
    guiones bajos ASCII, igual que la línea de firma."""
    return Paragraph(f"<b>{escape(etiqueta)}:</b> {'_' * ancho_guion}", estilos["normal"])


def _renderizar_ficha_imprimible(datos: dict, estilos: dict) -> list:
    """Formulario en blanco (ver docstring de PlantillaSeccion.config en
    models.py) — nunca lee contenido por documento. Los "casilleros" de la
    tabla de verificación son celdas VACÍAS con borde (el borde es el
    casillero), nunca un carácter Unicode: Times-Roman/Helvetica (fuentes
    base de PDF, sin TTF) no garantizan tener un glifo de casillero —
    un borde vacío siempre se dibuja bien, sin importar la fuente activa."""
    datos = datos or {}
    elementos = []

    for etiqueta in datos.get("campos_encabezado") or []:
        elementos.append(_linea_en_blanco(etiqueta, estilos))
    if datos.get("campos_encabezado"):
        elementos.append(Spacer(1, 6))

    if datos.get("leyenda"):
        elementos.append(Paragraph(escape(datos["leyenda"]), estilos["pie"]))
        elementos.append(Spacer(1, 4))

    columnas = datos.get("columnas") or []
    filas = datos.get("filas") or []
    if columnas and filas:
        encabezado = [""] + [Paragraph(f"<b>{escape(str(c))}</b>", estilos["celda_bold"]) for c in columnas]
        cuerpo = [[Paragraph(escape(str(fila)), estilos["celda"])] + ["" for _ in columnas] for fila in filas]
        # La columna de etiquetas (0) se queda con el espacio que sobre
        # (colWidths=None ahí); cada columna de verificación se ancha según
        # el largo real de SU encabezado — un ancho fijo único angostaba
        # "REQUIERE APOYO" a 3 líneas apretadas, y dejar las 6 columnas sin
        # ningún ancho fijo (como sí hace _renderizar_tabla_dinamica, que
        # nunca tiene más de 1 columna de texto largo) angostaba de más la
        # columna 0 al repartir el ancho total parejo entre todas.
        ancho_columnas = [None] + [
            max(1.3 * cm, 0.24 * cm * len(str(c)) + 0.6 * cm) for c in columnas
        ]
        tabla = Table([encabezado] + cuerpo, repeatRows=1, colWidths=ancho_columnas)
        tabla.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 8))

    for lista in datos.get("listas_checkbox") or []:
        if lista.get("titulo"):
            elementos.append(Paragraph(escape(lista["titulo"]), estilos["etiqueta"]))
        for opcion in lista.get("opciones") or []:
            elementos.append(Paragraph(f"[&nbsp;&nbsp;] {escape(opcion)}", estilos["normal"]))
        elementos.append(Spacer(1, 6))

    for pregunta in datos.get("preguntas_abiertas") or []:
        elementos.append(Paragraph(f"<b>{escape(pregunta)}</b>", estilos["normal"]))
        elementos.append(Spacer(1, 14))

    if datos.get("firmas_en_blanco"):
        elementos.append(Spacer(1, 10))
        for etiqueta in datos["firmas_en_blanco"]:
            elementos.append(_linea_en_blanco(etiqueta, estilos))
            elementos.append(Spacer(1, 6))

    if not elementos:
        elementos.append(_placeholder("Esta ficha no tiene campos configurados.", estilos))
    return elementos


def _renderizar_grafico_barras(datos: dict, estilos: dict) -> list:
    """Gráfico de barras embebido como imagen — reusa
    `core.pdf_generator.generar_grafico_barras`, el mismo que ya usa el
    informe psicométrico fijo, en vez de duplicar la lógica de matplotlib.
    `datos` ya viene resuelto por `crud._resolver_grafico_barras` (vinculado
    a una Inscripcion real, o manual) — este renderizador no sabe de dónde
    salió, solo dibuja."""
    datos = datos or {}
    if datos.get("retenido"):
        return [_placeholder(
            "Pendiente de revisión profesional: el resultado vinculado a este gráfico todavía no "
            "ha sido liberado por el psicólogo responsable.", estilos,
        )]
    puntos = datos.get("datos") or []
    if not puntos:
        return [_placeholder("Sin datos de gráfico configurados todavía.", estilos)]

    from core.pdf_generator import generar_grafico_barras
    puntajes = {p["etiqueta"]: p.get("valor") or 0 for p in puntos if p.get("etiqueta")}
    if not puntajes:
        return [_placeholder("Sin datos de gráfico configurados todavía.", estilos)]
    try:
        titulo_grafico = datos.get("prueba_nombre") or "Gráfico de puntajes"
        buffer = generar_grafico_barras(puntajes, titulo_grafico)
    except Exception as exc:
        logger.warning("No se pudo generar el gráfico de barras: %s", exc)
        return [_placeholder("No se pudo generar el gráfico con los datos configurados.", estilos)]
    return [Image(buffer, width=13 * cm, height=6.5 * cm)]


def _renderizar_imagen_anexo(datos: dict, estilos: dict) -> list:
    """Imagen subida directamente (ver `crud.guardar_imagen_seccion`) —
    los bytes NUNCA viajan en `contenido_snapshot`, solo el `storage_key`;
    se leen recién acá, al generar cada versión, igual que el logo
    institucional se re-descarga recién al generar (con la diferencia de
    que esto ya está en storage propio, no requiere red)."""
    datos = datos or {}
    storage_key = datos.get("storage_key")
    if not storage_key:
        return [_placeholder("Sin imagen/anexo cargado todavía.", estilos)]
    try:
        from core.storage import obtener_storage_service
        contenido_bytes = obtener_storage_service().leer(storage_key)
        buffer = io.BytesIO(contenido_bytes)
        try:
            from PIL import Image as PILImage
            with PILImage.open(buffer) as img:
                ancho_px, alto_px = img.size
            buffer.seek(0)
            ancho_max = 12 * cm
            alto = ancho_max * (alto_px / ancho_px) if ancho_px else 8 * cm
            alto_max = 16 * cm
            if alto > alto_max:
                alto = alto_max
                ancho_max = alto_max * (ancho_px / alto_px) if alto_px else ancho_max
            elementos = [Image(buffer, width=ancho_max, height=alto)]
        except Exception:
            buffer.seek(0)
            elementos = [Image(buffer, width=12 * cm, height=12 * cm)]
    except Exception as exc:
        logger.warning("No se pudo leer la imagen de la sección (%s): %s", storage_key, exc)
        return [_placeholder("La imagen de esta sección no está disponible.", estilos)]
    if datos.get("descripcion"):
        elementos.append(Spacer(1, 4))
        elementos.append(Paragraph(f"<i>{escape(datos['descripcion'])}</i>", estilos["normal"]))
    return elementos


_RENDERIZADORES = {
    "encabezado": _renderizar_encabezado,
    "datos_filiacion": _renderizar_datos_filiacion,
    "datos_familiares": _renderizar_datos_familiares,
    "texto_libre": _renderizar_texto_libre,
    "tabla_dinamica": _renderizar_tabla_dinamica,
    "resultados_prueba": _renderizar_resultados_prueba,
    "firma": _renderizar_firma,
    "grupo_campos": _renderizar_grupo_campos,
    "firma_doble": _renderizar_firma_doble,
    "ficha_imprimible": _renderizar_ficha_imprimible,
    "grafico_barras": _renderizar_grafico_barras,
    "imagen_anexo": _renderizar_imagen_anexo,
    "firma_triple": _renderizar_firma_triple,
    "resultados_prueba_multiple": _renderizar_resultados_prueba_multiple,
}


def generar_pdf_documento(contenido: dict) -> io.BytesIO:
    """Construye el PDF completo de UNA versión de un DocumentoInstitucional
    a partir de `contenido` (ver crud.construir_contenido_documento()).

    A diferencia de core/pdf_generator.py, aquí no hay una estructura fija
    de secciones numeradas — el documento es exactamente la secuencia de
    PlantillaSeccion de su plantilla, en su propio `orden`, cada una
    despachada por tipo_seccion al renderizador que le corresponde (nunca
    por nombre del TipoDocumento ni de la sección)."""
    documento = contenido.get("documento") or {}
    institucion = contenido.get("institucion") or {}
    plantilla = contenido.get("plantilla") or {}
    secciones = contenido.get("secciones") or []

    estilos, _, _ = _construir_estilos(plantilla)
    elementos = []

    # 🆕 Membrete/pie institucional — ahora se dibuja en el MARCO de cada
    # página (_dibujar_marco_pagina), no como contenido del flujo: así
    # aparece en TODAS las páginas, no solo en la primera. Se descarga una
    # sola vez aquí (SSRF-safe, core/url_segura.py) y se reutiliza como
    # ImageReader en cada página — nunca revienta el documento si la URL
    # falla o no es una imagen válida, solo se omite esa imagen.
    def _leer_imagen_institucional(url):
        if not url:
            return None
        datos_imagen = descargar_logo_seguro(url)
        if not datos_imagen:
            return None
        try:
            return ImageReader(io.BytesIO(datos_imagen))
        except Exception as exc:
            logger.warning("Imagen institucional descartada (no es una imagen válida): %s", exc)
            return None

    imagen_encabezado = _leer_imagen_institucional(institucion.get("logo_url"))
    imagen_pie = _leer_imagen_institucional(institucion.get("logo_pie_pagina_url"))
    # 🆕 Opt-in por plantilla (nunca automático por el solo hecho de que la
    # institución tenga un fondo configurado) — ver
    # PlantillaDocumento.mostrar_fondo_institucion.
    imagen_fondo = (
        _leer_imagen_institucional(institucion.get("fondo_documento_url"))
        if plantilla.get("mostrar_fondo_institucion") else None
    )

    # La sección 'encabezado' (si la plantilla trae una) no imprime su
    # propio rótulo de sección como las demás — es membrete/metadata, no
    # "una sección" desde la perspectiva de quien lee. Su línea de año
    # oficial, además, va ANTES del título (como en el documento de papel
    # real), no después: se extrae aquí y se borra de sus propios `datos`
    # para que _renderizar_encabezado no la repita más abajo.
    anio_oficial_texto = None
    for seccion in secciones:
        if seccion.get("tipo_seccion") == "encabezado":
            datos_encabezado = seccion.get("datos") or {}
            anio_oficial_texto = datos_encabezado.get("anio_oficial_texto")
            datos_encabezado["anio_oficial_texto"] = None
            break

    if anio_oficial_texto:
        elementos.append(Paragraph(f"“{escape(anio_oficial_texto.upper())}”", estilos["anio_oficial"]))

    titulo = documento.get("titulo") or "Documento institucional"
    elementos.append(Paragraph(escape(titulo.upper()), estilos["documento_titulo"]))
    if documento.get("numero_version"):
        info_version = f"Versión: v{documento['numero_version']}"
        if documento.get("motivo_version"):
            info_version += f" — {documento['motivo_version']}"
        elementos.append(Paragraph(escape(info_version), estilos["pie"]))
        elementos.append(Spacer(1, 10))

    for seccion in secciones:
        tipo_seccion = seccion.get("tipo_seccion")
        renderizador = _RENDERIZADORES.get(tipo_seccion)
        if renderizador is None:
            logger.error("tipo_seccion '%s' sin renderizador registrado; se omite.", tipo_seccion)
            continue
        if seccion.get("salto_pagina_antes"):
            elementos.append(PageBreak())
        bloque = []
        # 'encabezado'/'firma'/'firma_doble'/'firma_triple' son membrete y
        # cierre, nunca "una sección" para quien lee — nunca llevan su
        # propio rótulo (ej. nunca aparece literalmente la palabra "FIRMA"
        # en el PDF).
        # 🐛 Corregido: una sección de cualquier otro tipo sin `titulo`
        # (válido — ej. un grupo_campos cuyas propias etiquetas ya narran el
        # contenido, como "DIAGNÓSTICO PRESUNTIVO"/"DERIVACIÓN" en un
        # informe real) imprimía el nombre interno del enum en mayúsculas
        # ("GRUPO_CAMPOS") como si fuera un rótulo real — nunca tuvo
        # fallback antes porque ninguna sección cargada hasta ahora se
        # había dejado sin título. Ahora, sin título, simplemente no hay
        # línea de encabezado — igual que encabezado/firma/firma_doble/
        # firma_triple.
        if tipo_seccion not in ("encabezado", "firma", "firma_doble", "firma_triple") and seccion.get("titulo"):
            bloque.append(Paragraph(escape(seccion["titulo"].upper()), estilos["seccion_titulo"]))
        bloque.extend(renderizador(seccion.get("datos"), estilos))
        if tipo_seccion in ("firma", "firma_doble", "firma_triple"):
            # Nunca partir una firma entre dos páginas — es corta (nombre,
            # cargo, un par de líneas fijas) y una línea huérfana al
            # arrancar la página siguiente se ve roto. A diferencia de las
            # demás secciones (donde solo el título + primer elemento se
            # mantienen juntos, para no forzar un texto_libre largo entero
            # a la página siguiente), aquí TODO el bloque va junto.
            elementos.append(KeepTogether(bloque))
        else:
            elementos.append(KeepTogether(bloque[:2]))
            elementos.extend(bloque[2:])
        elementos.append(Spacer(1, 6))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=1.1 * cm + ALTO_BANDA_ENCABEZADO + 0.9 * cm,
        bottomMargin=1.6 * cm + ALTO_BANDA_PIE + 0.9 * cm,
    )
    marco = lambda canvas_obj, doc_obj: _dibujar_marco_pagina(  # noqa: E731
        canvas_obj, doc_obj, imagen_encabezado, imagen_pie, imagen_fondo,
    )
    doc.build(elementos, onFirstPage=marco, onLaterPages=marco)
    buffer.seek(0)
    return buffer
