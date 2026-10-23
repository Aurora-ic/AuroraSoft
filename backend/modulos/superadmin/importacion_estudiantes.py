"""Importación masiva de estudiantes desde Excel.

Flujo (ver README de la fase): plantilla -> subir+validar -> vista previa
-> confirmar. No se guarda el archivo en ningún lado: se procesa entero en
memoria y se descarta.

Reutiliza `Persona`, `codigo_institucional`, `tipo_perfil`, `NivelEducativo`,
`Grado`, `Seccion` y `MatriculaAcademica` tal como ya existen — esta
importación produce EXACTAMENTE los mismos registros que un alta manual
correcta, porque usa las mismas funciones de `crud.py`
(`buscar_persona_por_codigo`, `matricular_persona_en_seccion`) para la parte
que ya estaba resuelta, y solo añade el parseo/validación del Excel.

No toca consentimientos en absoluto (punto 12): un estudiante importado
nunca queda "autorizado" para nada por el solo hecho de existir.
"""

import io
import re
from datetime import datetime, date
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, crud

# ==========================================
# CONFIGURACIÓN DE LA PLANTILLA / LÍMITES DE ARCHIVO (punto 16)
# ==========================================
# codigo_institucional es EL identificador funcional de esta importación
# (punto 3) — nunca el id interno, nunca el DNI. anio_escolar se añade a la
# lista mínima que pedía la fase porque Sección está anclada a un año
# escolar concreto (ver Núcleo del Estudiante): sin este dato no hay forma
# de saber a qué "3° B" se refiere una fila, 2025 o 2026.
COLUMNAS = [
    "codigo_institucional", "nombres", "apellidos", "documento_identidad",
    "fecha_nacimiento", "genero", "nivel_educativo", "grado", "seccion",
    "turno", "anio_escolar",
]
COLUMNAS_OBLIGATORIAS = {"codigo_institucional", "nombres", "apellidos"}

# Nada de esto necesita guardar el archivo en disco: se procesa entero en
# memoria (bytes -> openpyxl -> filas -> se descarta) y nunca se re-sirve.
TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024   # 5 MiB — de sobra para texto plano
FILAS_MAXIMAS = 2000                     # "cientos de estudiantes", con margen
LONGITUD_MAXIMA_CAMPO = 200

# 🆕 PASO 2 — "sexo" (columna `genero`) es un CATÁLOGO ABIERTO, no un enum
# cerrado: cualquier texto no vacío se acepta tal cual (nunca es motivo de
# error de fila). Este diccionario ya NO valida — solo normaliza el
# capitalizado de los dos valores más comunes para que "MASCULINO"/
# "masculino"/"Masculino" no queden como tres grafías distintas en la base;
# cualquier otro valor (p. ej. "Otro", "No binario", "M") se guarda
# exactamente como se escribió. Ver auditoría de arquitectura genérica,
# punto 2-c (el SexoEnum cerrado del endpoint público de examen es un
# problema aparte, deliberadamente no tocado aquí).
_GENERO_NORMALIZADO = {"masculino": "Masculino", "femenino": "Femenino"}
DOCUMENTO_PATRON = re.compile(r"^[A-Za-z0-9\-]{4,20}$")

# 🆕 PASO 2 — nombres de columna cuya AUSENCIA en una fila nunca es un error,
# pero sí se reporta como "datos incompletos" para que quien importa sepa que
# falta completar algo después (nunca bloquea el alta/actualización).
CAMPOS_OPCIONALES_REPORTABLES = ("genero", "fecha_nacimiento")


class ArchivoInvalido(Exception):
    """Error del ARCHIVO en sí (extensión, tamaño, estructura, encabezados) —
    distinto de un error de FILA, que se reporta como parte del resultado,
    no como una excepción."""


def _error(campo: str, problema: str, valor_recibido, correccion_esperada: str) -> dict:
    return {
        "campo": campo,
        "problema": problema,
        "valor_recibido": "" if valor_recibido is None else str(valor_recibido),
        "correccion_esperada": correccion_esperada,
    }


def _normalizar_encabezado(valor) -> str:
    return str(valor or "").strip().lower().replace(" ", "_")


