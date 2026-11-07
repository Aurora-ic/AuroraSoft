import type { ReactNode } from "react";
import {
  ClipboardCheck,
  AlertTriangle,
  HeartHandshake,
  CalendarClock,
  Mail,
  IdCard,
  Stethoscope,
  ShieldCheck,
  HelpCircle,
  FileSignature,
  GraduationCap,
  FileWarning,
  ArrowRight,
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import type {
  Cita,
  HistorialInformePersona,
  Persona,
  PersonaAntecedentesClinicos,
  SeccionActual,
  SesionSeguimiento,
} from "@/types/api";
import { ACENTOS, type Acento } from "@/lib/acentos";

// 🆕 Perfil del estudiante (sesión 2026-10-30, a pedido del usuario: "como
// la ficha de paciente de la referencia, pero con orden jerárquico y los
// colores del Padrón"). Dos piezas, ambas SOLO de presentación — reciben lo
// que la ficha (estudiantes/[personaId]/page.tsx) ya tenía cargado, ningún
// endpoint nuevo:
// - TarjetaPerfil: identidad a la izquierda (avatar, nombre, contacto,
//   acciones) y la cuadrícula de datos clave a la derecha.
// - IndicadoresEstudiante: el equivalente a los "signos vitales" — 4
//   tarjetas con un número grande y una línea de estado.
// Color: teal (Padrón/Estudiantes) como base; cada indicador lleva el acento
// de la sección de la que sale su dato (pruebas = azul de Evaluación,
// citas = pizarra de Gestión) y el ámbar SOLO para alertas clínicas.

// "AAAA-MM-DD" (fecha_nacimiento) se interpreta como fecha LOCAL: con
// new Date("2010-05-03") JavaScript la toma como medianoche UTC, que en Perú
// (UTC-5) cae el día anterior — fecha mostrada y edad del cumpleaños mal.
// Mismo criterio que el calcularEdad original de la ficha.
function aFecha(valor: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(valor) ? new Date(`${valor}T00:00:00`) : new Date(valor);
}

function calcularEdad(fechaIso: string | null): number | null {
  if (!fechaIso) return null;
  const nac = aFecha(fechaIso);
  if (Number.isNaN(nac.getTime())) return null;
  const hoy = new Date();
  let edad = hoy.getFullYear() - nac.getFullYear();
  const m = hoy.getMonth() - nac.getMonth();
  if (m < 0 || (m === 0 && hoy.getDate() < nac.getDate())) edad--;
  return edad;
}

function fechaCorta(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = aFecha(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("es-PE", { day: "numeric", month: "short", year: "numeric" });
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: ReactNode }) {
  const vacio = valor === null || valor === undefined || valor === "";
  return (
    <div className="min-w-0">
      <dt className="text-[12px] text-ink/50 dark:text-ink-dark/50">{etiqueta}</dt>
      <dd className={`m-0 mt-1 text-[14px] font-semibold break-words ${vacio ? "text-ink/30 dark:text-ink-dark/30" : "text-ink dark:text-ink-dark"}`}>
        {vacio ? "—" : valor}
      </dd>
    </div>
  );
}

// 🔧 Tercera versión (misma sesión, a pedido del usuario: "el bloque
// principal debe estar en horizontal y con los demás datos"): UN solo bloque
// a todo el ancho.
// - Fila superior horizontal en 3 zonas separadas por líneas verticales:
//   perfil (avatar, nombre, contacto, estado) | datos clave que NO están en
//   filiación (edad, matrícula, turno, año, consentimiento, antigüedad) |
//   acciones (mismo ancho, apiladas).
// - Debajo, separado por una línea horizontal, `children`: los bloques de
//   filiación editables (Identidad, Datos familiares, Antecedentes,
//   Contactos) — la ficha los pasa tal cual, sin cambiar su contenido.
// Sexo, fecha de nacimiento y código institucional viven solo en
// "Identidad" (donde se editan), nunca repetidos aquí.
export function TarjetaPerfil({
  alumno,
  matricula,
  consentimientoVigente,
  antecedentes = null,
  puedeEditarAntecedentes = false,
  informesPorRevisar = 0,
  acciones,
  children,
}: {
  alumno: Persona;
  matricula: SeccionActual | null;
  // null = todavía no cargó (o el rol no lo ve): no se afirma nada.
  consentimientoVigente: boolean | null;
  // null = no cargó / error: no se muestra el apartado de riesgo.
  antecedentes?: PersonaAntecedentesClinicos | null;
  puedeEditarAntecedentes?: boolean;
  // 🆕 (sesión 2026-11-07) Informes retenidos (con alerta) esperando la
  // revisión del psicólogo — alimenta "Pendiente en esta ficha".
  informesPorRevisar?: number;
  acciones?: ReactNode;
  // 🔧 (sesión 2026-11-07) La ficha ya NO pasa la filiación aquí: quedaba
  // la página "empezando dentro de un recuadro y saliéndose de él" y tres
  // niveles de cajas anidadas. Se conserva para otros usos.
  children?: ReactNode;
}) {
  const estadoDx = estadoDiagnostico(antecedentes);
  const edad = calcularEdad(alumno.fecha_nacimiento);
  const iniciales = `${alumno.nombres.trim()[0] ?? ""}${alumno.apellidos.trim()[0] ?? ""}`.toUpperCase();
  const ubicacion = matricula ? [matricula.nivel_educativo, matricula.grado, matricula.seccion].filter(Boolean).join(" · ") : null;

  return (
    <section className="rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden">
      <div className="h-1.5 bg-gradient-to-r from-teal-900 via-teal-600 to-teal-400 dark:from-teal-accent-dark/60 dark:to-teal-accent-dark/20" />

      {/* 🔧 (sesión 2026-10-31) Fondo teal suave SOLO en la cabecera del
          perfil, para que se distinga de los bloques de datos del estudiante
          (filiación, abajo, sobre fondo neutro). */}
      <div className="grid lg:grid-cols-[minmax(16rem,20rem)_1fr_13rem] bg-gradient-to-br from-teal-600/[0.10] via-teal-400/[0.06] to-teal-600/[0.02] dark:from-teal-accent-dark/[0.10] dark:via-teal-accent-dark/[0.04] dark:to-transparent">
        {/* --- 1. Perfil --- */}
        <div className="flex items-center gap-4 p-6 border-b lg:border-b-0 lg:border-r border-teal-600/15 dark:border-border-dark">
          <div className="relative shrink-0">
            <span className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-teal-900 to-teal-600 font-display text-[26px] font-bold text-white ring-4 ring-teal-600/10 dark:from-teal-accent-dark/40 dark:to-teal-accent-dark/10 dark:text-teal-accent-dark dark:ring-teal-accent-dark/10">
              {iniciales}
            </span>
            <span
              title={alumno.activo ? "Activo" : "Inactivo"}
              className={`absolute bottom-0.5 right-0.5 h-4 w-4 rounded-full ring-[3px] ring-surface dark:ring-surface-dark ${
                alumno.activo ? "bg-teal-500 dark:bg-teal-accent-dark" : "bg-ink/30 dark:bg-ink-dark/30"
              }`}
            />
          </div>
          <div className="min-w-0">
            <h1 className="m-0 font-display text-[21px] font-bold leading-tight text-teal-900 dark:text-ink-dark break-words">
              {alumno.nombres} {alumno.apellidos}
            </h1>
            <div className="mt-1 flex flex-col gap-0.5 text-[12.5px] text-ink/55 dark:text-ink-dark/55">
              {alumno.documento_identidad && (
                <span className="inline-flex items-center gap-1.5">
                  <IdCard size={13} aria-hidden="true" className="shrink-0" />
                  {alumno.documento_identidad}
                </span>
              )}
              {alumno.email && (
                <span className="inline-flex max-w-full items-center gap-1.5">
                  <Mail size={13} aria-hidden="true" className="shrink-0" />
                  <span className="truncate">{alumno.email}</span>
                </span>
              )}
            </div>
            <span
              className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${
                alumno.activo
                  ? "bg-surface text-teal-800 ring-1 ring-teal-600/20 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark dark:ring-0"
                  : "bg-surface text-ink/55 ring-1 ring-border dark:bg-border-dark dark:text-ink-dark/55 dark:ring-0"
              }`}
            >
              <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${alumno.activo ? "bg-teal-500 dark:bg-teal-accent-dark" : "bg-ink/30"}`} />
              {alumno.activo ? "Activo" : "Inactivo"}
            </span>
            {estadoDx === "con-dx" && (
              <span className="ml-1.5 mt-2 inline-flex items-center gap-1 rounded-full bg-amber/20 px-2.5 py-0.5 text-[12px] font-bold text-amber-800 dark:bg-amber/15 dark:text-amber">
                <Stethoscope size={12} aria-hidden="true" />
                Con Dx
              </span>
            )}
          </div>
        </div>

        {/* --- 2. Datos clave (los que no están en filiación) --- */}
        <dl className="m-0 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5 p-6 content-center border-b lg:border-b-0 lg:border-r border-teal-600/15 dark:border-border-dark">
          <Dato etiqueta="Edad" valor={edad !== null ? `${edad} años` : null} />
          <Dato
            etiqueta="Nivel · grado · sección"
            valor={
              ubicacion ? (
                <span className="text-teal-800 dark:text-teal-accent-dark">{ubicacion}</span>
              ) : (
                <span className="font-medium text-ink/45 dark:text-ink-dark/45">Sin matrícula</span>
              )
            }
          />
          <Dato etiqueta="Turno" valor={matricula?.turno} />
          <Dato etiqueta="Año escolar" valor={matricula?.anio_escolar ? String(matricula.anio_escolar) : null} />
          <Dato
            etiqueta="Consentimiento del apoderado"
            valor={
              consentimientoVigente === null ? null : consentimientoVigente ? (
                <EtiquetaEstado tono="ok">Vigente</EtiquetaEstado>
              ) : (
                <EtiquetaEstado tono="problema">Pendiente</EtiquetaEstado>
              )
            }
          />
          <Dato etiqueta="En el padrón desde" valor={fechaCorta(alumno.fecha_registro)} />
        </dl>

        {/* --- 3. Acciones: mismo ancho, apiladas y centradas en su columna --- */}
        {acciones && (
          <div className="grid content-center gap-2 p-6 [&>*]:w-full [&>*]:justify-center">{acciones}</div>
        )}
      </div>

      {(estadoDx === "con-dx" || estadoDx === "sin-dx") && antecedentes && (
        <SituacionRiesgo estado={estadoDx} antecedentes={antecedentes} puedeEditar={puedeEditarAntecedentes} />
      )}

      <PendientesFicha
        consentimientoPendiente={consentimientoVigente === false}
        riesgoSinDefinir={estadoDx === "sin-completar"}
        puedeEditarAntecedentes={puedeEditarAntecedentes}
        sinMatricula={!matricula}
        informesPorRevisar={informesPorRevisar}
      />

      {/* --- Datos de filiación editables, dentro del mismo bloque --- */}
      {children && <div className="border-t border-teal-600/15 dark:border-border-dark bg-surface dark:bg-surface-dark p-5">{children}</div>}
    </section>
  );
}

