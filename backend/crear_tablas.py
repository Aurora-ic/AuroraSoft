import os
from core.database import engine, Base
from sqlalchemy import text

# 1. Importamos los modelos de TODOS los módulos activos
from modulos.superadmin import models as superadmin_models
from modulos.educativo import models as educativo_models
from modulos.auth import models as auth_models
from modulos.instituciones import models as instituciones_models
from modulos.documentos import models as documentos_models
from core import models_tareas as core_models_tareas

# ==========================================
# 🔒 GUARD DE SEGURIDAD — NO QUITAR
# ==========================================
# Se unifica el nombre de la variable a 'ENTORNO'
ENTORNO = os.getenv("ENTORNO", "development")
if ENTORNO != "development":
    raise RuntimeError(
        f"⛔ Este script NO se puede ejecutar con ENTORNO='{ENTORNO}'. "
        "Borraría toda la base de datos. Si de verdad necesitas "
        "reiniciar una base de producción, hazlo manualmente y "
        "con un respaldo confirmado primero, nunca con este script."
    )

confirmacion = input(
    "⚠️  Vas a BORRAR TODAS LAS TABLAS de la base de datos actual.\n"
    "Escribe 'BORRAR' en mayúsculas para confirmar: "
)
if confirmacion != "BORRAR":
    print("Operación cancelada.")
    exit(0)

print("Conectando con PostgreSQL...")

# 2. DEMOLICIÓN: Forzamos la limpieza total desde Python
print("Limpiando la estructura antigua...")
with engine.connect() as conexion:
    conexion.execute(text("DROP SCHEMA public CASCADE;"))
    conexion.execute(text("CREATE SCHEMA public;"))
    try:
        conexion.commit()
    except AttributeError:
        pass

# 3. CONSTRUCCIÓN: Creamos las tablas nuevas
print("Construyendo la nueva arquitectura modular...")
Base.metadata.create_all(bind=engine)
print("¡Éxito! Base de datos reiniciada y tablas creadas.")