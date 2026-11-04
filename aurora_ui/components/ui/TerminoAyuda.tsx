"use client";

import { useEffect, useId, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";
import { GLOSARIO, type ClaveTermino } from "@/lib/glosario";

const ANCHO_GLOBO = 256;
const MARGEN = 12;

/**
 * 🆕 (sesión 2026-11-02) Ícono "?" junto a un término (baremo, retenido, en
 * alerta…) que muestra su definición del glosario (lib/glosario.ts).
 *
 * - Se abre al hacer clic o con Enter/Espacio, no al pasar el ratón: en
 *   tablet y celular no hay "hover", y así funciona igual en todos lados.
 * - Escape, un clic fuera, sacar el foco o desplazar la página lo cierran.
 * - El globo es `position: fixed`, calculado desde el botón: así no lo
 *   recorta un contenedor con overflow oculto (p. ej. el `truncate` del
 *   detalle de una TarjetaKpi) y nunca se sale del ancho de la pantalla.
 * - Lector de pantalla: botón con aria-expanded y la definición enlazada por
 *   aria-describedby mientras está abierta.
 * - No usar dentro de otro <button> (p. ej. una TarjetaKpi con onClick):
 *   un botón dentro de otro no es HTML válido.
 */
export function TerminoAyuda({ termino }: { termino: ClaveTermino }) {
  const [posicion, setPosicion] = useState<{ top: number; left: number } | null>(null);
  const abierto = posicion !== null;
  const id = useId();
  const contenedor = useRef<HTMLSpanElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  const { termino: nombre, definicion } = GLOSARIO[termino];

  function alternar() {
    if (abierto) {
      setPosicion(null);
      return;
    }
    const r = boton.current?.getBoundingClientRect();
    if (!r) return;
    const left = Math.min(Math.max(MARGEN, r.left + r.width / 2 - ANCHO_GLOBO / 2), window.innerWidth - ANCHO_GLOBO - MARGEN);
    setPosicion({ top: r.bottom + 6, left: Math.max(MARGEN, left) });
  }

  useEffect(() => {
    if (!abierto) return;
    const cerrar = () => setPosicion(null);
    function alTeclado(e: KeyboardEvent) {
      if (e.key === "Escape") cerrar();
    }
    function alClicFuera(e: MouseEvent) {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) cerrar();
    }
    document.addEventListener("keydown", alTeclado);
    document.addEventListener("mousedown", alClicFuera);
    window.addEventListener("scroll", cerrar, true);
    window.addEventListener("resize", cerrar);
    return () => {
      document.removeEventListener("keydown", alTeclado);
      document.removeEventListener("mousedown", alClicFuera);
      window.removeEventListener("scroll", cerrar, true);
      window.removeEventListener("resize", cerrar);
    };
  }, [abierto]);

  return (
    <span ref={contenedor} className="inline-flex align-middle">
      <button
        ref={boton}
        type="button"
        onClick={alternar}
        onBlur={(e) => {
          if (!contenedor.current?.contains(e.relatedTarget as Node)) setPosicion(null);
        }}
        aria-expanded={abierto}
        aria-label={`Qué significa «${nombre}»`}
        aria-describedby={abierto ? id : undefined}
        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-ink/40 hover:text-teal-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 dark:text-ink-dark/45 dark:hover:text-teal-accent-dark"
      >
        <HelpCircle size={14} strokeWidth={2.2} aria-hidden="true" />
      </button>
      {posicion && (
        <span
          id={id}
          role="tooltip"
          style={{ top: posicion.top, left: posicion.left, width: ANCHO_GLOBO }}
          className="fixed z-[60] whitespace-normal rounded-xl border border-border bg-surface p-3 text-left text-[12.5px] font-normal normal-case leading-relaxed tracking-normal text-ink/75 shadow-xl dark:border-border-dark dark:bg-surface-raised-dark dark:text-ink-dark/80"
        >
          <strong className="mb-1 block font-semibold text-ink dark:text-ink-dark">{nombre}</strong>
          {definicion}
        </span>
      )}
    </span>
  );
}
