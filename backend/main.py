import logging
import os

# 🔒 Fase 4 — `load_dotenv()` tiene que correr ANTES de cualquier os.getenv()
# de este archivo. Antes solo se cargaba como efecto colateral de
# `from core.database import engine, Base` más abajo, así que SENTRY_DSN se
# leía (y perdía) más arriba, antes de que ese import ejecutara. Sentry nunca
# podía activarse por variable de .env, solo si ya estaba en el entorno del
# proceso. python-dotenv es idempotente: llamarlo de nuevo en database.py no
# tiene efecto ni sobreescribe nada.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Imports para Rate Limiting (slowapi)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.limiter import limiter  # 👈 Usamos la instancia única centralizada

# ==========================================
# CONFIGURACIÓN DE SENTRY (MONITOREO DE ERRORES)
# ==========================================
import sentry_sdk

SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,  # Registra el 100% de las trazas para depuración
        environment=os.getenv("ENTORNO", "development"),
    )

# ==========================================
# CONFIGURACIÓN DE LOGGING (REGISTRO DE ERRORES)
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aurorasoft")

# ==========================================
# 1. IMPORTACIONES DE BASE DE DATOS Y MODELOS
# ==========================================
from core.database import engine, Base
from modulos.superadmin import models as superadmin_models
from modulos.educativo import models as educativo_models
from modulos.auth import models as auth_models
from modulos.instituciones import models as instituciones_models
# 🆕 Motor de documentos institucionales — expediente_entradas.
# documento_institucional_id ya referencia documentos_institucionales por
# nombre de tabla: sin este import, SQLAlchemy no puede resolver esa FK al
# construir los mappers y CUALQUIER escritura a EntradaExpediente (no solo
# las de tipo 'documento_institucional') falla con NoReferencedTableError.
from modulos.documentos import models as documentos_models
# 🆕 Fase 3 del plan de remodelación — registro de tareas asíncronas
# (core/models_tareas.py). No es de ningún módulo de negocio, pero necesita
# registrarse igual con Base.metadata antes de que Alembic/create_all la vean.
from core import models_tareas as core_models_tareas

# ==========================================
# 2. IMPORTACIONES DE RUTAS (ROUTERS)
# ==========================================
from modulos.superadmin import router as superadmin_router
from modulos.educativo import router as educativo_router
from modulos.auth import router as auth_router
from modulos.instituciones import router as instituciones_router
from modulos.documentos import router as documentos_router

# ==========================================
# 3. APLICACIÓN Y CONFIGURACIÓN DE ENTORNO
# ==========================================
ENTORNO = os.getenv("ENTORNO", "development")

app = FastAPI(
    title="AuroraSoft API",
    docs_url="/docs" if ENTORNO == "development" else None,
    redoc_url="/redoc" if ENTORNO == "development" else None,
)

# Configuración del Limiter (Rate Limiting)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ==========================================
# MANEJADOR GLOBAL DE ERRORES (SEGURIDAD)
# ==========================================
@app.exception_handler(Exception)
async def manejador_global_de_errores(request: Request, exc: Exception):
    logger.error(f"Error no manejado en {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Ocurrió un error interno. El equipo de AuroraSoft ya fue notificado."}
    )

# ==========================================
# 4. CONFIGURACIÓN CORS
# ==========================================
origenes_permitidos = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 5. CONECTAR LOS ENRUTADORES
# ==========================================
app.include_router(superadmin_router.router, prefix="/api/admin")
app.include_router(educativo_router.router, prefix="/api")
app.include_router(auth_router.router, prefix="/api")
app.include_router(instituciones_router.router, prefix="/api")
app.include_router(documentos_router.router, prefix="/api")


@app.get("/")
def home():
    return {
        "mensaje": "Servidor AuroraSoft funcionando con Arquitectura Modular Limpia y Seguridad Integrada."
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}