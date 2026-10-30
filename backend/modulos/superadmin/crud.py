from sqlalchemy.orm import Session
from sqlalchemy import or_
from . import models, schemas
from datetime import timezone
from modulos.educativo import models as educativo_models
# ⚠️ Import circular: `modulos.educativo.crud` importa a su vez este módulo.
#
# Se enlaza el MÓDULO, no el nombre de la función. `from paquete import modulo`
# resuelve contra el objeto módulo, que Python registra en sys.modules en
# cuanto empieza a cargarse, así que tolera una inicialización parcial. La
# forma anterior, `from modulos.educativo.crud import obtener_historial_de_persona`,
# exigía que la función YA estuviera definida: importar educativo.crud primero
# reventaba con ImportError y la aplicación solo arrancaba por el orden
# accidental en que main.py carga los módulos.
#
# La llamada se resuelve en tiempo de ejecución (educativo_crud.funcion(...)),
# cuando ambos módulos están completos.
from modulos.educativo import crud as educativo_crud
import hashlib
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from typing import Optional
from core.concurrencia import commit_o_conflicto
# ==========================================
# CRUD PARA PERSONAS (EVALUADOS)
# ==========================================
def crear_persona(db: Session, persona: schemas.PersonaCreate):
    nueva_persona = models.Persona(
        institucion_id=persona.institucion_id,
        tipo_perfil=persona.tipo_perfil,
        nombres=persona.nombres,
        apellidos=persona.apellidos,
        documento_identidad=persona.documento_identidad,
        codigo_institucional=persona.codigo_institucional,
        email=persona.email,
        fecha_nacimiento=persona.fecha_nacimiento,
        genero=persona.genero,
        grado_seccion=persona.grado_seccion,
        puesto_postula=persona.puesto_postula,
        area_empresa=persona.area_empresa,
    )
    db.add(nueva_persona)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # 🆕 Núcleo del estudiante — ahora hay DOS restricciones únicas por
        # institución (documento y código institucional); un mensaje que
        # siempre culpara al documento sería engañoso si lo que chocó fue el
        # código.
        detalle = "Ya existe una persona registrada con ese documento de identidad o código institucional en esta institución."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
    db.refresh(nueva_persona)
    return nueva_persona


def obtener_personas_por_institucion(
    db: Session,
    institucion_id: int,
    busqueda: Optional[str] = None,
    incluir_inactivas: bool = False,
    skip: int = 0,
    limit: int = 50,
):
    """Lista el padrón de un colegio, paginado. Si se pasa `busqueda`, filtra
    por nombres, apellidos o documento de identidad (case-insensitive,
    coincidencia parcial).

    🔒 C-8 — Por defecto solo devuelve personas activas. La anonimización ARCO
    deja el registro con `activo = False` y la PII borrada, así que un padrón
    sin filtrar volvía a mostrar como alumno corriente a quien ya había
    ejercido su derecho de cancelación. Con `incluir_inactivas=True` se puede
    seguir consultando el histórico de forma explícita.

    🆕 Paginación real (ver docs/gaps-pendientes.md) — antes devolvía TODO el
    padrón sin tope; ahora `total` se cuenta antes de aplicar `offset/limit`
    para que el total refleje el padrón completo filtrado, no la página.
    """
    query = db.query(models.Persona).filter(
        models.Persona.institucion_id == institucion_id
    )
    if not incluir_inactivas:
        query = query.filter(models.Persona.activo == True)  # noqa: E712
    if busqueda:
        patron = f"%{busqueda.strip()}%"
        query = query.filter(
            (models.Persona.nombres.ilike(patron))
            | (models.Persona.apellidos.ilike(patron))
            | (models.Persona.documento_identidad.ilike(patron))
        )
    total = query.count()
    personas = query.order_by(models.Persona.apellidos).offset(skip).limit(limit).all()

    # 🆕 Sección vigente del padrón — UNA sola consulta batch para toda la
    # institución (join, no una query por alumno), mismo patrón "batch-loaded,
    # no N+1" que ya usan los dashboards de educativo/crud.py. Se adjunta como
    # atributo transitorio (no mapeado, no se persiste) para que
    # PersonaResponse.seccion_actual lo recoja vía from_attributes sin tocar
    # el modelo ORM ni requerir una migración — esto es solo lectura.
    secciones_vigentes = _secciones_vigentes_de_institucion(db, institucion_id)
    for persona in personas:
        persona.seccion_actual = secciones_vigentes.get(persona.id)
    return total, personas


def _secciones_vigentes_de_institucion(db: Session, institucion_id: int) -> dict:
    """Sección vigente de CADA persona de la institución con matrícula
    activa, resuelta en una sola consulta (join MatriculaAcademica ->
    Seccion -> Grado -> NivelEducativo, filtrada por institucion_id y
    fecha_fin IS NULL), indexada por persona_id. Mismo shape de campos que
    _describir_matricula(), reutilizado aquí en forma de batch para que
    listar el padrón completo no dispare una consulta por alumno."""
    filas = (
        db.query(models.MatriculaAcademica, models.Seccion, models.Grado, models.NivelEducativo)
        .join(models.Seccion, models.Seccion.id == models.MatriculaAcademica.seccion_id)
        .join(models.Grado, models.Grado.id == models.Seccion.grado_id)
        .join(models.NivelEducativo, models.NivelEducativo.id == models.Grado.nivel_educativo_id)
        .filter(
            models.MatriculaAcademica.institucion_id == institucion_id,
            models.MatriculaAcademica.fecha_fin.is_(None),
        )
        .all()
    )
    return {
        matricula.persona_id: {
            "matricula_id": matricula.id,
            "seccion_id": seccion.id,
            "seccion": seccion.nombre,
            "turno": seccion.turno,
            "anio_escolar": seccion.anio_escolar,
            "grado_id": grado.id,
            "grado": grado.nombre,
            "nivel_educativo_id": nivel.id,
            "nivel_educativo": nivel.nombre,
            "fecha_inicio": matricula.fecha_inicio,
            "fecha_fin": matricula.fecha_fin,
        }
        for matricula, seccion, grado, nivel in filas
    }


def registrar_consentimiento(
    db: Session,
    persona: models.Persona,
    datos,
    registrado_por_usuario_id: int,
    ip_registro: Optional[str] = None,
    tipo_consentimiento: str = models.TIPO_CONSENTIMIENTO_APODERADO,
):
    """Registra un consentimiento de una persona ya validada.

    🆕 Consentimientos del estudiante/apoderado — `datos` acepta tanto
    `ConsentimientoCreate` (apoderado) como `ConsentimientoAsentimientoCreate`
    (estudiante); los campos que solo tiene el primero (otorgado_por_nombre,
    tipo_otorgante, otorgante_*) se leen únicamente cuando
    tipo_consentimiento="apoderado", así que nunca se accede a un atributo
    que el segundo esquema no tiene. Son DOS historiales independientes: un
    consentimiento de apoderado NUNCA crea uno del estudiante, ni al revés
    (ver `tiene_consentimiento_vigente`, acotado por tipo).

    🔒 B-8 — La persona y la institución se toman del objeto `persona`, que el
    endpoint ya comprobó contra la sesión, NO de `datos.persona_id` ni de
    `datos.institucion_id`. Antes se validaba el `persona_id` de la ruta pero
    se escribía el del body, así que bastaba con apuntar la ruta a un alumno
    propio y el body a uno ajeno para fabricar un consentimiento falso en
    otro colegio —y con él, habilitar su evaluación—.

    🏛️ B-11 — Se deja constancia de la IP desde la que se registró.
    """
    es_apoderado = tipo_consentimiento == models.TIPO_CONSENTIMIENTO_APODERADO

    # Un mismo titular no debe acumular varios consentimientos VIGENTES DEL
    # MISMO TIPO: con duplicados, revocar uno dejaba los demás activos y el
    # alumno seguía siendo evaluable pese a la revocación. El índice único
    # parcial de la base es la garantía real; esto lo convierte en un 409
    # explicado en vez de un IntegrityError.
    if tiene_consentimiento_vigente(db, persona.id, persona.institucion_id, tipo_consentimiento):
        etiqueta = "de apoderado" if es_apoderado else "del propio estudiante"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta persona ya tiene un consentimiento {etiqueta} vigente. Revócalo "
                "antes de registrar uno nuevo; el historial anterior se conserva."
            ),
        )

    nuevo = models.ConsentimientoInformado(
        persona_id=persona.id,                    # 👈 del recurso validado
        institucion_id=persona.institucion_id,    # 👈 del recurso validado
        tipo_consentimiento=tipo_consentimiento,
        estado=models.ESTADO_CONSENTIMIENTO_VIGENTE,
        otorgado_por_nombre=datos.otorgado_por_nombre if es_apoderado else None,
        tipo_otorgante=datos.tipo_otorgante if es_apoderado else None,
        otorgante_apellidos=getattr(datos, "otorgante_apellidos", None) if es_apoderado else None,
        otorgante_documento=getattr(datos, "otorgante_documento", None) if es_apoderado else None,
        otorgante_relacion=getattr(datos, "otorgante_relacion", None) if es_apoderado else None,
        referencia_documento=datos.referencia_documento,
        evidencia_ruta=getattr(datos, "evidencia_ruta", None),
        registrado_por_usuario_id=registrado_por_usuario_id,
        ip_registro=ip_registro,
    )
    db.add(nuevo)
    # El chequeo de arriba (tiene_consentimiento_vigente) solo cierra la
    # ventana del caso SECUENCIAL. Dos registros concurrentes para la misma
    # persona+tipo pasan ambos ese chequeo antes de que cualquiera haga
    # commit, y solo el índice único parcial (uq_consentimiento_vigente_
    # por_persona_y_tipo) detiene al segundo — como IntegrityError crudo, no
    # como el mismo 409 explicado de arriba. Mismo patrón que
    # crear_documento_institucional en modulos/documentos/crud.py.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        etiqueta = "de apoderado" if es_apoderado else "del propio estudiante"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta persona ya tiene un consentimiento {etiqueta} vigente. Revócalo "
                "antes de registrar uno nuevo; el historial anterior se conserva."
            ),
        )
    db.refresh(nuevo)
    return nuevo


# ==========================================
# 🆕 EVIDENCIA DEL CONSENTIMIENTO (cierre de gap — docs/gaps-pendientes.md)
# ==========================================
EXTENSIONES_EVIDENCIA_PERMITIDAS = {".pdf", ".jpg", ".jpeg", ".png"}
TAMANO_MAXIMO_EVIDENCIA_BYTES = 10 * 1024 * 1024  # 10 MB — de sobra para un PDF/foto escaneado


def _extension_segura(nombre_archivo: str) -> str:
    """Nunca se usa el nombre de archivo del cliente tal cual para construir
    una key de storage (mismo criterio que construir_storage_key()): solo se
    rescata la extensión, en minúsculas, y solo si está en la lista blanca.
    Cualquier otra cosa (sin extensión, extensión desconocida, intento de
    path traversal tipo "../../x.pdf") cae al 400 explícito del caller."""
    import os as _os
    extension = _os.path.splitext(nombre_archivo or "")[1].lower()
    if extension not in EXTENSIONES_EVIDENCIA_PERMITIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Extensión de archivo no permitida para evidencia de consentimiento. "
                f"Usa una de: {', '.join(sorted(EXTENSIONES_EVIDENCIA_PERMITIDAS))}."
            ),
        )
    return extension


