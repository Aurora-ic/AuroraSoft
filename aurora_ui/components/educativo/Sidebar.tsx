"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  Home,
  Users,
  ClipboardCheck,
  FileText,
  SlidersHorizontal,
  ChevronRight,
  LogOut,
  X,
  type LucideIcon,
} from "lucide-react";
import { ACENTOS, type Acento } from "@/lib/acentos";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import type { Cita, Institucion } from "@/types/api";

type Enlace = { href: string; label: string };
// 🆕 `acento` (sesión 2026-10-30): color de identidad del grupo, solo en su
// ícono — ver lib/acentos.ts.
type Grupo = { titulo: string; icono: LucideIcon; acento: Acento; enlaces: Enlace[] };

// 🆕 Reorganización por flujo de trabajo (sesión 2026-10-24) — antes era
// una lista plana de 10 ítems con el mismo peso visual para todo. "Inicio"
// queda afuera de los grupos a propósito (es el aterrizaje, no una sección
// más); el resto se agrupa en 4 categorías, colapsables, con el grupo que
// contiene la ruta activa expandido por defecto.
//
// 🆕 Rediseño UI/UX (sesión 2026-10-25, a pedido del usuario) — dos
// hallazgos reales de la versión anterior: (1) ningún ítem tenía ícono,
// pese a que `lucide-react` ya estaba instalado y nunca se usaba en todo
// el proyecto; (2) un grupo (toggler) y un enlace (destino) se veían casi
// idénticos — el único indicio era un "›" delgado. Ahora un GRUPO nunca
// recibe la pastilla sólida de "seleccionado" (solo un tinte suave si
// contiene la ruta activa) y sus hijos cuelgan de una guía vertical
// indentada; solo un enlace de verdad (Inicio, o un hijo de un grupo)
// recibe esa pastilla. El buscador global se mudó al Topbar — la barra
// lateral queda 100% navegación, sin mezclar una acción distinta ahí.
const GRUPOS: Grupo[] = [
  {
    titulo: "Estudiantes",
    acento: "teal",
    icono: Users,
    enlaces: [
      { href: "/estudiantes", label: "Padrón" },
      { href: "/academico", label: "Estructura académica" },
    ],
  },
  {
    titulo: "Evaluación",
    acento: "azul",
    icono: ClipboardCheck,
    enlaces: [
      { href: "/campanas", label: "Campañas" },
      { href: "/pruebas", label: "Pruebas" },
      { href: "/casos-riesgo", label: "Casos en riesgo" },
    ],
  },
  {
    titulo: "Documentos",
    acento: "violeta",
    icono: FileText,
    enlaces: [
      { href: "/documentos", label: "Documentos" },
      { href: "/asentimiento", label: "Consentimiento y asentimiento" },
    ],
  },
  {
    titulo: "Gestión",
    acento: "pizarra",
    icono: SlidersHorizontal,
    enlaces: [
      { href: "/agenda", label: "Agenda" },
      { href: "/configuracion", label: "Configuración" },
    ],
  },
];

