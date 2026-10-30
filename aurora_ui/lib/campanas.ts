// 🆕 Hallazgo real (sesión 2026-10-25, reportado por el usuario y
// confirmado contra la BD real: 4 campañas de producción con
// estado="activa" y fecha_fin ya pasada — ids 2155/2162/2163/2177).
//
// El backend SÍ distingue una campaña "activa" de una campaña vencida por
// fecha: `crud.campana_esta_expirada()` es el candado real que usan los 7
// puntos del flujo de examen + matricular_roster_en_campana (ver
// docs/informes-psicometricos.md). Pero ninguna pantalla del frontend lo
// reflejaba — `estado` (activa/cerrada/cancelada) es la única fuente que
// se mostraba, y una campaña vencida por fecha sin que nadie la "cerrara"
// a mano sigue teniendo estado="activa" en la BD, así que se veía
// IDÉNTICA a una campaña genuinamente abierta: mismo badge verde "Activa",
// mismo botón "Editar campaña" disponible — hasta que alguien intentaba
// matricular o un alumno intentaba rendir y el backend lo rechazaba en
// silencio, sin que la pantalla hubiera avisado nada antes.
//
// `estadoVisibleCampana()` reproduce esa misma regla en el cliente (mismo
// criterio que `campana_esta_expirada`: activa + fecha_fin ya pasada) para
// que la UI muestre un 4to estado real, "vencida", en vez de mentir que
// sigue abierta.
export type EstadoVisibleCampana = "activa" | "vencida" | "cerrada" | "cancelada";

// 🆕 Fecha de cierre futura (sesión 2026-10-29) — el backend ya rechaza con
// 400 una `fecha_fin` pasada al crear/editar (crud.validar_fecha_fin_futura);
// esto es la misma regla en el formulario, para avisar antes de enviar.
// Formato de <input type="datetime-local">: "AAAA-MM-DDTHH:MM" en hora LOCAL.
export function ahoraParaInputLocal(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fechaCierreEsPasada(valorInputLocal: string): boolean {
  return !!valorInputLocal && new Date(valorInputLocal).getTime() <= Date.now();
}

export const MENSAJE_FECHA_CIERRE_PASADA = "La fecha de cierre debe ser posterior a la fecha y hora actual.";

export function estadoVisibleCampana(estado: string, fechaFin: string | null): EstadoVisibleCampana {
  if (estado === "activa" && fechaFin && new Date(fechaFin).getTime() < Date.now()) return "vencida";
  return (estado as EstadoVisibleCampana) ?? "activa";
}

export function etiquetaEstadoCampana(estado: EstadoVisibleCampana): string {
  switch (estado) {
    case "activa":
      return "Activa";
    case "vencida":
      return "Vencida";
    case "cerrada":
      return "Cerrada";
    case "cancelada":
      return "Cancelada";
  }
}

// El ámbar queda reservado en exclusiva para alertas clínicas de riesgo
// real (ver docs/motor-scoring.md) — "vencida"/"cancelada" usan el mismo
// rojo que TextoError, nunca ámbar, aunque conceptualmente sean una
// "advertencia": esto nunca es un riesgo clínico.
export function claseBadgeEstadoCampana(estado: EstadoVisibleCampana): string {
  switch (estado) {
    case "activa":
      return "bg-teal-400/20 text-teal-900";
    case "vencida":
    case "cancelada":
      return "bg-red-100 text-red-700";
    case "cerrada":
      return "bg-ink/10 text-ink/60";
  }
}
