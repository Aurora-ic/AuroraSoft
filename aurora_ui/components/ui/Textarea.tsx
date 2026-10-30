import type { ComponentProps } from "react";

// Mismo criterio y misma cadena de clases que Input.tsx/Select.tsx — ver su
// comentario. No había ningún <textarea> compartido todavía: los campos de
// texto largo (detalle de antecedentes clínicos, diagnóstico reportado...)
// se escribían con <input> de una sola línea o no existían en la UI.
// ComponentProps<"textarea"> (no TextareaHTMLAttributes) para que `ref` pase
// tal cual — React 19 lo trata como una prop más.
export function Textarea({ className = "", ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={`rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 dark:focus:ring-teal-accent-dark ${className}`}
      {...props}
    />
  );
}
