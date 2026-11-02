"use client";

import { useEffect, useState } from "react";

// 🆕 (sesión 2026-11-01, punto 5 del análisis de UI/UX) Índice fijo de la
// ficha del alumno: una sola página de ~14 bloques obligaba a hacer scroll
// en plena sesión para llegar a "Historial de sesiones" o al expediente.
// Se eligió un índice (y no pestañas) a propósito: las pestañas DESMONTAN
// los bloques ocultos, y varios tienen formularios en edición que se
// perderían al cambiar de pestaña; con el índice todo sigue montado y solo
// se salta a cada grupo. El grupo visible queda resaltado.
export type GrupoIndice = { id: string; etiqueta: string };

export function IndiceFicha({ grupos }: { grupos: GrupoIndice[] }) {
  const [activo, setActivo] = useState(grupos[0]?.id ?? "");

  useEffect(() => {
    // El grupo actual es el ÚLTIMO cuyo título ya pasó el 30 % superior de
    // la ventana — así también acierta tras un salto directo (sin pasar por
    // los grupos intermedios), que un IntersectionObserver no detecta.
    let pendiente = 0;
    function calcular() {
      pendiente = 0;
      const limite = window.innerHeight * 0.3;
      let actual = grupos[0]?.id ?? "";
      for (const g of grupos) {
        const el = document.getElementById(g.id);
        if (el && el.getBoundingClientRect().top <= limite) actual = g.id;
      }
      setActivo(actual);
    }
    function alDesplazar() {
      if (!pendiente) pendiente = window.requestAnimationFrame(calcular);
    }
    // Captura: el scroll ocurre en <main>, no en la ventana.
    window.addEventListener("scroll", alDesplazar, { passive: true, capture: true });
    window.addEventListener("resize", alDesplazar);
    return () => {
      if (pendiente) window.cancelAnimationFrame(pendiente);
      window.removeEventListener("scroll", alDesplazar, { capture: true });
      window.removeEventListener("resize", alDesplazar);
    };
  }, [grupos]);

  function ir(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActivo(id);
  }

  return (
    <nav
      aria-label="Secciones de la ficha"
      className="sticky top-0 z-20 -mx-1 overflow-x-auto rounded-xl border border-border dark:border-border-dark bg-surface/95 dark:bg-surface-dark/95 px-1 py-1 shadow-sm backdrop-blur"
    >
      <ul className="m-0 flex list-none gap-1 p-0">
        {grupos.map((g) => (
          <li key={g.id} className="shrink-0">
            <button
              type="button"
              onClick={() => ir(g.id)}
              aria-current={activo === g.id ? "location" : undefined}
              className={`rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${
                activo === g.id
                  ? "bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                  : "text-ink/65 hover:bg-mist hover:text-ink dark:text-ink-dark/65 dark:hover:bg-surface-raised-dark dark:hover:text-ink-dark"
              }`}
            >
              {g.etiqueta}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
