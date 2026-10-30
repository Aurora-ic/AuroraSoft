"use client";

import { useState } from "react";
import { AlertTriangle, ChevronRight } from "lucide-react";
import type { DimensionResumenEstadistico, ResumenEstadisticoDashboard } from "@/types/api";
import { ResumenEstadisticoPrueba } from "@/components/ui/ResumenEstadisticoPrueba";

// 🆕 Vista interactiva del resumen estadístico para el dashboard de
// /pruebas (sesión 2026-10-30, a pedido del usuario: "más interactivo para
// la visualización sin perder los colores"). Maestro–detalle:
// - izquierda, el MAPA de todas las dimensiones de un vistazo (media sobre
//   la escala + % en alerta), seleccionable;
// - derecha, el DETALLE de la elegida (estadísticos + distribución por
//   nivel, con resaltado al pasar el mouse).
//
// Igual que ResumenEstadisticoPrueba, solo DIBUJA lo que el backend ya
// calculó (crud.calcular_resumen_estadistico_dashboard) — nunca recalcula
// media/mediana/distribución. Colores: teal = normal, ámbar = es_alerta
// (autoritativo, nunca inferido del texto de `nivel`); el ámbar no llega a
// 3:1 de contraste sobre blanco, así que cada barra lleva SIEMPRE su número
// al lado y el ícono de alerta — nunca el color solo.
//
// Solo cubre el modo "rango" sin agrupar por área. Para "perfil"
// (IPIP-RIASEC) y CHASIDE (agrupar_dimensiones_por_area) delega en
// ResumenEstadisticoPrueba, que ya resuelve esos layouts específicos.

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function pctAlerta(d: DimensionResumenEstadistico): number | null {
  if (d.en_alerta === null || d.n === 0) return null;
  return (d.en_alerta / d.n) * 100;
}

function FilaMapa({
  d,
  activa,
  tieneAlertasPosibles,
  onClick,
}: {
  d: DimensionResumenEstadistico;
  activa: boolean;
  tieneAlertasPosibles: boolean;
  onClick: () => void;
}) {
  const escala = d.maximo_escala ?? d.maximo ?? null;
  const posMedia = d.media !== null && escala ? Math.min(Math.max((d.media / escala) * 100, 0), 100) : null;
  const pct = pctAlerta(d);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={activa}
      className={`w-full text-left rounded-lg px-3 py-2.5 transition-colors group ${
        activa
          ? "bg-teal-600/[0.07] ring-1 ring-teal-600/40 dark:bg-teal-accent-dark/10 dark:ring-teal-accent-dark/40"
          : "hover:bg-mist dark:hover:bg-surface-raised-dark"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[13px] font-semibold truncate ${activa ? "text-teal-900 dark:text-teal-accent-dark" : "text-ink/85 dark:text-ink-dark/85"}`}>
          {d.nombre}
        </span>
        <span className="flex items-center gap-1.5 shrink-0">
          {tieneAlertasPosibles && pct !== null && pct > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber/15 px-1.5 py-0.5 text-[10.5px] font-bold text-amber-700 dark:text-amber">
              <AlertTriangle size={10} strokeWidth={2.4} aria-hidden="true" />
              {pct.toFixed(0)}%
            </span>
          )}
          <ChevronRight
            size={14}
            aria-hidden="true"
            className={`transition-transform ${activa ? "text-teal-600 dark:text-teal-accent-dark translate-x-0.5" : "text-ink/25 dark:text-ink-dark/25"}`}
          />
        </span>
      </div>
      {d.n === 0 ? (
        <p className="m-0 mt-1 text-[11px] italic text-ink/40 dark:text-ink-dark/40">Sin datos todavía</p>
      ) : (
        <div className="mt-1.5 flex items-center gap-2">
          {/* Pista = escala completa; relleno = media del grupo. Una sola
              serie (teal), sin leyenda — el título de la fila la nombra. */}
          <div className="relative flex-1 h-1.5 rounded-full bg-border dark:bg-border-dark overflow-hidden">
            {posMedia !== null && (
              <div className="absolute inset-y-0 left-0 rounded-full bg-teal-600 dark:bg-teal-accent-dark" style={{ width: `${Math.max(posMedia, 2)}%` }} />
            )}
          </div>
          <span className="shrink-0 font-mono text-[10.5px] text-ink/50 dark:text-ink-dark/50">
            x̄ {fmt(d.media)}
            {escala != null ? `/${fmt(escala)}` : ""}
          </span>
        </div>
      )}
    </button>
  );
}

function Estadistico({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="rounded-lg bg-mist/70 dark:bg-surface-raised-dark px-3 py-2">
      <p className="m-0 text-[10.5px] font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">{etiqueta}</p>
      <p className="m-0 mt-0.5 font-display text-[17px] font-bold text-ink dark:text-ink-dark leading-tight">{valor}</p>
    </div>
  );
}

