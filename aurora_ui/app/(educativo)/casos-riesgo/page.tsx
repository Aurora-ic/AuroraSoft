"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { TextoError } from "@/components/ui/TextoError";

// Usa el endpoint /educativo/casos-pendientes que ya existe en el backend.
// Ajusta el tipo CasoRiesgo según la forma real que devuelva ese endpoint.
type CasoRiesgo = {
  persona_id: number;
  nombre_completo: string;
  prueba: string;
  nivel: string;
  fecha: string;
};

export default function CasosRiesgoPage() {
  const [casos, setCasos] = useState<CasoRiesgo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // 🆕 Antes esta llamada no tenía .catch(): un fallo de red/servidor
    // (o un 401 por sesión vencida) dejaba `casos=[]` sin ningún aviso —
    // en la ÚNICA pantalla cuyo trabajo es mostrar alumnos en riesgo, eso
    // se veía idéntico a "no hay nadie en riesgo". Un 401 además ya se
    // resuelve aparte (ver lib/api-client.ts/AuthContext.tsx: cierra sesión
    // y redirige); este mensaje cubre todo lo demás (red caída, 500, etc.).
    apiClient
      .get<CasoRiesgo[]>("/educativo/casos-pendientes")
      .then(setCasos)
      .catch((err) => setError(err.message || "No se pudieron cargar los casos en riesgo."))
      .finally(() => setCargando(false));
  }, []);

  return (
    <div>
      <h1 className="font-display text-2xl text-teal-900 mb-1">Casos en riesgo</h1>
      <p className="text-sm text-ink/60 mb-6">
        Alumnos con diagnóstico en nivel alto o crítico, pendientes de seguimiento.
      </p>

      {cargando && <p className="text-sm text-ink/40">Cargando…</p>}
      <TextoError className="mb-4">{error}</TextoError>

      <div className="flex flex-col gap-3">
        {casos.map((caso) => (
          <div
            key={`${caso.persona_id}-${caso.prueba}`}
            className="bg-white rounded-card border border-amber/40 border-l-4 border-l-amber px-4 py-3 flex items-center justify-between"
          >
            <div>
              <p className="text-sm text-ink">{caso.nombre_completo}</p>
              <p className="text-xs text-ink/60">{caso.prueba} — {caso.fecha}</p>
            </div>
            <span className="text-xs font-mono uppercase text-amber">{caso.nivel}</span>
          </div>
        ))}
        {!cargando && !error && casos.length === 0 && (
          <p className="text-sm text-ink/40">No hay casos pendientes.</p>
        )}
      </div>
    </div>
  );
}
