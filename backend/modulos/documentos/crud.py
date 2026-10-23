import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from . import models, schemas, pdf_generador
from .schemas import _parsear_lista_csv
from modulos.superadmin import models as superadmin_models
from modulos.superadmin import crud as superadmin_crud
from modulos.educativo import models as educativo_models
from modulos.auth import models as auth_models
from modulos.instituciones import models as instituciones_models
from core.cola_tareas import app as celery_app
from core.storage import obtener_storage_service, construir_storage_key_documento

logger = logging.getLogger("aurorasoft")


# ==========================================
# TipoDocumento
# ==========================================
def crear_tipo_documento(db: Session, datos: schemas.TipoDocumentoCreate) -> models.TipoDocumento:
    existente = db.query(models.TipoDocumento).filter(models.TipoDocumento.clave == datos.clave).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tipo de documento con clave '{datos.clave}'.",
        )
    tipo = models.TipoDocumento(**datos.model_dump())
    db.add(tipo)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos altas simultáneas con la misma clave — la
        # comprobación de arriba es solo la respuesta rápida común; esta
        # es la garantía real (mismo criterio que auth.crear_usuario).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un tipo de documento con clave '{datos.clave}'.",
        )
    db.refresh(tipo)
    return tipo


def listar_tipos_documento(db: Session, solo_activos: bool = False) -> List[models.TipoDocumento]:
    consulta = db.query(models.TipoDocumento)
    if solo_activos:
        consulta = consulta.filter(models.TipoDocumento.activo == True)  # noqa: E712
    return consulta.order_by(models.TipoDocumento.nombre).all()


def obtener_tipo_documento(db: Session, tipo_id: int) -> Optional[models.TipoDocumento]:
    return db.query(models.TipoDocumento).filter(models.TipoDocumento.id == tipo_id).first()


def actualizar_tipo_documento(
    db: Session, tipo: models.TipoDocumento, datos: schemas.TipoDocumentoUpdate,
) -> models.TipoDocumento:
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(tipo, campo, valor)
    db.commit()
    db.refresh(tipo)
    return tipo


# ==========================================
# AnioOficial
# ==========================================
def crear_o_actualizar_anio_oficial(db: Session, datos: schemas.AnioOficialCreate) -> models.AnioOficial:
    """Upsert por año — re-declarar el mismo año (ej. para corregir una
    errata de tipeo en el texto oficial) actualiza la fila existente en vez
    de chocar con la primary key."""
    fila = db.query(models.AnioOficial).filter(models.AnioOficial.anio == datos.anio).first()
    if fila:
        fila.texto = datos.texto
    else:
        fila = models.AnioOficial(anio=datos.anio, texto=datos.texto)
        db.add(fila)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos altas simultáneas del mismo año (poco probable
        # -- es un catálogo chico que edita superadmin -- pero barato de
        # blindar igual que el resto de este archivo).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El año {datos.anio} se guardó desde otra sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return fila


def listar_anios_oficiales(db: Session) -> List[models.AnioOficial]:
    return db.query(models.AnioOficial).order_by(models.AnioOficial.anio.desc()).all()


# ==========================================
# PlantillaDocumento
# ==========================================
def _desactivar_plantillas_activas(db: Session, institucion_id: int, tipo_documento_id: int) -> None:
    """🔒 Se llama SIEMPRE antes de insertar/activar una plantilla con
    activa=True, en la MISMA transacción. El índice único parcial
    `uq_documentos_plantilla_activa_por_institucion_y_tipo` exige que nunca
    haya dos plantillas activas a la vez para el mismo institución+tipo —
    sin este paso, activar una segunda plantilla lanzaría un IntegrityError
    crudo (500) en vez de reemplazar limpiamente a la anterior."""
    db.query(models.PlantillaDocumento).filter(
        models.PlantillaDocumento.institucion_id == institucion_id,
        models.PlantillaDocumento.tipo_documento_id == tipo_documento_id,
        models.PlantillaDocumento.activa == True,  # noqa: E712
    ).update({"activa": False})


def crear_plantilla_documento(
    db: Session, usuario_actual: auth_models.Usuario, datos: schemas.PlantillaDocumentoCreate,
) -> models.PlantillaDocumento:
    tipo = db.query(models.TipoDocumento).filter(models.TipoDocumento.id == datos.tipo_documento_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de documento no encontrado.")

    # 🔒 Igual que _institucion_para_importacion(): un no-superadmin queda
    # SIEMPRE forzado a su propia institución, sin importar qué mandó el
    # cliente — nunca 403, el valor ajeno simplemente se ignora. Antes de
    # abrir este endpoint a STAFF_CLINICO solo superadmin lo llamaba, así
    # que esta función nunca necesitó revalidar institucion_id.
    # 🆕 institucion_id=None (plantilla PREDETERMINADA global) solo lo puede
    # pedir superadmin — un no-superadmin que lo mande de todos modos
    # termina igual forzado a su propia institución, nunca a None.
    if datos.institucion_id is None and usuario_actual.rol != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo superadmin puede crear una plantilla predeterminada global.",
        )
    institucion_id = (
        datos.institucion_id if usuario_actual.rol == "superadmin" else usuario_actual.institucion_id
    )

    # 🆕 Las predeterminadas globales (institucion_id None) NUNCA se
    # desactivan entre sí — a diferencia de una institución real, donde
    # "activa" significa "la que gobierna los documentos nuevos de ese
    # tipo" (de ahí el candado de una sola a la vez), el catálogo global es
    # un MENÚ: varias predeterminadas del mismo tipo_documento_id pueden
    # coexistir activas (ej. "informe escolar" y "informe para padres",
    # ambas bajo el mismo tipo "Informe individual") — cada una un punto de
    # partida distinto para clonar, nunca una compitiendo con la otra.
    if datos.activa and institucion_id is not None:
        _desactivar_plantillas_activas(db, institucion_id, datos.tipo_documento_id)

    plantilla = models.PlantillaDocumento(
        institucion_id=institucion_id,
        tipo_documento_id=datos.tipo_documento_id,
        nombre=datos.nombre,
        activa=datos.activa,
        fuente=datos.fuente,
        tamano_pt=datos.tamano_pt,
        interlineado=datos.interlineado,
        justificado=datos.justificado,
        titulo_negrita=datos.titulo_negrita,
        titulo_cursiva=datos.titulo_cursiva,
        titulo_tamano_pt=datos.titulo_tamano_pt,
        subtitulo_tamano_pt=datos.subtitulo_tamano_pt,
        mostrar_fondo_institucion=datos.mostrar_fondo_institucion,
        formato_correlativo=datos.formato_correlativo,
        correlativo_reinicia_anualmente=datos.correlativo_reinicia_anualmente,
        generar_automaticamente_al_finalizar_examen=datos.generar_automaticamente_al_finalizar_examen,
        creado_por_usuario_id=usuario_actual.id,
    )
    db.add(plantilla)
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos "crear y activar" simultáneos para el mismo
        # institución+tipo: _desactivar_plantillas_activas de arriba no
        # bloquea la fila, así que dos requests pueden creer ambos que no
        # había ninguna activa que desactivar. El índice único parcial es
        # la garantía real; aquí solo se traduce a un 409 limpio.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya se activó otra plantilla para esta institución y tipo al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(plantilla)
    return plantilla


def clonar_plantilla_documento(
    db: Session, plantilla_origen: models.PlantillaDocumento, institucion_destino_id: int,
    usuario_id: int, nombre: Optional[str] = None, activar: bool = False,
) -> models.PlantillaDocumento:
    """Copia la ESTRUCTURA de una plantilla (secciones, su orden, tipo y
    config) a una institución nueva — nunca el contenido de ningún
    documento ya emitido con la plantilla de origen, que por definición es
    propio de esa otra institución. Pensado para escalar a cientos de
    colegios: la mayoría pide, en esencia, el mismo tipo de informe que otro
    ya tiene configurado, y sin esto cada uno se rearmaba sección por
    sección desde cero.

    `activar=False` por defecto: la institución destino nunca pierde sin
    querer la plantilla que ya tuviera activa para ese mismo tipo solo por
    clonar otra encima."""
    destino = db.query(instituciones_models.Institucion).filter(
        instituciones_models.Institucion.id == institucion_destino_id,
    ).first()
    if not destino:
        raise HTTPException(status_code=404, detail="La institución de destino no existe.")

    if activar:
        _desactivar_plantillas_activas(db, institucion_destino_id, plantilla_origen.tipo_documento_id)

    nueva = models.PlantillaDocumento(
        institucion_id=institucion_destino_id,
        tipo_documento_id=plantilla_origen.tipo_documento_id,
        nombre=nombre or f"{plantilla_origen.nombre} (copia)",
        activa=activar,
        fuente=plantilla_origen.fuente,
        tamano_pt=plantilla_origen.tamano_pt,
        interlineado=plantilla_origen.interlineado,
        justificado=plantilla_origen.justificado,
        titulo_negrita=plantilla_origen.titulo_negrita,
        titulo_cursiva=plantilla_origen.titulo_cursiva,
        titulo_tamano_pt=plantilla_origen.titulo_tamano_pt,
        subtitulo_tamano_pt=plantilla_origen.subtitulo_tamano_pt,
        mostrar_fondo_institucion=plantilla_origen.mostrar_fondo_institucion,
        formato_correlativo=plantilla_origen.formato_correlativo,
        correlativo_reinicia_anualmente=plantilla_origen.correlativo_reinicia_anualmente,
        # ⚠️ generar_automaticamente_al_finalizar_examen deliberadamente NO se
        # copia — mismo precedente que 'activa' quedando en False por
        # defecto en un clon: el enganche automático de un colegio nunca se
        # enciende solo porque clonó una plantilla que lo tenía activado en
        # otro lado (ver test_clonar_plantilla_no_copia_el_enganche, que
        # falla si esta línea vuelve a aparecer aquí).
        creado_por_usuario_id=usuario_id,
    )
    db.add(nueva)
    db.flush()  # necesita nueva.id para poder crear sus secciones

    secciones_origen = db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.plantilla_documento_id == plantilla_origen.id,
    ).order_by(models.PlantillaSeccion.orden).all()
    for seccion in secciones_origen:
        db.add(models.PlantillaSeccion(
            plantilla_documento_id=nueva.id,
            orden=seccion.orden,
            tipo_seccion=seccion.tipo_seccion,
            titulo=seccion.titulo,
            config=seccion.config,
        ))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe (o se activó al mismo tiempo) otra plantilla para esa institución y tipo.",
        )
    db.refresh(nueva)
    return nueva


