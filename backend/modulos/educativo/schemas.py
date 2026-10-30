from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Literal
from enum import Enum

# 🔒 ENUMS ESTRICTOS PARA VALIDACIÓN DE DEMOGRÁFICOS
class SexoEnum(str, Enum):
    MASCULINO = "Masculino"
    FEMENINO = "Femenino"

class PoblacionEnum(str, Enum):
    PRIMARIA = "Primaria"
    SECUNDARIA = "Secundaria"
    UNIVERSITARIO = "Universitario"

# ==========================================
# ESQUEMAS PARA INSCRIPCIONES (LINKS MÁGICOS DE ALUMNOS)
# ==========================================
class InscripcionResponse(BaseModel):
    id: int
    evaluacion_id: int
    token: str
    nombre_completo: Optional[str] = None
    edad: Optional[int] = None
    sexo: Optional[str] = None
    poblacion: Optional[str] = None
    estado: str
    fecha_resolucion: Optional[datetime] = None
    resultado_visible_alumno: bool = True
    informe_liberado: bool = True
    # Permite al panel del psicólogo distinguir "sin alerta" de "no se pudo
    # interpretar", que exigen acciones distintas (B-6).
    estado_interpretacion: str = "completa"
    dimensiones_sin_baremo: Optional[str] = None
    informante_tipo: str = "estudiante"
    informante_nombre: Optional[str] = None
    informante_relacion: Optional[str] = None

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA LA FICHA SOCIODEMOGRÁFICA
# ==========================================
class CampoSociodemograficoBase(BaseModel):
    pregunta: str
    tipo_respuesta: str # Ej: "texto", "numero", "opciones"
    opciones: Optional[str] = None
    obligatorio: bool = True

class CampoSociodemograficoCreate(CampoSociodemograficoBase):
    cliente_id: int

class CampoSociodemograficoResponse(CampoSociodemograficoBase):
    id: int

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA EL MOTOR DE TESTS
# ==========================================
# Mismo criterio que _AMBITOS_REGLA/_OPERADORES_REGLA más abajo: el set
# válido se duplica aquí en vez de importarse de models.py, para que el
# schema de entrada rechace un valor inválido ANTES de tocar la base de
# datos. "perfil" ya tiene algoritmo real (crud.interpretar_perfil_alumno,
# ver Prueba.modo_interpretacion en models.py) — solo se puede fijar al
# CREAR una prueba (PruebaCreate), nunca por PATCH (PruebaUpdate no lo
# expone a propósito).
_MODOS_INTERPRETACION_VALIDOS = {"rango", "perfil"}

# 🔒 Mismo criterio: duplicado de models.INFORMANTES_VALIDOS para que el
# schema de entrada rechace un valor inválido antes de tocar la BD.
_INFORMANTES_VALIDOS = {"estudiante", "padre_madre", "docente"}


class PruebaBase(BaseModel):
    nombre_tecnico: str
    nombre_publico: str
    # 🆕 Ver Prueba.nombre_corto en models.py — None = la UI debe usar
    # nombre_tecnico como título corto de respaldo.
    nombre_corto: Optional[str] = None
    instrucciones: Optional[str] = None
    requiere_consentimiento: bool = True
    activa: bool = True
    escala_minima: int = 0
    escala_maxima: int = 3
    modo_calculo: str = "likert_suma"
    # 🆕 Espejo de modo_calculo para la interpretación (ver models.py). Solo
    # admite "rango" por ahora — no confundir con una lista abierta.
    modo_interpretacion: str = "rango"
    # 🆕 Catálogo genérico (ver models.py): True = aparece en el catálogo que
    # ve una institución y admite campañas nuevas de no-superadmin. Default
    # True conserva el comportamiento de siempre para toda prueba existente.
    visible_para_clientes: bool = True
    # 🆕 Informe profesional — contenido configurado por la prueba (ver
    # "FUENTES DE CONTENIDO DEL INFORME"). Ninguno se inventa si falta.
    motivo_consulta_default: Optional[str] = Field(default=None, max_length=2000)
    tecnicas_adicionales: Optional[str] = Field(default=None, max_length=1000)
    # 🆕 Fallback de la sección 4 (observación conductual) — mismo mecanismo
    # que motivo_consulta_default, ver Prueba.observacion_conductual_default
    # en models.py. Inscripcion.observacion_conductual (el profesional)
    # SIEMPRE prevalece si está presente.
    observacion_conductual_default: Optional[str] = Field(default=None, max_length=3000)
    # 🆕 Ver Prueba.recomendacion_generica_default en models.py — recomendación
    # fija de la prueba para la sección 7, independiente del tramo alcanzado.
    recomendacion_generica_default: Optional[str] = Field(default=None, max_length=4000)
    # 🆕 Quién responde esta prueba (ver models.INFORMANTES_VALIDOS). Default
    # "estudiante" conserva el comportamiento de toda prueba existente. Una
    # batería con versión docente Y versión padres se carga como DOS Prueba
    # distintas, cada una con este campo puesto a su propio valor.
    informante_tipo: str = "estudiante"

    # 🆕 Ver Prueba.criterio_normativo_activo en models.py. None (default)
    # conserva el comportamiento de toda prueba existente — interpretar
    # contra los tramos de Baremo con criterio_normativo IS NULL.
    criterio_normativo_activo: Optional[str] = None

    # 🆕 Ver Prueba.ordenar_dimensiones_por_puntaje en models.py — "Diseño A"
    # para pruebas de perfil (IPIP-RIASEC). Default False conserva el orden
    # de siempre para toda prueba existente.
    ordenar_dimensiones_por_puntaje: bool = False

    # 🆕 Ver Prueba.agrupar_dimensiones_por_area en models.py — agrupamiento
    # por área en la sección 5.2 para pruebas con dimensiones pareadas
    # Intereses/Aptitudes (CHASIDE). Default False conserva el listado plano
    # de siempre para toda prueba existente.
    agrupar_dimensiones_por_area: bool = False

    @field_validator("modo_interpretacion")
    @classmethod
    def _modo_interpretacion_valido(cls, v: str) -> str:
        if v not in _MODOS_INTERPRETACION_VALIDOS:
            raise ValueError(f"modo_interpretacion debe ser uno de {sorted(_MODOS_INTERPRETACION_VALIDOS)}.")
        return v

    @field_validator("informante_tipo")
    @classmethod
    def _informante_tipo_valido(cls, v: str) -> str:
        if v not in _INFORMANTES_VALIDOS:
            raise ValueError(f"informante_tipo debe ser uno de {sorted(_INFORMANTES_VALIDOS)}.")
        return v

