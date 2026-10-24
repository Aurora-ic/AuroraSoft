"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { ETIQUETAS_TIPO_SECCION } from "@/lib/documentos-constantes";
import { VisorArchivoModal, type ArchivoParaVisor } from "@/components/ui/VisorArchivo";
import { Migas } from "@/components/ui/Migas";
import type {
  DocumentoInstitucionalDetalle,
  DocumentoInstitucionalSeccionContenido,
  DocumentoInstitucionalVersion,
  PlantillaSeccion,
  ReemitirDocumentoRequest,
  HistorialInformePersona,
  ResultadosPruebaMultipleRequest,
} from "@/types/api";

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

// Editor de contenido de UN DocumentoInstitucional — un formulario por
// sección según su tipo (texto libre con viñetas, cuadro de campos, tabla
// libre, gráfico de barras manual o vinculado a una aplicación real,
// resultados de una o de VARIAS pruebas consolidadas, imagen/anexo
// subida), generar/reemitir versión, historial y descarga.
export default function DetalleDocumentoPage() {
  const params = useParams();
  const documentoId = params.id as string;

  const [documento, setDocumento] = useState<DocumentoInstitucionalDetalle | null>(null);
  const [secciones, setSecciones] = useState<DocumentoInstitucionalSeccionContenido[]>([]);
  const [definiciones, setDefiniciones] = useState<Record<number, PlantillaSeccion>>({});
  const [versiones, setVersiones] = useState<DocumentoInstitucionalVersion[]>([]);
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
  const [mostrarReemision, setMostrarReemision] = useState(false);
  const [motivoReemision, setMotivoReemision] = useState("");
  const [descargandoVersionId, setDescargandoVersionId] = useState<number | null>(null);
  const [visorAbierto, setVisorAbierto] = useState(false);
  const [visorArchivo, setVisorArchivo] = useState<ArchivoParaVisor | null>(null);
  const [visorCargando, setVisorCargando] = useState(false);
  const [visorError, setVisorError] = useState<string | null>(null);

  function cargar() {
    setCargando(true);
    setError(null);
    Promise.all([
      apiClient.get<DocumentoInstitucionalDetalle>(`/documentos/${documentoId}`),
      apiClient.get<DocumentoInstitucionalSeccionContenido[]>(`/documentos/${documentoId}/secciones`),
      apiClient.get<DocumentoInstitucionalVersion[]>(`/documentos/${documentoId}/versiones`),
    ])
      .then(async ([doc, seccionesResp, versionesResp]) => {
        setDocumento(doc);
        setSecciones(seccionesResp);
        setVersiones(versionesResp);
        const defsResp = await apiClient.get<PlantillaSeccion[]>(`/documentos/plantillas/${doc.plantilla_documento_id}/secciones`);
        setDefiniciones(Object.fromEntries(defsResp.map((d) => [d.id, d])));

        const textos: Record<number, string> = {};
        const filiacion: Record<number, EdicionFiliacion> = {};
        const campos: Record<number, Record<string, string>> = {};
        const tablas: Record<number, Record<string, string>[]> = {};
        const graficos: Record<number, { etiqueta: string; valor: string }[]> = {};
        const resultadosMultiples: Record<number, number[]> = {};
        const defsPorId = Object.fromEntries(defsResp.map((d) => [d.id, d]));
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
          } else if (
            s.tipo_seccion === "tabla_dinamica" &&
            !(defsPorId[s.plantilla_seccion_id]?.config as any)?.filas_desde_lista_estudiantes
          ) {
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
        // resultados_prueba/grafico_barras) — solo tiene sentido con
        // exactamente un estudiante en la lista congelada.
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

  async function guardarSeccion(seccion: DocumentoInstitucionalSeccionContenido) {
    setGuardandoSeccionId(seccion.plantilla_seccion_id);
    setError(null);
    try {
      let contenido: Record<string, unknown>;
      if (seccion.tipo_seccion === "texto_libre") {
        contenido = { texto: edicionesTexto[seccion.plantilla_seccion_id] ?? "" };
      } else if (seccion.tipo_seccion === "grupo_campos") {
        contenido = { valores: edicionesCampos[seccion.plantilla_seccion_id] ?? {} };
      } else if (seccion.tipo_seccion === "datos_filiacion") {
        const f = edicionesFiliacion[seccion.plantilla_seccion_id];
        contenido = {
          diagnostico_presuntivo: f?.diagnostico_presuntivo || null,
          hijos: f?.hijos || null,
          examinadora: f?.examinadora || null,
          fecha_elaboracion: f?.fecha_elaboracion || null,
          periodo_propuesto: f?.periodo_propuesto || null,
        };
      } else if (seccion.tipo_seccion === "tabla_dinamica") {
        contenido = { filas: edicionesTablas[seccion.plantilla_seccion_id] ?? [] };
      } else if (seccion.tipo_seccion === "grafico_barras") {
        contenido = {
          datos: (edicionesGrafico[seccion.plantilla_seccion_id] ?? [])
            .filter((d) => d.etiqueta.trim())
            .map((d) => ({ etiqueta: d.etiqueta, valor: Number(d.valor) || 0 })),
        };
      } else {
        return;
      }
      const actualizado = await apiClient.put<DocumentoInstitucionalSeccionContenido>(
        `/documentos/${documentoId}/secciones/${seccion.plantilla_seccion_id}`,
        { contenido },
      );
      setSecciones((prev) => prev.map((s) => (s.plantilla_seccion_id === seccion.plantilla_seccion_id ? actualizado : s)));
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

  // 'resultados_prueba_multiple' — a diferencia de vincularAplicacion/
  // desvincularAplicacion (un solo inscripcion_id, su propio PUT/DELETE),
  // esta sección guarda una LISTA completa con un endpoint propio
  // (nunca el PUT genérico de contenido de sección — ver types/api.ts).
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

  // 🆕 "Ver" (react-pdf, ver components/ui/VisorArchivo.tsx) — mismo
  // endpoint que descargar(), pero abre el modal en vez de guardar a disco.
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

  if (cargando) return <div className="p-6 text-sm text-ink/60">Cargando...</div>;
  if (!documento) return <div className="p-6"><TextoError>{error}</TextoError></div>;

  const puedeVincular = documento.estudiantes.length === 1;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <Migas items={[{ label: "Documentos", href: "/documentos" }, { label: documento.titulo }]} />
      <div>
        <Link href="/documentos" className="text-xs text-ink/50 hover:underline">
          ← Documentos
        </Link>
        <h1 className="font-display text-2xl text-teal-900 mt-1">{documento.titulo}</h1>
        <p className="text-xs text-ink/50 mt-1">
          {documento.estudiantes.length === 0
            ? "Sin estudiantes vinculados"
            : documento.estudiantes.map((e) => e.nombre_completo_historico).join(", ")}
        </p>
      </div>

      <TextoError>{error}</TextoError>

      {/* Contenido por sección */}
      <div className="space-y-3">
        {secciones
          .slice()
          .sort((a, b) => a.orden - b.orden)
          .map((seccion) => (
            <div key={seccion.plantilla_seccion_id} className="bg-white border border-border rounded-card p-4 space-y-2">
              <p className="text-xs font-semibold text-ink/70 uppercase tracking-wide">
                {seccion.titulo || ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion] || seccion.tipo_seccion}
              </p>

              {seccion.tipo_seccion === "texto_libre" && (
                <>
                  <Textarea
                    rows={4}
                    value={edicionesTexto[seccion.plantilla_seccion_id] ?? ""}
                    onChange={(e) => setEdicionesTexto({ ...edicionesTexto, [seccion.plantilla_seccion_id]: e.target.value })}
                    className="w-full"
                  />
                  <div className="flex items-center gap-3">
                    <Boton onClick={() => guardarSeccion(seccion)} disabled={guardandoSeccionId === seccion.plantilla_seccion_id}>
                      {guardandoSeccionId === seccion.plantilla_seccion_id ? "Guardando..." : "Guardar"}
                    </Boton>
                    <button
                      type="button"
                      title="Agrega una línea nueva que empieza con viñeta (•) — se imprime como punto en el PDF"
                      onClick={() => {
                        const actual = edicionesTexto[seccion.plantilla_seccion_id] ?? "";
                        const separador = actual && !actual.endsWith("\n") ? "\n" : "";
                        setEdicionesTexto({ ...edicionesTexto, [seccion.plantilla_seccion_id]: `${actual}${separador}• ` });
                      }}
                      className="text-xs text-teal-700 hover:underline"
                    >
                      • Agregar viñeta
                    </button>
                  </div>
                  <p className="text-xs text-ink/40">
                    Tip: escribí <code className="font-mono">**así**</code> alrededor de una palabra para que salga en
                    <strong> negrita</strong> en el PDF.
                  </p>
                </>
              )}

              {seccion.tipo_seccion === "grupo_campos" && (
                <>
                  <div className="space-y-2">
                    {((definiciones[seccion.plantilla_seccion_id]?.config as any)?.campos ?? []).map((c: { etiqueta: string }) => (
                      <label key={c.etiqueta} className="flex flex-col gap-1 text-sm">
                        <span className="text-ink/70 font-medium">{c.etiqueta}</span>
                        <Input
                          value={edicionesCampos[seccion.plantilla_seccion_id]?.[c.etiqueta] ?? ""}
                          onChange={(e) =>
                            setEdicionesCampos({
                              ...edicionesCampos,
                              [seccion.plantilla_seccion_id]: { ...edicionesCampos[seccion.plantilla_seccion_id], [c.etiqueta]: e.target.value },
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                  <Boton onClick={() => guardarSeccion(seccion)} disabled={guardandoSeccionId === seccion.plantilla_seccion_id}>
                    {guardandoSeccionId === seccion.plantilla_seccion_id ? "Guardando..." : "Guardar"}
                  </Boton>
                </>
              )}

              {seccion.tipo_seccion === "datos_filiacion" && (
                <EditorDatosFiliacion
                  valores={
                    edicionesFiliacion[seccion.plantilla_seccion_id] ?? {
                      diagnostico_presuntivo: "",
                      hijos: "",
                      examinadora: "",
                      fecha_elaboracion: "",
                      periodo_propuesto: "",
                    }
                  }
                  onCambiar={(v) => setEdicionesFiliacion({ ...edicionesFiliacion, [seccion.plantilla_seccion_id]: v })}
                  onGuardar={() => guardarSeccion(seccion)}
                  guardando={guardandoSeccionId === seccion.plantilla_seccion_id}
                />
              )}

              {seccion.tipo_seccion === "tabla_dinamica" &&
                !((definiciones[seccion.plantilla_seccion_id]?.config as any)?.filas_desde_lista_estudiantes) && (
                  <EditorTablaLibre
                    columnas={((definiciones[seccion.plantilla_seccion_id]?.config as any)?.columnas ?? []).map((c: any) => c.titulo)}
                    filas={edicionesTablas[seccion.plantilla_seccion_id] ?? []}
                    onCambiar={(filas) => setEdicionesTablas({ ...edicionesTablas, [seccion.plantilla_seccion_id]: filas })}
                    onGuardar={() => guardarSeccion(seccion)}
                    guardando={guardandoSeccionId === seccion.plantilla_seccion_id}
                  />
                )}

              {(seccion.tipo_seccion === "grafico_barras" || seccion.tipo_seccion === "resultados_prueba") && (
                <EditorResultadoVinculable
                  tipo={seccion.tipo_seccion}
                  seccion={seccion}
                  puedeVincular={puedeVincular}
                  historial={historialAlumno}
                  vinculando={vinculandoSeccionId === seccion.plantilla_seccion_id}
                  onVincular={(inscripcionId) => vincularAplicacion(seccion, inscripcionId)}
                  onDesvincular={() => desvincularAplicacion(seccion)}
                  valoresManual={edicionesGrafico[seccion.plantilla_seccion_id] ?? []}
                  onCambiarManual={(v) => setEdicionesGrafico({ ...edicionesGrafico, [seccion.plantilla_seccion_id]: v })}
                  onGuardarManual={() => guardarSeccion(seccion)}
                  guardando={guardandoSeccionId === seccion.plantilla_seccion_id}
                />
              )}

              {seccion.tipo_seccion === "resultados_prueba_multiple" && (
                <EditorResultadosMultiplesVinculables
                  puedeVincular={puedeVincular}
                  historial={historialAlumno}
                  guardando={guardandoSeccionId === seccion.plantilla_seccion_id}
                  seleccionados={edicionesResultadosMultiples[seccion.plantilla_seccion_id] ?? []}
                  onGuardar={(ids) => guardarResultadosMultiples(seccion, ids)}
                />
              )}

              {seccion.tipo_seccion === "imagen_anexo" && (
                <div className="space-y-2 text-sm">
                  {(seccion.contenido as any)?.storage_key ? (
                    <p className="text-teal-700">Imagen cargada: {(seccion.contenido as any)?.nombre_archivo ?? "archivo"} ✓</p>
                  ) : (
                    <p className="text-ink/50 italic">Sin imagen todavía.</p>
                  )}
                  <input
                    type="file"
                    accept="image/jpeg,image/png"
                    disabled={subiendoImagenId === seccion.plantilla_seccion_id}
                    onChange={(e) => e.target.files?.[0] && subirImagen(seccion, e.target.files[0])}
                    onPaste={(e) => {
                      const archivo = Array.from(e.clipboardData.files ?? []).find((f) => f.type.startsWith("image/"));
                      if (archivo) subirImagen(seccion, archivo);
                    }}
                    className="text-xs"
                  />
                  <p className="text-xs text-ink/40">También podés pegar (Ctrl+V) una imagen copiada, con el foco en este campo.</p>
                </div>
              )}
            </div>
          ))}
      </div>

      {/* Generar / reemitir */}
      <section className="bg-white border border-border rounded-card p-4 space-y-3">
        <h2 className="font-display text-lg text-teal-900 font-semibold">Generar documento</h2>
        {documento.version_actual === null ? (
          <Boton onClick={generarOReemitir} disabled={generando}>
            {generando ? "Generando..." : "Generar versión 1"}
          </Boton>
        ) : mostrarReemision ? (
          <div className="space-y-2">
            <Input
              value={motivoReemision}
              onChange={(e) => setMotivoReemision(e.target.value)}
              placeholder="Motivo de la reemisión..."
              className="w-full"
            />
            <div className="flex items-center gap-3">
              <Boton onClick={generarOReemitir} disabled={generando || !motivoReemision}>
                {generando ? "Generando..." : "Confirmar reemisión"}
              </Boton>
              <button onClick={() => setMostrarReemision(false)} className="text-sm text-ink/60 hover:underline">
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <Boton onClick={() => setMostrarReemision(true)}>Reemitir (v{documento.version_actual + 1})</Boton>
        )}

        {versiones.length > 0 && (
          <div className="border-t border-border pt-3 space-y-1">
            {versiones
              .slice()
              .sort((a, b) => b.numero_version - a.numero_version)
              .map((v) => (
                <div key={v.id} className="flex items-center justify-between text-sm">
                  <span>
                    v{v.numero_version} — {new Date(v.generado_en).toLocaleString("es-PE")}
                    {v.motivo_version && <span className="text-ink/50"> ({v.motivo_version})</span>}
                  </span>
                  <span className="flex items-center gap-3">
                    <button onClick={() => ver(v)} className="text-teal-700 hover:underline text-xs">
                      Ver
                    </button>
                    <button
                      onClick={() => descargar(v)}
                      disabled={descargandoVersionId === v.id}
                      className="text-teal-700 hover:underline text-xs"
                    >
                      {descargandoVersionId === v.id ? "Descargando..." : "Descargar PDF"}
                    </button>
                  </span>
                </div>
              ))}
          </div>
        )}
      </section>

      <VisorArchivoModal
        abierto={visorAbierto}
        onCerrar={() => setVisorAbierto(false)}
        archivo={visorArchivo}
        cargando={visorCargando}
        error={visorError}
      />
    </div>
  );
}

// 'datos_filiacion' — nombre/sexo/fecha de nacimiento/documento/grado
// salen automáticos de la ficha del alumno (no se editan acá); estos 5
// campos son propios de ESTE documento en particular, nunca de Persona
// (ver docstring de crud._resolver_datos_filiacion en el backend).
function EditorDatosFiliacion({
  valores,
  onCambiar,
  onGuardar,
  guardando,
}: {
  valores: EdicionFiliacion;
  onCambiar: (v: EdicionFiliacion) => void;
  onGuardar: () => void;
  guardando: boolean;
}) {
  return (
    <>
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/70 font-medium">Diagnóstico presuntivo (lo demás sale de la ficha del alumno)</span>
        <Textarea
          rows={2}
          value={valores.diagnostico_presuntivo}
          onChange={(e) => onCambiar({ ...valores, diagnostico_presuntivo: e.target.value })}
        />
      </label>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Hijos</span>
          <Input
            value={valores.hijos}
            onChange={(e) => onCambiar({ ...valores, hijos: e.target.value })}
            placeholder="Ej. Ninguno"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Examinadora</span>
          <Input
            value={valores.examinadora}
            onChange={(e) => onCambiar({ ...valores, examinadora: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Fecha de elaboración</span>
          <Input
            value={valores.fecha_elaboracion}
            onChange={(e) => onCambiar({ ...valores, fecha_elaboracion: e.target.value })}
            placeholder="Ej. 28 de septiembre de 2026"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Periodo propuesto</span>
          <Input
            value={valores.periodo_propuesto}
            onChange={(e) => onCambiar({ ...valores, periodo_propuesto: e.target.value })}
            placeholder="Ej. Octubre–noviembre de 2026"
          />
        </label>
      </div>
      <Boton onClick={onGuardar} disabled={guardando}>
        {guardando ? "Guardando..." : "Guardar"}
      </Boton>
    </>
  );
}

function EditorTablaLibre({
  columnas,
  filas,
  onCambiar,
  onGuardar,
  guardando,
}: {
  columnas: string[];
  filas: Record<string, string>[];
  onCambiar: (filas: Record<string, string>[]) => void;
  onGuardar: () => void;
  guardando: boolean;
}) {
  if (columnas.length === 0) return <p className="text-xs text-ink/50 italic">Esta tabla no tiene columnas configuradas en la plantilla.</p>;
  return (
    <div className="space-y-2">
      {filas.map((fila, idxFila) => (
        <div key={idxFila} className="flex items-center gap-2 flex-wrap">
          {columnas.map((col) => (
            <input
              key={col}
              placeholder={col}
              value={fila[col] ?? ""}
              onChange={(e) => onCambiar(filas.map((f, i) => (i === idxFila ? { ...f, [col]: e.target.value } : f)))}
              className="rounded-card border border-border px-2 py-1 text-xs flex-1 min-w-[100px]"
            />
          ))}
          <button onClick={() => onCambiar(filas.filter((_, i) => i !== idxFila))} className="text-xs text-red-600 hover:underline">
            Quitar
          </button>
        </div>
      ))}
      <button onClick={() => onCambiar([...filas, {}])} className="text-xs text-teal-700 hover:underline">
        + Agregar fila
      </button>
      <div>
        <Boton onClick={onGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Boton>
      </div>
    </div>
  );
}

// 'grafico_barras': manual (lista etiqueta/valor) o vinculado a una
// aplicación real (mismo mecanismo que 'resultados_prueba', con el mismo
// candado de retención del lado del backend). 'resultados_prueba' solo
// admite el vínculo, nunca carga manual.
function EditorResultadoVinculable({
  tipo,
  seccion,
  puedeVincular,
  historial,
  vinculando,
  onVincular,
  onDesvincular,
  valoresManual,
  onCambiarManual,
  onGuardarManual,
  guardando,
}: {
  tipo: "grafico_barras" | "resultados_prueba";
  seccion: DocumentoInstitucionalSeccionContenido;
  puedeVincular: boolean;
  historial: HistorialInformePersona[];
  vinculando: boolean;
  onVincular: (inscripcionId: number) => void;
  onDesvincular: () => void;
  valoresManual: { etiqueta: string; valor: string }[];
  onCambiarManual: (v: { etiqueta: string; valor: string }[]) => void;
  onGuardarManual: () => void;
  guardando: boolean;
}) {
  return (
    <div className="space-y-3 text-sm">
      {puedeVincular && (
        <div className="space-y-1">
          <span className="text-ink/70 font-medium">Vincular a una aplicación real</span>
          {historial.length === 0 ? (
            <p className="text-xs text-ink/50 italic">Este alumno todavía no tiene ninguna aplicación psicométrica.</p>
          ) : (
            <div className="space-y-1">
              {historial.map((h) => (
                <div key={h.inscripcion_id} className="flex items-center justify-between gap-2 text-xs border border-border rounded-card px-2 py-1">
                  <span>
                    {h.prueba_nombre_publico} — {h.nombre_grupo}
                    {h.fecha_aplicacion && ` (${new Date(h.fecha_aplicacion).toLocaleDateString("es-PE")})`}
                    {!h.informe_liberado && <span className="text-amber-700"> · retenido</span>}
                  </span>
                  <button disabled={vinculando} onClick={() => onVincular(h.inscripcion_id)} className="text-teal-700 hover:underline">
                    Vincular
                  </button>
                </div>
              ))}
            </div>
          )}
          <button disabled={vinculando} onClick={onDesvincular} className="text-xs text-ink/50 hover:underline">
            Quitar vínculo
          </button>
        </div>
      )}

      {tipo === "grafico_barras" && (
        <div className="space-y-2 border-t border-border pt-2">
          <span className="text-ink/70 font-medium">O cargar valores manuales (si no hay una prueba vinculada)</span>
          {valoresManual.map((d, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                placeholder="Etiqueta"
                value={d.etiqueta}
                onChange={(e) => onCambiarManual(valoresManual.map((x, j) => (j === i ? { ...x, etiqueta: e.target.value } : x)))}
                className="rounded-card border border-border px-2 py-1 text-xs flex-1"
              />
              <input
                type="number"
                placeholder="Valor"
                value={d.valor}
                onChange={(e) => onCambiarManual(valoresManual.map((x, j) => (j === i ? { ...x, valor: e.target.value } : x)))}
                className="rounded-card border border-border px-2 py-1 text-xs w-24"
              />
              <button onClick={() => onCambiarManual(valoresManual.filter((_, j) => j !== i))} className="text-xs text-red-600 hover:underline">
                Quitar
              </button>
            </div>
          ))}
          <button onClick={() => onCambiarManual([...valoresManual, { etiqueta: "", valor: "" }])} className="text-xs text-teal-700 hover:underline">
            + Agregar punto
          </button>
          <div>
            <Boton onClick={onGuardarManual} disabled={guardando}>
              {guardando ? "Guardando..." : "Guardar valores manuales"}
            </Boton>
          </div>
        </div>
      )}
    </div>
  );
}

// 'resultados_prueba_multiple' — a diferencia de EditorResultadoVinculable
// (un solo vínculo, botón "Vincular"/"Quitar vínculo" por fila), esta
// sección consolida una cantidad VARIABLE de aplicaciones reales: casillas
// de selección múltiple sobre el mismo historial, un solo "Guardar
// selección" que reemplaza la lista completa (ver
// crud.vincular_resultados_prueba_multiple en el backend).
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

  // El historial puede llegar después del primer render (se carga aparte,
  // ver cargar() en el componente padre) — sincroniza una sola vez cuando
  // cambia lo ya guardado en el servidor, sin pisar una selección que el
  // usuario esté armando a mano.
  useEffect(() => {
    setMarcados(seleccionados);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seleccionados.join(",")]);

  if (!puedeVincular) {
    return <p className="text-xs text-ink/50 italic">Esta sección es de identidad individual — el documento no tiene exactamente un estudiante.</p>;
  }

  function alternar(inscripcionId: number) {
    setMarcados((prev) => (prev.includes(inscripcionId) ? prev.filter((id) => id !== inscripcionId) : [...prev, inscripcionId]));
  }

  return (
    <div className="space-y-2 text-sm">
      <span className="text-ink/70 font-medium">Pruebas a consolidar en esta sección</span>
      {historial.length === 0 ? (
        <p className="text-xs text-ink/50 italic">Este alumno todavía no tiene ninguna aplicación psicométrica.</p>
      ) : (
        <div className="space-y-1">
          {historial.map((h) => (
            <label key={h.inscripcion_id} className="flex items-center gap-2 text-xs border border-border rounded-card px-2 py-1 cursor-pointer">
              <input
                type="checkbox"
                checked={marcados.includes(h.inscripcion_id)}
                onChange={() => alternar(h.inscripcion_id)}
              />
              <span>
                {h.prueba_nombre_publico} — {h.nombre_grupo}
                {h.fecha_aplicacion && ` (${new Date(h.fecha_aplicacion).toLocaleDateString("es-PE")})`}
                {!h.informe_liberado && <span className="text-amber-700"> · retenido</span>}
              </span>
            </label>
          ))}
        </div>
      )}
      <Boton onClick={() => onGuardar(marcados)} disabled={guardando}>
        {guardando ? "Guardando..." : "Guardar selección"}
      </Boton>
    </div>
  );
}
