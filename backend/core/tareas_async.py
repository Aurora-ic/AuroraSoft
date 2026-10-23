"""Helper genérico para envolver una tarea de segundo plano con registro.

Ver `PLAN_REMODELACION_ARQUITECTURA.md`, sección 3, y el docstring de
`core.models_tareas` para el porqué. `ejecutar_tarea_registrada` se llama
DESDE DENTRO de un wrapper `tarea_*_en_segundo_plano` ya existente — nunca
lo reemplaza, nunca cambia su firma externa (hoy decorada como tarea Celery
real — ver `core/cola_tareas.py` —, antes conocida por `background_tasks.
add_task(...)`), y nunca cambia qué excepción se propaga ni cuándo:
simplemente envuelve la llamada con un registro antes/después.
"""

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from core.models_tareas import ESTADO_EXITO, ESTADO_FALLO, RegistroTareaAsincrona


def ejecutar_tarea_registrada(
    db: Session, tipo_tarea: str, referencia_id: int, fn: Callable[[], None],
    job_id: Optional[str] = None,
) -> None:
    """Ejecuta `fn()` (sin argumentos — ya debe venir cerrada sobre lo que
    necesite, típicamente `lambda: generar_y_almacenar_informe(db, ...)`)
    dejando un `RegistroTareaAsincrona` antes y después, en la MISMA
    sesión `db` que el wrapper que llama ya abrió para la tarea real (el
    wrapper sigue siendo responsable de abrir/cerrar esa sesión — esta
    función nunca crea ni cierra una conexión propia).

    🆕 `job_id` (opcional, Fase 2) — el id que Celery asigna a la tarea real
    (`self.request.id` dentro de un `@app.task(bind=True)`), para poder
    correlacionar esta fila con `celery inspect`/los logs del worker. Las
    tareas que llamaban a este helper antes de la Fase 2 no lo pasaban —
    sigue siendo opcional para no exigirle un argumento nuevo a un caller
    que no tiene un `job_id` real que ofrecer.

    Re-lanza cualquier excepción de `fn()` después de registrar el fallo,
    para que el `try/except/finally` del wrapper que llama (que hace su
    propio `db.rollback()` y logging) siga comportándose exactamente igual
    que antes de que este helper existiera.
    """
    registro = RegistroTareaAsincrona(tipo_tarea=tipo_tarea, referencia_id=referencia_id, job_id=job_id)
    db.add(registro)
    db.commit()
    try:
        fn()
        registro.estado = ESTADO_EXITO
    except Exception as exc:
        registro.estado = ESTADO_FALLO
        registro.error_detalle = str(exc)
        raise
    finally:
        registro.finalizado_en = datetime.now(timezone.utc)
        db.commit()
