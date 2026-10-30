import type { HTMLAttributes, ThHTMLAttributes } from "react";

// Fase 6 del plan de remodelación — <thead className="bg-mist/70"> + <th
// className="text-xs font-semibold uppercase tracking-wide text-ink/50">
// se reescribió igual en estudiantes/page.tsx, estudiantes/importar/page.tsx
// y el dashboard de campaña, cada uno con su propio padding (px-5 py-3,
// px-4 py-2.5, px-2 py-1...). En vez de forzar un padding único (que
// rompería el layout más compacto del dashboard), estos dos sub-componentes
// comparten solo las clases que SÍ son idénticas en los tres sitios y dejan
// el padding como className adicional — igual criterio que Input/Select.
//
// Se adopta en código NUEVO primero; el código ya escrito (los 3+ sitios de
// arriba) se migra después, archivo por archivo, verificando visualmente
// que el padding de cada uno no cambió.
export function TheadFila({ className = "", children, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={`bg-mist/70 dark:bg-surface-raised-dark text-left ${className}`} {...props}>
      {children}
    </tr>
  );
}

export function Th({ className = "", children, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={`text-xs font-semibold uppercase tracking-wide text-ink/50 dark:text-ink-dark/50 ${className}`} {...props}>
      {children}
    </th>
  );
}
