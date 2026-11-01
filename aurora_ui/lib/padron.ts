"use client";

import { useEffect, useState } from "react";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { IdsPadron, Persona, RespuestaPaginada, ResumenPadron } from "@/types/api";

// 🆕 Escalabilidad (sesión 2026-11-01) — consultas al padrón SIN bajarlo
// entero. Antes Padrón, Nueva campaña y la Agenda traían todas las páginas
// (getTodasLasPaginas) y filtraban en el navegador; con miles de alumnos
// eso eran decenas de peticiones y miles de filas en memoria. Los filtros
// viven ahora en el backend (crud._consulta_padron_filtrada), con la misma
// semántica (tests/verificar_padron_servidor_equivalencia.py).

// Filtros del listado y de /ids — los mismos nombres que acepta el backend.
export type FiltrosPadron = {
  busqueda?: string;
  estado?: "activos" | "inactivos" | "todos" | "con_dx";
  seccion_id?: number;
  grado_id?: number;
  sin_matricula?: boolean;
  datos_incompletos?: boolean;
  consentimiento_apoderado?: "vigente" | "sin";
};

export function parametrosPadron(filtros: FiltrosPadron): URLSearchParams {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor === undefined || valor === null || valor === "" || valor === false) continue;
    params.set(clave, String(valor));
  }
  return params;
}

// El valor, pero recién `ms` después de que deja de cambiar (búsquedas).
export function useValorDiferido<T>(valor: T, ms = 250): T {
  const [diferido, setDiferido] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setDiferido(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return diferido;
}

// Lista paginada del padrón con "Cargar más" (skip/limit reales — nunca
// `limit` creciente, que chocaría con el tope de 200 del backend).
export function usePadronPaginado({
  institucionId,
  filtros,
  tamano = 50,
  habilitado = true,
}: {
  institucionId: number | null | undefined;
  filtros: FiltrosPadron;
  tamano?: number;
  habilitado?: boolean;
}) {
  const params = parametrosPadron(filtros).toString();
  const consulta = useInfiniteQuery({
    queryKey: ["padron-paginado", institucionId, params, tamano],
    queryFn: ({ pageParam }) => {
      const p = new URLSearchParams(params);
      p.set("skip", String(pageParam));
      p.set("limit", String(tamano));
      return apiClient.get<RespuestaPaginada<Persona>>(`/admin/personas/${institucionId}?${p.toString()}`);
    },
    initialPageParam: 0,
    getNextPageParam: (ultima, todas) => {
      const cargados = todas.reduce((n, pag) => n + pag.items.length, 0);
      return cargados < ultima.total && ultima.items.length > 0 ? cargados : undefined;
    },
    enabled: habilitado && !!institucionId,
    placeholderData: keepPreviousData,
  });
  const vistos = new Set<number>();
  const items = (consulta.data?.pages ?? [])
    .flatMap((pag) => pag.items)
    .filter((p) => (vistos.has(p.id) ? false : (vistos.add(p.id), true)));
  return {
    items: habilitado ? items : [],
    total: habilitado ? (consulta.data?.pages.at(-1)?.total ?? 0) : 0,
    cargando: consulta.isFetching,
    error: consulta.error instanceof Error ? consulta.error.message : consulta.error ? "No se pudo consultar el padrón." : null,
    hayMas: !!consulta.hasNextPage,
    cargarMas: () => consulta.fetchNextPage(),
  };
}

// Solo los ids que cumplen los filtros (para "Seleccionar todos").
export function useIdsPadron({
  institucionId,
  filtros,
  habilitado = true,
}: {
  institucionId: number | null | undefined;
  filtros: FiltrosPadron;
  habilitado?: boolean;
}) {
  const params = parametrosPadron(filtros).toString();
  const consulta = useQuery({
    queryKey: ["padron-ids", institucionId, params],
    queryFn: () => apiClient.get<IdsPadron>(`/admin/personas/${institucionId}/ids?${params}`),
    enabled: habilitado && !!institucionId,
    placeholderData: keepPreviousData,
  });
  return { ids: consulta.data?.ids ?? [], cargando: consulta.isFetching, listo: consulta.isSuccess };
}

export function useResumenPadron({
  institucionId,
  incluirIds = false,
  habilitado = true,
}: {
  institucionId: number | null | undefined;
  incluirIds?: boolean;
  habilitado?: boolean;
}) {
  const consulta = useQuery({
    queryKey: ["padron-resumen", institucionId, incluirIds],
    queryFn: () =>
      apiClient.get<ResumenPadron>(`/admin/personas/${institucionId}/resumen-padron${incluirIds ? "?incluir_ids=true" : ""}`),
    enabled: habilitado && !!institucionId,
  });
  return {
    resumen: consulta.data ?? null,
    cargando: consulta.isFetching,
    error: consulta.error instanceof Error ? consulta.error.message : consulta.error ? "No se pudo cargar el padrón." : null,
    recargar: () => consulta.refetch(),
  };
}
