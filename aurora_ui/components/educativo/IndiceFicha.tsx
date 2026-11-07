"use client";

import { useEffect, useRef, useState } from "react";

// 🆕 (sesión 2026-11-01, punto 5 del análisis de UI/UX) Índice fijo de la
// ficha del alumno: una sola página de ~14 bloques obligaba a hacer scroll
// en plena sesión para llegar a "Historial de sesiones" o al expediente.
// Se eligió un índice (y no pestañas) a propósito: las pestañas DESMONTAN
// los bloques ocultos, y varios tienen formularios en edición que se
// perderían al cambiar de pestaña; con el índice todo sigue montado y solo
// se salta a cada grupo. El grupo visible queda resaltado.
//
// 🆕 (sesión 2026-11-07) Antes la barra quedaba fija DENTRO del relleno de
// <main> (ShellEducativo: py-6 / lg:p-8): entre la barra superior y el
// índice quedaba una franja por la que se veían pasar las tarjetas, y por
// los costados también — la ficha se veía "cortada". Ahora el índice va
// sobre una franja del color del fondo, de borde a borde, que sube hasta
// tocar la barra superior (top negativo = relleno de <main>) y tapa lo que
// pasa por debajo; toma sombra solo cuando está fija. En celular, además,
// la pestaña activa se desplaza sola a la vista.
export type GrupoIndice = { id: string; etiqueta: string };

export function IndiceFicha({ grupos }: { grupos: GrupoIndice[] }) {
  const [activo, setActivo] = useState(grupos[0]?.id ?? "");
  const [fijo, setFijo] = useState(false);
  const refFranja = useRef<HTMLDivElement>(null);
  const refLista = useRef<HTMLUListElement>(null);

  useEffect(() => {
    // El grupo actual es el ÚLTIMO cuyo título ya pasó el 30 % superior de
    // la ventana — así también acierta tras un salto directo (sin pasar por
    // los grupos intermedios), que un IntersectionObserver no detecta.
    let pendiente = 0;
    function calcular() {
      pendiente = 0;
      const limite = window.innerHeight * 0.3;
      let actual = grupos[0]?.id ?? "";
      for (const g of grupos.slice(1)) {
        const el = document.getElementById(g.id);
        if (el && el.getBoundingClientRect().top <= limite) actual = g.id;
      }
      setActivo(actual);
      // "Fija" = la franja ya llegó al borde superior del área que scrollea.
      const franja = refFranja.current;
      const contenedor = franja?.closest("main");
      if (franja && contenedor) {
        setFijo(contenedor.scrollTop > 0 && franja.getBoundingClientRect().top <= contenedor.getBoundingClientRect().top + 1);
      }
    }
    function alDesplazar() {
      if (!pendiente) pendiente = window.requestAnimationFrame(calcular);
    }
    calcular();
    // Captura: el scroll ocurre en <main>, no en la ventana.
    window.addEventListener("scroll", alDesplazar, { passive: true, capture: true });
    window.addEventListener("resize", alDesplazar);
    return () => {
      if (pendiente) window.cancelAnimationFrame(pendiente);
      window.removeEventListener("scroll", alDesplazar, { capture: true });
      window.removeEventListener("resize", alDesplazar);
    };
  }, [grupos]);

  // En pantallas angostas las pestañas no caben: la activa se trae a la vista
  // (solo dentro de la lista, sin mover la página).
  useEffect(() => {
    const lista = refLista.current;
    const boton = lista?.querySelector<HTMLElement>('[aria-current="location"]');
    if (!lista || !boton) return;
    const izquierda = boton.offsetLeft - lista.offsetLeft;
    if (izquierda < lista.scrollLeft || izquierda + boton.offsetWidth > lista.scrollLeft + lista.clientWidth) {
      lista.scrollTo({ left: izquierda - 8, behavior: "smooth" });
    }
  }, [activo]);

  function ir(id: string) {
    if (id === grupos[0]?.id) {
      // El primer grupo es el perfil completo: se vuelve al inicio de la ficha.
      refFranja.current?.closest("main")?.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    setActivo(id);
  }

  return (
    <div
      ref={refFranja}
      className={`sticky -top-6 lg:-top-8 z-20 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-2.5 bg-mist/95 dark:bg-mist-dark/95 backdrop-blur transition-shadow ${
        fijo ? "shadow-[0_6px_16px_-10px_rgba(11,61,52,0.35)] dark:shadow-[0_6px_16px_-10px_rgba(0,0,0,0.6)]" : ""
      }`}
    >
      <nav
        aria-label="Secciones de la ficha"
        className="mx-auto max-w-7xl rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-1 shadow-sm"
      >
        <ul ref={refLista} className="m-0 flex list-none gap-1 overflow-x-auto p-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {grupos.map((g) => (
            <li key={g.id} className="shrink-0">
              <button
                type="button"
                onClick={() => ir(g.id)}
                aria-current={activo === g.id ? "location" : undefined}
                className={`rounded-lg px-3 py-1.5 text-[13px] font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400 ${
                  activo === g.id
                    ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                    : "text-ink/65 hover:bg-mist hover:text-ink dark:text-ink-dark/65 dark:hover:bg-surface-raised-dark dark:hover:text-ink-dark"
                }`}
              >
                {g.etiqueta}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
