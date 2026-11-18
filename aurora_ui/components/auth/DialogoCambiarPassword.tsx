"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, KeyRound, Loader2 } from "lucide-react";
import { ApiError, cambiarPassword } from "@/lib/api-client";
import { CampoClave, errorPasswordNueva, NivelSeguridad } from "@/components/auth/CampoClave";

// 🆕 (2026-11-15) "Cambiar contraseña" desde la sesión, para cualquier rol.
// Pide la actual (si alguien encuentra la sesión abierta no puede quedarse
// con la cuenta). Al guardar, el backend cierra las demás sesiones abiertas
// (otro navegador, otra PC) y deja viva esta; además avisa por correo.
export function DialogoCambiarPassword({ onCerrar }: { onCerrar: () => void }) {
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [ver, setVer] = useState(false);
  const [errores, setErrores] = useState<{ actual?: string; nueva?: string; confirmacion?: string }>({});
  const [mensajeError, setMensajeError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);
  // Al cerrar, el foco vuelve al botón que abrió el diálogo.
  useEffect(() => {
    const anterior = document.activeElement as HTMLElement | null;
    return () => anterior?.focus?.();
  }, []);

  useEffect(() => {
    function teclas(e: KeyboardEvent) {
      if (e.key === "Escape" && !guardando) {
        e.preventDefault();
        onCerrar();
      }
    }
    window.addEventListener("keydown", teclas);
    return () => window.removeEventListener("keydown", teclas);
  }, [onCerrar, guardando]);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (guardando) return;
    setMensajeError("");
    const nuevos: typeof errores = {};
    if (!actual) nuevos.actual = "Escribe tu contraseña actual.";
    nuevos.nueva = errorPasswordNueva(nueva);
    if (!nuevos.nueva && nueva === actual) nuevos.nueva = "La nueva contraseña debe ser distinta de la actual.";
    if (!confirmacion) nuevos.confirmacion = "Repite la nueva contraseña.";
    else if (confirmacion !== nueva) nuevos.confirmacion = "Las contraseñas no coinciden.";
    setErrores(nuevos);
    if (nuevos.actual || nuevos.nueva || nuevos.confirmacion) return;

    setGuardando(true);
    try {
      await cambiarPassword(actual, nueva);
      setListo(true);
    } catch (error) {
      const texto = error instanceof Error && error.message ? error.message : "No se pudo cambiar la contraseña.";
      if (error instanceof ApiError && error.status === 400 && /actual/i.test(texto) && /no es correcta/i.test(texto)) {
        setErrores({ actual: texto });
      } else if (error instanceof ApiError && error.status === 429) {
        setMensajeError("Demasiados intentos. Espera un minuto antes de volver a intentarlo.");
      } else {
        setMensajeError(texto);
      }
    } finally {
      setGuardando(false);
    }
  };

  // Portal: el botón vive en la barra lateral, que en celular es un cajón
  // con `transform`; un `fixed` dentro de ella quedaría encerrado en la barra.
  return createPortal(
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-ink/45" aria-hidden="true" onClick={() => !guardando && onCerrar()} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-cambiar-password"
        className="relative max-h-[calc(100vh-2rem)] w-full max-w-md overflow-y-auto rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-6 shadow-xl"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
            {listo ? <CheckCircle2 size={19} aria-hidden="true" /> : <KeyRound size={19} aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <h2 id="titulo-cambiar-password" className="font-display text-[17px] font-semibold text-ink dark:text-ink-dark">
              {listo ? "Contraseña actualizada" : "Cambiar contraseña"}
            </h2>
            <p className="mt-1 text-sm leading-relaxed text-ink/65 dark:text-ink-dark/65">
              {listo
                ? "Desde ahora entras con la nueva. Cerramos las demás sesiones que tenías abiertas en otros navegadores, y te enviamos un aviso a tu correo."
                : "Por seguridad te pedimos la actual. Al guardar se cerrarán tus sesiones abiertas en otros navegadores; esta sigue activa."}
            </p>
          </div>
        </div>

        {listo ? (
          <div className="mt-6 flex justify-end">
            <button
              type="button"
              autoFocus
              onClick={onCerrar}
              className="rounded-card bg-accion px-4 py-2 text-sm font-semibold text-white hover:bg-accion-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 dark:bg-teal-accent-dark dark:text-mist-dark"
            >
              Listo
            </button>
          </div>
        ) : (
          <form onSubmit={guardar} noValidate className="mt-5 space-y-4">
            {mensajeError && (
              <div
                role="alert"
                className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-950/40 dark:text-red-200"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>{mensajeError}</span>
              </div>
            )}
            <CampoClave
              id="password-actual"
              etiqueta="Contraseña actual"
              valor={actual}
              onCambio={(v) => {
                setActual(v);
                if (errores.actual) setErrores((p) => ({ ...p, actual: undefined }));
              }}
              visible={ver}
              onAlternar={() => setVer((v) => !v)}
              error={errores.actual}
              autoFocus
              autoComplete="current-password"
              deshabilitado={guardando}
            />
            <CampoClave
              id="password-nueva"
              etiqueta="Nueva contraseña"
              valor={nueva}
              onCambio={(v) => {
                setNueva(v);
                if (errores.nueva) setErrores((p) => ({ ...p, nueva: undefined }));
              }}
              visible={ver}
              onAlternar={() => setVer((v) => !v)}
              error={errores.nueva}
              deshabilitado={guardando}
            />
            <NivelSeguridad password={nueva} />
            <CampoClave
              id="password-confirmacion"
              etiqueta="Repite la nueva contraseña"
              valor={confirmacion}
              onCambio={(v) => {
                setConfirmacion(v);
                if (errores.confirmacion) setErrores((p) => ({ ...p, confirmacion: undefined }));
              }}
              visible={ver}
              onAlternar={() => setVer((v) => !v)}
              error={errores.confirmacion}
              deshabilitado={guardando}
            />
            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={onCerrar}
                disabled={guardando}
                className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-4 py-2 text-sm font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={guardando}
                className="inline-flex items-center justify-center gap-2 rounded-card bg-accion px-4 py-2 text-sm font-semibold text-white hover:bg-accion-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 focus-visible:ring-offset-2 disabled:opacity-60 dark:bg-teal-accent-dark dark:text-mist-dark"
              >
                {guardando ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Guardando…
                  </>
                ) : (
                  "Guardar contraseña"
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>,
    document.body,
  );
}
