"""Pruebas unitarias — Dimension.tipo_calculo == 'conteo_sintomas' y
Dimension.conteo_umbral_item (conteo de síntomas, ver NICHQ Vanderbilt).

    python -m tests.test_conteo_sintomas_unitario

Sin BD ni servidor. Cubre: columna/constraints nuevas, los schemas (y su
validación cruzada "conteo_sintomas requiere conteo_umbral_item"), el
mecanismo de cálculo en core/algoritmo.py (la distinción real que motivó esta
extensión: contar ítems sobre un umbral NO es lo mismo que sumarlos, incluso
cuando la suma resultante sea mayor), el guard de actualizar_dimension, y la
exclusión en el puntaje_total de evaluar_reglas_interpretacion.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from types import SimpleNamespace  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from modulos.educativo import models, schemas, crud  # noqa: E402
from core import algoritmo  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columna_y_constants():
    print("\nModelo — Dimension.conteo_umbral_item existe, nullable, y el CHECK lo exige para 'conteo_sintomas'")
    columna = models.Dimension.__table__.columns["conteo_umbral_item"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es nullable (solo aplica a 'conteo_sintomas')", columna.nullable is True)
    comprobar("TIPO_CALCULO_CONTEO_SINTOMAS == 'conteo_sintomas'",
              models.TIPO_CALCULO_CONTEO_SINTOMAS == "conteo_sintomas")
    comprobar("TIPOS_CALCULO_DIMENSION_VALIDOS incluye 'conteo_sintomas'",
              models.TIPO_CALCULO_CONTEO_SINTOMAS in models.TIPOS_CALCULO_DIMENSION_VALIDOS)

    nombres = [c.name for c in models.Dimension.__table__.constraints]
    comprobar("El CHECK ck_dimensiones_tipo_calculo_valido existe", "ck_dimensiones_tipo_calculo_valido" in nombres)
    comprobar("El CHECK ck_dimensiones_conteo_umbral_requerido existe", "ck_dimensiones_conteo_umbral_requerido" in nombres)


def test_schemas_exponen_lo_nuevo():
    print("\nschemas — DimensionBase/Update exponen conteo_umbral_item y validan el requisito cruzado")
    comprobar("DimensionBase trae 'conteo_umbral_item' (opcional, default None)",
              "conteo_umbral_item" in schemas.DimensionBase.model_fields
              and schemas.DimensionBase(nombre="x").conteo_umbral_item is None)
    comprobar("DimensionUpdate permite 'conteo_umbral_item' (opcional)",
              "conteo_umbral_item" in schemas.DimensionUpdate.model_fields)

    from pydantic import ValidationError
    try:
        schemas.DimensionBase(nombre="x", tipo_calculo="conteo_sintomas")
        comprobar("Rechaza 'conteo_sintomas' sin conteo_umbral_item", False)
    except ValidationError:
        comprobar("Rechaza 'conteo_sintomas' sin conteo_umbral_item", True)

    try:
        d = schemas.DimensionBase(nombre="x", tipo_calculo="conteo_sintomas", conteo_umbral_item=2)
        comprobar("Acepta 'conteo_sintomas' CON conteo_umbral_item", d.conteo_umbral_item == 2)
    except ValidationError as e:
        comprobar("Acepta 'conteo_sintomas' CON conteo_umbral_item", False, f"lanzó {e!r}")


def test_algoritmo_cuenta_no_suma():
    print("\ncore.algoritmo.calcular_likert_generico — distingue CONTAR de SUMAR (el motivo real de esta extensión)")

    class _Resp:
        def __init__(self, pregunta_id, dimension, valor_raw):
            self.pregunta_id = pregunta_id
            self.dimension = dimension
            self.valor_raw = valor_raw

    # 9 ítems de una dimensión 'conteo_sintomas' (umbral=2): escenario A tiene
    # 6 ítems en valor 2 (conteo=6, suma=12); escenario B tiene 5 ítems en
    # valor 3 (conteo=5, suma=15 -- MAYOR que A, pero NO debe cumplir "6 de 9").
    respuestas_a = [_Resp(i, 1, 2) for i in range(6)] + [_Resp(i, 1, 0) for i in range(6, 9)]
    respuestas_b = [_Resp(i, 1, 3) for i in range(5)] + [_Resp(i, 1, 0) for i in range(5, 9)]

    resultado_a = algoritmo.calcular_likert_generico(
        respuestas_a, items_db=[], escala_minima=0, escala_maxima=3, dimensiones_conteo={1: 2},
    )
    resultado_b = algoritmo.calcular_likert_generico(
        respuestas_b, items_db=[], escala_minima=0, escala_maxima=3, dimensiones_conteo={1: 2},
    )
    comprobar("Escenario A (6 ítems en 2): puntaje = 6 (conteo), no 12 (suma)",
              resultado_a["puntajes_brutos"][1] == 6)
    comprobar("Escenario B (5 ítems en 3, suma=15 > suma de A): puntaje = 5 (conteo), NO 15",
              resultado_b["puntajes_brutos"][1] == 5)

    # Sin dimensiones_conteo (o dimension ausente del dict): comportamiento
    # de siempre, una suma normal — cero cambio para cualquier test existente.
    resultado_sin_conteo = algoritmo.calcular_likert_generico(
        respuestas_a, items_db=[], escala_minima=0, escala_maxima=3, dimensiones_conteo=None,
    )
    comprobar("Sin dimensiones_conteo, sigue sumando como siempre (12, no 6)",
              resultado_sin_conteo["puntajes_brutos"][1] == 12)

    resultado_dict_vacio = algoritmo.calcular_likert_generico(
        respuestas_a, items_db=[], escala_minima=0, escala_maxima=3, dimensiones_conteo={},
    )
    comprobar("Con dimensiones_conteo={} (dict vacío), también suma como siempre",
              resultado_dict_vacio["puntajes_brutos"][1] == 12)


def test_calcular_resultados_threading():
    print("\ncore.algoritmo.calcular_resultados — EJECUCIÓN real: dimensiones_conteo de verdad llega hasta calcular_likert_generico")
    # Antes esto solo comprobaba que la palabra "dimensiones_conteo" apareciera
    # en el texto fuente de calcular_resultados -- lo que no distingue "la
    # recibe y la reenvía" de "la recibe y la ignora" (un parámetro sin usar
    # también hace que la palabra aparezca). Llamando a la función real con
    # una prueba falsa y respuestas reales se confirma que el conteo de
    # verdad ocurre end-to-end a través de esta capa, no solo en
    # calcular_likert_generico directamente (que ya prueba
    # test_algoritmo_cuenta_no_suma).
    class _Resp:
        def __init__(self, pregunta_id, dimension, valor_raw):
            self.pregunta_id = pregunta_id
            self.dimension = dimension
            self.valor_raw = valor_raw

    respuestas = [_Resp(i, 1, 2) for i in range(6)] + [_Resp(i, 1, 0) for i in range(6, 9)]
    prueba_falsa = SimpleNamespace(modo_calculo="likert_suma", escala_minima=0, escala_maxima=3)

    resultado_con_conteo = algoritmo.calcular_resultados(
        codigo_prueba="PRUEBA_TEST", respuestas=respuestas, items_db=[], prueba=prueba_falsa,
        dimensiones_conteo={1: 2},
    )
    comprobar("Con dimensiones_conteo={1: 2}, el resultado real es 6 (conteo), no 12 (suma)",
              resultado_con_conteo["puntajes_brutos"][1] == 6)

    resultado_sin_conteo = algoritmo.calcular_resultados(
        codigo_prueba="PRUEBA_TEST", respuestas=respuestas, items_db=[], prueba=prueba_falsa,
        dimensiones_conteo=None,
    )
    comprobar("Sin dimensiones_conteo, el mismo camino (calcular_resultados) sigue sumando (12)",
              resultado_sin_conteo["puntajes_brutos"][1] == 12)


def test_correcto_incorrecto_tambien_cuenta():
    print("\ncore.algoritmo.calcular_correcto_incorrecto — FIX: antes ignoraba dimensiones_conteo por completo")
    # Antes de este fix, una Dimension 'conteo_sintomas' dentro de una Prueba
    # modo_calculo='correcto_incorrecto' sumaba en vez de contar — el
    # parámetro ni siquiera existía en la firma de la función. Nada en el
    # CHECK de BD liga conteo_sintomas a un modo_calculo específico, así que
    # la combinación es válida de cargar aunque hoy ningún seed la use.
    class _Resp:
        def __init__(self, pregunta_id, dimension, valor_raw):
            self.pregunta_id = pregunta_id
            self.dimension = dimension
            self.valor_raw = valor_raw

    # 9 ítems de una dimensión 'conteo_sintomas' (umbral=1): 6 en valor 1
    # (conteo=6, suma=6 -- coinciden por umbral=1) vs. escenario con 5 en
    # valor 1 y un umbral=1 (conteo=5). Se usa umbral=2 con valores 0/1 para
    # que suma y conteo DIVERJAN de verdad, igual que test_algoritmo_cuenta_no_suma.
    respuestas = [_Resp(i, 1, 2) for i in range(6)] + [_Resp(i, 1, 0) for i in range(6, 9)]

    resultado_con_conteo = algoritmo.calcular_correcto_incorrecto(
        respuestas, items_db=[], dimensiones_conteo={1: 2},
    )
    comprobar("Con dimensiones_conteo={1: 2}: puntaje = 6 (conteo), no 12 (suma)",
              resultado_con_conteo["puntajes_brutos"][1] == 6)

    resultado_sin_conteo = algoritmo.calcular_correcto_incorrecto(
        respuestas, items_db=[], dimensiones_conteo=None,
    )
    comprobar("Sin dimensiones_conteo, sigue sumando como siempre (12) — cero cambio para todo lo ya cargado",
              resultado_sin_conteo["puntajes_brutos"][1] == 12)

    prueba_falsa = SimpleNamespace(modo_calculo="correcto_incorrecto")
    resultado_end_to_end = algoritmo.calcular_resultados(
        codigo_prueba="PRUEBA_TEST", respuestas=respuestas, items_db=[], prueba=prueba_falsa,
        dimensiones_conteo={1: 2},
    )
    comprobar("End-to-end vía calcular_resultados (modo_calculo='correcto_incorrecto'): también cuenta (6), no suma (12)",
              resultado_end_to_end["puntajes_brutos"][1] == 6)


class _FakeQuerySecuencia:
    """Cada .query(Modelo) de calcular_resultados_dimensiones/
    actualizar_dimension se resuelve en un orden FIJO y conocido (se lee el
    código una vez para confirmarlo) -- a diferencia de un _FakeQuery que
    ignora filter() y siempre devuelve lo mismo, esto permite que el MISMO
    modelo (ej. Dimension, consultado dos veces con intención distinta:
    "todas las de la prueba" y luego "solo las compuestas") devuelva una
    respuesta distinta en cada llamada, en el orden real en que ocurren."""
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


def test_crud_calcular_resultados_dimensiones_cuenta_de_verdad_contra_bd_falsa():
    print("\ncrud.calcular_resultados_dimensiones — EJECUCIÓN real: construye dimensiones_conteo desde Dimension y el resultado guardado es el conteo, no la suma")
    agregados = []

    inscripcion = SimpleNamespace(id=1, evaluacion_id=10)
    evaluacion = SimpleNamespace(id=10, prueba_id=100)
    prueba = SimpleNamespace(id=100, nombre_tecnico="NICHQ_TEST", escala_minima=0, escala_maxima=3, modo_calculo="likert_suma")
    dimension_conteo = SimpleNamespace(
        id=1, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_CONTEO_SINTOMAS, conteo_umbral_item=2,
    )
    preguntas = [SimpleNamespace(id=i, dimension_id=1, prueba_id=100, es_inverso=False) for i in range(9)]
    # 6 respuestas en valor 2 (cumplen el umbral), 3 en valor 0 -- conteo real
    # esperado = 6, suma real = 12; si el wiring estuviera roto (p. ej. el
    # dict de conteo nunca se construye) este test vería 12, no 6.
    respuestas_conjuntas = [
        (SimpleNamespace(puntaje_obtenido=2), preguntas[i]) for i in range(6)
    ] + [
        (SimpleNamespace(puntaje_obtenido=0), preguntas[i]) for i in range(6, 9)
    ]

    class _FakeDB:
        def __init__(self):
            self._tablas = {
                models.Inscripcion: _FakeQuerySecuencia([inscripcion]),
                models.Evaluacion: _FakeQuerySecuencia([evaluacion]),
                models.Prueba: _FakeQuerySecuencia([prueba]),
                models.Pregunta: _FakeQuerySecuencia([preguntas]),
                models.RespuestaAlumno: _FakeQuerySecuencia([respuestas_conjuntas]),
                # 1ª llamada (todas las Dimension de la prueba, para armar el
                # dict de conteo): la única dimensión, de tipo conteo_sintomas.
                # 2ª llamada (solo las 'suma_de_dimensiones', segunda pasada):
                # ninguna -- este escenario no tiene dimensiones compuestas.
                models.Dimension: _FakeQuerySecuencia([[dimension_conteo], []]),
            }

        def query(self, *modelos):
            return self._tablas[modelos[0]]

        def add(self, obj):
            agregados.append(obj)

        def flush(self):
            pass

    resultado = crud.calcular_resultados_dimensiones(_FakeDB(), inscripcion_id=1)

    comprobar("Se creó exactamente un ResultadoDimension (una sola dimensión en la prueba)", len(resultado) == 1)
    if resultado:
        comprobar("El puntaje_directo guardado es 6 (CONTEO real, no 12 de suma) -- el wiring BD -> algoritmo funciona de verdad",
                  float(resultado[0].puntaje_directo) == 6.0, str(resultado[0].puntaje_directo))
        comprobar("El ResultadoDimension apunta a la dimensión correcta", resultado[0].dimension_id == 1)
    comprobar("db.add() se llamó exactamente una vez (mismos objetos devueltos)", len(agregados) == 1)


def test_actualizar_dimension_bloquea_cambios_riesgosos():
    print("\ncrud.actualizar_dimension — EJECUCIÓN real: bloquea tipo_calculo/conteo_umbral_item si ya hay resultados, exige umbral si el tipo final es 'conteo_sintomas'")

    def _fake_db(tiene_resultados=False, tiene_preguntas=False):
        class _FakeDB:
            def __init__(self):
                self.commits = 0

            def query(self, *args):
                objetivo = args[0]
                # db.query(models.Dimension) -- la propia dimensión a editar.
                if objetivo is models.Dimension:
                    return _FakeQuerySecuencia([dimension])
                # db.query(models.ResultadoDimension.id) / db.query(models.Pregunta.id)
                # son columnas, no clases -- InstrumentedAttribute expone
                # .class_ apuntando al modelo dueño.
                propietario = getattr(objetivo, "class_", objetivo)
                if propietario is models.ResultadoDimension:
                    return _FakeQuerySecuencia([SimpleNamespace() if tiene_resultados else None])
                if propietario is models.Pregunta:
                    return _FakeQuerySecuencia([SimpleNamespace() if tiene_preguntas else None])
                raise AssertionError(f"consulta inesperada a {objetivo!r}")

            def commit(self):
                self.commits += 1

            def refresh(self, obj):
                pass

        return _FakeDB()

    dimension = SimpleNamespace(
        id=1, tipo_calculo=models.TIPO_CALCULO_CONTEO_SINTOMAS, conteo_umbral_item=2, nombre="Inatención",
    )

    # 1) Cambiar conteo_umbral_item cuando NO hay resultados -> permitido.
    db1 = _fake_db(tiene_resultados=False)
    resultado1 = crud.actualizar_dimension(db1, dimension_id=1, datos=schemas.DimensionUpdate(conteo_umbral_item=3))
    comprobar("[1] Sin resultados: cambiar conteo_umbral_item SÍ se permite", resultado1.conteo_umbral_item == 3)
    comprobar("[1] Se confirmó con un commit real", db1.commits == 1)

    # 2) Cambiar conteo_umbral_item cuando SÍ hay resultados -> 409 real.
    dimension.conteo_umbral_item = 2  # se había mutado en el caso 1; se restaura
    db2 = _fake_db(tiene_resultados=True)
    try:
        crud.actualizar_dimension(db2, dimension_id=1, datos=schemas.DimensionUpdate(conteo_umbral_item=4))
        comprobar("[2] Con resultados ya calculados: debía rechazar el cambio de umbral", False)
    except HTTPException as exc:
        comprobar("[2] Con resultados ya calculados: SÍ rechaza (409) el cambio de umbral", exc.status_code == 409)
    comprobar("[2] conteo_umbral_item NUNCA se tocó (sigue en 2, el valor original)", dimension.conteo_umbral_item == 2)

    # 3) Convertir a 'suma_de_dimensiones' cuando la dimensión TIENE preguntas
    #    propias -> 400 real (sin resultados todavía, para no chocar con el guard de arriba).
    dimension_items = SimpleNamespace(id=2, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None, nombre="Hiperactividad")

    def _fake_db_conversion(tiene_preguntas):
        class _FakeDB:
            def query(self, *args):
                objetivo = args[0]
                if objetivo is models.Dimension:
                    return _FakeQuerySecuencia([dimension_items])
                propietario = getattr(objetivo, "class_", objetivo)
                if propietario is models.ResultadoDimension:
                    return _FakeQuerySecuencia([None])  # nunca hay resultados en este escenario
                if propietario is models.Pregunta:
                    return _FakeQuerySecuencia([SimpleNamespace() if tiene_preguntas else None])
                raise AssertionError(f"consulta inesperada a {objetivo!r}")

            def commit(self):
                pass

            def refresh(self, obj):
                pass
        return _FakeDB()

    db3 = _fake_db_conversion(tiene_preguntas=True)
    try:
        crud.actualizar_dimension(db3, dimension_id=2, datos=schemas.DimensionUpdate(tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES))
        comprobar("[3] Convertir a 'suma_de_dimensiones' con preguntas propias: debía rechazar", False)
    except HTTPException as exc:
        comprobar("[3] Convertir a 'suma_de_dimensiones' con preguntas propias: SÍ rechaza (400)", exc.status_code == 400)

    # 4) El mismo cambio, pero SIN preguntas propias -> permitido de verdad.
    dimension_items.tipo_calculo = models.TIPO_CALCULO_ITEMS  # se restaura por si el caso 3 lo mutó
    db4 = _fake_db_conversion(tiene_preguntas=False)
    resultado4 = crud.actualizar_dimension(db4, dimension_id=2, datos=schemas.DimensionUpdate(tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES))
    comprobar("[4] Sin preguntas propias: SÍ se permite convertir a 'suma_de_dimensiones'",
              resultado4.tipo_calculo == models.TIPO_CALCULO_SUMA_DE_DIMENSIONES)

    # 5) Pedir tipo_calculo='conteo_sintomas' sin umbral -> 400 real (estado FINAL inválido).
    dimension_sin_umbral = SimpleNamespace(id=3, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None, nombre="Ansiedad")

    def _fake_db_sin_umbral():
        class _FakeDB:
            def query(self, *args):
                objetivo = args[0]
                if objetivo is models.Dimension:
                    return _FakeQuerySecuencia([dimension_sin_umbral])
                propietario = getattr(objetivo, "class_", objetivo)
                if propietario in (models.ResultadoDimension, models.Pregunta):
                    return _FakeQuerySecuencia([None])
                raise AssertionError(f"consulta inesperada a {objetivo!r}")

            def commit(self):
                pass

            def refresh(self, obj):
                pass
        return _FakeDB()

    try:
        crud.actualizar_dimension(_fake_db_sin_umbral(), dimension_id=3,
                                   datos=schemas.DimensionUpdate(tipo_calculo=models.TIPO_CALCULO_CONTEO_SINTOMAS))
        comprobar("[5] tipo_calculo='conteo_sintomas' sin umbral (estado final inválido): debía rechazar", False)
    except HTTPException as exc:
        comprobar("[5] tipo_calculo='conteo_sintomas' sin umbral: SÍ rechaza (400), antes del commit", exc.status_code == 400)


def test_puntaje_total_excluye_conteo_sintomas():
    """Por qué esto SIGUE siendo una verificación por inspección de código, a
    diferencia de los tests de arriba: la exclusión real ocurre dentro de un
    `db.query(func.sum(...)).join(...).filter(...)` -- un agregado SQL cuyo
    resultado depende de que la base de datos real evalúe la condición del
    filtro sobre filas reales. Fakearlo de forma honesta exigiría
    reimplementar un motor de consultas que entienda expresiones de
    SQLAlchemy, no solo encolar valores de retorno como en los tests de
    arriba -- el mismo límite que ya reconoce test_dimension_compuesta_
    unitario.py para su propio equivalente (test_puntaje_total_no_cuenta_doble).
    La cobertura real de esta exclusión ya existe, pero contra una BD de
    verdad: 'un puntaje_total rule confirmed not to double-count' en
    verificar_dimension_compuesta_e2e.py, y la verificación manual
    documentada en CLAUDE.md para conteo_sintomas (sección "Conteo de
    síntomas")."""
    print("\ncrud.evaluar_reglas_interpretacion — 'puntaje_total' excluye también 'conteo_sintomas' (no son puntajes brutos sumables)")
    import inspect
    fuente = inspect.getsource(crud.evaluar_reglas_interpretacion)
    comprobar("El join con Dimension excluye tipo_calculo == 'conteo_sintomas' del sum()",
              "models.Dimension.tipo_calculo != models.TIPO_CALCULO_CONTEO_SINTOMAS" in fuente)
    comprobar("...Y SIGUE excluyendo también 'suma_de_dimensiones' (no reemplazó esa exclusión, la extendió)",
              "models.Dimension.tipo_calculo != models.TIPO_CALCULO_SUMA_DE_DIMENSIONES" in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Conteo de síntomas (tipo_calculo='conteo_sintomas'/conteo_umbral_item)")
    print("=" * 72)
    test_columna_y_constants()
    test_schemas_exponen_lo_nuevo()
    test_algoritmo_cuenta_no_suma()
    test_correcto_incorrecto_tambien_cuenta()
    test_calcular_resultados_threading()
    test_crud_calcular_resultados_dimensiones_cuenta_de_verdad_contra_bd_falsa()
    test_actualizar_dimension_bloquea_cambios_riesgosos()
    test_puntaje_total_excluye_conteo_sintomas()

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