class PruebaCreate(PruebaBase):
    # El router lo sobrescribe con la institución de la sesión cuando el
    # usuario no es superadmin, así que lo que mande el cliente aquí nunca
    # sirve para colarse en otro colegio. Debe estar declarado igualmente:
    # en Pydantic v2 asignar un atributo no declarado lanza ValueError, que
    # era justamente lo que rompía la creación de pruebas (B-2).
    # None = prueba pública del catálogo (solo superadmin).
    institucion_id: Optional[int] = None

class PruebaResponse(PruebaBase):
    id: int

    class Config:
        from_attributes = True

class PreguntaBase(BaseModel):
    texto_pregunta: str
    orden: int
    dimension_id: Optional[int] = None
    es_inverso: bool = False
    # 🆕 Ver Pregunta.incluir_en_informe/etiqueta_informe en models.py — ítem
    # informativo que no puntúa (típicamente con dimension_id=None), cuya
    # respuesta se imprime literal en el informe PDF bajo esta etiqueta.
    incluir_en_informe: bool = False
    etiqueta_informe: Optional[str] = None
    # 🆕 Ver Pregunta.escala_minima/escala_maxima en models.py (auditoría de
    # motor, sesión 2026-10-13). None (default) = usa la escala de la Prueba
    # como respaldo, igual que siempre. Solo hace falta fijarlos aquí para un
    # ítem cuya escala real difiera de la del resto de la prueba.
    escala_minima: Optional[int] = None
    escala_maxima: Optional[int] = None

class PreguntaCreate(PreguntaBase):
    prueba_id: int

class PreguntaResponse(PreguntaBase):
    id: int
    prueba_id: int

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA OPCIONES DE RESPUESTA
# ==========================================
class OpcionRespuestaBase(BaseModel):
    texto_opcion: str
    # 🔢 C-1 — admite ítems ponderados (0.5, 1.25...). Un entero sigue valiendo.
    valor_puntuacion: float

class OpcionRespuestaCreate(OpcionRespuestaBase):
    pregunta_id: int

class OpcionRespuestaResponse(OpcionRespuestaBase):
    id: int
    pregunta_id: int

    class Config:
        from_attributes = True

# 🟢 Definida ANTES para que DimensionConPreguntas pueda usarla
class PreguntaConOpciones(PreguntaResponse):
    opciones: List[OpcionRespuestaResponse] = []

# ==========================================
# ESQUEMAS PARA DIMENSIONES / ESCALAS
# ==========================================
# 🔒 Mismo criterio que _MODOS_INTERPRETACION_VALIDOS/_INFORMANTES_VALIDOS
# arriba: duplicado de models.TIPOS_CALCULO_DIMENSION_VALIDOS para que el
# schema de entrada rechace un valor inválido antes de tocar la BD.
_TIPOS_CALCULO_DIMENSION_VALIDOS = {"items", "suma_de_dimensiones", "conteo_sintomas"}


class DimensionBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    # 🆕 Ver Dimension.tipo_calculo en models.py. Default "items" conserva el
    # comportamiento de toda dimensión existente (suma de sus propias
    # Pregunta). "suma_de_dimensiones" no tiene preguntas propias — ver
    # DimensionComponente/PUT .../componentes. "conteo_sintomas" SÍ tiene
    # preguntas propias, pero su puntaje es un conteo de ítems que alcanzan
    # `conteo_umbral_item`, no una suma — ver NICHQ Vanderbilt en models.py.
    tipo_calculo: str = "items"
    conteo_umbral_item: Optional[int] = None

    @field_validator("tipo_calculo")
    @classmethod
    def _tipo_calculo_valido(cls, v: str) -> str:
        if v not in _TIPOS_CALCULO_DIMENSION_VALIDOS:
            raise ValueError(f"tipo_calculo debe ser uno de {sorted(_TIPOS_CALCULO_DIMENSION_VALIDOS)}")
        return v

    @model_validator(mode="after")
    def _conteo_umbral_requerido_si_corresponde(self):
        if self.tipo_calculo == "conteo_sintomas" and self.conteo_umbral_item is None:
            raise ValueError("una dimensión 'conteo_sintomas' requiere conteo_umbral_item")
        return self

class DimensionCreate(DimensionBase):
    prueba_id: int

