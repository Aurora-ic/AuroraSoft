import type { LucideIcon } from "lucide-react";
import { ClipboardCheck, PenLine, Printer, Wand2 } from "lucide-react";
import { ACENTOS } from "@/lib/acentos";
import { INFO_MODO, MODO_TIPO_SECCION, type ModoSeccion } from "@/lib/documentos-constantes";
import type { TipoSeccionDocumento } from "@/types/api";

// 🆕 (2026-11-17) El "cómo se llena" de cada sección, igual en las tres
// pantallas de Documentos (constructor, nuevo documento, llenar documento):
// mismo color, mismo ícono, misma frase. Ámbar NO se usa aquí: en AuroraSoft
// es solo riesgo clínico (docs/frontend.md).

// 🆕 (2026-11-17, plan de UX fase 2) "Una pantalla, un color": los 4 modos
// van en TONOS del violeta de Documentos (antes violeta, azul, pizarra y
// teal en la misma pantalla). Los distinguen el ícono, la palabra y el
// relleno: sólido = lo escribes tú, suave = eliges, contorno = se imprime en
// blanco, gris = sale solo (lo que menos atención pide).
export const ESTILO_MODO: Record<ModoSeccion, { clase: string; icono: LucideIcon }> = {
  escribes: {
    clase: "bg-acento-violeta text-white dark:bg-acento-violeta-dark dark:text-mist-dark",
    icono: PenLine,
  },
  eliges: { clase: ACENTOS.violeta.chip, icono: ClipboardCheck },
  automatica: { clase: "bg-ink/[0.06] text-ink/60 dark:bg-white/[0.06] dark:text-ink-dark/60", icono: Wand2 },
  imprimir: {
    clase: "border border-acento-violeta/50 text-acento-violeta dark:border-acento-violeta-dark/50 dark:text-acento-violeta-dark",
    icono: Printer,
  },
};

