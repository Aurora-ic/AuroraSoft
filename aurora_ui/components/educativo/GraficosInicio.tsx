"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarClock } from "lucide-react";
import type { CampanaAvanceInicio, MesSerieInicio } from "@/types/api";

// 🆕 Gráficos del Inicio (sesión 2026-10-30) — datos de
// GET /educativo/inicio/series (crud.obtener_series_inicio): solo dibujan lo
// que el backend ya agregó, nunca recalculan.
//
// Colores (validados con el validador de paleta, claro y oscuro):
// - Evaluaciones: teal = sin alerta, ámbar = con alerta. El ámbar es el
//   color semántico de riesgo clínico de toda la app — aquí también.
// - Seguimiento: teal = sesiones de seguimiento, azul = citas (el mismo azul
//   que las actividades de la Agenda). Teal↔pizarra no pasaba ni con visión
//   normal (ΔE 8), teal↔azul sí (ΔE 17).
// Hechos a mano (HTML/SVG) — sin librería de gráficos nueva, mismo criterio
// que GraficoTendenciaDimension. Cada gráfico tiene una tabla sr-only.

const NOMBRE_MES_CORTO = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const NOMBRE_MES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

function mesCorto(clave: string) {
  return NOMBRE_MES_CORTO[Number(clave.slice(5, 7)) - 1] ?? clave;
}
function mesLargo(clave: string) {
  return `${NOMBRE_MES[Number(clave.slice(5, 7)) - 1] ?? clave} ${clave.slice(0, 4)}`;
}

// Tope "redondo" del eje (1, 2, 5 × 10ⁿ) para que la escala se lea fácil.
function topeRedondo(max: number): number {
  if (max <= 0) return 4;
  const potencia = Math.pow(10, Math.floor(Math.log10(max)));
  for (const f of [1, 2, 2.5, 5, 10]) if (f * potencia >= max) return f * potencia;
  return 10 * potencia;
}