def guardar_evidencia_consentimiento(
    db: Session, consentimiento: models.ConsentimientoInformado,
    contenido: bytes, nombre_archivo: str, content_type: str, usuario_id: int,
) -> models.ConsentimientoInformado:
    """Sube el documento firmado/escaneado real de un consentimiento ya
    registrado — cierre del gap "evidencia_ruta sin usar" (docs/gaps-
    pendientes.md): el storage que lo bloqueaba (core/storage/) ya existe
    desde el motor de informes, así que esto reutiliza exactamente el mismo
    contrato (`obtener_storage_service().guardar/leer`), nunca uno propio.

    Una subida nueva SOBRESCRIBE la anterior en la misma key (sin
    versionado, a diferencia de InformeVersion/DocumentoInstitucionalVersion
    — la evidencia de un consentimiento no tiene el mismo requisito legal de
    conservar cada versión histórica que un informe clínico).
    """
    if len(contenido) > TAMANO_MAXIMO_EVIDENCIA_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo supera el tamaño máximo permitido ({TAMANO_MAXIMO_EVIDENCIA_BYTES // (1024*1024)} MB).",
        )
    extension = _extension_segura(nombre_archivo)

    from core.storage import obtener_storage_service, construir_storage_key_evidencia_consentimiento
    key = construir_storage_key_evidencia_consentimiento(
        consentimiento.institucion_id, consentimiento.id, extension,
    )
    obtener_storage_service().guardar(key, contenido, content_type or "application/octet-stream")

    consentimiento.evidencia_ruta = key
    consentimiento.evidencia_nombre_archivo = nombre_archivo
    consentimiento.evidencia_content_type = content_type or "application/octet-stream"
    consentimiento.evidencia_tamano_bytes = len(contenido)
    consentimiento.evidencia_subido_en = datetime.now(timezone.utc)
    consentimiento.evidencia_subido_por_usuario_id = usuario_id
    db.commit()
    db.refresh(consentimiento)
    return consentimiento


def leer_evidencia_consentimiento(consentimiento: models.ConsentimientoInformado) -> bytes:
    """Lee el binario de storage. Lanza FileNotFoundError si la key no
    existe (mismo contrato que StorageService.leer) — el caller decide si
    eso es un 404 o un dato inconsistente que vale la pena loguear."""
    from core.storage import obtener_storage_service
    return obtener_storage_service().leer(consentimiento.evidencia_ruta)


def obtener_consentimiento_vigente(
    db: Session, persona_id: int, institucion_id: Optional[int] = None,
    tipo_consentimiento: str = models.TIPO_CONSENTIMIENTO_APODERADO,
):
    """Devuelve la FILA del consentimiento vigente de ese tipo (o None).

    🆕 Consentimientos del estudiante/apoderado — a diferencia de
    `tiene_consentimiento_vigente` (que solo responde sí/no), esto devuelve
    el registro completo: lo usa `matricular_roster_en_campana` para
    guardar en la inscripción EXACTAMENTE cuál fue el consentimiento vigente
    en ese instante (`Inscripcion.consentimiento_apoderado_id` /
    `.consentimiento_asentimiento_id`), que es la base de todo el punto 7-9 de
    esta fase: poder demostrar qué consentimiento amparó cada aplicación.

    🔒 B-8 — Acepta `institucion_id` para exigir que el consentimiento sea
    DE ESA institución. Un consentimiento del colegio A nunca debe habilitar
    una inscripción del colegio B.
    """
    consulta = db.query(models.ConsentimientoInformado).filter(
        models.ConsentimientoInformado.persona_id == persona_id,
        models.ConsentimientoInformado.tipo_consentimiento == tipo_consentimiento,
        models.ConsentimientoInformado.revocado == False,  # noqa: E712
    )
    if institucion_id is not None:
        consulta = consulta.filter(
            models.ConsentimientoInformado.institucion_id == institucion_id
        )
    return consulta.first()


def tiene_consentimiento_vigente(
    db: Session, persona_id: int, institucion_id: Optional[int] = None,
    tipo_consentimiento: str = models.TIPO_CONSENTIMIENTO_APODERADO,
) -> bool:
    """¿Tiene esta persona un consentimiento vigente DE ESTE TIPO?

    El parámetro por defecto es "apoderado" a propósito: TODO el código que
    ya existía antes de esta fase (el candado de la matrícula por roster, el
    candado del examen en vivo) llama a esta función sin pasar
    `tipo_consentimiento`, y debe seguir comportándose EXACTAMENTE igual que
    antes de que existiera el consentimiento del estudiante — ese tipo nuevo
    es aditivo, nunca sustituye al candado ya vigente. Qué consentimiento es
    obligatorio para aplicar una prueba SÍ es ahora una política
    institucional configurable — ver `Institucion.exigir_asentimiento_estudiante`
    y su lectura en `matricular_roster_en_campana`/`consentimiento_vigente_para_inscripcion`
    (modulos/educativo/crud.py) — pero se implementa ahí, encima de esta
    función, nunca cambiando su propio parámetro por defecto.

    🔒 B-8 — Acepta `institucion_id` para exigir que el consentimiento sea
    DE ESA institución. Un consentimiento del colegio A nunca debe habilitar
    una inscripción del colegio B.
    """
    return obtener_consentimiento_vigente(db, persona_id, institucion_id, tipo_consentimiento) is not None


def revocar_consentimiento(
    db: Session, consentimiento_id: int,
    revocado_por_usuario_id: Optional[int] = None,
    ip_revocacion: Optional[str] = None,
):
    registro = db.query(models.ConsentimientoInformado).filter(
        models.ConsentimientoInformado.id == consentimiento_id
    ).first()
    if registro:
        registro.revocado = True
        registro.estado = models.ESTADO_CONSENTIMIENTO_REVOCADO
        registro.fecha_revocacion = datetime.utcnow()
        registro.revocado_por_usuario_id = revocado_por_usuario_id
        registro.ip_revocacion = ip_revocacion
        db.commit()
        db.refresh(registro)
    return registro


def revocar_consentimiento_de_persona(
    db: Session, persona_id: int, institucion_id: Optional[int] = None,
    revocado_por_usuario_id: Optional[int] = None,
    ip_revocacion: Optional[str] = None,
    tipo_consentimiento: str = models.TIPO_CONSENTIMIENTO_APODERADO,
):
    """Revoca TODOS los consentimientos vigentes DE ESE TIPO de una persona.

    Antes revocaba solo el primero que encontrase. Si por cualquier motivo
    existían dos vigentes, la revocación no surtía efecto real:
    `tiene_consentimiento_vigente` seguía devolviendo True y el alumno
    continuaba siendo evaluable pese a haber ejercido su derecho.

    No borra nada: marca cada registro como revocado con su responsable y su
    fecha, de modo que el historial queda íntegro (Ley 29733). Revocar el
    consentimiento de apoderado NO toca el del estudiante, ni al revés —
    cada uno se revoca explícitamente por su tipo.
    Devuelve el último revocado, o None si no había ninguno vigente.
    """
    consulta = db.query(models.ConsentimientoInformado).filter(
        models.ConsentimientoInformado.persona_id == persona_id,
        models.ConsentimientoInformado.tipo_consentimiento == tipo_consentimiento,
        models.ConsentimientoInformado.revocado == False,  # noqa: E712
    )
    if institucion_id is not None:
        consulta = consulta.filter(
            models.ConsentimientoInformado.institucion_id == institucion_id
        )

    vigentes = consulta.all()
    if not vigentes:
        return None

    ultimo = None
    for consentimiento in vigentes:
        ultimo = revocar_consentimiento(
            db, consentimiento.id,
            revocado_por_usuario_id=revocado_por_usuario_id,
            ip_revocacion=ip_revocacion,
        )
    return ultimo


def historial_consentimientos(
    db: Session, persona_id: int, institucion_id: Optional[int] = None,
    tipo_consentimiento: Optional[str] = None,
):
    """Historial completo (vigentes y revocados), del más reciente al más
    antiguo. `tipo_consentimiento=None` (por defecto) trae AMBOS tipos
    mezclados — lo usa la consulta combinada nueva; pásalo explícitamente
    para acotar a uno solo, como sigue haciendo el endpoint histórico de
    apoderado por compatibilidad."""
    consulta = db.query(models.ConsentimientoInformado).filter(
        models.ConsentimientoInformado.persona_id == persona_id
    )
    if institucion_id is not None:
        consulta = consulta.filter(
            models.ConsentimientoInformado.institucion_id == institucion_id
        )
    if tipo_consentimiento is not None:
        consulta = consulta.filter(
            models.ConsentimientoInformado.tipo_consentimiento == tipo_consentimiento
        )
    return consulta.order_by(models.ConsentimientoInformado.fecha_otorgamiento.desc()).all()


def _serializar_consentimiento(c: models.ConsentimientoInformado) -> dict:
    """Mismo nivel de detalle que ya exponía a mano el endpoint histórico de
    apoderado — un solo lugar que lo hace, ahora reutilizado por ambos
    tipos y por la vista combinada.

    🔧 Probado en vivo: `persona_id`/`institucion_id` faltaban aquí pese a
    que SÍ están en ConsentimientoResponse/ConsentimientoAsentimientoResponse
    (las respuestas de POST) — un consumidor que leyera ambas formas veía un
    objeto distinto según el endpoint. `evidencia_ruta` (la key interna de
    storage) se quita por el mismo motivo que en schemas.py: nunca debe
    salir en una respuesta."""
    return {
        "id": c.id,
        "persona_id": c.persona_id,
        "institucion_id": c.institucion_id,
        "tipo_consentimiento": c.tipo_consentimiento,
        "estado": c.estado,
        "otorgado_por_nombre": c.otorgado_por_nombre,
        "otorgante_apellidos": c.otorgante_apellidos,
        "otorgante_documento": c.otorgante_documento,
        "otorgante_relacion": c.otorgante_relacion,
        "tipo_otorgante": c.tipo_otorgante,
        "referencia_documento": c.referencia_documento,
        "evidencia_nombre_archivo": c.evidencia_nombre_archivo,
        "evidencia_content_type": c.evidencia_content_type,
        "evidencia_tamano_bytes": c.evidencia_tamano_bytes,
        "evidencia_subido_en": c.evidencia_subido_en,
        "fecha_otorgamiento": c.fecha_otorgamiento,
        "registrado_por_usuario_id": c.registrado_por_usuario_id,
        "ip_registro": c.ip_registro,
        "revocado": c.revocado,
        "fecha_revocacion": c.fecha_revocacion,
        "revocado_por_usuario_id": c.revocado_por_usuario_id,
        "ip_revocacion": c.ip_revocacion,
    }


def obtener_consentimientos_combinados(db: Session, persona_id: int, institucion_id: Optional[int] = None):
    """🆕 Vista combinada de los DOS consentimientos (punto 12: la consulta de
    historial debe distinguir como mínimo apoderado/estudiante). La usan
    tanto `GET /personas/{id}/consentimientos` como la ficha completa, para
    no mantener dos veces la misma composición."""
    resultado = {}
    for tipo in models.TIPOS_CONSENTIMIENTO_VALIDOS:
        resultado[tipo] = {
            "tiene_consentimiento_vigente": tiene_consentimiento_vigente(
                db, persona_id, institucion_id, tipo_consentimiento=tipo
            ),
            "historial": [
                _serializar_consentimiento(c)
                for c in historial_consentimientos(db, persona_id, institucion_id, tipo_consentimiento=tipo)
            ],
        }
    return resultado


# ==========================================
# 🏛️ BITÁCORA ARCO (B-12)
# ==========================================
def registrar_auditoria_arco(
    db: Session,
    accion: str,
    ejecutado_por,
    institucion_id: Optional[int] = None,
    persona_id: Optional[int] = None,
    inscripcion_id: Optional[int] = None,
    ip_solicitante: Optional[str] = None,
    detalle: Optional[str] = None,
):
    """Deja constancia de una acción ARCO. Solo añade, nunca modifica."""
    registro = models.RegistroAuditoriaArco(
        accion=accion,
        persona_id=persona_id,
        inscripcion_id=inscripcion_id,
        institucion_id=institucion_id,
        ejecutado_por_usuario_id=ejecutado_por.id,
        rol_ejecutor=ejecutado_por.rol,
        ip_solicitante=ip_solicitante,
        detalle=detalle,
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro

def anonimizar_persona_arco(
    db: Session, persona_id: int, institucion_id: int, es_superadmin: bool = False,
    ejecutado_por=None, ip_solicitante: Optional[str] = None,
    referencia_solicitud: Optional[str] = None,
) -> bool:
    """
    🏛 Ley 29733 - Derecho ARCO sobre el registro maestro de la Persona.
    Irreversible: borra nombre, DNI, email y fecha de nacimiento; desactiva la cuenta.

    NO es un borrado físico: la fila permanece para no romper el histórico
    psicométrico, solo se vacía la información identificable.

    🏛️ B-12 — Queda anotado en `auditoria_arco` quién ejecutó la acción, desde
    dónde y sobre quién, ANTES de perder los datos de la persona.
    """
    query = db.query(models.Persona).filter(models.Persona.id == persona_id)
    if not es_superadmin:
        query = query.filter(models.Persona.institucion_id == institucion_id)
    persona = query.first()
    if not persona:
        return False

    # La bitácora se escribe con los datos aún legibles: después ya no se
    # podría decir sobre quién se actuó.
    if ejecutado_por is not None:
        registrar_auditoria_arco(
            db, accion="anonimizacion_persona", ejecutado_por=ejecutado_por,
            institucion_id=persona.institucion_id, persona_id=persona.id,
            ip_solicitante=ip_solicitante,
            detalle=(
                f"Anonimización irreversible del registro maestro de "
                f"'{persona.nombres} {persona.apellidos}'"
                + (f". Solicitud: {referencia_solicitud}" if referencia_solicitud else "")
            ),
        )

    hash_arco = hashlib.sha256(f"ARCO_PERSONA_{persona.id}_{datetime.utcnow()}".encode()).hexdigest()[:10]
    persona.nombres = "ANONIMO"
    persona.apellidos = f"ARCO_{hash_arco}"
    persona.documento_identidad = None
    persona.email = None
    persona.fecha_nacimiento = None
    persona.activo = False
    db.commit()
    return True

def crear_cita(db: Session, cita: schemas.CitaCreate, psicologo_id: int, institucion_id: int):
    """`cita.persona_id` presente = cita individual de siempre.  Ausente =
    actividad grupal: `cita.participantes_ids`, si viene, es un roster
    OPCIONAL (puede ir vacío) de estudiantes de ESTA institución -- una
    persona de otro colegio ahí se descarta en silencio en vez de 404,
    mismo criterio que "no inventar una respuesta de error nueva para un
    campo que ni siquiera es obligatorio"."""
    nueva = models.CitaProgramada(
        persona_id=cita.persona_id,
        psicologo_id=psicologo_id,
        institucion_id=institucion_id,
        motivo=cita.motivo,
        fecha_hora=cita.fecha_hora,
        titulo=cita.titulo,
        tipo_actividad=cita.tipo_actividad,
        lugar=cita.lugar,
    )
    db.add(nueva)
    db.flush()  # necesitamos nueva.id para las filas de participantes

    if cita.participantes_ids:
        ids_unicos = set(cita.participantes_ids)
        personas_validas = db.query(models.Persona.id).filter(
            models.Persona.id.in_(ids_unicos),
            models.Persona.institucion_id == institucion_id,
        ).all()
        for (persona_id,) in personas_validas:
            db.add(models.CitaParticipante(cita_id=nueva.id, persona_id=persona_id))

    db.commit()
    db.refresh(nueva)
    return nueva

def listar_citas_del_psicologo(db: Session, psicologo_id: int, institucion_id: Optional[int] = None):
    """La agenda de un psicólogo trae SUS propias citas individuales (como
    siempre, filtradas por `psicologo_id`, privadas: ni otro psicólogo del
    mismo colegio las ve) MÁS TODAS las actividades grupales de la
    institución (`persona_id IS NULL`), las haya agendado quien sea --
    hallazgo de producto: un taller se coordina entre varios, no tiene
    sentido que solo lo vea quien lo creó.  `institucion_id=None` (p. ej.
    superadmin sin institución propia) deja el filtro de grupales vacío:
    nadie ve "todas las actividades de todas las instituciones" por
    accidente."""
    filtro_propias = models.CitaProgramada.psicologo_id == psicologo_id
    if institucion_id is not None:
        filtro_grupales = (
            models.CitaProgramada.persona_id.is_(None)
        ) & (models.CitaProgramada.institucion_id == institucion_id)
        condicion = or_(filtro_propias, filtro_grupales)
    else:
        condicion = filtro_propias

    return db.query(models.CitaProgramada).filter(
        condicion,
        models.CitaProgramada.estado == "Programada",
    ).order_by(models.CitaProgramada.fecha_hora).all()

def actualizar_cita(db: Session, cita_id: int, datos: "schemas.CitaUpdate"):
    cita = db.query(models.CitaProgramada).filter(
        models.CitaProgramada.id == cita_id
    ).first()
    if not cita:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(cita, campo, valor)
    db.commit()
    db.refresh(cita)
    return cita
 
 
def cancelar_cita(db: Session, cita_id: int):
    cita = db.query(models.CitaProgramada).filter(
        models.CitaProgramada.id == cita_id
    ).first()
    if not cita:
        return None
    cita.estado = "Cancelada"
    db.commit()
    db.refresh(cita)
    return cita
 
 
def listar_citas_por_persona(db: Session, persona_id: int):
    """Historial de un alumno: sus citas individuales de siempre MÁS las
    actividades grupales donde quedó anotado como participante (ver
    CitaParticipante) -- antes esto último no aparecía en ningún lado: un
    alumno agregado como asistente a un taller no mostraba ese taller en su
    propia ficha, pese a que el taller sí lo tenía anotado."""
    ids_como_participante = db.query(models.CitaParticipante.cita_id).filter(
        models.CitaParticipante.persona_id == persona_id
    )
    return db.query(models.CitaProgramada).filter(
        or_(
            models.CitaProgramada.persona_id == persona_id,
            models.CitaProgramada.id.in_(ids_como_participante),
        )
    ).order_by(models.CitaProgramada.fecha_hora.desc()).all()

def obtener_ficha_completa(db: Session, persona: models.Persona, usuario_actual):
    # 🔒 Remediación de permisos, paso 4 — `colegio` nunca debe ver contenido
    # clínico/psicométrico (nivel de diagnóstico, notas narrativas de
    # seguimiento), mismo criterio que el resto de esta remediación. Antes
    # este endpoint no tenía `response_model` y devolvía ambos bloques
    # verbatim para cualquier rol autenticado de la institución — ver
    # CLAUDE.md, "Permission surface: what the matrix test can't see". Se
    # cortan en el origen (ni siquiera se consultan) en vez de armarlos y
    # descartarlos después, para que no haya ninguna ruta de código donde el
    # dato clínico exista en memoria camino a la respuesta de un colegio.
    es_colegio = usuario_actual.rol == "colegio"

    historial_evaluaciones = []
    if not es_colegio:
        # Historial de evaluaciones psicométricas de este alumno, en todos los salones/campañas donde participó
        # 🔒 C-8 — La ficha activa NO debe resucitar registros que el titular
        # pidió eliminar ni evaluaciones ya anonimizadas. Antes se listaban todas
        # las inscripciones sin filtro, así que un ejercicio del derecho ARCO
        # quedaba deshecho en la práctica: el alumno reaparecía en su propia ficha.
        inscripciones = db.query(educativo_models.Inscripcion).filter(
            educativo_models.Inscripcion.persona_id == persona.id,
            educativo_models.Inscripcion.is_deleted == False,      # noqa: E712
            educativo_models.Inscripcion.is_anonymized == False,   # noqa: E712
        ).order_by(educativo_models.Inscripcion.fecha_resolucion.desc()).all()

        for insc in inscripciones:
            evaluacion = db.query(educativo_models.Evaluacion).filter(
                educativo_models.Evaluacion.id == insc.evaluacion_id
            ).first()
            prueba = db.query(educativo_models.Prueba).filter(
                educativo_models.Prueba.id == evaluacion.prueba_id
            ).first() if evaluacion else None

            diagnosticos = db.query(educativo_models.DiagnosticoAlumno, educativo_models.Dimension).join(
                educativo_models.Dimension,
                educativo_models.DiagnosticoAlumno.dimension_id == educativo_models.Dimension.id
            ).filter(educativo_models.DiagnosticoAlumno.inscripcion_id == insc.id).all()

            historial_evaluaciones.append({
                "inscripcion_id": insc.id,
                "prueba": prueba.nombre_publico if prueba else "N/A",
                "estado": insc.estado,
                "fecha_resolucion": insc.fecha_resolucion,
                "resultados": [{"dimension": dim.nombre, "nivel": diag.nivel} for diag, dim in diagnosticos],
            })

    sesiones = [] if es_colegio else educativo_crud.obtener_historial_de_persona(db=db, persona_id=persona.id)
    citas_futuras = db.query(models.CitaProgramada).filter(
        models.CitaProgramada.persona_id == persona.id,
        models.CitaProgramada.estado == "Programada",
    ).order_by(models.CitaProgramada.fecha_hora).all()
    # 🔒 B-8 — el consentimiento se comprueba acotado a SU institución.
    # Se mantiene tal cual (apoderado, por el valor por defecto del
    # parámetro) para no cambiar la forma que ya consume el frontend actual.
    tiene_consentimiento = tiene_consentimiento_vigente(
        db=db, persona_id=persona.id, institucion_id=persona.institucion_id
    )

    # 🆕 Núcleo del estudiante — información académica actual e historial.
    matricula_activa = obtener_matricula_activa(db=db, persona_id=persona.id)

    return {
        "datos_personales": {
            "id": persona.id,
            "nombres": persona.nombres,
            "apellidos": persona.apellidos,
            "codigo_institucional": persona.codigo_institucional,
            "grado_seccion": persona.grado_seccion,
        },
        "tiene_consentimiento_vigente": tiene_consentimiento,
        # 🆕 Consentimientos del estudiante/apoderado (punto 28) — vista
        # combinada de los DOS historiales independientes; "apoderado" aquí
        # es el mismo dato que `tiene_consentimiento_vigente` de arriba,
        # repetido dentro de la estructura nueva para que un consumidor
        # pueda migrar a leer solo `consentimientos` sin perder nada.
        "consentimientos": obtener_consentimientos_combinados(
            db=db, persona_id=persona.id, institucion_id=persona.institucion_id
        ),
        "informacion_academica_actual": (
            _describir_matricula(db=db, matricula=matricula_activa) if matricula_activa else None
        ),
        "historial_academico": obtener_historial_academico(db=db, persona_id=persona.id),
        "historial_evaluaciones": historial_evaluaciones,
        "sesiones_seguimiento": sesiones,
        "proximas_citas": citas_futuras,
    }


# ==========================================
# 🆕 ARCO — DERECHO DE ACCESO (exportar_datos_persona_arco)
# ==========================================
def exportar_datos_persona_arco(
    db: Session, persona: models.Persona, usuario_actual,
    ip_solicitante: Optional[str] = None, referencia_solicitud: Optional[str] = None,
    consentimiento_id: Optional[int] = None,
) -> dict:
    """
    🏛️ Ley 29733 — Derecho ARCO de ACCESO: "todo lo que se tiene" de esta
    Persona. A diferencia de `obtener_ficha_completa` (pensada para la UI de
    un colegio y que por eso redacta contenido clínico para `colegio`), este
    endpoint NUNCA lo invoca `colegio` (ver el router: `requerir_staff_clinico`)
    y por eso no redacta nada por rol — devuelve diagnósticos/informes/sesiones
    completos a superadmin/admin/psicólogo, exactamente lo que cada uno de
    esos roles ya puede ver hoy en otros endpoints de este mismo sistema.

    Lo único que SÍ se filtra por usuario, incluso aquí, es el expediente
    clínico (`EntradaExpediente`): su regla de confidencialidad (solo autor o
    superadmin) es independiente de "quién puede pedir un export" — un admin
    ejerciendo el derecho de acceso en nombre del titular no adquiere, por
    eso, acceso a notas clínicas privadas de un psicólogo que no es él. Las
    entradas que no le corresponden se OMITEN (nunca se listan ni como
    metadata), y se cuenta cuántas quedaron fuera en
    `expediente_entradas_omitidas` para que quien exporta sepa que el bundle
    no es literalmente completo para su propio usuario, sin revelar qué
    contenía lo omitido.

    Fuera de alcance a propósito (ver diseño aprobado): el motor de
    documentos institucionales (`modulos/documentos`) y el contenido binario
    de los PDF de informe — de estos últimos solo se exporta metadata/
    historial de versión, reutilizando `listar_versiones_de_informe`.

    🆕 Acotado a un consentimiento puntual (docs/gaps-pendientes.md, cierre
    del gap "ARCO scoped al propio registro de consentimiento") — cuando se
    pasa `consentimiento_id`, el titular/apoderado ejerce su derecho de
    acceso solo sobre lo que ESE consentimiento cubrió, útil cuando hay
    varios consentimientos en el tiempo (ej. uno revocado y otro vigente, o
    uno de apoderado y otro del propio estudiante) y quien pide el acceso
    solo tiene derecho/interés sobre el que él mismo firmó:
      - `inscripciones`/`informes` se recortan a las que citan ese
        consentimiento (`Inscripcion.consentimiento_apoderado_id` o
        `consentimiento_asentimiento_id` — el mismo enlace que ya escribe
        `matricular_roster_en_campana`, no una heurística nueva).
      - `consentimientos` deja de ser la vista combinada de ambos
        historiales y pasa a ser ÚNICAMENTE ese registro.
      - `datos_personales`/`informacion_academica_actual`/
        `historial_academico` NO se recortan: son identidad, no "datos
        cubiertos por un consentimiento" — existen con independencia de cuál
        esté vigente.
      - `expediente_clinico`, `sesiones_seguimiento`, `citas_programadas`,
        `datos_familiares`, `antecedentes_clinicos`, `contactos_familiares`,
        `historial_cambios_persona` y `registro_auditoria_arco_previo`
        quedan FUERA del bundle acotado a propósito: ninguna de esas tablas
        enlaza a un `ConsentimientoInformado` ni a una `Inscripcion`
        puntual, así que recortarlas exigiría inventar una heurística (por
        fecha, por ejemplo) que nadie pidió y que podría excluir u ocultar
        de más. 404 si el `consentimiento_id` no existe o no es de esta
        persona — nunca se "ignora en silencio" un id que no corresponde.

    Deja, al final, UNA fila en `auditoria_arco` (accion="acceso_datos_persona")
    — cada ejercicio de este derecho queda auditado igual que una
    anonimización, nunca en silencio.
    """
    consentimiento_filtro = None
    if consentimiento_id is not None:
        consentimiento_filtro = db.query(models.ConsentimientoInformado).filter(
            models.ConsentimientoInformado.id == consentimiento_id,
            models.ConsentimientoInformado.persona_id == persona.id,
        ).first()
        if not consentimiento_filtro:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ese consentimiento no existe o no corresponde a este estudiante.",
            )

    matricula_activa = obtener_matricula_activa(db=db, persona_id=persona.id)

    # ------------------------------------------------------------------
    # Inscripciones + diagnósticos — a diferencia de obtener_ficha_completa,
    # SIN filtrar is_deleted/is_anonymized (el titular tiene derecho a saber
    # que existieron) y con el contenido clínico completo de cada
    # DiagnosticoAlumno, no solo "nivel".
    # ------------------------------------------------------------------
    inscripciones_data = []
    inscripciones_query = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.persona_id == persona.id,
    )
    if consentimiento_filtro is not None:
        inscripciones_query = inscripciones_query.filter(
            or_(
                educativo_models.Inscripcion.consentimiento_apoderado_id == consentimiento_filtro.id,
                educativo_models.Inscripcion.consentimiento_asentimiento_id == consentimiento_filtro.id,
            )
        )
    inscripciones = inscripciones_query.order_by(educativo_models.Inscripcion.fecha_resolucion.desc()).all()

    for insc in inscripciones:
        evaluacion = db.query(educativo_models.Evaluacion).filter(
            educativo_models.Evaluacion.id == insc.evaluacion_id
        ).first()
        prueba = db.query(educativo_models.Prueba).filter(
            educativo_models.Prueba.id == evaluacion.prueba_id
        ).first() if evaluacion else None

        diagnosticos = db.query(educativo_models.DiagnosticoAlumno, educativo_models.Dimension).join(
            educativo_models.Dimension,
            educativo_models.DiagnosticoAlumno.dimension_id == educativo_models.Dimension.id
        ).filter(educativo_models.DiagnosticoAlumno.inscripcion_id == insc.id).all()

        inscripciones_data.append({
            "inscripcion_id": insc.id,
            "prueba": prueba.nombre_publico if prueba else None,
            "estado": insc.estado,
            "fecha_resolucion": insc.fecha_resolucion,
            "is_deleted": insc.is_deleted,
            "is_anonymized": insc.is_anonymized,
            "grado_seccion_historico": insc.grado_seccion_historico,
            "motivo_consulta": insc.motivo_consulta,
            "observacion_conductual": insc.observacion_conductual,
            "conclusion_override": insc.conclusion_override,
            "recomendaciones_override": insc.recomendaciones_override,
            "estado_interpretacion": insc.estado_interpretacion,
            "dimensiones_sin_baremo": insc.dimensiones_sin_baremo,
            "reglas_con_error": insc.reglas_con_error,
            "informe_liberado": insc.informe_liberado,
            "consentimiento_apoderado_id": insc.consentimiento_apoderado_id,
            "consentimiento_asentimiento_id": insc.consentimiento_asentimiento_id,
            "diagnosticos": [
                {
                    "dimension": dim.nombre,
                    "nivel": diag.nivel,
                    "valor_convertido": diag.valor_convertido,
                    "interpretacion": diag.interpretacion,
                    "conclusion_sugerida": diag.conclusion_sugerida,
                    "recomendacion_sugerida": diag.recomendacion_sugerida,
                    "rango_minimo": diag.rango_minimo,
                    "rango_maximo": diag.rango_maximo,
                    "es_alerta": diag.es_alerta,
                    "alerta_por": diag.alerta_por,
                }
                for diag, dim in diagnosticos
            ],
        })

    # ------------------------------------------------------------------
    # Informes — solo metadata/historial de versión (nunca el PDF binario).
    # ------------------------------------------------------------------
    informes_data = educativo_crud.listar_historial_informes_de_persona(
        db, persona_id=persona.id, institucion_id=persona.institucion_id,
    )
    if consentimiento_filtro is not None:
        ids_inscripciones_filtradas = {insc.id for insc in inscripciones}
        informes_data = [f for f in informes_data if f["inscripcion_id"] in ids_inscripciones_filtradas]
    for fila in informes_data:
        versiones = educativo_crud.listar_versiones_de_informe(db, informe_id=fila["informe_id"])
        fila["versiones"] = [
            {
                "numero_version": v.numero_version,
                "generado_en": v.generado_en,
                "motivo_version": v.motivo_version,
                "generado_por_usuario_id": v.generado_por_usuario_id,
                "nombre_archivo": v.nombre_archivo,
                "tamano_bytes": v.tamano_bytes,
            }
            for v in versiones
        ]

    # ------------------------------------------------------------------
    # Expediente clínico — SOLO lo que este usuario puede leer. Reutiliza la
    # misma regla de acceso y el mismo registro de lectura que ya usa el
    # endpoint de detalle: cada entrada incluida aquí deja también su fila en
    # `RegistroLecturasExpediente`, exactamente como si se hubiera abierto una
    # por una.
    # ------------------------------------------------------------------
    # 🆕 Cuando el export está acotado a un consentimiento puntual, ninguna
    # de estas tres tablas enlaza a un ConsentimientoInformado ni a una
    # Inscripcion concreta — se omiten del bundle (ver docstring) en vez de
    # consultarlas para descartarlas después, mismo criterio que ya usa este
    # archivo para "colegio" en obtener_ficha_completa.
    if consentimiento_filtro is None:
        todas_las_entradas = db.query(models.EntradaExpediente).filter(
            models.EntradaExpediente.persona_id == persona.id,
        ).order_by(models.EntradaExpediente.fecha_entrada.desc()).all()
        entradas_visibles = [
            e for e in todas_las_entradas
            if usuario_puede_ver_contenido_completo(db, e, usuario_actual)[0]
        ]
        expediente_data = [
            obtener_detalle_entrada_expediente(db=db, entrada=e, usuario_actual=usuario_actual, ip_lectura=ip_solicitante)
            for e in entradas_visibles
        ]

        # Citas — TODAS (pasadas y futuras), a diferencia de ficha-completa
        # que solo lista las "Programadas" próximas.
        citas = db.query(models.CitaProgramada).filter(
            models.CitaProgramada.persona_id == persona.id,
        ).order_by(models.CitaProgramada.fecha_hora.desc()).all()

    resultado = {
        "datos_personales": {
            "id": persona.id,
            "institucion_id": persona.institucion_id,
            "tipo_perfil": persona.tipo_perfil,
            "nombres": persona.nombres,
            "apellidos": persona.apellidos,
            "documento_identidad": persona.documento_identidad,
            "codigo_institucional": persona.codigo_institucional,
            "email": persona.email,
            "fecha_nacimiento": persona.fecha_nacimiento,
            "genero": persona.genero,
            "grado_seccion": persona.grado_seccion,
            "condicion_matricula": persona.condicion_matricula,
            "activo": persona.activo,
            "fecha_registro": persona.fecha_registro,
        },
        "informacion_academica_actual": (
            _describir_matricula(db=db, matricula=matricula_activa) if matricula_activa else None
        ),
        "historial_academico": obtener_historial_academico(db=db, persona_id=persona.id),
        "consentimientos": (
            {"acotado_a_un_consentimiento": _serializar_consentimiento(consentimiento_filtro)}
            if consentimiento_filtro is not None
            else obtener_consentimientos_combinados(
                db=db, persona_id=persona.id, institucion_id=persona.institucion_id
            )
        ),
        "inscripciones": inscripciones_data,
        "informes": informes_data,
    }
    if consentimiento_filtro is None:
        resultado.update({
            "datos_familiares": obtener_datos_familiares(db=db, persona_id=persona.id),
            "antecedentes_clinicos": obtener_antecedentes_clinicos(db=db, persona_id=persona.id),
            "contactos_familiares": listar_contactos_de_persona(db=db, persona_id=persona.id, incluir_inactivos=True),
            "sesiones_seguimiento": educativo_crud.obtener_historial_de_persona(db=db, persona_id=persona.id),
            "citas_programadas": citas,
            "expediente_clinico": expediente_data,
            "expediente_entradas_omitidas": len(todas_las_entradas) - len(entradas_visibles),
            "historial_cambios_persona": listar_historial_cambios_persona(db=db, persona_id=persona.id),
            "registro_auditoria_arco_previo": db.query(models.RegistroAuditoriaArco).filter(
                models.RegistroAuditoriaArco.persona_id == persona.id,
            ).order_by(models.RegistroAuditoriaArco.fecha.desc()).all(),
        })

    registrar_auditoria_arco(
        db, accion="acceso_datos_persona", ejecutado_por=usuario_actual,
        institucion_id=persona.institucion_id, persona_id=persona.id,
        ip_solicitante=ip_solicitante,
        detalle=(
            "Exportación ARCO de datos del registro."
            + (f" Acotada al consentimiento #{consentimiento_filtro.id}." if consentimiento_filtro is not None else "")
            + (f" Solicitud: {referencia_solicitud}" if referencia_solicitud else "")
        ),
    )
    return resultado


