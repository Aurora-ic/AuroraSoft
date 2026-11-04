"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Siren,
  Hourglass,
  Search,
  ArrowRight,
  HeartHandshake,
  CheckCircle2,
  Stethoscope,
  History,
  UserRound,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { VacioFicha } from "@/components/educativo/BloqueFicha";
import {
  CLASE_URGENCIA,
  DESCRIPCION_URGENCIA,
  ESTADOS_CASO,
  ETIQUETA_ESTADO,
  ETIQUETA_URGENCIA,
} from "@/lib/casos-riesgo";
import type { BandejaCasosRiesgo, CasoRiesgo, EstadoCaso, EventoCasoRiesgo, UrgenciaCaso } from "@/types/api";
import { TerminoAyuda } from "@/components/ui/TerminoAyuda";
import { CLAVE_AVISOS_URGENTES } from "@/components/educativo/AvisosUrgentes";

// 🆕 (sesión 2026-11-01, decisiones del usuario) Bandeja de casos con
// urgencia, estado y responsable — GET/PATCH /educativo/casos-riesgo (ver
// models.CasoRiesgo en el backend). Antes: una lista por alumno de
// GET /casos-pendientes, ordenada solo por antigüedad, donde una ideación
// suicida se veía igual que una ansiedad leve y un caso desaparecía con
// cualquier sesión registrada.
// - Urgencia automática: URGENTE (ítem crítico, p. ej. PHQ-9 ítem 9),
//   ALERTA (tramo de alerta del baremo), SEGUIMIENTO (antecedentes "Sí").
//   Urgentes siempre primero.
// - Estados: Nuevo → En atención → Derivado → En seguimiento → Cerrado. Un
//   caso solo sale de la bandeja al cerrarlo, con motivo. Registrar una
//   sesión lo pasa solo de Nuevo a En atención.
// - Responsable: el creador de la campaña, reasignable a cualquier
//   psicólogo/admin del colegio.
// La unidad es el CASO (una evaluación en alerta, o los antecedentes), no
// el alumno: un alumno puede tener más de un caso abierto.

const DIA_MS = 24 * 60 * 60 * 1000;

function diasDesde(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / DIA_MS));
}

function textoDias(dias: number | null): string {
  if (dias === null) return "Sin fecha";
  if (dias === 0) return "Hoy";
  if (dias === 1) return "Hace 1 día";
  return `Hace ${dias} días`;
}

function fecha(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleDateString("es-PE") : "—";
}

type FiltroUrgencia = "todas" | UrgenciaCaso;
type FiltroEstado = "abiertos" | EstadoCaso;
// "todos" | "mios" | "sin" | String(usuario_id)
type FiltroResponsable = string;

