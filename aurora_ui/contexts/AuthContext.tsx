"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { decodificarToken, tokenExpirado } from "@/lib/jwt";
import { login as loginApi } from "@/lib/api-client";
import type { Rol } from "@/types/api";

type SesionActual = { email: string; rol: Rol; institucionId: number | null } | null;

type AuthContextValue = {
  sesion: SesionActual;
  cargando: boolean;
  login: (correo: string, pass: string) => Promise<void>;
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

  useEffect(() => {
    const token = localStorage.getItem("aurora_token");
    if (token && !tokenExpirado(token)) {
      const datos = decodificarToken(token);
      if (datos) setSesion({ email: datos.sub, rol: datos.rol, institucionId: datos.institucion_id });
    }
    setCargando(false);
  }, []);

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

  async function login(correo: string, pass: string) {
    // Vía el helper de lib/api-client.ts, que respeta NEXT_PUBLIC_API_URL y
    // ya guarda el token (guardarToken) — antes esta función duplicaba esa
    // misma petición con "http://127.0.0.1:8000" fijo, que rompía el login
    // en cualquier deploy con otro origen de API.
    const respuesta = await loginApi(correo, pass);

    const datos = decodificarToken(respuesta.access_token);
    if (!datos) throw new Error("Token de sesión inválido.");

    const nuevaSesion = {
      email: datos.sub,
      rol: datos.rol,
      institucionId: datos.institucion_id,
    };

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
    localStorage.removeItem("aurora_token");
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