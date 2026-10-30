"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Users, UserCheck, UserX, FileWarning, School, Search, Upload, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Persona, SeccionActual } from "@/types/api";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { EsqueletoFilasTabla } from "@/components/ui/Esqueleto";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado, claseBotonBanner } from "@/components/ui/Encabezado";

type FiltroEstado = "activos" | "inactivos" | "todos";

const FILTROS_ESTADO: { valor: FiltroEstado; etiqueta: string }[] = [
  { valor: "activos", etiqueta: "Activos" },
  { valor: "inactivos", etiqueta: "Inactivos" },
  { valor: "todos", etiqueta: "Todos" },
];

// seccion_actual llega batch-loaded en la misma respuesta del padrón — nunca
// usar Persona.grado_seccion (texto libre heredado que ningún flujo de
// matrícula mantiene al día) para mostrar la sección real de un alumno.
function formatearSeccion(seccion: SeccionActual | null): { linea: string; detalle: string | null } | null {
  if (!seccion) return null;
  const partes = [seccion.nivel_educativo, seccion.grado, seccion.seccion].filter(Boolean);
  if (partes.length === 0) return null;
  return {
    linea: partes.join(" · "),
    detalle: seccion.turno ? `Turno ${seccion.turno}` : null,
  };
}

// Iniciales para el avatar de la fila — nunca el nombre completo otra vez
// (e2e/revision-informe.spec.ts hace getByText(nombre).click() en esta
// tabla: el nombre tiene que aparecer UNA sola vez por fila).
function iniciales(persona: Persona): string {
  return `${persona.nombres.trim()[0] ?? ""}${persona.apellidos.trim()[0] ?? ""}`.toUpperCase();
}

