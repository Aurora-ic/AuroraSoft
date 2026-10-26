"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Campo } from "@/components/ui/Campo";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { ContenidoVisorArchivo, VisorArchivoModal, type ArchivoParaVisor } from "@/components/ui/VisorArchivo";
import { Migas } from "@/components/ui/Migas";
import type {
  Persona,
  PersonaUpdate,
  RegistroCambioPersona,
  ContactoFamiliar,
  ContactoFamiliarCreate,
  ContactoFamiliarUpdate,
  PersonaDatosFamiliares,
  PersonaDatosFamiliaresUpdate,
  PersonaAntecedentesClinicos,
  PersonaAntecedentesClinicosUpdate,
  TipoEntradaExpediente,
  EntradaExpediente,
  EntradaExpedienteDetalle,
  EntradaExpedienteVersion,
  EntradaExpedienteCreate,
  EntradaExpedienteVersionCreate,
  AutorizacionAccesoColegio,
  AutorizacionAccesoColegioCreate,
  TipoConsentimiento,
  TipoOtorgante,
  ConsentimientoInformado,
  ConsentimientoCreate,
  ConsentimientoAsentimientoCreate,
  ConsentimientosCombinados,
  SeccionActual,
  NivelEducativo,
  Grado,
  Seccion,
  MatriculaCreate,
  MatriculaResponse,
  DocumentoInstitucional,
  HistorialInformePersona,
  DetalleInforme,
  RevisionInformeRequest,
  Cita,
  SesionSeguimiento,
  RespuestaPaginada,
} from "@/types/api";

// Debe coincidir con crud.TIPOS_ENTRADA_CON_CONTENIDO_PROPIO del backend:
// los otros 2 tipos son puente (enlazan a SesionSeguimiento/Informe, sin
// contenido ni versión propios).
const TIPOS_ENTRADA_NARRATIVOS: TipoEntradaExpediente[] = [
  "observacion_conducta",
  "contacto_apoderado",
  "derivacion",
];

const ETIQUETAS_TIPO_ENTRADA: Record<TipoEntradaExpediente, string> = {
  observacion_conducta: "Observación de conducta",
  contacto_apoderado: "Contacto con apoderado",
  derivacion: "Derivación",
  sesion: "Sesión de seguimiento",
  aplicacion_prueba: "Aplicación de prueba",
  evidencia: "Evidencia",
};

function esTipoEntradaNarrativo(tipo: TipoEntradaExpediente): boolean {
  return TIPOS_ENTRADA_NARRATIVOS.includes(tipo);
}

// Nota fija sobre el alcance de la lista — el backend ya filtra
// GET /{persona_id}/expediente por la regla de acceso (autor, superadmin, o
// "colegio" con autorización vigente), así que nunca aparece aquí una
// entrada que este usuario no pueda abrir. No existe un estado intermedio
// de "acceso denegado" que mostrar: lo que no se puede ver, simplemente no
// llega en la lista.
function notaAccesoExpediente(rol?: string | null): string {
  switch (rol) {
    case "superadmin":
      return "Como superadmin ves todas las entradas del expediente de este estudiante.";
    case "psicologo":
      return "Se muestran solo las entradas del expediente que registraste tú — el contenido clínico es confidencial por autor, las que registró otro profesional no aparecen aquí.";
    case "colegio":
      return "Estas entradas solo son visibles mientras exista una autorización de acceso vigente para el colegio sobre este estudiante.";
    default:
      return "El contenido del expediente clínico es confidencial: solo lo ve quien lo registró, o superadmin.";
  }
}

// 🔒 Los tipos `Cita`/`SesionSeguimiento` vivían declarados a mano aquí,
// desincronizados del contrato real del backend (`Cita.fecha_hora`, no
// `Cita.fecha` — la columna real es `CitaProgramada.fecha_hora`, ver
// modulos/superadmin/models.py). Esa interfaz local hacía que la fecha de
// cada cita se mostrara como "Invalid Date" más abajo. Ahora se reusan los
// tipos ya correctos de types/api.ts (los mismos que usa app/(educativo)/
// agenda/page.tsx).

// Clases del badge de estado de una cita — nunca ámbar (reservado para
// alertas de riesgo clínico real, ver docs/frontend.md).
function claseEstadoCita(estado: Cita["estado"]): string {
  if (estado === "Cancelada") return "bg-ink/10 text-ink/50";
  if (estado === "Realizada") return "bg-teal-400/20 text-teal-900";
  return "bg-teal-400/20 text-teal-900"; // "Programada"
}

// 🔧 Las 3 actualizaciones optimistas de consentimiento hacían
// `actual && {...actual, ...}` — si la carga inicial (GET .../consentimientos)
// había fallado, `consentimientos` quedaba en `null` y ese `&&` hacía que la
// actualización se perdiera en silencio: el POST real sí se guardaba en el
// backend, pero esta función de estado devolvía `null` de nuevo y la UI
// seguía mostrando "Sin consentimiento vigente" como si nada hubiera
// pasado. Esta base por defecto deja que la actualización optimista
// "pegue" incluso cuando la carga inicial nunca llegó a completarse.
function consentimientosOVacio(actual: ConsentimientosCombinados | null, personaId: string): ConsentimientosCombinados {
  return (
    actual ?? {
      persona_id: Number(personaId),
      apoderado: { tiene_consentimiento_vigente: false, historial: [] },
      asentimiento: { tiene_consentimiento_vigente: false, historial: [] },
    }
  );
}

function formatearFecha(fecha?: string | null): string | null {
  if (!fecha) return null;
  return new Date(`${fecha}T00:00:00`).toLocaleDateString();
}

// null = "no preguntado todavía" — nunca se muestra como "No" (eso sería
// afirmar algo que no se sabe). Mismo criterio que el backend, que guarda
// estos campos como Optional[bool] en vez de default False.
function formatearBooleanoTriple(valor?: boolean | null): string | null {
  if (valor === null || valor === undefined) return null;
  return valor ? "Sí" : "No";
}

// Para el <select> de edición: el valor del control es siempre string
// ("" | "true" | "false"), nunca un boolean — se convierte recién al armar
// el payload del PATCH.
function boolATextoSelect(valor: boolean | null | undefined): string {
  if (valor === null || valor === undefined) return "";
  return valor ? "true" : "false";
}

function textoSelectABool(valor: string): boolean | null {
  if (valor === "true") return true;
  if (valor === "false") return false;
  return null;
}

// Misma forma que la fila de "sección" que ya usa el padrón (SeccionActual) —
// aquí también describe cada entrada de GET /{persona_id}/historial-academico.
function formatearSeccion(seccion: SeccionActual): { linea: string; detalle: string | null } {
  const partes = [seccion.nivel_educativo, seccion.grado, seccion.seccion].filter(Boolean);
  const anio = seccion.anio_escolar ? `Año ${seccion.anio_escolar}` : null;
  const turno = seccion.turno ? `Turno ${seccion.turno}` : null;
  return {
    linea: partes.length ? partes.join(" · ") : "Sección sin nombre",
    detalle: [anio, turno].filter(Boolean).join(" · ") || null,
  };
}

