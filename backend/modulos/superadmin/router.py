import io
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from core.database import get_db
from core.deps import (
    ip_del_cliente,
    obtener_usuario_actual,
    requerir_staff_clinico,
    verificar_acceso_institucion,
)
from core import permisos
from core.schemas_comunes import RespuestaPaginada
from core.subida_archivos import leer_archivo_con_limite
from modulos.auth import models as auth_models
from . import schemas, crud, models, importacion_estudiantes as importacion  # 👈 Ojo: asegúrate de incluir 'models' si lo usas aquí
router = APIRouter(
    prefix="/personas",
    tags=["Gestión de Personas (Evaluados)"]
)


@router.post("/", response_model=schemas.PersonaResponse)
def registrar_persona(
    persona: schemas.PersonaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Registra a un estudiante, paciente o candidato para ser evaluado."""
    # 🔒 CANDADO: no puedes registrar personas en un colegio que no es el tuyo
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes registrar personas en un colegio que no es el tuyo."
        )
    return crud.crear_persona(db=db, persona=persona)


@router.get("/{institucion_id}", response_model=RespuestaPaginada[schemas.PersonaResponse])
def listar_personas_de_institucion(
    institucion_id: int,
    busqueda: Optional[str] = None,
    incluir_inactivas: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(verificar_acceso_institucion),
):
    """Lista el padrón activo de un colegio, paginado (`skip`/`limit`,
    default 50, tope 200).

    Pasa ?busqueda=texto para filtrar por nombre, apellido o documento.

    🔒 C-8 — Por defecto NO devuelve personas dadas de baja ni anonimizadas
    por ARCO (ambas quedan con `activo = False`). Con
    ?incluir_inactivas=true se consulta el histórico de forma explícita, que
    es distinto de que reaparezcan sin querer en la lista de trabajo diaria.

    🆕 Cada persona trae `seccion_actual` (nivel/grado/sección/año vigentes,
    resueltos desde MatriculaAcademica en una sola consulta batch — no una
    query por alumno) o `null` si no tiene matrícula activa. NO es
    `grado_seccion`: ese campo sigue viajando tal cual, sin tocar, pero es
    texto libre legado que ningún flujo de matrícula actualiza.

    🆕 Paginación real (docs/gaps-pendientes.md) — antes devolvía el padrón
    completo como lista plana, sin tope, acumulando filas con los años.
    `total` es el total filtrado (post-búsqueda/incluir_inactivas), no el
    tamaño de la página.
    """
    total, items = crud.obtener_personas_por_institucion(
        db=db, institucion_id=institucion_id, busqueda=busqueda,
        incluir_inactivas=incluir_inactivas, skip=skip, limit=limit,
    )
    return {"total": total, "items": items}


# 🟢 CORREGIDO: quitamos '/personas' repetido -> URL final: /api/admin/personas/{persona_id}/consentimiento
@router.post("/{persona_id}/consentimiento", response_model=schemas.ConsentimientoResponse)
def registrar_consentimiento_persona(
    persona_id: int,
    datos: schemas.ConsentimientoCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Registra el consentimiento informado de un alumno.

    🔒 B-8 — La persona y la institución del consentimiento salen de la
    PERSONA DE LA RUTA, ya validada contra la sesión. `datos.persona_id` y
    `datos.institucion_id` se siguen aceptando por compatibilidad con el
    frontend actual, pero se IGNORAN para determinar la propiedad: antes se
    validaba la ruta y se escribía el body, lo que permitía fabricar un
    consentimiento para un alumno de otro colegio.
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes registrar consentimientos de otro colegio.")

    return crud.registrar_consentimiento(
        db=db,
        persona=persona,                                  # 👈 fuente de verdad
        datos=datos,
        registrado_por_usuario_id=usuario_actual.id,
        ip_registro=ip_del_cliente(request),              # 🏛️ B-11
    )


# 🟢 CORREGIDO: quitamos '/personas' repetido -> URL final: /api/admin/personas/{persona_id}/consentimiento
@router.get("/{persona_id}/consentimiento")
def ver_estado_consentimiento(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver esto de otro colegio.")

    # 🔒 B-8: acotado a la institución de la persona
    vigente = crud.tiene_consentimiento_vigente(
        db=db, persona_id=persona_id, institucion_id=persona.institucion_id
    )
    # 🏛️ B-11: el historial completo, incluidos los revocados, como rastro de
    # auditoría. Acotado EXPLÍCITAMENTE a "apoderado": este endpoint es
    # anterior al consentimiento del estudiante y su forma de respuesta no
    # debe empezar a mezclar ambos tipos — para el historial combinado está
    # el endpoint nuevo GET /{persona_id}/consentimientos (plural).
    historial = crud.historial_consentimientos(
        db=db, persona_id=persona_id, institucion_id=persona.institucion_id,
        tipo_consentimiento=models.TIPO_CONSENTIMIENTO_APODERADO,
    )
    return {
        "persona_id": persona_id,
        "tiene_consentimiento_vigente": vigente,
        "historial": [
            {
                "id": c.id,
                "otorgado_por_nombre": c.otorgado_por_nombre,
                "tipo_otorgante": c.tipo_otorgante,
                "referencia_documento": c.referencia_documento,
                "fecha_otorgamiento": c.fecha_otorgamiento,
                "registrado_por_usuario_id": c.registrado_por_usuario_id,
                "ip_registro": c.ip_registro,
                "revocado": c.revocado,
                "fecha_revocacion": c.fecha_revocacion,
                "revocado_por_usuario_id": c.revocado_por_usuario_id,
                "ip_revocacion": c.ip_revocacion,
            }
            for c in historial
        ],
    }

@router.post("/{persona_id}/consentimiento/revocar",
             response_model=schemas.ConsentimientoResponse)
def revocar_consentimiento_endpoint(
    persona_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Revoca el consentimiento vigente de un alumno.

    No borra nada: marca los registros como revocados dejando constancia de
    quién, cuándo y desde dónde. El historial anterior se conserva íntegro.
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes revocar consentimientos de otro colegio.")
    resultado = crud.revocar_consentimiento_de_persona(
        db=db,
        persona_id=persona_id,
        institucion_id=persona.institucion_id,            # 🔒 B-8
        revocado_por_usuario_id=usuario_actual.id,        # 🏛️ B-11
        ip_revocacion=ip_del_cliente(request),            # 🏛️ B-11
    )
    if not resultado:
        raise HTTPException(
            status_code=404,
            detail="Este alumno no tiene un consentimiento vigente para revocar."
        )
    return resultado


# ==========================================
# 🆕 ASENTIMIENTO DEL PROPIO ESTUDIANTE
# ==========================================
# Registro INDEPENDIENTE del consentimiento del apoderado (arriba): crear uno
# de estos NUNCA crea ni modifica el otro (punto 2, IMPORTANTE de esta fase).
# Mismos candados multi-tenant que el bloque de apoderado — no se relajan
# solo porque el otorgante sea el propio alumno.

@router.post("/{persona_id}/consentimiento/asentimiento", response_model=schemas.ConsentimientoAsentimientoResponse)
def registrar_asentimiento_estudiante(
    persona_id: int,
    datos: schemas.ConsentimientoAsentimientoCreate,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Registra el asentimiento del propio estudiante.

    🆕 Ruta renombrada de /consentimiento/estudiante (docs/gaps-pendientes.md)
    — sin alias de compatibilidad: el sistema no tiene todavía institución
    real desplegada ni frontend consumiendo esta ruta, así que no hace falta
    mantener la vieja en paralelo."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes registrar consentimientos de otro colegio.")

    return crud.registrar_consentimiento(
        db=db,
        persona=persona,
        datos=datos,
        registrado_por_usuario_id=usuario_actual.id,
        ip_registro=ip_del_cliente(request),
        tipo_consentimiento=models.TIPO_CONSENTIMIENTO_ASENTIMIENTO,
    )


@router.post("/{persona_id}/consentimiento/asentimiento/revocar", response_model=schemas.ConsentimientoAsentimientoResponse)
def revocar_asentimiento_estudiante_endpoint(
    persona_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Revoca el asentimiento vigente del propio estudiante.

    No toca el consentimiento del apoderado de esta misma persona.
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes revocar consentimientos de otro colegio.")
    resultado = crud.revocar_consentimiento_de_persona(
        db=db,
        persona_id=persona_id,
        institucion_id=persona.institucion_id,
        revocado_por_usuario_id=usuario_actual.id,
        ip_revocacion=ip_del_cliente(request),
        tipo_consentimiento=models.TIPO_CONSENTIMIENTO_ASENTIMIENTO,
    )
    if not resultado:
        raise HTTPException(
            status_code=404,
            detail="Este alumno no tiene un consentimiento (propio) vigente para revocar."
        )
    return resultado


@router.get("/{persona_id}/consentimientos")
def ver_consentimientos_combinados(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """🆕 Historial combinado (punto 12): distingue explícitamente
    apoderado/estudiante, sin ocultar los consentimientos revocados de
    ninguno de los dos. La vigencia de cada uno puede consultarse aparte —
    aquí ya vienen ambas resueltas para no obligar a 2 llamadas."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver esto de otro colegio.")

    return {
        "persona_id": persona_id,
        **crud.obtener_consentimientos_combinados(
            db=db, persona_id=persona_id, institucion_id=persona.institucion_id,
        ),
    }


