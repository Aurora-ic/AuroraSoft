"use client";

import { keepPreviousData, useQuery, type QueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";

// 🆕 (2026-11-17, plan de UX fase 1) Lecturas con memoria entre pantallas.
//
// Antes cada pantalla pedía sus datos en un useEffect y los perdía al salir:
// volver al Padrón desde la ficha de un alumno lo descargaba otra vez desde
// cero, con su "Cargando…". Con esta capa, al volver se pinta al instante lo
// último que se vio y se actualiza por detrás (staleTime 0: SIEMPRE se vuelve
// a pedir al montar, así nunca se trabaja sobre datos viejos; la memoria solo
// evita la pantalla vacía mientras llega la respuesta).
//
// La memoria se borra al iniciar y al cerrar sesión (AuthContext), para que
// en una computadora compartida del colegio nadie vea datos de la sesión
// anterior.
//
// Clave: ["api", url]. Para refrescar algo tras guardar, usar `recargar()`
// o invalidar `claveApi(url)`.

export function claveApi(url: string) {
  return ["api", url] as const;
}

type Opciones<T, R> = {
  /** Transforma la respuesta (p. ej. quitar duplicados) sin otra petición. */
  seleccionar?: (datos: T) => R;
  /** Mensaje si el error no trae uno propio. */
  mensajeError?: string;
  /** Al cambiar la URL (página, filtro), deja lo anterior en pantalla
   *  mientras llega lo nuevo, en vez de volver a la silueta. */
  mantenerAnterior?: boolean;
};

/**
 * GET con memoria. `url = null` deja la consulta en espera (p. ej. mientras
 * falta un id o el rol no la necesita).
 */
export function useConsultaApi<T, R = T>(url: string | null, opciones: Opciones<T, R> = {}) {
  const consulta = useQuery({
    queryKey: claveApi(url ?? ""),
    queryFn: () => apiClient.get<T>(url as string),
    enabled: url !== null,
    select: opciones.seleccionar,
    placeholderData: opciones.mantenerAnterior ? keepPreviousData : undefined,
  });
  const error = consulta.error
    ? (consulta.error as Error).message || opciones.mensajeError || "No se pudo cargar la información."
    : null;
  return {
    datos: consulta.data as R | undefined,
    error,
    /** true solo la PRIMERA vez (sin nada en memoria que mostrar). */
    cargando: consulta.isPending && url !== null,
    /** true mientras se actualiza por detrás con datos ya en pantalla. */
    actualizando: consulta.isFetching && !consulta.isPending,
    /** true si lo que se ve es lo de la URL anterior (con mantenerAnterior). */
    mostrandoAnterior: consulta.isPlaceholderData,
    recargar: consulta.refetch,
  };
}

/** Marca como viejas (y vuelve a pedir las que estén en pantalla) todas las
 *  lecturas cuya URL empieza por `prefijo`. Para después de guardar. */
export function invalidarApi(queryClient: QueryClient, prefijo: string) {
  return queryClient.invalidateQueries({
    predicate: (q) => q.queryKey[0] === "api" && typeof q.queryKey[1] === "string" && q.queryKey[1].startsWith(prefijo),
  });
}

/** Lista vacía estable (misma referencia en cada render) para el
 *  `datos ?? LISTA_VACIA` de una lista: así un useMemo que depende de ella
 *  no se recalcula en cada render mientras no hay datos. No mutarla. */
export const LISTA_VACIA: never[] = [];
