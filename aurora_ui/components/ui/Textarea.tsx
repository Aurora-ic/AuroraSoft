import type { TextareaHTMLAttributes } from "react";

// Mismo criterio y misma cadena de clases que Input.tsx/Select.tsx — ver su
// comentario. No había ningún <textarea> compartido todavía: los campos de
// texto largo (detalle de antecedentes clínicos, diagnóstico reportado...)
// se escribían con <input> de una sola línea o no existían en la UI.
export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`rounded-card border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 ${className}`}
      {...props}
    />
  );
}
