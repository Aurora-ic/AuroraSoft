"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Users, Hourglass, Search, ArrowRight, HeartHandshake, CheckCircle2 } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado } from "@/components/ui/Encabezado";
import { VacioFicha } from "@/components/educativo/BloqueFicha";

// Forma real de GET /educativo/casos-pendientes (ver
// crud.obtener_casos_pendientes_de_seguimiento). 🔧 Antes esta pantalla
// leía `prueba`/`nivel`/`fecha`, claves que el endpoint nunca devolvía —
// cada tarjeta mostraba el nombre del alumno con todo lo demás vacío.
// `prueba`/`dimension`/`campana`/ids se sumaron al backend en la sesión
// 2026-10-30 (aditivo: Inicio sigue leyendo `nivel_alerta` igual que antes).
type CasoRiesgo = {
  persona_id: number;
  nombre_completo: string | null;
  nivel_alerta: string;
  fecha_evaluacion: string | null;
  inscripcion_id?: number;
  evaluacion_id?: number;
  campana?: string | null;
  prueba?: string | null;
  dimension?: string | null;
};

// Un alumno puede tener varias dimensiones en alerta (incluso de pruebas
// distintas) — el worklist es POR ALUMNO, no una fila por diagnóstico.
type CasoAgrupado = {
  persona_id: number;
  nombre_completo: string;
  alertas: CasoRiesgo[];
  pruebas: string[];
  fechaMasAntigua: Date | null;
};

type Orden = "antiguos" | "recientes";

const DIA_MS = 24 * 60 * 60 * 1000;

function diasDesde(fecha: Date | null): number | null {
  if (!fecha) return null;
  return Math.max(0, Math.floor((Date.now() - fecha.getTime()) / DIA_MS));
}

function textoDias(dias: number | null): string {
  if (dias === null) return "Sin fecha";
  if (dias === 0) return "Hoy";
  if (dias === 1) return "Hace 1 día";
  return `Hace ${dias} días`;
}

