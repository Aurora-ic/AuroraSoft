"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ClipboardList,
  BarChart3,
  LayoutGrid,
  Users,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Gauge,
  Download,
  TrendingUp,
  GitCompare,
  Search,
  ChevronDown,
  ArrowRight,
  Layers,
} from "lucide-react";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import { DimensionBar } from "@/components/ui/DimensionBar";
import { ResumenEstadisticoPrueba } from "@/components/ui/ResumenEstadisticoPrueba";
import { GraficoTendenciaDimension } from "@/components/ui/GraficoTendenciaDimension";
import { EsqueletoTarjetas } from "@/components/ui/Esqueleto";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado } from "@/components/ui/Encabezado";
import { PanelDimensiones } from "@/components/educativo/PanelDimensiones";
import { VacioFicha } from "@/components/educativo/BloqueFicha";
import type {
  Prueba,
  PruebaDetalle,
  NivelEducativo,
  Grado,
  Seccion,
  DashboardAcademico,
  TendenciaSeccion,
  AlumnoDashboard,
} from "@/types/api";

// Catálogo de solo lectura — cargar una prueba nueva (ítems, dimensiones,
// baremos) es un ejercicio de datos vía seed/API directa (ver CLAUDE.md
// "Scoring engine"), no un formulario de esta pantalla. Esto solo deja ver
// qué hay disponible, para elegir al crear una campaña.
//
// 🆕 Rediseño interactivo (sesión 2026-10-30, a pedido del usuario) — antes
// el catálogo (lista larga) y el dashboard (formulario + bloques sueltos)
// competían en una sola columna angosta. Ahora son dos vistas
// ("Resultados" por defecto, "Catálogo"), con KPIs, un mapa de dimensiones
// seleccionable (components/educativo/PanelDimensiones.tsx) y filtros de
// alumnos. Ningún endpoint ni cálculo cambió: mismas llamadas, mismos
// estados, solo la presentación.
//
// ⚠️ e2e/dashboard-academico.spec.ts depende de: las etiquetas "Prueba"/
// "Nivel"/"Grado"/"Sección", el botón "Ver dashboard", la línea "N
// finalizado(s)" (una sola vez antes de comparar), "Ver tendencia en el
// tiempo", y que el texto "Comparar con otra sección del mismo grado" tenga
// como padre directo el contenedor del <select> + botón "Comparar".

type Vista = "resultados" | "catalogo";
type FiltroAlumnos = "todos" | "alerta" | "pendientes";

function alumnoEnAlerta(a: AlumnoDashboard): boolean {
  return a.resultados.some((r) => r.es_alerta === true);
}

function etiquetaModo(modo: string): string {
  const mapa: Record<string, string> = {
    suma: "Suma",
    promedio: "Promedio",
    correcto_incorrecto: "Correcto/incorrecto",
  };
  return mapa[modo] ?? modo;
}