class DimensionResponse(DimensionBase):
    id: int
    prueba_id: int

    class Config:
        from_attributes = True


# ==========================================
# ESQUEMAS PARA COMPOSICIÓN DE DIMENSIONES COMPUESTAS
# ==========================================
class DimensionComponenteItem(BaseModel):
    """Un componente dentro de la lista que alimenta a una dimensión
    'suma_de_dimensiones' — ver PUT /dimensiones/{id}/componentes."""
    dimension_componente_id: int
    orden: int = 0

class DimensionComponentesReplace(BaseModel):
    """Reemplazo COMPLETO (no merge) de los componentes de una dimensión
    compuesta — mismo criterio que PUT /documentos/{id}/secciones/{...}."""
    componentes: List[DimensionComponenteItem] = []

class DimensionComponenteResponse(BaseModel):
    id: int
    dimension_compuesta_id: int
    dimension_componente_id: int
    orden: int

    class Config:
        from_attributes = True

class DimensionConPreguntas(DimensionResponse):
    preguntas: List[PreguntaConOpciones] = []

# ==========================================
# ESQUEMAS PARA RESPUESTAS DEL ALUMNO (EXAMEN EN VIVO)
# ==========================================
class RespuestaAlumnoBase(BaseModel):
    inscripcion_id: int
    pregunta_id: int
    opcion_id: int

class RespuestaAlumnoCreate(RespuestaAlumnoBase):
    pass

class RespuestaAlumnoResponse(RespuestaAlumnoBase):
    id: int
    puntaje_obtenido: float

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA RESULTADOS DE DIMENSIONES
# ==========================================
class ResultadoDimensionBase(BaseModel):
    inscripcion_id: int
    dimension_id: int
    puntaje_directo: float

class ResultadoDimensionCreate(ResultadoDimensionBase):
    pass

class ResultadoDimensionResponse(ResultadoDimensionBase):
    id: int

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA BAREMOS (INTERPRETACIÓN)
# ==========================================
class BaremoBase(BaseModel):
    edad_min: Optional[int] = None
    edad_max: Optional[int] = None
    sexo: Optional[str] = None
    poblacion: Optional[str] = None
    
    # 🔢 C-1 — decimales permitidos, para poder cubrir sin huecos una prueba
    # cuyos puntajes no son enteros (p. ej. 0–4.99 y 5–9.99).
    puntaje_minimo: float
    puntaje_maximo: float
    
    tipo_puntaje: Optional[str] = None
    valor_convertido: Optional[str] = None

    nivel: str
    interpretacion: Optional[str] = None

    # 🆕 Ver Baremo.criterio_normativo en models.py. None (default) conserva
    # el comportamiento de todo baremo existente — "el único criterio".
    criterio_normativo: Optional[str] = None

    # 🆕 Informe profesional — sugerencias de contenido para este TRAMO
    # concreto (ver Baremo.conclusion_sugerida/recomendacion_sugerida). El
    # profesional puede sustituirlas al revisar el informe.
    conclusion_sugerida: Optional[str] = Field(default=None, max_length=3000)
    recomendacion_sugerida: Optional[str] = Field(default=None, max_length=3000)

    # 🚨 Indicador explícito: marca este tramo como caso que exige revisión
    # profesional antes de entregar nada al alumno. `nivel` queda libre para
    # redactarse como el psicólogo quiera sin afectar a la protección.
    es_alerta: bool = False

    # 📏 Fase 4 — validación psicométrica mínima: antes no se comprobaba nada
    # y un tramo invertido (mínimo > máximo) simplemente no encajaba nunca en
    # la consulta `interpretar_resultados_alumno`, así que el alumno caía en
    # "sin baremo" sin que nadie viera el porqué. Ahora se rechaza al cargarlo.
    @model_validator(mode="after")
    def _rangos_coherentes(self):
        if self.puntaje_minimo > self.puntaje_maximo:
            raise ValueError(
                "puntaje_minimo no puede ser mayor que puntaje_maximo."
            )
        if self.edad_min is not None and self.edad_max is not None and self.edad_min > self.edad_max:
            raise ValueError("edad_min no puede ser mayor que edad_max.")
        return self

class BaremoCreate(BaremoBase):
    dimension_id: int

class BaremoResponse(BaremoBase):
    id: int
    dimension_id: int
    # 🆕 Solo lectura — ver Baremo.activo/actualizado_en en models.py.
    activo: bool = True
    actualizado_en: Optional[datetime] = None

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA REGLAS DE INTERPRETACIÓN (genéricas, por prueba)
# ==========================================
_AMBITOS_REGLA = {"item", "dimension", "puntaje_total"}
_OPERADORES_REGLA = {">", ">=", "<", "<=", "==", "!="}


class ReglaInterpretacionBase(BaseModel):
    ambito: str
    pregunta_id: Optional[int] = None
    dimension_id: Optional[int] = None
    operador: str
    valor_comparacion: float
    accion: str = "es_alerta"
    descripcion: Optional[str] = Field(default=None, max_length=1000)
    activa: bool = True

    @field_validator("ambito")
    @classmethod
    def _ambito_valido(cls, v: str) -> str:
        if v not in _AMBITOS_REGLA:
            raise ValueError(f"ambito debe ser uno de {sorted(_AMBITOS_REGLA)}")
        return v

    @field_validator("operador")
    @classmethod
    def _operador_valido(cls, v: str) -> str:
        if v not in _OPERADORES_REGLA:
            raise ValueError(f"operador debe ser uno de {sorted(_OPERADORES_REGLA)}")
        return v

    @field_validator("accion")
    @classmethod
    def _accion_valida(cls, v: str) -> str:
        if v != "es_alerta":
            raise ValueError("accion solo soporta 'es_alerta' por ahora")
        return v

    @model_validator(mode="after")
    def _campos_requeridos_segun_ambito(self):
        if self.ambito == "item" and self.pregunta_id is None:
            raise ValueError("una regla de ámbito 'item' requiere pregunta_id")
        if self.ambito == "dimension" and self.dimension_id is None:
            raise ValueError("una regla de ámbito 'dimension' requiere dimension_id")
        return self