def actualizar_plantilla_documento(
    db: Session, plantilla: models.PlantillaDocumento, datos: schemas.PlantillaDocumentoUpdate,
) -> models.PlantillaDocumento:
    cambios = datos.model_dump(exclude_unset=True)
    # Mismo criterio que crear_plantilla_documento: una predeterminada
    # global nunca desactiva a otra del mismo tipo.
    if cambios.get("activa") is True and not plantilla.activa and plantilla.institucion_id is not None:
        _desactivar_plantillas_activas(db, plantilla.institucion_id, plantilla.tipo_documento_id)
    for campo, valor in cambios.items():
        setattr(plantilla, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya se activó otra plantilla para esta institución y tipo al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(plantilla)
    return plantilla


def listar_plantillas_de_institucion(db: Session, institucion_id: int) -> List[models.PlantillaDocumento]:
    return db.query(models.PlantillaDocumento).filter(
        models.PlantillaDocumento.institucion_id == institucion_id,
    ).order_by(models.PlantillaDocumento.tipo_documento_id, models.PlantillaDocumento.creado_en.desc()).all()


def obtener_plantilla_documento(db: Session, plantilla_id: int) -> Optional[models.PlantillaDocumento]:
    return db.query(models.PlantillaDocumento).filter(models.PlantillaDocumento.id == plantilla_id).first()


def listar_plantillas_predeterminadas(db: Session) -> List[models.PlantillaDocumento]:
    """Catálogo de plantillas PREDETERMINADAS globales (institucion_id IS
    NULL) — el punto de partida clonable para cualquier colegio. Solo
    activas: una predeterminada desactivada es un borrador/reemplazo de
    AuroraSoft en curso, no algo que ofrecer todavía a los colegios."""
    return db.query(models.PlantillaDocumento).filter(
        models.PlantillaDocumento.institucion_id.is_(None),
        models.PlantillaDocumento.activa == True,  # noqa: E712
    ).order_by(models.PlantillaDocumento.tipo_documento_id, models.PlantillaDocumento.creado_en.desc()).all()


# ==========================================
# PlantillaSeccion
# ==========================================
def crear_plantilla_seccion(
    db: Session, plantilla: models.PlantillaDocumento, datos: schemas.PlantillaSeccionCreate,
) -> models.PlantillaSeccion:
    seccion = models.PlantillaSeccion(
        plantilla_documento_id=plantilla.id,
        orden=datos.orden,
        tipo_seccion=datos.tipo_seccion,
        titulo=datos.titulo,
        config=datos.config,
    )
    db.add(seccion)
    db.commit()
    db.refresh(seccion)
    return seccion


def listar_secciones_de_plantilla(db: Session, plantilla_id: int) -> List[models.PlantillaSeccion]:
    return db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.plantilla_documento_id == plantilla_id,
    ).order_by(models.PlantillaSeccion.orden).all()


def obtener_plantilla_seccion(db: Session, seccion_id: int) -> Optional[models.PlantillaSeccion]:
    return db.query(models.PlantillaSeccion).filter(models.PlantillaSeccion.id == seccion_id).first()


def actualizar_plantilla_seccion(
    db: Session, seccion: models.PlantillaSeccion, datos: schemas.PlantillaSeccionUpdate,
) -> models.PlantillaSeccion:
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(seccion, campo, valor)
    db.commit()
    db.refresh(seccion)
    return seccion


def eliminar_plantilla_seccion(db: Session, seccion: models.PlantillaSeccion) -> None:
    """Borra una sección de una plantilla EN BORRADOR (el constructor la usa
    para corregir el orden/composición antes de la primera versión). Si ya
    existe contenido de borrador o un resultado de prueba vinculado a esta
    sección en algún DocumentoInstitucional, la FK lo bloquea — se traduce
    a un 409 explícito en vez de un 500 crudo, mismo criterio que el resto
    de este módulo usa para toda escritura con constraint único detrás."""
    try:
        db.delete(seccion)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta sección ya tiene contenido o un resultado de prueba vinculado en algún documento "
                   "y no se puede eliminar. Edítala en su lugar, o elimina primero ese contenido.",
        )


# ==========================================
# DocumentoInstitucional — creación (Paso 3). Ver
# schemas.DocumentoInstitucionalCreate para las reglas de alcance/estructura.
# ==========================================
def _resolver_personas_de_nodo(
    db: Session, institucion_id: int, nodo: schemas.NodoEstructuraSeleccion, anio_escolar: Optional[int],
) -> List[superadmin_models.Persona]:
    """Estudiantes con matrícula VIGENTE bajo el nodo dado — re-valida que
    el nodo (Sección/Grado/NivelEducativo) pertenece a `institucion_id`
    desde la BD antes de resolver nada, nunca confía en que el id mandado
    por el cliente ya es de esta institución (mismo criterio que
    `matricular_persona_en_seccion`)."""
    if nodo.seccion_id is not None:
        seccion = db.query(superadmin_models.Seccion).filter(superadmin_models.Seccion.id == nodo.seccion_id).first()
        if not seccion or seccion.institucion_id != institucion_id:
            raise HTTPException(status_code=404, detail=f"La sección {nodo.seccion_id} no existe en esta institución.")
        filtro_extra = [superadmin_models.Seccion.id == seccion.id]
    else:
        if anio_escolar is None:
            raise HTTPException(
                status_code=422,
                detail="anio_escolar es obligatorio para resolver un nodo de grado o nivel educativo.",
            )
        if nodo.grado_id is not None:
            grado = db.query(superadmin_models.Grado).filter(superadmin_models.Grado.id == nodo.grado_id).first()
            if not grado or grado.institucion_id != institucion_id:
                raise HTTPException(status_code=404, detail=f"El grado {nodo.grado_id} no existe en esta institución.")
            filtro_extra = [superadmin_models.Grado.id == grado.id, superadmin_models.Seccion.anio_escolar == anio_escolar]
        else:
            nivel = db.query(superadmin_models.NivelEducativo).filter(
                superadmin_models.NivelEducativo.id == nodo.nivel_educativo_id,
            ).first()
            if not nivel or nivel.institucion_id != institucion_id:
                raise HTTPException(status_code=404, detail=f"El nivel educativo {nodo.nivel_educativo_id} no existe en esta institución.")
            filtro_extra = [
                superadmin_models.NivelEducativo.id == nivel.id,
                superadmin_models.Seccion.anio_escolar == anio_escolar,
            ]

    return (
        db.query(superadmin_models.Persona)
        .join(superadmin_models.MatriculaAcademica, superadmin_models.MatriculaAcademica.persona_id == superadmin_models.Persona.id)
        .join(superadmin_models.Seccion, superadmin_models.Seccion.id == superadmin_models.MatriculaAcademica.seccion_id)
        .join(superadmin_models.Grado, superadmin_models.Grado.id == superadmin_models.Seccion.grado_id)
        .join(superadmin_models.NivelEducativo, superadmin_models.NivelEducativo.id == superadmin_models.Grado.nivel_educativo_id)
        .filter(
            superadmin_models.MatriculaAcademica.institucion_id == institucion_id,
            superadmin_models.MatriculaAcademica.fecha_fin.is_(None),
            *filtro_extra,
        )
        .all()
    )


def crear_documento_institucional(
    db: Session, usuario_actual, datos: schemas.DocumentoInstitucionalCreate, commit: bool = True,
) -> models.DocumentoInstitucional:
    tipo = db.query(models.TipoDocumento).filter(models.TipoDocumento.id == datos.tipo_documento_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de documento no encontrado.")

    plantilla = db.query(models.PlantillaDocumento).filter(models.PlantillaDocumento.id == datos.plantilla_documento_id).first()
    if not plantilla:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    if plantilla.tipo_documento_id != tipo.id:
        raise HTTPException(status_code=422, detail="La plantilla elegida no pertenece a ese tipo de documento.")
    if not plantilla.activa:
        raise HTTPException(status_code=409, detail="Esa plantilla no está activa; actívala o elige otra antes de crear el documento.")

    # 🔒 institucion_id se DERIVA de la plantilla — nunca se acepta como
    # campo del request (ver schemas.DocumentoInstitucionalCreate).
    institucion_id = plantilla.institucion_id
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes crear documentos para otra institución.")

    if datos.alcance not in _parsear_lista_csv(tipo.alcances_permitidos):
        raise HTTPException(status_code=422, detail=f"El tipo '{tipo.nombre}' no admite alcance='{datos.alcance}'.")
    if datos.nivel_visibilidad not in _parsear_lista_csv(tipo.visibilidades_permitidas):
        raise HTTPException(status_code=422, detail=f"El tipo '{tipo.nombre}' no admite nivel_visibilidad='{datos.nivel_visibilidad}'.")

    documento = models.DocumentoInstitucional(
        institucion_id=institucion_id,
        tipo_documento_id=tipo.id,
        plantilla_documento_id=plantilla.id,
        alcance=datos.alcance,
        nivel_visibilidad=datos.nivel_visibilidad,
        titulo=datos.titulo,
        version_actual=None,  # borrador -- nace sin versión, a diferencia de Informe
        creado_por_usuario_id=usuario_actual.id,
    )
    db.add(documento)
    db.flush()  # necesita documento.id para las filas hijas

    # Consentimiento NO se valida aquí — deliberado (ver Paso 5): esto es
    # solo la identidad + la lista congelada, no un uso definitivo de datos.

    personas_por_id: dict = {}
    incluido_via_por_id: dict = {}

    for nodo in datos.estructura:
        for persona in _resolver_personas_de_nodo(db, institucion_id, nodo, datos.anio_escolar):
            personas_por_id.setdefault(persona.id, persona)
            incluido_via_por_id.setdefault(persona.id, "seccion")
        # Auditoría del criterio usado — siempre se registra, incluso si el
        # nodo no resolvió a ningún estudiante todavía (ej. sección recién
        # creada sin matrículas aún).
        db.add(models.DocumentoInstitucionalEstructura(
            documento_institucional_id=documento.id,
            institucion_id=institucion_id,
            nivel_educativo_id=nodo.nivel_educativo_id,
            grado_id=nodo.grado_id,
            seccion_id=nodo.seccion_id,
        ))

    for persona_id in datos.personas_ids:
        persona = personas_por_id.get(persona_id)
        if persona is None:
            persona = db.query(superadmin_models.Persona).filter(superadmin_models.Persona.id == persona_id).first()
            if not persona or persona.institucion_id != institucion_id:
                raise HTTPException(status_code=404, detail=f"La persona {persona_id} no existe en esta institución.")
            personas_por_id[persona_id] = persona
        incluido_via_por_id.setdefault(persona_id, "manual")

    for persona_id, persona in personas_por_id.items():
        matricula = superadmin_crud.obtener_matricula_activa(db=db, persona_id=persona_id)
        seccion_id_historico = None
        grado_seccion_historico = None
        if matricula:
            info = superadmin_crud._describir_matricula(db=db, matricula=matricula)
            seccion_id_historico = info["seccion_id"]
            if info["grado"] or info["seccion"]:
                grado_seccion_historico = f'{info["grado"] or ""} {info["seccion"] or ""}'.strip() or None
        db.add(models.DocumentoInstitucionalEstudiante(
            documento_institucional_id=documento.id,
            institucion_id=institucion_id,
            persona_id=persona_id,
            incluido_via=incluido_via_por_id[persona_id],
            nombre_completo_historico=f"{persona.nombres} {persona.apellidos}",
            seccion_id_historico=seccion_id_historico,
            grado_seccion_historico=grado_seccion_historico,
        ))

    if not commit:
        # El llamador (p. ej. _generar_documento_automatico_de_plantilla)
        # controla su propia transacción — ver el parámetro `commit` en su
        # docstring. flush() asigna documento.id sin confirmar nada todavía.
        db.flush()
        return documento
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo crear el documento (conflicto al guardar). Vuelve a intentarlo.",
        )
    db.refresh(documento)
    return documento


def obtener_documento_institucional(db: Session, documento_id: int) -> Optional[models.DocumentoInstitucional]:
    return db.query(models.DocumentoInstitucional).filter(models.DocumentoInstitucional.id == documento_id).first()


def listar_estudiantes_de_documento(db: Session, documento_id: int) -> List[models.DocumentoInstitucionalEstudiante]:
    return db.query(models.DocumentoInstitucionalEstudiante).filter(
        models.DocumentoInstitucionalEstudiante.documento_institucional_id == documento_id,
    ).order_by(models.DocumentoInstitucionalEstudiante.nombre_completo_historico).all()


