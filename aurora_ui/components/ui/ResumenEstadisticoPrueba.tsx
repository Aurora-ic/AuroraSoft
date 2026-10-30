import type { DimensionResumenEstadistico, ResumenEstadisticoDashboard } from "@/types/api";

type Props = {
  resumen: ResumenEstadisticoDashboard;
};

// Resumen estadístico por dimensión, compartido por /campanas/[id]/dashboard
// y el "Dashboard por salón o grado" de /pruebas — ambos entregan
// exactamente la misma forma (`ResumenEstadisticoDashboard`, ver types/api.ts
// y crud.calcular_resumen_estadistico_dashboard en el backend, que hace TODO
// el cálculo — este componente solo dibuja lo que ya viene resuelto, nunca
// recalcula media/mediana/distribución por su cuenta). Deliberadamente
// genérico: nunca rama por nombre/clave de prueba — solo por
// modo_interpretacion/tipo_calculo/agrupar_dimensiones_por_area/
// tiene_alertas_posibles, porque de 1 a 14 dimensiones y de PHQ-9 a CHASIDE
// a IPIP-RIASEC no se parecen entre sí.
//
// 🔒 El resumen se calcula server-side ANTES de la redacción para 'colegio'
// (es un agregado de grupo, no el diagnóstico puntual de un alumno), así que
// sigue viniendo completo aunque `alumnos[].resultados` llegue vacío para
// ese rol — este componente no necesita saber nada de eso, solo dibuja lo
// que el backend ya decidió que puede ver.

function fmt(n: number | null): string {
  if (n === null) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// Misma convención de nombre que crud._agrupar_dimensiones_por_area en el
// backend (ver docs/motor-scoring.md / seed_chaside.py): "Intereses — X:
// Nombre" / "Aptitudes — X: Nombre". Solo se usa aquí para decidir el
// LAYOUT visual (qué dimensiones van una al lado de la otra) — la
// frecuencia de "área compatible" ya viene calculada en
// `resumen.areas_compatibles`, nunca recalculada en el cliente.
const PATRON_DIMENSION_AREA = /^(Intereses|Aptitudes)\s+—\s+(.+?):\s*(.+)$/;

function EstadisticasNumericas({ d }: { d: DimensionResumenEstadistico }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink/60 dark:text-ink-dark/60">
      <span>n={d.n}</span>
      <span>Media: {fmt(d.media)}</span>
      <span>Mediana: {fmt(d.mediana)}</span>
      <span>
        Mín–Máx: {d.n > 0 ? `${fmt(d.minimo)}–${fmt(d.maximo)}` : "—"}
        {d.maximo_escala != null ? ` (de ${fmt(d.maximo_escala)})` : ""}
      </span>
    </div>
  );
}

function BadgeTipoCalculo({ tipoCalculo }: { tipoCalculo: DimensionResumenEstadistico["tipo_calculo"] }) {
  if (tipoCalculo === "suma_de_dimensiones") {
    return <span className="rounded-full px-2 py-0.5 bg-teal-900/10 dark:bg-teal-accent-dark/15 text-teal-900 dark:text-teal-accent-dark text-[10px] font-semibold uppercase tracking-wide">Total</span>;
  }
  if (tipoCalculo === "conteo_sintomas") {
    return <span className="rounded-full px-2 py-0.5 bg-mist dark:bg-surface-raised-dark text-ink/60 dark:text-ink-dark/60 text-[10px] font-semibold uppercase tracking-wide">Conteo</span>;
  }
  return null;
}

