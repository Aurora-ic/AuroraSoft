export type Rol = "superadmin" | "admin" | "psicologo" | "colegio";

// 🆕 Paginación real (ver docs/gaps-pendientes.md, hallazgo "Sin
// paginación real") — envoltorio único para los listados que antes
// devolvían una lista plana sin tope: GET /admin/personas/{institucion_id},
// GET /educativo/campanas/, GET /documentos/.
export type RespuestaPaginada<T> = {
  total: number;
  items: T[];
};

// Subconjunto de schemas.InstitucionResponse — solo lo que la UI consume
// hoy (el nombre para identificar de qué colegio se trata en el layout).
export type Institucion = {
  id: number;
  nombre: string;
  tipo: string | null;
  direccion: string | null;
  telefono: string | null;
  email_contacto: string | null;
  fecha_registro: string;
  plan_activo: boolean;
  logo_url?: string | null;
  logo_pie_pagina_url?: string | null;
  fondo_documento_url?: string | null;
  fecha_vencimiento_licencia: string | null;
  limite_pruebas_mensual_por_alumno: number;
  anio_escolar_activo: number | null;
  exigir_asentimiento_estudiante: boolean;
};

export type InstitucionCreate = {
  nombre: string;
  tipo?: string;
  direccion?: string | null;
  telefono?: string | null;
  email_contacto?: string | null;
  plan_activo?: boolean;
  fecha_vencimiento_licencia?: string | null;
  limite_pruebas_mensual_por_alumno?: number;
};

export type InstitucionUpdate = Partial<InstitucionCreate>;

export type UsuarioCreate = {
  email: string;
  password: string;
  nombre_completo: string;
  rol: Rol;
  institucion_id?: number | null;
};

export type UsuarioUpdate = {
  nombre_completo?: string;
  activo?: boolean;
  cargo?: string;
  firma_imagen_url?: string;
};

// Sección vigente de un estudiante, ya resuelta a etiquetas legibles —
// batch-loaded (join MatriculaAcademica -> Seccion -> Grado -> NivelEducativo)
// dentro de GET /admin/personas/{institucion_id}, sin una consulta por
// alumno. null si la persona no tiene matrícula activa.
export type SeccionActual = {
  matricula_id: number;
  seccion_id: number;
  seccion: string | null;
  turno: string | null;
  anio_escolar: number | null;
  grado_id: number | null;
  grado: string | null;
  nivel_educativo_id: number | null;
  nivel_educativo: string | null;
  fecha_inicio: string;
  fecha_fin: string | null;
};

export type Persona = {
  id: number;
  institucion_id: number;
  tipo_perfil: string;
  nombres: string;
  apellidos: string;
  documento_identidad: string | null;
  codigo_institucional: string | null;
  email: string | null;
  fecha_nacimiento: string | null;
  genero: string | null;
  // Texto libre heredado — ningún flujo de matrícula lo actualiza. No usar
  // para mostrar la sección real de un estudiante: usar `seccion_actual`.
  grado_seccion: string | null;
  puesto_postula: string | null;
  area_empresa: string | null;
  activo: boolean;
  fecha_registro: string;
  seccion_actual: SeccionActual | null;
};

// ==========================================
// Estructura académica — Nivel -> Grado -> Sección (anclada a anio_escolar)
// ==========================================
export type NivelEducativo = {
  id: number;
  institucion_id: number;
  nombre: string;
  orden: number;
  activo: boolean;
};

// Único de los tres que pide institucion_id explícito — no tiene padre del
// que derivarlo (Grado/Seccion sí lo derivan, ver sus *Create de abajo).
export type NivelEducativoCreate = {
  institucion_id: number;
  nombre: string;
  orden?: number;
};

export type Grado = {
  id: number;
  institucion_id: number;
  nivel_educativo_id: number;
  nombre: string;
  orden: number;
  activo: boolean;
};

export type GradoCreate = {
  nivel_educativo_id: number;
  nombre: string;
  orden?: number;
};

export type Seccion = {
  id: number;
  institucion_id: number;
  grado_id: number;
  nombre: string;
  turno: string | null;
  anio_escolar: number;
  activo: boolean;
};

export type SeccionCreate = {
  grado_id: number;
  nombre: string;
  turno?: string | null;
  anio_escolar: number;
};

export type MatriculaCreate = {
  seccion_id: number;
};

export type MatriculaResponse = {
  id: number;
  persona_id: number;
  institucion_id: number;
  seccion_id: number;
  fecha_inicio: string;
  fecha_fin: string | null;
  registrado_por_usuario_id: number | null;
  motivo_apertura: string | null;
  motivo_cierre: string | null;
};

// ==========================================
// Importación masiva de estudiantes (Excel) — modulos/superadmin/importacion_estudiantes.py
// ==========================================
export type ImportacionAccionFila = "nuevo" | "actualizado" | "duplicado" | "error";

export type ImportacionErrorCampo = {
  campo: string;
  problema: string;
  valor_recibido: string;
  correccion_esperada: string;
};

export type ImportacionEstructuraAcademica = {
  nivel_id: number | null;
  nivel: string | null;
  grado_id: number | null;
  grado: string | null;
  seccion_id: number | null;
  seccion: string | null;
  anio_escolar: number | null;
  turno: string | null;
};