export function ChipModo({ modo, tipo, className = "" }: { modo?: ModoSeccion; tipo?: TipoSeccionDocumento; className?: string }) {
  const m = modo ?? (tipo ? MODO_TIPO_SECCION[tipo] : "escribes");
  const { clase, icono: Icono } = ESTILO_MODO[m];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap ${clase} ${className}`}
    >
      <Icono size={11} aria-hidden="true" />
      {INFO_MODO[m].etiqueta}
    </span>
  );
}

/** Las 4 maneras de llenar una sección, con su frase — para guías e inducción. */
export function LeyendaModos({ modos = ["escribes", "eliges", "automatica", "imprimir"] }: { modos?: ModoSeccion[] }) {
  return (
    <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
      {modos.map((m) => (
        <li key={m} className="flex items-start gap-2 text-[12.5px] leading-snug text-ink/70 dark:text-ink-dark/70">
          <ChipModo modo={m} className="mt-px" />
          <span>{INFO_MODO[m].frase}</span>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Miniatura: un dibujo esquemático de cómo sale cada tipo en el PDF, para
// distinguir de un vistazo "texto para redactar" de "formato en blanco".
// ---------------------------------------------------------------------------
const L = "rounded-full bg-ink/15 dark:bg-ink-dark/20";
const LD = "rounded-full bg-ink/30 dark:bg-ink-dark/35";

function Linea({ w, oscura = false }: { w: string; oscura?: boolean }) {
  return <span className={`block h-1.5 ${oscura ? LD : L}`} style={{ width: w }} />;
}

function Hueco({ w }: { w: string }) {
  return <span className="block h-1.5 border-b border-dashed border-ink/35 dark:border-ink-dark/40" style={{ width: w }} />;
}

export function MiniaturaSeccion({ tipo, className = "" }: { tipo: TipoSeccionDocumento; className?: string }) {
  let dibujo: React.ReactNode;
  switch (tipo) {
    case "encabezado":
      dibujo = (
        <div className="flex items-center gap-2">
          <span className="h-6 w-6 rounded bg-acento-violeta/20" />
          <div className="flex-1 space-y-1">
            <Linea w="70%" oscura />
            <Linea w="45%" />
          </div>
        </div>
      );
      break;
    case "datos_filiacion":
    case "datos_familiares":
      dibujo = (
        <div className="space-y-1.5">
          {["55%", "70%", "40%"].map((w, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <Linea w="22%" oscura />
              <Linea w={w} />
            </div>
          ))}
        </div>
      );
      break;
    case "texto_libre":
      dibujo = (
        <div className="space-y-1.5">
          <Linea w="35%" oscura />
          <Linea w="100%" />
          <Linea w="95%" />
          <Linea w="80%" />
        </div>
      );
      break;
    case "grupo_campos":
      dibujo = (
        <div className="grid grid-cols-2 gap-x-2 gap-y-1.5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-1">
              <Linea w="35%" oscura />
              <Linea w="55%" />
            </div>
          ))}
        </div>
      );
      break;
    case "tabla_dinamica":
      dibujo = (
        <div className="grid grid-cols-3 overflow-hidden rounded-sm border border-ink/20 dark:border-ink-dark/25">
          {Array.from({ length: 9 }).map((_, i) => (
            <span key={i} className={`h-2.5 border-ink/15 dark:border-ink-dark/20 ${i < 3 ? "bg-ink/15 dark:bg-ink-dark/20" : ""} ${i % 3 ? "border-l" : ""} ${i >= 3 ? "border-t" : ""}`} />
          ))}
        </div>
      );
      break;
    case "resultados_prueba":
    case "resultados_prueba_multiple":
      dibujo = (
        <div className="space-y-1.5">
          <Linea w="50%" oscura />
          {(tipo === "resultados_prueba" ? [1] : [1, 2]).map((i) => (
            <div key={i} className="flex items-center gap-1.5">
              <Linea w="30%" />
              <span className="h-2 w-10 rounded-sm bg-acento-violeta/35" />
              <Linea w="25%" />
            </div>
          ))}
        </div>
      );
      break;
    case "grafico_barras":
      dibujo = (
        <div className="flex h-8 items-end gap-1.5 border-b border-l border-ink/25 pl-1 dark:border-ink-dark/30">
          {[60, 85, 40, 70].map((h, i) => (
            <span key={i} className="w-3 rounded-t-sm bg-acento-violeta/40" style={{ height: `${h}%` }} />
          ))}
        </div>
      );
      break;
    case "imagen_anexo":
      dibujo = (
        <div className="flex h-8 items-center justify-center rounded-sm border border-dashed border-ink/30 dark:border-ink-dark/35">
          <span className="h-4 w-6 rounded-sm bg-ink/15 dark:bg-ink-dark/20" />
        </div>
      );
      break;
    case "firma":
    case "firma_doble":
    case "firma_triple":
      dibujo = (
        <div className={`grid gap-2 ${tipo === "firma" ? "grid-cols-1 px-6" : tipo === "firma_doble" ? "grid-cols-2" : "grid-cols-3"}`}>
          {Array.from({ length: tipo === "firma" ? 1 : tipo === "firma_doble" ? 2 : 3 }).map((_, i) => (
            <div key={i} className="space-y-1 pt-2">
              <span className="block border-t border-ink/45 dark:border-ink-dark/45" />
              <Linea w="70%" oscura />
              <Linea w="50%" />
            </div>
          ))}
        </div>
      );
      break;
    case "ficha_imprimible":
      dibujo = (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Linea w="22%" oscura />
            <Hueco w="60%" />
          </div>
          {[0, 1].map((i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-[2px] border border-ink/45 dark:border-ink-dark/50" />
              <Linea w="50%" />
            </div>
          ))}
          <Hueco w="95%" />
        </div>
      );
      break;
  }
  return (
    <div
      aria-hidden="true"
      className={`rounded-md border border-border bg-white px-2.5 py-2 shadow-[0_1px_0_rgba(0,0,0,0.03)] dark:border-border-dark dark:bg-surface-raised-dark ${className}`}
    >
      {dibujo}
    </div>
  );
}
