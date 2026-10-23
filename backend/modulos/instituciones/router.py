from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, status
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.deps import obtener_usuario_actual
from core import permisos
from core.url_segura import UrlNoPermitida, validar_url_logo
from core.subida_archivos import leer_archivo_con_limite
from core.branding import TAMANO_MAXIMO_IMAGEN_BYTES
from modulos.auth import models as auth_models
from . import schemas, crud

router = APIRouter(
    prefix="/instituciones",
    tags=["Módulo de Instituciones (Clientes)"]
)


@router.post("/", response_model=schemas.InstitucionResponse, status_code=status.HTTP_201_CREATED)
def crear_nueva_institucion(
    institucion: schemas.InstitucionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN)  # 🔒 Solo AuroraSoft
):
    """Registra un nuevo colegio en el sistema (Solo el equipo de AuroraSoft)."""
    return crud.crear_institucion(db=db, institucion=institucion)


@router.get("/", response_model=List[schemas.InstitucionResponse])
def listar_instituciones(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN)  # 🔒 Solo AuroraSoft
):
    """Obtiene el listado de todos los colegios clientes (Solo el equipo de AuroraSoft)."""
    return crud.obtener_instituciones(db=db)


@router.get("/me", response_model=schemas.InstitucionResponse)
def ver_mi_institucion(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Cualquier usuario logueado ve solo los datos de SU PROPIO colegio."""
    if usuario_actual.institucion_id is None:
        raise HTTPException(status_code=404, detail="Esta cuenta no está asociada a ningún colegio.")
    institucion = crud.obtener_institucion_por_id(db=db, institucion_id=usuario_actual.institucion_id)
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada.")
    return institucion

@router.patch("/{institucion_id}", response_model=schemas.InstitucionResponse)
def actualizar_institucion_endpoint(
    institucion_id: int,
    datos: schemas.InstitucionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN)
):
    """Solo Superadmin puede activar/desactivar planes o renovar licencias."""
    # 🛡️ C-11 — Rechazo temprano de un logo que apunte a la red interna. La
    # descarga vuelve a validar antes de conectar (el DNS puede cambiar), pero
    # así una URL peligrosa ni siquiera llega a guardarse. Cadena vacía = quitar logo.
    if datos.logo_url:
        try:
            validar_url_logo(datos.logo_url)
        except UrlNoPermitida as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"URL de logo no permitida: {exc}",
            )
    elif datos.logo_url == "":
        datos.logo_url = None

    if datos.logo_pie_pagina_url:
        try:
            validar_url_logo(datos.logo_pie_pagina_url)
        except UrlNoPermitida as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"URL de imagen de pie de página no permitida: {exc}",
            )
    elif datos.logo_pie_pagina_url == "":
        datos.logo_pie_pagina_url = None

    institucion = crud.actualizar_institucion(db=db, institucion_id=institucion_id, datos=datos)
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada.")
    return institucion


@router.patch("/{institucion_id}/anio-escolar-activo", response_model=schemas.InstitucionResponse)
def activar_anio_escolar_endpoint(
    institucion_id: int,
    datos: schemas.ActivarAnioEscolarRequest,
    db: Session = Depends(get_db),
    # 🆕 Promoción anual — a diferencia del PATCH de arriba (solo
    # superadmin: licencia/plan son cosas de AuroraSoft), fijar el año
    # escolar activo es una decisión operativa DEL COLEGIO, así que su
    # propio admin puede hacerlo — nunca alguien de otra institución.
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Fija explícitamente el año escolar activo de la institución. Acción
    separada e intencional (nunca se activa solo por confirmar un
    ProcesoPromocion): permite dejar promovidas las secciones con
    anticipación sin que el resto de la app cambie de vista todavía."""
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes activar el año escolar de otro colegio.")
    institucion = crud.activar_anio_escolar(db=db, institucion_id=institucion_id, anio_escolar=datos.anio_escolar)
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada.")
    return institucion


@router.patch("/{institucion_id}/politica-consentimientos", response_model=schemas.InstitucionResponse)
def actualizar_politica_consentimientos_endpoint(
    institucion_id: int,
    datos: schemas.PoliticaConsentimientosRequest,
    db: Session = Depends(get_db),
    # 🆕 Política institucional de consentimientos — mismo criterio que
    # anio-escolar-activo (arriba): es una decisión operativa DEL COLEGIO
    # (a quién le exige consentimiento para evaluar), así que su propio
    # admin puede fijarla — nunca alguien de otra institución.
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Activa/desactiva que, además del consentimiento del apoderado, se
    exija también el asentimiento vigente del propio estudiante para
    matricularlo en una campaña o para que siga rindiendo un examen ya
    empezado. Con el flag apagado (default de toda institución existente)
    el comportamiento es exactamente el de siempre."""
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes cambiar la política de otro colegio.")
    institucion = crud.actualizar_politica_consentimientos(
        db=db, institucion_id=institucion_id,
        exigir_asentimiento_estudiante=datos.exigir_asentimiento_estudiante,
    )
    if not institucion:
        raise HTTPException(status_code=404, detail="Institución no encontrada.")
    return institucion


# ==========================================
# 🆕 Branding autoalojado del motor de documentos institucionales — ver
# crud.subir_imagen_branding(). Alternativa a pegar una URL externa en
# logo_url/logo_pie_pagina_url: la institución sube el archivo y AuroraSoft
# lo sirve desde su propio dominio.
# ==========================================
@router.post("/{institucion_id}/branding/{tipo}", response_model=schemas.InstitucionResponse)
async def subir_branding_institucion(
    institucion_id: int,
    tipo: str,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Sube la imagen de encabezado ('encabezado'), pie de página ('pie') o
    fondo de página completa ('fondo') que `modulos/documentos/
    pdf_generador.py` dibuja. Mismo criterio de tenant que el resto de
    endpoints administrativos del colegio: un admin solo sube la de SU
    institución."""
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes subir branding para otro colegio.")
    contenido = leer_archivo_con_limite(archivo, TAMANO_MAXIMO_IMAGEN_BYTES, "archivo de branding")
    return crud.subir_imagen_branding(
        db, institucion_id, tipo, contenido, archivo.filename or "", archivo.content_type or "",
    )


@router.get("/{institucion_id}/branding/{tipo}")
def servir_branding_institucion(institucion_id: int, tipo: str, db: Session = Depends(get_db)):
    """PÚBLICO a propósito, sin autenticación: es exactamente la URL que
    `core/url_segura.descargar_logo_seguro()` pide sin credenciales al
    generar un PDF — igual que pediría el logo externo de cualquier otro
    colegio que no use este branding autoalojado."""
    contenido, content_type = crud.leer_imagen_branding(db, institucion_id, tipo)
    return Response(content=contenido, media_type=content_type)