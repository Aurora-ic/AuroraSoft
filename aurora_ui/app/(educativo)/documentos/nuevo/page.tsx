"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import type {
  TipoDocumento,
  PlantillaDocumento,
  DocumentoInstitucional,
  DocumentoInstitucionalCreate,
  Persona,
  NivelEducativo,
  Grado,
  Seccion,
} from "@/types/api";

type Alcance = "personas" | "estructura";
type Granularidad = "seccion" | "grado" | "nivel";

// Crear un DocumentoInstitucional: elegir plantilla, a quién va (uno o
// varios alumnos del padrón, o un salón/grado/nivel completo) y el
// título. El contenido se llena después, en /documentos/[id].
//
// 🆕 Atajos por query string, ambos opcionales y combinables:
// - ?plantilla_id=X — viene del botón "Generar documento" de una tarjeta
//   de /documentos (tab "Mis plantillas"): precarga esa plantilla.
// - ?persona_id=X — viene del botón "+ Nuevo documento" de la ficha de un
//   alumno (/estudiantes/[personaId]): precarga el alcance "uno o varios
//   alumnos" con ESE alumno ya marcado, para no tener que volver a
//   buscarlo. Se muestra como un dato fijo con un botón "Elegir otro
//   alumno" para no perder la posibilidad de agregar/cambiar sin recargar.
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
  const [alcance, setAlcance] = useState<Alcance>("personas");

  // --- Alcance: alumno(s) ---
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  // true cuando llegamos con ?persona_id= y todavía no se tocó "Elegir otro
  // alumno" — muestra el alumno como dato fijo en vez del buscador/checklist.
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

  useEffect(() => {
    if (!sesion?.institucionId) return;
    Promise.all([
      apiClient.get<PlantillaDocumento[]>(`/documentos/plantillas?institucion_id=${sesion.institucionId}`),
      apiClient.get<TipoDocumento[]>("/documentos/tipos?solo_activos=true"),
      // 🆕 Paginación real: este selector necesita el padrón COMPLETO (el
      // usuario busca/elige entre todos), no una página de 50.
      apiClient.getTodasLasPaginas<Persona>(`/admin/personas/${sesion.institucionId}`),
      apiClient.get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`),
    ])
      .then(([p, t, personasResp, nivelesResp]) => {
        const plantillasActivas = p.filter((x) => x.activa);
        setPlantillas(plantillasActivas);
        setTipos(t);
        setPersonas(personasResp);
        setNiveles(nivelesResp);

        // Precarga por query string — ver docstring del componente.
        if (plantillaIdParam && plantillasActivas.some((x) => x.id === Number(plantillaIdParam))) {
          setPlantillaId(plantillaIdParam);
        }
        if (personaIdParam && personasResp.some((x) => x.id === Number(personaIdParam))) {
          setAlcance("personas");
          setSeleccionadas(new Set([Number(personaIdParam)]));
          setAlumnoFijado(true);
        }
      })
      .catch((err) => setError(err.message || "No se pudo cargar la información necesaria."))
      .finally(() => setCargando(false));
  }, [sesion?.institucionId]);

  useEffect(() => {
    if (!nivelId) {
      setGrados([]);
      setGradoId("");
      return;
    }
    apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelId}`).then(setGrados).catch(() => setGrados([]));
  }, [nivelId]);

  useEffect(() => {
    if (!gradoId) {
      setSecciones([]);
      setSeccionId("");
      return;
    }
    apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoId}`).then(setSecciones).catch(() => setSecciones([]));
  }, [gradoId]);

  function alternarPersona(id: number) {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (copia.has(id)) copia.delete(id);
      else copia.add(id);
      return copia;
    });
  }

  const plantillaElegida = plantillas.find((p) => p.id === Number(plantillaId));
  const tipoElegido = plantillaElegida ? tipos.find((t) => t.id === plantillaElegida.tipo_documento_id) : undefined;

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
        const seccionElegida = secciones.find((s) => s.id === Number(seccionId));
        if (seccionElegida) payload.anio_escolar = seccionElegida.anio_escolar;
      }
      const nuevo = await apiClient.post<DocumentoInstitucional>("/documentos/", payload);
      router.push(`/documentos/${nuevo.id}`);
    } catch (err: any) {
      setErrorCrear(err.message || "No se pudo crear el documento.");
    } finally {
      setCreando(false);
    }
  }

  if (cargando) return <div className="text-sm text-ink/60 dark:text-ink-dark/60">Cargando...</div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <Link href="/documentos" className="text-xs text-ink/50 dark:text-ink-dark/50 hover:underline">
          ← Documentos
        </Link>
        <h1 className="font-display text-2xl text-teal-900 dark:text-teal-accent-dark mt-1">Nuevo documento</h1>
      </div>

      <TextoError>{error}</TextoError>

      <form onSubmit={crearDocumento} className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-5">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Plantilla</span>
          <Select required value={plantillaId} onChange={(e) => setPlantillaId(e.target.value)}>
            <option value="">Elige una plantilla...</option>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </Select>
          {plantillas.length === 0 && (
            <span className="text-xs text-ink/50 dark:text-ink-dark/50 italic">
              Tu institución todavía no tiene ninguna plantilla activa — primero armá una en /documentos.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Título</span>
          {/* 🆕 El backend exige mínimo 2 caracteres (DocumentoInstitucionalCreate.
              titulo, Field(min_length=2)) -- minLength acá da el mismo aviso
              ANTES de pegarle a la red, en vez de un 422 silencioso. */}
          <Input
            required
            minLength={2}
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ej. Informe Psicológico"
          />
          <span className="text-xs text-ink/45 dark:text-ink-dark/45">Al menos 2 caracteres.</span>
        </label>

        <div className="space-y-2">
          <span className="text-sm text-ink/70 dark:text-ink-dark/70 font-medium">¿A quién va?</span>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" checked={alcance === "personas"} onChange={() => setAlcance("personas")} />
              Uno o varios alumnos
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" checked={alcance === "estructura"} onChange={() => setAlcance("estructura")} />
              Un salón, grado o nivel completo
            </label>
          </div>
        </div>

        {alcance === "personas" ? (
          alumnoFijado ? (
            // Vino con ?persona_id= desde la ficha del alumno — se muestra
            // fijo en vez del buscador, para no tener que volver a
            // encontrarlo. "Elegir otro alumno" vuelve al buscador normal
            // (sin perder la plantilla ya elegida).
            <div className="flex items-center justify-between gap-3 bg-mist dark:bg-surface-dark border border-border dark:border-border-dark rounded-card px-3 py-2">
              <span className="text-sm text-ink dark:text-ink-dark">
                Documento para:{" "}
                <strong className="font-medium">
                  {(() => {
                    const p = personas.find((x) => seleccionadas.has(x.id));
                    return p ? `${p.nombres} ${p.apellidos}` : `alumno #${Array.from(seleccionadas)[0]}`;
                  })()}
                </strong>
              </span>
              <button
                type="button"
                onClick={() => setAlumnoFijado(false)}
                className="text-xs font-medium text-teal-700 dark:text-teal-accent-dark hover:underline whitespace-nowrap"
              >
                Elegir otro alumno
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <Input
                placeholder="Buscar por nombre o apellido..."
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />
              <div className="max-h-56 overflow-y-auto border border-border dark:border-border-dark rounded-card divide-y divide-border dark:divide-border-dark">
                {personas
                  .filter((p) => {
                    const q = busqueda.trim().toLowerCase();
                    if (!q) return true;
                    return `${p.nombres} ${p.apellidos}`.toLowerCase().includes(q);
                  })
                  .slice(0, 80)
                  .map((p) => (
                    <label key={p.id} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-mist/40 dark:hover:bg-surface-raised-dark dark:bg-surface-dark/40 cursor-pointer">
                      <input type="checkbox" checked={seleccionadas.has(p.id)} onChange={() => alternarPersona(p.id)} />
                      {p.nombres} {p.apellidos}
                    </label>
                  ))}
                {personas.length === 0 && (
                  <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic px-3 py-2">No hay alumnos en el padrón de tu institución.</p>
                )}
              </div>
              {seleccionadas.size > 0 && (
                <p className="text-xs text-ink/60 dark:text-ink-dark/60">{seleccionadas.size} alumno(s) seleccionado(s).</p>
              )}
            </div>
          )
        ) : (
          <div className="space-y-3">
            <div className="grid sm:grid-cols-3 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Nivel</span>
                <Select value={nivelId} onChange={(e) => { setNivelId(e.target.value); setGranularidad("nivel"); }}>
                  <option value="">Elige...</option>
                  {niveles.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.nombre}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Grado</span>
                <Select value={gradoId} onChange={(e) => { setGradoId(e.target.value); setGranularidad("grado"); }} disabled={!nivelId}>
                  <option value="">Todo el nivel</option>
                  {grados.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.nombre}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Sección</span>
                <Select value={seccionId} onChange={(e) => { setSeccionId(e.target.value); setGranularidad("seccion"); }} disabled={!gradoId}>
                  <option value="">Todo el grado</option>
                  {secciones.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nombre} {s.anio_escolar}
                    </option>
                  ))}
                </Select>
              </label>
            </div>
            <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">
              Se aplica al nivel más específico que elijas: una sección puntual, o todo el grado/nivel si dejás la sección/grado en blanco.
            </p>
          </div>
        )}

        <TextoError>{errorCrear}</TextoError>
        <Boton
          type="submit"
          disabled={
            creando ||
            !plantillaId ||
            !titulo ||
            (alcance === "personas" ? seleccionadas.size === 0 : !nivelId)
          }
        >
          {creando ? "Creando..." : "Crear documento"}
        </Boton>
      </form>
    </div>
  );
}
