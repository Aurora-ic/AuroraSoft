"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  Flag,
  Users,
  CircleCheck,
  Clock,
  TriangleAlert,
  Pencil,
  FileSpreadsheet,
  Search,
  Link2,
  Copy,
  Check,
  CalendarClock,
  BarChart3,
  Download,
  Lock,
  Ban,
  Eye,
  type LucideIcon,
} from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { apiClient, descargarBlob, mensajeDe } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { DimensionBar } from "@/components/ui/DimensionBar";
import { ResumenEstadisticoPrueba } from "@/components/ui/ResumenEstadisticoPrueba";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { Migas } from "@/components/ui/Migas";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import type { DashboardCampana, InscripcionCampana, Prueba } from "@/types/api";
import {
  estadoVisibleCampana,
  etiquetaEstadoCampana,
  ahoraParaInputLocal,
  type EstadoVisibleCampana,
  fechaCierreEsPasada,
  MENSAJE_FECHA_CIERRE_PASADA,
} from "@/lib/campanas";

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

// 🆕 Rediseño (sesión 2026-10-31, a pedido del usuario: "mejorar la
// interfaz cuando se entra a una campaña creada") — misma lógica y mismos
// endpoints; cambia la presentación: franja "destacado" azul (Evaluación)
// con estado, cierre y barra de avance; KPIs; tabla de alumnos con búsqueda
// y filtro por estado; links y ciclo de vida en una columna lateral.
type FiltroAlumnos = "todos" | "finalizados" | "pendientes";

// Punto de color del estado sobre la franja degradada (el badge normal de
// lib/campanas.ts está pensado para fondo claro).
const PUNTO_ESTADO: Record<EstadoVisibleCampana, string> = {
  activa: "bg-teal-400",
  vencida: "bg-red-400",
  cancelada: "bg-red-400",
  cerrada: "bg-white/60",
};

function fechaLarga(iso: string): string {
  return new Date(iso).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" });
}

