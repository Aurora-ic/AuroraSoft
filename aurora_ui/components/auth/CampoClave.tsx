"use client";

import { Check, Eye, EyeOff, Lock } from "lucide-react";
import { CLASE_INPUT_AUTH, CLASE_INPUT_AUTH_ERROR, CLASE_INPUT_AUTH_OK } from "@/components/auth/MarcoAuth";

// Campos de contraseña compartidos por "Crea una nueva contraseña" (enlace
// del correo) y "Cambiar contraseña" (desde la sesión). Las reglas son las
// mismas que valida el backend (modulos/auth/schemas.validar_password_nueva).
export const MINIMO = 8;
// bcrypt solo usa los primeros 72 bytes: lo que sigue no protegería nada.
const MAXIMO_BYTES = 72;

/** Mensaje de error de una contraseña nueva, o undefined si es válida. */
export function errorPasswordNueva(p: string): string | undefined {
  if (p.length < MINIMO) return `La contraseña debe tener al menos ${MINIMO} caracteres.`;
  if (new TextEncoder().encode(p).length > MAXIMO_BYTES) return "La contraseña es demasiado larga (máximo 72 caracteres sin tildes).";
  if (!p.trim()) return "La contraseña no puede ser solo espacios.";
  return undefined;
}

const REQUISITOS = [
  { texto: `Al menos ${MINIMO} caracteres`, cumple: (p: string) => p.length >= MINIMO, obligatorio: true },
  { texto: "Mayúsculas y minúsculas", cumple: (p: string) => /[a-z]/.test(p) && /[A-Z]/.test(p), obligatorio: false },
  { texto: "Al menos un número", cumple: (p: string) => /\d/.test(p), obligatorio: false },
];

export function NivelSeguridad({ password }: { password: string }) {
  const puntos = REQUISITOS.filter((r) => r.cumple(password)).length + (password.length >= 12 ? 1 : 0);
  const niveles = [
    { texto: "Muy débil", color: "bg-red-500" },
    { texto: "Débil", color: "bg-red-500" },
    { texto: "Aceptable", color: "bg-amber-500" },
    { texto: "Buena", color: "bg-emerald-500" },
    { texto: "Muy buena", color: "bg-emerald-600" },
  ];
  const nivel = niveles[password ? puntos : 0];
  return (
    <div className="space-y-2" aria-live="polite">
      <div className="flex gap-1.5" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-1.5 flex-1 rounded-full ${password && puntos >= i ? nivel.color : "bg-border dark:bg-border-dark"}`} />
        ))}
      </div>
      {password && <p className="text-xs text-ink/55 dark:text-ink-dark/55">Seguridad: {nivel.texto}</p>}
      <ul className="space-y-1">
        {REQUISITOS.map((r) => {
          const ok = r.cumple(password);
          return (
            <li key={r.texto} className={`flex items-center gap-2 text-xs ${ok ? "text-emerald-700 dark:text-emerald-400" : "text-ink/50 dark:text-ink-dark/50"}`}>
              <Check className={`h-3.5 w-3.5 ${ok ? "opacity-100" : "opacity-30"}`} aria-hidden />
              {r.texto}
              {!r.obligatorio && <span className="text-ink/35 dark:text-ink-dark/35">(recomendado)</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function CampoClave(props: {
  id: string;
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  visible: boolean;
  onAlternar: () => void;
  error?: string;
  autoFocus?: boolean;
  deshabilitado?: boolean;
  autoComplete?: string;
}) {
  const { id, etiqueta, valor, onCambio, visible, onAlternar, error, autoFocus, deshabilitado, autoComplete = "new-password" } = props;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink/75 dark:text-ink-dark/75">
        {etiqueta}
      </label>
      <div className="relative">
        <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35 dark:text-ink-dark/40" aria-hidden />
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          autoFocus={autoFocus}
          value={valor}
          onChange={(e) => onCambio(e.target.value)}
          disabled={deshabilitado}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          className={`${CLASE_INPUT_AUTH} pr-11 ${error ? CLASE_INPUT_AUTH_ERROR : CLASE_INPUT_AUTH_OK}`}
        />
        <button
          type="button"
          onClick={onAlternar}
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          aria-pressed={visible}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-2 text-ink/45 transition hover:bg-mist hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 dark:text-ink-dark/50 dark:hover:bg-surface-raised-dark dark:hover:text-ink-dark"
        >
          {visible ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} className="text-xs text-red-700 dark:text-red-300">{error}</p>
      )}
    </div>
  );
}

