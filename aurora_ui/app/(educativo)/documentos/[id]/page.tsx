"use client";

import { useAvisoSinGuardar } from "@/lib/useAvisoSinGuardar";
import { useConfirmar } from "@/components/ui/DialogoConfirmacion";
import { useEffect, useMemo, useState } from "react";
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
  Wand2,
  Eye,
  Download,
  Lock,
  Link2,
  Plus,
  X,
  ImagePlus,
  Info,
} from "lucide-react";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { ACENTOS } from "@/lib/acentos";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import { VacioFicha } from "@/components/educativo/BloqueFicha";
import { CabeceraInterna, Insignia, TarjetaLateral, BarraAvance, CampoFormulario } from "@/components/documentos/PiezasDocumento";
import { ETIQUETAS_TIPO_SECCION, DESCRIPCION_TIPO_SECCION } from "@/lib/documentos-constantes";
import { VisorArchivoModal, type ArchivoParaVisor } from "@/components/ui/VisorArchivo";
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
          } else if (s.tipo_seccion === "tabla_dinamica" && !(defsPorId[s.plantilla_seccion_id]?.config as any)?.filas_desde_lista_estudiantes) {
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

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documentoId]);

  function esTablaAutomatica(seccion: DocumentoInstitucionalSeccionContenido): boolean {
    return seccion.tipo_seccion === "tabla_dinamica" && !!(definiciones[seccion.plantilla_seccion_id]?.config as any)?.filas_desde_lista_estudiantes;
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

  async function guardarSeccion(seccion: DocumentoInstitucionalSeccionContenido) {
    const contenido = contenidoEditado(seccion);
    if (!contenido) return;
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
    } catch (err: any) {
      setError(err.message || "No se pudo guardar esta sección.");
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
    } catch (err: any) {
      setError(err.message || "No se pudo vincular la aplicación.");
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
    } catch (err: any) {
      setError(err.message || "No se pudo desvincular.");
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
    } catch (err: any) {
      setError(err.message || "No se pudo guardar la selección de resultados.");
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
    } catch (err: any) {
      setError(err.message || "No se pudo subir la imagen.");
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
    } catch (err: any) {
      setError(err.message || "No se pudo descartar el borrador.");
      setDescartando(false);
    }
  }

  async function generarOReemitir() {
    if (!documento) return;
    setGenerando(true);
    setError(null);
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
    } catch (err: any) {
      setError(err.message || "No se pudo generar la versión.");
    } finally {
      setGenerando(false);
    }
  }

  async function descargar(version: DocumentoInstitucionalVersion) {
    setDescargandoVersionId(version.id);
    try {
      const blob = await apiClient.descargarArchivo(`/documentos/${documentoId}/versiones/${version.numero_version}/descargar`);
      descargarBlob(blob, version.nombre_archivo);
    } catch (err: any) {
      setError(err.message || "No se pudo descargar el PDF.");
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
    } catch (err: any) {
      setVisorError(err.message || "No se pudo cargar el PDF.");
    } finally {
      setVisorCargando(false);
    }
  }

  const ordenadas = useMemo(() => secciones.slice().sort((a, b) => a.orden - b.orden), [secciones]);
  // 🆕 Aviso al salir con secciones sin guardar (punto 5 del análisis de UI/UX).
  useAvisoSinGuardar(
    ordenadas.some((s) => !esAutomatica(s) && sinGuardar(s)),
    "Hay secciones del documento con cambios sin guardar; si sales ahora se perderán.",
  );
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

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
        {/* ===== Secciones ===== */}
        <div className="flex flex-col gap-3 min-w-0">
          {editables.length > 0 && (
            <div className={`rounded-xl border px-4 py-3 ${VIOLETA.fondoSuave}`}>
              <BarraAvance hechos={completas} total={editables.length} etiqueta="Secciones con contenido" />
              {pendientesDeGuardar > 0 && (
                <p className="m-0 mt-2 text-[12px] font-medium text-red-700 dark:text-red-300">
                  {pendientesDeGuardar === 1 ? "1 sección tiene cambios sin guardar." : `${pendientesDeGuardar} secciones tienen cambios sin guardar.`}
                </p>
              )}
              {!borrador && (
                <p className="m-0 mt-2 text-[12px] text-ink/50 dark:text-ink-dark/50">
                  Lo que cambies aquí se incluye en la próxima versión al reemitir; las versiones emitidas no cambian.
                </p>
              )}
            </div>
          )}

          {ordenadas.length === 0 && (
            <VacioFicha icono={FileText} texto="La plantilla de este documento no tiene secciones todavía." />
          )}

          {ordenadas.map((seccion, idx) => {
            const id = seccion.plantilla_seccion_id;
            const automatica = esAutomatica(seccion);
            const completa = !automatica && estaCompleta(seccion);
            const pendiente = !automatica && sinGuardar(seccion);
            const guardando = guardandoSeccionId === id;
            return (
              <article key={id} className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark overflow-hidden">
                <header className="flex items-start gap-3 px-4 py-3 border-b border-border/70 dark:border-border-dark">
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold ${
                      automatica ? "bg-mist text-ink/45 dark:bg-surface-raised-dark dark:text-ink-dark/50" : completa ? VIOLETA.chipSolido : VIOLETA.chip
                    }`}
                    aria-hidden="true"
                  >
                    {completa ? <CheckCircle2 size={14} /> : idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="m-0 text-[14px] font-bold text-ink dark:text-ink-dark leading-tight">
                      {seccion.titulo || ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion] || seccion.tipo_seccion}
                    </h3>
                    <p className="m-0 mt-0.5 text-[12px] text-ink/45 dark:text-ink-dark/45">
                      {seccion.titulo ? `${ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion]} · ` : ""}
                      {automatica && !esTablaAutomatica(seccion)
                        ? DESCRIPCION_TIPO_SECCION[seccion.tipo_seccion]
                        : esTablaAutomatica(seccion)
                        ? "Una fila por cada alumno del documento. Se llena sola."
                        : null}
                    </p>
                  </div>
                  <EstadoSeccion automatica={automatica} completa={completa} pendiente={pendiente} />
                </header>

                {!automatica && (
                  <div className="p-4 space-y-3">
                    {seccion.tipo_seccion === "texto_libre" && (
                      <>
                        <Textarea
                          rows={5}
                          value={edicionesTexto[id] ?? ""}
                          onChange={(e) => setEdicionesTexto({ ...edicionesTexto, [id]: e.target.value })}
                          className="w-full leading-relaxed"
                        />
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <button
                            type="button"
                            title="Agrega una línea nueva que empieza con viñeta (•) — se imprime como punto en el PDF"
                            onClick={() => {
                              const actual = edicionesTexto[id] ?? "";
                              const separador = actual && !actual.endsWith("\n") ? "\n" : "";
                              setEdicionesTexto({ ...edicionesTexto, [id]: `${actual}${separador}• ` });
                            }}
                            className={`text-xs font-semibold hover:underline ${VIOLETA.texto}`}
                          >
                            • Agregar viñeta
                          </button>
                          <span className="text-[12px] text-ink/40 dark:text-ink-dark/40">
                            <code className="font-mono">**así**</code> sale en <strong>negrita</strong> en el PDF
                          </span>
                        </div>
                        <BotonGuardar onClick={() => guardarSeccion(seccion)} guardando={guardando} pendiente={pendiente} />
                      </>
                    )}

                    {seccion.tipo_seccion === "grupo_campos" && (
                      <>
                        <div className="grid sm:grid-cols-2 gap-3">
                          {((definiciones[id]?.config as any)?.campos ?? []).map((c: { etiqueta: string }) => (
                            <CampoFormulario key={c.etiqueta} etiqueta={c.etiqueta}>
                              <Input
                                value={edicionesCampos[id]?.[c.etiqueta] ?? ""}
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
                        columnas={((definiciones[id]?.config as any)?.columnas ?? []).map((c: any) => c.titulo)}
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
                          {(seccion.contenido as any)?.storage_key ? (
                            <p className={`m-0 font-medium ${VIOLETA.texto}`}>{(seccion.contenido as any)?.nombre_archivo ?? "Imagen cargada"}</p>
                          ) : (
                            <p className="m-0 text-ink/50 dark:text-ink-dark/50">Sin imagen todavía.</p>
                          )}
                          <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">JPG o PNG. También puedes pegarla (Ctrl+V) con el foco en el botón.</p>
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
                          {subiendoImagenId === id ? "Subiendo..." : (seccion.contenido as any)?.storage_key ? "Cambiar imagen" : "Subir imagen"}
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
                )}
              </article>
            );
          })}
        </div>

        {/* ===== Columna lateral ===== */}
        <div className="flex flex-col gap-4 lg:sticky lg:top-4">
          <TarjetaLateral icono={Send} titulo={borrador ? "Emitir documento" : "Reemitir"}>
            {borrador ? (
              <div className="space-y-3">
                <p className="m-0 text-[12.5px] text-ink/60 dark:text-ink-dark/60">
                  Genera el PDF oficial con el contenido guardado. Después ya no se puede descartar; los cambios se emiten como una versión nueva.
                </p>
                {pendientesDeGuardar > 0 && (
                  <p className="m-0 text-[12px] font-medium text-red-700 dark:text-red-300">Guarda los cambios pendientes antes de generar.</p>
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
                  className="w-full text-center text-[12.5px] text-ink/55 dark:text-ink-dark/55 hover:underline"
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="m-0 text-[12.5px] text-ink/60 dark:text-ink-dark/60">
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
              <ul className="m-0 p-0 list-none space-y-2">
                {versionesOrdenadas.map((v) => (
                  <li key={v.id} className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2">
                    <p className="m-0 text-[12.5px] font-semibold text-ink dark:text-ink-dark">
                      v{v.numero_version} — {new Date(v.generado_en).toLocaleString("es-PE")}
                    </p>
                    {v.motivo_version && <p className="m-0 mt-0.5 text-[12px] text-ink/50 dark:text-ink-dark/50">{v.motivo_version}</p>}
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
              <p className="m-0 text-[12.5px] italic text-ink/50 dark:text-ink-dark/50">Sin estudiantes vinculados.</p>
            ) : (
              <ul className="m-0 p-0 list-none space-y-1.5 max-h-64 overflow-y-auto">
                {documento.estudiantes.map((e) => (
                  <li key={e.persona_id} className="flex items-center justify-between gap-2 text-[13px]">
                    <span className="min-w-0 truncate font-medium text-ink dark:text-ink-dark">{e.nombre_completo_historico}</span>
                    {e.grado_seccion_historico && <span className="shrink-0 text-[12px] text-ink/45 dark:text-ink-dark/45">{e.grado_seccion_historico}</span>}
                  </li>
                ))}
              </ul>
            )}
            <p className="m-0 mt-2.5 text-[12px] text-ink/40 dark:text-ink-dark/40">Lista congelada al crear el documento.</p>
          </TarjetaLateral>
        </div>
      </div>

      <VisorArchivoModal abierto={visorAbierto} onCerrar={() => setVisorAbierto(false)} archivo={visorArchivo} cargando={visorCargando} error={visorError} />
    </div>
  );
}

function EstadoSeccion({ automatica, completa, pendiente }: { automatica: boolean; completa: boolean; pendiente: boolean }) {
  if (automatica) {
    return (
      <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-mist dark:bg-surface-raised-dark px-2 py-0.5 text-[11.5px] font-semibold text-ink/50 dark:text-ink-dark/55">
        <Wand2 size={10} aria-hidden="true" />
        Automática
      </span>
    );
  }
  if (pendiente) {
    return (
      <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-red-50 dark:bg-red-500/15 px-2 py-0.5 text-[11.5px] font-semibold text-red-700 dark:text-red-300">
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
    <span className="shrink-0 inline-flex items-center gap-1 rounded-full border border-dashed border-ink/25 dark:border-ink-dark/25 px-2 py-0.5 text-[11.5px] font-semibold text-ink/50 dark:text-ink-dark/55">
      <Circle size={9} aria-hidden="true" />
      Por completar
    </span>
  );
}

function BotonGuardar({ onClick, guardando, pendiente, texto = "Guardar" }: { onClick: () => void; guardando: boolean; pendiente: boolean; texto?: string }) {
  return (
    <Boton onClick={onClick} disabled={guardando} variante={pendiente ? "primario" : "secundario"} className="!py-1.5">
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
      <p className="m-0 flex items-start gap-1.5 text-[12px] text-ink/50 dark:text-ink-dark/50">
        <Info size={12} className="mt-px shrink-0" aria-hidden="true" />
        Nombre, edad, documento y grado salen solos de la ficha del alumno. Aquí completas solo estos campos.
      </p>
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
    return <p className="m-0 text-xs italic text-ink/50 dark:text-ink-dark/50">Esta tabla no tiene columnas configuradas en la plantilla.</p>;
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
                    className="rounded p-1 text-ink/35 hover:text-red-700 dark:text-ink-dark/35 dark:hover:text-red-300"
                  >
                    <X size={13} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
            {filas.length === 0 && (
              <tr>
                <td colSpan={columnas.length + 1} className="px-3 py-3 text-center italic text-ink/40 dark:text-ink-dark/40">
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
        <span className="text-ink/50 dark:text-ink-dark/50">
          {" "}
          · {h.nombre_grupo}
          {h.fecha_aplicacion && ` · ${new Date(h.fecha_aplicacion).toLocaleDateString("es-PE")}`}
        </span>
        {/* Retenido = informe en riesgo aún sin revisar: ámbar, semántica clínica. */}
        {!h.informe_liberado && <span className="text-amber-700 dark:text-amber"> · retenido (no saldrá hasta liberarlo)</span>}
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
        <p className="m-0 text-xs italic text-ink/50 dark:text-ink-dark/50">
          Solo se puede vincular una prueba cuando el documento es de un único alumno.
        </p>
      ) : (
        <div className="space-y-2">
          <p className="m-0 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">Prueba vinculada</p>
          {vinculada ? (
            <FilaAplicacion
              h={vinculada}
              marcada
              derecha={
                <button type="button" disabled={vinculando} onClick={onDesvincular} className="shrink-0 text-xs font-semibold text-ink/55 dark:text-ink-dark/55 hover:text-red-700 hover:underline">
                  Quitar
                </button>
              }
            />
          ) : (
            <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">{historial.length === 0 ? "Este alumno todavía no tiene ninguna prueba aplicada." : "Ninguna todavía. Elige una:"}</p>
          )}
          {otras.length > 0 && (
            <div className="space-y-1.5">
              {vinculada && <p className="m-0 text-[12px] text-ink/45 dark:text-ink-dark/45">Otras aplicaciones del alumno:</p>}
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
          <p className="m-0 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">O valores manuales (si no hay una prueba vinculada)</p>
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
                className="rounded p-1 text-ink/35 hover:text-red-700 dark:text-ink-dark/35 dark:hover:text-red-300"
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
  // que el usuario esté armando a mano.
  useEffect(() => {
    setMarcados(seleccionados);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seleccionados.join(",")]);

  if (!puedeVincular) {
    return <p className="m-0 text-xs italic text-ink/50 dark:text-ink-dark/50">Solo se puede usar cuando el documento es de un único alumno.</p>;
  }

  function alternar(inscripcionId: number) {
    setMarcados((prev) => (prev.includes(inscripcionId) ? prev.filter((id) => id !== inscripcionId) : [...prev, inscripcionId]));
  }

  const cambio = marcados.slice().sort().join(",") !== seleccionados.slice().sort().join(",");

  return (
    <div className="space-y-2 text-sm">
      <p className="m-0 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">
        Pruebas a consolidar <span className="font-normal text-ink/45 dark:text-ink-dark/45">({marcados.length} elegidas)</span>
      </p>
      {historial.length === 0 ? (
        <p className="m-0 text-xs italic text-ink/50 dark:text-ink-dark/50">Este alumno todavía no tiene ninguna prueba aplicada.</p>
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
