"use client";

import { useConfirmar } from "@/components/ui/DialogoConfirmacion";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Users, UserCheck, UserX, FileWarning, School, Search, Upload, Plus, ChevronLeft, ChevronRight, Stethoscope } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Persona, RespuestaPaginada, ResumenPadron, SeccionActual } from "@/types/api";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { EsqueletoFilasTabla } from "@/components/ui/Esqueleto";
import { EncabezadoPagina, TarjetaKpi, ControlSegmentado, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";

// 🆕 (sesión 2026-10-31) "con-dx" = activos con diagnóstico — derivado en
// el backend (Persona.con_diagnostico) de los antecedentes clínicos externos
// de cada ficha: terapia psicológica o atención psiquiátrica externa = Sí.
// No hay un botón "en riesgo" aparte: se marca/desmarca solo al llenar esos
// dos Sí/No en la ficha.
type FiltroEstado = "activos" | "inactivos" | "todos" | "con-dx";

const FILTROS_ESTADO: { valor: FiltroEstado; etiqueta: string }[] = [
  { valor: "activos", etiqueta: "Activos" },
  { valor: "inactivos", etiqueta: "Inactivos" },
  { valor: "todos", etiqueta: "Todos" },
  { valor: "con-dx", etiqueta: "Con Dx" },
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
  // 🆕 Diálogo de confirmación propio (reemplaza window.confirm).
  const confirmar = useConfirmar();
  const { sesion } = useAuth();
  const router = useRouter();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [totalFiltrado, setTotalFiltrado] = useState(0);
  const [resumen, setResumen] = useState<ResumenPadron | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [busquedaAplicada, setBusquedaAplicada] = useState("");
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>("activos");
  // "todas" | "sin-matricula" | String(seccion_id)
  const [filtroSeccionId, setFiltroSeccionId] = useState<string>("todas");
  const [soloIncompletos, setSoloIncompletos] = useState(false);
  const [pagina, setPagina] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actualizandoId, setActualizandoId] = useState<number | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  // Sube tras activar/desactivar a alguien: recarga página y tarjetas.
  const [recarga, setRecarga] = useState(0);

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

  // 🆕 Escalabilidad (sesión 2026-11-01) — antes esta pantalla bajaba el
  // padrón COMPLETO (getTodasLasPaginas, de a 200: con 5000 alumnos, 25
  // peticiones y 5000 filas en memoria) para filtrar y contar en el
  // navegador. Ahora:
  // - la tabla pide UNA página de 50 ya filtrada en el servidor (estado,
  //   sección, incompletos, búsqueda — mismos criterios que antes, ver
  //   crud._consulta_padron_filtrada y tests/verificar_padron_servidor_equivalencia.py);
  // - las 5 tarjetas y el desplegable de secciones salen de
  //   /resumen-padron (agregados SQL sobre TODO el padrón, nunca sobre la
  //   página visible — mismo significado que antes).
  useEffect(() => {
    if (!sesion?.institucionId) return;
    let vigente = true;
    apiClient
      .get<ResumenPadron>(`/admin/personas/${sesion.institucionId}/resumen-padron`)
      .then((r) => vigente && setResumen(r))
      .catch((err) => vigente && setError(err.message));
    return () => {
      vigente = false;
    };
  }, [sesion?.institucionId, recarga]);

  // La búsqueda se manda 300 ms después de dejar de escribir.
  useEffect(() => {
    const t = setTimeout(() => {
      setBusquedaAplicada(busqueda.trim());
      setPagina(0);
    }, 300);
    return () => clearTimeout(t);
  }, [busqueda]);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    let vigente = true;
    const params = new URLSearchParams({
      estado: filtroEstado === "con-dx" ? "con_dx" : filtroEstado,
      skip: String(pagina * TAMANO_PAGINA),
      limit: String(TAMANO_PAGINA),
    });
    if (busquedaAplicada) params.set("busqueda", busquedaAplicada);
    if (filtroSeccionId === "sin-matricula") params.set("sin_matricula", "true");
    else if (filtroSeccionId !== "todas") params.set("seccion_id", filtroSeccionId);
    if (soloIncompletos) params.set("datos_incompletos", "true");
    setCargando(true);
    setError(null);
    apiClient
      .get<RespuestaPaginada<Persona>>(`/admin/personas/${sesion.institucionId}?${params.toString()}`)
      .then((r) => {
        if (!vigente) return;
        setPersonas(r.items);
        setTotalFiltrado(r.total);
      })
      .catch((err) => vigente && setError(err.message))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [sesion?.institucionId, busquedaAplicada, filtroEstado, filtroSeccionId, soloIncompletos, pagina, recarga]);

  // Cambiar un filtro vuelve a la página 1 — si no, "página 3" de un filtro
  // nuevo podría quedar vacía sin que sea obvio por qué. (En el handler, no
  // en un efecto: así no se dispara una petición con la página vieja.)
  function cambiarEstado(v: FiltroEstado | ((prev: FiltroEstado) => FiltroEstado)) {
    setFiltroEstado(v);
    setPagina(0);
  }
  function cambiarSeccion(v: string | ((prev: string) => string)) {
    setFiltroSeccionId(v);
    setPagina(0);
  }
  function cambiarIncompletos(v: boolean | ((prev: boolean) => boolean)) {
    setSoloIncompletos(v);
    setPagina(0);
  }

  const seccionesDisponibles = useMemo(
    () =>
      (resumen?.secciones ?? [])
        .map((s) => ({ id: s.seccion_id, etiqueta: [s.nivel_educativo, s.grado, s.seccion].filter(Boolean).join(" · ") }))
        .sort((a, b) => a.etiqueta.localeCompare(b.etiqueta)),
    [resumen],
  );

  // La página visible ya viene filtrada del servidor.
  const personasPaginaActual = personas;
  const cargandoResumen = resumen === null;

  async function alternarActivo(persona: Persona, e: React.MouseEvent) {
    e.stopPropagation(); // no navegar a la ficha al hacer clic en el botón de la fila
    const nombre = `${persona.nombres} ${persona.apellidos}`;
    if (
      !(await confirmar(
        persona.activo
          ? {
              titulo: `¿Desactivar a ${nombre}?`,
              mensaje: "Deja de aparecer en el padrón activo y no se le podrá aplicar pruebas. Puedes reactivarlo después.",
              textoConfirmar: "Desactivar",
              peligro: true,
            }
          : { titulo: `¿Reactivar a ${nombre}?`, mensaje: "Vuelve al padrón activo.", textoConfirmar: "Reactivar" },
      ))
    )
      return;
    setActualizandoId(persona.id);
    setErrorAccion(null);
    try {
      const actualizado = await apiClient.patch<Persona>(`/admin/personas/${persona.id}`, {
        activo: !persona.activo,
      });
      setPersonas((prev) => prev.map((p) => (p.id === persona.id ? { ...p, ...actualizado } : p)));
      // Tarjetas y filtro (p. ej. "Activos") cambian: se vuelven a pedir.
      setRecarga((n) => n + 1);
    } catch (err: any) {
      setErrorAccion(err.message || "No se pudo cambiar el estado del alumno.");
    } finally {
      setActualizandoId(null);
    }
  }

  const hayFiltrosExtra = soloIncompletos || filtroSeccionId !== "todas" || busqueda.trim() !== "";

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
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
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <TarjetaKpi
          icono={UserCheck}
          etiqueta="Activos"
          valor={cargandoResumen ? "…" : resumen.activos}
          activa={filtroEstado === "activos"}
          onClick={() => cambiarEstado("activos")}
        />
        <TarjetaKpi
          icono={UserX}
          tono="neutro"
          etiqueta="Inactivos"
          valor={cargandoResumen ? "…" : resumen.inactivos}
          activa={filtroEstado === "inactivos"}
          onClick={() => cambiarEstado("inactivos")}
        />
        <TarjetaKpi
          icono={FileWarning}
          tono="neutro"
          etiqueta="Datos incompletos"
          valor={cargandoResumen ? "…" : resumen.datos_incompletos}
          activa={soloIncompletos}
          onClick={() => {
            // El conteo es solo sobre activos — al filtrar, la tabla debe
            // quedar acotada igual, o mostraría filas que el número no contó.
            cambiarEstado("activos");
            cambiarIncompletos((v) => !v);
          }}
        />
        <TarjetaKpi
          icono={School}
          tono="neutro"
          etiqueta="Sin matrícula"
          valor={cargandoResumen ? "…" : resumen.sin_matricula}
          activa={filtroSeccionId === "sin-matricula"}
          onClick={() => {
            cambiarEstado("activos"); // mismo motivo: el conteo también es solo sobre activos
            cambiarSeccion((v) => (v === "sin-matricula" ? "todas" : "sin-matricula"));
          }}
        />
        {/* Ámbar: es riesgo clínico (tratamiento externo), no un dato administrativo. */}
        <TarjetaKpi
          icono={Stethoscope}
          tono="riesgo"
          etiqueta="Con diagnóstico"
          valor={cargandoResumen ? "…" : resumen.con_diagnostico}
          activa={filtroEstado === "con-dx"}
          onClick={() => cambiarEstado((v) => (v === "con-dx" ? "activos" : "con-dx"))}
        />
      </div>

      <TextoError>{error}</TextoError>
      <TextoError>{errorAccion}</TextoError>

      <div className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
        {/* Barra de herramientas — dentro de la misma tarjeta que la tabla */}
        <div className="flex flex-col gap-2.5 md:flex-row md:items-center md:justify-between px-4 py-3 border-b border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.08] dark:bg-teal-accent-dark/[0.08]">
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
                  cambiarSeccion("todas");
                  cambiarIncompletos(false);
                }}
                className="text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
              >
                Limpiar filtros
              </button>
            )}
            <Select
              value={filtroSeccionId}
              onChange={(e) => cambiarSeccion(e.target.value)}
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
              onCambiar={cambiarEstado}
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
              {!cargando && totalFiltrado === 0 && (
                <tr>
                  <td colSpan={esAdmin ? 5 : 4} className="px-4 py-10 text-center text-sm text-ink/40 dark:text-ink-dark/40">
                    No se encontraron alumnos.
                  </td>
                </tr>
              )}
              {!cargando &&
                personasPaginaActual.map((persona) => {
                  const seccion = formatearSeccion(persona.seccion_actual);
                  const conDx = !!persona.con_diagnostico;
                  return (
                    <tr
                      key={persona.id}
                      onClick={() => router.push(`/estudiantes/${persona.id}`)}
                      className={`cursor-pointer border-b border-border dark:border-border-dark last:border-0 transition-colors focus-within:ring-1 focus-within:ring-inset focus-within:ring-teal-400 ${
                        conDx
                          ? "bg-amber/[0.09] shadow-[inset_3px_0_0_var(--color-amber)] hover:bg-amber/15"
                          : "hover:bg-mist dark:hover:bg-surface-raised-dark focus-within:bg-teal-400/10"
                      }`}
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span
                            aria-hidden="true"
                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold ${
                              conDx
                                ? "bg-amber/25 text-amber-800 dark:bg-amber/20 dark:text-amber"
                                : persona.activo
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
                          {conDx && (
                            <span
                              title="Con diagnóstico: terapia o psiquiatría externa en sus antecedentes clínicos"
                              className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber/20 px-2 py-0.5 text-[11.5px] font-bold text-amber-800 dark:bg-amber/15 dark:text-amber"
                            >
                              <Stethoscope size={11} aria-hidden="true" />
                              Dx
                            </span>
                          )}
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

        {!cargando && totalFiltrado > 0 && (
          <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.06] dark:bg-teal-accent-dark/[0.06]">
            <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">
              {pagina * TAMANO_PAGINA + 1}–{Math.min((pagina + 1) * TAMANO_PAGINA, totalFiltrado)} de{" "}
              {totalFiltrado} alumnos
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
                disabled={(pagina + 1) * TAMANO_PAGINA >= totalFiltrado}
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
