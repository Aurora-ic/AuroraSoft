"""Pruebas unitarias — Dimension.tipo_calculo == 'suma_de_dimensiones' y
DimensionComponente (dimensión compuesta).

    python -m tests.test_dimension_compuesta_unitario

Sin BD ni servidor. Cubre: columnas/tabla/constraints nuevas, los schemas,
la validación de componentes (sin anidar, misma prueba, sin autorreferencia,
sin duplicados), los guards que impiden que una dimensión compuesta tenga
preguntas propias (crear_pregunta/actualizar_pregunta/cargar_test_masivo), y
que el motor de cálculo/reglas tratan la compuesta de forma genérica (segunda
pasada en calcular_resultados_dimensiones, exclusión en el puntaje_total de
evaluar_reglas_interpretacion para no contar doble).
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from fastapi import HTTPException  # noqa: E402

from modulos.educativo import models, schemas, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _FakeQuerySecuencia:
    """Cada .query(Modelo) de calcular_resultados_dimensiones/
    actualizar_dimension se resuelve en un orden FIJO y conocido -- a
    diferencia de un fake que ignora filter() y siempre devuelve lo mismo,
    esto permite que el MISMO modelo (ej. Dimension, consultado dos veces
    con intención distinta) devuelva una respuesta distinta en cada
    llamada, en el orden real en que ocurren. Réplica intencional del mismo
    helper en test_conteo_sintomas_unitario.py -- cada archivo de test
    queda autocontenido para poder correrse solo con `python -m tests.X`."""
    def __init__(self, respuestas_en_orden):
        self._cola = list(respuestas_en_orden)

    def filter(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self._cola.pop(0) if self._cola else []

    def first(self):
        return self._cola.pop(0) if self._cola else None


def test_columna_y_constants():
    print("\nModelo — Dimension.tipo_calculo existe, NOT NULL, default 'items'")
    columna = models.Dimension.__table__.columns["tipo_calculo"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es NOT NULL", columna.nullable is False)
    comprobar("Su server_default es 'items'", columna.server_default.arg == models.TIPO_CALCULO_ITEMS)
    comprobar("TIPOS_CALCULO_DIMENSION_VALIDOS == {'items', 'suma_de_dimensiones', 'conteo_sintomas'}",
              models.TIPOS_CALCULO_DIMENSION_VALIDOS == {"items", "suma_de_dimensiones", "conteo_sintomas"})

    nombres = [c.name for c in models.Dimension.__table__.constraints]
    comprobar("El CHECK constraint ck_dimensiones_tipo_calculo_valido existe", "ck_dimensiones_tipo_calculo_valido" in nombres)


def test_tabla_dimension_componente():
    print("\nModelo — DimensionComponente existe con sus constraints")
    tabla = models.DimensionComponente.__table__
    comprobar("Tabla edu_dimensiones_componentes existe", tabla.name == "edu_dimensiones_componentes")
    cols = tabla.columns
    comprobar("Tiene dimension_compuesta_id, dimension_componente_id, orden",
              {"dimension_compuesta_id", "dimension_componente_id", "orden"} <= set(cols.keys()))

    fk_compuesta = next(iter(cols["dimension_compuesta_id"].foreign_keys))
    comprobar("dimension_compuesta_id -> edu_dimensiones.id con ondelete=CASCADE",
              str(fk_compuesta.target_fullname) == "edu_dimensiones.id" and fk_compuesta.ondelete == "CASCADE")

    fk_componente = next(iter(cols["dimension_componente_id"].foreign_keys))
    comprobar("dimension_componente_id -> edu_dimensiones.id SIN cascade (eliminar_dimension la bloquea en código)",
              str(fk_componente.target_fullname) == "edu_dimensiones.id" and fk_componente.ondelete is None)

    nombres = [c.name for c in tabla.constraints]
    comprobar("UniqueConstraint uq_edu_dim_componentes_par existe", "uq_edu_dim_componentes_par" in nombres)
    comprobar("CheckConstraint ck_edu_dim_componentes_no_autorreferencia existe",
              "ck_edu_dim_componentes_no_autorreferencia" in nombres)


def test_schemas_exponen_lo_nuevo():
    print("\nschemas — DimensionBase/Update y los nuevos schemas de componentes")
    comprobar("DimensionBase trae 'tipo_calculo' con default 'items'",
              "tipo_calculo" in schemas.DimensionBase.model_fields
              and schemas.DimensionBase(nombre="x").tipo_calculo == "items")
    comprobar("DimensionUpdate permite 'tipo_calculo' (opcional)", "tipo_calculo" in schemas.DimensionUpdate.model_fields)

    from pydantic import ValidationError
    try:
        schemas.DimensionBase(nombre="x", tipo_calculo="promedio_de_dimensiones")
        comprobar("Un tipo_calculo inventado es rechazado por el schema", False)
    except ValidationError:
        comprobar("Un tipo_calculo inventado es rechazado por el schema (ValidationError)", True)

    comprobar("DimensionComponenteItem existe (dimension_componente_id + orden)",
              {"dimension_componente_id", "orden"} <= set(schemas.DimensionComponenteItem.model_fields.keys()))
    comprobar("DimensionComponentesReplace existe (reemplazo completo, lista 'componentes')",
              "componentes" in schemas.DimensionComponentesReplace.model_fields)
    comprobar("DimensionComponenteResponse existe",
              {"id", "dimension_compuesta_id", "dimension_componente_id", "orden"}
              <= set(schemas.DimensionComponenteResponse.model_fields.keys()))


def test_validacion_de_componentes():
    print("\ncrud._validar_componentes_dimension_compuesta — sin anidar, misma prueba, sin autorreferencia/duplicados")

    class _Dim:
        def __init__(self, id, prueba_id, tipo_calculo):
            self.id = id
            self.prueba_id = prueba_id
            self.tipo_calculo = tipo_calculo

    class _DBFalsa:
        def __init__(self, filas):
            self._filas = filas

        def query(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def all(self):
            return self._filas

    compuesta = _Dim(id=1, prueba_id=10, tipo_calculo="suma_de_dimensiones")
    no_compuesta = _Dim(id=1, prueba_id=10, tipo_calculo="items")

    comp_a = _Dim(id=2, prueba_id=10, tipo_calculo="items")
    comp_b = _Dim(id=3, prueba_id=10, tipo_calculo="items")
    comp_otra_prueba = _Dim(id=4, prueba_id=99, tipo_calculo="items")
    comp_a_su_vez_compuesta = _Dim(id=5, prueba_id=10, tipo_calculo="suma_de_dimensiones")

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a, comp_b]), no_compuesta, [2, 3])
        comprobar("Rechaza componentes sobre una dimensión que NO es 'suma_de_dimensiones'", False)
    except Exception as e:
        comprobar("Rechaza componentes sobre una dimensión que NO es 'suma_de_dimensiones'",
                  getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a]), compuesta, [1])
        comprobar("Rechaza que la compuesta sea su propio componente (autorreferencia)", False)
    except Exception as e:
        comprobar("Rechaza que la compuesta sea su propio componente (autorreferencia)",
                  getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a, comp_b]), compuesta, [2, 2])
        comprobar("Rechaza ids de componentes duplicados", False)
    except Exception as e:
        comprobar("Rechaza ids de componentes duplicados", getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a, comp_otra_prueba]), compuesta, [2, 4])
        comprobar("Rechaza un componente que pertenece a OTRA prueba", False)
    except Exception as e:
        comprobar("Rechaza un componente que pertenece a OTRA prueba", getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a_su_vez_compuesta]), compuesta, [5])
        comprobar("Rechaza anidar: un componente que es a su vez 'suma_de_dimensiones'", False)
    except Exception as e:
        comprobar("Rechaza anidar: un componente que es a su vez 'suma_de_dimensiones'",
                  getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a, comp_b]), compuesta, [2, 3])
        comprobar("Acepta una lista válida de componentes 'items' de la misma prueba", True)
    except Exception as e:
        comprobar("Acepta una lista válida de componentes 'items' de la misma prueba", False, f"lanzó {e!r}")

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([]), compuesta, [])
        comprobar("Acepta una lista vacía de componentes (dimensión compuesta sin configurar todavía)", True)
    except Exception as e:
        comprobar("Acepta una lista vacía de componentes", False, f"lanzó {e!r}")

    # 🆕 Auditoría de contenido (sesión 2026-10-12): mezclar 'items' con
    # 'conteo_sintomas' produce un total sin unidad común (misma razón por
    # la que evaluar_reglas_interpretacion ya excluye ambos de su propio
    # SUM en 'puntaje_total' — ver test_puntaje_total_no_cuenta_doble).
    comp_conteo_1 = _Dim(id=6, prueba_id=10, tipo_calculo="conteo_sintomas")
    comp_conteo_2 = _Dim(id=7, prueba_id=10, tipo_calculo="conteo_sintomas")

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_a, comp_conteo_1]), compuesta, [2, 6])
        comprobar("Rechaza mezclar un componente 'items' con uno 'conteo_sintomas'", False)
    except Exception as e:
        comprobar("Rechaza mezclar un componente 'items' con uno 'conteo_sintomas'",
                  getattr(e, "status_code", None) == 400)

    try:
        crud._validar_componentes_dimension_compuesta(_DBFalsa([comp_conteo_1, comp_conteo_2]), compuesta, [6, 7])
        comprobar("Acepta una lista válida de componentes TODOS 'conteo_sintomas' (ej. Vanderbilt)", True)
    except Exception as e:
        comprobar("Acepta una lista válida de componentes TODOS 'conteo_sintomas'", False, f"lanzó {e!r}")


def test_guards_pregunta_no_puede_apuntar_a_compuesta():
    print("\ncrud — ninguna Pregunta puede apuntar a una dimensión 'suma_de_dimensiones'")
    import inspect
    comprobar("crear_pregunta valida la dimensión antes de crear",
              "_validar_dimension_no_compuesta_para_pregunta" in inspect.getsource(crud.crear_pregunta))
    comprobar("actualizar_pregunta valida la dimensión cuando cambia dimension_id",
              "_validar_dimension_no_compuesta_para_pregunta" in inspect.getsource(crud.actualizar_pregunta))
    comprobar("cargar_test_masivo rechaza preguntas cuya dimensión (del mismo lote) es 'suma_de_dimensiones'",
              "TIPO_CALCULO_SUMA_DE_DIMENSIONES" in inspect.getsource(crud.cargar_test_masivo))


def test_actualizar_dimension_bloquea_cambios_riesgosos():
    """La cobertura REAL y exhaustiva de crud.actualizar_dimension (ejecutada
    de verdad contra una BD falsa, los 5 casos: cambiar tipo_calculo/umbral
    con y sin resultados ya calculados, convertir a 'suma_de_dimensiones'
    con y sin preguntas propias, pedir 'conteo_sintomas' sin umbral) vive en
    test_conteo_sintomas_unitario.py::test_actualizar_dimension_bloquea_
    cambios_riesgosos -- es la MISMA función, un solo lugar que la ejecute
    de verdad evita duplicar el mismo fake cinco veces entre dos archivos.
    Aquí solo queda el caso específico de ESTE archivo (convertir a
    'suma_de_dimensiones'), ejecutado de verdad, no solo buscado en el texto."""
    print("\ncrud.actualizar_dimension — EJECUCIÓN real: convertir a 'suma_de_dimensiones' se bloquea si ya hay ResultadoDimension")
    dimension = SimpleNamespace(id=1, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None, nombre="Síntomas")

    class _FakeDB:
        def query(self, *args):
            objetivo = args[0]
            if objetivo is models.Dimension:
                return _FakeQuerySecuencia([dimension])
            propietario = getattr(objetivo, "class_", objetivo)
            if propietario is models.ResultadoDimension:
                # Esta dimensión YA tiene un resultado calculado.
                return _FakeQuerySecuencia([SimpleNamespace()])
            raise AssertionError(f"consulta inesperada a {objetivo!r}")

        def commit(self):
            raise AssertionError("no debía llegar a confirmar nada -- el guard debe frenar antes")

    try:
        crud.actualizar_dimension(_FakeDB(), dimension_id=1,
                                   datos=schemas.DimensionUpdate(tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES))
        comprobar("Con un resultado ya calculado, cambiar tipo_calculo a 'suma_de_dimensiones' debía rechazarse", False)
    except HTTPException as exc:
        comprobar("Con un resultado ya calculado, cambiar tipo_calculo SÍ se rechaza (409), antes de tocar la BD",
                  exc.status_code == 409)
    comprobar("tipo_calculo nunca se modificó en el objeto real", dimension.tipo_calculo == models.TIPO_CALCULO_ITEMS)


def test_eliminar_dimension_bloquea_si_es_componente():
    print("\ncrud.eliminar_dimension — no se puede borrar una dimensión que es componente de otra")
    import inspect
    fuente = inspect.getsource(crud.eliminar_dimension)
    comprobar("Consulta DimensionComponente.dimension_componente_id antes de borrar",
              "dimension_componente_id == dimension_id" in fuente)


def test_motor_de_calculo_segunda_pasada():
    print("\ncrud.calcular_resultados_dimensiones — EJECUCIÓN real: la segunda pasada suma de verdad los componentes YA calculados")
    # Antes esto solo buscaba las palabras "TIPO_CALCULO_SUMA_DE_DIMENSIONES"/
    # "DimensionComponente" en el texto fuente -- lo que no distinguía "la
    # segunda pasada suma bien" de "la segunda pasada existe pero suma mal"
    # (o ni corre). Esto ejecuta la función real contra una BD falsa con dos
    # sub-dimensiones reales (7 y 5) y confirma que la compuesta sale en 12,
    # no en cualquier otro número que también haría aparecer esas palabras.
    agregados = []

    inscripcion = SimpleNamespace(id=1, evaluacion_id=10)
    evaluacion = SimpleNamespace(id=10, prueba_id=100)
    prueba = SimpleNamespace(id=100, nombre_tecnico="SDQ_TEST", escala_minima=0, escala_maxima=10, modo_calculo="likert_suma")
    sub1 = SimpleNamespace(id=1, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None)
    sub2 = SimpleNamespace(id=2, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None)
    compuesta = SimpleNamespace(id=3, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES, conteo_umbral_item=None)
    preguntas = [
        SimpleNamespace(id=1, dimension_id=1, prueba_id=100, es_inverso=False),
        SimpleNamespace(id=2, dimension_id=1, prueba_id=100, es_inverso=False),
        SimpleNamespace(id=3, dimension_id=2, prueba_id=100, es_inverso=False),
    ]
    # sub1 = 3 + 4 = 7; sub2 = 5; compuesta esperada = 7 + 5 = 12 (nunca 0,
    # nunca solo uno de los dos, nunca contado doble).
    respuestas_conjuntas = [
        (SimpleNamespace(puntaje_obtenido=3), preguntas[0]),
        (SimpleNamespace(puntaje_obtenido=4), preguntas[1]),
        (SimpleNamespace(puntaje_obtenido=5), preguntas[2]),
    ]
    # 🆕 Desde el fix de anidamiento en calcular_resultados_dimensiones, la
    # consulta real es un join DimensionComponente + Dimension.tipo_calculo
    # (para detectar un componente anidado), así que cada fila es una tupla
    # (DimensionComponente, tipo_calculo) -- no la fila sola.
    componentes_de_la_compuesta = [
        (SimpleNamespace(dimension_compuesta_id=3, dimension_componente_id=1), models.TIPO_CALCULO_ITEMS),
        (SimpleNamespace(dimension_compuesta_id=3, dimension_componente_id=2), models.TIPO_CALCULO_ITEMS),
    ]

    class _FakeDB:
        def __init__(self):
            self._tablas = {
                models.Inscripcion: _FakeQuerySecuencia([inscripcion]),
                models.Evaluacion: _FakeQuerySecuencia([evaluacion]),
                models.Prueba: _FakeQuerySecuencia([prueba]),
                models.Pregunta: _FakeQuerySecuencia([preguntas]),
                models.RespuestaAlumno: _FakeQuerySecuencia([respuestas_conjuntas]),
                # 1ª llamada a Dimension: TODAS las de la prueba (para el
                # dict de conteo_sintomas -- ninguna lo es aquí). 2ª: solo
                # las 'suma_de_dimensiones' (segunda pasada) -- la compuesta.
                models.Dimension: _FakeQuerySecuencia([[sub1, sub2, compuesta], [compuesta]]),
                models.DimensionComponente: _FakeQuerySecuencia([componentes_de_la_compuesta]),
            }

        def query(self, *modelos):
            return self._tablas[modelos[0]]

        def add(self, obj):
            agregados.append(obj)

        def flush(self):
            pass

    resultado = crud.calcular_resultados_dimensiones(_FakeDB(), inscripcion_id=1)

    comprobar("Se crearon 3 ResultadoDimension (sub1, sub2 y la compuesta -- ninguno descartado)", len(resultado) == 3)
    por_dimension = {r.dimension_id: float(r.puntaje_directo) for r in resultado}
    comprobar("sub1 (ítems propios) sale en 7", por_dimension.get(1) == 7.0, str(por_dimension))
    comprobar("sub2 (ítems propios) sale en 5", por_dimension.get(2) == 5.0, str(por_dimension))
    comprobar("La compuesta sale en 12 = 7 + 5 (suma real de sus componentes YA calculados, no un valor fijo)",
              por_dimension.get(3) == 12.0, str(por_dimension))
    comprobar("Es un ResultadoDimension real guardado vía db.add(), no un valor usado una sola vez y descartado",
              any(r.dimension_id == 3 for r in agregados))


def test_motor_de_calculo_excluye_componente_anidado():
    print("\ncrud.calcular_resultados_dimensiones — FIX: un componente anidado (otra compuesta) se excluye y se loguea, nunca cuenta 0 en silencio")
    # `reemplazar_componentes_de_dimension` ya bloquea esto al ESCRIBIR, pero
    # ese guard no vivía en el camino de CÁLCULO -- antes de este fix, una
    # fila de DimensionComponente apuntando a OTRA compuesta (insertada por
    # fuera de ese endpoint, p. ej. un seed script por ORM directo) producía
    # un puntaje_total silenciosamente incompleto, indistinguible de un
    # componente real sin respuestas. Ahora se detecta, se excluye del
    # cálculo (no se inventa un valor) y queda constancia en el log.
    agregados = []

    inscripcion = SimpleNamespace(id=1, evaluacion_id=10)
    evaluacion = SimpleNamespace(id=10, prueba_id=100)
    prueba = SimpleNamespace(id=100, nombre_tecnico="SDQ_TEST", escala_minima=0, escala_maxima=10, modo_calculo="likert_suma")
    sub1 = SimpleNamespace(id=1, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None)
    otra_compuesta = SimpleNamespace(id=2, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES, conteo_umbral_item=None)
    compuesta = SimpleNamespace(id=3, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES, conteo_umbral_item=None)
    preguntas = [
        SimpleNamespace(id=1, dimension_id=1, prueba_id=100, es_inverso=False),
    ]
    respuestas_conjuntas = [
        (SimpleNamespace(puntaje_obtenido=7), preguntas[0]),
    ]
    # El componente 2 ES una compuesta (anidado, inválido) -- debe excluirse.
    # Solo el componente 1 (sub1=7) debe contar: resultado esperado = 7, no 0.
    componentes_de_la_compuesta = [
        (SimpleNamespace(dimension_compuesta_id=3, dimension_componente_id=1), models.TIPO_CALCULO_ITEMS),
        (SimpleNamespace(dimension_compuesta_id=3, dimension_componente_id=2), models.TIPO_CALCULO_SUMA_DE_DIMENSIONES),
    ]

    class _FakeDB:
        def __init__(self):
            self._tablas = {
                models.Inscripcion: _FakeQuerySecuencia([inscripcion]),
                models.Evaluacion: _FakeQuerySecuencia([evaluacion]),
                models.Prueba: _FakeQuerySecuencia([prueba]),
                models.Pregunta: _FakeQuerySecuencia([preguntas]),
                models.RespuestaAlumno: _FakeQuerySecuencia([respuestas_conjuntas]),
                models.Dimension: _FakeQuerySecuencia([[sub1, otra_compuesta, compuesta], [compuesta]]),
                models.DimensionComponente: _FakeQuerySecuencia([componentes_de_la_compuesta]),
            }

        def query(self, *modelos):
            return self._tablas[modelos[0]]

        def add(self, obj):
            agregados.append(obj)

        def flush(self):
            pass

    resultado = crud.calcular_resultados_dimensiones(_FakeDB(), inscripcion_id=1)
    por_dimension = {r.dimension_id: float(r.puntaje_directo) for r in resultado}
    comprobar("sub1 (ítems propios) sale en 7", por_dimension.get(1) == 7.0, str(por_dimension))
    comprobar("La compuesta EXCLUYE al componente anidado: sale en 7 (solo sub1), nunca en 0",
              por_dimension.get(3) == 7.0, str(por_dimension))


def test_puntaje_total_no_cuenta_doble():
    """Por qué esto SIGUE siendo una verificación por inspección de código:
    la exclusión real corre dentro de un db.query(func.sum(...)).join(...)
    .filter(...) -- un agregado SQL cuyo resultado depende de que la base de
    datos real evalúe el filtro sobre filas reales. Fakearlo de forma
    honesta exigiría reimplementar un motor de consultas que entienda
    expresiones de SQLAlchemy, no solo encolar valores de retorno (que SÍ
    alcanza para funciones como calcular_resultados_dimensiones, donde cada
    .all()/.first() se resuelve en Python puro una vez recibido). La
    cobertura real de este caso específico ya existe contra una BD de
    verdad: 'a puntaje_total rule confirmed not to double-count' en
    verificar_dimension_compuesta_e2e.py (prefijo ZZDIMC)."""
    print("\ncrud.evaluar_reglas_interpretacion — 'puntaje_total' excluye dimensiones compuestas (no cuenta doble)")
    import inspect
    fuente = inspect.getsource(crud.evaluar_reglas_interpretacion)
    comprobar("El join con Dimension excluye tipo_calculo == 'suma_de_dimensiones' del sum()",
              "models.Dimension.tipo_calculo != models.TIPO_CALCULO_SUMA_DE_DIMENSIONES" in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Dimensión compuesta (tipo_calculo/DimensionComponente)")
    print("=" * 72)
    test_columna_y_constants()
    test_tabla_dimension_componente()
    test_schemas_exponen_lo_nuevo()
    test_validacion_de_componentes()
    test_guards_pregunta_no_puede_apuntar_a_compuesta()
    test_actualizar_dimension_bloquea_cambios_riesgosos()
    test_eliminar_dimension_bloquea_si_es_componente()
    test_motor_de_calculo_segunda_pasada()
    test_motor_de_calculo_excluye_componente_anidado()
    test_puntaje_total_no_cuenta_doble()

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