function BloqueDimensionRango({ d, tieneAlertasPosibles }: { d: DimensionResumenEstadistico; tieneAlertasPosibles: boolean }) {
  const mayoria = d.distribucion[0];
  const totalConNivel = d.distribucion.reduce((acc, niv) => acc + niv.cantidad, 0);

  return (
    <div className="space-y-1.5 py-2">
      <div className="flex items-center gap-2">
        <p className="text-sm font-semibold text-ink/80 dark:text-ink-dark/80">{d.nombre}</p>
        <BadgeTipoCalculo tipoCalculo={d.tipo_calculo} />
      </div>

      {d.n === 0 ? (
        <p className="text-xs text-ink/40 dark:text-ink-dark/40 italic">Sin datos todavía.</p>
      ) : (
        <>
          <EstadisticasNumericas d={d} />

          {d.distribucion.length > 0 && (
            <div className="space-y-1">
              {d.distribucion.map((niv) => (
                <div key={niv.nivel} className="flex items-center gap-2 text-xs">
                  <span className={`w-28 shrink-0 truncate ${niv === mayoria ? "font-semibold text-ink dark:text-ink-dark" : "text-ink/60 dark:text-ink-dark/60"}`}>
                    {niv.nivel}
                    {niv === mayoria ? " ◀" : ""}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-border dark:bg-border-dark overflow-hidden">
                    <div
                      className={`h-full rounded-full ${niv.es_alerta ? "bg-amber" : "bg-teal-600 dark:bg-teal-accent-dark"}`}
                      style={{ width: `${Math.max(niv.pct, 2)}%` }}
                    />
                  </div>
                  <span className="w-20 shrink-0 text-right text-ink/50 dark:text-ink-dark/50 font-mono">
                    {niv.cantidad} ({niv.pct.toFixed(0)}%)
                  </span>
                </div>
              ))}
              {mayoria && (
                <p className="text-xs text-ink/50 dark:text-ink-dark/50">
                  Mayoría: <span className="font-medium text-ink/70 dark:text-ink-dark/70">{mayoria.nivel}</span> ({mayoria.pct.toFixed(0)}%, {mayoria.cantidad} de{" "}
                  {totalConNivel})
                </p>
              )}
            </div>
          )}

          {tieneAlertasPosibles && d.en_alerta !== null && (
            <p className="text-xs">
              <span className={d.en_alerta > 0 ? "text-amber-700 font-medium" : "text-ink/40 dark:text-ink-dark/40"}>
                {d.en_alerta} de {d.n} en alerta ({d.n > 0 ? ((d.en_alerta / d.n) * 100).toFixed(0) : 0}%)
              </span>
            </p>
          )}
        </>
      )}
    </div>
  );
}

