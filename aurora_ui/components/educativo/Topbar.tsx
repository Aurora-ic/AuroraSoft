"use client";

import { useState } from "react";
import { HelpCircle, Sun, Moon } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { BusquedaGlobal } from "@/components/educativo/BusquedaGlobal";
import { CentroAyuda } from "@/components/educativo/CentroAyuda";

// 🆕 Barra superior (sesión 2026-10-25, rediseño UI/UX) — antes no existía:
// el buscador global vivía dentro del sidebar, mezclado con la navegación
// pura. Ahora el sidebar queda 100% navegación y esto concentra lo que es
// "acción sobre toda la app, sin importar dónde estés": buscar, pedir
// ayuda, cambiar de tema. Persistente entre pantallas (vive en el layout,
// no en cada página).
export function Topbar() {
  const { tema, alternarTema } = useTheme();
  const [ayudaAbierta, setAyudaAbierta] = useState(false);

  return (
    <>
      <header className="h-15 shrink-0 bg-surface dark:bg-surface-raised-dark border-b border-border dark:border-border-dark flex items-center gap-3.5 px-6">
        <div className="flex-1 max-w-[420px]">
          <BusquedaGlobal />
        </div>

        <div className="flex-1" />

        <button
          type="button"
          onClick={() => setAyudaAbierta(true)}
          aria-label="Centro de ayuda"
          className="text-ink/60 dark:text-ink-dark/60 hover:text-ink dark:hover:text-ink-dark hover:bg-mist dark:hover:bg-surface-dark p-2 rounded-lg transition-colors"
        >
          <HelpCircle size={18} strokeWidth={1.9} aria-hidden="true" />
        </button>

        <button
          type="button"
          onClick={alternarTema}
          aria-label={tema === "claro" ? "Cambiar a modo oscuro" : "Cambiar a modo claro"}
          className="text-ink dark:text-ink-dark bg-mist dark:bg-surface-dark border border-border dark:border-border-dark p-2 rounded-lg transition-colors"
        >
          {tema === "claro" ? (
            <Moon size={16} strokeWidth={2} aria-hidden="true" />
          ) : (
            <Sun size={16} strokeWidth={2} aria-hidden="true" />
          )}
        </button>
      </header>

      <CentroAyuda abierto={ayudaAbierta} onCerrar={() => setAyudaAbierta(false)} />
    </>
  );
}
