import type { Prueba } from "@/types/api";

// 🆕 Cuadrante de iniciales de una prueba (sesión 2026-10-31): la sigla real
// del instrumento a partir de nombre_tecnico — "PHQ-9" → PHQ + 9, "RCADS-47" → RCADS + 47,
// "DASS-21" → DASS + 21, "CHASIDE" → CHA, "HAMILTON_AUTOINFORME" → HAM —
// en vez de las 2 primeras letras de cualquier nombre ("PH", "NI", "Es").
// Compartido por el catálogo (/pruebas) y el paso 1 de /campanas/nueva.
// 🆕 (sesión 2026-11-02) "Cada 14 días (2 semanas)", "Cada 180 días (6
// meses)" — la reaplicación de una prueba en lenguaje de calendario.
export function textoReaplicacion(dias: number): string {
  const equivalente =
    dias % 30 === 0 && dias >= 30
      ? `${dias / 30} ${dias / 30 === 1 ? "mes" : "meses"}`
      : dias % 7 === 0
        ? `${dias / 7} ${dias / 7 === 1 ? "semana" : "semanas"}`
        : null;
  return `Cada ${dias} días${equivalente ? ` (${equivalente})` : ""}`;
}

export function siglaPrueba(p: Pick<Prueba, "nombre_tecnico">): { sigla: string; numero: string | null } {
  const partes = p.nombre_tecnico.split(/[-_\s]+/).filter(Boolean);
  const primera = (partes[0] ?? p.nombre_tecnico).toUpperCase();
  const sigla = primera.length <= 5 ? primera : primera.slice(0, 3);
  const numero = partes.slice(1).find((x) => /^\d+$/.test(x)) ?? null;
  return { sigla, numero };
}
