"""`RegistroTareaAsincrona` — bitácora de ejecuciones de tareas en 2º plano.

Ver `PLAN_REMODELACION_ARQUITECTURA.md`, sección 3. Toda generación de PDF
(informe psicométrico, documento institucional, el enganche automático)
corre en segundo plano — el bug de atomicidad del enganche automático (ver
CLAUDE.md, "Auditoría posterior") es exactamente la clase de falla que un
mecanismo sin reintento/recuperación sigue pudiendo producir en cualquier
tarea nueva que se agregue igual.

La Fase 1 (aditiva, sin cambiar el modelo de ejecución) fue solo esta tabla
de registro: `BackgroundTasks` de FastAPI seguía siendo el mecanismo real,
la tabla solo dejaba un rastro de qué corrió, cuándo, y si falló.

**🆕 Fase 2 — completa (sesión 2026-10-17, ver docs/gaps-pendientes.md)**:
`core/cola_tareas.py` reemplaza `BackgroundTasks` por Celery+Redis para los
5 sitios reales que lo usaban (`modulos/educativo/router.py`): reintento
automático (`max_retries`/`default_retry_delay`) y un job de reconciliación
(`tareas/reconciliar_tareas_colgadas.py`) para el caso "el proceso se
reinició a mitad de tarea" que esta tabla ya podía DETECTAR pero antes
nadie resolvía. La tabla se mantiene tal cual (ya existe, ya tiene índices,
el equipo ya sabe consultarla) en vez de migrar a leer el estado directamente
del result backend de Celery — Celery da el reintento/cola, esta tabla
sigue dando la bitácora auditable con SQL directo. `job_id`/`intentos`
(añadidos en esta fase) enlazan cada fila con la tarea Celery real que la
escribió, sin que `ejecutar_tarea_registrada` deje de ser la única forma de
escribir en esta tabla.

Vive en `core/` y no en ningún `modulos/*` porque no es una entidad de
negocio de un módulo concreto (no es del dominio clínico/educativo/
documental) — es infraestructura operativa transversal, igual que
`core/storage/`, `core/limiter.py` o `core/pdf_generator.py`, que tampoco
pertenecen a un módulo. `referencia_id` deliberadamente no es una FK: a qué
tabla apunta depende de `tipo_tarea` (una inscripción, un documento
institucional...), igual que `RegistroCambiosPersona.campo` es texto libre
en vez de una columna por campo — una tabla genérica de bitácora no puede
tener una FK fija sin dejar de ser genérica.
"""

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, Text, func

from core.database import Base

ESTADO_EN_PROGRESO = "en_progreso"
ESTADO_EXITO = "exito"
ESTADO_FALLO = "fallo"
ESTADOS_TAREA_ASINCRONA_VALIDOS = {ESTADO_EN_PROGRESO, ESTADO_EXITO, ESTADO_FALLO}


class RegistroTareaAsincrona(Base):
    """Una fila por cada ejecución de una tarea en segundo plano registrada
    con `core.tareas_async.ejecutar_tarea_registrada`. Se inserta en
    `estado='en_progreso'` ANTES de ejecutar la tarea real (para que una
    tarea que nunca termina — colgada, no solo fallida — también quede
    visible) y se actualiza a 'exito'/'fallo' al terminar."""

    __tablename__ = "registro_tareas_asincronas"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('en_progreso', 'exito', 'fallo')",
            name="ck_registro_tareas_asincronas_estado_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # "generar_informe", "generar_documento_automatico", ... — texto libre a
    # propósito (ver docstring del módulo): catalogar los tipos válidos
    # aquí duplicaría, en una constante que hay que recordar mantener
    # sincronizada, lo que ya está escrito una sola vez en cada wrapper
    # `tarea_*_en_segundo_plano` que llama a `ejecutar_tarea_registrada`.
    tipo_tarea = Column(String, nullable=False, index=True)
    referencia_id = Column(Integer, nullable=False, index=True)

    estado = Column(String, nullable=False, server_default=ESTADO_EN_PROGRESO)
    error_detalle = Column(Text, nullable=True)

    iniciado_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finalizado_en = Column(DateTime(timezone=True), nullable=True)

    # 🆕 Fase 2 (Celery) — job_id es el id que Celery asigna a la tarea real
    # (self.request.id), nullable porque las filas de la Fase 1 nunca lo
    # tuvieron y una fila nueva podría en teoría escribirse antes de que la
    # tarea tenga un id asignado. intentos arranca en 0 y lo incrementa
    # tareas/reconciliar_tareas_colgadas.py cada vez que re-encola una fila
    # colgada — nunca lo toca ejecutar_tarea_registrada en su camino normal,
    # que siempre crea una fila nueva por ejecución.
    job_id = Column(String, nullable=True, index=True)
    intentos = Column(Integer, nullable=False, server_default="0")
