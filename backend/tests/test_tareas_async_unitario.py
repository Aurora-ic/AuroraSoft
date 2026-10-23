"""Pruebas unitarias — RegistroTareaAsincrona y core.tareas_async.ejecutar_tarea_registrada.

    python -m tests.test_tareas_async_unitario

Sin BD real: usa una _DBFalsa duck-typed (mismo criterio que
test_patron_concurrencia_unitario.py/test_dimension_compuesta_unitario.py)
para confirmar, ejecutando la función real, que:

  1. se inserta un registro ANTES de correr la tarea (para que una tarea
     colgada también quede visible, no solo una fallida),
  2. en éxito, queda 'exito' y finalizado_en se llena,
  3. en fallo, queda 'fallo' con error_detalle, la excepción se relanza
     (el try/except/finally del wrapper que llama sigue viendo la misma
     excepción que vería sin este helper), y finalizado_en también se
     llena (no se queda "en_progreso" para siempre solo porque falló),
  4. nunca se abre ni cierra una sesión propia — usa exactamente la que
     recibe, cero cambio en quién administra la conexión.

Ver PLAN_REMODELACION_ARQUITECTURA.md, sección 3.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core import models_tareas  # noqa: E402
from core.tareas_async import ejecutar_tarea_registrada  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _DBFalsa:
    def __init__(self):
        self.agregados = []
        self.commits = 0

    def add(self, obj):
        self.agregados.append(obj)

    def commit(self):
        self.commits += 1


def test_modelo_columnas_y_constraint():
    print("\nModelo — RegistroTareaAsincrona: tabla, columnas, CHECK")
    tabla = models_tareas.RegistroTareaAsincrona.__table__
    comprobar("Tabla registro_tareas_asincronas existe", tabla.name == "registro_tareas_asincronas")
    comprobar(
        "Tiene tipo_tarea, referencia_id, estado, error_detalle, iniciado_en, finalizado_en",
        {"tipo_tarea", "referencia_id", "estado", "error_detalle", "iniciado_en", "finalizado_en"}
        <= set(tabla.columns.keys()),
    )
    comprobar("referencia_id NO es una FK (el tipo de tarea decide a qué tabla apunta)",
              len(tabla.columns["referencia_id"].foreign_keys) == 0)
    nombres_constraints = [c.name for c in tabla.constraints]
    comprobar("CHECK ck_registro_tareas_asincronas_estado_valido existe",
              "ck_registro_tareas_asincronas_estado_valido" in nombres_constraints)
    comprobar("estado NOT NULL con server_default='en_progreso'",
              tabla.columns["estado"].nullable is False
              and tabla.columns["estado"].server_default.arg == models_tareas.ESTADO_EN_PROGRESO)
    comprobar("Fase 2 (Celery) -- tiene job_id (nullable) e intentos (NOT NULL, default 0)",
              tabla.columns["job_id"].nullable is True
              and tabla.columns["intentos"].nullable is False
              and tabla.columns["intentos"].server_default.arg == "0")


def test_ejecutar_tarea_registrada_exito():
    print("\ncore.tareas_async.ejecutar_tarea_registrada — EJECUCIÓN real: camino de éxito")
    db = _DBFalsa()
    llamadas = []

    ejecutar_tarea_registrada(db, tipo_tarea="generar_informe", referencia_id=42, fn=lambda: llamadas.append("corrio"))

    comprobar("fn() sí se ejecutó", llamadas == ["corrio"])
    comprobar("Se agregó exactamente 1 RegistroTareaAsincrona", len(db.agregados) == 1)
    registro = db.agregados[0]
    comprobar("tipo_tarea/referencia_id correctos",
              registro.tipo_tarea == "generar_informe" and registro.referencia_id == 42)
    comprobar("Terminó en estado 'exito'", registro.estado == models_tareas.ESTADO_EXITO)
    comprobar("finalizado_en quedó lleno (no None)", registro.finalizado_en is not None)
    comprobar("error_detalle sigue vacío (nunca se tocó)", registro.error_detalle is None)
    comprobar(
        "Se comiteó DOS veces — una al insertar 'en_progreso' (antes de fn()), otra al cerrar "
        "'exito' (después) — nunca una tarea registrada sin su commit inicial",
        db.commits == 2,
    )


def test_ejecutar_tarea_registrada_fallo_relanza_y_registra():
    print("\ncore.tareas_async.ejecutar_tarea_registrada — EJECUCIÓN real: camino de fallo")
    db = _DBFalsa()

    def fn_que_falla():
        raise ValueError("boom de prueba")

    excepcion_vista = None
    try:
        ejecutar_tarea_registrada(db, tipo_tarea="generar_documento_automatico", referencia_id=7, fn=fn_que_falla)
    except ValueError as exc:
        excepcion_vista = exc

    comprobar("La excepción original se relanza tal cual (el wrapper que llama la sigue viendo)",
              excepcion_vista is not None and str(excepcion_vista) == "boom de prueba")
    registro = db.agregados[0]
    comprobar("Terminó en estado 'fallo'", registro.estado == models_tareas.ESTADO_FALLO)
    comprobar("error_detalle guarda el mensaje de la excepción", registro.error_detalle == "boom de prueba")
    comprobar("finalizado_en igual se llena en el fallo (no se queda 'en_progreso' para siempre)",
              registro.finalizado_en is not None)
    comprobar("Se comiteó igual DOS veces (insertar + cerrar en 'fallo')", db.commits == 2)


def test_ejecutar_tarea_registrada_job_id_opcional():
    print("\ncore.tareas_async.ejecutar_tarea_registrada — job_id (Fase 2, Celery) es opcional y se guarda tal cual")
    db = _DBFalsa()

    ejecutar_tarea_registrada(db, tipo_tarea="generar_informe", referencia_id=42,
                              fn=lambda: None, job_id="celery-task-id-123")
    comprobar("Con job_id explícito, queda guardado en la fila", db.agregados[0].job_id == "celery-task-id-123")

    db2 = _DBFalsa()
    ejecutar_tarea_registrada(db2, tipo_tarea="generar_informe", referencia_id=42, fn=lambda: None)
    comprobar("Sin pasarlo (como antes de la Fase 2), job_id queda None -- nunca exige el argumento nuevo",
              db2.agregados[0].job_id is None)


def test_ejecutar_tarea_registrada_nunca_abre_ni_cierra_sesion_propia():
    print("\ncore.tareas_async.ejecutar_tarea_registrada — nunca administra su propia sesión")
    import inspect
    fuente = inspect.getsource(ejecutar_tarea_registrada)
    comprobar("No llama a SessionLocal() (esa responsabilidad sigue siendo del wrapper que llama)",
              "SessionLocal" not in fuente)
    comprobar("No llama a db.close() (idem — abrir/cerrar la conexión sigue siendo del wrapper)",
              "db.close" not in fuente)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — RegistroTareaAsincrona / ejecutar_tarea_registrada")
    print("=" * 72)
    test_modelo_columnas_y_constraint()
    test_ejecutar_tarea_registrada_exito()
    test_ejecutar_tarea_registrada_fallo_relanza_y_registra()
    test_ejecutar_tarea_registrada_job_id_opcional()
    test_ejecutar_tarea_registrada_nunca_abre_ni_cierra_sesion_propia()

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
