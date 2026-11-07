import os
from datetime import datetime, timedelta, timezone
# 🆕 (revisión de seguridad 2026-11-07) PyJWT en vez de python-jose: este
# último dejó de mantenerse y arrastraba ecdsa/rsa/pyasn1 con CVEs abiertos.
import jwt
from passlib.context import CryptContext

# ==========================================
# CONFIGURACIÓN DE SEGURIDAD
# ==========================================
# 🔒 FIX CRÍTICO: la SECRET_KEY ya NO vive hardcodeada en el código.
# Se lee de la variable de entorno SECRET_KEY (definida en tu .env,
# nunca subida al repositorio). Si no existe, el sistema falla al
# arrancar en vez de arrancar con una clave insegura conocida.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "⚠️ Falta la variable de entorno SECRET_KEY. "
        "Defínela en tu archivo .env antes de iniciar el servidor. "
        "Nunca la hardcodees en el código ni la subas a un repositorio."
    )

ALGORITHM = "HS256"
# 🆕 (sesión 2026-11-02) Antes 7 días. Ahora el token de ACCESO es corto y
# se renueva con el de renovación (ver core/sesiones.py). Configurable para
# entornos de prueba con scripts largos que solo inician sesión una vez.
ACCESS_TOKEN_EXPIRE_MINUTES = float(os.getenv("ACCESS_TOKEN_MINUTOS", "15"))

# Motor de encriptación de contraseñas (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Recibe una contraseña plana y devuelve su versión encriptada (hash)"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara si la contraseña escrita coincide con la encriptada en la base de datos"""
    return pwd_context.verify(plain_password, hashed_password)


_HASH_FICTICIO = None


def verificar_password_sin_delatar(plain_password: str, hashed_password: str | None) -> bool:
    """🆕 (revisión de seguridad 2026-11-07) Como verify_password, pero si la
    cuenta no existe (`hashed_password=None`) igual hace el trabajo de bcrypt
    contra un hash ficticio y devuelve False. Antes el login se saltaba
    bcrypt para un correo inexistente y respondía ~700 ms antes: midiendo el
    tiempo se podía averiguar qué correos están registrados."""
    global _HASH_FICTICIO
    if hashed_password is None:
        if _HASH_FICTICIO is None:
            _HASH_FICTICIO = pwd_context.hash("aurorasoft-hash-ficticio")
        pwd_context.verify(plain_password, _HASH_FICTICIO)
        return False
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Genera el token JWT para que el usuario navegue autenticado"""
    to_encode = data.copy()
    # 🆕 Cierre de gap (docs/gaps-pendientes.md) — "exp" como datetime aware
    # en UTC (antes `datetime.utcnow()`, API marcada para remoción). PyJWT lo
    # convierte a timestamp igual que lo hacía python-jose.
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt