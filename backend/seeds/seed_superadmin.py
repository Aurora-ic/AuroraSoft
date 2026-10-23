"""
Crea o actualiza el primer usuario superadmin del sistema (equipo AuroraSoft).
Ejecutar:
    python -m seeds.seed_superadmin
"""
import os
import secrets
from core.database import SessionLocal
import modulos.instituciones.models  # Mantiene el registro del modelo Institucion
from modulos.auth import models
from core.security import get_password_hash

db = SessionLocal()

try:
    # 1. Obtener email del entorno o usar valor predeterminado
    email_superadmin = os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com")

    # 2. Obtener contraseña del .env o generar una segura temporal si no existe
    password_env = os.getenv("SUPERADMIN_PASSWORD")
    if password_env:
        password_final = password_env
        usando_env = True
    else:
        password_final = secrets.token_urlsafe(16)
        usando_env = False

    # 3. Buscar si el superadmin ya existe
    usuario = db.query(models.Usuario).filter(
        models.Usuario.email == email_superadmin
    ).first()

    if usuario:
        usuario.hashed_password = get_password_hash(password_final)
        usuario.activo = True
        # 🔑 C-4 — un reseteo de contraseña invalida los JWT emitidos antes
        usuario.token_version = (usuario.token_version or 0) + 1
        db.commit()
        print("🔄 Contraseña del superadmin actualizada con éxito.")
    else:
        superadmin = models.Usuario(
            email=email_superadmin,
            hashed_password=get_password_hash(password_final),
            nombre_completo="Administrador AuroraSoft",
            rol="superadmin",
            institucion_id=None,  # Permitido solo para superadmin
            activo=True,
        )
        db.add(superadmin)
        db.commit()
        print("✅ Superadmin creado con éxito.")

    # 4. Mensaje seguro según procedencia de la contraseña
    print("\n--------------------------------------------------")
    print("🔑 CREDENCIALES DE ACCESO SUPERADMIN:")
    print(f"   Email: {email_superadmin}")
    
    if usando_env:
        print("   Password: [CONFIGURADA DESDE VARIABLE DE ENTORNO SUPERADMIN_PASSWORD]")
    else:
        print(f"   Password Temporal Generada: {password_final}")
        print("   ⚠️ GUARDA ESTA CONTRASEÑA EN UN LUGAR SEGURO, NO SE VOLVERÁ A MOSTRAR.")
    print("--------------------------------------------------\n")

except Exception as e:
    db.rollback()
    print(f"❌ Error al procesar el superadmin: {e}")
finally:
    db.close()