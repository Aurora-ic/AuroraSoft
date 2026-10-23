import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Carga las variables definidas en el archivo .env
load_dotenv()

# Leemos la URL de la base de datos directamente del entorno (.env)
DATABASE_URL = os.getenv("DATABASE_URL")

# Si no está definida en el .env, detenemos la app con un error claro
if not DATABASE_URL:
    raise RuntimeError(
        "❌ [CRÍTICO] La variable de entorno DATABASE_URL no está configurada en el archivo .env"
    )

# 🆕 Hallazgo de auditoría (sesión 2026-10-16): `create_engine(DATABASE_URL)`
# sin argumentos caía en los defaults de SQLAlchemy (`pool_size=5`,
# `max_overflow=10`, sin `pool_pre_ping`) — bajo varios colegios reales con
# varios workers de uvicorn, eso se agota rápido, y sin `pool_pre_ping` un
# corte de conexión de un Postgres gestionado (común tras un idle timeout en
# un proveedor cloud) se ve como un error duro en el siguiente request en
# vez de una reconexión transparente. Configurable por variable de entorno
# (mismo criterio que `EMAIL_PORT` en core/email_service.py) para poder
# ajustarlo por despliegue sin tocar código; los defaults son generosos pero
# no exagerados para un solo proceso con unos pocos workers.
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 10))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", 20))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", 1800))  # segundos; evita conexiones "viejas" que el servidor ya cerró

engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()