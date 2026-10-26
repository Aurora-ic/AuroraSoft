"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import type {
  TipoDocumento,
  PlantillaDocumento,
  DocumentoInstitucional,
  PlantillaDocumentoCreate,
  PlantillaDocumentoClonarRequest,
  RespuestaPaginada,
} from "@/types/api";

const TAMANO_PAGINA = 50;

type Tab = "plantillas" | "catalogo" | "generados";

// Landing del motor de documentos institucionales, organizada en 3 pestañas
// que reflejan el único flujo real del motor (ver docs/motor-documentos.md):
//
//   1. Catálogo (predeterminadas, global, de solo lectura) — se CLONA, nunca
//      se usa directo para generar un documento.
//   2. Mis plantillas (propias de esta institución, clonadas o armadas desde
//      cero) — acá sí se edita estructura/tipografía, y desde acá se dispara
//      "Generar documento".
//   3. Documentos generados (instancias reales, cada una atada a uno o
//      varios alumnos o a una estructura académica).
//
// Antes las 3 vivían apiladas en un solo scroll sin ninguna explicación de
// cómo se relacionan — la tira de abajo y las pestañas son la respuesta
// directa a esa confusión (sesión 2026-10-25, a pedido del usuario).
export default function DocumentosPage() {
  const { sesion } = useAuth();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("plantillas");

  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([]);
  const [predeterminadas, setPredeterminadas] = useState<PlantillaDocumento[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoInstitucional[]>([]);
  const [totalDocumentos, setTotalDocumentos] = useState(0);
  const [paginaDocumentos, setPaginaDocumentos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchPlantillas, setSearchPlantillas] = useState("");
  const [searchCatalogo, setSearchCatalogo] = useState("");
  const [gruposAbiertos, setGruposAbiertos] = useState<Record<number, boolean>>({});

  const [tipoNuevaPlantilla, setTipoNuevaPlantilla] = useState("");
  const [crearDesdeCeroAbierto, setCrearDesdeCeroAbierto] = useState(false);
  const [creandoPlantilla, setCreandoPlantilla] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);

  const [clonandoId, setClonandoId] = useState<number | null>(null);
  const [errorClonar, setErrorClonar] = useState<string | null>(null);

  // 🆕 Cuántas PlantillaSeccion tiene cada plantilla propia — hallazgo
  // real (sesión 2026-10-25): varias plantillas quedaban "Activa" con 0
  // secciones (ver constructor, que ahora también avisa esto). -1 =
  // todavía no se pudo cargar el conteo, nunca se trata como "0 de
  // verdad" en el render.
  const [conteoSecciones, setConteoSecciones] = useState<Record<number, number>>({});
  const [activandoId, setActivandoId] = useState<number | null>(null);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    setCargando(true);
    // 🆕 Paginación real (docs/gaps-pendientes.md) — antes pedía todo
    // documento generado sin tope; ahora pide de a 50 con skip/limit.
    Promise.all([
      apiClient.get<TipoDocumento[]>("/documentos/tipos?solo_activos=true"),
      apiClient.get<PlantillaDocumento[]>(`/documentos/plantillas?institucion_id=${sesion.institucionId}`),
      apiClient.get<RespuestaPaginada<DocumentoInstitucional>>(
        `/documentos/?institucion_id=${sesion.institucionId}&skip=${paginaDocumentos * TAMANO_PAGINA}&limit=${TAMANO_PAGINA}`,
      ),
      apiClient.get<PlantillaDocumento[]>("/documentos/plantillas/predeterminadas"),
    ])
      .then(([t, p, d, pred]) => {
        setTipos(t);
        setPlantillas(p);
        setDocumentos(d.items);
        setTotalDocumentos(d.total);
        setPredeterminadas(pred);
      })
      .catch((err) => setError(err.message || "No se pudieron cargar los documentos."))
      .finally(() => setCargando(false));
  }, [sesion?.institucionId, paginaDocumentos]);

  useEffect(() => {
    if (plantillas.length === 0) return;
    Promise.all(
      plantillas.map((p) =>
        apiClient
          .get<unknown[]>(`/documentos/plantillas/${p.id}/secciones`)
          .then((s) => [p.id, s.length] as const)
          .catch(() => [p.id, -1] as const),
      ),
    ).then((pares) => setConteoSecciones(Object.fromEntries(pares)));
  }, [plantillas]);

  async function activarPlantilla(p: PlantillaDocumento) {
    setActivandoId(p.id);
    setErrorPlantilla(null);
    try {
      const actualizada = await apiClient.patch<PlantillaDocumento>(`/documentos/plantillas/${p.id}`, { activa: true });
      // El backend ya desactivó en silencio cualquier otra plantilla del
      // mismo tipo (exclusividad, ver _desactivar_plantillas_activas) —
      // se refleja acá mismo para no esperar un refetch completo.
      setPlantillas((prev) =>
        prev.map((x) => {
          if (x.id === actualizada.id) return actualizada;
          if (x.tipo_documento_id === actualizada.tipo_documento_id && x.activa) return { ...x, activa: false };
          return x;
        }),
      );
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo activar la plantilla.");
    } finally {
      setActivandoId(null);
    }
  }

  async function crearPlantilla() {
    if (!sesion?.institucionId || !tipoNuevaPlantilla) return;
    setCreandoPlantilla(true);
    setErrorPlantilla(null);
    try {
      const tipo = tipos.find((t) => t.id === Number(tipoNuevaPlantilla));
      const payload: PlantillaDocumentoCreate = {
        institucion_id: sesion.institucionId,
        tipo_documento_id: Number(tipoNuevaPlantilla),
        nombre: tipo ? `${tipo.nombre} — nueva plantilla` : "Nueva plantilla",
        // 🆕 Hallazgo real (sesión 2026-10-25): el default del backend es
        // activa=True (schemas.PlantillaDocumentoCreate), y "activa" es
        // exclusiva por tipo+institución (_desactivar_plantillas_activas) —
        // una plantilla recién creada, SIN NINGUNA SECCIÓN todavía, se
        // volvía de inmediato "la" activa de ese tipo, apagando en
        // silencio cualquier otra ya armada con contenido real. Confirmado
        // contra la BD real: así quedó activa una plantilla con 0
        // secciones mientras la clonada con 16 secciones seguía inactiva.
        // Nace inactiva; se activa a propósito desde el constructor
        // (ver /documentos/plantillas/[id], que ahora sí expone esa
        // acción) una vez que de verdad tiene contenido.
        activa: false,
      };
      const nueva = await apiClient.post<PlantillaDocumento>("/documentos/plantillas", payload);
      router.push(`/documentos/plantillas/${nueva.id}`);
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo crear la plantilla.");
    } finally {
      setCreandoPlantilla(false);
    }
  }

  async function clonarPlantilla(predeterminada: PlantillaDocumento) {
    if (!sesion?.institucionId) return;
    setClonandoId(predeterminada.id);
    setErrorClonar(null);
    try {
      const payload: PlantillaDocumentoClonarRequest = { institucion_destino_id: sesion.institucionId };
      const clon = await apiClient.post<PlantillaDocumento>(`/documentos/plantillas/${predeterminada.id}/clonar`, payload);
      router.push(`/documentos/plantillas/${clon.id}`);
    } catch (err: any) {
      setErrorClonar(err.message || "No se pudo clonar la plantilla.");
    } finally {
      setClonandoId(null);
    }
  }

  function nombreTipo(tipoId: number) {
    return tipos.find((t) => t.id === tipoId)?.nombre ?? `Tipo #${tipoId}`;
  }

  function fechaCorta(iso: string) {
    return new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
  }

  function toggleGrupo(tipoId: number) {
    setGruposAbiertos((prev) => ({ ...prev, [tipoId]: !prev[tipoId] }));
  }

  const plantillasFiltradas = useMemo(() => {
    const q = searchPlantillas.trim().toLowerCase();
    if (!q) return plantillas;
    return plantillas.filter((p) => p.nombre.toLowerCase().includes(q) || nombreTipo(p.tipo_documento_id).toLowerCase().includes(q));
  }, [plantillas, searchPlantillas, tipos]);

  // Predeterminadas agrupadas por tipo de documento — un acordeón por tipo
  // en vez de una lista plana, porque ya hay 8 tipos reales cargados
  // (seed_plantilla_*) y seguirán creciendo. Buscando, se abren solo los
  // grupos con resultado; sin buscar, el primer grupo con contenido queda
  // abierto por defecto y el resto respeta lo que el usuario haya tocado.
  const gruposCatalogo = useMemo(() => {
    const q = searchCatalogo.trim().toLowerCase();
    let primerConContenidoVisto = false;
    return tipos
      .map((t) => {
        const items = predeterminadas.filter(
          (pr) => pr.tipo_documento_id === t.id && (!q || pr.nombre.toLowerCase().includes(q) || t.nombre.toLowerCase().includes(q)),
        );
        let abierto: boolean;
        if (q) {
          abierto = items.length > 0;
        } else if (gruposAbiertos[t.id] !== undefined) {
          abierto = gruposAbiertos[t.id];
        } else {
          abierto = items.length > 0 && !primerConContenidoVisto;
        }
        if (items.length > 0) primerConContenidoVisto = true;
        return { tipo: t, items, abierto };
      })
      .filter((g) => g.items.length > 0);
  }, [tipos, predeterminadas, searchCatalogo, gruposAbiertos]);

  if (cargando) {
    return (
      <div className="max-w-6xl mx-auto space-y-8">
        <h1 className="font-display text-2xl text-teal-900 dark:text-teal-accent-dark">Documentos institucionales</h1>
        <EsqueletoLista cantidad={5} />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="font-display text-2xl text-teal-900 dark:text-teal-accent-dark">Documentos institucionales</h1>
          <p className="text-sm text-ink/60 dark:text-ink-dark/60 mt-1">Plantillas, catálogo y documentos generados en un solo lugar.</p>
        </div>
        <Link href="/documentos/nuevo" className={claseBoton("primario")}>
          + Nuevo documento
        </Link>
      </div>

      <TextoError>{error}</TextoError>

      {/* Tira "cómo funciona" — siempre visible, para que el flujo
          catálogo → plantilla → documento nunca dependa de recordarlo. */}
      <div className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark px-5 py-3.5 flex items-stretch gap-4 flex-wrap">
        <PasoFlujo numero={1} titulo="Catálogo" descripcion="Formatos listos de AuroraSoft. Solo se clonan, nunca se usan directo." />
        <FlechaPaso />
        <PasoFlujo numero={2} titulo="Tus plantillas" descripcion="Clonadas o armadas desde cero. Las editás las veces que quieras." />
        <FlechaPaso />
        <PasoFlujo numero={3} titulo="Documentos" descripcion="Una plantilla aplicada a un alumno o grupo puntual — esto es lo que se genera." />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border dark:border-border-dark">
        <BotonTab activo={tab === "plantillas"} onClick={() => setTab("plantillas")}>
          Mis plantillas ({plantillas.length})
        </BotonTab>
        <BotonTab activo={tab === "catalogo"} onClick={() => setTab("catalogo")}>
          Catálogo para clonar ({predeterminadas.length})
        </BotonTab>
        <BotonTab activo={tab === "generados"} onClick={() => setTab("generados")}>
          Documentos generados ({totalDocumentos})
        </BotonTab>
      </div>

      {/* ===== TAB: Mis plantillas ===== */}
      {tab === "plantillas" && (
        <section className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <Input
              value={searchPlantillas}
              onChange={(e) => setSearchPlantillas(e.target.value)}
              placeholder="Buscar por nombre o tipo de documento..."
              className="flex-1 min-w-[220px]"
            />
            <Boton variante="secundario" onClick={() => setCrearDesdeCeroAbierto((v) => !v)}>
              + Nueva desde cero
            </Boton>
          </div>

          {crearDesdeCeroAbierto && (
            <div className="bg-mist dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-4 flex items-end gap-3 flex-wrap">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Nueva plantilla a partir de un tipo de documento</span>
                <Select value={tipoNuevaPlantilla} onChange={(e) => setTipoNuevaPlantilla(e.target.value)}>
                  <option value="">Elige un tipo...</option>
                  {tipos.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.nombre}
                    </option>
                  ))}
                </Select>
              </label>
              <Boton onClick={crearPlantilla} disabled={!tipoNuevaPlantilla || creandoPlantilla}>
                {creandoPlantilla ? "Creando..." : "Crear y abrir el constructor"}
              </Boton>
            </div>
          )}
          <TextoError>{errorPlantilla}</TextoError>
          {tipos.length === 0 && (
            <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">
              Todavía no hay ningún tipo de documento en el catálogo (lo arma superadmin).
            </p>
          )}

          {plantillasFiltradas.length === 0 ? (
            <p className="text-sm text-ink/60 dark:text-ink-dark/60 italic py-2">
              {plantillas.length === 0 ? "Tu institución todavía no tiene ninguna plantilla." : "Ninguna plantilla coincide con la búsqueda."}
            </p>
          ) : (
            <div className="grid sm:grid-cols-2 gap-3.5">
              {plantillasFiltradas.map((p) => {
                const n = conteoSecciones[p.id];
                const sinContenido = n === 0;
                return (
                  <div key={p.id} className="border border-border dark:border-border-dark rounded-card p-4 flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[11px] font-semibold text-teal-700 dark:text-teal-accent-dark bg-mist dark:bg-surface-dark rounded-md px-2 py-0.5">
                        {nombreTipo(p.tipo_documento_id)}
                      </span>
                      <span
                        className={`text-[11px] font-semibold rounded-full px-2.5 py-0.5 whitespace-nowrap ${
                          p.activa ? "bg-teal-600 text-white" : "bg-surface dark:bg-surface-dark border border-border dark:border-border-dark text-ink/50 dark:text-ink-dark/50"
                        }`}
                      >
                        {p.activa ? "Activa" : "Inactiva"}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{p.nombre}</h3>
                    <p className="text-[11px] text-ink/45 dark:text-ink-dark/45">
                      Creada el {fechaCorta(p.creado_en)}
                      {n !== undefined && n >= 0 && ` · ${n} ${n === 1 ? "sección" : "secciones"}`}
                    </p>
                    {/* 🆕 Activa + sin secciones = generaría un documento vacío —
                        ver docstring de alternarActiva() en el constructor. */}
                    {p.activa && sinContenido && (
                      <p className="text-[11px] text-red-700 font-medium">⚠ Sin secciones — no generará contenido.</p>
                    )}
                    <div className="flex gap-2 mt-1">
                      <Link href={`/documentos/plantillas/${p.id}`} className={claseBoton("secundario", "flex-1 text-center")}>
                        Editar
                      </Link>
                      {p.activa ? (
                        <Link href={`/documentos/nuevo?plantilla_id=${p.id}`} className={claseBoton("primario", "flex-1 text-center")}>
                          Generar documento
                        </Link>
                      ) : (
                        // 🆕 "Generar documento" solo funciona de verdad con una
                        // plantilla activa (documentos/nuevo solo lista las
                        // activas) — antes el botón aparecía igual acá y el
                        // precargado fallaba en silencio, sin preseleccionar nada.
                        <Boton
                          variante="primario"
                          className="flex-1"
                          onClick={() => activarPlantilla(p)}
                          disabled={activandoId === p.id}
                        >
                          {activandoId === p.id ? "Activando..." : "Activar"}
                        </Boton>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* ===== TAB: Catálogo ===== */}
      {tab === "catalogo" && (
        <section className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-4">
          <Input
            value={searchCatalogo}
            onChange={(e) => setSearchCatalogo(e.target.value)}
            placeholder="Buscar por nombre o tipo de documento..."
          />
          <p className="text-xs text-ink/55 dark:text-ink-dark/55">
            Formatos armados por AuroraSoft. Clonar uno crea una copia propia de tu institución, totalmente editable — nunca
            modifica el original.
          </p>
          <TextoError>{errorClonar}</TextoError>

          {gruposCatalogo.length === 0 ? (
            <p className="text-sm text-ink/60 dark:text-ink-dark/60 italic py-2">
              {predeterminadas.length === 0 ? "Todavía no hay ningún formato en el catálogo." : "Ningún formato coincide con la búsqueda."}
            </p>
          ) : (
            <div className="space-y-2">
              {gruposCatalogo.map((g) => (
                <div key={g.tipo.id}>
                  <button
                    type="button"
                    onClick={() => toggleGrupo(g.tipo.id)}
                    className="w-full flex items-center justify-between bg-mist dark:bg-surface-dark rounded-card px-3.5 py-2.5 hover:bg-mist/70 dark:bg-surface-dark/70 transition-colors"
                  >
                    <span className="flex items-center gap-2.5">
                      <svg
                        width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                        className={`text-ink/70 dark:text-ink-dark/70 transition-transform ${g.abierto ? "rotate-90" : ""}`}
                      >
                        <path d="M9 6l6 6-6 6" />
                      </svg>
                      <span className="text-sm font-semibold text-ink dark:text-ink-dark">{g.tipo.nombre}</span>
                    </span>
                    <span className="text-[11px] text-ink/50 dark:text-ink-dark/50 bg-surface dark:bg-surface-dark rounded-full px-2.5 py-0.5">{g.items.length}</span>
                  </button>

                  {g.abierto && (
                    <div className="pt-2 pb-1 px-1 space-y-2">
                      {g.items.map((item) => (
                        <div key={item.id} className="flex items-center justify-between gap-3 border border-border dark:border-border-dark rounded-card px-3.5 py-2.5">
                          <span className="text-sm font-medium text-ink dark:text-ink-dark">{item.nombre}</span>
                          <Boton onClick={() => clonarPlantilla(item)} disabled={clonandoId === item.id}>
                            {clonandoId === item.id ? "Clonando..." : "Clonar a mi institución"}
                          </Boton>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ===== TAB: Documentos generados ===== */}
      {tab === "generados" && (
        <section className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-3">
          {documentos.length === 0 ? (
            <p className="text-sm text-ink/60 dark:text-ink-dark/60 italic py-2">Todavía no se generó ningún documento.</p>
          ) : (
            <>
              <div className="grid grid-cols-[2fr_1.2fr_0.9fr] gap-2 px-1 pb-2 border-b border-border dark:border-border-dark text-[11px] font-bold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">
                <span>Documento</span>
                <span>Tipo</span>
                <span>Estado</span>
              </div>
              <div className="divide-y divide-border">
                {documentos
                  .slice()
                  .sort((a, b) => b.id - a.id)
                  .map((d) => (
                    <Link
                      key={d.id}
                      href={`/documentos/${d.id}`}
                      className="grid grid-cols-[2fr_1.2fr_0.9fr] gap-2 items-center py-2.5 px-1 -mx-1 hover:bg-mist/40 dark:bg-surface-dark/40 rounded-card transition-colors"
                    >
                      <span className="text-sm font-medium text-ink dark:text-ink-dark">{d.titulo}</span>
                      <span className="text-xs text-ink/60 dark:text-ink-dark/60">{nombreTipo(d.tipo_documento_id)}</span>
                      <span
                        className={`text-[11px] font-semibold rounded-full px-2.5 py-0.5 w-fit ${
                          d.version_actual === null ? "bg-mist dark:bg-surface-dark border border-border dark:border-border-dark text-ink/55 dark:text-ink-dark/55" : "bg-teal-600 text-white"
                        }`}
                      >
                        {d.version_actual === null ? "Sin versión" : `Generado v${d.version_actual}`}
                      </span>
                    </Link>
                  ))}
              </div>
            </>
          )}

          {totalDocumentos > 0 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-ink/50 dark:text-ink-dark/50">
                {paginaDocumentos * TAMANO_PAGINA + 1}–{Math.min((paginaDocumentos + 1) * TAMANO_PAGINA, totalDocumentos)} de{" "}
                {totalDocumentos} documentos
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPaginaDocumentos((p) => Math.max(0, p - 1))}
                  disabled={paginaDocumentos === 0}
                  className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:bg-surface-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Anterior
                </button>
                <button
                  onClick={() => setPaginaDocumentos((p) => p + 1)}
                  disabled={(paginaDocumentos + 1) * TAMANO_PAGINA >= totalDocumentos}
                  className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:bg-surface-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Siguiente
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function BotonTab({ activo, onClick, children }: { activo: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2.5 text-sm font-semibold -mb-px border-b-2 transition-colors ${
        activo ? "text-teal-900 dark:text-teal-accent-dark border-teal-600" : "text-ink/55 dark:text-ink-dark/55 border-transparent hover:text-ink/80 dark:text-ink-dark/80"
      }`}
    >
      {children}
    </button>
  );
}

function PasoFlujo({ numero, titulo, descripcion }: { numero: number; titulo: string; descripcion: string }) {
  return (
    <div className="flex gap-2.5 items-start flex-1 min-w-[170px]">
      <span className="w-6 h-6 rounded-full bg-mist dark:bg-surface-dark text-teal-700 dark:text-teal-accent-dark text-[11px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
        {numero}
      </span>
      <div>
        <h3 className="text-[12.5px] font-bold text-ink dark:text-ink-dark m-0">{titulo}</h3>
        <p className="text-[11.5px] text-ink/60 dark:text-ink-dark/60 leading-snug mt-0.5">{descripcion}</p>
      </div>
    </div>
  );
}

function FlechaPaso() {
  return (
    <svg
      width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-border)" strokeWidth="2.5"
      className="self-center flex-shrink-0 hidden sm:block"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