# ==========================================
# 🆕 VISTA DE COMPARACIÓN HISTÓRICA ENTRE CAMPAÑAS
# (cierre de gap — docs/gaps-pendientes.md, "ARCO ... vista de comparación
# histórica entre campañas")
# ==========================================
def historico_campanas_de_persona(db: Session, persona: models.Persona) -> dict:
    """Evolución de un estudiante a través de TODAS las campañas en las que
    participó, para el equipo clínico (nunca 'colegio' — ver
    `requerir_staff_clinico` en el router). A diferencia de
    `exportar_datos_persona_arco` (un derecho legal de acceso que no filtra
    is_deleted/is_anonymized porque el titular tiene derecho a saber que
    existieron), esta es una vista de TRABAJO: mismo criterio que
    `obtener_ficha_completa` de no resucitar inscripciones borradas o
    anonimizadas por ARCO.

    Devuelve dos formas del mismo dato:
      - `evaluaciones`: lista cronológica ASCENDENTE (para leerla de
        izquierda a derecha como una línea de tiempo), una entrada por
        inscripción con sus diagnósticos completos.
      - `comparacion_por_dimension`: la mismísima información, reagrupada
        por nombre de dimensión, cada una con su propia serie ASCENDENTE de
        {campaña, fecha, nivel, valor_convertido, es_alerta} — la forma que
        de verdad responde "¿cómo cambió su puntaje de depresión entre la
        campaña de marzo y la de agosto?" sin que quien consume esto tenga
        que recorrer `evaluaciones` buscando una dimensión a mano.
    """
    inscripciones = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.persona_id == persona.id,
        educativo_models.Inscripcion.is_deleted == False,      # noqa: E712
        educativo_models.Inscripcion.is_anonymized == False,   # noqa: E712
    ).order_by(educativo_models.Inscripcion.fecha_resolucion.asc()).all()

    evaluaciones = []
    comparacion_por_dimension: dict = {}

    for insc in inscripciones:
        evaluacion = db.query(educativo_models.Evaluacion).filter(
            educativo_models.Evaluacion.id == insc.evaluacion_id
        ).first()
        prueba = db.query(educativo_models.Prueba).filter(
            educativo_models.Prueba.id == evaluacion.prueba_id
        ).first() if evaluacion else None

        diagnosticos = db.query(educativo_models.DiagnosticoAlumno, educativo_models.Dimension).join(
            educativo_models.Dimension,
            educativo_models.DiagnosticoAlumno.dimension_id == educativo_models.Dimension.id
        ).filter(educativo_models.DiagnosticoAlumno.inscripcion_id == insc.id).all()

        nombre_campana = evaluacion.nombre_grupo if evaluacion else None

        # 🆕 Estado del informe — para que la ficha del estudiante ("Pruebas
        # aplicadas"/"Instrumentos aplicados") sepa de un vistazo si ya hay
        # un PDF generado, si está retenido para revisión, y pueda enlazar
        # directo a verlo/revisarlo sin que el frontend tenga que adivinar.
        informe = db.query(educativo_models.Informe).filter(
            educativo_models.Informe.inscripcion_id == insc.id
        ).first()

        evaluaciones.append({
            "inscripcion_id": insc.id,
            "campana": nombre_campana,
            "prueba": prueba.nombre_publico if prueba else None,
            "fecha_resolucion": insc.fecha_resolucion,
            "estado": insc.estado,
            "tiene_informe": informe is not None,
            "informe_liberado": insc.informe_liberado,
            "resultado_visible_alumno": insc.resultado_visible_alumno,
            "diagnosticos": [
                {
                    "dimension": dim.nombre,
                    "nivel": diag.nivel,
                    "valor_convertido": diag.valor_convertido,
                    "es_alerta": diag.es_alerta,
                    "interpretacion": diag.interpretacion,
                }
                for diag, dim in diagnosticos
            ],
        })

        for diag, dim in diagnosticos:
            comparacion_por_dimension.setdefault(dim.nombre, []).append({
                "inscripcion_id": insc.id,
                "campana": nombre_campana,
                "fecha_resolucion": insc.fecha_resolucion,
                "nivel": diag.nivel,
                "valor_convertido": diag.valor_convertido,
                "es_alerta": diag.es_alerta,
            })

    return {
        "persona_id": persona.id,
        "evaluaciones": evaluaciones,
        "comparacion_por_dimension": comparacion_por_dimension,
    }


