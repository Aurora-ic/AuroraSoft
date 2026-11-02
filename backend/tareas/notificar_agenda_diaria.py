"""
Le manda a cada psicólogo su agenda del día (o le avisa que no tiene nada).

🆕 (sesión 2026-11-02) Lo programa Celery beat todos los días a las 7:00 de
Lima (ver `beat_schedule` en core/cola_tareas.py y la tarea en
tareas/tareas_programadas.py). Sigue pudiéndose correr a mano:
    python -m tareas.notificar_agenda_diaria

Cambios respecto de la versión anterior:
  · Ya no corre al importarse: la lógica vive en `notificar_agenda_diaria()`
    para que Celery pueda llamarla.
  · "Hoy" y las horas del correo se calculan en America/Lima.
    `CitaProgramada.fecha_hora` es DateTime(timezone=True); antes se
    comparaba con un datetime sin zona (que Postgres interpreta en la zona
    de la sesión) y la hora se imprimía tal cual salía de la base, así que
    en un servidor en UTC una cita de las 7:00 salía como 12:00.
"""
import os
import sys
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ZONA_PERU = ZoneInfo("America/Lima")


def notificar_agenda_diaria(db, hoy: Optional[date] = None, enviar=None) -> int:
    """Envía un correo por psicólogo/admin activo. Devuelve cuántos envió.
    `enviar` se inyecta en los tests; por defecto, core.email_service."""
    from modulos.auth import models as auth_models
    from modulos.superadmin import models as superadmin_models

    if enviar is None:
        from core.email_service import enviar_correo as enviar
    if hoy is None:
        hoy = datetime.now(ZONA_PERU).date()
    inicio_dia = datetime.combine(hoy, time.min, tzinfo=ZONA_PERU)
    fin_dia = datetime.combine(hoy, time.max, tzinfo=ZONA_PERU)

    psicologos = db.query(auth_models.Usuario).filter(
        auth_models.Usuario.rol.in_(["psicologo", "admin"]),
        auth_models.Usuario.activo == True,  # noqa: E712
    ).all()

    enviados = 0
    for psicologo in psicologos:
        citas = db.query(superadmin_models.CitaProgramada).filter(
            superadmin_models.CitaProgramada.psicologo_id == psicologo.id,
            superadmin_models.CitaProgramada.fecha_hora >= inicio_dia,
            superadmin_models.CitaProgramada.fecha_hora <= fin_dia,
            superadmin_models.CitaProgramada.estado == "Programada",
        ).order_by(superadmin_models.CitaProgramada.fecha_hora).all()

        if citas:
            filas = "".join(
                f"<li>{c.fecha_hora.astimezone(ZONA_PERU).strftime('%H:%M')} — {c.motivo}</li>" for c in citas
            )
            cuerpo = f"<p>Tu agenda de hoy ({hoy.strftime('%d/%m/%Y')}):</p><ul>{filas}</ul>"
        else:
            cuerpo = f"<p>No tienes citas programadas para hoy ({hoy.strftime('%d/%m/%Y')}).</p>"

        if enviar(psicologo.email, "Tu agenda de hoy — AuroraSoft", cuerpo):
            enviados += 1
    return enviados


if __name__ == "__main__":
    from core.database import SessionLocal

    db = SessionLocal()
    try:
        n = notificar_agenda_diaria(db)
        print(f"Agenda diaria enviada a {n} profesional(es).")
    finally:
        db.close()
