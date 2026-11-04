"use client";

import { useState } from "react";
import Image from "next/image";
import { HelpCircle, Sun, Moon, Menu } from "lucide-react";
import { useTheme } from "@/contexts/ThemeContext";
import { BusquedaGlobal } from "@/components/educativo/BusquedaGlobal";
import { CentroAyuda } from "@/components/educativo/CentroAyuda";
import { AvisosUrgentes } from "@/components/educativo/AvisosUrgentes";

// 🆕 Barra superior (sesión 2026-10-25, rediseño UI/UX) — antes no existía:
// el buscador global vivía dentro del sidebar, mezclado con la navegación
// pura. Ahora el sidebar queda 100% navegación y esto concentra lo que es
// "acción sobre toda la app, sin importar dónde estés": buscar, pedir
// ayuda, cambiar de tema. Persistente entre pantallas (vive en el layout,
// no en cada página).
export function Topbar({ onAbrirMenu }: { onAbrirMenu?: () => void }) {
  const { tema, alternarTema } = useTheme();
  const [ayudaAbierta, setAyudaAbierta] = useState(false);

  return (
    <>
      <header className="h-15 shrink-0 bg-surface dark:bg-surface-raised-dark border-b border-border dark:border-border-dark flex items-center gap-2 sm:gap-3.5 px-3 sm:px-6">
        {/* ☰ solo por debajo de `lg`, donde la barra lateral pasa a ser un cajón */}
        <button
          type="button"
          onClick={onAbrirMenu}
          aria-label="Abrir menú"
          className="lg:hidden shrink-0 p-2 rounded-lg text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-dark"
        >
          <Menu size={20} strokeWidth={2} aria-hidden="true" />
        </button>

        <div className="flex-1 min-w-0 max-w-[420px]">
          <BusquedaGlobal />
        </div>

        <div className="hidden sm:block flex-1" />

        {/* 🆕 (sesión 2026-11-02) Casos urgentes sin atender (solo equipo clínico). */}
        <AvisosUrgentes />

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

        {/* 🆕 (sesión 2026-10-31) Marca del software en la esquina superior
            derecha, al costado del botón de tema — la barra lateral pasó a
            mostrar el logo y nombre de la institución. */}
        <div className="flex shrink-0 items-center gap-2 pl-2 sm:pl-3.5 border-l border-border dark:border-border-dark" title="AuroraSoft">
          <Image src="/logo.png" alt="" width={140} height={99} className="h-6 w-auto" />
          <span className="hidden sm:inline font-display text-[15px] font-bold text-teal-900 dark:text-ink-dark">AuroraSoft</span>
          <span className="sr-only sm:hidden">AuroraSoft</span>
        </div>
      </header>

      <CentroAyuda abierto={ayudaAbierta} onCerrar={() => setAyudaAbierta(false)} />
    </>
  );
}
