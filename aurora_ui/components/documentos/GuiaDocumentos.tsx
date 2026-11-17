"use client";

import { useSyncExternalStore } from "react";
import { BookOpen, ChevronDown, Copy, FilePlus2, LayoutTemplate, X } from "lucide-react";
import { ACENTOS } from "@/lib/acentos";
import { LeyendaModos } from "@/components/documentos/ModoSeccion";

// 🆕 (2026-11-17, a pedido de la psicóloga del piloto) Inducción breve a
// Documentos: los tres conceptos (catálogo, plantilla, documento) y las 4
// maneras en que se llena una parte. Se puede ocultar; queda recordado en
// este navegador (solo una preferencia de vista, nada que deba persistir).

const VIOLETA = ACENTOS.violeta;
const CLAVE = "aurora.guia-documentos.oculta";
const oyentes = new Set<() => void>();

function leerOculta(): boolean {
  try {
    return window.localStorage.getItem(CLAVE) === "1";
  } catch {
    return false;
  }
}

function guardarOculta(valor: boolean) {
  try {
    if (valor) window.localStorage.setItem(CLAVE, "1");
    else window.localStorage.removeItem(CLAVE);
  } catch {
    // Sin almacenamiento (modo privado): solo dura esta visita.
  }
  oyentes.forEach((f) => f());
}

function suscribir(f: () => void) {
  oyentes.add(f);
  return () => oyentes.delete(f);
}

const PASOS = [
  {
    icono: Copy,
    titulo: "1. Catálogo",
    texto: "Formatos listos (informe escolar, para padres, plan de intervención…). Clonas el que te sirva.",
  },
  {
    icono: LayoutTemplate,
    titulo: "2. Mis plantillas",
    texto: "Tu copia del formato: el molde. Decides qué partes tiene y en qué orden. Se arma una vez.",
  },
  {
    icono: FilePlus2,
    titulo: "3. Nuevo documento",
    texto: "Eliges la plantilla y el alumno, completas solo lo que te toca y generas el PDF.",
  },
];

export function GuiaDocumentos() {
  const oculta = useSyncExternalStore(suscribir, leerOculta, () => false);

  if (oculta) {
    return (
      <button
        type="button"
        onClick={() => guardarOculta(false)}
        className={`self-start inline-flex items-center gap-1.5 text-[12.5px] font-semibold hover:underline ${VIOLETA.texto}`}
      >
        <BookOpen size={13} aria-hidden="true" />
        ¿Cómo funcionan los documentos?
        <ChevronDown size={12} aria-hidden="true" />
      </button>
    );
  }

  return (
    <section aria-labelledby="titulo-guia-documentos" className={`relative rounded-xl border px-4 py-4 sm:px-5 ${VIOLETA.fondoSuave}`}>
      <button
        type="button"
        onClick={() => guardarOculta(true)}
        className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-medium text-ink/55 hover:bg-ink/5 dark:text-ink-dark/55 dark:hover:bg-white/5"
      >
        <X size={12} aria-hidden="true" />
        Entendido, ocultar
      </button>
      <h2 id="titulo-guia-documentos" className="m-0 flex items-center gap-2 pr-32 text-[14.5px] font-bold text-ink dark:text-ink-dark">
        <BookOpen size={16} className={VIOLETA.texto} aria-hidden="true" />
        ¿Cómo funcionan los documentos?
      </h2>
      <ol className="m-0 mt-3 grid list-none gap-2.5 p-0 md:grid-cols-3">
        {PASOS.map(({ icono: Icono, titulo, texto }) => (
          <li key={titulo} className="flex gap-2.5 rounded-lg border border-border bg-surface px-3 py-2.5 dark:border-border-dark dark:bg-surface-dark">
            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${VIOLETA.chip}`}>
              <Icono size={15} aria-hidden="true" />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-bold text-ink dark:text-ink-dark">{titulo}</span>
              <span className="block text-[12.5px] leading-snug text-ink/60 dark:text-ink-dark/60">{texto}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="m-0 mt-3.5 mb-2 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">
        Cada parte de un documento lleva una etiqueta que dice cómo se llena:
      </p>
      <LeyendaModos />
    </section>
  );
}