export default function PadronPage() {
  const { sesion } = useAuth();
  const router = useRouter();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>("activos");
  // "todas" | "sin-matricula" | String(seccion_id) — derivado de seccion_actual,
  // que ya viaja en la misma respuesta del padrón: sin llamadas adicionales.
  const [filtroSeccionId, setFiltroSeccionId] = useState<string>("todas");
  // Sin filtro exacto propio en el backend (no es ni estado ni sección) —
  // se resuelve en cliente igual que el resto, a partir del mismo criterio
  // que ya usa "resumen.datosIncompletos".
  const [soloIncompletos, setSoloIncompletos] = useState(false);
  const [pagina, setPagina] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actualizandoId, setActualizandoId] = useState<number | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);

  const TAMANO_PAGINA = 50;

  // Solo admin/superadmin pueden activar/desactivar (el backend ya lo exige
  // en PATCH /admin/personas/{id}) — psicólogo usa el proceso de promoción
  // anual (retiro/traslado, con motivo) para dar de baja a un estudiante,
  // nunca este atajo directo sin trazabilidad.
  const esAdmin = sesion?.rol === "admin" || sesion?.rol === "superadmin";

  // STAFF_CLINICO del backend (superadmin/admin/psicologo) — quien puede
  // registrar/importar estudiantes. "colegio" queda afuera.
  const puedeGestionarPadron =
    sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";

  // Un solo fetch al montar — el padrón completo (activos + inactivos). Las
  // 4 tarjetas de resumen y los filtros de sección/incompletos necesitan el
  // UNIVERSO completo (no tiene sentido un "Sin matrícula: 3" que solo
  // contara una página), así que busqueda/estado/sección se siguen
  // filtrando en cliente sobre esta misma lista, como siempre.
  //
  // 🆕 Paginación real (docs/gaps-pendientes.md) — la diferencia es CÓMO se
  // trae ese universo completo: antes, una sola consulta sin tope
  // (`.all()`) que crecía para siempre con los años; ahora, el mismo total
  // se junta en páginas acotadas de 200 (getTodasLasPaginas), así que el
  // backend nunca vuelve a ejecutar una consulta sin LIMIT. La tabla
  // renderizada, además, pagina de a 50 sobre el resultado ya filtrado
  // (ver `personasPaginaActual` más abajo) — sin eso, con cientos de
  // alumnos la tabla completa se pintaba de una sola vez.
  useEffect(() => {
    if (!sesion?.institucionId) return;
    setCargando(true);
    setError(null);
    apiClient
      .getTodasLasPaginas<Persona>(`/admin/personas/${sesion.institucionId}?incluir_inactivas=true`)
      .then(setPersonas)
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false));
  }, [sesion]);

  // Cualquier cambio en los filtros/búsqueda vuelve a la página 1 — si no,
  // "página 3" de un filtro nuevo podría quedar vacía sin que sea obvio por qué.
  useEffect(() => {
    setPagina(0);
  }, [busqueda, filtroEstado, filtroSeccionId, soloIncompletos]);

  const seccionesDisponibles = useMemo(() => {
    const mapa = new Map<number, string>();
    personas.forEach((p) => {
      if (p.seccion_actual) {
        const s = p.seccion_actual;
        mapa.set(s.seccion_id, [s.nivel_educativo, s.grado, s.seccion].filter(Boolean).join(" · "));
      }
    });
    return Array.from(mapa.entries())
      .map(([id, etiqueta]) => ({ id, etiqueta }))
      .sort((a, b) => a.etiqueta.localeCompare(b.etiqueta));
  }, [personas]);

  const personasFiltradas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    return personas.filter((p) => {
      if (filtroEstado === "activos" && !p.activo) return false;
      if (filtroEstado === "inactivos" && p.activo) return false;
      if (filtroSeccionId === "sin-matricula") {
        if (p.seccion_actual) return false;
      } else if (filtroSeccionId !== "todas") {
        if (p.seccion_actual?.seccion_id !== Number(filtroSeccionId)) return false;
      }
      if (soloIncompletos && p.genero && p.fecha_nacimiento) return false;
      if (texto) {
        const coincide =
          p.nombres.toLowerCase().includes(texto) ||
          p.apellidos.toLowerCase().includes(texto) ||
          (p.documento_identidad ?? "").toLowerCase().includes(texto);
        if (!coincide) return false;
      }
      return true;
    });
  }, [personas, busqueda, filtroEstado, filtroSeccionId, soloIncompletos]);

  // Página visible de la tabla — sobre el resultado YA filtrado, nunca
  // sobre el padrón completo. "Anterior"/"Siguiente" navegan acá.
  const personasPaginaActual = useMemo(
    () => personasFiltradas.slice(pagina * TAMANO_PAGINA, (pagina + 1) * TAMANO_PAGINA),
    [personasFiltradas, pagina],
  );

  // Resumen sobre el padrón completo (nunca sobre personasFiltradas) — las
  // tarjetas muestran el estado real de la institución, independiente de lo
  // que la búsqueda/filtros actuales estén mostrando en la tabla.
  const resumen = useMemo(() => {
    const activos = personas.filter((p) => p.activo);
    return {
      activos: activos.length,
      inactivos: personas.length - activos.length,
      // Mismo criterio que la importación por Excel (CAMPOS_OPCIONALES_REPORTABLES):
      // genero/fecha_nacimiento faltantes cuentan como "incompleto", documento_identidad no.
      datosIncompletos: activos.filter((p) => !p.genero || !p.fecha_nacimiento).length,
      sinMatricula: activos.filter((p) => !p.seccion_actual).length,
    };
  }, [personas]);

  async function alternarActivo(persona: Persona, e: React.MouseEvent) {
    e.stopPropagation(); // no navegar a la ficha al hacer clic en el botón de la fila
    const pregunta = persona.activo
      ? `¿Desactivar a ${persona.nombres} ${persona.apellidos}?`
      : `¿Reactivar a ${persona.nombres} ${persona.apellidos}?`;
    if (!window.confirm(pregunta)) return;
    setActualizandoId(persona.id);
    setErrorAccion(null);
    try {
      const actualizado = await apiClient.patch<Persona>(`/admin/personas/${persona.id}`, {
        activo: !persona.activo,
      });
      setPersonas((prev) => prev.map((p) => (p.id === persona.id ? { ...p, ...actualizado } : p)));
    } catch (err: any) {
      setErrorAccion(err.message || "No se pudo cambiar el estado del alumno.");
    } finally {
      setActualizandoId(null);
    }
  }

  const hayFiltrosExtra = soloIncompletos || filtroSeccionId !== "todas" || busqueda.trim() !== "";

  return (
    <div className="max-w-7xl mx-auto flex flex-col gap-4">
      {/* 🔧 El backend ya rechaza /admin/personas/ (alta) y /importar/* con
          403 para "colegio" (permisos.STAFF_CLINICO excluye ese rol), pero
          estos dos links no tenían su propio candado — desde que
          (educativo)/layout.tsx deja entrar a "colegio" (antes lo
          expulsaba por error), ese rol veía ambos botones sin que
          llevaran a nada que pudiera completar. */}
      <EncabezadoPagina variante="destacado"
        icono={Users}
        acento="teal"
        titulo="Padrón"
        descripcion="Estudiantes registrados en tu institución — busca, revisa su estado y entra a la ficha de cada uno."
        acciones={
          puedeGestionarPadron && (
            <>
              <Link href="/estudiantes/importar" className={claseBotonBanner("secundario")}>
                <Upload size={15} aria-hidden="true" />
                Importar Excel
              </Link>
              <Link href="/estudiantes/nuevo" className={claseBotonBanner("primario")}>
                <Plus size={15} strokeWidth={2.4} aria-hidden="true" />
                Registrar alumno
              </Link>
            </>
          )
        }
      />

      {/* Resumen — cada tarjeta aplica su filtro correspondiente en la tabla de abajo */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <TarjetaKpi
          icono={UserCheck}
          etiqueta="Activos"
          valor={cargando ? "…" : resumen.activos}
          activa={filtroEstado === "activos"}
          onClick={() => setFiltroEstado("activos")}
        />
        <TarjetaKpi
          icono={UserX}
          tono="neutro"
          etiqueta="Inactivos"
          valor={cargando ? "…" : resumen.inactivos}
          activa={filtroEstado === "inactivos"}
          onClick={() => setFiltroEstado("inactivos")}
        />
        <TarjetaKpi
          icono={FileWarning}
          tono="neutro"
          etiqueta="Datos incompletos"
          valor={cargando ? "…" : resumen.datosIncompletos}
          activa={soloIncompletos}
          onClick={() => {
            // El conteo es solo sobre activos — al filtrar, la tabla debe
            // quedar acotada igual, o mostraría filas que el número no contó.
            setFiltroEstado("activos");
            setSoloIncompletos((v) => !v);
          }}
        />
        <TarjetaKpi
          icono={School}
          tono="neutro"
          etiqueta="Sin matrícula"
          valor={cargando ? "…" : resumen.sinMatricula}
          activa={filtroSeccionId === "sin-matricula"}
          onClick={() => {
            setFiltroEstado("activos"); // mismo motivo: el conteo también es solo sobre activos
            setFiltroSeccionId((v) => (v === "sin-matricula" ? "todas" : "sin-matricula"));
          }}
        />
      </div>

      <TextoError>{error}</TextoError>
      <TextoError>{errorAccion}</TextoError>

      <div className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden">
        {/* Barra de herramientas — dentro de la misma tarjeta que la tabla */}
        <div className="flex flex-col gap-2.5 md:flex-row md:items-center md:justify-between px-4 py-3 border-b border-border dark:border-border-dark">
          <div className="relative w-full md:max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
            <input
              type="text"
              placeholder="Buscar por nombre, apellido o documento…"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              className="w-full rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark placeholder:text-ink/40 dark:placeholder:text-ink-dark/40 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {hayFiltrosExtra && (
              <button
                type="button"
                onClick={() => {
                  setBusqueda("");
                  setFiltroSeccionId("todas");
                  setSoloIncompletos(false);
                }}
                className="text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
              >
                Limpiar filtros
              </button>
            )}
            <Select
              value={filtroSeccionId}
              onChange={(e) => setFiltroSeccionId(e.target.value)}
              className="min-w-0 flex-1 md:flex-none"
              aria-label="Filtrar por sección"
            >
              <option value="todas">Todas las secciones</option>
              <option value="sin-matricula">Sin matrícula</option>
              {seccionesDisponibles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.etiqueta}
                </option>
              ))}
            </Select>

            <ControlSegmentado<FiltroEstado>
              etiqueta="Estado"
              valor={filtroEstado}
              onCambiar={setFiltroEstado}
              opciones={FILTROS_ESTADO}
            />
          </div>
        </div>

        {/* Tabla — overflow-x-auto: en pantallas angostas se desplaza de lado
            dentro de su tarjeta en vez de empujar la página entera. */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm border-collapse">
            <thead>
              <TheadFila>
                <Th className="px-4 py-2.5">Nombre</Th>
                <Th className="px-4 py-2.5">Documento</Th>
                <Th className="px-4 py-2.5">Sección</Th>
                <Th className="px-4 py-2.5">Estado</Th>
                {esAdmin && <Th className="px-4 py-2.5"></Th>}
              </TheadFila>
            </thead>
            <tbody>
              {cargando && <EsqueletoFilasTabla filas={8} columnas={esAdmin ? 5 : 4} />}
              {!cargando && personasFiltradas.length === 0 && (
                <tr>
                  <td colSpan={esAdmin ? 5 : 4} className="px-4 py-10 text-center text-sm text-ink/40 dark:text-ink-dark/40">
                    No se encontraron alumnos.
                  </td>
                </tr>
              )}
              {!cargando &&
                personasPaginaActual.map((persona) => {
                  const seccion = formatearSeccion(persona.seccion_actual);
                  return (
                    <tr
                      key={persona.id}
                      onClick={() => router.push(`/estudiantes/${persona.id}`)}
                      className="cursor-pointer border-b border-border dark:border-border-dark last:border-0 transition-colors hover:bg-mist dark:hover:bg-surface-raised-dark focus-within:bg-teal-400/10 focus-within:ring-1 focus-within:ring-inset focus-within:ring-teal-400"
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span
                            aria-hidden="true"
                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                              persona.activo
                                ? "bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
                                : "bg-border text-ink/45 dark:bg-border-dark dark:text-ink-dark/45"
                            }`}
                          >
                            {iniciales(persona)}
                          </span>
                          <Link
                            href={`/estudiantes/${persona.id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="font-semibold text-teal-900 dark:text-ink-dark hover:text-teal-600 dark:hover:text-teal-accent-dark focus:outline-none"
                          >
                            {persona.nombres} {persona.apellidos}
                          </Link>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-ink/70 dark:text-ink-dark/70">
                        {persona.documento_identidad ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {seccion ? (
                          <div>
                            <div className="text-ink dark:text-ink-dark">{seccion.linea}</div>
                            {seccion.detalle && (
                              <div className="text-xs text-ink/40 dark:text-ink-dark/40 mt-0.5">{seccion.detalle}</div>
                            )}
                          </div>
                        ) : (
                          <span className="text-ink/40 dark:text-ink-dark/40">Sin matrícula</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            persona.activo
                              ? "bg-teal-400/20 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
                              : "bg-border text-ink/50 dark:bg-border-dark dark:text-ink-dark/50"
                          }`}
                        >
                          <span
                            aria-hidden="true"
                            className={`h-1.5 w-1.5 rounded-full ${persona.activo ? "bg-teal-600 dark:bg-teal-accent-dark" : "bg-ink/30 dark:bg-ink-dark/30"}`}
                          />
                          {persona.activo ? "Activo" : "Inactivo"}
                        </span>
                      </td>
                      {esAdmin && (
                        <td className="px-4 py-2.5 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => alternarActivo(persona, e)}
                            disabled={actualizandoId === persona.id}
                            className="text-xs font-medium text-ink/60 dark:text-ink-dark/60 hover:text-ink dark:hover:text-ink-dark hover:underline disabled:opacity-50"
                          >
                            {actualizandoId === persona.id
                              ? "Actualizando…"
                              : persona.activo
                              ? "Desactivar"
                              : "Reactivar"}
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {!cargando && personasFiltradas.length > 0 && (
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-border dark:border-border-dark bg-mist/40 dark:bg-surface-raised-dark">
            <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">
              {pagina * TAMANO_PAGINA + 1}–{Math.min((pagina + 1) * TAMANO_PAGINA, personasFiltradas.length)} de{" "}
              {personasFiltradas.length} alumnos
            </p>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPagina((p) => Math.max(0, p - 1))}
                disabled={pagina === 0}
                className="inline-flex items-center gap-1 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2.5 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={13} aria-hidden="true" />
                Anterior
              </button>
              <button
                onClick={() => setPagina((p) => p + 1)}
                disabled={(pagina + 1) * TAMANO_PAGINA >= personasFiltradas.length}
                className="inline-flex items-center gap-1 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2.5 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Siguiente
                <ChevronRight size={13} aria-hidden="true" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