# ==========================================
# 🆕 NÚCLEO DEL ESTUDIANTE — ESTRUCTURA ACADÉMICA
# ==========================================
def crear_nivel_educativo(db: Session, datos: schemas.NivelEducativoCreate):
    nuevo = models.NivelEducativo(
        institucion_id=datos.institucion_id, nombre=datos.nombre, orden=datos.orden,
    )
    db.add(nuevo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un nivel educativo llamado '{datos.nombre}' en esta institución.",
        )
    db.refresh(nuevo)
    return nuevo


def listar_niveles_de_institucion(db: Session, institucion_id: int):
    return db.query(models.NivelEducativo).filter(
        models.NivelEducativo.institucion_id == institucion_id,
        models.NivelEducativo.activo == True,  # noqa: E712
    ).order_by(models.NivelEducativo.orden, models.NivelEducativo.nombre).all()


def crear_grado(db: Session, datos: schemas.GradoCreate):
    # 🔒 institucion_id se deriva del nivel, nunca de un campo que el
    # frontend pudiera hacer no coincidir con el nivel real.
    nivel = db.query(models.NivelEducativo).filter(
        models.NivelEducativo.id == datos.nivel_educativo_id
    ).first()
    if not nivel:
        raise HTTPException(status_code=404, detail="Nivel educativo no encontrado.")

    nuevo = models.Grado(
        institucion_id=nivel.institucion_id,
        nivel_educativo_id=nivel.id,
        nombre=datos.nombre,
        orden=datos.orden,
    )
    db.add(nuevo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un grado llamado '{datos.nombre}' en ese nivel educativo.",
        )
    db.refresh(nuevo)
    return nuevo


def listar_grados_de_nivel(db: Session, nivel_educativo_id: int):
    return db.query(models.Grado).filter(
        models.Grado.nivel_educativo_id == nivel_educativo_id,
        models.Grado.activo == True,  # noqa: E712
    ).order_by(models.Grado.orden, models.Grado.nombre).all()


def crear_seccion(db: Session, datos: schemas.SeccionCreate):
    # 🔒 institucion_id se deriva del grado, mismo criterio que crear_grado.
    grado = db.query(models.Grado).filter(models.Grado.id == datos.grado_id).first()
    if not grado:
        raise HTTPException(status_code=404, detail="Grado no encontrado.")

    nueva = models.Seccion(
        institucion_id=grado.institucion_id,
        grado_id=grado.id,
        nombre=datos.nombre,
        turno=datos.turno,
        anio_escolar=datos.anio_escolar,
    )
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe la sección '{datos.nombre}' para ese grado en el "
                f"año escolar {datos.anio_escolar}."
            ),
        )
    db.refresh(nueva)
    return nueva


def listar_secciones_de_grado(db: Session, grado_id: int, anio_escolar: Optional[int] = None):
    query = db.query(models.Seccion).filter(
        models.Seccion.grado_id == grado_id,
        models.Seccion.activo == True,  # noqa: E712
    )
    if anio_escolar is not None:
        query = query.filter(models.Seccion.anio_escolar == anio_escolar)
    return query.order_by(models.Seccion.anio_escolar.desc(), models.Seccion.nombre).all()


def _aplicar_edicion_estructura(db: Session, objeto, cambios: dict, detalle_conflicto: str):
    """Aplica un PATCH de nivel/grado/sección. Comparte con crear_* el mismo
    manejo de la restricción única de nombre (IntegrityError → 409)."""
    if "nombre" in cambios:
        nombre = (cambios["nombre"] or "").strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre no puede quedar vacío.")
        cambios["nombre"] = nombre
    if "turno" in cambios:
        cambios["turno"] = (cambios["turno"] or "").strip() or None
    for campo, valor in cambios.items():
        setattr(objeto, campo, valor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle_conflicto)
    db.refresh(objeto)
    return objeto


def actualizar_nivel_educativo(db: Session, nivel: models.NivelEducativo, datos: schemas.NivelEducativoUpdate):
    cambios = datos.model_dump(exclude_unset=True)
    return _aplicar_edicion_estructura(
        db, nivel, cambios,
        f"Ya existe un nivel educativo llamado '{(cambios.get('nombre') or '').strip()}' en esta institución.",
    )


def actualizar_grado(db: Session, grado: models.Grado, datos: schemas.GradoUpdate):
    cambios = datos.model_dump(exclude_unset=True)
    return _aplicar_edicion_estructura(
        db, grado, cambios,
        f"Ya existe un grado llamado '{(cambios.get('nombre') or '').strip()}' en ese nivel educativo.",
    )


def actualizar_seccion(db: Session, seccion: models.Seccion, datos: schemas.SeccionUpdate):
    cambios = datos.model_dump(exclude_unset=True)
    return _aplicar_edicion_estructura(
        db, seccion, cambios,
        (
            f"Ya existe la sección '{(cambios.get('nombre') or '').strip()}' para ese grado en el "
            f"año escolar {seccion.anio_escolar}."
        ),
    )


# 🆕 Eliminación (DELETE, sesión 2026-10-29) — borrado FÍSICO, pero solo de
# algo que nadie usa todavía (típicamente un error de tipeo recién creado).
# Si un nivel tiene grados, un grado tiene secciones, o una sección tiene
# matrículas (aunque sean históricas) o inscripciones a campañas, se rechaza
# con 409 explicando qué lo bloquea: borrarla rompería el historial académico
# y los snapshots de evaluaciones ya aplicadas. Otras referencias menos
# comunes (documentos institucionales, procesos de promoción) las ataja la
# propia FK → IntegrityError → mismo 409.
def _borrar_elemento_estructura(db: Session, objeto, etiqueta: str):
    db.delete(objeto)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar {etiqueta}: está referenciado por documentos o procesos de promoción.",
        )


def eliminar_nivel_educativo(db: Session, nivel: models.NivelEducativo):
    grados = db.query(models.Grado).filter(models.Grado.nivel_educativo_id == nivel.id).count()
    if grados:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar '{nivel.nombre}': tiene {grados} grado(s). Elimínalos primero.",
        )
    _borrar_elemento_estructura(db, nivel, f"el nivel '{nivel.nombre}'")


def eliminar_grado(db: Session, grado: models.Grado):
    secciones = db.query(models.Seccion).filter(models.Seccion.grado_id == grado.id).count()
    if secciones:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No se puede eliminar el grado '{grado.nombre}': tiene {secciones} sección(es). Elimínalas primero.",
        )
    _borrar_elemento_estructura(db, grado, f"el grado '{grado.nombre}'")


def eliminar_seccion(db: Session, seccion: models.Seccion):
    matriculas = db.query(models.MatriculaAcademica).filter(models.MatriculaAcademica.seccion_id == seccion.id).count()
    if matriculas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar la sección '{seccion.nombre}': tiene {matriculas} matrícula(s) "
                "(actuales o históricas). Mueve a los alumnos a otra sección antes."
            ),
        )
    inscripciones = db.query(educativo_models.Inscripcion).filter(
        educativo_models.Inscripcion.seccion_id == seccion.id
    ).count()
    if inscripciones:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar la sección '{seccion.nombre}': {inscripciones} evaluación(es) "
                "aplicada(s) quedaron registradas con ella."
            ),
        )
    _borrar_elemento_estructura(db, seccion, f"la sección '{seccion.nombre}'")


def matricular_persona_en_seccion(
    db: Session, persona: models.Persona, seccion_id: int, usuario_id: Optional[int] = None,
    commit: bool = True,
):
    """Asigna (o mueve) a una persona a una sección.

    Nunca reescribe una matrícula existente: si había una vigente, la cierra
    (`fecha_fin = ahora`) y abre una nueva. El historial completo queda
    intacto y las evaluaciones ya aplicadas —que copiaron la sección vigente
    en su momento— no se alteran.

    `commit=False` es para un llamador que ya administra su propia
    transacción por lotes (p. ej. `aplicar_importacion`): hacer `commit()`
    aquí adentro rompería su atomicidad, ya que confirmaría en disco no solo
    esta matrícula sino también cualquier fila anterior del mismo lote que
    aún solo estuviera con `flush()`. El caller por lotes hace `flush()` y
    confirma (o revierte) todo junto al final — y ya traduce su propio
    `IntegrityError` a 409 (ver `aplicar_importacion`), así que no se repite
    aquí para ese camino.

    🔒 Auditoría de concurrencia (ver `PLAN_REMODELACION_ARQUITECTURA.md`,
    sección 1.3) — el camino `commit=True` (alta manual vía
    `POST /personas/{id}/matricula`) no tenía ningún `try/except
    IntegrityError` propio: dos solicitudes casi simultáneas para matricular
    a la MISMA persona (dos clics, o una reintentada por el frontend)
    ambas podían leer "sin matrícula vigente" y ambas intentar insertar una
    fila `fecha_fin IS NULL` — la segunda choca contra el índice único
    parcial `uq_matricula_activa_por_persona` con un `IntegrityError` crudo
    (500) en vez de un 409 explicado. Cerrado con `commit_o_conflicto`.
    """
    seccion = db.query(models.Seccion).filter(models.Seccion.id == seccion_id).first()
    if not seccion:
        raise HTTPException(status_code=404, detail="Sección no encontrada.")

    # 🔒 Nunca confíes en que seccion_id pertenece a la institución de la
    # persona solo porque así lo mandó el frontend: se revalida en BD.
    if seccion.institucion_id != persona.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esa sección no pertenece a la institución de este alumno.",
        )

    # 🆕 Pendiente detectado en la fase anterior (Núcleo del Estudiante,
    # punto 11) — la estructura académica es conceptualmente de estudiantes;
    # antes nada impedía matricular en una sección a un paciente o candidato
    # (`tipo_perfil` distinto de "estudiante"), aunque esos perfiles no
    # tienen por qué tener grado/sección.
    if persona.tipo_perfil != "estudiante":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Solo se puede matricular en una sección a personas con "
                f"tipo_perfil='estudiante' (esta persona es '{persona.tipo_perfil}')."
            ),
        )

    activa = obtener_matricula_activa(db=db, persona_id=persona.id)
    if activa:
        if activa.seccion_id == seccion_id:
            return activa  # ya está ahí: no genera un tramo de historial vacío
        activa.fecha_fin = datetime.now(timezone.utc)

    nueva = models.MatriculaAcademica(
        persona_id=persona.id,
        institucion_id=persona.institucion_id,
        seccion_id=seccion_id,
        registrado_por_usuario_id=usuario_id,
    )
    db.add(nueva)
    if commit:
        commit_o_conflicto(
            db,
            "Esta persona ya tiene una matrícula vigente registrada al mismo tiempo "
            "desde otra solicitud. Vuelve a intentarlo.",
        )
        db.refresh(nueva)
    else:
        db.flush()
    return nueva


