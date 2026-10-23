"use client";

import { useState } from "react";
import Image from "next/image";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";

export default function LoginPage() {
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [mensajeError, setMensajeError] = useState("");
  const [cargando, setCargando] = useState(false);

  const { login } = useAuth();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setMensajeError("");
    setCargando(true);

    try {
      // login() maneja el form-urlencoded, el token y la redirección según el rol.
      await login(usuario, password);
    } catch (error: any) {
      let textoError = "Credenciales incorrectas o error de conexión.";
      if (typeof error === "string") {
        textoError = error;
      } else if (error?.detail) {
        textoError = typeof error.detail === "string" ? error.detail : "Error de validación.";
      } else if (error?.message) {
        textoError = error.message;
      }
      setMensajeError(textoError);
      setCargando(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-mist px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <Image src="/logo.png" alt="AuroraSoft" width={140} height={99} priority className="mb-4 h-14 w-auto" />
          <h1 className="font-display text-xl font-semibold text-teal-900">AuroraSoft</h1>
          <p className="text-xs text-ink/50 mt-1">Plataforma de Evaluación Psicométrica</p>
        </div>

        <div className="bg-white rounded-card border border-border p-8 shadow-sm">
          <form onSubmit={handleLogin} className="space-y-4">
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium text-ink/70">Correo electrónico</span>
              <input
                type="email"
                required
                value={usuario}
                onChange={(e) => setUsuario(e.target.value)}
                placeholder="usuario@colegio.com"
                className="rounded-card border border-border px-3.5 py-2.5 text-sm text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium text-ink/70">Contraseña</span>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="rounded-card border border-border px-3.5 py-2.5 text-sm text-ink placeholder:text-ink/40 focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </label>

            <TextoError>{mensajeError}</TextoError>

            <Boton type="submit" disabled={cargando} className="w-full mt-2">
              {cargando ? "Iniciando sesión..." : "Ingresar al sistema"}
            </Boton>
          </form>
        </div>
      </div>
    </div>
  );
}