// Fila devuelta por POST /importar/validar — nunca escribe nada, es solo
// vista previa.
export type ImportacionFilaValidacion = {
  fila: number;
  accion: ImportacionAccionFila;
  codigo_institucional: string;
  nombres: string;
  apellidos: string;
  documento_identidad: string | null;
  fecha_nacimiento: string | null;
  genero: string | null;
  datos_incompletos: string[];
  estructura_academica: ImportacionEstructuraAcademica | null;
  persona_id_existente: number | null;
  errores: ImportacionErrorCampo[];
};

export type ImportacionResumen = {
  nuevos: number;
  actualizados: number;
  duplicados: number;
  errores: number;
};

export type ImportacionValidacionResultado = {
  total_filas: number;
  resumen: ImportacionResumen;
  filas_con_datos_incompletos: number;
  filas: ImportacionFilaValidacion[];
};

// Fila devuelta por POST /importar/confirmar, una vez aplicada de verdad.
export type ImportacionDetalleConfirmacion = {
  fila: number;
  accion: ImportacionAccionFila;
  codigo_institucional: string;
  persona_id: number;
  datos_incompletos: string[];
};

export type ImportacionConfirmacionResultado = {
  total_filas: number;
  resumen: ImportacionResumen;
  filas_con_datos_incompletos: number;
  detalle: ImportacionDetalleConfirmacion[];
};

// Solo los campos que PATCH /admin/personas/{persona_id} admite corregir
// (schemas.PersonaUpdate en el backend) — todos opcionales, se manda solo
// lo que cambia.
export type PersonaUpdate = Partial<
  Pick<
    Persona,
    | "nombres"
    | "apellidos"
    | "fecha_nacimiento"
    | "documento_identidad"
    | "codigo_institucional"
    | "email"
    | "genero"
    | "grado_seccion"
    | "activo"
  >
>;

// GET /admin/personas/{persona_id}/historial-cambios — una fila por campo
// modificado vía PersonaUpdate, nunca editada ni borrada.
export type RegistroCambioPersona = {
  id: number;
  campo: string;
  valor_anterior: string | null;
  valor_nuevo: string | null;
  modificado_por_usuario_id: number;
  rol_modificador: string | null;
  fecha: string;
};

// ==========================================
// Contactos familiares — modulos/superadmin
// ==========================================
export type ContactoFamiliar = {
  id: number;
  persona_id: number;
  institucion_id: number;
  nombre: string;
  telefono: string | null;
  relacion: string | null; // catálogo abierto: "madre", "padre", "tutor legal"...
  email: string | null;
  activo: boolean;
  fecha_registro: string;
  registrado_por_usuario_id: number | null;
};

export type ContactoFamiliarCreate = {
  nombre: string;
  telefono?: string | null;
  relacion?: string | null;
  email?: string | null;
};

export type ContactoFamiliarUpdate = Partial<ContactoFamiliarCreate>;

// ==========================================
// Datos de filiación del estudiante — modulos/superadmin
// (bloques 1:1 con Persona, se llenan una sola vez y se reutilizan/
// congelan como snapshot en cada informe/documento que los incluya)
// ==========================================
export type PersonaDatosFamiliares = {
  persona_id: number;
  numero_hermanos: number | null;
  vive_con: string | null;
  lugar_nacimiento: string | null;
  lugar_procedencia: string | null;
  actualizado_por_usuario_id: number | null;
  actualizado_en: string | null; // null = nunca editado
};

export type PersonaDatosFamiliaresUpdate = {
  numero_hermanos?: number | null;
  vive_con?: string | null;
  lugar_nacimiento?: string | null;
  lugar_procedencia?: string | null;
};

export type PersonaAntecedentesClinicos = {
  persona_id: number;
  // null = "no preguntado todavía", distinto de false ("no, no recibe") —
  // nunca se fuerza a false por defecto.
  recibe_terapia_psicologica_externa: boolean | null;
  detalle_terapia_psicologica_externa: string | null;
  recibe_atencion_psiquiatrica_externa: boolean | null;
  detalle_atencion_psiquiatrica_externa: string | null;
  diagnostico_reportado: string | null;
  actualizado_por_usuario_id: number | null;
  actualizado_en: string | null;
};

export type PersonaAntecedentesClinicosUpdate = {
  recibe_terapia_psicologica_externa?: boolean | null;
  detalle_terapia_psicologica_externa?: string | null;
  recibe_atencion_psiquiatrica_externa?: boolean | null;
  detalle_atencion_psiquiatrica_externa?: string | null;
  diagnostico_reportado?: string | null;
};

// ==========================================
// Expediente clínico — EntradaExpediente / EntradaExpedienteVersion
// ==========================================

// Debe coincidir con crud.TIPOS_ENTRADA_VALIDOS (backend). Los primeros 3
// tienen contenido narrativo propio y versionado; "sesion"/"aplicacion_prueba"
// son entradas puente que solo enlazan a una SesionSeguimiento/Informe ya
// existente y nunca tienen contenido ni versión propios.
export type TipoEntradaExpediente =
  | "observacion_conducta"
  | "contacto_apoderado"
  | "derivacion"
  | "sesion"
  | "aplicacion_prueba";

// GET /admin/personas/{persona_id}/expediente — solo metadata, nunca
// contenido narrativo. El backend ya filtra esta lista por la regla de
// acceso (autor, superadmin, o "colegio" con autorización vigente): si una
// entrada aparece aquí, este usuario puede abrirla.
export type EntradaExpediente = {
  id: number;
  persona_id: number;
  institucion_id: number;
  tipo_entrada: TipoEntradaExpediente;
  autor_usuario_id: number;
  fecha_entrada: string;
  creado_en: string;
  version_actual: number | null;
  sesion_seguimiento_id: number | null;
  informe_id: number | null;
  contacto_familiar_id: number | null;
};

