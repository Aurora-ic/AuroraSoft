import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.deps import obtener_usuario_actual, ip_del_cliente
from core import permisos
from core.schemas_comunes import RespuestaPaginada
from core.subida_archivos import leer_archivo_con_limite
from modulos.auth import models as auth_models
from . import models, schemas, crud

# ⚠️ Orden de registro importa: las rutas literales (/tipos, /anios-oficiales,
# /plantillas...) deben quedar declaradas ANTES de cualquier ruta dinámica de
# un solo segmento bajo /documentos (ej. un futuro GET /documentos/{id} del
# Paso 3) — Starlette resuelve por forma de segmento + método, y la primera
# que calce gana. Mismo criterio que ya exige CLAUDE.md para el router
# /personas (ver test_nucleo_estudiante_unitario.py).
router = APIRouter(prefix="/documentos", tags=["Documentos Institucionales"])


# ==========================================
# TipoDocumento — catálogo global. Solo superadmin escribe; lectura abierta
# a cualquier usuario autenticado (la UI de "elegir tipo" la necesita).
# ==========================================
@router.post("/tipos", response_model=schemas.TipoDocumentoResponse)
def crear_tipo_documento(
    datos: schemas.TipoDocumentoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN),
):
    return crud.crear_tipo_documento(db, datos)


@router.get("/tipos", response_model=List[schemas.TipoDocumentoResponse])
def listar_tipos_documento(
    solo_activos: bool = False,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    return crud.listar_tipos_documento(db, solo_activos=solo_activos)


@router.get("/tipos/{tipo_id}", response_model=schemas.TipoDocumentoResponse)
def obtener_tipo_documento(
    tipo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    tipo = crud.obtener_tipo_documento(db, tipo_id)
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de documento no encontrado.")
    return tipo


@router.patch("/tipos/{tipo_id}", response_model=schemas.TipoDocumentoResponse)
def actualizar_tipo_documento(
    tipo_id: int,
    datos: schemas.TipoDocumentoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN),
):
    tipo = crud.obtener_tipo_documento(db, tipo_id)
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de documento no encontrado.")
    return crud.actualizar_tipo_documento(db, tipo, datos)


# ==========================================
# AnioOficial — catálogo global chico. Solo superadmin escribe.
# ==========================================
@router.post("/anios-oficiales", response_model=schemas.AnioOficialResponse)
def crear_anio_oficial(
    datos: schemas.AnioOficialCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_SUPERADMIN),
):
    return crud.crear_o_actualizar_anio_oficial(db, datos)


