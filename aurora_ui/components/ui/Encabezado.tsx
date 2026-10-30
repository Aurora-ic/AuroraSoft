import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { ACENTOS, type Acento } from "@/lib/acentos";

// 🆕 Rediseño UI/UX (sesión 2026-10-30, a pedido del usuario: "formal,
// funcional, minimalista, llamativo, optimizando espacios") — cada pantalla
// de (educativo) armaba su propio <h1> + <p> con márgenes distintos
// (mb-1/mb-6, space-y-8, px-6 py-8 duplicando el padding que <main> ya
// pone). Dos variantes:
// - "destacado": la misma franja degradada del Inicio. 🆕 Desde la sesión
//   2026-10-30 es la de TODAS las secciones del Sidebar (a pedido del
//   usuario: "que sea más puntual en qué pestaña estás"), con el color de su
//   grupo y las acciones de la pantalla dentro de la franja — ver
//   claseBotonBanner abajo.
// - "simple": una sola fila compacta (icono + título + descripción corta +
//   acciones a la derecha), para las pantallas de trabajo.
export function EncabezadoPagina({
  icono: Icono,
  titulo,
  descripcion,
  acciones,
  variante = "simple",
  acento = "teal",
  children,
}: {
  icono: LucideIcon;
  titulo: string;
  descripcion?: ReactNode;
  acciones?: ReactNode;
  variante?: "simple" | "destacado";
  // 🆕 Color de identidad de la sección (ver lib/acentos.ts).
  acento?: Acento;
  // Contenido extra debajo del título (p. ej. chips de resumen en "destacado").
  children?: ReactNode;
}) {
  if (variante === "destacado") {
    return (
      // En oscuro el degradado pasa a neutro (un fondo saturado grande cansa
      // en modo oscuro); el color de la sección queda en el borde lateral.
      <div
        className={`bg-gradient-to-br ${ACENTOS[acento].degradado} dark:from-surface-raised-dark dark:to-surface-dark dark:border dark:border-border-dark dark:border-l-4 ${ACENTOS[acento].borde} rounded-2xl px-5 py-5 sm:px-6 flex items-center justify-between flex-wrap gap-4 shadow-sm`}
      >
        <div className="flex items-start gap-3.5 min-w-0">
          <span className={`hidden sm:flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white ${ACENTOS[acento].chipOscuro}`}>
            <Icono size={21} strokeWidth={2} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 className="m-0 font-display text-[24px] font-bold text-white dark:text-ink-dark leading-tight">{titulo}</h1>
            {descripcion && (
              <p className="m-0 mt-1 text-[13px] text-white/75 dark:text-ink-dark/60 max-w-xl">{descripcion}</p>
            )}
            {children}
          </div>
        </div>
        {acciones && <div className="flex items-center gap-2 flex-wrap">{acciones}</div>}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${ACENTOS[acento].chip}`}>
          <Icono size={19} strokeWidth={2} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="m-0 font-display text-[22px] font-bold text-teal-900 dark:text-ink-dark leading-tight">{titulo}</h1>
          {descripcion && <p className="m-0 mt-0.5 text-[12.5px] text-ink/55 dark:text-ink-dark/55">{descripcion}</p>}
        </div>
      </div>
      {acciones && <div className="flex items-center gap-2 flex-wrap">{acciones}</div>}
      {children}
    </div>
  );
}

// Tarjeta KPI compacta — número grande + etiqueta. Si recibe `onClick` se
// vuelve un filtro (botón con estado `activa`), mismo patrón que ya usaba
// el Padrón. `tono="riesgo"` es el ÚNICO uso cálido: resérvalo para un
// conteo de alerta clínica real (ver Badge.tsx), nunca para "pendientes".
export function TarjetaKpi({
  icono: Icono,
  etiqueta,
  valor,
  detalle,
  tono = "teal",
  activa = false,
  onClick,
}: {
  icono: LucideIcon;
  etiqueta: string;
  valor: ReactNode;
  detalle?: ReactNode;
  // Acento de sección (lib/acentos.ts) o "neutro". "riesgo" = ámbar,
  // SOLO para conteos de alerta clínica real.
  tono?: Acento | "neutro";
  activa?: boolean;
  onClick?: () => void;
}) {
  const Elemento = onClick ? "button" : "div";
  const claseIcono =
    tono === "neutro" ? "bg-border/70 text-ink/55 dark:bg-border-dark dark:text-ink-dark/60" : ACENTOS[tono].chip;
  return (
    <Elemento
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-pressed={onClick ? activa : undefined}
      className={`text-left bg-surface dark:bg-surface-dark border rounded-xl px-4 py-3.5 flex items-center gap-3 transition-colors ${
        activa
          ? "border-teal-600 ring-1 ring-teal-600/30 dark:border-teal-accent-dark dark:ring-teal-accent-dark/30"
          : "border-border dark:border-border-dark"
      } ${onClick ? "hover:border-teal-400 dark:hover:border-teal-accent-dark cursor-pointer" : ""}`}
    >
      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${claseIcono}`}>
        <Icono size={16} strokeWidth={2} aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block font-display text-[22px] font-bold leading-none text-ink dark:text-ink-dark">{valor}</span>
        <span className="block mt-1 text-[11.5px] font-medium text-ink/55 dark:text-ink-dark/55 truncate">{etiqueta}</span>
        {detalle && <span className="block text-[11px] text-ink/40 dark:text-ink-dark/40 truncate">{detalle}</span>}
      </span>
    </Elemento>
  );
}

