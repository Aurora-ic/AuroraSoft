import os
import sys
from logging.config import fileConfig

# --- LÍNEAS CRÍTICAS DE RUTAS (Garantizan la resolución de módulos) ---
CWD = os.getcwd()
if CWD not in sys.path:
    sys.path.insert(0, CWD)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
# ---------------------------------------------------------

# 🔒 Fase 4 — mismo bug de orden que en main.py: SENTRY_DSN se leía antes de
# que nada cargara el .env (eso solo pasaba después, como efecto colateral de
# `from core.database import engine, Base`), así que Sentry nunca se activaba
# aquí por variable de .env.
from dotenv import load_dotenv
load_dotenv()

# ==========================================
# CONFIGURACIÓN DE SENTRY (MIGRACIONES)
# ==========================================
import sentry_sdk

SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.getenv("ENTORNO", "development"),
    )

from alembic import context

# 🔑 REUTILIZAMOS EL ENGINE Y LA BASE REAL DE TU APLICACIÓN
from core.database import engine, Base

# IMPORTACIÓN DE MODELOS (Para que Alembic detecte los cambios de estructura)
from modulos.superadmin import models as superadmin_models
from modulos.educativo import models as educativo_models
from modulos.auth import models as auth_models
from modulos.instituciones import models as instituciones_models
from modulos.documentos import models as documentos_models
from core import models_tareas as core_models_tareas

# Configuración de logs de Alembic
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Ejecución de migraciones en modo offline."""
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecución de migraciones en modo online."""
    # Usamos el engine probado de core.database para asegurar la misma conexión
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()