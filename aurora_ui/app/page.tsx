"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, CheckCircle2, Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError, obtenerCaptcha, type CaptchaLogin } from "@/lib/api-client";
import { CampoCaptcha, LONGITUD_CAPTCHA } from "@/components/auth/CampoCaptcha";
import {
  CLASE_BOTON_AUTH,
  CLASE_BOTON_AUTH_NORMAL,
  CLASE_ENLACE_AUTH,
  CLASE_INPUT_AUTH as CLASE_INPUT,
  CLASE_INPUT_AUTH_ERROR as CLASE_INPUT_ERROR,
  CLASE_INPUT_AUTH_OK as CLASE_INPUT_OK,
  CLASE_TARJETA_AUTH,
  MarcoAuth,
} from "@/components/auth/MarcoAuth";

type Estado = "inactivo" | "cargando" | "exito";
type ErroresCampo = { usuario?: string; password?: string; captcha?: string };

function validar(usuario: string, password: string, captchaValor: string, conCaptcha: boolean): ErroresCampo {
  const errores: ErroresCampo = {};
  if (!usuario.trim()) errores.usuario = "Ingresa tu correo electrónico.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(usuario.trim())) errores.usuario = "El correo no tiene un formato válido.";
  if (!password) errores.password = "Ingresa tu contraseña.";
  if (conCaptcha && captchaValor.length !== LONGITUD_CAPTCHA)
    errores.captcha = `El código tiene ${LONGITUD_CAPTCHA} caracteres.`;
  return errores;
}