def _celda_a_texto(valor) -> str:
    """Cualquier celda se convierte a texto plano, recortado y sin
    caracteres de control — un valor "raro" (o una fórmula, ver más abajo)
    nunca llega tal cual a la base de datos."""
    if valor is None:
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.date().isoformat() if isinstance(valor, datetime) else valor.isoformat()
    texto = str(valor).strip()
    texto = "".join(ch for ch in texto if ch in ("\t", "\n") or ord(ch) >= 32)
    return texto[:LONGITUD_MAXIMA_CAMPO]


# ==========================================
# 1. PLANTILLA
# ==========================================
def generar_plantilla(db: Session, institucion_id: int) -> io.BytesIO:
    """Genera la plantilla oficial .xlsx. Incluye ejemplos y, en una segunda
    hoja, la estructura académica YA CREADA en esta institución — para que
    quien complete el Excel sepa exactamente qué nombres de nivel/grado/
    sección/año son válidos, sin adivinar."""
    wb = Workbook()

    ws = wb.active
    ws.title = "Estudiantes"
    encabezado_negrita = Font(bold=True)
    ws.append(COLUMNAS)
    for celda in ws[1]:
        celda.font = encabezado_negrita
    ws.append([
        "E-0001", "Ana", "Torres Quispe", "71234567", "2012-03-15", "Femenino",
        "Secundaria", "3°", "A", "Mañana", "2026",
    ])
    ws.append([
        "E-0002", "Luis", "Ramírez Paredes", "", "", "",
        "", "", "", "", "",
    ])

    instrucciones = wb.create_sheet("Instrucciones")
    filas_instrucciones = [
        ("Columna", "Obligatoria", "Formato / valores válidos"),
        ("codigo_institucional", "Sí", "Texto único por alumno dentro del colegio (no el DNI). Es la clave para crear o actualizar."),
        ("nombres", "Sí", "Texto."),
        ("apellidos", "Sí", "Texto."),
        ("documento_identidad", "No", "Letras/números/guiones, 4 a 20 caracteres. Único dentro del colegio si se indica."),
        ("fecha_nacimiento", "No", "AAAA-MM-DD. Vacía si no se conoce: el alumno se crea/actualiza igual, "
         "sin error. Solo se guarda la fecha — la edad nunca se calcula ni se guarda aquí, se calcula "
         "más adelante cuando se necesite (por ejemplo, al aplicar una prueba)."),
        ("genero", "No", "Texto libre (ej. 'Masculino', 'Femenino', 'Otro'). No hay una lista cerrada de "
         "valores válidos. Vacío si no corresponde: el alumno se crea/actualiza igual, sin error."),
        ("nivel_educativo", "No (requerido si indicas grado)", "Debe existir ya en el colegio (ver hoja 'Estructura académica')."),
        ("grado", "No (requerido si indicas sección)", "Debe existir ya bajo ese nivel."),
        ("seccion", "No", "Debe existir ya bajo ese grado, PARA EL anio_escolar indicado."),
        ("turno", "No", "Debe coincidir con el turno de esa sección, si la sección tiene uno definido."),
        ("anio_escolar", "No (requerido si indicas sección)", "Número de 4 dígitos, ej. 2026."),
        ("", "", ""),
        ("Ninguna sección/grado/nivel se crea automáticamente.", "", "Créalos antes desde la administración académica."),
        ("Si el codigo_institucional ya existe en el colegio, esa fila ACTUALIZA a ese alumno (no crea uno nuevo).", "", ""),
        ("Dejar genero y/o fecha_nacimiento vacíos NUNCA es un error: el alumno se crea/actualiza igual.", "",
         "El resultado de la importación marca esas filas como 'datos incompletos' para que las completes después."),
    ]
    for fila in filas_instrucciones:
        instrucciones.append(fila)
    for celda in instrucciones[1]:
        celda.font = encabezado_negrita

    estructura = wb.create_sheet("Estructura académica")
    estructura.append(["Nivel educativo", "Grado", "Sección", "Turno", "Año escolar"])
    for celda in estructura[1]:
        celda.font = encabezado_negrita
    filas_estructura = (
        db.query(models.NivelEducativo.nombre, models.Grado.nombre, models.Seccion.nombre,
                 models.Seccion.turno, models.Seccion.anio_escolar)
        .join(models.Grado, models.Grado.nivel_educativo_id == models.NivelEducativo.id)
        .join(models.Seccion, models.Seccion.grado_id == models.Grado.id)
        .filter(models.NivelEducativo.institucion_id == institucion_id)
        .order_by(models.NivelEducativo.orden, models.Grado.orden, models.Seccion.anio_escolar.desc(), models.Seccion.nombre)
        .all()
    )
    for nivel, grado, seccion, turno, anio in filas_estructura:
        estructura.append([nivel, grado, seccion, turno or "", anio])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ==========================================
