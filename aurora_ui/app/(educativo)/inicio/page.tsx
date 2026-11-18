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
import { useConsultaApi } from "@/lib/consultas";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { ACENTOS, type Acento } from "@/lib/acentos";
import type { BandejaCasosRiesgo, CasoRiesgo, Cita, Evaluacion, RespuestaPaginada, ResumenInicio, SeriesInicio } from "@/types/api";
import { CLASE_URGENCIA, ETIQUETA_URGENCIA } from "@/lib/casos-riesgo";
import { primerNombre, useUsuarioActual } from "@/lib/usuario";
import { AvanceCampanas, GraficoEvaluacionesMes, GraficoSeguimientoMes } from "@/components/educativo/GraficosInicio";
import { CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { EsqueletoLineas } from "@/components/ui/Esqueleto";


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

// 🆕 (sesión 2026-10-31) Fondo de cada bloque = color de su sección:
// ACENTOS[x].fondo (bloques chicos) / .fondoSuave (grandes), lib/acentos.ts.

// --- Accesos rápidos: 4 atajos a la acción más común de cada área ---
// 🆕 `acento` = color de la sección a la que lleva (lib/acentos.ts).
function AccesoRapido({ href, icono: Icono, label, acento }: { href: string; icono: typeof Plus; label: string; acento: Acento }) {
  return (
    <Link
      href={href}
      className={`flex items-center gap-3 border rounded-xl px-4 py-3.5 hover:shadow-sm hover:-translate-y-px transition-all group ${ACENTOS[acento].fondo}`}
    >
      <div className={`w-9 h-9 rounded-lg ${ACENTOS[acento].chipSolido} flex items-center justify-center flex-shrink-0`}>
        <Icono size={17} strokeWidth={2} aria-hidden="true" />
      </div>
      <span className="flex-1 min-w-0 text-[13px] font-semibold leading-snug text-ink dark:text-ink-dark">{label}</span>
      <ArrowRight
        size={15}
        strokeWidth={2}
        aria-hidden="true"
        className={`opacity-50 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all flex-shrink-0 ${ACENTOS[acento].texto}`}
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
    // 🆕 Ícono a la izquierda y, al costado, número + nombre (antes iban
    // apilados y dejaban espacio sobrante a la derecha de cada tarjeta).
    <div className={`border rounded-xl px-4 py-3.5 sm:px-5 sm:py-4 flex items-center gap-3.5 ${ACENTOS[acento].fondo}`}>
      <div className={`w-11 h-11 rounded-xl ${ACENTOS[acento].chipSolido} flex items-center justify-center flex-shrink-0 shadow-sm`}>
        <Icono size={20} strokeWidth={2} aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="font-display text-[26px] font-bold text-ink dark:text-ink-dark leading-none">
          {valor === null ? (
            <span className="inline-block w-10 h-6 bg-mist dark:bg-surface-raised-dark rounded animate-pulse align-middle" />
          ) : (
            <>
              {valor}
              {sufijo && <span className="text-[15px] font-semibold text-ink/65 dark:text-ink-dark/55 ml-1">{sufijo}</span>}
            </>
          )}
        </p>
        <p className="mt-1 text-[12px] font-medium leading-snug text-ink/65 dark:text-ink-dark/60">{label}</p>
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
    <div className={`border rounded-xl p-5 flex flex-col gap-3.5 min-w-0 ${ACENTOS[acento].fondoSuave} ${className}`}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[13px] font-bold text-ink dark:text-ink-dark">
          <span className={`flex h-6 w-6 items-center justify-center rounded-md ${ACENTOS[acento].chip}`}>
            <Icono size={13} strokeWidth={2.2} aria-hidden="true" />
          </span>
          {titulo}
          {subtitulo && <span className="font-medium text-ink/65 dark:text-ink-dark/55">· {subtitulo}</span>}
        </h2>
        <Link
          href={enlace}
          className="text-[12px] font-semibold text-seccion-700 dark:text-seccion-claro hover:underline whitespace-nowrap"
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
  // 🆕 Saludo con el nombre real (GET /auth/me), no con el usuario del correo.
  const usuario = useUsuarioActual(!!sesion);
  // 🆕 (2026-11-17) Mientras llega el nombre se dice solo "Hola" (antes se
  // veía un instante el usuario del correo, p. ej. "Hola, mvera.psi").
  const saludo = usuario ? (primerNombre(usuario.nombre_completo) ?? sesion?.email?.split("@")[0] ?? null) : null;

  // 🆕 (2026-11-17, plan de UX fase 1) Con memoria entre pantallas
  // (lib/consultas.ts): al volver al Inicio se ve al instante lo último y se
  // actualiza por detrás. Cada tarjeta sigue mostrando su propio error.
  const consultaResumen = useConsultaApi<ResumenInicio>(vePerfilClinico ? "/educativo/inicio/resumen" : null, {
    mensajeError: "No se pudo cargar el resumen del mes.",
  });
  // 🆕 (sesión 2026-11-01) La bandeja con urgencia (GET /casos-riesgo), que
  // ya viene ordenada: urgentes primero. Un alumno puede tener más de un caso
  // abierto; la tarjeta lista alumnos, cada uno con su caso más urgente.
  const consultaCasos = useConsultaApi<BandejaCasosRiesgo, CasoRiesgo[]>(vePerfilClinico ? "/educativo/casos-riesgo" : null, {
    seleccionar: ({ casos: lista }) => lista.filter((c, i) => lista.findIndex((o) => o.persona_id === c.persona_id) === i),
    mensajeError: "No se pudieron cargar los casos pendientes.",
  });
  // 🆕 Gráficos (sesión 2026-10-30) — GET /educativo/inicio/series.
  const consultaSeries = useConsultaApi<SeriesInicio>(vePerfilClinico ? "/educativo/inicio/series?meses=6" : null, {
    mensajeError: "No se pudieron cargar los gráficos.",
  });
  const consultaCitas = useConsultaApi<Cita[]>("/admin/personas/citas/mi-agenda", {
    mensajeError: "No se pudo cargar la agenda.",
  });
  // El staff clínico ve el avance de campañas desde /inicio/series; la lista
  // completa solo hace falta para la tarjeta de 'colegio'.
  const consultaCampanas = useConsultaApi<RespuestaPaginada<Evaluacion>, Evaluacion[]>(
    !vePerfilClinico && sesion?.institucionId ? `/educativo/campanas/?institucion_id=${sesion.institucionId}&limit=200` : null,
    { seleccionar: (r) => r.items, mensajeError: "No se pudieron cargar las campañas." },
  );

  const resumen = consultaResumen.datos ?? null;
  const errorResumen = consultaResumen.error;
  const casos = consultaCasos.datos ?? null;
  const errorCasos = consultaCasos.error;
  const series = consultaSeries.datos ?? null;
  const errorSeries = consultaSeries.error;
  const citas = consultaCitas.datos ?? null;
  const errorCitas = consultaCitas.error;
  const campanas = consultaCampanas.datos ?? null;
  const errorCampanas = consultaCampanas.error;

  const citasHoy = (citas ?? []).filter((c) => c.estado === "Programada" && esHoy(c.fecha_hora));
  const campanasActivas = (campanas ?? []).filter((c) => c.estado === "activa");
  const campanasPorCerrar = campanasActivas.filter((c) => cierraEnMenosDe(c.fecha_fin, 7));

  const nombreMes = new Date().toLocaleDateString("es-PE", { month: "long" });

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      {/* ===== Encabezado ===== */}
      <div className="bg-gradient-to-br from-seccion-900 to-seccion-600 dark:from-surface-raised-dark dark:to-surface-dark rounded-2xl px-5 py-6 sm:px-7 sm:py-7 flex items-center justify-between flex-wrap gap-5">
        <div>
          <p className="text-[13px] font-medium text-white/70 dark:text-seccion-claro">
            {new Date().toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1 className="mt-1 font-display text-[26px] font-bold text-white dark:text-ink-dark">
            Hola{saludo ? `, ${saludo}` : ""}
          </h1>
          <p className="mt-1.5 text-[13px] text-white/75 dark:text-ink-dark/60 max-w-md">
            Esto es lo que está pasando en tu institución este {nombreMes}.
          </p>
        </div>
        {vePerfilClinico && (
          <Link
            href="/campanas/nueva"
            className="flex items-center gap-2 bg-white dark:bg-seccion-claro text-seccion-900 dark:text-mist-dark rounded-xl px-5 py-2.5 text-[13px] font-bold hover:bg-white/90 dark:hover:opacity-90 transition-colors"
          >
            <Plus size={16} strokeWidth={2.4} aria-hidden="true" />
            Nueva campaña
          </Link>
        )}
      </div>

      {/* ===== Accesos rápidos ===== */}
      {/* 🆕 (2026-11-17, plan de UX fase 2) "Una pantalla, un color": el
          Inicio va en tonos teal. Los accesos rápidos son la ÚNICA excepción:
          su trabajo es llevar a cada sección, así que anticipan su color.
          Ámbar sigue solo en lo que es riesgo clínico. */}
      <div>
        <h2 className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink/65 dark:text-ink-dark/55">
          Accesos rápidos
        </h2>
        {/* 4 columnas solo cuando de verdad entran (xl) — antes `sm:grid-cols-4`
            apretaba "Casos en riesgo"/"Documentos" fuera de su tarjeta. */}
        <div className="grid grid-cols-1 min-[440px]:grid-cols-2 xl:grid-cols-4 gap-3">
          <AccesoRapido href="/estudiantes" icono={Users} label="Padrón" acento="teal" />
          {/* 🆕 (sesión 2026-11-01) El rol colegio no crea campañas ni ve la
              bandeja clínica: sus accesos son de consulta. */}
          {vePerfilClinico ? (
            <AccesoRapido href="/campanas/nueva" icono={Flag} label="Nueva campaña" acento="azul" />
          ) : (
            <AccesoRapido href="/campanas" icono={Flag} label="Campañas" acento="azul" />
          )}
          <AccesoRapido href="/documentos" icono={FileText} label="Documentos" acento="violeta" />
          {vePerfilClinico ? (
            <AccesoRapido href="/casos-riesgo" icono={AlertTriangle} label="Casos en riesgo" acento="riesgo" />
          ) : (
            <AccesoRapido href="/academico" icono={Users} label="Estructura académica" acento="teal" />
          )}
        </div>
      </div>

      {/* ===== Resumen del mes (KPIs reales) ===== */}
      {vePerfilClinico && (
        <div>
          <h2 className="mb-3 text-[12px] font-bold uppercase tracking-wide text-ink/65 dark:text-ink-dark/55">
            Resumen de {nombreMes}
          </h2>
          <TextoError className="mb-2">{errorResumen}</TextoError>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-3.5">
            <TarjetaKpi acento="teal" icono={GraduationCap} label="Alumnos en el padrón" valor={resumen?.total_alumnos ?? null} />
            <TarjetaKpi acento="teal" icono={Activity} label="Pruebas finalizadas este mes" valor={resumen?.pruebas_finalizadas_mes ?? null} />
            <TarjetaKpi acento="teal" icono={HeartHandshake} label="Alumnos con seguimiento este mes" valor={resumen?.estudiantes_con_seguimiento_mes ?? null} />
            <TarjetaKpi acento="teal" icono={Flag} label="Campañas activas" valor={resumen?.campanas_activas ?? null} />
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
              acento="teal"
              className="lg:col-span-2"
            >
              {series ? <GraficoEvaluacionesMes meses={series.meses} /> : <EsqueletoGrafico />}
            </TarjetaResumen>
            <TarjetaResumen icono={Flag} titulo="Avance de campañas" enlace="/campanas" acento="teal">
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
            <TarjetaResumen icono={AlertTriangle} titulo="Casos en riesgo" enlace="/casos-riesgo" acento="riesgo">
              {casos === null ? (
                <EsqueletoLineas cantidad={3} />
              ) : casos.length === 0 ? (
                <p className="text-[12px] text-ink/65 dark:text-ink-dark/55 italic">Sin casos pendientes.</p>
              ) : (
                <ul className="p-0 list-none flex flex-col gap-2">
                  {casos.slice(0, 4).map((c) => (
                    <li key={c.persona_id} className="flex items-center justify-between gap-2 text-[12.5px]">
                      <span className="truncate text-ink/80 dark:text-ink-dark/80">{c.nombre_completo}</span>
                      <span className={`flex-shrink-0 text-[11.5px] font-semibold rounded-full px-2 py-0.5 ${CLASE_URGENCIA[c.urgencia].insignia}`}>
                        {ETIQUETA_URGENCIA[c.urgencia]}
                      </span>
                    </li>
                  ))}
                  {casos.length > 4 && (
                    <li className="text-[12px] text-ink/65 dark:text-ink-dark/55">+{casos.length - 4} más</li>
                  )}
                </ul>
              )}
              <TextoError className="text-xs">{errorCasos}</TextoError>
            </TarjetaResumen>
            <TarjetaResumen icono={Calendar} titulo="Citas de hoy" enlace="/agenda" acento="teal">
              {citas === null ? (
                <EsqueletoLineas cantidad={3} />
              ) : citasHoy.length === 0 ? (
                <p className="text-[12px] text-ink/65 dark:text-ink-dark/55 italic">Sin citas agendadas para hoy.</p>
              ) : (
                <ul className="p-0 list-none flex flex-col gap-2">
                  {citasHoy.slice(0, 4).map((c) => (
                    <li key={c.id} className="flex items-center gap-2 text-[12.5px] text-ink/80 dark:text-ink-dark/80">
                      <Clock size={12} strokeWidth={2} className="text-ink/65 dark:text-ink-dark/55 flex-shrink-0" aria-hidden="true" />
                      <span className="font-mono text-[12px]">
                        {new Date(c.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <span className="truncate">{c.titulo || c.motivo}</span>
                    </li>
                  ))}
                  {citasHoy.length > 4 && (
                    <li className="text-[12px] text-ink/65 dark:text-ink-dark/55">+{citasHoy.length - 4} más</li>
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
          <TarjetaResumen icono={Calendar} titulo="Citas de hoy" enlace="/agenda" acento="teal">
            {citas === null ? (
              <EsqueletoLineas cantidad={3} />
            ) : citasHoy.length === 0 ? (
              <p className="text-[12px] text-ink/65 dark:text-ink-dark/55 italic">Sin citas agendadas para hoy.</p>
            ) : (
              <ul className="p-0 list-none flex flex-col gap-2">
                {citasHoy.slice(0, 4).map((c) => (
                  <li key={c.id} className="flex items-center gap-2 text-[12.5px] text-ink/80 dark:text-ink-dark/80">
                    <Clock size={12} strokeWidth={2} className="text-ink/65 dark:text-ink-dark/55 flex-shrink-0" aria-hidden="true" />
                    <span className="font-mono text-[12px]">
                      {new Date(c.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className="truncate">{c.titulo || c.motivo}</span>
                  </li>
                ))}
                {citasHoy.length > 4 && (
                  <li className="text-[12px] text-ink/65 dark:text-ink-dark/55">+{citasHoy.length - 4} más</li>
                )}
              </ul>
            )}
            <TextoError className="text-xs">{errorCitas}</TextoError>
          </TarjetaResumen>
          <TarjetaResumen icono={Flag} titulo="Campañas activas" enlace="/campanas" acento="teal">
            {campanas === null ? (
              <EsqueletoLineas cantidad={3} />
            ) : campanasActivas.length === 0 ? (
              <p className="text-[12px] text-ink/65 dark:text-ink-dark/55 italic">Sin campañas activas.</p>
            ) : (
              <>
                <p className="font-display text-2xl font-bold text-ink dark:text-ink-dark">{campanasActivas.length}</p>
                {campanasPorCerrar.length > 0 && (
                  <p className="text-[12px] text-ink/65 dark:text-ink-dark/60">
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