def obtener_matricula_activa(db: Session, persona_id: int):
    return db.query(models.MatriculaAcademica).filter(
        models.MatriculaAcademica.persona_id == persona_id,
        models.MatriculaAcademica.fecha_fin.is_(None),
    ).first()


def _describir_matricula(db: Session, matricula: models.MatriculaAcademica) -> dict:
    """Resuelve una matrícula a las etiquetas legibles (sección/grado/nivel)
    vigentes EN ESTE MOMENTO. Se usa tanto para "actual" como para cada fila
    del historial; para una matrícula cerrada esto muestra el nombre actual
    de esa sección, no uno "congelado" — a diferencia del snapshot de texto
    que sí se guarda en Inscripcion.grado_seccion_historico, que es
    deliberadamente inmutable."""
    seccion = db.query(models.Seccion).filter(models.Seccion.id == matricula.seccion_id).first()
    grado = db.query(models.Grado).filter(models.Grado.id == seccion.grado_id).first() if seccion else None
    nivel = (
        db.query(models.NivelEducativo).filter(models.NivelEducativo.id == grado.nivel_educativo_id).first()
        if grado else None
    )
    return {
        "matricula_id": matricula.id,
        "seccion_id": matricula.seccion_id,
        "seccion": seccion.nombre if seccion else None,
        "turno": seccion.turno if seccion else None,
        "anio_escolar": seccion.anio_escolar if seccion else None,
        "grado_id": grado.id if grado else None,
        "grado": grado.nombre if grado else None,
        "nivel_educativo_id": nivel.id if nivel else None,
        "nivel_educativo": nivel.nombre if nivel else None,
        "fecha_inicio": matricula.fecha_inicio,
        "fecha_fin": matricula.fecha_fin,
    }


def obtener_historial_academico(db: Session, persona_id: int):
    """Todas las matrículas de la persona, más antigua primero — la línea de
    tiempo completa (p. ej. 2025→2°A, 2026→3°B) sin que mover de sección
    haya alterado ninguna fila anterior."""
    matriculas = db.query(models.MatriculaAcademica).filter(
        models.MatriculaAcademica.persona_id == persona_id,
    ).order_by(models.MatriculaAcademica.fecha_inicio).all()
    return [_describir_matricula(db=db, matricula=m) for m in matriculas]


def buscar_persona_por_codigo(db: Session, institucion_id: int, codigo_institucional: str):
    """🆕 Búsqueda por el identificador funcional del punto 5 — el que usarán
    la importación Excel y la actualización masiva, nunca el DNI."""
    return db.query(models.Persona).filter(
        models.Persona.institucion_id == institucion_id,
        models.Persona.codigo_institucional == codigo_institucional,
    ).first()


# ==========================================
# 🆕 PROMOCIÓN ANUAL DE ESTUDIANTES
# ==========================================
# Flujo (validar/previsualizar/confirmar, mismo patrón que la importación
# Excel): `iniciar_proceso_promocion` calcula el mapeo automático de TODOS
# los estudiantes con matrícula vigente en el año de origen y lo persiste
# como un ProcesoPromocion 'borrador' + una fila ProcesoPromocionDetalle por
# estudiante (a diferencia de Excel, aquí SÍ conviene persistir el borrador:
# revisar el cierre de año de todo un colegio es trabajo de varias sesiones,
# no un solo POST). `editar_detalles_promocion` permite marcar excepciones
# individualmente o en lote mientras el proceso siga en 'borrador'.
# `confirmar_proceso_promocion` re-deriva y re-valida cada fila desde la BD
# (nunca confía en lo que quedó calculado al crear el borrador) y aplica
# todo en una sola transacción.
#
# Nada de esto toca Inscripcion/DiagnosticoAlumno/Informe: solo escribe
# MatriculaAcademica (nuevas filas) y Persona.condicion_matricula. Los
# snapshots que ya protegen el histórico (Inscripcion.seccion_id/
# grado_seccion_historico) siguen siendo ajenos a MatriculaAcademica, así que
# ninguna evaluación pasada puede verse afectada por este proceso.

TIPO_EXCEPCION_NINGUNA = "ninguna"
TIPO_EXCEPCION_REPITENTE = "repitente"
TIPO_EXCEPCION_RETIRADO = "retirado"
TIPO_EXCEPCION_TRASLADADO = "trasladado"
TIPO_EXCEPCION_CAMBIO_MANUAL = "cambio_manual"
TIPO_EXCEPCION_EGRESO = "egreso"
TIPOS_EXCEPCION_VALIDOS = (
    TIPO_EXCEPCION_NINGUNA, TIPO_EXCEPCION_REPITENTE, TIPO_EXCEPCION_RETIRADO,
    TIPO_EXCEPCION_TRASLADADO, TIPO_EXCEPCION_CAMBIO_MANUAL, TIPO_EXCEPCION_EGRESO,
)

# Excepciones que NUNCA abren una matrícula nueva — solo cierran la de
# origen. Cualquier otro tipo_excepcion sí necesita una seccion_definitiva_id.
EXCEPCIONES_SIN_MATRICULA_NUEVA = (
    TIPO_EXCEPCION_RETIRADO, TIPO_EXCEPCION_TRASLADADO, TIPO_EXCEPCION_EGRESO,
)

# Por qué se abre la matrícula nueva (MatriculaAcademica.motivo_apertura) —
# ver el CHECK del modelo. 'promocion' cubre tanto el mapeo automático como
# una fila corregida manualmente a un destino distinto (cambio_manual): en
# ambos casos el estudiante SÍ avanza, solo cambia quién decidió el destino.
MOTIVO_APERTURA_POR_EXCEPCION = {
    TIPO_EXCEPCION_NINGUNA: "promocion",
    TIPO_EXCEPCION_REPITENTE: "repitencia",
    TIPO_EXCEPCION_CAMBIO_MANUAL: "cambio_manual",
}
# Por qué se cierra la matrícula de origen (MatriculaAcademica.motivo_cierre).
# Para las tres excepciones que SÍ abren matrícula nueva, el cierre del
# origen siempre es 'promocion': la razón de fondo por la que el tramo
# anterior terminó es el cierre de año, sin importar si el destino fue el
# automático, una repitencia o una corrección manual.
MOTIVO_CIERRE_POR_EXCEPCION = {
    TIPO_EXCEPCION_NINGUNA: "promocion",
    TIPO_EXCEPCION_REPITENTE: "promocion",
    TIPO_EXCEPCION_CAMBIO_MANUAL: "promocion",
    TIPO_EXCEPCION_RETIRADO: "retiro",
    TIPO_EXCEPCION_TRASLADADO: "traslado",
    TIPO_EXCEPCION_EGRESO: "egreso",
}
CONDICION_MATRICULA_POR_EXCEPCION = {
    TIPO_EXCEPCION_RETIRADO: "retirado",
    TIPO_EXCEPCION_TRASLADADO: "trasladado",
    TIPO_EXCEPCION_EGRESO: "egresado",
}


def _grados_activos_ordenados(db: Session, nivel_educativo_id: int):
    return db.query(models.Grado).filter(
        models.Grado.nivel_educativo_id == nivel_educativo_id,
        models.Grado.activo == True,  # noqa: E712
    ).order_by(models.Grado.orden).all()


def _niveles_activos_ordenados(db: Session, institucion_id: int):
    return db.query(models.NivelEducativo).filter(
        models.NivelEducativo.institucion_id == institucion_id,
        models.NivelEducativo.activo == True,  # noqa: E712
    ).order_by(models.NivelEducativo.orden).all()


def _siguiente_por_orden(items, orden_actual):
    """De una lista de filas con `.orden` (grados de un nivel, o niveles de
    una institución), devuelve (siguiente, advertencia): la fila con el
    'orden' inmediatamente superior a `orden_actual`.

    La ambigüedad se mide SOLO sobre ese grupo inmediato — un 'orden'
    duplicado en cualquier OTRA parte de la lista (dos grados sin relación
    con el destino de este estudiante) no debe bloquear una sucesión que en
    realidad es perfectamente clara. Solo cuenta como ambiguo cuando hay más
    de una fila compitiendo por ser "la siguiente".
    """
    posteriores = [item for item in items if item.orden > orden_actual]
    if not posteriores:
        return None, None  # No hay nada después: fin de la estructura, caso esperado.
    orden_minimo = min(item.orden for item in posteriores)
    candidatos = [item for item in posteriores if item.orden == orden_minimo]
    if len(candidatos) > 1:
        return None, (
            f"Hay {len(candidatos)} filas con el mismo 'orden' ({orden_minimo}) "
            f"inmediatamente después: no se puede determinar cuál es la "
            f"siguiente automáticamente. Corrige el 'orden' o elige el destino "
            f"manualmente para este estudiante."
        )
    return candidatos[0], None


def resolver_grado_siguiente(db: Session, grado_actual: models.Grado):
    """El corazón del algoritmo de mapeo automático: (grado_destino,
    advertencia). Primero busca el siguiente grado por `orden` DENTRO del
    mismo nivel; si el grado actual ya es el último de su nivel, busca el
    PRIMER grado del siguiente nivel educativo por `orden` — así
    inicial→primaria y primaria→secundaria son el mismo caso que avanzar de
    grado, no una rama aparte. Si tampoco hay nivel siguiente, no hay grado
    destino: es un egreso (fin de la estructura académica).

    Nunca adivina ante ambigüedad real (dos filas empatadas por ser "la
    siguiente") — ver `_siguiente_por_orden`.
    """
    if not grado_actual.activo:
        return None, "El grado actual del estudiante ya no está activo; elige el destino manualmente."

    grados_nivel = _grados_activos_ordenados(db, grado_actual.nivel_educativo_id)
    grado_destino, advertencia = _siguiente_por_orden(grados_nivel, grado_actual.orden)
    if advertencia:
        return None, advertencia
    if grado_destino is not None:
        return grado_destino, None

    # Último grado del nivel: buscar el siguiente NIVEL educativo.
    nivel_actual = db.query(models.NivelEducativo).filter(
        models.NivelEducativo.id == grado_actual.nivel_educativo_id,
    ).first()
    if not nivel_actual or not nivel_actual.activo:
        return None, "El nivel educativo actual ya no está activo; elige el destino manualmente."

    niveles = _niveles_activos_ordenados(db, grado_actual.institucion_id)
    nivel_destino, advertencia = _siguiente_por_orden(niveles, nivel_actual.orden)
    if advertencia:
        return None, advertencia
    if nivel_destino is None:
        return None, None  # Fin de la estructura académica -> egreso, caso esperado, sin advertencia.

    grados_nivel_destino = _grados_activos_ordenados(db, nivel_destino.id)
    if not grados_nivel_destino:
        return None, (
            f"El nivel '{nivel_destino.nombre}' no tiene ningún grado activo "
            f"creado todavía: créalo antes de promover, o elige el destino "
            f"manualmente para este estudiante."
        )
    primer_orden = min(g.orden for g in grados_nivel_destino)
    primeros = [g for g in grados_nivel_destino if g.orden == primer_orden]
    if len(primeros) > 1:
        return None, (
            f"El nivel '{nivel_destino.nombre}' tiene {len(primeros)} grados "
            f"empatados con el 'orden' más bajo ({primer_orden}): no se puede "
            f"determinar cuál es el primer grado automáticamente. Corrige el "
            f"'orden' o elige el destino manualmente para este estudiante."
        )
    return primeros[0], None


def resolver_seccion_destino(db: Session, grado_destino_id: int, seccion_actual: models.Seccion, anio_destino: int):
    """Sección del grado/año destino con el mismo nombre que la actual.
    `nombre` es único por grado+año (uq_secciones_grado_nombre_anio), así que
    si hay coincidencia es la única posible — nunca hay que desambiguar por
    turno. Si no existe ninguna, la fila queda con grado resuelto pero
    sección pendiente de elegir manualmente (la sección destino DEBE
    preexistir; esta función nunca crea una)."""
    return db.query(models.Seccion).filter(
        models.Seccion.grado_id == grado_destino_id,
        models.Seccion.anio_escolar == anio_destino,
        models.Seccion.nombre == seccion_actual.nombre,
        models.Seccion.activo == True,  # noqa: E712
    ).first()


def calcular_propuesta_promocion(db: Session, matricula_origen: models.MatriculaAcademica, anio_destino: int) -> dict:
    """Propuesta automática para UNA matrícula de origen. Solo calcula, no
    escribe nada. Devuelve {"tipo": "grado_siguiente"|"egreso"|"manual",
    "seccion_propuesta_id": int|None, "advertencia": str|None}."""
    seccion_actual = db.query(models.Seccion).filter(models.Seccion.id == matricula_origen.seccion_id).first()
    if not seccion_actual:
        return {"tipo": "manual", "seccion_propuesta_id": None, "advertencia": "La sección de origen ya no existe."}
    grado_actual = db.query(models.Grado).filter(models.Grado.id == seccion_actual.grado_id).first()
    if not grado_actual:
        return {"tipo": "manual", "seccion_propuesta_id": None, "advertencia": "El grado de origen ya no existe."}

    grado_destino, advertencia = resolver_grado_siguiente(db, grado_actual)
    if advertencia:
        return {"tipo": "manual", "seccion_propuesta_id": None, "advertencia": advertencia}
    if grado_destino is None:
        return {"tipo": "egreso", "seccion_propuesta_id": None, "advertencia": None}

    seccion_destino = resolver_seccion_destino(db, grado_destino.id, seccion_actual, anio_destino)
    if seccion_destino is None:
        return {
            "tipo": "manual",
            "seccion_propuesta_id": None,
            "advertencia": (
                f"El grado destino ('{grado_destino.nombre}') se resolvió, pero no "
                f"existe una sección '{seccion_actual.nombre}' para el año "
                f"{anio_destino} en ese grado. Créala primero, o elige el destino "
                f"manualmente."
            ),
        }
    return {"tipo": "grado_siguiente", "seccion_propuesta_id": seccion_destino.id, "advertencia": None}


def _matriculas_activas_del_anio(db: Session, institucion_id: int, anio_escolar: int):
    """Candidatos a promoción: personas con matrícula VIGENTE cuya sección es
    del año de origen. Si una persona ya fue promovida (su matrícula
    vigente ya es de otro año), deja de ser candidata automáticamente — esto
    es lo que hace idempotente reintentar el mismo año de origen."""
    return (
        db.query(models.MatriculaAcademica)
        .join(models.Seccion, models.Seccion.id == models.MatriculaAcademica.seccion_id)
        .filter(
            models.MatriculaAcademica.institucion_id == institucion_id,
            models.MatriculaAcademica.fecha_fin.is_(None),
            models.Seccion.anio_escolar == anio_escolar,
        )
        .all()
    )