# 2. LECTURA Y VALIDACIÓN DE ARCHIVO (punto 16 + 5)
# ==========================================
def leer_filas_excel(contenido: bytes, nombre_archivo: str) -> list[dict]:
    """Convierte el archivo subido en una lista de filas {columna: texto}.

    Nunca confía solo en la extensión: exige que openpyxl pueda abrirlo como
    un .xlsx real. Se carga con `data_only=True`, así que si una celda tiene
    una FÓRMULA se lee su último valor calculado, nunca la fórmula en sí —
    cierra de raíz el riesgo de "inyección de fórmulas" sin necesitar más
    lógica: lo que entra a la base es siempre texto plano, nunca una
    expresión que algo más adelante pudiera evaluar.
    """
    if not nombre_archivo.lower().endswith(".xlsx"):
        raise ArchivoInvalido("Solo se aceptan archivos .xlsx (Excel). Ese archivo no tiene esa extensión.")
    if not contenido:
        raise ArchivoInvalido("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise ArchivoInvalido(
            f"El archivo pesa más del máximo permitido ({TAMANO_MAXIMO_BYTES // (1024 * 1024)} MiB)."
        )
    try:
        wb = load_workbook(io.BytesIO(contenido), data_only=True, read_only=True)
    except Exception:
        raise ArchivoInvalido("El archivo no es un .xlsx válido o está dañado.")

    try:
        ws = wb.worksheets[0]
        filas_iter = ws.iter_rows(values_only=True)
        try:
            encabezados_crudos = next(filas_iter)
        except StopIteration:
            raise ArchivoInvalido("El archivo no tiene ninguna fila, ni siquiera el encabezado.")

        encabezados = [_normalizar_encabezado(h) for h in encabezados_crudos]
        faltantes = COLUMNAS_OBLIGATORIAS - set(encabezados)
        if faltantes:
            raise ArchivoInvalido(
                "Faltan columnas obligatorias en el encabezado: "
                f"{', '.join(sorted(faltantes))}. Descarga la plantilla oficial y no "
                "cambies los nombres de columna de la primera fila."
            )
        indice = {nombre: pos for pos, nombre in enumerate(encabezados) if nombre in COLUMNAS}

        filas = []
        for fila_cruda in filas_iter:
            if fila_cruda is None or all(v is None or str(v).strip() == "" for v in fila_cruda):
                continue  # fila completamente vacía — se ignora, no es un dato ni un error
            fila = {columna: _celda_a_texto(fila_cruda[pos] if pos < len(fila_cruda) else None)
                    for columna, pos in indice.items()}
            filas.append(fila)
            if len(filas) > FILAS_MAXIMAS:
                raise ArchivoInvalido(f"El archivo supera el máximo de {FILAS_MAXIMAS} filas por importación.")
        return filas
    finally:
        wb.close()


def _parsear_fecha(texto: str):
    texto = texto.strip()
    if not texto:
        return None, None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date(), None
        except ValueError:
            continue
    return None, "Formato de fecha no reconocido."


def _parsear_anio(texto: str):
    texto = texto.strip()
    if not texto:
        return None, None
    try:
        anio = int(float(texto))  # celdas numéricas de Excel a veces llegan como "2026.0"
    except ValueError:
        return None, "El año escolar debe ser un número (ej. 2026)."
    if anio < 2000 or anio > 2100:
        return None, "El año escolar no es un valor razonable."
    return anio, None


