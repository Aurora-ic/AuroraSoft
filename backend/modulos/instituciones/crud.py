from fastapi import HTTPException
from sqlalchemy.orm import Session
from . import models, schemas

def crear_institucion(db: Session, institucion: schemas.InstitucionCreate):
    """Guarda un nuevo colegio en la base de datos"""
    db_institucion = models.Institucion(
        nombre=institucion.nombre,
        tipo=institucion.tipo,
        direccion=institucion.direccion,
        telefono=institucion.telefono,
        email_contacto=institucion.email_contacto,
        # 🏷️ C-17 — la licencia se fija al crear, en vez de ignorarse
        plan_activo=institucion.plan_activo,
        fecha_vencimiento_licencia=institucion.fecha_vencimiento_licencia,
        limite_pruebas_mensual_por_alumno=institucion.limite_pruebas_mensual_por_alumno,
    )
    db.add(db_institucion)
    db.commit()
    db.refresh(db_institucion)
    return db_institucion

def obtener_instituciones(db: Session, skip: int = 0, limit: int = 100):
    """Obtiene la lista de colegios registrados"""
    return db.query(models.Institucion).offset(skip).limit(limit).all()

def obtener_institucion_por_id(db: Session, institucion_id: int):
    """Busca un colegio específico por su ID"""
    return db.query(models.Institucion).filter(models.Institucion.id == institucion_id).first()

def actualizar_institucion(db: Session, institucion_id: int, datos: schemas.InstitucionUpdate):
    institucion = obtener_institucion_por_id(db, institucion_id)
    if not institucion:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(institucion, campo, valor)
    db.commit()
    db.refresh(institucion)
    return institucion


def activar_anio_escolar(db: Session, institucion_id: int, anio_escolar: int):
    """🆕 Promoción anual — única fuente de verdad de "en qué año estamos"
    para esta institución. Deliberadamente su propio endpoint/función, no un
    campo más de `actualizar_institucion`: es una acción explícita que el
    cierre de año dispara a propósito, nunca un efecto secundario de
    confirmar un ProcesoPromocion."""
    institucion = obtener_institucion_por_id(db, institucion_id)
    if not institucion:
        return None
    institucion.anio_escolar_activo = anio_escolar
    db.commit()
    db.refresh(institucion)
    return institucion


# ==========================================
# 🆕 Branding autoalojado (encabezado/pie/fondo del motor de documentos
# institucionales) — en vez de exigirle a cada colegio que tenga su propio
# hosting externo para estas imágenes, AuroraSoft las guarda en su
# propio storage (core/storage/, el mismo que ya usan los PDFs de informes)
# y las sirve desde su propio dominio público — `logo_url`/
# `logo_pie_pagina_url`/`fondo_documento_url` terminan apuntando a ESTE
# backend, no a un servidor de terceros. La validación (extensión/tamaño/
# URL pública contra SSRF) es core.branding — compartida con la firma
# personal de usuario (modulos/auth/crud.py), que sigue exactamente el
# mismo patrón. 'fondo' ('fondo_documento_url') es página completa, nunca
# una franja — ver PlantillaDocumento.mostrar_fondo_institucion, el toggle
# que decide si una plantilla en particular la usa.
# ==========================================
TIPOS_BRANDING_VALIDOS = {"encabezado", "pie", "fondo"}


def subir_imagen_branding(
    db: Session, institucion_id: int, tipo: str, contenido: bytes, nombre_archivo: str, content_type: str,
) -> models.Institucion:
    if tipo not in TIPOS_BRANDING_VALIDOS:
        raise HTTPException(status_code=400, detail=f"tipo debe ser uno de {sorted(TIPOS_BRANDING_VALIDOS)}.")

    from core import branding
    branding.validar_imagen_subida(contenido, content_type)
    extension = branding.extension_imagen_segura(nombre_archivo)

    institucion = obtener_institucion_por_id(db, institucion_id)
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada.")

    url_publica = branding.resolver_url_publica(f"/api/instituciones/{institucion_id}/branding/{tipo}")

    from core.storage import obtener_storage_service, construir_storage_key_logo_institucion
    key = construir_storage_key_logo_institucion(institucion_id, tipo, extension)
    obtener_storage_service().guardar(key, contenido, content_type)

    if tipo == "encabezado":
        institucion.logo_url = url_publica
    elif tipo == "pie":
        institucion.logo_pie_pagina_url = url_publica
    else:
        institucion.fondo_documento_url = url_publica
    db.commit()
    db.refresh(institucion)
    return institucion


def leer_imagen_branding(db: Session, institucion_id: int, tipo: str):
    """Sirve la imagen ya subida — endpoint PÚBLICO a propósito (sin
    Depends de auth): `descargar_logo_seguro` la pide sin credenciales,
    exactamente como pediría el logo externo de cualquier otro colegio."""
    if tipo not in TIPOS_BRANDING_VALIDOS:
        raise HTTPException(status_code=404, detail="No encontrado.")
    institucion = obtener_institucion_por_id(db, institucion_id)
    if not institucion:
        raise HTTPException(status_code=404, detail="No encontrado.")

    from core import branding
    from core.storage import obtener_storage_service, construir_storage_key_logo_institucion

    storage = obtener_storage_service()
    for extension in sorted(branding.EXTENSIONES_IMAGEN_PERMITIDAS):
        key = construir_storage_key_logo_institucion(institucion_id, tipo, extension)
        if storage.existe(key):
            return storage.leer(key), branding.content_type_por_extension(extension)
    raise HTTPException(status_code=404, detail="Esta institución no tiene esa imagen configurada.")


def actualizar_politica_consentimientos(db: Session, institucion_id: int, exigir_asentimiento_estudiante: bool):
    """🆕 Política institucional de consentimientos — mismo criterio que
    `activar_anio_escolar`: su propia función/endpoint, no un campo más de
    `actualizar_institucion` (que sigue siendo exclusivo de superadmin para
    licencia/plan), porque esta es una decisión operativa del propio colegio
    sobre a quién le exige consentimiento, no algo que AuroraSoft controle."""
    institucion = obtener_institucion_por_id(db, institucion_id)
    if not institucion:
        return None
    institucion.exigir_asentimiento_estudiante = exigir_asentimiento_estudiante
    db.commit()
    db.refresh(institucion)
    return institucion