def iniciar_proceso_promocion(
    db: Session, institucion_id: int, anio_origen: int, anio_destino: int, usuario_id: int,
) -> models.ProcesoPromocion:
    """Crea el borrador y calcula la propuesta automática para cada
    estudiante con matrícula vigente en `anio_origen`. No aplica ningún
    cambio real todavía — eso solo ocurre en `confirmar_proceso_promocion`."""
    if anio_destino <= anio_origen:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El año destino debe ser posterior al año de origen.",
        )

    borrador_existente = db.query(models.ProcesoPromocion).filter(
        models.ProcesoPromocion.institucion_id == institucion_id,
        models.ProcesoPromocion.anio_origen == anio_origen,
        models.ProcesoPromocion.anio_destino == anio_destino,
        models.ProcesoPromocion.estado == "borrador",
    ).first()
    if borrador_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya hay un proceso de promoción en borrador (#{borrador_existente.id}) "
                f"para {anio_origen} -> {anio_destino}. Ábrelo, edítalo o cancélalo "
                f"antes de crear uno nuevo."
            ),
        )
    confirmado_existente = db.query(models.ProcesoPromocion).filter(
        models.ProcesoPromocion.institucion_id == institucion_id,
        models.ProcesoPromocion.anio_origen == anio_origen,
        models.ProcesoPromocion.anio_destino == anio_destino,
        models.ProcesoPromocion.estado == "confirmado",
    ).first()
    if confirmado_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La promoción de {anio_origen} a {anio_destino} ya fue confirmada "
                f"(proceso #{confirmado_existente.id})."
            ),
        )

    proceso = models.ProcesoPromocion(
        institucion_id=institucion_id, anio_origen=anio_origen, anio_destino=anio_destino,
        creado_por_usuario_id=usuario_id,
    )
    db.add(proceso)
    db.flush()  # necesita proceso.id para las filas de detalle

    for matricula in _matriculas_activas_del_anio(db, institucion_id, anio_origen):
        propuesta = calcular_propuesta_promocion(db, matricula, anio_destino)
        if propuesta["advertencia"]:
            tipo_excepcion = TIPO_EXCEPCION_CAMBIO_MANUAL
            seccion_definitiva_id = None
        elif propuesta["tipo"] == "egreso":
            tipo_excepcion = TIPO_EXCEPCION_EGRESO
            seccion_definitiva_id = None
        else:
            tipo_excepcion = TIPO_EXCEPCION_NINGUNA
            seccion_definitiva_id = propuesta["seccion_propuesta_id"]

        db.add(models.ProcesoPromocionDetalle(
            proceso_id=proceso.id,
            persona_id=matricula.persona_id,
            matricula_origen_id=matricula.id,
            seccion_propuesta_id=propuesta["seccion_propuesta_id"],
            tipo_excepcion=tipo_excepcion,
            seccion_definitiva_id=seccion_definitiva_id,
            advertencia_mapeo=propuesta["advertencia"],
        ))

    db.commit()
    db.refresh(proceso)
    return proceso


def obtener_proceso_promocion(db: Session, proceso_id: int):
    return db.query(models.ProcesoPromocion).filter(models.ProcesoPromocion.id == proceso_id).first()


def listar_procesos_promocion(db: Session, institucion_id: int, estado: Optional[str] = None):
    query = db.query(models.ProcesoPromocion).filter(
        models.ProcesoPromocion.institucion_id == institucion_id,
    )
    if estado is not None:
        query = query.filter(models.ProcesoPromocion.estado == estado)
    return query.order_by(models.ProcesoPromocion.fecha_creacion.desc()).all()


def _describir_seccion_de_proceso(db: Session, seccion_id: Optional[int]) -> Optional[dict]:
    if seccion_id is None:
        return None
    seccion = db.query(models.Seccion).filter(models.Seccion.id == seccion_id).first()
    if not seccion:
        return None
    grado = db.query(models.Grado).filter(models.Grado.id == seccion.grado_id).first()
    nivel = (
        db.query(models.NivelEducativo).filter(models.NivelEducativo.id == grado.nivel_educativo_id).first()
        if grado else None
    )
    return {
        "seccion_id": seccion.id,
        "seccion": seccion.nombre,
        "turno": seccion.turno,
        "anio_escolar": seccion.anio_escolar,
        "grado_id": grado.id if grado else None,
        "grado": grado.nombre if grado else None,
        "nivel_educativo_id": nivel.id if nivel else None,
        "nivel_educativo": nivel.nombre if nivel else None,
    }


def _describir_detalle_promocion(db: Session, detalle: models.ProcesoPromocionDetalle) -> dict:
    persona = db.query(models.Persona).filter(models.Persona.id == detalle.persona_id).first()
    matricula_origen = db.query(models.MatriculaAcademica).filter(
        models.MatriculaAcademica.id == detalle.matricula_origen_id,
    ).first()
    return {
        "detalle_id": detalle.id,
        "persona_id": detalle.persona_id,
        "persona_nombre_completo": f"{persona.nombres} {persona.apellidos}" if persona else None,
        "matricula_origen": _describir_matricula(db=db, matricula=matricula_origen) if matricula_origen else None,
        "seccion_propuesta": _describir_seccion_de_proceso(db, detalle.seccion_propuesta_id),
        "tipo_excepcion": detalle.tipo_excepcion,
        "seccion_definitiva": _describir_seccion_de_proceso(db, detalle.seccion_definitiva_id),
        "advertencia_mapeo": detalle.advertencia_mapeo,
        "aplicado": detalle.aplicado,
        "matricula_resultante_id": detalle.matricula_resultante_id,
    }


def describir_proceso_promocion(db: Session, proceso: models.ProcesoPromocion) -> dict:
    detalles = db.query(models.ProcesoPromocionDetalle).filter(
        models.ProcesoPromocionDetalle.proceso_id == proceso.id,
    ).order_by(models.ProcesoPromocionDetalle.id).all()
    return {
        "proceso": {
            "id": proceso.id,
            "institucion_id": proceso.institucion_id,
            "anio_origen": proceso.anio_origen,
            "anio_destino": proceso.anio_destino,
            "estado": proceso.estado,
            "creado_por_usuario_id": proceso.creado_por_usuario_id,
            "fecha_creacion": proceso.fecha_creacion,
            "confirmado_por_usuario_id": proceso.confirmado_por_usuario_id,
            "fecha_confirmacion": proceso.fecha_confirmacion,
        },
        "detalle": [_describir_detalle_promocion(db=db, detalle=d) for d in detalles],
    }


def editar_detalles_promocion(db: Session, proceso: models.ProcesoPromocion, ediciones: list) -> list:
    """Aplica varias ediciones de excepción/destino sobre la vista previa de
    un proceso EN BORRADOR — todas o ninguna: si una fila de la lista es
    inválida, no se aplica ninguna (nada se comete hasta el final del
    bucle), para que el llamador corrija y reintente sin dejar el proceso a
    medio editar."""
    if proceso.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este proceso ya está '{proceso.estado}'; no se pueden editar sus filas.",
        )

    detalles_tocados = []
    for edicion in ediciones:
        tipo_excepcion = edicion.tipo_excepcion
        seccion_definitiva_id = edicion.seccion_definitiva_id
        if tipo_excepcion not in TIPOS_EXCEPCION_VALIDOS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"tipo_excepcion inválido: '{tipo_excepcion}'.",
            )

        detalle = db.query(models.ProcesoPromocionDetalle).filter(
            models.ProcesoPromocionDetalle.id == edicion.detalle_id,
            models.ProcesoPromocionDetalle.proceso_id == proceso.id,
        ).first()
        if not detalle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"La fila #{edicion.detalle_id} no pertenece a este proceso.",
            )

        if tipo_excepcion in EXCEPCIONES_SIN_MATRICULA_NUEVA:
            if seccion_definitiva_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Fila #{edicion.detalle_id}: '{tipo_excepcion}' no abre "
                        f"matrícula nueva, no debe traer seccion_definitiva_id."
                    ),
                )
        else:
            if seccion_definitiva_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Fila #{edicion.detalle_id}: indica seccion_definitiva_id para este tipo de excepción.",
                )
            seccion = db.query(models.Seccion).filter(models.Seccion.id == seccion_definitiva_id).first()
            if not seccion or seccion.institucion_id != proceso.institucion_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Fila #{edicion.detalle_id}: esa sección no existe en esta institución.",
                )
            if seccion.anio_escolar != proceso.anio_destino:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Fila #{edicion.detalle_id}: la sección debe ser del año "
                        f"destino ({proceso.anio_destino})."
                    ),
                )

        detalle.tipo_excepcion = tipo_excepcion
        detalle.seccion_definitiva_id = seccion_definitiva_id
        detalles_tocados.append(detalle)

    db.commit()
    for detalle in detalles_tocados:
        db.refresh(detalle)
    return detalles_tocados


def cancelar_proceso_promocion(db: Session, proceso: models.ProcesoPromocion) -> models.ProcesoPromocion:
    if proceso.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Solo se puede cancelar un proceso en borrador (este está '{proceso.estado}').",
        )
    proceso.estado = "cancelado"
    db.commit()
    db.refresh(proceso)
    return proceso


def confirmar_proceso_promocion(db: Session, proceso: models.ProcesoPromocion, usuario_id: int) -> models.ProcesoPromocion:
    """Aplica el proceso en una sola transacción. Re-deriva y re-valida cada
    fila desde la BD (nunca confía en lo que quedó calculado al crear el
    borrador, por si algo cambió desde entonces) y solo si TODAS las filas
    pasan esa revalidación se aplica ninguna... o todas."""
    if proceso.estado != "borrador":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Este proceso ya está '{proceso.estado}'; no se puede confirmar de nuevo.",
        )

    detalles = db.query(models.ProcesoPromocionDetalle).filter(
        models.ProcesoPromocionDetalle.proceso_id == proceso.id,
    ).all()

    errores = []
    for detalle in detalles:
        matricula_origen = db.query(models.MatriculaAcademica).filter(
            models.MatriculaAcademica.id == detalle.matricula_origen_id,
        ).first()
        if not matricula_origen or matricula_origen.fecha_fin is not None:
            errores.append(
                f"Persona #{detalle.persona_id}: su matrícula de origen ya no está "
                f"vigente (¿se movió por otra vía desde que se abrió este proceso?)."
            )
            continue
        if detalle.tipo_excepcion not in EXCEPCIONES_SIN_MATRICULA_NUEVA:
            if detalle.seccion_definitiva_id is None:
                errores.append(f"Persona #{detalle.persona_id}: no tiene una sección definitiva resuelta (mapeo manual pendiente).")
                continue
            seccion_def = db.query(models.Seccion).filter(models.Seccion.id == detalle.seccion_definitiva_id).first()
            if not seccion_def or seccion_def.anio_escolar != proceso.anio_destino or not seccion_def.activo:
                errores.append(f"Persona #{detalle.persona_id}: la sección definitiva ya no es válida para el año {proceso.anio_destino}.")
                continue

    if errores:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "mensaje": "No se pudo confirmar: hay filas con problemas. Corrígelas y vuelve a intentar.",
                "errores": errores,
            },
        )

    ahora = datetime.now(timezone.utc)
    # 🔒 El bucle de revalidación de arriba (líneas previas) solo cierra la
    # ventana SECUENCIAL: si una SEGUNDA promoción concurrente (otro borrador,
    # para el mismo origen pero distinto año destino) también pasó esa
    # revalidación antes de que esta confirmara, su `db.flush()` de abajo
    # puede chocar contra `uq_matricula_activa_por_persona` al intentar abrir
    # una segunda matrícula activa para la misma persona — un IntegrityError
    # que antes solo el `commit()` final atrapaba, dejando el `flush()` de
    # cada fila sin protección. Todo el bloque de escritura (flush incluido)
    # queda ahora bajo el mismo try/except que ya protegía el commit.
    try:
        for detalle in detalles:
            matricula_origen = db.query(models.MatriculaAcademica).filter(
                models.MatriculaAcademica.id == detalle.matricula_origen_id,
            ).first()
            persona = db.query(models.Persona).filter(models.Persona.id == detalle.persona_id).first()

            matricula_origen.fecha_fin = ahora
            matricula_origen.motivo_cierre = MOTIVO_CIERRE_POR_EXCEPCION[detalle.tipo_excepcion]

            if detalle.tipo_excepcion in EXCEPCIONES_SIN_MATRICULA_NUEVA:
                persona.condicion_matricula = CONDICION_MATRICULA_POR_EXCEPCION[detalle.tipo_excepcion]
            else:
                nueva = models.MatriculaAcademica(
                    persona_id=detalle.persona_id,
                    institucion_id=proceso.institucion_id,
                    seccion_id=detalle.seccion_definitiva_id,
                    registrado_por_usuario_id=usuario_id,
                    motivo_apertura=MOTIVO_APERTURA_POR_EXCEPCION[detalle.tipo_excepcion],
                )
                db.add(nueva)
                db.flush()  # necesita nueva.id para matricula_resultante_id
                detalle.matricula_resultante_id = nueva.id

            detalle.aplicado = True

        proceso.estado = "confirmado"
        proceso.confirmado_por_usuario_id = usuario_id
        proceso.fecha_confirmacion = ahora
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No se pudo confirmar: esta promoción (institución + año origen + año destino) "
                "ya fue confirmada antes, o otra promoción concurrente entró en conflicto con "
                "alguna fila de este proceso (p. ej. el mismo estudiante en dos borradores a la "
                "vez). Vuelve a intentar."
            ),
        )
    db.refresh(proceso)
    return proceso


# 🆕 PASO 3 — únicos campos auditados por ahora; ver RegistroCambiosPersona
# en models.py. Cambiar `genero`/`grado_seccion`/`email`/`activo` NO genera
# fila aquí — no se pidió, y ampliarlo no necesita ninguna migración nueva
# (basta con sumar el nombre del campo a esta tupla).
CAMPOS_AUDITADOS_PERSONA = ("nombres", "apellidos", "fecha_nacimiento", "documento_identidad")