// Control segmentado (pastillas) — reemplaza un <select> de 2–4 opciones
// cortas para que la elección se vea de un vistazo. role="radiogroup"
// para lectores de pantalla.
export function ControlSegmentado<T extends string>({
  opciones,
  valor,
  onCambiar,
  etiqueta,
  className = "",
}: {
  opciones: { valor: T; etiqueta: string; icono?: LucideIcon }[];
  valor: T;
  onCambiar: (valor: T) => void;
  etiqueta: string;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={etiqueta}
      className={`inline-flex items-center gap-0.5 rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-1 ${className}`}
    >
      {opciones.map((o) => {
        const activo = o.valor === valor;
        const Icono = o.icono;
        return (
          <button
            key={o.valor}
            type="button"
            role="radio"
            aria-checked={activo}
            onClick={() => onCambiar(o.valor)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold whitespace-nowrap transition-colors ${
              activo
                ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                : "text-ink/60 hover:text-ink hover:bg-mist dark:text-ink-dark/60 dark:hover:text-ink-dark dark:hover:bg-surface-raised-dark"
            }`}
          >
            {Icono && <Icono size={13} aria-hidden="true" />}
            {o.etiqueta}
          </button>
        );
      })}
    </div>
  );
}

// 🆕 Botones/enlaces DENTRO de la franja "destacado" — el primario de
// siempre (teal sobre teal) se perdía sobre el degradado. Primario: blanco
// sólido; secundario: translúcido con borde. En oscuro vuelven al estilo
// normal de la app (la franja es neutra ahí).
export function claseBotonBanner(variante: "primario" | "secundario" = "primario", className = ""): string {
  const base =
    "inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-[13px] font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const porVariante =
    variante === "primario"
      ? "bg-white text-teal-900 hover:bg-white/90 shadow-sm dark:bg-teal-accent-dark dark:text-mist-dark dark:hover:opacity-90"
      : "bg-white/10 text-white border border-white/30 hover:bg-white/20 dark:bg-surface-dark dark:text-ink-dark dark:border-border-dark dark:hover:bg-surface-raised-dark";
  return `${base} ${porVariante} ${className}`.trim();
}

// Pastilla informativa dentro de la franja (contador, estado de licencia...).
export function PastillaBanner({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-xl bg-white/12 px-3 py-1.5 text-[12px] font-medium text-white ring-1 ring-white/20 dark:bg-surface-dark dark:text-ink-dark dark:ring-border-dark ${className}`}
    >
      {children}
    </span>
  );
}
