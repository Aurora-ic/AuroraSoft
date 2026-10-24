from pydantic import BaseModel, field_validator, Field
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel, EmailStr

# ==========================================
# ESQUEMAS PARA PERSONAS (EVALUADOS)
# ==========================================
class PersonaBase(BaseModel):
    institucion_id: int
    tipo_perfil: str = "estudiante"
    nombres: str
    apellidos: str
    documento_identidad: Optional[str] = None
    # 🆕 Núcleo del estudiante — identificador funcional del padrón del
    # colegio (código de matrícula/legajo), único por institución.
    codigo_institucional: Optional[str] = None
    email: Optional[EmailStr] = None   # 👈 Ahora usa EmailStr para validación estricta
    fecha_nacimiento: Optional[date] = None
    genero: Optional[str] = None
    grado_seccion: Optional[str] = None
    puesto_postula: Optional[str] = None
    area_empresa: Optional[str] = None


class PersonaCreate(PersonaBase):
    pass


class SeccionActualResponse(BaseModel):
    """Sección vigente de un estudiante, ya resuelta a etiquetas legibles —
    mismo shape que _describir_matricula() en crud.py, usado también por
    informacion_academica_actual en la ficha completa. None si la persona
    no tiene matrícula activa (o no es un `tipo_perfil` académico)."""
    matricula_id: int
    seccion_id: int
    seccion: Optional[str] = None
    turno: Optional[str] = None
    anio_escolar: Optional[int] = None
    grado_id: Optional[int] = None
    grado: Optional[str] = None
    nivel_educativo_id: Optional[int] = None
    nivel_educativo: Optional[str] = None
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None

    class Config:
        from_attributes = True


class PersonaResponse(PersonaBase):
    id: int
    activo: bool
    fecha_registro: datetime
    # 🆕 Sección vigente (batch-loaded desde MatriculaAcademica, no una
    # consulta por alumno) — NO reemplaza `grado_seccion` (heredado de
    # PersonaBase): ese campo es texto libre que ningún flujo de matrícula
    # actualiza, así que mostrarlo como la sección real de un estudiante
    # sería mostrar un dato potencialmente falso. `seccion_actual` es la
    # fuente de verdad nueva y correcta; `None` si no hay matrícula activa.
    seccion_actual: Optional[SeccionActualResponse] = None

    class Config:
        from_attributes = True


class ConsentimientoCreate(BaseModel):
    """Consentimiento del PADRE/MADRE/APODERADO. `persona_id`/`institucion_id`
    se conservan por compatibilidad con el frontend actual, pero el endpoint
    los ignora para determinar propiedad — ver B-8 en el router."""
    persona_id: int
    institucion_id: int
    otorgado_por_nombre: str
    tipo_otorgante: str  # "apoderado" o "colegio_delegado"
    referencia_documento: Optional[str] = None
    # 🆕 Consentimientos del estudiante/apoderado — datos adicionales del
    # responsable, todos opcionales para no romper a quien ya integraba con
    # la forma anterior de este mismo esquema.
    otorgante_apellidos: Optional[str] = None
    otorgante_documento: Optional[str] = None
    otorgante_relacion: Optional[str] = None  # "madre", "padre", "tutor legal"...
    # 🔧 La key de storage es interna (ver construir_storage_key_evidencia_consentimiento)
    # y nunca debe salir en una respuesta — se acepta en el request por
    # compatibilidad con el placeholder histórico, pero Response la excluye
    # explícitamente (ver más abajo). Probado en vivo: antes de este fix,
    # POST/GET de consentimiento devolvían la key real de storage al cliente.
    evidencia_ruta: Optional[str] = Field(default=None, exclude=True)


class ConsentimientoAsentimientoCreate(BaseModel):
    """Asentimiento del PROPIO ESTUDIANTE — registro independiente del
    consentimiento de su apoderado (ver punto 2 del núcleo de
    consentimientos): no tiene "otorgante" porque es el propio titular quien
    asiente. `persona_id`/`institucion_id` NO se piden: siempre vienen de
    la ruta ya validada, igual que en el endpoint de apoderado.

    🆕 Renombrado de ConsentimientoEstudianteCreate (docs/gaps-pendientes.md)
    — el nombre de clase ahora nombra la figura legal (asentimiento), no a
    quién lo otorga (que sigue siendo el estudiante)."""
    referencia_documento: Optional[str] = None
    evidencia_ruta: Optional[str] = Field(default=None, exclude=True)  # ver nota en ConsentimientoCreate


