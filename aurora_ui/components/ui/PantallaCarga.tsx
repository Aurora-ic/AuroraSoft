"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { ACENTOS, ACENTO_POR_RUTA } from "@/lib/acentos";
import { AvisoCargando, EsqueletoBloque, EsqueletoTarjetas } from "@/components/ui/Esqueleto";

// 🆕 (2026-11-17, plan de UX fase 1) Pantallas de carga.
//
// - PantallaCargaMarca: al abrir o refrescar el sistema, mientras se
//   confirma la sesión. Antes era una pantalla gris con "Cargando…" tenue,
//   sin logo y siempre clara aunque la persona usara el modo oscuro.
// - EsqueletoSeccion: lo que se ve al instante al hacer clic en el menú,
//   mientras llega la página (app/(educativo)/loading.tsx). La franja toma
//   el color de la sección a la que se va (lib/acentos.ts), así se nota en
//   el acto que el clic funcionó y a dónde lleva.

export function PantallaCargaMarca({ texto = "Preparando tu espacio…" }: { texto?: string }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-5 bg-mist dark:bg-mist-dark px-4">
      <Image src="/logo.png" alt="AuroraSoft" width={140} height={99} priority className="h-14 w-auto animate-pulse" />
      <div className="h-1 w-40 overflow-hidden rounded-full bg-border dark:bg-border-dark" aria-hidden="true">
        <div className="h-full w-1/3 rounded-full bg-teal-600 dark:bg-teal-accent-dark animate-[deslizar_1.2s_ease-in-out_infinite]" />
      </div>
      <p role="status" className="m-0 text-[13px] text-ink/55 dark:text-ink-dark/55">
        {texto}
      </p>
    </div>
  );
}

function acentoDeRuta(pathname: string | null) {
  const ruta = Object.keys(ACENTO_POR_RUTA).find((r) => pathname?.startsWith(r));
  return ruta ? ACENTO_POR_RUTA[ruta] : "teal";
}

export function EsqueletoSeccion() {
  const pathname = usePathname();
  const acento = ACENTOS[acentoDeRuta(pathname)];
  return (
    <div className="max-w-7xl mx-auto w-full flex flex-col gap-5">
      <AvisoCargando />
      <div
        aria-hidden="true"
        className={`bg-gradient-to-br ${acento.degradado} dark:from-surface-raised-dark dark:to-surface-dark dark:border dark:border-border-dark dark:border-l-4 ${acento.borde} rounded-2xl px-5 py-5 sm:px-6 min-h-[7.5rem] flex items-center gap-3.5 opacity-90`}
      >
        <span className="hidden sm:block h-11 w-11 shrink-0 rounded-xl bg-white/15 dark:bg-white/5" />
        <div className="flex-1 space-y-2.5">
          <div className="h-5 w-48 max-w-full animate-pulse rounded bg-white/25 dark:bg-white/10" />
          <div className="h-3 w-80 max-w-full animate-pulse rounded bg-white/15 dark:bg-white/5" />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <EsqueletoTarjetas cantidad={4} />
      </div>
      <EsqueletoBloque lineas={5} />
    </div>
  );
}
