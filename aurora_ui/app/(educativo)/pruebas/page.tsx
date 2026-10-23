"use client";

import { useEffect, useState } from "react";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import { DimensionBar } from "@/components/ui/DimensionBar";
import { ResumenEstadisticoPrueba } from "@/components/ui/ResumenEstadisticoPrueba";
import { GraficoTendenciaDimension } from "@/components/ui/GraficoTendenciaDimension";
import type {
  Prueba,
  PruebaDetalle,
  NivelEducativo,
  Grado,
  Seccion,
  DashboardAcademico,
  TendenciaSeccion,
} from "@/types/api";

// Catálogo de solo lectura — cargar una prueba nueva (ítems, dimensiones,
// baremos) es un ejercicio de datos vía seed/API directa (ver CLAUDE.md
// "Scoring engine"), no un formulario de esta pantalla. Esto solo deja ver
// qué hay disponible, para elegir al crear una campaña.
export default function PruebasPage() {
  const { sesion } = useAuth();
  const [pruebas, setPruebas] = useState<Prueba[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [expandidaId, setExpandidaId] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<PruebaDetalle | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [errorDetalle, setErrorDetalle] = useState<string | null>(null);

  // --- Dashboard por salón o grado (cruza todas las campañas de una
  // prueba) — ver GET /educativo/dashboard/academico. ---
  const [dashPruebaId, setDashPruebaId] = useState("");
  const [dashAmbito, setDashAmbito] = useState<"seccion" | "grado">("seccion");
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
    if (dashAmbito === "seccion") params.set("seccion_id", dashSeccionId);
    else params.set("grado_id", dashGradoId);
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

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      <h1 className="font-display text-2xl text-teal-900">Pruebas</h1>
      <p className="text-sm text-ink/60">
        Catálogo de instrumentos disponibles para crear una campaña. Cargar un instrumento nuevo (ítems, dimensiones,
        baremos) es trabajo de datos, no se hace desde aquí.
      </p>

      <TextoError>{error}</TextoError>
      {loading && <p className="text-sm text-ink/40">Cargando...</p>}

      {pruebas && pruebas.length === 0 && (
        <p className="text-sm text-ink/60 italic">No hay ninguna prueba disponible para tu institución todavía.</p>
      )}

      {pruebas && pruebas.length > 0 && (
        <div className="space-y-2">
          {pruebas.map((p) => {
            const expandida = expandidaId === p.id;
            return (
              <div key={p.id} className="rounded-card border border-border overflow-hidden bg-white">
                <button
                  onClick={() => toggle(p)}
                  className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-mist/40 transition-colors"
                >
                  <div>
                    {/* Título corto arriba (nombre_corto curado, o nombre_tecnico de
                        respaldo — ej. "PHQ-9") para no saturar la fila; el nombre
                        completo queda debajo como descripción secundaria. */}
                    <p className="text-sm font-semibold text-teal-900">{p.nombre_corto || p.nombre_tecnico}</p>
                    <p className="text-xs text-ink/50">{p.nombre_publico}</p>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-ink/60">
                    <span className="rounded-full px-2 py-0.5 bg-mist/70">{p.modo_calculo}</span>
                    {p.informante_tipo !== "estudiante" && (
                      <span className="rounded-full px-2 py-0.5 bg-mist/70">Informante: {p.informante_tipo}</span>
                    )}
                    {!p.activa && <span className="rounded-full px-2 py-0.5 bg-border">Inactiva</span>}
                  </div>
                </button>

                {expandida && (
                  <div className="border-t border-border p-4 space-y-2">
                    {cargandoDetalle && <p className="text-sm text-ink/60">Cargando...</p>}
                    <TextoError>{errorDetalle}</TextoError>
                    {p.instrucciones && <p className="text-sm text-ink/70 italic">{p.instrucciones}</p>}
                    {!cargandoDetalle && detalle && detalle.id === p.id && (
                      <div>
                        <p className="text-xs font-semibold text-ink/70 uppercase tracking-wide mb-1">
                          Dimensiones ({detalle.dimensiones.length})
                        </p>
                        {detalle.dimensiones.length === 0 ? (
                          <p className="text-sm text-ink/60 italic">Sin dimensiones configuradas.</p>
                        ) : (
                          <ul className="text-sm text-ink/80 list-disc list-inside">
                            {detalle.dimensiones.map((d) => (
                              <li key={d.id}>
                                {d.nombre}
                                {d.tipo_calculo !== "items" ? ` (${d.tipo_calculo})` : ""}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Dashboard por salón o grado — cruza TODAS las campañas en las que
          se aplicó la prueba elegida para los alumnos de ese salón/grado,
          a diferencia del dashboard de una campaña puntual
          (/campanas/[id]/dashboard). Ver GET /educativo/dashboard/academico. */}
      <div className="bg-white rounded-card border border-border p-6 space-y-4 mt-6">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Dashboard por salón o grado
        </h2>
        <p className="text-sm text-ink/60">
          Elige una prueba y un salón o grado para ver cómo le fue a ese grupo, combinando todas las campañas en las
          que se aplicó esa prueba.
        </p>

        <form onSubmit={verDashboardAcademico} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-ink/70 font-medium">Prueba</span>
              <Select required value={dashPruebaId} onChange={(e) => setDashPruebaId(e.target.value)}>
                <option value="">Elige una prueba...</option>
                {(pruebas ?? []).map((p) => (
                  <option key={p.id} value={p.id} title={p.nombre_publico}>
                    {p.nombre_corto || p.nombre_tecnico}
                  </option>
                ))}
              </Select>
            </label>

            <label className="flex flex-col gap-1 text-sm">
              <span className="text-ink/70 font-medium">Ámbito</span>
              <Select value={dashAmbito} onChange={(e) => setDashAmbito(e.target.value as "seccion" | "grado")}>
                <option value="seccion">Un salón puntual</option>
                <option value="grado">Grado completo (todas sus secciones)</option>
              </Select>
            </label>

            <label className="flex flex-col gap-1 text-sm">
              <span className="text-ink/70 font-medium">Nivel</span>
              <Select required value={dashNivelId} onChange={(e) => setDashNivelId(e.target.value)}>
                <option value="">Elige un nivel...</option>
                {niveles.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.nombre}
                  </option>
                ))}
              </Select>
            </label>

            <label className="flex flex-col gap-1 text-sm">
              <span className="text-ink/70 font-medium">Grado</span>
              <Select required value={dashGradoId} onChange={(e) => setDashGradoId(e.target.value)} disabled={!dashNivelId}>
                <option value="">Elige un grado...</option>
                {grados.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.nombre}
                  </option>
                ))}
              </Select>
            </label>

            {dashAmbito === "seccion" && (
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 font-medium">Sección</span>
                <Select
                  required
                  value={dashSeccionId}
                  onChange={(e) => setDashSeccionId(e.target.value)}
                  disabled={!dashGradoId}
                >
                  <option value="">Elige una sección...</option>
                  {secciones.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre} ({s.anio_escolar})
                    </option>
                  ))}
                </Select>
              </label>
            )}
          </div>

          <Boton type="submit" disabled={cargandoDashboard}>
            {cargandoDashboard ? "Cargando..." : "Ver dashboard"}
          </Boton>
        </form>

        <TextoError>{errorDashboard}</TextoError>

        {dashboard && (
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <p className="text-sm font-semibold text-teal-900">
                  {dashboard.nombre_corto_prueba || dashboard.nombre_prueba} — {dashboard.ambito.nombre}
                </p>
                <p className="text-xs text-ink/50">{dashboard.nombre_prueba}</p>
                <p className="text-xs text-ink/60">
                  {dashboard.total_inscritos} inscrito(s) · {dashboard.total_finalizados} finalizado(s) ·{" "}
                  {dashboard.total_pendientes} pendiente(s)
                </p>
              </div>
              <Boton variante="secundario" onClick={exportarDashboardAcademicoExcel} disabled={exportandoDashboard}>
                {exportandoDashboard ? "Exportando..." : "Exportar Excel"}
              </Boton>
            </div>

            {dashboard.resumen_estadistico.dimensiones.length > 0 && (
              <div className="border-t border-border pt-3">
                <p className="text-sm font-semibold text-teal-900 mb-2">Resumen estadístico</p>
                <ResumenEstadisticoPrueba resumen={dashboard.resumen_estadistico} />
              </div>
            )}

            {/* Tendencia en el tiempo — solo tiene sentido para UN salón puntual
                (ver docstring de crud.obtener_tendencia_seccion: un grado mezclaría
                cohortes de campañas distintas en una sola línea). */}
            {dashboard.ambito.tipo === "seccion" && (
              <div className="border-t border-border pt-3 space-y-2">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-sm font-semibold text-teal-900">Tendencia en el tiempo</p>
                  <Boton variante="secundario" onClick={verTendenciaSeccion} disabled={cargandoTendencia}>
                    {cargandoTendencia ? "Cargando..." : tendencia ? "Actualizar" : "Ver tendencia en el tiempo"}
                  </Boton>
                </div>
                <TextoError>{errorTendencia}</TextoError>
                {tendencia && (
                  tendencia.puntos.length < 2 ? (
                    <p className="text-sm text-ink/60 italic">
                      Este salón solo tiene {tendencia.puntos.length} campaña(s) con resultados para esta prueba — hace
                      falta al menos dos para mostrar una evolución.
                    </p>
                  ) : (
                    <div className="divide-y divide-border">
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
                  )
                )}
              </div>
            )}

            {/* Comparar con otra sección del mismo grado, lado a lado — dos
                llamadas al mismo /dashboard/academico, sin endpoint nuevo. */}
            {dashboard.ambito.tipo === "seccion" && secciones.length > 1 && (
              <div className="border-t border-border pt-3 space-y-2">
                <p className="text-sm font-semibold text-teal-900">Comparar con otra sección del mismo grado</p>
                <div className="flex items-center gap-3 flex-wrap">
                  <Select
                    value={compararConSeccionId}
                    onChange={(e) => setCompararConSeccionId(e.target.value)}
                    className="max-w-xs"
                  >
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
                <TextoError>{errorComparacion}</TextoError>
                {dashboardComparado && (
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div className="border border-border rounded-card p-3">
                      <p className="text-sm font-semibold text-teal-900">{dashboard.ambito.nombre}</p>
                      <p className="text-xs text-ink/60 mb-2">
                        {dashboard.total_finalizados} finalizado(s) de {dashboard.total_inscritos}
                      </p>
                      <ResumenEstadisticoPrueba resumen={dashboard.resumen_estadistico} />
                    </div>
                    <div className="border border-border rounded-card p-3">
                      <p className="text-sm font-semibold text-teal-900">{dashboardComparado.ambito.nombre}</p>
                      <p className="text-xs text-ink/60 mb-2">
                        {dashboardComparado.total_finalizados} finalizado(s) de {dashboardComparado.total_inscritos}
                      </p>
                      <ResumenEstadisticoPrueba resumen={dashboardComparado.resumen_estadistico} />
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="max-h-96 overflow-y-auto border border-border rounded-card divide-y divide-border">
              {dashboard.alumnos.length === 0 ? (
                <p className="text-sm text-ink/60 italic p-3">Sin alumnos con esta prueba todavía.</p>
              ) : (
                dashboard.alumnos.map((a) => (
                  <div key={a.inscripcion_id} className="p-3 text-sm">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-medium">
                        {a.nombre_completo}
                        {a.seccion ? <span className="text-ink/40 font-normal"> · {a.seccion}</span> : ""}
                      </span>
                      <span className="text-xs text-ink/60">{a.estado}</span>
                    </div>
                    {a.resultados.length > 0 && (
                      <div className="flex flex-col gap-1.5 mt-1">
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
                            <span key={r.dimension} className="text-xs text-ink/60">
                              {r.dimension}: {r.nivel ?? "—"}
                            </span>
                          )
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
