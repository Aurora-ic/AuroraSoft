"""Reconciliación de tareas asíncronas colgadas — Fase 2 de
`core/models_tareas.py` (ver su docstring para el porqué de esta tabla y de
Celery como mecanismo real).

Si el proceso worker de Celery se reinicia (o el pod/contenedor se
reemplaza) a mitad de una tarea, la fila `RegistroTareaAsincrona` que
`ejecutar_tarea_registrada` insertó en `'en_progreso'` ANTES de ejecutarla
nunca la actualiza nadie más — queda colgada para siempre, exactamente el
caso que esa tabla fue diseñada para poder DETECTAR (ver su docstring:
"para que una tarea que nunca termina — colgada, no solo fallida — también
quede visible"), pero que hasta ahora nadie resolvía automáticamente. Este
script la encuentra, la marca `'fallo'`, y re-encola la tarea real (vía
`.delay()`, el mismo mecanismo que el call site original en
`modulos/educativo/router.py`).

🔒 Límite conocido, aceptado a propósito: si el worker en realidad sigue
vivo y la tarea sigue corriendo de verdad (solo que tarda más de
`--minutos`), reconciliar la marca como colgada igual y la re-encola —
eso puede producir una ejecución duplicada. Mismo tipo de límite ya
aceptado en otras partes de este proyecto (ver "Riesgo operacional del
reproceso" en docs/gaps-pendientes.md): no hay forma de distinguir "colgada
de verdad" de "lenta mucho tiempo" sin un heartbeat propio, que no existe
hoy. Elegir `--minutos` generosamente (default 15) para el tamaño real de
PDF/documentos que este proyecto genera reduce el riesgo sin eliminarlo.

Solo cubre las DOS tareas que escriben en `RegistroTareaAsincrona`
(`generar_informe`, `generar_documento_automatico`) — las dos alertas por
email (`enviar_alerta_riesgo`/`enviar_alerta_regresion_informe_liberado`)
no tienen fila propia que reconciliar (ver el docstring de esas tareas en
`core/email_service.py`): su propio reintento de Celery ya las cubre.

Ejecutar periódicamente (ej. cada 15 minutos vía cron):
    python -m tareas.reconciliar_tareas_colgadas
    python -m tareas.reconciliar_tareas_colgadas --minutos 30
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal  # noqa: E402
from core.models_tareas import ESTADO_EN_PROGRESO, ESTADO_FALLO, RegistroTareaAsincrona  # noqa: E402

MINUTOS_LIMITE_DEFAULT = 15

# tipo_tarea -> cómo re-encolarla. Import perezoso (adentro de la función,
# no al tope del módulo) para que este script pueda correr aunque algún
# otro módulo de la app no cargue por algún motivo ajeno a esto.
def _reencolar(tipo_tarea: str, referencia_id: int) -> bool:
    if tipo_tarea == "generar_informe":
        from modulos.educativo.crud import tarea_generar_informe_en_segundo_plano
        tarea_generar_informe_en_segundo_plano.delay(referencia_id)
        return True
    if tipo_tarea == "generar_documento_automatico":
        from modulos.documentos.crud import tarea_generar_documentos_automaticos_en_segundo_plano
        tarea_generar_documentos_automaticos_en_segundo_plano.delay(referencia_id)
        return True
    return False


def reconciliar_tareas_colgadas(db, minutos_limite: int = MINUTOS_LIMITE_DEFAULT) -> int:
    """Marca `'fallo'` y re-encola toda fila `RegistroTareaAsincrona` que
    sigue en `'en_progreso'` desde hace más de `minutos_limite` minutos.
    Devuelve cuántas filas tocó."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos_limite)
    colgadas = db.query(RegistroTareaAsincrona).filter(
        RegistroTareaAsincrona.estado == ESTADO_EN_PROGRESO,
        RegistroTareaAsincrona.iniciado_en < limite,
    ).all()
    for fila in colgadas:
        fila.estado = ESTADO_FALLO
        fila.error_detalle = (
            f"Reconciliación: seguía 'en_progreso' después de {minutos_limite} minutos "
            "(probable reinicio del worker a mitad de ejecución) -- marcada como fallo y re-encolada."
        )
        fila.finalizado_en = datetime.now(timezone.utc)
        fila.intentos = (fila.intentos or 0) + 1
        _reencolar(fila.tipo_tarea, fila.referencia_id)
    db.commit()
    return len(colgadas)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutos", type=int, default=MINUTOS_LIMITE_DEFAULT)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        n = reconciliar_tareas_colgadas(db, minutos_limite=args.minutos)
        print(f"Reconciliadas {n} tarea(s) colgada(s) (umbral: {args.minutos} min).")
    finally:
        db.close()
