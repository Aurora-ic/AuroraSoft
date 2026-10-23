"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
export default function NuevoDocumentoPage() {
  const { sesion } = useAuth();
  const router = useRouter();

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
        setPlantillas(p.filter((x) => x.activa));
        setTipos(t);
        setPersonas(personasResp);
        setNiveles(nivelesResp);
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

  if (cargando) return <div className="p-6 text-sm text-ink/60">Cargando...</div>;

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <Link href="/documentos" className="text-xs text-ink/50 hover:underline">
          ← Documentos
        </Link>
        <h1 className="font-display text-2xl text-teal-900 mt-1">Nuevo documento</h1>
      </div>

      <TextoError>{error}</TextoError>

      <form onSubmit={crearDocumento} className="bg-white rounded-card border border-border p-6 space-y-5">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Plantilla</span>
          <Select required value={plantillaId} onChange={(e) => setPlantillaId(e.target.value)}>
            <option value="">Elige una plantilla...</option>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </Select>
          {plantillas.length === 0 && (
            <span className="text-xs text-ink/50 italic">
              Tu institución todavía no tiene ninguna plantilla activa — primero armá una en /documentos.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 font-medium">Título</span>
          <Input required value={titulo} onChange={(e) => setTitulo(e.target.value)} placeholder="Ej. Informe Psicológico" />
        </label>

        <div className="space-y-2">
          <span className="text-sm text-ink/70 font-medium">¿A quién va?</span>
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
          <div className="space-y-2">
            <Input
              placeholder="Buscar por nombre o apellido..."
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
            />
            <div className="max-h-56 overflow-y-auto border border-border rounded-card divide-y divide-border">
              {personas
                .filter((p) => {
                  const q = busqueda.trim().toLowerCase();
                  if (!q) return true;
                  return `${p.nombres} ${p.apellidos}`.toLowerCase().includes(q);
                })
                .slice(0, 80)
                .map((p) => (
                  <label key={p.id} className="flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-mist/40 cursor-pointer">
                    <input type="checkbox" checked={seleccionadas.has(p.id)} onChange={() => alternarPersona(p.id)} />
                    {p.nombres} {p.apellidos}
                  </label>
                ))}
              {personas.length === 0 && (
                <p className="text-xs text-ink/50 italic px-3 py-2">No hay alumnos en el padrón de tu institución.</p>
              )}
            </div>
            {seleccionadas.size > 0 && (
              <p className="text-xs text-ink/60">{seleccionadas.size} alumno(s) seleccionado(s).</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid sm:grid-cols-3 gap-3">
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-ink/70 font-medium">Nivel</span>
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
                <span className="text-ink/70 font-medium">Grado</span>
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
                <span className="text-ink/70 font-medium">Sección</span>
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
            <p className="text-xs text-ink/50 italic">
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