def listar_documentos_de_institucion(
    db: Session, institucion_id: int, skip: int = 0, limit: int = 50,
) -> tuple[int, List[models.DocumentoInstitucional]]:
    query = db.query(models.DocumentoInstitucional).filter(
        models.DocumentoInstitucional.institucion_id == institucion_id,
    )
    total = query.count()
    items = query.order_by(models.DocumentoInstitucional.creado_en.desc()).offset(skip).limit(limit).all()
    return total, items


def listar_documentos_visibles_para_usuario(
    db: Session, institucion_id: int, usuario_actual, persona_id: Optional[int] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[int, List[models.DocumentoInstitucional]]:
    """Mismo listado que `listar_documentos_de_institucion`, pero acotado
    por `nivel_visibilidad` cuando quien pregunta es 'colegio' — mismo
    criterio de acceso que `usuario_puede_ver_documento` (Paso 6), aplicado
    a un listado en vez de a un documento suelto: 'colegio' NO queda
    bloqueado del listado entero, solo deja de ver las filas
    'confidencial_clinico'.

    🆕 `persona_id` (opcional) acota a los documentos que incluyen a ESE
    estudiante en su lista congelada (join con `DocumentoInstitucionalEstudiante`)
    — pensado para la ficha del alumno, que necesita "los documentos de
    este estudiante" sin cargar los de toda la institución y filtrar en el
    cliente. `None` (el default) preserva exactamente el comportamiento
    anterior.

    🆕 Paginación real (docs/gaps-pendientes.md) — antes devolvía todo
    documento generado, sin tope, para siempre. El `COUNT`/`LIMIT` se aplica
    DESPUÉS del filtro de `nivel_visibilidad`/`persona_id`, no antes, para
    que `total` refleje lo que el rol 'colegio' realmente puede ver."""
    query = db.query(models.DocumentoInstitucional).filter(
        models.DocumentoInstitucional.institucion_id == institucion_id,
    )
    if usuario_actual.rol == "colegio":
        query = query.filter(models.DocumentoInstitucional.nivel_visibilidad == "compartible_colegio")
    if persona_id is not None:
        query = query.join(
            models.DocumentoInstitucionalEstudiante,
            models.DocumentoInstitucionalEstudiante.documento_institucional_id == models.DocumentoInstitucional.id,
        ).filter(models.DocumentoInstitucionalEstudiante.persona_id == persona_id)
    total = query.count()
    items = query.order_by(models.DocumentoInstitucional.creado_en.desc()).offset(skip).limit(limit).all()
    return total, items


# ==========================================
# DocumentoInstitucionalSeccionContenido — borrador editable (Paso 4).
# ==========================================
def _fila_contenido_a_dict(
    seccion: models.PlantillaSeccion, fila: Optional[models.DocumentoInstitucionalSeccionContenido],
) -> dict:
    return {
        "plantilla_seccion_id": seccion.id,
        "tipo_seccion": seccion.tipo_seccion,
        "titulo": seccion.titulo,
        "orden": seccion.orden,
        "contenido": fila.contenido if fila else None,
        "editado_por_usuario_id": fila.editado_por_usuario_id if fila else None,
        "actualizado_en": fila.actualizado_en if fila else None,
    }


def obtener_contenido_secciones(db: Session, documento: models.DocumentoInstitucional) -> List[dict]:
    """Una fila por CADA `PlantillaSeccion` de la plantilla del documento,
    con su contenido actual si existe o un placeholder vacío si la sección
    todavía no se tocó — nunca 404 por una sección sin editar todavía."""
    secciones = db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.plantilla_documento_id == documento.plantilla_documento_id,
    ).order_by(models.PlantillaSeccion.orden).all()
    contenidos = {
        c.plantilla_seccion_id: c
        for c in db.query(models.DocumentoInstitucionalSeccionContenido).filter(
            models.DocumentoInstitucionalSeccionContenido.documento_institucional_id == documento.id,
        ).all()
    }
    return [_fila_contenido_a_dict(seccion, contenidos.get(seccion.id)) for seccion in secciones]


def obtener_plantilla_seccion_de_documento(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int,
) -> models.PlantillaSeccion:
    """🔒 Re-valida que la sección pertenece a la PLANTILLA DE ESTE
    DOCUMENTO — nunca se acepta un plantilla_seccion_id de otra plantilla
    (que podría ser de otra institución) solo porque el cliente lo mandó
    junto al documento correcto. Variante de la regla 6 que se aplica a
    nivel de sub-recurso, no solo de institución."""
    seccion = db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.id == plantilla_seccion_id,
        models.PlantillaSeccion.plantilla_documento_id == documento.plantilla_documento_id,
    ).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Esa sección no pertenece a la plantilla de este documento.")
    return seccion


def actualizar_contenido_seccion(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int,
    usuario_id: int, datos: schemas.DocumentoInstitucionalSeccionContenidoUpdate,
) -> dict:
    """Upsert (get-or-create) sobre el índice único
    (documento_institucional_id, plantilla_seccion_id). PUT de reemplazo
    total del campo `contenido` — no un merge parcial: el editor de
    sección manda siempre el estado completo de su propio bloque.

    Deliberadamente editable AUNQUE el documento ya tenga `version_actual`
    (ya se emitió al menos una vez): esto es justamente cómo se prepara el
    contenido de la SIGUIENTE reemisión — la versión ya emitida vive en su
    propio `contenido_snapshot` congelado y nunca se entera de ediciones
    posteriores aquí (Paso 5)."""
    seccion = obtener_plantilla_seccion_de_documento(db, documento, plantilla_seccion_id)

    fila = db.query(models.DocumentoInstitucionalSeccionContenido).filter(
        models.DocumentoInstitucionalSeccionContenido.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalSeccionContenido.plantilla_seccion_id == plantilla_seccion_id,
    ).first()
    if not fila:
        fila = models.DocumentoInstitucionalSeccionContenido(
            documento_institucional_id=documento.id, plantilla_seccion_id=plantilla_seccion_id,
        )
        db.add(fila)
    fila.contenido = datos.contenido
    fila.editado_por_usuario_id = usuario_id
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos guardados simultáneos de la MISMA sección (dos
        # pestañas, o dos personas editando el mismo borrador a la vez).
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta sección se guardó desde otra pestaña o sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return _fila_contenido_a_dict(seccion, fila)


EXTENSIONES_IMAGEN_SECCION_PERMITIDAS = {".jpg", ".jpeg", ".png"}
TAMANO_MAXIMO_IMAGEN_SECCION_BYTES = 8 * 1024 * 1024  # 8 MB — de sobra para una foto/escaneo


def _extension_imagen_segura(nombre_archivo: str) -> str:
    """Mismo criterio que `_extension_segura` en modulos/superadmin/crud.py
    (evidencia de consentimiento): nunca se usa el nombre del cliente tal
    cual, solo se rescata la extensión y solo si está en la lista blanca."""
    import os as _os
    extension = _os.path.splitext(nombre_archivo or "")[1].lower()
    if extension not in EXTENSIONES_IMAGEN_SECCION_PERMITIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Extensión de imagen no permitida. "
                f"Usa una de: {', '.join(sorted(EXTENSIONES_IMAGEN_SECCION_PERMITIDAS))}."
            ),
        )
    return extension


def guardar_imagen_seccion(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int,
    contenido: bytes, nombre_archivo: str, usuario_id: int,
) -> dict:
    """Sube una imagen (dibujo, foto de una prueba gráfica/proyectiva)
    directamente a una sección `imagen_anexo` — ver docstring de
    `PlantillaSeccion.config` en models.py. A diferencia de
    `actualizar_contenido_seccion` (JSON puro), esto recibe bytes reales y
    los guarda en `core/storage/` antes de escribir la referencia; cada
    subida obtiene una key ÚNICA (nunca sobrescribe la anterior), para que
    una `DocumentoInstitucionalVersion` ya emitida con la imagen vieja
    nunca pierda sus bytes si se sube una nueva antes de la siguiente
    versión."""
    seccion = obtener_plantilla_seccion_de_documento(db, documento, plantilla_seccion_id)
    if seccion.tipo_seccion != "imagen_anexo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esa sección no es de tipo 'imagen_anexo'.",
        )
    if len(contenido) > TAMANO_MAXIMO_IMAGEN_SECCION_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La imagen supera el tamaño máximo permitido ({TAMANO_MAXIMO_IMAGEN_SECCION_BYTES // (1024*1024)} MB).",
        )
    extension = _extension_imagen_segura(nombre_archivo)

    from core.storage import obtener_storage_service, construir_storage_key_imagen_seccion_documento
    import uuid
    token = uuid.uuid4().hex
    key = construir_storage_key_imagen_seccion_documento(
        documento.institucion_id, documento.id, plantilla_seccion_id, token, extension,
    )
    content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}[extension]
    obtener_storage_service().guardar(key, contenido, content_type)

    fila = db.query(models.DocumentoInstitucionalSeccionContenido).filter(
        models.DocumentoInstitucionalSeccionContenido.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalSeccionContenido.plantilla_seccion_id == plantilla_seccion_id,
    ).first()
    if not fila:
        fila = models.DocumentoInstitucionalSeccionContenido(
            documento_institucional_id=documento.id, plantilla_seccion_id=plantilla_seccion_id,
        )
        db.add(fila)
    fila.contenido = {
        "storage_key": key,
        "nombre_archivo": nombre_archivo,
        "descripcion": (fila.contenido or {}).get("descripcion") if fila.contenido else None,
    }
    fila.editado_por_usuario_id = usuario_id
    try:
        db.commit()
    except IntegrityError:
        # 🔒 Mismo get-or-create sobre el mismo índice único
        # (uq_documentos_seccion_contenido_unica) que actualizar_contenido_
        # seccion ya protege — hallazgo real de la auditoría de convención de
        # concurrencia (test_patron_concurrencia_unitario.py, sesión
        # 2026-10-15): esta función duplicaba el mismo patrón get-or-create
        # sin copiar la protección, así que dos subidas simultáneas a la
        # misma sección (doble clic, o un reintento de red) podían competir
        # por crear la fila y la segunda reventaba con un IntegrityError 500
        # crudo en vez de un 409 limpio.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta sección se guardó desde otra pestaña o sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return _fila_contenido_a_dict(seccion, fila)


