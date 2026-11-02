"""Tareas programadas de Celery beat (tareas/tareas_programadas.py, sesión
2026-11-02).

Necesita la BD real y Redis, pero NO el servidor ni un worker: las tareas se
llaman en el mismo proceso. Todo lo que escribe en la BD va dentro de una
transacción que SIEMPRE se revierte, así que no deja datos ni hay que pasar
--limpiar. No manda correos: `enviar` se reemplaza por un espía.

Comprueba:
  · el calendario de beat: reconciliar cada 15 min, agenda a las 12:00 UTC
    (= 7:00 Lima) y ambas tareas registradas en la app de Celery;
  · la agenda cuenta el día en hora de Lima: una cita a las 7:00 y otra a
    las 23:30 de Lima (que en UTC ya es el día siguiente) entran las dos, y
    una del día anterior no; el correo muestra las horas de Lima;
  · las canceladas no salen, y un profesional sin citas recibe el aviso de
    "no tienes citas";
  · el candado por fecha: el segundo disparo del mismo día no manda nada.

    python -m tests.verificar_tareas_programadas
"""
import os
import sys
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core.cola_tareas import app as celery_app  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from modulos.auth import models as auth_models  # noqa: E402
from modulos.instituciones import models as inst_models  # noqa: E402
from modulos.superadmin import models as sa_models  # noqa: E402
from tareas import tareas_programadas  # noqa: E402
from tareas.notificar_agenda_diaria import ZONA_PERU, notificar_agenda_diaria  # noqa: E402

_resultados = []


def comprobar(nombre, condicion):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}")


def main():
    print("\nCalendario de Celery beat")
    celery_app.loader.import_default_modules()
    calendario = celery_app.conf.beat_schedule
    rec = calendario["reconciliar-tareas-colgadas"]["schedule"]
    ag = calendario["notificar-agenda-diaria"]["schedule"]
    comprobar("Reconciliar cada 15 minutos", rec.minute == {0, 15, 30, 45} and len(rec.hour) == 24)
    comprobar("Agenda a las 12:00 UTC (7:00 Lima)", ag.hour == {12} and ag.minute == {0})
    comprobar(
        "Ambas tareas registradas en la app",
        {"tareas.reconciliar_tareas_colgadas", "tareas.notificar_agenda_diaria"} <= set(celery_app.tasks),
    )

    print("\nAgenda diaria en hora de Lima")
    db = SessionLocal()
    try:
        institucion = db.query(inst_models.Institucion).first()
        if institucion is None:
            print("  No hay ninguna institución en la BD para colgar los datos de prueba.")
            sys.exit(1)
        con_citas = auth_models.Usuario(
            email="zztareas.agenda@aurorasoft.test", nombre_completo="ZZTAREAS con citas",
            hashed_password="x", rol="psicologo", institucion_id=institucion.id, activo=True,
        )
        sin_citas = auth_models.Usuario(
            email="zztareas.vacia@aurorasoft.test", nombre_completo="ZZTAREAS sin citas",
            hashed_password="x", rol="psicologo", institucion_id=institucion.id, activo=True,
        )
        db.add_all([con_citas, sin_citas])
        db.flush()

        hoy = date(2031, 5, 14)

        def cita(hora, minuto, motivo, dia=hoy, estado="Programada"):
            return sa_models.CitaProgramada(
                psicologo_id=con_citas.id, institucion_id=institucion.id, titulo=motivo, motivo=motivo,
                fecha_hora=datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=ZONA_PERU), estado=estado,
            )

        db.add_all([
            cita(7, 0, "ZZ temprano"),
            cita(23, 30, "ZZ noche"),  # 04:30 UTC del día siguiente
            cita(10, 0, "ZZ cancelada", estado="Cancelada"),
            cita(23, 0, "ZZ ayer", dia=date(2031, 5, 13)),
        ])
        db.flush()

        enviados = {}

        def espia(destinatario, asunto, cuerpo):
            enviados[destinatario] = cuerpo
            return True

        n = notificar_agenda_diaria(db, hoy=hoy, enviar=espia)
        cuerpo = enviados.get(con_citas.email, "")
        comprobar("Devuelve cuántos correos envió", n == len(enviados) and n >= 2)
        comprobar("La cita de las 7:00 de Lima sale como 07:00", "07:00 — ZZ temprano" in cuerpo)
        comprobar("La de las 23:30 de Lima entra en el día (en UTC ya es mañana)", "23:30 — ZZ noche" in cuerpo)
        comprobar("La cancelada no sale", "ZZ cancelada" not in cuerpo)
        comprobar("La del día anterior no sale", "ZZ ayer" not in cuerpo)
        comprobar("En orden de hora", cuerpo.find("ZZ temprano") < cuerpo.find("ZZ noche"))
        comprobar("El profesional sin citas recibe el aviso", "No tienes citas" in enviados.get(sin_citas.email, ""))
    finally:
        db.rollback()
        db.close()

    print("\nCandado por fecha (un solo envío por día)")
    import redis

    r = redis.Redis.from_url(tareas_programadas.CELERY_BROKER_URL)
    clave = "aurora:agenda-diaria:zztest"
    r.delete(clave)
    primero = tareas_programadas._tomar_candado_del_dia(clave)
    segundo = tareas_programadas._tomar_candado_del_dia(clave)
    comprobar("El primer disparo del día toma el candado; el segundo no", primero and not segundo)
    comprobar("El candado caduca solo (≤ 36 h)", 0 < r.ttl(clave) <= tareas_programadas.CANDADO_AGENDA_SEGUNDOS)
    r.delete(clave)

    with mock.patch.object(tareas_programadas, "_tomar_candado_del_dia", return_value=False), \
         mock.patch("tareas.notificar_agenda_diaria.notificar_agenda_diaria") as real:
        comprobar("Sin candado, la tarea no manda nada", tareas_programadas.tarea_notificar_agenda_diaria() == 0 and not real.called)

    print("\nReconciliación vía la tarea")
    with mock.patch("tareas.reconciliar_tareas_colgadas.reconciliar_tareas_colgadas", return_value=0) as rec_fn:
        comprobar("La tarea llama al script y devuelve su conteo", tareas_programadas.tarea_reconciliar_tareas_colgadas() == 0 and rec_fn.called)

    print(f"\n{sum(_resultados)}/{len(_resultados)} comprobaciones pasaron")
    sys.exit(0 if all(_resultados) else 1)


if __name__ == "__main__":
    main()