class ConsentimientoResponse(ConsentimientoCreate):
    id: int
    tipo_consentimiento: str
    estado: str
    registrado_por_usuario_id: int
    fecha_otorgamiento: datetime
    revocado: bool
    # 🔧 Probado en vivo contra el backend real: faltaba en este esquema (el
    # modelo y el endpoint de revocar siempre la seteaban, pero
    # response_model la descartaba igual que a cualquier atributo no
    # declarado) — sin esto, el frontend nunca podía mostrar cuándo se
    # revocó un consentimiento ya respondido por POST .../revocar.
    fecha_revocacion: Optional[datetime] = None
    # 🆕 Evidencia — metadata de la subida real (ver POST .../evidencia). NULL
    # mientras nadie subió nada, o si evidencia_ruta sigue siendo la nota de
    # texto libre heredada del placeholder (ver comentario en models.py).
    evidencia_nombre_archivo: Optional[str] = None
    evidencia_content_type: Optional[str] = None
    evidencia_tamano_bytes: Optional[int] = None
    evidencia_subido_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConsentimientoAsentimientoResponse(ConsentimientoAsentimientoCreate):
    id: int
    persona_id: int
    institucion_id: int
    tipo_consentimiento: str
    estado: str
    registrado_por_usuario_id: int
    fecha_otorgamiento: datetime
    revocado: bool
    fecha_revocacion: Optional[datetime] = None  # mismo fix que ConsentimientoResponse
    evidencia_nombre_archivo: Optional[str] = None
    evidencia_content_type: Optional[str] = None
    evidencia_tamano_bytes: Optional[int] = None
    evidencia_subido_en: Optional[datetime] = None

    class Config:
        from_attributes = True


class CitaParticipanteResponse(BaseModel):
    persona_id: int
    nombre_completo: str

    class Config:
        from_attributes = True


class CitaCreate(BaseModel):
    """`persona_id` presente = cita INDIVIDUAL de siempre. Ausente = ACTIVIDAD
    GRUPAL (taller, charla...) — en ese caso `titulo` es obligatorio (mismo
    CHECK en models.py) y `participantes_ids` es un roster opcional de
    estudiantes asistentes (puede ir vacío/omitido: una actividad grupal no
    necesita nombrar a nadie). `institucion_id` solo importa para una
    actividad grupal creada por un superadmin (que no tiene institución
    propia) — para cualquier otro rol, o para una cita individual, se
    ignora y se usa la institución real (ver agendar_cita en router.py)."""
    persona_id: Optional[int] = None
    institucion_id: Optional[int] = None
    motivo: str
    fecha_hora: datetime
    titulo: Optional[str] = None
    tipo_actividad: Optional[str] = None  # texto libre: "Taller", "Charla", "Otro"...
    lugar: Optional[str] = None
    participantes_ids: Optional[List[int]] = None


class CitaResponse(BaseModel):
    id: int
    persona_id: Optional[int] = None
    psicologo_id: int
    institucion_id: int
    motivo: str
    fecha_hora: datetime
    estado: str
    titulo: Optional[str] = None
    tipo_actividad: Optional[str] = None
    lugar: Optional[str] = None
    # 🆕 Objetos con nombre, no solo ids -- la agenda los muestra directo sin
    # tener que resolver cada persona_id por separado.
    participantes: List[CitaParticipanteResponse] = []

    class Config:
        from_attributes = True

class CitaUpdate(BaseModel):
    """Todos los campos son opcionales: solo mandas los que quieres cambiar
    (reprogramar horario, cambiar motivo/título/lugar, o marcar como
    Realizada/Cancelada). La lista de participantes no se edita aquí --
    cancela y vuelve a crear la actividad si cambió."""
    motivo: Optional[str] = None
    fecha_hora: Optional[datetime] = None
    estado: Optional[str] = None  # "Programada" | "Realizada" | "Cancelada"
    titulo: Optional[str] = None
    tipo_actividad: Optional[str] = None
    lugar: Optional[str] = None
    