export default function LoginPage() {
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [verPassword, setVerPassword] = useState(false);
  const [mayusculas, setMayusculas] = useState(false);
  const [mensajeError, setMensajeError] = useState("");
  const [errores, setErrores] = useState<ErroresCampo>({});
  const [estado, setEstado] = useState<Estado>("inactivo");
  const [sacudir, setSacudir] = useState(false); // animación breve al fallar

  const [captcha, setCaptcha] = useState<CaptchaLogin | null>(null);
  const [captchaValor, setCaptchaValor] = useState("");
  const [captchaCargando, setCaptchaCargando] = useState(true);
  const [captchaErrorCarga, setCaptchaErrorCarga] = useState("");

  const refUsuario = useRef<HTMLInputElement>(null);
  const refPassword = useRef<HTMLInputElement>(null);
  const refCaptcha = useRef<HTMLInputElement>(null);

  const { login } = useAuth();

  const aplicarCaptcha = useCallback((pedido: Promise<CaptchaLogin>, sigueVigente: () => boolean = () => true) => {
    return pedido
      .then((nuevo) => sigueVigente() && setCaptcha(nuevo))
      .catch((error) => {
        if (!sigueVigente()) return;
        setCaptcha(null);
        setCaptchaErrorCarga(error instanceof Error ? error.message : "No se pudo cargar el código de verificación.");
      })
      .finally(() => sigueVigente() && setCaptchaCargando(false));
  }, []);

  const cargarCaptcha = useCallback(() => {
    setCaptchaCargando(true);
    setCaptchaErrorCarga("");
    setCaptchaValor("");
    return aplicarCaptcha(obtenerCaptcha());
  }, [aplicarCaptcha]);

  // Primer captcha al entrar (el estado inicial ya es "cargando").
  useEffect(() => {
    let vigente = true;
    aplicarCaptcha(obtenerCaptcha(), () => vigente);
    return () => {
      vigente = false;
    };
  }, [aplicarCaptcha]);

  const conCaptcha = captcha?.habilitado ?? true;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (estado !== "inactivo") return;
    setMensajeError("");

    const nuevosErrores = validar(usuario, password, captchaValor, conCaptcha);
    setErrores(nuevosErrores);
    if (nuevosErrores.usuario) return refUsuario.current?.focus();
    if (nuevosErrores.password) return refPassword.current?.focus();
    if (nuevosErrores.captcha) return refCaptcha.current?.focus();

    setEstado("cargando");
    try {
      // login() maneja el form-urlencoded, el token y la redirección según el rol.
      await login(
        usuario.trim(),
        password,
        conCaptcha && captcha?.captcha_id ? { captchaId: captcha.captcha_id, respuesta: captchaValor } : undefined,
      );
      setEstado("exito");
    } catch (error: unknown) {
      const texto =
        error instanceof Error && error.message ? error.message : "No se pudo iniciar sesión. Inténtalo de nuevo.";
      const esDeCaptcha = error instanceof ApiError && error.status === 400 && /verificaci/i.test(texto);

      setEstado("inactivo");
      setSacudir(true);
      if (esDeCaptcha) {
        setErrores({ captcha: texto });
      } else {
        setMensajeError(texto);
      }
      // El backend consume el captcha en cada intento, acierte o no: siempre
      // hace falta uno nuevo para el siguiente.
      if (conCaptcha) await cargarCaptcha();
      if (esDeCaptcha) refCaptcha.current?.focus();
      else if (error instanceof ApiError && error.status === 401) refPassword.current?.focus();
    }
  };

  const ocupado = estado !== "inactivo";

  return (
    <MarcoAuth titulo="Iniciar sesión" subtitulo="Ingresa con la cuenta que te asignó tu institución.">
      <div
        onAnimationEnd={() => setSacudir(false)}
        className={`${CLASE_TARJETA_AUTH} ${
          sacudir ? "animar-sacudida" : ""
        }`}
      >
        <form onSubmit={handleLogin} noValidate className="space-y-5">
          {mensajeError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-800 dark:border-red-400/30 dark:bg-red-950/40 dark:text-red-200"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{mensajeError}</span>
            </div>
          )}

          {/* Correo */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="usuario" className="text-sm font-medium text-ink/75 dark:text-ink-dark/75">
              Correo electrónico
            </label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35 dark:text-ink-dark/40" aria-hidden />
              <input
                ref={refUsuario}
                id="usuario"
                type="email"
                autoComplete="username"
                autoFocus
                value={usuario}
                onChange={(e) => {
                  setUsuario(e.target.value);
                  if (errores.usuario) setErrores((p) => ({ ...p, usuario: undefined }));
                }}
                disabled={ocupado}
                placeholder="usuario@colegio.com"
                aria-invalid={!!errores.usuario}
                aria-describedby={errores.usuario ? "usuario-error" : undefined}
                className={`${CLASE_INPUT} pr-3.5 ${errores.usuario ? CLASE_INPUT_ERROR : CLASE_INPUT_OK}`}
              />
            </div>
            {errores.usuario && (
              <p id="usuario-error" className="text-xs text-red-700 dark:text-red-300">{errores.usuario}</p>
            )}
          </div>

          {/* Contraseña */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-3">
              <label htmlFor="password" className="text-sm font-medium text-ink/75 dark:text-ink-dark/75">
                Contraseña
              </label>
              <Link href="/recuperar-password" className={`text-xs ${CLASE_ENLACE_AUTH}`}>
                ¿Olvidaste tu contraseña?
              </Link>
            </div>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/35 dark:text-ink-dark/40" aria-hidden />
              <input
                ref={refPassword}
                id="password"
                type={verPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (errores.password) setErrores((p) => ({ ...p, password: undefined }));
                }}
                onKeyUp={(e) => setMayusculas(e.getModifierState("CapsLock"))}
                onBlur={() => setMayusculas(false)}
                disabled={ocupado}
                placeholder="••••••••"
                aria-invalid={!!errores.password}
                aria-describedby={errores.password ? "password-error" : undefined}
                className={`${CLASE_INPUT} pr-11 ${errores.password ? CLASE_INPUT_ERROR : CLASE_INPUT_OK}`}
              />
              <button
                type="button"
                onClick={() => setVerPassword((v) => !v)}
                aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                aria-pressed={verPassword}
                title={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg p-2 text-ink/45 transition hover:bg-mist hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 dark:text-ink-dark/50 dark:hover:bg-surface-raised-dark dark:hover:text-ink-dark"
              >
                {verPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
              </button>
            </div>
            {errores.password ? (
              <p id="password-error" className="text-xs text-red-700 dark:text-red-300">{errores.password}</p>
            ) : (
              mayusculas && <p className="text-xs text-amber-700 dark:text-amber-300">Bloq Mayús está activado.</p>
            )}
          </div>

          {conCaptcha && (
            <CampoCaptcha
              captcha={captcha}
              cargando={captchaCargando}
              errorCarga={captchaErrorCarga}
              valor={captchaValor}
              onCambio={(v) => {
                setCaptchaValor(v);
                if (errores.captcha) setErrores((p) => ({ ...p, captcha: undefined }));
              }}
              onRecargar={() => {
                setErrores((p) => ({ ...p, captcha: undefined }));
                cargarCaptcha();
              }}
              error={errores.captcha}
              deshabilitado={ocupado}
              inputRef={refCaptcha}
            />
          )}

          <button
            type="submit"
            disabled={ocupado || (conCaptcha && captchaCargando)}
            aria-live="polite"
            className={`${CLASE_BOTON_AUTH} ${estado === "exito" ? "bg-emerald-600" : CLASE_BOTON_AUTH_NORMAL}`}
          >
            {estado === "cargando" && (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Verificando…
              </>
            )}
            {estado === "exito" && (
              <>
                <CheckCircle2 className="h-4 w-4" aria-hidden /> Acceso concedido, entrando…
              </>
            )}
            {estado === "inactivo" && (
              <>
                Ingresar al sistema
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </>
            )}
          </button>
        </form>
      </div>
    </MarcoAuth>
  );
}
