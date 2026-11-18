"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, X } from "lucide-react";

// 🆕 (2026-11-17, plan de UX fase 3) Avisos breves de "listo" en una esquina.
// Antes, guardar algo (datos de la ficha, una cita, un caso) solo se notaba
// porque el formulario se cerraba o el dato cambiaba: no había ninguna
// confirmación de que el cambio quedó guardado. Los ERRORES siguen junto a
// lo que falló (TextoError), donde se pueden leer y corregir; aquí solo se
// confirma lo que salió bien.
//
// Uso: const avisar = useAvisar(); ... await apiClient.patch(...); avisar("Cita reprogramada.");

type Aviso = { id: number; texto: string };

const ContextoAvisos = createContext<(texto: string) => void>(() => {});

export function useAvisar() {
  return useContext(ContextoAvisos);
}

const DURACION_MS = 3500;

export function ProveedorAvisos({ children }: { children: React.ReactNode }) {
  const [avisos, setAvisos] = useState<Aviso[]>([]);
  const siguienteId = useRef(1);

  const quitar = useCallback((id: number) => setAvisos((prev) => prev.filter((a) => a.id !== id)), []);

  const avisar = useCallback((texto: string) => {
    const id = siguienteId.current++;
    // Como mucho 3 a la vista: el más viejo sale primero.
    setAvisos((prev) => [...prev.filter((a) => a.texto !== texto).slice(-2), { id, texto }]);
  }, []);

  return (
    <ContextoAvisos.Provider value={avisar}>
      {children}
      <div
        aria-live="polite"
        role="status"
        className="pointer-events-none fixed bottom-4 right-4 left-4 sm:left-auto z-[60] flex flex-col items-end gap-2"
      >
        {avisos.map((a) => (
          <ItemAviso key={a.id} aviso={a} onCerrar={quitar} />
        ))}
      </div>
    </ContextoAvisos.Provider>
  );
}

function ItemAviso({ aviso, onCerrar }: { aviso: Aviso; onCerrar: (id: number) => void }) {
  const [pausado, setPausado] = useState(false);
  useEffect(() => {
    if (pausado) return;
    const t = setTimeout(() => onCerrar(aviso.id), DURACION_MS);
    return () => clearTimeout(t);
  }, [aviso.id, onCerrar, pausado]);

  return (
    <div
      onMouseEnter={() => setPausado(true)}
      onMouseLeave={() => setPausado(false)}
      className="animar-aparecer pointer-events-auto flex w-full sm:w-auto sm:max-w-sm items-center gap-2.5 rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-raised-dark px-3.5 py-2.5 text-[13px] font-medium text-ink dark:text-ink-dark shadow-lg"
    >
      <CheckCircle2 size={17} className="shrink-0 text-seccion-600 dark:text-seccion-claro" aria-hidden="true" />
      <span className="min-w-0 flex-1">{aviso.texto}</span>
      <button
        type="button"
        onClick={() => onCerrar(aviso.id)}
        aria-label="Cerrar aviso"
        className="shrink-0 rounded-md p-1 text-ink/65 hover:bg-ink/5 hover:text-ink/70 dark:text-ink-dark/55 dark:hover:bg-white/5"
      >
        <X size={13} aria-hidden="true" />
      </button>
    </div>
  );
}
