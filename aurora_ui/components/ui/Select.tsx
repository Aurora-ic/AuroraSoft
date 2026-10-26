import type { SelectHTMLAttributes } from "react";

// Mismo criterio y misma cadena de clases que Input.tsx — ver su comentario.
export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 dark:focus:ring-teal-accent-dark ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}
