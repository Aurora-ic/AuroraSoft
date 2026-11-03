"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { LIMITE_MS, estaBloqueado, leerUltimaActividad, olvidarInactividad } from "@/lib/inactividad";
import { useRouter } from "next/navigation";
import {
  apiClient,
  borrarSesionPublica,
  cerrarSesionEnServidor,
  guardarSesionPublica,
  leerSesionPublica,
  login as loginApi,
  renovarSesion,
  type RespuestaCaptcha,
  type SesionPublica,
} from "@/lib/api-client";
import type { Rol } from "@/types/api";

type SesionActual = SesionPublica | null;

// 🆕 (sesión 2026-11-02) El acceso dura ~15 min (backend/core/sesiones.py).
// Mientras la persona trabaja se renueva antes de que venza, así una página
// que pasa mucho rato sin pedir nada (redactar un informe largo) no llega a
// SESION_INACTIVIDAD_MINUTOS del servidor y no pierde la sesión. Sin
// actividad reciente NO se renueva: eso le toca al bloqueo por inactividad.
const MINUTOS_RENOVACION_PROACTIVA = 10;

type AuthContextValue = {
  sesion: SesionActual;
  cargando: boolean;
  login: (correo: string, pass: string, captcha?: RespuestaCaptcha) => Promise<void>;
  cerrarSesion: () => void;
};

const AuthContext = createContext<AuthContextValue>({
  sesion: null,
  cargando: true,
  login: async () => {},
  cerrarSesion: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [sesion, setSesion] = useState<SesionActual>(null);
  const [cargando, setCargando] = useState(true);
  const router = useRouter();

  // 🆕 (sesión 2026-11-02) El token vive en una cookie httpOnly que este
  // código no puede leer. Se pinta la interfaz con la sesión pública guardada
  // al iniciar sesión y se confirma con el servidor en segundo plano: si la
  // sesión ya no vale (y no se puede renovar), api-client dispara
  // "aurora:no-autorizado" y se cierra abajo.
  useEffect(() => {
    // Diferido: así el estado no se fija sincrónicamente dentro del efecto
    // (react-hooks/set-state-in-effect). localStorage no existe en el
    // servidor, por eso no puede ir en el valor inicial de useState.
    const primera = setTimeout(() => {
      const guardada = leerSesionPublica();
      setSesion(guardada);
      setCargando(false);
      if (!guardada) return;
      apiClient
        .get<{ email: string; rol: Rol; institucion_id: number | null }>("/auth/me")
        .then((u) => {
          const confirmada = { email: u.email, rol: u.rol, institucionId: u.institucion_id };
          guardarSesionPublica(confirmada);
          setSesion(confirmada);
        })
        .catch(() => {
          // 401: ya lo maneja el evento global. Sin red: se sigue con la guardada.
        });
    }, 0);
    return () => clearTimeout(primera);
  }, []);

  useEffect(() => {
    if (!sesion) return;
    const intervalo = setInterval(() => {
      const ultima = leerUltimaActividad();
      if (estaBloqueado() || ultima === null || Date.now() - ultima > LIMITE_MS) return;
      void renovarSesion();
    }, MINUTOS_RENOVACION_PROACTIVA * 60 * 1000);
    return () => clearInterval(intervalo);
  }, [sesion]);

  // 🆕 lib/api-client.ts dispara este evento ante CUALQUIER 401 de la API
  // (token expirado, o revocado por un cambio de contraseña — la versión de
  // credencial que ya valida cada request en el backend). Antes, un 401 a
  // mitad de sesión solo producía un ApiError que cada page.tsx manejaba (o
  // no) por su cuenta — varias páginas lo dejaban pasar sin .catch() y
  // terminaban mostrando "no hay datos" en vez de avisar que había que
  // volver a iniciar sesión. Centralizado aquí: un solo lugar cierra la
  // sesión y redirige, sin que cada pantalla tenga que saber de esto.
  useEffect(() => {
    function alNoAutorizado() {
      cerrarSesion();
    }
    window.addEventListener("aurora:no-autorizado", alNoAutorizado);
    return () => window.removeEventListener("aurora:no-autorizado", alNoAutorizado);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function login(correo: string, pass: string, captcha?: RespuestaCaptcha) {
    // Vía el helper de lib/api-client.ts, que respeta NEXT_PUBLIC_API_URL —
    // antes esta función duplicaba esa misma petición con
    // "http://127.0.0.1:8000" fijo, que rompía el login en cualquier deploy
    // con otro origen de API. 🆕 (sesión 2026-11-02) Las cookies las deja el
    // backend; aquí solo llega la sesión pública.
    const nuevaSesion = await loginApi(correo, pass, captcha);

    setSesion(nuevaSesion);

    // Redireccionar según el rol del usuario
    if (nuevaSesion.rol === "superadmin") {
      router.push("/master");
    } else {
      // 🆕 Antes caía directo en /estudiantes (un listado crudo, sin ningún
      // "qué tengo que atender hoy"). /inicio es el dashboard de aterrizaje.
      router.push("/inicio");
    }
  }

  function cerrarSesion() {
    // 🆕 (sesión 2026-11-02) Antes solo se borraba el token del navegador y
    // seguía valiendo en el servidor. Ahora se revoca allá (sin esperar: si
    // no hay red, la sesión igual caduca por inactividad en el servidor).
    void cerrarSesionEnServidor();
    borrarSesionPublica();
    olvidarInactividad(); // 🆕 sin sesión no hay nada que bloquear
    setSesion(null);
    router.push("/");
  }

  return (
    <AuthContext.Provider value={{ sesion, cargando, login, cerrarSesion }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

export function RequireAuth({
  children,
  rolesPermitidos,
}: {
  children: React.ReactNode;
  rolesPermitidos: Rol[];
}) {
  const { sesion, cargando, cerrarSesion } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (cargando) return;
    if (!sesion) {
      router.replace("/");
      return;
    }
    if (!rolesPermitidos.includes(sesion.rol)) {
      cerrarSesion();
    }
  }, [cargando, sesion, rolesPermitidos, router, cerrarSesion]);

  if (cargando || !sesion || !rolesPermitidos.includes(sesion.rol)) {
    return <div className="min-h-screen flex items-center justify-center bg-mist text-ink/40">Cargando…</div>;
  }

  return <>{children}</>;
}