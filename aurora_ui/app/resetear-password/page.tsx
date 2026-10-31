"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertCircle, ArrowLeft, Check, CheckCircle2, Eye, EyeOff, Link2Off, Loader2, Lock } from "lucide-react";
import { ApiError, resetearPassword } from "@/lib/api-client";
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

// Destino del enlace del correo de recuperación (backend/core/email_service.py
// arma `${FRONTEND_URL}/resetear-password?token=...`). El token se lee una
// vez y se quita de la barra de direcciones, para que no quede en el
// historial ni viaje como Referer a otro sitio.
const MINIMO = 8; // mismo mínimo que valida el backend (schemas.ResetearPasswordRequest)

const REQUISITOS = [
  { texto: `Al menos ${MINIMO} caracteres`, cumple: (p: string) => p.length >= MINIMO, obligatorio: true },
  { texto: "Mayúsculas y minúsculas", cumple: (p: string) => /[a-z]/.test(p) && /[A-Z]/.test(p), obligatorio: false },
  { texto: "Al menos un número", cumple: (p: string) => /\d/.test(p), obligatorio: false },
];

function NivelSeguridad({ password }: { password: string }) {
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

function CampoClave(props: {
  id: string;
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  visible: boolean;
  onAlternar: () => void;
  error?: string;
  autoFocus?: boolean;
  deshabilitado?: boolean;
}) {
  const { id, etiqueta, valor, onCambio, visible, onAlternar, error, autoFocus, deshabilitado } = props;
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
          autoComplete="new-password"
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

function FormularioResetear() {
  const parametros = useSearchParams();
  const [token] = useState(() => parametros.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [errores, setErrores] = useState<{ password?: string; confirmacion?: string }>({});
  const [mensajeError, setMensajeError] = useState("");
  const [enlaceInvalido, setEnlaceInvalido] = useState(!token);
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (token) window.history.replaceState(null, "", "/resetear-password");
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (guardando) return;
    setMensajeError("");
    const nuevos: typeof errores = {};
    if (password.length < MINIMO) nuevos.password = `La contraseña debe tener al menos ${MINIMO} caracteres.`;
    if (!confirmacion) nuevos.confirmacion = "Repite la nueva contraseña.";
    else if (confirmacion !== password) nuevos.confirmacion = "Las contraseñas no coinciden.";
    setErrores(nuevos);
    if (nuevos.password || nuevos.confirmacion) return;

    setGuardando(true);
    try {
      await resetearPassword(token, password);
      setListo(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 400) setEnlaceInvalido(true);
      else setMensajeError(error instanceof Error && error.message ? error.message : "No se pudo guardar la contraseña.");
    } finally {
      setGuardando(false);
    }
  };

  if (listo) {
    return (
      <MarcoAuth titulo="Contraseña actualizada" subtitulo="Ya puedes entrar con tu nueva contraseña.">
        <div className={CLASE_TARJETA_AUTH} role="status">
          <div className="flex flex-col items-center text-center">
            <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-7 w-7" aria-hidden />
            </span>
            <p className="text-sm text-ink/75 dark:text-ink-dark/75">
              Por seguridad, cerramos todas las sesiones que estaban abiertas con la contraseña anterior.
            </p>
            <Link href="/" className={`${CLASE_BOTON_AUTH} ${CLASE_BOTON_AUTH_NORMAL} mt-6`}>
              Ir a iniciar sesión
            </Link>
          </div>
        </div>
      </MarcoAuth>
    );
  }

  if (enlaceInvalido) {
    return (
      <MarcoAuth titulo="Enlace no válido" subtitulo="Este enlace de recuperación venció o ya se usó.">
        <div className={CLASE_TARJETA_AUTH} role="alert">
          <div className="flex flex-col items-center text-center">
            <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10 text-red-600 dark:text-red-400">
              <Link2Off className="h-7 w-7" aria-hidden />
            </span>
            <p className="text-sm text-ink/75 dark:text-ink-dark/75">
              Los enlaces duran 1 hora y sirven una sola vez. Si pediste varios, solo vale el más reciente que no hayas usado.
            </p>
            <Link href="/recuperar-password" className={`${CLASE_BOTON_AUTH} ${CLASE_BOTON_AUTH_NORMAL} mt-6`}>
              Pedir un enlace nuevo
            </Link>
            <Link href="/" className={`mt-4 inline-flex items-center gap-1.5 text-sm ${CLASE_ENLACE_AUTH}`}>
              <ArrowLeft className="h-4 w-4" aria-hidden /> Volver a iniciar sesión
            </Link>
          </div>
        </div>
      </MarcoAuth>
    );
  }

  return (
    <MarcoAuth titulo="Crea una nueva contraseña" subtitulo="Elige una contraseña que no hayas usado antes en AuroraSoft.">
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

          <CampoClave
            id="nueva"
            etiqueta="Nueva contraseña"
            valor={password}
            onCambio={(v) => {
              setPassword(v);
              if (errores.password) setErrores((p) => ({ ...p, password: undefined }));
            }}
            visible={verPassword}
            onAlternar={() => setVerPassword((v) => !v)}
            error={errores.password}
            autoFocus
            deshabilitado={guardando}
          />
          <NivelSeguridad password={password} />
          <CampoClave
            id="confirmacion"
            etiqueta="Repite la nueva contraseña"
            valor={confirmacion}
            onCambio={(v) => {
              setConfirmacion(v);
              if (errores.confirmacion) setErrores((p) => ({ ...p, confirmacion: undefined }));
            }}
            visible={verPassword}
            onAlternar={() => setVerPassword((v) => !v)}
            error={errores.confirmacion}
            deshabilitado={guardando}
          />

          <button type="submit" disabled={guardando} className={`${CLASE_BOTON_AUTH} ${CLASE_BOTON_AUTH_NORMAL}`}>
            {guardando ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Guardando…
              </>
            ) : (
              "Guardar nueva contraseña"
            )}
          </button>
        </form>
      </div>
    </MarcoAuth>
  );
}

export default function ResetearPasswordPage() {
  // useSearchParams() exige un límite de Suspense en el App Router.
  return (
    <Suspense fallback={<div className="min-h-screen bg-mist dark:bg-mist-dark" />}>
      <FormularioResetear />
    </Suspense>
  );
}
