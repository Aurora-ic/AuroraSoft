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
  /** 🆕 (sesión 2026-10-31) Fondo + borde de un bloque CHICO de la sección
   *  (acceso rápido, KPI): tinte visible. */
  fondo: string;
  /** Fondo + borde de un bloque GRANDE (tarjeta con tabla, formulario,
   *  gráfico): tinte tenue para no competir con el contenido. */
  fondoSuave: string;
  /** Franja de cabecera de un bloque grande (sobre `fondoSuave`). */
  cabecera: string;
  /** Cuadro del ícono en sólido (ícono blanco) — sobre los fondos tintados. */
  chipSolido: string;
};

export const ACENTOS: Record<Acento, ClasesAcento> = {
  teal: {
    chip: "bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark",
    chipOscuro: "dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark",
    texto: "text-teal-700 dark:text-teal-accent-dark",
    degradado: "from-teal-900 to-teal-600",
    solido: "bg-teal-600 dark:bg-teal-accent-dark",
    borde: "border-l-teal-600 dark:border-l-teal-accent-dark",
    fondo: "bg-teal-600/[0.07] border-teal-600/20 dark:bg-teal-accent-dark/[0.07] dark:border-teal-accent-dark/25",
    fondoSuave: "bg-teal-600/[0.035] border-teal-600/15 dark:bg-teal-accent-dark/[0.05] dark:border-teal-accent-dark/20",
    cabecera: "bg-teal-600/[0.08] border-teal-600/15 dark:bg-teal-accent-dark/[0.08] dark:border-teal-accent-dark/20",
    chipSolido: "bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark",
  },
  azul: {
    chip: "bg-acento-azul/10 text-acento-azul dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark",
    chipOscuro: "dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark",
    texto: "text-acento-azul dark:text-acento-azul-dark",
    degradado: "from-teal-900 to-acento-azul",
    solido: "bg-acento-azul dark:bg-acento-azul-dark",
    borde: "border-l-acento-azul dark:border-l-acento-azul-dark",
    fondo: "bg-acento-azul/[0.07] border-acento-azul/20 dark:bg-acento-azul-dark/[0.07] dark:border-acento-azul-dark/25",
    fondoSuave: "bg-acento-azul/[0.035] border-acento-azul/15 dark:bg-acento-azul-dark/[0.05] dark:border-acento-azul-dark/20",
    cabecera: "bg-acento-azul/[0.08] border-acento-azul/15 dark:bg-acento-azul-dark/[0.08] dark:border-acento-azul-dark/20",
    chipSolido: "bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark",
  },
  violeta: {
    chip: "bg-acento-violeta/10 text-acento-violeta dark:bg-acento-violeta-dark/15 dark:text-acento-violeta-dark",
    chipOscuro: "dark:bg-acento-violeta-dark/15 dark:text-acento-violeta-dark",
    texto: "text-acento-violeta dark:text-acento-violeta-dark",
    degradado: "from-teal-900 to-acento-violeta",
    solido: "bg-acento-violeta dark:bg-acento-violeta-dark",
    borde: "border-l-acento-violeta dark:border-l-acento-violeta-dark",
    fondo: "bg-acento-violeta/[0.07] border-acento-violeta/20 dark:bg-acento-violeta-dark/[0.07] dark:border-acento-violeta-dark/25",
    fondoSuave: "bg-acento-violeta/[0.035] border-acento-violeta/15 dark:bg-acento-violeta-dark/[0.05] dark:border-acento-violeta-dark/20",
    cabecera: "bg-acento-violeta/[0.08] border-acento-violeta/15 dark:bg-acento-violeta-dark/[0.08] dark:border-acento-violeta-dark/20",
    chipSolido: "bg-acento-violeta text-white dark:bg-acento-violeta-dark dark:text-mist-dark",
  },
  pizarra: {
    chip: "bg-acento-pizarra/10 text-acento-pizarra dark:bg-acento-pizarra-dark/15 dark:text-acento-pizarra-dark",
    chipOscuro: "dark:bg-acento-pizarra-dark/15 dark:text-acento-pizarra-dark",
    texto: "text-acento-pizarra dark:text-acento-pizarra-dark",
    degradado: "from-teal-900 to-acento-pizarra",
    solido: "bg-acento-pizarra dark:bg-acento-pizarra-dark",
    borde: "border-l-acento-pizarra dark:border-l-acento-pizarra-dark",
    fondo: "bg-acento-pizarra/[0.08] border-acento-pizarra/20 dark:bg-acento-pizarra-dark/[0.08] dark:border-acento-pizarra-dark/25",
    fondoSuave: "bg-acento-pizarra/[0.05] border-acento-pizarra/20 dark:bg-acento-pizarra-dark/[0.06] dark:border-acento-pizarra-dark/20",
    cabecera: "bg-acento-pizarra/[0.09] border-acento-pizarra/15 dark:bg-acento-pizarra-dark/[0.09] dark:border-acento-pizarra-dark/20",
    chipSolido: "bg-acento-pizarra text-white dark:bg-acento-pizarra-dark dark:text-mist-dark",
  },
  riesgo: {
    chip: "bg-amber/15 text-amber",
    chipOscuro: "dark:bg-amber/15 dark:text-amber",
    texto: "text-amber-700 dark:text-amber",
    degradado: "from-teal-900 to-amber",
    solido: "bg-amber",
    borde: "border-l-amber",
    fondo: "bg-amber/[0.09] border-amber/30 dark:bg-amber/[0.07] dark:border-amber/25",
    fondoSuave: "bg-amber/[0.06] border-amber/25 dark:bg-amber/[0.05] dark:border-amber/20",
    cabecera: "bg-amber/[0.12] border-amber/25 dark:bg-amber/[0.09] dark:border-amber/20",
    chipSolido: "bg-amber text-white dark:text-mist-dark",
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
