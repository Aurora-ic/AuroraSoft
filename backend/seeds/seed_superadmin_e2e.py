"""
Crea o actualiza la cuenta superadmin DEDICADA a los tests e2e (ver
tests/__init__.py). Solo en desarrollo.

    python -m seeds.seed_superadmin_e2e

Requiere en el .env:
    ENTORNO=development
    E2E_SUPERADMIN_EMAIL=...      (distinto de SUPERADMIN_EMAIL)
    E2E_SUPERADMIN_PASSWORD=...

A diferencia de seeds/seed_superadmin.py, aquí la contraseña del .env SÍ se
reaplica en cada corrida: es una cuenta de pruebas, no la de una persona, y
su contraseña debe coincidir siempre con la que leen los tests. Nunca toca
al superadmin real.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from core.database import SessionLocal  # noqa: E402
import modulos.instituciones.models  # noqa: E402,F401  (registro del modelo Institucion)
from modulos.auth import models  # noqa: E402
from core.security import get_password_hash  # noqa: E402

if os.getenv("ENTORNO") != "development":
    sys.exit("❌ Solo se ejecuta con ENTORNO=development: una cuenta superadmin de pruebas no debe existir en producción.")

email = (os.getenv("E2E_SUPERADMIN_EMAIL") or "").strip().lower()
password = os.getenv("E2E_SUPERADMIN_PASSWORD") or ""
if not email or not password:
    sys.exit("❌ Define E2E_SUPERADMIN_EMAIL y E2E_SUPERADMIN_PASSWORD en el .env.")
if email == (os.getenv("SUPERADMIN_EMAIL") or "").strip().lower():
    sys.exit("❌ E2E_SUPERADMIN_EMAIL debe ser distinto de SUPERADMIN_EMAIL: esta cuenta nunca reemplaza al superadmin real.")
if len(password) < 12:
    sys.exit("❌ E2E_SUPERADMIN_PASSWORD debe tener al menos 12 caracteres.")

db = SessionLocal()
try:
    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if usuario and usuario.rol != "superadmin":
        sys.exit(f"❌ {email} ya existe con rol '{usuario.rol}'; elige otro correo para la cuenta e2e.")
    if usuario:
        usuario.hashed_password = get_password_hash(password)
        usuario.activo = True
        # 🔑 C-4 — cambiar la contraseña invalida los JWT emitidos antes.
        usuario.token_version = (usuario.token_version or 0) + 1
        print(f"🔄 Cuenta e2e {email} actualizada (contraseña del .env reaplicada).")
    else:
        db.add(models.Usuario(
            email=email,
            hashed_password=get_password_hash(password),
            nombre_completo="Superadmin E2E (solo desarrollo)",
            rol="superadmin",
            institucion_id=None,
            activo=True,
        ))
        print(f"✅ Cuenta e2e {email} creada.")
    db.commit()
finally:
    db.close()
