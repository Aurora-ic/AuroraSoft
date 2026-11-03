"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { Lock, Loader2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError, bloquearSesionEnServidor, login, obtenerCaptcha, type CaptchaLogin } from "@/lib/api-client";
import { CampoCaptcha, LONGITUD_CAPTCHA } from "@/components/auth/CampoCaptcha";
import {
  CLAVES_INACTIVIDAD,
  LIMITE_MS,
  MINUTOS_INACTIVIDAD,
  SEGUNDOS_AVISO,
  bloquear,
  estaBloqueado,
  leerUltimaActividad,
  marcarActividad,
  reiniciarInactividad,
} from "@/lib/inactividad";

// 🆕 (sesión 2026-11-01, punto 3 del análisis de UI/UX) Bloqueo por
// inactividad — ver lib/inactividad.ts para el porqué.
// - Tras MINUTOS_INACTIVIDAD sin teclado/ratón/toque/scroll en NINGUNA
//   pestaña, la pantalla se cubre y pide la contraseña. Un aviso aparece
//   SEGUNDOS_AVISO antes.
// - La página sigue montada debajo (marcada `inert`): al desbloquear, lo que
//   se estaba escribiendo sigue ahí.
// - Desbloquear = un login real (POST /auth/login, con captcha si el
//   servidor lo pide) que emite un token nuevo.
// - Si se cierra la pestaña y se vuelve después del límite, arranca
//   bloqueada.
const MARGEN_ESCRITURA_MS = 15_000; // no escribir en localStorage en cada movimiento

export function BloqueoInactividad({ children }: { children: React.ReactNode }) {
  const { sesion, cerrarSesion } = useAuth();
  const [bloqueado, setBloqueado] = useState(false);
  const [segundosRestantes, setSegundosRestantes] = useState<number | null>(null);
  const ultimaEscritura = useRef(0);

  const revisar = useCallback(() => {
    if (estaBloqueado()) {
      setBloqueado(true);
      setSegundosRestantes(null);
      return;
    }
    const ultima = leerUltimaActividad();
    if (ultima === null) {
      marcarActividad();
      return;
    }
    const restante = LIMITE_MS - (Date.now() - ultima);
    if (restante <= 0) {
      bloquear();
      // 🆕 (sesión 2026-11-02) El bloqueo también vale en el SERVIDOR: la
      // sesión queda bloqueada y ningún acceso de ella sirve hasta
      // desbloquear con la contraseña. Antes era solo esta capa, que se
      // podía quitar con las herramientas del navegador.
      void bloquearSesionEnServidor();
      setBloqueado(true);
      setSegundosRestantes(null);
    } else {
      setBloqueado(false);
      setSegundosRestantes(restante <= SEGUNDOS_AVISO * 1000 ? Math.ceil(restante / 1000) : null);
    }
  }, []);

  useEffect(() => {
    // Primera revisión diferida: así el estado no se fija sincrónicamente
    // dentro del efecto (react-hooks/set-state-in-effect).
    const primera = setTimeout(revisar, 0);
    const intervalo = setInterval(revisar, 1000);
    function alActuar() {
      if (estaBloqueado()) return;
      const ahora = Date.now();
      if (ahora - ultimaEscritura.current < MARGEN_ESCRITURA_MS) return;
      ultimaEscritura.current = ahora;
      marcarActividad();
      setSegundosRestantes(null);
    }
    function alCambiarOtraPestana(e: StorageEvent) {
      if (e.key && CLAVES_INACTIVIDAD.includes(e.key)) revisar();
    }
    const eventos = ["mousemove", "mousedown", "keydown", "touchstart", "wheel"] as const;
    eventos.forEach((ev) => window.addEventListener(ev, alActuar, { passive: true }));
    window.addEventListener("scroll", alActuar, { passive: true, capture: true });
    window.addEventListener("storage", alCambiarOtraPestana);
    return () => {
      clearTimeout(primera);
      clearInterval(intervalo);
      eventos.forEach((ev) => window.removeEventListener(ev, alActuar));
      window.removeEventListener("scroll", alActuar, { capture: true });
      window.removeEventListener("storage", alCambiarOtraPestana);
    };
  }, [revisar]);

  function seguirTrabajando() {
    ultimaEscritura.current = Date.now();
    marcarActividad();
    setSegundosRestantes(null);
  }

  return (
    <>
      <div inert={bloqueado} aria-hidden={bloqueado || undefined} className="contents">
        {children}
      </div>

      {segundosRestantes !== null && !bloqueado && (
        <div role="alertdialog" aria-live="assertive" aria-labelledby="aviso-inactividad" className="fixed inset-x-0 bottom-4 z-[90] flex justify-center px-4">
          <div className="flex w-full max-w-md items-center gap-3 rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-4 py-3 shadow-xl">
            <Lock size={18} className="shrink-0 text-acento-pizarra dark:text-acento-pizarra-dark" aria-hidden="true" />
            <p id="aviso-inactividad" className="m-0 flex-1 text-sm text-ink dark:text-ink-dark">
              Por inactividad, la sesión se bloqueará en <strong>{segundosRestantes} s</strong>.
            </p>
            <button
              type="button"
              onClick={seguirTrabajando}
              className="shrink-0 rounded-card bg-accion px-3 py-1.5 text-[13px] font-semibold text-white hover:bg-accion-hover dark:bg-teal-accent-dark dark:text-mist-dark"
            >
              Seguir trabajando
            </button>
          </div>
        </div>
      )}

      {bloqueado && sesion && (
        <PantallaBloqueo
          email={sesion.email}
          onDesbloqueado={() => {
            reiniciarInactividad();
            setBloqueado(false);
          }}
          onCerrarSesion={cerrarSesion}
        />
      )}
    </>
  );
}