class ReglaInterpretacionCreate(ReglaInterpretacionBase):
    """prueba_id viene de la URL (POST /pruebas/{prueba_id}/reglas), nunca del body:
    mismo criterio anti-IDOR que el resto de recursos anidados bajo una prueba."""
    pass


class ReglaInterpretacionUpdate(BaseModel):
    activa: Optional[bool] = None
    descripcion: Optional[str] = Field(default=None, max_length=1000)
    valor_comparacion: Optional[float] = None


class ReglaInterpretacionResponse(ReglaInterpretacionBase):
    id: int
    prueba_id: int

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS COMPUESTOS (DETALLE COMPLETO)
# ==========================================
class PruebaDetalleResponse(PruebaResponse):
    dimensiones: List[DimensionConPreguntas] = []
    baremos: List[BaremoResponse] = []
    reglas: List[ReglaInterpretacionResponse] = []

# ==========================================
# ESQUEMAS PARA DIAGNÓSTICOS FINALES
# ==========================================
class DiagnosticoAlumnoBase(BaseModel):
    inscripcion_id: int
    dimension_id: int
    nivel: str
    tipo_puntaje_usado: Optional[str] = None
    valor_convertido: Optional[str] = None
    interpretacion: Optional[str] = None
    es_alerta: bool = False
    # 🆕 Trazabilidad: "baremo" | "regla" | "baremo,regla" | None.
    alerta_por: Optional[str] = None
    regla_activada_id: Optional[int] = None
    # 🆕 Puntero histórico a la fila de Baremo que produjo este diagnóstico —
    # ver DiagnosticoAlumno.baremo_id en models.py. NULL si el baremo que lo
    # generó ya fue borrado físicamente (nunca si solo fue desactivado).
    baremo_id: Optional[int] = None

