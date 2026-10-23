"""Pruebas unitarias — Prueba.ordenar_dimensiones_por_puntaje ("Diseño A"
para pruebas de perfil, ver IPIP-RIASEC en CLAUDE.md).

    python -m tests.test_perfil_ordenado_unitario

Sin BD ni servidor. Cubre: la columna existe con default False (cero cambio
de comportamiento para toda prueba existente), los schemas la exponen,
`_calcular_codigo_perfil` produce el código top-3 esperado (incluyendo el
ejemplo exacto de la ficha técnica del IPIP-RIASEC: S=35/A=31/I=29 -> "SAI"),
`_prueba_puede_generar_alerta` distingue baremo vs. regla vs. ninguno, y que
`pdf_generator.py` solo cambia título/redacción de la sección 5.3 cuando
`puede_alertar` es False (nunca para una prueba ya cargada, que no manda esa
clave y cae en el default True).
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


def test_columna_existe_con_default_false():
    print("\nModelo — Prueba.ordenar_dimensiones_por_puntaje existe, NOT NULL, default False")
    columna = models.Prueba.__table__.columns["ordenar_dimensiones_por_puntaje"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es NOT NULL", columna.nullable is False)
    comprobar("Su server_default es 'false'", columna.server_default.arg == "false")


def test_schemas_exponen_lo_nuevo():
    print("\nschemas — PruebaBase/PruebaUpdate exponen lo nuevo")
    comprobar("PruebaBase trae 'ordenar_dimensiones_por_puntaje' con default False",
              "ordenar_dimensiones_por_puntaje" in schemas.PruebaBase.model_fields
              and schemas.PruebaCreate(nombre_tecnico="x", nombre_publico="x").ordenar_dimensiones_por_puntaje is False)
    comprobar("PruebaUpdate permite 'ordenar_dimensiones_por_puntaje' (PATCH normal)",
              "ordenar_dimensiones_por_puntaje" in schemas.PruebaUpdate.model_fields)


def test_calcular_codigo_perfil():
    print("\ncrud._calcular_codigo_perfil — top-3 por puntaje descendente")
    # Ejemplo EXACTO de la ficha técnica del IPIP-RIASEC (sección 8): S=35,
    # A=31, I=29, E=23, C=20, R=17 -> código "SAI".
    dimensiones = [
        {"nombre": "Social", "puntaje": 35},
        {"nombre": "Artístico", "puntaje": 31},
        {"nombre": "Investigativo", "puntaje": 29},
        {"nombre": "Emprendedor", "puntaje": 23},
        {"nombre": "Convencional", "puntaje": 20},
        {"nombre": "Realista", "puntaje": 17},
    ]
    comprobar("Reproduce el ejemplo de la ficha técnica: 'SAI'",
              crud._calcular_codigo_perfil(dimensiones) == "SAI")
    comprobar("No depende del orden de entrada (ya desordenado también da 'SAI')",
              crud._calcular_codigo_perfil(list(reversed(dimensiones))) == "SAI")
    comprobar("top_n es configurable",
              crud._calcular_codigo_perfil(dimensiones, top_n=2) == "SA")
    comprobar("Dimensiones sin puntaje (None) se excluyen, no rompen el cálculo",
              crud._calcular_codigo_perfil([{"nombre": "X", "puntaje": None}]) is None)
    comprobar("Lista vacía -> None", crud._calcular_codigo_perfil([]) is None)


def test_prueba_puede_generar_alerta():
    print("\ncrud._prueba_puede_generar_alerta — baremo activo con es_alerta, o regla activa, o ninguno")

    class _Query:
        def __init__(self, resultado):
            self._resultado = resultado

        def join(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def first(self):
            return self._resultado

    class _DBConBaremoAlerta:
        def query(self, modelo):
            if modelo is models.Baremo.id:
                return _Query(("fila",))
            return _Query(None)

    class _DBConReglaActiva:
        def query(self, modelo):
            if modelo is models.ReglaInterpretacion.id:
                return _Query(("fila",))
            return _Query(None)

    class _DBSinNinguno:
        def query(self, modelo):
            return _Query(None)

    comprobar("True cuando hay un Baremo activo con es_alerta=True",
              crud._prueba_puede_generar_alerta(_DBConBaremoAlerta(), prueba_id=1) is True)
    comprobar("True cuando hay una ReglaInterpretacion activa (aunque ningún baremo alerte)",
              crud._prueba_puede_generar_alerta(_DBConReglaActiva(), prueba_id=1) is True)
    comprobar("False cuando no hay ni baremo-alerta ni regla activa",
              crud._prueba_puede_generar_alerta(_DBSinNinguno(), prueba_id=1) is False)


def test_obtener_datos_para_pdf_usa_los_helpers():
    print("\ncrud.obtener_datos_para_pdf — reordena y calcula codigo_perfil/puede_alertar")
    import inspect
    fuente = inspect.getsource(crud.obtener_datos_para_pdf)
    comprobar("Reordena dimensiones_datos cuando ordenar_dimensiones_por_puntaje es True",
              "ordenar_dimensiones_por_puntaje" in fuente and "sorted(" in fuente)
    comprobar("Llama a _calcular_codigo_perfil", "_calcular_codigo_perfil(" in fuente)
    comprobar("Llama a _prueba_puede_generar_alerta", "_prueba_puede_generar_alerta(" in fuente)
    comprobar("El dict de retorno incluye 'codigo_perfil'", '"codigo_perfil": codigo_perfil' in fuente)
    comprobar("El dict de retorno incluye 'puede_alertar'", '"puede_alertar": puede_alertar' in fuente)


def test_construir_contenido_pdf_propaga_lo_nuevo():
    print("\ncrud.construir_contenido_pdf — propaga codigo_perfil/puede_alertar al dict que lee el PDF")
    import inspect
    fuente = inspect.getsource(crud.construir_contenido_pdf)
    comprobar("Expone 'codigo_perfil' a nivel raíz del contenido", '"codigo_perfil": datos.get("codigo_perfil")' in fuente)
    comprobar("Expone 'puede_alertar' dentro de analisis_riesgo",
              '"puede_alertar": datos.get("puede_alertar", True)' in fuente)


def test_pdf_generator_condiciona_la_seccion_5_3():
    print("\ncore.pdf_generator.generar_pdf — título/redacción de 5.3 solo cambian cuando puede_alertar es False")
    import inspect
    import core.pdf_generator as pdf_generator
    fuente = inspect.getsource(pdf_generator.generar_pdf)
    comprobar("Lee analisis_riesgo.get('puede_alertar', True) — default True preserva el comportamiento de siempre",
              'analisis_riesgo.get("puede_alertar", True)' in fuente)
    comprobar("Tiene una rama de título neutral ('INDICADORES REGISTRADOS') distinta de 'ANÁLISIS DE RIESGO'",
              "INDICADORES REGISTRADOS" in fuente and "ANÁLISIS DE RIESGO" in fuente)
    comprobar("Tiene una redacción neutral para 'sin indicadores' distinta de la clínica",
              "no clasifica resultados como indicadores de alerta clínica" in fuente)
    comprobar("Imprime 'Código de perfil' solo cuando contenido.get('codigo_perfil') existe",
              'contenido.get("codigo_perfil")' in fuente and "Código de perfil" in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Perfil ordenado por puntaje (Prueba.ordenar_dimensiones_por_puntaje)")
    print("=" * 72)
    test_columna_existe_con_default_false()
    test_schemas_exponen_lo_nuevo()
    test_calcular_codigo_perfil()
    test_prueba_puede_generar_alerta()
    test_obtener_datos_para_pdf_usa_los_helpers()
    test_construir_contenido_pdf_propaga_lo_nuevo()
    test_pdf_generator_condiciona_la_seccion_5_3()

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
