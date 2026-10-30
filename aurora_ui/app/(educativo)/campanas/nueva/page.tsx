"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  ClipboardList,
  Search,
  Users,
  CalendarClock,
  Tag,
  Link2,
  Copy,
  CircleCheck,
  CircleAlert,
  ArrowRight,
  Info,
  UserRound,
  UsersRound,
  School,
  type LucideIcon,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Migas } from "@/components/ui/Migas";
import { ahoraParaInputLocal, fechaCierreEsPasada, MENSAJE_FECHA_CIERRE_PASADA } from "@/lib/campanas";
import type {
  Prueba,
  PruebaDetalle,
  Evaluacion,
  EvaluacionCreate,
  Persona,
  MatriculaRosterResponse,
  ConsentimientosCombinados,
  NivelEducativo,
  Grado,
  Seccion,
} from "@/types/api";

// Quién responde cada prueba — el psicólogo elige distinto si el
// instrumento lo contesta el alumno, su apoderado o un docente.
const INFORMANTES: Record<string, { label: string; icono: LucideIcon }> = {
  estudiante: { label: "Autoinforme", icono: UserRound },
  padre_madre: { label: "Padres", icono: UsersRound },
  docente: { label: "Docente", icono: School },
};

const PASOS = ["Configurar", "Matricular alumnos", "Compartir links"];

const CLASE_TARJETA = "rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm";

