"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { BusquedaGlobal } from "@/components/educativo/BusquedaGlobal";
import type { Cita, Institucion } from "@/types/api";

type Enlace = { href: string; label: string };
type Grupo = { titulo: string; enlaces: Enlace[] };

// 🆕 Reorganización por flujo de trabajo (sesión 2026-10-24) — antes era
// una lista plana de 10 ítems con el mismo peso visual para todo. "Inicio"
// queda afuera de los grupos a propósito (es el aterrizaje, no una sección
// más); el resto se agrupa en 4 categorías, colapsables, con el grupo que
// contiene la ruta activa expandido por defecto.
const GRUPOS: Grupo[] = [
  {
    titulo: "Estudiantes",
    enlaces: [
      { href: "/estudiantes", label: "Padrón" },
      { href: "/academico", label: "Estructura académica" },
    ],
  },
  {
    titulo: "Evaluación",
    enlaces: [
      { href: "/campanas", label: "Campañas" },
      { href: "/pruebas", label: "Pruebas" },
      { href: "/casos-riesgo", label: "Casos en riesgo" },
    ],
  },
  {
    titulo: "Documentos",
    enlaces: [
      { href: "/documentos", label: "Documentos" },
      { href: "/asentimiento", label: "Asentimiento informado" },
    ],
  },
  {
    titulo: "Gestión",
    enlaces: [
      { href: "/agenda", label: "Agenda" },
      { href: "/configuracion", label: "Configuración" },
    ],
  },
];

export function SidebarEducativo() {
  const pathname = usePathname();
  const { cerrarSesion } = useAuth();
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

  function renderEnlace(enlace: Enlace) {
    const activo = pathname?.startsWith(enlace.href);
    return (
      <Link
        key={enlace.href}
        href={enlace.href}
        className={`rounded-card px-3 py-2 text-sm transition-colors flex items-center justify-between ${
          activo ? "bg-teal-900 text-white" : "text-ink hover:bg-mist"
        }`}
      >
        {enlace.label}
        {enlace.href === "/agenda" && !!citasHoy && (
          <span
            className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold leading-none ${
              activo ? "bg-white/20 text-white" : "bg-teal-600/10 text-teal-900"
            }`}
          >
            {citasHoy}
          </span>
        )}
      </Link>
    );
  }

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-white flex flex-col justify-between overflow-y-auto">
      <div>
        <div className="px-5 py-6">
          <div className="flex items-center gap-2">
            <Image src="/logo.png" alt="" width={140} height={99} className="h-6 w-auto" />
            <span className="font-display text-lg text-teal-900">AuroraSoft</span>
          </div>
          {institucion && (
            <p className="mt-1.5 text-xs text-ink/50 truncate" title={institucion.nombre}>
              {institucion.nombre}
            </p>
          )}
        </div>
        <div className="px-3 pb-3">
          <BusquedaGlobal />
        </div>
        <nav className="flex flex-col gap-1 px-3 pb-3">
          {renderEnlace({ href: "/inicio", label: "Inicio" })}
        </nav>
        <nav className="flex flex-col gap-1 px-3">
          {GRUPOS.map((grupo) => {
            const abierto = abiertos.has(grupo.titulo);
            return (
              <div key={grupo.titulo} className="mb-1">
                <button
                  onClick={() => alternarGrupo(grupo.titulo)}
                  className="w-full flex items-center justify-between px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-ink/40 hover:text-ink/70"
                >
                  {grupo.titulo}
                  <span className={`transition-transform ${abierto ? "rotate-90" : ""}`}>›</span>
                </button>
                {abierto && <div className="flex flex-col gap-1 mt-0.5">{grupo.enlaces.map(renderEnlace)}</div>}
              </div>
            );
          })}
        </nav>
      </div>
      <div className="p-3">
        <button onClick={cerrarSesion} className="w-full rounded-card px-3 py-2 text-sm text-left text-ink/60 hover:bg-mist">
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}