// El contenido narrativo de una versión concreta — solo existe para los 3
// tipos con contenido propio.
export type EntradaExpedienteVersion = {
  numero_version: number;
  motivo: string | null;
  contenido: string | null;
  interpretacion: string | null;
  diagnostico_presuntivo: string | null;
  creado_por_usuario_id: number;
  creado_en: string;
  motivo_version: string | null; // null en la v1 ("Creación inicial" implícita)
};

// GET /admin/personas/expediente/{entrada_id} — metadata + la versión
// solicitada (la vigente, o ?version=N). null cuando la entrada es puente
// y no tiene contenido propio que mostrar.
export type EntradaExpedienteDetalle = EntradaExpediente & {
  version: EntradaExpedienteVersion | null;
};

export type EntradaExpedienteCreate = {
  tipo_entrada: TipoEntradaExpediente;
  fecha_entrada?: string | null; // ausente/null -> ahora
  motivo?: string | null;
  contenido?: string | null;
  interpretacion?: string | null;
  diagnostico_presuntivo?: string | null;
  sesion_seguimiento_id?: number | null;
  informe_id?: number | null;
  contacto_familiar_id?: number | null;
};

// POST /admin/personas/expediente/{entrada_id}/versiones — siempre v2+;
// motivo_version es obligatorio sin excepción (la v1 se crea junto con la
// entrada y no pasa por aquí).
export type EntradaExpedienteVersionCreate = {
  motivo?: string | null;
  contenido?: string | null;
  interpretacion?: string | null;
  diagnostico_presuntivo?: string | null;
  motivo_version: string;
};

// ==========================================
// Autorización de acceso del colegio — excepción de solo lectura, por
// estudiante, para el rol "colegio". Nunca habilita escritura.
// ==========================================
export type AutorizacionAccesoColegio = {
  id: number;
  persona_id: number;
  institucion_id: number;
  otorgado_por_usuario_id: number;
  rol_otorgante: string | null;
  motivo: string;
  fecha_otorgado: string;
  vigente: boolean;
  fecha_revocado: string | null;
  revocado_por_usuario_id: number | null;
  rol_revocador: string | null;
};

export type AutorizacionAccesoColegioCreate = {
  motivo: string;
};

// ==========================================
// Consentimiento informado — dos tipos independientes por persona+institución
// (ver backend/modulos/superadmin/models.py, ConsentimientoInformado):
// "apoderado" (siempre obligatorio para matricular en campaña o completar un
// examen) y "asentimiento" del propio estudiante (solo exigido si la
// institución activó Institucion.exigir_asentimiento_estudiante). Historial
// append-only: a lo sumo UN registro con estado "vigente" por persona+
// institución+tipo (índice único parcial en el backend) — revocar nunca
// borra, solo cierra esa fila; "renovar" es registrar uno nuevo.
// ==========================================
export type TipoConsentimiento = "apoderado" | "asentimiento";
export type EstadoConsentimiento = "vigente" | "revocado";
export type TipoOtorgante = "apoderado" | "colegio_delegado";

export type ConsentimientoInformado = {
  id: number;
  persona_id: number;
  institucion_id: number;
  tipo_consentimiento: TipoConsentimiento;
  estado: EstadoConsentimiento;
  // Los 4 campos de otorgante solo aplican a tipo_consentimiento="apoderado"
  // — en "asentimiento" van null (el titular es el propio estudiante).
  otorgado_por_nombre: string | null;
  otorgante_apellidos: string | null;
  otorgante_documento: string | null;
  otorgante_relacion: string | null;
  tipo_otorgante: TipoOtorgante | null;
  referencia_documento: string | null;
  registrado_por_usuario_id: number;
  fecha_otorgamiento: string;
  revocado: boolean;
  fecha_revocacion: string | null;
  // Metadata de la evidencia subida (ver /consentimiento/{id}/evidencia) —
  // la key de storage (evidencia_ruta) nunca se expone en la respuesta.
  evidencia_nombre_archivo: string | null;
  evidencia_content_type: string | null;
  evidencia_tamano_bytes: number | null;
  evidencia_subido_en: string | null;
};

export type ConsentimientoCreate = {
  otorgado_por_nombre: string;
  tipo_otorgante: TipoOtorgante;
  referencia_documento?: string | null;
  otorgante_apellidos?: string | null;
  otorgante_documento?: string | null;
  otorgante_relacion?: string | null;
};

export type ConsentimientoAsentimientoCreate = {
  referencia_documento?: string | null;
};

export type ConsentimientoEstadoHistorial = {
  tiene_consentimiento_vigente: boolean;
  historial: ConsentimientoInformado[];
};

// GET /admin/personas/{persona_id}/consentimientos — ambos tipos combinados.
export type ConsentimientosCombinados = {
  persona_id: number;
  apoderado: ConsentimientoEstadoHistorial;
  asentimiento: ConsentimientoEstadoHistorial;
};

export type CitaParticipante = {
  persona_id: number;
  nombre_completo: string;
};

