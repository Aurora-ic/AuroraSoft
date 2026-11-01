"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
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
  School,
  type LucideIcon,
} from "lucide-react";
import { type Acento } from "@/lib/acentos";
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

// 🆕 (sesión 2026-10-31, a pedido del usuario, con una imagen de referencia
// SOLO para el color) Barra lateral en verde petróleo con degradado, texto
// claro y el enlace activo en una pastilla verde agua — los mismos verdes
// de los bloques del Inicio. Arriba ya no va AuroraSoft sino el logo y el
// nombre de la INSTITUCIÓN (Institucion.logo_url, el mismo logo de
// encabezado que se sube en Configuración); AuroraSoft pasó a la esquina
// superior derecha del Topbar.
const PASTILLA_ACTIVA =
  "bg-gradient-to-r from-[#2BB3A0] to-[#1C8F80] text-white shadow-[0_6px_16px_-6px_rgba(43,179,160,0.65)]";
const TEXTO_ENLACE = "text-white/75 hover:bg-white/[0.08] hover:text-white";

// Chip del ícono de cada grupo sobre fondo oscuro: las variantes "-dark" de
// cada acento (pensadas justamente para fondos oscuros, ver globals.css).
const CHIP_GRUPO: Record<Acento, string> = {
  teal: "bg-teal-accent-dark/20 text-teal-accent-dark",
  azul: "bg-acento-azul-dark/20 text-acento-azul-dark",
  violeta: "bg-acento-violeta-dark/20 text-acento-violeta-dark",
  pizarra: "bg-acento-pizarra-dark/25 text-acento-pizarra-dark",
  riesgo: "bg-amber/20 text-amber",
};

function inicialesInstitucion(nombre: string): string {
  const palabras = nombre
    .replace(/[^\p{L}\s]/gu, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 || /^[A-ZÁÉÍÓÚÑ]/.test(w));
  return (palabras.slice(0, 2).map((w) => w[0]).join("") || nombre.slice(0, 2)).toUpperCase();
}

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
          activo ? PASTILLA_ACTIVA : TEXTO_ENLACE
        }`}
      >
        {enlace.label}
        {enlace.href === "/agenda" && !!citasHoy && (
          <span
            className={`rounded-full px-1.5 py-0.5 text-[10.5px] font-semibold leading-none ${
              activo ? "bg-white/25 text-white" : "bg-teal-accent-dark/25 text-[#7FE3D2]"
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
      className={`fixed inset-y-0 left-0 z-40 w-64 max-w-[85vw] shrink-0 bg-gradient-to-b from-[#0E4A44] via-[#0A3B36] to-[#062B28] dark:from-[#0A2E2A] dark:via-[#082522] dark:to-[#051A18] text-white flex flex-col justify-between h-screen overflow-y-auto transition-transform duration-200 lg:sticky lg:top-0 lg:z-auto lg:translate-x-0 lg:transition-none ${
        abierto ? "translate-x-0 shadow-xl" : "-translate-x-full"
      }`}
    >
      <div>
        <div className="relative px-5 pt-6 pb-5">
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar menú"
            className="lg:hidden absolute top-5 right-3 p-1.5 rounded-lg text-white/60 hover:bg-white/10 hover:text-white"
          >
            <X size={18} strokeWidth={2} aria-hidden="true" />
          </button>
          {/* Logo + nombre de la institución. El logo va sobre una
              pastilla blanca: cualquier logo (fondo blanco o transparente,
              a color) se lee igual sobre el verde oscuro. */}
          <div className="flex items-center gap-3 pr-6">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-white/20">
              {institucion?.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element -- URL externa configurada por la institución (mismo <img> que Configuración)
                <img src={institucion.logo_url} alt="" className="h-full w-full object-contain p-1" />
              ) : institucion ? (
                <span className="font-display text-[15px] font-bold text-teal-900">{inicialesInstitucion(institucion.nombre)}</span>
              ) : (
                <School size={20} className="text-teal-900/60" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0">
              <p className="m-0 font-display text-[15px] font-bold leading-tight text-white line-clamp-2" title={institucion?.nombre}>
                {institucion?.nombre ?? "Mi institución"}
              </p>
              <p className="m-0 mt-0.5 text-[11px] text-white/55 truncate">
                {institucion?.anio_escolar_activo ? `Año escolar ${institucion.anio_escolar_activo}` : institucion?.tipo || "Institución educativa"}
              </p>
            </div>
          </div>
        </div>

        {/* Inicio — único enlace de nivel superior: icono + label, SIN
            chevron, pastilla sólida igual que cualquier otro enlace real. */}
        <nav className="flex flex-col gap-0.5 px-3 pb-2">
          <Link
            href="/inicio"
            className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-semibold transition-colors ${
              pathname?.startsWith("/inicio") ? PASTILLA_ACTIVA : TEXTO_ENLACE
            }`}
          >
            <Home size={17} strokeWidth={2} aria-hidden="true" />
            Inicio
          </Link>
        </nav>

        <div className="h-px bg-white/10 mx-4 my-2" />

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
                      ? "bg-white/[0.07] text-white"
                      : "text-white/70 hover:bg-white/[0.08] hover:text-white"
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <span className={`flex h-6 w-6 items-center justify-center rounded-md ${CHIP_GRUPO[grupo.acento]}`}>
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
                  <div className="flex flex-col gap-0.5 mt-1 ml-[25px] pl-3.5 border-l border-white/15">
                    {grupo.enlaces.map((e) => renderEnlace(e, true))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
      </div>

      {/* Cuenta / cerrar sesión */}
      <div className="p-3 border-t border-white/10 bg-black/10">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#2BB3A0] to-[#1C8F80] flex items-center justify-center text-[12px] font-bold text-white flex-shrink-0">
            {(sesion?.email?.[0] || "?").toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="m-0 text-[12.5px] font-semibold text-white truncate" title={sesion?.email}>
              {sesion?.email}
            </p>
            <p className="m-0 text-[11px] text-white/55 capitalize">{sesion?.rol}</p>
          </div>
          <button
            onClick={cerrarSesion}
            aria-label="Cerrar sesión"
            className="flex-shrink-0 text-white/55 hover:text-white p-1.5 rounded-lg hover:bg-white/10"
          >
            <LogOut size={15} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>
  );
}
