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
    <div className="rounded-xl border border-seccion-600/15 dark:border-seccion-claro/20 bg-seccion-600/[0.035] dark:bg-seccion-claro/[0.05] shadow-sm overflow-hidden">
      <div className="bg-gradient-to-br from-seccion-600/[0.10] via-seccion-400/[0.06] to-transparent dark:from-seccion-claro/[0.10] p-4 border-b border-seccion-600/15 dark:border-border-dark">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-seccion-900 to-seccion-600 font-display text-[16px] font-bold text-white dark:from-seccion-claro/40 dark:to-seccion-claro/10 dark:text-seccion-claro">
            {iniciales || <UserRound size={20} aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <p className="font-display text-[15.5px] font-bold leading-tight text-seccion-900 dark:text-ink-dark break-words">
              {alumno ? `${alumno.nombres} ${alumno.apellidos}` : "Cargando…"}
            </p>
            {alumno?.documento_identidad && (
              <p className="mt-0.5 font-mono text-[12px] text-ink/65 dark:text-ink-dark/55">{alumno.documento_identidad}</p>
            )}
          </div>
        </div>
        <p className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-surface/80 dark:bg-surface-dark px-2.5 py-1 text-[12px] text-seccion-900 dark:text-seccion-claro ring-1 ring-seccion-600/15 dark:ring-0">
          <GraduationCap size={12} aria-hidden="true" />
          {ubicacion ?? "Sin matrícula"}
        </p>
      </div>
      {children && <div className="p-4">{children}</div>}
      <div className="px-4 pb-4">
        <Link href={`/estudiantes/${personaId}`} className="text-[12px] font-semibold text-seccion-700 dark:text-seccion-claro hover:underline">
          Ver ficha completa →
        </Link>
      </div>
    </div>
  );
}

// Encabezado de un bloque de formulario (mismo de "Registrar alumno").
export function CabeceraBloque({ icono: Icono, titulo, descripcion }: { icono: React.ComponentType<{ size?: number; "aria-hidden"?: boolean }>; titulo: string; descripcion: string }) {
  return (
    <header className="flex items-center gap-2.5 px-4 py-3 bg-seccion-600/[0.08] dark:bg-seccion-claro/[0.08] border-b border-seccion-600/15 dark:border-seccion-claro/20">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-seccion-600 text-white dark:bg-seccion-claro dark:text-mist-dark">
        <Icono size={16} aria-hidden={true} />
      </span>
      <div className="min-w-0">
        <h2 className="text-[14px] font-bold text-seccion-900 dark:text-ink-dark">{titulo}</h2>
        <p className="text-[12px] text-ink/65 dark:text-ink-dark/55">{descripcion}</p>
      </div>
    </header>
  );
}
