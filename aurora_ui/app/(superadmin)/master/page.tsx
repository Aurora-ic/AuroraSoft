"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import type { Institucion } from "@/types/api";

// Landing del panel interno de AuroraSoft — conteos rápidos leídos del
// mismo GET /instituciones/ que /master/clientes ya usa para la lista
// completa, sin un endpoint de métricas aparte.
export default function MasterPage() {
  const [instituciones, setInstituciones] = useState<Institucion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Institucion[]>("/instituciones/")
      .then(setInstituciones)
      .catch((err) => setError(err.message || "No se pudo cargar el resumen de instituciones."));
  }, []);

  const total = instituciones?.length ?? null;
  const activas = instituciones?.filter((i) => i.plan_activo).length ?? null;
  const licenciaVencida = (i: Institucion) =>
    !!i.fecha_vencimiento_licencia && new Date(i.fecha_vencimiento_licencia).getTime() < Date.now();
  const vencidas = instituciones?.filter(licenciaVencida).length ?? null;

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl text-teal-900">Panel interno</h1>

      <TextoError>{error}</TextoError>

      <div className="grid grid-cols-3 gap-4 max-w-xl">
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className="text-2xl font-display text-teal-900">{total ?? "…"}</p>
          <p className="text-xs text-ink/60">Instituciones</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className="text-2xl font-display text-teal-900">{activas ?? "…"}</p>
          <p className="text-xs text-ink/60">Con plan activo</p>
        </div>
        <div className="bg-white rounded-card border border-border p-4 text-center">
          <p className={`text-2xl font-display ${vencidas ? "text-red-700" : "text-teal-900"}`}>{vencidas ?? "…"}</p>
          <p className="text-xs text-ink/60">Licencia vencida</p>
        </div>
      </div>

      <Link href="/master/clientes" className={claseBoton("primario")}>
        Gestionar instituciones →
      </Link>
    </div>
  );
}
