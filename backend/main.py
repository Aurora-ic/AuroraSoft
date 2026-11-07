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
from core.entorno import ENTORNO, ES_DESARROLLO  # noqa: E402 — ver core/entorno.py (falta = producción)
from core.monitoreo import iniciar_sentry  # noqa: E402

# 🆕 (sesión 2026-11-07, M4) Sin variables locales, sin cuerpo, sin cookies y
# con los tokens del examen/firma tapados — ver core/monitoreo.py. Solo se
# activa si existe SENTRY_DSN.
iniciar_sentry("api")

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
# ENTORNO / ES_DESARROLLO vienen de core/entorno.py (importado arriba): si la
# variable falta, el backend se comporta como producción, no como desarrollo.

# 🆕 (sesión 2026-11-02) Fuera de desarrollo, los contadores de seguridad
# (rate limit, captchas, captcha adaptativo) deben ir a Redis para que los
# compartan todos los workers — ver core/almacen_seguridad.py.
from core.almacen_seguridad import ALMACEN_SEGURIDAD_URL  # noqa: E402
if not ES_DESARROLLO and not ALMACEN_SEGURIDAD_URL:
    logger.warning(
        "ALMACEN_SEGURIDAD_URL no está definida: rate limit y captchas viven en la "
        "memoria de cada proceso. Con más de un worker de uvicorn NO se comparten."
    )

app = FastAPI(
    title="AuroraSoft API",
    docs_url="/docs" if ES_DESARROLLO else None,
    redoc_url="/redoc" if ES_DESARROLLO else None,
    # 🆕 (sesión 2026-11-07, M3) Antes solo se apagaban /docs y /redoc:
    # /openapi.json seguía publicando el mapa completo de rutas, parámetros
    # y esquemas en producción. `npm run generar-tipos` corre contra el
    # backend local (desarrollo), así que no lo necesita en producción.
    openapi_url="/openapi.json" if ES_DESARROLLO else None,
)

# Configuración del Limiter (Rate Limiting)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 🆕 (sesión 2026-11-07) El 422 ya no devuelve `input` (lo que mandó el
# cliente: contraseñas, datos del alumno) — ver core/errores_validacion.py.
from fastapi.exceptions import RequestValidationError  # noqa: E402
from core.errores_validacion import manejador_validacion  # noqa: E402

app.add_exception_handler(RequestValidationError, manejador_validacion)

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
# 3b. TOPE DE TAMAÑO DEL CUERPO (antes de autenticar)
# ==========================================
# 🆕 (sesión 2026-11-05, A2 de la revisión de seguridad) FastAPI lee el
# multipart completo antes de resolver Depends(...): sin esto, cualquiera sin
# sesión podía mandar varios GB a una ruta de subida y llenar el disco. Ver
# core/limite_cuerpo.py. Cada ruta con UploadFile lleva el tope de su propio
# endpoint + margen del multipart; tests/test_limite_cuerpo_unitario.py falla
# si aparece una ruta de subida nueva sin su fila aquí.
# Se registra ANTES que CORS a propósito: add_middleware apila hacia afuera,
# así CORS queda envolviendo este middleware y el 413 sale con las cabeceras
# CORS (si no, el navegador lo ve como un error de red sin mensaje).
from core.branding import TAMANO_MAXIMO_IMAGEN_BYTES  # noqa: E402
from core.limite_cuerpo import LIMITE_CUERPO_POR_DEFECTO_BYTES, MARGEN_MULTIPART_BYTES, MiddlewareLimiteCuerpo  # noqa: E402
from modulos.documentos.crud import TAMANO_MAXIMO_IMAGEN_SECCION_BYTES  # noqa: E402
from modulos.superadmin.crud import TAMANO_MAXIMO_EVIDENCIA_BYTES  # noqa: E402
from modulos.superadmin.importacion_estudiantes import TAMANO_MAXIMO_BYTES as TAMANO_MAXIMO_EXCEL_BYTES  # noqa: E402

LIMITES_SUBIDA_POR_RUTA = {
    ruta: tope + MARGEN_MULTIPART_BYTES
    for ruta, tope in {
        "/api/admin/personas/consentimiento/{consentimiento_id}/evidencia": TAMANO_MAXIMO_EVIDENCIA_BYTES,
        "/api/admin/personas/{persona_id}/expediente/evidencia": TAMANO_MAXIMO_EVIDENCIA_BYTES,
        "/api/admin/personas/importar/validar": TAMANO_MAXIMO_EXCEL_BYTES,
        "/api/admin/personas/importar/confirmar": TAMANO_MAXIMO_EXCEL_BYTES,
        "/api/auth/usuarios/{usuario_id}/firma": TAMANO_MAXIMO_IMAGEN_BYTES,
        "/api/instituciones/{institucion_id}/branding/{tipo}": TAMANO_MAXIMO_IMAGEN_BYTES,
        "/api/documentos/{documento_id}/secciones/{plantilla_seccion_id}/imagen": TAMANO_MAXIMO_IMAGEN_SECCION_BYTES,
    }.items()
}

app.add_middleware(
    MiddlewareLimiteCuerpo,
    limites_por_ruta=LIMITES_SUBIDA_POR_RUTA,
    limite_por_defecto=LIMITE_CUERPO_POR_DEFECTO_BYTES,
)

# ==========================================
# 4. CONFIGURACIÓN CORS
# ==========================================
# 🆕 (sesión 2026-11-07) Validada al arrancar — ver core/cors.py: un "*",
# "null", una ruta o (fuera de desarrollo) un http:// detienen el arranque.
from core.cors import origenes_cors  # noqa: E402

origenes_permitidos = origenes_cors(os.getenv("CORS_ALLOWED_ORIGINS"), ES_DESARROLLO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origenes_permitidos,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 4b. CABECERAS DE SEGURIDAD (el middleware más externo)
# ==========================================
# 🆕 (sesión 2026-11-07, M2) Se registra DESPUÉS de CORS a propósito:
# add_middleware apila hacia afuera, así también llevan estas cabeceras el
# preflight de CORS, un 413 del tope de cuerpo y un 429. Ver
# core/cabeceras_seguridad.py.
from core.cabeceras_seguridad import MiddlewareCabecerasSeguridad  # noqa: E402

app.add_middleware(MiddlewareCabecerasSeguridad, es_desarrollo=ES_DESARROLLO)

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