// 🆕 (sesión 2026-11-07) Etiqueta de estado (Vigente / Pendiente): antes era
// solo texto de color, que se confundía con un dato más de la cuadrícula.
function EtiquetaEstado({ tono, children }: { tono: "ok" | "problema"; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold ${
        tono === "ok"
          ? "bg-teal-600/10 text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
          : "bg-red-600/10 text-red-700 dark:bg-red-400/15 dark:text-red-300"
      }`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${tono === "ok" ? "bg-teal-500 dark:bg-teal-accent-dark" : "bg-red-500 dark:bg-red-300"}`} />
      {children}
    </span>
  );
}

// 🆕 (sesión 2026-11-07) "Pendiente en esta ficha": lo que falta para que la
// ficha esté completa o lo que espera una acción del psicólogo, cada uno con
// un enlace directo al bloque donde se resuelve. Antes estaba disperso: un
// "Pendiente" en rojo en la cuadrícula, una línea gris sobre la situación de
// riesgo y los informes retenidos solo dentro de "Pruebas aplicadas". El
// ámbar solo marca informes retenidos (resultado clínico real); un dato sin
// llenar no es una alerta clínica.
function PendientesFicha({
  consentimientoPendiente,
  riesgoSinDefinir,
  puedeEditarAntecedentes,
  sinMatricula,
  informesPorRevisar,
}: {
  consentimientoPendiente: boolean;
  riesgoSinDefinir: boolean;
  puedeEditarAntecedentes: boolean;
  sinMatricula: boolean;
  informesPorRevisar: number;
}) {
  const items: { icono: LucideIcon; texto: string; detalle: string; href: string; destacado?: boolean }[] = [];
  if (informesPorRevisar > 0) {
    items.push({
      icono: FileWarning,
      texto: informesPorRevisar === 1 ? "1 informe por revisar" : `${informesPorRevisar} informes por revisar`,
      detalle: "Retenido hasta tu revisión",
      href: "#pruebas-aplicadas",
      destacado: true,
    });
  }
  if (consentimientoPendiente) {
    items.push({ icono: FileSignature, texto: "Consentimiento del apoderado", detalle: "Necesario para evaluarlo", href: "#consentimiento-informado" });
  }
  if (riesgoSinDefinir && puedeEditarAntecedentes) {
    items.push({ icono: HelpCircle, texto: "Antecedentes clínicos externos", detalle: "Define la situación de riesgo", href: "#antecedentes-clinicos" });
  }
  if (sinMatricula) {
    items.push({ icono: GraduationCap, texto: "Matrícula académica", detalle: "Sin nivel, grado ni sección", href: "#matricula-academica" });
  }
  if (items.length === 0) return null;

  return (
    <div className="border-t border-teal-600/15 dark:border-border-dark px-5 py-3.5">
      <div className="flex flex-col gap-2.5 lg:flex-row lg:items-center">
        <p className="m-0 flex shrink-0 items-center gap-1.5 text-[12px] font-semibold uppercase tracking-wide text-ink/50 dark:text-ink-dark/50">
          <ListChecks size={14} aria-hidden="true" />
          Pendiente en esta ficha
        </p>
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
          {items.map((it) => (
            <li key={it.href}>
              <a
                href={it.href}
                className={`group inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${
                  it.destacado
                    ? "border-amber/50 bg-amber/10 hover:bg-amber/20 dark:border-amber/40"
                    : "border-border bg-surface hover:border-teal-400 hover:bg-mist dark:border-border-dark dark:bg-surface-dark dark:hover:bg-surface-raised-dark"
                }`}
              >
                <it.icono
                  size={15}
                  aria-hidden="true"
                  className={it.destacado ? "shrink-0 text-amber-700 dark:text-amber" : "shrink-0 text-ink/45 dark:text-ink-dark/50"}
                />
                <span className="leading-tight">
                  <span className="block text-[13px] font-semibold text-ink dark:text-ink-dark">{it.texto}</span>
                  <span className="block text-[11.5px] text-ink/50 dark:text-ink-dark/50">{it.detalle}</span>
                </span>
                <ArrowRight
                  size={14}
                  aria-hidden="true"
                  className="shrink-0 text-ink/30 transition-transform group-hover:translate-x-0.5 dark:text-ink-dark/40"
                />
              </a>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 🆕 Situación de riesgo (sesión 2026-10-31). No hay un botón "marcar en
// riesgo": el estado se DERIVA de los antecedentes clínicos externos que ya
// se llenan en la ficha — mismo criterio que el backend usa para el padrón y
// la estructura académica (crud._condicion_con_diagnostico):
// - "con-dx": terapia psicológica externa = Sí o atención psiquiátrica externa = Sí.
// - "sin-dx": ambas respondidas y ninguna es Sí.
// - "sin-completar": alguna sigue sin responder (NULL) y ninguna es Sí —
//   nunca se afirma "sin Dx" sobre algo que no se preguntó.
type EstadoDx = "con-dx" | "sin-dx" | "sin-completar";

export function estadoDiagnostico(a: PersonaAntecedentesClinicos | null | undefined): EstadoDx | null {
  if (!a) return null;
  const terapia = a.recibe_terapia_psicologica_externa;
  const psiquiatria = a.recibe_atencion_psiquiatrica_externa;
  if (terapia === true || psiquiatria === true) return "con-dx";
  if (terapia === false && psiquiatria === false) return "sin-dx";
  return "sin-completar";
}

function SituacionRiesgo({
  estado,
  antecedentes,
  puedeEditar,
}: {
  estado: EstadoDx;
  antecedentes: PersonaAntecedentesClinicos;
  puedeEditar: boolean;
}) {
  const enlace = (
    <a href="#antecedentes-clinicos" className="font-semibold underline underline-offset-2 hover:no-underline">
      {puedeEditar ? "Actualizar en Antecedentes clínicos externos" : "Ver Antecedentes clínicos externos"}
    </a>
  );

  if (estado === "con-dx") {
    const motivos: { etiqueta: string; detalle: string | null | undefined }[] = [];
    if (antecedentes.recibe_terapia_psicologica_externa) {
      motivos.push({ etiqueta: "Recibe terapia psicológica externa", detalle: antecedentes.detalle_terapia_psicologica_externa });
    }
    if (antecedentes.recibe_atencion_psiquiatrica_externa) {
      motivos.push({ etiqueta: "Recibe atención psiquiátrica externa", detalle: antecedentes.detalle_atencion_psiquiatrica_externa });
    }
    return (
      <div role="status" className="border-t border-amber/40 bg-amber/[0.08] px-6 py-4 shadow-[inset_4px_0_0_var(--color-amber)]">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber/20 text-amber-800 dark:text-amber">
            <Stethoscope size={17} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="m-0 font-display text-[15px] font-bold text-amber-800 dark:text-amber">Situación de riesgo: estudiante con diagnóstico</p>
            <ul className="m-0 mt-1.5 list-none p-0 space-y-1 text-[13px] text-ink/80 dark:text-ink-dark/80">
              {motivos.map((m) => (
                <li key={m.etiqueta}>
                  <span className="font-semibold">{m.etiqueta}</span>
                  {m.detalle ? <span className="text-ink/60 dark:text-ink-dark/60"> — {m.detalle}</span> : null}
                </li>
              ))}
              {antecedentes.diagnostico_reportado && (
                <li>
                  <span className="font-semibold">Diagnóstico reportado:</span>{" "}
                  <span className="text-ink/70 dark:text-ink-dark/70">{antecedentes.diagnostico_reportado}</span>
                </li>
              )}
            </ul>
            <p className="m-0 mt-2 text-[12px] text-ink/55 dark:text-ink-dark/55">
              Se marca automáticamente a partir de los antecedentes clínicos externos — aparece en amarillo en el Padrón y en la
              Estructura académica. {enlace}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // "sin-completar" ya no llega aquí: se muestra en PendientesFicha.
  return (
    <div className="border-t border-border dark:border-border-dark px-6 py-3">
      <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-ink/60 dark:text-ink-dark/60">
        <ShieldCheck size={15} aria-hidden="true" className="text-teal-600 dark:text-teal-accent-dark" />
        <span className="font-semibold text-ink/75 dark:text-ink-dark/75">Sin diagnóstico externo registrado</span>
        <span>No recibe terapia psicológica ni atención psiquiátrica externa.</span>
        {enlace}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------

type Tono = "ok" | "alerta" | "problema" | "neutro";
const CLASE_TONO: Record<Tono, string> = {
  ok: "text-teal-700 dark:text-teal-accent-dark",
  alerta: "text-amber-700 dark:text-amber",
  problema: "text-red-700 dark:text-red-300",
  neutro: "text-ink/50 dark:text-ink-dark/50",
};

function Indicador({
  titulo,
  icono: Icono,
  acento,
  valor,
  unidad,
  estado,
  tono,
}: {
  titulo: string;
  icono: LucideIcon;
  acento: Acento;
  valor: ReactNode;
  unidad?: string;
  estado: string;
  tono: Tono;
}) {
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-2 ${ACENTOS[acento].fondo}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="m-0 text-[12.5px] font-medium text-ink/65 dark:text-ink-dark/65">{titulo}</p>
        <span className={`flex h-7 w-7 items-center justify-center rounded-lg ${ACENTOS[acento].chipSolido}`}>
          <Icono size={14} aria-hidden="true" />
        </span>
      </div>
      <p className="m-0 flex items-baseline gap-1.5">
        <span className="font-display text-[28px] font-bold leading-none text-ink dark:text-ink-dark tabular-nums">{valor}</span>
        {unidad && <span className="text-[12px] text-ink/45 dark:text-ink-dark/45">{unidad}</span>}
      </p>
      <p className={`m-0 text-[12px] font-medium ${CLASE_TONO[tono]}`}>{estado}</p>
    </div>
  );
}

function proximaCita(citas: Cita[]): Cita | undefined {
  const ahora = Date.now();
  return citas
    .filter((c) => c.estado === "Programada" && new Date(c.fecha_hora).getTime() >= ahora)
    .sort((a, b) => (a.fecha_hora < b.fecha_hora ? -1 : 1))[0];
}

export function IndicadoresEstudiante({
  pruebas,
  seguimientos,
  citas,
}: {
  // null = no cargado / sin permiso: se muestra "—", nunca un 0 falso.
  pruebas: HistorialInformePersona[] | null;
  seguimientos: SesionSeguimiento[];
  citas: Cita[];
}) {
  const conAlerta = pruebas ? pruebas.filter((p) => p.es_alerta) : [];
  const retenidos = pruebas ? pruebas.filter((p) => !p.informe_liberado) : [];
  const ultimaPrueba = pruebas
    ?.map((p) => p.fecha_aplicacion)
    .filter((f): f is string => !!f)
    .sort()
    .slice(-1)[0];

  const sesionesOrdenadas = [...seguimientos].sort((a, b) => (a.fecha < b.fecha ? 1 : -1));
  const ultimaSesion = sesionesOrdenadas[0]?.fecha;

  const proxima = proximaCita(citas);

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Indicador
        titulo="Pruebas aplicadas"
        icono={ClipboardCheck}
        acento="azul"
        valor={pruebas ? pruebas.length : "—"}
        unidad={pruebas && pruebas.length === 1 ? "prueba" : "pruebas"}
        estado={
          !pruebas ? "Sin información" : retenidos.length > 0 ? `${retenidos.length} informe(s) por revisar` : ultimaPrueba ? `Última: ${fechaCorta(ultimaPrueba)}` : "Aún sin evaluar"
        }
        tono={!pruebas ? "neutro" : retenidos.length > 0 ? "alerta" : pruebas.length > 0 ? "ok" : "neutro"}
      />
      <Indicador
        titulo="Resultados en alerta"
        icono={AlertTriangle}
        acento="riesgo"
        valor={pruebas ? conAlerta.length : "—"}
        unidad="de alerta"
        estado={!pruebas ? "Sin información" : conAlerta.length > 0 ? "Requiere atención clínica" : "Sin indicadores de riesgo"}
        tono={!pruebas ? "neutro" : conAlerta.length > 0 ? "alerta" : "ok"}
      />
      <Indicador
        titulo="Sesiones de seguimiento"
        icono={HeartHandshake}
        acento="teal"
        valor={seguimientos.length}
        unidad={seguimientos.length === 1 ? "sesión" : "sesiones"}
        estado={ultimaSesion ? `Última: ${fechaCorta(ultimaSesion)}` : conAlerta.length > 0 ? "Sin seguimiento registrado" : "Ninguna todavía"}
        tono={ultimaSesion ? "ok" : conAlerta.length > 0 ? "alerta" : "neutro"}
      />
      <Indicador
        titulo="Próxima cita"
        icono={CalendarClock}
        acento="pizarra"
        valor={proxima ? new Date(proxima.fecha_hora).toLocaleDateString("es-PE", { day: "numeric", month: "short" }) : "—"}
        unidad={proxima ? new Date(proxima.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" }) : undefined}
        estado={proxima ? proxima.motivo : "Sin citas programadas"}
        tono={proxima ? "ok" : "neutro"}
      />
    </div>
  );
}

// Título de grupo de apartados — da la jerarquía de la ficha (Evaluación y
// seguimiento → Expediente → Datos del estudiante → Documentos).
export function TituloGrupoFicha({
  titulo,
  descripcion,
  acento,
  id,
}: {
  titulo: string;
  descripcion?: string;
  acento: Acento;
  /** 🆕 Ancla para el índice fijo de la ficha (components/educativo/IndiceFicha.tsx). */
  id?: string;
}) {
  return (
    <div id={id} className="flex scroll-mt-24 items-center gap-3 pt-2">
      <span aria-hidden="true" className={`h-6 w-1 rounded-full ${ACENTOS[acento].solido}`} />
      <div className="min-w-0">
        <h2 className="m-0 font-display text-[18px] font-bold text-teal-900 dark:text-ink-dark">{titulo}</h2>
        {descripcion && <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>}
      </div>
    </div>
  );
}