function CasosRiesgoPageContenido() {
  const queryClient = useQueryClient();
  const [busqueda, setBusqueda] = useState("");
  const [filtroUrgencia, setFiltroUrgencia] = useState<FiltroUrgencia>("todas");
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>("abiertos");
  const [filtroResponsable, setFiltroResponsable] = useState<FiltroResponsable>("todos");

  // Los cerrados solo se piden al filtrar por "Cerrado".
  const incluirCerrados = filtroEstado === "cerrado";
  const claveBandeja = ["casos-riesgo", incluirCerrados];
  const consulta = useQuery({
    queryKey: claveBandeja,
    queryFn: () =>
      apiClient.get<BandejaCasosRiesgo>(`/educativo/casos-riesgo${incluirCerrados ? "?incluir_cerrados=true" : ""}`),
    placeholderData: keepPreviousData,
  });
  const bandeja = consulta.data ?? null;
  const cargando = consulta.isPending;
  const error = consulta.error instanceof Error ? consulta.error.message : consulta.error ? "No se pudieron cargar los casos en riesgo." : null;

  const casos = useMemo(() => bandeja?.casos ?? [], [bandeja]);
  const abiertos = useMemo(() => casos.filter((c) => c.estado !== "cerrado"), [casos]);

  const visibles = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    return casos.filter((c) => {
      if (filtroEstado === "abiertos" ? c.estado === "cerrado" : c.estado !== filtroEstado) return false;
      if (filtroUrgencia !== "todas" && c.urgencia !== filtroUrgencia) return false;
      if (filtroResponsable === "mios" && c.responsable?.id !== bandeja?.yo) return false;
      if (filtroResponsable === "sin" && c.responsable) return false;
      if (!["todos", "mios", "sin"].includes(filtroResponsable) && String(c.responsable?.id) !== filtroResponsable) return false;
      if (texto && !c.nombre_completo.toLowerCase().includes(texto)) return false;
      return true;
    });
  }, [casos, busqueda, filtroEstado, filtroUrgencia, filtroResponsable, bandeja?.yo]);

  const conteo = (u: UrgenciaCaso) => abiertos.filter((c) => c.urgencia === u).length;
  const masAntiguo = useMemo(() => {
    const dias = abiertos.map((c) => diasDesde(c.fecha_referencia)).filter((d): d is number => d !== null);
    return dias.length ? Math.max(...dias) : null;
  }, [abiertos]);

  // Tras un PATCH: se reemplaza el caso en la caché (sin recargar todo).
  function reemplazarCaso(actualizado: CasoRiesgo) {
    queryClient.setQueryData<BandejaCasosRiesgo>(claveBandeja, (previo) =>
      previo ? { ...previo, casos: previo.casos.map((c) => (c.id === actualizado.id ? actualizado : c)) } : previo,
    );
    // La otra vista (con/sin cerrados) queda vieja: se vuelve a pedir al abrirla.
    queryClient.invalidateQueries({ queryKey: ["casos-riesgo", !incluirCerrados] });
    // 🆕 (sesión 2026-11-02) La campana de avisos baja en el acto.
    queryClient.invalidateQueries({ queryKey: CLAVE_AVISOS_URGENTES });
    queryClient.invalidateQueries({ queryKey: ["caso-historial", actualizado.id] });
  }

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <EncabezadoPagina
        variante="destacado"
        icono={AlertTriangle}
        acento="azul"
        titulo="Casos en riesgo"
        descripcion="Casos ordenados por urgencia. Un caso sale de esta lista solo cuando lo cierras, indicando el motivo."
      />

      <div className="grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-4 gap-3">
        <TarjetaKpi
          icono={Siren}
          tono="riesgo"
          etiqueta="Urgentes"
          valor={cargando ? "…" : conteo("urgente")}
          detalle="ítem crítico"
          activa={filtroUrgencia === "urgente"}
          onClick={() => setFiltroUrgencia((v) => (v === "urgente" ? "todas" : "urgente"))}
        />
        <TarjetaKpi
          icono={AlertTriangle}
          tono="riesgo"
          etiqueta="En alerta"
          valor={cargando ? "…" : conteo("alerta")}
          detalle="por baremo"
          activa={filtroUrgencia === "alerta"}
          onClick={() => setFiltroUrgencia((v) => (v === "alerta" ? "todas" : "alerta"))}
        />
        <TarjetaKpi
          icono={Stethoscope}
          tono="pizarra"
          etiqueta="Seguimiento"
          valor={cargando ? "…" : conteo("seguimiento")}
          detalle="antecedentes"
          activa={filtroUrgencia === "seguimiento"}
          onClick={() => setFiltroUrgencia((v) => (v === "seguimiento" ? "todas" : "seguimiento"))}
        />
        <TarjetaKpi
          icono={Hourglass}
          tono="azul"
          etiqueta="Espera más larga"
          valor={cargando ? "…" : masAntiguo === null ? "—" : masAntiguo}
          detalle={masAntiguo !== null && !cargando ? "días sin seguimiento" : undefined}
        />
      </div>

      <TextoError>{error}</TextoError>

      <div className="flex flex-col gap-2.5 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
          <input
            type="search"
            aria-label="Buscar alumno"
            placeholder="Buscar alumno…"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            className="w-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <ControlSegmentado<FiltroUrgencia>
            etiqueta="Urgencia"
            valor={filtroUrgencia}
            onCambiar={setFiltroUrgencia}
            opciones={[
              { valor: "todas", etiqueta: "Todas" },
              { valor: "urgente", etiqueta: "Urgente" },
              { valor: "alerta", etiqueta: "Alerta" },
              { valor: "seguimiento", etiqueta: "Seguimiento" },
            ]}
          />
          <Select value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value as FiltroEstado)} aria-label="Filtrar por estado">
            <option value="abiertos">Todos los abiertos</option>
            {ESTADOS_CASO.map((e) => (
              <option key={e} value={e}>
                {ETIQUETA_ESTADO[e]}
              </option>
            ))}
          </Select>
          <Select value={filtroResponsable} onChange={(e) => setFiltroResponsable(e.target.value)} aria-label="Filtrar por responsable">
            <option value="todos">Todos los responsables</option>
            <option value="mios">Mis casos</option>
            <option value="sin">Sin responsable</option>
            {(bandeja?.profesionales ?? []).map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.nombre}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {cargando && <EsqueletoLista cantidad={4} />}

      {!cargando && !error && filtroEstado === "abiertos" && abiertos.length === 0 && (
        <VacioFicha icono={CheckCircle2} texto="No hay casos abiertos: ningún resultado en alerta ni antecedentes clínicos externos pendientes de cierre." />
      )}

      {!cargando && (filtroEstado !== "abiertos" || abiertos.length > 0) && visibles.length === 0 && (
        <p className="m-0 text-sm text-ink/50 dark:text-ink-dark/50 italic">Ningún caso coincide con el filtro.</p>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        {visibles.map((c) => (
          <TarjetaCaso key={c.id} caso={c} profesionales={bandeja?.profesionales ?? []} onActualizado={reemplazarCaso} />
        ))}
      </div>
    </div>
  );
}

