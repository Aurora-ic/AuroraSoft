"use client";

import type { RefObject } from "react";
import { KeyRound, RefreshCw } from "lucide-react";
import type { CaptchaLogin } from "@/lib/api-client";

// Bloque del captcha del login (backend/core/captcha.py). Solo muestra la
// imagen que manda el backend y recoge lo que escribe el usuario: el texto
// correcto nunca llega al navegador, así que aquí no hay nada que validar
// salvo el largo.
export const LONGITUD_CAPTCHA = 5;

type Props = {
  captcha: CaptchaLogin | null;
  cargando: boolean;
  errorCarga: string;
  valor: string;
  onCambio: (valor: string) => void;
  onRecargar: () => void;
  error?: string;
  deshabilitado?: boolean;
  inputRef?: RefObject<HTMLInputElement | null>;
};

export function CampoCaptcha({ captcha, cargando, errorCarga, valor, onCambio, onRecargar, error, deshabilitado, inputRef }: Props) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="captcha" className="text-sm font-medium text-ink/75 dark:text-ink-dark/75">
        Código de verificación
      </label>

      <div className="flex items-stretch gap-2">
        <div
          className="relative flex h-[70px] flex-1 items-center justify-center overflow-hidden rounded-xl border border-border bg-[#F7FAF9] dark:border-border-dark"
          aria-live="polite"
        >
          {cargando ? (
            <span className="h-full w-full animate-pulse bg-mist dark:bg-surface-raised-dark" aria-label="Cargando código" />
          ) : captcha?.imagen ? (
            // eslint-disable-next-line @next/next/no-img-element -- data URL generado por el backend, no hay nada que optimizar
            <img
              src={captcha.imagen}
              alt="Código de verificación: caracteres distorsionados que debes escribir abajo"
              width={220}
              height={70}
              className="h-full w-auto select-none"
              draggable={false}
            />
          ) : (
            <span className="px-3 text-center text-xs text-red-700">{errorCarga || "No se pudo cargar el código."}</span>
          )}
        </div>
        <button
          type="button"
          onClick={onRecargar}
          disabled={cargando || deshabilitado}
          title="Generar otro código"
          aria-label="Generar otro código de verificación"
          className="flex w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-surface text-ink/60 transition hover:border-teal-400 hover:text-accion focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 disabled:opacity-40 dark:border-border-dark dark:bg-surface-dark dark:text-ink-dark/60 dark:hover:text-teal-accent-dark"
        >
          <RefreshCw className={`h-4.5 w-4.5 ${cargando ? "animate-spin" : ""}`} aria-hidden />
        </button>
      </div>

      <div className="relative">
        <KeyRound className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35 dark:text-ink-dark/40" aria-hidden />
        <input
          ref={inputRef}
          id="captcha"
          name="captcha"
          type="text"
          inputMode="text"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={LONGITUD_CAPTCHA}
          value={valor}
          onChange={(e) => onCambio(e.target.value.replace(/\s/g, "").toUpperCase())}
          disabled={deshabilitado || cargando || !captcha?.imagen}
          placeholder="Escribe los 5 caracteres"
          aria-invalid={!!error}
          aria-describedby={error ? "captcha-error" : "captcha-ayuda"}
          className={`w-full rounded-xl border bg-surface py-3 pl-10 pr-3.5 font-mono text-sm uppercase tracking-[0.3em] text-ink placeholder:font-body placeholder:normal-case placeholder:tracking-normal placeholder:text-ink/35 transition focus:outline-none focus:ring-2 disabled:opacity-60 dark:bg-surface-dark dark:text-ink-dark dark:placeholder:text-ink-dark/35 ${
            error
              ? "border-red-400 focus:ring-red-300 dark:border-red-400/70"
              : "border-border focus:border-teal-400 focus:ring-teal-400/40 dark:border-border-dark"
          }`}
        />
      </div>
      {error ? (
        <p id="captcha-error" className="text-xs text-red-700 dark:text-red-300">{error}</p>
      ) : (
        <p id="captcha-ayuda" className="text-xs text-ink/45 dark:text-ink-dark/45">
          No distingue mayúsculas de minúsculas. ¿No se lee bien? Pide otro código.
        </p>
      )}
    </div>
  );
}