@router.get("/anios-oficiales", response_model=List[schemas.AnioOficialResponse])
def listar_anios_oficiales(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    return crud.listar_anios_oficiales(db)


# ==========================================
# PlantillaDocumento — por institución. `TipoDocumento` (el catálogo global
# de clases de documento) se queda superadmin-only porque es una decisión
# de plataforma; la PLANTILLA (secciones, orden, tipografía) es del propio
# colegio — admin/psicólogo de STAFF_CLINICO ya pueden armar y editar la
# suya ("constructor de plantillas"), nunca la de otra institución (ver
# el candado de tenant en cada endpoint de abajo, igual que en los GET).
#
# 🆕 `institucion_id IS NULL` es la plantilla PREDETERMINADA global (ver
# docstring de PlantillaDocumento en models.py): solo superadmin la crea o
# edita (_verificar_acceso_plantilla, abajo), pero cualquier STAFF_CLINICO
# puede leerla y clonarla a su propia institución.
# ==========================================
def _verificar_acceso_plantilla(
    usuario: auth_models.Usuario, plantilla: models.PlantillaDocumento, escritura: bool = False,
) -> None:
    """Candado de tenant único, reutilizado por cada endpoint de
    PlantillaDocumento/PlantillaSeccion de abajo (antes repetido inline en
    cada uno). superadmin siempre puede; para la predeterminada global
    (institucion_id None), cualquier autenticado puede LEERLA pero solo
    superadmin puede escribirla; para una plantilla de institución normal,
    solo quien pertenece a esa institución (lectura o escritura)."""
    if usuario.rol == "superadmin":
        return
    if plantilla.institucion_id is None:
        if escritura:
            raise HTTPException(
                status_code=403, detail="Solo superadmin puede editar una plantilla predeterminada global.",
            )
        return
    if plantilla.institucion_id != usuario.institucion_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a la plantilla de otra institución.")


@router.post("/plantillas", response_model=schemas.PlantillaDocumentoResponse)
def crear_plantilla_documento(
    datos: schemas.PlantillaDocumentoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    return crud.crear_plantilla_documento(db, usuario_actual, datos)


# ⚠️ Ruta literal — debe quedar declarada ANTES de GET /plantillas/{plantilla_id}
# (ver nota de orden de registro al inicio del archivo).
@router.get("/plantillas/predeterminadas", response_model=List[schemas.PlantillaDocumentoResponse])
def listar_plantillas_predeterminadas(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Catálogo de plantillas predeterminadas globales (institucion_id IS
    NULL) — el punto de partida que cualquier colegio puede clonar
    (POST /plantillas/{id}/clonar) y editar como propia."""
    return crud.listar_plantillas_predeterminadas(db)


@router.get("/plantillas", response_model=List[schemas.PlantillaDocumentoResponse])
def listar_plantillas(
    institucion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a las plantillas de otra institución.")
    return crud.listar_plantillas_de_institucion(db, institucion_id)


@router.get("/plantillas/{plantilla_id}", response_model=schemas.PlantillaDocumentoResponse)
def obtener_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    plantilla = crud.obtener_plantilla_documento(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    _verificar_acceso_plantilla(usuario_actual, plantilla)
    return plantilla


@router.patch("/plantillas/{plantilla_id}", response_model=schemas.PlantillaDocumentoResponse)
def actualizar_plantilla(
    plantilla_id: int,
    datos: schemas.PlantillaDocumentoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    plantilla = crud.obtener_plantilla_documento(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    _verificar_acceso_plantilla(usuario_actual, plantilla, escritura=True)
    return crud.actualizar_plantilla_documento(db, plantilla, datos)


@router.post("/plantillas/{plantilla_id}/clonar", response_model=schemas.PlantillaDocumentoResponse)
def clonar_plantilla(
    plantilla_id: int,
    datos: schemas.PlantillaDocumentoClonar,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Copia la estructura de esta plantilla (predeterminada global o
    propia de la institución del caller) a una institución destino —
    pensado para no rearmar sección por sección cada colegio nuevo que
    pide, en esencia, el mismo tipo de informe que otro ya tiene. Un
    STAFF_CLINICO que no es superadmin solo puede clonar HACIA su propia
    institución, nunca hacia otra."""
    plantilla = crud.obtener_plantilla_documento(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    _verificar_acceso_plantilla(usuario_actual, plantilla)
    if usuario_actual.rol != "superadmin" and datos.institucion_destino_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes clonar una plantilla hacia otra institución.")
    return crud.clonar_plantilla_documento(
        db, plantilla, datos.institucion_destino_id, usuario_actual.id,
        nombre=datos.nombre, activar=datos.activar,
    )


# ==========================================
# PlantillaSeccion — misma regla de escritura/lectura que su plantilla.
# ==========================================
@router.post("/plantillas/{plantilla_id}/secciones", response_model=schemas.PlantillaSeccionResponse)
def crear_seccion(
    plantilla_id: int,
    datos: schemas.PlantillaSeccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    plantilla = crud.obtener_plantilla_documento(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    _verificar_acceso_plantilla(usuario_actual, plantilla, escritura=True)
    return crud.crear_plantilla_seccion(db, plantilla, datos)


@router.get("/plantillas/{plantilla_id}/secciones", response_model=List[schemas.PlantillaSeccionResponse])
def listar_secciones(
    plantilla_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    plantilla = crud.obtener_plantilla_documento(db, plantilla_id)
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    _verificar_acceso_plantilla(usuario_actual, plantilla)
    return crud.listar_secciones_de_plantilla(db, plantilla_id)


def _seccion_o_404_con_acceso(
    db: Session, seccion_id: int, usuario_actual: auth_models.Usuario,
) -> models.PlantillaSeccion:
    seccion = crud.obtener_plantilla_seccion(db, seccion_id)
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada.")
    plantilla = crud.obtener_plantilla_documento(db, seccion.plantilla_documento_id)
    # Escritura: los dos únicos callers de este helper son PATCH/DELETE.
    _verificar_acceso_plantilla(usuario_actual, plantilla, escritura=True)
    return seccion


@router.patch("/secciones/{seccion_id}", response_model=schemas.PlantillaSeccionResponse)
def actualizar_seccion(
    seccion_id: int,
    datos: schemas.PlantillaSeccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    seccion = _seccion_o_404_con_acceso(db, seccion_id, usuario_actual)
    return crud.actualizar_plantilla_seccion(db, seccion, datos)


@router.delete("/secciones/{seccion_id}", status_code=204)
def eliminar_seccion(
    seccion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Nuevo — antes solo existía crear/editar; el constructor de plantillas
    necesita poder sacar una sección agregada por error mientras el
    documento sigue en borrador (ver eliminar_plantilla_seccion)."""
    seccion = _seccion_o_404_con_acceso(db, seccion_id, usuario_actual)
    crud.eliminar_plantilla_seccion(db, seccion)


# ==========================================
# DocumentoInstitucional — Paso 3. Van AL FINAL del archivo a propósito:
# GET /documentos/{documento_id} es un único segmento dinámico bajo el
# prefijo del router, así que debe quedar registrado DESPUÉS de todas las
# rutas literales (/tipos, /anios-oficiales, /plantillas, /secciones) o
# Starlette lo atraparía a él primero (mismo criterio que ya exige
# CLAUDE.md para el router /personas).
# ==========================================
@router.post("/", response_model=schemas.DocumentoInstitucionalDetalleResponse)
def crear_documento_institucional(
    datos: schemas.DocumentoInstitucionalCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    documento = crud.crear_documento_institucional(db, usuario_actual, datos)
    estudiantes = crud.listar_estudiantes_de_documento(db, documento.id)
    return schemas.DocumentoInstitucionalDetalleResponse(
        **schemas.DocumentoInstitucionalResponse.model_validate(documento).model_dump(),
        estudiantes=estudiantes,
    )


def _obtener_documento_o_404_con_acceso(db: Session, documento_id: int, usuario_actual: auth_models.Usuario) -> models.DocumentoInstitucional:
    """🔒 Usa `crud.usuario_puede_ver_documento` (Paso 6) — no un chequeo de
    tenant a secas: desde este paso, 'colegio' solo pasa si el documento es
    'compartible_colegio', igual que en el listado y en la descarga. Antes
    de este paso, cualquier rol de la institución (incluido 'colegio')
    veía el detalle/contenido de CUALQUIER documento sin importar su
    nivel_visibilidad — se corrige aquí para que la regla sea una sola en
    todo punto de lectura del recurso `DocumentoInstitucional`."""
    documento = crud.obtener_documento_institucional(db, documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    if not crud.usuario_puede_ver_documento(usuario_actual, documento):
        raise HTTPException(status_code=403, detail="No tienes acceso a este documento.")
    return documento


@router.get("/", response_model=RespuestaPaginada[schemas.DocumentoInstitucionalResponse])
def listar_documentos_institucionales(
    institucion_id: int,
    persona_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """🆕 Paginación real (docs/gaps-pendientes.md) — antes devolvía todo
    documento generado, sin tope, para siempre."""
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No tienes acceso a los documentos de otra institución.")
    total, items = crud.listar_documentos_visibles_para_usuario(
        db, institucion_id, usuario_actual, persona_id=persona_id, skip=skip, limit=limit,
    )
    return {"total": total, "items": items}


@router.get("/{documento_id}", response_model=schemas.DocumentoInstitucionalDetalleResponse)
def obtener_documento_institucional(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    estudiantes = crud.listar_estudiantes_de_documento(db, documento.id)
    return schemas.DocumentoInstitucionalDetalleResponse(
        **schemas.DocumentoInstitucionalResponse.model_validate(documento).model_dump(),
        estudiantes=estudiantes,
    )


# ==========================================
# DocumentoInstitucionalSeccionContenido — Paso 4, borrador editable.
# ==========================================
@router.get("/{documento_id}/secciones", response_model=List[schemas.DocumentoInstitucionalSeccionContenidoResponse])
def obtener_contenido_secciones_endpoint(
    documento_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    contenido = crud.obtener_contenido_secciones(db, documento)
    # 🔒 Paso 7 — esto SÍ es contenido completo (el borrador real de cada
    # sección), a diferencia del detalle/listado del documento, que es solo
    # metadata y no se audita.
    crud.registrar_lectura_documento(db, documento, usuario_actual, "contenido", ip_del_cliente(request))
    return contenido


@router.put("/{documento_id}/secciones/{plantilla_seccion_id}", response_model=schemas.DocumentoInstitucionalSeccionContenidoResponse)
def actualizar_contenido_seccion_endpoint(
    documento_id: int,
    plantilla_seccion_id: int,
    datos: schemas.DocumentoInstitucionalSeccionContenidoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.actualizar_contenido_seccion(db, documento, plantilla_seccion_id, usuario_actual.id, datos)


@router.post("/{documento_id}/secciones/{plantilla_seccion_id}/imagen", response_model=schemas.DocumentoInstitucionalSeccionContenidoResponse)
def subir_imagen_seccion_endpoint(
    documento_id: int,
    plantilla_seccion_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Sube directamente la imagen de una sección 'imagen_anexo' (dibujo,
    foto de una prueba gráfica/proyectiva) — nunca una URL externa, a
    diferencia del logo institucional. Una subida nueva no sobrescribe el
    storage de la anterior (ver crud.guardar_imagen_seccion)."""
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    contenido = leer_archivo_con_limite(archivo, crud.TAMANO_MAXIMO_IMAGEN_SECCION_BYTES, "imagen")
    return crud.guardar_imagen_seccion(
        db, documento, plantilla_seccion_id, contenido, archivo.filename or "imagen", usuario_actual.id,
    )


# ==========================================
# DocumentoInstitucionalResultadoPrueba — enlaza una sección
# 'resultados_prueba' o 'grafico_barras' a una Inscripcion real. Antes solo
# se podía escribir por SQL directo (ver CLAUDE.md); estos dos endpoints
# son la forma pública.
# ==========================================
@router.put(
    "/{documento_id}/secciones/{plantilla_seccion_id}/resultados-prueba",
    response_model=schemas.DocumentoInstitucionalResultadoPruebaResponse,
)
def vincular_resultado_prueba_endpoint(
    documento_id: int,
    plantilla_seccion_id: int,
    datos: schemas.DocumentoInstitucionalResultadoPruebaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.vincular_resultado_prueba(
        db, documento, plantilla_seccion_id, datos.persona_id, datos.inscripcion_id,
    )


@router.delete("/{documento_id}/secciones/{plantilla_seccion_id}/resultados-prueba/{persona_id}", status_code=204)
def desvincular_resultado_prueba_endpoint(
    documento_id: int,
    plantilla_seccion_id: int,
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    crud.desvincular_resultado_prueba(db, documento, plantilla_seccion_id, persona_id)


# 🆕 'resultados_prueba_multiple' — consolida una lista VARIABLE de
# aplicaciones reales en una sola sección (a diferencia de
# 'resultados_prueba'/'grafico_barras' arriba, un solo vínculo cada uno).
# Endpoint propio, nunca el PUT genérico de contenido de sección
# (actualizar_contenido_seccion_endpoint): esta sección SÍ referencia filas
# reales de Inscripcion, así que necesita la misma re-validación
# persona+institución que vincular_resultado_prueba ya hace para su propio
# caso — ver crud.vincular_resultados_prueba_multiple.
@router.put(
    "/{documento_id}/secciones/{plantilla_seccion_id}/resultados-prueba-multiple",
    response_model=schemas.DocumentoInstitucionalSeccionContenidoResponse,
)
def vincular_resultados_prueba_multiple_endpoint(
    documento_id: int,
    plantilla_seccion_id: int,
    datos: schemas.ResultadosPruebaMultipleRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.vincular_resultados_prueba_multiple(
        db, documento, plantilla_seccion_id, usuario_actual.id, datos.persona_id, datos.inscripcion_ids,
    )


# ==========================================
# DocumentoInstitucionalVersion — Paso 5, generar/reemitir. Sincrónico (no
# BackgroundTasks): a diferencia del informe psicométrico, que se genera
# automáticamente tras un evento (finalizar examen), aquí es la propia
# acción que el usuario pide — espera el PDF real, no un fire-and-forget.
# ==========================================
@router.post("/{documento_id}/generar-version", response_model=schemas.DocumentoInstitucionalVersionResponse)
def generar_version_endpoint(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.generar_version_documento(db, documento_id, usuario_actual.id, motivo=None)


@router.post("/{documento_id}/reemitir", response_model=schemas.DocumentoInstitucionalVersionResponse)
def reemitir_documento_endpoint(
    documento_id: int,
    datos: schemas.ReemitirDocumentoRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.generar_version_documento(db, documento_id, usuario_actual.id, motivo=datos.motivo)


# ==========================================
# Paso 6 — lectura/descarga gobernada por nivel_visibilidad. Ambos
# endpoints reutilizan _obtener_documento_o_404_con_acceso, así que
# 'colegio' solo pasa si el documento es 'compartible_colegio' — nunca
# tiene efecto alguno sobre la entrada-puente del expediente de los
# estudiantes incluidos, que sigue su propia regla estricta sin excepción.
# ==========================================
@router.get("/{documento_id}/versiones", response_model=List[schemas.DocumentoInstitucionalVersionResponse])
def listar_versiones_endpoint(
    documento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    return crud.listar_versiones_documento(db, documento.id)


@router.get("/{documento_id}/versiones/{numero_version}/descargar")
def descargar_version_endpoint(
    documento_id: int,
    numero_version: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    documento = _obtener_documento_o_404_con_acceso(db, documento_id, usuario_actual)
    version = crud.obtener_version_documento(db, documento.id, numero_version)
    if not version:
        raise HTTPException(status_code=404, detail="Esa versión no existe.")
    # 🔒 El storage_key SIEMPRE se resuelve server-side a partir de la
    # versión ya autorizada — nunca se acepta una key/ruta del cliente.
    try:
        contenido = crud.leer_pdf_de_version_documento(version)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="El archivo de esta versión no está disponible.")
    # 🔒 Paso 7 — toda descarga de PDF queda auditada, después de confirmar
    # que el archivo existe (no se audita un intento fallido de descarga).
    crud.registrar_lectura_documento(
        db, documento, usuario_actual, "descarga_pdf", ip_del_cliente(request),
        numero_version_leida=version.numero_version,
    )
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=version.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{version.nombre_archivo}"'},
    )
