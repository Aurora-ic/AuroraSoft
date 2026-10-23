"""Pruebas unitarias — crud.interpretar_perfil_alumno / interpretar_segun_modo
(el algoritmo real de modo_interpretacion='perfil', ver "Interpretación por
perfil" en CLAUDE.md).

    python -m tests.test_interpretacion_perfil_unitario

Sin BD ni servidor — mismo criterio que el resto del repo: objetos
duck-typed en vez de una base de datos real (ver test_fase4_unitario.py
para el mismo patrón sobre _validar_solapamiento_baremo).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _FakeResultado:
    def __init__(self, dimension_id, puntaje_directo):
        self.dimension_id = dimension_id
        self.puntaje_directo = puntaje_directo


class _FakeQuery:
    def __init__(self, filas):
        self._filas = filas

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._filas


class _FakeDBPerfil:
    """Simula lo que interpretar_perfil_alumno necesita de la Session:
    dos formas de query() (ResultadoDimension completo, y las columnas
    Dimension.id/Dimension.nombre) más add()/flush() como no-ops."""

    def __init__(self, resultados, nombres_por_dimension):
        self._resultados = resultados
        self._nombres = nombres_por_dimension
        self.agregados = []

    def query(self, *args):
        if len(args) == 1 and args[0] is models.ResultadoDimension:
            return _FakeQuery(self._resultados)
        return _FakeQuery(list(self._nombres.items()))

    def add(self, obj):
        self.agregados.append(obj)

    def flush(self):
        pass


def test_interpretar_perfil_alumno_asigna_puestos_por_puntaje():
    print("\ninterpretar_perfil_alumno — asigna 1º/2º/3º por puntaje descendente, nunca alerta, nunca cita Baremo")
    nombres = {1: "Dim1", 2: "Dim2", 3: "Dim3"}
    resultados = [
        _FakeResultado(dimension_id=1, puntaje_directo=10),  # debe quedar 3º
        _FakeResultado(dimension_id=2, puntaje_directo=30),  # debe quedar 1º
        _FakeResultado(dimension_id=3, puntaje_directo=20),  # debe quedar 2º
    ]
    db = _FakeDBPerfil(resultados, nombres)

    resultado = crud.interpretar_perfil_alumno(db, inscripcion_id=999)

    comprobar("interpretacion_completa es True (el modo perfil nunca deja 'sin baremo')",
              resultado["interpretacion_completa"] is True)
    comprobar("dimensiones_sin_baremo está vacío", resultado["dimensiones_sin_baremo"] == [])
    comprobar("Se generó un DiagnosticoAlumno por cada dimensión (vía db.add)",
              len(resultado["diagnosticos"]) == 3 and len(db.agregados) == 3)

    por_dimension = {d.dimension_id: d for d in resultado["diagnosticos"]}
    comprobar("La dimensión con mayor puntaje (Dim2=30) queda en el puesto 1º",
              por_dimension[2].nivel == "1º de 3", por_dimension[2].nivel)
    comprobar("La de puntaje medio (Dim3=20) queda en el puesto 2º", por_dimension[3].nivel == "2º de 3")
    comprobar("La de menor puntaje (Dim1=10) queda en el puesto 3º", por_dimension[1].nivel == "3º de 3")
    comprobar("Ningún diagnóstico queda con es_alerta=True",
              all(d.es_alerta is False for d in resultado["diagnosticos"]))
    comprobar("Ningún diagnóstico cita un baremo_id", all(d.baremo_id is None for d in resultado["diagnosticos"]))
    comprobar("Ningún diagnóstico tiene alerta_por (nada que explicar, nunca alertó)",
              all(d.alerta_por is None for d in resultado["diagnosticos"]))
    comprobar("La interpretación automática existe y menciona el puntaje directo",
              all(d.interpretacion and "puntaje directo" in d.interpretacion.lower() for d in resultado["diagnosticos"]))


def test_interpretar_perfil_alumno_sin_resultados_retiene():
    print("\ninterpretar_perfil_alumno — sin ResultadoDimension no rompe, pero retiene (no asume limpio)")
    db = _FakeDBPerfil([], {})
    resultado = crud.interpretar_perfil_alumno(db, inscripcion_id=1)
    comprobar("diagnosticos vacío", resultado["diagnosticos"] == [])
    comprobar("interpretacion_completa es False (sin ResultadoDimension que rankear, "
              "p.ej. examen finalizado sin respuestas — no es 'nada que interpretar', "
              "es un caso a retener para revisión, igual que sin baremo aplicable)",
              resultado["interpretacion_completa"] is False)


class _FakeDBModo:
    """Simula lo único que interpretar_segun_modo necesita antes de
    despachar: db.query(Prueba.modo_interpretacion).filter(...).scalar()."""

    def __init__(self, modo):
        self._modo = modo

    def query(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def scalar(self):
        return self._modo


def test_interpretar_segun_modo_despacha_segun_prueba():
    print("\ninterpretar_segun_modo — despacha a interpretar_perfil_alumno o interpretar_resultados_alumno según Prueba.modo_interpretacion")
    llamadas = []

    def fake_perfil(db, inscripcion_id):
        llamadas.append(("perfil", inscripcion_id))
        return {"diagnosticos": [], "dimensiones_sin_baremo": [], "interpretacion_completa": True}

    def fake_rango(db, inscripcion_id):
        llamadas.append(("rango", inscripcion_id))
        return {"diagnosticos": [], "dimensiones_sin_baremo": [], "interpretacion_completa": True}

    original_perfil = crud.interpretar_perfil_alumno
    original_rango = crud.interpretar_resultados_alumno
    crud.interpretar_perfil_alumno = fake_perfil
    crud.interpretar_resultados_alumno = fake_rango
    try:
        crud.interpretar_segun_modo(_FakeDBModo(models.MODO_INTERPRETACION_PERFIL), inscripcion_id=1, prueba_id=10)
        comprobar("Con modo_interpretacion='perfil' despacha a interpretar_perfil_alumno",
                  llamadas == [("perfil", 1)], str(llamadas))

        llamadas.clear()
        crud.interpretar_segun_modo(_FakeDBModo(models.MODO_INTERPRETACION_RANGO), inscripcion_id=2, prueba_id=20)
        comprobar("Con modo_interpretacion='rango' despacha a interpretar_resultados_alumno",
                  llamadas == [("rango", 2)], str(llamadas))

        llamadas.clear()
        crud.interpretar_segun_modo(_FakeDBModo(None), inscripcion_id=3, prueba_id=30)
        comprobar("Si no hay fila de Prueba (modo None) cae de vuelta a 'rango' por defecto — el mismo "
                  "comportamiento que existía antes de que 'perfil' existiera",
                  llamadas == [("rango", 3)], str(llamadas))
    finally:
        crud.interpretar_perfil_alumno = original_perfil
        crud.interpretar_resultados_alumno = original_rango


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Interpretación por perfil (interpretar_perfil_alumno / interpretar_segun_modo)")
    print("=" * 72)
    test_interpretar_perfil_alumno_asigna_puestos_por_puntaje()
    test_interpretar_perfil_alumno_sin_resultados_retiene()
    test_interpretar_segun_modo_despacha_segun_prueba()

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
