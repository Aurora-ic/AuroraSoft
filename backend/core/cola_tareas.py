"""Cola de tareas asíncronas real (Celery + Redis) — Fase 2 de
`core/models_tareas.py` (ver su docstring para la Fase 1). Reemplaza
`BackgroundTasks` de FastAPI para los 5 sitios reales que lo usaban
(`modulos/educativo/router.py`: el informe PDF, el enganche automático de
documentos, y las dos alertas por email) con reintento/backoff real — justo
lo que `BackgroundTasks` nunca dio.

Un solo módulo compartido, igual que `core/limiter.py`/`core/database.py`.
`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` por variable de entorno, mismo
criterio que `DATABASE_URL` — con default a un Redis local (`db 0`/`db 1`
separados) para que un `uvicorn --reload` de desarrollo arranque sin tener
que configurar nada si Redis ya está corriendo en localhost.

`include=[...]` en vez de autodiscovery (`app.autodiscover_tasks`, que
asume un `tasks.py` por paquete): los wrappers decorados viven DENTRO de
módulos de dominio ya existentes (`modulos/educativo/crud.py`,
`modulos/documentos/crud.py`, `core/email_service.py`), nunca en un
`tasks.py` nuevo — mismo criterio de "explícito sobre mágico" que ya sigue
este proyecto en todos lados. Celery solo importa esos tres módulos de
forma PEREZOSA (`app.loader.import_default_modules()`, que un worker real
corre al arrancar) — nunca al construir este módulo (`Celery(...)` guarda
los nombres como texto, no los importa), así que el proceso web
(`uvicorn main:app`, que también importa esos mismos módulos para servir
sus propios endpoints) nunca dispara una doble importación ni un ciclo.
"""
import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery(
    "aurorasoft",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "modulos.educativo.crud",
        "modulos.documentos.crud",
        "core.email_service",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # 🆕 Visibilidad operativa mínima: un worker real imprime qué tarea
    # ejecuta y su resultado, sin tener que grepear RegistroTareaAsincrona
    # para un diagnóstico rápido.
    task_track_started=True,
    # 🔒 Sin esto, `.delay()` contra un Redis caído/inalcanzable puede
    # QUEDARSE COLGADO (no solo lanzar un error) — confirmado probando
    # contra un puerto que no escucha: el socket nunca completa el
    # connect y no hay timeout por default. Eso convertiría una caída de
    # Redis en un request de `finalizar_examen_seguro`/`reprocesar` que
    # nunca responde, para un alumno/psicólogo que no tiene nada que ver
    # con la infraestructura de la cola. Con esto, `.delay()` falla rápido
    # (en vez de colgarse) y el call site (ver `_encolar_sin_bloquear` en
    # modulos/educativo/router.py) atrapa esa falla sin romper la
    # respuesta HTTP.
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
    broker_connection_timeout=3,
)
