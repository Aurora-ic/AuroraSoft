"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2, Mail, MailCheck } from "lucide-react";
import { solicitarRecuperacion } from "@/lib/api-client";
import {
  CLASE_BOTON_AUTH,
  CLASE_BOTON_AUTH_NORMAL,
  CLASE_ENLACE_AUTH,
  CLASE_INPUT_AUTH,
  CLASE_INPUT_AUTH_ERROR,
  CLASE_INPUT_AUTH_OK,
  CLASE_TARJETA_AUTH,
  MarcoAuth,
} from "@/components/auth/MarcoAuth";

// "Olvidé mi contraseña": pide el enlace al backend. La respuesta es la misma
// exista o no la cuenta (no se delata qué correos están registrados), y el
// correo solo se envía a una cuenta superadmin — las demás cuentas las
// restablece un administrador.
export default function RecuperarPasswordPage() {
  const [email, setEmail] = useState("");
  const [errorCampo, setErrorCampo] = useState("");
  const [mensajeError, setMensajeError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    setMensajeError("");
    const limpio = email.trim();
    if (!limpio) return setErrorCampo("Ingresa tu correo electrónico.");
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(limpio)) return setErrorCampo("El correo no tiene un formato válido.");

    setEnviando(true);
    try {
      await solicitarRecuperacion(limpio);
      setEnviado(true);
    } catch (error) {
      setMensajeError(error instanceof Error && error.message ? error.message : "No se pudo enviar la solicitud.");
    } finally {
      setEnviando(false);
    }
  };

  const volver = (
    <Link href="/" className={`inline-flex items-center gap-1.5 ${CLASE_ENLACE_AUTH}`}>
      <ArrowLeft className="h-4 w-4" aria-hidden /> Volver a iniciar sesión
    </Link>
  );

  if (enviado) {
    return (
      <MarcoAuth titulo="Revisa tu correo" subtitulo="Te enviamos las instrucciones si la cuenta corresponde." pie={volver}>
        <div className={CLASE_TARJETA_AUTH} role="status">
          <div className="flex flex-col items-center text-center">
            <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-teal-400/15 text-accion dark:text-teal-accent-dark">
              <MailCheck className="h-7 w-7" aria-hidden />
            </span>
            <p className="text-sm text-ink/80 dark:text-ink-dark/80">
              Si <strong className="font-semibold text-ink dark:text-ink-dark">{email.trim()}</strong> es la cuenta de
              administración de AuroraSoft, en unos minutos recibirás un enlace para crear una nueva contraseña.
            </p>
            <ul className="mt-5 w-full space-y-2 rounded-xl bg-mist p-4 text-left text-xs text-ink/60 dark:bg-surface-raised-dark dark:text-ink-dark/60">
              <li>• El enlace vence en 1 hora y sirve una sola vez.</li>
              <li>• Si no lo ves, revisa la carpeta de spam o correo no deseado.</li>
              <li>• ¿Eres psicólogo o personal del colegio? Pide al administrador de tu institución que restablezca tu contraseña.</li>
            </ul>
            <button
              type="button"
              onClick={() => setEnviado(false)}
              className={`mt-5 text-sm ${CLASE_ENLACE_AUTH}`}
            >
              Enviar a otro correo
            </button>
          </div>
        </div>
      </MarcoAuth>
    );
  }

  return (
    <MarcoAuth
      titulo="¿Olvidaste tu contraseña?"
      subtitulo="Escribe el correo de tu cuenta y te enviaremos un enlace para crear una nueva."
      pie={volver}
    >
      <div className={CLASE_TARJETA_AUTH}>
        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {mensajeError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-950/40 dark:text-red-200"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{mensajeError}</span>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-ink/75 dark:text-ink-dark/75">
              Correo electrónico
            </label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35 dark:text-ink-dark/40" aria-hidden />
              <input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (errorCampo) setErrorCampo("");
                }}
                disabled={enviando}
                placeholder="usuario@colegio.com"
                aria-invalid={!!errorCampo}
                aria-describedby={errorCampo ? "email-error" : "email-ayuda"}
                className={`${CLASE_INPUT_AUTH} pr-3.5 ${errorCampo ? CLASE_INPUT_AUTH_ERROR : CLASE_INPUT_AUTH_OK}`}
              />
            </div>
            {errorCampo ? (
              <p id="email-error" className="text-xs text-red-700 dark:text-red-300">{errorCampo}</p>
            ) : (
              <p id="email-ayuda" className="text-xs text-ink/45 dark:text-ink-dark/45">
                La recuperación por correo está disponible para la cuenta de administración de AuroraSoft.
              </p>
            )}
          </div>

          <button type="submit" disabled={enviando} className={`${CLASE_BOTON_AUTH} ${CLASE_BOTON_AUTH_NORMAL}`}>
            {enviando ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Enviando…
              </>
            ) : (
              "Enviar enlace de recuperación"
            )}
          </button>
        </form>
      </div>
    </MarcoAuth>
  );
}
