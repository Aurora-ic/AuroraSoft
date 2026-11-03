"use client";

import { useEffect, type DependencyList } from "react";

/**
 * 🆕 (sesión 2026-11-02) Corre `cargar` al montar y cada vez que cambian
 * `deps`, fuera del cuerpo síncrono del efecto.
 *
 * Por qué: las pantallas que cargan datos al abrirse marcaban
 * `setCargando(true)` / `setError(null)` directamente dentro de `useEffect`,
 * que la regla `react-hooks/set-state-in-effect` marca como error (renders
 * en cascada). Diferir a la siguiente vuelta del event loop es el mismo
 * criterio que ya usan AuthContext y BloqueoInactividad; el comportamiento
 * visible no cambia (el estado inicial de esas pantallas ya es "cargando").
 *
 * `cargar` puede devolver una función de limpieza (p. ej. la que apaga el
 * flag `vigente` que descarta respuestas viejas); se llama al desmontar o
 * antes de la siguiente carga, igual que la limpieza de un efecto normal.
 *
 * Las pantallas nuevas deberían usar react-query (como lib/padron.ts) en vez
 * de este patrón.
 */
export function useCargaDiferida(cargar: () => void | (() => void), deps: DependencyList): void {
  useEffect(() => {
    let limpiar: void | (() => void);
    const temporizador = setTimeout(() => {
      limpiar = cargar();
    }, 0);
    return () => {
      clearTimeout(temporizador);
      if (typeof limpiar === "function") limpiar();
    };
    // `deps` las decide quien llama, igual que en un useEffect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