function iniciales(nombre: string | null): string {
  const partes = (nombre ?? "").trim().split(/\s+/).filter(Boolean);
  return ((partes[0]?.[0] ?? "?") + (partes[1]?.[0] ?? "")).toUpperCase();
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
  // 🆕 Interruptor "los estudiantes ven su resultado" (Evaluacion.alumno_ve_informe).
  const [cambiandoVisibilidad, setCambiandoVisibilidad] = useState(false);
  const [errorVisibilidad, setErrorVisibilidad] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [motivoCancelar, setMotivoCancelar] = useState("");
  const [mostrarCancelar, setMostrarCancelar] = useState(false);

  const [pruebas, setPruebas] = useState<Prueba[]>([]);
  const [mostrarEditar, setMostrarEditar] = useState(false);
  const [formEditar, setFormEditar] = useState({ nombre_grupo: "", fecha_fin: "", prueba_id: "" });
  // Valor de fecha_fin al abrir el formulario: solo se reenvía (y se valida
  // como futura) si el usuario la cambió — así una campaña ya vencida por
  // fecha se puede renombrar sin que el backend la rechace.
  const [fechaFinOriginal, setFechaFinOriginal] = useState("");
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

  // 🆕 Acciones masivas (sesión 2026-10-24) — antes todo era uno por uno.
  // Reusa exactamente los mismos endpoints que ya existían (el de descargar
  // un informe, el de "Copiar link" de cada fila) — nada nuevo en el
  // backend, solo dispararlos en secuencia sobre la selección.
  const [seleccionados, setSeleccionados] = useState<Set<number>>(new Set());
  const [descargandoMasivo, setDescargandoMasivo] = useState(false);
  const [errorMasivo, setErrorMasivo] = useState<string | null>(null);
  const [copiadoLinksPendientes, setCopiadoLinksPendientes] = useState(false);
  const [copiadoLinkId, setCopiadoLinkId] = useState<number | null>(null);

  // 🆕 Filtro de la tabla de alumnos (solo cliente: el dashboard ya trae a
  // todos los alumnos de la campaña).
  const [busquedaAlumno, setBusquedaAlumno] = useState("");
  const [filtroAlumnos, setFiltroAlumnos] = useState<FiltroAlumnos>("todos");
  const terminoAlumno = busquedaAlumno.trim().toLowerCase();
  const alumnosVisibles = (dashboard?.alumnos ?? []).filter((a) => {
    if (filtroAlumnos === "finalizados" && a.estado !== "Finalizado") return false;
    if (filtroAlumnos === "pendientes" && a.estado === "Finalizado") return false;
    return !terminoAlumno || (a.nombre_completo ?? "").toLowerCase().includes(terminoAlumno);
  });

  // 🆕 Virtualización de la tabla de alumnos (hallazgo de escala, docs/
  // gaps-pendientes.md) — una campaña de un colegio grande puede matricular
  // cientos o miles de alumnos; renderizar esa cantidad de <tr> reales (cada
  // una con varias DimensionBar y, potencialmente, el formulario inline de
  // "Reprocesar") degradaba el navegador mucho antes de llegar a esa escala.
  // Hook incondicional (regla de hooks) aunque `dashboard` todavía sea null
  // al montar — cuenta sobre `dashboard?.alumnos.length ?? 0`.
  const filasAlumnosRef = useRef<HTMLDivElement>(null);
  // TanStack Virtual devuelve funciones que el React Compiler no puede
  // memoizar: solo AVISA que se salta este componente (no es un error).
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizadorAlumnos = useVirtualizer({
    count: alumnosVisibles.length,
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
    const fechaInicial = isoParaInputLocal(dashboard.fecha_fin);
    setFormEditar({
      nombre_grupo: dashboard.nombre_grupo,
      fecha_fin: fechaInicial,
      prueba_id: String(dashboard.prueba_id),
    });
    setFechaFinOriginal(fechaInicial);
    setErrorEdicion(null);
    setMostrarEditar(true);
  }

  const fechaFinCambio = formEditar.fecha_fin !== fechaFinOriginal;
  const fechaFinEditadaPasada = fechaFinCambio && fechaCierreEsPasada(formEditar.fecha_fin);

  async function guardarEdicion(e: React.FormEvent) {
    e.preventDefault();
    if (fechaFinEditadaPasada) {
      setErrorEdicion(MENSAJE_FECHA_CIERRE_PASADA);
      return;
    }
    setGuardandoEdicion(true);
    setErrorEdicion(null);
    try {
      await apiClient.patch(`/educativo/campanas/${campanaId}`, {
        nombre_grupo: formEditar.nombre_grupo,
        ...(fechaFinCambio && {
          fecha_fin: formEditar.fecha_fin ? new Date(formEditar.fecha_fin).toISOString() : null,
        }),
        prueba_id: Number(formEditar.prueba_id),
      });
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
      setMostrarEditar(false);
    } catch (err) {
      setErrorEdicion(mensajeDe(err) || "No se pudo guardar la edición de la campaña.");
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
    } catch (err) {
      setErrorReprocesar(mensajeDe(err) || "No se pudo reprocesar esta inscripción.");
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
    } catch (err) {
      setErrorLinks(mensajeDe(err) || "No se pudieron cargar los links de esta campaña.");
    }
  }

  async function exportarExcel() {
    setExportando(true);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/campanas/${campanaId}/exportar-excel`);
      descargarBlob(blob, `resultados_${campanaId}.xlsx`);
    } catch (err) {
      setError(mensajeDe(err) || "No se pudo exportar el Excel.");
    } finally {
      setExportando(false);
    }
  }

  function alternarSeleccion(inscripcionId: number) {
    setSeleccionados((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(inscripcionId)) siguiente.delete(inscripcionId);
      else siguiente.add(inscripcionId);
      return siguiente;
    });
  }

  const finalizados = dashboard?.alumnos.filter((a) => a.estado === "Finalizado") ?? [];

  function alternarSeleccionTodos() {
    setSeleccionados((prev) =>
      prev.size === finalizados.length ? new Set() : new Set(finalizados.map((a) => a.inscripcion_id)),
    );
  }

  // Mismo endpoint que ya usa la ficha del alumno para "Descargar PDF" —
  // disparado en secuencia (no en paralelo) para no saturar al navegador
  // con decenas de descargas simultáneas ni al backend con un burst de
  // requests; una pausa corta entre cada una evita que el navegador
  // bloquee "múltiples descargas" como si fuera spam.
  async function descargarInformesSeleccionados() {
    setDescargandoMasivo(true);
    setErrorMasivo(null);
    let fallos = 0;
    for (const inscripcionId of seleccionados) {
      try {
        const blob = await apiClient.descargarArchivo(`/educativo/inscripciones/${inscripcionId}/informe-pdf`);
        descargarBlob(blob, `informe_${inscripcionId}.pdf`);
      } catch {
        fallos++;
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (fallos > 0) {
      setErrorMasivo(`${fallos} de ${seleccionados.size} informes no se pudieron descargar (puede que estén retenidos).`);
    }
    setDescargandoMasivo(false);
  }

  // Copia TODOS los links de inscripciones pendientes (nunca los ya
  // finalizados) a la vez, uno por línea — mismo texto/formato que "Copiar
  // link" ya usa por fila, pero en lote, para pegar de una sola vez en un
  // mensaje de WhatsApp/correo a los alumnos que todavía no rindieron.
  async function copiarLink(id: number, url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiadoLinkId(id);
      setTimeout(() => setCopiadoLinkId((actual) => (actual === id ? null : actual)), 2000);
    } catch {
      setErrorLinks("El navegador no permitió copiar al portapapeles.");
    }
  }

  async function copiarLinksPendientes() {
    if (!links) return;
    const pendientes = links.filter((ins) => ins.estado !== "Finalizado");
    const texto = pendientes
      .map((ins) => `${ins.nombre_completo ?? "(sin nombre)"}: ${window.location.origin}/examen/${ins.token}`)
      .join("\n");
    await navigator.clipboard.writeText(texto);
    setCopiadoLinksPendientes(true);
    setTimeout(() => setCopiadoLinksPendientes(false), 2000);
  }

  // Se puede cambiar en cualquier estado de la campaña (también cerrada):
  // afecta al instante a todos sus estudiantes, incluidos los que ya terminaron.
  async function alternarVisibilidadAlumno() {
    if (!dashboard) return;
    setCambiandoVisibilidad(true);
    setErrorVisibilidad(null);
    try {
      await apiClient.patch(`/educativo/campanas/${campanaId}`, { alumno_ve_informe: !dashboard.alumno_ve_informe });
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
    } catch (err: unknown) {
      setErrorVisibilidad(err instanceof Error ? err.message : "No se pudo cambiar la visibilidad para los estudiantes.");
    } finally {
      setCambiandoVisibilidad(false);
    }
  }

  async function cerrar() {
    setAccionando(true);
    setErrorAccion(null);
    try {
      await apiClient.post(`/educativo/campanas/${campanaId}/cerrar`, {});
      const actualizado = await apiClient.get<DashboardCampana>(`/educativo/campanas/${campanaId}/dashboard`);
      setDashboard(actualizado);
    } catch (err) {
      setErrorAccion(mensajeDe(err) || "No se pudo cerrar la campaña.");
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
    } catch (err) {
      setErrorAccion(mensajeDe(err) || "No se pudo cancelar la campaña.");
    } finally {
      setAccionando(false);
    }
  }

  if (loading) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        <div className="h-[7.5rem] animate-pulse rounded-2xl bg-border/60 dark:bg-border-dark" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[4.5rem] animate-pulse rounded-xl bg-border/50 dark:bg-border-dark" />
          ))}
        </div>
        <p className="text-center text-sm text-ink/50 dark:text-ink-dark/50">Cargando dashboard...</p>
      </div>
    );
  }
  if (error || !dashboard) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        <TextoError>{error || "Campaña no encontrada."}</TextoError>
      </div>
    );
  }

  // Mismo criterio que el backend (crud.campana_esta_expirada) — ver
  // lib/campanas.ts. dashboard.estado sigue diciendo "activa" en la BD
  // aunque ya pasó fecha_fin; esto es lo que de verdad se muestra.
  const estadoVisible = estadoVisibleCampana(dashboard.estado, dashboard.fecha_fin);
  const vencida = estadoVisible === "vencida";
  const avance = dashboard.total_inscritos > 0 ? Math.round((dashboard.total_finalizados / dashboard.total_inscritos) * 100) : 0;
  // 'colegio' recibe alumnos[].resultados redactado (vacío) server-side —
  // un conteo de "con alerta" calculado acá sería un falso 0 para ese rol.
  const veResultadosClinicos = sesion?.rol !== "colegio";
  const conAlerta = dashboard.alumnos.filter((a) => a.resultados.some((r) => r.es_alerta)).length;
  const pendientesLinks = links?.filter((ins) => ins.estado !== "Finalizado") ?? [];
  const columnas = 3 + (puedeReprocesar ? 1 : 0) + (puedeAdministrar ? 1 : 0);

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas sinMargen items={[{ label: "Campañas", href: "/campanas" }, { label: dashboard.nombre_grupo }]} />

      <EncabezadoPagina
        variante="destacado"
        icono={Flag}
        acento="azul"
        titulo={dashboard.nombre_grupo}
        descripcion={
          dashboard.nombre_corto_prueba
            ? `${dashboard.nombre_corto_prueba} · ${dashboard.nombre_prueba}`
            : dashboard.nombre_prueba
        }
        acciones={
          <>
            {puedeAdministrar && dashboard.estado === "activa" && !mostrarEditar && (
              <button type="button" onClick={abrirEditar} className={claseBotonBanner("secundario")}>
                <Pencil size={14} aria-hidden="true" />
                Editar campaña
              </button>
            )}
            <button type="button" onClick={exportarExcel} disabled={exportando} className={claseBotonBanner("primario")}>
              <FileSpreadsheet size={15} aria-hidden="true" />
              {exportando ? "Exportando..." : "Exportar Excel"}
            </button>
          </>
        }
      >
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-2.5 py-1 font-semibold text-white dark:bg-surface-dark dark:text-ink-dark">
            <span className={`h-2 w-2 rounded-full ${PUNTO_ESTADO[estadoVisible]}`} aria-hidden="true" />
            {etiquetaEstadoCampana(estadoVisible)}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-white/85 dark:bg-surface-dark dark:text-ink-dark/70">
            <CalendarClock size={12} aria-hidden="true" />
            {dashboard.fecha_fin ? `Cierra ${fechaLarga(dashboard.fecha_fin)}` : "Sin fecha límite"}
          </span>
          {dashboard.total_inscritos > 0 && (
            <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-2.5 py-1 text-white/85 dark:bg-surface-dark dark:text-ink-dark/70">
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-white/25 dark:bg-border-dark" aria-hidden="true">
                <span className="block h-full rounded-full bg-white dark:bg-acento-azul-dark" style={{ width: `${avance}%` }} />
              </span>
              {avance}% completado
            </span>
          )}
        </div>
      </EncabezadoPagina>

      {/* 🆕 Aviso real: la campaña sigue "activa" en la BD, pero ya pasó su
          fecha_fin — el backend rechaza en silencio cualquier intento de
          matricular o de que un alumno rinda (ver lib/campanas.ts). Sin
          este aviso no había ninguna señal de esto hasta que algo fallaba. */}
      {vencida && puedeAdministrar && (
        <div className="flex items-start gap-2.5 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <Clock size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <p className="m-0">
            Esta campaña venció el {dashboard.fecha_fin ? new Date(dashboard.fecha_fin).toLocaleString("es-PE") : ""} y ya
            no acepta actividad nueva (nadie puede matricularse ni rendir el examen). Si fue sin querer, edita la fecha de
            cierre para reabrirla; si ya terminó de verdad, ciérrala formalmente en «Ciclo de vida».
          </p>
        </div>
      )}

      {mostrarEditar && (
        <form onSubmit={guardarEdicion} className={`${CLASE_TARJETA} overflow-hidden`}>
          <CabeceraTarjeta icono={Pencil} titulo="Editar campaña" />
          <div className="p-5 space-y-4">
            <TextoError>{errorEdicion}</TextoError>
            <div className="grid sm:grid-cols-2 gap-4">
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
                  min={ahoraParaInputLocal()}
                  value={formEditar.fecha_fin}
                  onChange={(e) => setFormEditar({ ...formEditar, fecha_fin: e.target.value })}
                  aria-invalid={fechaFinEditadaPasada}
                  className={fechaFinEditadaPasada ? "border-red-400 focus:ring-red-300" : ""}
                />
                {fechaFinEditadaPasada && (
                  <span className="text-xs font-medium text-red-700 dark:text-red-300 mt-1">{MENSAJE_FECHA_CIERRE_PASADA}</span>
                )}
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
                  <span className="text-xs text-ink/50 dark:text-ink-dark/50 mt-1">
                    Ya tiene {dashboard.total_inscritos} inscripción(es) — la prueba no se puede cambiar.
                  </span>
                )}
              </CampoEditable>
            </div>
            <div className="flex items-center gap-3">
              <Boton type="submit" disabled={guardandoEdicion}>
                {guardandoEdicion ? "Guardando..." : "Guardar cambios"}
              </Boton>
              <Boton type="button" variante="secundario" onClick={() => setMostrarEditar(false)}>
                Cancelar
              </Boton>
            </div>
          </div>
        </form>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <TarjetaKpi icono={Users} tono="azul" valor={dashboard.total_inscritos} etiqueta="Inscritos" />
        <TarjetaKpi
          icono={CircleCheck}
          tono="teal"
          valor={dashboard.total_finalizados}
          etiqueta="Finalizados"
          detalle={dashboard.total_inscritos > 0 ? `${avance}% del total` : undefined}
        />
        <TarjetaKpi icono={Clock} tono="neutro" valor={dashboard.total_pendientes} etiqueta="Pendientes" />
        {veResultadosClinicos ? (
          <TarjetaKpi
            icono={TriangleAlert}
            tono={conAlerta > 0 ? "riesgo" : "neutro"}
            valor={conAlerta}
            etiqueta="Con alerta clínica"
            detalle={conAlerta > 0 ? "Informe retenido hasta revisión" : undefined}
          />
        ) : (
          <TarjetaKpi icono={BarChart3} tono="azul" valor={`${avance}%`} etiqueta="Avance" />
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_20rem] gap-5 items-start">
        <div className="space-y-5 min-w-0">
          {dashboard.resumen_estadistico.dimensiones.length > 0 && (
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <CabeceraTarjeta icono={BarChart3} titulo="Resumen estadístico" descripcion="Agregado del grupo por dimensión." />
              <div className="p-5">
                <ResumenEstadisticoPrueba resumen={dashboard.resumen_estadistico} />
              </div>
            </section>
          )}

          <section className={`${CLASE_TARJETA} overflow-hidden`}>
            <CabeceraTarjeta
              icono={Users}
              titulo="Alumnos"
              descripcion={`${dashboard.alumnos.length} matriculado${dashboard.alumnos.length === 1 ? "" : "s"}`}
              acciones={
                puedeAdministrar &&
                seleccionados.size > 0 && (
                  <Boton
                    variante="secundario"
                    onClick={descargarInformesSeleccionados}
                    disabled={descargandoMasivo}
                    className="inline-flex items-center gap-1.5 !py-1.5 !text-xs"
                  >
                    <Download size={14} aria-hidden="true" />
                    {descargandoMasivo
                      ? `Descargando... (${seleccionados.size})`
                      : `Descargar ${seleccionados.size} informe${seleccionados.size === 1 ? "" : "s"} seleccionado${seleccionados.size === 1 ? "" : "s"}`}
                  </Boton>
                )
              }
            />
            <div className="p-5 space-y-3">
              <TextoError>{errorMasivo}</TextoError>
              {dashboard.alumnos.length === 0 ? (
                <div className="py-10 text-center">
                  <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-ink/40 dark:text-ink-dark/40">
                    <Users size={22} aria-hidden="true" />
                  </span>
                  <p className="mt-3 text-sm text-ink/60 dark:text-ink-dark/60">Todavía no hay alumnos matriculados en esta campaña.</p>
                </div>
              ) : (
                <>
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <div className="relative flex-1">
                      <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                      <Input
                        type="search"
                        value={busquedaAlumno}
                        onChange={(e) => setBusquedaAlumno(e.target.value)}
                        placeholder="Buscar alumno"
                        aria-label="Buscar alumno"
                        className="w-full pl-9"
                      />
                    </div>
                    <ControlSegmentado<FiltroAlumnos>
                      etiqueta="Filtrar por estado"
                      valor={filtroAlumnos}
                      onCambiar={setFiltroAlumnos}
                      opciones={[
                        { valor: "todos", etiqueta: `Todos (${dashboard.alumnos.length})` },
                        { valor: "finalizados", etiqueta: `Finalizados (${dashboard.total_finalizados})` },
                        { valor: "pendientes", etiqueta: `Pendientes (${dashboard.total_pendientes})` },
                      ]}
                    />
                  </div>
                  <TextoError>{errorReprocesar}</TextoError>
                  {avisoRetraccion && (
                    <p className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 dark:bg-amber/10 dark:text-amber border border-amber-200 dark:border-amber/30 rounded-xl px-3 py-2">
                      <TriangleAlert size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
                      {avisoRetraccion}
                    </p>
                  )}
                  <div ref={filasAlumnosRef} className="max-h-150 overflow-auto rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark">
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 z-10 bg-mist dark:bg-surface-raised-dark">
                        <TheadFila>
                          {puedeAdministrar && (
                            <Th className="px-3 py-2 w-8">
                              <input
                                type="checkbox"
                                className="h-4 w-4 accent-teal-600"
                                checked={finalizados.length > 0 && seleccionados.size === finalizados.length}
                                onChange={alternarSeleccionTodos}
                                title="Seleccionar todos los finalizados"
                                aria-label="Seleccionar todos los finalizados"
                              />
                            </Th>
                          )}
                          <Th className="px-3 py-2">Alumno</Th>
                          <Th className="px-3 py-2">Estado</Th>
                          <Th className="px-3 py-2">Resultados</Th>
                          {puedeReprocesar && <Th className="px-3 py-2">Acciones</Th>}
                        </TheadFila>
                      </thead>
                      <tbody>
                        {/* Fila-colchón de arriba — ver mismo patrón en
                            estudiantes/importar/page.tsx (vista previa de Excel). */}
                        {virtualizadorAlumnos.getVirtualItems().length > 0 && (
                          <tr style={{ height: virtualizadorAlumnos.getVirtualItems()[0].start }} aria-hidden>
                            <td colSpan={columnas} />
                          </tr>
                        )}
                        {virtualizadorAlumnos.getVirtualItems().map((item) => {
                          const a = alumnosVisibles[item.index];
                          const finalizado = a.estado === "Finalizado";
                          const tieneAlerta = a.resultados.some((r) => r.es_alerta);
                          return (
                            <tr
                              key={a.inscripcion_id}
                              data-index={item.index}
                              ref={virtualizadorAlumnos.measureElement}
                              className={`border-b border-border dark:border-border-dark last:border-b-0 ${
                                tieneAlerta ? "shadow-[inset_3px_0_0_var(--color-amber)]" : ""
                              }`}
                            >
                              {puedeAdministrar && (
                                <td className="px-3 py-2.5 align-top">
                                  {finalizado && (
                                    <input
                                      type="checkbox"
                                      className="h-4 w-4 accent-teal-600"
                                      checked={seleccionados.has(a.inscripcion_id)}
                                      onChange={() => alternarSeleccion(a.inscripcion_id)}
                                      aria-label={`Seleccionar a ${a.nombre_completo ?? "alumno"}`}
                                    />
                                  )}
                                </td>
                              )}
                              <td className="px-3 py-2.5 align-top">
                                <span className="flex items-center gap-2.5">
                                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-acento-azul/10 text-[12px] font-bold text-acento-azul dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark">
                                    {iniciales(a.nombre_completo)}
                                  </span>
                                  <span className="min-w-0">
                                    <span className="block font-medium text-ink dark:text-ink-dark">{a.nombre_completo || "(sin nombre)"}</span>
                                    {a.fecha_resolucion && (
                                      <span className="block text-[12px] text-ink/45 dark:text-ink-dark/45">
                                        {new Date(a.fecha_resolucion).toLocaleDateString("es-PE", { day: "numeric", month: "short", year: "numeric" })}
                                      </span>
                                    )}
                                  </span>
                                </span>
                              </td>
                              <td className="px-3 py-2.5 align-top">
                                <span
                                  className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-semibold ${
                                    finalizado
                                      ? "bg-teal-400/20 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
                                      : "bg-ink/[0.06] text-ink/60 dark:bg-white/10 dark:text-ink-dark/60"
                                  }`}
                                >
                                  {finalizado ? <CircleCheck size={11} aria-hidden="true" /> : <Clock size={11} aria-hidden="true" />}
                                  {a.estado}
                                </span>
                              </td>
                              <td className="px-3 py-2.5 align-top">
                                {a.resultados.length === 0 ? (
                                  <span className="text-ink/35 dark:text-ink-dark/35">—</span>
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
                                        <span key={r.dimension} className="text-xs text-ink/70 dark:text-ink-dark/70">
                                          {r.dimension}: {r.nivel ?? r.puntaje_directo}
                                        </span>
                                      )
                                    )}
                                  </div>
                                )}
                              </td>
                              {puedeReprocesar && (
                                <td className="px-3 py-2.5 align-top">
                                  {!finalizado ? (
                                    <span className="text-ink/35 dark:text-ink-dark/35">—</span>
                                  ) : mostrarReprocesarId !== a.inscripcion_id ? (
                                    <button
                                      onClick={() => {
                                        setMostrarReprocesarId(a.inscripcion_id);
                                        setMotivoReprocesar("");
                                        setErrorReprocesar(null);
                                      }}
                                      className="text-xs text-teal-700 dark:text-teal-accent-dark hover:underline font-semibold"
                                    >
                                      Reprocesar
                                    </button>
                                  ) : (
                                    <form onSubmit={(e) => reprocesar(e, a.inscripcion_id)} className="flex flex-col gap-1.5 min-w-48">
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
                                        className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400"
                                      />
                                      <div className="flex items-center gap-2">
                                        <button
                                          type="submit"
                                          disabled={reprocesandoId === a.inscripcion_id}
                                          className="text-xs text-white bg-accion hover:bg-accion-hover rounded-card px-2 py-1 disabled:opacity-50"
                                        >
                                          {reprocesandoId === a.inscripcion_id ? "Reprocesando..." : "Confirmar"}
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => setMostrarReprocesarId(null)}
                                          className="text-xs text-ink/50 dark:text-ink-dark/50 hover:underline"
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
                        {/* Fila-colchón de abajo — ver mismo patrón en
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
                            <td colSpan={columnas} />
                          </tr>
                        )}
                      </tbody>
                    </table>
                    {alumnosVisibles.length === 0 && (
                      <p className="px-4 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">Ningún alumno coincide con el filtro.</p>
                    )}
                  </div>
                </>
              )}
            </div>
          </section>
        </div>

        <aside className="space-y-5 xl:sticky xl:top-0">
          <section className={`${CLASE_TARJETA} overflow-hidden`}>
            <CabeceraTarjeta
              icono={Link2}
              titulo="Links de examen"
              descripcion="Un link personal por alumno."
              acciones={
                <button
                  type="button"
                  onClick={alternarLinks}
                  className="text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
                >
                  {mostrarLinks ? "Ocultar" : "Ver links"}
                </button>
              }
            />
            {mostrarLinks ? (
              <div className="p-4 space-y-3">
                <TextoError>{errorLinks}</TextoError>
                {pendientesLinks.length > 0 && (
                  <Boton
                    variante="secundario"
                    onClick={copiarLinksPendientes}
                    className="w-full inline-flex items-center justify-center gap-1.5 !py-1.5 !text-xs"
                  >
                    {copiadoLinksPendientes ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
                    {copiadoLinksPendientes ? "¡Copiado!" : `Copiar todos los links pendientes (${pendientesLinks.length})`}
                  </Boton>
                )}
                {links === null ? (
                  <p className="text-sm text-ink/50 dark:text-ink-dark/50">Cargando...</p>
                ) : links.length === 0 ? (
                  <p className="text-sm text-ink/50 dark:text-ink-dark/50">Sin inscripciones todavía.</p>
                ) : (
                  <ul className="m-0 list-none p-0 max-h-80 overflow-y-auto divide-y divide-border dark:divide-border-dark -mx-1">
                    {links.map((ins) => {
                      const url = typeof window !== "undefined" ? `${window.location.origin}/examen/${ins.token}` : "";
                      const finalizado = ins.estado === "Finalizado";
                      return (
                        <li key={ins.id} className="flex items-center gap-2 px-1 py-2">
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[13px] font-medium text-ink dark:text-ink-dark">{ins.nombre_completo}</span>
                            <span className={`block text-[12px] ${finalizado ? "text-teal-700 dark:text-teal-accent-dark" : "text-ink/45 dark:text-ink-dark/45"}`}>
                              {ins.estado}
                            </span>
                          </span>
                          <button
                            type="button"
                            onClick={() => copiarLink(ins.id, url)}
                            className={`shrink-0 inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[12px] font-semibold transition-colors ${
                              copiadoLinkId === ins.id
                                ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                                : "bg-mist text-teal-700 hover:bg-teal-600/10 dark:bg-surface-raised-dark dark:text-teal-accent-dark"
                            }`}
                          >
                            {copiadoLinkId === ins.id ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
                            {copiadoLinkId === ins.id ? "Copiado" : "Copiar link"}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : (
              <p className="m-0 px-4 py-3 text-[12px] text-ink/50 dark:text-ink-dark/50">
                Copia el link de cada alumno o todos los pendientes de una vez para enviarlos por WhatsApp o correo.
              </p>
            )}
          </section>

          {puedeAdministrar && (
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <CabeceraTarjeta icono={Eye} titulo="Resultados para los estudiantes" />
              <div className="p-4 space-y-3">
                <TextoError>{errorVisibilidad}</TextoError>
                <div className="flex items-start justify-between gap-3">
                  <p className="m-0 text-[13px] font-semibold text-ink dark:text-ink-dark">
                    {dashboard.alumno_ve_informe ? "Ven su resultado y su PDF" : "No ven su resultado"}
                  </p>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={!!dashboard.alumno_ve_informe}
                    aria-label="Los estudiantes ven su resultado al terminar"
                    onClick={alternarVisibilidadAlumno}
                    disabled={cambiandoVisibilidad}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 disabled:opacity-50 ${
                      dashboard.alumno_ve_informe ? "bg-accion dark:bg-teal-accent-dark" : "bg-border dark:bg-border-dark"
                    }`}
                  >
                    <span
                      className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                        dashboard.alumno_ve_informe ? "translate-x-5" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>
                <p className="m-0 text-[12px] leading-relaxed text-ink/60 dark:text-ink-dark/60">
                  Encendido, cada estudiante ve un resumen por dimensión y puede descargar su informe en PDF —{" "}
                  <strong className="font-semibold">también si hay alerta clínica, sin tu revisión previa</strong>. Tú siempre
                  recibes todos los resultados. El cambio aplica al instante, también a quienes ya terminaron.
                </p>
              </div>
            </section>
          )}

          {puedeAdministrar && (
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <CabeceraTarjeta icono={Lock} titulo="Ciclo de vida" />
              <div className="p-4 space-y-3">
                <TextoError>{errorAccion}</TextoError>
                {dashboard.estado !== "activa" ? (
                  // El backend solo permite cerrar/cancelar una campaña activa
                  // (crud._cerrar_o_cancelar_campana) — no se ofrecen botones que
                  // terminarían en error.
                  <p className="m-0 text-[12.5px] text-ink/60 dark:text-ink-dark/60">
                    Esta campaña está <strong className="font-semibold">{etiquetaEstadoCampana(estadoVisible).toLowerCase()}</strong>: ya
                    no admite cambios en su ciclo de vida.
                  </p>
                ) : (
                  <>
                    <p className="m-0 text-[12px] text-ink/55 dark:text-ink-dark/55">
                      Cerrar la campaña desactiva los links pendientes; los resultados ya obtenidos se conservan.
                    </p>
                    <Boton
                      variante="secundario"
                      onClick={cerrar}
                      disabled={accionando}
                      className="w-full inline-flex items-center justify-center gap-1.5"
                    >
                      <Lock size={14} aria-hidden="true" />
                      Cerrar campaña
                    </Boton>
                    {!mostrarCancelar ? (
                      <button
                        type="button"
                        onClick={() => setMostrarCancelar(true)}
                        className="w-full inline-flex items-center justify-center gap-1.5 text-[12.5px] font-semibold text-red-600 dark:text-red-300 hover:underline"
                      >
                        <Ban size={13} aria-hidden="true" />
                        Cancelar campaña...
                      </button>
                    ) : (
                      <form onSubmit={cancelar} className="space-y-2 rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50/60 dark:bg-red-500/10 p-3">
                        <Input
                          required
                          minLength={3}
                          placeholder="Motivo (obligatorio)"
                          value={motivoCancelar}
                          onChange={(e) => setMotivoCancelar(e.target.value)}
                          className="w-full"
                        />
                        <div className="flex items-center gap-2">
                          <Boton type="submit" disabled={accionando} className="flex-1 !py-1.5 !text-xs">
                            Confirmar cancelación
                          </Boton>
                          <button
                            type="button"
                            onClick={() => setMostrarCancelar(false)}
                            className="text-xs text-ink/55 dark:text-ink-dark/55 hover:underline"
                          >
                            Volver
                          </button>
                        </div>
                      </form>
                    )}
                  </>
                )}
              </div>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

// 🆕 (sesión 2026-10-31) Fondo tenue azul (Evaluación) — mismo sistema que
// ACENTOS.azul.fondoSuave/cabecera/chipSolido (lib/acentos.ts).
const CLASE_TARJETA = "rounded-2xl border border-acento-azul/15 dark:border-acento-azul-dark/20 bg-acento-azul/[0.035] dark:bg-acento-azul-dark/[0.05] shadow-sm";

// Cabecera de tarjeta — mismo lenguaje que los bloques de /campanas/nueva
// (franja suave + ícono en el chip azul de Evaluación).
function CabeceraTarjeta({
  icono: Icono,
  titulo,
  descripcion,
  acciones,
}: {
  icono: LucideIcon;
  titulo: string;
  descripcion?: string;
  acciones?: React.ReactNode;
}) {
  return (
    <header className="flex items-center justify-between gap-3 border-b px-4 py-3 border-acento-azul/15 dark:border-acento-azul-dark/20 bg-acento-azul/[0.08] dark:bg-acento-azul-dark/[0.08]">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark">
          <Icono size={16} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="m-0 font-display text-[15px] font-semibold text-teal-900 dark:text-ink-dark">{titulo}</h2>
          {descripcion && <p className="m-0 truncate text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>}
        </div>
      </div>
      {acciones && <div className="shrink-0">{acciones}</div>}
    </header>
  );
}
