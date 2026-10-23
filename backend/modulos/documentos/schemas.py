from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from typing import Optional, List, Dict, Any

# 🔒 Mismo criterio que _MODOS_INTERPRETACION_VALIDOS en
# modulos/educativo/schemas.py: el set válido se duplica aquí (no se importa
# de models.py) para que el esquema de entrada rechace un valor inválido
# ANTES de tocar la base de datos. Debe coincidir exactamente con los CHECK
# de modulos/documentos/models.py — si un CHECK cambia, este set cambia con él.
_ALCANCES_VALIDOS = {"institucion", "estructura_academica", "personas_especificas", "ninguno"}
_VISIBILIDADES_VALIDAS = {"confidencial_clinico", "compartible_colegio"}
_TIPOS_SECCION_VALIDOS = {
    "encabezado", "datos_filiacion", "datos_familiares",
    "texto_libre", "tabla_dinamica", "resultados_prueba", "firma", "grupo_campos", "firma_doble",
    "ficha_imprimible", "grafico_barras", "imagen_anexo", "firma_triple", "resultados_prueba_multiple",
}


def _parsear_lista_csv(valor: str) -> List[str]:
    return [v.strip() for v in valor.split(",") if v.strip()]


def _validar_subconjunto_csv(valor: str, validos: set, nombre_campo: str) -> str:
    """Normaliza y valida una lista separada por comas (mismo formato que
    `Prueba.tecnicas_adicionales`) contra un vocabulario cerrado. Se usa
    para `alcances_permitidos`/`visibilidades_permitidas`: TipoDocumento no
    decide qué valores EXISTEN (eso lo fijan los CHECK de
    DocumentoInstitucional), solo cuáles de esos valores ya-válidos puede
    ofrecer este tipo en particular."""
    partes = _parsear_lista_csv(valor)
    if not partes:
        raise ValueError(f"{nombre_campo} no puede quedar vacío.")
    desconocidos = set(partes) - validos
    if desconocidos:
        raise ValueError(
            f"{nombre_campo} contiene valores no reconocidos: {sorted(desconocidos)}. "
            f"Válidos: {sorted(validos)}."
        )
    return ", ".join(partes)


def _validar_formato_correlativo(v: Optional[str]) -> Optional[str]:
    """Dry-run del formato AL GUARDAR la plantilla — un placeholder inválido
    debe fallar aquí (422, configuración), nunca en el momento real de
    emitir un documento (Paso 5)."""
    if v is None:
        return v
    try:
        v.format(correlativo=1, anio=2026)
    except (KeyError, ValueError, IndexError) as exc:
        raise ValueError(
            "formato_correlativo inválido: solo admite los placeholders "
            "{correlativo} y {anio} (ej. 'INFORME-{correlativo:04d}-{anio}'). "
            f"Detalle: {exc}"
        )
    return v


# ==========================================
# TipoDocumento — catálogo global (solo superadmin escribe)
# ==========================================
class TipoDocumentoBase(BaseModel):
    clave: str = Field(min_length=2, max_length=100)
    nombre: str = Field(min_length=2, max_length=200)
    alcances_permitidos: str
    visibilidades_permitidas: str
    requiere_consentimiento_individual: bool = False
    activo: bool = True

    @field_validator("alcances_permitidos")
    @classmethod
    def _val_alcances(cls, v: str) -> str:
        return _validar_subconjunto_csv(v, _ALCANCES_VALIDOS, "alcances_permitidos")

    @field_validator("visibilidades_permitidas")
    @classmethod
    def _val_visibilidades(cls, v: str) -> str:
        return _validar_subconjunto_csv(v, _VISIBILIDADES_VALIDAS, "visibilidades_permitidas")


class TipoDocumentoCreate(TipoDocumentoBase):
    pass


class TipoDocumentoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=200)
    alcances_permitidos: Optional[str] = None
    visibilidades_permitidas: Optional[str] = None
    requiere_consentimiento_individual: Optional[bool] = None
    activo: Optional[bool] = None

    @field_validator("alcances_permitidos")
    @classmethod
    def _val_alcances(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _validar_subconjunto_csv(v, _ALCANCES_VALIDOS, "alcances_permitidos")

    @field_validator("visibilidades_permitidas")
    @classmethod
    def _val_visibilidades(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _validar_subconjunto_csv(v, _VISIBILIDADES_VALIDAS, "visibilidades_permitidas")


class TipoDocumentoResponse(TipoDocumentoBase):
    id: int

    class Config:
        from_attributes = True


# ==========================================
# AnioOficial — catálogo global chico (solo superadmin escribe)
# ==========================================
class AnioOficialCreate(BaseModel):
    anio: int = Field(ge=2000, le=2100)
    texto: str = Field(min_length=3, max_length=300)


class AnioOficialResponse(AnioOficialCreate):
    class Config:
        from_attributes = True


# ==========================================
# PlantillaDocumento — por institución; admin/psicólogo de la institución
# dueña la arman y editan (el "constructor"), ver permisos.STAFF_CLINICO en
# router.py. institucion_id=None es la plantilla PREDETERMINADA global
# (solo superadmin la crea/edita) — cualquier STAFF_CLINICO puede clonarla
# (o clonar una propia de su institución) a su propia institución.
# ==========================================
class PlantillaDocumentoBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    fuente: str = Field(default="Arial", max_length=100)
    tamano_pt: int = Field(default=11, ge=6, le=48)
    interlineado: float = Field(default=1.15, ge=1.0, le=3.0)
    justificado: bool = True
    # Estilo del título del documento — independiente del cuerpo, ver
    # docstring de PlantillaDocumento en models.py.
    titulo_negrita: bool = True
    titulo_cursiva: bool = False
    titulo_tamano_pt: Optional[int] = Field(default=None, ge=6, le=72)
    # 🆕 Tamaño del subtítulo de cada sección — NULL = tamano_pt + 1 (fórmula
    # de siempre), mismo criterio que titulo_tamano_pt. Siempre negrita
    # (no configurable, nunca se pidió).
    subtitulo_tamano_pt: Optional[int] = Field(default=None, ge=6, le=48)
    # 🆕 Fondo de página de la institución (Institucion.fondo_documento_url)
    # — apagado por defecto, ver docstring de PlantillaDocumento en models.py.
    mostrar_fondo_institucion: bool = False
    formato_correlativo: Optional[str] = Field(default=None, max_length=200)
    correlativo_reinicia_anualmente: bool = False
    # Enganche automático examen -> documento (ver modelo). False por
    # defecto: una plantilla nueva nunca empieza generando documentos solos.
    generar_automaticamente_al_finalizar_examen: bool = False

    @field_validator("formato_correlativo")
    @classmethod
    def _val_formato_correlativo(cls, v: Optional[str]) -> Optional[str]:
        return _validar_formato_correlativo(v)


class PlantillaDocumentoCreate(PlantillaDocumentoBase):
    # 🆕 NULL = esta plantilla es la PREDETERMINADA global (ver docstring de
    # PlantillaDocumento en models.py) — solo superadmin puede crearla así
    # (candado en router.py/crud.py, no aquí: el esquema de entrada no
    # conoce el rol del caller). Un admin/psicólogo de STAFF_CLINICO que
    # intente crear con institucion_id=None es rechazado en crud; si manda
    # un institucion_id que no es el suyo, también.
    institucion_id: Optional[int] = None
    tipo_documento_id: int
    activa: bool = True


class PlantillaDocumentoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=200)
    activa: Optional[bool] = None
    fuente: Optional[str] = Field(default=None, max_length=100)
    tamano_pt: Optional[int] = Field(default=None, ge=6, le=48)
    interlineado: Optional[float] = Field(default=None, ge=1.0, le=3.0)
    justificado: Optional[bool] = None
    titulo_negrita: Optional[bool] = None
    titulo_cursiva: Optional[bool] = None
    titulo_tamano_pt: Optional[int] = Field(default=None, ge=6, le=72)
    subtitulo_tamano_pt: Optional[int] = Field(default=None, ge=6, le=48)
    mostrar_fondo_institucion: Optional[bool] = None
    formato_correlativo: Optional[str] = Field(default=None, max_length=200)
    correlativo_reinicia_anualmente: Optional[bool] = None
    generar_automaticamente_al_finalizar_examen: Optional[bool] = None

    @field_validator("formato_correlativo")
    @classmethod
    def _val_formato_correlativo(cls, v: Optional[str]) -> Optional[str]:
        return _validar_formato_correlativo(v)


class PlantillaDocumentoResponse(PlantillaDocumentoBase):
    id: int
    # NULL = plantilla predeterminada global, ver PlantillaDocumentoCreate.
    institucion_id: Optional[int] = None
    tipo_documento_id: int
    activa: bool
    creado_por_usuario_id: int
    creado_en: datetime

    class Config:
        from_attributes = True


class PlantillaDocumentoClonar(BaseModel):
    """Copia la ESTRUCTURA (secciones, orden, tipo, config) de una plantilla
    existente a una institución nueva — pensado para no rearmar cada colegio
    desde cero cuando pide, en esencia, el mismo tipo de informe que otro ya
    tiene (solo cambia tipografía/logo/textos puntuales). Nunca copia
    contenido de ningún documento ya emitido: eso es siempre propio de la
    institución de origen."""
    institucion_destino_id: int
    nombre: Optional[str] = Field(default=None, min_length=2, max_length=200)
    activar: bool = False


# ==========================================
# PlantillaSeccion
# ==========================================
class PlantillaSeccionBase(BaseModel):
    orden: int = Field(ge=0)
    tipo_seccion: str
    titulo: Optional[str] = Field(default=None, max_length=200)
    config: Optional[Dict[str, Any]] = None

    @field_validator("tipo_seccion")
    @classmethod
    def _val_tipo_seccion(cls, v: str) -> str:
        if v not in _TIPOS_SECCION_VALIDOS:
            raise ValueError(f"tipo_seccion debe ser uno de {sorted(_TIPOS_SECCION_VALIDOS)}.")
        return v


class PlantillaSeccionCreate(PlantillaSeccionBase):
    pass


class PlantillaSeccionUpdate(BaseModel):
    orden: Optional[int] = Field(default=None, ge=0)
    titulo: Optional[str] = Field(default=None, max_length=200)
    config: Optional[Dict[str, Any]] = None
    # tipo_seccion deliberadamente NO editable: cambiar el tipo de una
    # sección ya creada invalidaría cualquier contenido de borrador ya
    # escrito contra su forma anterior (Paso 4). Para cambiar el tipo, se
    # borra la sección y se crea otra.


class PlantillaSeccionResponse(PlantillaSeccionBase):
    id: int
    plantilla_documento_id: int
    creado_en: datetime

    class Config:
        from_attributes = True


# ==========================================
# DocumentoInstitucional — creación (Paso 3). `institucion_id` NUNCA se
# acepta aquí: se deriva de `plantilla_documento_id` en el CRUD (rule 6 —
# nunca confiar en un institucion_id que mande el cliente), y se re-valida
# contra la institución del usuario autenticado.
# ==========================================
class NodoEstructuraSeleccion(BaseModel):
    """Un nodo del atajo por sección — exactamente uno de los tres campos,
    igual criterio que el CHECK `ck_documentos_estructura_un_solo_nivel`."""
    nivel_educativo_id: Optional[int] = None
    grado_id: Optional[int] = None
    seccion_id: Optional[int] = None

    @model_validator(mode="after")
    def _exactamente_uno(self):
        elegidos = [v for v in (self.nivel_educativo_id, self.grado_id, self.seccion_id) if v is not None]
        if len(elegidos) != 1:
            raise ValueError(
                "Cada nodo de estructura debe traer exactamente uno de "
                "nivel_educativo_id/grado_id/seccion_id."
            )
        return self


class DocumentoInstitucionalCreate(BaseModel):
    tipo_documento_id: int
    plantilla_documento_id: int
    alcance: str
    nivel_visibilidad: str = "confidencial_clinico"
    titulo: str = Field(min_length=2, max_length=300)
    # Obligatorio solo si algún nodo de `estructura` es nivel_educativo_id o
    # grado_id — una Seccion concreta ya trae su propio anio_escolar (ver
    # crud._resolver_personas_de_nodo).
    anio_escolar: Optional[int] = Field(default=None, ge=2000, le=2100)
    estructura: List[NodoEstructuraSeleccion] = Field(default_factory=list)
    personas_ids: List[int] = Field(default_factory=list)

    @field_validator("alcance")
    @classmethod
    def _val_alcance(cls, v: str) -> str:
        if v not in _ALCANCES_VALIDOS:
            raise ValueError(f"alcance debe ser uno de {sorted(_ALCANCES_VALIDOS)}.")
        return v

    @field_validator("nivel_visibilidad")
    @classmethod
    def _val_visibilidad(cls, v: str) -> str:
        if v not in _VISIBILIDADES_VALIDAS:
            raise ValueError(f"nivel_visibilidad debe ser uno de {sorted(_VISIBILIDADES_VALIDAS)}.")
        return v

    @model_validator(mode="after")
    def _coherencia_alcance_seleccion(self):
        """Regla técnica (no de producto): 'estructura_academica' admite
        combinar el atajo por sección con nombres sueltos (personas_ids
        encima); 'personas_especificas' es selección manual PURA — si hace
        falta un atajo por sección, el alcance correcto es
        'estructura_academica'. 'institucion'/'ninguno' nunca llevan
        estudiantes ligados (deben producir cero filas en la lista
        congelada)."""
        if self.alcance in ("institucion", "ninguno"):
            if self.estructura or self.personas_ids:
                raise ValueError(
                    f"alcance='{self.alcance}' no admite estudiantes ligados "
                    "(ni 'estructura' ni 'personas_ids')."
                )
        elif self.alcance == "estructura_academica":
            if not self.estructura:
                raise ValueError("alcance='estructura_academica' necesita al menos un nodo en 'estructura'.")
        elif self.alcance == "personas_especificas":
            if self.estructura:
                raise ValueError(
                    "alcance='personas_especificas' es selección manual pura: no admite "
                    "'estructura' (usa 'estructura_academica' para combinar un atajo por "
                    "sección con nombres sueltos)."
                )
            if not self.personas_ids:
                raise ValueError("alcance='personas_especificas' necesita al menos una persona en 'personas_ids'.")
        return self


class DocumentoInstitucionalEstudianteResponse(BaseModel):
    persona_id: int
    incluido_via: str
    nombre_completo_historico: Optional[str] = None
    seccion_id_historico: Optional[int] = None
    grado_seccion_historico: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentoInstitucionalResponse(BaseModel):
    id: int
    institucion_id: int
    tipo_documento_id: int
    plantilla_documento_id: int
    alcance: str
    nivel_visibilidad: str
    titulo: str
    version_actual: Optional[int] = None
    creado_por_usuario_id: int
    creado_en: datetime

    class Config:
        from_attributes = True


class DocumentoInstitucionalDetalleResponse(DocumentoInstitucionalResponse):
    """Igual que DocumentoInstitucionalResponse + la lista congelada de
    estudiantes — solo en el detalle, nunca en un listado (evita cargar
    N listas completas al listar documentos de una institución)."""
    estudiantes: List[DocumentoInstitucionalEstudianteResponse] = []


# ==========================================
# DocumentoInstitucionalSeccionContenido — borrador editable (Paso 4).
# `contenido` es JSON de forma libre a propósito: no todos los tipo_seccion
# lo usan de la misma manera (texto_libre/tabla_dinamica lo escribe la
# psicóloga; datos_filiacion/datos_familiares/resultados_prueba/encabezado
# son mayormente automáticos y el Paso 5 decide qué parte de esto, si
# alguna, realmente usa al ensamblar la versión) — fijar aquí una forma
# estricta por tipo sería adelantarse al ensamblador real. La única
# validación de forma es que `contenido` sea un objeto JSON (o None), nunca
# un array/string/número suelto — eso ya lo garantiza el tipado Dict[str, Any].
# ==========================================
class DocumentoInstitucionalSeccionContenidoUpdate(BaseModel):
    contenido: Optional[Dict[str, Any]] = None


class DocumentoInstitucionalSeccionContenidoResponse(BaseModel):
    plantilla_seccion_id: int
    tipo_seccion: str
    titulo: Optional[str] = None
    orden: int
    contenido: Optional[Dict[str, Any]] = None
    editado_por_usuario_id: Optional[int] = None
    # None = la sección todavía no se tocó (no hay fila de contenido
    # propia todavía) — distinto de "se guardó vacío", que sí tendría fecha.
    actualizado_en: Optional[datetime] = None


# ==========================================
# DocumentoInstitucionalResultadoPrueba — a qué Inscripcion real referencia
# una sección 'resultados_prueba', para un estudiante puntual del documento.
# ==========================================
class DocumentoInstitucionalResultadoPruebaCreate(BaseModel):
    persona_id: int
    inscripcion_id: int


class DocumentoInstitucionalResultadoPruebaResponse(BaseModel):
    id: int
    documento_institucional_id: int
    plantilla_seccion_id: int
    persona_id: int
    inscripcion_id: int

    class Config:
        from_attributes = True


# 🆕 PUT .../resultados-prueba-multiple — a diferencia de
# DocumentoInstitucionalResultadoPruebaCreate (un solo inscripcion_id, su
# propia tabla), esta sección consolida una lista VARIABLE de aplicaciones
# reales en una única sección 'resultados_prueba_multiple'; se guarda en
# DocumentoInstitucionalSeccionContenido.contenido (no en
# DocumentoInstitucionalResultadoPrueba) — ver crud.vincular_resultados_
# prueba_multiple. Reemplazo total, lista vacía = desvincular todas.
class ResultadosPruebaMultipleRequest(BaseModel):
    persona_id: int
    inscripcion_ids: List[int] = Field(default_factory=list)


# ==========================================
# DocumentoInstitucionalVersion — generar/reemitir (Paso 5).
# ==========================================
class ReemitirDocumentoRequest(BaseModel):
    """Solo para v2+ — mismo patrón que ReemitirInformeRequest. v1
    ('Emisión inicial') no exige body; POST /generar-version no toma ninguno."""
    motivo: str = Field(min_length=3, max_length=1000)


class DocumentoInstitucionalVersionResponse(BaseModel):
    """Solo metadata — el contenido_snapshot completo nunca viaja en esta
    respuesta (es JSON grande, pensado para reconstrucción/auditoría, no
    para listar)."""
    id: int
    documento_institucional_id: int
    numero_version: int
    nombre_archivo: str
    mime_type: str
    tamano_bytes: int
    checksum_sha256: str
    generado_en: datetime
    generado_por_usuario_id: int
    motivo_version: Optional[str] = None

    class Config:
        from_attributes = True
