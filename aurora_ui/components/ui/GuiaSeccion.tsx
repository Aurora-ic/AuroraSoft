"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { BookOpen, ChevronDown, X, type LucideIcon } from "lucide-react";

// 🆕 (2026-11-17, plan de UX fase 3) Inducción breve de una sección: 3 pasos
// y, si hace falta, algo más debajo. Nació en Documentos (GuiaDocumentos) y
// se generalizó para Campañas, Casos en riesgo y Pruebas. Se puede ocultar;
// queda recordado en este navegador (solo una preferencia de vista). Toma el
// color de la sección en la que está (`seccion-*`, app/globals.css).

export type PasoGuia = { icono: LucideIcon; titulo: string; texto: string };

const oyentes = new Set<() => void>();

function leer(clave: string): boolean {
  try {
    return window.localStorage.getItem(clave) === "1";
  } catch {
    return false;
  }
}

function guardar(clave: string, oculta: boolean) {
  try {
    if (oculta) window.localStorage.setItem(clave, "1");
    else window.localStorage.removeItem(clave);
  } catch {
    // Sin almacenamiento (modo privado): solo dura esta visita.
  }
  oyentes.forEach((f) => f());
}

function suscribir(f: () => void) {
  oyentes.add(f);
  return () => oyentes.delete(f);
}

export function GuiaSeccion({
  clave,
  titulo,
  pasos,
  children,
}: {
  /** Clave en localStorage para recordar si se ocultó. */
  clave: string;
  titulo: string;
  pasos: PasoGuia[];
  children?: ReactNode;
}) {
  const oculta = useSyncExternalStore(suscribir, () => leer(clave), () => false);

  if (oculta) {
    return (
      <button
        type="button"
        onClick={() => guardar(clave, false)}
        className="self-start inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-seccion-700 hover:underline dark:text-seccion-claro"
      >
        <BookOpen size={13} aria-hidden="true" />
        {titulo}
        <ChevronDown size={12} aria-hidden="true" />
      </button>
    );
  }

  return (
    // Sin aria-labelledby a propósito: una región con nombre ("¿Cómo se usa
    // esta sección?") choca con las etiquetas de los campos de la pantalla
    // ("Sección", "Prueba") para quien navega por etiquetas.
    <section
      className="relative rounded-xl border border-seccion-600/15 bg-seccion-600/[0.035] px-4 py-4 sm:px-5 dark:border-seccion-claro/20 dark:bg-seccion-claro/[0.05]"
    >
      <button
        type="button"
        onClick={() => guardar(clave, true)}
        className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-ink/65 hover:bg-ink/5 dark:text-ink-dark/55 dark:hover:bg-white/5"
      >
        <X size={12} aria-hidden="true" />
        Entendido, ocultar
      </button>
      <h2 className="m-0 flex items-center gap-2 pr-32 text-[14.5px] font-bold text-ink dark:text-ink-dark">
        <BookOpen size={16} className="text-seccion-700 dark:text-seccion-claro" aria-hidden="true" />
        {titulo}
      </h2>
      <ol className="m-0 mt-3 grid list-none gap-2.5 p-0 md:grid-cols-3">
        {pasos.map(({ icono: Icono, titulo: t, texto }) => (
          <li key={t} className="flex gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 dark:border-border-dark dark:bg-surface-dark">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-seccion-600/10 text-seccion-700 dark:bg-seccion-claro/15 dark:text-seccion-claro">
              <Icono size={15} aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-bold text-ink dark:text-ink-dark">{t}</span>
              <span className="block text-[12.5px] leading-snug text-ink/65 dark:text-ink-dark/60">{texto}</span>
            </span>
          </li>
        ))}
      </ol>
      {children}
    </section>
  );
}
