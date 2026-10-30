// 🆕 Identidad de color por SECCIÓN (sesión 2026-10-30) — ver los tokens
// `--color-acento-*` en app/globals.css para el porqué de cada color.
//
// Reglas de uso (para que el color sume orden y no ruido):
// - El acento va en el ÍCONO y su "chip", y como mucho en una franja o
//   degradado de encabezado. Nunca en fondos de tarjeta completos, nunca en
//   texto de lectura, nunca en botones primarios (esos siguen en teal de
//   marca en toda la app: una acción se ve igual en cualquier sección).
// - "riesgo" (ámbar) NO es un acento de sección: es semántico, solo para
//   pantallas/cifras de alerta clínica real.
// - Clases escritas completas (no armadas con template strings) para que
//   Tailwind las detecte al compilar.

export type Acento = "teal" | "azul" | "violeta" | "pizarra" | "riesgo";

type ClasesAcento = {
  /** Fondo suave + color del ícono, para el cuadrito que envuelve un ícono. */
  chip: string;
  /** Solo la parte de modo oscuro de `chip` (sobre el degradado, que en
   *  claro lleva el ícono en blanco). */
  chipOscuro: string;
  /** Solo el color del ícono/texto de acento. */
  texto: string;
  /** Degradado del encabezado "destacado" (siempre parte del teal de marca). */
  degradado: string;
  /** Punto/barra sólida (indicadores pequeños). */
  solido: string;
  /** Borde lateral de acento. */
  borde: string;
};

export const ACENTOS: Record<Acento, ClasesAcento> = {
  teal: {
    chip: "bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark",
    chipOscuro: "dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark",
    texto: "text-teal-700 dark:text-teal-accent-dark",
    degradado: "from-teal-900 to-teal-600",
    solido: "bg-teal-600 dark:bg-teal-accent-dark",
    borde: "border-l-teal-600 dark:border-l-teal-accent-dark",
  },
  azul: {
    chip: "bg-acento-azul/10 text-acento-azul dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark",
    chipOscuro: "dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark",
    texto: "text-acento-azul dark:text-acento-azul-dark",
    degradado: "from-teal-900 to-acento-azul",
    solido: "bg-acento-azul dark:bg-acento-azul-dark",
    borde: "border-l-acento-azul dark:border-l-acento-azul-dark",
  },
  violeta: {
    chip: "bg-acento-violeta/10 text-acento-violeta dark:bg-acento-violeta-dark/15 dark:text-acento-violeta-dark",
    chipOscuro: "dark:bg-acento-violeta-dark/15 dark:text-acento-violeta-dark",
    texto: "text-acento-violeta dark:text-acento-violeta-dark",
    degradado: "from-teal-900 to-acento-violeta",
    solido: "bg-acento-violeta dark:bg-acento-violeta-dark",
    borde: "border-l-acento-violeta dark:border-l-acento-violeta-dark",
  },
  pizarra: {
    chip: "bg-acento-pizarra/10 text-acento-pizarra dark:bg-acento-pizarra-dark/15 dark:text-acento-pizarra-dark",
    chipOscuro: "dark:bg-acento-pizarra-dark/15 dark:text-acento-pizarra-dark",
    texto: "text-acento-pizarra dark:text-acento-pizarra-dark",
    degradado: "from-teal-900 to-acento-pizarra",
    solido: "bg-acento-pizarra dark:bg-acento-pizarra-dark",
    borde: "border-l-acento-pizarra dark:border-l-acento-pizarra-dark",
  },
  riesgo: {
    chip: "bg-amber/15 text-amber",
    chipOscuro: "dark:bg-amber/15 dark:text-amber",
    texto: "text-amber-700 dark:text-amber",
    degradado: "from-teal-900 to-amber",
    solido: "bg-amber",
    borde: "border-l-amber",
  },
};

// Sección -> acento, una sola fuente de verdad (Sidebar, encabezados, Inicio).
export const ACENTO_POR_RUTA: Record<string, Acento> = {
  "/estudiantes": "teal",
  "/academico": "teal",
  "/campanas": "azul",
  "/pruebas": "azul",
  "/casos-riesgo": "riesgo",
  "/documentos": "violeta",
  "/asentimiento": "violeta",
  "/agenda": "pizarra",
  "/configuracion": "pizarra",
};