// `persona_id` presente = cita individual de siempre (ligada a un alumno
// puntual). `persona_id` ausente = actividad grupal (taller/charla/otro) —
// en ese caso trae `titulo`/`tipo_actividad`/`lugar` y, opcionalmente,
// `participantes` (puede venir vacío: no es obligatorio nombrar asistentes).
// Visible para todo el staff de la institución, a diferencia de una cita
// individual (que solo ve quien la agendó) — ver GET /citas/mi-agenda.
export type Cita = {
  id: number;
  persona_id: number | null;
  psicologo_id: number;
  institucion_id: number;
  motivo: string;
  fecha_hora: string;
  estado: "Programada" | "Realizada" | "Cancelada";
  titulo: string | null;
  tipo_actividad: string | null;
  lugar: string | null;
  participantes: CitaParticipante[];
};

export type CitaUpdate = Partial<
  Pick<Cita, "motivo" | "fecha_hora" | "estado" | "titulo" | "tipo_actividad" | "lugar">
>;

export type CitaCreate = {
  persona_id?: number | null;
  institucion_id?: number | null; // solo lo usa superadmin creando una actividad grupal
  motivo: string;
  fecha_hora: string;
  titulo?: string | null; // obligatorio si no hay persona_id
  tipo_actividad?: string | null;
  lugar?: string | null;
  participantes_ids?: number[];
};

export type SesionSeguimiento = {
  id: number;
  persona_id: number;
  psicologo_id: number;
  fecha: string;
  observaciones: string;
  accion_tomada: string | null;
  acuerdos_compromisos: string | null;
  proxima_cita: string | null;
  estado: string;
};

export type SesionSeguimientoUpdate = Partial<
  Pick<SesionSeguimiento, "observaciones" | "accion_tomada" | "acuerdos_compromisos" | "proxima_cita" | "estado">
>;

export type SesionSeguimientoCreate = {
  persona_id: number;
  observaciones?: string;
  accion_tomada?: string;
};

export type Usuario = {
  id: number;
  email: string;
  nombre_completo: string;
  rol: Rol;
  institucion_id: number | null;
  activo: boolean;
  fecha_registro: string;
  cargo: string | null;
  firma_imagen_url: string | null;
};

// ==========================================
// Flujo público del examen (sin sesión, token mágico en la URL) — ver
// app/(examen)/examen/[token]/.
// ==========================================

export type RegistroAlumnoDemograficos = {
  nombre_completo: string;
  edad: number;
  sexo: "Masculino" | "Femenino";
  poblacion: "Primaria" | "Secundaria" | "Universitario";
  acepta_terminos: boolean;
  // Solo exigidos por el backend cuando la Prueba de esta inscripción tiene
  // informante_tipo != 'estudiante' (un padre/madre o docente respondiendo
  // EN NOMBRE del alumno) — para autorreporte, da igual mandarlos vacíos.
  informante_nombre?: string | null;
  informante_relacion?: string | null;
};

// Lo que ya se sabe de esta inscripción ANTES de pedirle nada al estudiante
// (ver GET /educativo/examen/{token}/intake) — para no volver a pedir datos
// que el colegio ya cargó al matricular por padrón.
export type IntakeExamen = {
  nombre_completo: string | null;
  nombre_conocido: boolean; // true si viene de una Persona del padrón, no editable
  edad: number | null;
  sexo: string | null;
  poblacion: string | null;
  informante_tipo: string;
  ya_acepto_asentimiento: boolean;
};

// 🆕 Texto versionado del asentimiento informado (reemplaza la constante
// fija que antes vivía en examen/[token]/page.tsx) — ver docs/gaps-pendientes.md.
export type AsentimientoInformadoTextoPublico = {
  version: number;
  contenido: string; // párrafos separados por "\n", mismo criterio que el array viejo
};

export type AsentimientoInformadoTexto = {
  id: number;
  institucion_id: number | null; // null = versión global
  version: number;
  contenido: string;
  activo: boolean;
  creado_en: string;
};

export type AsentimientoInformadoTextoCreate = {
  institucion_id?: number | null; // omitido/null = versión GLOBAL (solo superadmin)
  contenido: string;
};

export type CampoSociodemografico = {
  id: number;
  pregunta: string;
  tipo_respuesta: string;
  opciones: string | null; // CSV cuando tipo_respuesta es de opción cerrada
  obligatorio: boolean;
};

export type OpcionExamen = {
  id: number;
  texto_opcion: string;
};

export type PreguntaExamen = {
  id: number;
  texto_pregunta: string;
  // 🆕 "opcion_multiple" (de siempre) o "numerico" — ver Pregunta.tipo_respuesta
  // en el backend (BARSIT "Razonamiento numérico" es el primer caso real).
  tipo_respuesta: string;
  // 🆕 Solo cuando tipo_respuesta es "numerico": cuántos campos numéricos debe
  // llenar el alumno (ej. 2 para una serie con dos espacios en blanco). Nunca
  // la clave de corrección — eso se queda solo en el servidor.
  cantidad_valores_numericos: number | null;
  opciones: OpcionExamen[];
};

export type RespuestaAlumnoSubmit = {
  pregunta_id: number;
  // 🆕 Ambos opcionales: una pregunta "opcion_multiple" manda opcion_id, una
  // "numerico" manda respuesta_numerica — exactamente uno de los dos.
  opcion_id?: number | null;
  respuesta_numerica?: number[] | null;
};

export type ProgresoExamen = {
  estado: string;
  respuestas: RespuestaAlumnoSubmit[];
};