function Leyenda({ items }: { items: { color: string; etiqueta: string }[] }) {
  return (
    <div className="flex items-center gap-3.5 flex-wrap text-[11.5px] text-ink/60 dark:text-ink-dark/60">
      {items.map((i) => (
        <span key={i.etiqueta} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-[3px] ${i.color}`} />
          {i.etiqueta}
        </span>
      ))}
    </div>
  );
}

function SinDatos({ texto }: { texto: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center">
      <p className="m-0 rounded-lg bg-surface/90 dark:bg-surface-dark/90 px-3 py-1.5 text-[12px] text-ink/50 dark:text-ink-dark/50">{texto}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 1) Evaluaciones finalizadas por mes — columnas apiladas sin/con alerta
// ---------------------------------------------------------------------------
export function GraficoEvaluacionesMes({ meses }: { meses: MesSerieInicio[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const tope = topeRedondo(Math.max(...meses.map((m) => m.evaluaciones), 0));
  const vacio = meses.every((m) => m.evaluaciones === 0);
  const ALTO = 150; // px del área de trazado

  return (
    <div className="flex flex-col gap-3">
      <Leyenda
        items={[
          { color: "bg-teal-600 dark:bg-teal-accent-dark", etiqueta: "Sin alerta" },
          { color: "bg-amber", etiqueta: "Con alerta" },
        ]}
      />
      <div className="relative" onMouseLeave={() => setHover(null)}>
        {/* Rejilla recesiva: solo 0, mitad y tope */}
        <div className="absolute inset-x-0 top-0 pointer-events-none" style={{ height: ALTO }} aria-hidden="true">
          {[1, 0.5, 0].map((f) => (
            <div key={f} className="absolute inset-x-0 flex items-center gap-2" style={{ top: `${(1 - f) * 100}%` }}>
              <span className="w-6 -translate-y-1/2 text-right text-[10px] tabular-nums text-ink/35 dark:text-ink-dark/35">
                {Math.round(tope * f)}
              </span>
              <span className={`flex-1 -translate-y-1/2 border-t ${f === 0 ? "border-border dark:border-border-dark" : "border-dashed border-border/70 dark:border-border-dark/70"}`} />
            </div>
          ))}
        </div>

        <div className="relative ml-8 grid gap-2" style={{ gridTemplateColumns: `repeat(${meses.length}, minmax(0, 1fr))` }}>
          {meses.map((m, i) => {
            const hSin = (m.sin_alerta / tope) * ALTO;
            const hCon = (m.con_alerta / tope) * ALTO;
            const activo = hover === i;
            return (
              <div
                key={m.mes}
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={`${mesLargo(m.mes)}: ${m.evaluaciones} evaluaciones, ${m.con_alerta} con alerta`}
                className="relative flex flex-col items-center outline-none"
              >
                {/* Área de impacto = toda la columna, no solo la barra */}
                <div
                  className={`relative w-full flex flex-col items-center justify-end rounded-md transition-colors ${activo ? "bg-mist dark:bg-surface-raised-dark" : ""}`}
                  style={{ height: ALTO }}
                >
                  {m.evaluaciones > 0 && (
                    <span className="mb-1 text-[11px] font-semibold tabular-nums text-ink/70 dark:text-ink-dark/70">{m.evaluaciones}</span>
                  )}
                  <div className="flex w-[55%] max-w-9 flex-col items-stretch gap-[2px]">
                    {m.con_alerta > 0 && (
                      <div className="bg-amber rounded-t-[4px]" style={{ height: Math.max(hCon, 3) }} />
                    )}
                    {m.sin_alerta > 0 && (
                      <div
                        className={`bg-teal-600 dark:bg-teal-accent-dark ${m.con_alerta > 0 ? "" : "rounded-t-[4px]"}`}
                        style={{ height: Math.max(hSin, 3) }}
                      />
                    )}
                  </div>
                </div>
                <span className={`mt-1.5 text-[11px] capitalize ${activo ? "font-semibold text-ink dark:text-ink-dark" : "text-ink/50 dark:text-ink-dark/50"}`}>
                  {mesCorto(m.mes)}
                </span>

                {activo && (
                  <div
                    role="tooltip"
                    className="absolute bottom-full mb-1 z-10 w-40 -translate-y-6 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-raised-dark px-3 py-2 text-[11.5px] shadow-lg pointer-events-none"
                  >
                    <p className="m-0 mb-1 font-semibold capitalize text-ink dark:text-ink-dark">{mesLargo(m.mes)}</p>
                    <p className="m-0 flex justify-between text-ink/70 dark:text-ink-dark/70">
                      Evaluaciones <strong className="tabular-nums text-ink dark:text-ink-dark">{m.evaluaciones}</strong>
                    </p>
                    <p className="m-0 flex justify-between text-ink/70 dark:text-ink-dark/70">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-sm bg-teal-600 dark:bg-teal-accent-dark" />
                        Sin alerta
                      </span>
                      <span className="tabular-nums">{m.sin_alerta}</span>
                    </p>
                    <p className="m-0 flex justify-between text-ink/70 dark:text-ink-dark/70">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-sm bg-amber" />
                        Con alerta
                      </span>
                      <span className="tabular-nums">{m.con_alerta}</span>
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        {vacio && <SinDatos texto="Sin evaluaciones finalizadas en estos meses." />}
      </div>

      <table className="sr-only">
        <caption>Evaluaciones finalizadas por mes</caption>
        <thead>
          <tr><th>Mes</th><th>Total</th><th>Sin alerta</th><th>Con alerta</th></tr>
        </thead>
        <tbody>
          {meses.map((m) => (
            <tr key={m.mes}><td>{mesLargo(m.mes)}</td><td>{m.evaluaciones}</td><td>{m.sin_alerta}</td><td>{m.con_alerta}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2) Seguimiento por mes — dos líneas (sesiones / citas) con cruz al pasar
// ---------------------------------------------------------------------------
const ANCHO = 420;
const ALTO_L = 150;
const PAD = { izq: 26, der: 10, sup: 12, inf: 22 };

export function GraficoSeguimientoMes({ meses }: { meses: MesSerieInicio[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const tope = topeRedondo(Math.max(...meses.flatMap((m) => [m.sesiones_seguimiento, m.citas]), 0));
  const vacio = meses.every((m) => m.sesiones_seguimiento === 0 && m.citas === 0);
  const anchoUtil = ANCHO - PAD.izq - PAD.der;
  const altoUtil = ALTO_L - PAD.sup - PAD.inf;
  const x = (i: number) => PAD.izq + (meses.length === 1 ? anchoUtil / 2 : (i / (meses.length - 1)) * anchoUtil);
  const y = (v: number) => PAD.sup + altoUtil - (v / tope) * altoUtil;

  const series = [
    { clave: "sesiones_seguimiento" as const, etiqueta: "Sesiones", trazo: "stroke-teal-600 dark:stroke-teal-accent-dark", relleno: "fill-teal-600 dark:fill-teal-accent-dark", muestra: "bg-teal-600 dark:bg-teal-accent-dark" },
    { clave: "citas" as const, etiqueta: "Citas", trazo: "stroke-acento-azul dark:stroke-acento-azul-dark", relleno: "fill-acento-azul dark:fill-acento-azul-dark", muestra: "bg-acento-azul dark:bg-acento-azul-dark" },
  ];
  const activo = hover !== null ? meses[hover] : null;

  return (
    <div className="flex flex-col gap-3">
      <Leyenda items={series.map((s) => ({ color: s.muestra, etiqueta: s.etiqueta }))} />
      <div className="relative" onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${ANCHO} ${ALTO_L}`} className="w-full h-auto overflow-visible" role="img" aria-label="Sesiones de seguimiento y citas por mes">
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line
                x1={PAD.izq} x2={ANCHO - PAD.der} y1={y(tope * f)} y2={y(tope * f)}
                className={f === 0 ? "stroke-border dark:stroke-border-dark" : "stroke-border/70 dark:stroke-border-dark/70"}
                strokeDasharray={f === 0 ? undefined : "3 3"} strokeWidth={1}
              />
              <text x={PAD.izq - 6} y={y(tope * f) + 3} textAnchor="end" fontSize={9} className="fill-ink/35 dark:fill-ink-dark/35">
                {Math.round(tope * f)}
              </text>
            </g>
          ))}

          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.sup} y2={PAD.sup + altoUtil} className="stroke-ink/25 dark:stroke-ink-dark/25" strokeWidth={1} />
          )}

          {series.map((s) => (
            <polyline
              key={s.clave}
              fill="none"
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              className={s.trazo}
              points={meses.map((m, i) => `${x(i)},${y(m[s.clave])}`).join(" ")}
            />
          ))}
          {series.map((s) =>
            meses.map((m, i) => (
              <circle
                key={`${s.clave}-${m.mes}`}
                cx={x(i)} cy={y(m[s.clave])} r={hover === i ? 5 : 3.5}
                strokeWidth={2}
                className={`${s.relleno} stroke-surface dark:stroke-surface-dark`}
              />
            )),
          )}

          {meses.map((m, i) => (
            <text key={m.mes} x={x(i)} y={ALTO_L - 4} textAnchor="middle" fontSize={10}
              className={hover === i ? "fill-ink dark:fill-ink-dark font-semibold" : "fill-ink/50 dark:fill-ink-dark/50"}>
              {mesCorto(m.mes)}
            </text>
          ))}

          {/* Franjas de impacto por mes (más anchas que los puntos) */}
          {meses.map((m, i) => (
            <rect
              key={`hit-${m.mes}`}
              x={x(i) - anchoUtil / Math.max(meses.length - 1, 1) / 2}
              y={0}
              width={anchoUtil / Math.max(meses.length - 1, 1)}
              height={ALTO_L}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>

        {activo && hover !== null && (
          <div
            role="tooltip"
            className="absolute top-0 z-10 w-36 -translate-x-1/2 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-raised-dark px-3 py-2 text-[11.5px] shadow-lg pointer-events-none"
            style={{ left: `${Math.min(Math.max((x(hover) / ANCHO) * 100, 18), 82)}%` }}
          >
            <p className="m-0 mb-1 font-semibold capitalize text-ink dark:text-ink-dark">{mesLargo(activo.mes)}</p>
            {series.map((s) => (
              <p key={s.clave} className="m-0 flex justify-between text-ink/70 dark:text-ink-dark/70">
                <span className="inline-flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-sm ${s.muestra}`} />
                  {s.etiqueta}
                </span>
                <strong className="tabular-nums text-ink dark:text-ink-dark">{activo[s.clave]}</strong>
              </p>
            ))}
          </div>
        )}
        {vacio && <SinDatos texto="Sin sesiones ni citas en estos meses." />}
      </div>

      <table className="sr-only">
        <caption>Sesiones de seguimiento y citas por mes</caption>
        <thead><tr><th>Mes</th><th>Sesiones</th><th>Citas</th></tr></thead>
        <tbody>
          {meses.map((m) => (
            <tr key={m.mes}><td>{mesLargo(m.mes)}</td><td>{m.sesiones_seguimiento}</td><td>{m.citas}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3) Avance de campañas activas — barras de progreso
// ---------------------------------------------------------------------------
function diasHasta(iso: string | null): number | null {
  if (!iso) return null;
  return Math.ceil((new Date(iso).getTime() - Date.now()) / (24 * 60 * 60 * 1000));
}

export function AvanceCampanas({ campanas }: { campanas: CampanaAvanceInicio[] }) {
  if (campanas.length === 0) {
    return <p className="m-0 text-[12.5px] italic text-ink/45 dark:text-ink-dark/45">Sin campañas activas.</p>;
  }
  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-3.5">
      {campanas.map((c) => {
        const pct = c.inscritos > 0 ? Math.round((c.finalizados / c.inscritos) * 100) : 0;
        const dias = diasHasta(c.fecha_fin);
        const urgente = dias !== null && dias <= 7;
        return (
          <li key={c.id}>
            <Link href={`/campanas/${c.id}/dashboard`} className="group block">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[12.5px] font-semibold text-ink dark:text-ink-dark group-hover:text-acento-azul dark:group-hover:text-acento-azul-dark">
                  {c.nombre_grupo}
                </span>
                <span className="shrink-0 text-[11px] tabular-nums text-ink/55 dark:text-ink-dark/55">
                  {c.finalizados}/{c.inscritos} · <strong className="text-ink dark:text-ink-dark">{pct}%</strong>
                </span>
              </div>
              <div className="mt-1.5 h-1.5 rounded-full bg-border dark:bg-border-dark overflow-hidden">
                <div className="h-full rounded-full bg-acento-azul dark:bg-acento-azul-dark transition-all" style={{ width: `${Math.max(pct, c.finalizados > 0 ? 3 : 0)}%` }} />
              </div>
              <div className="mt-1 flex items-center justify-between gap-2 text-[10.5px] text-ink/45 dark:text-ink-dark/45">
                <span className="truncate">{c.prueba ?? ""}</span>
                {dias !== null && (
                  <span className={`inline-flex items-center gap-1 shrink-0 ${urgente ? "font-semibold text-red-700 dark:text-red-300" : ""}`}>
                    <CalendarClock size={11} aria-hidden="true" />
                    {dias < 0 ? "Plazo vencido" : dias === 0 ? "Cierra hoy" : `Cierra en ${dias} día${dias === 1 ? "" : "s"}`}
                  </span>
                )}
              </div>
            </Link>
          </li>
        );
      })}
      <li>
        <Link href="/campanas" className="inline-flex items-center gap-1 text-[11.5px] font-semibold text-acento-azul dark:text-acento-azul-dark hover:underline">
          Ver todas las campañas
          <ArrowRight size={12} aria-hidden="true" />
        </Link>
      </li>
    </ul>
  );
}