export default function PruebasPage() {
  const { sesion } = useAuth();
  // 'colegio' recibe alumnos[].resultados redactado (vacío) server-side —
  // un conteo de "en alerta" calculado en cliente sería un falso 0.
  const veResultadosClinicos = sesion?.rol !== "colegio";

  const [vista, setVista] = useState<Vista>("resultados");

  const [pruebas, setPruebas] = useState<Prueba[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [expandidaId, setExpandidaId] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<PruebaDetalle | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [errorDetalle, setErrorDetalle] = useState<string | null>(null);

  // --- Dashboard por salón, grado o colegio completo (cruza todas las
  // campañas de una prueba) — ver GET /educativo/dashboard/academico.
  // 🆕 "institucion" (sesión 2026-10-25, docs/gaps-pendientes.md): antes
  // una prueba aplicada en varios grados a la vez solo se podía revisar
  // salón por salón. ---
  const [dashPruebaId, setDashPruebaId] = useState("");
  const [dashAmbito, setDashAmbito] = useState<"seccion" | "grado" | "institucion">("seccion");
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [grados, setGrados] = useState<Grado[]>([]);
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [dashNivelId, setDashNivelId] = useState("");
  const [dashGradoId, setDashGradoId] = useState("");
  const [dashSeccionId, setDashSeccionId] = useState("");
  const [dashboard, setDashboard] = useState<DashboardAcademico | null>(null);
  const [cargandoDashboard, setCargandoDashboard] = useState(false);
  const [errorDashboard, setErrorDashboard] = useState<string | null>(null);
  const [exportandoDashboard, setExportandoDashboard] = useState(false);

  // --- Tendencia en el tiempo de UN salón (todas sus campañas, ordenadas
  // por fecha) — ver GET .../dashboard/academico/tendencia. Solo aplica
  // cuando el ámbito visto es "seccion" (nunca "grado", ver docstring de
  // crud.obtener_tendencia_seccion en el backend). ---
  const [tendencia, setTendencia] = useState<TendenciaSeccion | null>(null);
  const [cargandoTendencia, setCargandoTendencia] = useState(false);
  const [errorTendencia, setErrorTendencia] = useState<string | null>(null);

  // --- Comparar dos secciones del mismo grado, lado a lado — dos llamadas
  // en paralelo al mismo /dashboard/academico de siempre, sin endpoint
  // nuevo: la comparación es puramente de presentación. ---
  const [compararConSeccionId, setCompararConSeccionId] = useState("");
  const [dashboardComparado, setDashboardComparado] = useState<DashboardAcademico | null>(null);
  const [cargandoComparacion, setCargandoComparacion] = useState(false);
  const [errorComparacion, setErrorComparacion] = useState<string | null>(null);

  // --- Filtros de la lista de alumnos (solo cliente, sobre dashboard.alumnos) ---
  const [filtroAlumnos, setFiltroAlumnos] = useState<FiltroAlumnos>("todos");
  const [busquedaAlumno, setBusquedaAlumno] = useState("");

  useEffect(() => {
    apiClient
      .get<Prueba[]>("/educativo/pruebas/")
      .then(setPruebas)
      .catch((err) => setError(err.message || "No se pudo cargar el catálogo de pruebas."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    apiClient
      .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
      .then(setNiveles)
      .catch(() => setNiveles([]));
  }, [sesion?.institucionId]);

  useEffect(() => {
    if (!dashNivelId) {
      setGrados([]);
      setDashGradoId("");
      return;
    }
    apiClient.get<Grado[]>(`/admin/personas/academico/grados/${dashNivelId}`).then(setGrados).catch(() => setGrados([]));
  }, [dashNivelId]);

  useEffect(() => {
    if (!dashGradoId) {
      setSecciones([]);
      setDashSeccionId("");
      return;
    }
    apiClient
      .get<Seccion[]>(`/admin/personas/academico/secciones/${dashGradoId}`)
      .then(setSecciones)
      .catch(() => setSecciones([]));
  }, [dashGradoId]);

  function paramsDashboardAcademico(): URLSearchParams | null {
    if (!dashPruebaId) return null;
    if (dashAmbito === "seccion" && !dashSeccionId) return null;
    if (dashAmbito === "grado" && !dashGradoId) return null;
    const params = new URLSearchParams({ prueba_id: dashPruebaId });
    // "institucion" no agrega ningún parámetro más — el backend asume la
    // propia institución del caller cuando no se manda seccion_id/grado_id
    // (ver router.ver_dashboard_academico). sesion.institucionId es null
    // para superadmin, que no tiene esta pantalla disponible de todos modos.
    if (dashAmbito === "seccion") params.set("seccion_id", dashSeccionId);
    else if (dashAmbito === "grado") params.set("grado_id", dashGradoId);
    return params;
  }

  async function verDashboardAcademico(e: React.FormEvent) {
    e.preventDefault();
    const params = paramsDashboardAcademico();
    if (!params) return;

    setCargandoDashboard(true);
    setErrorDashboard(null);
    setDashboard(null);
    // Un nuevo salón/grado invalida la tendencia/comparación ya mostradas
    // -- nunca dejar el panel de un ámbito anterior visible por error.
    setTendencia(null);
    setErrorTendencia(null);
    setDashboardComparado(null);
    setErrorComparacion(null);
    setCompararConSeccionId("");
    setFiltroAlumnos("todos");
    setBusquedaAlumno("");
    try {
      const datos = await apiClient.get<DashboardAcademico>(`/educativo/dashboard/academico?${params.toString()}`);
      setDashboard(datos);
    } catch (err: any) {
      setErrorDashboard(err.message || "No se pudo cargar el dashboard.");
    } finally {
      setCargandoDashboard(false);
    }
  }

  async function verTendenciaSeccion() {
    if (!dashPruebaId || dashAmbito !== "seccion" || !dashSeccionId) return;
    setCargandoTendencia(true);
    setErrorTendencia(null);
    try {
      const datos = await apiClient.get<TendenciaSeccion>(
        `/educativo/dashboard/academico/tendencia?prueba_id=${dashPruebaId}&seccion_id=${dashSeccionId}`,
      );
      setTendencia(datos);
    } catch (err: any) {
      setErrorTendencia(err.message || "No se pudo cargar la tendencia.");
    } finally {
      setCargandoTendencia(false);
    }
  }

  async function compararSeccion() {
    if (!dashPruebaId || !compararConSeccionId) return;
    setCargandoComparacion(true);
    setErrorComparacion(null);
    try {
      const datos = await apiClient.get<DashboardAcademico>(
        `/educativo/dashboard/academico?prueba_id=${dashPruebaId}&seccion_id=${compararConSeccionId}`,
      );
      setDashboardComparado(datos);
    } catch (err: any) {
      setErrorComparacion(err.message || "No se pudo cargar la sección a comparar.");
    } finally {
      setCargandoComparacion(false);
    }
  }

  async function exportarDashboardAcademicoExcel() {
    const params = paramsDashboardAcademico();
    if (!params) return;
    setExportandoDashboard(true);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/dashboard/academico/exportar-excel?${params.toString()}`);
      descargarBlob(blob, `resultados_${dashPruebaId}_${dashboard?.ambito.nombre ?? "salon"}.xlsx`);
    } catch (err: any) {
      setErrorDashboard(err.message || "No se pudo exportar el Excel.");
    } finally {
      setExportandoDashboard(false);
    }
  }

  async function toggle(prueba: Prueba) {
    if (expandidaId === prueba.id) {
      setExpandidaId(null);
      setDetalle(null);
      return;
    }
    setExpandidaId(prueba.id);
    setDetalle(null);
    setErrorDetalle(null);
    setCargandoDetalle(true);
    try {
      const datos = await apiClient.get<PruebaDetalle>(`/educativo/pruebas/${prueba.id}/completa`);
      setDetalle(datos);
    } catch (err: any) {
      setErrorDetalle(err.message || "No se pudo cargar el detalle de esta prueba.");
    } finally {
      setCargandoDetalle(false);
    }
  }

  // Atajo desde el catálogo: deja la prueba elegida en el filtro del
  // dashboard (no lo dispara solo — falta elegir el ámbito).
  function verResultadosDe(prueba: Prueba) {
    setDashPruebaId(String(prueba.id));
    setVista("resultados");
  }

  const alumnosEnAlerta = useMemo(() => (dashboard ? dashboard.alumnos.filter(alumnoEnAlerta).length : 0), [dashboard]);
  const alumnosPendientes = useMemo(
    () => (dashboard ? dashboard.alumnos.filter((a) => a.estado !== "Finalizado").length : 0),
    [dashboard],
  );

  const alumnosVisibles = useMemo(() => {
    if (!dashboard) return [];
    const texto = busquedaAlumno.trim().toLowerCase();
    return dashboard.alumnos.filter((a) => {
      if (filtroAlumnos === "alerta" && !alumnoEnAlerta(a)) return false;
      if (filtroAlumnos === "pendientes" && a.estado === "Finalizado") return false;
      if (texto && !(a.nombre_completo ?? "").toLowerCase().includes(texto)) return false;
      return true;
    });
  }, [dashboard, filtroAlumnos, busquedaAlumno]);

  const avance = dashboard && dashboard.total_inscritos > 0 ? Math.round((dashboard.total_finalizados / dashboard.total_inscritos) * 100) : 0;
  const muestraAlertas = veResultadosClinicos && (dashboard?.resumen_estadistico.tiene_alertas_posibles ?? false);
  const pruebaElegida = (pruebas ?? []).find((p) => String(p.id) === dashPruebaId) ?? null;

  const etiquetaCampo = "flex flex-col gap-1 text-[12.5px]";
  const textoEtiqueta = "text-ink/60 dark:text-ink-dark/60 font-semibold";

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-5">
      <EncabezadoPagina
        variante="destacado"
        acento="azul"
        icono={ClipboardList}
        titulo="Pruebas"
        descripcion="Resultados por salón, grado o colegio completo, y el catálogo de instrumentos disponibles para tus campañas."
        acciones={
          <div className="flex items-center gap-2 rounded-xl bg-white/10 dark:bg-surface-dark px-3.5 py-2 text-white dark:text-ink-dark">
            <Layers size={15} aria-hidden="true" className="opacity-80" />
            <span className="font-display text-lg font-bold leading-none">{pruebas ? pruebas.length : "…"}</span>
            <span className="text-[12px] opacity-75">instrumentos</span>
          </div>
        }
      />

      <ControlSegmentado<Vista>
        etiqueta="Vista"
        valor={vista}
        onCambiar={setVista}
        className="self-start"
        opciones={[
          { valor: "resultados", etiqueta: "Resultados", icono: BarChart3 },
          { valor: "catalogo", etiqueta: `Catálogo${pruebas ? ` (${pruebas.length})` : ""}`, icono: LayoutGrid },
        ]}
      />

      <TextoError>{error}</TextoError>

      {/* ============================ CATÁLOGO ============================ */}
      {vista === "catalogo" && (
        <>
          {loading && (
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
              <EsqueletoTarjetas cantidad={6} />
            </div>
          )}
          {pruebas && pruebas.length === 0 && (
            <VacioFicha icono={ClipboardList} texto="No hay ninguna prueba disponible para tu institución todavía." />
          )}
          {pruebas && pruebas.length > 0 && (
            <>
              <p className="m-0 -mt-1 text-[12px] text-ink/50 dark:text-ink-dark/50">
                Cargar un instrumento nuevo (ítems, dimensiones, baremos) es trabajo de datos, no se hace desde aquí.
              </p>
              <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 items-start">
                {pruebas.map((p) => {
                  const expandida = expandidaId === p.id;
                  return (
                    <div
                      key={p.id}
                      className={`rounded-xl border bg-surface dark:bg-surface-dark overflow-hidden transition-colors ${
                        expandida ? "border-teal-400 dark:border-teal-accent-dark" : "border-border dark:border-border-dark hover:border-teal-400/60"
                      }`}
                    >
                      <div className="p-4 flex flex-col gap-3">
                        <div className="flex items-start gap-3">
                          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark font-display text-[12px] font-bold">
                            {(p.nombre_corto || p.nombre_tecnico).slice(0, 2).toUpperCase()}
                          </span>
                          <div className="min-w-0">
                            {/* Título corto arriba (nombre_corto curado, o nombre_tecnico de
                                respaldo — ej. "PHQ-9") para no saturar la tarjeta; el nombre
                                completo queda debajo como descripción secundaria. */}
                            <p className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark truncate">{p.nombre_corto || p.nombre_tecnico}</p>
                            <p className="m-0 text-[12px] text-ink/55 dark:text-ink-dark/55 line-clamp-2">{p.nombre_publico}</p>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-1.5 text-[10.5px] font-semibold">
                          <span className="rounded-full px-2 py-0.5 bg-mist dark:bg-surface-raised-dark text-ink/60 dark:text-ink-dark/60">
                            {etiquetaModo(p.modo_calculo)}
                          </span>
                          {p.modo_interpretacion === "perfil" && (
                            <span className="rounded-full px-2 py-0.5 bg-teal-600/10 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
                              Perfil
                            </span>
                          )}
                          {p.informante_tipo !== "estudiante" && (
                            <span className="rounded-full px-2 py-0.5 bg-mist dark:bg-surface-raised-dark text-ink/60 dark:text-ink-dark/60">
                              Informante: {p.informante_tipo}
                            </span>
                          )}
                          {!p.activa && (
                            <span className="rounded-full px-2 py-0.5 bg-border dark:bg-border-dark text-ink/60 dark:text-ink-dark/60">Inactiva</span>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-2 pt-1 border-t border-border/70 dark:border-border-dark">
                          <button
                            type="button"
                            onClick={() => toggle(p)}
                            aria-expanded={expandida}
                            className="inline-flex items-center gap-1 pt-2 text-[12px] font-semibold text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark"
                          >
                            <ChevronDown size={14} aria-hidden="true" className={`transition-transform ${expandida ? "rotate-180" : ""}`} />
                            {expandida ? "Ocultar detalle" : "Ver detalle"}
                          </button>
                          <button
                            type="button"
                            onClick={() => verResultadosDe(p)}
                            className="inline-flex items-center gap-1 pt-2 text-[12px] font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
                          >
                            Ver resultados
                            <ArrowRight size={13} aria-hidden="true" />
                          </button>
                        </div>
                      </div>

                      {expandida && (
                        <div className="border-t border-border dark:border-border-dark bg-mist/40 dark:bg-surface-raised-dark px-4 py-3 space-y-2">
                          {cargandoDetalle && <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">Cargando...</p>}
                          <TextoError className="text-xs">{errorDetalle}</TextoError>
                          {p.instrucciones && (
                            <p className="m-0 text-[12px] text-ink/65 dark:text-ink-dark/65 italic line-clamp-4">{p.instrucciones}</p>
                          )}
                          {!cargandoDetalle && detalle && detalle.id === p.id && (
                            <div>
                              <p className="m-0 mb-1.5 text-[10.5px] font-bold text-ink/50 dark:text-ink-dark/50 uppercase tracking-wide">
                                Dimensiones ({detalle.dimensiones.length})
                              </p>
                              {detalle.dimensiones.length === 0 ? (
                                <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50 italic">Sin dimensiones configuradas.</p>
                              ) : (
                                <div className="flex flex-wrap gap-1.5">
                                  {detalle.dimensiones.map((d) => (
                                    <span
                                      key={d.id}
                                      className="rounded-md border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2 py-0.5 text-[11.5px] text-ink/75 dark:text-ink-dark/75"
                                    >
                                      {d.nombre}
                                      {d.tipo_calculo !== "items" ? ` (${d.tipo_calculo})` : ""}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}

      {/* =========================== RESULTADOS =========================== */}
      {/* Dashboard por salón o grado — cruza TODAS las campañas en las que
          se aplicó la prueba elegida para los alumnos de ese salón/grado,
          a diferencia del dashboard de una campaña puntual
          (/campanas/[id]/dashboard). Ver GET /educativo/dashboard/academico. */}
      {vista === "resultados" && (
        <>
          <form
            onSubmit={verDashboardAcademico}
            className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 flex flex-col gap-3"
          >
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <ControlSegmentado<"seccion" | "grado" | "institucion">
                etiqueta="Ámbito"
                valor={dashAmbito}
                onCambiar={setDashAmbito}
                opciones={[
                  { valor: "seccion", etiqueta: "Un salón" },
                  { valor: "grado", etiqueta: "Grado completo" },
                  { valor: "institucion", etiqueta: "Todo el colegio" },
                ]}
              />
              {pruebaElegida && (
                <p className="m-0 text-[11.5px] text-ink/50 dark:text-ink-dark/50 truncate max-w-md" title={pruebaElegida.nombre_publico}>
                  {pruebaElegida.nombre_publico}
                </p>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr_auto] gap-3 items-end">
              <label className={etiquetaCampo}>
                <span className={textoEtiqueta}>Prueba</span>
                <Select required value={dashPruebaId} onChange={(e) => setDashPruebaId(e.target.value)}>
                  <option value="">Elige una prueba...</option>
                  {(pruebas ?? []).map((p) => (
                    <option key={p.id} value={p.id} title={p.nombre_publico}>
                      {p.nombre_corto || p.nombre_tecnico}
                    </option>
                  ))}
                </Select>
              </label>

              {dashAmbito !== "institucion" ? (
                <>
                  <label className={etiquetaCampo}>
                    <span className={textoEtiqueta}>Nivel</span>
                    <Select required value={dashNivelId} onChange={(e) => setDashNivelId(e.target.value)}>
                      <option value="">Elige un nivel...</option>
                      {niveles.map((n) => (
                        <option key={n.id} value={n.id}>
                          {n.nombre}
                        </option>
                      ))}
                    </Select>
                  </label>

                  <label className={etiquetaCampo}>
                    <span className={textoEtiqueta}>Grado</span>
                    <Select required value={dashGradoId} onChange={(e) => setDashGradoId(e.target.value)} disabled={!dashNivelId}>
                      <option value="">Elige un grado...</option>
                      {grados.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.nombre}
                        </option>
                      ))}
                    </Select>
                  </label>

                  {dashAmbito === "seccion" ? (
                    <label className={etiquetaCampo}>
                      <span className={textoEtiqueta}>Sección</span>
                      <Select required value={dashSeccionId} onChange={(e) => setDashSeccionId(e.target.value)} disabled={!dashGradoId}>
                        <option value="">Elige una sección...</option>
                        {secciones.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.nombre} ({s.anio_escolar})
                          </option>
                        ))}
                      </Select>
                    </label>
                  ) : (
                    <div className="hidden lg:block" />
                  )}
                </>
              ) : (
                <p className="m-0 lg:col-span-3 text-[12px] text-ink/50 dark:text-ink-dark/50 pb-2.5">
                  Se combinan todos los alumnos del colegio evaluados con esta prueba.
                </p>
              )}

              <Boton type="submit" disabled={cargandoDashboard} className="whitespace-nowrap">
                {cargandoDashboard ? "Cargando..." : "Ver dashboard"}
              </Boton>
            </div>
          </form>

          <TextoError>{errorDashboard}</TextoError>

          {!dashboard && !cargandoDashboard && (
            <VacioFicha
              icono={BarChart3}
              texto="Elige una prueba y un salón, grado o el colegio completo para ver cómo le fue al grupo, combinando todas las campañas en las que se aplicó."
            />
          )}

          {cargandoDashboard && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <EsqueletoTarjetas cantidad={4} />
            </div>
          )}

          {dashboard && (
            <div className="flex flex-col gap-4">
              {/* --- Cabecera del resultado --- */}
              <div className="flex items-end justify-between flex-wrap gap-3">
                <div className="min-w-0">
                  <p className="m-0 font-display text-[19px] font-bold text-teal-900 dark:text-ink-dark leading-tight">
                    {dashboard.nombre_corto_prueba || dashboard.nombre_prueba}
                    <span className="text-ink/35 dark:text-ink-dark/35 font-semibold"> · </span>
                    {dashboard.ambito.nombre}
                  </p>
                  <p className="m-0 mt-0.5 text-[12px] text-ink/55 dark:text-ink-dark/55">
                    {dashboard.total_inscritos} inscrito(s) · {dashboard.total_finalizados} finalizado(s) · {dashboard.total_pendientes} pendiente(s)
                  </p>
                </div>
                <Boton variante="secundario" onClick={exportarDashboardAcademicoExcel} disabled={exportandoDashboard} className="inline-flex items-center gap-2">
                  <Download size={15} aria-hidden="true" />
                  {exportandoDashboard ? "Exportando..." : "Exportar Excel"}
                </Boton>
              </div>

              {/* --- KPIs --- */}
              <div className={`grid grid-cols-2 gap-3 ${muestraAlertas ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
                <TarjetaKpi icono={Users} tono="azul" etiqueta="Inscritos" valor={dashboard.total_inscritos} />
                <TarjetaKpi
                  icono={Gauge}
                  tono="azul"
                  etiqueta="Avance de aplicación"
                  valor={`${avance}%`}
                  detalle={
                    <span className="mt-1.5 block h-1 w-24 rounded-full bg-border dark:bg-border-dark overflow-hidden">
                      <span className="block h-full rounded-full bg-teal-600 dark:bg-teal-accent-dark" style={{ width: `${avance}%` }} />
                    </span>
                  }
                />
                <TarjetaKpi
                  icono={Clock}
                  tono="neutro"
                  etiqueta="Pendientes de rendir"
                  valor={dashboard.total_pendientes}
                  onClick={() => setFiltroAlumnos((f) => (f === "pendientes" ? "todos" : "pendientes"))}
                  activa={filtroAlumnos === "pendientes"}
                />
                {muestraAlertas && (
                  <TarjetaKpi
                    icono={AlertTriangle}
                    tono="riesgo"
                    etiqueta="Alumnos en alerta"
                    valor={alumnosEnAlerta}
                    onClick={() => setFiltroAlumnos((f) => (f === "alerta" ? "todos" : "alerta"))}
                    activa={filtroAlumnos === "alerta"}
                  />
                )}
              </div>

              {/* --- Resumen estadístico interactivo --- */}
              {dashboard.resumen_estadistico.dimensiones.length > 0 && (
                <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
                  <div className="flex items-center justify-between gap-2 mb-3">
                    <h2 className="m-0 flex items-center gap-2 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
                      <BarChart3 size={16} className="text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                      Resumen estadístico
                    </h2>
                    <span className="text-[11.5px] text-ink/45 dark:text-ink-dark/45">
                      {dashboard.resumen_estadistico.dimensiones.length} dimensión(es)
                    </span>
                  </div>
                  <PanelDimensiones resumen={dashboard.resumen_estadistico} />
                </section>
              )}

              {/* --- Análisis: tendencia + comparación (solo un salón puntual) --- */}
              {dashboard.ambito.tipo === "seccion" && (
                <div className={`grid gap-4 ${secciones.length > 1 ? "lg:grid-cols-2" : ""}`}>
                  {/* Tendencia en el tiempo — solo tiene sentido para UN salón puntual
                      (ver docstring de crud.obtener_tendencia_seccion: un grado mezclaría
                      cohortes de campañas distintas en una sola línea). */}
                  <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 space-y-2 min-w-0">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <h2 className="m-0 flex items-center gap-2 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
                        <TrendingUp size={16} className="text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                        Tendencia en el tiempo
                      </h2>
                      <Boton variante="secundario" onClick={verTendenciaSeccion} disabled={cargandoTendencia}>
                        {cargandoTendencia ? "Cargando..." : tendencia ? "Actualizar" : "Ver tendencia en el tiempo"}
                      </Boton>
                    </div>
                    {!tendencia && !errorTendencia && (
                      <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">
                        Evolución de la media del salón campaña a campaña.
                      </p>
                    )}
                    <TextoError>{errorTendencia}</TextoError>
                    {tendencia &&
                      (tendencia.puntos.length < 2 ? (
                        <p className="m-0 text-[12.5px] text-ink/60 dark:text-ink-dark/60 italic">
                          Este salón solo tiene {tendencia.puntos.length} campaña(s) con resultados para esta prueba — hace falta al
                          menos dos para mostrar una evolución.
                        </p>
                      ) : (
                        <div className="divide-y divide-border dark:divide-border-dark max-h-[28rem] overflow-y-auto">
                          {tendencia.puntos[tendencia.puntos.length - 1].resumen_estadistico.dimensiones.map((dRef) => (
                            <GraficoTendenciaDimension
                              key={dRef.nombre}
                              nombreDimension={dRef.nombre}
                              puntos={tendencia.puntos.map((punto) => {
                                const d = punto.resumen_estadistico.dimensiones.find((x) => x.nombre === dRef.nombre);
                                return {
                                  evaluacionId: punto.evaluacion_id,
                                  nombreGrupo: punto.nombre_grupo,
                                  fecha: punto.fecha,
                                  media: d?.media ?? null,
                                  maximoEscala: d?.maximo_escala ?? null,
                                };
                              })}
                            />
                          ))}
                        </div>
                      ))}
                  </section>

                  {/* Comparar con otra sección del mismo grado, lado a lado — dos
                      llamadas al mismo /dashboard/academico, sin endpoint nuevo. */}
                  {secciones.length > 1 && (
                    <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 space-y-2.5 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <GitCompare size={16} className="text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                        <p className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark">Comparar con otra sección del mismo grado</p>
                        <div className="flex items-center gap-2 w-full">
                          <Select value={compararConSeccionId} onChange={(e) => setCompararConSeccionId(e.target.value)} className="flex-1 min-w-0">
                            <option value="">Elige una sección...</option>
                            {secciones
                              .filter((s) => String(s.id) !== dashSeccionId)
                              .map((s) => (
                                <option key={s.id} value={s.id}>
                                  {s.nombre} ({s.anio_escolar})
                                </option>
                              ))}
                          </Select>
                          <Boton variante="secundario" onClick={compararSeccion} disabled={cargandoComparacion || !compararConSeccionId}>
                            {cargandoComparacion ? "Cargando..." : "Comparar"}
                          </Boton>
                        </div>
                      </div>
                      <TextoError>{errorComparacion}</TextoError>
                      {!dashboardComparado && !errorComparacion && (
                        <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">Pon dos salones del mismo grado lado a lado.</p>
                      )}
                    </section>
                  )}
                </div>
              )}

              {dashboardComparado && (
                <div className="grid sm:grid-cols-2 gap-4">
                  {[dashboard, dashboardComparado].map((dash, i) => (
                    <div
                      key={i}
                      className={`rounded-xl border bg-surface dark:bg-surface-dark p-4 ${
                        i === 0 ? "border-teal-400/70 dark:border-teal-accent-dark/60" : "border-border dark:border-border-dark"
                      }`}
                    >
                      <p className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark">{dash.ambito.nombre}</p>
                      <p className="m-0 text-[12px] text-ink/55 dark:text-ink-dark/55 mb-2">
                        {dash.total_finalizados} finalizado(s) de {dash.total_inscritos}
                      </p>
                      <ResumenEstadisticoPrueba resumen={dash.resumen_estadistico} />
                    </div>
                  ))}
                </div>
              )}

              {/* --- Alumnos --- */}
              <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark overflow-hidden">
                <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-border dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark">
                  <h2 className="m-0 flex items-center gap-2 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
                    <Users size={16} className="text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                    Alumnos
                    <span className="text-[12px] font-semibold text-ink/40 dark:text-ink-dark/40">
                      {alumnosVisibles.length}/{dashboard.alumnos.length}
                    </span>
                  </h2>
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="relative">
                      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                      <input
                        type="search"
                        aria-label="Buscar alumno"
                        placeholder="Buscar alumno…"
                        value={busquedaAlumno}
                        onChange={(e) => setBusquedaAlumno(e.target.value)}
                        className="w-48 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark pl-8 pr-2.5 py-1.5 text-[12.5px] focus:outline-none focus:ring-2 focus:ring-teal-400"
                      />
                    </div>
                    <ControlSegmentado<FiltroAlumnos>
                      etiqueta="Filtrar alumnos"
                      valor={filtroAlumnos}
                      onCambiar={setFiltroAlumnos}
                      opciones={[
                        { valor: "todos", etiqueta: "Todos" },
                        ...(muestraAlertas ? [{ valor: "alerta" as const, etiqueta: `En alerta (${alumnosEnAlerta})` }] : []),
                        { valor: "pendientes", etiqueta: `Pendientes (${alumnosPendientes})` },
                      ]}
                    />
                  </div>
                </div>

                <div className="max-h-[34rem] overflow-y-auto divide-y divide-border dark:divide-border-dark">
                  {dashboard.alumnos.length === 0 ? (
                    <p className="m-0 text-sm text-ink/60 dark:text-ink-dark/60 italic p-4">Sin alumnos con esta prueba todavía.</p>
                  ) : alumnosVisibles.length === 0 ? (
                    <p className="m-0 text-sm text-ink/50 dark:text-ink-dark/50 italic p-4">Ningún alumno coincide con el filtro.</p>
                  ) : (
                    alumnosVisibles.map((a) => {
                      const enAlerta = alumnoEnAlerta(a);
                      const finalizado = a.estado === "Finalizado";
                      return (
                        <div
                          key={a.inscripcion_id}
                          className={`px-4 py-3 text-sm ${enAlerta ? "border-l-[3px] border-l-amber" : "border-l-[3px] border-l-transparent"}`}
                        >
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="font-semibold text-ink dark:text-ink-dark">
                              {a.nombre_completo}
                              {a.seccion ? <span className="text-ink/40 dark:text-ink-dark/40 font-normal"> · {a.seccion}</span> : ""}
                            </span>
                            <span className="flex items-center gap-1.5">
                              {enAlerta && (
                                <span className="inline-flex items-center gap-1 rounded-full bg-amber/15 px-2 py-0.5 text-[10.5px] font-bold text-amber-700 dark:text-amber">
                                  <AlertTriangle size={10} strokeWidth={2.4} aria-hidden="true" />
                                  Alerta
                                </span>
                              )}
                              <span
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${
                                  finalizado
                                    ? "bg-teal-600/10 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
                                    : "bg-border dark:bg-border-dark text-ink/60 dark:text-ink-dark/60"
                                }`}
                              >
                                {finalizado && <CheckCircle2 size={10} aria-hidden="true" />}
                                {a.estado}
                              </span>
                            </span>
                          </div>
                          {a.resultados.length > 0 && (
                            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-x-5 gap-y-2 mt-2">
                              {a.resultados.map((r) =>
                                r.minimo != null && r.maximo != null ? (
                                  <DimensionBar
                                    key={r.dimension}
                                    nombre={r.dimension}
                                    puntajeDirecto={r.puntaje_directo}
                                    minimo={r.minimo}
                                    maximo={r.maximo}
                                    nivel={r.nivel ?? "—"}
                                    esAlerta={r.es_alerta ?? false}
                                  />
                                ) : (
                                  <span key={r.dimension} className="text-xs text-ink/60 dark:text-ink-dark/60">
                                    {r.dimension}: {r.nivel ?? "—"}
                                  </span>
                                ),
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </section>
            </div>
          )}
        </>
      )}
    </div>
  );
}