export type DiagnosticoAlumno = {
  id: number;
  inscripcion_id: number;
  dimension_id: number;
  nivel: string;
  interpretacion: string | null;
  es_alerta: boolean;
};

export type EstadoResultadosAlumno = {
  estado_examen: string;
  resultado_visible_alumno: boolean;
  informe_liberado: boolean;
  estado_interpretacion: string;
  mensaje: string;
};

// ==========================================
// Motor de pruebas/campañas (modulos/educativo). Crear/editar el
// CATÁLOGO de pruebas (ítems, dimensiones, baremos) es carga de datos vía
// seed/API directa, no una pantalla — ver CLAUDE.md "Scoring engine": se
// trata como un ejercicio de datos, nunca de código. Esta UI solo LEE el
// catálogo (para elegir una prueba al crear una campaña) y administra el
// ciclo de vida de una campaña (crear, matricular, cerrar/cancelar, ver
// resultados).
// ==========================================

export type Prueba = {
  id: number;
  nombre_tecnico: string;
  nombre_publico: string;
  // Título corto curado para UI — null = usar nombre_tecnico como respaldo
  // (ya es razonable para la mayoría; solo instrumentos con nombre_tecnico
  // "feo" tipo HAMILTON_AUTOINFORME lo definen).
  nombre_corto: string | null;
  instrucciones: string | null;
  activa: boolean;
  modo_calculo: string;
  modo_interpretacion: string;
  visible_para_clientes: boolean;
  informante_tipo: string;
};

export type Dimension = {
  id: number;
  prueba_id: number;
  nombre: string;
  descripcion: string | null;
  tipo_calculo: string;
};

// GET /educativo/pruebas/{id}/completa — detalle con dimensiones (para
// decidir, al crear una campaña, qué mide realmente la prueba elegida).
export type PruebaDetalle = Prueba & {
  dimensiones: Dimension[];
};

export type Evaluacion = {
  id: number;
  prueba_id: number;
  nombre_grupo: string;
  activo: boolean;
  estado: string; // "activa" | "cerrada" | "cancelada"
  fecha_fin: string | null;
  fecha_creacion: string;
};

export type EvaluacionCreate = {
  prueba_id: number;
  nombre_grupo: string;
  institucion_id: number;
  fecha_fin?: string | null;
};

export type EvaluacionUpdate = Partial<{
  nombre_grupo: string;
  fecha_fin: string | null;
  prueba_id: number;
}>;

// GET /educativo/campanas/{id}/links y POST .../matricular-roster — el
// token ES una credencial de acceso al examen de ese alumno, no solo un id.
export type InscripcionCampana = {
  id: number;
  evaluacion_id: number;
  token: string;
  nombre_completo: string | null;
  edad: number | null;
  sexo: string | null;
  estado: string;
  fecha_resolucion: string | null;
  informe_liberado: boolean;
  estado_interpretacion: string;
};

export type MatriculaRosterResponse = {
  generados: InscripcionCampana[];
  rechazados: { persona_id: number; nombre: string; motivo: string }[];
  error: string | null;
};

export type ResultadoAlumnoDashboard = {
  dimension: string;
  puntaje_directo: number;
  nivel: string | null;
  // Rango del tramo de Baremo que produjo este nivel, y si es de alerta —
  // null cuando no hay diagnóstico aplicable (sin baremo, o modo "perfil").
  minimo?: number | null;
  maximo?: number | null;
  es_alerta?: boolean | null;
};

export type AlumnoDashboard = {
  inscripcion_id: number;
  nombre_completo: string | null;
  estado: string;
  fecha_resolucion: string | null;
  resultados: ResultadoAlumnoDashboard[];
  // Solo viene relleno en DashboardAcademico de ámbito "grado" (varias
  // secciones combinadas) — ver ese tipo más abajo.
  seccion?: string | null;
};

// Resumen estadístico por dimensión — ver crud.calcular_resumen_estadistico_
// dashboard en el backend (una sola implementación, compartida por el JSON
// de ambos dashboards y por la hoja "Resumen estadístico" del Excel). Señales
// ESTRUCTURALES de la prueba (nunca por nombre/clave — ver docs/motor-
// scoring.md) para que ResumenEstadisticoPrueba elija la presentación
// correcta sin conocer el instrumento: modo_interpretacion decide niveles+
// alertas ("rango") vs. ranking comparativo ("perfil", hoy solo
// IPIP-RIASEC); agrupar_dimensiones_por_area agrupa por área (CHASIDE);
// tiene_alertas_posibles oculta la tarjeta de alertas por completo en una
// prueba no clínica, en vez de mostrar "0 alertas" engañoso.
//
// 🔒 Se calcula server-side ANTES de la redacción para 'colegio' — es un
// agregado de grupo, nunca el diagnóstico puntual de un alumno (mismo
// criterio que ya protegía `distribucion_por_dimension`), así que sigue
// viniendo completo aunque `alumnos[].resultados` llegue vacío.
export type NivelDistribucionDashboard = {
  nivel: string;
  cantidad: number;
  pct: number;
  es_alerta: boolean;
};

export type DimensionResumenEstadistico = {
  nombre: string;
  tipo_calculo: "items" | "suma_de_dimensiones" | "conteo_sintomas";
  n: number;
  media: number | null;
  mediana: number | null;
  minimo: number | null;
  maximo: number | null;
  // El máximo del tramo de Baremo más alto alcanzado entre los alumnos del
  // grupo — null en modo "perfil" (nunca hay Baremo).
  maximo_escala: number | null;
  // Ordenada de mayor a menor cantidad — distribucion[0], si existe, es la
  // mayoría. Vacía en modo "perfil".
  distribucion: NivelDistribucionDashboard[];
  en_alerta: number | null; // null cuando tiene_alertas_posibles=false
  // Solo en modo "perfil": cuántos alumnos tienen a ESTA dimensión como la
  // de mayor puntaje de su propio ranking.
  dominante_cantidad: number | null;
};

