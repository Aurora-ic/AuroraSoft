from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from . import models, schemas
from core.security import get_password_hash
import secrets
from datetime import datetime, timedelta, timezone

# Mensaje único para el correo duplicado: claro para el administrador que da
# de alta la cuenta, sin revelar a qué institución pertenece la existente.
MENSAJE_EMAIL_EN_USO = "No se pudo crear la cuenta: ese correo electrónico ya está en uso."

def obtener_usuario_por_email(db: Session, email: str):
    """Busca en la base de datos si el correo ya existe"""
    return db.query(models.Usuario).filter(models.Usuario.email == email).first()


def crear_usuario(db: Session, usuario: schemas.UsuarioCreate):
    """Encripta la contraseña y guarda al nuevo usuario, ligado a su colegio"""

    # 🔒 Regla de negocio: todo usuario debe pertenecer a un colegio,
    # excepto el rol "superadmin" (equipo de AuroraSoft).
    if usuario.rol != "superadmin" and usuario.institucion_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="institucion_id es obligatorio para este rol."
        )

    # 📧 C-3 — Antes no se comprobaba: `auth_usuarios.email` es UNIQUE, el INSERT
    # lanzaba IntegrityError y el manejador global lo convertía en un 500 genérico.
    # La comparación ignora mayúsculas para que "Ana@x.com" y "ana@x.com" no
    # acaben siendo dos cuentas distintas.
    ya_existe = db.query(models.Usuario.id).filter(
        func.lower(models.Usuario.email) == usuario.email.lower()
    ).first()
    if ya_existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=MENSAJE_EMAIL_EN_USO)

    hashed_password = get_password_hash(usuario.password)

    nuevo_usuario = models.Usuario(
        email=usuario.email,
        hashed_password=hashed_password,
        nombre_completo=usuario.nombre_completo,
        rol=usuario.rol,
        institucion_id=usuario.institucion_id,
    )
    db.add(nuevo_usuario)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos altas simultáneas con el mismo correo: la
        # restricción UNIQUE es la garantía real; aquí solo se traduce.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=MENSAJE_EMAIL_EN_USO)
    db.refresh(nuevo_usuario)
    return nuevo_usuario

def crear_token_recuperacion(db: Session, usuario_id: int):
    token = secrets.token_urlsafe(32)
    nuevo = models.TokenRecuperacion(
        usuario_id=usuario_id,
        token=token,
        # UTC CON zona: la columna es timestamptz. Un utcnow() naive se guardaba
        # como hora local del servidor (Perú, UTC-5) y el enlace de "1 hora"
        # caducaba en realidad a las 6 horas.
        fecha_expiracion=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


def validar_token_recuperacion(db: Session, token: str):
    registro = db.query(models.TokenRecuperacion).filter(
        models.TokenRecuperacion.token == token,
        models.TokenRecuperacion.usado == False,
    ).first()
    # 🔑 Fase 3 — Antes: fecha_expiracion (aware, timestamptz) < utcnow() (naive)
    # lanzaba TypeError, así que TODO reseteo de contraseña acababa en 500:
    # la recuperación de cuenta no había funcionado nunca.
    if not registro:
        return None
    expira = registro.fecha_expiracion
    if expira.tzinfo is None:          # filas antiguas guardadas sin zona
        expira = expira.replace(tzinfo=timezone.utc)
    if expira < datetime.now(timezone.utc):
        return None
    return registro


def resetear_password(db: Session, registro: models.TokenRecuperacion, nueva_password: str):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == registro.usuario_id).first()
    usuario.hashed_password = get_password_hash(nueva_password)

    # 🔑 C-4 — Cambiar la contraseña invalida TODAS las sesiones abiertas.
    # Antes un JWT robado seguía sirviendo hasta 7 días después del cambio,
    # que es justo cuando el titular intenta echar al intruso.
    usuario.token_version = (usuario.token_version or 0) + 1

    # Y los demás enlaces de recuperación pendientes de ese usuario también
    # dejan de valer: si alguien pidió varios, no debe quedar ninguno vivo.
    db.query(models.TokenRecuperacion).filter(
        models.TokenRecuperacion.usuario_id == usuario.id,
        models.TokenRecuperacion.usado == False,  # noqa: E712
    ).update({"usado": True}, synchronize_session=False)
    registro.usado = True
    db.commit()

def listar_usuarios_de_institucion(db: Session, institucion_id: int):
    return db.query(models.Usuario).filter(
        models.Usuario.institucion_id == institucion_id
    ).order_by(models.Usuario.id).all()

def actualizar_usuario(db: Session, usuario_id: int, datos: schemas.UsuarioUpdate):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(usuario, campo, valor)
    db.commit()
    db.refresh(usuario)
    return usuario


# ==========================================
# 🆕 Firma personal autoalojada — ver Usuario.firma_imagen_url en models.py.
# Mismo patrón que el branding institucional (modulos/instituciones/crud.py):
# valida/resuelve vía core.branding, guarda en core.storage, nunca un
# mecanismo propio. Única diferencia real: aquí el "dueño" del recurso es
# el propio usuario, así que el router también deja que alguien suba SU
# PROPIA firma, no solo un admin/superadmin de su institución.
# ==========================================
def subir_firma_usuario(db: Session, usuario_id: int, contenido: bytes, nombre_archivo: str, content_type: str) -> models.Usuario:
    from core import branding
    branding.validar_imagen_subida(contenido, content_type)
    extension = branding.extension_imagen_segura(nombre_archivo)

    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    url_publica = branding.resolver_url_publica(f"/api/auth/usuarios/{usuario_id}/firma")

    from core.storage import obtener_storage_service, construir_storage_key_firma_usuario
    key = construir_storage_key_firma_usuario(usuario_id, extension)
    obtener_storage_service().guardar(key, contenido, content_type)

    usuario.firma_imagen_url = url_publica
    db.commit()
    db.refresh(usuario)
    return usuario


def leer_firma_usuario(db: Session, usuario_id: int):
    """Sirve la firma ya subida — endpoint PÚBLICO a propósito (sin Depends
    de auth): `descargar_logo_seguro` la pide sin credenciales al generar
    un PDF, exactamente como pediría el logo institucional."""
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="No encontrado.")

    from core import branding
    from core.storage import obtener_storage_service, construir_storage_key_firma_usuario

    storage = obtener_storage_service()
    for extension in sorted(branding.EXTENSIONES_IMAGEN_PERMITIDAS):
        key = construir_storage_key_firma_usuario(usuario_id, extension)
        if storage.existe(key):
            return storage.leer(key), branding.content_type_por_extension(extension)
    raise HTTPException(status_code=404, detail="Este usuario no tiene firma configurada.")