class PersonaUpdate(BaseModel):
    grado_seccion: Optional[str] = None
    codigo_institucional: Optional[str] = None
    email: Optional[str] = None
    genero: Optional[str] = None
    activo: Optional[bool] = None
    # 🆕 PASO 3 — antes solo se podían fijar al CREAR (PersonaBase); no había
    # forma de corregirlos después aunque el candado de institución de
    # editar_persona (router.py) ya autorizaba a cualquier rol de la propia
    # institución a tocar esta fila. No es un cambio de permisos: es la misma
    # autorización que ya regía para genero/email, extendida a estos 4 campos.
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    documento_identidad: Optional[str] = None


class RegistroCambioPersonaResponse(BaseModel):
    id: int
    campo: str
    valor_anterior: Optional[str] = None
    valor_nuevo: Optional[str] = None
    modificado_por_usuario_id: int
    rol_modificador: Optional[str] = None
    fecha: datetime

    class Config:
        from_attributes = True


# ==========================================
# 🆕 NÚCLEO DEL ESTUDIANTE — ESTRUCTURA ACADÉMICA
# ==========================================
class NivelEducativoCreate(BaseModel):
    institucion_id: int
    nombre: str
    orden: int = 0


class NivelEducativoResponse(NivelEducativoCreate):
    id: int
    activo: bool

    class Config:
        from_attributes = True


class GradoCreate(BaseModel):
    # institucion_id NO se pide aquí: se deriva del propio nivel_educativo_id
    # (que ya está validado como perteneciente a una institución) para no
    # abrir un segundo campo que el frontend pudiera hacer no coincidir.
    nivel_educativo_id: int
    nombre: str
    orden: int = 0


class GradoResponse(BaseModel):
    id: int
    institucion_id: int
    nivel_educativo_id: int
    nombre: str
    orden: int
    activo: bool

    class Config:
        from_attributes = True


class SeccionCreate(BaseModel):
    grado_id: int
    nombre: str
    turno: Optional[str] = None
    anio_escolar: int


class SeccionResponse(BaseModel):
    id: int
    institucion_id: int
    grado_id: int
    nombre: str
    turno: Optional[str] = None
    anio_escolar: int
    activo: bool

    class Config:
        from_attributes = True


class MatriculaCreate(BaseModel):
    seccion_id: int


class MatriculaResponse(BaseModel):
    id: int
    persona_id: int
    institucion_id: int
    seccion_id: int
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    registrado_por_usuario_id: Optional[int] = None
    # 🆕 Promoción anual — ver CheckConstraints en models.py.
    motivo_apertura: Optional[str] = None
    motivo_cierre: Optional[str] = None
    motivo_detalle: Optional[str] = None

    class Config:
        from_attributes = True


# ==========================================
# 🆕 PROMOCIÓN ANUAL DE ESTUDIANTES
# ==========================================
# Debe coincidir con crud.TIPOS_EXCEPCION_VALIDOS y con el CHECK
# ck_promocion_detalle_tipo_excepcion_valido — no se importa desde crud.py
# para no crear un ciclo (crud.py ya importa este módulo), mismo criterio
# que _MODOS_INTERPRETACION_VALIDOS en modulos/educativo/schemas.py.
_TIPOS_EXCEPCION_PROMOCION_VALIDOS = {
    "ninguna", "repitente", "retirado", "trasladado", "cambio_manual", "egreso",
}


class ProcesoPromocionCreate(BaseModel):
    # institucion_id: superadmin debe indicarlo explícitamente; el resto
    # siempre usa el suyo (mismo criterio que la importación Excel).
    institucion_id: Optional[int] = None
    anio_origen: int
    anio_destino: int


class ProcesoPromocionResponse(BaseModel):
    id: int
    institucion_id: int
    anio_origen: int
    anio_destino: int
    estado: str
    creado_por_usuario_id: int
    fecha_creacion: datetime
    confirmado_por_usuario_id: Optional[int] = None
    fecha_confirmacion: Optional[datetime] = None

    class Config:
        from_attributes = True