function PantallaBloqueo({
  email,
  onDesbloqueado,
  onCerrarSesion,
}: {
  email: string;
  onDesbloqueado: () => void;
  onCerrarSesion: () => void;
}) {
  const [password, setPassword] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [captcha, setCaptcha] = useState<CaptchaLogin | null>(null);
  const [captchaValor, setCaptchaValor] = useState("");
  const [captchaCargando, setCaptchaCargando] = useState(true);
  const refCaptcha = useRef<HTMLInputElement>(null);

  // Al abrirse ya se pregunta si hace falta captcha: fallos recientes de
  // contraseña (en el login o aquí) lo exigen también para desbloquear.
  useEffect(() => {
    let vigente = true;
    obtenerCaptcha(email)
      .then((c) => vigente && setCaptcha(c))
      .catch(() => vigente && setCaptcha(null))
      .finally(() => vigente && setCaptchaCargando(false));
    return () => {
      vigente = false;
    };
  }, [email]);

  async function cargarCaptcha() {
    setCaptchaCargando(true);
    setCaptchaValor("");
    try {
      setCaptcha(await obtenerCaptcha(email));
    } catch {
      setCaptcha(null);
    } finally {
      setCaptchaCargando(false);
    }
  }

  const conCaptcha = !!captcha?.habilitado;

  async function desbloquear(e: React.FormEvent) {
    e.preventDefault();
    if (!password || enviando) return;
    if (conCaptcha && captchaValor.length !== LONGITUD_CAPTCHA) {
      setError(`El código tiene ${LONGITUD_CAPTCHA} caracteres.`);
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await login(
        email,
        password,
        conCaptcha && captcha?.captcha_id ? { captchaId: captcha.captcha_id, respuesta: captchaValor } : undefined,
      );
      onDesbloqueado();
    } catch (err: unknown) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "No se pudo verificar la contraseña.");
      setPassword("");
      await cargarCaptcha(); // tras fallos, el servidor puede empezar a pedirlo
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-mist dark:bg-mist-dark px-4" role="dialog" aria-modal="true" aria-labelledby="titulo-bloqueo">
      <form onSubmit={desbloquear} className="w-full max-w-sm rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-6 shadow-xl sm:p-8">
        <div className="mb-6 flex flex-col items-center text-center">
          <Image src="/logo.png" alt="AuroraSoft" width={140} height={99} className="mb-4 h-12 w-auto" />
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-acento-pizarra/15 text-acento-pizarra dark:bg-acento-pizarra-dark/20 dark:text-acento-pizarra-dark">
            <Lock size={20} aria-hidden="true" />
          </span>
          <h1 id="titulo-bloqueo" className="mt-3 font-display text-xl font-semibold text-teal-900 dark:text-ink-dark">
            Sesión bloqueada
          </h1>
          <p className="mt-1.5 text-sm text-ink/60 dark:text-ink-dark/60">
            Pasaron {MINUTOS_INACTIVIDAD} minutos sin actividad. Para proteger los datos de los estudiantes, ingresa tu contraseña.
            Lo que estabas haciendo sigue abierto.
          </p>
        </div>
        <p className="mb-1.5 text-xs font-medium text-ink/55 dark:text-ink-dark/55">Cuenta</p>
        <p className="mb-4 truncate rounded-xl bg-mist dark:bg-surface-raised-dark px-3.5 py-2.5 text-sm text-ink dark:text-ink-dark">{email}</p>
        <label htmlFor="password-bloqueo" className="mb-1.5 block text-sm font-medium text-ink/75 dark:text-ink-dark/75">
          Contraseña
        </label>
        <input
          id="password-bloqueo"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={enviando}
          className="w-full rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3.5 py-3 text-sm text-ink dark:text-ink-dark focus:border-teal-400 focus:outline-none focus:ring-2 focus:ring-teal-400/40"
        />
        {conCaptcha && (
          <div className="mt-4">
            <CampoCaptcha
              captcha={captcha}
              cargando={captchaCargando}
              errorCarga=""
              valor={captchaValor}
              onCambio={setCaptchaValor}
              onRecargar={cargarCaptcha}
              deshabilitado={enviando}
              inputRef={refCaptcha}
            />
          </div>
        )}
        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={enviando || !password || (conCaptcha && captchaCargando)}
          className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-accion px-4 py-3 text-sm font-semibold text-white hover:bg-accion-hover disabled:cursor-not-allowed disabled:opacity-60 dark:bg-teal-accent-dark dark:text-mist-dark"
        >
          {enviando && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
          {enviando ? "Verificando…" : "Desbloquear"}
        </button>
        <button type="button" onClick={onCerrarSesion} className="mt-4 w-full text-center text-[13px] text-ink/55 dark:text-ink-dark/55 hover:underline">
          Cerrar sesión e ingresar con otra cuenta
        </button>
      </form>
    </div>
  );
}
