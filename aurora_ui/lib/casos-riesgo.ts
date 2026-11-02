import type { EstadoCaso, UrgenciaCaso } from "@/types/api";

// 🆕 (sesión 2026-11-01) Etiquetas y colores de la bandeja de casos en
// riesgo. Urgente en ROJO (inconfundible, triaje clínico); alerta en ÁMBAR
// (la semántica de riesgo clínico de toda la app); seguimiento en pizarra.

export const ETIQUETA_URGENCIA: Record<UrgenciaCaso, string> = {
  urgente: "Urgente",
  alerta: "Alerta",
  seguimiento: "Seguimiento",
};

export const DESCRIPCION_URGENCIA: Record<UrgenciaCaso, string> = {
  urgente: "Respuesta positiva en un ítem crítico",
  alerta: "Resultado en el tramo de alerta del baremo",
  seguimiento: "Antecedentes clínicos externos",
};

export const CLASE_URGENCIA: Record<UrgenciaCaso, { insignia: string; tarjeta: string }> = {
  urgente: {
    insignia: "bg-red-600 text-white dark:bg-red-500",
    tarjeta: "border-red-300 border-l-red-600 bg-red-50/60 dark:border-red-500/40 dark:border-l-red-500 dark:bg-red-500/[0.07]",
  },
  alerta: {
    insignia: "bg-amber/20 text-amber-800 dark:bg-amber/20 dark:text-amber",
    tarjeta: "border-amber/35 border-l-amber bg-amber/[0.05] dark:bg-amber/[0.05]",
  },
  seguimiento: {
    insignia: "bg-acento-pizarra/15 text-acento-pizarra dark:bg-acento-pizarra-dark/20 dark:text-acento-pizarra-dark",
    tarjeta:
      "border-acento-pizarra/25 border-l-acento-pizarra bg-acento-pizarra/[0.04] dark:border-acento-pizarra-dark/30 dark:border-l-acento-pizarra-dark dark:bg-acento-pizarra-dark/[0.05]",
  },
};

export const ESTADOS_CASO: EstadoCaso[] = ["nuevo", "en_atencion", "derivado", "en_seguimiento", "cerrado"];

export const ETIQUETA_ESTADO: Record<EstadoCaso, string> = {
  nuevo: "Nuevo",
  en_atencion: "En atención",
  derivado: "Derivado",
  en_seguimiento: "En seguimiento",
  cerrado: "Cerrado",
};