# ==========================================
# DocumentoInstitucionalResultadoPrueba — el enlace que le dice a una
# sección 'resultados_prueba' A QUÉ aplicación real (Inscripcion) referirse.
# Hasta ahora la única forma de poblar esta tabla era un INSERT directo en
# la BD (ver CLAUDE.md, "no hay endpoint público para escribir
# DocumentoInstitucionalResultadoPrueba") — un psicólogo no podía armar esto
# desde la API. Sigue el mismo criterio de "nunca confíes en un id del
# cliente sin re-validarlo contra la BD" que el resto del módulo.
# ==========================================
def vincular_resultado_prueba(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int,
    persona_id: int, inscripcion_id: int, commit: bool = True,
) -> models.DocumentoInstitucionalResultadoPrueba:
    """Upsert sobre el índice único (documento, sección, estudiante) —
    volver a vincular reemplaza a qué Inscripcion apunta, útil para
    corregir un enlace antes de generar la versión (el contenido de un
    documento en borrador siempre es editable, igual que
    `actualizar_contenido_seccion`)."""
    seccion = obtener_plantilla_seccion_de_documento(db, documento, plantilla_seccion_id)
    # 🆕 'grafico_barras' reusa este mismo vínculo (ver
    # crud._resolver_grafico_barras) — ambos tipos solo necesitan "a qué
    # Inscripcion real apunta esta sección, para esta persona", nunca su
    # propia tabla.
    if seccion.tipo_seccion not in ("resultados_prueba", "grafico_barras"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esa sección no es de tipo 'resultados_prueba' ni 'grafico_barras'.",
        )

    # 🔒 El estudiante debe pertenecer a la lista CONGELADA de este
    # documento — nunca se vincula un resultado de alguien ajeno a él.
    en_lista = db.query(models.DocumentoInstitucionalEstudiante).filter(
        models.DocumentoInstitucionalEstudiante.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalEstudiante.persona_id == persona_id,
    ).first()
    if not en_lista:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese estudiante no forma parte de la lista de este documento.",
        )

    # 🔒 La inscripción debe ser realmente de esa persona Y de una
    # evaluación de la MISMA institución que el documento — re-validado
    # desde la BD, nunca aceptado porque el cliente mandó ambos ids juntos.
    inscripcion = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.id == inscripcion_id,
        educativo_models.Inscripcion.persona_id == persona_id,
    ).first()
    if not inscripcion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Esa inscripción no existe o no pertenece a ese estudiante.",
        )
    evaluacion = db.query(educativo_models.Evaluacion).filter(
        educativo_models.Evaluacion.id == inscripcion.evaluacion_id,
    ).first()
    if not evaluacion or evaluacion.institucion_id != documento.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esa inscripción no pertenece a la institución de este documento.",
        )

    existente = db.query(models.DocumentoInstitucionalResultadoPrueba).filter(
        models.DocumentoInstitucionalResultadoPrueba.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalResultadoPrueba.plantilla_seccion_id == plantilla_seccion_id,
        models.DocumentoInstitucionalResultadoPrueba.persona_id == persona_id,
    ).first()
    if existente:
        existente.inscripcion_id = inscripcion_id
        if not commit:
            db.flush()
            return existente
        db.commit()
        db.refresh(existente)
        return existente

    nuevo = models.DocumentoInstitucionalResultadoPrueba(
        documento_institucional_id=documento.id,
        plantilla_seccion_id=plantilla_seccion_id,
        institucion_id=documento.institucion_id,
        persona_id=persona_id,
        inscripcion_id=inscripcion_id,
    )
    db.add(nuevo)
    if not commit:
        # Mismo motivo que en crear_documento_institucional: el llamador
        # (_generar_documento_automatico_de_plantilla) controla la
        # transacción completa, para que un fallo más adelante (p. ej. en
        # generar_version_documento) deshaga también este vínculo.
        db.flush()
        return nuevo
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos vinculaciones simultáneas de la misma sección
        # para el mismo estudiante.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese vínculo ya fue creado por otra solicitud al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(nuevo)
    return nuevo


def desvincular_resultado_prueba(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int, persona_id: int,
) -> None:
    fila = db.query(models.DocumentoInstitucionalResultadoPrueba).filter(
        models.DocumentoInstitucionalResultadoPrueba.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalResultadoPrueba.plantilla_seccion_id == plantilla_seccion_id,
        models.DocumentoInstitucionalResultadoPrueba.persona_id == persona_id,
    ).first()
    if not fila:
        raise HTTPException(status_code=404, detail="No existe ese vínculo.")
    db.delete(fila)
    db.commit()


def vincular_resultados_prueba_multiple(
    db: Session, documento: models.DocumentoInstitucional, plantilla_seccion_id: int,
    usuario_id: int, persona_id: int, inscripcion_ids: List[int],
) -> dict:
    """Reemplaza TODO el conjunto de `Inscripcion` que una sección
    'resultados_prueba_multiple' consolida para esta persona — PUT de
    reemplazo total, igual criterio que `actualizar_contenido_seccion`,
    nunca un merge con lo que ya hubiera vinculado.

    A diferencia de `resultados_prueba`/`grafico_barras` (UN solo vínculo
    por sección, en su propia tabla `DocumentoInstitucionalResultadoPrueba`
    — ver `vincular_resultado_prueba`), esta sección existe justamente para
    una cantidad VARIABLE de pruebas por alumno, nunca fija por plantilla:
    el motor no tiene (ni necesita) una tabla de vínculo N-a-N propia, la
    lista de ids vive directamente en
    `DocumentoInstitucionalSeccionContenido.contenido` — mismo mecanismo
    que ya usan `texto_libre`/`grupo_campos`/`tabla_dinamica`.

    🔒 A diferencia de esos tres (texto libre, sin ninguna referencia a
    otra tabla), esta sección SÍ referencia filas reales (`Inscripcion`) —
    por eso, aunque el contenido vive en la misma tabla JSON genérica, el
    guardado pasa por ESTE endpoint dedicado, nunca por el PUT genérico de
    contenido de sección: cada id se re-valida tan estricto como
    `vincular_resultado_prueba` (persona Y misma institución del
    documento) ANTES de guardar nada — si cualquiera falla, se rechaza la
    lista completa, nunca se guardan unos sí y otros no en silencio.
    `crud.construir_contenido_documento` vuelve a re-validar cada id al
    generar el PDF (nunca confía en que lo guardado siga siendo válido
    para siempre — una Inscripcion podría anonimizarse por ARCO después)."""
    seccion = obtener_plantilla_seccion_de_documento(db, documento, plantilla_seccion_id)
    if seccion.tipo_seccion != "resultados_prueba_multiple":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esa sección no es de tipo 'resultados_prueba_multiple'.",
        )

    en_lista = db.query(models.DocumentoInstitucionalEstudiante).filter(
        models.DocumentoInstitucionalEstudiante.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalEstudiante.persona_id == persona_id,
    ).first()
    if not en_lista:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ese estudiante no forma parte de la lista de este documento.",
        )

    ids_unicos = list(dict.fromkeys(inscripcion_ids))  # preserva el orden elegido, sin duplicados
    for inscripcion_id in ids_unicos:
        inscripcion = db.query(educativo_models.Inscripcion).filter(
            educativo_models.Inscripcion.id == inscripcion_id,
            educativo_models.Inscripcion.persona_id == persona_id,
        ).first()
        if not inscripcion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La inscripción {inscripcion_id} no existe o no pertenece a ese estudiante.",
            )
        evaluacion = db.query(educativo_models.Evaluacion).filter(
            educativo_models.Evaluacion.id == inscripcion.evaluacion_id,
        ).first()
        if not evaluacion or evaluacion.institucion_id != documento.institucion_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"La inscripción {inscripcion_id} no pertenece a la institución de este documento.",
            )

    fila = db.query(models.DocumentoInstitucionalSeccionContenido).filter(
        models.DocumentoInstitucionalSeccionContenido.documento_institucional_id == documento.id,
        models.DocumentoInstitucionalSeccionContenido.plantilla_seccion_id == plantilla_seccion_id,
    ).first()
    if not fila:
        fila = models.DocumentoInstitucionalSeccionContenido(
            documento_institucional_id=documento.id, plantilla_seccion_id=plantilla_seccion_id,
        )
        db.add(fila)
    fila.contenido = {"inscripcion_ids": ids_unicos}
    fila.editado_por_usuario_id = usuario_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta sección se guardó desde otra pestaña o sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return _fila_contenido_a_dict(seccion, fila)


# ==========================================
# Paso 5 — Generar una versión. El paso de mayor riesgo del feature: lock
# de correlativo + lock del documento (mismo bug de identity-map que
# finalizar_examen_seguro, ver CLAUDE.md), gate de consentimiento en CADA
# llamada (v1 y cada reemisión), ensamblado de contenido, PDF, storage, y
# creación de las entradas-puente del expediente — todo en una sola
# transacción con un único commit al final.
# ==========================================
def bloquear_documento_institucional_para_version(db: Session, documento_id: int) -> Optional[models.DocumentoInstitucional]:
    """Mismo shape exacto que `crud.bloquear_inscripcion_para_finalizar` en
    modulos/educativo/crud.py: `.with_for_update().populate_existing()`
    para leer `version_actual` FRESCO bajo lock, nunca el objeto que el
    identity map de la sesión pudiera tener cacheado de una consulta
    anterior sin lock."""
    return db.query(models.DocumentoInstitucional).filter(
        models.DocumentoInstitucional.id == documento_id,
    ).with_for_update().populate_existing().first()


def bloquear_correlativo_para_emision(db: Session, institucion_id: int, tipo_documento_id: int, anio: int) -> models.CorrelativoDocumento:
    """Get-or-create con lock: dos emisiones simultáneas del mismo
    institución+tipo(+año) nunca deben recibir el mismo número —
    `CorrelativoDocumento` no tiene ninguna unicidad sobre el NÚMERO en sí
    (solo sobre institución+tipo+año), así que un lock roto ni siquiera
    lanzaría error: imprimiría el mismo correlativo en dos documentos
    reales. `anio=0` es el centinela de "no reinicia anualmente" (ver el
    modelo — Postgres trata los NULL de un UNIQUE como distintos entre sí,
    así que NULL no serviría para este propósito)."""
    fila = db.query(models.CorrelativoDocumento).filter(
        models.CorrelativoDocumento.institucion_id == institucion_id,
        models.CorrelativoDocumento.tipo_documento_id == tipo_documento_id,
        models.CorrelativoDocumento.anio == anio,
    ).with_for_update().first()
    if fila is not None:
        return fila

    # No existe todavía. Si dos transacciones concurrentes llegan aquí a la
    # vez, ambas ven "no existe" y ambas intentan crearla: se usa un
    # SAVEPOINT propio (begin_nested) para que la que pierde la carrera
    # pueda recuperarse sin tumbar la transacción completa, y vuelve a
    # consultar CON LOCK — en ese punto la fila ya existe (la creó la otra)
    # y el lock la espera hasta que esa otra transacción libere el suyo.
    nested = db.begin_nested()
    try:
        nueva = models.CorrelativoDocumento(
            institucion_id=institucion_id, tipo_documento_id=tipo_documento_id, anio=anio, ultimo_numero=0,
        )
        db.add(nueva)
        nested.commit()
        return nueva
    except IntegrityError:
        nested.rollback()
        return db.query(models.CorrelativoDocumento).filter(
            models.CorrelativoDocumento.institucion_id == institucion_id,
            models.CorrelativoDocumento.tipo_documento_id == tipo_documento_id,
            models.CorrelativoDocumento.anio == anio,
        ).with_for_update().first()


def _resolver_datos_filiacion(db: Session, estudiantes: List[models.DocumentoInstitucionalEstudiante], contenido_seccion: Optional[dict]) -> dict:
    """Solo tiene sentido para un documento de UN estudiante — un documento
    grupal/institucional no tiene "el" estudiante al que referirse. Nunca
    se adivina cuál mostrar cuando hay 0 o más de 1: se declara
    explícitamente que la sección no aplica, en vez de mostrar datos de la
    persona equivocada."""
    if len(estudiantes) != 1:
        return {"aplica": False}
    est = estudiantes[0]
    persona = db.query(superadmin_models.Persona).filter(superadmin_models.Persona.id == est.persona_id).first()
    contenido_seccion = contenido_seccion or {}
    return {
        "aplica": True,
        "nombre_completo": est.nombre_completo_historico,
        "sexo": persona.genero if persona else None,
        "fecha_nacimiento": persona.fecha_nacimiento.date().isoformat() if persona and persona.fecha_nacimiento else None,
        "documento_identidad": persona.documento_identidad if persona else None,
        "grado_seccion": est.grado_seccion_historico,
        # 🆕 4 campos propios de ESTE documento, nunca de la ficha del
        # estudiante (a diferencia de todo lo de arriba) — mismo criterio
        # que diagnostico_presuntivo: se llenan a mano por documento vía
        # PUT /{documento_id}/secciones/{plantilla_seccion_id}, sin tocar
        # Persona ni ninguna otra tabla. "Hijos"/"Examinadora"/las fechas de
        # evaluación son datos de ESTE informe en particular (ej. "Hijos" en
        # un informe escolar real pregunta por los hijos del estudiante
        # menor de edad, casi siempre "Ninguno" — nunca un hecho reusable
        # del núcleo del estudiante).
        "hijos": contenido_seccion.get("hijos"),
        "examinadora": contenido_seccion.get("examinadora"),
        "fecha_elaboracion": contenido_seccion.get("fecha_elaboracion"),
        "periodo_propuesto": contenido_seccion.get("periodo_propuesto"),
        # Único campo profesional "clínico" de esta sección -- lo demás
        # (arriba) es automático de la ficha del estudiante.
        "diagnostico_presuntivo": contenido_seccion.get("diagnostico_presuntivo"),
    }


