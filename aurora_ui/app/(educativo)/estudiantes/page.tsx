"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Persona, SeccionActual } from "@/types/api";
import { TextoError } from "@/components/ui/TextoError";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import { EsqueletoFilasTabla } from "@/components/ui/Esqueleto";

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

function TarjetaResumen({
  etiqueta,
  valor,
  activa,
  onClick,
}: {
  etiqueta: string;
  valor: number | string;
  activa?: boolean;
  onClick?: () => void;
}) {
  const Elemento = onClick ? "button" : "div";
  return (
    <Elemento
      onClick={onClick}
      className={`text-left bg-white rounded-card border p-4 transition-colors ${
        activa ? "border-teal-600 bg-teal-600/5" : "border-border"
      } ${onClick ? "hover:border-teal-400 cursor-pointer" : ""}`}
    >
      <div className="font-display text-2xl font-semibold text-teal-900">{valor}</div>
      <div className="mt-0.5 text-xs text-ink/60">{etiqueta}</div>
    </Elemento>
  );
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

  return (
    <div className="max-w-7xl mx-auto lg:px-6 lg:py-8 space-y-8">
      {/* Cabecera */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <div>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-teal-900 tracking-tight">Padrón</h1>
          <p className="mt-1 text-sm text-ink/60">
            Estudiantes registrados en tu institución — busca, revisa su estado y entra a la ficha de cada uno.
          </p>
        </div>
        {/* 🔧 El backend ya rechaza /admin/personas/ (alta) y /importar/* con
            403 para "colegio" (permisos.STAFF_CLINICO excluye ese rol), pero
            estos dos links no tenían su propio candado — desde que
            (educativo)/layout.tsx deja entrar a "colegio" (antes lo
            expulsaba por error), ese rol veía ambos botones sin que
            llevaran a nada que pudiera completar. */}
        {puedeGestionarPadron && (
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/estudiantes/importar"
              className="rounded-card border border-border bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-mist transition-colors"
            >
              Importar Excel
            </Link>
            <Link
              href="/estudiantes/nuevo"
              className="rounded-card bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-900 transition-colors shadow-sm"
            >
              + Registrar alumno
            </Link>
          </div>
        )}
      </div>

      {/* Resumen — cada tarjeta aplica su filtro correspondiente en la tabla de abajo */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <TarjetaResumen
          etiqueta="Activos"
          valor={cargando ? "…" : resumen.activos}
          activa={filtroEstado === "activos"}
          onClick={() => setFiltroEstado("activos")}
        />
        <TarjetaResumen
          etiqueta="Inactivos"
          valor={cargando ? "…" : resumen.inactivos}
          activa={filtroEstado === "inactivos"}
          onClick={() => setFiltroEstado("inactivos")}
        />
        <TarjetaResumen
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
        <TarjetaResumen
          etiqueta="Sin matrícula"
          valor={cargando ? "…" : resumen.sinMatricula}
          activa={filtroSeccionId === "sin-matricula"}
          onClick={() => {
            setFiltroEstado("activos"); // mismo motivo: el conteo también es solo sobre activos
            setFiltroSeccionId((v) => (v === "sin-matricula" ? "todas" : "sin-matricula"));
          }}
        />
      </div>

      {/* Barra de herramientas — búsqueda y filtro de estado respiran aparte de la tabla */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Input
          type="text"
          placeholder="Buscar por nombre, apellido o documento…"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="w-full max-w-sm bg-white placeholder:text-ink/40"
        />

        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={filtroSeccionId}
            onChange={(e) => setFiltroSeccionId(e.target.value)}
            className="bg-white min-w-0 flex-1 sm:flex-none"
          >
            <option value="todas">Todas las secciones</option>
            <option value="sin-matricula">Sin matrícula</option>
            {seccionesDisponibles.map((s) => (
              <option key={s.id} value={s.id}>
                {s.etiqueta}
              </option>
            ))}
          </Select>

          <div className="inline-flex items-center gap-0.5 rounded-card border border-border bg-white p-1 self-start">
            {FILTROS_ESTADO.map((f) => (
              <button
                key={f.valor}
                onClick={() => setFiltroEstado(f.valor)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  filtroEstado === f.valor ? "bg-teal-600 text-white" : "text-ink/60 hover:text-ink hover:bg-mist"
                }`}
              >
                {f.etiqueta}
              </button>
            ))}
          </div>
        </div>
      </div>

      <TextoError>{error}</TextoError>
      <TextoError>{errorAccion}</TextoError>

      {/* Tabla — overflow-x-auto: en pantallas angostas se desplaza de lado
          dentro de su tarjeta en vez de empujar la página entera. */}
      <div className="rounded-card border border-border bg-white shadow-sm overflow-x-auto">
        <table className="w-full min-w-[36rem] text-sm border-collapse">
          <thead>
            <TheadFila>
              <Th className="px-5 py-3">Nombre</Th>
              <Th className="px-5 py-3">Documento</Th>
              <Th className="px-5 py-3">Sección</Th>
              <Th className="px-5 py-3">Estado</Th>
              {esAdmin && <Th className="px-5 py-3"></Th>}
            </TheadFila>
          </thead>
          <tbody>
            {cargando && <EsqueletoFilasTabla filas={8} columnas={esAdmin ? 5 : 4} />}
            {!cargando && personasFiltradas.length === 0 && (
              <tr>
                <td colSpan={esAdmin ? 5 : 4} className="px-5 py-10 text-center text-sm text-ink/40">
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
                    className="cursor-pointer border-b border-border last:border-0 transition-colors hover:bg-mist focus-within:bg-teal-400/10 focus-within:ring-1 focus-within:ring-inset focus-within:ring-teal-400"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/estudiantes/${persona.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium text-teal-900 hover:text-teal-600 focus:outline-none"
                      >
                        {persona.nombres} {persona.apellidos}
                      </Link>
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-ink/70">
                      {persona.documento_identidad ?? "—"}
                    </td>
                    <td className="px-5 py-3">
                      {seccion ? (
                        <div>
                          <div className="text-ink">{seccion.linea}</div>
                          {seccion.detalle && <div className="text-xs text-ink/40 mt-0.5">{seccion.detalle}</div>}
                        </div>
                      ) : (
                        <span className="text-ink/40">Sin matrícula</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          persona.activo ? "bg-teal-400/20 text-teal-900" : "bg-border text-ink/50"
                        }`}
                      >
                        {persona.activo ? "Activo" : "Inactivo"}
                      </span>
                    </td>
                    {esAdmin && (
                      <td className="px-5 py-3 text-right whitespace-nowrap">
                        <button
                          onClick={(e) => alternarActivo(persona, e)}
                          disabled={actualizandoId === persona.id}
                          className="text-xs font-medium text-ink/60 hover:text-ink hover:underline disabled:opacity-50"
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
        <div className="flex items-center justify-between">
          <p className="text-xs text-ink/50">
            {pagina * TAMANO_PAGINA + 1}–{Math.min((pagina + 1) * TAMANO_PAGINA, personasFiltradas.length)} de{" "}
            {personasFiltradas.length} alumnos
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPagina((p) => Math.max(0, p - 1))}
              disabled={pagina === 0}
              className="rounded-card border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-mist disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Anterior
            </button>
            <button
              onClick={() => setPagina((p) => p + 1)}
              disabled={(pagina + 1) * TAMANO_PAGINA >= personasFiltradas.length}
              className="rounded-card border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-mist disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
