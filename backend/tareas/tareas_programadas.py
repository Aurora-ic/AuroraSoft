"""🆕 (sesión 2026-11-02) Tareas PERIÓDICAS de Celery (Celery beat).

Antes, `reconciliar_tareas_colgadas` y `notificar_agenda_diaria` eran
scripts que "había que poner en un cron", y en producción nadie lo había
hecho. Ahora el calendario vive en el código (`beat_schedule` en
core/cola_tareas.py) y basta con correr UN proceso beat junto al worker:

    celery -A core.cola_tareas worker --loglevel=info
    celery -A core.cola_tareas beat --loglevel=info

Los dos scripts siguen pudiéndose correr a mano con `python -m tareas.<x>`;
estas tareas solo los envuelven, sin lógica propia.

⚠️ Debe haber UN solo proceso beat. Por si acaso (dos beat por error, o un
reinicio que dispara de nuevo la tarea del día), la agenda diaria toma un
candado por fecha en Redis: el segundo disparo del mismo día no manda nada.
La reconciliación no lo necesita, porque correrla dos veces seguidas no
encuentra nada nuevo la segunda vez.
"""
import logging

from core.cola_tareas import CELERY_BROKER_URL, app as celery_app

logger = logging.getLogger(__name__)

CANDADO_AGENDA_SEGUNDOS = 36 * 3600  # sobra para cubrir el día completo


@celery_app.task(name="tareas.reconciliar_tareas_colgadas")
def tarea_reconciliar_tareas_colgadas() -> int:
    from core.database import SessionLocal
    from tareas.reconciliar_tareas_colgadas import reconciliar_tareas_colgadas

    db = SessionLocal()
    try:
        n = reconciliar_tareas_colgadas(db)
    finally:
        db.close()
    if n:
        logger.warning("Reconciliadas %s tarea(s) colgada(s).", n)
    return n


def _tomar_candado_del_dia(clave: str) -> bool:
    import redis

    r = redis.Redis.from_url(CELERY_BROKER_URL, socket_connect_timeout=3, socket_timeout=3)
    return bool(r.set(clave, "1", nx=True, ex=CANDADO_AGENDA_SEGUNDOS))


@celery_app.task(name="tareas.notificar_agenda_diaria")
def tarea_notificar_agenda_diaria() -> int:
    from datetime import datetime

    from core.database import SessionLocal
    from tareas.notificar_agenda_diaria import ZONA_PERU, notificar_agenda_diaria

    hoy = datetime.now(ZONA_PERU).date()
    if not _tomar_candado_del_dia(f"aurora:agenda-diaria:{hoy.isoformat()}"):
        logger.info("La agenda del %s ya se envió; no se repite.", hoy)
        return 0
    db = SessionLocal()
    try:
        return notificar_agenda_diaria(db, hoy=hoy)
    finally:
        db.close()
