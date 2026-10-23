"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import type { Cita, Institucion } from "@/types/api";

const ENLACES = [
  { href: "/estudiantes", label: "Padrón" },
  { href: "/campanas", label: "Campañas" },
  { href: "/documentos", label: "Documentos" },
  { href: "/pruebas", label: "Pruebas" },
  { href: "/agenda", label: "Agenda" },
  { href: "/casos-riesgo", label: "Casos en riesgo" },
  { href: "/academico", label: "Estructura académica" },
  { href: "/asentimiento", label: "Asentimiento informado" },
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

  return (
    <aside className="w-60 shrink-0 border-r border-border bg-white flex flex-col justify-between">
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
        <nav className="flex flex-col gap-1 px-3">
          {ENLACES.map((enlace) => {
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
