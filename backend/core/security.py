import os
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
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
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 días

# Motor de encriptación de contraseñas (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Recibe una contraseña plana y devuelve su versión encriptada (hash)"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara si la contraseña escrita coincide con la encriptada en la base de datos"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Genera el token JWT para que el usuario navegue autenticado"""
    to_encode = data.copy()
    # 🆕 Cierre de gap (docs/gaps-pendientes.md) — python-jose calcula el
    # claim "exp" con `.utctimetuple()`, que da el mismo resultado para un
    # datetime naive-UTC o uno aware-UTC (para el naive asume que ya está en
    # UTC, exactamente lo que `datetime.utcnow()` garantizaba; para el aware
    # lo convierte). Cero cambio de comportamiento, solo deja de depender de
    # una API marcada para remoción.
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt