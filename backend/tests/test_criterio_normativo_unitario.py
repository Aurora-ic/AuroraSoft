"""Pruebas unitarias — Baremo.criterio_normativo / Prueba.criterio_normativo_activo.

    python -m tests.test_criterio_normativo_unitario

Sin BD ni servidor. Cubre: las columnas existen con su default NULL (cero
cambio de comportamiento para las 6 pruebas ya cargadas), los schemas las
exponen, _validar_solapamiento_baremo distingue criterios distintos (no
chocan) de tramos del mismo criterio (sí chocan, exactamente como antes), y
que interpretar_resultados_alumno filtra por el criterio activo de la prueba.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, schemas, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columnas_existen_con_default_null():
    print("\nModelo — columnas nuevas existen, nullable, default NULL")
    baremo_cols = models.Baremo.__table__.columns
    comprobar("Baremo.criterio_normativo existe y es nullable",
              "criterio_normativo" in baremo_cols and baremo_cols["criterio_normativo"].nullable)
    comprobar("Baremo.criterio_normativo no tiene server_default (NULL real, no una etiqueta inventada)",
              baremo_cols["criterio_normativo"].server_default is None)

    prueba_cols = models.Prueba.__table__.columns
    comprobar("Prueba.criterio_normativo_activo existe y es nullable",
              "criterio_normativo_activo" in prueba_cols and prueba_cols["criterio_normativo_activo"].nullable)
    comprobar("Prueba.criterio_normativo_activo no tiene server_default",
              prueba_cols["criterio_normativo_activo"].server_default is None)


def test_schemas_exponen_lo_nuevo():
    print("\nschemas — BaremoBase/BaremoUpdate/PruebaBase/PruebaUpdate exponen lo nuevo")
    comprobar("BaremoBase (y por lo tanto BaremoCreate/Response) trae 'criterio_normativo'",
              "criterio_normativo" in schemas.BaremoBase.model_fields)
    comprobar("BaremoUpdate permite 'criterio_normativo'",
              "criterio_normativo" in schemas.BaremoUpdate.model_fields)
    comprobar("PruebaBase trae 'criterio_normativo_activo'",
              "criterio_normativo_activo" in schemas.PruebaBase.model_fields)
    comprobar("PruebaUpdate permite 'criterio_normativo_activo' (PATCH normal, sin endpoint nuevo)",
              "criterio_normativo_activo" in schemas.PruebaUpdate.model_fields)

    base = {"nombre_tecnico": "X", "nombre_publico": "X"}
    comprobar("Default de criterio_normativo_activo en PruebaCreate es None",
              schemas.PruebaCreate(**base).criterio_normativo_activo is None)
    comprobar("Default de criterio_normativo en BaremoCreate es None",
              schemas.BaremoCreate(dimension_id=1, puntaje_minimo=0, puntaje_maximo=1, nivel="X").criterio_normativo is None)


def test_solapamiento_distingue_criterios():
    print("\ncrud._validar_solapamiento_baremo — dos criterios distintos NO chocan; el mismo criterio SÍ")

    class _Falsa:  # simula una fila models.Baremo existente
        id = 99
        sexo = None
        poblacion = None
        edad_min = None
        edad_max = None
        puntaje_minimo = 8
        puntaje_maximo = 9
        nivel = "Moderada"
        criterio_normativo = None  # criterio clásico

    class _DBFalsa:
        def query(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def all(self):
            return [_Falsa()]

    class _NuevoOtroCriterio:
        sexo = None
        poblacion = None
        edad_min = None
        edad_max = None
        puntaje_minimo = 8
        puntaje_maximo = 9
        criterio_normativo = "corte_peru_2024"  # distinto del existente

    class _NuevoMismoCriterio:
        sexo = None
        poblacion = None
        edad_min = None
        edad_max = None
        puntaje_minimo = 8
        puntaje_maximo = 9
        criterio_normativo = None  # mismo que el existente

    try:
        crud._validar_solapamiento_baremo(_DBFalsa(), _NuevoOtroCriterio(), dimension_id=1)
        comprobar("Mismo rango de puntaje pero criterio_normativo distinto: NO dispara 409", True)
    except Exception as e:
        comprobar("Mismo rango de puntaje pero criterio_normativo distinto: NO dispara 409", False,
                  f"lanzó {e!r}")

    try:
        crud._validar_solapamiento_baremo(_DBFalsa(), _NuevoMismoCriterio(), dimension_id=1)
        comprobar("Mismo rango de puntaje y MISMO criterio_normativo (ambos NULL): SÍ dispara 409", False)
    except Exception as e:
        comprobar("Mismo rango de puntaje y MISMO criterio_normativo (ambos NULL): SÍ dispara 409",
                  getattr(e, "status_code", None) == 409)


def test_interpretar_resultados_alumno_filtra_por_criterio_activo():
    """Por qué esto sigue siendo una verificación por inspección de código,
    no una ejecución real: lo que hay que probar es que, entre DOS filas de
    Baremo que comparten el mismo rango de puntaje pero distinto
    criterio_normativo, la consulta real elige la correcta según
    criterio_normativo_activo -- eso depende de que una base de datos real
    evalúe la condición `Baremo.criterio_normativo == criterio_normativo_
    activo` encadenada con varias otras (sexo/edad/población) sobre filas
    reales. Un fake que solo encola una respuesta por .first() ya conoce de
    antemano cuál fila es "la correcta" (la puse yo al armar el fake), así
    que no prueba el FILTRO, prueba que mi fake esté bien escrito -- mismo
    límite ya documentado en test_conteo_sintomas_unitario.py/test_
    dimension_compuesta_unitario.py para sus propios agregados SQL.

    La cobertura real de este comportamiento específico SÍ existe contra
    Postgres de verdad: tests/verificar_criterio_normativo_e2e.py (prefijo
    ZZCRIT) monta dos tramos reales con distinto criterio_normativo sobre
    el mismo rango, interpreta una inscripción bajo el criterio NULL por
    defecto, y confirma que un PATCH criterio_normativo_activo + reprocesar
    cambia de verdad cuál tramo se usa -- sin re-tomar el examen."""
    print("\ncrud.interpretar_resultados_alumno — lee criterio_normativo_activo de la Prueba y filtra el Baremo por él")
    import inspect
    fuente = inspect.getsource(crud.interpretar_resultados_alumno)
    comprobar("Lee Prueba.criterio_normativo_activo de la prueba de esta inscripción",
              "criterio_normativo_activo" in fuente)
    comprobar("Filtra la consulta de Baremo por Baremo.criterio_normativo == criterio_normativo_activo",
              "models.Baremo.criterio_normativo == criterio_normativo_activo" in fuente)


def test_actualizar_baremo_incluye_criterio_en_la_fusion():
    print("\ncrud.actualizar_baremo — la fusión PATCH-parcial que revalida solapamiento incluye criterio_normativo")
    import inspect
    fuente = inspect.getsource(crud.actualizar_baremo)
    comprobar("La tupla de campos fusionados incluye 'criterio_normativo'",
              '"criterio_normativo"' in fuente)
    comprobar("'criterio_normativo' NO está en los campos bloqueados tras uso (mismo criterio que sexo/poblacion)",
              "criterio_normativo" not in crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Criterio normativo (Baremo/Prueba)")
    print("=" * 72)
    test_columnas_existen_con_default_null()
    test_schemas_exponen_lo_nuevo()
    test_solapamiento_distingue_criterios()
    test_interpretar_resultados_alumno_filtra_por_criterio_activo()
    test_actualizar_baremo_incluye_criterio_en_la_fusion()

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
