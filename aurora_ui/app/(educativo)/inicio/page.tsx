"use client";

// 🆕 Rediseño del dashboard de aterrizaje (sesión 2026-10-25, a pedido del
// usuario: "quiero algo similar [a una referencia de dashboard con
// accesos rápidos y resumen por sección] pero con buena calidad de
// interfaz, lo que menos se desea es lo genérico"). Reusa los 3 endpoints
// que ya existían (casos-pendientes, mi-agenda, campañas) y suma uno
// nuevo, chico y real: GET /educativo/inicio/resumen (ver
// docs/gaps-pendientes.md) — total de alumnos, pruebas finalizadas y
// alumnos con seguimiento ESTE MES, campañas activas. Nada de fotos de
// stock ni contenido de relleno: cada número de esta pantalla viene de
// una consulta real a la base de datos de la institución.
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Plus,
  Users,
  FileText,
  AlertTriangle,
  Calendar,
  Flag,
  Activity,
  HeartHandshake,
  GraduationCap,
  ArrowRight,
  Clock,
  BarChart3,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { ACENTOS, type Acento } from "@/lib/acentos";
import type { Cita, Evaluacion, RespuestaPaginada, ResumenInicio, SeriesInicio } from "@/types/api";
import { AvanceCampanas, GraficoEvaluacionesMes, GraficoSeguimientoMes } from "@/components/educativo/GraficosInicio";

type CasoPendiente = {
  persona_id: number;
  nombre_completo: string;
  nivel_alerta: string;
  [clave: string]: unknown;
};

function esHoy(fechaIso: string): boolean {
  const fecha = new Date(fechaIso);
  const hoy = new Date();
  return (
    fecha.getFullYear() === hoy.getFullYear() &&
    fecha.getMonth() === hoy.getMonth() &&
    fecha.getDate() === hoy.getDate()
  );
}

function cierraEnMenosDe(fechaIso: string | null, dias: number): boolean {
  if (!fechaIso) return false;
  const limite = new Date();
  limite.setDate(limite.getDate() + dias);
  return new Date(fechaIso) <= limite;
}

// --- Accesos rápidos: 4 atajos a la acción más común de cada área ---
// 🆕 `acento` = color de la sección a la que lleva (lib/acentos.ts).
function AccesoRapido({ href, icono: Icono, label, acento }: { href: string; icono: typeof Plus; label: string; acento: Acento }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-xl px-4 py-3.5 hover:border-teal-400 dark:hover:border-teal-accent-dark transition-colors group"
    >
      <div className={`w-9 h-9 rounded-lg ${ACENTOS[acento].chip} flex items-center justify-center flex-shrink-0`}>
        <Icono size={17} strokeWidth={2} aria-hidden="true" />
      </div>
      <span className="flex-1 min-w-0 text-[13px] font-semibold leading-snug text-ink dark:text-ink-dark">{label}</span>
      <ArrowRight
        size={15}
        strokeWidth={2}
        aria-hidden="true"
        className="text-ink/25 dark:text-ink-dark/25 group-hover:text-teal-600 dark:group-hover:text-teal-accent-dark group-hover:translate-x-0.5 transition-all flex-shrink-0"
      />
    </Link>
  );
}

// --- Tarjeta KPI: número grande + etiqueta, el resumen real del mes ---
function TarjetaKpi({
  icono: Icono,
  label,
  valor,
  sufijo,
  acento,
}: {
  icono: typeof Activity;
  label: string;
  valor: number | null;
  sufijo?: string;
  acento: Acento;
}) {
  return (
    <div className="bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-xl p-4 sm:p-5 flex flex-col gap-3">
      <div className={`w-8 h-8 rounded-lg ${ACENTOS[acento].chip} flex items-center justify-center`}>
        <Icono size={15} strokeWidth={2} aria-hidden="true" />
      </div>
      <div>
        <p className="m-0 font-display text-[28px] font-bold text-ink dark:text-ink-dark leading-none">
          {valor === null ? (
            <span className="inline-block w-10 h-6 bg-mist dark:bg-surface-raised-dark rounded animate-pulse align-middle" />
          ) : (
            <>
              {valor}
              {sufijo && <span className="text-[15px] font-semibold text-ink/40 dark:text-ink-dark/40 ml-1">{sufijo}</span>}
            </>
          )}
        </p>
        <p className="m-0 mt-1.5 text-[12px] font-medium text-ink/55 dark:text-ink-dark/55">{label}</p>
      </div>
    </div>
  );
}