function VistaRango({ resumen }: { resumen: ResumenEstadisticoDashboard }) {
  const { dimensiones, agrupar_dimensiones_por_area, tiene_alertas_posibles, areas_compatibles } = resumen;

  if (!agrupar_dimensiones_por_area) {
    return (
      <div className="divide-y divide-border dark:divide-border-dark">
        {dimensiones.map((d) => (
          <BloqueDimensionRango key={d.nombre} d={d} tieneAlertasPosibles={tiene_alertas_posibles} />
        ))}
      </div>
    );
  }

  // Agrupamiento por área (CHASIDE) — empareja "Intereses — X" / "Aptitudes
  // — X" por su código de área para el layout visual; lo que no sigue la
  // convención se muestra suelto al final.
  const areas = new Map<string, { nombreArea: string; interes?: DimensionResumenEstadistico; aptitud?: DimensionResumenEstadistico }>();
  const sueltas: DimensionResumenEstadistico[] = [];
  for (const d of dimensiones) {
    const m = PATRON_DIMENSION_AREA.exec(d.nombre);
    if (!m) {
      sueltas.push(d);
      continue;
    }
    const [, tipo, codigo, nombreArea] = m;
    const entrada = areas.get(codigo) ?? { nombreArea };
    if (tipo === "Intereses") entrada.interes = d;
    else entrada.aptitud = d;
    areas.set(codigo, entrada);
  }

  return (
    <div className="space-y-4">
      {areas_compatibles.length > 0 && (
        <div className="rounded-card bg-mist/60 dark:bg-surface-raised-dark p-3 space-y-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink/60 dark:text-ink-dark/60">Áreas vocacionales compatibles más frecuentes</p>
          <div className="flex flex-wrap gap-2">
            {areas_compatibles.map((a) => (
              <span key={a.area} className="rounded-full px-2 py-0.5 bg-surface dark:bg-surface-dark border border-border dark:border-border-dark text-xs text-ink/70 dark:text-ink-dark/70">
                {a.area}: {a.cantidad} alumno{a.cantidad === 1 ? "" : "s"}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="divide-y divide-border dark:divide-border-dark">
        {Array.from(areas.values()).map((entrada) => (
          <div key={entrada.nombreArea} className="py-2">
            <p className="text-sm font-semibold text-teal-900 dark:text-teal-accent-dark mb-1">{entrada.nombreArea}</p>
            <div className="divide-y divide-border/60 dark:divide-border-dark">
              {entrada.interes && <BloqueDimensionRango d={entrada.interes} tieneAlertasPosibles={tiene_alertas_posibles} />}
              {entrada.aptitud && <BloqueDimensionRango d={entrada.aptitud} tieneAlertasPosibles={tiene_alertas_posibles} />}
            </div>
          </div>
        ))}
        {sueltas.map((d) => (
          <BloqueDimensionRango key={d.nombre} d={d} tieneAlertasPosibles={tiene_alertas_posibles} />
        ))}
      </div>
    </div>
  );
}

function VistaPerfil({ dimensiones }: { dimensiones: DimensionResumenEstadistico[] }) {
  // Modo "perfil" (hoy solo IPIP-RIASEC): nunca hay niveles/alertas que
  // mostrar (interpretar_perfil_alumno nunca marca es_alerta ni consulta
  // Baremo, ver docs/motor-scoring.md) — en su lugar, dos lecturas
  // comparativas del grupo: el promedio por dimensión, y cuántos alumnos la
  // tienen como su 1ª (dominante_cantidad, ya calculado server-side).
  const totalDominante = dimensiones.reduce((acc, d) => acc + (d.dominante_cantidad ?? 0), 0);
  const ordenadas = [...dimensiones].sort((a, b) => (b.media ?? -Infinity) - (a.media ?? -Infinity));

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">
        Esta prueba interpreta por ranking comparativo entre dimensiones, no por rango absoluto — nunca hay niveles de alerta que mostrar.
      </p>
      <div className="divide-y divide-border dark:divide-border-dark">
        {ordenadas.map((d) => (
          <div key={d.nombre} className="py-2 space-y-1">
            <p className="text-sm font-semibold text-ink/80 dark:text-ink-dark/80">{d.nombre}</p>
            {d.n === 0 ? (
              <p className="text-xs text-ink/40 dark:text-ink-dark/40 italic">Sin datos todavía.</p>
            ) : (
              <>
                <EstadisticasNumericas d={d} />
                <div className="flex items-center gap-2 text-xs">
                  <div className="flex-1 h-2 rounded-full bg-border dark:bg-border-dark overflow-hidden">
                    <div
                      className="h-full rounded-full bg-teal-600 dark:bg-teal-accent-dark"
                      style={{
                        width: `${totalDominante > 0 ? Math.max(((d.dominante_cantidad ?? 0) / totalDominante) * 100, (d.dominante_cantidad ?? 0) > 0 ? 2 : 0) : 0}%`,
                      }}
                    />
                  </div>
                  <span className="w-44 shrink-0 text-right text-ink/50 dark:text-ink-dark/50">
                    {d.dominante_cantidad ?? 0} alumno{(d.dominante_cantidad ?? 0) === 1 ? "" : "s"} la tienen como 1ª
                  </span>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ResumenEstadisticoPrueba({ resumen }: Props) {
  // Sin dimensiones catalogadas (prueba sin Dimension cargada, o snapshot
  // viejo de antes de este feature) o sin ningún alumno con resultados
  // todavía — no hay nada que resumir, mismo criterio que el resto del
  // dashboard ("Sin alumnos matriculados todavía").
  if (resumen.dimensiones.length === 0 || resumen.dimensiones.every((d) => d.n === 0)) {
    return <p className="text-sm text-ink/60 dark:text-ink-dark/60 italic py-2">Todavía no hay resultados suficientes para un resumen estadístico.</p>;
  }

  return resumen.modo_interpretacion === "perfil" ? (
    <VistaPerfil dimensiones={resumen.dimensiones} />
  ) : (
    <VistaRango resumen={resumen} />
  );
}
