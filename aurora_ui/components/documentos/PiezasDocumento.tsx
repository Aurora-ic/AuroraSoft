import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Check } from "lucide-react";
import { ACENTOS } from "@/lib/acentos";
import { Migas, type MigaItem } from "@/components/ui/Migas";

// 🆕 (sesión 2026-11-01) Piezas de las pantallas INTERNAS de Documentos
// (nuevo documento, constructor de plantilla, editor del documento), en el
// violeta de la sección y con el mismo lenguaje que la ficha del alumno:
// bloque tintado + tarjetas blancas encima. Antes cada una armaba su propio
// <h1> teal suelto con "← Documentos" duplicando las migas.

const VIOLETA = ACENTOS.violeta;

/** Cabecera de una pantalla interna: migas + ícono sólido + título +
 *  subtítulo + insignias de estado, y las acciones a la derecha. */
export function CabeceraInterna({
  migas,
  icono: Icono,
  titulo,
  subtitulo,
  insignias,
  acciones,
}: {
  migas: MigaItem[];
  icono: LucideIcon;
  titulo: string;
  subtitulo?: ReactNode;
  insignias?: ReactNode;
  acciones?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <Migas items={migas} sinMargen />
      <div className={`rounded-xl border px-4 py-3.5 sm:px-5 flex items-center justify-between gap-3 flex-wrap ${VIOLETA.fondo}`}>
        <div className="flex items-center gap-3 min-w-0">
          <span className={`hidden sm:flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${VIOLETA.chipSolido}`}>
            <Icono size={20} strokeWidth={2} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h1 className="m-0 font-display text-[21px] font-bold leading-tight text-ink dark:text-ink-dark break-words">{titulo}</h1>
            {(subtitulo || insignias) && (
              <div className="mt-1 flex items-center gap-2 flex-wrap text-[12.5px] text-ink/55 dark:text-ink-dark/55">
                {subtitulo}
                {insignias}
              </div>
            )}
          </div>
        </div>
        {acciones && <div className="flex items-center gap-2 flex-wrap">{acciones}</div>}
      </div>
    </div>
  );
}

/** Insignia de estado. "solida" = violeta lleno (activo/emitido);
 *  "contorno" = neutro (inactivo/borrador). */
export function Insignia({ children, variante = "contorno", icono: Icono }: { children: ReactNode; variante?: "solida" | "contorno" | "suave"; icono?: LucideIcon }) {
  const clase =
    variante === "solida"
      ? VIOLETA.chipSolido
      : variante === "suave"
      ? VIOLETA.chip
      : "border border-dashed border-ink/25 text-ink/60 dark:border-ink-dark/25 dark:text-ink-dark/60";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold whitespace-nowrap ${clase}`}>
      {Icono && <Icono size={11} aria-hidden="true" />}
      {children}
    </span>
  );
}

/** Paso numerado de un formulario: el número pasa a ✓ cuando el paso ya
 *  está completo, para que se vea de un vistazo qué falta. */
export function PasoFormulario({
  numero,
  titulo,
  descripcion,
  completo,
  children,
}: {
  numero: number;
  titulo: string;
  descripcion?: string;
  completo: boolean;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 sm:p-5">
      <header className="flex items-start gap-3 mb-3.5">
        <span
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold transition-colors ${
            completo ? VIOLETA.chipSolido : VIOLETA.chip
          }`}
          aria-hidden="true"
        >
          {completo ? <Check size={14} strokeWidth={3} /> : numero}
        </span>
        <div className="min-w-0">
          <h2 className="m-0 text-[14px] font-bold text-ink dark:text-ink-dark leading-tight">{titulo}</h2>
          {descripcion && <p className="m-0 mt-0.5 text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

/** Tarjeta de la columna lateral (resumen, emitir, versiones...). */
export function TarjetaLateral({
  icono: Icono,
  titulo,
  children,
  acciones,
}: {
  icono: LucideIcon;
  titulo: string;
  children: ReactNode;
  acciones?: ReactNode;
}) {
  return (
    <section className={`rounded-xl border overflow-hidden ${VIOLETA.fondoSuave}`}>
      <header className={`flex items-center justify-between gap-2 px-4 py-2.5 border-b ${VIOLETA.cabecera}`}>
        <h2 className="m-0 flex items-center gap-2 text-[13px] font-bold text-ink dark:text-ink-dark">
          <span className={`flex h-6 w-6 items-center justify-center rounded-md ${VIOLETA.chipSolido}`}>
            <Icono size={13} strokeWidth={2.2} aria-hidden="true" />
          </span>
          {titulo}
        </h2>
        {acciones}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

/** Barra de avance (secciones completas, pasos...). */
export function BarraAvance({ hechos, total, etiqueta }: { hechos: number; total: number; etiqueta: string }) {
  const pct = total === 0 ? 0 : Math.round((hechos / total) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-[12px] mb-1.5">
        <span className="font-semibold text-ink/70 dark:text-ink-dark/70">{etiqueta}</span>
        <span className={`font-bold ${VIOLETA.texto}`}>
          {hechos} de {total}
        </span>
      </div>
      <div className="h-2 rounded-full bg-border/70 dark:bg-border-dark overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-full rounded-full transition-all ${VIOLETA.solido}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Etiqueta + control, mismo estilo de formulario en las 3 pantallas. */
export function CampoFormulario({ etiqueta, ayuda, children, className = "" }: { etiqueta: string; ayuda?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">{etiqueta}</span>
      {children}
      {ayuda && <span className="text-[11.5px] text-ink/45 dark:text-ink-dark/45">{ayuda}</span>}
    </label>
  );
}