def _precargar_estructura_academica(db: Session, institucion_id: int):
    """Trae TODA la estructura académica del colegio (NivelEducativo/Grado/
    Seccion) en 3 queries, no una por fila — hallazgo de auditoría, sesión
    2026-10-16: `validar_filas` hacía hasta 4 queries de estructura POR FILA
    (nivel, grado + su fallback "existe en otro nivel", sección + su
    fallback "existe con otro año"), que con 2000-5000 filas significa
    miles de round-trips. La estructura académica de un colegio es chica
    (decenas de niveles/grados/secciones, nunca miles) así que se precarga
    completa, sin filtrar por lo que aparece en el archivo — a diferencia de
    `Persona` más abajo, que sí se acota a los códigos/documentos del
    archivo porque el padrón de un colegio grande puede tener miles de filas.

    Devuelve 4 diccionarios que replican EXACTAMENTE la semántica de las
    queries que reemplazan (mismo criterio de comparación: nombre en
    minúsculas, mismo alcance institución/nivel/grado):
    - `por_nombre`: NivelEducativo por nombre en minúsculas.
    - `por_nivel_y_nombre`: Grado por (nivel_educativo_id, nombre en minúsculas).
    - `por_nombre_institucion`: Grado por nombre en minúsculas, CUALQUIER
      nivel — para el fallback "existe pero en otro nivel".
    - `por_grado_nombre_anio`: Seccion por (grado_id, nombre en minúsculas, año).
    - `por_grado_y_nombre`: Seccion por (grado_id, nombre en minúsculas),
      CUALQUIER año — para el fallback "existe pero no para ese año".
    """
    niveles_por_nombre = {
        n.nombre.lower(): n
        for n in db.query(models.NivelEducativo)
        .filter(models.NivelEducativo.institucion_id == institucion_id).all()
    }
    grados = db.query(models.Grado).filter(models.Grado.institucion_id == institucion_id).all()
    grados_por_nivel_y_nombre = {(g.nivel_educativo_id, g.nombre.lower()): g for g in grados}
    grados_por_nombre_institucion: dict[str, models.Grado] = {}
    for g in grados:
        grados_por_nombre_institucion.setdefault(g.nombre.lower(), g)

    secciones = db.query(models.Seccion).filter(models.Seccion.institucion_id == institucion_id).all()
    secciones_por_grado_nombre_anio = {
        (s.grado_id, s.nombre.lower(), s.anio_escolar): s for s in secciones
    }
    secciones_por_grado_y_nombre: dict[tuple[int, str], models.Seccion] = {}
    for s in secciones:
        secciones_por_grado_y_nombre.setdefault((s.grado_id, s.nombre.lower()), s)

    return (
        niveles_por_nombre, grados_por_nivel_y_nombre, grados_por_nombre_institucion,
        secciones_por_grado_nombre_anio, secciones_por_grado_y_nombre,
    )


def _precargar_personas_del_archivo(db: Session, institucion_id: int, filas_crudas: list[dict]):
    """Trae, en 2 queries (no una por fila), solo las `Persona` cuyo código o
    documento aparece en ESTE archivo — a diferencia de la estructura
    académica, el padrón completo de un colegio puede tener miles de filas,
    así que cargarlo entero sería peor que el N+1 que se está arreglando.
    """
    codigos = {
        c for c in (fila.get("codigo_institucional", "").strip() for fila in filas_crudas) if c
    }
    documentos = {
        d for d in (fila.get("documento_identidad", "").strip() for fila in filas_crudas) if d
    }
    personas_por_codigo = {
        p.codigo_institucional: p
        for p in db.query(models.Persona).filter(
            models.Persona.institucion_id == institucion_id,
            models.Persona.codigo_institucional.in_(codigos),
        ).all()
    } if codigos else {}
    personas_por_documento = {
        p.documento_identidad: p
        for p in db.query(models.Persona).filter(
            models.Persona.institucion_id == institucion_id,
            models.Persona.documento_identidad.in_(documentos),
        ).all()
    } if documentos else {}
    return personas_por_codigo, personas_por_documento


