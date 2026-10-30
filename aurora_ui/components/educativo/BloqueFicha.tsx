import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

// 🆕 Piezas visuales de la ficha del alumno (sesión 2026-10-29, a pedido del
// usuario: "unos marcos/bordes, que no se vea espacioso, algo profesional").
// Antes cada sub-bloque de "Datos de filiación" era un <h3> en mayúsculas +
// un grid suelto de <Campo>, separados solo por una línea — mucho aire y
// ninguna estructura visual. Ahora cada sub-bloque es una tarjeta con
// cabecera (icono + título + acciones) y los datos van en celdas con borde.
// Solo presentación: ningún dato ni endpoint cambia.

export function BloqueFicha({
  icono: Icono,
  titulo,
  descripcion,
  acciones,
  children,
  className = "",
}: {
  icono: LucideIcon;
  titulo: string;
  descripcion?: string;
  acciones?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden ${className}`}
    >
      <header className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 bg-mist/60 dark:bg-surface-raised-dark border-b border-border dark:border-border-dark">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
            <Icono size={16} strokeWidth={2} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-teal-900 dark:text-ink-dark leading-tight">{titulo}</h3>
            {descripcion && <p className="text-[11.5px] text-ink/50 dark:text-ink-dark/50 leading-tight mt-0.5">{descripcion}</p>}
          </div>
        </div>
        {acciones && <div className="flex items-center gap-1.5">{acciones}</div>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

// Celdas con borde: el truco `gap-px` + fondo `bg-border` dibuja las líneas
// divisorias entre celdas sin bordes dobles. `columnas` es el máximo en
// pantallas anchas; en celular siempre es 1 columna.
export function CuadriculaDatos({ children, columnas = 2 }: { children: ReactNode; columnas?: 2 | 3 }) {
  return (
    <dl
      className={`grid grid-cols-1 ${columnas === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"} gap-px overflow-hidden rounded-lg border border-border dark:border-border-dark bg-border dark:bg-border-dark text-sm`}
    >
      {children}
    </dl>
  );
}

export function DatoFicha({
  etiqueta,
  valor,
  ancho = false,
  icono: Icono,
}: {
  etiqueta: string;
  valor?: ReactNode;
  // Ocupa toda la fila (p. ej. un texto largo como "Diagnóstico reportado").
  ancho?: boolean;
  icono?: LucideIcon;
}) {
  const vacio = valor === null || valor === undefined || valor === "";
  return (
    <div className={`bg-surface dark:bg-surface-dark px-3.5 py-2.5 ${ancho ? "sm:col-span-full" : ""}`}>
      <dt className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
        {Icono && <Icono size={12} aria-hidden="true" />}
        {etiqueta}
      </dt>
      <dd className={`mt-0.5 break-words ${vacio ? "text-ink/30 dark:text-ink-dark/30" : "font-medium text-ink dark:text-ink-dark"}`}>
        {vacio ? "—" : valor}
      </dd>
    </div>
  );
}

// Acción compacta de la cabecera de un bloque ("Editar", "Historial"...) —
// antes eran botones primarios grandes que competían con el título.
export function BotonAccionFicha({
  icono: Icono,
  children,
  activo = false,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { icono?: LucideIcon; activo?: boolean }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
        activo
          ? "border-teal-600 bg-teal-600 text-white dark:border-teal-accent-dark dark:bg-teal-accent-dark dark:text-mist-dark"
          : "border-border bg-surface text-ink/70 hover:border-teal-400 hover:text-teal-700 dark:border-border-dark dark:bg-surface-dark dark:text-ink-dark/70 dark:hover:text-teal-accent-dark"
      } ${className}`}
      {...props}
    >
      {Icono && <Icono size={13} aria-hidden="true" />}
      {children}
    </button>
  );
}
