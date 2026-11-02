"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Rol, Usuario } from "@/types/api";

// 🆕 (sesión 2026-11-01, punto 4 del análisis de UI/UX) El usuario actual
// desde GET /auth/me (nombre, cargo) — el JWT solo trae correo y rol. Una
// sola consulta cacheada que comparten la barra lateral y el Inicio.
export function useUsuarioActual(habilitado = true) {
  const consulta = useQuery({
    queryKey: ["usuario-actual"],
    queryFn: () => apiClient.get<Usuario>("/auth/me"),
    enabled: habilitado,
    staleTime: 5 * 60 * 1000,
  });
  return consulta.data ?? null;
}

export const ETIQUETA_ROL: Record<Rol, string> = {
  superadmin: "Superadministrador",
  admin: "Administrador",
  psicologo: "Psicólogo(a)",
  colegio: "Dirección / colegio",
};

/** Primer nombre para un saludo ("Hola, Ana"). */
export function primerNombre(nombreCompleto: string | null | undefined): string | null {
  const nombre = (nombreCompleto ?? "").trim().split(/\s+/)[0];
  return nombre || null;
}