def validar_filas(db: Session, institucion_id: int, filas_crudas: list[dict]) -> dict:
    """Valida cada fila SIN escribir nada en la base (punto 1, 11).

    Clasifica cada fila en exactamente una de: nuevo, actualizado, duplicado
    (repetido dentro del propio archivo), error. Nunca dos personas nuevas
    para el mismo código (punto 6): si el código ya existe en la
    institución, la fila se trata como actualización, no como alta.
    """
    (
        niveles_por_nombre, grados_por_nivel_y_nombre, grados_por_nombre_institucion,
        secciones_por_grado_nombre_anio, secciones_por_grado_y_nombre,
    ) = _precargar_estructura_academica(db, institucion_id)
    personas_por_codigo, personas_por_documento = _precargar_personas_del_archivo(
        db, institucion_id, filas_crudas
    )

    codigos_vistos: dict[str, int] = {}
    documentos_vistos: dict[str, int] = {}
    resultados = []
    resumen = {"nuevos": 0, "actualizados": 0, "duplicados": 0, "errores": 0}
    # 🆕 PASO 2 — contador aparte, no dentro de `resumen`: `resumen` es
    # mutuamente excluyente por fila (nuevos+actualizados+duplicados+errores
    # == total_filas) y varias pruebas ya existentes comparan ese dict por
    # igualdad exacta; "datos incompletos" es una señal ORTOGONAL (una fila
    # 'nuevo' puede tener o no datos incompletos), así que vive en su propia
    # clave del resultado.
    filas_con_datos_incompletos = 0

    for numero, cruda in enumerate(filas_crudas, start=2):  # la fila 1 es el encabezado
        errores = []
        codigo = cruda.get("codigo_institucional", "").strip()
        nombres = cruda.get("nombres", "").strip()
        apellidos = cruda.get("apellidos", "").strip()
        documento = cruda.get("documento_identidad", "").strip() or None
        genero_txt = cruda.get("genero", "").strip()
        nivel_nombre = cruda.get("nivel_educativo", "").strip() or None
        grado_nombre = cruda.get("grado", "").strip() or None
        seccion_nombre = cruda.get("seccion", "").strip() or None
        turno = cruda.get("turno", "").strip() or None
        anio_txt = cruda.get("anio_escolar", "").strip()

        if not codigo:
            errores.append(_error("codigo_institucional", "vacío", codigo,
                                   "Indica un código institucional único para este alumno."))
        if not nombres:
            errores.append(_error("nombres", "vacío", nombres, "El nombre es obligatorio."))
        if not apellidos:
            errores.append(_error("apellidos", "vacío", apellidos, "El apellido es obligatorio."))

        # --- Identificador: duplicado DENTRO del propio archivo ---
        if codigo and codigo in codigos_vistos:
            resumen["duplicados"] += 1
            resultados.append({
                "fila": numero, "accion": "duplicado", "codigo_institucional": codigo,
                "nombres": nombres, "apellidos": apellidos,
                "errores": [_error(
                    "codigo_institucional", "duplicado dentro del archivo", codigo,
                    f"Ya aparece en la fila {codigos_vistos[codigo]} de este mismo Excel. "
                    "Deja una sola fila por alumno.",
                )],
            })
            continue
        if codigo:
            codigos_vistos[codigo] = numero

        # --- Datos personales ---
        fecha_nacimiento = None
        fecha_txt = cruda.get("fecha_nacimiento", "").strip()
        if fecha_txt:
            fecha_nacimiento, motivo = _parsear_fecha(fecha_txt)
            if motivo:
                errores.append(_error("fecha_nacimiento", motivo, fecha_txt, "Usa el formato AAAA-MM-DD."))
            elif fecha_nacimiento > date.today():
                errores.append(_error("fecha_nacimiento", "es una fecha futura", fecha_txt,
                                       "Revisa el año de nacimiento."))

        # 🆕 PASO 2 — catálogo abierto: cualquier texto no vacío se acepta tal
        # cual (normalizando solo el capitalizado de los dos valores más
        # comunes); nunca es un error de fila.
        genero = _GENERO_NORMALIZADO.get(genero_txt.lower(), genero_txt) if genero_txt else None

        if documento and not DOCUMENTO_PATRON.match(documento):
            errores.append(_error("documento_identidad", "formato inválido", documento,
                                   "Usa solo letras, números y guiones, entre 4 y 20 caracteres."))

        # --- Estructura académica: se resuelve en cadena Nivel -> Grado -> Sección ---
        if grado_nombre and not nivel_nombre:
            errores.append(_error("nivel_educativo", "falta", "",
                                   "Para indicar un grado también debes indicar su nivel educativo."))
        if seccion_nombre and not grado_nombre:
            errores.append(_error("grado", "falta", "",
                                   "Para indicar una sección también debes indicar su grado."))

        nivel = grado = seccion = None
        anio = None
        if nivel_nombre:
            nivel = niveles_por_nombre.get(nivel_nombre.lower())
            if not nivel:
                errores.append(_error("nivel_educativo", "no existe en esta institución", nivel_nombre,
                                       "Crea este nivel educativo antes de importar, o corrige el nombre."))

        if grado_nombre and nivel:
            grado = grados_por_nivel_y_nombre.get((nivel.id, grado_nombre.lower()))
            if not grado:
                existe_en_otro_nivel = grados_por_nombre_institucion.get(grado_nombre.lower())
                if existe_en_otro_nivel:
                    errores.append(_error("grado", "pertenece a otro nivel educativo", grado_nombre,
                                           f"Ese grado existe, pero bajo un nivel distinto de '{nivel_nombre}'."))
                else:
                    errores.append(_error("grado", "no existe en ese nivel", grado_nombre,
                                           "Crea este grado antes de importar, o corrige el nombre."))

        if seccion_nombre and grado:
            anio, motivo_anio = _parsear_anio(anio_txt)
            if motivo_anio:
                errores.append(_error("anio_escolar", motivo_anio, anio_txt,
                                       "Indica el año escolar de la sección (ej. 2026)."))
            elif anio is None:
                errores.append(_error("anio_escolar", "falta", "",
                                       "Para indicar una sección también debes indicar su año escolar."))
            else:
                seccion = secciones_por_grado_nombre_anio.get((grado.id, seccion_nombre.lower(), anio))
                if not seccion:
                    existe_mismo_nombre = secciones_por_grado_y_nombre.get((grado.id, seccion_nombre.lower()))
                    if existe_mismo_nombre:
                        # 🔒 Punto 9 — nunca se crea la sección automáticamente.
                        errores.append(_error(
                            "anio_escolar", "esa sección no existe para ese año escolar", anio_txt,
                            f"La sección '{seccion_nombre}' de ese grado existe, pero no para "
                            f"el año {anio}. Crea esa sección para ese año antes de importar.",
                        ))
                    else:
                        errores.append(_error("seccion", "no existe en ese grado", seccion_nombre,
                                               "Crea esta sección antes de importar, o corrige el nombre."))
                elif turno and seccion.turno and turno.lower() != seccion.turno.lower():
                    errores.append(_error("turno", "incompatible con la sección", turno,
                                           f"La sección '{seccion_nombre}' tiene el turno '{seccion.turno}'."))

        # --- Documento duplicado DENTRO del propio archivo ---
        # 🔒 El chequeo contra la BD (más abajo) solo ve conflictos con
        # personas que YA EXISTEN; dos filas NUEVAS del mismo archivo con el
        # mismo documento no chocan con nada en la BD todavía, pero sí
        # chocarían entre sí al confirmar (violarían la restricción UNIQUE de
        # documento_identidad por institución) — se detecta aquí, antes de
        # escribir nada, en vez de dejar que reviente a mitad de la
        # transacción de `aplicar_importacion`.
        if documento and documento in documentos_vistos:
            errores.append(_error(
                "documento_identidad", "duplicado dentro del archivo", documento,
                f"Ya aparece en la fila {documentos_vistos[documento]} de este mismo Excel.",
            ))
        elif documento:
            documentos_vistos[documento] = numero

        # --- ¿Nuevo o actualización? Nunca confía en nada más que el código + institución del usuario ---
        # 🆕 `personas_por_codigo`/`personas_por_documento` ya se precargaron
        # en bloque (ver _precargar_personas_del_archivo) — antes esto era
        # una query (`buscar_persona_por_codigo`) más otra (conflicto de
        # documento) POR FILA.
        persona_existente = None
        if codigo:
            persona_existente = personas_por_codigo.get(codigo)
            if persona_existente and persona_existente.tipo_perfil != "estudiante":
                errores.append(_error(
                    "codigo_institucional", "ya usado por una persona que no es estudiante", codigo,
                    f"Ya existe una persona con ese código y tipo_perfil='{persona_existente.tipo_perfil}'; "
                    "usa otro código.",
                ))
            elif documento:
                conflicto = personas_por_documento.get(documento)
                if conflicto and conflicto.id != (persona_existente.id if persona_existente else -1):
                    errores.append(_error(
                        "documento_identidad", "ya usado por otro estudiante de esta institución", documento,
                        "Cada documento debe ser único dentro del colegio; revisa si es un duplicado real.",
                    ))

        if errores:
            accion = "error"
            resumen["errores"] += 1
        elif persona_existente:
            accion = "actualizado"
            resumen["actualizados"] += 1
        else:
            accion = "nuevo"
            resumen["nuevos"] += 1

        # 🆕 PASO 2 — señal puramente informativa, nunca bloqueante: qué
        # campos demográficos opcionales quedaron vacíos en una fila que SÍ
        # se va a crear/actualizar. No es un error (no cambia `accion`) ni
        # entra en `resumen` (ver el comentario junto a filas_con_datos_incompletos).
        datos_incompletos = []
        if accion in ("nuevo", "actualizado"):
            if not genero:
                datos_incompletos.append("genero")
            if not fecha_nacimiento:
                datos_incompletos.append("fecha_nacimiento")
            if datos_incompletos:
                filas_con_datos_incompletos += 1

        resultados.append({
            "fila": numero,
            "accion": accion,
            "codigo_institucional": codigo,
            "nombres": nombres,
            "apellidos": apellidos,
            "documento_identidad": documento,
            "fecha_nacimiento": fecha_nacimiento.isoformat() if fecha_nacimiento else None,
            "genero": genero,
            "datos_incompletos": datos_incompletos,
            "estructura_academica": (
                {
                    "nivel_id": nivel.id if nivel else None,
                    "nivel": nivel_nombre,
                    "grado_id": grado.id if grado else None,
                    "grado": grado_nombre,
                    "seccion_id": seccion.id if seccion else None,
                    "seccion": seccion_nombre,
                    "anio_escolar": anio,
                    "turno": turno,
                }
                if (nivel_nombre or grado_nombre or seccion_nombre) else None
            ),
            "persona_id_existente": persona_existente.id if persona_existente else None,
            "errores": errores,
        })

    return {
        "total_filas": len(filas_crudas),
        "resumen": resumen,
        "filas_con_datos_incompletos": filas_con_datos_incompletos,
        "filas": resultados,
    }


