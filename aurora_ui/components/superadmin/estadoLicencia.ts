import type { Institucion } from "@/types/api";

// Antes cada pantalla del panel interno reescribía su propio
// `licenciaVencida()`. Un solo cálculo, más el caso "por vencer" (dentro de
// DIAS_AVISO días) que el rediseño muestra como aviso en el resumen y en la
// lista de instituciones.
export const DIAS_AVISO = 30;

export type EstadoLicencia = "sin_caducidad" | "vigente" | "por_vencer" | "vencida";

export function diasParaVencer(institucion: Institucion): number | null {
  if (!institucion.fecha_vencimiento_licencia) return null;
  const vence = new Date(institucion.fecha_vencimiento_licencia).getTime();
  if (Number.isNaN(vence)) return null;
  return Math.ceil((vence - Date.now()) / 86_400_000);
}

export function estadoLicencia(institucion: Institucion): EstadoLicencia {
  const dias = diasParaVencer(institucion);
  if (dias === null) return "sin_caducidad";
  if (dias < 0) return "vencida";
  if (dias <= DIAS_AVISO) return "por_vencer";
  return "vigente";
}

export function formatearFecha(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
}