def _resolver_datos_familiares(db: Session, estudiantes: List[models.DocumentoInstitucionalEstudiante]) -> dict:
    """Mismo criterio de 'un solo estudiante' que _resolver_datos_filiacion.
    Combina PersonaDatosFamiliares (composición del hogar) y
    PersonaAntecedentesClinicos (terapia/psiquiatría externa, diagnóstico
    reportado) en un solo bloque -- ambos son ficha del estudiante, ambos
    reutilizables, mismo tratamiento en el PDF."""
    if len(estudiantes) != 1:
        return {"aplica": False}
    persona_id = estudiantes[0].persona_id
    familiares = superadmin_crud.obtener_datos_familiares(db, persona_id)
    antecedentes = superadmin_crud.obtener_antecedentes_clinicos(db, persona_id)
    return {
        "aplica": True,
        "numero_hermanos": familiares.numero_hermanos if familiares else None,
        "vive_con": familiares.vive_con if familiares else None,
        "lugar_nacimiento": familiares.lugar_nacimiento if familiares else None,
        "lugar_procedencia": familiares.lugar_procedencia if familiares else None,
        "recibe_terapia_psicologica_externa": antecedentes.recibe_terapia_psicologica_externa if antecedentes else None,
        "detalle_terapia_psicologica_externa": antecedentes.detalle_terapia_psicologica_externa if antecedentes else None,
        "recibe_atencion_psiquiatrica_externa": antecedentes.recibe_atencion_psiquiatrica_externa if antecedentes else None,
        "detalle_atencion_psiquiatrica_externa": antecedentes.detalle_atencion_psiquiatrica_externa if antecedentes else None,
        "diagnostico_reportado": antecedentes.diagnostico_reportado if antecedentes else None,
    }


def _resolver_resultados_prueba(db: Session, documento_id: int, plantilla_seccion_id: int, estudiantes: List[models.DocumentoInstitucionalEstudiante]) -> dict:
    """Lee `DocumentoInstitucionalResultadoPrueba` para (documento, ESTA
    sección, el único estudiante) -- si el documento tiene 0 o más de 1
    estudiante, o nadie vinculó una aplicación real a esta sección
    todavía, la sección declara explícitamente que no aplica en vez de
    mostrar datos de otra aplicación o inventar un resultado.

    🔒 Hallazgo B (ver CLAUDE.md, "Motor de documentos institucionales"):
    si la `Inscripcion` vinculada todavía está retenida para revisión
    profesional (`informe_liberado=False`), la sección NUNCA imprime el
    puntaje/nivel/interpretación real -- mismo criterio de fondo que
    `modulos.educativo.crud.verificar_puede_ver_informe` (que ya protege el
    acceso directo a un informe puntual). A diferencia de ese endpoint, el
    contenido de una `DocumentoInstitucionalVersion` queda CONGELADO en el
    momento de generarla y nunca se re-evalúa por lector después, así que
    esta decisión debe tomarse aquí, una sola vez, de forma conservadora
    (independiente de a quién termine siendo visible el documento) — nunca
    "omitida" silenciosamente como antes de este fix, que dejaba pasar el
    resultado real sin comprobar `informe_liberado`.

    🆕 Decisión de alcance (sesión 2026-10-17, ver docs/gaps-pendientes.md
    y docs/motor-documentos.md "Hallazgo abierto... resuelto"): este motor
    ya NO exige además `resultado_visible_alumno=True`. Ese segundo booleano
    responde "¿el ALUMNO, específicamente, puede ver esto en su propio
    portal?" (`GET /examen/{token}/estado-resultados`) -- una pregunta sin
    sentido para la mayoría de los documentos institucionales (un plan de
    intervención, una ficha de derivación externa), que nunca van dirigidos
    al alumno y son precisamente las herramientas que el equipo clínico
    necesita usar MIENTRAS un caso de riesgo sigue retenido para la
    familia. `informe_liberado` (un profesional ya revisó y liberó este
    resultado) es la condición que de verdad protege a este motor; seguir
    exigiendo también `resultado_visible_alumno` solo bloqueaba sin razón
    real los casos que más necesitan estos documentos de trabajo interno."""
    if len(estudiantes) != 1:
        return {"aplica": False}
    persona_id = estudiantes[0].persona_id
    referencia = db.query(models.DocumentoInstitucionalResultadoPrueba).filter(
        models.DocumentoInstitucionalResultadoPrueba.documento_institucional_id == documento_id,
        models.DocumentoInstitucionalResultadoPrueba.plantilla_seccion_id == plantilla_seccion_id,
        models.DocumentoInstitucionalResultadoPrueba.persona_id == persona_id,
    ).first()
    if not referencia:
        return {"aplica": False}
    resultado = _resolver_un_resultado_de_inscripcion(db, referencia.inscripcion_id)
    if resultado is None:
        return {"aplica": False}
    return {"aplica": True, **resultado}


def _resolver_un_resultado_de_inscripcion(db: Session, inscripcion_id: int) -> Optional[dict]:
    """Extraído de `_resolver_resultados_prueba` para que
    `resultados_prueba` (un solo vínculo) y `resultados_prueba_multiple`
    (una lista) compartan EXACTAMENTE el mismo candado de retención y la
    misma resolución de instrumento/dimensiones — nunca dos copias que
    puedan desincronizarse. `None` = la Inscripcion ya no existe (nunca
    pasa en el flujo normal, pero una fila vieja podría apuntar a una que
    se borró/anonimizó después)."""
    inscripcion = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.id == inscripcion_id,
    ).first()
    if not inscripcion:
        return None
    # 🆕 Solo `informe_liberado` -- ver docstring de _resolver_resultados_prueba
    # arriba (decisión de alcance, sesión 2026-10-17).
    if not inscripcion.informe_liberado:
        return {"retenido": True}
    evaluacion = db.query(educativo_models.Evaluacion).filter(
        educativo_models.Evaluacion.id == inscripcion.evaluacion_id,
    ).first()
    prueba = (
        db.query(educativo_models.Prueba).filter(educativo_models.Prueba.id == evaluacion.prueba_id).first()
        if evaluacion else None
    )
    diagnosticos = (
        db.query(educativo_models.DiagnosticoAlumno, educativo_models.Dimension)
        .join(educativo_models.Dimension, educativo_models.Dimension.id == educativo_models.DiagnosticoAlumno.dimension_id)
        .filter(educativo_models.DiagnosticoAlumno.inscripcion_id == inscripcion.id)
        .all()
    )
    return {
        "retenido": False,
        "prueba_nombre": prueba.nombre_publico if prueba else "Instrumento psicométrico",
        "fecha_evaluacion": inscripcion.fecha_resolucion.isoformat() if inscripcion.fecha_resolucion else None,
        "dimensiones": [
            {"nombre": dim.nombre, "nivel": diag.nivel, "interpretacion": diag.interpretacion}
            for diag, dim in diagnosticos
        ],
    }


def _resolver_resultados_prueba_multiple(
    db: Session, estudiantes: List[models.DocumentoInstitucionalEstudiante], contenido_seccion: Optional[dict],
) -> dict:
    """Mismo candado de un único estudiante que el resto de secciones
    automáticas de esta función (`_resolver_datos_filiacion` et al.) y el
    mismo candado de retención por resultado (solo `informe_liberado`, ver
    decisión de alcance en `_resolver_un_resultado_de_inscripcion`) que
    `_resolver_resultados_prueba` — aplicado a una LISTA de Inscripcion en
    vez de a una sola, el único cambio real frente a 'resultados_prueba'.

    🔒 Los ids vienen de `contenido_seccion["inscripcion_ids"]` (guardados
    por `crud.vincular_resultados_prueba_multiple`, ya validados ahí contra
    persona+institución al momento de guardar) — pero NUNCA se confía en
    que sigan siendo válidos para siempre: se re-valida aquí mismo, otra
    vez, persona por persona, antes de incluir cada uno. Un id que ya no
    resuelve o que apunta a otra persona (ej. una Inscripcion anonimizada
    por ARCO después de vincularse) se omite en silencio, nunca rompe la
    sección entera."""
    if len(estudiantes) != 1:
        return {"aplica": False}
    persona_id = estudiantes[0].persona_id
    inscripcion_ids = (contenido_seccion or {}).get("inscripcion_ids") or []
    resultados = []
    for inscripcion_id in inscripcion_ids:
        inscripcion = db.query(educativo_models.Inscripcion).filter(
            educativo_models.Inscripcion.id == inscripcion_id,
            educativo_models.Inscripcion.persona_id == persona_id,
        ).first()
        if not inscripcion:
            continue
        resultado = _resolver_un_resultado_de_inscripcion(db, inscripcion_id)
        if resultado is not None:
            resultados.append(resultado)
    return {"aplica": True, "resultados": resultados}


def _resolver_grafico_barras(
    db: Session, documento_id: int, plantilla_seccion_id: int,
    estudiantes: List[models.DocumentoInstitucionalEstudiante], contenido_guardado: Optional[dict],
) -> dict:
    """Dos fuentes posibles, en este orden de precedencia:

    1. Vinculado a una `Inscripcion` real vía `DocumentoInstitucionalResultadoPrueba`
       (mismo mecanismo exacto que `_resolver_resultados_prueba` — reusa la
       misma fila, el mismo candado de retención `informe_liberado` (ver
       decisión de alcance, sesión 2026-10-17, en esa función), y la misma
       regla de "solo con exactamente un estudiante en la lista"). Un
       gráfico nunca debe mostrar un puntaje que el profesional todavía no
       liberó.
    2. Si no hay vínculo, datos manuales escritos por quien llena el
       documento (`contenido_guardado["datos"]`) — para instrumentos sin
       motor de scoring (ej. una prueba proyectiva).
    """
    if len(estudiantes) == 1:
        persona_id = estudiantes[0].persona_id
        referencia = db.query(models.DocumentoInstitucionalResultadoPrueba).filter(
            models.DocumentoInstitucionalResultadoPrueba.documento_institucional_id == documento_id,
            models.DocumentoInstitucionalResultadoPrueba.plantilla_seccion_id == plantilla_seccion_id,
            models.DocumentoInstitucionalResultadoPrueba.persona_id == persona_id,
        ).first()
        if referencia:
            inscripcion = db.query(educativo_models.Inscripcion).filter(
                educativo_models.Inscripcion.id == referencia.inscripcion_id,
            ).first()
            if inscripcion:
                if not inscripcion.informe_liberado:
                    return {"modo": "automatico", "retenido": True}
                evaluacion = db.query(educativo_models.Evaluacion).filter(
                    educativo_models.Evaluacion.id == inscripcion.evaluacion_id,
                ).first()
                prueba = (
                    db.query(educativo_models.Prueba).filter(educativo_models.Prueba.id == evaluacion.prueba_id).first()
                    if evaluacion else None
                )
                filas = (
                    db.query(educativo_models.Dimension, educativo_models.ResultadoDimension)
                    .join(
                        educativo_models.ResultadoDimension,
                        educativo_models.ResultadoDimension.dimension_id == educativo_models.Dimension.id,
                    )
                    .filter(educativo_models.ResultadoDimension.inscripcion_id == inscripcion.id)
                    .all()
                )
                return {
                    "modo": "automatico",
                    "retenido": False,
                    "prueba_nombre": prueba.nombre_publico if prueba else "Instrumento psicométrico",
                    "datos": [
                        {"etiqueta": dim.nombre, "valor": float(res.puntaje_directo or 0)}
                        for dim, res in filas
                    ],
                }

    datos_manuales = (contenido_guardado or {}).get("datos") or []
    if datos_manuales:
        return {"modo": "manual", "datos": datos_manuales}
    return {"modo": None}