export default function FichaAlumnoPage() {
  const params = useParams();
  const router = useRouter();
  const { sesion, cargando: cargandoSesion } = useAuth();
  const personaId = params.personaId as string;

  const [alumno, setAlumno] = useState<Persona | null>(null);
  const [citas, setCitas] = useState<Cita[]>([]);
  const [seguimientos, setSeguimientos] = useState<SesionSeguimiento[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [errorCitas, setErrorCitas] = useState<string | null>(null);
  const [cancelandoCitaId, setCancelandoCitaId] = useState<number | null>(null);
  const [reprogramandoCitaId, setReprogramandoCitaId] = useState<number | null>(null);
  const [formReprogramar, setFormReprogramar] = useState({ fecha: "", hora: "" });
  const [guardandoReprogramacion, setGuardandoReprogramacion] = useState(false);

  const [errorSesiones, setErrorSesiones] = useState<string | null>(null);
  const [editandoSesionId, setEditandoSesionId] = useState<number | null>(null);
  const [formSesion, setFormSesion] = useState({
    observaciones: "",
    accion_tomada: "",
    acuerdos_compromisos: "",
    proxima_cita_fecha: "",
    proxima_cita_hora: "",
    estado: "Atendido",
  });
  const [guardandoSesion, setGuardandoSesion] = useState(false);

  const [editando, setEditando] = useState(false);
  const [form, setForm] = useState({ nombres: "", apellidos: "", documento_identidad: "", fecha_nacimiento: "", genero: "" });
  const [guardando, setGuardando] = useState(false);
  const [errorEdicion, setErrorEdicion] = useState<string | null>(null);

  const [mostrarHistorial, setMostrarHistorial] = useState(false);
  const [historial, setHistorial] = useState<RegistroCambioPersona[] | null>(null);
  const [cargandoHistorial, setCargandoHistorial] = useState(false);
  const [errorHistorial, setErrorHistorial] = useState<string | null>(null);

  const [historialAcademico, setHistorialAcademico] = useState<SeccionActual[]>([]);
  const [errorMatricula, setErrorMatricula] = useState<string | null>(null);
  const [mostrarHistorialAcademico, setMostrarHistorialAcademico] = useState(false);

  // --- Pruebas aplicadas / instrumentos — historial de informes del alumno
  // (GET /educativo/personas/{id}/informes), con un panel de revisión por
  // fila que reutiliza PATCH .../revision-informe y POST .../informe/reemitir. ---
  const [pruebasAplicadas, setPruebasAplicadas] = useState<HistorialInformePersona[] | null>(null);
  const [errorPruebas, setErrorPruebas] = useState<string | null>(null);
  const [inscripcionExpandida, setInscripcionExpandida] = useState<number | null>(null);
  const [detalleInforme, setDetalleInforme] = useState<DetalleInforme | null>(null);
  const [cargandoDetalleInforme, setCargandoDetalleInforme] = useState(false);
  const [formRevision, setFormRevision] = useState<RevisionInformeRequest>({});
  const [guardandoRevision, setGuardandoRevision] = useState(false);
  const [errorRevision, setErrorRevision] = useState<string | null>(null);
  const [motivoReemision, setMotivoReemision] = useState("");
  const [reemitiendo, setReemitiendo] = useState(false);
  const [errorReemitir, setErrorReemitir] = useState<string | null>(null);
  const [descargandoInformeId, setDescargandoInformeId] = useState<number | null>(null);
  // 🆕 Vista previa del PDF embebida junto al formulario de revisión, para no
  // tener que descargar el archivo cada vez que se quiere ver el resultado
  // de una edición/reemisión. Un solo archivo vivo a la vez (el panel de
  // revisión también muestra una sola inscripción expandida a la vez).
  // 🆕 Renderizado con <ContenidoVisorArchivo> (react-pdf) en vez del
  // <iframe> nativo de antes — el visor nativo del navegador fuerza la
  // descarga en vez de mostrar inline en varios móviles (Chrome Android,
  // Safari iOS), ver components/ui/VisorArchivo.tsx.
  const [pdfPreviewArchivo, setPdfPreviewArchivo] = useState<ArchivoParaVisor | null>(null);
  const [cargandoPreviewPdf, setCargandoPreviewPdf] = useState(false);
  const [errorPreviewPdf, setErrorPreviewPdf] = useState<string | null>(null);

  // 🆕 Modal "Ver" rápido desde una lista (pruebas aplicadas, documentos
  // institucionales, evidencia del expediente) — independiente del panel de
  // revisión de arriba, que muestra el PDF embebido al lado del formulario.
  const [visorModalAbierto, setVisorModalAbierto] = useState(false);
  const [visorModalArchivo, setVisorModalArchivo] = useState<ArchivoParaVisor | null>(null);
  const [visorModalCargando, setVisorModalCargando] = useState(false);
  const [visorModalError, setVisorModalError] = useState<string | null>(null);
  const [visorModalTitulo, setVisorModalTitulo] = useState<string | undefined>(undefined);

  const [editandoMatricula, setEditandoMatricula] = useState(false);
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [grados, setGrados] = useState<Grado[]>([]);
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [nivelSeleccionado, setNivelSeleccionado] = useState("");
  const [gradoSeleccionado, setGradoSeleccionado] = useState("");
  const [seccionSeleccionada, setSeccionSeleccionada] = useState("");
  const [cargandoNiveles, setCargandoNiveles] = useState(false);
  const [cargandoGrados, setCargandoGrados] = useState(false);
  const [cargandoSecciones, setCargandoSecciones] = useState(false);
  const [guardandoMatricula, setGuardandoMatricula] = useState(false);
  const [errorFormularioMatricula, setErrorFormularioMatricula] = useState<string | null>(null);

  // --- Datos de filiación: familiares (1:1 con Persona) ---
  const [datosFamiliares, setDatosFamiliares] = useState<PersonaDatosFamiliares | null>(null);
  const [errorDatosFamiliares, setErrorDatosFamiliares] = useState<string | null>(null);
  const [editandoDatosFamiliares, setEditandoDatosFamiliares] = useState(false);
  const [formDatosFamiliares, setFormDatosFamiliares] = useState({
    numero_hermanos: "",
    vive_con: "",
    lugar_nacimiento: "",
    lugar_procedencia: "",
  });
  const [guardandoDatosFamiliares, setGuardandoDatosFamiliares] = useState(false);
  const [errorFormularioDatosFamiliares, setErrorFormularioDatosFamiliares] = useState<string | null>(null);

  // --- Datos de filiación: antecedentes clínicos externos (1:1 con Persona) ---
  const [antecedentesClinicos, setAntecedentesClinicos] = useState<PersonaAntecedentesClinicos | null>(null);
  const [errorAntecedentesClinicos, setErrorAntecedentesClinicos] = useState<string | null>(null);
  const [editandoAntecedentesClinicos, setEditandoAntecedentesClinicos] = useState(false);
  const [formAntecedentesClinicos, setFormAntecedentesClinicos] = useState({
    recibe_terapia_psicologica_externa: "",
    detalle_terapia_psicologica_externa: "",
    recibe_atencion_psiquiatrica_externa: "",
    detalle_atencion_psiquiatrica_externa: "",
    diagnostico_reportado: "",
  });
  const [guardandoAntecedentesClinicos, setGuardandoAntecedentesClinicos] = useState(false);
  const [errorFormularioAntecedentesClinicos, setErrorFormularioAntecedentesClinicos] = useState<string | null>(null);

  const [contactos, setContactos] = useState<ContactoFamiliar[]>([]);
  const [errorContactos, setErrorContactos] = useState<string | null>(null);
  // null = panel cerrado; id === null = creando uno nuevo; id !== null = editando ese contacto.
  const [formularioContacto, setFormularioContacto] = useState<{
    id: number | null;
    nombre: string;
    telefono: string;
    relacion: string;
    email: string;
  } | null>(null);
  const [guardandoContacto, setGuardandoContacto] = useState(false);
  const [errorFormularioContacto, setErrorFormularioContacto] = useState<string | null>(null);
  const [desactivandoContactoId, setDesactivandoContactoId] = useState<number | null>(null);

  const [entradas, setEntradas] = useState<EntradaExpediente[]>([]);
  const [errorEntradas, setErrorEntradas] = useState<string | null>(null);
  const [entradaExpandidaId, setEntradaExpandidaId] = useState<number | null>(null);
  const [detalleEntrada, setDetalleEntrada] = useState<EntradaExpedienteDetalle | null>(null);
  const [versionSeleccionada, setVersionSeleccionada] = useState<number | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [errorDetalle, setErrorDetalle] = useState<string | null>(null);

  const [formEntrada, setFormEntrada] = useState<{
    tipo_entrada: TipoEntradaExpediente;
    fecha_entrada: string;
    motivo: string;
    contenido: string;
    interpretacion: string;
    diagnostico_presuntivo: string;
    contacto_familiar_id: string;
  } | null>(null);
  const [guardandoEntrada, setGuardandoEntrada] = useState(false);
  const [errorFormularioEntrada, setErrorFormularioEntrada] = useState<string | null>(null);

  // 🆕 Formulario de evidencia (archivo escaneado) — multipart, nunca pasa
  // por formEntrada/crearEntrada (esos solo manejan los 3 tipos narrativos
  // en JSON). archivo=null hasta que el usuario elige un File real.
  const [formEvidencia, setFormEvidencia] = useState<{
    archivo: File | null;
    titulo: string;
    descripcion: string;
    fecha_entrada: string;
    informe_id: string;
    incluir_en_pdf_informe: boolean;
  } | null>(null);
  const [subiendoEvidencia, setSubiendoEvidencia] = useState(false);
  const [errorFormularioEvidencia, setErrorFormularioEvidencia] = useState<string | null>(null);
  const [actualizandoIncluirPdfId, setActualizandoIncluirPdfId] = useState<number | null>(null);
  const [descargandoEvidenciaExpedienteId, setDescargandoEvidenciaExpedienteId] = useState<number | null>(null);

  const [mostrarFormularioVersion, setMostrarFormularioVersion] = useState(false);
  const [formVersion, setFormVersion] = useState({
    motivo: "",
    contenido: "",
    interpretacion: "",
    diagnostico_presuntivo: "",
    motivo_version: "",
  });
  const [guardandoVersion, setGuardandoVersion] = useState(false);
  const [errorFormularioVersion, setErrorFormularioVersion] = useState<string | null>(null);

  const [autorizacionVigente, setAutorizacionVigente] = useState<AutorizacionAccesoColegio | null>(null);
  const [errorAutorizacion, setErrorAutorizacion] = useState<string | null>(null);
  const [formularioAutorizacion, setFormularioAutorizacion] = useState<{ motivo: string } | null>(null);
  const [guardandoAutorizacion, setGuardandoAutorizacion] = useState(false);
  const [errorFormularioAutorizacion, setErrorFormularioAutorizacion] = useState<string | null>(null);
  const [revocandoAutorizacion, setRevocandoAutorizacion] = useState(false);

  // --- Consentimiento informado: apoderado (siempre obligatorio) y
  // asentimiento del propio estudiante (solo si la institución lo exige) —
  // ver ConsentimientosCombinados en types/api.ts. ---
  const [consentimientos, setConsentimientos] = useState<ConsentimientosCombinados | null>(null);
  const [errorConsentimientos, setErrorConsentimientos] = useState<string | null>(null);
  const [formularioConsentimiento, setFormularioConsentimiento] = useState<{
    tipo: TipoConsentimiento;
    otorgado_por_nombre: string;
    otorgante_apellidos: string;
    otorgante_documento: string;
    otorgante_relacion: string;
    tipo_otorgante: TipoOtorgante;
    referencia_documento: string;
  } | null>(null);
  const [guardandoConsentimiento, setGuardandoConsentimiento] = useState(false);
  const [errorFormularioConsentimiento, setErrorFormularioConsentimiento] = useState<string | null>(null);
  const [revocandoConsentimientoId, setRevocandoConsentimientoId] = useState<number | null>(null);
  const [subiendoEvidenciaId, setSubiendoEvidenciaId] = useState<number | null>(null);
  const [descargandoEvidenciaId, setDescargandoEvidenciaId] = useState<number | null>(null);
  const [mostrarHistorialConsentimiento, setMostrarHistorialConsentimiento] = useState<
    Record<TipoConsentimiento, boolean>
  >({ apoderado: false, asentimiento: false });

  // --- Documentos institucionales: listado simple con link a /documentos/[id]
  // (el armado de plantillas y la edición de contenido viven en esa pantalla
  // del sidebar, no acá — ver docs/motor-documentos.md). ---
  const [documentos, setDocumentos] = useState<DocumentoInstitucional[]>([]);
  const [errorDocumentos, setErrorDocumentos] = useState<string | null>(null);

  useEffect(() => {
    if (!personaId || cargandoSesion) return;

    const fetchData = async () => {
      try {
        setLoading(true);
        // Solo psicólogo/superadmin pueden otorgar/revocar/ver esta excepción
        // en esta ficha (ver plan de FASE A) — para otro rol ni se consulta.
        const puedeGestionarAutorizacion = sesion?.rol === "psicologo" || sesion?.rol === "superadmin";
        // Peticiones paralelas para el alumno, sus citas y su historial de seguimiento
        const [
          datosAlumno,
          resCitas,
          resSeguimiento,
          resHistorialAcademico,
          resDatosFamiliares,
          resAntecedentesClinicos,
          resContactos,
          resEntradas,
          resAutorizaciones,
          resConsentimientos,
        ] = await Promise.all([
          apiClient.get<Persona>(`/admin/personas/${personaId}/detalle`),
          apiClient.get<Cita[]>(`/admin/personas/${personaId}/citas`).catch(() => []),
          apiClient.get<SesionSeguimiento[]>(`/educativo/seguimiento/${personaId}`).catch(() => []),
          apiClient.get<SeccionActual[]>(`/admin/personas/${personaId}/historial-academico`).catch((err) => {
            setErrorMatricula(err.message || "No se pudo cargar la matrícula académica.");
            return [] as SeccionActual[];
          }),
          apiClient
            .get<PersonaDatosFamiliares>(`/admin/personas/${personaId}/datos-familiares`)
            .catch((err) => {
              setErrorDatosFamiliares(err.message || "No se pudieron cargar los datos familiares.");
              return null;
            }),
          apiClient
            .get<PersonaAntecedentesClinicos>(`/admin/personas/${personaId}/antecedentes-clinicos`)
            .catch((err) => {
              setErrorAntecedentesClinicos(err.message || "No se pudieron cargar los antecedentes clínicos.");
              return null;
            }),
          apiClient
            .get<ContactoFamiliar[]>(`/admin/personas/${personaId}/contactos?incluir_inactivos=true`)
            .catch((err) => {
              setErrorContactos(err.message || "No se pudieron cargar los contactos familiares.");
              return [] as ContactoFamiliar[];
            }),
          apiClient.get<EntradaExpediente[]>(`/admin/personas/${personaId}/expediente`).catch((err) => {
            setErrorEntradas(err.message || "No se pudo cargar el expediente clínico.");
            return [] as EntradaExpediente[];
          }),
          puedeGestionarAutorizacion
            ? apiClient
                .get<AutorizacionAccesoColegio[]>(`/admin/personas/${personaId}/autorizacion-colegio`)
                .catch((err) => {
                  setErrorAutorizacion(err.message || "No se pudo cargar la autorización de acceso del colegio.");
                  return [] as AutorizacionAccesoColegio[];
                })
            : Promise.resolve([] as AutorizacionAccesoColegio[]),
          apiClient
            .get<ConsentimientosCombinados>(`/admin/personas/${personaId}/consentimientos`)
            .catch((err) => {
              setErrorConsentimientos(err.message || "No se pudieron cargar los consentimientos.");
              return null;
            }),
        ]);

        setAlumno(datosAlumno);
        setCitas(resCitas);
        setSeguimientos(resSeguimiento);
        setHistorialAcademico(resHistorialAcademico);
        setDatosFamiliares(resDatosFamiliares);
        setAntecedentesClinicos(resAntecedentesClinicos);
        setContactos(resContactos);
        setEntradas(resEntradas);
        setAutorizacionVigente(resAutorizaciones.find((a) => a.vigente) ?? null);
        setConsentimientos(resConsentimientos);

        // Documentos institucionales: la institución se toma del propio
        // alumno (datosAlumno.institucion_id), no de la sesión — así
        // funciona igual para superadmin (que no tiene institucion_id
        // propio) como para admin/psicólogo/colegio de esa institución.
        await apiClient
          .get<RespuestaPaginada<DocumentoInstitucional>>(
            `/documentos/?institucion_id=${datosAlumno.institucion_id}&persona_id=${personaId}`,
          )
          .then((res) => setDocumentos(res.items))
          .catch((err) => setErrorDocumentos(err.message || "No se pudieron cargar los documentos institucionales."));
      } catch (err: any) {
        setError(err.message || "Error al cargar la información del alumno.");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [personaId, cargandoSesion, sesion]);

  // --- Pruebas aplicadas: historial propio, separado del Promise.all de
  // arriba — así un fallo aquí nunca bloquea el resto de la ficha. ---
  useEffect(() => {
    if (!personaId || cargandoSesion) return;
    apiClient
      .get<HistorialInformePersona[]>(`/educativo/personas/${personaId}/informes`)
      .then(setPruebasAplicadas)
      .catch((err) => setErrorPruebas(err.message || "No se pudo cargar el historial de pruebas aplicadas."));
  }, [personaId, cargandoSesion]);

  async function recargarPruebasAplicadas() {
    try {
      const lista = await apiClient.get<HistorialInformePersona[]>(`/educativo/personas/${personaId}/informes`);
      setPruebasAplicadas(lista);
    } catch {
      // El panel ya muestra su propio error si hace falta; no bloqueamos la UI por esto.
    }
  }

  function cerrarPreviewPdf() {
    setPdfPreviewArchivo(null);
    setErrorPreviewPdf(null);
  }

  async function cargarPreviewPdf(inscripcionId: number) {
    setCargandoPreviewPdf(true);
    setErrorPreviewPdf(null);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/inscripciones/${inscripcionId}/informe-pdf`);
      setPdfPreviewArchivo({ blob, contentType: "application/pdf", nombreArchivo: `informe_${inscripcionId}.pdf` });
    } catch (err: any) {
      setErrorPreviewPdf(err.message || "No se pudo cargar la vista previa del informe.");
    } finally {
      setCargandoPreviewPdf(false);
    }
  }

  function cerrarVisorModal() {
    setVisorModalAbierto(false);
    setVisorModalArchivo(null);
    setVisorModalError(null);
  }

  async function verInformeDesdeFicha(inscripcionId: number) {
    setVisorModalAbierto(true);
    setVisorModalArchivo(null);
    setVisorModalError(null);
    setVisorModalTitulo("Informe");
    setVisorModalCargando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/inscripciones/${inscripcionId}/informe-pdf`);
      setVisorModalArchivo({ blob, contentType: "application/pdf", nombreArchivo: `informe_${inscripcionId}.pdf` });
    } catch (err: any) {
      setVisorModalError(err.message || "No se pudo cargar el informe.");
    } finally {
      setVisorModalCargando(false);
    }
  }

  async function verEvidenciaExpediente(entrada: EntradaExpediente) {
    setVisorModalAbierto(true);
    setVisorModalArchivo(null);
    setVisorModalError(null);
    setVisorModalTitulo(entrada.titulo || "Evidencia");
    setVisorModalCargando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/admin/personas/expediente/evidencia/${entrada.id}/archivo`);
      setVisorModalArchivo({
        blob,
        contentType: entrada.content_type,
        nombreArchivo: entrada.nombre_archivo_original || `evidencia-${entrada.id}`,
      });
    } catch (err: any) {
      setVisorModalError(err.message || "No se pudo cargar la evidencia.");
    } finally {
      setVisorModalCargando(false);
    }
  }

  async function alternarRevision(inscripcionId: number) {
    if (inscripcionExpandida === inscripcionId) {
      setInscripcionExpandida(null);
      cerrarPreviewPdf();
      return;
    }
    setInscripcionExpandida(inscripcionId);
    setDetalleInforme(null);
    setErrorRevision(null);
    setErrorReemitir(null);
    setMotivoReemision("");
    setCargandoDetalleInforme(true);
    cerrarPreviewPdf();
    try {
      const detalle = await apiClient.get<DetalleInforme>(`/educativo/inscripciones/${inscripcionId}/informe`);
      setDetalleInforme(detalle);
      setFormRevision({
        motivo_consulta: detalle.motivo_consulta ?? "",
        observacion_conductual: detalle.observacion_conductual ?? "",
        tecnicas_override: detalle.tecnicas_override ?? "",
        conclusion_override: detalle.conclusion_override ?? "",
        recomendaciones_override: detalle.recomendaciones_override ?? "",
        firma_cargo_override: detalle.firma_cargo_override ?? "",
        firma_nombre_override: detalle.firma_nombre_override ?? "",
        firma_dni_override: detalle.firma_dni_override ?? "",
        interpretacion_clinica: detalle.interpretacion_clinica ?? "",
        resultado_visible_alumno: detalle.resultado_visible_alumno,
        informe_liberado: detalle.informe_liberado,
      });
      if (detalle.existe) {
        await cargarPreviewPdf(inscripcionId);
      }
    } catch (err: any) {
      setErrorRevision(err.message || "No se pudo cargar el detalle del informe.");
    } finally {
      setCargandoDetalleInforme(false);
    }
  }

  async function guardarRevision(inscripcionId: number) {
    setGuardandoRevision(true);
    setErrorRevision(null);
    try {
      await apiClient.patch(`/educativo/inscripciones/${inscripcionId}/revision-informe`, formRevision);
      const detalle = await apiClient.get<DetalleInforme>(`/educativo/inscripciones/${inscripcionId}/informe`);
      setDetalleInforme(detalle);
      await recargarPruebasAplicadas();
    } catch (err: any) {
      setErrorRevision(err.message || "No se pudo guardar la revisión.");
    } finally {
      setGuardandoRevision(false);
    }
  }

  async function reemitirInformeDesdeFicha(inscripcionId: number) {
    if (!motivoReemision.trim()) {
      setErrorReemitir("Indica el motivo de la reemisión.");
      return;
    }
    setReemitiendo(true);
    setErrorReemitir(null);
    try {
      await apiClient.post(`/educativo/inscripciones/${inscripcionId}/informe/reemitir`, {
        motivo: motivoReemision.trim(),
      });
      setMotivoReemision("");
      const detalle = await apiClient.get<DetalleInforme>(`/educativo/inscripciones/${inscripcionId}/informe`);
      setDetalleInforme(detalle);
      await recargarPruebasAplicadas();
      await cargarPreviewPdf(inscripcionId); // la reemisión SÍ cambia el PDF — refrescar la vista previa
    } catch (err: any) {
      setErrorReemitir(err.message || "No se pudo reemitir el informe.");
    } finally {
      setReemitiendo(false);
    }
  }

  async function descargarInformeDesdeFicha(inscripcionId: number) {
    setDescargandoInformeId(inscripcionId);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/inscripciones/${inscripcionId}/informe-pdf`);
      descargarBlob(blob, `informe_${inscripcionId}.pdf`);
    } catch (err: any) {
      setErrorPruebas(err.message || "No se pudo descargar el informe.");
    } finally {
      setDescargandoInformeId(null);
    }
  }

  function abrirEdicion() {
    if (!alumno) return;
    setForm({
      nombres: alumno.nombres,
      apellidos: alumno.apellidos,
      documento_identidad: alumno.documento_identidad ?? "",
      fecha_nacimiento: alumno.fecha_nacimiento ?? "",
      genero: alumno.genero ?? "",
    });
    setErrorEdicion(null);
    setEditando(true);
  }

  async function guardarEdicion(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true);
    setErrorEdicion(null);
    try {
      const payload: PersonaUpdate = {
        nombres: form.nombres,
        apellidos: form.apellidos,
        documento_identidad: form.documento_identidad || null,
        fecha_nacimiento: form.fecha_nacimiento || null,
        genero: form.genero || null,
      };
      const actualizado = await apiClient.patch<Persona>(`/admin/personas/${personaId}`, payload);
      setAlumno((prev) => (prev ? { ...prev, ...actualizado } : actualizado));
      setEditando(false);
    } catch (err: any) {
      setErrorEdicion(err.message || "No se pudo guardar los cambios.");
    } finally {
      setGuardando(false);
    }
  }

  async function alternarHistorial() {
    if (mostrarHistorial) {
      setMostrarHistorial(false);
      return;
    }
    setMostrarHistorial(true);
    if (historial !== null) return; // ya se cargó una vez, no repetir el fetch
    setCargandoHistorial(true);
    setErrorHistorial(null);
    try {
      const datos = await apiClient.get<RegistroCambioPersona[]>(`/admin/personas/${personaId}/historial-cambios`);
      setHistorial(datos);
    } catch (err: any) {
      setErrorHistorial(err.message || "No se pudo cargar el historial de cambios.");
    } finally {
      setCargandoHistorial(false);
    }
  }

  function abrirEdicionDatosFamiliares() {
    setFormDatosFamiliares({
      numero_hermanos: datosFamiliares?.numero_hermanos?.toString() ?? "",
      vive_con: datosFamiliares?.vive_con ?? "",
      lugar_nacimiento: datosFamiliares?.lugar_nacimiento ?? "",
      lugar_procedencia: datosFamiliares?.lugar_procedencia ?? "",
    });
    setErrorFormularioDatosFamiliares(null);
    setEditandoDatosFamiliares(true);
  }

  async function guardarDatosFamiliares(e: React.FormEvent) {
    e.preventDefault();
    setGuardandoDatosFamiliares(true);
    setErrorFormularioDatosFamiliares(null);
    try {
      const payload: PersonaDatosFamiliaresUpdate = {
        numero_hermanos: formDatosFamiliares.numero_hermanos === "" ? null : Number(formDatosFamiliares.numero_hermanos),
        vive_con: formDatosFamiliares.vive_con || null,
        lugar_nacimiento: formDatosFamiliares.lugar_nacimiento || null,
        lugar_procedencia: formDatosFamiliares.lugar_procedencia || null,
      };
      const actualizado = await apiClient.patch<PersonaDatosFamiliares>(
        `/admin/personas/${personaId}/datos-familiares`,
        payload,
      );
      setDatosFamiliares(actualizado);
      setEditandoDatosFamiliares(false);
    } catch (err: any) {
      setErrorFormularioDatosFamiliares(err.message || "No se pudieron guardar los datos familiares.");
    } finally {
      setGuardandoDatosFamiliares(false);
    }
  }

  function abrirEdicionAntecedentesClinicos() {
    setFormAntecedentesClinicos({
      recibe_terapia_psicologica_externa: boolATextoSelect(antecedentesClinicos?.recibe_terapia_psicologica_externa),
      detalle_terapia_psicologica_externa: antecedentesClinicos?.detalle_terapia_psicologica_externa ?? "",
      recibe_atencion_psiquiatrica_externa: boolATextoSelect(antecedentesClinicos?.recibe_atencion_psiquiatrica_externa),
      detalle_atencion_psiquiatrica_externa: antecedentesClinicos?.detalle_atencion_psiquiatrica_externa ?? "",
      diagnostico_reportado: antecedentesClinicos?.diagnostico_reportado ?? "",
    });
    setErrorFormularioAntecedentesClinicos(null);
    setEditandoAntecedentesClinicos(true);
  }

  async function guardarAntecedentesClinicos(e: React.FormEvent) {
    e.preventDefault();
    setGuardandoAntecedentesClinicos(true);
    setErrorFormularioAntecedentesClinicos(null);
    try {
      const payload: PersonaAntecedentesClinicosUpdate = {
        recibe_terapia_psicologica_externa: textoSelectABool(formAntecedentesClinicos.recibe_terapia_psicologica_externa),
        detalle_terapia_psicologica_externa: formAntecedentesClinicos.detalle_terapia_psicologica_externa || null,
        recibe_atencion_psiquiatrica_externa: textoSelectABool(formAntecedentesClinicos.recibe_atencion_psiquiatrica_externa),
        detalle_atencion_psiquiatrica_externa: formAntecedentesClinicos.detalle_atencion_psiquiatrica_externa || null,
        diagnostico_reportado: formAntecedentesClinicos.diagnostico_reportado || null,
      };
      const actualizado = await apiClient.patch<PersonaAntecedentesClinicos>(
        `/admin/personas/${personaId}/antecedentes-clinicos`,
        payload,
      );
      setAntecedentesClinicos(actualizado);
      setEditandoAntecedentesClinicos(false);
    } catch (err: any) {
      setErrorFormularioAntecedentesClinicos(err.message || "No se pudieron guardar los antecedentes clínicos.");
    } finally {
      setGuardandoAntecedentesClinicos(false);
    }
  }

  async function abrirEdicionMatricula() {
    setEditandoMatricula(true);
    setErrorFormularioMatricula(null);
    setNivelSeleccionado("");
    setGradoSeleccionado("");
    setSeccionSeleccionada("");
    setGrados([]);
    setSecciones([]);
    if (niveles.length > 0 || !alumno) return; // ya se cargaron una vez, no repetir el fetch
    setCargandoNiveles(true);
    try {
      const datos = await apiClient.get<NivelEducativo[]>(`/admin/personas/academico/niveles/${alumno.institucion_id}`);
      setNiveles(datos);
    } catch (err: any) {
      setErrorFormularioMatricula(err.message || "No se pudieron cargar los niveles educativos.");
    } finally {
      setCargandoNiveles(false);
    }
  }

  async function seleccionarNivel(nivelId: string) {
    setNivelSeleccionado(nivelId);
    setGradoSeleccionado("");
    setSeccionSeleccionada("");
    setGrados([]);
    setSecciones([]);
    if (!nivelId) return;
    setCargandoGrados(true);
    setErrorFormularioMatricula(null);
    try {
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelId}`);
      setGrados(datos);
    } catch (err: any) {
      setErrorFormularioMatricula(err.message || "No se pudieron cargar los grados.");
    } finally {
      setCargandoGrados(false);
    }
  }

  async function seleccionarGrado(gradoId: string) {
    setGradoSeleccionado(gradoId);
    setSeccionSeleccionada("");
    setSecciones([]);
    if (!gradoId) return;
    setCargandoSecciones(true);
    setErrorFormularioMatricula(null);
    try {
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoId}`);
      // Una sección existe por (grado, año) — se muestran todos los años
      // disponibles de ese grado, el más reciente primero.
      setSecciones([...datos].sort((a, b) => b.anio_escolar - a.anio_escolar || a.nombre.localeCompare(b.nombre)));
    } catch (err: any) {
      setErrorFormularioMatricula(err.message || "No se pudieron cargar las secciones.");
    } finally {
      setCargandoSecciones(false);
    }
  }

  async function guardarMatricula(e: React.FormEvent) {
    e.preventDefault();
    if (!seccionSeleccionada) return;
    setGuardandoMatricula(true);
    setErrorFormularioMatricula(null);
    try {
      const payload: MatriculaCreate = { seccion_id: Number(seccionSeleccionada) };
      await apiClient.post<MatriculaResponse>(`/admin/personas/${personaId}/matricula`, payload);
      // La matrícula vigente/historial se derivan del historial completo,
      // nunca de la respuesta del POST — se recarga desde la fuente.
      const datos = await apiClient.get<SeccionActual[]>(`/admin/personas/${personaId}/historial-academico`);
      setHistorialAcademico(datos);
      setEditandoMatricula(false);
    } catch (err: any) {
      setErrorFormularioMatricula(err.message || "No se pudo actualizar la matrícula.");
    } finally {
      setGuardandoMatricula(false);
    }
  }

  function abrirNuevoContacto() {
    setFormularioContacto({ id: null, nombre: "", telefono: "", relacion: "", email: "" });
    setErrorFormularioContacto(null);
  }

  function abrirEdicionContacto(contacto: ContactoFamiliar) {
    setFormularioContacto({
      id: contacto.id,
      nombre: contacto.nombre,
      telefono: contacto.telefono ?? "",
      relacion: contacto.relacion ?? "",
      email: contacto.email ?? "",
    });
    setErrorFormularioContacto(null);
  }

  async function guardarContacto(e: React.FormEvent) {
    e.preventDefault();
    if (!formularioContacto) return;
    setGuardandoContacto(true);
    setErrorFormularioContacto(null);
    try {
      if (formularioContacto.id === null) {
        const payload: ContactoFamiliarCreate = {
          nombre: formularioContacto.nombre,
          telefono: formularioContacto.telefono || null,
          relacion: formularioContacto.relacion || null,
          email: formularioContacto.email || null,
        };
        const nuevo = await apiClient.post<ContactoFamiliar>(`/admin/personas/${personaId}/contactos`, payload);
        setContactos((prev) => [...prev, nuevo]);
      } else {
        const payload: ContactoFamiliarUpdate = {
          nombre: formularioContacto.nombre,
          telefono: formularioContacto.telefono || null,
          relacion: formularioContacto.relacion || null,
          email: formularioContacto.email || null,
        };
        const actualizado = await apiClient.patch<ContactoFamiliar>(
          `/admin/personas/contactos/${formularioContacto.id}`,
          payload,
        );
        setContactos((prev) => prev.map((c) => (c.id === actualizado.id ? actualizado : c)));
      }
      setFormularioContacto(null);
    } catch (err: any) {
      setErrorFormularioContacto(err.message || "No se pudo guardar el contacto.");
    } finally {
      setGuardandoContacto(false);
    }
  }

  async function desactivarContacto(id: number) {
    if (!window.confirm("¿Desactivar este contacto familiar? No hay una acción para reactivarlo desde aquí.")) {
      return;
    }
    setDesactivandoContactoId(id);
    setErrorContactos(null);
    try {
      const actualizado = await apiClient.delete<ContactoFamiliar>(`/admin/personas/contactos/${id}`);
      setContactos((prev) => prev.map((c) => (c.id === actualizado.id ? actualizado : c)));
    } catch (err: any) {
      setErrorContactos(err.message || "No se pudo desactivar el contacto.");
    } finally {
      setDesactivandoContactoId(null);
    }
  }

  async function cancelarCita(id: number) {
    if (!window.confirm("¿Cancelar esta cita?")) return;
    setCancelandoCitaId(id);
    setErrorCitas(null);
    try {
      await apiClient.delete(`/admin/personas/citas/${id}`);
      // El DELETE del backend solo confirma con un mensaje, no devuelve la
      // fila — se actualiza localmente en vez de volver a pedir la lista
      // completa (mismo criterio que agenda/page.tsx tras cancelar).
      setCitas((prev) => prev.map((c) => (c.id === id ? { ...c, estado: "Cancelada" } : c)));
    } catch (err: any) {
      setErrorCitas(err.message || "No se pudo cancelar la cita.");
    } finally {
      setCancelandoCitaId(null);
    }
  }

  function abrirReprogramar(cita: Cita) {
    const fechaHora = new Date(cita.fecha_hora);
    setFormReprogramar({
      fecha: Number.isNaN(fechaHora.getTime()) ? "" : fechaHora.toISOString().slice(0, 10),
      hora: Number.isNaN(fechaHora.getTime()) ? "" : fechaHora.toTimeString().slice(0, 5),
    });
    setErrorCitas(null);
    setReprogramandoCitaId(cita.id);
  }

  async function guardarReprogramacion(e: React.FormEvent, citaId: number) {
    e.preventDefault();
    const { fecha, hora } = formReprogramar;
    if (!fecha || !hora) {
      setErrorCitas("Indica la fecha y la hora de la nueva cita.");
      return;
    }
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) {
      setErrorCitas("La fecha u hora ingresadas no son válidas.");
      return;
    }
    setGuardandoReprogramacion(true);
    setErrorCitas(null);
    try {
      const actualizada = await apiClient.patch<Cita>(`/admin/personas/citas/${citaId}`, {
        fecha_hora: fechaHora.toISOString(),
      });
      setCitas((prev) => prev.map((c) => (c.id === citaId ? actualizada : c)));
      setReprogramandoCitaId(null);
    } catch (err: any) {
      setErrorCitas(err.message || "No se pudo reprogramar la cita.");
    } finally {
      setGuardandoReprogramacion(false);
    }
  }

  function abrirEditarSesion(sesion: SesionSeguimiento) {
    const proxima = sesion.proxima_cita ? new Date(sesion.proxima_cita) : null;
    setFormSesion({
      observaciones: sesion.observaciones || "",
      accion_tomada: sesion.accion_tomada || "",
      acuerdos_compromisos: sesion.acuerdos_compromisos || "",
      proxima_cita_fecha: proxima && !Number.isNaN(proxima.getTime()) ? proxima.toISOString().slice(0, 10) : "",
      proxima_cita_hora: proxima && !Number.isNaN(proxima.getTime()) ? proxima.toTimeString().slice(0, 5) : "",
      estado: sesion.estado || "Atendido",
    });
    setErrorSesiones(null);
    setEditandoSesionId(sesion.id);
  }

  async function guardarEdicionSesion(e: React.FormEvent, sesionId: number) {
    e.preventDefault();
    setGuardandoSesion(true);
    setErrorSesiones(null);
    try {
      const { proxima_cita_fecha, proxima_cita_hora, ...resto } = formSesion;
      const proximaCitaIso =
        proxima_cita_fecha && proxima_cita_hora
          ? new Date(`${proxima_cita_fecha}T${proxima_cita_hora}`).toISOString()
          : null;
      const actualizada = await apiClient.patch<SesionSeguimiento>(`/educativo/seguimiento/${sesionId}`, {
        observaciones: resto.observaciones.trim() || undefined,
        accion_tomada: resto.accion_tomada.trim() || undefined,
        acuerdos_compromisos: resto.acuerdos_compromisos.trim() || undefined,
        proxima_cita: proximaCitaIso,
        estado: resto.estado,
      });
      setSeguimientos((prev) => prev.map((s) => (s.id === sesionId ? actualizada : s)));
      setEditandoSesionId(null);
    } catch (err: any) {
      setErrorSesiones(err.message || "No se pudo guardar la edición de la sesión.");
    } finally {
      setGuardandoSesion(false);
    }
  }

  async function toggleEntrada(entrada: EntradaExpediente) {
    if (entradaExpandidaId === entrada.id) {
      setEntradaExpandidaId(null);
      setDetalleEntrada(null);
      setMostrarFormularioVersion(false);
      return;
    }
    setEntradaExpandidaId(entrada.id);
    setDetalleEntrada(null);
    setMostrarFormularioVersion(false);
    setErrorDetalle(null);
    setCargandoDetalle(true);
    try {
      const detalle = await apiClient.get<EntradaExpedienteDetalle>(`/admin/personas/expediente/${entrada.id}`);
      setDetalleEntrada(detalle);
      setVersionSeleccionada(detalle.version?.numero_version ?? detalle.version_actual);
    } catch (err: any) {
      setErrorDetalle(err.message || "No se pudo cargar el contenido de esta entrada.");
    } finally {
      setCargandoDetalle(false);
    }
  }

  async function cambiarVersionMostrada(numero: number) {
    if (!detalleEntrada) return;
    setCargandoDetalle(true);
    setErrorDetalle(null);
    try {
      const detalle = await apiClient.get<EntradaExpedienteDetalle>(
        `/admin/personas/expediente/${detalleEntrada.id}?version=${numero}`,
      );
      setDetalleEntrada(detalle);
      setVersionSeleccionada(numero);
    } catch (err: any) {
      setErrorDetalle(err.message || "No se pudo cargar esa versión.");
    } finally {
      setCargandoDetalle(false);
    }
  }

  function abrirFormularioEntrada() {
    setFormEntrada({
      tipo_entrada: "observacion_conducta",
      fecha_entrada: "",
      motivo: "",
      contenido: "",
      interpretacion: "",
      diagnostico_presuntivo: "",
      contacto_familiar_id: "",
    });
    setErrorFormularioEntrada(null);
  }

  async function crearEntrada(e: React.FormEvent) {
    e.preventDefault();
    if (!formEntrada) return;
    setGuardandoEntrada(true);
    setErrorFormularioEntrada(null);
    try {
      const payload: EntradaExpedienteCreate = {
        tipo_entrada: formEntrada.tipo_entrada,
        fecha_entrada: formEntrada.fecha_entrada ? new Date(formEntrada.fecha_entrada).toISOString() : null,
        motivo: formEntrada.motivo || null,
        contenido: formEntrada.contenido || null,
        interpretacion: formEntrada.interpretacion || null,
        diagnostico_presuntivo: formEntrada.diagnostico_presuntivo || null,
        contacto_familiar_id:
          formEntrada.tipo_entrada === "contacto_apoderado" && formEntrada.contacto_familiar_id
            ? Number(formEntrada.contacto_familiar_id)
            : null,
      };
      const nueva = await apiClient.post<EntradaExpediente>(`/admin/personas/${personaId}/expediente`, payload);
      setEntradas((prev) =>
        [nueva, ...prev].sort((a, b) => new Date(b.fecha_entrada).getTime() - new Date(a.fecha_entrada).getTime()),
      );
      setFormEntrada(null);
    } catch (err: any) {
      setErrorFormularioEntrada(err.message || "No se pudo crear la entrada.");
    } finally {
      setGuardandoEntrada(false);
    }
  }

  function abrirFormularioEvidencia() {
    setFormEvidencia({
      archivo: null,
      titulo: "",
      descripcion: "",
      fecha_entrada: "",
      informe_id: "",
      incluir_en_pdf_informe: false,
    });
    setErrorFormularioEvidencia(null);
  }

  async function subirEvidencia(e: React.FormEvent) {
    e.preventDefault();
    if (!formEvidencia || !formEvidencia.archivo) {
      setErrorFormularioEvidencia("Elige un archivo para subir.");
      return;
    }
    setSubiendoEvidencia(true);
    setErrorFormularioEvidencia(null);
    try {
      const fd = new FormData();
      fd.append("archivo", formEvidencia.archivo);
      fd.append("titulo", formEvidencia.titulo);
      if (formEvidencia.descripcion) fd.append("descripcion", formEvidencia.descripcion);
      if (formEvidencia.fecha_entrada) fd.append("fecha_entrada", new Date(formEvidencia.fecha_entrada).toISOString());
      if (formEvidencia.informe_id) fd.append("informe_id", formEvidencia.informe_id);
      fd.append("incluir_en_pdf_informe", String(formEvidencia.informe_id ? formEvidencia.incluir_en_pdf_informe : false));

      const nueva = await apiClient.postForm<EntradaExpediente>(`/admin/personas/${personaId}/expediente/evidencia`, fd);
      setEntradas((prev) =>
        [nueva, ...prev].sort((a, b) => new Date(b.fecha_entrada).getTime() - new Date(a.fecha_entrada).getTime()),
      );
      setFormEvidencia(null);
    } catch (err: any) {
      setErrorFormularioEvidencia(err.message || "No se pudo subir la evidencia.");
    } finally {
      setSubiendoEvidencia(false);
    }
  }

  async function alternarIncluirEnPdf(entrada: EntradaExpediente, valor: boolean) {
    setActualizandoIncluirPdfId(entrada.id);
    try {
      const actualizada = await apiClient.patch<EntradaExpediente>(`/admin/personas/expediente/evidencia/${entrada.id}`, {
        incluir_en_pdf_informe: valor,
      });
      setEntradas((prev) => prev.map((en) => (en.id === entrada.id ? actualizada : en)));
    } catch (err: any) {
      setErrorEntradas(err.message || "No se pudo actualizar la evidencia.");
    } finally {
      setActualizandoIncluirPdfId(null);
    }
  }

  async function descargarEvidenciaExpediente(entrada: EntradaExpediente) {
    setDescargandoEvidenciaExpedienteId(entrada.id);
    try {
      const blob = await apiClient.descargarArchivo(`/admin/personas/expediente/evidencia/${entrada.id}/archivo`);
      descargarBlob(blob, entrada.nombre_archivo_original || `evidencia-${entrada.id}`);
    } catch (err: any) {
      setErrorEntradas(err.message || "No se pudo descargar la evidencia.");
    } finally {
      setDescargandoEvidenciaExpedienteId(null);
    }
  }

  function abrirFormularioVersion() {
    setFormVersion({ motivo: "", contenido: "", interpretacion: "", diagnostico_presuntivo: "", motivo_version: "" });
    setErrorFormularioVersion(null);
    setMostrarFormularioVersion(true);
  }

  async function agregarVersion(e: React.FormEvent) {
    e.preventDefault();
    if (!detalleEntrada) return;
    setGuardandoVersion(true);
    setErrorFormularioVersion(null);
    try {
      const payload: EntradaExpedienteVersionCreate = {
        motivo: formVersion.motivo || null,
        contenido: formVersion.contenido || null,
        interpretacion: formVersion.interpretacion || null,
        diagnostico_presuntivo: formVersion.diagnostico_presuntivo || null,
        motivo_version: formVersion.motivo_version,
      };
      const nuevaVersion = await apiClient.post<EntradaExpedienteVersion>(
        `/admin/personas/expediente/${detalleEntrada.id}/versiones`,
        payload,
      );
      setEntradas((prev) =>
        prev.map((en) => (en.id === detalleEntrada.id ? { ...en, version_actual: nuevaVersion.numero_version } : en)),
      );
      setDetalleEntrada((prev) =>
        prev ? { ...prev, version_actual: nuevaVersion.numero_version, version: nuevaVersion } : prev,
      );
      setVersionSeleccionada(nuevaVersion.numero_version);
      setMostrarFormularioVersion(false);
    } catch (err: any) {
      setErrorFormularioVersion(err.message || "No se pudo agregar la versión.");
    } finally {
      setGuardandoVersion(false);
    }
  }

  function abrirFormularioAutorizacion() {
    setFormularioAutorizacion({ motivo: "" });
    setErrorFormularioAutorizacion(null);
  }

  async function otorgarAutorizacion(e: React.FormEvent) {
    e.preventDefault();
    if (!formularioAutorizacion) return;
    setGuardandoAutorizacion(true);
    setErrorFormularioAutorizacion(null);
    try {
      const payload: AutorizacionAccesoColegioCreate = { motivo: formularioAutorizacion.motivo };
      const nueva = await apiClient.post<AutorizacionAccesoColegio>(
        `/admin/personas/${personaId}/autorizacion-colegio`,
        payload,
      );
      setAutorizacionVigente(nueva);
      setFormularioAutorizacion(null);
    } catch (err: any) {
      setErrorFormularioAutorizacion(err.message || "No se pudo otorgar la autorización.");
    } finally {
      setGuardandoAutorizacion(false);
    }
  }

  async function revocarAutorizacion() {
    if (!autorizacionVigente) return;
    if (!window.confirm("¿Revocar la autorización de acceso del colegio al expediente de este estudiante?")) {
      return;
    }
    setRevocandoAutorizacion(true);
    setErrorAutorizacion(null);
    try {
      const actualizada = await apiClient.post<AutorizacionAccesoColegio>(
        `/admin/personas/autorizacion-colegio/${autorizacionVigente.id}/revocar`,
      );
      setAutorizacionVigente(actualizada.vigente ? actualizada : null);
    } catch (err: any) {
      setErrorAutorizacion(err.message || "No se pudo revocar la autorización.");
    } finally {
      setRevocandoAutorizacion(false);
    }
  }

  function abrirFormularioConsentimiento(tipo: TipoConsentimiento) {
    setFormularioConsentimiento({
      tipo,
      otorgado_por_nombre: "",
      otorgante_apellidos: "",
      otorgante_documento: "",
      otorgante_relacion: "",
      tipo_otorgante: "apoderado",
      referencia_documento: "",
    });
    setErrorFormularioConsentimiento(null);
  }

  async function registrarConsentimiento(e: React.FormEvent) {
    e.preventDefault();
    if (!formularioConsentimiento) return;
    const { tipo } = formularioConsentimiento;
    setGuardandoConsentimiento(true);
    setErrorFormularioConsentimiento(null);
    try {
      let nuevo: ConsentimientoInformado;
      if (tipo === "apoderado") {
        const payload: ConsentimientoCreate = {
          otorgado_por_nombre: formularioConsentimiento.otorgado_por_nombre,
          tipo_otorgante: formularioConsentimiento.tipo_otorgante,
          referencia_documento: formularioConsentimiento.referencia_documento || null,
          otorgante_apellidos: formularioConsentimiento.otorgante_apellidos || null,
          otorgante_documento: formularioConsentimiento.otorgante_documento || null,
          otorgante_relacion: formularioConsentimiento.otorgante_relacion || null,
        };
        nuevo = await apiClient.post<ConsentimientoInformado>(`/admin/personas/${personaId}/consentimiento`, payload);
      } else {
        const payload: ConsentimientoAsentimientoCreate = {
          referencia_documento: formularioConsentimiento.referencia_documento || null,
        };
        nuevo = await apiClient.post<ConsentimientoInformado>(
          `/admin/personas/${personaId}/consentimiento/asentimiento`,
          payload,
        );
      }
      setConsentimientos((actual) => {
        const base = consentimientosOVacio(actual, personaId as string);
        return {
          ...base,
          [tipo]: { tiene_consentimiento_vigente: true, historial: [nuevo, ...base[tipo].historial] },
        };
      });
      setFormularioConsentimiento(null);
    } catch (err: any) {
      setErrorFormularioConsentimiento(err.message || "No se pudo registrar el consentimiento.");
    } finally {
      setGuardandoConsentimiento(false);
    }
  }

  async function revocarConsentimiento(tipo: TipoConsentimiento, consentimientoId: number) {
    if (
      !window.confirm(
        "¿Revocar este consentimiento? El historial anterior se conserva, pero este alumno dejará de poder ser matriculado o completar un examen hasta registrar uno nuevo.",
      )
    ) {
      return;
    }
    setRevocandoConsentimientoId(consentimientoId);
    setErrorConsentimientos(null);
    try {
      const path =
        tipo === "apoderado"
          ? `/admin/personas/${personaId}/consentimiento/revocar`
          : `/admin/personas/${personaId}/consentimiento/asentimiento/revocar`;
      const actualizado = await apiClient.post<ConsentimientoInformado>(path);
      setConsentimientos((actual) => {
        const base = consentimientosOVacio(actual, personaId as string);
        return {
          ...base,
          [tipo]: {
            tiene_consentimiento_vigente: false,
            historial: base[tipo].historial.map((c) => (c.id === actualizado.id ? actualizado : c)),
          },
        };
      });
    } catch (err: any) {
      setErrorConsentimientos(err.message || "No se pudo revocar el consentimiento.");
    } finally {
      setRevocandoConsentimientoId(null);
    }
  }

  // La evidencia (foto/PDF del documento firmado en papel) es un respaldo
  // opcional — lo que habilita matrícula/examen es el registro con
  // estado="vigente", nunca la presencia de evidencia adjunta.
  async function subirEvidenciaConsentimiento(tipo: TipoConsentimiento, consentimientoId: number, archivo: File) {
    setSubiendoEvidenciaId(consentimientoId);
    setErrorConsentimientos(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const actualizado = await apiClient.postForm<ConsentimientoInformado>(
        `/admin/personas/consentimiento/${consentimientoId}/evidencia`,
        fd,
      );
      setConsentimientos((actual) => {
        const base = consentimientosOVacio(actual, personaId as string);
        return {
          ...base,
          [tipo]: {
            ...base[tipo],
            historial: base[tipo].historial.map((c) => (c.id === actualizado.id ? actualizado : c)),
          },
        };
      });
    } catch (err: any) {
      setErrorConsentimientos(err.message || "No se pudo subir la evidencia.");
    } finally {
      setSubiendoEvidenciaId(null);
    }
  }

  async function descargarEvidenciaConsentimiento(consentimiento: ConsentimientoInformado) {
    setDescargandoEvidenciaId(consentimiento.id);
    setErrorConsentimientos(null);
    try {
      const blob = await apiClient.descargarArchivo(`/admin/personas/consentimiento/${consentimiento.id}/evidencia`);
      descargarBlob(blob, consentimiento.evidencia_nombre_archivo || `consentimiento-${consentimiento.id}`);
    } catch (err: any) {
      setErrorConsentimientos(err.message || "No se pudo descargar la evidencia.");
    } finally {
      setDescargandoEvidenciaId(null);
    }
  }

  // El backend exige rol psicologo/superadmin tanto para crear una entrada
  // como para agregar una versión — ver requerir_rol en el router. Gatear
  // por rol alcanza: el JWT no trae el id numérico del usuario (no hay
  // /auth/me todavía) y no hace falta compararlo con autor_usuario_id,
  // porque el listado ya solo devuelve entradas que este usuario puede
  // abrir por completo (ver notaAccesoExpediente).
  const puedeEscribirExpediente = sesion?.rol === "psicologo" || sesion?.rol === "superadmin";

  // Datos familiares / antecedentes clínicos: GET abierto a cualquier rol
  // autenticado (incluido 'colegio'), PATCH restringido a STAFF_CLINICO
  // (superadmin/admin/psicologo) — ver router.py, permisos.STAFF_CLINICO.
  // 'colegio' debe ver estos dos bloques en modo solo-lectura, nunca con
  // controles editables que el backend le rechazaría con 403 al guardar.
  const puedeEscribirDatosPrincipales =
    sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";

  // A lo sumo una fila con fecha_fin null (índice único parcial en el
  // backend) — esa es la matrícula vigente; el resto es historial.
  const matriculaVigente = historialAcademico.find((h) => h.fecha_fin === null) ?? null;

  if (loading) {
    return (
      <div className="p-8 text-center text-teal-900 font-medium">
        Cargando expediente clínico del alumno...
      </div>
    );
  }

  if (error || !alumno) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center">
        <TextoError className="mb-4">{error || "Estudiante no encontrado."}</TextoError>
        <Link href="/estudiantes" className="text-teal-600 underline font-medium">
          ← Volver al padrón
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Migas items={[{ label: "Padrón", href: "/estudiantes" }, { label: `${alumno.nombres} ${alumno.apellidos}` }]} />
      {/* Cabecera y Navegación */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border pb-4">
        <div>
          <Link href="/estudiantes" className="text-sm text-teal-600 hover:underline inline-block mb-1 font-medium">
            ← Volver al padrón
          </Link>
          <h1 className="font-display text-3xl text-teal-900 font-bold">
            {alumno.nombres} {alumno.apellidos}
          </h1>
        </div>

        <div className="flex items-center gap-3">
          <Boton onClick={() => router.push(`/estudiantes/${personaId}/cita/nueva`)}>+ Nueva Cita</Boton>
          <Boton onClick={() => router.push(`/estudiantes/${personaId}/seguimiento/nuevo`)}>
            + Registrar Sesión
          </Boton>
        </div>
      </div>

      {/* Datos de filiación del estudiante — identidad + familiares +
          antecedentes clínicos + contactos, unificados en un solo apartado
          a pedido explícito (antes vivían en 4 secciones separadas). Cada
          sub-bloque sigue golpeando su propio endpoint/tabla del backend
          (Persona / PersonaDatosFamiliares / PersonaAntecedentesClinicos /
          ContactoFamiliar) — esto es reordenamiento visual, no un cambio de
          modelo de datos. */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-6">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Datos de filiación del estudiante
        </h2>

        {/* --- Identidad --- */}
        <div className="space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-teal-900 uppercase tracking-wide">Identidad</h3>
            <div className="flex items-center gap-3">
              <button onClick={alternarHistorial} className="text-sm text-teal-600 hover:underline font-medium">
                {mostrarHistorial ? "Ocultar historial de cambios" : "Ver historial de cambios"}
              </button>
              {!editando && <Boton onClick={abrirEdicion}>Editar</Boton>}
            </div>
          </div>

          {!editando ? (
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Campo etiqueta="Nombres" valor={alumno.nombres} />
              <Campo etiqueta="Apellidos" valor={alumno.apellidos} />
              <Campo etiqueta="Documento de identidad" valor={alumno.documento_identidad} />
              <Campo etiqueta="Fecha de nacimiento" valor={formatearFecha(alumno.fecha_nacimiento)} />
              <Campo etiqueta="Género" valor={alumno.genero} />
            </div>
          ) : (
            <form onSubmit={guardarEdicion} className="grid sm:grid-cols-2 gap-4 text-sm">
              <CampoEditable etiqueta="Nombres">
                <Input required value={form.nombres} onChange={(e) => setForm({ ...form, nombres: e.target.value })} />
              </CampoEditable>
              <CampoEditable etiqueta="Apellidos">
                <Input required value={form.apellidos} onChange={(e) => setForm({ ...form, apellidos: e.target.value })} />
              </CampoEditable>
              <CampoEditable etiqueta="Documento de identidad">
                <Input
                  value={form.documento_identidad}
                  onChange={(e) => setForm({ ...form, documento_identidad: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Fecha de nacimiento">
                <Input
                  type="date"
                  value={form.fecha_nacimiento}
                  onChange={(e) => setForm({ ...form, fecha_nacimiento: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Género">
                <Input value={form.genero} onChange={(e) => setForm({ ...form, genero: e.target.value })} />
              </CampoEditable>

              <TextoError className="sm:col-span-2">{errorEdicion}</TextoError>

              <div className="sm:col-span-2 flex items-center gap-3 pt-1">
                <Boton type="submit" disabled={guardando}>
                  {guardando ? "Guardando..." : "Guardar cambios"}
                </Boton>
                <button
                  type="button"
                  onClick={() => setEditando(false)}
                  className="text-sm text-ink/60 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}

          {mostrarHistorial && (
            <div className="border-t border-border pt-4 mt-2">
              <h4 className="text-sm font-semibold text-teal-900 mb-2">Historial de cambios</h4>
              {cargandoHistorial && <p className="text-sm text-ink/60">Cargando historial...</p>}
              <TextoError>{errorHistorial}</TextoError>
              {!cargandoHistorial && !errorHistorial && historial && historial.length === 0 && (
                <p className="text-sm text-ink/60 italic">Sin cambios registrados todavía.</p>
              )}
              {!cargandoHistorial && historial && historial.length > 0 && (
                <div className="space-y-2">
                  {historial.map((registro) => (
                    <div key={registro.id} className="text-xs bg-mist border border-border/50 rounded p-2.5">
                      <span className="font-semibold text-teal-900">{registro.campo}</span>
                      {": "}
                      <span className="text-ink/70">{registro.valor_anterior ?? "(vacío)"}</span>
                      {" → "}
                      <span className="text-ink/90 font-medium">{registro.valor_nuevo ?? "(vacío)"}</span>
                      <div className="text-ink/50 mt-0.5">
                        {new Date(registro.fecha).toLocaleString()} · rol: {registro.rol_modificador ?? "—"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* --- Datos familiares (PersonaDatosFamiliares, 1:1) --- */}
        <div className="border-t border-border pt-4 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-teal-900 uppercase tracking-wide">Datos familiares</h3>
            {puedeEscribirDatosPrincipales && !editandoDatosFamiliares && (
              <Boton onClick={abrirEdicionDatosFamiliares}>Editar</Boton>
            )}
          </div>

          <TextoError>{errorDatosFamiliares}</TextoError>

          {!editandoDatosFamiliares ? (
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Campo etiqueta="Número de hermanos" valor={datosFamiliares?.numero_hermanos?.toString() ?? null} />
              <Campo etiqueta="Vive con" valor={datosFamiliares?.vive_con ?? null} />
              <Campo etiqueta="Lugar de nacimiento" valor={datosFamiliares?.lugar_nacimiento ?? null} />
              <Campo etiqueta="Lugar de procedencia" valor={datosFamiliares?.lugar_procedencia ?? null} />
            </div>
          ) : (
            <form onSubmit={guardarDatosFamiliares} className="grid sm:grid-cols-2 gap-4 text-sm">
              <CampoEditable etiqueta="Número de hermanos">
                <Input
                  type="number"
                  min={0}
                  max={30}
                  value={formDatosFamiliares.numero_hermanos}
                  onChange={(e) => setFormDatosFamiliares({ ...formDatosFamiliares, numero_hermanos: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Vive con">
                <Input
                  placeholder="ambos padres, madre, tutor legal..."
                  value={formDatosFamiliares.vive_con}
                  onChange={(e) => setFormDatosFamiliares({ ...formDatosFamiliares, vive_con: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Lugar de nacimiento">
                <Input
                  value={formDatosFamiliares.lugar_nacimiento}
                  onChange={(e) => setFormDatosFamiliares({ ...formDatosFamiliares, lugar_nacimiento: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Lugar de procedencia">
                <Input
                  value={formDatosFamiliares.lugar_procedencia}
                  onChange={(e) => setFormDatosFamiliares({ ...formDatosFamiliares, lugar_procedencia: e.target.value })}
                />
              </CampoEditable>

              <TextoError className="sm:col-span-2">{errorFormularioDatosFamiliares}</TextoError>

              <div className="sm:col-span-2 flex items-center gap-3 pt-1">
                <Boton type="submit" disabled={guardandoDatosFamiliares}>
                  {guardandoDatosFamiliares ? "Guardando..." : "Guardar cambios"}
                </Boton>
                <button
                  type="button"
                  onClick={() => setEditandoDatosFamiliares(false)}
                  className="text-sm text-ink/60 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>

        {/* --- Antecedentes clínicos externos (PersonaAntecedentesClinicos, 1:1) --- */}
        <div className="border-t border-border pt-4 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-teal-900 uppercase tracking-wide">Antecedentes clínicos externos</h3>
            {puedeEscribirDatosPrincipales && !editandoAntecedentesClinicos && (
              <Boton onClick={abrirEdicionAntecedentesClinicos}>Editar</Boton>
            )}
          </div>

          <TextoError>{errorAntecedentesClinicos}</TextoError>

          {!editandoAntecedentesClinicos ? (
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Campo
                etiqueta="Recibe terapia psicológica externa"
                valor={formatearBooleanoTriple(antecedentesClinicos?.recibe_terapia_psicologica_externa)}
              />
              <Campo etiqueta="Detalle" valor={antecedentesClinicos?.detalle_terapia_psicologica_externa ?? null} />
              <Campo
                etiqueta="Recibe atención psiquiátrica externa"
                valor={formatearBooleanoTriple(antecedentesClinicos?.recibe_atencion_psiquiatrica_externa)}
              />
              <Campo etiqueta="Detalle" valor={antecedentesClinicos?.detalle_atencion_psiquiatrica_externa ?? null} />
              <Campo
                etiqueta="Diagnóstico reportado"
                valor={antecedentesClinicos?.diagnostico_reportado ?? null}
                className="sm:col-span-2"
              />
            </div>
          ) : (
            <form onSubmit={guardarAntecedentesClinicos} className="grid sm:grid-cols-2 gap-4 text-sm">
              <CampoEditable etiqueta="Recibe terapia psicológica externa">
                <Select
                  value={formAntecedentesClinicos.recibe_terapia_psicologica_externa}
                  onChange={(e) =>
                    setFormAntecedentesClinicos({ ...formAntecedentesClinicos, recibe_terapia_psicologica_externa: e.target.value })
                  }
                >
                  <option value="">Sin especificar</option>
                  <option value="true">Sí</option>
                  <option value="false">No</option>
                </Select>
              </CampoEditable>
              <CampoEditable etiqueta="Detalle">
                <Input
                  value={formAntecedentesClinicos.detalle_terapia_psicologica_externa}
                  onChange={(e) =>
                    setFormAntecedentesClinicos({ ...formAntecedentesClinicos, detalle_terapia_psicologica_externa: e.target.value })
                  }
                />
              </CampoEditable>
              <CampoEditable etiqueta="Recibe atención psiquiátrica externa">
                <Select
                  value={formAntecedentesClinicos.recibe_atencion_psiquiatrica_externa}
                  onChange={(e) =>
                    setFormAntecedentesClinicos({ ...formAntecedentesClinicos, recibe_atencion_psiquiatrica_externa: e.target.value })
                  }
                >
                  <option value="">Sin especificar</option>
                  <option value="true">Sí</option>
                  <option value="false">No</option>
                </Select>
              </CampoEditable>
              <CampoEditable etiqueta="Detalle">
                <Input
                  value={formAntecedentesClinicos.detalle_atencion_psiquiatrica_externa}
                  onChange={(e) =>
                    setFormAntecedentesClinicos({ ...formAntecedentesClinicos, detalle_atencion_psiquiatrica_externa: e.target.value })
                  }
                />
              </CampoEditable>
              <CampoEditable etiqueta="Diagnóstico reportado" className="sm:col-span-2">
                <Textarea
                  rows={3}
                  value={formAntecedentesClinicos.diagnostico_reportado}
                  onChange={(e) =>
                    setFormAntecedentesClinicos({ ...formAntecedentesClinicos, diagnostico_reportado: e.target.value })
                  }
                />
              </CampoEditable>

              <TextoError className="sm:col-span-2">{errorFormularioAntecedentesClinicos}</TextoError>

              <div className="sm:col-span-2 flex items-center gap-3 pt-1">
                <Boton type="submit" disabled={guardandoAntecedentesClinicos}>
                  {guardandoAntecedentesClinicos ? "Guardando..." : "Guardar cambios"}
                </Boton>
                <button
                  type="button"
                  onClick={() => setEditandoAntecedentesClinicos(false)}
                  className="text-sm text-ink/60 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>

        {/* --- Contactos familiares (ContactoFamiliar, 1:muchos) --- */}
        <div className="border-t border-border pt-4 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h3 className="text-sm font-semibold text-teal-900 uppercase tracking-wide">Contactos familiares</h3>
            {!formularioContacto && <Boton onClick={abrirNuevoContacto}>+ Agregar contacto</Boton>}
          </div>

          <TextoError>{errorContactos}</TextoError>

          {formularioContacto && (
            <form onSubmit={guardarContacto} className="grid sm:grid-cols-2 gap-4 text-sm border-b border-border pb-4">
              <CampoEditable etiqueta="Nombre">
                <Input
                  required
                  value={formularioContacto.nombre}
                  onChange={(e) => setFormularioContacto({ ...formularioContacto, nombre: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Relación">
                <Input
                  placeholder="madre, padre, tutor legal..."
                  value={formularioContacto.relacion}
                  onChange={(e) => setFormularioContacto({ ...formularioContacto, relacion: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Teléfono">
                <Input
                  value={formularioContacto.telefono}
                  onChange={(e) => setFormularioContacto({ ...formularioContacto, telefono: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Email">
                <Input
                  type="email"
                  value={formularioContacto.email}
                  onChange={(e) => setFormularioContacto({ ...formularioContacto, email: e.target.value })}
                />
              </CampoEditable>

              <TextoError className="sm:col-span-2">{errorFormularioContacto}</TextoError>

              <div className="sm:col-span-2 flex items-center gap-3 pt-1">
                <Boton type="submit" disabled={guardandoContacto}>
                  {guardandoContacto ? "Guardando..." : formularioContacto.id === null ? "Agregar contacto" : "Guardar cambios"}
                </Boton>
                <button
                  type="button"
                  onClick={() => setFormularioContacto(null)}
                  className="text-sm text-ink/60 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}

          {contactos.length === 0 ? (
            <p className="text-sm text-ink/60 italic py-2">No hay contactos familiares registrados.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <TheadFila>
                    <Th className="py-2 pr-4">Nombre</Th>
                    <Th className="py-2 pr-4">Relación</Th>
                    <Th className="py-2 pr-4">Teléfono</Th>
                    <Th className="py-2 pr-4">Email</Th>
                    <Th className="py-2 pr-4">Estado</Th>
                    <Th className="py-2 pr-4"></Th>
                  </TheadFila>
                </thead>
                <tbody>
                  {contactos.map((contacto) => (
                    <tr
                      key={contacto.id}
                      className={`border-b border-border last:border-0 ${contacto.activo ? "" : "opacity-40"}`}
                    >
                      <td className="py-2.5 pr-4 font-medium text-ink">{contacto.nombre}</td>
                      <td className="py-2.5 pr-4 text-ink/80">{contacto.relacion || "—"}</td>
                      <td className="py-2.5 pr-4 text-ink/80">{contacto.telefono || "—"}</td>
                      <td className="py-2.5 pr-4 text-ink/80">{contacto.email || "—"}</td>
                      <td className="py-2.5 pr-4">
                        <span
                          className={`text-xs rounded-full px-2 py-0.5 font-medium ${
                            contacto.activo ? "bg-teal-400/20 text-teal-900" : "bg-border text-ink/50"
                          }`}
                        >
                          {contacto.activo ? "Activo" : "Inactivo"}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => abrirEdicionContacto(contacto)}
                          className="text-teal-600 hover:underline font-medium mr-3"
                        >
                          Editar
                        </button>
                        {contacto.activo && (
                          <button
                            onClick={() => desactivarContacto(contacto.id)}
                            disabled={desactivandoContactoId === contacto.id}
                            className="text-ink/70 hover:text-ink hover:underline font-medium disabled:opacity-50"
                          >
                            {desactivandoContactoId === contacto.id ? "Desactivando..." : "Desactivar"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Consentimiento informado — "apoderado" siempre obligatorio para
          matricular en campaña o completar un examen; "asentimiento" del
          propio estudiante solo se exige si la institución activó esa
          política (Institucion.exigir_asentimiento_estudiante). Historial
          append-only (ver ConsentimientosCombinados en types/api.ts):
          revocar nunca borra, solo cierra la fila vigente; "renovar" es
          simplemente registrar uno nuevo. La evidencia adjunta (foto/PDF del
          documento firmado en papel) es un respaldo opcional, no un
          requisito — lo que habilita matrícula/examen es el registro con
          estado="vigente" en la base de datos, nunca la evidencia en sí. */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-6">
        <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
          <h2 className="font-display text-xl text-teal-900 font-semibold">Consentimiento informado</h2>
        </div>

        <p className="text-xs text-ink/50 italic">
          Sin un consentimiento del apoderado vigente, este estudiante no puede ser matriculado en una campaña ni
          completar un examen. Si tu institución además exige el asentimiento del propio estudiante, regístralo en
          el segundo bloque.
        </p>

        <TextoError>{errorConsentimientos}</TextoError>

        {(["apoderado", "asentimiento"] as const).map((tipo) => {
          const bloque = consentimientos?.[tipo] ?? null;
          const vigente = bloque?.historial.find((c) => c.estado === "vigente") ?? null;
          const formularioAbiertoAqui = formularioConsentimiento?.tipo === tipo ? formularioConsentimiento : null;

          return (
            <div key={tipo} className="border-t border-border pt-5 first:border-0 first:pt-0 space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <h3 className="text-sm font-semibold text-teal-900 uppercase tracking-wide">
                  {tipo === "apoderado" ? "Consentimiento del apoderado" : "Asentimiento del estudiante"}
                </h3>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs rounded-full px-2.5 py-0.5 font-medium ${
                      vigente ? "bg-teal-400/20 text-teal-900" : "bg-amber/15 text-amber"
                    }`}
                  >
                    {vigente ? "Vigente" : "Sin consentimiento vigente"}
                  </span>
                  {puedeEscribirDatosPrincipales && !vigente && !formularioAbiertoAqui && (
                    <Boton onClick={() => abrirFormularioConsentimiento(tipo)}>Registrar</Boton>
                  )}
                </div>
              </div>

              {vigente && (
                <div className="grid sm:grid-cols-2 gap-4 text-sm">
                  {tipo === "apoderado" && (
                    <>
                      <Campo
                        etiqueta="Otorgado por"
                        valor={`${vigente.otorgado_por_nombre ?? ""} ${vigente.otorgante_apellidos ?? ""}`.trim() || null}
                      />
                      <Campo
                        etiqueta="Tipo de otorgante"
                        valor={vigente.tipo_otorgante === "colegio_delegado" ? "Colegio (autoridad delegada)" : "Apoderado"}
                      />
                      <Campo etiqueta="Documento de identidad" valor={vigente.otorgante_documento} />
                      <Campo etiqueta="Relación con el estudiante" valor={vigente.otorgante_relacion} />
                    </>
                  )}
                  <Campo etiqueta="Referencia del documento" valor={vigente.referencia_documento} />
                  <Campo etiqueta="Otorgado el" valor={new Date(vigente.fecha_otorgamiento).toLocaleString()} />

                  <div className="sm:col-span-2 flex flex-wrap items-center gap-3 border-t border-border/50 pt-3">
                    {vigente.evidencia_nombre_archivo ? (
                      <>
                        <span className="text-xs text-teal-700">
                          Evidencia adjunta: {vigente.evidencia_nombre_archivo} ✓
                        </span>
                        <button
                          onClick={() => descargarEvidenciaConsentimiento(vigente)}
                          disabled={descargandoEvidenciaId === vigente.id}
                          className="text-xs text-teal-600 hover:underline font-medium disabled:opacity-50"
                        >
                          {descargandoEvidenciaId === vigente.id ? "Descargando..." : "Descargar"}
                        </button>
                      </>
                    ) : (
                      <span className="text-xs text-ink/50 italic">Sin evidencia adjunta todavía.</span>
                    )}
                    {puedeEscribirDatosPrincipales && (
                      <label className="text-xs text-teal-600 hover:underline font-medium cursor-pointer">
                        {subiendoEvidenciaId === vigente.id
                          ? "Subiendo..."
                          : vigente.evidencia_nombre_archivo
                            ? "Reemplazar evidencia"
                            : "Adjuntar evidencia (foto o PDF del documento firmado)"}
                        <input
                          type="file"
                          accept="application/pdf,image/jpeg,image/png"
                          className="hidden"
                          disabled={subiendoEvidenciaId === vigente.id}
                          onChange={(e) => {
                            const archivo = e.target.files?.[0];
                            e.target.value = "";
                            if (archivo) subirEvidenciaConsentimiento(tipo, vigente.id, archivo);
                          }}
                        />
                      </label>
                    )}
                  </div>

                  {puedeEscribirDatosPrincipales && (
                    <div className="sm:col-span-2">
                      <button
                        onClick={() => revocarConsentimiento(tipo, vigente.id)}
                        disabled={revocandoConsentimientoId === vigente.id}
                        className={claseBoton("secundario")}
                      >
                        {revocandoConsentimientoId === vigente.id ? "Revocando..." : "Revocar"}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {!vigente && formularioAbiertoAqui && (
                <form onSubmit={registrarConsentimiento} className="grid sm:grid-cols-2 gap-4 text-sm">
                  {tipo === "apoderado" && (
                    <>
                      <CampoEditable etiqueta="Nombres de quien otorga (obligatorio)">
                        <Input
                          required
                          value={formularioAbiertoAqui.otorgado_por_nombre}
                          onChange={(e) =>
                            setFormularioConsentimiento({ ...formularioAbiertoAqui, otorgado_por_nombre: e.target.value })
                          }
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Apellidos">
                        <Input
                          value={formularioAbiertoAqui.otorgante_apellidos}
                          onChange={(e) =>
                            setFormularioConsentimiento({ ...formularioAbiertoAqui, otorgante_apellidos: e.target.value })
                          }
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Documento de identidad">
                        <Input
                          value={formularioAbiertoAqui.otorgante_documento}
                          onChange={(e) =>
                            setFormularioConsentimiento({ ...formularioAbiertoAqui, otorgante_documento: e.target.value })
                          }
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Relación con el estudiante">
                        <Input
                          placeholder="madre, padre, tutor legal..."
                          value={formularioAbiertoAqui.otorgante_relacion}
                          onChange={(e) =>
                            setFormularioConsentimiento({ ...formularioAbiertoAqui, otorgante_relacion: e.target.value })
                          }
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Tipo de otorgante">
                        <Select
                          value={formularioAbiertoAqui.tipo_otorgante}
                          onChange={(e) =>
                            setFormularioConsentimiento({
                              ...formularioAbiertoAqui,
                              tipo_otorgante: e.target.value as TipoOtorgante,
                            })
                          }
                        >
                          <option value="apoderado">Apoderado (padre/madre/tutor legal)</option>
                          <option value="colegio_delegado">Colegio, con autoridad delegada</option>
                        </Select>
                      </CampoEditable>
                    </>
                  )}
                  <CampoEditable etiqueta="Referencia del documento (opcional)">
                    <Input
                      placeholder='Ej. "Ficha de matrícula 2026, folio 45"'
                      value={formularioAbiertoAqui.referencia_documento}
                      onChange={(e) =>
                        setFormularioConsentimiento({ ...formularioAbiertoAqui, referencia_documento: e.target.value })
                      }
                    />
                  </CampoEditable>

                  <TextoError className="sm:col-span-2">{errorFormularioConsentimiento}</TextoError>

                  <div className="sm:col-span-2 flex items-center gap-3 pt-1">
                    <Boton type="submit" disabled={guardandoConsentimiento}>
                      {guardandoConsentimiento ? "Guardando..." : "Registrar consentimiento"}
                    </Boton>
                    <button
                      type="button"
                      onClick={() => setFormularioConsentimiento(null)}
                      className="text-sm text-ink/60 hover:underline"
                    >
                      Cancelar
                    </button>
                  </div>
                </form>
              )}

              {!vigente && !formularioAbiertoAqui && (
                <p className="text-sm text-ink/60 italic py-1">
                  {tipo === "apoderado"
                    ? "Sin consentimiento del apoderado vigente."
                    : "Sin asentimiento del propio estudiante vigente."}
                </p>
              )}

              {bloque && bloque.historial.length > 1 && (
                <button
                  onClick={() =>
                    setMostrarHistorialConsentimiento((prev) => ({ ...prev, [tipo]: !prev[tipo] }))
                  }
                  className="text-xs text-teal-600 hover:underline font-medium"
                >
                  {mostrarHistorialConsentimiento[tipo] ? "Ocultar historial" : `Ver historial (${bloque.historial.length})`}
                </button>
              )}
              {bloque && mostrarHistorialConsentimiento[tipo] && (
                <div className="space-y-2">
                  {[...bloque.historial].reverse().map((c) => (
                    <div key={c.id} className="text-xs bg-mist border border-border/50 rounded p-2.5">
                      <span className={`font-semibold ${c.estado === "vigente" ? "text-teal-900" : "text-ink/50"}`}>
                        {c.estado === "vigente" ? "Vigente" : "Revocado"}
                      </span>
                      {tipo === "apoderado" && (
                        <span className="text-ink/70">
                          {" "}
                          — {c.otorgado_por_nombre} {c.otorgante_apellidos}
                        </span>
                      )}
                      <div className="text-ink/50 mt-0.5">
                        Otorgado el {new Date(c.fecha_otorgamiento).toLocaleString()}
                        {c.fecha_revocacion && ` · revocado el ${new Date(c.fecha_revocacion).toLocaleString()}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </section>

      {/* Matrícula académica */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
          <h2 className="font-display text-xl text-teal-900 font-semibold">Matrícula académica</h2>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMostrarHistorialAcademico(!mostrarHistorialAcademico)}
              className="text-sm text-teal-600 hover:underline font-medium"
            >
              {mostrarHistorialAcademico ? "Ocultar historial académico" : "Ver historial académico"}
            </button>
            {!editandoMatricula && (
              <Boton onClick={abrirEdicionMatricula}>
                {matriculaVigente ? "Cambiar de sección" : "Matricular"}
              </Boton>
            )}
          </div>
        </div>

        <TextoError>{errorMatricula}</TextoError>

        {!editandoMatricula ? (
          matriculaVigente ? (
            (() => {
              const f = formatearSeccion(matriculaVigente);
              return (
                <div>
                  <div className="font-medium text-ink">{f.linea}</div>
                  {f.detalle && <div className="mt-0.5 text-xs text-ink/50">{f.detalle}</div>}
                  <div className="mt-1 text-xs text-ink/40">
                    Desde el {formatearFecha(matriculaVigente.fecha_inicio.slice(0, 10))}
                  </div>
                </div>
              );
            })()
          ) : (
            <p className="py-2 text-sm italic text-ink/60">Sin matrícula activa.</p>
          )
        ) : (
          <form onSubmit={guardarMatricula} className="grid gap-4 text-sm sm:grid-cols-3">
            <CampoEditable etiqueta="Nivel educativo">
              <Select
                required
                value={nivelSeleccionado}
                onChange={(e) => seleccionarNivel(e.target.value)}
                disabled={cargandoNiveles}
              >
                <option value="">{cargandoNiveles ? "Cargando…" : "Selecciona…"}</option>
                {niveles.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.nombre}
                  </option>
                ))}
              </Select>
            </CampoEditable>

            <CampoEditable etiqueta="Grado">
              <Select
                required
                value={gradoSeleccionado}
                onChange={(e) => seleccionarGrado(e.target.value)}
                disabled={!nivelSeleccionado || cargandoGrados}
                className="disabled:bg-mist disabled:text-ink/40"
              >
                <option value="">{cargandoGrados ? "Cargando…" : "Selecciona…"}</option>
                {grados.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.nombre}
                  </option>
                ))}
              </Select>
            </CampoEditable>

            <CampoEditable etiqueta="Sección">
              <Select
                required
                value={seccionSeleccionada}
                onChange={(e) => setSeccionSeleccionada(e.target.value)}
                disabled={!gradoSeleccionado || cargandoSecciones}
                className="disabled:bg-mist disabled:text-ink/40"
              >
                <option value="">{cargandoSecciones ? "Cargando…" : "Selecciona…"}</option>
                {secciones.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nombre} · {s.anio_escolar}
                    {s.turno ? ` (${s.turno})` : ""}
                  </option>
                ))}
              </Select>
            </CampoEditable>

            <TextoError className="sm:col-span-3">{errorFormularioMatricula}</TextoError>

            <div className="flex items-center gap-3 pt-1 sm:col-span-3">
              <Boton type="submit" disabled={!seccionSeleccionada || guardandoMatricula}>
                {guardandoMatricula ? "Guardando..." : "Guardar matrícula"}
              </Boton>
              <button
                type="button"
                onClick={() => setEditandoMatricula(false)}
                className="text-sm text-ink/60 hover:underline"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}

        {mostrarHistorialAcademico && (
          <div className="border-t border-border pt-4 mt-2">
            <h3 className="text-sm font-semibold text-teal-900 mb-2">Historial académico</h3>
            {historialAcademico.length === 0 ? (
              <p className="text-sm text-ink/60 italic">Sin matrículas registradas todavía.</p>
            ) : (
              <div className="space-y-2">
                {[...historialAcademico].reverse().map((h) => {
                  const f = formatearSeccion(h);
                  return (
                    <div key={h.matricula_id} className="text-xs bg-mist border border-border/50 rounded p-2.5">
                      <span className="font-semibold text-teal-900">{f.linea}</span>
                      {f.detalle && <span className="text-ink/60"> — {f.detalle}</span>}
                      <div className="text-ink/50 mt-0.5">
                        {formatearFecha(h.fecha_inicio.slice(0, 10))} →{" "}
                        {h.fecha_fin ? formatearFecha(h.fecha_fin.slice(0, 10)) : "vigente"}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Pruebas aplicadas / instrumentos aplicados — historial de informes
          (GET /educativo/personas/{id}/informes), uno por aplicación real.
          Aparece apenas el estudiante finaliza un examen (el informe se
          genera automático en segundo plano) y vale para CUALQUIER prueba
          del catálogo, no solo PHQ-9. Desde aquí mismo se revisa/edita el
          contenido profesional del informe (PATCH revision-informe) y se
          reemite el PDF para que la edición quede reflejada. */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
          <h2 className="font-display text-xl text-teal-900 font-semibold">Pruebas aplicadas</h2>
        </div>

        <TextoError>{errorPruebas}</TextoError>

        {pruebasAplicadas === null ? (
          <p className="text-sm text-ink/60">Cargando...</p>
        ) : pruebasAplicadas.length === 0 ? (
          <p className="text-sm text-ink/60 italic">Este estudiante todavía no tiene pruebas aplicadas.</p>
        ) : (
          <div className="space-y-3">
            {pruebasAplicadas.map((fila) => (
              <div key={fila.inscripcion_id} className="border border-border rounded-card">
                <div className="flex items-center justify-between gap-3 p-3 flex-wrap">
                  <div className="text-sm">
                    <p className="font-medium text-ink">{fila.prueba_nombre_publico}</p>
                    <p className="text-ink/60">
                      {fila.nombre_grupo}
                      {fila.fecha_aplicacion ? ` · ${formatearFecha(fila.fecha_aplicacion.slice(0, 10))}` : ""} · v
                      {fila.version_actual}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {fila.es_alerta && (
                      <span className="text-xs font-medium px-2 py-1 rounded-full bg-red-100 text-red-700">Alerta</span>
                    )}
                    {fila.estado_interpretacion === "incompleta" && (
                      <span className="text-xs font-medium px-2 py-1 rounded-full bg-amber-100 text-amber-700">
                        Interpretación incompleta
                      </span>
                    )}
                    <span
                      className={`text-xs font-medium px-2 py-1 rounded-full ${
                        fila.informe_liberado ? "bg-teal-100 text-teal-700" : "bg-ink/10 text-ink/60"
                      }`}
                    >
                      {fila.informe_liberado ? "Liberado" : "Retenido"}
                    </span>
                    <button
                      onClick={() => verInformeDesdeFicha(fila.inscripcion_id)}
                      className="text-sm text-teal-600 hover:underline font-medium"
                    >
                      Ver
                    </button>
                    <button
                      onClick={() => descargarInformeDesdeFicha(fila.inscripcion_id)}
                      disabled={descargandoInformeId === fila.inscripcion_id}
                      className="text-sm text-teal-600 hover:underline font-medium"
                    >
                      {descargandoInformeId === fila.inscripcion_id ? "Descargando..." : "Descargar PDF"}
                    </button>
                    <button
                      onClick={() => alternarRevision(fila.inscripcion_id)}
                      className="text-sm text-teal-600 hover:underline font-medium"
                    >
                      {inscripcionExpandida === fila.inscripcion_id ? "Ocultar" : "Revisar informe"}
                    </button>
                  </div>
                </div>

                {inscripcionExpandida === fila.inscripcion_id && (
                  <div className="border-t border-border p-4 space-y-4 bg-mist/30">
                    {cargandoDetalleInforme ? (
                      <p className="text-sm text-ink/60">Cargando...</p>
                    ) : detalleInforme ? (
                      <div className="lg:flex lg:gap-6 lg:items-start">
                        {/* 🆕 Vista previa del PDF embebida (react-pdf, ver
                            components/ui/VisorArchivo.tsx) — así la psicóloga ve el
                            informe sin descargarlo cada vez. Muestra siempre la ÚLTIMA versión
                            emitida; "Guardar revisión" no la cambia (el PDF no se regenera
                            solo), por eso el botón "Actualizar vista previa" y el refresco
                            automático tras reemitir. */}
                        <div className="lg:w-[46%] lg:sticky lg:top-4 mb-4 lg:mb-0 space-y-2">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-medium text-ink/70">Vista previa del PDF</p>
                            <button
                              onClick={() => cargarPreviewPdf(fila.inscripcion_id)}
                              disabled={cargandoPreviewPdf}
                              className="text-xs text-teal-600 hover:underline font-medium disabled:opacity-50"
                            >
                              {cargandoPreviewPdf ? "Cargando..." : "Actualizar vista previa"}
                            </button>
                          </div>
                          <TextoError>{errorPreviewPdf}</TextoError>
                          <ContenidoVisorArchivo
                            archivo={pdfPreviewArchivo}
                            cargando={cargandoPreviewPdf}
                            alturaClase="h-[70vh]"
                          />
                        </div>

                        <div className="flex-1 min-w-0 space-y-4">
                        <p className="text-xs text-ink/60">
                          Lo que se guarda aquí NO cambia el PDF ya emitido — hace falta reemitir (abajo) para que
                          una nueva versión lo refleje.
                        </p>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">Motivo de consulta</span>
                          <Textarea
                            rows={2}
                            value={formRevision.motivo_consulta ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, motivo_consulta: e.target.value })}
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">Observación conductual</span>
                          <Textarea
                            rows={2}
                            value={formRevision.observacion_conductual ?? ""}
                            onChange={(e) =>
                              setFormRevision({ ...formRevision, observacion_conductual: e.target.value })
                            }
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">
                            Técnicas adicionales (reemplaza las predeterminadas; separadas por coma — ej. &quot;Entrevista,
                            Observación&quot;. El instrumento mismo siempre se imprime aparte, no hace falta repetirlo aquí)
                          </span>
                          <Textarea
                            rows={2}
                            value={formRevision.tecnicas_override ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, tecnicas_override: e.target.value })}
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">Conclusión (reemplaza la sugerida)</span>
                          <Textarea
                            rows={3}
                            value={formRevision.conclusion_override ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, conclusion_override: e.target.value })}
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">Recomendaciones (reemplaza la sugerida)</span>
                          <Textarea
                            rows={3}
                            value={formRevision.recomendaciones_override ?? ""}
                            onChange={(e) =>
                              setFormRevision({ ...formRevision, recomendaciones_override: e.target.value })
                            }
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">Cargo/especialidad en la firma</span>
                          <Input
                            placeholder="Ej. Psicóloga Clínica — COP 12345"
                            value={formRevision.firma_cargo_override ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, firma_cargo_override: e.target.value })}
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">
                            Nombre en la firma (reemplaza al que revisó el informe)
                          </span>
                          <Input
                            placeholder="Por defecto: quien revisó/liberó el informe"
                            value={formRevision.firma_nombre_override ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, firma_nombre_override: e.target.value })}
                          />
                        </label>

                        <label className="flex flex-col gap-1 text-sm">
                          <span className="text-ink/70 font-medium">DNI del profesional en la firma</span>
                          <Input
                            placeholder="Por defecto queda en blanco, para llenar a mano"
                            value={formRevision.firma_dni_override ?? ""}
                            onChange={(e) => setFormRevision({ ...formRevision, firma_dni_override: e.target.value })}
                          />
                        </label>

                        <div className="flex items-center gap-6 text-sm">
                          <label className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={formRevision.informe_liberado ?? false}
                              onChange={(e) => setFormRevision({ ...formRevision, informe_liberado: e.target.checked })}
                            />
                            Informe liberado al alumno
                          </label>
                          <label className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={formRevision.resultado_visible_alumno ?? false}
                              onChange={(e) =>
                                setFormRevision({ ...formRevision, resultado_visible_alumno: e.target.checked })
                              }
                            />
                            Resultado visible al alumno
                          </label>
                        </div>

                        <TextoError>{errorRevision}</TextoError>
                        <Boton onClick={() => guardarRevision(fila.inscripcion_id)} disabled={guardandoRevision}>
                          {guardandoRevision ? "Guardando..." : "Guardar revisión"}
                        </Boton>

                        <div className="border-t border-border pt-4 space-y-2">
                          <p className="text-sm font-medium text-ink/70">Reemitir PDF con estos cambios</p>
                          <div className="flex items-center gap-2 flex-wrap">
                            <Input
                              placeholder="Motivo de la reemisión (obligatorio)"
                              value={motivoReemision}
                              onChange={(e) => setMotivoReemision(e.target.value)}
                              className="flex-1 min-w-[240px]"
                            />
                            <Boton
                              onClick={() => reemitirInformeDesdeFicha(fila.inscripcion_id)}
                              disabled={reemitiendo}
                            >
                              {reemitiendo ? "Reemitiendo..." : "Reemitir informe"}
                            </Boton>
                          </div>
                          <TextoError>{errorReemitir}</TextoError>
                        </div>

                        {detalleInforme.versiones && detalleInforme.versiones.length > 0 && (
                          <div className="border-t border-border pt-4">
                            <p className="text-sm font-medium text-ink/70 mb-1">Historial de versiones</p>
                            <ul className="text-sm text-ink/60 space-y-1">
                              {detalleInforme.versiones.map((v) => (
                                <li key={v.numero_version}>
                                  v{v.numero_version} — {new Date(v.generado_en).toLocaleString()}
                                  {v.motivo_version ? ` — ${v.motivo_version}` : ""} ({v.origen})
                                  {v.retracta_version_previa_liberada && (
                                    <span className="text-amber-700">
                                      {" "}· retracta la v{v.numero_version - 1}, que ya estaba liberada y visible
                                      para el alumno (si ya fue descargada, esa copia sigue en su poder)
                                    </span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        </div>
                      </div>
                    ) : (
                      <TextoError>{errorRevision}</TextoError>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Línea de tiempo del expediente clínico */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
          <h2 className="font-display text-xl text-teal-900 font-semibold">Expediente clínico</h2>
          {puedeEscribirExpediente && !formEntrada && !formEvidencia && (
            <div className="flex items-center gap-2">
              <Boton onClick={abrirFormularioEntrada}>+ Nueva entrada</Boton>
              <button onClick={abrirFormularioEvidencia} className={claseBoton("secundario")}>
                + Subir evidencia
              </button>
            </div>
          )}
        </div>

        <p className="text-xs text-ink/50 italic">{notaAccesoExpediente(sesion?.rol)}</p>

        <TextoError>{errorEntradas}</TextoError>

        {formEvidencia && (
          <form onSubmit={subirEvidencia} className="grid sm:grid-cols-2 gap-4 text-sm border-b border-border pb-4">
            <CampoEditable etiqueta="Archivo (PDF/JPG/PNG, máx. 10 MB)" className="sm:col-span-2">
              <input
                type="file"
                accept=".pdf,.jpg,.jpeg,.png"
                required
                onChange={(e) => setFormEvidencia({ ...formEvidencia, archivo: e.target.files?.[0] ?? null })}
                className="block w-full text-sm text-ink/70 file:mr-3 file:rounded-full file:border-0 file:bg-teal-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-teal-700 hover:file:bg-teal-100"
              />
            </CampoEditable>
            <CampoEditable etiqueta="Título (obligatorio)" className="sm:col-span-2">
              <Input
                required
                placeholder='Ej. "Dibujo bajo la lluvia"'
                value={formEvidencia.titulo}
                onChange={(e) => setFormEvidencia({ ...formEvidencia, titulo: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Descripción (opcional)" className="sm:col-span-2">
              <Textarea
                rows={2}
                value={formEvidencia.descripcion}
                onChange={(e) => setFormEvidencia({ ...formEvidencia, descripcion: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Fecha (opcional, por defecto ahora)">
              <Input
                type="datetime-local"
                value={formEvidencia.fecha_entrada}
                onChange={(e) => setFormEvidencia({ ...formEvidencia, fecha_entrada: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Vincular a un informe (opcional)">
              <Select
                value={formEvidencia.informe_id}
                onChange={(e) =>
                  setFormEvidencia({ ...formEvidencia, informe_id: e.target.value, incluir_en_pdf_informe: false })
                }
              >
                <option value="">(suelta — no vinculada a ningún informe)</option>
                {(pruebasAplicadas ?? []).map((p) => (
                  <option key={p.informe_id} value={p.informe_id}>
                    {p.prueba_nombre_publico} — {p.fecha_aplicacion ? new Date(p.fecha_aplicacion).toLocaleDateString() : "sin fecha"}
                  </option>
                ))}
              </Select>
            </CampoEditable>

            {formEvidencia.informe_id && (
              <label className="sm:col-span-2 flex items-center gap-2 text-sm text-ink/70">
                <input
                  type="checkbox"
                  checked={formEvidencia.incluir_en_pdf_informe}
                  onChange={(e) => setFormEvidencia({ ...formEvidencia, incluir_en_pdf_informe: e.target.checked })}
                />
                Incluir como anexo la próxima vez que se genere una versión de ese informe (automática, &quot;Reemitir
                informe&quot; o &quot;Reprocesar&quot;) — nunca modifica una versión ya emitida.
              </label>
            )}

            <TextoError className="sm:col-span-2">{errorFormularioEvidencia}</TextoError>

            <div className="sm:col-span-2 flex items-center gap-3 pt-1">
              <Boton type="submit" disabled={subiendoEvidencia}>
                {subiendoEvidencia ? "Subiendo..." : "Subir evidencia"}
              </Boton>
              <button
                type="button"
                onClick={() => setFormEvidencia(null)}
                className="text-sm text-ink/60 hover:underline"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}

        {formEntrada && (
          <form onSubmit={crearEntrada} className="grid sm:grid-cols-2 gap-4 text-sm border-b border-border pb-4">
            <CampoEditable etiqueta="Tipo de entrada">
              <Select
                value={formEntrada.tipo_entrada}
                onChange={(e) =>
                  setFormEntrada({ ...formEntrada, tipo_entrada: e.target.value as TipoEntradaExpediente })
                }
              >
                {TIPOS_ENTRADA_NARRATIVOS.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {ETIQUETAS_TIPO_ENTRADA[tipo]}
                  </option>
                ))}
              </Select>
            </CampoEditable>
            <CampoEditable etiqueta="Fecha (opcional, por defecto ahora)">
              <Input
                type="datetime-local"
                value={formEntrada.fecha_entrada}
                onChange={(e) => setFormEntrada({ ...formEntrada, fecha_entrada: e.target.value })}
              />
            </CampoEditable>

            {formEntrada.tipo_entrada === "contacto_apoderado" && (
              <CampoEditable etiqueta="Contacto familiar (opcional)" className="sm:col-span-2">
                <Select
                  value={formEntrada.contacto_familiar_id}
                  onChange={(e) => setFormEntrada({ ...formEntrada, contacto_familiar_id: e.target.value })}
                >
                  <option value="">(ninguno)</option>
                  {contactos
                    .filter((c) => c.activo)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.nombre} {c.relacion ? `(${c.relacion})` : ""}
                      </option>
                    ))}
                </Select>
              </CampoEditable>
            )}

            <CampoEditable etiqueta="Motivo" className="sm:col-span-2">
              <Input
                value={formEntrada.motivo}
                onChange={(e) => setFormEntrada({ ...formEntrada, motivo: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Contenido" className="sm:col-span-2">
              <Textarea
                rows={3}
                value={formEntrada.contenido}
                onChange={(e) => setFormEntrada({ ...formEntrada, contenido: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Interpretación" className="sm:col-span-2">
              <Textarea
                rows={2}
                value={formEntrada.interpretacion}
                onChange={(e) => setFormEntrada({ ...formEntrada, interpretacion: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Diagnóstico presuntivo" className="sm:col-span-2">
              <Textarea
                rows={2}
                value={formEntrada.diagnostico_presuntivo}
                onChange={(e) => setFormEntrada({ ...formEntrada, diagnostico_presuntivo: e.target.value })}
              />
            </CampoEditable>

            <TextoError className="sm:col-span-2">{errorFormularioEntrada}</TextoError>

            <div className="sm:col-span-2 flex items-center gap-3 pt-1">
              <Boton type="submit" disabled={guardandoEntrada}>
                {guardandoEntrada ? "Guardando..." : "Crear entrada"}
              </Boton>
              <button
                type="button"
                onClick={() => setFormEntrada(null)}
                className="text-sm text-ink/60 hover:underline"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}

        {entradas.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">No hay entradas de expediente visibles para ti.</p>
        ) : (
          <div className="space-y-3">
            {entradas.map((entrada) => {
              // 🆕 'evidencia' no es narrativa ni puente (ver docstring de
              // EntradaExpediente en models.py) — título/descripción/descarga
              // ya vienen en el listado (metadata, no contenido narrativo),
              // así que no necesita el toggle con fetch+auditoría de abajo:
              // la propia descarga del archivo es lo que se audita.
              if (entrada.tipo_entrada === "evidencia") {
                return (
                  <div key={entrada.id} className="rounded-card border border-border p-4 space-y-2">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-teal-900">{entrada.titulo || "Evidencia"}</span>
                        <span className="text-xs rounded-full px-2 py-0.5 font-medium bg-teal-900/10 text-teal-900">
                          Evidencia
                        </span>
                        {entrada.informe_id && (
                          <span className="text-xs text-ink/50">vinculada a informe #{entrada.informe_id}</span>
                        )}
                      </div>
                      <span className="text-xs text-ink/60 whitespace-nowrap">
                        {new Date(entrada.fecha_entrada).toLocaleString()}
                      </span>
                    </div>
                    {entrada.descripcion && <p className="text-sm text-ink/70">{entrada.descripcion}</p>}
                    <div className="flex items-center gap-4 flex-wrap pt-1">
                      <button
                        onClick={() => verEvidenciaExpediente(entrada)}
                        className="text-xs text-teal-600 hover:underline font-medium"
                      >
                        Ver
                      </button>
                      <button
                        onClick={() => descargarEvidenciaExpediente(entrada)}
                        disabled={descargandoEvidenciaExpedienteId === entrada.id}
                        className="text-xs text-teal-600 hover:underline font-medium disabled:opacity-50"
                      >
                        {descargandoEvidenciaExpedienteId === entrada.id
                          ? "Descargando..."
                          : `Descargar (${entrada.nombre_archivo_original || "archivo"})`}
                      </button>
                      {entrada.informe_id && puedeEscribirExpediente && (
                        <label className="flex items-center gap-2 text-xs text-ink/70">
                          <input
                            type="checkbox"
                            checked={entrada.incluir_en_pdf_informe}
                            disabled={actualizandoIncluirPdfId === entrada.id}
                            onChange={(e) => alternarIncluirEnPdf(entrada, e.target.checked)}
                          />
                          Incluir en la próxima versión del PDF
                        </label>
                      )}
                    </div>
                  </div>
                );
              }

              const narrativa = esTipoEntradaNarrativo(entrada.tipo_entrada);
              const expandida = entradaExpandidaId === entrada.id;
              return (
                <div key={entrada.id} className="rounded-card border border-border overflow-hidden">
                  <button
                    onClick={() => toggleEntrada(entrada)}
                    className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-mist/40 transition-colors"
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-teal-900">
                        {ETIQUETAS_TIPO_ENTRADA[entrada.tipo_entrada]}
                      </span>
                      <span
                        className={`text-xs rounded-full px-2 py-0.5 font-medium ${
                          narrativa ? "bg-teal-400/20 text-teal-900" : "bg-border text-ink/60"
                        }`}
                      >
                        {narrativa ? "Narrativa" : "Puente"}
                      </span>
                      {entrada.version_actual !== null && (
                        <span className="text-xs text-ink/50">v{entrada.version_actual}</span>
                      )}
                    </div>
                    <span className="text-xs text-ink/60 whitespace-nowrap">
                      {new Date(entrada.fecha_entrada).toLocaleString()}
                    </span>
                  </button>

                  {expandida && (
                    <div className="border-t border-border p-4 space-y-3">
                      {cargandoDetalle && <p className="text-sm text-ink/60">Cargando contenido...</p>}
                      <TextoError>{errorDetalle}</TextoError>

                      {!cargandoDetalle && detalleEntrada && detalleEntrada.id === entrada.id && (
                        <>
                          {narrativa ? (
                            <>
                              {detalleEntrada.version_actual !== null && detalleEntrada.version_actual > 1 && (
                                <label className="flex items-center gap-2 text-xs text-ink/70">
                                  Versión:
                                  <select
                                    value={versionSeleccionada ?? detalleEntrada.version_actual}
                                    onChange={(e) => cambiarVersionMostrada(Number(e.target.value))}
                                    className="rounded border border-border px-2 py-1"
                                  >
                                    {Array.from({ length: detalleEntrada.version_actual }, (_, i) => i + 1).map(
                                      (n) => (
                                        <option key={n} value={n}>
                                          v{n}
                                          {n === detalleEntrada.version_actual ? " (vigente)" : ""}
                                        </option>
                                      ),
                                    )}
                                  </select>
                                </label>
                              )}

                              {detalleEntrada.version ? (
                                <div className="space-y-2 text-sm">
                                  {detalleEntrada.version.motivo && (
                                    <Campo etiqueta="Motivo" valor={detalleEntrada.version.motivo} />
                                  )}
                                  {detalleEntrada.version.contenido && (
                                    <Campo etiqueta="Contenido" valor={detalleEntrada.version.contenido} />
                                  )}
                                  {detalleEntrada.version.interpretacion && (
                                    <Campo etiqueta="Interpretación" valor={detalleEntrada.version.interpretacion} />
                                  )}
                                  {detalleEntrada.version.diagnostico_presuntivo && (
                                    <Campo
                                      etiqueta="Diagnóstico presuntivo"
                                      valor={detalleEntrada.version.diagnostico_presuntivo}
                                    />
                                  )}
                                  {detalleEntrada.version.motivo_version && (
                                    <Campo
                                      etiqueta="Motivo de esta versión"
                                      valor={detalleEntrada.version.motivo_version}
                                    />
                                  )}
                                  <p className="text-xs text-ink/50">
                                    Registrado el {new Date(detalleEntrada.version.creado_en).toLocaleString()}
                                  </p>
                                </div>
                              ) : (
                                <p className="text-sm text-ink/60 italic">Esta versión no tiene contenido.</p>
                              )}

                              {puedeEscribirExpediente && !mostrarFormularioVersion && (
                                <button
                                  onClick={abrirFormularioVersion}
                                  className="text-sm text-teal-600 hover:underline font-medium"
                                >
                                  + Agregar versión
                                </button>
                              )}

                              {mostrarFormularioVersion && (
                                <form onSubmit={agregarVersion} className="space-y-3 border-t border-border pt-3">
                                  <CampoEditable etiqueta="Motivo">
                                    <Input
                                      value={formVersion.motivo}
                                      onChange={(e) => setFormVersion({ ...formVersion, motivo: e.target.value })}
                                    />
                                  </CampoEditable>
                                  <CampoEditable etiqueta="Contenido">
                                    <Textarea
                                      rows={3}
                                      value={formVersion.contenido}
                                      onChange={(e) => setFormVersion({ ...formVersion, contenido: e.target.value })}
                                    />
                                  </CampoEditable>
                                  <CampoEditable etiqueta="Interpretación">
                                    <Textarea
                                      rows={2}
                                      value={formVersion.interpretacion}
                                      onChange={(e) =>
                                        setFormVersion({ ...formVersion, interpretacion: e.target.value })
                                      }
                                    />
                                  </CampoEditable>
                                  <CampoEditable etiqueta="Diagnóstico presuntivo">
                                    <Textarea
                                      rows={2}
                                      value={formVersion.diagnostico_presuntivo}
                                      onChange={(e) =>
                                        setFormVersion({ ...formVersion, diagnostico_presuntivo: e.target.value })
                                      }
                                    />
                                  </CampoEditable>
                                  <CampoEditable etiqueta="Motivo de esta corrección (obligatorio)">
                                    <Input
                                      required
                                      value={formVersion.motivo_version}
                                      onChange={(e) =>
                                        setFormVersion({ ...formVersion, motivo_version: e.target.value })
                                      }
                                    />
                                  </CampoEditable>

                                  <TextoError>{errorFormularioVersion}</TextoError>

                                  <div className="flex items-center gap-3">
                                    <Boton type="submit" disabled={guardandoVersion}>
                                      {guardandoVersion ? "Guardando..." : "Guardar versión"}
                                    </Boton>
                                    <button
                                      type="button"
                                      onClick={() => setMostrarFormularioVersion(false)}
                                      className="text-sm text-ink/60 hover:underline"
                                    >
                                      Cancelar
                                    </button>
                                  </div>
                                </form>
                              )}
                            </>
                          ) : (
                            <p className="text-sm text-ink/70">
                              Esta entrada enlaza a{" "}
                              {detalleEntrada.tipo_entrada === "sesion"
                                ? "una sesión de seguimiento"
                                : "un informe"}{" "}
                              ya existente
                              {detalleEntrada.sesion_seguimiento_id
                                ? ` (#${detalleEntrada.sesion_seguimiento_id})`
                                : ""}
                              {detalleEntrada.informe_id ? ` (#${detalleEntrada.informe_id})` : ""} — su contenido
                              vive en esa sección, no se duplica aquí.
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Autorización de acceso del colegio — misma condición de rol que
          escribir en el expediente, ver comentario de puedeEscribirExpediente. */}
      {puedeEscribirExpediente && (
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
            <h2 className="font-display text-xl text-teal-900 font-semibold">Autorización de acceso del colegio</h2>
            {!autorizacionVigente && !formularioAutorizacion && (
              <Boton onClick={abrirFormularioAutorizacion}>Otorgar</Boton>
            )}
          </div>

          <p className="text-xs text-ink/50 italic">
            Mientras esté vigente, el rol &quot;colegio&quot; obtiene lectura completa de todo el expediente clínico
            de este estudiante — es la única excepción a la confidencialidad por autor.
          </p>

          <TextoError>{errorAutorizacion}</TextoError>

          {autorizacionVigente ? (
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <Campo etiqueta="Motivo" valor={autorizacionVigente.motivo} />
              <Campo etiqueta="Otorgada el" valor={new Date(autorizacionVigente.fecha_otorgado).toLocaleString()} />
              <Campo
                etiqueta="Otorgada por"
                valor={`Usuario #${autorizacionVigente.otorgado_por_usuario_id}${
                  autorizacionVigente.rol_otorgante ? ` (${autorizacionVigente.rol_otorgante})` : ""
                }`}
              />
              <div className="sm:col-span-2">
                <button
                  onClick={revocarAutorizacion}
                  disabled={revocandoAutorizacion}
                  className={claseBoton("secundario")}
                >
                  {revocandoAutorizacion ? "Revocando..." : "Revocar"}
                </button>
              </div>
            </div>
          ) : formularioAutorizacion ? (
            <form onSubmit={otorgarAutorizacion} className="space-y-3 text-sm">
              <CampoEditable etiqueta="Motivo (obligatorio)">
                <Input
                  required
                  value={formularioAutorizacion.motivo}
                  onChange={(e) => setFormularioAutorizacion({ motivo: e.target.value })}
                />
              </CampoEditable>

              <TextoError>{errorFormularioAutorizacion}</TextoError>

              <div className="flex items-center gap-3">
                <Boton type="submit" disabled={guardandoAutorizacion}>
                  {guardandoAutorizacion ? "Guardando..." : "Otorgar autorización"}
                </Boton>
                <button
                  type="button"
                  onClick={() => setFormularioAutorizacion(null)}
                  className="text-sm text-ink/60 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            </form>
          ) : (
            <p className="text-sm text-ink/60 italic py-2">No hay una autorización vigente para este estudiante.</p>
          )}
        </section>
      )}

      {/* Documentos institucionales — listado simple con link a la pantalla
          dedicada del sidebar (/documentos), donde se arman las plantillas y
          se edita el contenido de cada documento — ver docs/motor-documentos.md.
          🆕 "+ Nuevo documento" pasa personaId por query string: /documentos/nuevo
          lo lee y precarga el alcance "uno o varios alumnos" con este alumno ya
          marcado (ver ese archivo), para no tener que volver a buscarlo. Se abre
          en pestaña nueva (target=_blank) para no perder la ficha de donde se vino. */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2 flex-wrap gap-2">
          <h2 className="font-display text-xl text-teal-900 font-semibold">Documentos institucionales</h2>
          <Link
            href={`/documentos/nuevo?persona_id=${personaId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-teal-700 hover:underline"
          >
            + Nuevo documento ↗
          </Link>
        </div>

        <TextoError>{errorDocumentos}</TextoError>

        {documentos.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">No hay documentos institucionales para este estudiante.</p>
        ) : (
          <div className="divide-y divide-border">
            {documentos.map((documento) => (
              <Link
                key={documento.id}
                href={`/documentos/${documento.id}`}
                className="flex items-center justify-between gap-3 py-2 hover:bg-mist/40 -mx-2 px-2 rounded-card transition-colors"
              >
                <span className="text-sm font-medium text-ink">{documento.titulo}</span>
                <span className="text-xs text-ink/50">
                  {documento.version_actual === null ? "Sin versión generada" : `v${documento.version_actual}`}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>


      {/* Sección de Citas */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Citas Programadas
        </h2>

        <TextoError>{errorCitas}</TextoError>

        {citas.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">No hay citas registradas para este alumno.</p>
        ) : (
          <div className="grid gap-3">
            {citas.map((cita) => {
              // 🆕 persona_id null = actividad grupal (taller/charla/otro) en
              // la que este alumno quedó anotado como participante, no una
              // cita suya — aparece aquí para que su historial quede
              // completo, pero a propósito SIN "Reprogramar"/"Cancelar":
              // esas acciones afectan a TODOS los asistentes de la
              // actividad, no solo a este alumno, y ejercerlas por error
              // desde la ficha de uno solo de ellos reprogramaría/cancelaría
              // el taller completo. Esa edición vive en /agenda.
              const esGrupal = cita.persona_id === null;
              return (
              <div key={cita.id} className="p-4 rounded-card border border-border space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    {esGrupal && (
                      <span className="inline-block rounded-full px-2 py-0.5 text-[11px] font-medium bg-teal-600/10 text-teal-900 mb-1">
                        Actividad grupal{cita.tipo_actividad ? `: ${cita.tipo_actividad}` : ""}
                      </span>
                    )}
                    <p className="text-sm font-semibold text-teal-900">
                      {esGrupal ? cita.titulo : `Motivo: ${cita.motivo}`}
                    </p>
                    <p className="text-xs text-ink/70 mt-1">
                      Fecha: {new Date(cita.fecha_hora).toLocaleString("es-PE")}
                      {esGrupal && cita.lugar && ` · ${cita.lugar}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${claseEstadoCita(cita.estado)}`}>
                      {cita.estado}
                    </span>
                    {!esGrupal && cita.estado === "Programada" && reprogramandoCitaId !== cita.id && (
                      <>
                        <button
                          onClick={() => abrirReprogramar(cita)}
                          className="text-xs text-teal-700 hover:underline"
                        >
                          Reprogramar
                        </button>
                        <button
                          onClick={() => cancelarCita(cita.id)}
                          disabled={cancelandoCitaId === cita.id}
                          className="text-xs text-ink/60 hover:text-ink hover:underline disabled:opacity-50"
                        >
                          Cancelar
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {!esGrupal && reprogramandoCitaId === cita.id && (
                  <form
                    onSubmit={(e) => guardarReprogramacion(e, cita.id)}
                    className="flex flex-wrap items-end gap-3 border-t border-border/60 pt-3"
                  >
                    <CampoEditable etiqueta="Nueva fecha">
                      <Input
                        type="date"
                        required
                        value={formReprogramar.fecha}
                        onChange={(e) => setFormReprogramar((f) => ({ ...f, fecha: e.target.value }))}
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Nueva hora">
                      <Input
                        type="time"
                        required
                        value={formReprogramar.hora}
                        onChange={(e) => setFormReprogramar((f) => ({ ...f, hora: e.target.value }))}
                      />
                    </CampoEditable>
                    <Boton type="submit" disabled={guardandoReprogramacion}>
                      {guardandoReprogramacion ? "Guardando..." : "Guardar"}
                    </Boton>
                    <button
                      type="button"
                      onClick={() => setReprogramandoCitaId(null)}
                      className="text-xs text-ink/60 hover:text-ink hover:underline"
                    >
                      Cancelar edición
                    </button>
                  </form>
                )}
              </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Sección de Seguimiento / Sesiones Psicológicas */}
      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Historial de Sesiones de Seguimiento
        </h2>

        <TextoError>{errorSesiones}</TextoError>

        {seguimientos.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">No se han registrado sesiones de seguimiento clínico.</p>
        ) : (
          <div className="space-y-4">
            {seguimientos.map((sesion) => (
              <div key={sesion.id} className="p-5 rounded-card border border-border bg-white shadow-xs space-y-3">
                <div className="flex justify-between items-center border-b border-border/60 pb-2">
                  <span className="text-xs font-semibold text-ink/70">
                    Fecha de Sesión: {new Date(sesion.fecha).toLocaleDateString()}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="px-2.5 py-1 text-xs font-medium rounded-full bg-teal-400/20 text-teal-900">
                      {sesion.estado}
                    </span>
                    {editandoSesionId !== sesion.id && (
                      <button
                        onClick={() => abrirEditarSesion(sesion)}
                        className="text-xs text-teal-700 hover:underline"
                      >
                        Editar
                      </button>
                    )}
                  </div>
                </div>

                {editandoSesionId === sesion.id ? (
                  <form onSubmit={(e) => guardarEdicionSesion(e, sesion.id)} className="space-y-3">
                    <CampoEditable etiqueta="Observaciones de la sesión">
                      <Textarea
                        required
                        rows={4}
                        value={formSesion.observaciones}
                        onChange={(e) => setFormSesion((f) => ({ ...f, observaciones: e.target.value }))}
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Acción tomada">
                      <Textarea
                        rows={2}
                        value={formSesion.accion_tomada}
                        onChange={(e) => setFormSesion((f) => ({ ...f, accion_tomada: e.target.value }))}
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Acuerdos y compromisos">
                      <Textarea
                        rows={2}
                        value={formSesion.acuerdos_compromisos}
                        onChange={(e) => setFormSesion((f) => ({ ...f, acuerdos_compromisos: e.target.value }))}
                      />
                    </CampoEditable>
                    <div className="grid md:grid-cols-3 gap-4">
                      <CampoEditable etiqueta="Próxima cita — fecha">
                        <Input
                          type="date"
                          value={formSesion.proxima_cita_fecha}
                          onChange={(e) => setFormSesion((f) => ({ ...f, proxima_cita_fecha: e.target.value }))}
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Próxima cita — hora">
                        <Input
                          type="time"
                          value={formSesion.proxima_cita_hora}
                          onChange={(e) => setFormSesion((f) => ({ ...f, proxima_cita_hora: e.target.value }))}
                        />
                      </CampoEditable>
                      <CampoEditable etiqueta="Estado">
                        <Select
                          value={formSesion.estado}
                          onChange={(e) => setFormSesion((f) => ({ ...f, estado: e.target.value }))}
                        >
                          <option value="Pendiente">Pendiente</option>
                          <option value="En proceso">En proceso</option>
                          <option value="Atendido">Atendido</option>
                        </Select>
                      </CampoEditable>
                    </div>
                    <div className="flex items-center gap-3">
                      <Boton type="submit" disabled={guardandoSesion}>
                        {guardandoSesion ? "Guardando..." : "Guardar cambios"}
                      </Boton>
                      <button
                        type="button"
                        onClick={() => setEditandoSesionId(null)}
                        className="text-xs text-ink/60 hover:text-ink hover:underline"
                      >
                        Cancelar edición
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div className="grid md:grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="block font-medium text-teal-900">Observaciones:</span>
                        <p className="text-ink/80 mt-0.5 bg-mist p-2.5 rounded border border-border/50 text-xs leading-relaxed">
                          {sesion.observaciones || "Sin observaciones registradas."}
                        </p>
                      </div>

                      <div>
                        <span className="block font-medium text-teal-900">Acción Tomada:</span>
                        <p className="text-ink/80 mt-0.5 bg-mist p-2.5 rounded border border-border/50 text-xs leading-relaxed">
                          {sesion.accion_tomada || "Ninguna especificada."}
                        </p>
                      </div>
                    </div>

                    {sesion.acuerdos_compromisos && (
                      <div>
                        <span className="block text-sm font-medium text-teal-900">Acuerdos y Compromisos:</span>
                        <p className="text-xs text-ink/80 mt-0.5 bg-mist p-2.5 rounded border border-border/50">
                          {sesion.acuerdos_compromisos}
                        </p>
                      </div>
                    )}

                    {sesion.proxima_cita && (
                      <p className="text-xs text-ink/70">
                        Próxima cita: {new Date(sesion.proxima_cita).toLocaleString("es-PE")}
                      </p>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <VisorArchivoModal
        abierto={visorModalAbierto}
        onCerrar={cerrarVisorModal}
        archivo={visorModalArchivo}
        cargando={visorModalCargando}
        error={visorModalError}
        titulo={visorModalTitulo}
      />
    </div>
  );
}
