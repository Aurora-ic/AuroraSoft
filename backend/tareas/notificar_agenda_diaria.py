"""
Le manda a cada psicólogo su agenda del día (o le avisa que no tiene nada).
Ejecutar con cron todas las mañanas, ej: 0 7 * * * (7am hora Perú)
    python tareas/notificar_agenda_diaria.py
"""
from datetime import date, datetime, time
from core.database import SessionLocal
from modulos.auth import models as auth_models
from modulos.superadmin import models as superadmin_models
from core.email_service import enviar_correo

db = SessionLocal()
hoy = date.today()
inicio_dia = datetime.combine(hoy, time.min)
fin_dia = datetime.combine(hoy, time.max)

psicologos = db.query(auth_models.Usuario).filter(
    auth_models.Usuario.rol.in_(["psicologo", "admin"]),
    auth_models.Usuario.activo == True,
).all()

for psicologo in psicologos:
    citas = db.query(superadmin_models.CitaProgramada).filter(
        superadmin_models.CitaProgramada.psicologo_id == psicologo.id,
        superadmin_models.CitaProgramada.fecha_hora >= inicio_dia,
        superadmin_models.CitaProgramada.fecha_hora <= fin_dia,
        superadmin_models.CitaProgramada.estado == "Programada",
    ).order_by(superadmin_models.CitaProgramada.fecha_hora).all()

    if citas:
        filas = "".join(f"<li>{c.fecha_hora.strftime('%H:%M')} — {c.motivo}</li>" for c in citas)
        cuerpo = f"<p>Tu agenda de hoy ({hoy.strftime('%d/%m/%Y')}):</p><ul>{filas}</ul>"
    else:
        cuerpo = f"<p>No tienes citas programadas para hoy ({hoy.strftime('%d/%m/%Y')}).</p>"

    enviar_correo(psicologo.email, "Tu agenda de hoy — AuroraSoft", cuerpo)

db.close()