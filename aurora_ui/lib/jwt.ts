import type { Rol } from "@/types/api";

type PayloadToken = {
  sub: string; // email
  rol: Rol;
  institucion_id: number | null;
  exp: number;
};

/** Decodifica el payload de un JWT sin validar la firma (eso ya lo hace
 * el backend en cada request) — solo para leer rol/email en el cliente
 * y decidir qué mostrar en la UI. */
export function decodificarToken(token: string): PayloadToken | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json);
  } catch {
    return null;
  }
}

export function tokenExpirado(token: string): boolean {
  const datos = decodificarToken(token);
  if (!datos) return true;
  return Date.now() >= datos.exp * 1000;
}
