from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.sql import func, text
from sqlalchemy.orm import relationship
from core.database import Base


# Tabla Central de Personas (Pacientes, Estudiantes, Candidatos, Empleados)
# NOTA: Cliente y Usuario fueron eliminados de este módulo — eran
# duplicados de Institucion (modulos.instituciones) y Usuario (modulos.auth).
class Persona(Base):
    __tablename__ = "personas"

    # 🔒 C-7 — La unicidad del documento es POR INSTITUCIÓN, no global.
    # Antes `documento_identidad` era unique a secas: dos colegios distintos
    # no podían registrar al mismo DNI (un alumno que se traslada, o un
    # hermano homónimo mal tecleado), y el 409 delataba que ese documento ya
    # existía en OTRO cliente, filtrando información entre inquilinos.
    # Los NULL siguen permitidos y no colisionan (PostgreSQL los trata como
    # distintos), así que una persona sin documento no bloquea a nadie.
    __table_args__ = (
        UniqueConstraint(
            "institucion_id", "documento_identidad",
            name="uq_personas_institucion_documento",
        ),
        # 🆕 Núcleo del estudiante — mismo criterio que el documento: único
        # POR INSTITUCIÓN, no global (dos colegios pueden numerar su propio
        # padrón "E-0001" sin chocar), y los NULL no colisionan entre sí.
        UniqueConstraint(
            "institucion_id", "codigo_institucional",
            name="uq_personas_institucion_codigo",
        ),
        # 🆕 Promoción anual — "retirado" y "trasladado" se mantienen como
        # valores separados (no un estado genérico) porque la institución
        # necesita poder reportarlos por separado; "egresado" es su propio
        # valor porque un egresado no debe desaparecer del todo, solo salir
        # del listado activo por defecto (queda visible en un filtro/pestaña
        # separada). NULL = condición normal, sin novedad académica.
        CheckConstraint(
            "condicion_matricula IN ('retirado', 'trasladado', 'egresado')",
            name="ck_personas_condicion_matricula_valida",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # 🔒 Ahora apunta a la tabla real de colegios
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    tipo_perfil = Column(String, nullable=False, default="estudiante")

    # Datos personales
    nombres = Column(String, nullable=False)
    apellidos = Column(String, nullable=False)
    # index sí (se busca por documento), unique NO: lo garantiza el
    # UniqueConstraint compuesto de __table_args__.
    documento_identidad = Column(String, index=True, nullable=True)

    # 🆕 Núcleo del estudiante — identificador FUNCIONAL del padrón del
    # colegio (código de matrícula, código SIAGIE, legajo interno...). Es lo
    # que se usa para importación Excel, búsqueda y asociación masiva de
    # evaluaciones — nunca el DNI, que puede faltar, repetirse entre
    # hermanos mal tecleado, o ser un dato que el colegio no maneja para
    # menores. `Persona.id` sigue siendo la clave real para toda relación
    # interna (FK); esto es solo la llave de negocio de cara al colegio.
    codigo_institucional = Column(String, index=True, nullable=True)

    email = Column(String, nullable=True)
    fecha_nacimiento = Column(DateTime(timezone=True), nullable=True)
    genero = Column(String, nullable=True)

    # Campos dinámicos según el rubro
    #
    # 🆕 Núcleo del estudiante — `grado_seccion` era texto libre repetido en
    # cada Persona, sin relación con una estructura real: no permitía
    # consultar "Institución → Grado → Sección → Estudiantes" ni saber dónde
    # estuvo el alumno el año pasado. Se conserva el campo (compatibilidad:
    # ninguna fila existente pierde su valor) pero deja de ser la fuente de
    # verdad para estudiantes — ahora lo es `MatriculaAcademica`, más abajo.
    # Sigue siendo útil tal cual para poblaciones sin estructura de
    # grado/sección (`tipo_perfil` distinto de "estudiante").
    grado_seccion = Column(String, nullable=True)
    puesto_postula = Column(String, nullable=True)
    area_empresa = Column(String, nullable=True)

    activo = Column(Boolean, default=True)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())

    # 🆕 Promoción anual — distinto de `activo` (genérico) y de la
    # anonimización ARCO (que vive en Inscripcion, no aquí): esto es
    # específicamente la condición académica de un estudiante tras un cierre
    # de año. NULL = sin novedad. Nunca se borra ni se sobreescribe la
    # matrícula histórica por esto — ver `MatriculaAcademica.motivo_cierre`.
    condicion_matricula = Column(String, nullable=True)

class ConsentimientoInformado(Base):
    """
    Registro de quién autorizó la evaluación de un estudiante.
    Es un historial (no se borra), así que si se revoca queda constancia.

    🆕 Consentimientos del estudiante/apoderado — esta MISMA tabla sirve para
    los DOS consentimientos independientes que pide la fase (apoderado y
    estudiante), discriminados por `tipo_consentimiento`. No se separó en dos
    tablas: casi todos los campos (persona, institución, vigencia,
    revocación, auditoría, historial) son idénticos para ambos, así que
    duplicar la tabla habría duplicado también toda esa lógica. Lo que sí
    difiere (nombre/documento/relación del otorgante) queda en columnas
    NULLABLE que solo se rellenan para tipo_consentimiento="apoderado" — un
    consentimiento del propio estudiante no tiene "otorgante", es él mismo.

    Un consentimiento del apoderado NUNCA crea uno del estudiante, ni al
    revés: son dos historiales independientes que solo comparten persona_id.
    """
    __tablename__ = "consentimientos_informados"
    __table_args__ = (
        # 🔒 Como máximo UN consentimiento VIGENTE por persona+institución
        # POR TIPO — no uno combinado. El apoderado puede tener un
        # consentimiento vigente mientras el del estudiante todavía no existe,
        # o viceversa, sin que se pisen entre sí. Mismo patrón que
        # `uq_matricula_activa_por_persona` del Núcleo del Estudiante: un
        # índice único PARCIAL, que la base de datos garantiza sola.
        Index(
            "uq_consentimiento_vigente_por_persona_y_tipo",
            "persona_id", "institucion_id", "tipo_consentimiento",
            unique=True,
            postgresql_where=text("estado = 'vigente'"),
        ),
        CheckConstraint(
            "tipo_consentimiento IN ('apoderado', 'asentimiento')",
            name="ck_consentimientos_tipo_valido",
        ),
        CheckConstraint(
            "estado IN ('vigente', 'revocado')",
            name="ck_consentimientos_estado_valido",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False)

    # 🆕 "apoderado" | "asentimiento" — controlado por constantes, no texto
    # libre (ver TIPO_CONSENTIMIENTO_* más abajo). Cuando esto se escribió,
    # el CHECK a nivel de BD era deliberadamente más estricto que en otras
    # columnas de estado de este proyecto (Inscripcion.estado, Usuario.rol,
    # CitaProgramada.estado...): esas eran legado con filas detrás, y
    # ponerles un CHECK habría exigido primero confirmar que no hubiera
    # ningún valor fuera de lo esperado. Esa confirmación se hizo después
    # (docs/gaps-pendientes.md) — las tablas estaban limpias, así que esas
    # columnas también tienen su CHECK hoy. Esta seguía siendo, de todos
    # modos, una columna NUEVA sin ese costo desde el día uno.
    tipo_consentimiento = Column(
        String, nullable=False, server_default="apoderado", default="apoderado", index=True,
    )
    # 🆕 "vigente" | "revocado" — reemplaza en la práctica a `revocado`
    # (booleano, ver abajo) como fuente de verdad para el código NUEVO y para
    # el índice único parcial de arriba, pero `revocado` se conserva
    # sincronizado en cada escritura: lo siguen leyendo `crud.py` (Fase 2,
    # B-8) y las pruebas de regresión de esa fase, y una inserción SQL cruda
    # que no mencione estas columnas nuevas debe seguir funcionando (por eso
    # ambas tienen server_default).
    estado = Column(String, nullable=False, server_default="vigente", default="vigente", index=True)

    # 📎 Solo aplica a tipo_consentimiento="apoderado" — NULL para
    # "asentimiento" (el propio estudiante no tiene un "otorgante" distinto de
    # sí mismo). La validación de qué es obligatorio para cada tipo vive en
    # los esquemas (ConsentimientoCreate / ConsentimientoAsentimientoCreate),
    # no aquí: la columna sigue siendo NULLABLE en la base para poder alojar
    # ambos tipos en la misma tabla.
    otorgado_por_nombre = Column(String, nullable=True)  # nombre(s) del padre/apoderado o responsable
    otorgante_apellidos = Column(String, nullable=True)
    otorgante_documento = Column(String, nullable=True)   # documento del responsable, cuando corresponda
    otorgante_relacion = Column(String, nullable=True)    # "madre", "padre", "tutor legal"...
    tipo_otorgante = Column(String, nullable=True)  # "apoderado" | "colegio_delegado"
    referencia_documento = Column(String, nullable=True)  # ej: "Ficha de matrícula 2026, folio 45"

    # 🆕 Evidencia (docs/gaps-pendientes.md, cierre del gap "evidencia_ruta
    # sin usar") — ya NO es un placeholder: `POST
    # /admin/personas/consentimiento/{id}/evidencia` sube el documento
    # firmado/escaneado real a través de core/storage/ y deja aquí la
    # KEY de storage (nunca el binario, mismo criterio que InformeVersion).
    # `referencia_documento` (arriba) sigue siendo la nota humana ("folio
    # 45"), escrita a mano al registrar el consentimiento; esto es la
    # referencia que lee una máquina, y solo existe después de una subida
    # real. Se sigue aceptando como texto libre en
    # ConsentimientoCreate/ConsentimientoAsentimientoCreate por compatibilidad
    # con quien ya la usaba como nota manual — subir un archivo de verdad
    # SOBRESCRIBE lo que hubiera aquí con la key real.
    evidencia_ruta = Column(String, nullable=True)
    evidencia_nombre_archivo = Column(String, nullable=True)
    evidencia_content_type = Column(String, nullable=True)
    evidencia_tamano_bytes = Column(Integer, nullable=True)
    evidencia_subido_en = Column(DateTime(timezone=True), nullable=True)
    evidencia_subido_por_usuario_id = Column(
        Integer,
        ForeignKey("auth_usuarios.id", name="fk_consentimientos_evidencia_subido_por_usuario"),
        nullable=True,
    )

    registrado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    fecha_otorgamiento = Column(DateTime(timezone=True), server_default=func.now())
    # 🔁 Se mantiene por compatibilidad con la Fase 2 (B-8/B-11): crud.py y
    # las pruebas de regresión ya leen y escriben esta columna. Todo el
    # código NUEVO de esta fase escribe también `estado`, en el mismo commit,
    # así que las dos nunca quedan desincronizadas.
    revocado = Column(Boolean, default=False)
    fecha_revocacion = Column(DateTime(timezone=True), nullable=True)

    # 🏛️ B-11 — Trazabilidad completa del evento (Ley 29733).
    # Desde qué IP se registró el consentimiento, y quién lo revocó y desde
    # dónde. Antes solo constaba la fecha de revocación, sin responsable.
    ip_registro = Column(String, nullable=True)
    revocado_por_usuario_id = Column(
        Integer,
        # Nombre explícito = el que crea la migración f7a2c5e91d40, para que
        # create_all y la cadena de migraciones produzcan el mismo esquema.
        ForeignKey("auth_usuarios.id", name="fk_consentimientos_revocado_por_usuario"),
        nullable=True,
    )
    ip_revocacion = Column(String, nullable=True)


# 🆕 Constantes de tipo/estado — mismo criterio que TIPO_PUNTAJE/
# INTERPRETACION_COMPLETA en modulos/educativo/models.py: nada de texto
# libre disperso por crud.py/router.py, un único lugar que nombra los
# valores válidos.
TIPO_CONSENTIMIENTO_APODERADO = "apoderado"
# 🆕 Renombrado de "estudiante" a "asentimiento" (docs/gaps-pendientes.md) —
# el valor ahora nombra la FIGURA LEGAL correcta (el asentimiento del propio
# menor, distinto del consentimiento informado que da su apoderado), no a
# quién lo otorga (que sigue siendo, por supuesto, el propio estudiante).
# Ver la migración que recreó el CHECK constraint y hizo el backfill de las
# filas ya existentes: 2026_10_08_*_asentimiento_estudiante_rename.py.
TIPO_CONSENTIMIENTO_ASENTIMIENTO = "asentimiento"
TIPOS_CONSENTIMIENTO_VALIDOS = (TIPO_CONSENTIMIENTO_APODERADO, TIPO_CONSENTIMIENTO_ASENTIMIENTO)

ESTADO_CONSENTIMIENTO_VIGENTE = "vigente"
ESTADO_CONSENTIMIENTO_REVOCADO = "revocado"
ESTADOS_CONSENTIMIENTO_VALIDOS = (ESTADO_CONSENTIMIENTO_VIGENTE, ESTADO_CONSENTIMIENTO_REVOCADO)

class RegistroAuditoriaArco(Base):
    """🏛️ Bitácora de las acciones ARCO (Ley 29733).

    La anonimización es IRREVERSIBLE y el borrado lógico oculta datos
    clínicos: ambas necesitan constar por escrito. Esta tabla es de solo
    añadir —nunca se actualiza ni se borra— y sobrevive al dato que describe.

    `persona_id` e `inscripcion_id` se guardan como enteros sueltos, SIN clave
    foránea, a propósito: la anonimización rompe el vínculo con la persona
    (`Inscripcion.persona_id` pasa a NULL) y el registro de auditoría debe
    seguir diciendo sobre quién se actuó aunque ese enlace ya no exista.
    """
    __tablename__ = "auditoria_arco"

    id = Column(Integer, primary_key=True, index=True)

    # "anonimizacion_persona" | "anonimizacion_inscripcion" | "soft_delete_inscripcion"
    accion = Column(String, nullable=False, index=True)

    persona_id = Column(Integer, nullable=True, index=True)
    inscripcion_id = Column(Integer, nullable=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)

    ejecutado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    rol_ejecutor = Column(String, nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    ip_solicitante = Column(String, nullable=True)

    # Texto libre: referencia de la solicitud del titular, motivo, etc.
    detalle = Column(Text, nullable=True)


# 🆕 PASO 3 (auditoría de arquitectura genérica) — a diferencia de
# `RegistroAuditoriaArco` (bitácora legal de ARCO, Ley 29733), esta tabla es
# un log operativo de ediciones de datos básicos del estudiante: una fila por
# CAMPO realmente cambiado (nunca una por request), con su valor anterior y
# nuevo, para poder auditar "quién cambió qué y cuándo" campo por campo, sin
# mezclar esa consulta con la evidencia de cumplimiento legal de ARCO.
# `campo` es texto libre (no CHECK/enum) a propósito: extenderla a más campos
# el día de mañana no debe pedir otra migración, solo escribir más filas.
class RegistroCambiosPersona(Base):
    """Bitácora de ediciones a los datos básicos de un estudiante (PASO 3):
    nombres, apellidos, fecha_nacimiento, documento_identidad. Solo se añade,
    nunca se edita ni se borra — es un historial, no un estado."""
    __tablename__ = "registro_cambios_persona"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    campo = Column(String, nullable=False)
    valor_anterior = Column(Text, nullable=True)
    valor_nuevo = Column(Text, nullable=True)

    modificado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    rol_modificador = Column(String, nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class CitaProgramada(Base):
    """Entrevistas/sesiones individuales Y actividades grupales (talleres,
    charlas...) agendadas a futuro, para armar la agenda del psicólogo —
    misma tabla para ambos casos, distinguidos por `persona_id`.

    🆕 Actividades grupales (hallazgo de producto: "agregar en la agenda un
    apartado para crear actividades que no son individuales, como
    talleres") — `persona_id` pasa a ser NULLABLE: NULL significa "esto no
    es sobre un alumno puntual", análogo a `Inscripcion.persona_id`
    (modulos/educativo/models.py) para los cupos anónimos de una campaña.
    Una cita individual sigue exactamente igual que antes (persona_id
    siempre presente); una actividad grupal usa `titulo`/`tipo_actividad`/
    `lugar` en su lugar y, opcionalmente, una lista de participantes
    concretos vía `CitaParticipante` — nunca ambas cosas (ni personal_id Y
    participantes para el mismo registro: una cita individual no usa
    `CitaParticipante`)."""
    __tablename__ = "citas_programadas"
    __table_args__ = (
        # 🆕 Cierre de gap (docs/gaps-pendientes.md) — mismos tres valores
        # que ya documentaba el comentario de la columna `estado` y el de
        # `CitaUpdate.estado` en schemas.py, ahora garantizados por la base
        # de datos. `PATCH /citas/{id}` acepta `estado` como texto libre
        # desde el cliente (ver editar_cita en router.py) — este CHECK es la
        # única validación real de qué valores puede escribir.
        CheckConstraint(
            "estado IN ('Programada', 'Realizada', 'Cancelada')",
            name="ck_citas_programadas_estado_valido",
        ),
        # 🆕 Toda fila necesita CÓMO mostrarse: una cita individual se
        # identifica por su alumno (persona_id); una actividad grupal, por
        # su título (nunca ambas cosas a la vez según el criterio de arriba,
        # pero esa combinación no está prohibida a nivel de base de datos —
        # solo que al menos una de las dos debe estar presente).
        CheckConstraint(
            "persona_id IS NOT NULL OR titulo IS NOT NULL",
            name="ck_citas_programadas_persona_o_titulo",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)
    psicologo_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False)
    motivo = Column(String, nullable=False)
    fecha_hora = Column(DateTime(timezone=True), nullable=False)
    estado = Column(String, default="Programada")  # "Programada", "Realizada", "Cancelada"
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())

    # --- Solo actividades grupales (persona_id NULL) ---
    titulo = Column(String, nullable=True)
    tipo_actividad = Column(String, nullable=True)  # texto libre: "Taller", "Charla", "Otro"...
    lugar = Column(String, nullable=True)

    participantes = relationship(
        "CitaParticipante", back_populates="cita", cascade="all, delete-orphan",
    )


class CitaParticipante(Base):
    """Lista OPCIONAL de estudiantes asistentes a una actividad grupal — no
    es un roster cerrado como `Inscripcion` (nadie "se matricula", el
    psicólogo simplemente anota quién participó si quiere), así que no
    tiene estado propio ni link mágico: solo identifica qué personas están
    asociadas a qué actividad."""
    __tablename__ = "citas_participantes"
    __table_args__ = (
        UniqueConstraint("cita_id", "persona_id", name="uq_citas_participantes_cita_persona"),
    )
    id = Column(Integer, primary_key=True, index=True)
    cita_id = Column(Integer, ForeignKey("citas_programadas.id"), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)

    cita = relationship("CitaProgramada", back_populates="participantes")
    persona = relationship("Persona")

    @property
    def nombre_completo(self) -> str:
        """Resuelto en vivo desde Persona (a diferencia de
        `Inscripcion.nombre_completo`, que es un snapshot propio): esta
        lista no necesita sobrevivir a una anonimización ARCO de la
        persona, así que no vale la pena duplicar el dato."""
        return f"{self.persona.nombres} {self.persona.apellidos}"


# ==========================================
# 🆕 NÚCLEO DEL ESTUDIANTE — ESTRUCTURA ACADÉMICA
# ==========================================
# Jerarquía: Institución -> NivelEducativo -> Grado -> Sección -> (matrícula) -> Persona.
#
# NivelEducativo y Grado son catálogos ESTABLES: se crean una vez por
# institución y se reutilizan cada año ("Secundaria" y su "3°" no cambian en
# 2027 solo porque cambió el año escolar). Sección SÍ está anclada al año
# (`anio_escolar`): la sección real —el grupo de compañeros y el aula— es
# distinta cada año aunque conserve la misma etiqueta ("3° B" de 2025 y "3° B"
# de 2026 son dos filas distintas). Esto hace que "Institución -> Grado ->
# Sección -> Estudiantes" sea una consulta sin ambigüedad para un año dado, y
# que el historial (en qué sección estuvo cada año) salga de tener secciones
# por año en vez de una sola etiqueta reciclada con un año aparte.
#
# `institucion_id` se repite en Grado y Sección aunque ya se puede derivar
# subiendo la cadena de FKs — mismo criterio de defensa en profundidad que ya
# usan CitaProgramada y RegistroAuditoriaArco: permite comprobar en una sola
# fila que un grado/sección pertenece a la institución del que llama, sin
# tener que confiar en que el nivel_educativo_id/grado_id que llegó del
# frontend ya fue validado río arriba.
class NivelEducativo(Base):
    __tablename__ = "niveles_educativos"
    __table_args__ = (
        UniqueConstraint("institucion_id", "nombre", name="uq_niveles_institucion_nombre"),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)   # "Inicial", "Primaria", "Secundaria"...
    orden = Column(Integer, nullable=False, server_default="0", default=0)
    activo = Column(Boolean, nullable=False, server_default="true", default=True)


class Grado(Base):
    __tablename__ = "grados"
    __table_args__ = (
        UniqueConstraint("nivel_educativo_id", "nombre", name="uq_grados_nivel_nombre"),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    nivel_educativo_id = Column(Integer, ForeignKey("niveles_educativos.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)   # "1°", "2°"...
    orden = Column(Integer, nullable=False, server_default="0", default=0)
    activo = Column(Boolean, nullable=False, server_default="true", default=True)


class Seccion(Base):
    __tablename__ = "secciones"
    __table_args__ = (
        UniqueConstraint(
            "grado_id", "nombre", "anio_escolar",
            name="uq_secciones_grado_nombre_anio",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    grado_id = Column(Integer, ForeignKey("grados.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)          # "A", "B"...
    turno = Column(String, nullable=True)             # "Mañana", "Tarde"...
    anio_escolar = Column(Integer, nullable=False, index=True)
    activo = Column(Boolean, nullable=False, server_default="true", default=True)


class MatriculaAcademica(Base):
    """Vincula una Persona a una Sección durante un tramo de tiempo.

    Cambiar de sección NUNCA actualiza una fila existente: cierra la
    matrícula vigente (`fecha_fin = ahora`) y crea una nueva. Así:
      - el historial completo es `SELECT ... ORDER BY fecha_inicio`, sin
        perder nunca dónde estuvo el alumno antes;
      - las evaluaciones ya aplicadas, que copian la sección vigente en el
        momento de matricularse a la campaña (ver `Inscripcion.seccion_id`),
        jamás cambian retroactivamente aunque el alumno se mueva después.

    El índice único parcial garantiza como máximo UNA matrícula vigente
    (`fecha_fin IS NULL`) por persona a la vez — es la base de datos, no la
    aplicación, la que impide dos secciones activas simultáneas.
    """
    __tablename__ = "matriculas_academicas"
    __table_args__ = (
        Index(
            "uq_matricula_activa_por_persona",
            "persona_id",
            unique=True,
            postgresql_where=text("fecha_fin IS NULL"),
        ),
        # 🆕 Promoción anual — por qué existe esta fila (motivo_apertura) y
        # por qué se cerró, si ya se cerró (motivo_cierre). Ambas columnas
        # son nuevas y sin filas previas que las violen, así que llevan CHECK
        # desde el día uno, igual que tipo_consentimiento/estado. NULL en
        # ambas es una fila creada fuera de este flujo (alta manual o import
        # de un estudiante nuevo, cuyo `motivo_apertura` sí se espera que sea
        # 'ingreso_nuevo' cuando venga por la importación Excel).
        CheckConstraint(
            "motivo_apertura IN "
            "('promocion', 'repitencia', 'ingreso_nuevo', 'cambio_manual', 'correccion')",
            name="ck_matriculas_motivo_apertura_valido",
        ),
        CheckConstraint(
            "motivo_cierre IN ('promocion', 'retiro', 'traslado', 'egreso', 'correccion')",
            name="ck_matriculas_motivo_cierre_valido",
        ),
        # 🆕 Decisión de la psicóloga (Fase de diseño, promoción anual): una
        # corrección posterior a una promoción ya confirmada SIEMPRE exige un
        # motivo en texto libre, sin umbral de tiempo — mismo criterio que
        # `InformeVersion.motivo_version` para reemitir un informe. Se aplica
        # tanto si la corrección abrió esta fila como si la cerró.
        CheckConstraint(
            "(motivo_apertura IS DISTINCT FROM 'correccion' "
            "AND motivo_cierre IS DISTINCT FROM 'correccion') "
            "OR motivo_detalle IS NOT NULL",
            name="ck_matriculas_correccion_requiere_motivo",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    seccion_id = Column(Integer, ForeignKey("secciones.id"), nullable=False, index=True)
    fecha_inicio = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    registrado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)

    # 🆕 Promoción anual — ver CheckConstraints arriba. `motivo_detalle` es
    # texto libre (el "por qué" de una corrección puntual); para
    # promoción/repitencia/ingreso_nuevo automáticos no es obligatorio, el
    # propio valor de motivo_apertura/motivo_cierre ya lo explica.
    motivo_apertura = Column(String, nullable=True)
    motivo_cierre = Column(String, nullable=True)
    motivo_detalle = Column(Text, nullable=True)


class ProcesoPromocion(Base):
    """Cabecera de UNA corrida de cierre de año (promoción) para una
    institución: de qué año_escolar a cuál.

    No reemplaza nada de `MatriculaAcademica` — esa sigue siendo la fuente
    de verdad de la matrícula en sí. Esta tabla es el registro de trabajo de
    "qué se propuso, revisó y confirmó" para poder auditar el cierre de año
    completo, no fila por fila.

    El índice único parcial impide confirmar dos veces la misma promoción
    (institución + año origen + año destino) — no porque volver a correrla
    dañaría algo (la selección de candidatos en el flujo ya es idempotente,
    ver diseño), sino para que un cierre de año confirmado no pueda
    duplicarse por error operativo.
    """
    __tablename__ = "procesos_promocion"
    __table_args__ = (
        Index(
            "uq_proceso_promocion_confirmado",
            "institucion_id", "anio_origen", "anio_destino",
            unique=True,
            postgresql_where=text("estado = 'confirmado'"),
        ),
        CheckConstraint(
            "estado IN ('borrador', 'confirmado', 'cancelado')",
            name="ck_procesos_promocion_estado_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    anio_origen = Column(Integer, nullable=False)
    anio_destino = Column(Integer, nullable=False)
    estado = Column(String, nullable=False, server_default="borrador", default="borrador")
    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    fecha_confirmacion = Column(DateTime(timezone=True), nullable=True)


class ProcesoPromocionDetalle(Base):
    """Una fila por estudiante dentro de un `ProcesoPromocion`: la propuesta
    automática, la excepción marcada (si la hubo) y, tras confirmar, qué se
    aplicó realmente.

    `seccion_propuesta_id`/`seccion_definitiva_id` van NULL cuando la
    propuesta (o la decisión final) es "egreso" — no hay sección de destino
    porque no se abre matrícula nueva. `matricula_resultante_id` queda NULL
    para 'retirado'/'trasladado'/'egreso' por la misma razón; para el resto
    apunta a la fila que `matricular_persona_en_seccion` (o su equivalente en
    lote) haya creado al confirmar.
    """
    __tablename__ = "procesos_promocion_detalle"
    __table_args__ = (
        UniqueConstraint(
            "proceso_id", "persona_id",
            name="uq_promocion_detalle_persona_por_proceso",
        ),
        CheckConstraint(
            "tipo_excepcion IN "
            "('ninguna', 'repitente', 'retirado', 'trasladado', 'cambio_manual', 'egreso')",
            name="ck_promocion_detalle_tipo_excepcion_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    proceso_id = Column(
        Integer, ForeignKey("procesos_promocion.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    matricula_origen_id = Column(
        Integer, ForeignKey("matriculas_academicas.id"), nullable=False, index=True,
    )
    seccion_propuesta_id = Column(Integer, ForeignKey("secciones.id"), nullable=True, index=True)
    tipo_excepcion = Column(String, nullable=False, server_default="ninguna", default="ninguna")
    seccion_definitiva_id = Column(Integer, ForeignKey("secciones.id"), nullable=True, index=True)
    aplicado = Column(Boolean, nullable=False, server_default="false", default=False)
    matricula_resultante_id = Column(
        Integer, ForeignKey("matriculas_academicas.id"), nullable=True, index=True,
    )
    # 🆕 Por qué el algoritmo de mapeo NO pudo proponer un destino automático
    # (orden de grados/niveles ambiguo, sección destino inexistente, etc.) —
    # NULL cuando sí hubo propuesta automática. Se recalcula al crear el
    # proceso; no es una fuente de verdad, es solo la explicación mostrada en
    # la vista previa de por qué esta fila quedó en 'cambio_manual'.
    advertencia_mapeo = Column(Text, nullable=True)


# ==========================================
# 🆕 EXPEDIENTE / SEGUIMIENTO DEL ESTUDIANTE
# ==========================================
# Fase de diseño — modelo de datos y esquema solamente. Ningún endpoint ni
# lógica de autorización se construye todavía; eso es la siguiente fase.
#
# `ContactoFamiliar` (más abajo) es independiente de todo lo demás en este
# bloque y no forma parte de la importación masiva por Excel — se edita a
# mano desde la ficha del estudiante.

class ContactoFamiliar(Base):
    """Un apoderado/contacto familiar de un estudiante. Un estudiante puede
    tener varios (persona_id NO es único aquí). `relacion` es un catálogo
    ABIERTO (texto libre), mismo criterio que `Persona.genero`: "madre",
    "padre", "tutor legal", "apoderado"... cualquier texto se acepta tal
    cual, nunca es motivo de rechazo.

    Nunca se borra físicamente: `EntradaExpediente.contacto_familiar_id`
    puede apuntar a esta fila desde una entrada de tipo 'contacto_apoderado'
    ya escrita, y borrar el contacto rompería esa referencia histórica. Para
    retirar un contacto (se mudó, cambió la custodia...) se desactiva
    (`activo=False`), igual que `NivelEducativo`/`Grado`/`Seccion`.
    """
    __tablename__ = "contactos_familiares"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    nombre = Column(String, nullable=False)
    telefono = Column(String, nullable=True)
    relacion = Column(String, nullable=True)   # "madre", "padre", "tutor legal"... catálogo abierto
    email = Column(String, nullable=True)

    activo = Column(Boolean, nullable=False, server_default="true", default=True)
    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())
    registrado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)


class PersonaDatosFamiliares(Base):
    """Bloque de datos familiares de la ficha del estudiante — número de
    hermanos, con quién vive, lugar de nacimiento y lugar de procedencia
    (dos datos distintos: dónde nació vs. de dónde procede/migra, tal como
    los distingue un informe psicológico real). Vive aquí, 1:1 con
    `Persona` y mutable (sin tabla de versiones propia, mismo trato que
    `Persona.genero`/`nombres`), para llenarse UNA vez en la ficha y
    reutilizarse en cualquier informe individual futuro de ese estudiante,
    en vez de recapturarse en cada documento — y explícitamente NO en la
    importación masiva de estudiantes, que no lo toca.

    Un documento que incluye la sección `datos_familiares` (ver
    `modulos/documentos`) snapshotea estos valores en el momento de generar
    su versión — mismo criterio "instantánea, no referencia" que
    `Inscripcion.grado_seccion_historico`: editar este bloque después nunca
    reescribe un documento ya emitido.
    """
    __tablename__ = "personas_datos_familiares"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, unique=True, index=True)

    numero_hermanos = Column(Integer, nullable=True)
    vive_con = Column(String, nullable=True)
    lugar_nacimiento = Column(String, nullable=True)
    lugar_procedencia = Column(String, nullable=True)

    actualizado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    actualizado_en = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class PersonaAntecedentesClinicos(Base):
    """Antecedentes de tratamiento externo y diagnóstico reportado de un
    estudiante — distinto de `PersonaDatosFamiliares` (que es composición
    del hogar: hermanos, con quién vive, procedencia): esto es historial
    clínico externo a AuroraSoft, no generado por ninguna prueba propia.
    Vive en la ficha del estudiante, 1:1 con `Persona`, mutable (sin tabla
    de versiones propia, mismo trato que `PersonaDatosFamiliares`), para
    llenarse una vez y reutilizarse en cualquier informe individual futuro
    — snapshoteado al momento de generar un documento, nunca leído en vivo
    desde un informe ya emitido (mismo criterio "instantánea, no
    referencia" de siempre).

    Los booleanos quedan NULL (no `False`) cuando todavía no se preguntó —
    "no lo sabemos" es distinto de "no, no recibe" y no deben confundirse.
    """
    __tablename__ = "personas_antecedentes_clinicos"

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, unique=True, index=True)

    recibe_terapia_psicologica_externa = Column(Boolean, nullable=True)
    detalle_terapia_psicologica_externa = Column(Text, nullable=True)
    recibe_atencion_psiquiatrica_externa = Column(Boolean, nullable=True)
    detalle_atencion_psiquiatrica_externa = Column(Text, nullable=True)
    diagnostico_reportado = Column(Text, nullable=True)

    actualizado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    actualizado_en = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class EntradaExpediente(Base):
    """La IDENTIDAD de una entrada de la línea de tiempo clínica de un
    estudiante — nunca el contenido en sí. El contenido narrativo vive
    versionado en `EntradaExpedienteVersion` (más abajo), exactamente igual
    que `Informe` es la identidad y `InformeVersion` guarda cada snapshot
    real: esta fila no se edita para cambiar contenido, se le agrega una
    versión nueva.

    Tres tipos son PUENTE, no contenido propio — no duplican nada, solo
    enlazan (de solo lectura) a algo que ya existe, y por eso NUNCA tienen
    versión (`version_actual` queda NULL para ellos — no hay nada propio
    que versionar, el contenido es de la tabla enlazada):
      - 'sesion'                 -> `SesionSeguimiento` (ya existente).
      - 'aplicacion_prueba'      -> `Informe` (ya existente, con su PROPIO
                                     versionado independiente — InformeVersion).
      - 'documento_institucional' -> `DocumentoInstitucional` (modulos/documentos,
                                     con su PROPIO versionado independiente —
                                     DocumentoInstitucionalVersion). Se crea una
                                     fila por cada Persona incluida en el
                                     documento, en el momento en que se emite
                                     su v1 — nunca antes. 🔒 Esta entrada-puente
                                     NUNCA hereda `DocumentoInstitucional.
                                     nivel_visibilidad`: sigue exactamente la
                                     misma regla estricta de confidencialidad
                                     que cualquier otra entrada (ver más abajo),
                                     decisión explícita para no crear un
                                     segundo canal de autorización hacia este
                                     mismo expediente — `AutorizacionAccesoColegio`
                                     sigue siendo la ÚNICA excepción posible.
    Ninguna escritura de este módulo toca esas tres tablas jamás.

    Los otros tres tipos ('observacion_conducta', 'contacto_apoderado',
    'derivacion') SÍ tienen contenido narrativo propio, en sus
    `EntradaExpedienteVersion`.

    🔒 Confidencialidad (regla de la psicóloga, sin nivel intermedio y sin
    excepción para "admin"): el contenido completo de CUALQUIER entrada —
    sin importar su tipo — solo lo puede leer `autor_usuario_id` o
    superadmin. La ÚNICA excepción es `AutorizacionAccesoColegio` (más
    abajo): mientras esté vigente para esta persona, el rol "colegio"
    también obtiene lectura completa. No existe ningún nivel "compartido"
    ni ningún resumen — quedó eliminado a propósito. Esta tabla no necesita
    saber nada de esa autorización — se resuelve enteramente consultando la
    otra tabla en el momento de leer.
    """
    __tablename__ = "expediente_entradas"
    __table_args__ = (
        CheckConstraint(
            "tipo_entrada IN "
            "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', "
            "'aplicacion_prueba', 'documento_institucional')",
            name="ck_expediente_tipo_entrada_valido",
        ),
        # 🔒 Coherencia entre tipo_entrada y qué enlace trae la fila — mismo
        # criterio que ck_reglas_interpretacion_campos_segun_ambito.
        CheckConstraint(
            "(tipo_entrada IN ('observacion_conducta', 'derivacion') "
            " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL"
            " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
            " OR "
            "(tipo_entrada = 'contacto_apoderado' "
            " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL AND documento_institucional_id IS NULL)"
            " OR "
            "(tipo_entrada = 'sesion' "
            " AND sesion_seguimiento_id IS NOT NULL AND informe_id IS NULL"
            " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
            " OR "
            "(tipo_entrada = 'aplicacion_prueba' "
            " AND informe_id IS NOT NULL AND sesion_seguimiento_id IS NULL"
            " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
            " OR "
            "(tipo_entrada = 'documento_institucional' "
            " AND documento_institucional_id IS NOT NULL AND sesion_seguimiento_id IS NULL"
            " AND informe_id IS NULL AND contacto_familiar_id IS NULL)",
            name="ck_expediente_campos_segun_tipo",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    tipo_entrada = Column(String, nullable=False, index=True)
    # 🔒 El único "propietario" clínico de esta entrada — ver el docstring
    # de la clase. Nunca "cualquier psicólogo de la institución".
    autor_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False, index=True)

    fecha_entrada = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # NULL para 'sesion'/'aplicacion_prueba' (nada propio que versionar);
    # para los 3 tipos narrativos, apunta siempre hacia adelante al número
    # de la versión vigente en EntradaExpedienteVersion — mismo mecanismo
    # que Informe.version_actual.
    version_actual = Column(Integer, nullable=True)

    # Enlaces de solo lectura — ver CHECK ck_expediente_campos_segun_tipo.
    sesion_seguimiento_id = Column(Integer, ForeignKey("edu_sesiones_seguimiento.id"), nullable=True, index=True)
    informe_id = Column(Integer, ForeignKey("edu_informes.id"), nullable=True, index=True)
    # Solo relevante (y opcional incluso ahí) para 'contacto_apoderado': a
    # qué apoderado se llamó, si ya estaba registrado en ContactoFamiliar.
    contacto_familiar_id = Column(Integer, ForeignKey("contactos_familiares.id"), nullable=True, index=True)
    # Solo para 'documento_institucional' — enlace de solo lectura al
    # documento (modulos/documentos), nunca escrito por este módulo.
    #
    # Nombre explícito = el que crea la migración 9f13619766a9 (mismo criterio
    # que seccion_id/revisado_por_usuario_id en Inscripcion): sin esto,
    # create_all()/crear_tablas.py dejaba que Postgres autogenerara
    # "expediente_entradas_documento_institucional_id_fkey", distinto del
    # nombre que la migración ya usó en cualquier base real — divergencia
    # puramente de metadata que tests/comparar_esquemas.py detectó.
    documento_institucional_id = Column(
        Integer,
        ForeignKey(
            "documentos_institucionales.id",
            name="fk_expediente_entradas_documento_institucional",
        ),
        nullable=True, index=True,
    )


class EntradaExpedienteVersion(Base):
    """Un snapshot INMUTABLE del contenido narrativo de una
    `EntradaExpediente`, en un momento dado — nunca se edita ni se
    sobreescribe, mismo patrón exacto que `InformeVersion`: corregir una
    entrada crea la versión `numero_version + 1`, la anterior queda intacta
    para siempre. Solo existe para los 3 tipos narrativos (nunca para
    'sesion'/'aplicacion_prueba', que no tienen versión — ver
    `EntradaExpediente.version_actual`).
    """
    __tablename__ = "expediente_entradas_version"
    __table_args__ = (
        UniqueConstraint("entrada_expediente_id", "numero_version", name="uq_expediente_version_entrada_numero"),
    )

    id = Column(Integer, primary_key=True, index=True)
    entrada_expediente_id = Column(Integer, ForeignKey("expediente_entradas.id"), nullable=False, index=True)
    numero_version = Column(Integer, nullable=False)

    motivo = Column(Text, nullable=True)
    contenido = Column(Text, nullable=True)
    interpretacion = Column(Text, nullable=True)
    diagnostico_presuntivo = Column(Text, nullable=True)

    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Obligatorio solo para correcciones (v2+); v1 lleva "Creación inicial"
    # — exactamente el mismo criterio que InformeVersion.motivo_version (la
    # obligatoriedad se exige en el endpoint, no con un CHECK, mismo criterio
    # que el propio InformeVersion).
    motivo_version = Column(Text, nullable=True)


class RegistroLecturasExpediente(Base):
    """Quién leyó el CONTENIDO COMPLETO de una entrada del expediente
    (cualquier versión de él), y cuándo. Append-only — nunca se edita ni se
    borra, mismo criterio que `RegistroCambiosPersona` y
    `RegistroAuditoriaArco`. Se audita TODA lectura de contenido completo,
    sin excepción — incluidas las que ocurren bajo una
    `AutorizacionAccesoColegio` vigente.

    A diferencia de `RegistroAuditoriaArco` (cuyas columnas de sujeto NO
    llevan FK a propósito, porque la propia acción auditada puede destruir
    el vínculo), aquí SÍ son FK normales: leer una entrada nunca la destruye
    ni le cambia nada, así que no hay esa razón para omitir la referencia.

    Ver una fila en un LISTADO (solo metadata: tipo/fecha, sin contenido) no
    genera una fila aquí; solo abrir el contenido completo de una versión
    específica lo hace — esa distinción vive en la fase de endpoints, no en
    este esquema.
    """
    __tablename__ = "registro_lecturas_expediente"

    id = Column(Integer, primary_key=True, index=True)
    entrada_expediente_id = Column(Integer, ForeignKey("expediente_entradas.id"), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    leido_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False, index=True)
    rol_lector = Column(String, nullable=True)
    fecha_lectura = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    ip_lectura = Column(String, nullable=True)
    # 🆕 Qué versión concreta se leyó — un expediente con historial de
    # correcciones necesita poder decir "leyó la v2", no solo "leyó algo de
    # esta entrada". NULL para una entrada puente sin versión propia.
    numero_version_leida = Column(Integer, nullable=True)

    # 🆕 Ampliación 1 — si esta lectura de "colegio" solo fue posible por una
    # excepción vigente, queda apuntada aquí: un puntero permanente e
    # inmutable a "bajo qué autorización se leyó esto", mismo patrón que
    # `Inscripcion.consentimiento_apoderado_id` snapshotea qué consentimiento
    # respaldó una aplicación. NULL para cualquier lectura del propio autor
    # o de superadmin, que no depende de ninguna excepción.
    autorizacion_acceso_colegio_id = Column(
        Integer, ForeignKey("autorizaciones_acceso_colegio.id"), nullable=True, index=True,
    )


class AutorizacionAccesoColegio(Base):
    """🆕 Ampliación 1 — excepción explícita, por estudiante, otorgada por
    el propio equipo clínico (rol 'psicologo'; nunca 'colegio' ni 'admin')
    para que el rol 'colegio' obtenga lectura COMPLETA del expediente de
    ESE estudiante (todas las entradas, todo el contenido narrativo),
    mientras esté vigente.

    El expediente es confidencial por defecto y siempre (autor + superadmin
    únicamente); esta tabla es la ÚNICA excepción posible, y es por
    estudiante, no por entrada — no cambia ni una fila del expediente, solo
    se consulta en el momento de leer.

    Mismo mecanismo que `ConsentimientoInformado`: otorgar es una fila
    NUEVA; revocar MUTA la misma fila (fecha_revocado/revocado_por, nunca se
    borra ni se reescribe motivo/otorgado_por); el índice único parcial
    garantiza como máximo UNA vigente por persona, así que renovar tras una
    revocación exige otra fila nueva, no reactivar la vieja — la base de
    datos, no la aplicación, es la que impide dos excepciones vigentes
    simultáneas para el mismo estudiante.
    """
    __tablename__ = "autorizaciones_acceso_colegio"
    __table_args__ = (
        Index(
            "uq_autorizacion_colegio_vigente_por_persona",
            "persona_id",
            unique=True,
            postgresql_where=text("vigente = true"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    otorgado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    # Snapshot del rol de quien otorgó, en el momento de otorgar — mismo
    # criterio que RegistroCambiosPersona.rol_modificador. Que solo
    # "psicologo" pueda otorgar/revocar se exige en el endpoint (fase
    # siguiente), no aquí; esta columna es solo el rastro de auditoría.
    rol_otorgante = Column(String, nullable=True)
    motivo = Column(Text, nullable=False)
    fecha_otorgado = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vigente = Column(Boolean, nullable=False, server_default="true", default=True)
    fecha_revocado = Column(DateTime(timezone=True), nullable=True)
    revocado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    rol_revocador = Column(String, nullable=True)