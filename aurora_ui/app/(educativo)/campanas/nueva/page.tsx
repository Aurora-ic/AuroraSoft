"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Check,
  ClipboardList,
  Flag,
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
  Eye,
  Ban,
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
import { EncabezadoPagina, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { siglaPrueba } from "@/lib/pruebas";
import { useIdsPadron, usePadronPaginado, useResumenPadron, useValorDiferido } from "@/lib/padron";
import { ahoraParaInputLocal, fechaCierreEsPasada, MENSAJE_FECHA_CIERRE_PASADA } from "@/lib/campanas";
import type {
  Prueba,
  PruebaDetalle,
  Evaluacion,
  EvaluacionCreate,
  MatriculaRosterResponse,
  ElegibilidadPrueba,
  NoElegible,
  SeccionResumenPadron,
} from "@/types/api";

// Quién responde cada prueba — el psicólogo elige distinto si el
// instrumento lo contesta el alumno, su apoderado o un docente.
const INFORMANTES: Record<string, { label: string; icono: LucideIcon }> = {
  estudiante: { label: "Autoinforme", icono: UserRound },
  padre_madre: { label: "Padres", icono: UsersRound },
  docente: { label: "Docente", icono: School },
};

const PASOS = ["Elegir prueba", "Elegir estudiantes", "Compartir links"];
const TAMANO_LISTA = 50;

// 🆕 (sesión 2026-11-01) Bloques con fondo tenue azul (Evaluación), mismo
// sistema que ACENTOS.azul.fondoSuave/cabecera/chipSolido (lib/acentos.ts).
const CLASE_TARJETA = "rounded-2xl border border-acento-azul/15 dark:border-acento-azul-dark/20 bg-acento-azul/[0.035] dark:bg-acento-azul-dark/[0.05] shadow-sm";

function etiquetaSalon(s: SeccionResumenPadron): string {
  return [s.grado, s.seccion, s.nivel_educativo].filter(Boolean).join(" ") || `Sección ${s.seccion_id}`;
}

function fechaCorta(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("es-PE") : "";
}

// 🆕 Rediseño (sesión 2026-11-01, a pedido del usuario: "campaña y salón a la
// vez" confundía y la selección de alumnos era post-hoc). Ahora todo se arma
// en UNA pantalla y la campaña se crea recién al final, junto con la
// matrícula — antes se creaba en el paso 1 y, si alguien abandonaba en el
// paso 2, quedaba una campaña "activa" sin alumnos:
//   1. la prueba;
//   2. los SALONES (lo principal): elegir un salón marca a todos sus
//      alumnos que pueden rendir la prueba (/resumen-padron?incluir_ids);
//   3. ajuste fino alumno por alumno (opcional), con búsqueda;
//   4. nombre (sale solo de los salones + la prueba) y cierre. 🆕 (sesión
//      2026-11-07, M6) Ya no hay "los alumnos ven su resultado": el enlace
//      del examen, al terminar, solo dice "Ya terminaste".
// Quien NO puede rendir la prueba ahora (sin consentimiento, la rindió hace
// menos de lo que pide la prueba, la tiene pendiente en otra campaña, límite
// mensual) aparece bloqueado con el motivo y la fecha en que vuelve a estar
// disponible — GET /educativo/pruebas/{id}/elegibilidad, la misma regla que
// el servidor vuelve a aplicar al matricular.
// Mismos endpoints de siempre para crear y matricular (POST /campanas/ +
// /matricular-roster). Las etiquetas "Crear campaña y generar links", la
// casilla "Seleccionar todos" y el paso de links son lo que miran los e2e.

export default function NuevaCampanaPage() {
  const { sesion } = useAuth();
  const router = useRouter();
  const institucionId = sesion?.institucionId;

  // --- 1. Prueba ---
  const [pruebas, setPruebas] = useState<Prueba[] | null>(null);
  const [errorPruebas, setErrorPruebas] = useState<string | null>(null);
  const [busquedaPrueba, setBusquedaPrueba] = useState("");
  const [filtroInformante, setFiltroInformante] = useState<string>("todos");
  const [detalles, setDetalles] = useState<Map<number, PruebaDetalle>>(new Map());
  const [form, setForm] = useState({ prueba_id: "", nombre_grupo: "", fecha_fin: "" });
  const [nombreManual, setNombreManual] = useState(false);

  // --- 2 y 3. Salones y estudiantes ---
  const [salones, setSalones] = useState<Set<number>>(new Set());
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  const [busquedaAlumno, setBusquedaAlumno] = useState("");
  const [filtroSeccion, setFiltroSeccion] = useState("todas");
  const [verLista, setVerLista] = useState(false);

  // --- Crear + matricular ---
  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState<string | null>(null);
  const [campana, setCampana] = useState<Evaluacion | null>(null);
  const [resultadoMatricula, setResultadoMatricula] = useState<MatriculaRosterResponse | null>(null);
  const [copiado, setCopiado] = useState<number | "todos" | null>(null);

  useEffect(() => {
    apiClient
      .get<Prueba[]>("/educativo/pruebas/")
      .then((datos) => setPruebas(datos.filter((p) => p.activa)))
      .catch((err) => setErrorPruebas(err.message || "No se pudo cargar el catálogo de pruebas."));
  }, []);

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

  // Salones con sus ids (un entero por alumno) y quién no puede rendir la prueba.
  const { resumen } = useResumenPadron({ institucionId, incluirIds: true, habilitado: !!institucionId });
  const elegibilidad = useQuery({
    queryKey: ["elegibilidad", pruebaIdElegida, institucionId],
    queryFn: () => apiClient.get<ElegibilidadPrueba>(`/educativo/pruebas/${pruebaIdElegida}/elegibilidad`),
    enabled: pruebaIdElegida !== null && !!institucionId,
  });
  const noElegibles = useMemo(
    () => new Map<number, NoElegible>((elegibilidad.data?.no_elegibles ?? []).map((n) => [n.persona_id, n])),
    [elegibilidad.data],
  );
  // Sin prueba elegida todavía, al menos se marca a quien no tiene consentimiento.
  const consentimientos = useIdsPadron({ institucionId, filtros: { consentimiento_apoderado: "sin" }, habilitado: !!institucionId });
  const sinConsentimiento = useMemo(() => new Set(consentimientos.ids), [consentimientos.ids]);
  function motivoBloqueo(id: number): NoElegible | null {
    if (pruebaIdElegida !== null) return noElegibles.get(id) ?? null;
    return sinConsentimiento.has(id)
      ? { persona_id: id, motivo: "sin_consentimiento", detalle: "Sin consentimiento vigente del apoderado.", disponible_desde: null }
      : null;
  }

  const textoAlumno = useValorDiferido(busquedaAlumno.trim());
  const filtrosLista = {
    busqueda: textoAlumno,
    sin_matricula: filtroSeccion === "sin-seccion",
    seccion_id: filtroSeccion !== "todas" && filtroSeccion !== "sin-seccion" ? Number(filtroSeccion) : undefined,
  };
  const lista = usePadronPaginado({ institucionId, filtros: filtrosLista, tamano: TAMANO_LISTA, habilitado: verLista });
  const idsVisibles = useIdsPadron({ institucionId, filtros: filtrosLista, habilitado: verLista });

  const seccionesConAlumnos = useMemo(() => (resumen?.secciones ?? []).filter((s) => s.cantidad > 0), [resumen]);
  const sinEstructura = resumen !== null && seccionesConAlumnos.length === 0;
  const padronVacio = resumen !== null && resumen.activos === 0;

  // Lo que de verdad se matricula: lo marcado menos quien no puede rendirla.
  const efectivas = Array.from(seleccionadas).filter((id) => !motivoBloqueo(id));
  const bloqueadasMarcadas = seleccionadas.size - efectivas.length;

  function alternarSalon(s: SeccionResumenPadron) {
    const ids = s.persona_ids ?? [];
    const quitar = salones.has(s.seccion_id);
    setSalones((prev) => {
      const copia = new Set(prev);
      if (quitar) copia.delete(s.seccion_id);
      else copia.add(s.seccion_id);
      return copia;
    });
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      ids.forEach((id) => (quitar ? copia.delete(id) : copia.add(id)));
      return copia;
    });
  }

  function alternarSeleccion(id: number) {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (copia.has(id)) copia.delete(id);
      else copia.add(id);
      return copia;
    });
  }

  const idsFiltroElegibles = idsVisibles.ids.filter((id) => !motivoBloqueo(id));
  const todasVisiblesMarcadas = idsFiltroElegibles.length > 0 && idsFiltroElegibles.every((id) => seleccionadas.has(id));
  function alternarTodasVisibles() {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (todasVisiblesMarcadas) idsFiltroElegibles.forEach((id) => copia.delete(id));
      else idsFiltroElegibles.forEach((id) => copia.add(id));
      return copia;
    });
  }

  // Nombre automático: los salones elegidos + la prueba + el año.
  const pruebaElegida = (pruebas ?? []).find((p) => p.id === pruebaIdElegida) ?? null;
  const detalleElegida = pruebaIdElegida !== null ? detalles.get(pruebaIdElegida) : undefined;
  const salonesElegidos = seccionesConAlumnos.filter((s) => salones.has(s.seccion_id));
  const nombreSugerido = useMemo(() => {
    const prueba = pruebaElegida ? pruebaElegida.nombre_corto || pruebaElegida.nombre_tecnico : "";
    const anio = salonesElegidos[0]?.anio_escolar ?? new Date().getFullYear();
    const grupo =
      salonesElegidos.length === 0
        ? efectivas.length > 0
          ? "Selección de estudiantes"
          : ""
        : salonesElegidos.length <= 3
          ? salonesElegidos.map(etiquetaSalon).join(", ")
          : `${salonesElegidos.length} salones`;
    return grupo ? [grupo, [prueba, anio].filter(Boolean).join(" ")].filter(Boolean).join(" — ") : "";
  }, [pruebaElegida, salonesElegidos, efectivas.length]);
  const nombreEfectivo = nombreManual ? form.nombre_grupo : nombreSugerido;

  const fechaPasada = fechaCierreEsPasada(form.fecha_fin);
  const faltante = !form.prueba_id
    ? "Elige una prueba para continuar."
    : efectivas.length === 0
      ? "Elige al menos un salón o un estudiante que pueda rendirla."
      : !nombreEfectivo.trim()
        ? "Ponle un nombre a la campaña."
        : null;

  async function crearYMatricular(e: React.FormEvent) {
    e.preventDefault();
    if (!institucionId) {
      setErrorCrear("Tu sesión no tiene una institución asociada — esta pantalla es para admin/psicólogo de un colegio.");
      return;
    }
    if (faltante || fechaPasada) {
      setErrorCrear(faltante ?? MENSAJE_FECHA_CIERRE_PASADA);
      return;
    }
    setCreando(true);
    setErrorCrear(null);
    let nueva: Evaluacion | null = campana;
    try {
      if (!nueva) {
        const payload: EvaluacionCreate = {
          prueba_id: Number(form.prueba_id),
          nombre_grupo: nombreEfectivo.trim(),
          institucion_id: institucionId,
          fecha_fin: form.fecha_fin ? new Date(form.fecha_fin).toISOString() : null,
        };
        nueva = await apiClient.post<Evaluacion>("/educativo/campanas/", payload);
        setCampana(nueva);
      }
      setResultadoMatricula(
        await apiClient.post<MatriculaRosterResponse>(`/educativo/campanas/${nueva.id}/matricular-roster`, efectivas),
      );
    } catch (err: unknown) {
      const mensaje = err instanceof Error && err.message ? err.message : "No se pudo crear la campaña.";
      // Si la campaña ya se creó y falló la matrícula, el botón reintenta
      // solo la matrícula (no crea otra campaña).
      setErrorCrear(nueva ? `La campaña se creó, pero no se pudo matricular: ${mensaje} Vuelve a intentarlo.` : mensaje);
    } finally {
      setCreando(false);
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
      setErrorCrear("El navegador no permitió copiar al portapapeles.");
    }
  }

  // 🔧 El backend ya rechaza esto con 403 (`requerir_staff_clinico` en
  // POST /educativo/campanas/ y /matricular-roster); mismo criterio que el
  // resto de la app: gatear en la UI lo que el backend ya gatea.
  const puedeCrearCampana = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  if (!puedeCrearCampana) {
    return (
      <div className="max-w-3xl mx-auto">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  const pasoActual = resultadoMatricula ? 2 : form.prueba_id ? 1 : 0;

  const terminoPrueba = busquedaPrueba.trim().toLowerCase();
  const pruebasVisibles = (pruebas ?? []).filter((p) => {
    if (filtroInformante !== "todos" && p.informante_tipo !== filtroInformante) return false;
    if (!terminoPrueba) return true;
    return [p.nombre_corto, p.nombre_tecnico, p.nombre_publico].some((v) => v?.toLowerCase().includes(terminoPrueba));
  });
  const informantesPresentes = Array.from(new Set((pruebas ?? []).map((p) => p.informante_tipo))).filter((i) => INFORMANTES[i]);
  const cargandoElegibilidad = pruebaIdElegida !== null && elegibilidad.isPending;

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas sinMargen items={[{ label: "Campañas", href: "/campanas" }, { label: "Nueva campaña" }]} />

      <EncabezadoPagina
        variante="destacado"
        icono={Flag}
        acento="azul"
        titulo="Nueva campaña"
        descripcion="Elige la prueba y los salones; cada estudiante recibe su link personal al examen."
        acciones={
          <Link href="/campanas" className={claseBotonBanner("secundario")}>
            Volver a campañas
          </Link>
        }
      >
        <IndicadorPasos actual={pasoActual} />
      </EncabezadoPagina>

      {!resultadoMatricula && (
        <form onSubmit={crearYMatricular} className="grid grid-cols-1 lg:grid-cols-[1fr_21rem] gap-5 items-start">
          <div className="space-y-5">
            {/* ===== 1. Prueba ===== */}
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <EncabezadoSeccion numero={1} titulo="Elige la prueba" subtitulo="El instrumento que responderán los alumnos." />
              <div className="px-5 pb-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
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
                            ? "bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark"
                            : "bg-mist text-ink/65 hover:bg-border dark:bg-surface-raised-dark dark:text-ink-dark/65 dark:hover:bg-border-dark"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                <TextoError className="mt-4">{errorPruebas}</TextoError>

                <div role="radiogroup" aria-label="Prueba" className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[22rem] overflow-y-auto pr-1 -mr-1">
                  {pruebas === null && !errorPruebas
                    ? Array.from({ length: 6 }).map((_, i) => (
                        <div key={i} className="h-[5.5rem] animate-pulse rounded-xl bg-border/50 dark:bg-border-dark" />
                      ))
                    : pruebasVisibles.map((p) => {
                        const elegida = p.id === pruebaIdElegida;
                        const informante = INFORMANTES[p.informante_tipo];
                        const { sigla, numero } = siglaPrueba(p);
                        return (
                          <button
                            key={p.id}
                            type="button"
                            role="radio"
                            aria-checked={elegida}
                            disabled={!!campana}
                            onClick={() => setForm({ ...form, prueba_id: String(p.id) })}
                            className={`relative flex items-start gap-3 rounded-xl border p-3.5 text-left transition-all ${
                              elegida
                                ? "border-acento-azul bg-acento-azul/[0.06] ring-2 ring-acento-azul/25 dark:border-acento-azul-dark dark:bg-acento-azul-dark/10 dark:ring-acento-azul-dark/25"
                                : "border-border bg-surface hover:border-acento-azul/50 dark:bg-surface-dark dark:border-border-dark dark:hover:border-acento-azul-dark/60 dark:hover:bg-surface-raised-dark"
                            }`}
                          >
                            <span
                              className={`flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-lg leading-none transition-colors ${
                                elegida
                                  ? "bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark"
                                  : "bg-acento-azul/10 text-acento-azul dark:bg-acento-azul-dark/15 dark:text-acento-azul-dark"
                              }`}
                              aria-hidden="true"
                            >
                              <span className={`font-display font-bold ${sigla.length > 3 ? "text-[11px]" : "text-[13px]"}`}>{sigla}</span>
                              {numero && <span className="mt-0.5 text-[10px] font-semibold opacity-80">{numero}</span>}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block pr-6 text-sm font-semibold text-ink dark:text-ink-dark">{p.nombre_corto || p.nombre_tecnico}</span>
                              <span className="mt-0.5 block text-xs leading-snug text-ink/55 dark:text-ink-dark/55 line-clamp-2">{p.nombre_publico}</span>
                              {informante && (
                                <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-mist px-2 py-0.5 text-[12px] font-medium text-ink/60 dark:bg-surface-raised-dark dark:text-ink-dark/60">
                                  <informante.icono size={11} aria-hidden="true" />
                                  {informante.label}
                                </span>
                              )}
                            </span>
                            {elegida && (
                              <span className="absolute right-3 top-3 flex h-5 w-5 items-center justify-center rounded-full bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark">
                                <Check size={13} strokeWidth={3} aria-hidden="true" />
                              </span>
                            )}
                          </button>
                        );
                      })}
                  {pruebas !== null && pruebasVisibles.length === 0 && (
                    <p className="sm:col-span-2 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">Ninguna prueba coincide con la búsqueda.</p>
                  )}
                </div>
              </div>
            </section>

            {/* ===== 2. Salones ===== */}
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <EncabezadoSeccion
                numero={2}
                titulo="Elige los salones"
                subtitulo="Cada salón elegido marca a todos sus alumnos que pueden rendir la prueba."
              />
              <div className="px-5 pb-5 space-y-3">
                {padronVacio ? (
                  <div className="py-8 text-center">
                    <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-ink/40 dark:text-ink-dark/40">
                      <Users size={22} aria-hidden="true" />
                    </span>
                    <p className="mt-3 text-sm font-medium text-ink dark:text-ink-dark">Tu padrón todavía está vacío</p>
                    <p className="mt-1 text-xs text-ink/50 dark:text-ink-dark/50">Registra o importa alumnos primero.</p>
                    <div className="mt-4 flex flex-wrap justify-center gap-2">
                      <Link href="/estudiantes/importar" className="rounded-card border border-border dark:border-border-dark px-4 py-2 text-sm font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark">
                        Importar Excel
                      </Link>
                      <Link href="/estudiantes/nuevo" className="rounded-card bg-accion dark:bg-teal-accent-dark px-4 py-2 text-sm font-medium text-white dark:text-mist-dark hover:bg-accion-hover">
                        + Registrar alumno
                      </Link>
                    </div>
                  </div>
                ) : sinEstructura ? (
                  <div className="flex items-start gap-3 rounded-xl border border-dashed border-border dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark/50 px-4 py-3 text-xs text-ink/65 dark:text-ink-dark/65">
                    <Info size={15} className="mt-px shrink-0 text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                    <p>
                      Ningún alumno tiene salón asignado todavía. Créalos en{" "}
                      <Link href="/academico" className="font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
                        Estructura académica
                      </Link>{" "}
                      y matricúlalos; mientras tanto, elige a los estudiantes uno por uno abajo.
                    </p>
                  </div>
                ) : resumen === null ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div key={i} className="h-16 animate-pulse rounded-xl bg-border/50 dark:bg-border-dark" />
                    ))}
                  </div>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    {seccionesConAlumnos.map((s) => {
                      const ids = s.persona_ids ?? [];
                      const bloqueados = ids.filter((id) => motivoBloqueo(id)).length;
                      const elegido = salones.has(s.seccion_id);
                      return (
                        <label
                          key={s.seccion_id}
                          className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${
                            elegido
                              ? "border-acento-azul bg-acento-azul/[0.07] dark:border-acento-azul-dark dark:bg-acento-azul-dark/10"
                              : "border-border bg-surface hover:border-acento-azul/50 dark:border-border-dark dark:bg-surface-dark"
                          } ${campana ? "pointer-events-none opacity-60" : ""}`}
                        >
                          <input
                            type="checkbox"
                            checked={elegido}
                            onChange={() => alternarSalon(s)}
                            className="mt-0.5 h-4 w-4 shrink-0 accent-teal-600"
                            aria-label={`Salón ${etiquetaSalon(s)}`}
                          />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-ink dark:text-ink-dark">{etiquetaSalon(s)}</span>
                            <span className="block text-xs text-ink/55 dark:text-ink-dark/55">
                              {s.cantidad} alumno{s.cantidad === 1 ? "" : "s"}
                              {bloqueados > 0 && (
                                <span className="text-red-700 dark:text-red-300">
                                  {" "}
                                  · {bloqueados} no pueden rendirla
                                </span>
                              )}
                            </span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
                {cargandoElegibilidad && (
                  <p className="flex items-center gap-2 text-xs text-ink/50 dark:text-ink-dark/50">
                    <span className="h-3 w-3 animate-spin rounded-full border-2 border-teal-600 border-t-transparent" aria-hidden="true" />
                    Revisando quién puede rendir esta prueba...
                  </p>
                )}
              </div>
            </section>

            {/* ===== 3. Ajuste alumno por alumno ===== */}
            {!padronVacio && (
              <section className={`${CLASE_TARJETA} overflow-hidden`}>
                <EncabezadoSeccion
                  numero={3}
                  titulo="Revisa los estudiantes"
                  subtitulo="Opcional: quita a alguien o agrega estudiantes de otros salones."
                />
                <div className="px-5 pb-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                    <p className="m-0 text-ink/70 dark:text-ink-dark/70">
                      <span className="font-display text-lg font-semibold text-teal-900 dark:text-ink-dark">{efectivas.length}</span>{" "}
                      estudiante{efectivas.length === 1 ? "" : "s"} seleccionado{efectivas.length === 1 ? "" : "s"}
                      {bloqueadasMarcadas > 0 && (
                        <span className="text-red-700 dark:text-red-300"> · {bloqueadasMarcadas} de tus salones no pueden rendirla</span>
                      )}
                    </p>
                    <button
                      type="button"
                      onClick={() => setVerLista((v) => !v)}
                      aria-expanded={verLista}
                      className="text-[13px] font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
                    >
                      {verLista ? "Ocultar la lista" : "Ver y ajustar la lista"}
                    </button>
                  </div>

                  {verLista && (
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
                          {seccionesConAlumnos.map((s) => (
                            <option key={s.seccion_id} value={String(s.seccion_id)}>
                              {etiquetaSalon(s)}
                            </option>
                          ))}
                          <option value="sin-seccion">Sin sección</option>
                        </Select>
                      </div>

                      <TextoError>{lista.error}</TextoError>

                      <div className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark overflow-hidden">
                        <label className="flex items-center gap-3 bg-mist/70 dark:bg-surface-raised-dark px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink/55 dark:text-ink-dark/55 cursor-pointer">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-teal-600"
                            checked={todasVisiblesMarcadas}
                            onChange={alternarTodasVisibles}
                            disabled={idsFiltroElegibles.length === 0 || !!campana}
                          />
                          Seleccionar todos los que pueden rendirla ({idsFiltroElegibles.length})
                        </label>
                        <div className="max-h-[24rem] overflow-y-auto divide-y divide-border dark:divide-border-dark">
                          {lista.items.length === 0 ? (
                            <p className="px-4 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">
                              {lista.cargando ? "Cargando alumnos..." : "Ningún alumno coincide con el filtro."}
                            </p>
                          ) : (
                            lista.items.map((p) => {
                              const bloqueo = motivoBloqueo(p.id);
                              const marcada = seleccionadas.has(p.id) && !bloqueo;
                              const seccion = p.seccion_actual ? [p.seccion_actual.grado, p.seccion_actual.seccion].filter(Boolean).join(" ") : null;
                              return (
                                <label
                                  key={p.id}
                                  className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                                    bloqueo
                                      ? "cursor-not-allowed bg-mist/40 dark:bg-surface-raised-dark/40"
                                      : marcada
                                        ? "cursor-pointer bg-teal-600/[0.05] dark:bg-teal-accent-dark/[0.07]"
                                        : "cursor-pointer hover:bg-mist/50 dark:hover:bg-surface-raised-dark/60"
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    className="h-4 w-4 shrink-0 accent-teal-600"
                                    checked={marcada}
                                    disabled={!!bloqueo || !!campana}
                                    onChange={() => alternarSeleccion(p.id)}
                                  />
                                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-[12px] font-bold text-teal-700 dark:text-teal-accent-dark">
                                    {`${p.nombres[0] ?? ""}${p.apellidos[0] ?? ""}`.toUpperCase()}
                                  </span>
                                  <span className="min-w-0 flex-1">
                                    <span className={`block truncate font-medium ${bloqueo ? "text-ink/50 dark:text-ink-dark/50" : "text-ink dark:text-ink-dark"}`}>
                                      {p.nombres} {p.apellidos}
                                    </span>
                                    <span className="block truncate text-xs text-ink/50 dark:text-ink-dark/50">
                                      {[seccion, p.codigo_institucional && `Cód. ${p.codigo_institucional}`].filter(Boolean).join(" · ") || "Sin sección"}
                                    </span>
                                  </span>
                                  {bloqueo && (
                                    <span
                                      className="shrink-0 inline-flex max-w-[16rem] items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[12px] font-medium text-red-700 dark:bg-red-500/15 dark:text-red-300"
                                      title={bloqueo.detalle}
                                    >
                                      <Ban size={11} className="shrink-0" aria-hidden="true" />
                                      <span className="truncate">
                                        {bloqueo.disponible_desde ? `Disponible desde el ${fechaCorta(bloqueo.disponible_desde)}` : bloqueo.detalle}
                                      </span>
                                    </span>
                                  )}
                                </label>
                              );
                            })
                          )}
                          {lista.hayMas && (
                            <button
                              type="button"
                              onClick={() => lista.cargarMas()}
                              disabled={lista.cargando}
                              className="w-full px-4 py-2.5 text-center text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:bg-mist/50 dark:hover:bg-surface-raised-dark/60 disabled:opacity-50"
                            >
                              {lista.cargando ? "Cargando..." : `Cargar más (${lista.items.length} de ${lista.total})`}
                            </button>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </section>
            )}

            {/* ===== 4. Detalles ===== */}
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <EncabezadoSeccion numero={4} titulo="Detalles" subtitulo="Nombre y cierre de la campaña." />
              <div className="px-5 pb-5">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                  <CampoEditable etiqueta="Nombre de la campaña">
                    <Input
                      required
                      value={nombreEfectivo}
                      readOnly={!nombreManual}
                      onChange={(e) => setForm({ ...form, nombre_grupo: e.target.value })}
                      placeholder="Se arma al elegir la prueba y los salones"
                      className={!nombreManual ? "bg-mist/60 dark:bg-surface-raised-dark text-ink/80" : ""}
                    />
                    <button
                      type="button"
                      onClick={() => {
                        if (!nombreManual) setForm({ ...form, nombre_grupo: nombreSugerido });
                        setNombreManual((v) => !v);
                      }}
                      className="self-start text-xs font-medium text-teal-700 dark:text-teal-accent-dark hover:underline"
                    >
                      {nombreManual ? "Usar el nombre automático" : "Editar el nombre"}
                    </button>
                  </CampoEditable>
                  <CampoEditable etiqueta="Fecha de cierre (opcional)">
                    <Input
                      type="datetime-local"
                      min={ahoraParaInputLocal()}
                      value={form.fecha_fin}
                      onChange={(e) => setForm({ ...form, fecha_fin: e.target.value })}
                      aria-invalid={fechaPasada}
                      className={fechaPasada ? "border-red-400 focus:ring-red-300" : ""}
                    />
                    {fechaPasada ? (
                      <span className="text-xs font-medium text-red-700">{MENSAJE_FECHA_CIERRE_PASADA}</span>
                    ) : (
                      <span className="text-xs text-ink/45 dark:text-ink-dark/45">Después de esta fecha los links dejan de funcionar.</span>
                    )}
                  </CampoEditable>
                </div>
              </div>
            </section>
          </div>

          {/* Resumen lateral */}
          <aside className="lg:sticky lg:top-0 space-y-4">
            <section className={`${CLASE_TARJETA} overflow-hidden`}>
              <div className="bg-gradient-to-br from-teal-900 to-acento-azul dark:from-surface-raised-dark dark:to-surface-dark px-5 py-4">
                <p className="text-[12px] font-semibold uppercase tracking-wider text-white/60 dark:text-acento-azul-dark">Resumen</p>
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
                      {elegibilidad.data && (
                        <span className="block text-xs text-ink/50 dark:text-ink-dark/50">
                          Se reaplica cada {elegibilidad.data.dias_minimos_entre_aplicaciones} días
                        </span>
                      )}
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
                            <span key={d.id} className="rounded-md bg-mist px-1.5 py-0.5 text-[12px] text-ink/70 dark:bg-surface-raised-dark dark:text-ink-dark/70">
                              {d.nombre}
                            </span>
                          ))}
                          {detalleElegida.dimensiones.length > 8 && (
                            <span className="text-[12px] text-ink/45 dark:text-ink-dark/45">+{detalleElegida.dimensiones.length - 8} más</span>
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
                <FilaResumen icono={Users} etiqueta="Estudiantes">
                  <span className="font-semibold text-ink dark:text-ink-dark">{efectivas.length}</span>
                  <span className="text-ink/60 dark:text-ink-dark/60">
                    {" "}
                    {salonesElegidos.length > 0 ? `de ${salonesElegidos.length} salón${salonesElegidos.length === 1 ? "" : "es"}` : "elegidos"}
                  </span>
                  {bloqueadasMarcadas > 0 && (
                    <span className="block text-xs text-red-700 dark:text-red-300">{bloqueadasMarcadas} no pueden rendirla (quedan fuera)</span>
                  )}
                </FilaResumen>
                <FilaResumen icono={Eye} etiqueta="Resultado">
                  <span className="text-ink dark:text-ink-dark">Solo el equipo de orientación</span>
                </FilaResumen>
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
                  disabled={creando || !!faltante || fechaPasada || cargandoElegibilidad}
                  className="w-full inline-flex items-center justify-center gap-2 !py-2.5"
                >
                  {creando ? "Creando..." : campana ? "Reintentar la matrícula" : "Crear campaña y generar links"}
                  {!creando && <ArrowRight size={16} aria-hidden="true" />}
                </Boton>
                {faltante && <p className="text-center text-xs text-ink/45 dark:text-ink-dark/45">{faltante}</p>}
              </div>
            </section>

            <div className="rounded-2xl border border-dashed border-border dark:border-border-dark p-4 text-xs text-ink/60 dark:text-ink-dark/60">
              <p className="flex items-center gap-1.5 font-semibold text-ink/75 dark:text-ink-dark/75">
                <Info size={14} aria-hidden="true" />
                ¿Cómo funciona?
              </p>
              <p className="mt-1.5 leading-relaxed">
                Cada alumno recibe un link único y responde sin iniciar sesión. Si un resultado indica riesgo, el informe queda retenido
                hasta que lo revises. Para evaluar a un solo estudiante, usa «Aplicar prueba» desde su perfil.
              </p>
            </div>
          </aside>
        </form>
      )}

      {/* ===== Links ===== */}
      {campana && resultadoMatricula && (
        <div className="space-y-6">
          <section className={`${CLASE_TARJETA} overflow-hidden`}>
            <div className="bg-gradient-to-br from-teal-900 to-acento-azul dark:from-surface-raised-dark dark:to-surface-dark px-6 py-7 text-center">
              <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-white/15 dark:bg-teal-accent-dark/15">
                <CircleCheck size={28} className="text-white dark:text-acento-azul-dark" aria-hidden="true" />
              </span>
              <h2 className="mt-3 font-display text-xl sm:text-2xl font-semibold text-white dark:text-ink-dark">¡Campaña lista!</h2>
              <p className="mt-1 text-sm text-white/75 dark:text-ink-dark/60">Comparte con cada alumno su link personal. «{campana.nombre_grupo}»</p>
            </div>
            <div className="grid grid-cols-2 divide-x divide-border dark:divide-border-dark">
              <div className="px-5 py-4 text-center">
                <p className="font-display text-2xl font-semibold text-teal-900 dark:text-ink-dark">{resultadoMatricula.generados.length}</p>
                <p className="text-xs text-ink/55 dark:text-ink-dark/55">links generados</p>
              </div>
              <div className="px-5 py-4 text-center">
                <p className={`font-display text-2xl font-semibold ${resultadoMatricula.rechazados.length > 0 ? "text-red-700 dark:text-red-300" : "text-teal-900 dark:text-ink-dark"}`}>
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
                No se generó link para {resultadoMatricula.rechazados.length} alumno{resultadoMatricula.rechazados.length === 1 ? "" : "s"}
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
                  <Link2 size={17} aria-hidden="true" className="text-acento-azul dark:text-acento-azul-dark" />
                  Links de examen
                </h3>
                <Boton
                  variante="secundario"
                  onClick={() =>
                    copiar(resultadoMatricula.generados.map((ins) => `${ins.nombre_completo ?? "Alumno"}: ${urlExamen(ins.token)}`).join("\n"), "todos")
                  }
                  className="inline-flex items-center justify-center gap-1.5 !py-1.5"
                >
                  {copiado === "todos" ? <Check size={15} aria-hidden="true" /> : <Copy size={15} aria-hidden="true" />}
                  {copiado === "todos" ? "Copiados" : "Copiar todos los links"}
                </Boton>
              </div>
              <ul className="max-h-[26rem] overflow-y-auto bg-surface dark:bg-surface-dark divide-y divide-border dark:divide-border-dark">
                {resultadoMatricula.generados.map((ins) => {
                  const url = urlExamen(ins.token);
                  return (
                    <li key={ins.id} className="flex items-center gap-3 px-5 py-3">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-[12px] font-bold text-teal-700 dark:text-teal-accent-dark">
                        {(ins.nombre_completo?.[0] || "?").toUpperCase()}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">{ins.nombre_completo}</p>
                        <p className="truncate font-mono text-[12px] text-ink/40 dark:text-ink-dark/40">{url}</p>
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

          <TextoError>{errorCrear}</TextoError>

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

// Dentro de la franja "destacado" (degradado en claro, neutra en oscuro):
// círculos blancos/translúcidos en vez de teal sobre teal.
function IndicadorPasos({ actual }: { actual: number }) {
  return (
    <ol className="m-0 mt-3.5 flex max-w-xl list-none items-center gap-2 p-0 sm:gap-3">
      {PASOS.map((paso, i) => {
        const hecho = i < actual;
        const activo = i === actual;
        return (
          <li key={paso} className={`flex items-center gap-2 sm:gap-3 ${i < PASOS.length - 1 ? "flex-1" : ""}`}>
            <span className="flex items-center gap-2" aria-current={activo ? "step" : undefined}>
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold transition-colors ${
                  hecho
                    ? "bg-white/90 text-teal-900 dark:bg-acento-azul-dark dark:text-mist-dark"
                    : activo
                      ? "bg-white text-acento-azul ring-4 ring-white/25 dark:bg-acento-azul-dark dark:text-mist-dark dark:ring-acento-azul-dark/25"
                      : "bg-white/10 text-white/70 ring-1 ring-white/30 dark:bg-surface-dark dark:text-ink-dark/40 dark:ring-border-dark"
                }`}
              >
                {hecho ? <Check size={14} strokeWidth={3} aria-hidden="true" /> : i + 1}
              </span>
              <span
                className={`text-[12.5px] font-semibold whitespace-nowrap ${
                  activo ? "text-white dark:text-ink-dark" : "text-white/65 dark:text-ink-dark/45"
                } ${activo ? "" : "hidden md:inline"}`}
              >
                {paso}
              </span>
            </span>
            {i < PASOS.length - 1 && (
              <span className={`h-0.5 flex-1 rounded-full ${hecho ? "bg-white/80 dark:bg-acento-azul-dark" : "bg-white/25 dark:bg-border-dark"}`} />
            )}
          </li>
        );
      })}
    </ol>
  );
}

// Cabecera de bloque — mismo lenguaje que los formularios de Estudiantes
// (franja suave + número en el chip del acento de la sección).
function EncabezadoSeccion({ numero, titulo, subtitulo }: { numero: number; titulo: string; subtitulo: string }) {
  return (
    <div className="mb-5 flex items-center gap-3 border-b px-5 py-3.5 border-acento-azul/15 dark:border-acento-azul-dark/20 bg-acento-azul/[0.08] dark:bg-acento-azul-dark/[0.08]">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark">
        {numero}
      </span>
      <div>
        <h2 className="m-0 font-display text-[15px] font-semibold text-teal-900 dark:text-ink-dark">{titulo}</h2>
        <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">{subtitulo}</p>
      </div>
    </div>
  );
}

function FilaResumen({ icono: Icono, etiqueta, children }: { icono: LucideIcon; etiqueta: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 px-5 py-3.5">
      <Icono size={16} className="mt-0.5 shrink-0 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <dt className="text-[12px] font-semibold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">{etiqueta}</dt>
        <dd className="mt-0.5">{children}</dd>
      </div>
    </div>
  );
}
