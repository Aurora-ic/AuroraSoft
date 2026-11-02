"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, HelpCircle } from "lucide-react";

// 🆕 (sesión 2026-11-01, punto 6 del análisis de UI/UX) Diálogo de
// confirmación propio en lugar de window.confirm: el nativo rompía la
// estética, no explicaba la consecuencia (solo un "Aceptar/Cancelar" genérico)
// y algunos navegadores lo bloquean. Uso:
//
//   const confirmar = useConfirmar();
//   if (!(await confirmar({ titulo: "¿Cancelar esta cita?", mensaje: "…", textoConfirmar: "Cancelar cita", peligro: true }))) return;
//
// En una acción destructiva (`peligro`) el foco arranca en "Volver", nunca en
// la acción: un Enter apresurado no borra nada. Escape o clic fuera = volver.

export type OpcionesConfirmacion = {
  titulo: string;
  mensaje?: ReactNode;
  textoConfirmar?: string;
  textoCancelar?: string;
  peligro?: boolean;
};

type Pendiente = OpcionesConfirmacion & { resolver: (ok: boolean) => void };

const ContextoConfirmacion = createContext<(o: OpcionesConfirmacion) => Promise<boolean>>(async () => false);

export function useConfirmar() {
  return useContext(ContextoConfirmacion);
}

export function ProveedorConfirmacion({ children }: { children: ReactNode }) {
  const [pendiente, setPendiente] = useState<Pendiente | null>(null);

  const confirmar = useCallback(
    (opciones: OpcionesConfirmacion) =>
      new Promise<boolean>((resolver) => {
        setPendiente({ ...opciones, resolver });
      }),
    [],
  );

  function cerrar(ok: boolean) {
    pendiente?.resolver(ok);
    setPendiente(null);
  }

  return (
    <ContextoConfirmacion.Provider value={confirmar}>
      {children}
      {pendiente && <Dialogo opciones={pendiente} onCerrar={cerrar} />}
    </ContextoConfirmacion.Provider>
  );
}

function Dialogo({ opciones, onCerrar }: { opciones: OpcionesConfirmacion; onCerrar: (ok: boolean) => void }) {
  const refCancelar = useRef<HTMLButtonElement>(null);
  const refConfirmar = useRef<HTMLButtonElement>(null);
  const peligro = !!opciones.peligro;

  useEffect(() => {
    const anterior = document.activeElement as HTMLElement | null;
    (peligro ? refCancelar : refConfirmar).current?.focus();
    function teclas(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onCerrar(false);
      }
      if (e.key === "Tab") {
        // Foco atrapado entre los dos botones.
        const otro = document.activeElement === refCancelar.current ? refConfirmar.current : refCancelar.current;
        e.preventDefault();
        otro?.focus();
      }
    }
    window.addEventListener("keydown", teclas);
    return () => {
      window.removeEventListener("keydown", teclas);
      anterior?.focus?.();
    };
  }, [peligro, onCerrar]);

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-ink/45" aria-hidden="true" onClick={() => onCerrar(false)} />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="titulo-confirmacion"
        aria-describedby={opciones.mensaje ? "mensaje-confirmacion" : undefined}
        className="relative w-full max-w-md rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-6 shadow-xl"
      >
        <div className="flex items-start gap-3">
          <span
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
              peligro ? "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-300" : "bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
            }`}
          >
            {peligro ? <AlertTriangle size={19} aria-hidden="true" /> : <HelpCircle size={19} aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <h2 id="titulo-confirmacion" className="m-0 font-display text-[17px] font-semibold text-ink dark:text-ink-dark">
              {opciones.titulo}
            </h2>
            {opciones.mensaje && (
              <div id="mensaje-confirmacion" className="mt-1.5 text-sm leading-relaxed text-ink/70 dark:text-ink-dark/70">
                {opciones.mensaje}
              </div>
            )}
          </div>
        </div>
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            ref={refCancelar}
            type="button"
            onClick={() => onCerrar(false)}
            className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-4 py-2 text-sm font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-400"
          >
            {opciones.textoCancelar ?? "Volver"}
          </button>
          <button
            ref={refConfirmar}
            type="button"
            onClick={() => onCerrar(true)}
            className={`rounded-card px-4 py-2 text-sm font-semibold text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 ${
              peligro
                ? "bg-red-600 hover:bg-red-700 focus-visible:ring-red-400"
                : "bg-accion hover:bg-accion-hover focus-visible:ring-teal-400 dark:bg-teal-accent-dark dark:text-mist-dark"
            }`}
          >
            {opciones.textoConfirmar ?? "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  );
}