export type AreaCompatibleDashboard = {
  area: string;
  cantidad: number;
};

export type ResumenEstadisticoDashboard = {
  modo_interpretacion: "rango" | "perfil";
  agrupar_dimensiones_por_area: boolean;
  tiene_alertas_posibles: boolean;
  dimensiones: DimensionResumenEstadistico[];
  // Solo relleno cuando agrupar_dimensiones_por_area=true (CHASIDE).
  areas_compatibles: AreaCompatibleDashboard[];
};

// GET /educativo/campanas/{id}/dashboard — para 'colegio' viene redactado
// server-side (alumnos[].resultados queda vacío), nunca se filtra aquí.
export type DashboardCampana = {
  evaluacion_id: number;
  nombre_grupo: string;
  nombre_prueba: string;
  nombre_corto_prueba?: string | null;
  total_inscritos: number;
  total_finalizados: number;
  total_pendientes: number;
  distribucion_por_dimension: Record<string, Record<string, number>>;
  alumnos: AlumnoDashboard[];
  resumen_estadistico: ResumenEstadisticoDashboard;
  // Campos de la propia Evaluacion, para "Editar campaña" (PATCH
  // /campanas/{id}) sin un segundo endpoint — ver DashboardCampanaResponse
  // en el backend.
  estado: "activa" | "cerrada" | "cancelada";
  fecha_fin: string | null;
  prueba_id: number;
};

// GET /educativo/dashboard/academico?prueba_id=&seccion_id=|grado_id= — mismo
// tipo de resumen que DashboardCampana, pero cruzando TODAS las campañas en
// las que se aplicó esa prueba para un salón o grado, no una campaña puntual.
// GET .../exportar-excel (mismo query, nueva) descarga el mismo Excel que ya
// existía para la campaña puntual, incluida la hoja de resumen estadístico.
export type AmbitoDashboardAcademico = {
  tipo: "seccion" | "grado";
  id: number;
  nombre: string;
};

export type DashboardAcademico = {
  prueba_id: number;
  nombre_prueba: string;
  nombre_corto_prueba?: string | null;
  ambito: AmbitoDashboardAcademico;
  total_inscritos: number;
  total_finalizados: number;
  total_pendientes: number;
  distribucion_por_dimension: Record<string, Record<string, number>>;
  alumnos: AlumnoDashboard[];
  resumen_estadistico: ResumenEstadisticoDashboard;
};

// GET /educativo/dashboard/academico/tendencia?prueba_id=&seccion_id= —
// evolución de UN salón en el tiempo: un punto por campaña (nunca fundidas
// en un solo agregado, a diferencia de DashboardAcademico), ordenados por
// fecha. Nunca expone alumnos[] — solo resumen_estadistico por punto.
export type PuntoTendenciaSeccion = {
  evaluacion_id: number;
  nombre_grupo: string;
  fecha: string;
  total_finalizados: number;
  resumen_estadistico: ResumenEstadisticoDashboard;
};

export type TendenciaSeccion = {
  prueba_id: number;
  nombre_prueba: string;
  nombre_corto_prueba?: string | null;
  ambito: AmbitoDashboardAcademico;
  puntos: PuntoTendenciaSeccion[];
};

// ==========================================
// Documentos institucionales — motor genérico de informes configurables
// por institución (backend: modulos/documentos). Desde la pantalla
// /documentos (el "constructor"), admin/psicólogo de la institución dueña
// arman y editan su propia PlantillaDocumento/PlantillaSeccion — ver
// "Constructor de plantillas" en docs/motor-documentos.md. TipoDocumento
// (el catálogo global de clases de documento) sigue siendo solo lectura
// para no-superadmin.
// ==========================================

// Debe coincidir con _TIPOS_SECCION_VALIDOS (backend, schemas.py).
export type TipoSeccionDocumento =
  | "encabezado"
  | "datos_filiacion"
  | "datos_familiares"
  | "texto_libre"
  | "tabla_dinamica"
  | "resultados_prueba"
  | "firma"
  | "grupo_campos"
  | "firma_doble"
  | "ficha_imprimible"
  | "grafico_barras"
  | "imagen_anexo"
  | "firma_triple"
  | "resultados_prueba_multiple";

export type TipoDocumento = {
  id: number;
  clave: string;
  nombre: string;
  alcances_permitidos: string; // CSV
  visibilidades_permitidas: string; // CSV
  requiere_consentimiento_individual: boolean;
  activo: boolean;
};

