"use client";

import { useAvisoSinGuardar } from "@/lib/useAvisoSinGuardar";
import { useConfirmar } from "@/components/ui/DialogoConfirmacion";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  FileText,
  FilePen,
  FileCheck2,
  Users,
  History,
  Send,
  CheckCircle2,
  Circle,
  Eye,
  Download,
  Lock,
  Link2,
  Plus,
  X,
  ImagePlus,
  Lightbulb,
  ChevronDown,
  Loader2,
  ListChecks,
} from "lucide-react";
import { apiClient, descargarBlob, mensajeDe } from "@/lib/api-client";
import { ACENTOS } from "@/lib/acentos";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import { VacioFicha } from "@/components/educativo/BloqueFicha";
import { CabeceraInterna, Insignia, TarjetaLateral, BarraAvance, CampoFormulario } from "@/components/documentos/PiezasDocumento";
import { ETIQUETAS_TIPO_SECCION, ORIGEN_AUTOMATICA, MODO_TIPO_SECCION, instruccionPorDefecto } from "@/lib/documentos-constantes";
import { ChipModo, MiniaturaSeccion } from "@/components/documentos/ModoSeccion";
import { VisorArchivoModal, type ArchivoParaVisor } from "@/components/ui/VisorArchivo";
import { PanelVistaPrevia, useVistaPreviaPdf } from "@/components/documentos/VistaPreviaDocumento";
import { EditorTextoDocumento } from "@/components/documentos/EditorTextoDocumento";
import { useAuth } from "@/contexts/AuthContext";
import type {
  DocumentoInstitucionalDetalle,
  DocumentoInstitucionalSeccionContenido,
  DocumentoInstitucionalVersion,
  PlantillaSeccion,
  ReemitirDocumentoRequest,
  HistorialInformePersona,
  ResultadosPruebaMultipleRequest,
  TipoDocumento,
} from "@/types/api";
import { useCargaDiferida } from "@/lib/useCargaDiferida";
// 🆕 (sesión 2026-11-02) Los campos de `config`/`contenido` que esta página
// lee (antes `as any`). El backend guarda una forma libre por tipo_seccion
// (ver PlantillaSeccion.config en types/api.ts); aquí solo se describe lo usado.
type ConfigSeccion = {
  filas_desde_lista_estudiantes?: boolean;
  campos?: { etiqueta: string }[];
  columnas?: { titulo: string }[];
  // 🆕 (2026-11-17) Instrucción para quien llena, escrita en el constructor.
  ayuda?: string;
  // ficha_imprimible — solo para mostrar qué contiene el formato en blanco.
  campos_encabezado?: string[];
  listas_checkbox?: { titulo: string }[];
  preguntas_abiertas?: string[];
  firmas_en_blanco?: string[];
  filas?: string[];
};
type ContenidoImagenAnexo = { storage_key?: string; nombre_archivo?: string };


const VIOLETA = ACENTOS.violeta;

// Los 5 únicos campos "profesionales" de 'datos_filiacion' — todo lo demás
// de esa sección sale automático de la ficha del alumno, nunca se edita
// desde aquí (ver crud._resolver_datos_filiacion en el backend).
type EdicionFiliacion = {
  diagnostico_presuntivo: string;
  hijos: string;
  examinadora: string;
  fecha_elaboracion: string;
  periodo_propuesto: string;
};

const FILIACION_VACIA: EdicionFiliacion = { diagnostico_presuntivo: "", hijos: "", examinadora: "", fecha_elaboracion: "", periodo_propuesto: "" };

// Secciones que se completan solas al generar (de la ficha del alumno, del
// usuario que emite o de la propia plantilla) — no tienen nada que llenar
// acá y no cuentan para el avance.
const TIPOS_AUTOMATICOS = new Set(["encabezado", "datos_familiares", "firma", "firma_doble", "firma_triple", "ficha_imprimible"]);

