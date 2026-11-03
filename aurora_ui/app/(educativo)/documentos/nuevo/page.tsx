"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { FilePlus2, LayoutTemplate, Users, School, Search, X, ClipboardList, Info, ArrowRight } from "lucide-react";
import { apiClient, mensajeDe } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { ACENTOS } from "@/lib/acentos";
import { Boton } from "@/components/ui/Boton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import { ControlSegmentado, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import { CabeceraInterna, PasoFormulario, TarjetaLateral, CampoFormulario } from "@/components/documentos/PiezasDocumento";
import type {
  TipoDocumento,
  PlantillaDocumento,
  DocumentoInstitucional,
  DocumentoInstitucionalCreate,
  Persona,
  NivelEducativo,
  Grado,
  Seccion,
  RespuestaPaginada,
} from "@/types/api";

type Alcance = "personas" | "estructura";
type Granularidad = "seccion" | "grado" | "nivel";

const VIOLETA = ACENTOS.violeta;
const MIGAS = [{ label: "Documentos", href: "/documentos" }, { label: "Nuevo documento" }];

// Crear un DocumentoInstitucional: elegir plantilla, a quién va (uno o
// varios alumnos del padrón, o un salón/grado/nivel completo) y el
// título. El contenido se llena después, en /documentos/[id].
//
// Atajos por query string, ambos opcionales y combinables:
// - ?plantilla_id=X — viene del botón "Generar documento" de una tarjeta
//   de /documentos (pestaña "Mis plantillas"): precarga esa plantilla.
// - ?persona_id=X — viene del botón "+ Nuevo documento" de la ficha de un
//   alumno: precarga ESE alumno como dato fijo, con "Elegir otro alumno".
//
// 🆕 Rediseño (sesión 2026-11-01): 3 pasos numerados que se marcan con ✓ al
// completarse + un resumen lateral con el botón de crear, en el violeta de
// Documentos. El título se sugiere solo a partir de la plantilla. Se
// conservan los textos que usa e2e/documentos.spec.ts (etiquetas
// "Plantilla"/"Título", el buscador y "Crear documento").
export default function NuevoDocumentoPage() {
  const { sesion } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const plantillaIdParam = searchParams.get("plantilla_id");
  const personaIdParam = searchParams.get("persona_id");

  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([]);
  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [plantillaId, setPlantillaId] = useState("");
  const [titulo, setTitulo] = useState("");
  // true mientras el título sea el sugerido por la plantilla (cambiar de
  // plantilla lo actualiza); se apaga en cuanto el usuario lo edita.
  const [tituloSugerido, setTituloSugerido] = useState(true);
  const [alcance, setAlcance] = useState<Alcance>("personas");

  // --- Alcance: alumno(s) ---
  // 🆕 Escalabilidad (sesión 2026-11-01): el buscador consulta el SERVIDOR
  // (?busqueda=, tope de 20) en vez de descargar el padrón completo al
  // abrir la pantalla. Los alumnos ya elegidos se guardan aparte
  // (`elegidos`) para no perder su nombre al cambiar la búsqueda.
  const [resultados, setResultados] = useState<Persona[]>([]);
  const [totalResultados, setTotalResultados] = useState(0);
  const [buscandoAlumnos, setBuscandoAlumnos] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  const [elegidos, setElegidos] = useState<Record<number, Persona>>({});
  const [alumnoFijado, setAlumnoFijado] = useState(false);

  // --- Alcance: estructura académica ---
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [grados, setGrados] = useState<Grado[]>([]);
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [nivelId, setNivelId] = useState("");
  const [gradoId, setGradoId] = useState("");
  const [seccionId, setSeccionId] = useState("");
  const [granularidad, setGranularidad] = useState<Granularidad>("seccion");

  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState<string | null>(null);

  // Borradores YA abiertos de esta misma plantilla para los alumnos
  // elegidos (sesión 2026-11-01) — solo avisa y ofrece continuarlo, nunca
  // bloquea. 🆕 Una sola consulta filtrada en el servidor (antes una por
  // alumno, con tope de 5).
  const [borradoresExistentes, setBorradoresExistentes] = useState<DocumentoInstitucional[]>([]);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    Promise.all([
      apiClient.get<PlantillaDocumento[]>(`/documentos/plantillas?institucion_id=${sesion.institucionId}`),
      apiClient.get<TipoDocumento[]>("/documentos/tipos?solo_activos=true"),
      apiClient.get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`),
      // Solo el alumno precargado (si vino de su ficha), nunca el padrón entero.
      personaIdParam
        ? apiClient.get<Persona>(`/admin/personas/${personaIdParam}/detalle`).catch(() => null)
        : Promise.resolve(null),
    ])
      .then(([p, t, nivelesResp, personaPrecargada]) => {
        const plantillasActivas = p.filter((x) => x.activa);
        setPlantillas(plantillasActivas);
        setTipos(t);
        setNiveles(nivelesResp);

        const precargada = plantillaIdParam ? plantillasActivas.find((x) => x.id === Number(plantillaIdParam)) : undefined;
        if (precargada) {
          setPlantillaId(String(precargada.id));
          setTitulo(tituloDesdePlantilla(precargada));
        }
        if (personaPrecargada && personaPrecargada.institucion_id === sesion.institucionId) {
          setAlcance("personas");
          setSeleccionadas(new Set([personaPrecargada.id]));
          setElegidos({ [personaPrecargada.id]: personaPrecargada });
          setAlumnoFijado(true);
        }
      })
      .catch((err) => setError(err.message || "No se pudo cargar la información necesaria."))
      .finally(() => setCargando(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sesion?.institucionId]);

  // 🆕 (sesión 2026-11-02) Los efectos solo CARGAN. Vaciar el grado/sección
  // al quitar el nivel/grado lo hace el onChange de cada select, y la lista
  // visible se deriva (antes el efecto hacía setState directo: lint
  // react-hooks/set-state-in-effect).
  useEffect(() => {
    if (!nivelId) return;
    apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelId}`).then(setGrados).catch(() => setGrados([]));
  }, [nivelId]);

  useEffect(() => {
    if (!gradoId) return;
    apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoId}`).then(setSecciones).catch(() => setSecciones([]));
  }, [gradoId]);

  const gradosVisibles = nivelId ? grados : [];
  const seccionesVisibles = gradoId ? secciones : [];

  // Búsqueda en el servidor, 250 ms después de dejar de escribir. Sin texto
  // muestra los primeros 20 por apellido.
  useEffect(() => {
    if (!sesion?.institucionId || alcance !== "personas" || alumnoFijado) return;
    let vigente = true;
    const t = setTimeout(() => {
      setBuscandoAlumnos(true);
      const params = new URLSearchParams({ limit: "20" });
      if (busqueda.trim()) params.set("busqueda", busqueda.trim());
      apiClient
        .get<RespuestaPaginada<Persona>>(`/admin/personas/${sesion.institucionId}?${params.toString()}`)
        .then((r) => {
          if (!vigente) return;
          setResultados(r.items);
          setTotalResultados(r.total);
        })
        .catch(() => vigente && setResultados([]))
        .finally(() => vigente && setBuscandoAlumnos(false));
    }, 250);
    return () => {
      vigente = false;
      clearTimeout(t);
    };
  }, [sesion?.institucionId, busqueda, alcance, alumnoFijado]);

  function alternarPersona(persona: Persona) {
    const id = persona.id;
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (copia.has(id)) copia.delete(id);
      else copia.add(id);
      return copia;
    });
    setElegidos((prev) => ({ ...prev, [id]: persona }));
  }

  function quitarPersona(id: number) {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      copia.delete(id);
      return copia;
    });
  }

  function elegirPlantilla(id: string) {
    setPlantillaId(id);
    const p = plantillas.find((x) => x.id === Number(id));
    if (p && (tituloSugerido || !titulo)) {
      setTitulo(tituloDesdePlantilla(p));
      setTituloSugerido(true);
    }
  }

  const buscarBorradores = !!sesion?.institucionId && !!plantillaId && alcance === "personas" && seleccionadas.size > 0;

  useEffect(() => {
    if (!buscarBorradores) return;
    let vigente = true;
    const params = new URLSearchParams({
      institucion_id: String(sesion.institucionId),
      plantilla_documento_id: plantillaId,
      estado: "borrador",
      limit: "20",
    });
    Array.from(seleccionadas).forEach((id) => params.append("persona_id", String(id)));
    apiClient
      .get<RespuestaPaginada<DocumentoInstitucional>>(`/documentos/?${params.toString()}`)
      .then((r) => vigente && setBorradoresExistentes(r.items))
      .catch(() => vigente && setBorradoresExistentes([]));
    return () => {
      vigente = false;
    };
  }, [sesion?.institucionId, plantillaId, seleccionadas, buscarBorradores]);
  // Fuera de las condiciones de búsqueda el aviso se oculta sin tocar el
  // estado (nada de setState síncrono dentro del efecto).
  const borradoresVisibles = buscarBorradores ? borradoresExistentes : [];

  const plantillaElegida = plantillas.find((p) => p.id === Number(plantillaId));
  const tipoElegido = plantillaElegida ? tipos.find((t) => t.id === plantillaElegida.tipo_documento_id) : undefined;
  const personasPorId = useMemo(() => {
    const mapa = new Map<number, Persona>(Object.values(elegidos).map((p) => [p.id, p]));
    resultados.forEach((p) => mapa.set(p.id, p));
    return mapa;
  }, [elegidos, resultados]);
  const personasFiltradas = resultados;

  const destinatariosListos = alcance === "personas" ? seleccionadas.size > 0 : !!nivelId;
  const tituloListo = titulo.trim().length >= 2;
  const puedeCrear = !creando && !!plantillaId && tituloListo && destinatariosListos;

  function resumenDestino(): string {
    if (alcance === "personas") {
      if (seleccionadas.size === 0) return "Sin elegir";
      if (seleccionadas.size === 1) {
        const p = personasPorId.get(Array.from(seleccionadas)[0]);
        return p ? `${p.nombres} ${p.apellidos}` : "1 alumno";
      }
      return `${seleccionadas.size} alumnos`;
    }
    if (!nivelId) return "Sin elegir";
    const nivel = niveles.find((n) => n.id === Number(nivelId))?.nombre;
    const grado = gradosVisibles.find((g) => g.id === Number(gradoId))?.nombre;
    const seccion = seccionesVisibles.find((s) => s.id === Number(seccionId))?.nombre;
    return [nivel, grado, seccion && `Sección ${seccion}`].filter(Boolean).join(" · ");
  }

  async function crearDocumento(e: React.FormEvent) {
    e.preventDefault();
    if (!plantillaElegida || !tipoElegido) return;
    setCreando(true);
    setErrorCrear(null);
    try {
      const payload: DocumentoInstitucionalCreate = {
        tipo_documento_id: tipoElegido.id,
        plantilla_documento_id: plantillaElegida.id,
        titulo,
        alcance: alcance === "personas" ? "personas_especificas" : "estructura_academica",
      };
      if (alcance === "personas") {
        payload.personas_ids = Array.from(seleccionadas);
      } else {
        const nodo: { nivel_educativo_id?: number; grado_id?: number; seccion_id?: number } = {};
        if (granularidad === "seccion" && seccionId) nodo.seccion_id = Number(seccionId);
        else if (granularidad === "grado" && gradoId) nodo.grado_id = Number(gradoId);
        else if (granularidad === "nivel" && nivelId) nodo.nivel_educativo_id = Number(nivelId);
        payload.estructura = [nodo];
        const seccionElegida = seccionesVisibles.find((s) => s.id === Number(seccionId));
        if (seccionElegida) payload.anio_escolar = seccionElegida.anio_escolar;
      }
      const nuevo = await apiClient.post<DocumentoInstitucional>("/documentos/", payload);
      router.push(`/documentos/${nuevo.id}`);
    } catch (err) {
      setErrorCrear(mensajeDe(err) || "No se pudo crear el documento.");
    } finally {
      setCreando(false);
    }
  }

  if (cargando) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        <CabeceraInterna migas={MIGAS} icono={FilePlus2} titulo="Nuevo documento" />
        <EsqueletoLista cantidad={3} />
      </div>
    );
  }

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <CabeceraInterna
        migas={MIGAS}
        icono={FilePlus2}
        titulo="Nuevo documento"
        subtitulo="Elige la plantilla y para quién es. El contenido lo completas en el siguiente paso."
      />

      <TextoError>{error}</TextoError>

      <form onSubmit={crearDocumento} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
        <div className="flex flex-col gap-4 min-w-0">
          {/* ---- Paso 1: plantilla ---- */}
          <PasoFormulario numero={1} titulo="Plantilla" descripcion="Solo aparecen las plantillas activas de tu institución." completo={!!plantillaElegida}>
            <CampoFormulario etiqueta="Plantilla">
              <Select required value={plantillaId} onChange={(e) => elegirPlantilla(e.target.value)}>
                <option value="">Elige una plantilla...</option>
                {plantillas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre}
                  </option>
                ))}
              </Select>
            </CampoFormulario>
            {plantillaElegida && tipoElegido && (
              <p className="m-0 mt-2 flex items-center gap-1.5 text-[12px] text-ink/55 dark:text-ink-dark/55">
                <LayoutTemplate size={13} className={VIOLETA.texto} aria-hidden="true" />
                {tipoElegido.nombre}
                {tipoElegido.requiere_consentimiento_individual && " · requiere consentimiento vigente del apoderado para emitirse"}
              </p>
            )}
            {plantillas.length === 0 && (
              <p className="m-0 mt-2 text-[12px] text-ink/55 dark:text-ink-dark/55">
                Tu institución todavía no tiene ninguna plantilla activa.{" "}
                <Link href="/documentos" className={`font-semibold hover:underline ${VIOLETA.texto}`}>
                  Clona una del catálogo →
                </Link>
              </p>
            )}
          </PasoFormulario>

          {/* ---- Paso 2: destinatarios ---- */}
          <PasoFormulario numero={2} titulo="¿Para quién es?" completo={destinatariosListos}>
            <ControlSegmentado<Alcance>
              etiqueta="Destinatarios"
              valor={alcance}
              onCambiar={setAlcance}
              className="mb-3"
              opciones={[
                { valor: "personas", etiqueta: "Uno o varios alumnos", icono: Users },
                { valor: "estructura", etiqueta: "Salón, grado o nivel", icono: School },
              ]}
            />

            {alcance === "personas" ? (
              alumnoFijado ? (
                // Vino con ?persona_id= desde la ficha del alumno.
                <div className={`flex items-center justify-between gap-3 rounded-lg border px-3.5 py-2.5 ${VIOLETA.fondo}`}>
                  <span className="text-sm text-ink dark:text-ink-dark">
                    Documento para: <strong className="font-semibold">{resumenDestino()}</strong>
                  </span>
                  <button
                    type="button"
                    onClick={() => setAlumnoFijado(false)}
                    className={`text-xs font-semibold hover:underline whitespace-nowrap ${VIOLETA.texto}`}
                  >
                    Elegir otro alumno
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  {seleccionadas.size > 0 && (
                    <ul className="m-0 p-0 list-none flex flex-wrap gap-1.5" aria-label="Alumnos elegidos">
                      {Array.from(seleccionadas).map((id) => {
                        const p = personasPorId.get(id);
                        return (
                          <li key={id} className={`inline-flex items-center gap-1 rounded-full pl-2.5 pr-1 py-0.5 text-[12px] font-medium ${VIOLETA.chip}`}>
                            {p ? `${p.apellidos}, ${p.nombres}` : `#${id}`}
                            <button
                              type="button"
                              onClick={() => quitarPersona(id)}
                              aria-label="Quitar alumno"
                              className="rounded-full p-0.5 hover:bg-acento-violeta/15 dark:hover:bg-acento-violeta-dark/20"
                            >
                              <X size={12} aria-hidden="true" />
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  <div className="relative">
                    <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
                    <Input
                      placeholder="Buscar por nombre o apellido..."
                      value={busqueda}
                      onChange={(e) => setBusqueda(e.target.value)}
                      className="w-full pl-9"
                    />
                  </div>
                  <div className="max-h-60 overflow-y-auto rounded-lg border border-border dark:border-border-dark divide-y divide-border dark:divide-border-dark">
                    {personasFiltradas.map((p) => {
                      const marcado = seleccionadas.has(p.id);
                      return (
                        <label
                          key={p.id}
                          className={`flex items-center gap-2.5 px-3 py-2 text-sm cursor-pointer transition-colors ${
                            marcado ? "bg-acento-violeta/[0.06] dark:bg-acento-violeta-dark/[0.08]" : "hover:bg-mist/50 dark:hover:bg-surface-raised-dark"
                          }`}
                        >
                          <input type="checkbox" checked={marcado} onChange={() => alternarPersona(p)} className="accent-[var(--color-acento-violeta)]" />
                          <span className="flex-1 min-w-0 truncate text-ink dark:text-ink-dark">
                            {p.nombres} {p.apellidos}
                          </span>
                          {p.grado_seccion && <span className="text-[12px] text-ink/45 dark:text-ink-dark/45">{p.grado_seccion}</span>}
                        </label>
                      );
                    })}
                    {!buscandoAlumnos && personasFiltradas.length === 0 && (
                      <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50 italic px-3 py-3">
                        {busqueda.trim() ? "Ningún alumno coincide con la búsqueda." : "No hay alumnos en el padrón de tu institución."}
                      </p>
                    )}
                    {buscandoAlumnos && personasFiltradas.length === 0 && (
                      <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50 italic px-3 py-3">Buscando...</p>
                    )}
                  </div>
                  {totalResultados > personasFiltradas.length && (
                    <p className="m-0 text-[12px] text-ink/45 dark:text-ink-dark/45">
                      Mostrando {personasFiltradas.length} de {totalResultados}. Escribe nombre, apellido o DNI para afinar.
                    </p>
                  )}
                </div>
              )
            ) : (
              <div className="space-y-2.5">
                <div className="grid sm:grid-cols-3 gap-3">
                  <CampoFormulario etiqueta="Nivel">
                    <Select value={nivelId} onChange={(e) => { setNivelId(e.target.value); setGranularidad("nivel"); if (!e.target.value) { setGradoId(""); setSeccionId(""); } }}>
                      <option value="">Elige...</option>
                      {niveles.map((n) => (
                        <option key={n.id} value={n.id}>
                          {n.nombre}
                        </option>
                      ))}
                    </Select>
                  </CampoFormulario>
                  <CampoFormulario etiqueta="Grado">
                    <Select value={gradoId} onChange={(e) => { setGradoId(e.target.value); setGranularidad("grado"); if (!e.target.value) setSeccionId(""); }} disabled={!nivelId}>
                      <option value="">Todo el nivel</option>
                      {gradosVisibles.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.nombre}
                        </option>
                      ))}
                    </Select>
                  </CampoFormulario>
                  <CampoFormulario etiqueta="Sección">
                    <Select value={seccionId} onChange={(e) => { setSeccionId(e.target.value); setGranularidad("seccion"); }} disabled={!gradoId}>
                      <option value="">Todo el grado</option>
                      {seccionesVisibles.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.nombre} {s.anio_escolar}
                        </option>
                      ))}
                    </Select>
                  </CampoFormulario>
                </div>
                <p className="m-0 flex items-start gap-1.5 text-[12px] text-ink/50 dark:text-ink-dark/50">
                  <Info size={12} className="mt-px shrink-0" aria-hidden="true" />
                  Se usa lo más específico que elijas: una sección, o todo el grado/nivel si dejas la sección o el grado en blanco.
                </p>
              </div>
            )}
          </PasoFormulario>

          {/* ---- Paso 3: título ---- */}
          <PasoFormulario numero={3} titulo="Título" descripcion="Así se verá en la lista de documentos y en el PDF." completo={tituloListo}>
            {/* El backend exige mínimo 2 caracteres (DocumentoInstitucionalCreate.titulo). */}
            <CampoFormulario etiqueta="Título">
              <Input
                required
                minLength={2}
                value={titulo}
                onChange={(e) => {
                  setTitulo(e.target.value);
                  setTituloSugerido(false);
                }}
                placeholder="Ej. Informe psicológico"
              />
            </CampoFormulario>
            {tituloSugerido && plantillaElegida && titulo && (
              <p className="m-0 mt-1.5 text-[12px] text-ink/45 dark:text-ink-dark/45">Sugerido a partir de la plantilla; puedes cambiarlo.</p>
            )}
          </PasoFormulario>
        </div>

        {/* ---- Resumen lateral ---- */}
        <div className="flex flex-col gap-4 lg:sticky lg:top-4">
          <TarjetaLateral icono={ClipboardList} titulo="Resumen">
            <dl className="m-0 space-y-2.5 text-[13px]">
              <FilaResumen etiqueta="Plantilla" valor={plantillaElegida?.nombre} />
              <FilaResumen etiqueta="Para" valor={destinatariosListos ? resumenDestino() : undefined} />
              <FilaResumen etiqueta="Título" valor={tituloListo ? titulo : undefined} />
            </dl>

            {borradoresVisibles.length > 0 && (
              <div role="status" className="mt-3.5 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-2.5 text-[12.5px]">
                <p className="m-0 font-semibold text-ink dark:text-ink-dark">
                  Ya hay {borradoresVisibles.length === 1 ? "un borrador" : `${borradoresVisibles.length} borradores`} de esta plantilla:
                </p>
                <ul className="m-0 mt-1.5 p-0 list-none space-y-1.5">
                  {borradoresVisibles.map((d) => (
                    <li key={d.id}>
                      <Link href={`/documentos/${d.id}`} className={`inline-flex items-center gap-1 font-semibold hover:underline ${VIOLETA.texto}`}>
                        Continuar «{d.titulo}»
                        <ArrowRight size={12} aria-hidden="true" />
                      </Link>
                      {d.estudiantes_resumen?.length ? (
                        <span className="block text-[12px] text-ink/50 dark:text-ink-dark/50">{d.estudiantes_resumen.join(", ")}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
                <p className="m-0 mt-1.5 text-[12px] text-ink/45 dark:text-ink-dark/45">Puedes crear otro igual si lo necesitas.</p>
              </div>
            )}

            <TextoError className="mt-3">{errorCrear}</TextoError>
            <Boton type="submit" disabled={!puedeCrear} className="mt-4 w-full">
              {creando ? "Creando..." : "Crear documento"}
            </Boton>
            <p className="m-0 mt-2 text-[12px] text-center text-ink/45 dark:text-ink-dark/45">
              Se crea como borrador: después completas el contenido y generas el PDF.
            </p>
          </TarjetaLateral>
        </div>
      </form>
    </div>
  );
}

// Nombre de la plantilla sin el sufijo " (copia)" que le pone el clonado.
function tituloDesdePlantilla(p: PlantillaDocumento): string {
  return p.nombre.replace(/\s*\(copia\)\s*$/i, "").trim();
}

function FilaResumen({ etiqueta, valor }: { etiqueta: string; valor?: string }) {
  return (
    <div>
      <dt className="text-[12px] font-semibold uppercase tracking-wide text-ink/40 dark:text-ink-dark/40">{etiqueta}</dt>
      <dd className={`m-0 mt-0.5 break-words ${valor ? "font-medium text-ink dark:text-ink-dark" : "italic text-ink/35 dark:text-ink-dark/35"}`}>
        {valor || "Sin elegir"}
      </dd>
    </div>
  );
}