function iniciales(nombre: string): string {
  return nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export default function CasosRiesgoPage() {
  const [casos, setCasos] = useState<CasoRiesgo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [busqueda, setBusqueda] = useState("");
  const [filtroPrueba, setFiltroPrueba] = useState("todas");
  const [orden, setOrden] = useState<Orden>("antiguos");

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

  const agrupados = useMemo<CasoAgrupado[]>(() => {
    const mapa = new Map<number, CasoAgrupado>();
    for (const c of casos) {
      const g = mapa.get(c.persona_id) ?? {
        persona_id: c.persona_id,
        nombre_completo: c.nombre_completo || "Alumno sin nombre",
        alertas: [],
        pruebas: [],
        fechaMasAntigua: null,
      };
      g.alertas.push(c);
      if (c.prueba && !g.pruebas.includes(c.prueba)) g.pruebas.push(c.prueba);
      if (c.fecha_evaluacion) {
        const f = new Date(c.fecha_evaluacion);
        if (!Number.isNaN(f.getTime()) && (!g.fechaMasAntigua || f < g.fechaMasAntigua)) g.fechaMasAntigua = f;
      }
      mapa.set(c.persona_id, g);
    }
    return Array.from(mapa.values());
  }, [casos]);

  const pruebasDisponibles = useMemo(
    () => Array.from(new Set(casos.map((c) => c.prueba).filter((p): p is string => !!p))).sort(),
    [casos],
  );

  const visibles = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    const filtrados = agrupados.filter((g) => {
      if (filtroPrueba !== "todas" && !g.pruebas.includes(filtroPrueba)) return false;
      if (texto && !g.nombre_completo.toLowerCase().includes(texto)) return false;
      return true;
    });
    // Sin fecha al final siempre, en ambos órdenes.
    return filtrados.sort((a, b) => {
      const ta = a.fechaMasAntigua?.getTime();
      const tb = b.fechaMasAntigua?.getTime();
      if (ta === undefined && tb === undefined) return 0;
      if (ta === undefined) return 1;
      if (tb === undefined) return -1;
      return orden === "antiguos" ? ta - tb : tb - ta;
    });
  }, [agrupados, busqueda, filtroPrueba, orden]);

  const masAntiguo = useMemo(() => {
    const dias = agrupados.map((g) => diasDesde(g.fechaMasAntigua)).filter((d): d is number => d !== null);
    return dias.length ? Math.max(...dias) : null;
  }, [agrupados]);

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-5">
      <EncabezadoPagina variante="destacado"
        icono={AlertTriangle}
        acento="azul"
        titulo="Casos en riesgo"
        descripcion="Alumnos con al menos un resultado en nivel de alerta y sin una sesión de seguimiento registrada desde entonces."
      />

      <div className="grid grid-cols-1 min-[480px]:grid-cols-3 gap-3">
        <TarjetaKpi icono={Users} tono="riesgo" etiqueta="Alumnos pendientes" valor={cargando ? "…" : agrupados.length} />
        <TarjetaKpi icono={AlertTriangle} tono="riesgo" etiqueta="Resultados en alerta" valor={cargando ? "…" : casos.length} />
        <TarjetaKpi
          icono={Hourglass}
          tono="neutro"
          etiqueta="Espera más larga"
          valor={cargando ? "…" : masAntiguo === null ? "—" : masAntiguo}
          detalle={masAntiguo !== null && !cargando ? "días sin seguimiento" : undefined}
        />
      </div>

      <TextoError>{error}</TextoError>

      {(agrupados.length > 0 || cargando) && (
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-xs">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
            <input
              type="search"
              aria-label="Buscar alumno"
              placeholder="Buscar alumno…"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              className="w-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {pruebasDisponibles.length > 1 && (
              <Select value={filtroPrueba} onChange={(e) => setFiltroPrueba(e.target.value)} aria-label="Filtrar por prueba">
                <option value="todas">Todas las pruebas</option>
                {pruebasDisponibles.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            )}
            <ControlSegmentado<Orden>
              etiqueta="Orden"
              valor={orden}
              onCambiar={setOrden}
              opciones={[
                { valor: "antiguos", etiqueta: "Más antiguos" },
                { valor: "recientes", etiqueta: "Más recientes" },
              ]}
            />
          </div>
        </div>
      )}

      {cargando && <EsqueletoLista cantidad={4} />}

      {!cargando && !error && casos.length === 0 && (
        <VacioFicha icono={CheckCircle2} texto="No hay casos pendientes de seguimiento. Todos los resultados en alerta ya tienen una sesión registrada." />
      )}

      {!cargando && agrupados.length > 0 && visibles.length === 0 && (
        <p className="m-0 text-sm text-ink/50 dark:text-ink-dark/50 italic">Ningún caso coincide con el filtro.</p>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {visibles.map((g) => {
          const dias = diasDesde(g.fechaMasAntigua);
          // >14 días sin seguimiento: se resalta la espera, no el riesgo
          // (el riesgo ya lo marca el ámbar de toda la tarjeta).
          const esperaLarga = dias !== null && dias > 14;
          return (
            <article
              key={g.persona_id}
              className="rounded-xl border border-amber/35 border-l-4 border-l-amber bg-surface dark:bg-surface-dark p-4 flex flex-col gap-3"
            >
              <div className="flex items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber/15 text-amber-700 dark:text-amber font-display text-[13px] font-bold">
                  {iniciales(g.nombre_completo)}
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={`/estudiantes/${g.persona_id}`}
                    className="block text-[14px] font-bold text-ink dark:text-ink-dark hover:text-teal-700 dark:hover:text-teal-accent-dark truncate"
                  >
                    {g.nombre_completo}
                  </Link>
                  <p className="m-0 mt-0.5 text-[11.5px] text-ink/50 dark:text-ink-dark/50">
                    {g.alertas.length} resultado{g.alertas.length === 1 ? "" : "s"} en alerta
                    {g.pruebas.length > 0 ? ` · ${g.pruebas.join(", ")}` : ""}
                  </p>
                </div>
                <span
                  className={`shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${
                    esperaLarga
                      ? "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300"
                      : "bg-mist text-ink/60 dark:bg-surface-raised-dark dark:text-ink-dark/60"
                  }`}
                  title={g.fechaMasAntigua ? g.fechaMasAntigua.toLocaleDateString("es-PE") : undefined}
                >
                  <Hourglass size={10} aria-hidden="true" />
                  {textoDias(dias)}
                </span>
              </div>

              <ul className="m-0 p-0 list-none flex flex-wrap gap-1.5">
                {g.alertas.map((a, i) => (
                  <li
                    key={`${a.inscripcion_id ?? i}-${a.dimension ?? i}`}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-amber/30 bg-amber/[0.07] px-2 py-1 text-[11.5px]"
                    title={a.campana ? `Campaña: ${a.campana}` : undefined}
                  >
                    <AlertTriangle size={11} className="text-amber shrink-0" aria-hidden="true" />
                    <span className="text-ink/70 dark:text-ink-dark/70">
                      {[a.prueba, a.dimension].filter(Boolean).join(" · ") || "Resultado"}
                    </span>
                    <span className="font-bold text-amber-800 dark:text-amber">{a.nivel_alerta}</span>
                  </li>
                ))}
              </ul>

              <div className="flex items-center justify-end gap-3 pt-2 border-t border-border/70 dark:border-border-dark text-[12px] font-semibold">
                <Link
                  href={`/estudiantes/${g.persona_id}/seguimiento/nuevo`}
                  className="inline-flex items-center gap-1.5 text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark"
                >
                  <HeartHandshake size={14} aria-hidden="true" />
                  Registrar seguimiento
                </Link>
                <Link
                  href={`/estudiantes/${g.persona_id}`}
                  className="inline-flex items-center gap-1 text-teal-700 dark:text-teal-accent-dark hover:underline"
                >
                  Ver ficha
                  <ArrowRight size={13} aria-hidden="true" />
                </Link>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
