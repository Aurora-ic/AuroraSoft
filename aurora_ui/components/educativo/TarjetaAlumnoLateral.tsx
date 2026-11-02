"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { GraduationCap, UserRound } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import type { Persona, SeccionActual } from "@/types/api";

// 🆕 (sesión 2026-10-31) Columna lateral de los formularios que se abren
// DESDE la ficha de un alumno (Nueva cita, Registrar sesión): quién es, en
// qué sección está y — vía `children` — UN solo dato de contexto que cada
// formulario elige (próximas citas / última sesión). Mismo lenguaje visual
// que la vista previa de "Registrar alumno". Solo lectura, mismos GET que
// ya usa la ficha (/detalle y /historial-academico).
export function useAlumno(personaId: string) {
  const [alumno, setAlumno] = useState<Persona | null>(null);
  const [seccion, setSeccion] = useState<SeccionActual | null>(null);

  useEffect(() => {
    // Solo contexto: si falla, el formulario sigue siendo usable.
    apiClient
      .get<Persona>(`/admin/personas/${personaId}/detalle`)
      .then(setAlumno)
      .catch(() => {});
    apiClient
      .get<SeccionActual[]>(`/admin/personas/${personaId}/historial-academico`)
      .then((h) => setSeccion(h.find((x) => x.fecha_fin === null) ?? null))
      .catch(() => {});
  }, [personaId]);

  return { alumno, seccion };
}

export function TarjetaAlumnoLateral({
  personaId,
  alumno,
  seccion,
  children,
}: {
  personaId: string;
  alumno: Persona | null;
  seccion: SeccionActual | null;
  children?: React.ReactNode;
}) {
  const iniciales = alumno ? `${alumno.nombres.trim()[0] ?? ""}${alumno.apellidos.trim()[0] ?? ""}`.toUpperCase() : "";
  const ubicacion = seccion ? [seccion.nivel_educativo, seccion.grado, seccion.seccion].filter(Boolean).join(" · ") : null;

  return (
    <div className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
      <div className="bg-gradient-to-br from-teal-600/[0.10] via-teal-400/[0.06] to-transparent dark:from-teal-accent-dark/[0.10] p-4 border-b border-teal-600/15 dark:border-border-dark">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-900 to-teal-600 font-display text-[16px] font-bold text-white dark:from-teal-accent-dark/40 dark:to-teal-accent-dark/10 dark:text-teal-accent-dark">
            {iniciales || <UserRound size={20} aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <p className="m-0 font-display text-[15.5px] font-bold leading-tight text-teal-900 dark:text-ink-dark break-words">
              {alumno ? `${alumno.nombres} ${alumno.apellidos}` : "Cargando…"}
            </p>
            {alumno?.documento_identidad && (
              <p className="m-0 mt-0.5 font-mono text-[12px] text-ink/50 dark:text-ink-dark/50">{alumno.documento_identidad}</p>
            )}
          </div>
        </div>
        <p className="m-0 mt-3 inline-flex items-center gap-1.5 rounded-lg bg-surface/80 dark:bg-surface-dark px-2.5 py-1 text-[12px] text-teal-800 dark:text-teal-accent-dark ring-1 ring-teal-600/15 dark:ring-0">
          <GraduationCap size={12} aria-hidden="true" />
          {ubicacion ?? "Sin matrícula"}
        </p>
      </div>
      {children && <div className="p-4">{children}</div>}
      <div className="px-4 pb-4">
        <Link href={`/estudiantes/${personaId}`} className="text-[12px] font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
          Ver ficha completa →
        </Link>
      </div>
    </div>
  );
}

// Encabezado de un bloque de formulario (mismo de "Registrar alumno").
export function CabeceraBloque({ icono: Icono, titulo, descripcion }: { icono: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>; titulo: string; descripcion: string }) {
  return (
    <header className="flex items-center gap-2.5 px-4 py-3 bg-teal-600/[0.08] dark:bg-teal-accent-dark/[0.08] border-b border-teal-600/15 dark:border-teal-accent-dark/20">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark">
        <Icono size={16} aria-hidden={true} />
      </span>
      <div className="min-w-0">
        <h2 className="m-0 text-[14px] font-bold text-teal-900 dark:text-ink-dark">{titulo}</h2>
        <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>
      </div>
    </header>
  );
}
