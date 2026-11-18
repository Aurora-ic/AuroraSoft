"use client";

import { useLayoutEffect, useState } from "react";
import { acentoDeRuta } from "@/lib/acentos";
import { usePathname } from "next/navigation";
import { SidebarEducativo } from "@/components/educativo/Sidebar";
import { Topbar } from "@/components/educativo/Topbar";

// 🆕 Responsive (sesión 2026-10-29) — el layout de (educativo) es un Server
// Component, así que el estado del cajón lateral (abierto/cerrado en
// pantallas angostas) vive acá: el botón ☰ del Topbar lo abre, el fondo
// oscuro o el ✕ del Sidebar lo cierran, y navegar a otra pantalla también.
export function ShellEducativo({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuAbierto, setMenuAbierto] = useState(false);

  // Ajuste de estado derivado durante el render — mismo patrón que el
  // `pathnameAnterior` de components/educativo/Sidebar.tsx.
  const [pathnameAnterior, setPathnameAnterior] = useState(pathname);
  if (pathname !== pathnameAnterior) {
    setPathnameAnterior(pathname);
    setMenuAbierto(false);
  }

  // 🆕 (sesión 2026-10-31) overflow-hidden + <main relative>: los
  // elementos `absolute` sin ancestro posicionado (p. ej. los sr-only de
  // los gráficos del Inicio) escapaban del scroll de <main> y alargaban
  // el documento — aparecía una SEGUNDA barra de scroll y la interfaz se
  // descuadraba al bajar.
  // 🆕 (2026-11-17, plan de UX fase 2) "Una pantalla, un color": marca la
  // sección en <html data-seccion> para que botones, enlaces, títulos y
  // seleccionados tomen sus tonos (app/globals.css, clases `seccion-*` y
  // `accion`). En <html> y no en este div para que también lo vean los
  // diálogos que se pintan fuera (confirmación). Antes del pintado, así no
  // parpadea el color de la sección anterior.
  const seccion = acentoDeRuta(pathname);
  useLayoutEffect(() => {
    const raiz = document.documentElement;
    if (seccion === "teal") delete raiz.dataset.seccion;
    else raiz.dataset.seccion = seccion;
    return () => {
      delete raiz.dataset.seccion;
    };
  }, [seccion]);

  return (
    <div className="flex h-screen overflow-hidden bg-mist dark:bg-mist-dark">
      <SidebarEducativo abierto={menuAbierto} onCerrar={() => setMenuAbierto(false)} />
      {menuAbierto && (
        <div className="lg:hidden fixed inset-0 z-30 bg-ink/40" aria-hidden="true" onClick={() => setMenuAbierto(false)} />
      )}
      {/* 🆕 Topbar (sesión 2026-10-25) — persiste entre pantallas, por
          fuera del scroll del contenido (solo <main> scrollea). */}
      <div className="flex-1 min-w-0 flex flex-col h-screen">
        <Topbar onAbrirMenu={() => setMenuAbierto(true)} />
        <main className="relative flex-1 overflow-y-auto px-4 py-6 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
