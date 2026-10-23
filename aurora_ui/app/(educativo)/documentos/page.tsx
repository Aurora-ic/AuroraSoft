"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import type {
  TipoDocumento,
  PlantillaDocumento,
  DocumentoInstitucional,
  PlantillaDocumentoCreate,
  PlantillaDocumentoClonarRequest,
  RespuestaPaginada,
} from "@/types/api";

const TAMANO_PAGINA = 50;

// Landing del motor de documentos institucionales: plantillas predeterminadas
// (catálogo global clonable, ver GET .../plantillas/predeterminadas), las
// plantillas propias de esta institución (el "constructor" — ver
// /documentos/plantillas/[id]) y documentos ya generados (ver
// /documentos/[id]). TipoDocumento es de solo lectura acá (catálogo global,
// solo superadmin lo crea); PlantillaDocumento sí se arma desde esta
// institución, ya sea desde cero o clonando una predeterminada.
export default function DocumentosPage() {
  const { sesion } = useAuth();
  const router = useRouter();

  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([]);
  const [predeterminadas, setPredeterminadas] = useState<PlantillaDocumento[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoInstitucional[]>([]);
  const [totalDocumentos, setTotalDocumentos] = useState(0);
  const [paginaDocumentos, setPaginaDocumentos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tipoNuevaPlantilla, setTipoNuevaPlantilla] = useState("");
  const [creandoPlantilla, setCreandoPlantilla] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);

  const [clonandoId, setClonandoId] = useState<number | null>(null);
  const [errorClonar, setErrorClonar] = useState<string | null>(null);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    setCargando(true);
    // 🆕 Paginación real (docs/gaps-pendientes.md) — antes pedía todo
    // documento generado sin tope; ahora pide de a 50 con skip/limit.
    Promise.all([
      apiClient.get<TipoDocumento[]>("/documentos/tipos?solo_activos=true"),
      apiClient.get<PlantillaDocumento[]>(`/documentos/plantillas?institucion_id=${sesion.institucionId}`),
      apiClient.get<RespuestaPaginada<DocumentoInstitucional>>(
        `/documentos/?institucion_id=${sesion.institucionId}&skip=${paginaDocumentos * TAMANO_PAGINA}&limit=${TAMANO_PAGINA}`,
      ),
      apiClient.get<PlantillaDocumento[]>("/documentos/plantillas/predeterminadas"),
    ])
      .then(([t, p, d, pred]) => {
        setTipos(t);
        setPlantillas(p);
        setDocumentos(d.items);
        setTotalDocumentos(d.total);
        setPredeterminadas(pred);
      })
      .catch((err) => setError(err.message || "No se pudieron cargar los documentos."))
      .finally(() => setCargando(false));
  }, [sesion?.institucionId, paginaDocumentos]);

  async function crearPlantilla() {
    if (!sesion?.institucionId || !tipoNuevaPlantilla) return;
    setCreandoPlantilla(true);
    setErrorPlantilla(null);
    try {
      const tipo = tipos.find((t) => t.id === Number(tipoNuevaPlantilla));
      const payload: PlantillaDocumentoCreate = {
        institucion_id: sesion.institucionId,
        tipo_documento_id: Number(tipoNuevaPlantilla),
        nombre: tipo ? `${tipo.nombre} — nueva plantilla` : "Nueva plantilla",
      };
      const nueva = await apiClient.post<PlantillaDocumento>("/documentos/plantillas", payload);
      router.push(`/documentos/plantillas/${nueva.id}`);
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo crear la plantilla.");
    } finally {
      setCreandoPlantilla(false);
    }
  }

  async function clonarPlantilla(predeterminada: PlantillaDocumento) {
    if (!sesion?.institucionId) return;
    setClonandoId(predeterminada.id);
    setErrorClonar(null);
    try {
      const payload: PlantillaDocumentoClonarRequest = { institucion_destino_id: sesion.institucionId };
      const clon = await apiClient.post<PlantillaDocumento>(`/documentos/plantillas/${predeterminada.id}/clonar`, payload);
      router.push(`/documentos/plantillas/${clon.id}`);
    } catch (err: any) {
      setErrorClonar(err.message || "No se pudo clonar la plantilla.");
    } finally {
      setClonandoId(null);
    }
  }

  function nombreTipo(tipoId: number) {
    return tipos.find((t) => t.id === tipoId)?.nombre ?? `Tipo #${tipoId}`;
  }

  if (cargando) return <div className="p-6 text-sm text-ink/60">Cargando...</div>;

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-8">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="font-display text-2xl text-teal-900">Documentos institucionales</h1>
        <Link href="/documentos/nuevo" className="text-sm font-medium text-teal-700 hover:underline">
          + Nuevo documento
        </Link>
      </div>

      <TextoError>{error}</TextoError>

      {/* Plantillas predeterminadas — catálogo global, mantenido por
          AuroraSoft, para clonar y editar como propia. Nunca se modifican
          por el uso de un colegio. */}
      {predeterminadas.length > 0 && (
        <section className="bg-white rounded-card border border-border p-6 space-y-4">
          <div>
            <h2 className="font-display text-lg text-teal-900 font-semibold border-b border-border pb-2">
              Plantillas predeterminadas
            </h2>
            <p className="text-xs text-ink/50 mt-2">
              Formatos ya armados que podés usar como punto de partida — clonarlos crea una copia propia de tu
              institución, totalmente editable, sin afectar al original.
            </p>
          </div>
          <TextoError>{errorClonar}</TextoError>
          <div className="divide-y divide-border">
            {predeterminadas.map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <span className="text-sm font-medium text-ink">{p.nombre}</span>
                  <span className="block text-xs text-ink/50">{nombreTipo(p.tipo_documento_id)}</span>
                </div>
                <Boton onClick={() => clonarPlantilla(p)} disabled={clonandoId === p.id}>
                  {clonandoId === p.id ? "Clonando..." : "Clonar a mi institución"}
                </Boton>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Plantillas — el constructor */}
      <section className="bg-white rounded-card border border-border p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <h2 className="font-display text-lg text-teal-900 font-semibold">Plantillas</h2>
        </div>

        <div className="flex items-end gap-3 flex-wrap">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 font-medium">Nueva plantilla a partir de un tipo de documento</span>
            <Select value={tipoNuevaPlantilla} onChange={(e) => setTipoNuevaPlantilla(e.target.value)}>
              <option value="">Elige un tipo...</option>
              {tipos.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nombre}
                </option>
              ))}
            </Select>
          </label>
          <Boton onClick={crearPlantilla} disabled={!tipoNuevaPlantilla || creandoPlantilla}>
            {creandoPlantilla ? "Creando..." : "Crear y abrir el constructor"}
          </Boton>
        </div>
        <TextoError>{errorPlantilla}</TextoError>
        {tipos.length === 0 && (
          <p className="text-xs text-ink/50 italic">
            Todavía no hay ningún tipo de documento en el catálogo (lo arma superadmin).
          </p>
        )}

        {plantillas.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">Tu institución todavía no tiene ninguna plantilla.</p>
        ) : (
          <div className="divide-y divide-border">
            {plantillas.map((p) => (
              <Link
                key={p.id}
                href={`/documentos/plantillas/${p.id}`}
                className="flex items-center justify-between gap-3 py-2 hover:bg-mist/40 -mx-2 px-2 rounded-card transition-colors"
              >
                <div>
                  <span className="text-sm font-medium text-ink">{p.nombre}</span>
                  <span className="block text-xs text-ink/50">{nombreTipo(p.tipo_documento_id)}</span>
                </div>
                <span className={`text-xs ${p.activa ? "text-teal-700" : "text-ink/40"}`}>
                  {p.activa ? "Activa" : "Inactiva"}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Documentos ya generados */}
      <section className="bg-white rounded-card border border-border p-6 space-y-4">
        <h2 className="font-display text-lg text-teal-900 font-semibold border-b border-border pb-2">
          Documentos generados
        </h2>
        {documentos.length === 0 ? (
          <p className="text-sm text-ink/60 italic py-2">Todavía no se generó ningún documento.</p>
        ) : (
          <div className="divide-y divide-border">
            {documentos
              .slice()
              .sort((a, b) => b.id - a.id)
              .map((d) => (
                <Link
                  key={d.id}
                  href={`/documentos/${d.id}`}
                  className="flex items-center justify-between gap-3 py-2 hover:bg-mist/40 -mx-2 px-2 rounded-card transition-colors"
                >
                  <span className="text-sm font-medium text-ink">{d.titulo}</span>
                  <span className="text-xs text-ink/50">
                    {d.version_actual === null ? "Sin versión generada" : `v${d.version_actual}`}
                  </span>
                </Link>
              ))}
          </div>
        )}

        {totalDocumentos > 0 && (
          <div className="flex items-center justify-between pt-2">
            <p className="text-xs text-ink/50">
              {paginaDocumentos * TAMANO_PAGINA + 1}–{Math.min((paginaDocumentos + 1) * TAMANO_PAGINA, totalDocumentos)} de{" "}
              {totalDocumentos} documentos
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPaginaDocumentos((p) => Math.max(0, p - 1))}
                disabled={paginaDocumentos === 0}
                className="rounded-card border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-mist disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Anterior
              </button>
              <button
                onClick={() => setPaginaDocumentos((p) => p + 1)}
                disabled={(paginaDocumentos + 1) * TAMANO_PAGINA >= totalDocumentos}
                className="rounded-card border border-border bg-white px-3 py-1.5 text-xs font-medium text-ink hover:bg-mist disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Siguiente
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
