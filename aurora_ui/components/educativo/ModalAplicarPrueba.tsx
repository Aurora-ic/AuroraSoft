"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, Copy, ExternalLink, Search, X, CircleCheck, CircleAlert } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { TextoError } from "@/components/ui/TextoError";
import { Input } from "@/components/ui/Input";
import { siglaPrueba } from "@/lib/pruebas";
import { ahoraParaInputLocal, fechaCierreEsPasada, MENSAJE_FECHA_CIERRE_PASADA } from "@/lib/campanas";
import type { AplicacionIndividual, ElegibilidadPrueba, Prueba } from "@/types/api";

// 🆕 (sesión 2026-11-01) "Aplicar prueba" desde el perfil del estudiante,
// sin armar una campaña a mano. Por detrás, POST
// /educativo/personas/{id}/aplicacion-individual crea una campaña
// `individual` de un solo inscrito (aparece en Campañas → Individuales y no
// cuenta en las estadísticas por salón). Antes de enviar se muestra si el
// estudiante puede rendir la prueba elegida (GET .../elegibilidad?persona_id=):
// consentimiento, reaplicación, otra pendiente, límite mensual.
export function ModalAplicarPrueba({
  personaId,
  nombreAlumno,
  onCerrar,
}: {
  personaId: number;
  nombreAlumno: string;
  onCerrar: () => void;
}) {
  const [busqueda, setBusqueda] = useState("");
  const [pruebaId, setPruebaId] = useState<number | null>(null);
  const [fechaFin, setFechaFin] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<AplicacionIndividual | null>(null);
  const [copiado, setCopiado] = useState(false);

  const pruebas = useQuery({
    queryKey: ["pruebas-aplicables"],
    queryFn: () => apiClient.get<Prueba[]>("/educativo/pruebas/"),
    select: (lista) => lista.filter((p) => p.activa && p.visible_para_clientes !== false),
  });
  const elegibilidad = useQuery({
    queryKey: ["elegibilidad", pruebaId, personaId],
    queryFn: () => apiClient.get<ElegibilidadPrueba>(`/educativo/pruebas/${pruebaId}/elegibilidad?persona_id=${personaId}`),
    enabled: pruebaId !== null,
  });
  const bloqueo = elegibilidad.data?.no_elegibles[0] ?? null;

  const termino = busqueda.trim().toLowerCase();
  const visibles = (pruebas.data ?? []).filter(
    (p) => !termino || [p.nombre_corto, p.nombre_tecnico, p.nombre_publico].some((v) => v?.toLowerCase().includes(termino)),
  );
  const fechaPasada = fechaCierreEsPasada(fechaFin);
  const urlExamen = resultado && typeof window !== "undefined" ? `${window.location.origin}/examen/${resultado.token}` : "";

  async function aplicar(e: React.FormEvent) {
    e.preventDefault();
    if (pruebaId === null || bloqueo || fechaPasada) return;
    setEnviando(true);
    setError(null);
    try {
      setResultado(
        await apiClient.post<AplicacionIndividual>(`/educativo/personas/${personaId}/aplicacion-individual`, {
          prueba_id: pruebaId,
          fecha_fin: fechaFin ? new Date(fechaFin).toISOString() : null,
        }),
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo aplicar la prueba.");
    } finally {
      setEnviando(false);
    }
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(urlExamen);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setError("El navegador no permitió copiar al portapapeles.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 overflow-y-auto">
      <div className="fixed inset-0 bg-ink/45" aria-hidden="true" onClick={onCerrar} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-aplicar-prueba"
        className="relative w-full max-w-2xl rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-xl text-sm"
      >
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
          <h2 id="titulo-aplicar-prueba" className="m-0 flex items-center gap-2 font-display text-[17px] font-semibold text-teal-900 dark:text-ink-dark">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark">
              <ClipboardCheck size={15} aria-hidden="true" />
            </span>
            Aplicar prueba a {nombreAlumno}
          </h2>
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar"
            className="rounded-lg p-1.5 text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>

        {resultado ? (
          <div className="space-y-4 px-5 py-5">
            <p className="m-0 flex items-center gap-2 text-[15px] font-semibold text-teal-800 dark:text-teal-accent-dark">
              <CircleCheck size={18} aria-hidden="true" />
              Prueba lista para {nombreAlumno}
            </p>
            <p className="m-0 text-ink/65 dark:text-ink-dark/65">
              Comparte el enlace con el estudiante, o ábrelo en este equipo si la aplicas ahora en sesión. El resultado aparecerá
              en su perfil al terminar.
            </p>
            <div className="flex items-center gap-2 rounded-xl border border-border dark:border-border-dark bg-mist/60 dark:bg-surface-raised-dark px-3 py-2">
              <code className="min-w-0 flex-1 truncate text-[12.5px] text-ink/80 dark:text-ink-dark/80">{urlExamen}</code>
              <button type="button" onClick={copiar} className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
                <Copy size={13} aria-hidden="true" />
                {copiado ? "Copiado ✓" : "Copiar"}
              </button>
            </div>
            <TextoError>{error}</TextoError>
            <div className="flex flex-wrap items-center justify-end gap-3">
              <Link
                href={`/campanas/${resultado.evaluacion.id}/dashboard`}
                className="text-[13px] font-semibold text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark"
              >
                Ver la aplicación
              </Link>
              <a
                href={urlExamen}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-card bg-accion px-4 py-2 text-[13px] font-semibold text-white hover:bg-accion-hover dark:bg-teal-accent-dark dark:text-mist-dark"
              >
                <ExternalLink size={14} aria-hidden="true" />
                Abrir el examen en este equipo
              </a>
            </div>
          </div>
        ) : (
          <form onSubmit={aplicar} className="space-y-4 px-5 py-5">
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
              <input
                type="search"
                aria-label="Buscar prueba"
                placeholder="Buscar prueba…"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                className="w-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
              />
            </div>

            <div role="radiogroup" aria-label="Prueba" className="grid max-h-64 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {pruebas.isPending && <p className="m-0 text-ink/50 dark:text-ink-dark/50">Cargando pruebas…</p>}
              {visibles.map((p) => {
                const elegida = p.id === pruebaId;
                return (
                  <button
                    key={p.id}
                    type="button"
                    role="radio"
                    aria-checked={elegida}
                    onClick={() => setPruebaId(p.id)}
                    className={`flex items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors ${
                      elegida
                        ? "border-acento-azul bg-acento-azul/[0.07] dark:border-acento-azul-dark dark:bg-acento-azul-dark/10"
                        : "border-border dark:border-border-dark hover:border-acento-azul/50"
                    }`}
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-acento-azul/10 text-[12px] font-bold text-acento-azul dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark">
                      {siglaPrueba(p).sigla}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate font-semibold text-ink dark:text-ink-dark">{p.nombre_corto || p.nombre_tecnico}</span>
                      <span className="block truncate text-[12px] text-ink/50 dark:text-ink-dark/50">{p.nombre_publico}</span>
                    </span>
                  </button>
                );
              })}
            </div>

            {pruebaId !== null && (
              <div aria-live="polite">
                {elegibilidad.isPending ? (
                  <p className="m-0 text-ink/50 dark:text-ink-dark/50">Revisando si puede rendirla…</p>
                ) : bloqueo ? (
                  <p className="m-0 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-800 dark:border-red-400/30 dark:bg-red-950/40 dark:text-red-200">
                    <CircleAlert size={15} className="mt-0.5 shrink-0" aria-hidden="true" />
                    <span>
                      No puede rendirla ahora: {bloqueo.detalle}
                      {bloqueo.disponible_desde ? ` Disponible desde el ${new Date(bloqueo.disponible_desde).toLocaleDateString("es-PE")}.` : ""}
                    </span>
                  </p>
                ) : elegibilidad.data ? (
                  <p className="m-0 flex items-center gap-2 text-teal-800 dark:text-teal-accent-dark">
                    <CircleCheck size={15} aria-hidden="true" />
                    Puede rendirla. Esta prueba se reaplica cada {elegibilidad.data.dias_minimos_entre_aplicaciones} días.
                  </p>
                ) : null}
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-[12px] font-semibold text-ink/60 dark:text-ink-dark/60">
                Fecha de cierre (opcional)
                <Input type="datetime-local" min={ahoraParaInputLocal()} value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} aria-invalid={fechaPasada} />
                {fechaPasada && <span className="font-medium text-red-700 dark:text-red-300">{MENSAJE_FECHA_CIERRE_PASADA}</span>}
              </label>
            </div>

            <TextoError>{error}</TextoError>

            <div className="flex items-center justify-end gap-3 border-t border-border dark:border-border-dark pt-4">
              <button type="button" onClick={onCerrar} className="text-[13px] text-ink/60 dark:text-ink-dark/60 hover:underline">
                Cancelar
              </button>
              <button
                type="submit"
                disabled={enviando || pruebaId === null || !!bloqueo || elegibilidad.isPending || fechaPasada}
                className="rounded-card bg-accion px-4 py-2 text-[13px] font-semibold text-white hover:bg-accion-hover disabled:cursor-not-allowed disabled:opacity-40 dark:bg-teal-accent-dark dark:text-mist-dark"
              >
                {enviando ? "Aplicando…" : "Aplicar y generar enlace"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