# ==========================================
# 3. CONFIRMACIÓN — operación atómica (punto 11)
# ==========================================
def aplicar_importacion(db: Session, institucion_id: int, resultado_validacion: dict, usuario_id: int) -> dict:
    """Aplica TODAS las filas 'nuevo'/'actualizado' en una sola transacción.

    Las filas 'duplicado'/'error' nunca se escriben — no participan de la
    operación atómica porque nunca se intenta escribirlas, no porque hayan
    "fallado" dentro de la transacción. Si algo inesperado sí falla a mitad
    de camino (una carrera con otro proceso, por ejemplo), se revierte TODA
    la transacción: no queda medio lote aplicado.

    NUNCA toca evaluaciones/inscripciones/diagnósticos/informes, y NUNCA crea
    ni modifica un consentimiento (punto 12, 14).
    """
    aplicadas_nuevos = 0
    aplicadas_actualizados = 0
    detalle = []

    # 🆕 Precarga en bloque de las Personas a ACTUALIZAR (hallazgo de
    # auditoría, sesión 2026-10-16) — antes era una query
    # (`buscar_persona_por_codigo`) POR FILA 'actualizado' dentro de este
    # mismo lazo de escritura, además del N+1 ya arreglado en `validar_filas`.
    codigos_a_actualizar = {
        fila["codigo_institucional"] for fila in resultado_validacion["filas"]
        if fila["accion"] == "actualizado"
    }
    personas_a_actualizar = {
        p.codigo_institucional: p
        for p in db.query(models.Persona).filter(
            models.Persona.institucion_id == institucion_id,
            models.Persona.codigo_institucional.in_(codigos_a_actualizar),
        ).all()
    } if codigos_a_actualizar else {}

    try:
        for fila in resultado_validacion["filas"]:
            if fila["accion"] not in ("nuevo", "actualizado"):
                continue  # duplicado / error: nunca se escribe

            estructura = fila.get("estructura_academica")
            seccion_id = estructura["seccion_id"] if estructura else None

            if fila["accion"] == "nuevo":
                persona = models.Persona(
                    institucion_id=institucion_id,
                    tipo_perfil="estudiante",
                    codigo_institucional=fila["codigo_institucional"],
                    nombres=fila["nombres"],
                    apellidos=fila["apellidos"],
                    documento_identidad=fila["documento_identidad"],
                    fecha_nacimiento=fila["fecha_nacimiento"],
                    genero=fila["genero"],
                )
                db.add(persona)
                db.flush()  # necesita persona.id para poder matricularla
                aplicadas_nuevos += 1
            else:
                persona = personas_a_actualizar[fila["codigo_institucional"]]
                # 🔒 Solo se tocan datos básicos y matrícula (punto 7) — nunca
                # institucion_id, tipo_perfil, ni nada de historial clínico.
                persona.nombres = fila["nombres"]
                persona.apellidos = fila["apellidos"]
                if fila["documento_identidad"]:
                    persona.documento_identidad = fila["documento_identidad"]
                if fila["genero"]:
                    persona.genero = fila["genero"]
                if fila["fecha_nacimiento"]:
                    persona.fecha_nacimiento = fila["fecha_nacimiento"]
                db.flush()
                aplicadas_actualizados += 1

            if seccion_id:
                # Reutiliza la MISMA función que usa el alta manual (punto 2 y
                # 8): cierra la matrícula vigente y abre una nueva sin tocar
                # ninguna Inscripcion histórica.
                # commit=False: esta función corre dentro del try/commit-al-final
                # de aplicar_importacion — un commit interno aquí confirmaría en
                # disco también las filas anteriores del lote que aún solo
                # estaban con flush(), rompiendo la atomicidad de todo el batch.
                crud.matricular_persona_en_seccion(
                    db=db, persona=persona, seccion_id=seccion_id, usuario_id=usuario_id,
                    commit=False,
                )

            detalle.append({
                "fila": fila["fila"], "accion": fila["accion"],
                "codigo_institucional": fila["codigo_institucional"], "persona_id": persona.id,
                # 🆕 PASO 2 — mismo dato informativo que ya traía /validar,
                # repetido aquí para que la respuesta de /confirmar sea
                # igual de útil sin tener que cruzarla con la de /validar.
                "datos_incompletos": fila.get("datos_incompletos", []),
            })

        db.commit()
    except IntegrityError:
        # 🔒 `/confirmar` re-deriva y re-valida todo contra la BD, pero entre
        # esa validación y este commit puede haber transcurrido una carrera
        # real con otro proceso (p. ej. el mismo codigo_institucional creado
        # por otra vía en ese instante) — antes esto se propagaba como un
        # IntegrityError crudo hasta FastAPI (500 genérico sin explicación);
        # el rollback ya revertía el lote completo correctamente, solo
        # faltaba traducirlo a un error legible, mismo patrón que
        # crear_documento_institucional en modulos/documentos/crud.py.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se pudo confirmar la importación: alguna fila entró en conflicto con un "
                "cambio concurrente en la base de datos (por ejemplo, otro proceso creó el mismo "
                "código institucional justo en este instante). Ningún cambio de este archivo se "
                "aplicó — vuelve a intentarlo."
            ),
        )
    except Exception:
        db.rollback()
        raise

    resumen = dict(resultado_validacion["resumen"])
    resumen["nuevos"] = aplicadas_nuevos
    resumen["actualizados"] = aplicadas_actualizados
    return {
        "total_filas": resultado_validacion["total_filas"],
        "resumen": resumen,
        "filas_con_datos_incompletos": resultado_validacion.get("filas_con_datos_incompletos", 0),
        "detalle": detalle,
    }