export type PlantillaDocumento = {
  id: number;
  // null = plantilla PREDETERMINADA global (catálogo mantenido por
  // superadmin, clonable por cualquier institución vía POST .../clonar).
  institucion_id: number | null;
  tipo_documento_id: number;
  nombre: string;
  activa: boolean;
  fuente: string;
  tamano_pt: number;
  interlineado: number;
  justificado: boolean;
  // Estilo del título del documento — independiente del cuerpo.
  titulo_negrita: boolean;
  titulo_cursiva: boolean;
  titulo_tamano_pt: number | null;
  // Tamaño del SUBTÍTULO de cada sección — null = tamano_pt + 1 (fórmula
  // de siempre), mismo criterio que titulo_tamano_pt. Siempre negrita.
  subtitulo_tamano_pt: number | null;
  // Fondo de página de la institución (Institucion.fondo_documento_url) —
  // apagado por defecto, opt-in por plantilla.
  mostrar_fondo_institucion: boolean;
  formato_correlativo: string | null;
  correlativo_reinicia_anualmente: boolean;
  generar_automaticamente_al_finalizar_examen: boolean;
  creado_por_usuario_id: number;
  creado_en: string;
};

// POST /documentos/plantillas — institucion_id null solo lo acepta el
// backend de un superadmin (crea una PREDETERMINADA global); para
// cualquier otro rol se IGNORA y se fuerza a la institución de quien llama
// (ver docs/motor-documentos.md).
export type PlantillaDocumentoCreate = {
  institucion_id: number | null;
  tipo_documento_id: number;
  nombre: string;
  activa?: boolean;
  fuente?: string;
  tamano_pt?: number;
  interlineado?: number;
  justificado?: boolean;
  titulo_negrita?: boolean;
  titulo_cursiva?: boolean;
  titulo_tamano_pt?: number | null;
  subtitulo_tamano_pt?: number | null;
  mostrar_fondo_institucion?: boolean;
  formato_correlativo?: string | null;
  correlativo_reinicia_anualmente?: boolean;
  generar_automaticamente_al_finalizar_examen?: boolean;
};

export type PlantillaDocumentoUpdate = Partial<
  Omit<PlantillaDocumentoCreate, "institucion_id" | "tipo_documento_id">
>;

// POST /documentos/plantillas/{id}/clonar — copia estructura (secciones,
// orden, tipo, config) de una plantilla (predeterminada global o propia de
// la institución del caller) a institucion_destino_id. activar=false por
// defecto (nunca reemplaza en silencio la plantilla activa del destino).
export type PlantillaDocumentoClonarRequest = {
  institucion_destino_id: number;
  nombre?: string;
  activar?: boolean;
};

export type PlantillaSeccion = {
  id: number;
  plantilla_documento_id: number;
  orden: number;
  tipo_seccion: TipoSeccionDocumento;
  titulo: string | null;
  // Shape libre por tipo_seccion — ver docstring de PlantillaSeccion.config
  // en models.py para el detalle completo de cada uno.
  config: Record<string, unknown> | null;
  creado_en: string;
};

export type PlantillaSeccionCreate = {
  orden: number;
  tipo_seccion: TipoSeccionDocumento;
  titulo?: string | null;
  config?: Record<string, unknown> | null;
};

export type PlantillaSeccionUpdate = {
  orden?: number;
  titulo?: string | null;
  config?: Record<string, unknown> | null;
};

// GET /documentos/?institucion_id=&persona_id= — metadata, sin la lista de
// estudiantes (ver DocumentoInstitucionalDetalle para eso).
export type DocumentoInstitucional = {
  id: number;
  institucion_id: number;
  tipo_documento_id: number;
  plantilla_documento_id: number;
  alcance: string;
  nivel_visibilidad: string;
  titulo: string;
  version_actual: number | null; // null = borrador, nunca generó una versión
  creado_por_usuario_id: number;
  creado_en: string;
};

export type DocumentoInstitucionalEstudiante = {
  persona_id: number;
  incluido_via: string;
  nombre_completo_historico: string | null;
  seccion_id_historico: number | null;
  grado_seccion_historico: string | null;
};

// GET /documentos/{id} — incluye la lista congelada de estudiantes.
export type DocumentoInstitucionalDetalle = DocumentoInstitucional & {
  estudiantes: DocumentoInstitucionalEstudiante[];
};

// POST /documentos/ — 'personas_ids' admite uno o varios ids (un alumno o
// varios, ej. un reporte de incidente con estudiante afectado +
// involucrado(s)); 'estructura' es el atajo por salón/grado/nivel completo
// — se puede combinar con 'personas_ids' en la misma creación.
export type DocumentoInstitucionalCreate = {
  tipo_documento_id: number;
  plantilla_documento_id: number;
  alcance: "institucion" | "estructura_academica" | "personas_especificas" | "ninguno";
  nivel_visibilidad?: "confidencial_clinico" | "compartible_colegio";
  titulo: string;
  anio_escolar?: number | null;
  estructura?: { nivel_educativo_id?: number; grado_id?: number; seccion_id?: number }[];
  personas_ids?: number[];
};