def _texto_para_auditoria(valor):
    if valor is None:
        return None
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def _valor_comparable(valor):
    """fecha_nacimiento llega como `date` desde el schema (PersonaUpdate) pero
    se lee como `datetime` desde la columna (DateTime(timezone=True)) — sin
    esto, corregir el mismo día de nacimiento se vería como 'cambió' solo por
    la diferencia de tipo, y generaría una fila de auditoría vacía de sentido.

    Para los campos de texto (nombres/apellidos/documento_identidad), un
    espacio en blanco al inicio/final no es un cambio real — sin este
    `.strip()`, guardar el mismo valor con un espacio de más generaba una
    fila de `RegistroCambiosPersona` (y potencialmente una de `auditoria_arco`
    si venía `referencia_solicitud_arco`) para una edición cosmética. No se
    normaliza mayúsculas/minúsculas a propósito: corregir "juan" a "Juan" sí
    es un cambio real que debe quedar auditado."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        return valor.strip()
    return valor


def actualizar_persona(
    db: Session, persona_id: int, datos: schemas.PersonaUpdate, usuario_actual=None,
    referencia_solicitud_arco: Optional[str] = None,
):
    """
    🆕 ARCO — rectificación con trazabilidad. `referencia_solicitud_arco` es
    opcional y no cambia NADA de la edición en sí (mismo diff, misma
    `RegistroCambiosPersona` de siempre): cuando viene informado Y al menos
    un campo auditado (CAMPOS_AUDITADOS_PERSONA) cambió de verdad, además se
    añade UNA fila en `auditoria_arco` (accion="rectificacion_persona"), en
    la MISMA transacción que el resto — así una edición rutinaria (sin esta
    referencia) sigue sin tocar `auditoria_arco`, y una invocada explícitamente
    como ejercicio del derecho ARCO de rectificación queda separable del
    ruido de ediciones normales sin necesitar un endpoint ni una tabla nueva.
    """
    persona = db.query(models.Persona).filter(models.Persona.id == persona_id).first()
    if not persona:
        return None
    cambios = datos.model_dump(exclude_unset=True)

    # 🆕 PASO 3 — el diff se calcula ANTES de aplicar los setattr (para poder
    # comparar contra el valor real que tenía la fila) y se inserta en la
    # MISMA transacción que la propia edición: si el commit de abajo falla
    # (p. ej. el 409 de código institucional duplicado), el rollback deshace
    # también estas filas de auditoría — nunca queda un registro de un
    # cambio que en realidad no se aplicó.
    registros_auditoria = []
    if usuario_actual is not None:
        for campo in CAMPOS_AUDITADOS_PERSONA:
            if campo not in cambios:
                continue
            valor_anterior = getattr(persona, campo)
            valor_nuevo = cambios[campo]
            if _valor_comparable(valor_anterior) == _valor_comparable(valor_nuevo):
                continue
            registros_auditoria.append(models.RegistroCambiosPersona(
                persona_id=persona.id,
                institucion_id=persona.institucion_id,
                campo=campo,
                valor_anterior=_texto_para_auditoria(valor_anterior),
                valor_nuevo=_texto_para_auditoria(valor_nuevo),
                modificado_por_usuario_id=usuario_actual.id,
                rol_modificador=usuario_actual.rol,
            ))

    for campo, valor in cambios.items():
        setattr(persona, campo, valor)
    for registro in registros_auditoria:
        db.add(registro)
    if referencia_solicitud_arco and registros_auditoria:
        campos_cambiados = ", ".join(r.campo for r in registros_auditoria)
        db.add(models.RegistroAuditoriaArco(
            accion="rectificacion_persona",
            persona_id=persona.id,
            institucion_id=persona.institucion_id,
            ejecutado_por_usuario_id=usuario_actual.id,
            rol_ejecutor=usuario_actual.rol,
            detalle=(
                f"Rectificación ARCO de: {campos_cambiados}. "
                f"Solicitud: {referencia_solicitud_arco}"
            ),
        ))
    try:
        db.commit()
    except IntegrityError:
        # 🆕 Núcleo del estudiante — antes esta función no podía tocar ninguna
        # columna con restricción UNIQUE; ahora `codigo_institucional` sí la
        # tiene, así que un PATCH que lo duplique debe volver 409, no un 500
        # sin manejar.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe otra persona con ese código institucional en esta institución.",
        )
    db.refresh(persona)
    return persona


def listar_historial_cambios_persona(db: Session, persona_id: int):
    return db.query(models.RegistroCambiosPersona).filter(
        models.RegistroCambiosPersona.persona_id == persona_id
    ).order_by(models.RegistroCambiosPersona.fecha.desc()).all()


# ==========================================
# 🆕 EXPEDIENTE / SEGUIMIENTO DEL ESTUDIANTE
# ==========================================
# Regla de acceso final (aprobada): el contenido completo de CUALQUIER
# entrada, sin importar su tipo, solo lo puede leer su propio
# `autor_usuario_id`, o superadmin, o el rol "colegio" mientras exista una
# `AutorizacionAccesoColegio` vigente para esa persona. Nadie más — ni
# "admin" ni otro "psicologo" — bajo ninguna circunstancia. Esa regla se
# aplica en UN solo lugar (`usuario_puede_ver_contenido_completo`) y tanto
# el listado como el detalle la usan, para que no puedan divergir.

TIPO_ENTRADA_OBSERVACION = "observacion_conducta"
TIPO_ENTRADA_CONTACTO_APODERADO = "contacto_apoderado"
TIPO_ENTRADA_DERIVACION = "derivacion"
TIPO_ENTRADA_SESION = "sesion"
TIPO_ENTRADA_APLICACION_PRUEBA = "aplicacion_prueba"
# 🆕 'evidencia' — igual que 'documento_institucional', deliberadamente NO
# entra en TIPOS_ENTRADA_VALIDOS/_TIPOS_ENTRADA_EXPEDIENTE_VALIDOS (schemas.py):
# tiene su propio endpoint multipart dedicado (POST .../expediente/evidencia),
# nunca el genérico POST .../expediente (que solo acepta JSON, sin archivo).
TIPO_ENTRADA_EVIDENCIA = "evidencia"
TIPOS_ENTRADA_VALIDOS = (
    TIPO_ENTRADA_OBSERVACION, TIPO_ENTRADA_CONTACTO_APODERADO, TIPO_ENTRADA_DERIVACION,
    TIPO_ENTRADA_SESION, TIPO_ENTRADA_APLICACION_PRUEBA,
)
# Los 3 tipos con contenido narrativo propio (versionado). Los otros 2 son
# puente — su "contenido" vive en SesionSeguimiento/Informe, ajenos a este
# módulo, y este módulo nunca los escribe.
TIPOS_ENTRADA_CON_CONTENIDO_PROPIO = (TIPO_ENTRADA_OBSERVACION, TIPO_ENTRADA_CONTACTO_APODERADO, TIPO_ENTRADA_DERIVACION)
TIPOS_ENTRADA_PUENTE = (TIPO_ENTRADA_SESION, TIPO_ENTRADA_APLICACION_PRUEBA)


def _validar_enlaces_segun_tipo(
    db: Session, persona: models.Persona, tipo_entrada: str,
    sesion_seguimiento_id: Optional[int], informe_id: Optional[int], contacto_familiar_id: Optional[int],
):
    """Valida ANTES de tocar la BD, con mensajes claros, en vez de dejar que
    `ck_expediente_campos_segun_tipo` reviente como un IntegrityError crudo.
    También revalida que cualquier enlace de verdad pertenezca a ESTA
    persona — nunca se confía en un id ajeno enviado por el cliente."""
    if tipo_entrada in TIPOS_ENTRADA_CON_CONTENIDO_PROPIO:
        if sesion_seguimiento_id is not None or informe_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{tipo_entrada}' no es una entrada puente: no admite sesion_seguimiento_id ni informe_id.",
            )
        if tipo_entrada != TIPO_ENTRADA_CONTACTO_APODERADO and contacto_familiar_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{tipo_entrada}' no admite contacto_familiar_id (solo 'contacto_apoderado').",
            )
        if contacto_familiar_id is not None:
            contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_familiar_id).first()
            if not contacto or contacto.persona_id != persona.id:
                raise HTTPException(status_code=404, detail="Ese contacto familiar no pertenece a este estudiante.")
        return

    if tipo_entrada == TIPO_ENTRADA_SESION:
        if not sesion_seguimiento_id:
            raise HTTPException(status_code=422, detail="'sesion' exige sesion_seguimiento_id.")
        if informe_id is not None or contacto_familiar_id is not None:
            raise HTTPException(status_code=422, detail="'sesion' no admite informe_id ni contacto_familiar_id.")
        sesion = db.query(educativo_models.SesionSeguimiento).filter(
            educativo_models.SesionSeguimiento.id == sesion_seguimiento_id,
        ).first()
        if not sesion or sesion.persona_id != persona.id:
            raise HTTPException(status_code=404, detail="Esa sesión de seguimiento no pertenece a este estudiante.")
        return

    if tipo_entrada == TIPO_ENTRADA_APLICACION_PRUEBA:
        if not informe_id:
            raise HTTPException(status_code=422, detail="'aplicacion_prueba' exige informe_id.")
        if sesion_seguimiento_id is not None or contacto_familiar_id is not None:
            raise HTTPException(status_code=422, detail="'aplicacion_prueba' no admite sesion_seguimiento_id ni contacto_familiar_id.")
        informe = db.query(educativo_models.Informe).filter(educativo_models.Informe.id == informe_id).first()
        if not informe or informe.persona_id != persona.id:
            raise HTTPException(status_code=404, detail="Ese informe no pertenece a este estudiante.")
        return


def crear_entrada_expediente(db: Session, persona: models.Persona, autor_usuario_id: int, datos: schemas.EntradaExpedienteCreate):
    """Crea la entrada y, si es de un tipo con contenido propio, su v1 en la
    misma transacción — nunca queda una entrada narrativa sin ninguna
    versión."""
    tipo_entrada = datos.tipo_entrada
    _validar_enlaces_segun_tipo(
        db, persona, tipo_entrada, datos.sesion_seguimiento_id, datos.informe_id, datos.contacto_familiar_id,
    )

    tiene_contenido_propio = tipo_entrada in TIPOS_ENTRADA_CON_CONTENIDO_PROPIO
    entrada = models.EntradaExpediente(
        persona_id=persona.id,
        institucion_id=persona.institucion_id,
        tipo_entrada=tipo_entrada,
        autor_usuario_id=autor_usuario_id,
        fecha_entrada=datos.fecha_entrada or datetime.now(timezone.utc),
        version_actual=1 if tiene_contenido_propio else None,
        sesion_seguimiento_id=datos.sesion_seguimiento_id,
        informe_id=datos.informe_id,
        contacto_familiar_id=datos.contacto_familiar_id,
    )
    db.add(entrada)
    db.flush()  # necesita entrada.id para la versión

    if tiene_contenido_propio:
        db.add(models.EntradaExpedienteVersion(
            entrada_expediente_id=entrada.id,
            numero_version=1,
            motivo=datos.motivo,
            contenido=datos.contenido,
            interpretacion=datos.interpretacion,
            diagnostico_presuntivo=datos.diagnostico_presuntivo,
            creado_por_usuario_id=autor_usuario_id,
            motivo_version=None,   # v1 no exige motivo — "Creación inicial" implícita
        ))

    db.commit()
    db.refresh(entrada)
    return entrada


def crear_entrada_expediente_documento_institucional(
    db: Session, persona_id: int, institucion_id: int, documento_institucional_id: int, autor_usuario_id: int,
) -> models.EntradaExpediente:
    """Crea la entrada-puente 'documento_institucional' — SOLO para uso
    interno de `modulos.documentos.crud.generar_version_documento`, NUNCA
    expuesta por el endpoint público `POST .../expediente`: su schema
    (`EntradaExpedienteCreate`) no admite este `tipo_entrada` — un cliente
    que lo intente recibe 422 antes de llegar aquí.

    🔁 Idempotente: el enlace apunta a la IDENTIDAD del documento
    (`DocumentoInstitucional`), no a una versión concreta — mismo criterio
    que la entrada 'aplicacion_prueba' apunta a `Informe`, nunca a una
    `InformeVersion`, y por lo tanto nunca se duplica al reemitir. Se
    invoca en CADA generación de versión (v1 y cada reemisión), pero si ya
    existe una entrada para este (persona, documento) de una versión
    anterior del MISMO documento, se devuelve esa fila tal cual — nunca una
    segunda.

    A diferencia de `crear_entrada_expediente()` (pública), esta función
    deliberadamente NO hace `db.commit()` cuando SÍ crea una fila nueva —
    se inserta dentro de la MISMA transacción que la
    `DocumentoInstitucionalVersion` que la origina, para que un fallo a
    mitad de camino no deje una versión generada con un rastro incompleto
    en el expediente de algún estudiante incluido.

    🔒 Confidencialidad: esta entrada sigue la regla ESTRICTA del expediente
    sin ninguna excepción nueva — `autor_usuario_id`/superadmin, con
    `AutorizacionAccesoColegio` como única vía adicional, exactamente igual
    que cualquier otra entrada. `DocumentoInstitucional.nivel_visibilidad`
    NUNCA se consulta aquí — decisión explícita para no abrir un segundo
    canal de autorización hacia este mismo expediente (ver el docstring de
    `EntradaExpediente` en models.py)."""
    existente = db.query(models.EntradaExpediente).filter(
        models.EntradaExpediente.tipo_entrada == "documento_institucional",
        models.EntradaExpediente.persona_id == persona_id,
        models.EntradaExpediente.documento_institucional_id == documento_institucional_id,
    ).first()
    if existente:
        return existente

    entrada = models.EntradaExpediente(
        persona_id=persona_id,
        institucion_id=institucion_id,
        tipo_entrada="documento_institucional",
        autor_usuario_id=autor_usuario_id,
        fecha_entrada=datetime.now(timezone.utc),
        version_actual=None,  # puente -- nada propio que versionar
        documento_institucional_id=documento_institucional_id,
    )
    db.add(entrada)
    return entrada


def crear_entrada_expediente_evidencia(
    db: Session, persona: models.Persona, autor_usuario_id: int,
    contenido: bytes, nombre_archivo: str, content_type: str,
    titulo: str, descripcion: Optional[str], fecha_entrada: Optional[datetime],
    informe_id: Optional[int], incluir_en_pdf_informe: bool,
) -> models.EntradaExpediente:
    """Registra un archivo escaneado (dibujo proyectivo, ficha física,
    cualquier hoja) como entrada 'evidencia' del expediente — suelta
    (informe_id=None) o vinculada a una aplicación puntual. Reutiliza
    exactamente la misma lista blanca/tope de tamaño/storage que
    guardar_evidencia_consentimiento(), sin inventar un segundo mecanismo de
    saneo de archivos.

    `incluir_en_pdf_informe=True` exige informe_id (ver
    ck_expediente_incluir_pdf_requiere_evidencia_con_informe) — validado acá
    con un 422 claro, igual criterio que _validar_enlaces_segun_tipo, en vez
    de dejar que el CHECK reviente como IntegrityError crudo.
    """
    if not titulo or not titulo.strip():
        raise HTTPException(status_code=422, detail="El título de la evidencia es obligatorio.")
    if informe_id is not None:
        informe = db.query(educativo_models.Informe).filter(educativo_models.Informe.id == informe_id).first()
        if not informe or informe.persona_id != persona.id:
            raise HTTPException(status_code=404, detail="Ese informe no pertenece a este estudiante.")
    if incluir_en_pdf_informe and informe_id is None:
        raise HTTPException(
            status_code=422,
            detail="Solo se puede incluir en el PDF una evidencia vinculada a un informe (informe_id).",
        )
    if len(contenido) > TAMANO_MAXIMO_EVIDENCIA_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo supera el tamaño máximo permitido ({TAMANO_MAXIMO_EVIDENCIA_BYTES // (1024*1024)} MB).",
        )
    extension = _extension_segura(nombre_archivo)

    # Se escribe el storage ANTES de insertar la fila — storage_key es
    # NOT NULL desde el primer INSERT (ck_expediente_campos_segun_tipo), así
    # que no se puede depender de entrada.id (que recién existiría después
    # de un flush/insert) como hace, por ejemplo, el informe PDF con su
    # propio id de versión. Mismo criterio de "token, no id" que
    # construir_storage_key_imagen_seccion_documento.
    import uuid as _uuid
    from core.storage import obtener_storage_service, construir_storage_key_evidencia_expediente
    token = _uuid.uuid4().hex
    key = construir_storage_key_evidencia_expediente(persona.institucion_id, persona.id, token, extension)
    obtener_storage_service().guardar(key, contenido, content_type or "application/octet-stream")

    entrada = models.EntradaExpediente(
        persona_id=persona.id,
        institucion_id=persona.institucion_id,
        tipo_entrada=TIPO_ENTRADA_EVIDENCIA,
        autor_usuario_id=autor_usuario_id,
        fecha_entrada=fecha_entrada or datetime.now(timezone.utc),
        version_actual=None,  # archivo fijo, no narrativo — ver docstring de la clase
        informe_id=informe_id,
        titulo=titulo.strip(),
        descripcion=descripcion,
        storage_key=key,
        nombre_archivo_original=nombre_archivo,
        content_type=content_type,
        incluir_en_pdf_informe=incluir_en_pdf_informe,
    )
    db.add(entrada)
    db.commit()
    db.refresh(entrada)
    return entrada


def leer_evidencia_expediente(entrada: models.EntradaExpediente) -> bytes:
    """Lee el binario de storage. Lanza FileNotFoundError si la key no
    existe (mismo contrato que StorageService.leer)."""
    from core.storage import obtener_storage_service
    return obtener_storage_service().leer(entrada.storage_key)


def actualizar_evidencia_expediente(
    db: Session, entrada: models.EntradaExpediente, incluir_en_pdf_informe: bool,
) -> models.EntradaExpediente:
    """Único campo editable de una evidencia ya subida — ver
    EntradaExpedienteEvidenciaUpdate."""
    if incluir_en_pdf_informe and entrada.informe_id is None:
        raise HTTPException(
            status_code=422,
            detail="Solo se puede incluir en el PDF una evidencia vinculada a un informe.",
        )
    entrada.incluir_en_pdf_informe = incluir_en_pdf_informe
    db.commit()
    db.refresh(entrada)
    return entrada


def usuario_puede_ver_contenido_completo(db: Session, entrada: models.EntradaExpediente, usuario_actual):
    """LA regla de acceso — ver el comentario del bloque. Devuelve
    (autorizado, autorizacion_usada); la segunda solo viene poblada cuando
    la única razón de acceso fue una excepción vigente de colegio, para que
    quede trazada en el registro de lectura."""
    if usuario_actual.rol == "superadmin":
        return True, None
    if entrada.autor_usuario_id == usuario_actual.id:
        return True, None
    if usuario_actual.rol == "colegio":
        autorizacion = obtener_autorizacion_colegio_vigente(db, entrada.persona_id)
        if autorizacion:
            return True, autorizacion
    return False, None


def listar_entradas_expediente_visibles(db: Session, persona_id: int, usuario_actual):
    """Metadata únicamente (nunca contenido narrativo, nunca genera
    auditoría de lectura) de las entradas que ESTE usuario puede ver —
    aplica la misma regla de acceso fila por fila, así que dos psicólogos
    distintos de la misma institución pueden ver listas distintas del
    mismo estudiante."""
    entradas = db.query(models.EntradaExpediente).filter(
        models.EntradaExpediente.persona_id == persona_id,
    ).order_by(models.EntradaExpediente.fecha_entrada.desc()).all()
    return [e for e in entradas if usuario_puede_ver_contenido_completo(db, e, usuario_actual)[0]]


def _describir_version_expediente(version: Optional[models.EntradaExpedienteVersion]) -> Optional[dict]:
    if version is None:
        return None
    return {
        "numero_version": version.numero_version,
        "motivo": version.motivo,
        "contenido": version.contenido,
        "interpretacion": version.interpretacion,
        "diagnostico_presuntivo": version.diagnostico_presuntivo,
        "creado_por_usuario_id": version.creado_por_usuario_id,
        "creado_en": version.creado_en,
        "motivo_version": version.motivo_version,
    }


def obtener_detalle_entrada_expediente(
    db: Session, entrada: models.EntradaExpediente, usuario_actual,
    ip_lectura: Optional[str] = None, numero_version: Optional[int] = None,
) -> dict:
    """Detalle completo — aplica la regla de acceso (403 si no corresponde)
    y, solo si el acceso se concede, registra la lectura en
    `RegistroLecturasExpediente` ANTES de devolver nada. Se audita TODA
    lectura de contenido completo, sin excepción — incluidas las que
    ocurren bajo una autorización de colegio."""
    autorizado, autorizacion = usuario_puede_ver_contenido_completo(db, entrada, usuario_actual)
    if not autorizado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso al contenido de esta entrada del expediente.",
        )

    version = None
    if entrada.version_actual is not None:
        query = db.query(models.EntradaExpedienteVersion).filter(
            models.EntradaExpedienteVersion.entrada_expediente_id == entrada.id,
        )
        numero_a_buscar = numero_version if numero_version is not None else entrada.version_actual
        version = query.filter(models.EntradaExpedienteVersion.numero_version == numero_a_buscar).first()
        if not version:
            raise HTTPException(status_code=404, detail=f"No existe la versión {numero_a_buscar} de esta entrada.")

    db.add(models.RegistroLecturasExpediente(
        entrada_expediente_id=entrada.id,
        persona_id=entrada.persona_id,
        institucion_id=entrada.institucion_id,
        leido_por_usuario_id=usuario_actual.id,
        rol_lector=usuario_actual.rol,
        ip_lectura=ip_lectura,
        numero_version_leida=version.numero_version if version else None,
        autorizacion_acceso_colegio_id=autorizacion.id if autorizacion else None,
    ))
    db.commit()

    return {
        "id": entrada.id,
        "persona_id": entrada.persona_id,
        "institucion_id": entrada.institucion_id,
        "tipo_entrada": entrada.tipo_entrada,
        "autor_usuario_id": entrada.autor_usuario_id,
        "fecha_entrada": entrada.fecha_entrada,
        "creado_en": entrada.creado_en,
        "version_actual": entrada.version_actual,
        "sesion_seguimiento_id": entrada.sesion_seguimiento_id,
        "informe_id": entrada.informe_id,
        "contacto_familiar_id": entrada.contacto_familiar_id,
        "documento_institucional_id": entrada.documento_institucional_id,
        "titulo": entrada.titulo,
        "descripcion": entrada.descripcion,
        "nombre_archivo_original": entrada.nombre_archivo_original,
        "content_type": entrada.content_type,
        "incluir_en_pdf_informe": entrada.incluir_en_pdf_informe,
        "version": _describir_version_expediente(version),
    }


def agregar_version_expediente(
    db: Session, entrada: models.EntradaExpediente, usuario_actual, datos: schemas.EntradaExpedienteVersionCreate,
):
    """Corrección/actualización de contenido — nunca edita una versión
    existente, siempre crea `version_actual + 1`. Solo el propio autor o
    superadmin pueden escribir aquí: una `AutorizacionAccesoColegio` es
    exclusivamente de LECTURA, nunca habilita escritura."""
    if entrada.tipo_entrada not in TIPOS_ENTRADA_CON_CONTENIDO_PROPIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{entrada.tipo_entrada}' es una entrada puente: no tiene contenido propio que versionar.",
        )
    if usuario_actual.rol != "superadmin" and entrada.autor_usuario_id != usuario_actual.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el autor de esta entrada (o superadmin) puede agregar una nueva versión.",
        )

    siguiente_numero = (entrada.version_actual or 0) + 1
    nueva_version = models.EntradaExpedienteVersion(
        entrada_expediente_id=entrada.id,
        numero_version=siguiente_numero,
        motivo=datos.motivo,
        contenido=datos.contenido,
        interpretacion=datos.interpretacion,
        diagnostico_presuntivo=datos.diagnostico_presuntivo,
        creado_por_usuario_id=usuario_actual.id,
        motivo_version=datos.motivo_version,
    )
    db.add(nueva_version)
    entrada.version_actual = siguiente_numero
    # 🔒 Auditoría de concurrencia — `siguiente_numero` se calcula a partir
    # de `entrada.version_actual` leído SIN lock de fila: dos solicitudes
    # casi simultáneas para agregar una versión a la MISMA entrada (dos
    # pestañas corrigiendo la misma nota clínica) pueden leer el mismo
    # version_actual, calcular el mismo siguiente_numero, y solo chocar al
    # commit contra `uq_expediente_version_entrada_numero` con un
    # IntegrityError crudo (500) en vez de un 409 explicado.
    commit_o_conflicto(
        db,
        "Esta entrada se actualizó al mismo tiempo desde otra sesión. Recarga y "
        "vuelve a intentar la corrección.",
    )
    db.refresh(nueva_version)
    return nueva_version


# ------------------------------------------
# ContactoFamiliar — soft-delete, nunca borrado físico (EntradaExpediente
# puede seguir apuntando a un contacto ya retirado).
# ------------------------------------------
def crear_contacto_familiar(db: Session, persona: models.Persona, datos: schemas.ContactoFamiliarCreate, usuario_id: Optional[int] = None):
    nuevo = models.ContactoFamiliar(
        persona_id=persona.id,
        institucion_id=persona.institucion_id,
        nombre=datos.nombre,
        telefono=datos.telefono,
        relacion=datos.relacion,
        email=datos.email,
        registrado_por_usuario_id=usuario_id,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


def listar_contactos_de_persona(db: Session, persona_id: int, incluir_inactivos: bool = False):
    query = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.persona_id == persona_id)
    if not incluir_inactivos:
        query = query.filter(models.ContactoFamiliar.activo == True)  # noqa: E712
    return query.order_by(models.ContactoFamiliar.fecha_registro).all()


def actualizar_contacto_familiar(db: Session, contacto_id: int, datos: schemas.ContactoFamiliarUpdate):
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        return None
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(contacto, campo, valor)
    db.commit()
    db.refresh(contacto)
    return contacto


def desactivar_contacto_familiar(db: Session, contacto_id: int):
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        return None
    contacto.activo = False
    db.commit()
    db.refresh(contacto)
    return contacto


def reactivar_contacto_familiar(db: Session, contacto_id: int):
    """Revierte una desactivación — vuelve a poner `activo=True` en la MISMA
    fila (nunca crea un registro nuevo), simétrico a
    `desactivar_contacto_familiar`. No hay nada que "reconciliar": la fila
    nunca se editó ni se borró al desactivarse, así que reactivarla la deja
    exactamente como estaba antes de la baja."""
    contacto = db.query(models.ContactoFamiliar).filter(models.ContactoFamiliar.id == contacto_id).first()
    if not contacto:
        return None
    contacto.activo = True
    db.commit()
    db.refresh(contacto)
    return contacto


# ------------------------------------------
# PersonaDatosFamiliares / PersonaAntecedentesClinicos — dos bloques 1:1
# con Persona, mutables, sin tabla de versiones propia. Mismo patrón
# get-or-create en ambos: la fila puede no existir todavía (un estudiante
# creado antes de esta funcionalidad, o cuya ficha nunca se llenó), y la
# primera edición la crea en vez de exigir un alta separada.
# ------------------------------------------
def obtener_datos_familiares(db: Session, persona_id: int):
    return db.query(models.PersonaDatosFamiliares).filter(
        models.PersonaDatosFamiliares.persona_id == persona_id,
    ).first()


def actualizar_datos_familiares(db: Session, persona_id: int, usuario_id: int, datos: schemas.PersonaDatosFamiliaresUpdate):
    fila = obtener_datos_familiares(db, persona_id)
    if not fila:
        fila = models.PersonaDatosFamiliares(persona_id=persona_id)
        db.add(fila)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(fila, campo, valor)
    fila.actualizado_por_usuario_id = usuario_id
    try:
        db.commit()
    except IntegrityError:
        # Carrera entre dos guardados simultáneos de la misma ficha (doble
        # clic, dos pestañas): el índice único de persona_id es la garantía
        # real: el que pierde la carrera recibe un 409 limpio, no un 500 sin
        # manejar — mismo criterio que el resto de este archivo.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta ficha se guardó desde otra pestaña o sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return fila


def obtener_antecedentes_clinicos(db: Session, persona_id: int):
    return db.query(models.PersonaAntecedentesClinicos).filter(
        models.PersonaAntecedentesClinicos.persona_id == persona_id,
    ).first()


def actualizar_antecedentes_clinicos(db: Session, persona_id: int, usuario_id: int, datos: schemas.PersonaAntecedentesClinicosUpdate):
    fila = obtener_antecedentes_clinicos(db, persona_id)
    if not fila:
        fila = models.PersonaAntecedentesClinicos(persona_id=persona_id)
        db.add(fila)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        setattr(fila, campo, valor)
    fila.actualizado_por_usuario_id = usuario_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta ficha se guardó desde otra pestaña o sesión al mismo tiempo. Vuelve a intentarlo.",
        )
    db.refresh(fila)
    return fila


# ------------------------------------------
# AutorizacionAccesoColegio — otorgar es una fila nueva; revocar MUTA la
# misma fila (nunca se borra ni se reescribe motivo/otorgado_por). Solo
# "psicologo" (o superadmin) puede otorgar/revocar — se exige en el router
# vía requerir_rol, no aquí.
# ------------------------------------------
def obtener_autorizacion_colegio_vigente(db: Session, persona_id: int):
    return db.query(models.AutorizacionAccesoColegio).filter(
        models.AutorizacionAccesoColegio.persona_id == persona_id,
        models.AutorizacionAccesoColegio.vigente == True,  # noqa: E712
    ).first()


def otorgar_autorizacion_colegio(db: Session, persona: models.Persona, usuario_actual, motivo: str):
    # 🔒 Precheck explicado (409 claro) — el índice único parcial
    # uq_autorizacion_colegio_vigente_por_persona sigue siendo la garantía
    # real contra una carrera concurrente; el except de abajo es el
    # respaldo para ese caso exacto.
    existente = obtener_autorizacion_colegio_vigente(db, persona.id)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ya existe una autorización vigente (#{existente.id}) para este estudiante. "
                f"Revócala antes de otorgar una nueva."
            ),
        )
    nueva = models.AutorizacionAccesoColegio(
        persona_id=persona.id,
        institucion_id=persona.institucion_id,
        otorgado_por_usuario_id=usuario_actual.id,
        rol_otorgante=usuario_actual.rol,
        motivo=motivo,
    )
    db.add(nueva)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una autorización vigente para este estudiante. Revócala antes de otorgar una nueva.",
        )
    db.refresh(nueva)
    return nueva


def revocar_autorizacion_colegio(db: Session, autorizacion: models.AutorizacionAccesoColegio, usuario_actual):
    if not autorizacion.vigente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta autorización ya estaba revocada.")
    autorizacion.vigente = False
    autorizacion.fecha_revocado = datetime.now(timezone.utc)
    autorizacion.revocado_por_usuario_id = usuario_actual.id
    autorizacion.rol_revocador = usuario_actual.rol
    db.commit()
    db.refresh(autorizacion)
    return autorizacion


def listar_autorizaciones_colegio(db: Session, persona_id: int):
    return db.query(models.AutorizacionAccesoColegio).filter(
        models.AutorizacionAccesoColegio.persona_id == persona_id,
    ).order_by(models.AutorizacionAccesoColegio.fecha_otorgado.desc()).all()