// Flujo en 3 pasos, uno a la vez — crear la campaña, matricular el padrón
// (o parte de él), y ver los links mágicos generados. Sin wizard de rutas
// separadas: todo en esta misma página, igual de simple que
// estudiantes/importar/page.tsx.
//
// 🆕 Rediseño visual (sesión 2026-10-29, a pedido del usuario: "quiero una
// interfaz más bonita, no simple") — misma lógica y mismos endpoints que
// antes; cambia la presentación: indicador de pasos, pruebas como tarjetas
// con búsqueda/filtro por informante, panel de resumen con las dimensiones
// reales de la prueba elegida (GET /educativo/pruebas/{id}/completa), lista
// de alumnos con búsqueda/filtro por sección/"seleccionar todos", y links
// con "Copiar todos" y confirmación visual al copiar.
export default function NuevaCampanaPage() {
  const { sesion } = useAuth();
  const router = useRouter();

  const [pruebas, setPruebas] = useState<Prueba[] | null>(null);
  const [errorPruebas, setErrorPruebas] = useState<string | null>(null);
  const [busquedaPrueba, setBusquedaPrueba] = useState("");
  const [filtroInformante, setFiltroInformante] = useState<string>("todos");
  // Detalle (dimensiones) por prueba, cacheado por id: así el panel de
  // resumen se deriva de la prueba elegida sin limpiar estado en un efecto.
  const [detalles, setDetalles] = useState<Map<number, PruebaDetalle>>(new Map());

  const [form, setForm] = useState({ prueba_id: "", nombre_grupo: "", fecha_fin: "" });

  // 🆕 Grupo desde la Estructura académica real (Nivel → Grado → Sección, ver
  // /academico) en vez de solo texto libre. `nombre_grupo` sigue siendo un
  // String en el backend (Evaluacion.nombre_grupo): acá se ARMA a partir de
  // la sección elegida, y el usuario puede editarlo (`nombreManual`). Cada
  // lista se carga en el onChange de su padre, no en un efecto.
  const [niveles, setNiveles] = useState<NivelEducativo[] | null>(null);
  const [grados, setGrados] = useState<Grado[]>([]);
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [grupo, setGrupo] = useState({ nivel_id: "", grado_id: "", seccion_id: "" });
  const [nombreManual, setNombreManual] = useState(false);
  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState<string | null>(null);
  const [campana, setCampana] = useState<Evaluacion | null>(null);

  const [personas, setPersonas] = useState<Persona[]>([]);
  const [errorPersonas, setErrorPersonas] = useState<string | null>(null);
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  const [busquedaAlumno, setBusquedaAlumno] = useState("");
  const [filtroSeccion, setFiltroSeccion] = useState("todas");
  const [matriculando, setMatriculando] = useState(false);
  const [errorMatricular, setErrorMatricular] = useState<string | null>(null);
  const [resultadoMatricula, setResultadoMatricula] = useState<MatriculaRosterResponse | null>(null);
  const [copiado, setCopiado] = useState<number | "todos" | null>(null);

  // Estado preventivo del consentimiento del apoderado (el único siempre
  // obligatorio, con o sin la política institucional de asentimiento) para
  // cada persona del padrón — así el psicólogo ve de antemano quién no tiene
  // consentimiento vigente, en vez de enterarse recién en el resultado de
  // "matricular-roster" (que ya existía, pero es post-hoc). Una llamada por
  // alumno (no hay endpoint batch todavía); aceptable porque esta pantalla
  // ya carga el padrón completo de una sola vez con el mismo costo.
  const [estadosConsentimiento, setEstadosConsentimiento] = useState<Map<number, boolean>>(new Map());
  const [cargandoConsentimientos, setCargandoConsentimientos] = useState(false);

  useEffect(() => {
    apiClient
      .get<Prueba[]>("/educativo/pruebas/")
      .then((datos) => setPruebas(datos.filter((p) => p.activa)))
      .catch((err) => setErrorPruebas(err.message || "No se pudo cargar el catálogo de pruebas."));
  }, []);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    apiClient
      .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
      .then((datos) => setNiveles(datos.filter((n) => n.activo).sort((a, b) => a.orden - b.orden)))
      .catch(() => setNiveles([])); // sin estructura → queda el nombre escrito a mano
  }, [sesion?.institucionId]);

  async function elegirNivel(nivelId: string) {
    setGrupo({ nivel_id: nivelId, grado_id: "", seccion_id: "" });
    setGrados([]);
    setSecciones([]);
    if (!nivelId) return;
    try {
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelId}`);
      setGrados(datos.filter((g) => g.activo).sort((a, b) => a.orden - b.orden));
    } catch {
      setGrados([]);
    }
  }

  async function elegirGrado(gradoId: string) {
    setGrupo((g) => ({ ...g, grado_id: gradoId, seccion_id: "" }));
    setSecciones([]);
    if (!gradoId) return;
    try {
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoId}`);
      setSecciones(
        datos.filter((s) => s.activo).sort((a, b) => b.anio_escolar - a.anio_escolar || a.nombre.localeCompare(b.nombre)),
      );
    } catch {
      setSecciones([]);
    }
  }

  const nivelElegido = (niveles ?? []).find((n) => String(n.id) === grupo.nivel_id) ?? null;
  const gradoElegido = grados.find((g) => String(g.id) === grupo.grado_id) ?? null;
  const seccionElegida = secciones.find((s) => String(s.id) === grupo.seccion_id) ?? null;
  const pruebaParaNombre = (pruebas ?? []).find((p) => String(p.id) === form.prueba_id) ?? null;
  // Ej. "3° A Secundaria — PHQ-9 2026" (o "3° Secundaria — …" si se eligió
  // el grado completo, sin sección).
  const nombreSugerido = gradoElegido
    ? [
        [gradoElegido.nombre, seccionElegida?.nombre, nivelElegido?.nombre].filter(Boolean).join(" "),
        [pruebaParaNombre?.nombre_corto || pruebaParaNombre?.nombre_tecnico, seccionElegida?.anio_escolar ?? new Date().getFullYear()]
          .filter(Boolean)
          .join(" "),
      ].join(" — ")
    : "";
  const sinEstructura = niveles !== null && niveles.length === 0;
  const nombreEfectivo = nombreManual || sinEstructura ? form.nombre_grupo : nombreSugerido;

  const pruebaIdElegida = form.prueba_id ? Number(form.prueba_id) : null;
  useEffect(() => {
    if (pruebaIdElegida === null || detalles.has(pruebaIdElegida)) return;
    apiClient
      .get<PruebaDetalle>(`/educativo/pruebas/${pruebaIdElegida}/completa`)
      .then((d) => setDetalles((prev) => new Map(prev).set(pruebaIdElegida, d)))
      .catch(() => {}); // informativo: sin detalle, el resumen muestra solo el nombre
  }, [pruebaIdElegida, detalles]);

  // "Copiado ✓" se apaga solo a los dos segundos.
  useEffect(() => {
    if (copiado === null) return;
    const t = setTimeout(() => setCopiado(null), 2000);
    return () => clearTimeout(t);
  }, [copiado]);

  async function crearCampana(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) {
      setErrorCrear("Tu sesión no tiene una institución asociada — esta pantalla es para admin/psicólogo de un colegio.");
      return;
    }
    if (!form.prueba_id) {
      setErrorCrear("Elige una prueba para la campaña.");
      return;
    }
    if (!nombreEfectivo.trim()) {
      setErrorCrear("Elige el grupo (grado y sección) o escribe un nombre.");
      return;
    }
    if (fechaCierreEsPasada(form.fecha_fin)) {
      setErrorCrear(MENSAJE_FECHA_CIERRE_PASADA);
      return;
    }
    setCreando(true);
    setErrorCrear(null);
    try {
      const payload: EvaluacionCreate = {
        prueba_id: Number(form.prueba_id),
        nombre_grupo: nombreEfectivo.trim(),
        institucion_id: sesion.institucionId,
        fecha_fin: form.fecha_fin ? new Date(form.fecha_fin).toISOString() : null,
      };
      const nueva = await apiClient.post<Evaluacion>("/educativo/campanas/", payload);
      setCampana(nueva);
      // Cargar el padrón recién ahora -- no hace falta antes de tener campaña.
      // 🆕 Paginación real: este selector necesita el padrón COMPLETO (el
      // usuario elige a quién matricular), no una página de 50 — por eso
      // usa getTodasLasPaginas en vez de get.
      const datosPersonas = await apiClient.getTodasLasPaginas<Persona>(`/admin/personas/${sesion.institucionId}`);
      setPersonas(datosPersonas);
      // Si la campaña se armó para una sección (o un grado completo), sus
      // alumnos llegan preseleccionados al paso 2 — se pueden desmarcar.
      if (gradoElegido) {
        const delGrupo = datosPersonas.filter((p) =>
          seccionElegida
            ? p.seccion_actual?.seccion_id === seccionElegida.id
            : p.seccion_actual?.grado_id === gradoElegido.id,
        );
        setSeleccionadas(new Set(delGrupo.map((p) => p.id)));
        if (seccionElegida) setFiltroSeccion(String(seccionElegida.id));
      }
      cargarEstadosConsentimiento(datosPersonas);
    } catch (err: any) {
      setErrorCrear(err.message || "No se pudo crear la campaña.");
    } finally {
      setCreando(false);
    }
  }

  async function cargarEstadosConsentimiento(lista: Persona[]) {
    setCargandoConsentimientos(true);
    try {
      const resultados = await Promise.all(
        lista.map((p) =>
          apiClient
            .get<ConsentimientosCombinados>(`/admin/personas/${p.id}/consentimientos`)
            .then((r): [number, boolean] => [p.id, r.apoderado.tiene_consentimiento_vigente])
            .catch((): [number, boolean | null] => [p.id, null]),
        ),
      );
      setEstadosConsentimiento(
        new Map(resultados.filter((r): r is [number, boolean] => r[1] !== null)),
      );
    } finally {
      setCargandoConsentimientos(false);
    }
  }

  function alternarSeleccion(id: number) {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (copia.has(id)) copia.delete(id);
      else copia.add(id);
      return copia;
    });
  }

  async function matricular() {
    if (!campana || seleccionadas.size === 0) return;
    setMatriculando(true);
    setErrorMatricular(null);
    try {
      const resultado = await apiClient.post<MatriculaRosterResponse>(
        `/educativo/campanas/${campana.id}/matricular-roster`,
        Array.from(seleccionadas),
      );
      setResultadoMatricula(resultado);
    } catch (err: any) {
      setErrorMatricular(err.message || "No se pudo matricular a los alumnos elegidos.");
    } finally {
      setMatriculando(false);
    }
  }

  function urlExamen(token: string): string {
    return typeof window !== "undefined" ? `${window.location.origin}/examen/${token}` : "";
  }

  async function copiar(texto: string, clave: number | "todos") {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(clave);
    } catch {
      setErrorMatricular("El navegador no permitió copiar al portapapeles.");
    }
  }

  // 🔧 El backend ya rechaza esto con 403 (`requerir_staff_clinico` en
  // POST /educativo/campanas/ y /matricular-roster — "colegio" nunca está
  // en esa lista), pero esta página no tenía su propio candado: desde que
  // el layout de (educativo) deja entrar a "colegio" (antes lo expulsaba
  // por error, ver app/(educativo)/layout.tsx), ese rol podía llegar hasta
  // acá, ver el padrón completo con los badges de consentimiento, y recién
  // enterarse de que no puede nada al enviar el formulario. Mismo criterio
  // que el resto de la app: gatear en la UI lo que el backend ya gatea.
  const puedeCrearCampana = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  if (!puedeCrearCampana) {
    return (
      <div className="max-w-3xl mx-auto">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  const pasoActual = !campana ? 0 : !resultadoMatricula ? 1 : 2;

  // --- Paso 1: catálogo filtrado ---
  const terminoPrueba = busquedaPrueba.trim().toLowerCase();
  const pruebasVisibles = (pruebas ?? []).filter((p) => {
    if (filtroInformante !== "todos" && p.informante_tipo !== filtroInformante) return false;
    if (!terminoPrueba) return true;
    return [p.nombre_corto, p.nombre_tecnico, p.nombre_publico].some((v) => v?.toLowerCase().includes(terminoPrueba));
  });
  const informantesPresentes = Array.from(new Set((pruebas ?? []).map((p) => p.informante_tipo))).filter((i) => INFORMANTES[i]);
  const pruebaElegida = (pruebas ?? []).find((p) => p.id === pruebaIdElegida) ?? null;
  const detalleElegida = pruebaIdElegida !== null ? detalles.get(pruebaIdElegida) : undefined;

  // --- Paso 2: padrón filtrado ---
  const seccionesPadron = Array.from(
    new Map(
      personas
        .filter((p) => p.seccion_actual)
        .map((p) => [
          String(p.seccion_actual!.seccion_id),
          [p.seccion_actual!.grado, p.seccion_actual!.seccion].filter(Boolean).join(" "),
        ]),
    ),
  );
  const terminoAlumno = busquedaAlumno.trim().toLowerCase();
  const personasVisibles = personas.filter((p) => {
    if (filtroSeccion === "sin-seccion" && p.seccion_actual) return false;
    if (filtroSeccion !== "todas" && filtroSeccion !== "sin-seccion" && String(p.seccion_actual?.seccion_id) !== filtroSeccion)
      return false;
    if (!terminoAlumno) return true;
    return [`${p.nombres} ${p.apellidos}`, p.codigo_institucional, p.documento_identidad].some((v) =>
      v?.toLowerCase().includes(terminoAlumno),
    );
  });
  const todasVisiblesMarcadas = personasVisibles.length > 0 && personasVisibles.every((p) => seleccionadas.has(p.id));

  function alternarTodasVisibles() {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (todasVisiblesMarcadas) personasVisibles.forEach((p) => copia.delete(p.id));
      else personasVisibles.forEach((p) => copia.add(p.id));
      return copia;
    });
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <Migas items={[{ label: "Campañas", href: "/campanas" }, { label: "Nueva campaña" }]} />
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-teal-900 dark:text-ink-dark">Nueva campaña</h1>
        <p className="mt-1 text-sm text-ink/55 dark:text-ink-dark/55">
          Elige una prueba, matricula a los alumnos y comparte con cada uno su link personal al examen.
        </p>
      </div>

      <IndicadorPasos actual={pasoActual} />

      {/* ===== Paso 1: configurar la campaña ===== */}
      {!campana && (
        <form onSubmit={crearCampana} className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2 space-y-6">
            <section className={`${CLASE_TARJETA} p-5 sm:p-6`}>
              <EncabezadoSeccion numero={1} titulo="Elige la prueba" subtitulo="El instrumento que responderán los alumnos." />

              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="relative flex-1">
                  <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                  <Input
                    type="search"
                    value={busquedaPrueba}
                    onChange={(e) => setBusquedaPrueba(e.target.value)}
                    placeholder="Buscar prueba (PHQ-9, ansiedad, vocacional...)"
                    aria-label="Buscar prueba"
                    className="w-full pl-9"
                  />
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                  {[["todos", "Todas"], ...informantesPresentes.map((i) => [i, INFORMANTES[i].label])].map(([valor, label]) => (
                    <button
                      key={valor}
                      type="button"
                      onClick={() => setFiltroInformante(valor)}
                      aria-pressed={filtroInformante === valor}
                      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                        filtroInformante === valor
                          ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                          : "bg-mist text-ink/65 hover:bg-border dark:bg-surface-raised-dark dark:text-ink-dark/65 dark:hover:bg-border-dark"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <TextoError className="mt-4">{errorPruebas}</TextoError>

              <div
                role="radiogroup"
                aria-label="Prueba"
                className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[26rem] overflow-y-auto pr-1 -mr-1"
              >
                {pruebas === null && !errorPruebas
                  ? Array.from({ length: 6 }).map((_, i) => (
                      <div key={i} className="h-[5.5rem] animate-pulse rounded-xl bg-border/50 dark:bg-border-dark" />
                    ))
                  : pruebasVisibles.map((p) => {
                      const elegida = p.id === pruebaIdElegida;
                      const informante = INFORMANTES[p.informante_tipo];
                      return (
                        <button
                          key={p.id}
                          type="button"
                          role="radio"
                          aria-checked={elegida}
                          onClick={() => setForm({ ...form, prueba_id: String(p.id) })}
                          className={`relative flex items-start gap-3 rounded-xl border p-3.5 text-left transition-all ${
                            elegida
                              ? "border-teal-600 bg-teal-600/[0.06] ring-2 ring-teal-600/25 dark:border-teal-accent-dark dark:bg-teal-accent-dark/10 dark:ring-teal-accent-dark/25"
                              : "border-border hover:border-teal-400 hover:bg-mist/50 dark:border-border-dark dark:hover:border-teal-accent-dark/60 dark:hover:bg-surface-raised-dark"
                          }`}
                        >
                          <span
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
                              elegida
                                ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                                : "bg-mist text-teal-700 dark:bg-surface-raised-dark dark:text-teal-accent-dark"
                            }`}
                          >
                            <ClipboardList size={18} strokeWidth={2} aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block pr-6 text-sm font-semibold text-ink dark:text-ink-dark">
                              {p.nombre_corto || p.nombre_tecnico}
                            </span>
                            <span className="mt-0.5 block text-xs leading-snug text-ink/55 dark:text-ink-dark/55 line-clamp-2">
                              {p.nombre_publico}
                            </span>
                            {informante && (
                              <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-mist px-2 py-0.5 text-[11px] font-medium text-ink/60 dark:bg-surface-raised-dark dark:text-ink-dark/60">
                                <informante.icono size={11} aria-hidden="true" />
                                {informante.label}
                              </span>
                            )}
                          </span>
                          {elegida && (
                            <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark">
                              <Check size={13} strokeWidth={3} aria-hidden="true" />
                            </span>
                          )}
                        </button>
                      );
                    })}
                {pruebas !== null && pruebasVisibles.length === 0 && (
                  <p className="sm:col-span-2 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">
                    Ninguna prueba coincide con la búsqueda.
                  </p>
                )}
              </div>
            </section>

            <section className={`${CLASE_TARJETA} p-5 sm:p-6`}>
              <EncabezadoSeccion
                numero={2}
                titulo="Grupo a evaluar"
                subtitulo="Elige el grupo desde la estructura académica de tu colegio."
              />

              {sinEstructura && (
                <div className="mt-5 flex items-start gap-3 rounded-xl border border-dashed border-border dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark/50 px-4 py-3 text-xs text-ink/65 dark:text-ink-dark/65">
                  <Info size={15} className="mt-px shrink-0 text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                  <p>
                    Tu colegio todavía no tiene niveles, grados ni secciones registrados. Créalos en{" "}
                    <Link href="/academico" className="font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
                      Estructura académica
                    </Link>{" "}
                    para elegir el grupo desde una lista; mientras tanto, escribe el nombre a mano.
                  </p>
                </div>
              )}

              <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                {!sinEstructura && (
                  <div className="sm:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <CampoEditable etiqueta="Nivel">
                      <Select value={grupo.nivel_id} onChange={(e) => elegirNivel(e.target.value)} disabled={niveles === null}>
                        <option value="">{niveles === null ? "Cargando..." : "Elige un nivel"}</option>
                        {(niveles ?? []).map((n) => (
                          <option key={n.id} value={n.id}>
                            {n.nombre}
                          </option>
                        ))}
                      </Select>
                    </CampoEditable>
                    <CampoEditable etiqueta="Grado">
                      <Select value={grupo.grado_id} onChange={(e) => elegirGrado(e.target.value)} disabled={!grupo.nivel_id}>
                        <option value="">{grupo.nivel_id && grados.length === 0 ? "Sin grados" : "Elige un grado"}</option>
                        {grados.map((g) => (
                          <option key={g.id} value={g.id}>
                            {g.nombre}
                          </option>
                        ))}
                      </Select>
                    </CampoEditable>
                    <CampoEditable etiqueta="Sección">
                      <Select
                        value={grupo.seccion_id}
                        onChange={(e) => setGrupo({ ...grupo, seccion_id: e.target.value })}
                        disabled={!grupo.grado_id}
                      >
                        <option value="">Todo el grado</option>
                        {secciones.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.nombre}
                            {s.turno ? ` (${s.turno})` : ""} · {s.anio_escolar}
                          </option>
                        ))}
                      </Select>
                    </CampoEditable>
                  </div>
                )}

                <CampoEditable etiqueta="Nombre de la campaña">
                  <Input
                    required
                    value={nombreEfectivo}
                    readOnly={!nombreManual && !sinEstructura}
                    onChange={(e) => setForm({ ...form, nombre_grupo: e.target.value })}
                    placeholder={sinEstructura ? 'Ej. "3° A - Evaluación anual 2026"' : "Se arma al elegir el grupo"}
                    className={!nombreManual && !sinEstructura ? "bg-mist/60 dark:bg-surface-raised-dark text-ink/80" : ""}
                  />
                  {!sinEstructura && (
                    <button
                      type="button"
                      onClick={() => {
                        // Al pasar a manual, arranca desde el nombre sugerido
                        // en vez de un campo vacío.
                        if (!nombreManual) setForm({ ...form, nombre_grupo: nombreSugerido });
                        setNombreManual((v) => !v);
                      }}
                      className="self-start text-xs font-medium text-teal-700 dark:text-teal-accent-dark hover:underline"
                    >
                      {nombreManual ? "Usar el nombre automático" : "Editar el nombre"}
                    </button>
                  )}
                </CampoEditable>
                <CampoEditable etiqueta="Fecha de cierre (opcional)">
                  <Input
                    type="datetime-local"
                    min={ahoraParaInputLocal()}
                    value={form.fecha_fin}
                    onChange={(e) => setForm({ ...form, fecha_fin: e.target.value })}
                    aria-invalid={fechaCierreEsPasada(form.fecha_fin)}
                    className={fechaCierreEsPasada(form.fecha_fin) ? "border-red-400 focus:ring-red-300" : ""}
                  />
                  {fechaCierreEsPasada(form.fecha_fin) ? (
                    <span className="text-xs font-medium text-red-700">{MENSAJE_FECHA_CIERRE_PASADA}</span>
                  ) : (
                    <span className="text-xs text-ink/45 dark:text-ink-dark/45">Después de esta fecha los links dejan de funcionar.</span>
                  )}
                </CampoEditable>
              </div>
            </section>
          </div>

          {/* Resumen lateral */}
          <aside className="lg:sticky lg:top-0 space-y-4">
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <div className="bg-gradient-to-br from-teal-900 to-teal-600 dark:from-surface-raised-dark dark:to-surface-dark px-5 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-white/60 dark:text-teal-accent-dark">Resumen</p>
                <p className="mt-0.5 font-display text-lg font-semibold leading-snug text-white dark:text-ink-dark break-words">
                  {nombreEfectivo || "Campaña sin nombre"}
                </p>
              </div>
              <dl className="divide-y divide-border dark:divide-border-dark text-sm">
                <FilaResumen icono={ClipboardList} etiqueta="Prueba">
                  {pruebaElegida ? (
                    <>
                      <span className="font-semibold text-ink dark:text-ink-dark">{pruebaElegida.nombre_corto || pruebaElegida.nombre_tecnico}</span>
                      <span className="block text-xs text-ink/50 dark:text-ink-dark/50">{pruebaElegida.nombre_publico}</span>
                    </>
                  ) : (
                    <span className="italic text-ink/40 dark:text-ink-dark/40">Sin elegir</span>
                  )}
                </FilaResumen>
                {pruebaElegida && (
                  <FilaResumen icono={Tag} etiqueta="Qué mide">
                    {detalleElegida ? (
                      detalleElegida.dimensiones.length > 0 ? (
                        <span className="flex flex-wrap gap-1 pt-0.5">
                          {detalleElegida.dimensiones.slice(0, 8).map((d) => (
                            <span
                              key={d.id}
                              className="rounded-md bg-mist px-1.5 py-0.5 text-[11px] text-ink/70 dark:bg-surface-raised-dark dark:text-ink-dark/70"
                            >
                              {d.nombre}
                            </span>
                          ))}
                          {detalleElegida.dimensiones.length > 8 && (
                            <span className="text-[11px] text-ink/45 dark:text-ink-dark/45">+{detalleElegida.dimensiones.length - 8} más</span>
                          )}
                        </span>
                      ) : (
                        <span className="text-ink/50 dark:text-ink-dark/50">—</span>
                      )
                    ) : (
                      <span className="block h-4 w-32 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
                    )}
                  </FilaResumen>
                )}
                <FilaResumen icono={CalendarClock} etiqueta="Cierre">
                  {form.fecha_fin ? (
                    <span className="text-ink dark:text-ink-dark">
                      {new Date(form.fecha_fin).toLocaleString("es-PE", { dateStyle: "medium", timeStyle: "short" })}
                    </span>
                  ) : (
                    <span className="italic text-ink/40 dark:text-ink-dark/40">Sin fecha límite</span>
                  )}
                </FilaResumen>
              </dl>
              <div className="p-5 pt-4 space-y-3 border-t border-border dark:border-border-dark">
                <TextoError>{errorCrear}</TextoError>
                <Boton
                  type="submit"
                  disabled={creando || !form.prueba_id || !nombreEfectivo.trim() || fechaCierreEsPasada(form.fecha_fin)}
                  className="w-full inline-flex items-center justify-center gap-2 !py-2.5"
                >
                  {creando ? "Creando..." : "Crear campaña"}
                  {!creando && <ArrowRight size={16} aria-hidden="true" />}
                </Boton>
                {(!form.prueba_id || !nombreEfectivo.trim()) && (
                  <p className="text-center text-xs text-ink/45 dark:text-ink-dark/45">
                    {!form.prueba_id
                      ? "Elige una prueba para continuar."
                      : sinEstructura || nombreManual
                        ? "Ponle un nombre al grupo."
                        : "Elige el nivel y el grado del grupo."}
                  </p>
                )}
              </div>
            </section>

            <div className="rounded-2xl border border-dashed border-border dark:border-border-dark p-4 text-xs text-ink/60 dark:text-ink-dark/60">
              <p className="flex items-center gap-1.5 font-semibold text-ink/75 dark:text-ink-dark/75">
                <Info size={14} aria-hidden="true" />
                ¿Cómo funciona?
              </p>
              <p className="mt-1.5 leading-relaxed">
                Cada alumno recibe un link único y responde sin iniciar sesión. Si un resultado indica riesgo, el informe queda
                retenido hasta que lo revises.
              </p>
            </div>
          </aside>
        </form>
      )}

      {/* ===== Paso 2: matricular alumnos del padrón ===== */}
      {campana && !resultadoMatricula && (
        <section className={`${CLASE_TARJETA} overflow-hidden`}>
          <div className="flex items-start gap-3 bg-teal-600/[0.06] dark:bg-teal-accent-dark/10 px-5 py-4 border-b border-border dark:border-border-dark">
            <CircleCheck size={20} className="mt-0.5 shrink-0 text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-ink dark:text-ink-dark">
                Campaña «{campana.nombre_grupo}» creada
              </p>
              <p className="text-xs text-ink/55 dark:text-ink-dark/55">Ahora elige a qué alumnos del padrón quieres evaluar.</p>
            </div>
          </div>

          <div className="p-5 space-y-4">
            <TextoError>{errorPersonas}</TextoError>

            {personas.length === 0 ? (
              <div className="py-10 text-center">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-ink/40 dark:text-ink-dark/40">
                  <Users size={22} aria-hidden="true" />
                </span>
                <p className="mt-3 text-sm font-medium text-ink dark:text-ink-dark">Tu padrón todavía está vacío</p>
                <p className="mt-1 text-xs text-ink/50 dark:text-ink-dark/50">
                  Registra o importa alumnos primero; podrás matricularlos desde el dashboard de la campaña.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <Link
                    href="/estudiantes/importar"
                    className="rounded-card border border-border dark:border-border-dark px-4 py-2 text-sm font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark"
                  >
                    Importar Excel
                  </Link>
                  <Link
                    href="/estudiantes/nuevo"
                    className="rounded-card bg-accion dark:bg-teal-accent-dark px-4 py-2 text-sm font-medium text-white dark:text-mist-dark hover:bg-accion-hover"
                  >
                    + Registrar alumno
                  </Link>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="relative flex-1">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                    <Input
                      type="search"
                      value={busquedaAlumno}
                      onChange={(e) => setBusquedaAlumno(e.target.value)}
                      placeholder="Buscar por nombre, código o documento"
                      aria-label="Buscar alumno"
                      className="w-full pl-9"
                    />
                  </div>
                  <Select value={filtroSeccion} onChange={(e) => setFiltroSeccion(e.target.value)} aria-label="Filtrar por sección" className="sm:w-56">
                    <option value="todas">Todas las secciones</option>
                    {seccionesPadron.map(([id, etiqueta]) => (
                      <option key={id} value={id}>
                        {etiqueta || `Sección ${id}`}
                      </option>
                    ))}
                    <option value="sin-seccion">Sin sección</option>
                  </Select>
                </div>

                {cargandoConsentimientos && (
                  <p className="flex items-center gap-2 text-xs text-ink/50 dark:text-ink-dark/50">
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" aria-hidden="true" />
                    Verificando consentimiento vigente de cada alumno...
                  </p>
                )}

                <div className="rounded-xl border border-border dark:border-border-dark overflow-hidden">
                  <label className="flex items-center gap-3 bg-mist/70 dark:bg-surface-raised-dark px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink/55 dark:text-ink-dark/55 cursor-pointer">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-teal-600"
                      checked={todasVisiblesMarcadas}
                      onChange={alternarTodasVisibles}
                      disabled={personasVisibles.length === 0}
                    />
                    Seleccionar todos {personasVisibles.length !== personas.length && "los visibles"} ({personasVisibles.length})
                  </label>
                  <div className="max-h-[24rem] overflow-y-auto divide-y divide-border dark:divide-border-dark">
                    {personasVisibles.length === 0 ? (
                      <p className="px-4 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">Ningún alumno coincide con el filtro.</p>
                    ) : (
                      personasVisibles.map((p) => {
                        const sinConsentimiento = estadosConsentimiento.get(p.id) === false;
                        const marcada = seleccionadas.has(p.id);
                        const seccion = p.seccion_actual
                          ? [p.seccion_actual.grado, p.seccion_actual.seccion].filter(Boolean).join(" ")
                          : null;
                        return (
                          <label
                            key={p.id}
                            className={`flex items-center gap-3 px-4 py-3 text-sm cursor-pointer transition-colors ${
                              marcada ? "bg-teal-600/[0.05] dark:bg-teal-accent-dark/[0.07]" : "hover:bg-mist/50 dark:hover:bg-surface-raised-dark/60"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="h-4 w-4 shrink-0 accent-teal-600"
                              checked={marcada}
                              onChange={() => alternarSeleccion(p.id)}
                            />
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-[11px] font-bold text-teal-700 dark:text-teal-accent-dark">
                              {`${p.nombres[0] ?? ""}${p.apellidos[0] ?? ""}`.toUpperCase()}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate font-medium text-ink dark:text-ink-dark">
                                {p.nombres} {p.apellidos}
                              </span>
                              <span className="block truncate text-xs text-ink/50 dark:text-ink-dark/50">
                                {[seccion, p.codigo_institucional && `Cód. ${p.codigo_institucional}`].filter(Boolean).join(" · ") ||
                                  "Sin sección"}
                              </span>
                            </span>
                            {sinConsentimiento && (
                              <span className="shrink-0 text-[11px] rounded-full px-2 py-0.5 font-medium bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-300">
                                <span className="hidden sm:inline">Sin consentimiento del apoderado</span>
                                <span className="sm:hidden">Sin consent.</span>
                              </span>
                            )}
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>

                {Array.from(seleccionadas).some((id) => estadosConsentimiento.get(id) === false) && (
                  <p className="flex items-start gap-2 rounded-xl bg-red-50 dark:bg-red-500/10 px-4 py-3 text-xs text-red-700 dark:text-red-300">
                    <CircleAlert size={15} className="mt-px shrink-0" aria-hidden="true" />
                    Hay alumnos seleccionados sin consentimiento del apoderado vigente — puedes intentar matricularlos igual, pero
                    el colegio quedará fuera de la lista de links generados hasta registrarlo en su ficha.
                  </p>
                )}
              </>
            )}

            <TextoError>{errorMatricular}</TextoError>
          </div>

          {/* Barra de acción */}
          <div className="flex flex-col-reverse gap-3 px-5 py-4 bg-mist/50 dark:bg-surface-raised-dark/50 border-t border-border dark:border-border-dark sm:flex-row sm:items-center sm:justify-between">
            <Link
              href={`/campanas/${campana.id}/dashboard`}
              className="text-center text-sm font-medium text-ink/60 dark:text-ink-dark/60 hover:text-teal-700 dark:hover:text-teal-accent-dark hover:underline"
            >
              Omitir por ahora, ir al dashboard
            </Link>
            {personas.length > 0 && (
              <div className="flex items-center justify-between gap-4 sm:justify-end">
                <span className="text-sm text-ink/60 dark:text-ink-dark/60">
                  <span className="font-display text-lg font-semibold text-teal-900 dark:text-ink-dark">{seleccionadas.size}</span>{" "}
                  seleccionado{seleccionadas.size === 1 ? "" : "s"}
                </span>
                <Boton
                  onClick={matricular}
                  disabled={matriculando || seleccionadas.size === 0}
                  className="inline-flex items-center gap-2 !py-2.5"
                >
                  {matriculando ? "Matriculando..." : "Matricular y generar links"}
                  {!matriculando && <ArrowRight size={16} aria-hidden="true" />}
                </Boton>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ===== Paso 3: resultado + links mágicos ===== */}
      {campana && resultadoMatricula && (
        <div className="space-y-6">
          <section className={`${CLASE_TARJETA} overflow-hidden`}>
            <div className="bg-gradient-to-br from-teal-900 to-teal-600 dark:from-surface-raised-dark dark:to-surface-dark px-6 py-7 text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-white/15 dark:bg-teal-accent-dark/15">
                <CircleCheck size={28} className="text-white dark:text-teal-accent-dark" aria-hidden="true" />
              </span>
              <h2 className="mt-3 font-display text-xl sm:text-2xl font-semibold text-white dark:text-ink-dark">¡Campaña lista!</h2>
              <p className="mt-1 text-sm text-white/75 dark:text-ink-dark/60">
                Comparte con cada alumno su link personal. «{campana.nombre_grupo}»
              </p>
            </div>
            <div className="grid grid-cols-2 divide-x divide-border dark:divide-border-dark">
              <div className="px-5 py-4 text-center">
                <p className="font-display text-2xl font-semibold text-teal-900 dark:text-ink-dark">{resultadoMatricula.generados.length}</p>
                <p className="text-xs text-ink/55 dark:text-ink-dark/55">links generados</p>
              </div>
              <div className="px-5 py-4 text-center">
                <p
                  className={`font-display text-2xl font-semibold ${
                    resultadoMatricula.rechazados.length > 0 ? "text-red-700 dark:text-red-300" : "text-teal-900 dark:text-ink-dark"
                  }`}
                >
                  {resultadoMatricula.rechazados.length}
                </p>
                <p className="text-xs text-ink/55 dark:text-ink-dark/55">rechazados</p>
              </div>
            </div>
          </section>

          {resultadoMatricula.rechazados.length > 0 && (
            <section className="rounded-2xl border border-red-200 dark:border-red-500/30 bg-red-50/60 dark:bg-red-500/10 p-5">
              <p className="flex items-center gap-2 text-sm font-semibold text-red-700 dark:text-red-300">
                <CircleAlert size={16} aria-hidden="true" />
                No se generó link para {resultadoMatricula.rechazados.length} alumno
                {resultadoMatricula.rechazados.length === 1 ? "" : "s"}
              </p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {resultadoMatricula.rechazados.map((r) => (
                  <li key={r.persona_id} className="text-ink/75 dark:text-ink-dark/75">
                    <span className="font-medium text-ink dark:text-ink-dark">{r.nombre}:</span> {r.motivo}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {resultadoMatricula.generados.length > 0 && (
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <div className="flex flex-col gap-3 px-5 py-4 border-b border-border dark:border-border-dark sm:flex-row sm:items-center sm:justify-between">
                <h3 className="flex items-center gap-2 font-display text-base font-semibold text-teal-900 dark:text-ink-dark">
                  <Link2 size={17} aria-hidden="true" />
                  Links de examen
                </h3>
                <Boton
                  variante="secundario"
                  onClick={() =>
                    copiar(
                      resultadoMatricula.generados.map((ins) => `${ins.nombre_completo ?? "Alumno"}: ${urlExamen(ins.token)}`).join("\n"),
                      "todos",
                    )
                  }
                  className="inline-flex items-center justify-center gap-1.5 !py-1.5"
                >
                  {copiado === "todos" ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
                  {copiado === "todos" ? "Copiados" : "Copiar todos los links"}
                </Boton>
              </div>
              <ul className="max-h-[26rem] overflow-y-auto divide-y divide-border dark:divide-border-dark">
                {resultadoMatricula.generados.map((ins) => {
                  const url = urlExamen(ins.token);
                  return (
                    <li key={ins.id} className="flex items-center gap-3 px-5 py-3">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-[11px] font-bold text-teal-700 dark:text-teal-accent-dark">
                        {(ins.nombre_completo?.[0] || "?").toUpperCase()}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">{ins.nombre_completo}</p>
                        <p className="truncate font-mono text-[11px] text-ink/40 dark:text-ink-dark/40">{url}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => copiar(url, ins.id)}
                        className={`shrink-0 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                          copiado === ins.id
                            ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                            : "bg-mist text-teal-700 hover:bg-teal-600/10 dark:bg-surface-raised-dark dark:text-teal-accent-dark"
                        }`}
                      >
                        {copiado === ins.id ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
                        {copiado === ins.id ? "Copiado" : "Copiar"}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          <TextoError>{errorMatricular}</TextoError>

          <div className="flex justify-center">
            <Boton onClick={() => router.push(`/campanas/${campana.id}/dashboard`)} className="inline-flex items-center gap-2 !px-6 !py-2.5">
              Ir al dashboard de la campaña
              <ArrowRight size={16} aria-hidden="true" />
            </Boton>
          </div>
        </div>
      )}
    </div>
  );
}

function IndicadorPasos({ actual }: { actual: number }) {
  return (
    <ol className="flex items-center gap-2 sm:gap-3">
      {PASOS.map((paso, i) => {
        const hecho = i < actual;
        const activo = i === actual;
        return (
          <li key={paso} className={`flex items-center gap-2 sm:gap-3 ${i < PASOS.length - 1 ? "flex-1" : ""}`}>
            <span className="flex items-center gap-2">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
                  hecho
                    ? "bg-accion text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                    : activo
                      ? "bg-teal-900 text-white ring-4 ring-teal-600/15 dark:bg-teal-accent-dark dark:text-mist-dark dark:ring-teal-accent-dark/20"
                      : "bg-surface border border-border text-ink/40 dark:bg-surface-dark dark:border-border-dark dark:text-ink-dark/40"
                }`}
              >
                {hecho ? <Check size={15} strokeWidth={3} aria-hidden="true" /> : i + 1}
              </span>
              <span
                className={`text-sm font-medium whitespace-nowrap ${
                  activo ? "text-ink dark:text-ink-dark" : "text-ink/45 dark:text-ink-dark/45"
                } ${activo ? "" : "hidden md:inline"}`}
              >
                {paso}
              </span>
            </span>
            {i < PASOS.length - 1 && (
              <span className={`h-0.5 flex-1 rounded-full ${hecho ? "bg-teal-600 dark:bg-teal-accent-dark" : "bg-border dark:bg-border-dark"}`} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function EncabezadoSeccion({ numero, titulo, subtitulo }: { numero: number; titulo: string; subtitulo: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-xs font-bold text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
        {numero}
      </span>
      <div>
        <h2 className="font-display text-base font-semibold text-teal-900 dark:text-ink-dark">{titulo}</h2>
        <p className="text-xs text-ink/50 dark:text-ink-dark/50">{subtitulo}</p>
      </div>
    </div>
  );
}

function FilaResumen({ icono: Icono, etiqueta, children }: { icono: LucideIcon; etiqueta: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 px-5 py-3.5">
      <Icono size={16} className="mt-0.5 shrink-0 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <dt className="text-[11px] font-semibold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">{etiqueta}</dt>
        <dd className="mt-0.5">{children}</dd>
      </div>
    </div>
  );
}