function DetalleDimension({ d, tieneAlertasPosibles }: { d: DimensionResumenEstadistico; tieneAlertasPosibles: boolean }) {
  const [nivelHover, setNivelHover] = useState<string | null>(null);
  const totalConNivel = d.distribucion.reduce((acc, niv) => acc + niv.cantidad, 0);
  const maxPct = Math.max(...d.distribucion.map((n) => n.pct), 1);
  const pct = pctAlerta(d);
  const hover = d.distribucion.find((n) => n.nivel === nivelHover) ?? null;

  if (d.n === 0) {
    return <p className="text-sm italic text-ink/50 dark:text-ink-dark/50 py-6 text-center">Esta dimensión todavía no tiene resultados.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Estadistico etiqueta="Alumnos (n)" valor={String(d.n)} />
        <Estadistico etiqueta="Media" valor={fmt(d.media)} />
        <Estadistico etiqueta="Mediana" valor={fmt(d.mediana)} />
        <Estadistico
          etiqueta="Mín – Máx"
          valor={`${fmt(d.minimo)}–${fmt(d.maximo)}${d.maximo_escala != null ? ` /${fmt(d.maximo_escala)}` : ""}`}
        />
      </div>

      {tieneAlertasPosibles && d.en_alerta !== null && (
        <div
          className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-[12.5px] ${
            d.en_alerta > 0
              ? "bg-amber/10 text-amber-800 dark:text-amber border border-amber/30"
              : "bg-teal-600/[0.06] text-teal-900 dark:text-teal-accent-dark border border-teal-600/15"
          }`}
        >
          <AlertTriangle size={15} strokeWidth={2.2} aria-hidden="true" className="shrink-0" />
          {d.en_alerta > 0 ? (
            <span>
              <strong>{d.en_alerta}</strong> de {d.n} alumnos en nivel de alerta ({(pct ?? 0).toFixed(0)}%)
            </span>
          ) : (
            <span>Ningún alumno en nivel de alerta en esta dimensión.</span>
          )}
        </div>
      )}

      {d.distribucion.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2 gap-2">
            <p className="m-0 text-[11px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Distribución por nivel</p>
            <p className="m-0 text-[11px] text-ink/50 dark:text-ink-dark/50 min-h-[1em]" aria-live="polite">
              {hover ? (
                <>
                  <span className="font-semibold text-ink dark:text-ink-dark">{hover.nivel}</span>: {hover.cantidad} de {totalConNivel} alumnos
                </>
              ) : (
                "Pasa el mouse sobre un nivel"
              )}
            </p>
          </div>
          <ul className="m-0 p-0 list-none space-y-1" onMouseLeave={() => setNivelHover(null)}>
            {d.distribucion.map((niv) => {
              const atenuado = nivelHover !== null && nivelHover !== niv.nivel;
              return (
                <li
                  key={niv.nivel}
                  onMouseEnter={() => setNivelHover(niv.nivel)}
                  className={`grid grid-cols-[minmax(6rem,9rem)_1fr_auto] items-center gap-3 rounded-md px-1.5 py-1.5 transition-opacity ${
                    atenuado ? "opacity-40" : "opacity-100"
                  }`}
                >
                  <span className="flex items-center gap-1.5 min-w-0 text-[12px] text-ink/80 dark:text-ink-dark/80">
                    {niv.es_alerta && <AlertTriangle size={11} className="shrink-0 text-amber" aria-label="Nivel de alerta" />}
                    <span className="truncate" title={niv.nivel}>
                      {niv.nivel}
                    </span>
                  </span>
                  <div className="h-3 rounded bg-border/60 dark:bg-border-dark overflow-hidden">
                    {/* Ancho relativo al nivel más frecuente — la barra más
                        larga siempre llena la pista; el % real va en texto. */}
                    <div
                      className={`h-full rounded transition-all ${niv.es_alerta ? "bg-amber" : "bg-teal-600 dark:bg-teal-accent-dark"}`}
                      style={{ width: `${Math.max((niv.pct / maxPct) * 100, 2)}%` }}
                    />
                  </div>
                  <span className="w-[4.5rem] text-right font-mono text-[11px] text-ink/60 dark:text-ink-dark/60">
                    {niv.cantidad} · {niv.pct.toFixed(0)}%
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PanelDimensiones({ resumen }: { resumen: ResumenEstadisticoDashboard }) {
  const { dimensiones, tiene_alertas_posibles } = resumen;
  // Por defecto, la dimensión con más alumnos en alerta (lo primero que un
  // psicólogo querría mirar); si ninguna tiene alertas, la primera.
  const [seleccion, setSeleccion] = useState<string | null>(null);

  const sinDatos = dimensiones.length === 0 || dimensiones.every((d) => d.n === 0);
  if (sinDatos || resumen.modo_interpretacion === "perfil" || resumen.agrupar_dimensiones_por_area) {
    return <ResumenEstadisticoPrueba resumen={resumen} />;
  }

  const porDefecto = [...dimensiones].sort((a, b) => (b.en_alerta ?? 0) - (a.en_alerta ?? 0))[0];
  const activa = dimensiones.find((d) => d.nombre === seleccion) ?? porDefecto;

  // Una sola dimensión: el mapa no aporta nada, va directo al detalle.
  if (dimensiones.length === 1) {
    return <DetalleDimension d={activa} tieneAlertasPosibles={tiene_alertas_posibles} />;
  }

  return (
    <div className="grid lg:grid-cols-[minmax(15rem,20rem)_1fr] gap-4">
      <div className="space-y-0.5 lg:max-h-[26rem] lg:overflow-y-auto lg:pr-1" role="list" aria-label="Dimensiones">
        {dimensiones.map((d) => (
          <div role="listitem" key={d.nombre}>
            <FilaMapa
              d={d}
              activa={d.nombre === activa.nombre}
              tieneAlertasPosibles={tiene_alertas_posibles}
              onClick={() => setSeleccion(d.nombre)}
            />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-border dark:border-border-dark p-4 min-w-0">
        <p className="m-0 mb-3 font-display text-[15px] font-bold text-teal-900 dark:text-ink-dark">{activa.nombre}</p>
        <DetalleDimension key={activa.nombre} d={activa} tieneAlertasPosibles={tiene_alertas_posibles} />
      </div>
    </div>
  );
}
