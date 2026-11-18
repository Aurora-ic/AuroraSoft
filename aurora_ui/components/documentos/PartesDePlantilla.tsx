"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { ETIQUETAS_TIPO_SECCION, MODO_TIPO_SECCION, type ModoSeccion } from "@/lib/documentos-constantes";
import { ChipModo } from "@/components/documentos/ModoSeccion";
import type { PlantillaSeccion } from "@/types/api";
import { EsqueletoLineas } from "@/components/ui/Esqueleto";

// 🆕 (2026-11-17) Al crear un documento: qué partes tiene la plantilla
// elegida y cuáles vas a tener que completar tú — antes se descubría recién
// al abrir el borrador, con secciones "Automática" mezcladas sin explicación.
export function PartesDePlantilla({ plantillaId }: { plantillaId: number }) {
  const consulta = useQuery({
    queryKey: ["plantilla-secciones", plantillaId],
    queryFn: () => apiClient.get<PlantillaSeccion[]>(`/documentos/plantillas/${plantillaId}/secciones`),
    staleTime: 60 * 1000,
  });
  if (consulta.isLoading)
    return (
      <div className="mt-3 rounded-lg border border-border bg-surface p-3 dark:border-border-dark dark:bg-surface-dark">
        <EsqueletoLineas cantidad={3} />
      </div>
    );
  const partes = (consulta.data ?? []).slice().sort((a, b) => a.orden - b.orden);
  if (partes.length === 0) return null;

  const modoDe = (p: PlantillaSeccion): ModoSeccion =>
    p.tipo_seccion === "datos_filiacion" ? "escribes" : MODO_TIPO_SECCION[p.tipo_seccion];
  const tuyas = partes.filter((p) => ["escribes", "eliges"].includes(modoDe(p)));
  const solas = partes.filter((p) => !["escribes", "eliges"].includes(modoDe(p)));

  return (
    <div className="mt-3 grid gap-3 rounded-lg border border-border bg-surface p-3 dark:border-border-dark dark:bg-surface-dark sm:grid-cols-2">
      <div>
        <p className="m-0 mb-1.5 text-[12.5px] font-bold text-ink dark:text-ink-dark">
          Vas a completar {tuyas.length === 1 ? "1 parte" : `${tuyas.length} partes`}
        </p>
        {tuyas.length === 0 ? (
          <p className="m-0 text-[12px] text-ink/65 dark:text-ink-dark/55">Ninguna: este documento sale completo solo.</p>
        ) : (
          <ul className="m-0 list-none space-y-1 p-0">
            {tuyas.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 text-[12.5px]">
                <span className="min-w-0 truncate text-ink/80 dark:text-ink-dark/80">{p.titulo || ETIQUETAS_TIPO_SECCION[p.tipo_seccion]}</span>
                <ChipModo modo={modoDe(p)} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="m-0 mb-1.5 text-[12.5px] font-bold text-ink dark:text-ink-dark">
          {solas.length === 1 ? "1 parte sale sola" : `${solas.length} partes salen solas`}
        </p>
        {solas.length === 0 ? (
          <p className="m-0 text-[12px] text-ink/65 dark:text-ink-dark/55">Ninguna.</p>
        ) : (
          <ul className="m-0 list-none space-y-1 p-0">
            {solas.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-2 text-[12.5px]">
                <span className="min-w-0 truncate text-ink/65 dark:text-ink-dark/60">{p.titulo || ETIQUETAS_TIPO_SECCION[p.tipo_seccion]}</span>
                <ChipModo modo={modoDe(p)} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