function TarjetaCaso({
  caso,
  profesionales,
  onActualizado,
}: {
  caso: CasoRiesgo;
  profesionales: { id: number; nombre: string }[];
  onActualizado: (c: CasoRiesgo) => void;
}) {
  const [guardando, setGuardando] = useState(false);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [cerrando, setCerrando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [verHistorial, setVerHistorial] = useState(false);
  // Lo elegido se muestra mientras se guarda (si no, el desplegable volvía
  // un instante al valor anterior); si falla, vuelve al valor real.
  const [estadoPendiente, setEstadoPendiente] = useState<EstadoCaso | null>(null);
  const [responsablePendiente, setResponsablePendiente] = useState<string | null>(null);

  const dias = diasDesde(caso.fecha_referencia);
  const esperaLarga = caso.estado !== "cerrado" && dias !== null && dias > 14;
  const clases = CLASE_URGENCIA[caso.urgencia];
  // El responsable actual puede no estar ya en la lista (desactivado): se
  // muestra igual para no "perderlo" en el desplegable.
  const opcionesResponsable =
    caso.responsable && !profesionales.some((p) => p.id === caso.responsable!.id)
      ? [...profesionales, { id: caso.responsable.id, nombre: caso.responsable.nombre ?? "Usuario inactivo" }]
      : profesionales;

  async function guardar(cambios: Record<string, unknown>) {
    setGuardando(true);
    setErrorAccion(null);
    try {
      onActualizado(await apiClient.patch<CasoRiesgo>(`/educativo/casos-riesgo/${caso.id}`, cambios));
      return true;
    } catch (err: unknown) {
      setErrorAccion(err instanceof Error ? err.message : "No se pudo guardar el cambio.");
      return false;
    } finally {
      setGuardando(false);
      setEstadoPendiente(null);
      setResponsablePendiente(null);
    }
  }

  function cambiarEstado(nuevo: EstadoCaso) {
    if (nuevo === "cerrado") {
      setCerrando(true);
      return;
    }
    setCerrando(false);
    setEstadoPendiente(nuevo);
    guardar({ estado: nuevo });
  }

  async function confirmarCierre(e: React.FormEvent) {
    e.preventDefault();
    if (await guardar({ estado: "cerrado", motivo_cierre: motivo.trim() })) {
      setCerrando(false);
      setMotivo("");
    }
  }

  return (
    <article className={`rounded-xl border border-l-4 p-4 flex flex-col gap-3 ${clases.tarjeta} ${caso.estado === "cerrado" ? "opacity-75" : ""}`}>
      <div className="flex items-start gap-3">
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-bold uppercase tracking-wide ${clases.insignia}`}
          title={DESCRIPCION_URGENCIA[caso.urgencia]}
        >
          {caso.urgencia === "urgente" && <Siren size={12} aria-hidden="true" />}
          {ETIQUETA_URGENCIA[caso.urgencia]}
        </span>
        {/* 🆕 (sesión 2026-11-02) Qué significa cada nivel, sin salir de la bandeja. */}
        {caso.urgencia !== "seguimiento" && (
          <TerminoAyuda termino={caso.urgencia === "urgente" ? "urgente" : "en_alerta"} />
        )}
        <div className="min-w-0 flex-1">
          <Link
            href={`/estudiantes/${caso.persona_id}`}
            className="block text-[14px] font-bold text-ink dark:text-ink-dark hover:text-teal-700 dark:hover:text-teal-accent-dark truncate"
          >
            {caso.nombre_completo}
          </Link>
          <p className="m-0 mt-0.5 text-[12px] text-ink/55 dark:text-ink-dark/55">
            {caso.origen === "prueba"
              ? [caso.prueba, caso.campana, caso.fecha_evaluacion ? `evaluado el ${fecha(caso.fecha_evaluacion)}` : null]
                  .filter(Boolean)
                  .join(" · ")
              : "Antecedentes clínicos externos"}
          </p>
        </div>
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold ${
            esperaLarga
              ? "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300"
              : "bg-surface/80 text-ink/60 dark:bg-surface-raised-dark dark:text-ink-dark/60"
          }`}
          title={caso.ultimo_seguimiento ? `Último seguimiento: ${fecha(caso.ultimo_seguimiento)}` : "Sin sesiones de seguimiento"}
        >
          <Hourglass size={11} aria-hidden="true" />
          {textoDias(dias)}
        </span>
      </div>

      {caso.origen === "prueba" && (caso.alertas ?? []).length > 0 && (
        <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
          {(caso.alertas ?? []).map((a, i) => (
            <li key={i} className="rounded-lg border border-border/70 dark:border-border-dark bg-surface/70 dark:bg-surface-dark/70 px-2.5 py-1.5 text-[12.5px]">
              <span className="text-ink/70 dark:text-ink-dark/70">{a.dimension || "Resultado"}</span>{" "}
              <span className="font-bold text-ink dark:text-ink-dark">{a.nivel}</span>
              {a.item_critico && (
                <span className="mt-0.5 flex items-start gap-1.5 font-semibold text-red-700 dark:text-red-300">
                  <Siren size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                  <span>Ítem crítico{a.motivo ? `: ${a.motivo}` : ""}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {caso.origen === "antecedentes" && (
        <p className="m-0 rounded-lg border border-border/70 dark:border-border-dark bg-surface/70 dark:bg-surface-dark/70 px-2.5 py-1.5 text-[12.5px] text-ink/75 dark:text-ink-dark/75">
          {(caso.motivos ?? []).join(" · ") || "Antecedentes en «Sí»"}
          {caso.diagnostico_reportado ? ` — ${caso.diagnostico_reportado}` : ""}
        </p>
      )}

      {/* Estado y responsable, editables en el lugar. */}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-[12px] font-semibold text-ink/55 dark:text-ink-dark/55">
          Estado
          <Select
            value={cerrando ? "cerrado" : (estadoPendiente ?? caso.estado)}
            onChange={(e) => cambiarEstado(e.target.value as EstadoCaso)}
            disabled={guardando}
            aria-label={`Estado del caso de ${caso.nombre_completo}`}
          >
            {ESTADOS_CASO.map((e) => (
              <option key={e} value={e}>
                {ETIQUETA_ESTADO[e]}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-[12px] font-semibold text-ink/55 dark:text-ink-dark/55">
          Responsable
          <Select
            value={responsablePendiente ?? (caso.responsable ? String(caso.responsable.id) : "")}
            onChange={(e) => {
              setResponsablePendiente(e.target.value);
              guardar({ responsable_usuario_id: e.target.value ? Number(e.target.value) : null });
            }}
            disabled={guardando}
            aria-label={`Responsable del caso de ${caso.nombre_completo}`}
          >
            <option value="">Sin responsable</option>
            {opcionesResponsable.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.nombre}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {cerrando && caso.estado !== "cerrado" && (
        <form onSubmit={confirmarCierre} className="flex flex-col gap-2 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-3">
          <label htmlFor={`motivo-${caso.id}`} className="text-[12px] font-semibold text-ink dark:text-ink-dark">
            Motivo del cierre
          </label>
          <textarea
            id={`motivo-${caso.id}`}
            required
            minLength={3}
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej.: síntomas remitidos tras la intervención; alta en terapia externa…"
            className="w-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
          />
          <div className="flex items-center justify-end gap-3">
            <button type="button" onClick={() => setCerrando(false)} className="text-[12.5px] text-ink/60 dark:text-ink-dark/60 hover:underline">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={guardando || motivo.trim().length < 3}
              className="rounded-card bg-accion px-3 py-1.5 text-[12.5px] font-semibold text-white hover:bg-accion-hover disabled:opacity-40 dark:bg-teal-accent-dark dark:text-mist-dark"
            >
              {guardando ? "Cerrando…" : "Cerrar caso"}
            </button>
          </div>
        </form>
      )}

      {caso.estado === "cerrado" && caso.motivo_cierre && (
        <p className="m-0 text-[12px] text-ink/60 dark:text-ink-dark/60">
          <strong className="font-semibold">Cerrado el {fecha(caso.cerrado_en)}:</strong> {caso.motivo_cierre}
        </p>
      )}

      <TextoError className="text-xs">{errorAccion}</TextoError>

      {verHistorial && <HistorialCaso casoId={caso.id} />}

      <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2 pt-2 border-t border-border/70 dark:border-border-dark text-[12.5px] font-semibold">
        <button
          type="button"
          onClick={() => setVerHistorial((v) => !v)}
          aria-expanded={verHistorial}
          className="mr-auto inline-flex items-center gap-1.5 text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark"
        >
          <History size={14} aria-hidden="true" />
          {verHistorial ? "Ocultar historial" : "Historial"}
        </button>
        <Link
          href={`/estudiantes/${caso.persona_id}/seguimiento/nuevo`}
          className="inline-flex items-center gap-1.5 text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark"
        >
          <HeartHandshake size={14} aria-hidden="true" />
          Registrar seguimiento
        </Link>
        <Link
          href={`/estudiantes/${caso.persona_id}`}
          className="inline-flex items-center gap-1 text-teal-700 dark:text-teal-accent-dark hover:underline"
        >
          Ver ficha
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

function HistorialCaso({ casoId }: { casoId: number }) {
  const consulta = useQuery({
    queryKey: ["caso-historial", casoId],
    queryFn: () => apiClient.get<EventoCasoRiesgo[]>(`/educativo/casos-riesgo/${casoId}/historial`),
  });
  if (consulta.isPending) return <p className="m-0 text-[12px] text-ink/45 dark:text-ink-dark/45">Cargando historial…</p>;
  if (consulta.error) return <TextoError className="text-xs">No se pudo cargar el historial.</TextoError>;
  return (
    <ol className="m-0 flex flex-col gap-1.5 rounded-lg border border-border/70 dark:border-border-dark bg-surface/70 dark:bg-surface-dark/70 p-3 list-none">
      {(consulta.data ?? []).map((e) => (
        <li key={e.id} className="text-[12px] text-ink/70 dark:text-ink-dark/70">
          <span className="text-ink/45 dark:text-ink-dark/45">{new Date(e.creado_en).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" })}</span>{" "}
          <span className="inline-flex items-center gap-1 font-semibold text-ink dark:text-ink-dark">
            <UserRound size={11} aria-hidden="true" />
            {e.usuario ?? "Sistema"}
          </span>{" "}
          {e.tipo === "creado" && "abrió el caso."}
          {e.tipo === "estado" && (
            <>
              cambió el estado: {e.estado_anterior ? ETIQUETA_ESTADO[e.estado_anterior] : "—"} →{" "}
              <strong className="font-semibold">{e.estado_nuevo ? ETIQUETA_ESTADO[e.estado_nuevo] : "—"}</strong>.
            </>
          )}
          {e.tipo === "responsable" && (
            <>
              cambió el responsable: {e.responsable_anterior ?? "sin responsable"} →{" "}
              <strong className="font-semibold">{e.responsable_nuevo ?? "sin responsable"}</strong>.
            </>
          )}
          {e.nota && <span className="block pl-4 italic text-ink/55 dark:text-ink-dark/55">“{e.nota}”</span>}
        </li>
      ))}
    </ol>
  );
}

// 🆕 (sesión 2026-11-01, punto 4 del análisis de UI/UX) El rol colegio no
// tiene acceso a esta sección (el backend le responde 403): se le explica en
// vez de mostrarle un error. El menú ya no le ofrece el enlace.
export default function CasosRiesgoPage() {
  const { sesion } = useAuth();
  if (sesion?.rol === "colegio") {
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-6 text-sm text-ink/70 dark:text-ink-dark/70">
        <p className="m-0 font-semibold text-ink dark:text-ink-dark">Casos en riesgo</p>
        <p className="m-0 mt-1">Esta sección es solo para el equipo de psicología del colegio.</p>
      </div>
    );
  }
  return <CasosRiesgoPageContenido />;
}