def _resolver_tabla_dinamica(estudiantes: List[models.DocumentoInstitucionalEstudiante], config: Optional[dict], contenido_seccion: Optional[dict]) -> dict:
    """Dos modos, según `PlantillaSeccion.config.filas_desde_lista_estudiantes`:
    - True: una fila por estudiante de la lista congelada, columnas
      'automatico' resueltas desde el snapshot (nombre/grado_sección) y
      columnas 'libre' leídas de contenido["celdas"][persona_id][titulo]
      -- así una tabla de 29 estudiantes no se retipea a mano.
    - False (o ausente): tabla libre, filas = contenido["filas"] tal cual
      las escribió la psicóloga (ej. "Cuadro de apoyos prioritarios")."""
    config = config or {}
    columnas = config.get("columnas") or []
    contenido_seccion = contenido_seccion or {}
    titulos = [c.get("titulo", "") for c in columnas]

    if config.get("filas_desde_lista_estudiantes"):
        celdas = contenido_seccion.get("celdas") or {}
        filas = []
        for est in estudiantes:
            celdas_persona = celdas.get(str(est.persona_id)) or {}
            fila = []
            for col in columnas:
                titulo = col.get("titulo", "")
                if col.get("origen") == "automatico":
                    campo = col.get("campo_automatico")
                    if campo == "nombre_completo":
                        valor = est.nombre_completo_historico
                    elif campo == "grado_seccion":
                        valor = est.grado_seccion_historico
                    else:
                        valor = None
                else:
                    valor = celdas_persona.get(titulo)
                fila.append(valor or "")
            filas.append(fila)
    else:
        filas = [[f.get(titulo, "") for titulo in titulos] for f in (contenido_seccion.get("filas") or [])]

    return {"columnas": titulos, "filas": filas}


def construir_contenido_documento(
    db: Session, documento: models.DocumentoInstitucional, plantilla: models.PlantillaDocumento,
    estudiantes: List[models.DocumentoInstitucionalEstudiante], correlativo_texto: Optional[str],
    numero_version: int, motivo_version: Optional[str],
    usuario_generador: Optional[auth_models.Usuario], usuario_responsable: Optional[auth_models.Usuario],
) -> dict:
    """Ensambla TODO el contenido de una versión -- plantilla, cada sección
    resuelta según su tipo_seccion, formato de tipografía resuelto -- en un
    solo dict que a la vez (a) alimenta al renderizador de PDF y (b) se
    congela tal cual en DocumentoInstitucionalVersion.contenido_snapshot,
    mismo criterio "instantánea, no referencia" que InformeVersion."""
    institucion = db.query(instituciones_models.Institucion).filter(
        instituciones_models.Institucion.id == documento.institucion_id,
    ).first()

    anio_oficial_texto = None
    secciones_plantilla = db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.plantilla_documento_id == plantilla.id,
    ).order_by(models.PlantillaSeccion.orden).all()

    contenidos_guardados = {
        c.plantilla_seccion_id: c.contenido
        for c in db.query(models.DocumentoInstitucionalSeccionContenido).filter(
            models.DocumentoInstitucionalSeccionContenido.documento_institucional_id == documento.id,
        ).all()
    }

    secciones_render = []
    for seccion in secciones_plantilla:
        contenido_guardado = contenidos_guardados.get(seccion.id)
        config = seccion.config or {}

        if seccion.tipo_seccion == "encabezado":
            if config.get("mostrar_anio_oficial") and anio_oficial_texto is None:
                fila_anio = db.query(models.AnioOficial).filter(
                    models.AnioOficial.anio == datetime.now(timezone.utc).year,
                ).first()
                anio_oficial_texto = fila_anio.texto if fila_anio else ""
            # mostrar_emisor (default True, backward-compatible): algunas
            # plantillas no quieren la línea "DE: <quien generó la versión>"
            # bajo el título (ej. un reporte de incidente que ya firma al
            # final con el responsable real, vía la sección 'firma') — un
            # flag de catálogo, nunca una decisión por tipo/clave de
            # documento.
            datos = {
                "destinatarios": config.get("destinatarios") or [],
                "anio_oficial_texto": anio_oficial_texto or None,
                "correlativo_texto": correlativo_texto,
                "emisor_nombre": (
                    usuario_generador.nombre_completo
                    if usuario_generador and config.get("mostrar_emisor", True) else None
                ),
                "emisor_cargo": (
                    getattr(usuario_generador, "cargo", None)
                    if config.get("mostrar_emisor", True) else None
                ),
            }
        elif seccion.tipo_seccion == "datos_filiacion":
            datos = _resolver_datos_filiacion(db, estudiantes, contenido_guardado)
        elif seccion.tipo_seccion == "datos_familiares":
            datos = _resolver_datos_familiares(db, estudiantes)
        elif seccion.tipo_seccion == "resultados_prueba":
            datos = _resolver_resultados_prueba(db, documento.id, seccion.id, estudiantes)
        elif seccion.tipo_seccion == "resultados_prueba_multiple":
            datos = _resolver_resultados_prueba_multiple(db, estudiantes, contenido_guardado)
        elif seccion.tipo_seccion == "tabla_dinamica":
            datos = _resolver_tabla_dinamica(estudiantes, config, contenido_guardado)
        elif seccion.tipo_seccion == "texto_libre":
            datos = {"texto": (contenido_guardado or {}).get("texto")}
        elif seccion.tipo_seccion == "grupo_campos":
            # `config["campos"]` define las etiquetas (fijas por plantilla);
            # `contenido_guardado["valores"]` trae lo que se llenó para ESTE
            # documento, indexado por esa misma etiqueta. Una etiqueta
            # definida en la plantilla sin valor llenado se muestra vacía,
            # nunca se omite — el profesional ve qué le falta responder.
            etiquetas = [c.get("etiqueta") for c in (config.get("campos") or []) if c.get("etiqueta")]
            valores = (contenido_guardado or {}).get("valores") or {}
            datos = {"campos": [{"etiqueta": e, "valor": valores.get(e)} for e in etiquetas]}
        elif seccion.tipo_seccion == "firma":
            datos = {
                "nombre": usuario_responsable.nombre_completo if usuario_responsable else None,
                "cargo": getattr(usuario_responsable, "cargo", None),
                "lineas_fijas": config.get("lineas_fijas") or [],
                # 🆕 Firma personal (imagen) — ver Usuario.firma_imagen_url.
                # Solo la URL viaja en el snapshot (igual que institucion.
                # logo_url); pdf_generador.py la descarga recién al generar
                # el PDF. Sin imagen propia, sigue mostrando la línea de
                # subrayado de siempre — cero cambio de comportamiento.
                "firma_imagen_url": getattr(usuario_responsable, "firma_imagen_url", None),
            }
        elif seccion.tipo_seccion in ("firma_doble", "firma_triple"):
            cfg_izq = config.get("izquierda") or {}
            cfg_der = config.get("derecha") or {}
            datos = {
                "izquierda": {
                    "nombre": usuario_responsable.nombre_completo if usuario_responsable else None,
                    "cargo": getattr(usuario_responsable, "cargo", None),
                    "lineas_fijas": cfg_izq.get("lineas_fijas") or [],
                    "firma_imagen_url": getattr(usuario_responsable, "firma_imagen_url", None),
                },
                "derecha": {
                    "cargo": cfg_der.get("cargo_fijo"),
                    "lineas_fijas": cfg_der.get("lineas_fijas") or [],
                    # El lado derecho nunca tiene una persona asociada (ver
                    # docstring de PlantillaSeccion.config), así que nunca
                    # muestra una firma personal — solo texto fijo.
                    "firma_imagen_url": None,
                },
            }
            if seccion.tipo_seccion == "firma_triple":
                cfg_centro = config.get("centro") or {}
                # Mismo criterio que 'derecha' — nunca una persona asociada.
                datos["centro"] = {
                    "cargo": cfg_centro.get("cargo_fijo"),
                    "lineas_fijas": cfg_centro.get("lineas_fijas") or [],
                    "firma_imagen_url": None,
                }
        elif seccion.tipo_seccion == "grafico_barras":
            datos = _resolver_grafico_barras(db, documento.id, seccion.id, estudiantes, contenido_guardado)
        elif seccion.tipo_seccion == "imagen_anexo":
            datos = {
                "storage_key": (contenido_guardado or {}).get("storage_key"),
                "descripcion": (contenido_guardado or {}).get("descripcion"),
            }
        elif seccion.tipo_seccion == "ficha_imprimible":
            # Nunca lee contenido_guardado — ver docstring de
            # PlantillaSeccion.config en models.py: es un formulario en
            # blanco, lo que define la plantilla es exactamente lo que sale
            # impreso.
            datos = {
                "campos_encabezado": config.get("campos_encabezado") or [],
                "leyenda": config.get("leyenda"),
                "columnas": config.get("columnas") or [],
                "filas": config.get("filas") or [],
                "listas_checkbox": config.get("listas_checkbox") or [],
                "preguntas_abiertas": config.get("preguntas_abiertas") or [],
                "firmas_en_blanco": config.get("firmas_en_blanco") or [],
            }
        else:
            logger.error("tipo_seccion '%s' sin resolución de contenido conocida.", seccion.tipo_seccion)
            datos = {}

        secciones_render.append({
            "tipo_seccion": seccion.tipo_seccion,
            "titulo": seccion.titulo,
            "orden": seccion.orden,
            "datos": datos,
            # Flag genérico de catálogo, leído igual para CUALQUIER
            # tipo_seccion (nunca una decisión por nombre/clave de
            # documento) — una plantilla real a veces combina dos partes
            # distintas en un documento (ej. el reporte y la respuesta al
            # apoderado) y la segunda debe empezar en página nueva sin
            # importar dónde terminó la anterior.
            "salto_pagina_antes": bool(config.get("salto_pagina_antes")),
        })

    return {
        "documento": {
            "titulo": documento.titulo,
            "correlativo": correlativo_texto,
            "numero_version": numero_version,
            "motivo_version": motivo_version if numero_version > 1 else "Emisión inicial",
            "generado_en": datetime.now(timezone.utc).isoformat(),
        },
        # 🆕 logo_url viaja en el snapshot igual que el resto de este dict:
        # se resuelve UNA vez, al generar esta versión, y queda congelado —
        # si la institución cambia de logo después, las versiones ya
        # emitidas no se enteran, mismo criterio que el informe psicométrico
        # (core/pdf_generator.py) ya aplica para su propio logo.
        "institucion": {
            "nombre": institucion.nombre if institucion else None,
            "logo_url": institucion.logo_url if institucion else None,
            "logo_pie_pagina_url": institucion.logo_pie_pagina_url if institucion else None,
            "fondo_documento_url": institucion.fondo_documento_url if institucion else None,
        },
        "plantilla": {
            "fuente": plantilla.fuente, "tamano_pt": plantilla.tamano_pt,
            "interlineado": float(plantilla.interlineado) if plantilla.interlineado is not None else 1.15,
            "justificado": plantilla.justificado,
            "titulo_negrita": plantilla.titulo_negrita,
            "titulo_cursiva": plantilla.titulo_cursiva,
            "titulo_tamano_pt": plantilla.titulo_tamano_pt,
            "subtitulo_tamano_pt": plantilla.subtitulo_tamano_pt,
            "mostrar_fondo_institucion": plantilla.mostrar_fondo_institucion,
        },
        "secciones": secciones_render,
    }