// JSON con claves ordenadas: el backend guarda `contenido` en JSONB, que
// reordena las claves — sin esto "sin guardar" daría falsos positivos.
function estable(valor: unknown): string {
  if (Array.isArray(valor)) return `[${valor.map(estable).join(",")}]`;
  if (valor && typeof valor === "object") {
    return `{${Object.keys(valor as Record<string, unknown>)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${estable((valor as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(valor ?? null);
}

// Editor de contenido de UN DocumentoInstitucional — un formulario por
// sección según su tipo, generar/reemitir versión, historial y descarga.
//
// 🆕 Rediseño (sesión 2026-11-01): secciones numeradas a la izquierda con
// su estado (lista / por completar / automática / sin guardar) y una barra
// de avance; a la derecha, fija, la columna de emitir (generar, reemitir,
// descartar borrador), las versiones y los destinatarios. Las secciones de
// resultados muestran por fin QUÉ aplicación quedó vinculada (antes el
// vínculo no viajaba en la respuesta). Se conservan los textos que usa
// e2e/documentos.spec.ts: el <h1> con el título, el nombre del alumno UNA
// sola vez, "Guardar", "Generar versión 1", "v1 — fecha", "Descargar PDF",
// "Reemitir (v2)", el placeholder del motivo y "Confirmar reemisión".
export default function DetalleDocumentoPage() {
  // 🆕 Diálogo de confirmación propio (reemplaza window.confirm).
  const confirmar = useConfirmar();
  const params = useParams();
  const router = useRouter();
  const documentoId = params.id as string;

  const [documento, setDocumento] = useState<DocumentoInstitucionalDetalle | null>(null);
  const [secciones, setSecciones] = useState<DocumentoInstitucionalSeccionContenido[]>([]);
  const [definiciones, setDefiniciones] = useState<Record<number, PlantillaSeccion>>({});
  const [versiones, setVersiones] = useState<DocumentoInstitucionalVersion[]>([]);
  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [edicionesTexto, setEdicionesTexto] = useState<Record<number, string>>({});
  const [edicionesFiliacion, setEdicionesFiliacion] = useState<Record<number, EdicionFiliacion>>({});
  const [edicionesCampos, setEdicionesCampos] = useState<Record<number, Record<string, string>>>({});
  const [edicionesTablas, setEdicionesTablas] = useState<Record<number, Record<string, string>[]>>({});
  const [edicionesGrafico, setEdicionesGrafico] = useState<Record<number, { etiqueta: string; valor: string }[]>>({});
  const [edicionesResultadosMultiples, setEdicionesResultadosMultiples] = useState<Record<number, number[]>>({});
  const [guardandoSeccionId, setGuardandoSeccionId] = useState<number | null>(null);

  const [historialAlumno, setHistorialAlumno] = useState<HistorialInformePersona[]>([]);
  const [vinculandoSeccionId, setVinculandoSeccionId] = useState<number | null>(null);
  const [subiendoImagenId, setSubiendoImagenId] = useState<number | null>(null);

  const [generando, setGenerando] = useState(false);
  const [descartando, setDescartando] = useState(false);
  const [mostrarReemision, setMostrarReemision] = useState(false);
  const [motivoReemision, setMotivoReemision] = useState("");
  const [descargandoVersionId, setDescargandoVersionId] = useState<number | null>(null);
  const [visorAbierto, setVisorAbierto] = useState(false);
  const [visorArchivo, setVisorArchivo] = useState<ArchivoParaVisor | null>(null);
  const [visorCargando, setVisorCargando] = useState(false);
  const [visorError, setVisorError] = useState<string | null>(null);

  function cargar() {
    setError(null);
    Promise.all([
      apiClient.get<DocumentoInstitucionalDetalle>(`/documentos/${documentoId}`),
      apiClient.get<DocumentoInstitucionalSeccionContenido[]>(`/documentos/${documentoId}/secciones`),
      apiClient.get<DocumentoInstitucionalVersion[]>(`/documentos/${documentoId}/versiones`),
      apiClient.get<TipoDocumento[]>("/documentos/tipos").catch(() => [] as TipoDocumento[]),
    ])
      .then(async ([doc, seccionesResp, versionesResp, tiposResp]) => {
        setDocumento(doc);
        setSecciones(seccionesResp);
        setVersiones(versionesResp);
        setTipos(tiposResp);
        const defsResp = await apiClient.get<PlantillaSeccion[]>(`/documentos/plantillas/${doc.plantilla_documento_id}/secciones`);
        const defsPorId = Object.fromEntries(defsResp.map((d) => [d.id, d]));
        setDefiniciones(defsPorId);

        const textos: Record<number, string> = {};
        const filiacion: Record<number, EdicionFiliacion> = {};
        const campos: Record<number, Record<string, string>> = {};
        const tablas: Record<number, Record<string, string>[]> = {};
        const graficos: Record<number, { etiqueta: string; valor: string }[]> = {};
        const resultadosMultiples: Record<number, number[]> = {};
        seccionesResp.forEach((s) => {
          if (s.tipo_seccion === "texto_libre") {
            textos[s.plantilla_seccion_id] = (s.contenido?.texto as string) ?? "";
          } else if (s.tipo_seccion === "grupo_campos") {
            campos[s.plantilla_seccion_id] = (s.contenido?.valores as Record<string, string>) ?? {};
          } else if (s.tipo_seccion === "datos_filiacion") {
            const c = s.contenido ?? {};
            filiacion[s.plantilla_seccion_id] = {
              diagnostico_presuntivo: (c.diagnostico_presuntivo as string) ?? "",
              hijos: (c.hijos as string) ?? "",
              examinadora: (c.examinadora as string) ?? "",
              fecha_elaboracion: (c.fecha_elaboracion as string) ?? "",
              periodo_propuesto: (c.periodo_propuesto as string) ?? "",
            };
          } else if (s.tipo_seccion === "tabla_dinamica" && !(defsPorId[s.plantilla_seccion_id]?.config as ConfigSeccion | null | undefined)?.filas_desde_lista_estudiantes) {
            tablas[s.plantilla_seccion_id] = (s.contenido?.filas as Record<string, string>[]) ?? [];
          } else if (s.tipo_seccion === "grafico_barras") {
            const datos = (s.contenido?.datos as { etiqueta: string; valor: number }[]) ?? [];
            graficos[s.plantilla_seccion_id] = datos.map((d) => ({ etiqueta: d.etiqueta, valor: String(d.valor) }));
          } else if (s.tipo_seccion === "resultados_prueba_multiple") {
            resultadosMultiples[s.plantilla_seccion_id] = (s.contenido?.inscripcion_ids as number[]) ?? [];
          }
        });
        setEdicionesTexto(textos);
        setEdicionesFiliacion(filiacion);
        setEdicionesCampos(campos);
        setEdicionesTablas(tablas);
        setEdicionesGrafico(graficos);
        setEdicionesResultadosMultiples(resultadosMultiples);

        // Historial de aplicaciones reales del único alumno (para vincular
        // resultados_prueba/grafico_barras) — solo con exactamente uno.
        if (doc.estudiantes.length === 1) {
          apiClient
            .get<HistorialInformePersona[]>(`/educativo/personas/${doc.estudiantes[0].persona_id}/informes`)
            .then(setHistorialAlumno)
            .catch(() => setHistorialAlumno([]));
        }
      })
      .catch((err) => setError(err.message || "No se pudo cargar el documento."))
      .finally(() => setCargando(false));
  }

  useCargaDiferida(cargar, [documentoId]);

  function esTablaAutomatica(seccion: DocumentoInstitucionalSeccionContenido): boolean {
    return seccion.tipo_seccion === "tabla_dinamica" && !!(definiciones[seccion.plantilla_seccion_id]?.config as ConfigSeccion | null | undefined)?.filas_desde_lista_estudiantes;
  }

  function esAutomatica(seccion: DocumentoInstitucionalSeccionContenido): boolean {
    return TIPOS_AUTOMATICOS.has(seccion.tipo_seccion) || esTablaAutomatica(seccion);
  }

  // Lo que se enviaría al guardar esta sección (null = no se guarda por el
  // PUT genérico). Fuente única para guardarSeccion() y para "sin guardar".
  function contenidoEditado(seccion: DocumentoInstitucionalSeccionContenido): Record<string, unknown> | null {
    const id = seccion.plantilla_seccion_id;
    switch (seccion.tipo_seccion) {
      case "texto_libre":
        return { texto: edicionesTexto[id] ?? "" };
      case "grupo_campos":
        return { valores: edicionesCampos[id] ?? {} };
      case "datos_filiacion": {
        const f = edicionesFiliacion[id];
        return {
          diagnostico_presuntivo: f?.diagnostico_presuntivo || null,
          hijos: f?.hijos || null,
          examinadora: f?.examinadora || null,
          fecha_elaboracion: f?.fecha_elaboracion || null,
          periodo_propuesto: f?.periodo_propuesto || null,
        };
      }
      case "tabla_dinamica":
        return esTablaAutomatica(seccion) ? null : { filas: edicionesTablas[id] ?? [] };
      case "grafico_barras":
        return {
          datos: (edicionesGrafico[id] ?? []).filter((d) => d.etiqueta.trim()).map((d) => ({ etiqueta: d.etiqueta, valor: Number(d.valor) || 0 })),
        };
      default:
        return null;
    }
  }

  function sinGuardar(seccion: DocumentoInstitucionalSeccionContenido): boolean {
    const editado = contenidoEditado(seccion);
    if (!editado) return false;
    const guardado = seccion.contenido ?? null;
    // Una sección nunca tocada equivale a su versión "vacía".
    if (!guardado) {
      return Object.values(editado).some((v) => (Array.isArray(v) ? v.length > 0 : v && typeof v === "object" ? Object.values(v).some(Boolean) : !!v));
    }
    const comparable = Object.fromEntries(Object.keys(editado).map((k) => [k, (guardado as Record<string, unknown>)[k] ?? null]));
    return estable(editado) !== estable(comparable);
  }

  function estaCompleta(seccion: DocumentoInstitucionalSeccionContenido): boolean {
    const c = (seccion.contenido ?? {}) as Record<string, unknown>;
    switch (seccion.tipo_seccion) {
      case "texto_libre":
        return typeof c.texto === "string" && c.texto.trim().length > 0;
      case "grupo_campos":
        return Object.values((c.valores as Record<string, string>) ?? {}).some((v) => v && String(v).trim());
      case "datos_filiacion":
        return ["diagnostico_presuntivo", "hijos", "examinadora", "fecha_elaboracion", "periodo_propuesto"].some((k) => !!c[k]);
      case "tabla_dinamica":
        return Array.isArray(c.filas) && c.filas.length > 0;
      case "grafico_barras":
        return (Array.isArray(c.datos) && c.datos.length > 0) || (seccion.inscripciones_vinculadas?.length ?? 0) > 0;
      case "resultados_prueba":
        return (seccion.inscripciones_vinculadas?.length ?? 0) > 0;
      case "resultados_prueba_multiple":
        return (edicionesResultadosMultiples[seccion.plantilla_seccion_id]?.length ?? 0) > 0;
      case "imagen_anexo":
        return !!c.storage_key;
      default:
        return true;
    }
  }

  async function guardarSeccion(seccion: DocumentoInstitucionalSeccionContenido): Promise<boolean> {
    const contenido = contenidoEditado(seccion);
    if (!contenido) return true;
    setGuardandoSeccionId(seccion.plantilla_seccion_id);
    setError(null);
    try {
      const actualizado = await apiClient.put<DocumentoInstitucionalSeccionContenido>(
        `/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}`,
        { contenido },
      );
      setSecciones((prev) =>
        prev.map((s) =>
          s.plantilla_seccion_id === seccion.plantilla_seccion_id ? { ...actualizado, inscripciones_vinculadas: s.inscripciones_vinculadas } : s,
        ),
      );
      return true;
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo guardar esta sección.");
      return false;
    } finally {
      setGuardandoSeccionId(null);
    }
  }

  async function vincularAplicacion(seccion: DocumentoInstitucionalSeccionContenido, inscripcionId: number) {
    if (!documento || documento.estudiantes.length !== 1) return;
    setVinculandoSeccionId(seccion.plantilla_seccion_id);
    setError(null);
    try {
      await apiClient.put(`/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}/resultados-prueba`, {
        persona_id: documento.estudiantes[0].persona_id,
        inscripcion_id: inscripcionId,
      });
      cargar();
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo vincular la aplicación.");
    } finally {
      setVinculandoSeccionId(null);
    }
  }

  async function desvincularAplicacion(seccion: DocumentoInstitucionalSeccionContenido) {
    if (!documento || documento.estudiantes.length !== 1) return;
    setVinculandoSeccionId(seccion.plantilla_seccion_id);
    try {
      await apiClient.delete(
        `/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}/resultados-prueba/${documento.estudiantes[0].persona_id}`,
      );
      cargar();
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo desvincular.");
    } finally {
      setVinculandoSeccionId(null);
    }
  }

  // 'resultados_prueba_multiple' guarda una LISTA completa con su propio
  // endpoint (nunca el PUT genérico de contenido de sección).
  async function guardarResultadosMultiples(seccion: DocumentoInstitucionalSeccionContenido, inscripcionIds: number[]) {
    if (!documento || documento.estudiantes.length !== 1) return;
    setGuardandoSeccionId(seccion.plantilla_seccion_id);
    setError(null);
    try {
      const payload: ResultadosPruebaMultipleRequest = {
        persona_id: documento.estudiantes[0].persona_id,
        inscripcion_ids: inscripcionIds,
      };
      await apiClient.put(`/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}/resultados-prueba-multiple`, payload);
      setEdicionesResultadosMultiples({ ...edicionesResultadosMultiples, [seccion.plantilla_seccion_id]: inscripcionIds });
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo guardar la selección de resultados.");
    } finally {
      setGuardandoSeccionId(null);
    }
  }

  async function subirImagen(seccion: DocumentoInstitucionalSeccionContenido, archivo: File) {
    setSubiendoImagenId(seccion.plantilla_seccion_id);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const actualizado = await apiClient.postForm<DocumentoInstitucionalSeccionContenido>(
        `/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}/imagen`,
        fd,
      );
      setSecciones((prev) => prev.map((s) => (s.plantilla_seccion_id === seccion.plantilla_seccion_id ? actualizado : s)));
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo subir la imagen.");
    } finally {
      setSubiendoImagenId(null);
    }
  }

  // Solo para un borrador (version_actual null) — el backend responde 409
  // si ya se emitió. Soft-delete: ver crud.descartar_borrador_documento.
  async function descartarBorrador() {
    if (!documento) return;
    if (
      !(await confirmar({
        titulo: `¿Descartar el borrador «${documento.titulo}»?`,
        mensaje: "Se pierde lo que se haya escrito en él. Esta acción no se puede deshacer.",
        textoConfirmar: "Descartar borrador",
        peligro: true,
      }))
    )
      return;
    setDescartando(true);
    setError(null);
    try {
      await apiClient.delete(`/documentos/${documentoId}`);
      router.push("/documentos");
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo descartar el borrador.");
      setDescartando(false);
    }
  }

  async function generarOReemitir() {
    if (!documento) return;
    setGenerando(true);
    setError(null);
    // 🆕 Lo que esté sin guardar se guarda antes de emitir: el PDF sale del
    // contenido guardado, y antes había que acordarse de cada "Guardar".
    if (!(await guardarPendientes.current())) {
      setGenerando(false);
      setError("No se pudo guardar todo antes de generar. Revisa la conexión e inténtalo otra vez.");
      return;
    }
    try {
      const nuevaVersion =
        documento.version_actual === null
          ? await apiClient.post<DocumentoInstitucionalVersion>(`/documentos/${documentoId}/generar-version`)
          : await apiClient.post<DocumentoInstitucionalVersion>(`/documentos/${documentoId}/reemitir`, {
              motivo: motivoReemision,
            } as ReemitirDocumentoRequest);
      setDocumento({ ...documento, version_actual: nuevaVersion.numero_version });
      setVersiones((prev) => [...prev, nuevaVersion]);
      setMostrarReemision(false);
      setMotivoReemision("");
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo generar la versión.");
    } finally {
      setGenerando(false);
    }
  }

  async function descargar(version: DocumentoInstitucionalVersion) {
    setDescargandoVersionId(version.id);
    try {
      const blob = await apiClient.descargarArchivo(`/documentos/${documentoId}/versiones/${version.numero_version}/descargar`);
      descargarBlob(blob, version.nombre_archivo);
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo descargar el PDF.");
    } finally {
      setDescargandoVersionId(null);
    }
  }

  // "Ver" (react-pdf, ver components/ui/VisorArchivo.tsx) — mismo endpoint
  // que descargar(), pero abre el modal en vez de guardar a disco.
  async function ver(version: DocumentoInstitucionalVersion) {
    setVisorAbierto(true);
    setVisorArchivo(null);
    setVisorError(null);
    setVisorCargando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/documentos/${documentoId}/versiones/${version.numero_version}/descargar`);
      setVisorArchivo({ blob, contentType: "application/pdf", nombreArchivo: version.nombre_archivo });
    } catch (err) {
      setVisorError(mensajeDe(err) || "No se pudo cargar el PDF.");
    } finally {
      setVisorCargando(false);
    }
  }

  const ordenadas = useMemo(() => secciones.slice().sort((a, b) => a.orden - b.orden), [secciones]);

  // 🆕 (2026-11-17) Guardado automático: 1,5 s después de dejar de escribir
  // se guardan las secciones con cambios (antes había un "Guardar" por
  // sección y era fácil olvidarlo). La función vive en una ref para que el
  // temporizador use siempre el estado más reciente.
  const guardarPendientes = useRef<() => Promise<boolean>>(async () => true);
  useEffect(() => {
    guardarPendientes.current = async () => {
      let todoBien = true;
      for (const s of ordenadas) {
        if (!esAutomatica(s) && sinGuardar(s)) todoBien = (await guardarSeccion(s)) && todoBien;
      }
      return todoBien;
    };
  });
  const firmaEdiciones = JSON.stringify([edicionesTexto, edicionesCampos, edicionesFiliacion, edicionesTablas, edicionesGrafico]);
  useEffect(() => {
    if (cargando) return;
    const t = setTimeout(() => void guardarPendientes.current(), 1500);
    return () => clearTimeout(t);
  }, [firmaEdiciones, secciones, cargando]);
  const [soloPendientes, setSoloPendientes] = useState(false);
  // 🆕 Aviso al salir con secciones sin guardar (punto 5 del análisis de UI/UX).
  useAvisoSinGuardar(
    ordenadas.some((s) => !esAutomatica(s) && sinGuardar(s)),
    "Hay secciones del documento con cambios sin guardar; si sales ahora se perderán.",
  );
  // 🆕 (2026-11-18) Vista previa en vivo (components/documentos/VistaPreviaDocumento.tsx):
  // en pantallas anchas, el PDF del borrador al lado del formulario; se
  // puede ocultar (queda recordado en este navegador). En celular, un botón
  // la abre en el visor. Solo staff clínico (la ruta rechaza a colegio).
  const { sesion } = useAuth();
  const puedeVerVistaPrevia = sesion?.rol !== "colegio";
  const pantallaAncha = useSyncExternalStore(suscribirAncho, leerPantallaAncha, () => false);
  const [preferenciaVista, setPreferenciaVista] = useState<boolean>(leerPreferenciaVista);
  function cambiarPreferenciaVista(valor: boolean) {
    setPreferenciaVista(valor);
    try {
      window.localStorage.setItem(CLAVE_VISTA_PREVIA, valor ? "1" : "0");
    } catch {
      // sin almacenamiento: dura esta visita
    }
  }
  const mostrarVistaPrevia = puedeVerVistaPrevia && pantallaAncha && preferenciaVista;
  const hayCambiosSinGuardar = ordenadas.some((s) => !esAutomatica(s) && sinGuardar(s));
  const firmaVistaPrevia = useMemo(() => JSON.stringify(secciones), [secciones]);
  const vistaPrevia = useVistaPreviaPdf(
    documentoId,
    firmaVistaPrevia,
    guardandoSeccionId === null && !hayCambiosSinGuardar,
    mostrarVistaPrevia && !cargando && !!documento,
  );
  async function verVistaPreviaEnVisor() {
    // Antes de mostrarla, se guarda lo pendiente: así incluye lo último escrito.
    await guardarPendientes.current();
    setVisorAbierto(true);
    setVisorArchivo(null);
    setVisorError(null);
    setVisorCargando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/documentos/${documentoId}/vista-previa`);
      setVisorArchivo({ blob, contentType: "application/pdf", nombreArchivo: `vista_previa_${documentoId}.pdf` });
    } catch (err) {
      setVisorError(mensajeDe(err) || "No se pudo armar la vista previa.");
    } finally {
      setVisorCargando(false);
    }
  }

  const migas = [{ label: "Documentos", href: "/documentos" }, { label: "Documentos generados", href: "/documentos" }, { label: documento?.titulo ?? "Documento" }];

  if (cargando) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        <CabeceraInterna migas={migas} icono={FileText} titulo="Documento" />
        <EsqueletoLista cantidad={4} />
      </div>
    );
  }
  if (!documento) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        <TextoError>{error}</TextoError>
      </div>
    );
  }

  const puedeVincular = documento.estudiantes.length === 1;
  const borrador = documento.version_actual === null;
  const editables = ordenadas.filter((s) => !esAutomatica(s));
  const completas = editables.filter(estaCompleta).length;
  const pendientesDeGuardar = editables.filter(sinGuardar).length;
  const nombreTipo = tipos.find((t) => t.id === documento.tipo_documento_id)?.nombre;
  const versionesOrdenadas = versiones.slice().sort((a, b) => b.numero_version - a.numero_version);

  // Emitir, versiones y destinatarios: a la derecha, o debajo del formulario
  // cuando la derecha la ocupa la vista previa.
  const columnaLateral = (
    <div className={`flex flex-col gap-4 ${mostrarVistaPrevia ? "" : "lg:sticky lg:top-4"}`}>
    <TarjetaLateral icono={Send} titulo={borrador ? "Emitir documento" : "Reemitir"}>
      {borrador ? (
        <div className="space-y-3">
          <p className="text-[12.5px] text-ink/65 dark:text-ink-dark/60">
            Genera el PDF oficial con el contenido guardado. Después ya no se puede descartar; los cambios se emiten como una versión nueva.
          </p>
          {editables.length - completas > 0 && (
            <div className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2">
              <p className="text-[12px] font-semibold text-ink/70 dark:text-ink-dark/70">
                {editables.length - completas === 1 ? "Falta 1 parte por completar:" : `Faltan ${editables.length - completas} partes por completar:`}
              </p>
              <ul className="mt-1 list-none space-y-0.5 p-0">
                {editables
                  .filter((s) => !estaCompleta(s))
                  .map((s) => (
                    <li key={s.plantilla_seccion_id}>
                      <a
                        href={`#seccion-${s.plantilla_seccion_id}`}
                        className={`text-[12.5px] font-medium hover:underline ${VIOLETA.texto}`}
                      >
                        {s.titulo || ETIQUETAS_TIPO_SECCION[s.tipo_seccion]}
                      </a>
                    </li>
                  ))}
              </ul>
              <p className="mt-1 text-[11.5px] text-ink/65 dark:text-ink-dark/55">Puedes generar igual: las vacías salen en blanco.</p>
            </div>
          )}
          <Boton onClick={generarOReemitir} disabled={generando || descartando} className="w-full">
            {generando ? "Generando..." : "Generar versión 1"}
          </Boton>
          <button
            type="button"
            onClick={descartarBorrador}
            disabled={generando || descartando}
            className="w-full text-center text-[12.5px] font-medium text-red-700 dark:text-red-300 hover:underline disabled:opacity-40"
          >
            {descartando ? "Descartando..." : "Descartar borrador"}
          </button>
        </div>
      ) : mostrarReemision ? (
        <div className="space-y-2.5">
          <Input
            value={motivoReemision}
            onChange={(e) => setMotivoReemision(e.target.value)}
            placeholder="Motivo de la reemisión..."
            className="w-full"
          />
          <Boton onClick={generarOReemitir} disabled={generando || !motivoReemision} className="w-full">
            {generando ? "Generando..." : "Confirmar reemisión"}
          </Boton>
          <button
            type="button"
            onClick={() => setMostrarReemision(false)}
            className="w-full text-center text-[12.5px] text-ink/65 dark:text-ink-dark/55 hover:underline"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[12.5px] text-ink/65 dark:text-ink-dark/60">
            Para corregir algo, edita las secciones y reemite: se crea una versión nueva con su motivo y las anteriores se conservan.
          </p>
          <Boton onClick={() => setMostrarReemision(true)} className="w-full">
            Reemitir (v{(documento.version_actual ?? 0) + 1})
          </Boton>
        </div>
      )}
    </TarjetaLateral>

    {versionesOrdenadas.length > 0 && (
      <TarjetaLateral icono={History} titulo="Versiones">
        <ul className="p-0 list-none space-y-2">
          {versionesOrdenadas.map((v) => (
            <li key={v.id} className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2">
              <p className="text-[12.5px] font-semibold text-ink dark:text-ink-dark">
                v{v.numero_version} — {new Date(v.generado_en).toLocaleString("es-PE")}
              </p>
              {v.motivo_version && <p className="mt-0.5 text-[12px] text-ink/65 dark:text-ink-dark/55">{v.motivo_version}</p>}
              <div className="mt-1.5 flex items-center gap-3">
                <button type="button" onClick={() => ver(v)} className={`inline-flex items-center gap-1 text-xs font-semibold hover:underline ${VIOLETA.texto}`}>
                  <Eye size={12} aria-hidden="true" />
                  Ver
                </button>
                <button
                  type="button"
                  onClick={() => descargar(v)}
                  disabled={descargandoVersionId === v.id}
                  className={`inline-flex items-center gap-1 text-xs font-semibold hover:underline disabled:opacity-50 ${VIOLETA.texto}`}
                >
                  <Download size={12} aria-hidden="true" />
                  {descargandoVersionId === v.id ? "Descargando..." : "Descargar PDF"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      </TarjetaLateral>
    )}

    <TarjetaLateral icono={Users} titulo={documento.estudiantes.length === 1 ? "Alumno" : `Alumnos (${documento.estudiantes.length})`}>
      {documento.estudiantes.length === 0 ? (
        <p className="text-[12.5px] italic text-ink/65 dark:text-ink-dark/55">Sin estudiantes vinculados.</p>
      ) : (
        <ul className="p-0 list-none space-y-1.5 max-h-64 overflow-y-auto">
          {documento.estudiantes.map((e) => (
            <li key={e.persona_id} className="flex items-center justify-between gap-2 text-[13px]">
              <span className="min-w-0 truncate font-medium text-ink dark:text-ink-dark">{e.nombre_completo_historico}</span>
              {e.grado_seccion_historico && <span className="shrink-0 text-[12px] text-ink/65 dark:text-ink-dark/55">{e.grado_seccion_historico}</span>}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2.5 text-[12px] text-ink/65 dark:text-ink-dark/55">Lista congelada al crear el documento.</p>
    </TarjetaLateral>
  </div>
  );

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <CabeceraInterna
        migas={migas}
        icono={borrador ? FilePen : FileCheck2}
        titulo={documento.titulo}
        subtitulo={nombreTipo && <span>{nombreTipo}</span>}
        insignias={
          <>
            <Insignia variante={borrador ? "contorno" : "solida"}>{borrador ? "Borrador" : `Emitido v${documento.version_actual}`}</Insignia>
            <Insignia variante="suave" icono={Lock}>
              {documento.nivel_visibilidad === "compartible_colegio" ? "Compartible con el colegio" : "Confidencial clínico"}
            </Insignia>
          </>
        }
      />

      <TextoError>{error}</TextoError>

      <div
        className={`grid gap-4 items-start ${
          mostrarVistaPrevia ? "lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" : "lg:grid-cols-[minmax(0,1fr)_320px]"
        }`}
      >
        {/* ===== Secciones ===== */}
        <div className="flex flex-col gap-3 min-w-0">
          {/* 🆕 (2026-11-17) Guía corta + avance: qué se hace en esta pantalla. */}
          <div className={`rounded-xl border px-4 py-3.5 ${VIOLETA.fondoSuave}`}>
            <p className="flex items-center gap-1.5 text-[13.5px] font-bold text-ink dark:text-ink-dark">
              <ListChecks size={15} className={VIOLETA.texto} aria-hidden="true" />
              Cómo completar este documento
            </p>
            <ol className={`mt-2 grid list-none gap-2 p-0 text-[12.5px] leading-snug text-ink/70 dark:text-ink-dark/70 ${mostrarVistaPrevia ? "" : "sm:grid-cols-3"}`}>
              <li className="flex gap-2">
                <PasoGuia n={1} />
                <span>
                  Completa las partes marcadas <ChipModo modo="escribes" /> o <ChipModo modo="eliges" />. Cada una dice qué escribir.
                </span>
              </li>
              <li className="flex gap-2">
                <PasoGuia n={2} />
                <span>
                  Las partes <ChipModo modo="automatica" /> y <ChipModo modo="imprimir" /> no se tocan: salen solas en el PDF.
                </span>
              </li>
              <li className="flex gap-2">
                <PasoGuia n={3} />
                <span>Lo que escribes se guarda solo. Cuando termines, pulsa «{borrador ? "Generar versión 1" : "Reemitir"}» en el panel «{borrador ? "Emitir documento" : "Reemitir"}».</span>
              </li>
            </ol>
            {editables.length > 0 && (
              <div className="mt-3 border-t border-acento-violeta/15 pt-3 dark:border-acento-violeta-dark/20">
                <BarraAvance hechos={completas} total={editables.length} etiqueta="Partes que completas tú" />
                <div className="mt-2 flex items-center justify-between gap-3 flex-wrap">
                  <p className="text-[12px] text-ink/65 dark:text-ink-dark/55">
                    {guardandoSeccionId !== null
                      ? "Guardando…"
                      : pendientesDeGuardar > 0
                      ? "Hay cambios por guardar (se guardan solos en un momento)."
                      : "Todo lo escrito está guardado."}
                  </p>
                  <label className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink/70 dark:text-ink-dark/70 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={soloPendientes}
                      onChange={(e) => setSoloPendientes(e.target.checked)}
                      className="accent-[var(--color-acento-violeta)]"
                    />
                    Mostrar solo lo que me falta
                  </label>
                  {puedeVerVistaPrevia && !mostrarVistaPrevia && (
                    <button
                      type="button"
                      onClick={() => (pantallaAncha ? cambiarPreferenciaVista(true) : void verVistaPreviaEnVisor())}
                      className={`inline-flex items-center gap-1.5 text-[12.5px] font-semibold hover:underline ${VIOLETA.texto}`}
                    >
                      <Eye size={13} aria-hidden="true" />
                      {pantallaAncha ? "Mostrar cómo queda el PDF" : "Ver cómo queda el PDF"}
                    </button>
                  )}
                </div>
              </div>
            )}
            {!borrador && (
              <p className="mt-2 text-[12px] text-ink/65 dark:text-ink-dark/55">
                Lo que cambies aquí se incluye en la próxima versión al reemitir; las versiones ya emitidas no cambian.
              </p>
            )}
          </div>

          {ordenadas.length === 0 && (
            <VacioFicha icono={FileText} texto="La plantilla de este documento no tiene secciones todavía." />
          )}

          {ordenadas.map((seccion, idx) => {
            const id = seccion.plantilla_seccion_id;
            const automatica = esAutomatica(seccion);
            const completa = !automatica && estaCompleta(seccion);
            const pendiente = !automatica && sinGuardar(seccion);
            const guardando = guardandoSeccionId === id;
            const config = definiciones[id]?.config as ConfigSeccion | null | undefined;
            const titulo = seccion.titulo || ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion] || seccion.tipo_seccion;
            if (soloPendientes && (automatica || completa)) return null;

            // Partes que se llenan solas o se imprimen en blanco: una fila
            // compacta que dice de dónde sale, nunca una tarjeta vacía.
            if (automatica) {
              return (
                <SeccionAutomatica
                  key={id}
                  numero={idx + 1}
                  titulo={titulo}
                  tipo={seccion.tipo_seccion}
                  origen={
                    esTablaAutomatica(seccion)
                      ? "Una fila por cada alumno del documento, con sus datos. Se llena sola."
                      : ORIGEN_AUTOMATICA[seccion.tipo_seccion] ?? "Se completa sola al generar el PDF."
                  }
                  esTablaAutomatica={esTablaAutomatica(seccion)}
                  config={config ?? null}
                />
              );
            }

            const instruccion = config?.ayuda?.trim() || instruccionPorDefecto(seccion.tipo_seccion, seccion.titulo);
            return (
              <article
                key={id}
                id={`seccion-${id}`}
                className={`scroll-mt-24 rounded-xl border bg-surface dark:bg-surface-dark overflow-hidden ${
                  completa ? "border-border dark:border-border-dark" : "border-acento-violeta/35 dark:border-acento-violeta-dark/35"
                }`}
              >
                <header className="flex items-start gap-3 px-4 py-3 border-b border-border/70 dark:border-border-dark">
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold ${completa ? VIOLETA.chipSolido : VIOLETA.chip}`}
                    aria-hidden="true"
                  >
                    {completa ? <CheckCircle2 size={14} /> : idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-[14.5px] font-bold text-ink dark:text-ink-dark leading-tight">{titulo}</h3>
                    <div className="mt-1 flex items-center gap-1.5 flex-wrap">
                      <ChipModo modo={MODO_TIPO_SECCION[seccion.tipo_seccion] === "automatica" ? "escribes" : MODO_TIPO_SECCION[seccion.tipo_seccion]} />
                      {seccion.titulo && <span className="text-[12px] text-ink/65 dark:text-ink-dark/55">{ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion]}</span>}
                    </div>
                  </div>
                  <EstadoSeccion completa={completa} pendiente={pendiente} guardando={guardando} />
                </header>

                <div className="p-4 space-y-3">
                  {instruccion && (
                    <p className="flex items-start gap-2 rounded-lg bg-acento-violeta/[0.06] px-3 py-2 text-[13px] leading-snug text-ink/80 dark:bg-acento-violeta-dark/10 dark:text-ink-dark/80">
                      <Lightbulb size={14} className={`mt-0.5 shrink-0 ${VIOLETA.texto}`} aria-hidden="true" />
                      <span>{instruccion}</span>
                    </p>
                  )}

                  {seccion.tipo_seccion === "texto_libre" && (
                    <>
                      {/* 🆕 (2026-11-18) Editor con formato (negrita, cursiva,
                          subrayado, listas) en vez de un cuadro de texto con
                          **marcas**: se guarda el mismo formato que antes. */}
                      <EditorTextoDocumento
                        etiqueta={titulo}
                        valor={edicionesTexto[id] ?? ""}
                        onCambio={(texto) => setEdicionesTexto((prev) => ({ ...prev, [id]: texto }))}
                        onSalir={() => pendiente && guardarSeccion(seccion)}
                      />
                      <BotonGuardar onClick={() => guardarSeccion(seccion)} guardando={guardando} pendiente={pendiente} />
                    </>
                  )}

                  {seccion.tipo_seccion === "grupo_campos" && (
                    <>
                      <div className="grid sm:grid-cols-2 gap-3">
                        {(config?.campos ?? []).map((c: { etiqueta: string }) => (
                          <CampoFormulario key={c.etiqueta} etiqueta={c.etiqueta}>
                            <Input
                              value={edicionesCampos[id]?.[c.etiqueta] ?? ""}
                              placeholder={`Escribe ${c.etiqueta.toLowerCase()}`}
                              onChange={(e) => setEdicionesCampos({ ...edicionesCampos, [id]: { ...edicionesCampos[id], [c.etiqueta]: e.target.value } })}
                            />
                          </CampoFormulario>
                        ))}
                      </div>
                      <BotonGuardar onClick={() => guardarSeccion(seccion)} guardando={guardando} pendiente={pendiente} />
                    </>
                  )}

                  {seccion.tipo_seccion === "datos_filiacion" && (
                    <EditorDatosFiliacion
                      valores={edicionesFiliacion[id] ?? FILIACION_VACIA}
                      onCambiar={(v) => setEdicionesFiliacion({ ...edicionesFiliacion, [id]: v })}
                      onGuardar={() => guardarSeccion(seccion)}
                      guardando={guardando}
                      pendiente={pendiente}
                    />
                  )}

                  {seccion.tipo_seccion === "tabla_dinamica" && (
                    <EditorTablaLibre
                      columnas={(config?.columnas ?? []).map((c) => c.titulo)}
                      filas={edicionesTablas[id] ?? []}
                      onCambiar={(filas) => setEdicionesTablas({ ...edicionesTablas, [id]: filas })}
                      onGuardar={() => guardarSeccion(seccion)}
                      guardando={guardando}
                      pendiente={pendiente}
                    />
                  )}

                  {(seccion.tipo_seccion === "grafico_barras" || seccion.tipo_seccion === "resultados_prueba") && (
                    <EditorResultadoVinculable
                      tipo={seccion.tipo_seccion}
                      puedeVincular={puedeVincular}
                      historial={historialAlumno}
                      vinculadas={seccion.inscripciones_vinculadas ?? []}
                      vinculando={vinculandoSeccionId === id}
                      onVincular={(inscripcionId) => vincularAplicacion(seccion, inscripcionId)}
                      onDesvincular={() => desvincularAplicacion(seccion)}
                      valoresManual={edicionesGrafico[id] ?? []}
                      onCambiarManual={(v) => setEdicionesGrafico({ ...edicionesGrafico, [id]: v })}
                      onGuardarManual={() => guardarSeccion(seccion)}
                      guardando={guardando}
                      pendiente={pendiente}
                    />
                  )}

                  {seccion.tipo_seccion === "resultados_prueba_multiple" && (
                    <EditorResultadosMultiplesVinculables
                      puedeVincular={puedeVincular}
                      historial={historialAlumno}
                      guardando={guardando}
                      seleccionados={edicionesResultadosMultiples[id] ?? []}
                      onGuardar={(ids) => guardarResultadosMultiples(seccion, ids)}
                    />
                  )}

                  {seccion.tipo_seccion === "imagen_anexo" && (
                    <div className="flex items-center justify-between gap-3 flex-wrap rounded-lg border border-dashed border-border dark:border-border-dark px-3.5 py-3">
                      <div className="min-w-0 text-sm">
                        {(seccion.contenido as ContenidoImagenAnexo | null)?.storage_key ? (
                          <p className={`font-medium ${VIOLETA.texto}`}>{(seccion.contenido as ContenidoImagenAnexo | null)?.nombre_archivo ?? "Imagen cargada"}</p>
                        ) : (
                          <p className="text-ink/65 dark:text-ink-dark/55">Sin imagen todavía.</p>
                        )}
                        <p className="text-[12px] text-ink/65 dark:text-ink-dark/55">JPG o PNG. También puedes pegarla (Ctrl+V) con el foco en el botón.</p>
                      </div>
                      <label
                        className={claseBoton("secundario", "inline-flex items-center gap-1.5 !py-1.5 cursor-pointer")}
                        onPaste={(e) => {
                          const archivo = Array.from(e.clipboardData.files ?? []).find((f) => f.type.startsWith("image/"));
                          if (archivo) subirImagen(seccion, archivo);
                        }}
                        tabIndex={0}
                      >
                        <ImagePlus size={14} aria-hidden="true" />
                        {subiendoImagenId === id ? "Subiendo..." : (seccion.contenido as ContenidoImagenAnexo | null)?.storage_key ? "Cambiar imagen" : "Subir imagen"}
                        <input
                          type="file"
                          accept="image/jpeg,image/png"
                          className="sr-only"
                          disabled={subiendoImagenId === id}
                          onChange={(e) => e.target.files?.[0] && subirImagen(seccion, e.target.files[0])}
                        />
                      </label>
                    </div>
                  )}
                </div>
              </article>
            );
          })}

          {soloPendientes && editables.length > 0 && completas === editables.length && (
            <VacioFicha icono={CheckCircle2} texto="No te falta nada: todas las partes que completas tú tienen contenido." />
          )}
          {mostrarVistaPrevia && columnaLateral}
        </div>

        {/* ===== Columna derecha: vista previa en vivo, o el panel de emitir/versiones ===== */}
        {mostrarVistaPrevia ? (
          <PanelVistaPrevia
            vista={vistaPrevia}
            pendiente={hayCambiosSinGuardar || guardandoSeccionId !== null}
            onAmpliar={() => {
              if (!vistaPrevia.pdf) return;
              setVisorAbierto(true);
              setVisorError(null);
              setVisorCargando(false);
              setVisorArchivo({ blob: vistaPrevia.pdf, contentType: "application/pdf", nombreArchivo: `vista_previa_${documentoId}.pdf` });
            }}
            onOcultar={() => cambiarPreferenciaVista(false)}
          />
        ) : (
          columnaLateral
        )}
      </div>

      <VisorArchivoModal abierto={visorAbierto} onCerrar={() => setVisorAbierto(false)} archivo={visorArchivo} cargando={visorCargando} error={visorError} />
    </div>
  );
}

function EstadoSeccion({ completa, pendiente, guardando }: { completa: boolean; pendiente: boolean; guardando: boolean }) {
  if (guardando) {
    return (
      <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-mist dark:bg-surface-raised-dark px-2 py-0.5 text-[11.5px] font-semibold text-ink/65 dark:text-ink-dark/60">
        <Loader2 size={10} className="animate-spin" aria-hidden="true" />
        Guardando…
      </span>
    );
  }
  if (pendiente) {
    return (
      <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-mist dark:bg-surface-raised-dark px-2 py-0.5 text-[11.5px] font-semibold text-ink/65 dark:text-ink-dark/60">
        Sin guardar
      </span>
    );
  }
  return completa ? (
    <span className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${VIOLETA.chip}`}>
      <CheckCircle2 size={10} aria-hidden="true" />
      Lista
    </span>
  ) : (
    <span className="shrink-0 inline-flex items-center gap-1 rounded-full border border-dashed border-ink/25 dark:border-ink-dark/25 px-2 py-0.5 text-[11.5px] font-semibold text-ink/65 dark:text-ink-dark/55">
      <Circle size={9} aria-hidden="true" />
      Por completar
    </span>
  );
}

function PasoGuia({ n }: { n: number }) {
  return (
    <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${VIOLETA.chipSolido}`} aria-hidden="true">
      {n}
    </span>
  );
}

// 🆕 (2026-11-17) Una parte que no se llena aquí: fila compacta con su
// título, cómo se llena y de dónde sale. Para el formato en blanco, además,
// se puede ver qué contiene (antes aparecía como una tarjeta más, con un
// título como «Motivo de derivación» que invitaba a buscar dónde escribir).
function SeccionAutomatica({
  numero,
  titulo,
  tipo,
  origen,
  esTablaAutomatica,
  config,
}: {
  numero: number;
  titulo: string;
  tipo: DocumentoInstitucionalSeccionContenido["tipo_seccion"];
  origen: string;
  esTablaAutomatica: boolean;
  config: ConfigSeccion | null;
}) {
  const [abierta, setAbierta] = useState(false);
  const esImprimible = tipo === "ficha_imprimible";
  const partes = esImprimible
    ? [
        ...(config?.campos_encabezado ?? []).map((c) => `${c}: ______`),
        ...((config?.filas ?? []).length ? [`Tabla de ${(config?.filas ?? []).length} indicadores para marcar`] : []),
        ...(config?.listas_checkbox ?? []).map((l) => `Casilleros: ${l.titulo || "lista de opciones"}`),
        ...(config?.preguntas_abiertas ?? []).map((q) => `Pregunta: ${q}`),
        ...(config?.firmas_en_blanco ?? []).map((f) => `Firma: ${f}`),
      ]
    : [];
  return (
    <div className="rounded-xl border border-dashed border-border dark:border-border-dark bg-surface/50 dark:bg-surface-dark/40">
      <div className="flex items-start gap-3 px-4 py-2.5">
        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-mist text-[11.5px] font-bold text-ink/65 dark:bg-surface-raised-dark dark:text-ink-dark/55" aria-hidden="true">
          {numero}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[13.5px] font-semibold text-ink/75 dark:text-ink-dark/75">{titulo}</span>
            <ChipModo modo={esTablaAutomatica ? "automatica" : MODO_TIPO_SECCION[tipo]} />
          </div>
          <p className="mt-0.5 text-[12px] leading-snug text-ink/65 dark:text-ink-dark/55">{origen}</p>
          {esImprimible && partes.length > 0 && (
            <button
              type="button"
              onClick={() => setAbierta((v) => !v)}
              aria-expanded={abierta}
              className="mt-1 inline-flex items-center gap-1 text-[12px] font-semibold text-seccion-700 hover:underline dark:text-seccion-claro"
            >
              <ChevronDown size={12} className={`transition-transform ${abierta ? "rotate-180" : ""}`} aria-hidden="true" />
              {abierta ? "Ocultar qué contiene" : "Ver qué contiene el formato"}
            </button>
          )}
          {abierta && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12px] text-ink/65 dark:text-ink-dark/60">
              {partes.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
        </div>
        <MiniaturaSeccion tipo={tipo} className="hidden w-24 shrink-0 sm:block" />
      </div>
    </div>
  );
}

// 🆕 Con el guardado automático, el botón solo aparece mientras hay algo
// sin guardar (para quien prefiere guardar al instante).
function BotonGuardar({ onClick, guardando, pendiente, texto = "Guardar" }: { onClick: () => void; guardando: boolean; pendiente: boolean; texto?: string }) {
  if (!pendiente && !guardando) return null;
  return (
    <Boton onClick={onClick} disabled={guardando} variante="secundario" className="!py-1.5">
      {guardando ? "Guardando..." : texto}
    </Boton>
  );
}

// 'datos_filiacion' — nombre/sexo/fecha de nacimiento/documento/grado
// salen automáticos de la ficha del alumno (no se editan acá); estos 5
// campos son propios de ESTE documento, nunca de Persona.
function EditorDatosFiliacion({
  valores,
  onCambiar,
  onGuardar,
  guardando,
  pendiente,
}: {
  valores: EdicionFiliacion;
  onCambiar: (v: EdicionFiliacion) => void;
  onGuardar: () => void;
  guardando: boolean;
  pendiente: boolean;
}) {
  return (
    <>
      <CampoFormulario etiqueta="Diagnóstico presuntivo">
        <Textarea rows={2} value={valores.diagnostico_presuntivo} onChange={(e) => onCambiar({ ...valores, diagnostico_presuntivo: e.target.value })} />
      </CampoFormulario>
      <div className="grid sm:grid-cols-2 gap-3">
        <CampoFormulario etiqueta="Hijos">
          <Input value={valores.hijos} onChange={(e) => onCambiar({ ...valores, hijos: e.target.value })} placeholder="Ej. Ninguno" />
        </CampoFormulario>
        <CampoFormulario etiqueta="Examinadora">
          <Input value={valores.examinadora} onChange={(e) => onCambiar({ ...valores, examinadora: e.target.value })} />
        </CampoFormulario>
        <CampoFormulario etiqueta="Fecha de elaboración">
          <Input value={valores.fecha_elaboracion} onChange={(e) => onCambiar({ ...valores, fecha_elaboracion: e.target.value })} placeholder="Ej. 28 de septiembre de 2026" />
        </CampoFormulario>
        <CampoFormulario etiqueta="Periodo propuesto">
          <Input value={valores.periodo_propuesto} onChange={(e) => onCambiar({ ...valores, periodo_propuesto: e.target.value })} placeholder="Ej. Octubre–noviembre de 2026" />
        </CampoFormulario>
      </div>
      <BotonGuardar onClick={onGuardar} guardando={guardando} pendiente={pendiente} />
    </>
  );
}

function EditorTablaLibre({
  columnas,
  filas,
  onCambiar,
  onGuardar,
  guardando,
  pendiente,
}: {
  columnas: string[];
  filas: Record<string, string>[];
  onCambiar: (filas: Record<string, string>[]) => void;
  onGuardar: () => void;
  guardando: boolean;
  pendiente: boolean;
}) {
  if (columnas.length === 0) {
    return <p className="text-xs italic text-ink/65 dark:text-ink-dark/55">Esta tabla no tiene columnas configuradas en la plantilla.</p>;
  }
  return (
    <div className="space-y-2.5">
      <div className="overflow-x-auto rounded-lg border border-border dark:border-border-dark">
        <table className="w-full text-xs">
          <thead className="bg-acento-violeta/[0.06] dark:bg-acento-violeta-dark/[0.08]">
            <tr>
              {columnas.map((col) => (
                <th key={col} className="px-2.5 py-2 text-left font-semibold text-ink/70 dark:text-ink-dark/70">
                  {col}
                </th>
              ))}
              <th className="w-8" aria-label="Acciones" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border dark:divide-border-dark">
            {filas.map((fila, idxFila) => (
              <tr key={idxFila}>
                {columnas.map((col) => (
                  <td key={col} className="p-1">
                    <input
                      aria-label={col}
                      value={fila[col] ?? ""}
                      onChange={(e) => onCambiar(filas.map((f, i) => (i === idxFila ? { ...f, [col]: e.target.value } : f)))}
                      className="w-full min-w-[90px] rounded-md border border-transparent bg-transparent px-1.5 py-1 text-xs text-ink dark:text-ink-dark hover:border-border focus:border-acento-violeta focus:outline-none dark:hover:border-border-dark"
                    />
                  </td>
                ))}
                <td className="p-1 text-center">
                  <button
                    type="button"
                    aria-label="Quitar fila"
                    onClick={() => onCambiar(filas.filter((_, i) => i !== idxFila))}
                    className="rounded p-1 text-ink/65 hover:text-red-700 dark:text-ink-dark/55 dark:hover:text-red-300"
                  >
                    <X size={13} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
            {filas.length === 0 && (
              <tr>
                <td colSpan={columnas.length + 1} className="px-3 py-3 text-center italic text-ink/65 dark:text-ink-dark/55">
                  Sin filas todavía.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => onCambiar([...filas, {}])} className={`inline-flex items-center gap-1 text-xs font-semibold hover:underline ${VIOLETA.texto}`}>
          <Plus size={12} aria-hidden="true" />
          Agregar fila
        </button>
      </div>
      <BotonGuardar onClick={onGuardar} guardando={guardando} pendiente={pendiente} />
    </div>
  );
}

function FilaAplicacion({ h, derecha, marcada }: { h: HistorialInformePersona; derecha: React.ReactNode; marcada?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-[12.5px] ${
        marcada ? `${VIOLETA.fondo}` : "border-border dark:border-border-dark"
      }`}
    >
      <span className="min-w-0">
        <span className="font-semibold text-ink dark:text-ink-dark">{h.prueba_nombre_publico}</span>
        <span className="text-ink/65 dark:text-ink-dark/55">
          {" "}
          · {h.nombre_grupo}
          {h.fecha_aplicacion && ` · ${new Date(h.fecha_aplicacion).toLocaleDateString("es-PE")}`}
        </span>
        {/* Retenido = informe en riesgo aún sin revisar: ámbar, semántica clínica. */}
        {!h.informe_liberado && <span className="text-amber-800 dark:text-amber"> · retenido (no saldrá hasta liberarlo)</span>}
      </span>
      {derecha}
    </div>
  );
}

// 'grafico_barras': vinculado a una aplicación real o con valores
// manuales. 'resultados_prueba' solo admite el vínculo. 🆕 Ahora muestra
// cuál está vinculada (`vinculadas`, de la respuesta del backend).
function EditorResultadoVinculable({
  tipo,
  puedeVincular,
  historial,
  vinculadas,
  vinculando,
  onVincular,
  onDesvincular,
  valoresManual,
  onCambiarManual,
  onGuardarManual,
  guardando,
  pendiente,
}: {
  tipo: "grafico_barras" | "resultados_prueba";
  puedeVincular: boolean;
  historial: HistorialInformePersona[];
  vinculadas: number[];
  vinculando: boolean;
  onVincular: (inscripcionId: number) => void;
  onDesvincular: () => void;
  valoresManual: { etiqueta: string; valor: string }[];
  onCambiarManual: (v: { etiqueta: string; valor: string }[]) => void;
  onGuardarManual: () => void;
  guardando: boolean;
  pendiente: boolean;
}) {
  const vinculada = historial.find((h) => vinculadas.includes(h.inscripcion_id));
  const otras = historial.filter((h) => !vinculadas.includes(h.inscripcion_id));
  return (
    <div className="space-y-3 text-sm">
      {!puedeVincular ? (
        <p className="text-xs italic text-ink/65 dark:text-ink-dark/55">
          Solo se puede vincular una prueba cuando el documento es de un único alumno.
        </p>
      ) : (
        <div className="space-y-2">
          <p className="text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">Prueba vinculada</p>
          {vinculada ? (
            <FilaAplicacion
              h={vinculada}
              marcada
              derecha={
                <button type="button" disabled={vinculando} onClick={onDesvincular} className="shrink-0 text-xs font-semibold text-ink/65 dark:text-ink-dark/55 hover:text-red-700 hover:underline">
                  Quitar
                </button>
              }
            />
          ) : (
            <p className="text-xs text-ink/65 dark:text-ink-dark/55">{historial.length === 0 ? "Este alumno todavía no tiene ninguna prueba aplicada." : "Ninguna todavía. Elige una:"}</p>
          )}
          {otras.length > 0 && (
            <div className="space-y-1.5">
              {vinculada && <p className="text-[12px] text-ink/65 dark:text-ink-dark/55">Otras aplicaciones del alumno:</p>}
              {otras.map((h) => (
                <FilaAplicacion
                  key={h.inscripcion_id}
                  h={h}
                  derecha={
                    <button
                      type="button"
                      disabled={vinculando}
                      onClick={() => onVincular(h.inscripcion_id)}
                      className={`shrink-0 inline-flex items-center gap-1 text-xs font-semibold hover:underline disabled:opacity-50 ${VIOLETA.texto}`}
                    >
                      <Link2 size={12} aria-hidden="true" />
                      {vinculada ? "Usar esta" : "Vincular"}
                    </button>
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {tipo === "grafico_barras" && (
        <div className="space-y-2 border-t border-border dark:border-border-dark pt-3">
          <p className="text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">O valores manuales (si no hay una prueba vinculada)</p>
          {valoresManual.map((d, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                placeholder="Etiqueta"
                value={d.etiqueta}
                onChange={(e) => onCambiarManual(valoresManual.map((x, j) => (j === i ? { ...x, etiqueta: e.target.value } : x)))}
                className="flex-1 !py-1.5 text-xs"
              />
              <Input
                type="number"
                placeholder="Valor"
                value={d.valor}
                onChange={(e) => onCambiarManual(valoresManual.map((x, j) => (j === i ? { ...x, valor: e.target.value } : x)))}
                className="w-24 !py-1.5 text-xs"
              />
              <button
                type="button"
                aria-label="Quitar punto"
                onClick={() => onCambiarManual(valoresManual.filter((_, j) => j !== i))}
                className="rounded p-1 text-ink/65 hover:text-red-700 dark:text-ink-dark/55 dark:hover:text-red-300"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => onCambiarManual([...valoresManual, { etiqueta: "", valor: "" }])}
            className={`inline-flex items-center gap-1 text-xs font-semibold hover:underline ${VIOLETA.texto}`}
          >
            <Plus size={12} aria-hidden="true" />
            Agregar punto
          </button>
          <div>
            <BotonGuardar onClick={onGuardarManual} guardando={guardando} pendiente={pendiente} texto="Guardar valores manuales" />
          </div>
        </div>
      )}
    </div>
  );
}

// 'resultados_prueba_multiple' — consolida una cantidad VARIABLE de
// aplicaciones reales: casillas sobre el mismo historial y un solo
// "Guardar selección" que reemplaza la lista completa.
function EditorResultadosMultiplesVinculables({
  puedeVincular,
  historial,
  guardando,
  seleccionados,
  onGuardar,
}: {
  puedeVincular: boolean;
  historial: HistorialInformePersona[];
  guardando: boolean;
  seleccionados: number[];
  onGuardar: (inscripcionIds: number[]) => void;
}) {
  const [marcados, setMarcados] = useState<number[]>(seleccionados);

  // El historial puede llegar después del primer render — sincroniza
  // cuando cambia lo ya guardado en el servidor, sin pisar una selección
  // que el usuario esté armando a mano. 🆕 (sesión 2026-11-02) Ajuste durante
  // el render ("storing information from previous renders", react.dev) en
  // vez de un efecto con setState (lint react-hooks/set-state-in-effect).
  const claveSeleccionados = seleccionados.join(",");
  const [claveAnterior, setClaveAnterior] = useState(claveSeleccionados);
  if (claveSeleccionados !== claveAnterior) {
    setClaveAnterior(claveSeleccionados);
    setMarcados(seleccionados);
  }

  if (!puedeVincular) {
    return <p className="text-xs italic text-ink/65 dark:text-ink-dark/55">Solo se puede usar cuando el documento es de un único alumno.</p>;
  }

  function alternar(inscripcionId: number) {
    setMarcados((prev) => (prev.includes(inscripcionId) ? prev.filter((id) => id !== inscripcionId) : [...prev, inscripcionId]));
  }

  const cambio = marcados.slice().sort().join(",") !== seleccionados.slice().sort().join(",");

  return (
    <div className="space-y-2 text-sm">
      <p className="text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">
        Pruebas a consolidar <span className="font-normal text-ink/65 dark:text-ink-dark/55">({marcados.length} elegidas)</span>
      </p>
      {historial.length === 0 ? (
        <p className="text-xs italic text-ink/65 dark:text-ink-dark/55">Este alumno todavía no tiene ninguna prueba aplicada.</p>
      ) : (
        <div className="space-y-1.5">
          {historial.map((h) => (
            <label key={h.inscripcion_id} className="block cursor-pointer">
              <FilaAplicacion
                h={h}
                marcada={marcados.includes(h.inscripcion_id)}
                derecha={
                  <input
                    type="checkbox"
                    checked={marcados.includes(h.inscripcion_id)}
                    onChange={() => alternar(h.inscripcion_id)}
                    className="shrink-0 accent-[var(--color-acento-violeta)]"
                  />
                }
              />
            </label>
          ))}
        </div>
      )}
      <Boton onClick={() => onGuardar(marcados)} disabled={guardando} variante={cambio ? "primario" : "secundario"} className="!py-1.5">
        {guardando ? "Guardando..." : "Guardar selección"}
      </Boton>
    </div>
  );
}

// 🆕 (2026-11-18) Preferencia de la vista previa y ancho de pantalla.
const CLAVE_VISTA_PREVIA = "aurora.documento.vista-previa";

function leerPreferenciaVista(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(CLAVE_VISTA_PREVIA) !== "0";
  } catch {
    return true;
  }
}

function leerPantallaAncha(): boolean {
  return window.matchMedia("(min-width: 1024px)").matches;
}

function suscribirAncho(alCambiar: () => void) {
  const consulta = window.matchMedia("(min-width: 1024px)");
  consulta.addEventListener("change", alCambiar);
  return () => consulta.removeEventListener("change", alCambiar);
}