class DetallePromocionEdicion(BaseModel):
    """Una fila a editar: marcar una excepción (repitente/retirado/
    trasladado/cambio_manual/egreso) o confirmar el destino automático
    ('ninguna') con una sección definitiva distinta."""
    detalle_id: int
    tipo_excepcion: str
    seccion_definitiva_id: Optional[int] = None

    @field_validator("tipo_excepcion")
    @classmethod
    def _tipo_excepcion_valido(cls, v: str) -> str:
        if v not in _TIPOS_EXCEPCION_PROMOCION_VALIDOS:
            raise ValueError(
                f"tipo_excepcion debe ser uno de {sorted(_TIPOS_EXCEPCION_PROMOCION_VALIDOS)}, recibido: '{v}'"
            )
        return v


class EditarDetallesPromocionRequest(BaseModel):
    ediciones: List[DetallePromocionEdicion]


# ==========================================
# 🆕 EXPEDIENTE / SEGUIMIENTO DEL ESTUDIANTE
# ==========================================
class ContactoFamiliarCreate(BaseModel):
    nombre: str
    telefono: Optional[str] = None
    relacion: Optional[str] = None   # catálogo abierto: "madre", "padre", "tutor legal"...
    email: Optional[EmailStr] = None


class ContactoFamiliarUpdate(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    relacion: Optional[str] = None
    email: Optional[EmailStr] = None


class ContactoFamiliarResponse(BaseModel):
    id: int
    persona_id: int
    institucion_id: int
    nombre: str
    telefono: Optional[str] = None
    relacion: Optional[str] = None
    # Sin EmailStr en la RESPUESTA (mismo criterio que InstitucionResponse):
    # un dato ya guardado no debe convertir un GET en un 500.
    email: Optional[str] = None
    activo: bool
    fecha_registro: datetime
    registrado_por_usuario_id: Optional[int] = None

    class Config:
        from_attributes = True


# ==========================================
# PersonaDatosFamiliares — bloque "datos familiares" de la ficha del
# estudiante (composición del hogar). 1:1 con Persona, mutable, sin
# versionado propio.
# ==========================================
class PersonaDatosFamiliaresUpdate(BaseModel):
    numero_hermanos: Optional[int] = Field(default=None, ge=0, le=30)
    vive_con: Optional[str] = Field(default=None, max_length=300)
    lugar_nacimiento: Optional[str] = Field(default=None, max_length=200)
    lugar_procedencia: Optional[str] = Field(default=None, max_length=200)


class PersonaDatosFamiliaresResponse(BaseModel):
    persona_id: int
    numero_hermanos: Optional[int] = None
    vive_con: Optional[str] = None
    lugar_nacimiento: Optional[str] = None
    lugar_procedencia: Optional[str] = None
    actualizado_por_usuario_id: Optional[int] = None
    # None = la ficha nunca se editó — nunca una fecha inventada "de ahora
    # mismo" (ver el placeholder que arma el router cuando no hay fila).
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==========================================
# PersonaAntecedentesClinicos — tratamiento externo (terapia psicológica /
# atención psiquiátrica) y diagnóstico reportado. 1:1 con Persona, mutable,
# distinto de PersonaDatosFamiliares (composición del hogar).
# ==========================================
class PersonaAntecedentesClinicosUpdate(BaseModel):
    recibe_terapia_psicologica_externa: Optional[bool] = None
    detalle_terapia_psicologica_externa: Optional[str] = Field(default=None, max_length=2000)
    recibe_atencion_psiquiatrica_externa: Optional[bool] = None
    detalle_atencion_psiquiatrica_externa: Optional[str] = Field(default=None, max_length=2000)
    diagnostico_reportado: Optional[str] = Field(default=None, max_length=2000)


class PersonaAntecedentesClinicosResponse(BaseModel):
    persona_id: int
    recibe_terapia_psicologica_externa: Optional[bool] = None
    detalle_terapia_psicologica_externa: Optional[str] = None
    recibe_atencion_psiquiatrica_externa: Optional[bool] = None
    detalle_atencion_psiquiatrica_externa: Optional[str] = None
    diagnostico_reportado: Optional[str] = None
    actualizado_por_usuario_id: Optional[int] = None
    # None = nunca se editó — mismo criterio que PersonaDatosFamiliaresResponse.
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True


# Debe coincidir con crud.TIPOS_ENTRADA_VALIDOS y con el CHECK
# ck_expediente_tipo_entrada_valido — no se importa desde crud.py para no
# crear un ciclo, mismo criterio que _TIPOS_EXCEPCION_PROMOCION_VALIDOS.
_TIPOS_ENTRADA_EXPEDIENTE_VALIDOS = {
    "observacion_conducta", "contacto_apoderado", "derivacion", "sesion", "aplicacion_prueba",
}


class EntradaExpedienteCreate(BaseModel):
    tipo_entrada: str
    fecha_entrada: Optional[datetime] = None   # None -> ahora
    # Contenido narrativo — solo para 'observacion_conducta'/'contacto_apoderado'/'derivacion'.
    motivo: Optional[str] = None
    contenido: Optional[str] = None
    interpretacion: Optional[str] = None
    diagnostico_presuntivo: Optional[str] = None
    # Enlaces — exactamente uno según tipo_entrada, validado en crud.py
    # contra ck_expediente_campos_segun_tipo antes de tocar la BD.
    sesion_seguimiento_id: Optional[int] = None
    informe_id: Optional[int] = None
    contacto_familiar_id: Optional[int] = None

    @field_validator("tipo_entrada")
    @classmethod
    def _tipo_entrada_valido(cls, v: str) -> str:
        if v not in _TIPOS_ENTRADA_EXPEDIENTE_VALIDOS:
            raise ValueError(
                f"tipo_entrada debe ser uno de {sorted(_TIPOS_ENTRADA_EXPEDIENTE_VALIDOS)}, recibido: '{v}'"
            )
        return v


class EntradaExpedienteVersionCreate(BaseModel):
    """Agregar una corrección/actualización de contenido — SIEMPRE v2+
    (la v1 se crea junto con la entrada), así que `motivo_version` es
    obligatorio aquí sin excepción, mismo criterio que reemitir un informe."""
    motivo: Optional[str] = None
    contenido: Optional[str] = None
    interpretacion: Optional[str] = None
    diagnostico_presuntivo: Optional[str] = None
    motivo_version: str

    @field_validator("motivo_version")
    @classmethod
    def _motivo_version_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("motivo_version es obligatorio para corregir una entrada ya creada.")
        return v


class EntradaExpedienteResponse(BaseModel):
    """Metadata únicamente — nunca contenido narrativo. Es lo que devuelve
    el listado; el detalle completo (con contenido) es un endpoint aparte
    que además audita la lectura."""
    id: int
    persona_id: int
    institucion_id: int
    tipo_entrada: str
    autor_usuario_id: int
    fecha_entrada: datetime
    creado_en: datetime
    version_actual: Optional[int] = None
    sesion_seguimiento_id: Optional[int] = None
    informe_id: Optional[int] = None
    contacto_familiar_id: Optional[int] = None
    # 🔧 FIX: los otros dos puentes (sesion_seguimiento_id/informe_id) ya
    # exponían su id destino; a este le faltaba, dejando al llamador sin
    # forma de saber a qué DocumentoInstitucional apunta una entrada
    # tipo_entrada='documento_institucional' sin ir directo a la BD.
    documento_institucional_id: Optional[int] = None
    # 🆕 Solo poblados para tipo_entrada='evidencia' (ver EntradaExpediente
    # en models.py) — None para los otros 6 tipos. Nunca el binario en sí:
    # eso se descarga aparte, GET /expediente/evidencia/{id}/archivo.
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    nombre_archivo_original: Optional[str] = None
    content_type: Optional[str] = None
    incluir_en_pdf_informe: bool = False

    class Config:
        from_attributes = True


class EntradaExpedienteEvidenciaUpdate(BaseModel):
    """Único campo editable de una evidencia ya subida — para cambiar el
    archivo/título hay que registrar una entrada nueva (ver docstring de
    EntradaExpediente: append-only, nunca se sobrescribe)."""
    incluir_en_pdf_informe: bool


class AutorizacionAccesoColegioCreate(BaseModel):
    motivo: str

    @field_validator("motivo")
    @classmethod
    def _motivo_no_vacio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("motivo es obligatorio para otorgar acceso al colegio.")
        return v


class AutorizacionAccesoColegioResponse(BaseModel):
    id: int
    persona_id: int
    institucion_id: int
    otorgado_por_usuario_id: int
    rol_otorgante: Optional[str] = None
    motivo: str
    fecha_otorgado: datetime
    vigente: bool
    fecha_revocado: Optional[datetime] = None
    revocado_por_usuario_id: Optional[int] = None
    rol_revocador: Optional[str] = None

    class Config:
        from_attributes = True