# ==========================================
# 🆕 EVIDENCIA DEL CONSENTIMIENTO (cierre de gap — docs/gaps-pendientes.md)
# ==========================================
# Por id de CONSENTIMIENTO, no de persona (igual que /expediente/{entrada_id}
# más abajo): el consentimiento ya identifica sin ambigüedad a su persona e
# institución, así que no hace falta un segundo parámetro en la ruta que
# tendría que validarse contra el primero.
def _obtener_consentimiento_o_404(db: Session, consentimiento_id: int) -> models.ConsentimientoInformado:
    consentimiento = db.query(models.ConsentimientoInformado).filter(
        models.ConsentimientoInformado.id == consentimiento_id
    ).first()
    if not consentimiento:
        raise HTTPException(status_code=404, detail="Consentimiento no encontrado.")
    return consentimiento


@router.post("/consentimiento/{consentimiento_id}/evidencia", response_model=schemas.ConsentimientoResponse)
def subir_evidencia_consentimiento_endpoint(
    consentimiento_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    # 🔒 Mismo candado que registrar/ver/revocar consentimiento: cualquier
    # rol autenticado DE LA MISMA institución (ni GESTION_EXPEDIENTE ni
    # STAFF_CLINICO aquí — esto es administrativo, no clínico, y "colegio"
    # ya puede registrar y ver consentimientos hoy).
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Sube el documento firmado/escaneado real de un consentimiento ya
    registrado (PDF/JPG/PNG, máx. 10 MB) y lo guarda vía el storage ya
    existente del motor de informes — cierra el gap "evidencia_ruta sin
    usar" (docs/gaps-pendientes.md). Una subida nueva reemplaza a la
    anterior; no hay versionado como en los PDF de informe."""
    consentimiento = _obtener_consentimiento_o_404(db, consentimiento_id)
    _verificar_misma_institucion_o_403(usuario_actual, consentimiento.institucion_id, "No puedes subir evidencia de un consentimiento de otro colegio.")
    contenido = leer_archivo_con_limite(archivo, crud.TAMANO_MAXIMO_EVIDENCIA_BYTES, "archivo de evidencia")
    return crud.guardar_evidencia_consentimiento(
        db=db, consentimiento=consentimiento, contenido=contenido,
        nombre_archivo=archivo.filename or "evidencia",
        content_type=archivo.content_type or "application/octet-stream",
        usuario_id=usuario_actual.id,
    )


@router.get("/consentimiento/{consentimiento_id}/evidencia")
def descargar_evidencia_consentimiento_endpoint(
    consentimiento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Descarga el archivo subido con el endpoint de arriba. 404 si el
    consentimiento no tiene evidencia (nunca hubo una subida)."""
    consentimiento = _obtener_consentimiento_o_404(db, consentimiento_id)
    _verificar_misma_institucion_o_403(usuario_actual, consentimiento.institucion_id, "No puedes ver evidencia de un consentimiento de otro colegio.")
    if not consentimiento.evidencia_ruta:
        raise HTTPException(status_code=404, detail="Este consentimiento no tiene evidencia adjunta.")
    try:
        contenido = crud.leer_evidencia_consentimiento(consentimiento)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="La evidencia registrada ya no está disponible en el almacenamiento.")

    nombre_descarga = consentimiento.evidencia_nombre_archivo or "evidencia"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=consentimiento.evidencia_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre_descarga}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        },
    )