class DiagnosticoAlumnoResponse(DiagnosticoAlumnoBase):
    id: int

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA CONTROL DE ACCESO
# ==========================================
class EvaluacionCreate(BaseModel):
    prueba_id: int
    nombre_grupo: str
    institucion_id: int
    fecha_fin: Optional[datetime] = None

    @field_validator("fecha_fin")
    @classmethod
    def fecha_fin_a_utc_naive(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Normaliza la fecha de cierre a UTC sin tzinfo.

        La columna es `DateTime` sin zona horaria y todos los candados de
        expiración comparan contra `datetime.utcnow()` (naive). Si el cliente
        envía un ISO con offset (ej. "2026-12-01T00:00:00-05:00"), guardarlo
        tal cual haría que la campaña cerrara a la hora equivocada, o que la
        comparación lanzara TypeError por mezclar naive y aware.
        """
        if v is not None and v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v

class EvaluacionResponse(BaseModel):
    id: int
    prueba_id: int
    nombre_grupo: str
    activo: bool
    estado: str
    fecha_fin: Optional[datetime] = None
    fecha_creacion: datetime

    class Config:
        from_attributes = True


class EvaluacionUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales, solo se cambia lo enviado.

    Qué campo es editable depende del estado actual de la campaña y de si ya
    tiene inscripciones (ver crud.actualizar_campana): `prueba_id` se bloquea
    en cuanto existe una sola inscripción, aunque todavía no tenga respuestas
    — un link mágico ya emitido asume las preguntas/baremos de la prueba
    original. `nombre_grupo`/`fecha_fin` son cosméticos y siempre editables
    mientras la campaña esté "activa". `institucion_id` nunca es editable
    (no hay precedente de mover un tenant en todo este código).
    """
    nombre_grupo: Optional[str] = None
    fecha_fin: Optional[datetime] = None
    prueba_id: Optional[int] = None

    @field_validator("fecha_fin")
    @classmethod
    def fecha_fin_a_utc_naive(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Mismo criterio que EvaluacionCreate.fecha_fin_a_utc_naive."""
        if v is not None and v.tzinfo is not None:
            return v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class CerrarCampanaRequest(BaseModel):
    """Motivo opcional: cerrar es el fin normal del ciclo de vida, no exige justificación."""
    motivo: Optional[str] = Field(default=None, max_length=1000)


class CancelarCampanaRequest(BaseModel):
    """Motivo obligatorio: cancelar anula una campaña que nunca llegó a
    producir resultados reales, así que siempre queda trazado por qué."""
    motivo: str = Field(min_length=3, max_length=1000)

class RegistroAlumnoDemograficos(BaseModel):
    nombre_completo: str
    edad: int
    sexo: SexoEnum
    poblacion: PoblacionEnum
    acepta_terminos: bool = Field(
        ...,
        description="Casilla explícita de asentimiento informado/aceptación de términos, del propio estudiante"
    )
    # 🆕 Solo obligatorios cuando la Prueba de esta inscripción tiene
    # informante_tipo != 'estudiante' (validado en
    # crud.validar_y_comenzar_evaluacion, no aquí, porque el schema no tiene
    # forma de saber a qué Prueba pertenece esta inscripción). Para el
    # autorreporte de siempre (la inmensa mayoría) se ignoran si vienen, y
    # nunca se piden.
    informante_nombre: Optional[str] = Field(default=None, max_length=200)
    informante_relacion: Optional[str] = Field(default=None, max_length=100)

# 🆕 Lo que ya se sabe de esta inscripción ANTES de que el estudiante escriba
# nada — para que el formulario de "Antes de comenzar" no vuelva a pedir
# datos que el colegio ya cargó al matricularlo por padrón (ver
# crud.obtener_intake_previo_por_token). En un link anónimo todo esto viene
# en None/False, así que el formulario se ve exactamente igual que hoy.
class IntakeExamenResponse(BaseModel):
    nombre_completo: Optional[str] = None
    nombre_conocido: bool  # True si nombre_completo viene de una Persona del padrón, no editable
    edad: Optional[int] = None
    sexo: Optional[str] = None
    poblacion: Optional[str] = None
    informante_tipo: str
    ya_acepto_asentimiento: bool

# ==========================================
# 🆕 TEXTO VERSIONADO DEL ASENTIMIENTO INFORMADO
# ==========================================
class AsentimientoInformadoTextoResponse(BaseModel):
    id: int
    institucion_id: Optional[int] = None
    # 🆕 "apoderado" (consentimiento) | "asentimiento"; nivel_educativo_id
    # None = modelo general del colegio (o global). Ver models.py.
    tipo_texto: str = "asentimiento"
    nivel_educativo_id: Optional[int] = None
    version: int
    contenido: str
    activo: bool
    creado_en: datetime

    class Config:
        from_attributes = True


class AsentimientoInformadoTextoCreate(BaseModel):
    # None = versión GLOBAL (solo superadmin, ver router) -- un entero
    # exige que coincida con la propia institución del caller salvo que sea
    # superadmin, mismo criterio que crear_nivel_educativo.
    institucion_id: Optional[int] = None
    contenido: str = Field(min_length=10)
    # 🆕 Por defecto "asentimiento" — un cliente anterior a este cambio
    # sigue creando exactamente lo mismo que antes.
    tipo_texto: Literal["apoderado", "asentimiento"] = "asentimiento"
    nivel_educativo_id: Optional[int] = None


# 🆕 GET /educativo/modelos-consentimiento/vigente — el texto que le
# corresponde a UN alumno (por su nivel actual), para mostrarlo al registrar
# su consentimiento/asentimiento en la ficha. `origen` dice de dónde salió:
# "nivel" | "colegio" | "global".
class TextoConsentimientoVigente(BaseModel):
    id: int
    tipo_texto: str
    version: int
    contenido: str
    nivel_educativo_id: Optional[int] = None
    origen: str


# Lo mínimo que el flujo público del examen necesita para mostrar el texto
# activo -- nunca el historial completo ni quién lo creó.
class AsentimientoInformadoTextoPublico(BaseModel):
    version: int
    contenido: str

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA RENDERIZAR EL EXAMEN EN VIVO
# ==========================================
class OpcionRespuestaExamen(BaseModel):
    id: int
    texto_opcion: str

    class Config:
        from_attributes = True

class PreguntaExamen(BaseModel):
    id: int
    texto_pregunta: str
    # 🆕 'opcion_multiple' (de siempre) o 'numerico' (ver Pregunta.tipo_
    # respuesta en models.py) — el frontend decide qué widget renderizar.
    tipo_respuesta: str = "opcion_multiple"
    # 🆕 Solo para 'numerico': cuántos campos numéricos debe llenar el
    # alumno (ej. 2 para una serie con dos espacios en blanco). NUNCA la
    # clave de corrección — eso vive solo en el servidor.
    cantidad_valores_numericos: Optional[int] = None
    opciones: List[OpcionRespuestaExamen] = []

    class Config:
        from_attributes = True

# ==========================================
# ESQUEMAS PARA GUARDAR RESPUESTAS DEL ALUMNO
# ==========================================
class RespuestaAlumnoSubmit(BaseModel):
    pregunta_id: int
    # 🆕 Ambos quedan opcionales: un ítem 'opcion_multiple' manda opcion_id,
    # uno 'numerico' manda respuesta_numerica — exactamente uno de los dos
    # según Pregunta.tipo_respuesta. crud.guardar_respuestas_examen es quien
    # decide cuál corresponde a cada pregunta_id (nunca confía en que el
    # cliente haya mandado el campo correcto) y rechaza el lote completo si
    # no coincide con lo que la BD dice que esa pregunta espera.
    opcion_id: Optional[int] = None
    respuesta_numerica: Optional[List[int]] = Field(default=None, max_length=10)

class ExamenSubmit(BaseModel):
    respuestas: List[RespuestaAlumnoSubmit]


class ProgresoExamenResponse(BaseModel):
    """🔁 C-5 — Lo que el alumno ya contestó, para poder reanudar.
    Solo pares (pregunta, opción): nunca puntajes."""
    estado: str
    respuestas: List[RespuestaAlumnoSubmit] = []


class LiberarInformeRequest(BaseModel):
    """Comentario opcional que el profesional incorpora al informe al liberarlo."""
    interpretacion_clinica: Optional[str] = Field(default=None, max_length=5000)


class RevisionInformeRequest(BaseModel):
    """Configuración clínica de lo que el alumno podrá consultar.

    🆕 Los cuatro campos de contenido profesional (motivo_consulta,
    observacion_conductual, conclusion_override, recomendaciones_override)
    quedan guardados en la Inscripcion pero NO se reflejan automáticamente en
    ningún PDF ya generado — como el resto del sistema de informes, un
    cambio de contenido exige una reemisión explícita
    (POST /inscripciones/{id}/informe/reemitir) para congelarse en una nueva
    InformeVersion. Guardar aquí sin reemitir después no altera el PDF v1 ya
    almacenado.
    """
    interpretacion_clinica: Optional[str] = Field(default=None, max_length=5000)
    resultado_visible_alumno: Optional[bool] = None
    informe_liberado: Optional[bool] = None
    motivo_consulta: Optional[str] = Field(default=None, max_length=2000)
    observacion_conductual: Optional[str] = Field(default=None, max_length=3000)
    # 🆕 Override de técnicas adicionales (sección 3) para esta aplicación
    # puntual — reemplaza Prueba.tecnicas_adicionales, nunca el nombre del
    # instrumento (ver Inscripcion.tecnicas_override en models.py).
    tecnicas_override: Optional[str] = Field(default=None, max_length=1000)
    conclusion_override: Optional[str] = Field(default=None, max_length=3000)
    recomendaciones_override: Optional[str] = Field(default=None, max_length=3000)
    firma_cargo_override: Optional[str] = Field(default=None, max_length=300)
    # 🆕 Completan el bloque de firma — ver Inscripcion.firma_nombre_override/
    # firma_dni_override en models.py. Vacíos = comportamiento de siempre
    # (nombre derivado automáticamente, DNI en blanco).
    firma_nombre_override: Optional[str] = Field(default=None, max_length=300)
    firma_dni_override: Optional[str] = Field(default=None, max_length=20)


class ReemitirInformeRequest(BaseModel):
    """Motivo obligatorio: una reemisión queda trazada (VERSIONADO DEL INFORME)."""
    motivo: str = Field(min_length=3, max_length=1000)


class ReprocesarInformeRequest(BaseModel):
    """Motivo obligatorio, mismo criterio que ReemitirInformeRequest.

    A diferencia de una reemisión simple (que solo vuelve a renderizar el PDF
    con lo que YA está en DiagnosticoAlumno), reprocesar RECALCULA desde las
    respuestas crudas del alumno contra los baremos/reglas vigentes — pensado
    para el caso "corregí un baremo mal configurado y necesito que esta
    inscripción ya finalizada refleje la interpretación correcta".
    """
    motivo: str = Field(min_length=3, max_length=1000)


class EstadoResultadosAlumnoResponse(BaseModel):
    estado_examen: str
    resultado_visible_alumno: bool
    informe_liberado: bool
    # "completa" | "incompleta" — distingue un resultado interpretado de uno
    # que quedó pendiente por falta de baremo aplicable (B-6).
    estado_interpretacion: str = "completa"
    mensaje: str

# ==========================================
# ESQUEMAS PARA CARGA MASIVA DE TESTS
# ==========================================
class OpcionCargaMasiva(BaseModel):
    texto_opcion: str
    valor_puntuacion: float

class PreguntaCargaMasiva(BaseModel):
    texto_pregunta: str
    orden: int
    nombre_dimension: Optional[str] = None
    es_inverso: bool = False
    incluir_en_informe: bool = False
    etiqueta_informe: Optional[str] = None
    opciones: List[OpcionCargaMasiva]

class CargaMasivaTest(BaseModel):
    prueba_id: int
    dimensiones: List[DimensionBase]
    preguntas: List[PreguntaCargaMasiva]

# ==========================================
# ESQUEMAS PARA EL DASHBOARD POR SALÓN
# ==========================================
class ResultadoAlumnoDashboard(BaseModel):
    dimension: str
    puntaje_directo: float
    nivel: Optional[str] = None
    # 🆕 Rango del tramo de Baremo que produjo este nivel (snapshot ya
    # existente en DiagnosticoAlumno.rango_minimo/rango_maximo — ver
    # docs/informes-psicometricos.md) y si ese tramo es de alerta. None
    # cuando no hay DiagnosticoAlumno (dimensión sin baremo aplicable) o en
    # modo_interpretacion='perfil' (no usa Baremo, ver docs/motor-scoring.md
    # "Interpretación por perfil") — la UI debe caer a mostrar solo
    # dimension/puntaje_directo/nivel como texto cuando falten.
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    es_alerta: Optional[bool] = None

class AlumnoDashboard(BaseModel):
    inscripcion_id: int
    nombre_completo: Optional[str] = None
    estado: str
    fecha_resolucion: Optional[datetime] = None
    resultados: List[ResultadoAlumnoDashboard] = []
    # 🆕 Solo viene relleno en el dashboard académico de ÁMBITO "grado" (ver
    # DashboardAcademicoResponse) — varias secciones combinadas necesitan
    # distinguirse fila por fila; el de campaña y el de un solo salón nunca
    # lo necesitan (todos los alumnos ya comparten salón por construcción).
    seccion: Optional[str] = None


# 🆕 Resumen estadístico por dimensión — ver crud.calcular_resumen_
# estadistico_dashboard (una sola implementación, compartida por el JSON de
# ambos dashboards y por la hoja "Resumen estadístico" de generar_excel_
# dashboard). Señales ESTRUCTURALES de la prueba, nunca por nombre/clave
# (ver docs/motor-scoring.md), para que el consumidor elija la presentación
# correcta sin conocer cada instrumento: modo_interpretacion decide niveles+
# alertas ("rango") vs. ranking comparativo ("perfil", hoy solo
# IPIP-RIASEC); agrupar_dimensiones_por_area agrupa por área (CHASIDE);
# tiene_alertas_posibles oculta la tarjeta/columna de alertas por completo
# en una prueba no clínica, en vez de mostrar "0 alertas" engañoso.
#
# 🔒 Se calcula SIEMPRE antes de la redacción para 'colegio' — ver docstring
# de calcular_resumen_estadistico_dashboard: es un agregado de grupo, nunca
# el diagnóstico puntual de un alumno, así que sobrevive esa redacción igual
# que `distribucion_por_dimension` ya lo hacía.
class NivelDistribucionDashboard(BaseModel):
    nivel: str
    cantidad: int
    pct: float
    es_alerta: bool

class DimensionResumenEstadistico(BaseModel):
    nombre: str
    tipo_calculo: str  # "items" | "suma_de_dimensiones" | "conteo_sintomas"
    n: int
    media: Optional[float] = None
    mediana: Optional[float] = None
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    # El máximo del tramo de Baremo más alto alcanzado entre los alumnos del
    # grupo — None en modo 'perfil' (nunca hay Baremo, ver docs/motor-scoring.md).
    maximo_escala: Optional[float] = None
    # Ordenada de mayor a menor cantidad — distribucion[0], si existe, es la
    # mayoría. Vacía en modo 'perfil' (nunca hay niveles categóricos).
    distribucion: List[NivelDistribucionDashboard] = []
    en_alerta: Optional[int] = None  # None cuando tiene_alertas_posibles=False
    # Solo en modo 'perfil': cuántos alumnos tienen a ESTA dimensión como la
    # de mayor puntaje de su propio ranking (ver interpretar_perfil_alumno).
    dominante_cantidad: Optional[int] = None

class AreaCompatibleDashboard(BaseModel):
    area: str
    cantidad: int

class ResumenEstadisticoDashboard(BaseModel):
    modo_interpretacion: str  # "rango" | "perfil"
    agrupar_dimensiones_por_area: bool
    tiene_alertas_posibles: bool
    dimensiones: List[DimensionResumenEstadistico] = []
    # Solo relleno cuando agrupar_dimensiones_por_area=True (CHASIDE) — la
    # versión por-grupo de "áreas vocacionales compatibles" que el informe
    # PDF ya calcula por alumno (ver crud._agrupar_dimensiones_por_area).
    areas_compatibles: List[AreaCompatibleDashboard] = []

class DashboardCampanaResponse(BaseModel):
    evaluacion_id: int
    nombre_grupo: str
    nombre_prueba: str
    # 🆕 Título corto para la UI (ver Prueba.nombre_corto en models.py) — ya
    # resuelto con el respaldo a nombre_tecnico, nunca None si la prueba
    # existe. nombre_prueba (el nombre completo) sigue existiendo para la
    # descripción expandida.
    nombre_corto_prueba: Optional[str] = None
    total_inscritos: int
    total_finalizados: int
    total_pendientes: int
    distribucion_por_dimension: Dict[str, Dict[str, int]]
    alumnos: List[AlumnoDashboard]
    resumen_estadistico: ResumenEstadisticoDashboard
    # 🆕 Campos de la propia Evaluacion que la UI necesita para ofrecer
    # "Editar campaña" (PATCH /campanas/{id}) sin un segundo endpoint — el
    # dashboard ya consulta la Evaluacion, así que exponerlos aquí no cuesta
    # una query nueva. `prueba_id` deja que el frontend sepa si mostrar el
    # selector de prueba como editable (se bloquea en cuanto existe una sola
    # inscripción — ver EvaluacionUpdate/crud.actualizar_campana).
    estado: str  # "activa" | "cerrada" | "cancelada"
    fecha_fin: Optional[datetime] = None
    prueba_id: int

# 🆕 Dashboard académico — mismo tipo de resumen que DashboardCampanaResponse
# pero por salón/grado (cruzando todas las campañas en que se aplicó la
# prueba) en vez de por campaña puntual. Ver crud.obtener_dashboard_academico.
class AmbitoDashboardAcademico(BaseModel):
    tipo: str  # "seccion" | "grado"
    id: int
    nombre: str

class DashboardAcademicoResponse(BaseModel):
    prueba_id: int
    nombre_prueba: str
    # 🆕 Ver DashboardCampanaResponse.nombre_corto_prueba arriba.
    nombre_corto_prueba: Optional[str] = None
    ambito: AmbitoDashboardAcademico
    total_inscritos: int
    total_finalizados: int
    total_pendientes: int
    distribucion_por_dimension: Dict[str, Dict[str, int]]
    alumnos: List[AlumnoDashboard]
    # 🆕 Ver DashboardCampanaResponse.resumen_estadistico arriba.
    resumen_estadistico: ResumenEstadisticoDashboard


# 🆕 Tendencia de un salón en el tiempo — ver crud.obtener_tendencia_seccion.
class PuntoTendenciaSeccion(BaseModel):
    evaluacion_id: int
    nombre_grupo: str
    fecha: datetime
    total_finalizados: int
    resumen_estadistico: ResumenEstadisticoDashboard


class TendenciaSeccionResponse(BaseModel):
    prueba_id: int
    nombre_prueba: str
    nombre_corto_prueba: Optional[str] = None
    ambito: AmbitoDashboardAcademico
    puntos: List[PuntoTendenciaSeccion]

class MatriculaRosterResponse(BaseModel):
    generados: List[InscripcionResponse]
    rechazados: List[Dict[str, Any]]
    # `matricular_roster_en_campana` ya devolvía este motivo cuando rechaza la
    # operación entera (campaña caducada o inexistente), pero al no estar
    # declarado aquí el response_model lo descartaba y el psicólogo recibía
    # una respuesta vacía sin explicación.
    error: Optional[str] = None

class SesionSeguimientoCreate(BaseModel):
    persona_id: int
    observaciones: Optional[str] = None
    accion_tomada: Optional[str] = None

class SesionSeguimientoResponse(SesionSeguimientoCreate):
    id: int
    psicologo_id: int
    institucion_id: int
    fecha: datetime
    # 🆕 Faltaban en la respuesta aunque ya existían en el modelo y en
    # SesionSeguimientoUpdate -- sin esto, el frontend no tenía forma de
    # precargar un formulario de edición (ni de mostrar el estado/acuerdos
    # reales en el historial, que ya los renderizaba asumiendo que
    # llegarían). Ver docs/frontend.md.
    acuerdos_compromisos: Optional[str] = None
    proxima_cita: Optional[datetime] = None
    # Optional porque la columna es nullable en la BD (sin server_default) —
    # en la práctica el modelo siempre pone "Atendido" al crear, pero el
    # schema no debe asumir lo que la base de datos no garantiza.
    estado: Optional[str] = None

    class Config:
        from_attributes = True

class SesionSeguimientoUpdate(BaseModel):
    """Todos los campos opcionales — solo mandas lo que corriges."""
    observaciones: Optional[str] = None
    accion_tomada: Optional[str] = None
    acuerdos_compromisos: Optional[str] = None
    proxima_cita: Optional[datetime] = None
    estado: Optional[str] = None  # 'Pendiente', 'En proceso', 'Atendido'

class PruebaUpdate(BaseModel):
    nombre_publico: Optional[str] = None
    instrucciones: Optional[str] = None
    activa: Optional[bool] = None
    dias_minimos_entre_aplicaciones: Optional[int] = None
    # 🆕 Ver Prueba.criterio_normativo_activo en models.py — un PATCH normal,
    # no un endpoint nuevo. Cambiarlo y luego reprocesar las inscripciones
    # afectadas es el mecanismo para adoptar otro criterio ya cargado.
    criterio_normativo_activo: Optional[str] = None
    # 🆕 Ver Prueba.ordenar_dimensiones_por_puntaje en models.py.
    ordenar_dimensiones_por_puntaje: Optional[bool] = None
    # 🆕 Ver Prueba.agrupar_dimensiones_por_area en models.py.
    agrupar_dimensiones_por_area: Optional[bool] = None

class RespuestaSociodemograficaSubmit(BaseModel):
    campo_id: int
    valor: str

class CamposSocioSubmit(BaseModel):
    respuestas: List[RespuestaSociodemograficaSubmit]

class PreguntaUpdate(BaseModel):
    texto_pregunta: Optional[str] = None
    orden: Optional[int] = None
    dimension_id: Optional[int] = None
    es_inverso: Optional[bool] = None
    incluir_en_informe: Optional[bool] = None
    etiqueta_informe: Optional[str] = None
    # 🆕 Ver Pregunta.escala_minima/escala_maxima en models.py.
    escala_minima: Optional[int] = None
    escala_maxima: Optional[int] = None

class DimensionUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    # 🆕 Ver Dimension.tipo_calculo en models.py. crud.actualizar_dimension
    # bloquea el cambio si la dimensión ya tiene resultados calculados, o si
    # se intenta convertir a 'suma_de_dimensiones' una dimensión que todavía
    # tiene preguntas propias, o si el resultado final deja 'conteo_sintomas'
    # sin conteo_umbral_item.
    tipo_calculo: Optional[str] = None
    conteo_umbral_item: Optional[int] = None

    @field_validator("tipo_calculo")
    @classmethod
    def _tipo_calculo_valido(cls, v):
        if v is not None and v not in _TIPOS_CALCULO_DIMENSION_VALIDOS:
            raise ValueError(f"tipo_calculo debe ser uno de {sorted(_TIPOS_CALCULO_DIMENSION_VALIDOS)}")
        return v

class OpcionRespuestaUpdate(BaseModel):
    texto_opcion: Optional[str] = None
    valor_puntuacion: Optional[float] = None

class BaremoUpdate(BaseModel):
    edad_min: Optional[int] = None
    edad_max: Optional[int] = None
    sexo: Optional[str] = None
    poblacion: Optional[str] = None
    puntaje_minimo: Optional[float] = None
    puntaje_maximo: Optional[float] = None
    tipo_puntaje: Optional[str] = None
    valor_convertido: Optional[str] = None
    nivel: Optional[str] = None
    interpretacion: Optional[str] = None
    es_alerta: Optional[bool] = None
    # 🆕 Ver Baremo.criterio_normativo en models.py.
    criterio_normativo: Optional[str] = None
    # 🆕 Única forma de "retirar" un baremo que ya tiene diagnósticos
    # asociados (crud.actualizar_baremo bloquea el resto de campos en ese
    # caso, pero SIEMPRE permite desactivar). Ver Baremo.activo en models.py.
    activo: Optional[bool] = None