def generar_version_documento(
    db: Session, documento_id: int, usuario_id: int, motivo: Optional[str] = None,
) -> models.DocumentoInstitucionalVersion:
    """v1 y cada reemisión pasan por AQUÍ — nunca hay un camino separado
    para "la primera vez". El consentimiento (cuando el tipo lo exige) y el
    correlativo se resuelven en cada llamada, sin atajos por ser v1."""
    documento = bloquear_documento_institucional_para_version(db, documento_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    numero_version = (documento.version_actual or 0) + 1
    if numero_version > 1 and not (motivo and motivo.strip()):
        raise HTTPException(status_code=422, detail="Reemitir una versión exige indicar un motivo.")

    tipo = db.query(models.TipoDocumento).filter(models.TipoDocumento.id == documento.tipo_documento_id).first()
    estudiantes = listar_estudiantes_de_documento(db, documento.id)

    # 🔒 Gate de consentimiento -- SOLO cuando el tipo lo exige (nunca por
    # su clave/slug), revalidado en CADA generación: a diferencia de
    # finalizar_examen_seguro (un hecho histórico que nunca vuelve a
    # chequear), cada versión de un documento es un acto nuevo de generar
    # una salida con datos personales, en una fecha propia. Chequea el
    # consentimiento del APODERADO -- el asentimiento del estudiante queda
    # visible en su perfil (GET /personas/{id}/consentimientos) pero no
    # bloquea esta generación (decisión del Paso 5).
    if tipo and tipo.requiere_consentimiento_individual:
        faltantes = [
            est.nombre_completo_historico or f"persona #{est.persona_id}"
            for est in estudiantes
            if not superadmin_crud.tiene_consentimiento_vigente(db, est.persona_id, documento.institucion_id)
        ]
        if faltantes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "No se puede generar: falta el consentimiento vigente del apoderado para: "
                    + ", ".join(faltantes)
                ),
            )

    plantilla = db.query(models.PlantillaDocumento).filter(models.PlantillaDocumento.id == documento.plantilla_documento_id).first()

    correlativo_texto = None
    if plantilla and plantilla.formato_correlativo:
        anio_actual = datetime.now(timezone.utc).year
        anio_correlativo = anio_actual if plantilla.correlativo_reinicia_anualmente else 0
        contador = bloquear_correlativo_para_emision(db, documento.institucion_id, documento.tipo_documento_id, anio_correlativo)
        contador.ultimo_numero += 1
        try:
            correlativo_texto = plantilla.formato_correlativo.format(correlativo=contador.ultimo_numero, anio=anio_actual)
        except (KeyError, ValueError, IndexError):
            # No debería pasar -- el formato se valida al GUARDAR la
            # plantilla (Paso 1) -- pero una emisión real nunca debe
            # abortar por esto: se usa el número crudo como respaldo.
            logger.error("formato_correlativo inválido en plantilla %s: %r", plantilla.id, plantilla.formato_correlativo)
            correlativo_texto = str(contador.ultimo_numero)

    usuario_generador = db.query(auth_models.Usuario).filter(auth_models.Usuario.id == usuario_id).first()
    usuario_responsable = db.query(auth_models.Usuario).filter(
        auth_models.Usuario.id == documento.creado_por_usuario_id,
    ).first()

    contenido_dict = construir_contenido_documento(
        db, documento, plantilla, estudiantes, correlativo_texto, numero_version, motivo,
        usuario_generador, usuario_responsable,
    )

    pdf_buffer = pdf_generador.generar_pdf_documento(contenido_dict)
    contenido_bytes = pdf_buffer.getvalue()
    checksum = hashlib.sha256(contenido_bytes).hexdigest()
    storage_key = construir_storage_key_documento(documento.institucion_id, documento.id, numero_version)
    obtener_storage_service().guardar(storage_key, contenido_bytes, "application/pdf")

    version = models.DocumentoInstitucionalVersion(
        documento_institucional_id=documento.id,
        numero_version=numero_version,
        contenido_snapshot=contenido_dict,
        storage_key=storage_key,
        nombre_archivo=f"documento_{documento.id}_v{numero_version}.pdf",
        mime_type="application/pdf",
        tamano_bytes=len(contenido_bytes),
        checksum_sha256=checksum,
        generado_por_usuario_id=usuario_id,
        motivo_version=motivo if numero_version > 1 else "Emisión inicial",
    )
    db.add(version)
    documento.version_actual = numero_version

    for est in estudiantes:
        superadmin_crud.crear_entrada_expediente_documento_institucional(
            db, persona_id=est.persona_id, institucion_id=documento.institucion_id,
            documento_institucional_id=documento.id, autor_usuario_id=documento.creado_por_usuario_id,
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya se generó otra versión de este documento al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(version)
    return version


def obtener_version_documento(db: Session, documento_id: int, numero_version: int) -> Optional[models.DocumentoInstitucionalVersion]:
    return db.query(models.DocumentoInstitucionalVersion).filter(
        models.DocumentoInstitucionalVersion.documento_institucional_id == documento_id,
        models.DocumentoInstitucionalVersion.numero_version == numero_version,
    ).first()


def listar_versiones_documento(db: Session, documento_id: int) -> List[models.DocumentoInstitucionalVersion]:
    return db.query(models.DocumentoInstitucionalVersion).filter(
        models.DocumentoInstitucionalVersion.documento_institucional_id == documento_id,
    ).order_by(models.DocumentoInstitucionalVersion.numero_version.desc()).all()


# ==========================================
# Enganche automático: motor de pruebas -> motor de documentos.
#
# Hasta aquí, un DocumentoInstitucional con una sección resultados_prueba
# solo nacía de una acción manual (crear el documento, vincular el
# resultado, generar la versión — los tres por API). Esto cierra ese hueco
# para el caso más común: una institución que ya configuró, vía
# PlantillaDocumento.generar_automaticamente_al_finalizar_examen, qué
# plantilla propia quiere recibir automáticamente por cada examen que
# finaliza — sin que eso signifique que TODAS las instituciones comparten
# un único diseño: cada una tiene su propia plantilla (o ninguna, si no
# activó el enganche), construida por superadmin igual que cualquier otra.
#
# Se invoca SOLO desde BackgroundTasks, después de que
# finalizar_examen_seguro ya confirmó su propia transacción — mismo lugar y
# misma razón que crud.tarea_generar_informe_en_segundo_plano del módulo
# educativo (ver ese docstring): la sesión de la petición HTTP que finalizó
# el examen ya está cerrada, así que esto abre la suya propia. Un fallo acá
# nunca afecta al examen que ya terminó ni al informe psicométrico
# automático, que es un pipeline completamente aparte.
# ==========================================
def _resolver_actor_automatico_para_institucion(db: Session, institucion_id: int, evaluacion) -> Optional[int]:
    """A quién atribuir un DocumentoInstitucional que nadie pidió a mano.

    `creado_por_usuario_id` no es solo auditoría: generar_version_documento
    lo usa como `autor_usuario_id` de la entrada-puente que crea en el
    expediente de cada estudiante (ver crear_entrada_expediente_documento_
    institucional), y la confidencialidad del expediente es estricta
    (autor_usuario_id o superadmin, nadie más) — dejar esta columna en NULL
    habría hecho que NINGÚN psicólogo/admin pudiera leer esa entrada-puente
    sin pasar por superadmin, justo lo contrario de lo que este enganche
    busca. Por eso se resuelve un usuario real, nunca NULL, con una cadena
    de respaldo deliberadamente más corta que la de obtener_destinatarios_
    alerta (que también incluye 'colegio' y un correo de contacto): aquí se
    necesita alguien con permiso real de ESCRIBIR documentos
    (requerir_rol de los endpoints de instancia es superadmin/admin/
    psicologo — 'colegio' nunca podría haber creado este documento a mano,
    así que tampoco figura como su autor automático):
      1. el creador de la campaña (evaluacion.creador_id), si sigue activo;
      2. el primer admin activo de la institución (orden por id, estable);
      3. el primer psicólogo activo de la institución (ídem).
    None si ninguno existe — caso degenerado (institución sin ningún
    usuario activo habilitado para documentos), el llamador se lo salta.
    """
    if evaluacion and evaluacion.creador_id:
        creador = db.query(auth_models.Usuario).filter(
            auth_models.Usuario.id == evaluacion.creador_id,
            auth_models.Usuario.activo == True,  # noqa: E712
        ).first()
        if creador:
            return creador.id

    for rol in ("admin", "psicologo"):
        respaldo = db.query(auth_models.Usuario).filter(
            auth_models.Usuario.institucion_id == institucion_id,
            auth_models.Usuario.rol == rol,
            auth_models.Usuario.activo == True,  # noqa: E712
        ).order_by(auth_models.Usuario.id).first()
        if respaldo:
            return respaldo.id

    return None


def _generar_documento_automatico_de_plantilla(
    db: Session, plantilla: models.PlantillaDocumento, inscripcion, actor_usuario_id: int,
) -> None:
    """Crea y emite (v1) un DocumentoInstitucional de UNA plantilla para EL
    estudiante de esta inscripción — o se omite, con un log, si la
    plantilla no es elegible ahora mismo.

    🔒 Nunca deja un documento a medias — garantía REAL, no solo narrada:
    `crear_documento_institucional`/`vincular_resultado_prueba` se llaman
    con `commit=False` (hacen `flush()`, nunca `commit()`), así que los tres
    pasos (crear borrador, vincular el resultado, generar la versión) viven
    en la MISMA transacción. El único commit real es el que ya hace
    `generar_version_documento` al final. Si algo falla en cualquier punto
    (p. ej. consentimiento revocado entre el pre-chequeo de abajo y el
    re-chequeo dentro de `generar_version_documento`), el `db.rollback()`
    del llamador (`generar_documentos_automaticos_por_examen`) deshace los
    tres pasos juntos — antes de este fix, los dos primeros ya habían hecho
    su propio commit independiente y quedaban huérfanos en la BD aunque el
    tercero fallara.
    """
    secciones_resultado = db.query(models.PlantillaSeccion).filter(
        models.PlantillaSeccion.plantilla_documento_id == plantilla.id,
        models.PlantillaSeccion.tipo_seccion == "resultados_prueba",
    ).all()
    if len(secciones_resultado) != 1:
        logger.info(
            "Plantilla %s tiene %s sección(es) 'resultados_prueba' (se "
            "requiere exactamente 1 para el enganche automático); se omite "
            "para la inscripción %s.",
            plantilla.id, len(secciones_resultado), inscripcion.id,
        )
        return
    seccion = secciones_resultado[0]

    tipo = db.query(models.TipoDocumento).filter(
        models.TipoDocumento.id == plantilla.tipo_documento_id,
        models.TipoDocumento.activo == True,  # noqa: E712
    ).first()
    if not tipo:
        logger.info(
            "Plantilla %s apunta a un tipo de documento inactivo o inexistente; "
            "se omite para la inscripción %s.", plantilla.id, inscripcion.id,
        )
        return

    # Mismo gate de consentimiento que generar_version_documento ya aplica
    # más abajo — revalidado aquí ANTES para no dejar un
    # DocumentoInstitucional huérfano en borrador cuando ya se sabe que su
    # versión va a fallar por esto.
    if tipo.requiere_consentimiento_individual and not superadmin_crud.tiene_consentimiento_vigente(
        db, inscripcion.persona_id, plantilla.institucion_id,
    ):
        logger.info(
            "Persona %s sin consentimiento vigente del apoderado; se omite "
            "el documento automático de la plantilla %s para la "
            "inscripción %s.", inscripcion.persona_id, plantilla.id, inscripcion.id,
        )
        return

    documento = crear_documento_institucional(
        db,
        usuario_actual=db.query(auth_models.Usuario).filter(auth_models.Usuario.id == actor_usuario_id).first(),
        datos=schemas.DocumentoInstitucionalCreate(
            tipo_documento_id=tipo.id,
            plantilla_documento_id=plantilla.id,
            alcance="personas_especificas",
            titulo=f"{tipo.nombre} — {inscripcion.nombre_completo or ('Persona ' + str(inscripcion.persona_id))}",
            personas_ids=[inscripcion.persona_id],
        ),
        commit=False,
    )
    vincular_resultado_prueba(
        db, documento=documento, plantilla_seccion_id=seccion.id,
        persona_id=inscripcion.persona_id, inscripcion_id=inscripcion.id,
        commit=False,
    )
    generar_version_documento(db, documento_id=documento.id, usuario_id=actor_usuario_id)
    logger.info(
        "Documento automático %s (plantilla %s) generado para la inscripción %s.",
        documento.id, plantilla.id, inscripcion.id,
    )


def generar_documentos_automaticos_por_examen(db: Session, inscripcion_id: int) -> None:
    """Punto de entrada del enganche — ver la nota de sección arriba.

    Recorre todas las PlantillaDocumento activas de la institución de esta
    inscripción marcadas generar_automaticamente_al_finalizar_examen=True,
    y genera un documento por cada una que sea elegible. El fallo de UNA
    plantilla (consentimiento, tipo inactivo, sección ambigua, lo que sea)
    nunca impide generar la de otra: cada una corre en su propio
    try/except con rollback, exactamente como calcular_resultados_
    dimensiones/interpretar_segun_modo lo hacen con sus propios pasos
    dentro de finalizar_examen_seguro, pero aquí CADA PASO es independiente
    en vez de ser una sola transacción, porque son documentos distintos sin
    relación entre sí."""
    inscripcion = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.id == inscripcion_id
    ).first()
    # Un link anónimo (persona_id NULL) no tiene a quién atribuirle un
    # documento de alcance 'personas_especificas' — se omite entero, sin
    # registrar nada (no es una configuración incompleta, es un tipo de
    # inscripción para el que este enganche simplemente no aplica).
    if not inscripcion or not inscripcion.persona_id:
        return

    evaluacion = db.query(educativo_models.Evaluacion).filter(
        educativo_models.Evaluacion.id == inscripcion.evaluacion_id
    ).first()
    if not evaluacion:
        return
    institucion_id = evaluacion.institucion_id

    plantillas = db.query(models.PlantillaDocumento).filter(
        models.PlantillaDocumento.institucion_id == institucion_id,
        models.PlantillaDocumento.activa == True,  # noqa: E712
        models.PlantillaDocumento.generar_automaticamente_al_finalizar_examen == True,  # noqa: E712
    ).all()
    if not plantillas:
        return

    actor_usuario_id = _resolver_actor_automatico_para_institucion(db, institucion_id, evaluacion)
    if actor_usuario_id is None:
        logger.warning(
            "Institución %s no tiene ningún admin/psicólogo activo para "
            "atribuir documentos automáticos; se omite para la inscripción %s.",
            institucion_id, inscripcion_id,
        )
        return

    for plantilla in plantillas:
        try:
            _generar_documento_automatico_de_plantilla(
                db, plantilla=plantilla, inscripcion=inscripcion, actor_usuario_id=actor_usuario_id,
            )
        except Exception:
            db.rollback()
            logger.error(
                "Fallo generando el documento automático de la plantilla %s "
                "(institución %s) para la inscripción %s. Se omite esta "
                "plantilla y se sigue con las demás.",
                plantilla.id, institucion_id, inscripcion_id, exc_info=True,
            )


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def tarea_generar_documentos_automaticos_en_segundo_plano(self, inscripcion_id: int):
    """Tarea Celery real (Fase 2, ver core/cola_tareas.py): abre su PROPIA
    sesión de DB — mismo motivo exacto que modulos.educativo.crud.
    tarea_generar_informe_en_segundo_plano, que es la convención que esta
    tarea sigue al pie de la letra (incluyendo el registro de
    PLAN_REMODELACION_ARQUITECTURA.md, fase 3, y el reintento real de la
    Fase 2 — ver el docstring de esa función para el detalle)."""
    from core.database import SessionLocal
    from core.tareas_async import ejecutar_tarea_registrada
    db = SessionLocal()
    try:
        ejecutar_tarea_registrada(
            db, tipo_tarea="generar_documento_automatico", referencia_id=inscripcion_id,
            fn=lambda: generar_documentos_automaticos_por_examen(db, inscripcion_id=inscripcion_id),
            job_id=self.request.id,
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Fallo generando documentos automáticos para la inscripción %s en segundo plano "
            "(intento %s/%s).",
            inscripcion_id, self.request.retries + 1, self.max_retries + 1, exc_info=True,
        )
        raise self.retry(exc=exc)
    finally:
        db.close()