# ℹ️ Citas se quedan igual porque están bajo /personas/citas/...
@router.post("/citas/", response_model=schemas.CitaResponse)
def agendar_cita(
    cita: schemas.CitaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """`cita.persona_id` presente -> cita individual (igual que siempre).
    Ausente -> actividad grupal (taller/charla/otro): exige `titulo` y
    resuelve la institución de la SESIÓN (nunca de `cita.institucion_id`,
    salvo para superadmin, que no tiene institución propia y por eso sí
    debe indicarla -- mismo criterio B-8 que ConsentimientoCreate)."""
    if cita.persona_id is not None:
        persona = db.query(models.Persona).filter(models.Persona.id == cita.persona_id).first()
        if not persona:
            raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
        if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
            raise HTTPException(status_code=403, detail="No puedes agendar citas de otro colegio.")
        institucion_id = persona.institucion_id
    else:
        if not cita.titulo or not cita.titulo.strip():
            raise HTTPException(
                status_code=400,
                detail="Una actividad grupal (sin alumno puntual) necesita un título.",
            )
        if usuario_actual.rol == "superadmin":
            if cita.institucion_id is None:
                raise HTTPException(status_code=400, detail="Indica institucion_id para una actividad grupal.")
            institucion_id = cita.institucion_id
        else:
            institucion_id = usuario_actual.institucion_id

    return crud.crear_cita(db=db, cita=cita, psicologo_id=usuario_actual.id, institucion_id=institucion_id)


@router.get("/citas/mi-agenda", response_model=List[schemas.CitaResponse])
def mi_agenda(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Citas individuales propias + TODAS las actividades grupales de la
    institución (ver crud.listar_citas_del_psicologo)."""
    return crud.listar_citas_del_psicologo(
        db=db, psicologo_id=usuario_actual.id, institucion_id=usuario_actual.institucion_id,
    )

@router.patch("/citas/{cita_id}", response_model=schemas.CitaResponse)
def editar_cita(
    cita_id: int,
    datos: schemas.CitaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Reprogramar horario/motivo, o cambiar el estado de una cita."""
    cita = db.query(models.CitaProgramada).filter(models.CitaProgramada.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    if usuario_actual.rol != "superadmin" and cita.psicologo_id != usuario_actual.id:
        raise HTTPException(status_code=403, detail="No puedes editar una cita de otro psicólogo.")
    return crud.actualizar_cita(db=db, cita_id=cita_id, datos=datos)


@router.delete("/citas/{cita_id}", status_code=status.HTTP_200_OK)
def cancelar_cita_endpoint(
    cita_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Cancela una cita (soft-delete cambiando estado a 'Cancelada')."""
    cita = db.query(models.CitaProgramada).filter(models.CitaProgramada.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")
    if usuario_actual.rol != "superadmin" and cita.psicologo_id != usuario_actual.id:
        raise HTTPException(status_code=403, detail="No puedes cancelar una cita de otro psicólogo.")
    crud.cancelar_cita(db=db, cita_id=cita_id)
    return {"mensaje": "Cita cancelada."}


@router.get("/{persona_id}/citas", response_model=List[schemas.CitaResponse])
def listar_citas_de_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Historial de citas de un alumno específico."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver las citas de un alumno de otro colegio.")
    return crud.listar_citas_por_persona(db=db, persona_id=persona_id)

# 🟢 CORREGIDO: quitamos '/personas' repetido -> URL final: /api/admin/personas/{persona_id}/ficha-completa
@router.get("/{persona_id}/ficha-completa")
def ver_ficha_completa(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Vista unificada: datos del alumno + evaluaciones + sesiones + citas + consentimiento."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver la ficha de un alumno de otro colegio.")

    return crud.obtener_ficha_completa(db=db, persona=persona, usuario_actual=usuario_actual)


@router.get("/{persona_id}/detalle", response_model=schemas.PersonaResponse)
def ver_detalle_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Un único registro de Persona con TODOS sus campos — a diferencia de
    ficha-completa (que solo expone un subconjunto dentro de
    datos_personales) o de listar_personas_de_institucion (que exige conocer
    de antemano institucion_id, algo que un superadmin no trae en su propio
    JWT). Mismo candado que ver_ficha_completa/editar_persona: superadmin
    siempre puede, sin depender de su propio institucion_id porque la
    comparación de abajo ni se evalúa para ese rol; cualquier otro rol solo
    dentro de su propia institución.

    Nota de ruteo: no puede llamarse "GET /{persona_id}" a secas — esa forma
    de un solo segmento ya la ocupa GET /{institucion_id} (línea ~36) y,
    como ambas compartirían la misma forma de ruta, la primera registrada
    ganaría siempre (mismo problema que ya documenta
    test_nucleo_estudiante_unitario.py para otras rutas de este router).
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el registro de un alumno de otro colegio.")
    return persona


@router.patch("/{persona_id}", response_model=schemas.PersonaResponse)
def editar_persona(
    persona_id: int,
    datos: schemas.PersonaUpdate,
    # 🆕 ARCO — rectificación con trazabilidad. Opcional: una edición
    # rutinaria (sin este parámetro) se comporta exactamente igual que
    # siempre. Cuando el propio titular (o su apoderado) ejerce formalmente
    # su derecho de rectificación, pasar la referencia de esa solicitud deja,
    # además del `RegistroCambiosPersona` de siempre, una fila en
    # `auditoria_arco` que lo distingue de una corrección administrativa
    # cualquiera — ver crud.actualizar_persona.
    referencia_solicitud_arco: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar registros de otra institución.")
    # 🔒 "activo" es un atajo directo sin motivo ni trazabilidad — a
    # diferencia de dar de baja/trasladar vía el proceso de promoción anual
    # (que exige `motivo_detalle` y queda registrado en
    # ProcesoPromocionDetalle) o de la anonimización ARCO (que además borra
    # datos y audita en RegistroAuditoriaArco). "psicologo" puede seguir
    # editando el resto de PersonaUpdate con total normalidad; solo este
    # campo queda reservado a quien administra el colegio.
    if "activo" in datos.model_fields_set and usuario_actual.rol not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Tu rol no puede activar/desactivar estudiantes directamente. "
                "Usa el proceso de promoción anual (retiro/traslado, con motivo) para esto."
            ),
        )
    return crud.actualizar_persona(
        db=db, persona_id=persona_id, datos=datos, usuario_actual=usuario_actual,
        referencia_solicitud_arco=referencia_solicitud_arco,
    )


@router.get("/{persona_id}/historial-cambios", response_model=List[schemas.RegistroCambioPersonaResponse])
def ver_historial_cambios_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    # 🆕 PASO 3 — igual que el resto de accesos "de staff" a la ficha de un
    # alumno, pero además EXCLUYE explícitamente el rol "colegio": esta
    # bitácora es para quien gestiona al estudiante clínica/administrativamente
    # (superadmin/admin/psicólogo), no para la cuenta genérica del colegio.
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el historial de cambios de otra institución.")
    return crud.listar_historial_cambios_persona(db=db, persona_id=persona_id)


@router.post("/{persona_id}/anonimizar-arco", status_code=status.HTTP_200_OK)
def anonimizar_persona_derecho_arco(
    persona_id: int,
    request: Request,
    referencia_solicitud: Optional[str] = None,
    db: Session = Depends(get_db),
    # 🔒 B-12: acción IRREVERSIBLE. Antes bastaba con estar autenticado: un
    # psicólogo o la cuenta genérica "colegio" podían destruir la PII de un
    # alumno. Ahora exige responsable con autoridad sobre el colegio.
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """🏛️ Ley 29733 — Anonimiza el registro maestro del estudiante.

    No es un borrado físico: la fila permanece para no romper el histórico,
    solo se vacía la información identificable. Queda anotado en la bitácora
    `auditoria_arco` quién lo hizo, cuándo, desde qué IP y sobre quién.
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes anonimizar registros de otra institución.")

    exito = crud.anonimizar_persona_arco(
        db=db,
        persona_id=persona_id,
        institucion_id=usuario_actual.institucion_id,
        es_superadmin=(usuario_actual.rol == "superadmin"),
        ejecutado_por=usuario_actual,                      # 🏛️ B-12
        ip_solicitante=ip_del_cliente(request),
        referencia_solicitud=referencia_solicitud,
    )
    if not exito:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    return {"mensaje": "Los datos identificables del registro maestro han sido irreversiblemente anonimizados."}


@router.get("/{persona_id}/exportar-datos-arco")
def exportar_datos_persona_derecho_arco(
    persona_id: int,
    request: Request,
    referencia_solicitud: Optional[str] = None,
    # 🆕 Acota el export a lo cubierto por ESE consentimiento puntual —
    # ver crud.exportar_datos_persona_arco para el detalle de qué se
    # incluye/excluye cuando se pasa este parámetro. Omitido = comportamiento
    # de siempre (bundle completo).
    consentimiento_id: Optional[int] = None,
    db: Session = Depends(get_db),
    # 🔒 ARCO — derecho de ACCESO. Nunca "colegio": el bundle incluye
    # contenido clínico (diagnósticos, informes, sesiones de seguimiento)
    # que "colegio" no puede ver en ningún otro endpoint de este sistema —
    # dejarlo entrar aquí sería un atajo alrededor de toda la remediación de
    # permisos ya cerrada (ver CLAUDE.md, "Permission surface").
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🏛️ Ley 29733 — Derecho ARCO de ACCESO: exporta todo lo que se tiene
    de este estudiante (ficha, matrícula, consentimientos, inscripciones,
    diagnósticos, informes —solo metadata de versión, nunca el PDF—, sesiones
    de seguimiento, citas y expediente clínico). El expediente clínico solo
    incluye las entradas que ESTE usuario puede leer (autor o superadmin) —
    ver `crud.exportar_datos_persona_arco`. Queda anotado en `auditoria_arco`,
    igual que una anonimización.

    Pasa `?consentimiento_id=N` para acotar el export a solo lo cubierto por
    ese consentimiento puntual (útil con varios consentimientos en el
    tiempo)."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes exportar datos de otra institución.")

    return crud.exportar_datos_persona_arco(
        db=db, persona=persona, usuario_actual=usuario_actual,
        ip_solicitante=ip_del_cliente(request),
        referencia_solicitud=referencia_solicitud,
        consentimiento_id=consentimiento_id,
    )


@router.get("/{persona_id}/historico-campanas")
def ver_historico_campanas_endpoint(
    persona_id: int,
    db: Session = Depends(get_db),
    # 🔒 Mismo criterio que exportar-datos-arco: incluye diagnósticos/niveles
    # clínicos a través del tiempo, así que nunca "colegio".
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🆕 Vista de comparación histórica entre campañas (docs/gaps-
    pendientes.md) — la evolución de este estudiante a través de todas las
    campañas en las que participó, lista cronológica y reagrupada por
    dimensión para comparar un mismo indicador (ej. puntaje de depresión)
    entre dos fechas. Ver `crud.historico_campanas_de_persona`."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el histórico de otro colegio.")

    return crud.historico_campanas_de_persona(db=db, persona=persona)


# ==========================================
# 🆕 NÚCLEO DEL ESTUDIANTE — ESTRUCTURA ACADÉMICA
# ==========================================
# Todas las rutas de este bloque usan más de un segmento de path
# (p. ej. "/academico/niveles"), a propósito: "/{institucion_id}" más arriba
# es de un solo segmento y capturaría cualquier ruta literal nueva de un solo
# segmento que se declare después, antes de llegar a FastAPI/Starlette a
# intentar la ruta correcta.

@router.post("/academico/niveles", response_model=schemas.NivelEducativoResponse)
def crear_nivel_educativo(
    datos: schemas.NivelEducativoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Crea un nivel educativo (Inicial/Primaria/Secundaria...) de una institución."""
    if usuario_actual.rol != "superadmin" and datos.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes crear estructura académica para otro colegio.")
    return crud.crear_nivel_educativo(db=db, datos=datos)


@router.get("/academico/niveles/{institucion_id}", response_model=List[schemas.NivelEducativoResponse])
def listar_niveles_educativos(
    institucion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(verificar_acceso_institucion),
):
    return crud.listar_niveles_de_institucion(db=db, institucion_id=institucion_id)


@router.post("/academico/grados", response_model=schemas.GradoResponse)
def crear_grado(
    datos: schemas.GradoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Crea un grado (1°, 2°...) dentro de un nivel educativo ya existente."""
    nivel = db.query(models.NivelEducativo).filter(models.NivelEducativo.id == datos.nivel_educativo_id).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="Nivel educativo no encontrado.")
    if usuario_actual.rol != "superadmin" and nivel.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes crear estructura académica para otro colegio.")
    return crud.crear_grado(db=db, datos=datos)


@router.get("/academico/grados/{nivel_educativo_id}", response_model=List[schemas.GradoResponse])
def listar_grados(
    nivel_educativo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    nivel = db.query(models.NivelEducativo).filter(models.NivelEducativo.id == nivel_educativo_id).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="Nivel educativo no encontrado.")
    if usuario_actual.rol != "superadmin" and nivel.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver la estructura académica de otro colegio.")
    return crud.listar_grados_de_nivel(db=db, nivel_educativo_id=nivel_educativo_id)


@router.post("/academico/secciones", response_model=schemas.SeccionResponse)
def crear_seccion(
    datos: schemas.SeccionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Crea una sección (A, B...) de un grado para un año escolar concreto.

    🔒 Cada año escolar es una fila de Sección distinta a propósito (ver el
    comentario en modulos/superadmin/models.py) — para reabrir un grado en un
    año nuevo, crea secciones nuevas en vez de reutilizar las del año pasado.
    """
    grado = db.query(models.Grado).filter(models.Grado.id == datos.grado_id).first()
    if not grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado.")
    if usuario_actual.rol != "superadmin" and grado.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes crear estructura académica para otro colegio.")
    return crud.crear_seccion(db=db, datos=datos)


@router.get("/academico/secciones/{grado_id}", response_model=List[schemas.SeccionResponse])
def listar_secciones(
    grado_id: int,
    anio_escolar: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    grado = db.query(models.Grado).filter(models.Grado.id == grado_id).first()
    if not grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado.")
    if usuario_actual.rol != "superadmin" and grado.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver la estructura académica de otro colegio.")
    return crud.listar_secciones_de_grado(db=db, grado_id=grado_id, anio_escolar=anio_escolar)


# 🆕 Edición (PATCH) — mismos permisos y mismo candado de tenant que los
# POST de arriba: solo admin/superadmin, y un admin solo sobre su propio
# colegio. Qué campos se pueden cambiar (y por qué no el padre ni el año
# escolar) está explicado en schemas.NivelEducativoUpdate.
@router.patch("/academico/niveles/{nivel_id}", response_model=schemas.NivelEducativoResponse)
def actualizar_nivel_educativo(
    nivel_id: int,
    datos: schemas.NivelEducativoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Corrige el nombre u orden de un nivel educativo."""
    nivel = db.query(models.NivelEducativo).filter(models.NivelEducativo.id == nivel_id).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="Nivel educativo no encontrado.")
    if usuario_actual.rol != "superadmin" and nivel.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar la estructura académica de otro colegio.")
    return crud.actualizar_nivel_educativo(db=db, nivel=nivel, datos=datos)


@router.patch("/academico/grados/{grado_id}", response_model=schemas.GradoResponse)
def actualizar_grado(
    grado_id: int,
    datos: schemas.GradoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Corrige el nombre u orden de un grado."""
    grado = db.query(models.Grado).filter(models.Grado.id == grado_id).first()
    if not grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado.")
    if usuario_actual.rol != "superadmin" and grado.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar la estructura académica de otro colegio.")
    return crud.actualizar_grado(db=db, grado=grado, datos=datos)


@router.patch("/academico/secciones/{seccion_id}", response_model=schemas.SeccionResponse)
def actualizar_seccion(
    seccion_id: int,
    datos: schemas.SeccionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Corrige el nombre o turno de una sección (el año escolar no se edita)."""
    seccion = db.query(models.Seccion).filter(models.Seccion.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada.")
    if usuario_actual.rol != "superadmin" and seccion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar la estructura académica de otro colegio.")
    return crud.actualizar_seccion(db=db, seccion=seccion, datos=datos)


# 🆕 Eliminación (DELETE) — mismos permisos y candado de tenant que crear/
# editar. Solo borra lo que nadie usa (ver crud.eliminar_nivel_educativo):
# lo que ya tiene hijos, matrículas o evaluaciones aplicadas devuelve 409.
@router.delete("/academico/niveles/{nivel_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_nivel_educativo(
    nivel_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    nivel = db.query(models.NivelEducativo).filter(models.NivelEducativo.id == nivel_id).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="Nivel educativo no encontrado.")
    if usuario_actual.rol != "superadmin" and nivel.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes eliminar la estructura académica de otro colegio.")
    crud.eliminar_nivel_educativo(db=db, nivel=nivel)


@router.delete("/academico/grados/{grado_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_grado(
    grado_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    grado = db.query(models.Grado).filter(models.Grado.id == grado_id).first()
    if not grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado.")
    if usuario_actual.rol != "superadmin" and grado.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes eliminar la estructura académica de otro colegio.")
    crud.eliminar_grado(db=db, grado=grado)


@router.delete("/academico/secciones/{seccion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_seccion(
    seccion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    seccion = db.query(models.Seccion).filter(models.Seccion.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada.")
    if usuario_actual.rol != "superadmin" and seccion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes eliminar la estructura académica de otro colegio.")
    crud.eliminar_seccion(db=db, seccion=seccion)


@router.post("/{persona_id}/matricula", response_model=schemas.MatriculaResponse)
def matricular_persona(
    persona_id: int,
    datos: schemas.MatriculaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Asigna o mueve a un alumno a una sección. Un cambio de sección NO
    reescribe evaluaciones pasadas: solo cierra la matrícula vigente y abre
    una nueva (ver `crud.matricular_persona_en_seccion`)."""
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes matricular alumnos de otro colegio.")
    return crud.matricular_persona_en_seccion(
        db=db, persona=persona, seccion_id=datos.seccion_id, usuario_id=usuario_actual.id,
    )


@router.get("/{persona_id}/historial-academico")
def ver_historial_academico(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el historial académico de otro colegio.")
    return crud.obtener_historial_academico(db=db, persona_id=persona_id)


@router.get("/por-codigo/{codigo_institucional}", response_model=schemas.PersonaResponse)
def buscar_por_codigo_institucional(
    codigo_institucional: str,
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """🆕 Búsqueda por el identificador funcional del alumno (punto 5): el
    que usarán importación Excel, búsqueda y asociación masiva — nunca el DNI.

    superadmin debe indicar ?institucion_id=; el resto siempre busca dentro
    de su propia institución, sin poder pedir la de otro colegio.
    """
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(status_code=400, detail="Como superadmin, debes especificar ?institucion_id=")
    else:
        institucion_id = usuario_actual.institucion_id

    persona = crud.buscar_persona_por_codigo(
        db=db, institucion_id=institucion_id, codigo_institucional=codigo_institucional,
    )
    if not persona:
        raise HTTPException(status_code=404, detail="No hay ningún alumno con ese código en esta institución.")
    return persona


# ==========================================
# 🆕 IMPORTACIÓN MASIVA DE ESTUDIANTES (EXCEL)
# ==========================================
# Tres operaciones bien delimitadas, no una sola que lo haga todo:
#   1) plantilla   — de solo lectura, ni toca la BD ni recibe nada del cliente.
#   2) validar     — sube y valida el archivo; NUNCA escribe. Puede llamarse
#                     tantas veces como se quiera mientras se corrige el Excel.
#   3) confirmar    — vuelve a validar desde cero (nunca confía en lo que el
#                     cliente recuerde de una llamada anterior a "validar") y,
#                     solo si eso sale limpio para cada fila, aplica en una
#                     única transacción atómica.
#
# institucion_id SIEMPRE sale del usuario autenticado (o del parámetro
# explícito de superadmin) — el Excel nunca puede declarar una institución
# distinta (punto 15).

def _institucion_para_importacion(usuario_actual: auth_models.Usuario, institucion_id: Optional[int]) -> int:
    # 🔒 Misma convención que GET /auth/usuarios/: superadmin debe indicar
    # ?institucion_id= explícito; admin/psicologo SIEMPRE se fuerzan a la
    # institución de su propio token, y cualquier institucion_id ajeno que
    # manden en la request se ignora en silencio (nunca se usa para nada, así
    # que no hay nada que un 403 protegería que esto no proteja ya). El acceso
    # de rol (`colegio` no puede llegar aquí en absoluto) lo filtra el
    # `requerir_rol(...)` de cada endpoint, no esta función.
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(status_code=400, detail="Como superadmin, debes especificar ?institucion_id=")
        return institucion_id
    return usuario_actual.institucion_id


@router.get("/importar/plantilla")
def descargar_plantilla_importacion(
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Descarga la plantilla oficial .xlsx, con la estructura académica YA
    creada en esta institución en su segunda hoja, a modo de referencia."""
    inst_id = _institucion_para_importacion(usuario_actual, institucion_id)
    buffer = importacion.generar_plantilla(db=db, institucion_id=inst_id)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=plantilla_estudiantes_aurorasoft.xlsx"},
    )


@router.post("/importar/validar")
async def validar_importacion_estudiantes(
    archivo: UploadFile = File(...),
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Sube y valida el Excel — NUNCA escribe nada en la base. Devuelve el
    resumen (nuevos/actualizados/duplicados/errores) y el detalle fila por
    fila para la vista previa. Puede llamarse repetidamente mientras se
    corrige el archivo, sin ningún efecto secundario."""
    inst_id = _institucion_para_importacion(usuario_actual, institucion_id)
    contenido = leer_archivo_con_limite(archivo, importacion.TAMANO_MAXIMO_BYTES, "archivo")
    try:
        filas_crudas = importacion.leer_filas_excel(contenido, archivo.filename or "")
    except importacion.ArchivoInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    return importacion.validar_filas(db=db, institucion_id=inst_id, filas_crudas=filas_crudas)


@router.post("/importar/confirmar")
async def confirmar_importacion_estudiantes(
    archivo: UploadFile = File(...),
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Aplica la importación de verdad.

    🔒 Vuelve a leer y a validar el MISMO archivo desde cero, contra el
    estado ACTUAL de la base — nunca contra un resultado de `/validar` que
    el cliente pueda haber guardado. Si algo cambió entre medio (alguien
    creó ese código en paralelo, por ejemplo), esta segunda validación lo
    vuelve a detectar; no hay ningún dato "de confianza" que el cliente
    pueda inyectar aquí.
    """
    inst_id = _institucion_para_importacion(usuario_actual, institucion_id)
    contenido = leer_archivo_con_limite(archivo, importacion.TAMANO_MAXIMO_BYTES, "archivo")
    try:
        filas_crudas = importacion.leer_filas_excel(contenido, archivo.filename or "")
    except importacion.ArchivoInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    resultado_validacion = importacion.validar_filas(db=db, institucion_id=inst_id, filas_crudas=filas_crudas)
    return importacion.aplicar_importacion(
        db=db, institucion_id=inst_id, resultado_validacion=resultado_validacion,
        usuario_id=usuario_actual.id,
    )


# ==========================================
# 🆕 PROMOCIÓN ANUAL DE ESTUDIANTES
# ==========================================
# Mismo patrón validar/previsualizar/confirmar que la importación de arriba:
#   1) iniciar    — calcula el mapeo automático (algoritmo de grado/nivel
#                    siguiente) para cada estudiante con matrícula vigente en
#                    `anio_origen` y lo deja como borrador editable. No
#                    aplica ningún cambio real todavía.
#   2) previsualizar/editar — reabrir el borrador cuantas veces haga falta y
#                    marcar excepciones (repitente/retirado/trasladado/
#                    cambio_manual/egreso) por fila o en lote.
#   3) confirmar  — re-valida cada fila contra la BD en este momento (nunca
#                    contra lo que quedó calculado al crear el borrador) y
#                    aplica todo en una única transacción.
# A diferencia de Excel, aquí SÍ conviene persistir el borrador server-side
# (ProcesoPromocion/ProcesoPromocionDetalle): revisar el cierre de año de
# todo un colegio es trabajo de varias sesiones, no un solo POST.
#
# Todas las rutas tienen 2+ segmentos, mismo criterio que /academico/... más
# arriba — para no quedar atrapadas por GET/{institucion_id} o
# PATCH/{persona_id}, de un solo segmento, registrados antes en este router.

def _institucion_para_promocion(usuario_actual: auth_models.Usuario, institucion_id: Optional[int]) -> int:
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(status_code=400, detail="Como superadmin, debes especificar institucion_id.")
        return institucion_id
    if institucion_id is not None and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes gestionar la promoción de otro colegio.")
    return usuario_actual.institucion_id


def _obtener_proceso_promocion_o_404(db: Session, proceso_id: int) -> models.ProcesoPromocion:
    proceso = crud.obtener_proceso_promocion(db=db, proceso_id=proceso_id)
    if not proceso:
        raise HTTPException(status_code=404, detail="Proceso de promoción no encontrado.")
    return proceso


@router.post("/promocion/procesos", status_code=status.HTTP_201_CREATED)
def iniciar_proceso_promocion_endpoint(
    datos: schemas.ProcesoPromocionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Calcula el mapeo automático de TODOS los estudiantes con matrícula
    vigente en `anio_origen` y lo deja como borrador editable — no aplica
    ningún cambio real todavía (eso solo pasa en /confirmar)."""
    inst_id = _institucion_para_promocion(usuario_actual, datos.institucion_id)
    proceso = crud.iniciar_proceso_promocion(
        db=db, institucion_id=inst_id, anio_origen=datos.anio_origen,
        anio_destino=datos.anio_destino, usuario_id=usuario_actual.id,
    )
    return crud.describir_proceso_promocion(db=db, proceso=proceso)


@router.get("/promocion/procesos")
def listar_procesos_promocion_endpoint(
    institucion_id: Optional[int] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Lista los procesos de promoción de una institución (borrador/
    confirmado/cancelado), más reciente primero — para encontrar un borrador
    ya iniciado antes de crear uno nuevo."""
    inst_id = _institucion_para_promocion(usuario_actual, institucion_id)
    procesos = crud.listar_procesos_promocion(db=db, institucion_id=inst_id, estado=estado)
    return [
        {
            "id": p.id, "institucion_id": p.institucion_id, "anio_origen": p.anio_origen,
            "anio_destino": p.anio_destino, "estado": p.estado,
            "creado_por_usuario_id": p.creado_por_usuario_id, "fecha_creacion": p.fecha_creacion,
            "confirmado_por_usuario_id": p.confirmado_por_usuario_id,
            "fecha_confirmacion": p.fecha_confirmacion,
        }
        for p in procesos
    ]


@router.get("/promocion/procesos/{proceso_id}")
def ver_proceso_promocion_endpoint(
    proceso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Vista previa completa: cabecera + una fila por estudiante con la
    propuesta automática (o la excepción marcada) y, tras confirmar, qué
    matrícula resultó."""
    proceso = _obtener_proceso_promocion_o_404(db, proceso_id)
    if usuario_actual.rol != "superadmin" and proceso.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver un proceso de promoción de otro colegio.")
    return crud.describir_proceso_promocion(db=db, proceso=proceso)


@router.patch("/promocion/procesos/{proceso_id}/detalle")
def editar_detalles_promocion_endpoint(
    proceso_id: int,
    datos: schemas.EditarDetallesPromocionRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Marca excepciones o corrige el destino de una o varias filas del
    borrador antes de confirmar — todo o nada: si una fila de la lista es
    inválida, ninguna se aplica."""
    proceso = _obtener_proceso_promocion_o_404(db, proceso_id)
    if usuario_actual.rol != "superadmin" and proceso.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar un proceso de promoción de otro colegio.")
    crud.editar_detalles_promocion(db=db, proceso=proceso, ediciones=datos.ediciones)
    return crud.describir_proceso_promocion(db=db, proceso=proceso)


@router.post("/promocion/procesos/{proceso_id}/confirmar")
def confirmar_proceso_promocion_endpoint(
    proceso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Aplica el proceso: por cada fila cierra la matrícula de origen y, si
    corresponde, abre la matrícula del año destino — todo en una única
    transacción, re-validando cada fila contra la BD en este momento (nunca
    contra lo que quedó calculado al crear el borrador)."""
    proceso = _obtener_proceso_promocion_o_404(db, proceso_id)
    if usuario_actual.rol != "superadmin" and proceso.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes confirmar un proceso de promoción de otro colegio.")
    crud.confirmar_proceso_promocion(db=db, proceso=proceso, usuario_id=usuario_actual.id)
    return crud.describir_proceso_promocion(db=db, proceso=proceso)


@router.post("/promocion/procesos/{proceso_id}/cancelar")
def cancelar_proceso_promocion_endpoint(
    proceso_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Descarta un borrador sin aplicar ningún cambio real — libera el año
    origen/destino para poder iniciar un proceso nuevo."""
    proceso = _obtener_proceso_promocion_o_404(db, proceso_id)
    if usuario_actual.rol != "superadmin" and proceso.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes cancelar un proceso de promoción de otro colegio.")
    crud.cancelar_proceso_promocion(db=db, proceso=proceso)
    return {"mensaje": "Proceso de promoción cancelado."}


# ==========================================
# 🆕 EXPEDIENTE / SEGUIMIENTO DEL ESTUDIANTE
# ==========================================
# Todas las rutas de este bloque tienen 2+ segmentos, mismo criterio que
# /academico/... y /promocion/... más arriba.

def _obtener_persona_o_404(db: Session, persona_id: int) -> models.Persona:
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    return persona


def _verificar_misma_institucion_o_403(usuario_actual: auth_models.Usuario, institucion_id: int, mensaje: str):
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail=mensaje)


@router.post("/{persona_id}/expediente", response_model=schemas.EntradaExpedienteResponse, status_code=status.HTTP_201_CREATED)
def crear_entrada_expediente_endpoint(
    persona_id: int,
    datos: schemas.EntradaExpedienteCreate,
    db: Session = Depends(get_db),
    # 🔒 Solo el equipo clínico escribe el expediente — nunca "admin" ni
    # "colegio", ni siquiera para las entradas puente (enlazar una sesión o
    # una prueba ya existente sigue siendo un acto clínico).
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    """Crea una entrada del expediente. Si es de un tipo con contenido
    propio, crea también su v1 en la misma transacción."""
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes escribir en el expediente de otro colegio.")
    return crud.crear_entrada_expediente(db=db, persona=persona, autor_usuario_id=usuario_actual.id, datos=datos)


@router.get("/{persona_id}/expediente", response_model=List[schemas.EntradaExpedienteResponse])
def listar_expediente_endpoint(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Metadata (sin contenido narrativo) de las entradas que ESTE usuario
    puede ver — dos psicólogos distintos del mismo colegio pueden ver listas
    distintas del mismo estudiante, según quién sea el autor de cada fila."""
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes ver el expediente de otro colegio.")
    return crud.listar_entradas_expediente_visibles(db=db, persona_id=persona_id, usuario_actual=usuario_actual)


@router.get("/expediente/{entrada_id}")
def ver_detalle_entrada_expediente_endpoint(
    entrada_id: int,
    request: Request,
    version: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Contenido completo de una entrada (la versión vigente, o una
    puntual con ?version=N). Aplica la regla de acceso final — 403 si no
    corresponde — y registra la lectura en RegistroLecturasExpediente."""
    entrada = db.query(models.EntradaExpediente).filter(models.EntradaExpediente.id == entrada_id).first()
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada de expediente no encontrada.")
    _verificar_misma_institucion_o_403(usuario_actual, entrada.institucion_id, "No puedes ver el expediente de otro colegio.")
    return crud.obtener_detalle_entrada_expediente(
        db=db, entrada=entrada, usuario_actual=usuario_actual,
        ip_lectura=ip_del_cliente(request),
        numero_version=version,
    )


@router.post("/expediente/{entrada_id}/versiones", status_code=status.HTTP_201_CREATED)
def agregar_version_expediente_endpoint(
    entrada_id: int,
    datos: schemas.EntradaExpedienteVersionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    """Corrige/actualiza el contenido — crea version_actual + 1, nunca edita
    una versión existente. `motivo_version` es obligatorio (ver esquema).
    Solo el autor de la entrada (o superadmin) puede llamar esto: una
    autorización de colegio es de lectura, jamás de escritura."""
    entrada = db.query(models.EntradaExpediente).filter(models.EntradaExpediente.id == entrada_id).first()
    if not entrada:
        raise HTTPException(status_code=404, detail="Entrada de expediente no encontrada.")
    _verificar_misma_institucion_o_403(usuario_actual, entrada.institucion_id, "No puedes editar el expediente de otro colegio.")
    return crud.agregar_version_expediente(db=db, entrada=entrada, usuario_actual=usuario_actual, datos=datos)


@router.post("/{persona_id}/expediente/evidencia", response_model=schemas.EntradaExpedienteResponse, status_code=status.HTTP_201_CREATED)
def subir_evidencia_expediente_endpoint(
    persona_id: int,
    archivo: UploadFile = File(...),
    titulo: str = Form(...),
    descripcion: Optional[str] = Form(None),
    fecha_entrada: Optional[datetime] = Form(None),
    informe_id: Optional[int] = Form(None),
    incluir_en_pdf_informe: bool = Form(False),
    db: Session = Depends(get_db),
    # 🔒 Mismo rol que el resto del expediente — ver crear_entrada_expediente_endpoint.
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    """Sube un archivo escaneado/fotografiado (dibujo proyectivo, ficha
    física, hoja de respuestas en papel...) como entrada 'evidencia' del
    expediente clínico — PDF/JPG/PNG, máx. 10 MB, misma lista blanca que la
    evidencia de consentimientos. `informe_id` es opcional: ausente =
    evidencia suelta del estudiante; presente = vinculada a esa aplicación
    puntual. `incluir_en_pdf_informe=True` (exige informe_id) la marca para
    incrustarse como anexo la próxima vez que se genere una versión de ese
    informe (automática, "Reemitir informe" o "Reprocesar") — nunca
    modifica una versión ya emitida."""
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes subir evidencia al expediente de otro colegio.")
    contenido = leer_archivo_con_limite(archivo, crud.TAMANO_MAXIMO_EVIDENCIA_BYTES, "archivo de evidencia")
    return crud.crear_entrada_expediente_evidencia(
        db=db, persona=persona, autor_usuario_id=usuario_actual.id,
        contenido=contenido, nombre_archivo=archivo.filename or "evidencia",
        content_type=archivo.content_type or "application/octet-stream",
        titulo=titulo, descripcion=descripcion, fecha_entrada=fecha_entrada,
        informe_id=informe_id, incluir_en_pdf_informe=incluir_en_pdf_informe,
    )


@router.get("/expediente/evidencia/{entrada_id}/archivo")
def descargar_evidencia_expediente_endpoint(
    entrada_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Descarga el archivo de una entrada 'evidencia' — misma regla de
    acceso y el mismo registro de auditoría que el detalle de cualquier
    otra entrada del expediente (ver obtener_detalle_entrada_expediente):
    autor/superadmin, o 'colegio' con AutorizacionAccesoColegio vigente."""
    entrada = db.query(models.EntradaExpediente).filter(
        models.EntradaExpediente.id == entrada_id,
        models.EntradaExpediente.tipo_entrada == crud.TIPO_ENTRADA_EVIDENCIA,
    ).first()
    if not entrada:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada.")
    _verificar_misma_institucion_o_403(usuario_actual, entrada.institucion_id, "No puedes ver evidencia de otro colegio.")
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(db, entrada, usuario_actual)
    if not autorizado:
        raise HTTPException(status_code=403, detail="No tienes acceso a esta evidencia.")
    try:
        contenido = crud.leer_evidencia_expediente(entrada)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="El archivo ya no está disponible en el almacenamiento.")

    db.add(models.RegistroLecturasExpediente(
        entrada_expediente_id=entrada.id,
        persona_id=entrada.persona_id,
        institucion_id=entrada.institucion_id,
        leido_por_usuario_id=usuario_actual.id,
        rol_lector=usuario_actual.rol,
        ip_lectura=ip_del_cliente(request),
        numero_version_leida=None,
        autorizacion_acceso_colegio_id=autorizacion.id if autorizacion else None,
    ))
    db.commit()

    nombre_descarga = entrada.nombre_archivo_original or "evidencia"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type=entrada.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nombre_descarga}"'},
    )


@router.patch("/expediente/evidencia/{entrada_id}", response_model=schemas.EntradaExpedienteResponse)
def actualizar_evidencia_expediente_endpoint(
    entrada_id: int,
    datos: schemas.EntradaExpedienteEvidenciaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    """Alterna `incluir_en_pdf_informe` — único campo editable de una
    evidencia ya subida (el archivo/título no se corrigen in-place, se
    registra una entrada nueva). Solo el propio autor o superadmin, mismo
    criterio que agregar_version_expediente."""
    entrada = db.query(models.EntradaExpediente).filter(
        models.EntradaExpediente.id == entrada_id,
        models.EntradaExpediente.tipo_entrada == crud.TIPO_ENTRADA_EVIDENCIA,
    ).first()
    if not entrada:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada.")
    _verificar_misma_institucion_o_403(usuario_actual, entrada.institucion_id, "No puedes editar evidencia de otro colegio.")
    if entrada.autor_usuario_id != usuario_actual.id and usuario_actual.rol != "superadmin":
        raise HTTPException(status_code=403, detail="Solo quien registró esta evidencia (o superadmin) puede editarla.")
    return crud.actualizar_evidencia_expediente(db=db, entrada=entrada, incluir_en_pdf_informe=datos.incluir_en_pdf_informe)


# ------------------------------------------
# 🆕 ContactoFamiliar
# ------------------------------------------
@router.post("/{persona_id}/contactos", response_model=schemas.ContactoFamiliarResponse, status_code=status.HTTP_201_CREATED)
def crear_contacto_familiar_endpoint(
    persona_id: int,
    datos: schemas.ContactoFamiliarCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes crear contactos de otro colegio.")
    return crud.crear_contacto_familiar(db=db, persona=persona, datos=datos, usuario_id=usuario_actual.id)


@router.get("/{persona_id}/contactos", response_model=List[schemas.ContactoFamiliarResponse])
def listar_contactos_familiares_endpoint(
    persona_id: int,
    incluir_inactivos: bool = False,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes ver los contactos de otro colegio.")
    return crud.listar_contactos_de_persona(db=db, persona_id=persona_id, incluir_inactivos=incluir_inactivos)


@router.patch("/contactos/{contacto_id}", response_model=schemas.ContactoFamiliarResponse)
def actualizar_contacto_familiar_endpoint(
    contacto_id: int,
    datos: schemas.ContactoFamiliarUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        raise HTTPException(status_code=404, detail="Contacto familiar no encontrado.")
    _verificar_misma_institucion_o_403(usuario_actual, contacto.institucion_id, "No puedes editar contactos de otro colegio.")
    return crud.actualizar_contacto_familiar(db=db, contacto_id=contacto_id, datos=datos)


@router.delete("/contactos/{contacto_id}", response_model=schemas.ContactoFamiliarResponse)
def desactivar_contacto_familiar_endpoint(
    contacto_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Soft-delete — nunca borra físicamente (un EntradaExpediente puede
    seguir apuntando a este contacto)."""
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        raise HTTPException(status_code=404, detail="Contacto familiar no encontrado.")
    _verificar_misma_institucion_o_403(usuario_actual, contacto.institucion_id, "No puedes desactivar contactos de otro colegio.")
    return crud.desactivar_contacto_familiar(db=db, contacto_id=contacto_id)


@router.post("/contactos/{contacto_id}/reactivar", response_model=schemas.ContactoFamiliarResponse)
def reactivar_contacto_familiar_endpoint(
    contacto_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Revierte una desactivación — mismo candado de institución/rol que el
    resto del CRUD de ContactoFamiliar (crear/editar/desactivar)."""
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        raise HTTPException(status_code=404, detail="Contacto familiar no encontrado.")
    _verificar_misma_institucion_o_403(usuario_actual, contacto.institucion_id, "No puedes reactivar contactos de otro colegio.")
    return crud.reactivar_contacto_familiar(db=db, contacto_id=contacto_id)


# ------------------------------------------
# 🆕 Motor de documentos institucionales, Paso 2 — PersonaDatosFamiliares
# (composición del hogar) y PersonaAntecedentesClinicos (tratamiento
# externo / diagnóstico reportado). Ambos 1:1 con Persona, mutables,
# reutilizables en cualquier informe individual futuro. Rutas de 2+
# segmentos (ver la nota de test_nucleo_estudiante_unitario.py sobre por
# qué una ruta literal de un solo segmento en este router nunca se
# alcanzaría).
# ------------------------------------------
@router.get("/{persona_id}/datos-familiares", response_model=schemas.PersonaDatosFamiliaresResponse)
def obtener_datos_familiares_endpoint(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes ver los datos familiares de otro colegio.")
    fila = crud.obtener_datos_familiares(db, persona_id)
    if not fila:
        # Todavía no se llenó la ficha — se devuelve la forma vacía en vez
        # de un 404 (una ficha nueva sin nada escrito no es un "recurso
        # inexistente"), con actualizado_en=None — nunca una fecha
        # inventada "de ahora mismo" para algo que nunca se editó.
        return schemas.PersonaDatosFamiliaresResponse(persona_id=persona_id)
    return fila


@router.patch("/{persona_id}/datos-familiares", response_model=schemas.PersonaDatosFamiliaresResponse)
def actualizar_datos_familiares_endpoint(
    persona_id: int,
    datos: schemas.PersonaDatosFamiliaresUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes editar los datos familiares de otro colegio.")
    return crud.actualizar_datos_familiares(db=db, persona_id=persona_id, usuario_id=usuario_actual.id, datos=datos)


@router.get("/{persona_id}/antecedentes-clinicos", response_model=schemas.PersonaAntecedentesClinicosResponse)
def obtener_antecedentes_clinicos_endpoint(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes ver los antecedentes clínicos de otro colegio.")
    fila = crud.obtener_antecedentes_clinicos(db, persona_id)
    if not fila:
        return schemas.PersonaAntecedentesClinicosResponse(persona_id=persona_id)
    return fila


@router.patch("/{persona_id}/antecedentes-clinicos", response_model=schemas.PersonaAntecedentesClinicosResponse)
def actualizar_antecedentes_clinicos_endpoint(
    persona_id: int,
    datos: schemas.PersonaAntecedentesClinicosUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes editar los antecedentes clínicos de otro colegio.")
    return crud.actualizar_antecedentes_clinicos(db=db, persona_id=persona_id, usuario_id=usuario_actual.id, datos=datos)


# ------------------------------------------
# 🆕 AutorizacionAccesoColegio
# ------------------------------------------
@router.post("/{persona_id}/autorizacion-colegio", response_model=schemas.AutorizacionAccesoColegioResponse, status_code=status.HTTP_201_CREATED)
def otorgar_autorizacion_colegio_endpoint(
    persona_id: int,
    datos: schemas.AutorizacionAccesoColegioCreate,
    db: Session = Depends(get_db),
    # 🔒 Solo el propio equipo clínico decide esta excepción — nunca
    # "colegio" (sería otorgarse acceso a sí mismo) ni "admin".
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes otorgar acceso sobre un estudiante de otro colegio.")
    return crud.otorgar_autorizacion_colegio(db=db, persona=persona, usuario_actual=usuario_actual, motivo=datos.motivo)


@router.post("/autorizacion-colegio/{autorizacion_id}/revocar", response_model=schemas.AutorizacionAccesoColegioResponse)
def revocar_autorizacion_colegio_endpoint(
    autorizacion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.GESTION_EXPEDIENTE),
):
    autorizacion = db.query(models.AutorizacionAccesoColegio).filter(models.AutorizacionAccesoColegio.id == autorizacion_id).first()
    if not autorizacion:
        raise HTTPException(status_code=404, detail="Autorización no encontrada.")
    _verificar_misma_institucion_o_403(usuario_actual, autorizacion.institucion_id, "No puedes revocar una autorización de otro colegio.")
    return crud.revocar_autorizacion_colegio(db=db, autorizacion=autorizacion, usuario_actual=usuario_actual)


@router.get("/{persona_id}/autorizacion-colegio", response_model=List[schemas.AutorizacionAccesoColegioResponse])
def listar_autorizaciones_colegio_endpoint(
    persona_id: int,
    db: Session = Depends(get_db),
    # Ver el estado (vigente/histórico) de la excepción es metadata de
    # permisos, no contenido clínico — admin sí puede consultarlo, aunque no
    # pueda otorgarlo ni revocarlo.
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    persona = _obtener_persona_o_404(db, persona_id)
    _verificar_misma_institucion_o_403(usuario_actual, persona.institucion_id, "No puedes ver esto de otro colegio.")
    return crud.listar_autorizaciones_colegio(db=db, persona_id=persona_id)