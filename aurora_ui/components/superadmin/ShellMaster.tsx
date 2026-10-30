"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Building2, LogOut, Menu, X, Sun, Moon, type LucideIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

type Enlace = { href: string; label: string; icono: LucideIcon; exacto?: boolean };

const ENLACES: Enlace[] = [
  { href: "/master", label: "Resumen", icono: LayoutDashboard, exacto: true },
  { href: "/master/clientes", label: "Instituciones", icono: Building2 },
];

// 🆕 Rediseño del panel interno (sesión 2026-10-29, a pedido del usuario) —
// antes era solo un <header> con texto y un <main> con padding fijo, sin
// navegación, sin cerrar sesión, sin modo oscuro y sin adaptarse a pantallas
// angostas. Mismo lenguaje visual que components/educativo/Sidebar.tsx
// (pastilla sólida para el enlace activo, iconos lucide, tokens dark:), pero
// responsive: barra lateral fija desde `lg`, y por debajo una barra superior
// con un botón que abre la misma navegación como cajón lateral.
export function ShellMaster({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [menuAbierto, setMenuAbierto] = useState(false);

  // Cierra el cajón al navegar — ajuste de estado derivado durante el render,
  // mismo patrón que el `pathnameAnterior` de components/educativo/Sidebar.tsx.
  const [pathnameAnterior, setPathnameAnterior] = useState(pathname);
  if (pathname !== pathnameAnterior) {
    setPathnameAnterior(pathname);
    setMenuAbierto(false);
  }

  return (
    <div className="min-h-screen bg-mist dark:bg-mist-dark lg:flex">
      {/* Barra lateral fija (escritorio) */}
      <aside className="hidden lg:flex w-64 shrink-0 h-screen sticky top-0 border-r border-border dark:border-border-dark bg-surface dark:bg-surface-raised-dark">
        <ContenidoNavegacion pathname={pathname} />
      </aside>

      {/* Barra superior (móvil/tablet) */}
      <header className="lg:hidden sticky top-0 z-30 flex items-center gap-3 h-14 px-4 border-b border-border dark:border-border-dark bg-surface/95 dark:bg-surface-raised-dark/95 backdrop-blur">
        <button
          type="button"
          onClick={() => setMenuAbierto(true)}
          aria-label="Abrir menú"
          className="p-2 -ml-2 rounded-lg text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-dark"
        >
          <Menu size={20} strokeWidth={2} aria-hidden="true" />
        </button>
        <Image src="/logo.png" alt="" width={140} height={99} className="h-6 w-auto" />
        <span className="font-display text-[16px] font-bold text-ink dark:text-ink-dark">AuroraSoft</span>
        <span className="ml-auto rounded-full bg-teal-600/10 dark:bg-teal-accent-dark/15 px-2.5 py-0.5 text-[11px] font-semibold text-teal-900 dark:text-teal-accent-dark">
          Panel interno
        </span>
      </header>

      {/* Cajón lateral (móvil/tablet) */}
      {menuAbierto && (
        <div className="lg:hidden fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Menú">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMenuAbierto(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] flex bg-surface dark:bg-surface-raised-dark shadow-xl">
            <button
              type="button"
              onClick={() => setMenuAbierto(false)}
              aria-label="Cerrar menú"
              className="absolute top-5 right-3 p-1.5 rounded-lg text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-dark"
            >
              <X size={18} strokeWidth={2} aria-hidden="true" />
            </button>
            <ContenidoNavegacion pathname={pathname} />
          </aside>
        </div>
      )}

      <main className="flex-1 min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        <div className="mx-auto w-full max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

function ContenidoNavegacion({ pathname }: { pathname: string | null }) {
  const { sesion, cerrarSesion } = useAuth();
  const { tema, alternarTema } = useTheme();

  return (
    <div className="flex flex-col justify-between w-full overflow-y-auto">
      <div>
        <div className="px-5 pt-6 pb-5">
          <div className="flex items-center gap-2.5">
            <Image src="/logo.png" alt="" width={140} height={99} className="h-7 w-auto" />
            <span className="font-display text-[17px] font-bold text-ink dark:text-ink-dark">AuroraSoft</span>
          </div>
          <p className="mt-1.5 text-[11.5px] text-ink/45 dark:text-ink-dark/45">Panel interno · Superadmin</p>
        </div>

        <nav className="flex flex-col gap-0.5 px-3">
          {ENLACES.map((enlace) => {
            const activo = enlace.exacto ? pathname === enlace.href : pathname?.startsWith(enlace.href);
            const Icono = enlace.icono;
            return (
              <Link
                key={enlace.href}
                href={enlace.href}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-semibold transition-colors ${
                  activo
                    ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                    : "text-ink/75 dark:text-ink-dark/75 hover:bg-mist dark:hover:bg-surface-dark"
                }`}
              >
                <Icono size={17} strokeWidth={2} aria-hidden="true" />
                {enlace.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="p-3 space-y-1 border-t border-border dark:border-border-dark">
        <button
          type="button"
          onClick={alternarTema}
          className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium text-ink/70 dark:text-ink-dark/70 hover:bg-mist dark:hover:bg-surface-dark"
        >
          {tema === "claro" ? (
            <Moon size={16} strokeWidth={2} aria-hidden="true" />
          ) : (
            <Sun size={16} strokeWidth={2} aria-hidden="true" />
          )}
          {tema === "claro" ? "Modo oscuro" : "Modo claro"}
        </button>
        <div className="flex items-center gap-2.5 px-2 py-1.5">
          <div className="w-8 h-8 rounded-full bg-mist dark:bg-surface-dark flex items-center justify-center text-[12px] font-bold text-teal-700 dark:text-teal-accent-dark shrink-0">
            {(sesion?.email?.[0] || "?").toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="m-0 text-[12.5px] font-semibold text-ink dark:text-ink-dark truncate" title={sesion?.email}>
              {sesion?.email}
            </p>
            <p className="m-0 text-[11px] text-ink/45 dark:text-ink-dark/45 capitalize">{sesion?.rol}</p>
          </div>
          <button
            type="button"
            onClick={cerrarSesion}
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
            className="shrink-0 text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:hover:text-ink-dark p-1.5 rounded-lg hover:bg-mist dark:hover:bg-surface-dark"
          >
            <LogOut size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}
