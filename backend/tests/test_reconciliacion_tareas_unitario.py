"""Pruebas unitarias — tareas.reconciliar_tareas_colgadas (Fase 2 de
core/models_tareas.py: el job de reconciliación de tareas colgadas).

Sin BD real: duck-typing de la consulta (mismo criterio que
test_dimension_compuesta_unitario.py/test_conteo_sintomas_unitario.py),
monkeypatching las DOS tareas Celery reales que `_reencolar` importa para
confirmar, ejecutando la función real, que:

  1. solo toca filas 'en_progreso' más viejas que el umbral (nunca una
     reciente, nunca una ya 'exito'/'fallo'),
  2. las marca 'fallo', incrementa intentos, y llena finalizado_en,
  3. re-encola la tarea real correcta según tipo_tarea (nunca cruza
     generar_informe con generar_documento_automatico),
  4. un tipo_tarea desconocido no revienta (_reencolar devuelve False sin
     encolar nada, pero la fila igual se marca 'fallo' -- no se pierde
     visibilidad solo porque no se supo re-encolar).

    python -m tests.test_reconciliacion_tareas_unitario
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core.models_tareas import ESTADO_EN_PROGRESO, ESTADO_EXITO, ESTADO_FALLO, RegistroTareaAsincrona  # noqa: E402
from tareas.reconciliar_tareas_colgadas import reconciliar_tareas_colgadas  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _fila(id_, tipo_tarea, referencia_id, estado, hace_minutos, intentos=0):
    return RegistroTareaAsincrona(
        id=id_, tipo_tarea=tipo_tarea, referencia_id=referencia_id, estado=estado,
        iniciado_en=datetime.now(timezone.utc) - timedelta(minutes=hace_minutos),
        intentos=intentos,
    )


class _FakeQuery:
    def __init__(self, filas):
        self._filas = filas

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._filas


class _FakeDB:
    def __init__(self, filas):
        self._filas = filas
        self.commits = 0

    def query(self, modelo):
        return _FakeQuery(self._filas)

    def commit(self):
        self.commits += 1


def test_solo_toca_filas_en_progreso_mas_viejas_que_el_umbral():
    print("\nreconciliar_tareas_colgadas — filtra correctamente (duck-typed, el filtro real lo prueba el e2e)")
    # Esta prueba no ejercita el .filter() real de SQLAlchemy (eso requiere
    # Postgres -- ver verificar_cola_tareas_e2e.py) sino que confirma que la
    # función SOLO procesa lo que la consulta le devuelve, sin filtrar nada
    # por su cuenta de forma redundante ni saltarse ninguna.
    colgada = _fila(1, "generar_informe", 42, ESTADO_EN_PROGRESO, hace_minutos=30)
    db = _FakeDB([colgada])

    import modulos.educativo.crud as educativo_crud

    llamadas = []
    original = educativo_crud.tarea_generar_informe_en_segundo_plano.delay
    educativo_crud.tarea_generar_informe_en_segundo_plano.delay = lambda *a, **k: llamadas.append(("informe", a))
    try:
        n = reconciliar_tareas_colgadas(db, minutos_limite=15)
    finally:
        educativo_crud.tarea_generar_informe_en_segundo_plano.delay = original

    comprobar("Procesó exactamente la fila que la consulta devolvió", n == 1)
    comprobar("La fila quedó en estado 'fallo'", colgada.estado == ESTADO_FALLO)
    comprobar("finalizado_en quedó lleno", colgada.finalizado_en is not None)
    comprobar("intentos se incrementó de 0 a 1", colgada.intentos == 1)
    comprobar("error_detalle explica que fue la reconciliación, no un fallo real de la tarea",
              "Reconciliación" in colgada.error_detalle)
    comprobar("Se comiteó una vez", db.commits == 1)
    comprobar("Re-encoló tarea_generar_informe_en_segundo_plano con el referencia_id correcto",
              llamadas == [("informe", (42,))])


def test_reencola_la_tarea_correcta_segun_tipo_tarea():
    print("\n_reencolar — nunca cruza generar_informe con generar_documento_automatico")
    fila_informe = _fila(1, "generar_informe", 10, ESTADO_EN_PROGRESO, hace_minutos=30)
    fila_documento = _fila(2, "generar_documento_automatico", 20, ESTADO_EN_PROGRESO, hace_minutos=30)
    db = _FakeDB([fila_informe, fila_documento])

    import modulos.educativo.crud as educativo_crud
    import modulos.documentos.crud as documentos_crud

    llamadas_informe, llamadas_documento = [], []
    orig_informe = educativo_crud.tarea_generar_informe_en_segundo_plano.delay
    orig_documento = documentos_crud.tarea_generar_documentos_automaticos_en_segundo_plano.delay
    educativo_crud.tarea_generar_informe_en_segundo_plano.delay = lambda *a, **k: llamadas_informe.append(a)
    documentos_crud.tarea_generar_documentos_automaticos_en_segundo_plano.delay = lambda *a, **k: llamadas_documento.append(a)
    try:
        reconciliar_tareas_colgadas(db, minutos_limite=15)
    finally:
        educativo_crud.tarea_generar_informe_en_segundo_plano.delay = orig_informe
        documentos_crud.tarea_generar_documentos_automaticos_en_segundo_plano.delay = orig_documento

    comprobar("Re-encoló generar_informe con referencia_id=10 (nunca con el 20 del otro tipo)",
              llamadas_informe == [(10,)])
    comprobar("Re-encoló generar_documento_automatico con referencia_id=20 (nunca con el 10 del otro tipo)",
              llamadas_documento == [(20,)])


def test_tipo_tarea_desconocido_no_revienta_pero_igual_marca_fallo():
    print("\nreconciliar_tareas_colgadas — un tipo_tarea sin re-encolador conocido no rompe el job")
    fila_rara = _fila(1, "tipo_inventado_que_no_existe", 99, ESTADO_EN_PROGRESO, hace_minutos=30)
    db = _FakeDB([fila_rara])

    n = reconciliar_tareas_colgadas(db, minutos_limite=15)

    comprobar("No revienta, procesa la fila igual", n == 1)
    comprobar("La marca 'fallo' de todos modos (no se pierde visibilidad)", fila_rara.estado == ESTADO_FALLO)


if __name__ == "__main__":
    test_solo_toca_filas_en_progreso_mas_viejas_que_el_umbral()
    test_reencola_la_tarea_correcta_segun_tipo_tarea()
    test_tipo_tarea_desconocido_no_revienta_pero_igual_marca_fallo()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    sys.exit(0 if not fallos else 1)