// 🆕 Responsive (sesión 2026-10-29, a pedido del usuario) — antes la barra
// lateral era fija en todo ancho y se comía el espacio del contenido en
// pantallas angostas. Ahora desde `lg` sigue igual (sticky, siempre
// visible); por debajo es un cajón fuera de pantalla que abre el botón ☰
// del Topbar (`abierto`/`onCerrar` los maneja ShellEducativo). Una sola
// instancia en los dos modos, para no duplicar los GET de institución/citas.
export function SidebarEducativo({ abierto = false, onCerrar }: { abierto?: boolean; onCerrar?: () => void }) {
  const pathname = usePathname();
  const { sesion, cerrarSesion } = useAuth();
  const [institucion, setInstitucion] = useState<Institucion | null>(null);
  // "Recordatorio" dentro de la app (docs/frontend.md): un contador de
  // citas programadas para HOY, leído del mismo GET que /agenda ya usa —
  // nunca una notificación push ni nada en tiempo real, solo visible la
  // próxima vez que se carga el sidebar.
  const [citasHoy, setCitasHoy] = useState<number | null>(null);

  // Grupo(s) expandido(s) — se inicializa con el que contiene la ruta
  // activa (ajuste de estado derivado durante el render, no en un efecto,
  // ver react-hooks/set-state-in-effect en components/ui/VisorArchivo.tsx
  // para el mismo patrón ya usado antes en este proyecto).
  const [abiertos, setAbiertos] = useState<Set<string>>(() => {
    const grupoActivo = GRUPOS.find((g) => g.enlaces.some((e) => pathname?.startsWith(e.href)));
    return new Set(grupoActivo ? [grupoActivo.titulo] : []);
  });
  const [pathnameAnterior, setPathnameAnterior] = useState(pathname);
  if (pathname !== pathnameAnterior) {
    setPathnameAnterior(pathname);
    const grupoActivo = GRUPOS.find((g) => g.enlaces.some((e) => pathname?.startsWith(e.href)));
    if (grupoActivo && !abiertos.has(grupoActivo.titulo)) {
      setAbiertos((prev) => new Set(prev).add(grupoActivo.titulo));
    }
  }

  function alternarGrupo(titulo: string) {
    setAbiertos((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(titulo)) siguiente.delete(titulo);
      else siguiente.add(titulo);
      return siguiente;
    });
  }

  useEffect(() => {
    apiClient
      .get<Institucion>("/instituciones/me")
      .then(setInstitucion)
      .catch(() => setInstitucion(null)); // informativo, nunca bloquea el sidebar

    apiClient
      .get<Cita[]>("/admin/personas/citas/mi-agenda")
      .then((citas) => {
        const hoy = new Date();
        setCitasHoy(
          citas.filter((c) => {
            if (c.estado !== "Programada") return false;
            const fecha = new Date(c.fecha_hora);
            return (
              fecha.getFullYear() === hoy.getFullYear() &&
              fecha.getMonth() === hoy.getMonth() &&
              fecha.getDate() === hoy.getDate()
            );
          }).length,
        );
      })
      .catch(() => setCitasHoy(null));
  }, []);

  function renderEnlace(enlace: Enlace, indentado: boolean) {
    const activo = pathname?.startsWith(enlace.href);
    return (
      <Link
        key={enlace.href}
        href={enlace.href}
        className={`flex items-center justify-between gap-2 rounded-lg text-[13px] transition-colors ${
          indentado ? "px-3 py-1.5 font-medium" : "px-3 py-2 font-semibold"
        } ${
          activo
            ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
            : "text-ink/75 dark:text-ink-dark/75 hover:bg-mist dark:hover:bg-surface-dark"
        }`}
      >
        {enlace.label}
        {enlace.href === "/agenda" && !!citasHoy && (
          <span
            className={`rounded-full px-1.5 py-0.5 text-[10.5px] font-semibold leading-none ${
              activo ? "bg-white/20 text-white" : "bg-teal-600/10 dark:bg-teal-accent-dark/15 text-teal-900 dark:text-teal-accent-dark"
            }`}
          >
            {citasHoy}
          </span>
        )}
      </Link>
    );
  }

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-64 max-w-[85vw] shrink-0 border-r border-border dark:border-border-dark bg-surface dark:bg-surface-raised-dark flex flex-col justify-between h-screen overflow-y-auto transition-transform duration-200 lg:sticky lg:top-0 lg:z-auto lg:translate-x-0 lg:transition-none ${
        abierto ? "translate-x-0 shadow-xl" : "-translate-x-full"
      }`}
    >
      <div>
        <div className="relative px-5 pt-6 pb-5">
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar menú"
            className="lg:hidden absolute top-5 right-3 p-1.5 rounded-lg text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-dark"
          >
            <X size={18} strokeWidth={2} aria-hidden="true" />
          </button>
          <div className="flex items-center gap-2.5">
            <Image src="/logo.png" alt="" width={140} height={99} className="h-7 w-auto" />
            <span className="font-display text-[17px] font-bold text-ink dark:text-ink-dark">AuroraSoft</span>
          </div>
          {institucion && (
            <p
              className="mt-1.5 text-[11.5px] text-ink/45 dark:text-ink-dark/45 truncate"
              title={institucion.nombre}
            >
              {institucion.nombre}
            </p>
          )}
        </div>

        {/* Inicio — único enlace de nivel superior: icono + label, SIN
            chevron, pastilla sólida igual que cualquier otro enlace real. */}
        <nav className="flex flex-col gap-0.5 px-3 pb-2">
          <Link
            href="/inicio"
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-semibold transition-colors ${
              pathname?.startsWith("/inicio")
                ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                : "text-ink/80 dark:text-ink-dark/80 hover:bg-mist dark:hover:bg-surface-dark"
            }`}
          >
            <Home size={17} strokeWidth={2} aria-hidden="true" />
            Inicio
          </Link>
        </nav>

        <div className="h-px bg-border dark:bg-border-dark mx-4 my-2" />

        <nav className="flex flex-col gap-0.5 px-3 pb-3">
          {GRUPOS.map((grupo) => {
            const abierto = abiertos.has(grupo.titulo);
            const contieneActiva = grupo.enlaces.some((e) => pathname?.startsWith(e.href));
            const Icono = grupo.icono;
            return (
              <div key={grupo.titulo} className="mb-0.5">
                {/*
                  🆕 Fila de GRUPO: nunca pastilla sólida (eso queda
                  reservado para un enlace real) — solo un tinte suave
                  cuando contiene la ruta activa, más un chevron grande y
                  claramente rotable. Esa ausencia de "seleccionado" sólido
                  es la señal de que este botón expande, no navega.
                */}
                <button
                  type="button"
                  onClick={() => alternarGrupo(grupo.titulo)}
                  aria-expanded={abierto}
                  className={`w-full flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-[13px] font-semibold transition-colors ${
                    contieneActiva
                      ? "bg-mist dark:bg-surface-dark text-ink dark:text-ink-dark"
                      : "text-ink/60 dark:text-ink-dark/60 hover:bg-mist dark:hover:bg-surface-dark"
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <span className={`flex h-6 w-6 items-center justify-center rounded-md ${ACENTOS[grupo.acento].chip}`}>
                      <Icono size={14} strokeWidth={2.1} aria-hidden="true" />
                    </span>
                    {grupo.titulo}
                  </span>
                  <ChevronRight
                    size={14}
                    strokeWidth={2.4}
                    aria-hidden="true"
                    className={`transition-transform ${abierto ? "rotate-90" : ""}`}
                  />
                </button>
                {abierto && (
                  <div className="flex flex-col gap-0.5 mt-1 ml-[25px] pl-3.5 border-l border-border dark:border-border-dark">
                    {grupo.enlaces.map((e) => renderEnlace(e, true))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      {/* Cuenta / cerrar sesión */}
      <div className="p-3 border-t border-border dark:border-border-dark">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
          <div className="w-8 h-8 rounded-full bg-mist dark:bg-surface-dark flex items-center justify-center text-[12px] font-bold text-teal-700 dark:text-teal-accent-dark flex-shrink-0">
            {(sesion?.email?.[0] || "?").toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="m-0 text-[12.5px] font-semibold text-ink dark:text-ink-dark truncate" title={sesion?.email}>
              {sesion?.email}
            </p>
            <p className="m-0 text-[11px] text-ink/45 dark:text-ink-dark/45 capitalize">{sesion?.rol}</p>
          </div>
          <button
            onClick={cerrarSesion}
            aria-label="Cerrar sesión"
            className="flex-shrink-0 text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:hover:text-ink-dark p-1.5 rounded-lg hover:bg-mist dark:hover:bg-surface-dark"
          >
            <LogOut size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