// GET /documentos/{id}/secciones — el borrador editable de cada sección.
// `contenido` es JSON libre por tipo_seccion: { texto: string } para
// 'texto_libre' (admite **negrita** manual, ver pdf_generador.py), {
// valores: Record<etiqueta, string> } para 'grupo_campos', { filas:
// Record<columna_titulo, string>[] } para 'tabla_dinamica' en modo libre,
// { datos: [{etiqueta, valor}] } para 'grafico_barras' en modo manual (sin
// vínculo a una Inscripcion real — ver DocumentoInstitucionalResultadoPrueba
// más abajo), { storage_key, nombre_archivo, descripcion } para
// 'imagen_anexo' (lo escribe el backend al subir, nunca a mano),
// { diagnostico_presuntivo, hijos, examinadora, fecha_elaboracion,
// periodo_propuesto } para 'datos_filiacion' (los 5 únicos campos
// "profesionales" de esa sección — todo lo demás sale automático de la
// ficha del alumno, nunca se edita desde aquí), { inscripcion_ids: number[]
// } para 'resultados_prueba_multiple' — SE LEE de aquí (este GET), pero se
// ESCRIBE solo con ResultadosPruebaMultipleRequest vía su propio endpoint
// dedicado, nunca con el PUT genérico de contenido de sección (cada id
// referencia una Inscripcion real, necesita la misma re-validación que
// resultados_prueba) — las demás (datos_familiares/resultados_prueba/
// encabezado/firma/firma_doble/firma_triple) son automáticas y no se
// editan desde aquí.
export type DocumentoInstitucionalSeccionContenido = {
  plantilla_seccion_id: number;
  tipo_seccion: TipoSeccionDocumento;
  titulo: string | null;
  orden: number;
  contenido: Record<string, unknown> | null;
  editado_por_usuario_id: number | null;
  actualizado_en: string | null;
};

// PUT /documentos/{id}/secciones/{plantilla_seccion_id} — reemplazo
// completo del contenido de esa sección, nunca un merge.
export type DocumentoInstitucionalSeccionContenidoUpdate = {
  contenido: Record<string, unknown> | null;
};

// GET /documentos/{id}/versiones — solo metadata (el PDF se descarga por
// separado, ver apiClient.descargarArchivo).
export type DocumentoInstitucionalVersion = {
  id: number;
  documento_institucional_id: number;
  numero_version: number;
  nombre_archivo: string;
  mime_type: string;
  tamano_bytes: number;
  checksum_sha256: string;
  generado_en: string;
  generado_por_usuario_id: number;
  motivo_version: string | null;
};

// POST /documentos/{id}/reemitir — solo para v2+; v1 (POST .../generar-version)
// no toma body.
export type ReemitirDocumentoRequest = {
  motivo: string;
};

// PUT/DELETE /documentos/{id}/secciones/{plantilla_seccion_id}/resultados-prueba
// — vincula una sección 'resultados_prueba' O 'grafico_barras' a una
// Inscripcion real (mismo mecanismo para ambos tipos, ver
// crud.vincular_resultado_prueba en el backend).
export type DocumentoInstitucionalResultadoPruebaCreate = {
  persona_id: number;
  inscripcion_id: number;
};

export type DocumentoInstitucionalResultadoPrueba = {
  id: number;
  documento_institucional_id: number;
  plantilla_seccion_id: number;
  persona_id: number;
  inscripcion_id: number;
};

// PUT /documentos/{id}/secciones/{plantilla_seccion_id}/resultados-prueba-multiple
// — a diferencia de DocumentoInstitucionalResultadoPruebaCreate (un solo
// inscripcion_id, su propia tabla), consolida una lista VARIABLE de
// aplicaciones reales en UNA sección 'resultados_prueba_multiple'.
// Reemplazo total: lista vacía = desvincular todas. Ver
// crud.vincular_resultados_prueba_multiple en el backend.
export type ResultadosPruebaMultipleRequest = {
  persona_id: number;
  inscripcion_ids: number[];
};

// GET /educativo/personas/{persona_id}/informes — historial de aplicaciones
// psicométricas reales de un alumno, usado para vincular una sección
// 'resultados_prueba'/'grafico_barras' a una Inscripcion concreta.
export type HistorialInformePersona = {
  informe_id: number;
  inscripcion_id: number;
  prueba_nombre_publico: string;
  nombre_grupo: string;
  fecha_aplicacion: string | null;
  version_actual: number;
  es_alerta: boolean;
  estado_interpretacion: string;
  informe_liberado: boolean;
};

// GET /educativo/inscripciones/{id}/informe — metadata + contenido
// profesional CRUDO (sin resolver contra lo configurado por la prueba) de
// una aplicación puntual, para precargar el panel de revisión.
export type VersionInforme = {
  numero_version: number;
  generado_en: string;
  generado_por_usuario_id: number | null;
  motivo_version: string | null;
  origen: string;
  tamano_bytes: number;
  checksum_sha256: string;
  mime_type: string;
  // Riesgo operacional (docs/gaps-pendientes.md): esta versión reemplaza a
  // una anterior (numero_version - 1) que ya estaba liberada y visible
  // para el alumno antes de esta corrección.
  retracta_version_previa_liberada: boolean;
};

export type DetalleInforme = {
  existe: boolean;
  informe_id?: number;
  version_actual?: number;
  resultado_visible_alumno: boolean;
  informe_liberado: boolean;
  estado_interpretacion: string;
  motivo_consulta?: string | null;
  observacion_conductual?: string | null;
  tecnicas_override?: string | null;
  conclusion_override?: string | null;
  recomendaciones_override?: string | null;
  firma_cargo_override?: string | null;
  firma_nombre_override?: string | null;
  firma_dni_override?: string | null;
  interpretacion_clinica?: string | null;
  versiones?: VersionInforme[];
};

export type RevisionInformeRequest = {
  interpretacion_clinica?: string | null;
  resultado_visible_alumno?: boolean | null;
  informe_liberado?: boolean | null;
  motivo_consulta?: string | null;
  observacion_conductual?: string | null;
  tecnicas_override?: string | null;
  conclusion_override?: string | null;
  recomendaciones_override?: string | null;
  firma_cargo_override?: string | null;
  firma_nombre_override?: string | null;
  firma_dni_override?: string | null;
};