def reemitir_documentos_vinculados_a_inscripcion(
    db: Session, inscripcion_id: int, usuario_id: int, motivo: str,
) -> List[int]:
    """Tras un reproceso del examen (`POST /educativo/inscripciones/{id}/
    reprocesar`), cualquier DocumentoInstitucional cuya sección
    resultados_prueba apunte a ESTA Inscripcion queda con contenido
    desactualizado — su versión más reciente congeló el resultado ANTERIOR
    a la corrección del baremo. Esto cierra el hueco que `CLAUDE.md`
    documentaba como "no enganchado a reprocesar, decisión deliberada de
    alcance": en vez de dejarlo sin resolver, se reemite una nueva versión
    de cada documento afectado, con el mismo mecanismo (`generar_version_
    documento`) que ya usa cualquier reemisión manual.

    Aplica por igual a un documento creado por el enganche automático
    (`generar_documentos_automaticos_por_examen`) o vinculado a mano vía
    `PUT .../resultados-prueba` — no se distingue el origen, porque el
    problema (contenido desactualizado) es idéntico para los dos: esta
    función solo mira `DocumentoInstitucionalResultadoPrueba`, nunca cómo
    llegó a existir esa fila.

    Un documento que TODAVÍA no generó ninguna versión (`version_actual`
    sigue NULL, un borrador) se deja intacto a propósito — su próxima
    generación manual ya va a leer el resultado corregido sin ayuda de
    nadie, el mismo principio por el que un Baremo corregido no necesita
    "reprocesar" nada que nunca llegó a generarse.

    Se invoca de forma SÍNCRONA desde el endpoint de reprocesar (no via
    BackgroundTasks): esa acción ya es administrativa, no está sirviendo a
    un alumno esperando una respuesta, y ya regenera el informe
    psicométrico de la misma forma síncrona en el mismo request — mantiene
    la sesión de BD que el endpoint ya tiene abierta, sin necesidad de
    abrir una nueva. Un documento que falla al reemitir (p. ej. su
    consentimiento se revocó justo entre medio) se registra y se omite —
    nunca revierte el reproceso del examen, que ya se confirmó antes de
    llegar aquí. Devuelve la lista de ids efectivamente reemitidos, solo
    para que el llamador pueda loguear cuántos se tocaron."""
    documento_ids = [
        fila[0] for fila in db.query(models.DocumentoInstitucionalResultadoPrueba.documento_institucional_id)
        .filter(models.DocumentoInstitucionalResultadoPrueba.inscripcion_id == inscripcion_id)
        .distinct()
        .all()
    ]
    reemitidos = []
    for documento_id in documento_ids:
        documento = db.query(models.DocumentoInstitucional).filter(
            models.DocumentoInstitucional.id == documento_id,
        ).first()
        if not documento or documento.version_actual is None:
            continue
        try:
            generar_version_documento(db, documento_id=documento_id, usuario_id=usuario_id, motivo=motivo)
            reemitidos.append(documento_id)
        except Exception:
            db.rollback()
            logger.error(
                "Fallo reemitiendo el documento %s tras el reproceso de la inscripción %s "
                "(se omite; el reproceso del examen ya quedó confirmado antes de esto).",
                documento_id, inscripcion_id, exc_info=True,
            )
    return reemitidos


# ==========================================
# Paso 6 — Lectura/descarga gobernada por nivel_visibilidad. Completamente
# independiente de la regla del expediente (ver
# crear_entrada_expediente_documento_institucional): esta función NUNCA
# afecta, ni es afectada por, quién puede leer la entrada-puente de un
# estudiante incluido en el documento.
# ==========================================
def usuario_puede_ver_documento(usuario_actual, documento: models.DocumentoInstitucional) -> bool:
    """superadmin: siempre. admin/psicologo de la MISMA institución:
    siempre, sin importar quién creó el documento -- mismo criterio de
    tenant+rol que el resto de recursos institucionales, sin ACL por
    documento (decisión de producto confirmada para este paso). 'colegio':
    solo si nivel_visibilidad='compartible_colegio'. Cualquier otro caso
    (otra institución, u otro rol) no ve el documento."""
    if usuario_actual.rol == "superadmin":
        return True
    if documento.institucion_id != usuario_actual.institucion_id:
        return False
    if usuario_actual.rol == "colegio":
        return documento.nivel_visibilidad == "compartible_colegio"
    return usuario_actual.rol in ("admin", "psicologo")


def leer_pdf_de_version_documento(version: models.DocumentoInstitucionalVersion) -> bytes:
    return obtener_storage_service().leer(version.storage_key)


# ==========================================
# Paso 7 — auditoría de lectura. Solo se llama desde los dos endpoints que
# entregan contenido real (secciones, descarga de PDF) — nunca desde el
# listado, el detalle o la lista de versiones, que son metadata.
# ==========================================
def registrar_lectura_documento(
    db: Session,
    documento: models.DocumentoInstitucional,
    usuario_actual,
    tipo_acceso: str,
    ip_lectura: Optional[str] = None,
    numero_version_leida: Optional[int] = None,
) -> models.RegistroLecturaDocumento:
    """Inserta una fila de auditoría append-only. `acceso_via_visibilidad_
    colegio` se deriva del rol del lector en este mismo instante: dado
    `usuario_puede_ver_documento`, 'colegio' solo llega hasta acá cuando
    `nivel_visibilidad='compartible_colegio'`, así que el rol por sí solo ya
    identifica la vía — se guarda explícito en vez de inferirlo después con
    un join, mismo espíritu que `Inscripcion.consentimiento_apoderado_id`
    snapshotea qué consentimiento respaldó una aplicación en vez de dejar
    que un lector futuro tenga que reconstruirlo."""
    registro = models.RegistroLecturaDocumento(
        documento_institucional_id=documento.id,
        institucion_id=documento.institucion_id,
        leido_por_usuario_id=usuario_actual.id,
        rol_lector=usuario_actual.rol,
        ip_lectura=ip_lectura,
        tipo_acceso=tipo_acceso,
        numero_version_leida=numero_version_leida,
        acceso_via_visibilidad_colegio=(usuario_actual.rol == "colegio"),
    )
    db.add(registro)
    db.commit()
    return registro
