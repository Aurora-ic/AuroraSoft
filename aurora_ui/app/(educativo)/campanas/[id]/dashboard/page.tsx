"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useVirtualizer } from "@tanstack/react-virtual";
import { apiClient, descargarBlob } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { DimensionBar } from "@/components/ui/DimensionBar";
import { ResumenEstadisticoPrueba } from "@/components/ui/ResumenEstadisticoPrueba";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import type { DashboardCampana, InscripcionCampana, Prueba } from "@/types/api";

// Convierte el datetime que manda el backend al formato que acepta
// <input type="datetime-local"> — mismo criterio inverso que `campanas/
// nueva/page.tsx` ya usa al crear (`new Date(form.fecha_fin).toISOString()`):
// esa pantalla toma la hora LOCAL que el usuario escribe y la convierte a
// UTC antes de mandarla; esto arma un <input> con los componentes LOCALES
// de vuelta a partir de lo que el backend devuelve, para que editar sin
// cambiar la fecha la deje intacta.
function isoParaInputLocal(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function DashboardCampanaPage() {
  const params = useParams();
  const { sesion } = useAuth();
  const campanaId = params.id as string;

  const [dashboard, setDashboard] = useState<DashboardCampana | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [mostrarLinks, setMostrarLinks] = useState(false);
  const [links, setLinks] = useState<InscripcionCampana[] | null>(null);
  const [errorLinks, setErrorLinks] = useState<string | null>(null);

  const [exportando, setExportando] = useState(false);
  const [accionando, setAccionando] = useState(false);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [motivoCancelar, setMotivoCancelar] = useState("");
  const [mostrarCancelar, setMostrarCancelar] = useState(false);

  const [pruebas, setPruebas] = useState<Prueba[]>([]);
  const [mostrarEditar, setMostrarEditar] = useState(false);
  const [formEditar, setFormEditar] = useState({ nombre_grupo: "", fecha_fin: "", prueba_id: "" });
  const [guardandoEdicion, setGuardandoEdicion] = useState(false);
  const [errorEdicion, setErrorEdicion] = useState<string | null>(null);

  const [reprocesandoId, setReprocesandoId] = useState<number | null>(null);
  const [mostrarReprocesarId, setMostrarReprocesarId] = useState<number | null>(null);
  const [motivoReprocesar, setMotivoReprocesar] = useState("");
  const [errorReprocesar, setErrorReprocesar] = useState<string | null>(null);
  // Riesgo operacional (docs/gaps-pendientes.md): si el reproceso retracta
  // una versión que ya estaba liberada/visible, no hay forma de invalidar
  // un PDF que el alumno ya pudo haber descargado — lo único que la
  // plataforma puede hacer es dejarlo explícito aquí mismo.
  const [avisoRetraccion, setAvisoRetraccion] = useState<string | null>(null);

  // 🆕 Virtualización de la tabla de alumnos (hallazgo de escala, docs/
  // gaps-pendientes.md) — una campaña de un colegio grande puede matricular
  // cientos o miles de alumnos; renderizar esa cantidad de <tr> reales (cada
  // una con varias DimensionBar y, potencialmente, el formulario inline de
  // "Reprocesar") degradaba el navegador mucho antes de llegar a esa escala.
  // Hook incondicional (regla de hooks) aunque `dashboard` todavía sea null
  // al montar — cuenta sobre `dashboard?.alumnos.length ?? 0`.
  const filasAlumnosRef = useRef<HTMLDivElement>(null);
  const virtualizadorAlumnos = useVirtualizer({
    count: dashboard?.alumnos.length ?? 0,
    getScrollElement: () => filasAlumnosRef.current,
    estimateSize: () => 60,
    overscan: 10,
  });

  const puedeAdministrar = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  // 🔒 Reprocesar está restringido a admin/superadmin en el backend
  // (permisos.SOLO_ADMINISTRATIVO, deliberadamente excluye psicólogo — ver
  // docs/informes-psicometricos.md: corregir un baremo y reprocesar es una
  // acción administrativa sobre la configuración del motor, no un juicio
  // clínico caso por caso).
  const puedeReprocesar = sesion?.rol === "admin" || sesion?.rol === "superadmin";

  useEffect(() => {
    if (!campanaId) return;
    apiClient
      .get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`)
      .then(setDashboard)
      .catch((err) => setError(err.message || "No se pudo cargar el dashboard de esta campaña."))
      .finally(() => setLoading(false));
  }, [campanaId]);

  // Catálogo de pruebas para el selector de "Editar campaña" — solo hace
  // falta para quien puede administrar, y solo se pide una vez.
  useEffect(() => {
    if (!puedeAdministrar) return;
    apiClient.get<Prueba[]>("/educativo/pruebas/").then(setPruebas).catch(() => setPruebas([]));
  }, [puedeAdministrar]);

  function abrirEditar() {
    if (!dashboard) return;
    setFormEditar({
      nombre_grupo: dashboard.nombre_grupo,
      fecha_fin: isoParaInputLocal(dashboard.fecha_fin),
      prueba_id: String(dashboard.prueba_id),
    });
    setErrorEdicion(null);
    setMostrarEditar(true);
  }

  async function guardarEdicion(e: React.FormEvent) {
    e.preventDefault();
    setGuardandoEdicion(true);
    setErrorEdicion(null);
    try {
      await apiClient.patch(`/educativo/campanas/${campanaId}`, {
        nombre_grupo: formEditar.nombre_grupo,
        fecha_fin: formEditar.fecha_fin ? new Date(formEditar.fecha_fin).toISOString() : null,
        prueba_id: Number(formEditar.prueba_id),
      });
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
      setMostrarEditar(false);
    } catch (err: any) {
      setErrorEdicion(err.message || "No se pudo guardar la edición de la campaña.");
    } finally {
      setGuardandoEdicion(false);
    }
  }

  async function reprocesar(e: React.FormEvent, inscripcionId: number) {
    e.preventDefault();
    setReprocesandoId(inscripcionId);
    setErrorReprocesar(null);
    try {
      const resultado = await apiClient.post<{
        retraccion_informe_liberado?: boolean;
        revisor_original_notificado?: boolean;
      }>(`/educativo/inscripciones/${inscripcionId}/reprocesar`, { motivo: motivoReprocesar });
      if (resultado?.retraccion_informe_liberado) {
        setAvisoRetraccion(
          resultado.revisor_original_notificado
            ? "Esta corrección retiene de nuevo un informe que ya estaba liberado y visible para el alumno. " +
                "Se avisó a quien lo había liberado originalmente, pero si el alumno o su apoderado ya " +
                "descargaron el PDF anterior, esa copia sigue en su poder: la plataforma no puede invalidarla."
            : "Esta corrección retiene de nuevo un informe que ya estaba liberado y visible para el alumno, " +
                "pero no se encontró a quien lo había liberado originalmente para avisarle. Si el alumno o su " +
                "apoderado ya descargaron el PDF anterior, esa copia sigue en su poder: la plataforma no puede " +
                "invalidarla — contáctalos directamente si corresponde."
        );
      } else {
        setAvisoRetraccion(null);
      }
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
      setMostrarReprocesarId(null);
      setMotivoReprocesar("");
    } catch (err: any) {
      setErrorReprocesar(err.message || "No se pudo reprocesar esta inscripción.");
    } finally {
      setReprocesandoId(null);
    }
  }

  async function alternarLinks() {
    if (mostrarLinks) {
      setMostrarLinks(false);
      return;
    }
    setMostrarLinks(true);
    if (links !== null) return;
    setErrorLinks(null);
    try {
      const datos = await apiClient.get<InscripcionCampana[]>(`/educativo/campanas/${campanaId}/links`);
      setLinks(datos);
    } catch (err: any) {
      setErrorLinks(err.message || "No se pudieron cargar los links de esta campaña.");
    }
  }

  async function exportarExcel() {
    setExportando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/campanas/${campanaId}/exportar-excel`);
      descargarBlob(blob, `resultados_${campanaId}.xlsx`);
    } catch (err: any) {
      setError(err.message || "No se pudo exportar el Excel.");
    } finally {
      setExportando(false);
    }
  }

  async function cerrar() {
    setAccionando(true);
    setErrorAccion(null);
    try {
      await apiClient.post(`/educativo/campanas/${campanaId}/cerrar`, {});
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
    } catch (err: any) {
      setErrorAccion(err.message || "No se pudo cerrar la campaña.");
    } finally {
      setAccionando(false);
    }
  }

  async function cancelar(e: React.FormEvent) {
    e.preventDefault();
    setAccionando(true);
    setErrorAccion(null);
    try {
      await apiClient.post(`/educativo/campanas/${campanaId}/cancelar`, { motivo: motivoCancelar });
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
      setMostrarCancelar(false);
    } catch (err: any) {
      setErrorAccion(err.message || "No se pudo cancelar la campaña.");
    } finally {
      setAccionando(false);
    }
  }

  if (loading) return <div className="p-8 text-center text-teal-900">Cargando dashboard...</div>;
  if (error || !dashboard) return <div className="p-8"><TextoError>{error || "Campaña no encontrada."}</TextoError></div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="font-display text-2xl text-teal-900">{dashboard.nombre_grupo}</h1>
            <span
              className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                dashboard.estado === "activa"
                  ? "bg-teal-400/20 text-teal-900"
                  : dashboard.estado === "cerrada"
                    ? "bg-ink/10 text-ink/60"
                    : "bg-red-100 text-red-700"
              }`}
            >
              {dashboard.estado}
            </span>
          </div>
          <p className="text-sm text-ink/60">{dashboard.nombre_corto_prueba || dashboard.nombre_prueba}</p>
          {dashboard.nombre_corto_prueba && (
            <p className="text-xs text-ink/40">{dashboard.nombre_prueba}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {puedeAdministrar && dashboard.estado === "activa" && !mostrarEditar && (
            <button onClick={abrirEditar} className="text-sm text-teal-600 hover:underline font-medium">
              Editar campaña
            </button>
          )}
          <Boton variante="secundario" onClick={exportarExcel} disabled={exportando}>
            {exportando ? "Exportando..." : "Exportar Excel"}
          </Boton>
        </div>
      </div>

      {mostrarEditar && (
        <form onSubmit={guardarEdicion} className="bg-white rounded-card border border-border p-6 space-y-3">
          <h2 className="font-display text-lg text-teal-900">Editar campaña</h2>
          <TextoError>{errorEdicion}</TextoError>
          <div className="grid sm:grid-cols-2 gap-3">
            <CampoEditable etiqueta="Nombre del grupo">
              <Input
                required
                value={formEditar.nombre_grupo}
                onChange={(e) => setFormEditar({ ...formEditar, nombre_grupo: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Fecha de cierre (opcional)">
              <Input
                type="datetime-local"
                value={formEditar.fecha_fin}
                onChange={(e) => setFormEditar({ ...formEditar, fecha_fin: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Prueba" className="sm:col-span-2">
              <Select
                value={formEditar.prueba_id}
                disabled={dashboard.total_inscritos > 0}
                onChange={(e) => setFormEditar({ ...formEditar, prueba_id: e.target.value })}
              >
                {pruebas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre_corto || p.nombre_tecnico}
                  </option>
                ))}
              </Select>
              {dashboard.total_inscritos > 0 && (
                <span className="text-xs text-ink/50 mt-1">
                  Ya tiene {dashboard.total_inscritos} inscripción(es) — la prueba no se puede cambiar.
                </span>
              )}
            </CampoEditable>
          </div>
          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={guardandoEdicion}>
              {guardandoEdicion ? "Guardando..." : "Guardar cambios"}
            </Boton>
            <button
              type="button"
              onClick={() => setMostrarEditar(false)}
              className="text-sm text-ink/60 hover:text-ink hover:underline"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className="text-2xl font-display text-teal-900">{dashboard.total_inscritos}</p>
          <p className="text-xs text-ink/60">Inscritos</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className="text-2xl font-display text-teal-900">{dashboard.total_finalizados}</p>
          <p className="text-xs text-ink/60">Finalizados</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className="text-2xl font-display text-teal-900">{dashboard.total_pendientes}</p>
          <p className="text-xs text-ink/60">Pendientes</p>
        </div>
      </div>

      {dashboard.resumen_estadistico.dimensiones.length > 0 && (
        <div className="bg-white rounded-card border border-border p-6 space-y-3">
          <h2 className="font-display text-lg text-teal-900">Resumen estadístico</h2>
          <ResumenEstadisticoPrueba resumen={dashboard.resumen_estadistico} />
        </div>
      )}

      <div className="bg-white rounded-card border border-border p-6 space-y-3">
        <h2 className="font-display text-lg text-teal-900">Alumnos</h2>
        {dashboard.alumnos.length === 0 ? (
          <p className="text-sm text-ink/60 italic">Todavía no hay alumnos matriculados en esta campaña.</p>
        ) : (
          <>
            <TextoError>{errorReprocesar}</TextoError>
            {avisoRetraccion && (
              <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                ⚠ {avisoRetraccion}
              </p>
            )}
            <div ref={filasAlumnosRef} className="max-h-150 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-white">
                <TheadFila>
                  <Th className="px-2 py-1">Alumno</Th>
                  <Th className="px-2 py-1">Estado</Th>
                  <Th className="px-2 py-1">Resultados</Th>
                  {puedeReprocesar && <Th className="px-2 py-1">Acciones</Th>}
                </TheadFila>
              </thead>
              <tbody>
                {/* 🆕 Fila-colchón de arriba — ver mismo patrón en
                    estudiantes/importar/page.tsx (vista previa de Excel). */}
                {virtualizadorAlumnos.getVirtualItems().length > 0 && (
                  <tr style={{ height: virtualizadorAlumnos.getVirtualItems()[0].start }} aria-hidden>
                    <td colSpan={puedeReprocesar ? 4 : 3} />
                  </tr>
                )}
                {virtualizadorAlumnos.getVirtualItems().map((item) => {
                  const a = dashboard.alumnos[item.index];
                  return (
                  <tr
                    key={a.inscripcion_id}
                    data-index={item.index}
                    ref={virtualizadorAlumnos.measureElement}
                    className="border-b border-border"
                  >
                    <td className="px-2 py-1">{a.nombre_completo || "(sin nombre)"}</td>
                    <td className="px-2 py-1">{a.estado}</td>
                    <td className="px-2 py-1">
                      {a.resultados.length === 0 ? (
                        "—"
                      ) : (
                        <div className="flex flex-col gap-1.5 min-w-55">
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
                              // Sin rango de baremo disponible (sin baremo aplicable, o
                              // modo_interpretacion='perfil') — se mantiene como texto.
                              <span key={r.dimension} className="text-xs text-ink/70">
                                {r.dimension}: {r.nivel ?? r.puntaje_directo}
                              </span>
                            )
                          )}
                        </div>
                      )}
                    </td>
                    {puedeReprocesar && (
                      <td className="px-2 py-1 align-top">
                        {a.estado !== "Finalizado" ? (
                          "—"
                        ) : mostrarReprocesarId !== a.inscripcion_id ? (
                          <button
                            onClick={() => {
                              setMostrarReprocesarId(a.inscripcion_id);
                              setMotivoReprocesar("");
                              setErrorReprocesar(null);
                            }}
                            className="text-xs text-teal-600 hover:underline font-medium"
                          >
                            Reprocesar
                          </button>
                        ) : (
                          <form
                            onSubmit={(e) => reprocesar(e, a.inscripcion_id)}
                            className="flex flex-col gap-1.5 min-w-48"
                          >
                            {/* Deliberadamente NO <Input/>: esta fila de tabla necesita
                                px-2/py-1/text-xs más compacto que el tamaño estándar que
                                <Input/> ya trae fijo (px-3/py-2/text-sm) — pasar esas
                                clases por className no las sobrescribiría de forma
                                confiable (misma especificidad CSS, orden de generación de
                                Tailwind). */}
                            <input
                              required
                              minLength={3}
                              placeholder="Motivo (ej. corregí un baremo)"
                              value={motivoReprocesar}
                              onChange={(e) => setMotivoReprocesar(e.target.value)}
                              className="rounded-card border border-border px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                type="submit"
                                disabled={reprocesandoId === a.inscripcion_id}
                                className="text-xs text-white bg-teal-600 hover:bg-teal-900 rounded-card px-2 py-1 disabled:opacity-50"
                              >
                                {reprocesandoId === a.inscripcion_id ? "Reprocesando..." : "Confirmar"}
                              </button>
                              <button
                                type="button"
                                onClick={() => setMostrarReprocesarId(null)}
                                className="text-xs text-ink/50 hover:underline"
                              >
                                Cancelar
                              </button>
                            </div>
                          </form>
                        )}
                      </td>
                    )}
                  </tr>
                  );
                })}
                {/* 🆕 Fila-colchón de abajo — ver mismo patrón en
                    estudiantes/importar/page.tsx. */}
                {virtualizadorAlumnos.getVirtualItems().length > 0 && (
                  <tr
                    style={{
                      height:
                        virtualizadorAlumnos.getTotalSize() -
                        virtualizadorAlumnos.getVirtualItems()[virtualizadorAlumnos.getVirtualItems().length - 1].end,
                    }}
                    aria-hidden
                  >
                    <td colSpan={puedeReprocesar ? 4 : 3} />
                  </tr>
                )}
              </tbody>
            </table>
            </div>
          </>
        )}
      </div>

      <div className="bg-white rounded-card border border-border p-6 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg text-teal-900">Links mágicos</h2>
          <button onClick={alternarLinks} className="text-sm text-teal-600 hover:underline font-medium">
            {mostrarLinks ? "Ocultar" : "Ver links"}
          </button>
        </div>
        {mostrarLinks && (
          <>
            <TextoError>{errorLinks}</TextoError>
            {links === null ? (
              <p className="text-sm text-ink/60">Cargando...</p>
            ) : links.length === 0 ? (
              <p className="text-sm text-ink/60 italic">Sin inscripciones todavía.</p>
            ) : (
              <div className="space-y-1 max-h-80 overflow-y-auto">
                {links.map((ins) => {
                  const url = typeof window !== "undefined" ? `${window.location.origin}/examen/${ins.token}` : "";
                  return (
                    <div key={ins.id} className="flex items-center justify-between gap-2 text-sm border-b border-border py-1">
                      <span>
                        {ins.nombre_completo} <span className="text-ink/40">({ins.estado})</span>
                      </span>
                      <button
                        onClick={() => navigator.clipboard.writeText(url)}
                        className="text-teal-600 hover:underline font-mono text-xs"
                      >
                        Copiar link
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {puedeAdministrar && (
        <div className="bg-white rounded-card border border-border p-6 space-y-3">
          <h2 className="font-display text-lg text-teal-900">Ciclo de vida</h2>
          <TextoError>{errorAccion}</TextoError>
          <div className="flex items-center gap-3">
            <Boton variante="secundario" onClick={cerrar} disabled={accionando}>
              Cerrar campaña
            </Boton>
            {!mostrarCancelar ? (
              <button
                onClick={() => setMostrarCancelar(true)}
                className="text-sm text-red-600 hover:underline font-medium"
              >
                Cancelar campaña...
              </button>
            ) : (
              <form onSubmit={cancelar} className="flex items-center gap-2">
                <Input
                  required
                  minLength={3}
                  placeholder="Motivo (obligatorio)"
                  value={motivoCancelar}
                  onChange={(e) => setMotivoCancelar(e.target.value)}
                />
                <Boton type="submit" disabled={accionando}>
                  Confirmar cancelación
                </Boton>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
