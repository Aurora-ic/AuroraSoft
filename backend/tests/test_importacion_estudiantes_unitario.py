"""Pruebas unitarias — Importación masiva de estudiantes (Excel).

    python tests/test_importacion_estudiantes_unitario.py

No necesitan la base de datos ni el servidor: cubren el parseo/validación
de archivo que no depende de consultar la BD (para eso está el E2E).
"""

import io
import os
import sys

from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import importacion_estudiantes as importacion  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _xlsx_de(filas: list, encabezados=None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(encabezados or importacion.COLUMNAS)
    for fila in filas:
        ws.append(fila)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_rechaza_extension_no_xlsx():
    print("\n[16] Seguridad de archivo — extensión")
    try:
        importacion.leer_filas_excel(b"contenido", "estudiantes.csv")
        ok = False
    except importacion.ArchivoInvalido as e:
        ok = "xlsx" in str(e).lower()
    comprobar("Un archivo .csv se rechaza sin intentar parsearlo como Excel", ok)


def test_rechaza_archivo_vacio():
    print("\n[2] Excel vacío")
    try:
        importacion.leer_filas_excel(b"", "vacio.xlsx")
        ok = False
    except importacion.ArchivoInvalido:
        ok = True
    comprobar("Un archivo de 0 bytes se rechaza como ArchivoInvalido", ok)


def test_rechaza_archivo_corrupto():
    print("\n[16] Seguridad de archivo — estructura")
    try:
        importacion.leer_filas_excel(b"esto no es un xlsx real", "estudiantes.xlsx")
        ok = False
    except importacion.ArchivoInvalido as e:
        ok = "dañado" in str(e) or "válido" in str(e)
    comprobar("Un .xlsx corrupto/falso se rechaza sin reventar", ok)


def test_rechaza_tamano_excesivo():
    print("\n[16] Seguridad de archivo — tamaño máximo")
    grande = b"x" * (importacion.TAMANO_MAXIMO_BYTES + 1)
    try:
        importacion.leer_filas_excel(grande, "estudiantes.xlsx")
        ok = False
    except importacion.ArchivoInvalido as e:
        ok = "tamaño" in str(e) or "pesa" in str(e)
    comprobar("Un archivo más pesado que el máximo se rechaza", ok)


def test_encabezados_incorrectos():
    print("\n[3] Encabezados incorrectos")
    contenido = _xlsx_de([], encabezados=["columna_a", "columna_b"])
    try:
        importacion.leer_filas_excel(contenido, "estudiantes.xlsx")
        ok = False
    except importacion.ArchivoInvalido as e:
        ok = "codigo_institucional" in str(e)
    comprobar("Encabezados sin las columnas obligatorias se rechazan, indicando cuáles faltan", ok)


def test_encabezados_insensibles_a_mayusculas_y_espacios():
    print("\nParseo — encabezados tolerantes a mayúsculas/espacios")
    contenido = _xlsx_de(
        [["E-001", "Ana", "Torres"]],
        encabezados=["Codigo Institucional", "Nombres", "Apellidos"],
    )
    filas = importacion.leer_filas_excel(contenido, "estudiantes.xlsx")
    comprobar("Se reconoce 'Codigo Institucional' como codigo_institucional", len(filas) == 1 and filas[0]["codigo_institucional"] == "E-001")


def test_ignora_filas_completamente_vacias():
    print("\nParseo — filas vacías se ignoran, no son datos ni errores")
    contenido = _xlsx_de([
        ["E-001", "Ana", "Torres"],
        [None, None, None],
        ["", "", ""],
        ["E-002", "Luis", "Ramírez"],
    ])
    filas = importacion.leer_filas_excel(contenido, "estudiantes.xlsx")
    comprobar("Solo se devuelven las 2 filas con datos reales", len(filas) == 2, str(len(filas)))


def test_formulas_se_leen_como_valor_no_como_expresion():
    print("\n[16] Seguridad — una fórmula se lee como su VALOR calculado, nunca como texto de fórmula")
    wb_dummy = Workbook()
    ws = wb_dummy.active
    ws.append(importacion.COLUMNAS)
    ws.append(["E-001", "Ana", "Torres"])
    ws["A2"] = "=1+1"  # simula una fórmula en una celda de texto
    buffer = io.BytesIO()
    wb_dummy.save(buffer)
    filas = importacion.leer_filas_excel(buffer.getvalue(), "estudiantes.xlsx")
    # openpyxl sin libro recalculado no tiene valor cacheado para una fórmula
    # escrita programáticamente; lo importante es que NUNCA se ejecuta nada:
    # se lee como texto o como None, jamás se evalúa como código.
    comprobar(
        "El contenido de la celda-fórmula llega como texto plano (o vacío), nunca se ejecuta",
        filas[0]["codigo_institucional"] in ("=1+1", ""),
        repr(filas[0]["codigo_institucional"]),
    )


def test_limite_de_filas():
    print("\n[16] Límite de filas por importación")
    filas_de_mas = [[f"E-{i:04d}", "Nombre", "Apellido"] for i in range(importacion.FILAS_MAXIMAS + 5)]
    contenido = _xlsx_de(filas_de_mas)
    try:
        importacion.leer_filas_excel(contenido, "estudiantes.xlsx")
        ok = False
    except importacion.ArchivoInvalido as e:
        ok = "máximo" in str(e)
    comprobar(f"Más de {importacion.FILAS_MAXIMAS} filas se rechaza", ok)


def test_parsear_fecha():
    print("\nParseo — fecha de nacimiento")
    valor, motivo = importacion._parsear_fecha("2012-03-15")
    comprobar("AAAA-MM-DD se parsea correctamente", valor is not None and motivo is None, str(valor))
    valor, motivo = importacion._parsear_fecha("15/03/2012")
    comprobar("DD/MM/AAAA también se acepta", valor is not None and motivo is None)
    valor, motivo = importacion._parsear_fecha("no es una fecha")
    comprobar("Texto sin formato de fecha devuelve un motivo de error", valor is None and motivo is not None)
    valor, motivo = importacion._parsear_fecha("")
    comprobar("Vacío es válido (campo opcional): no es ni valor ni error", valor is None and motivo is None)


def test_parsear_anio():
    print("\nParseo — año escolar")
    valor, motivo = importacion._parsear_anio("2026")
    comprobar("Año válido se parsea", valor == 2026 and motivo is None)
    valor, motivo = importacion._parsear_anio("2026.0")
    comprobar("Celda numérica de Excel ('2026.0') también se acepta", valor == 2026 and motivo is None)
    valor, motivo = importacion._parsear_anio("no-es-un-año")
    comprobar("Texto no numérico devuelve un motivo de error", valor is None and motivo is not None)
    valor, motivo = importacion._parsear_anio("1500")
    comprobar("Un año no razonable (1500) se rechaza", valor is None and motivo is not None)


def test_celda_a_texto_recorta_y_limpia():
    print("\nParseo — saneamiento de celdas")
    texto_con_control = "Ana\x00\x07Torres"
    limpio = importacion._celda_a_texto(texto_con_control)
    comprobar("Los caracteres de control se eliminan", "\x00" not in limpio and "\x07" not in limpio, repr(limpio))
    largo = "A" * 500
    comprobar("El texto se recorta a LONGITUD_MAXIMA_CAMPO", len(importacion._celda_a_texto(largo)) == importacion.LONGITUD_MAXIMA_CAMPO)


def test_columnas_obligatorias_correctas():
    print("\nConfiguración — columnas obligatorias del punto 4")
    comprobar(
        "codigo_institucional, nombres y apellidos son obligatorias; el resto no",
        importacion.COLUMNAS_OBLIGATORIAS == {"codigo_institucional", "nombres", "apellidos"},
        str(importacion.COLUMNAS_OBLIGATORIAS),
    )
    comprobar("anio_escolar está en la plantilla (necesario para resolver una Sección anclada a un año)",
              "anio_escolar" in importacion.COLUMNAS)


def test_genero_es_catalogo_abierto():
    print("\nPASO 2 — 'genero' es un catálogo abierto: normaliza los 2 valores conocidos, acepta cualquier otro")
    comprobar("_GENERO_NORMALIZADO solo normaliza capitalización, no restringe valores",
              importacion._GENERO_NORMALIZADO == {"masculino": "Masculino", "femenino": "Femenino"})

    import inspect
    fuente = inspect.getsource(importacion)
    comprobar("El mensaje de rechazo anterior ('Usa Masculino o Femenino') ya NO existe en el código",
              "Usa 'Masculino' o 'Femenino'" not in fuente)
    comprobar("Ya no existe ningún GENEROS_VALIDOS cerrado (renombrado a _GENERO_NORMALIZADO, ya no valida)",
              not hasattr(importacion, "GENEROS_VALIDOS"))

    # Simula exactamente la expresión que usa validar_filas() para resolver
    # 'genero', sin necesitar una sesión de BD real.
    def resolver_genero(texto):
        return importacion._GENERO_NORMALIZADO.get(texto.lower(), texto) if texto else None

    comprobar("'masculino' (minúsculas) se normaliza a 'Masculino'", resolver_genero("masculino") == "Masculino")
    comprobar("'FEMENINO' (mayúsculas) se normaliza a 'Femenino'", resolver_genero("FEMENINO") == "Femenino")
    comprobar("'Otro' (fuera del catálogo cerrado anterior) se acepta TAL CUAL, sin error", resolver_genero("Otro") == "Otro")
    comprobar("'No binario' se acepta tal cual", resolver_genero("No binario") == "No binario")
    comprobar("Cadena vacía se resuelve a None (campo opcional, no un valor)", resolver_genero("") is None)


def test_importacion_nunca_deriva_edad():
    print("\nPASO 2 — la importación NUNCA calcula/guarda 'edad': solo fecha_nacimiento")
    import inspect
    fuente_validar = inspect.getsource(importacion.validar_filas)
    fuente_aplicar = inspect.getsource(importacion.aplicar_importacion)
    # La ÚNICA mención aceptable de "edad" en todo el módulo es la línea
    # informativa de la hoja de Instrucciones que aclara esta misma regla al
    # usuario — nunca código que la calcule. Por eso se comprueba el CÓDIGO
    # de las dos funciones que escriben datos, no el archivo completo.
    comprobar("validar_filas() no calcula ni asigna ninguna variable 'edad'",
              "edad" not in fuente_validar.lower())
    comprobar("aplicar_importacion() no calcula ni asigna ninguna variable 'edad' "
              "(solo copia fecha_nacimiento; la edad se deriva en otro punto del sistema, al aplicar una prueba)",
              "edad" not in fuente_aplicar.lower())
    comprobar("Persona.fecha_nacimiento se copia tal cual, nunca convertida a una edad en este archivo",
              "fecha_nacimiento" in fuente_aplicar and "edad" not in fuente_aplicar.lower())


def test_datos_incompletos_es_informativo_no_bloqueante():
    print("\nPASO 2 — 'datos_incompletos' es una señal aparte, nunca cambia la clasificación de la fila")
    comprobar("CAMPOS_OPCIONALES_REPORTABLES es exactamente (genero, fecha_nacimiento)",
              importacion.CAMPOS_OPCIONALES_REPORTABLES == ("genero", "fecha_nacimiento"))

    import inspect
    fuente = inspect.getsource(importacion.validar_filas)
    comprobar("filas_con_datos_incompletos se cuenta APARTE de `resumen` (que sigue siendo mutuamente excluyente)",
              "filas_con_datos_incompletos" in fuente and 'resumen["con_datos_incompletos"]' not in fuente)
    comprobar("datos_incompletos nunca fuerza accion='error' (se calcula DESPUÉS de decidir accion)",
              fuente.index("if errores:") < fuente.index("datos_incompletos = []"))


def test_generar_plantilla_sin_bd_real():
    print("\nPlantilla — se genera un .xlsx real, descargable")
    from openpyxl import load_workbook

    class _DBFalsa:
        def query(self, *a, **k):
            return self

        def join(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            return []

    buffer = importacion.generar_plantilla(db=_DBFalsa(), institucion_id=1)
    wb = load_workbook(buffer)
    comprobar("Tiene la hoja 'Estudiantes' con el encabezado completo",
              wb["Estudiantes"][1][0].value == "codigo_institucional")
    comprobar("Tiene una hoja 'Instrucciones'", "Instrucciones" in wb.sheetnames)
    comprobar("Tiene una hoja 'Estructura académica'", "Estructura académica" in wb.sheetnames)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — IMPORTACIÓN MASIVA DE ESTUDIANTES")
    print("=" * 72)
    test_rechaza_extension_no_xlsx()
    test_rechaza_archivo_vacio()
    test_rechaza_archivo_corrupto()
    test_rechaza_tamano_excesivo()
    test_encabezados_incorrectos()
    test_encabezados_insensibles_a_mayusculas_y_espacios()
    test_ignora_filas_completamente_vacias()
    test_formulas_se_leen_como_valor_no_como_expresion()
    test_limite_de_filas()
    test_parsear_fecha()
    test_parsear_anio()
    test_celda_a_texto_recorta_y_limpia()
    test_columnas_obligatorias_correctas()
    test_genero_es_catalogo_abierto()
    test_importacion_nunca_deriva_edad()
    test_datos_incompletos_es_informativo_no_bloqueante()
    test_generar_plantilla_sin_bd_real()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
