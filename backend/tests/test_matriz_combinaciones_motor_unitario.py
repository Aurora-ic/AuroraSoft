"""Pruebas unitarias — Matriz de combinaciones del motor de scoring.

    python -m tests.test_matriz_combinaciones_motor_unitario

Sin BD ni servidor. Ver `PLAN_REMODELACION_ARQUITECTURA.md`, sección 4: cinco
ejes del motor se cruzan entre sí (`modo_calculo`, `Dimension.tipo_calculo`,
`criterio_normativo`, `modo_interpretacion`, `informante_tipo`), se agregaron
reactivamente uno por uno, y ya se encontraron 2 bugs reales exactamente en
cruces que nadie había probado explícitamente:

  1. `conteo_sintomas` dentro de una `Prueba` `modo_calculo='correcto_incorrecto'`
     — `calcular_correcto_incorrecto` ignoraba `dimensiones_conteo` por
     completo (sumaba en vez de contar). Corregido; test real en
     `test_conteo_sintomas_unitario.py::test_correcto_incorrecto_tambien_cuenta`.
  2. Anidar `suma_de_dimensiones` dentro de otra — el guard solo vivía en el
     endpoint de escritura (`reemplazar_componentes_de_dimension`), nunca en
     el cálculo real (`calcular_resultados_dimensiones`). Corregido; test
     real en `test_dimension_compuesta_unitario.py::test_motor_de_calculo_
     excluye_componente_anidado`.

Solo dos de los cinco ejes interactúan de verdad en el código real de
`core/algoritmo.py`/`crud.calcular_resultados_dimensiones`: `modo_calculo`
decide QUÉ función de la "primera pasada" corre (`calcular_likert_generico`
vs. `calcular_correcto_incorrecto`), y `Dimension.tipo_calculo` decide cómo
se agrega cada dimensión dentro de esa pasada (o en una segunda pasada, para
`suma_de_dimensiones`, que ni siquiera vive en algoritmo.py — ver abajo).
`criterio_normativo`/`modo_interpretacion`/`informante_tipo` actúan en capas
completamente separadas (interpretación, no cálculo) y no se cruzan con
estos dos, así que no hace falta una matriz de 5 dimensiones — la real es
esta tabla de 2:

| modo_calculo         | tipo_calculo         | ¿Combinación real probada? |
|-----------------------|----------------------|------------------------------------|
| likert_suma           | items                | Sí — PHQ-9 y casi todo lo cargado  |
| likert_suma           | conteo_sintomas      | Sí — Vanderbilt (seed real)        |
| likert_suma           | suma_de_dimensiones  | Sí — SDQ (seed real)               |
| correcto_incorrecto   | items                | Sí — aptitud técnica (seed real)   |
| correcto_incorrecto   | conteo_sintomas      | Sí — test unitario dedicado (bug encontrado y corregido, ver arriba) |
| correcto_incorrecto   | suma_de_dimensiones  | Antes de este archivo: NO — ningún seed ni test la ejercía. Se agrega abajo. |

La fila que faltaba es la única que este archivo ejecuta de punta a punta
(duck-typed, mismo patrón `_FakeDB`/`_FakeQuerySecuencia` que
`test_dimension_compuesta_unitario.py`/`test_conteo_sintomas_unitario.py`).
El resto de la tabla no se reproduce aquí para no duplicar cobertura que ya
existe en otro archivo — este archivo es el ÍNDICE vivo de la matriz, no una
copia de cada test.

Valor de este archivo a futuro: cuando se agregue un sexto eje (va a pasar
— cada instrumento nuevo cargado hasta ahora agregó uno), esta tabla se
actualiza PRIMERO, con sus nuevas filas marcadas "no probado", y cada una se
convierte en un caso real antes de que un seed real la descubra por
accidente — exactamente como ya pasó con las dos filas de arriba.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, crud  # noqa: E402
from core import algoritmo  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _FakeQuerySecuencia:
    """Mismo helper que ya usan test_dimension_compuesta_unitario.py/
    test_conteo_sintomas_unitario.py — cada .query(Modelo) se resuelve en un
    orden fijo y conocido, así que el MISMO modelo consultado dos veces con
    intención distinta (p. ej. Dimension) puede devolver respuestas
    distintas en el orden real en que el código las pide."""
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


def test_correcto_incorrecto_con_dimension_compuesta():
    print("\ncrud.calcular_resultados_dimensiones — fila NO PROBADA de la matriz: "
          "modo_calculo='correcto_incorrecto' × tipo_calculo='suma_de_dimensiones'")
    # Igual que test_dimension_compuesta_unitario.py::test_motor_de_calculo_
    # segunda_pasada, pero con modo_calculo='correcto_incorrecto' en vez de
    # 'likert_suma': la segunda pasada de calcular_resultados_dimensiones no
    # vive en core/algoritmo.py en absoluto (ver crud.py) — opera siempre
    # sobre el dict puntajes_brutos que la PRIMERA pasada ya produjo, sea
    # cual sea la función que lo generó. Esta prueba confirma que eso es
    # cierto en código real, no solo "debería funcionar por diseño".
    agregados = []

    inscripcion = SimpleNamespace(id=1, evaluacion_id=10)
    evaluacion = SimpleNamespace(id=10, prueba_id=100)
    prueba = SimpleNamespace(
        id=100, nombre_tecnico="APTITUD_TEST", escala_minima=None, escala_maxima=None,
        modo_calculo="correcto_incorrecto",
    )
    sub1 = SimpleNamespace(id=1, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None)
    sub2 = SimpleNamespace(id=2, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_ITEMS, conteo_umbral_item=None)
    compuesta = SimpleNamespace(
        id=3, prueba_id=100, tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES, conteo_umbral_item=None,
    )
    preguntas = [
        SimpleNamespace(id=1, dimension_id=1, prueba_id=100, es_inverso=False),
        SimpleNamespace(id=2, dimension_id=1, prueba_id=100, es_inverso=False),
        SimpleNamespace(id=3, dimension_id=2, prueba_id=100, es_inverso=False),
    ]
    # sub1 (dominio A, correcto/incorrecto): acierta 1 de 2 -> 1. sub2
    # (dominio B): acierta el único ítem -> 1. compuesta esperada = 1+1 = 2
    # (nunca 0, nunca solo uno de los dos).
    respuestas_conjuntas = [
        (SimpleNamespace(puntaje_obtenido=1), preguntas[0]),
        (SimpleNamespace(puntaje_obtenido=0), preguntas[1]),
        (SimpleNamespace(puntaje_obtenido=1), preguntas[2]),
    ]
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

    comprobar("Se crearon 3 ResultadoDimension (sub1, sub2 y la compuesta)", len(resultado) == 3)
    por_dimension = {r.dimension_id: float(r.puntaje_directo) for r in resultado}
    comprobar("sub1 (correcto/incorrecto, ítems propios) sale en 1", por_dimension.get(1) == 1.0, str(por_dimension))
    comprobar("sub2 (correcto/incorrecto, ítems propios) sale en 1", por_dimension.get(2) == 1.0, str(por_dimension))
    comprobar(
        "La compuesta sale en 2 = 1 + 1, aun cuando sus componentes vinieron de "
        "calcular_correcto_incorrecto (no de calcular_likert_generico)",
        por_dimension.get(3) == 2.0, str(por_dimension),
    )
    comprobar(
        "La función no tomó ningún atajo que dependa de modo_calculo=='likert_suma' "
        "(no lanzó excepción, no devolvió la compuesta en 0)",
        any(r.dimension_id == 3 for r in agregados),
    )


def test_fila_conteo_sintomas_ya_cubierta_en_otro_archivo():
    print("\nFila de la matriz correcto_incorrecto × conteo_sintomas — ya probada en test_conteo_sintomas_unitario.py")
    # No se duplica el test aquí (sería la misma aserción con otro nombre de
    # archivo) — solo se confirma que la función real sigue aceptando el
    # parámetro que esa fila necesita, para que un refactor que le quite el
    # parámetro a calcular_correcto_incorrecto falle AQUÍ también, no solo
    # en el archivo original.
    import inspect
    firma = inspect.signature(algoritmo.calcular_correcto_incorrecto)
    comprobar(
        "calcular_correcto_incorrecto todavía acepta dimensiones_conteo "
        "(ver test_conteo_sintomas_unitario.py::test_correcto_incorrecto_tambien_cuenta "
        "para la ejecución real de esta fila)",
        "dimensiones_conteo" in firma.parameters,
    )


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Matriz de combinaciones del motor de scoring")
    print("=" * 72)
    test_correcto_incorrecto_con_dimension_compuesta()
    test_fila_conteo_sintomas_ya_cubierta_en_otro_archivo()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
