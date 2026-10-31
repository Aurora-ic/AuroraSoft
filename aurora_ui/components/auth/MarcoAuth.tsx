"use client";

import Image from "next/image";
import { CheckCircle2, Moon, ShieldCheck, Sun } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { IlustracionLogin } from "@/components/auth/IlustracionLogin";

// Marco común de las pantallas sin sesión (login, "olvidé mi contraseña",
// nueva contraseña): panel de marca a la izquierda en pantallas anchas,
// formulario a la derecha, selector de tema y pie de privacidad. Cada
// pantalla solo aporta su título y su tarjeta.
const PUNTOS_PRODUCTO = [
  "Campañas con un enlace único por estudiante, sin cuentas que crear.",
  "Resultados interpretados con baremos y reglas clínicas.",
  "Los casos en riesgo los revisa un profesional antes de publicarse.",
];

type Props = {
  titulo: string;
  subtitulo: string;
  children: React.ReactNode;
  /** Contenido bajo la tarjeta (p. ej. "Volver a iniciar sesión"). */
  pie?: React.ReactNode;
};

export function MarcoAuth({ titulo, subtitulo, children, pie }: Props) {
  const { tema, alternarTema } = useTheme();

  return (
    <div className="flex min-h-screen bg-mist dark:bg-mist-dark">
      {/* ── Panel de marca (solo en pantallas anchas) ── */}
      <aside className="relative hidden w-[46%] max-w-[680px] flex-col justify-between overflow-hidden bg-gradient-to-br from-[#0F5A4F] via-[#0B3D34] to-[#072A24] p-10 text-white lg:flex xl:p-14">
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[#2FB49D]/20 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-[#5EE0C6]/10 blur-3xl" />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.07] [background-image:radial-gradient(#fff_1px,transparent_1px)] [background-size:22px_22px]"
        />

        <div className="relative">
          <p className="font-display text-lg font-semibold tracking-tight">AuroraSoft</p>
          <p className="text-xs text-white/60">Plataforma de Evaluación Psicométrica</p>
        </div>

        <div className="relative mx-auto w-full max-w-md">
          <IlustracionLogin className="w-full drop-shadow-[0_20px_40px_rgba(0,0,0,0.25)]" />
        </div>

        <div className="relative max-w-md">
          <h2 className="font-display text-2xl font-semibold leading-snug xl:text-[28px]">
            Evaluación psicométrica escolar, con criterio profesional.
          </h2>
          <ul className="mt-6 space-y-3">
            {PUNTOS_PRODUCTO.map((punto) => (
              <li key={punto} className="flex items-start gap-3 text-sm text-white/80">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#5EE0C6]" aria-hidden />
                {punto}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* ── Contenido ── */}
      <main className="relative flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
        <button
          type="button"
          onClick={alternarTema}
          aria-label={tema === "oscuro" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
          title={tema === "oscuro" ? "Modo claro" : "Modo oscuro"}
          className="absolute right-4 top-4 rounded-full border border-border bg-surface p-2.5 text-ink/60 shadow-sm transition hover:text-accion focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 dark:border-border-dark dark:bg-surface-dark dark:text-ink-dark/60 dark:hover:text-teal-accent-dark sm:right-6 sm:top-6"
        >
          {tema === "oscuro" ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
        </button>

        <div className="w-full max-w-[420px]">
          <div className="mb-8 flex flex-col items-center text-center">
            <Image src="/logo.png" alt="AuroraSoft" width={140} height={99} priority className="mb-5 h-16 w-auto" />
            <h1 className="font-display text-2xl font-semibold text-teal-900 dark:text-ink-dark">{titulo}</h1>
            <p className="mt-1.5 text-sm text-ink/55 dark:text-ink-dark/55">{subtitulo}</p>
          </div>

          {children}

          {pie && <div className="mt-5 text-center text-sm">{pie}</div>}

          <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-ink/45 dark:text-ink-dark/45">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
            Conexión protegida · Datos tratados conforme a la Ley N.° 29733
          </p>
        </div>
      </main>
    </div>
  );
}

// Clases compartidas por los formularios de estas pantallas.
export const CLASE_TARJETA_AUTH =
  "rounded-2xl border border-border bg-surface p-6 shadow-[0_8px_30px_rgba(11,61,52,0.08)] dark:border-border-dark dark:bg-surface-dark dark:shadow-none sm:p-8";
export const CLASE_INPUT_AUTH =
  "w-full rounded-xl border bg-surface py-3 pl-10 text-sm text-ink placeholder:text-ink/35 transition focus:outline-none focus:ring-2 disabled:opacity-60 dark:bg-surface-dark dark:text-ink-dark dark:placeholder:text-ink-dark/35";
export const CLASE_INPUT_AUTH_OK = "border-border focus:border-teal-400 focus:ring-teal-400/40 dark:border-border-dark";
export const CLASE_INPUT_AUTH_ERROR = "border-red-400 focus:ring-red-300 dark:border-red-400/70";
export const CLASE_BOTON_AUTH =
  "group flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-surface-dark";
export const CLASE_BOTON_AUTH_NORMAL =
  "bg-accion hover:bg-accion-hover disabled:cursor-not-allowed disabled:opacity-70 dark:bg-teal-accent-dark dark:text-mist-dark dark:hover:opacity-90";
export const CLASE_ENLACE_AUTH =
  "font-medium text-accion underline-offset-4 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 rounded dark:text-teal-accent-dark";
