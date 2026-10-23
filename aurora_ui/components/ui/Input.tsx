import type { InputHTMLAttributes } from "react";

// Fase 6 del plan de remodelación — la cadena de clases
// "rounded-card border border-border px-3 py-2 text-sm focus:outline-none
// focus:ring-2 focus:ring-teal-400" está pegada a mano en 50+ <input>/
// <select> de este proyecto (ver también Select.tsx). Envolver <input> una
// vez no cambia ningún comportamiento ni estilo, solo deja de repetir la
// cadena — se adopta en código NUEVO primero; el código ya escrito se
// migra después, archivo por archivo, verificando visualmente.
export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`rounded-card border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400 ${className}`}
      {...props}
    />
  );
}