// --- Tarjeta de resumen por apartado (casos/citas/campañas) ---
function TarjetaResumen({
  icono: Icono,
  titulo,
  enlace,
  acento,
  subtitulo,
  className = "",
  children,
}: {
  icono: typeof AlertTriangle;
  titulo: string;
  enlace: string;
  acento: Acento;
  subtitulo?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`bg-surface dark:bg-surface-dark border border-border dark:border-border-dark rounded-xl p-5 flex flex-col gap-3.5 min-w-0 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="m-0 flex items-center gap-2 text-[13px] font-bold text-ink dark:text-ink-dark">
          <span className={`flex h-6 w-6 items-center justify-center rounded-md ${ACENTOS[acento].chip}`}>
            <Icono size={13} strokeWidth={2.2} aria-hidden="true" />
          </span>
          {titulo}
          {subtitulo && <span className="font-medium text-ink/40 dark:text-ink-dark/40">· {subtitulo}</span>}
        </h2>
        <Link
          href={enlace}
          className="text-[11.5px] font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline whitespace-nowrap"
        >
          Ver todo →
        </Link>
      </div>
      {children}
    </div>
  );
}

function EsqueletoGrafico({ bajo = false }: { bajo?: boolean }) {
  return <div className={`w-full animate-pulse rounded-lg bg-mist dark:bg-surface-raised-dark ${bajo ? "h-40" : "h-48"}`} />;
}

export default function InicioPage() {
  const { sesion } = useAuth();
  const vePerfilClinico = sesion?.rol === "psicologo" || sesion?.rol === "admin";

  const [resumen, setResumen] = useState<ResumenInicio | null>(null);
  const [errorResumen, setErrorResumen] = useState<string | null>(null);

  const [casos, setCasos] = useState<CasoPendiente[] | null>(null);
  const [errorCasos, setErrorCasos] = useState<string | null>(null);

  const [citas, setCitas] = useState<Cita[] | null>(null);
  const [errorCitas, setErrorCitas] = useState<string | null>(null);

  const [campanas, setCampanas] = useState<Evaluacion[] | null>(null);

  // 🆕 Gráficos (sesión 2026-10-30) — GET /educativo/inicio/series.
  const [series, setSeries] = useState<SeriesInicio | null>(null);
  const [errorSeries, setErrorSeries] = useState<string | null>(null);
  const [errorCampanas, setErrorCampanas] = useState<string | null>(null);

  useEffect(() => {
    if (vePerfilClinico) {
      apiClient
        .get<CasoPendiente[]>("/educativo/casos-pendientes")
        .then(setCasos)
        .catch((err) => setErrorCasos(err.message || "No se pudieron cargar los casos pendientes."));

      apiClient
        .get<ResumenInicio>("/educativo/inicio/resumen")
        .then(setResumen)
        .catch((err) => setErrorResumen(err.message || "No se pudo cargar el resumen del mes."));

      apiClient
        .get<SeriesInicio>("/educativo/inicio/series?meses=6")
        .then(setSeries)
        .catch((err) => setErrorSeries(err.message || "No se pudieron cargar los gráficos."));
    }

    apiClient
      .get<Cita[]>("/admin/personas/citas/mi-agenda")
      .then(setCitas)
      .catch((err) => setErrorCitas(err.message || "No se pudo cargar la agenda."));

    // El staff clínico ve el avance de campañas desde /inicio/series; la
    // lista completa solo hace falta para la tarjeta de 'colegio'.
    if (!vePerfilClinico && sesion?.institucionId) {
      apiClient
        .get<RespuestaPaginada<Evaluacion>>(`/educativo/campanas/?institucion_id=${sesion.institucionId}&limit=200`)
        .then((r) => setCampanas(r.items))
        .catch((err) => setErrorCampanas(err.message || "No se pudieron cargar las campañas."));
    }
  }, [vePerfilClinico, sesion?.institucionId]);

  const citasHoy = (citas ?? []).filter((c) => c.estado === "Programada" && esHoy(c.fecha_hora));
  const campanasActivas = (campanas ?? []).filter((c) => c.estado === "activa");
  const campanasPorCerrar = campanasActivas.filter((c) => cierraEnMenosDe(c.fecha_fin, 7));

  const nombreMes = new Date().toLocaleDateString("es-PE", { month: "long" });

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-5">
      {/* ===== Encabezado ===== */}
      <div className="bg-gradient-to-br from-teal-900 to-teal-600 dark:from-surface-raised-dark dark:to-surface-dark rounded-2xl px-5 py-6 sm:px-7 sm:py-7 flex items-center justify-between flex-wrap gap-5">
        <div>
          <p className="m-0 text-[13px] font-medium text-white/70 dark:text-teal-accent-dark">
            {new Date().toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1 className="m-0 mt-1 font-display text-[26px] font-bold text-white dark:text-ink-dark">
            Hola{sesion?.email ? `, ${sesion.email.split("@")[0]}` : ""}
          </h1>
          <p className="m-0 mt-1.5 text-[13px] text-white/75 dark:text-ink-dark/60 max-w-md">
            Esto es lo que está pasando en tu institución este {nombreMes}.
          </p>
        </div>
        {vePerfilClinico && (
          <Link
            href="/campanas/nueva"
            className="flex items-center gap-2 bg-white dark:bg-teal-accent-dark text-teal-900 dark:text-mist-dark rounded-xl px-5 py-2.5 text-[13px] font-bold hover:bg-white/90 dark:hover:opacity-90 transition-colors"
          >
            <Plus size={16} strokeWidth={2.4} aria-hidden="true" />
            Nueva campaña
          </Link>
        )}
      </div>

      {/* ===== Accesos rápidos ===== */}
      <div>
        <h2 className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">
          Accesos rápidos
        </h2>
        {/* 4 columnas solo cuando de verdad entran (xl) — antes `sm:grid-cols-4`
            apretaba "Casos en riesgo"/"Documentos" fuera de su tarjeta. */}
        <div className="grid grid-cols-1 min-[440px]:grid-cols-2 xl:grid-cols-4 gap-3">
          <AccesoRapido href="/campanas/nueva" icono={Flag} label="Nueva campaña" acento="azul" />
          <AccesoRapido href="/estudiantes" icono={Users} label="Padrón" acento="teal" />
          <AccesoRapido href="/documentos" icono={FileText} label="Documentos" acento="violeta" />
          <AccesoRapido href="/casos-riesgo" icono={AlertTriangle} label="Casos en riesgo" acento="riesgo" />
        </div>
      </div>

      {/* ===== Resumen del mes (KPIs reales) ===== */}
      {vePerfilClinico && (
        <div>
          <h2 className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">
            Resumen de {nombreMes}
          </h2>
          <TextoError className="mb-2">{errorResumen}</TextoError>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-3.5">
            <TarjetaKpi acento="teal" icono={GraduationCap} label="Alumnos en el padrón" valor={resumen?.total_alumnos ?? null} />
            <TarjetaKpi acento="azul" icono={Activity} label="Pruebas finalizadas este mes" valor={resumen?.pruebas_finalizadas_mes ?? null} />
            <TarjetaKpi acento="teal" icono={HeartHandshake} label="Alumnos con seguimiento este mes" valor={resumen?.estudiantes_con_seguimiento_mes ?? null} />
            <TarjetaKpi acento="azul" icono={Flag} label="Campañas activas" valor={resumen?.campanas_activas ?? null} />
          </div>
        </div>
      )}

      {/* ===== 🆕 Gráficos (sesión 2026-10-30) — solo staff clínico: las
          series cuentan alertas y sesiones de seguimiento. Filas de 3
          columnas con tarjetas de la misma altura (grid estira), sin
          huecos: 2/3 + 1/3 arriba, 1/3 + 1/3 + 1/3 abajo. ===== */}
      {vePerfilClinico ? (
        <>
          <TextoError>{errorSeries}</TextoError>
          <div className="grid gap-3.5 lg:grid-cols-3">
            <TarjetaResumen
              icono={BarChart3}
              titulo="Evaluaciones por mes"
              subtitulo="últimos 6 meses"
              enlace="/pruebas"
              acento="azul"
              className="lg:col-span-2"
            >
              {series ? <GraficoEvaluacionesMes meses={series.meses} /> : <EsqueletoGrafico />}
            </TarjetaResumen>
            <TarjetaResumen icono={Flag} titulo="Avance de campañas" enlace="/campanas" acento="azul">
              {series ? <AvanceCampanas campanas={series.campanas} /> : <EsqueletoGrafico bajo />}
            </TarjetaResumen>
          </div>

          <div className="grid gap-3.5 md:grid-cols-2 lg:grid-cols-3">
            <TarjetaResumen
              icono={HeartHandshake}
              titulo="Seguimiento por mes"
              enlace="/agenda"
              acento="teal"
              className="md:col-span-2 lg:col-span-1"
            >
              {series ? <GraficoSeguimientoMes meses={series.meses} /> : <EsqueletoGrafico />}
            </TarjetaResumen>
            <TarjetaResumen icono={AlertTriangle} titulo="Casos sin seguimiento" enlace="/casos-riesgo" acento="riesgo">
              {casos === null ? (
                <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">Cargando...</p>
              ) : casos.length === 0 ? (
                <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40 italic">Sin casos pendientes.</p>
              ) : (
                <ul className="m-0 p-0 list-none flex flex-col gap-2">
                  {casos.slice(0, 4).map((c) => (
                    <li key={c.persona_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                      <span className="truncate text-ink/80 dark:text-ink-dark/80">{c.nombre_completo}</span>
                      <span className="flex-shrink-0 text-[10.5px] font-semibold text-amber-800 dark:text-amber bg-amber/15 rounded-full px-2 py-0.5">
                        {c.nivel_alerta}
                      </span>
                    </li>
                  ))}
                  {casos.length > 4 && (
                    <li className="text-[11.5px] text-ink/40 dark:text-ink-dark/40">+{casos.length - 4} más</li>
                  )}
                </ul>
              )}
              <TextoError className="text-xs">{errorCasos}</TextoError>
            </TarjetaResumen>
            <TarjetaResumen icono={Calendar} titulo="Citas de hoy" enlace="/agenda" acento="pizarra">
              {citas === null ? (
                <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">Cargando...</p>
              ) : citasHoy.length === 0 ? (
                <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40 italic">Sin citas agendadas para hoy.</p>
              ) : (
                <ul className="m-0 p-0 list-none flex flex-col gap-2">
                  {citasHoy.slice(0, 4).map((c) => (
                    <li key={c.id} className="flex items-center gap-2 text-[12.5px] text-ink/80 dark:text-ink-dark/80">
                      <Clock size={12} strokeWidth={2} className="text-ink/35 dark:text-ink-dark/35 flex-shrink-0" aria-hidden="true" />
                      <span className="font-mono text-[11.5px]">
                        {new Date(c.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="truncate">{c.titulo || c.motivo}</span>
                    </li>
                  ))}
                  {citasHoy.length > 4 && (
                    <li className="text-[11.5px] text-ink/40 dark:text-ink-dark/40">+{citasHoy.length - 4} más</li>
                  )}
                </ul>
              )}
              <TextoError className="text-xs">{errorCitas}</TextoError>
            </TarjetaResumen>
          </div>
        </>
      ) : (
        // 'colegio': sin datos clínicos — dos columnas completas.
        <div className="grid gap-3.5 sm:grid-cols-2">
          <TarjetaResumen icono={Calendar} titulo="Citas de hoy" enlace="/agenda" acento="pizarra">
            {citas === null ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">Cargando...</p>
            ) : citasHoy.length === 0 ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40 italic">Sin citas agendadas para hoy.</p>
            ) : (
              <ul className="m-0 p-0 list-none flex flex-col gap-2">
                {citasHoy.slice(0, 4).map((c) => (
                  <li key={c.id} className="flex items-center gap-2 text-[12.5px] text-ink/80 dark:text-ink-dark/80">
                    <Clock size={12} strokeWidth={2} className="text-ink/35 dark:text-ink-dark/35 flex-shrink-0" aria-hidden="true" />
                    <span className="font-mono text-[11.5px]">
                      {new Date(c.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className="truncate">{c.titulo || c.motivo}</span>
                  </li>
                ))}
                {citasHoy.length > 4 && (
                  <li className="text-[11.5px] text-ink/40 dark:text-ink-dark/40">+{citasHoy.length - 4} más</li>
                )}
              </ul>
            )}
            <TextoError className="text-xs">{errorCitas}</TextoError>
          </TarjetaResumen>
          <TarjetaResumen icono={Flag} titulo="Campañas activas" enlace="/campanas" acento="azul">
            {campanas === null ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">Cargando...</p>
            ) : campanasActivas.length === 0 ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40 italic">Sin campañas activas.</p>
            ) : (
              <>
                <p className="m-0 font-display text-2xl font-bold text-ink dark:text-ink-dark">{campanasActivas.length}</p>
                {campanasPorCerrar.length > 0 && (
                  <p className="m-0 text-[12px] text-ink/60 dark:text-ink-dark/60">
                    <span className="font-semibold text-ink dark:text-ink-dark">{campanasPorCerrar.length}</span> cierra
                    {campanasPorCerrar.length === 1 ? "" : "n"} en los próximos 7 días.
                  </p>
                )}
              </>
            )}
            <TextoError className="text-xs">{errorCampanas}</TextoError>
          </TarjetaResumen>
        </div>
      )}
    </div>
  );
}
