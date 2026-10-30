"use client";

import { useState } from "react";

export type PuntoGraficoTendencia = {
  evaluacionId: number;
  nombreGrupo: string;
  fecha: string;
  media: number | null;
  maximoEscala: number | null;
};

type Props = {
  nombreDimension: string;
  puntos: PuntoGraficoTendencia[];
};

const ANCHO = 480;
const ALTO = 160;
const PAD_IZQ = 36;
const PAD_DER = 12;
const PAD_SUP = 16;
const PAD_INF = 28;

function formatearFechaCorta(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short" });
}

function fmt(n: number | null): string {
  if (n === null) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// Línea de tendencia hecha a mano con SVG nativo — sin librería de
// gráficos nueva (mismo criterio que el resto de aurorasoft), un gráfico
// de línea por dimensión (small multiples), nunca varias dimensiones en el
// mismo eje Y (escalas distintas entre dimensiones). Un solo punto no
// traza línea — se muestra como un único marcador.
export function GraficoTendenciaDimension({ nombreDimension, puntos }: Props) {
  const [indiceHover, setIndiceHover] = useState<number | null>(null);
  const [mostrarTabla, setMostrarTabla] = useState(false);

  const conValor = puntos.filter((p) => p.media !== null);
  if (conValor.length === 0) {
    return (
      <div className="py-2">
        <p className="text-sm font-semibold text-ink/80 dark:text-ink-dark/80">{nombreDimension}</p>
        <p className="text-xs text-ink/40 dark:text-ink-dark/40 italic">Sin datos suficientes para graficar.</p>
      </div>
    );
  }

  const valores = conValor.map((p) => p.media as number);
  const maximoDeclarado = Math.max(...puntos.map((p) => p.maximoEscala ?? 0));
  const maxY = Math.max(maximoDeclarado, ...valores, 1);
  const minY = 0;

  const anchoUtil = ANCHO - PAD_IZQ - PAD_DER;
  const altoUtil = ALTO - PAD_SUP - PAD_INF;

  function x(i: number): number {
    return puntos.length === 1 ? PAD_IZQ + anchoUtil / 2 : PAD_IZQ + (i / (puntos.length - 1)) * anchoUtil;
  }
  function y(valor: number): number {
    return PAD_SUP + altoUtil - ((valor - minY) / (maxY - minY)) * altoUtil;
  }

  const puntosConValor = puntos.map((p, i) => ({ ...p, i, cx: x(i), cy: p.media !== null ? y(p.media) : null }));
  const lineaPoints = puntosConValor.filter((p) => p.cy !== null).map((p) => `${p.cx},${p.cy}`).join(" ");
  const activo = indiceHover !== null ? puntosConValor[indiceHover] : null;

  return (
    <div className="py-2 space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink/80 dark:text-ink-dark/80">{nombreDimension}</p>
        <button onClick={() => setMostrarTabla((v) => !v)} className="text-xs text-teal-700 dark:text-teal-accent-dark hover:underline">
          {mostrarTabla ? "Ver gráfico" : "Ver como tabla"}
        </button>
      </div>

      {mostrarTabla ? (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-ink/50 dark:text-ink-dark/50">
              <th className="py-1 pr-2 font-medium">Campaña</th>
              <th className="py-1 pr-2 font-medium">Fecha</th>
              <th className="py-1 font-medium">Media</th>
            </tr>
          </thead>
          <tbody>
            {puntos.map((p) => (
              <tr key={p.evaluacionId} className="border-t border-border/60 dark:border-border-dark">
                <td className="py-1 pr-2 text-ink dark:text-ink-dark">{p.nombreGrupo}</td>
                <td className="py-1 pr-2 text-ink/60 dark:text-ink-dark/60">{formatearFechaCorta(p.fecha)}</td>
                <td className="py-1 text-ink/80 dark:text-ink-dark/80 font-mono">{fmt(p.media)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="w-full h-auto" role="img" aria-label={`Tendencia de ${nombreDimension}`}>
            {/* Eje Y recesivo: solo min/máx, nunca una grilla densa */}
            <line x1={PAD_IZQ} y1={PAD_SUP} x2={PAD_IZQ} y2={PAD_SUP + altoUtil} stroke="var(--color-border)" strokeWidth={1} />
            <line x1={PAD_IZQ} y1={PAD_SUP + altoUtil} x2={ANCHO - PAD_DER} y2={PAD_SUP + altoUtil} stroke="var(--color-border)" strokeWidth={1} />
            <text x={PAD_IZQ - 6} y={PAD_SUP + 4} textAnchor="end" className="fill-ink/40 dark:fill-ink-dark/40" fontSize={9}>
              {fmt(maxY)}
            </text>
            <text x={PAD_IZQ - 6} y={PAD_SUP + altoUtil} textAnchor="end" className="fill-ink/40 dark:fill-ink-dark/40" fontSize={9}>
              0
            </text>

            {lineaPoints && (
              <polyline points={lineaPoints} fill="none" stroke="var(--color-teal-600)" strokeWidth={2} strokeLinecap="round" />
            )}

            {puntosConValor.map((p) => (
              <g key={p.evaluacionId}>
                {p.cy !== null && (
                  <circle
                    cx={p.cx}
                    cy={p.cy}
                    r={indiceHover === p.i ? 5 : 4}
                    fill="var(--color-teal-600)"
                    stroke="white"
                    strokeWidth={1.5}
                    onMouseEnter={() => setIndiceHover(p.i)}
                    onMouseLeave={() => setIndiceHover(null)}
                    style={{ cursor: "pointer" }}
                  />
                )}
                <text x={p.cx} y={ALTO - 6} textAnchor="middle" className="fill-ink/40 dark:fill-ink-dark/40" fontSize={8}>
                  {formatearFechaCorta(p.fecha)}
                </text>
              </g>
            ))}
          </svg>

          {activo && activo.cy !== null && (
            <div
              className="absolute -translate-x-1/2 -translate-y-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2 py-1 text-xs shadow-sm pointer-events-none"
              style={{ left: `${(activo.cx / ANCHO) * 100}%`, top: `${(activo.cy / ALTO) * 100 - 4}%` }}
            >
              <p className="font-medium text-ink dark:text-ink-dark">{activo.nombreGrupo}</p>
              <p className="text-ink/60 dark:text-ink-dark/60">
                {formatearFechaCorta(activo.fecha)} · Media: {fmt(activo.media)}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
