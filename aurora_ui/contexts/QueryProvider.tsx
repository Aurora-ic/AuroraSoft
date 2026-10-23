"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * PLAN_REMODELACION_ARQUITECTURA.md, fase 5 — capa de datos del frontend.
 * Reemplaza, para código NUEVO a partir de ahora, el patrón repetido en
 * cada pantalla (useState de datos + useState de loading + useState de
 * error + useEffect con apiClient.get(...)): caché, deduplicación de
 * requests y revalidación automática, de una vez.
 *
 * `new QueryClient()` vive dentro de `useState(() => ...)` (nunca a nivel
 * de módulo) para que cada sesión del navegador tenga su propia instancia
 * — a nivel de módulo, un refresh de Fast Refresh en desarrollo recrearía
 * el QueryClient en cada edición y perdería la caché; a nivel de useState,
 * sobrevive mientras el árbol de React no se desmonte.
 *
 * Ninguna página existente se migra en esta fase (ver CLAUDE.md/plan):
 * las páginas ya escritas siguen con su propio useState+useEffect tal cual
 * están. Solo las páginas nuevas que se escriban de ahora en adelante usan
 * `useQuery`/`useMutation` de @tanstack/react-query.
 */
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
