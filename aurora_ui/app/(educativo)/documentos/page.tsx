"use client";

import { useConfirmar } from "@/components/ui/DialogoConfirmacion";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FolderOpen,
  LayoutTemplate,
  Library,
  FileText,
  FilePen,
  FileCheck2,
  Copy,
  Pencil,
  Power,
  Trash2,
  Zap,
  CopyCheck,
  Users,
  Search,
  Plus,
  ArrowRight,
  CheckCircle2,
  type LucideIcon,
} from "lucide-react";
import { EncabezadoPagina, claseBotonBanner, ControlSegmentado, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { BloqueFicha, VacioFicha } from "@/components/educativo/BloqueFicha";
import { apiClient } from "@/lib/api-client";
import { ACENTOS } from "@/lib/acentos";
import { useAuth } from "@/contexts/AuthContext";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Select } from "@/components/ui/Select";
import { EsqueletoLista } from "@/components/ui/Esqueleto";
import type {
  TipoDocumento,
  PlantillaDocumento,
  DocumentoInstitucional,
  PlantillaDocumentoCreate,
  PlantillaDocumentoClonarRequest,
  RespuestaPaginada,
} from "@/types/api";

const TAMANO_PAGINA = 50;
const VIOLETA = ACENTOS.violeta;

type Tab = "plantillas" | "catalogo" | "generados";
type FiltroEstado = "todos" | "borradores" | "emitidos";

// Landing del motor de documentos institucionales: 3 pestañas que reflejan
// el único flujo real del motor (ver docs/motor-documentos.md):
//
//   1. Mis plantillas (propias de esta institución, clonadas o armadas desde
//      cero) — acá se edita estructura/tipografía, y desde acá se dispara
//      "Generar documento".
//   2. Catálogo (predeterminadas, global, de solo lectura) — se CLONA, nunca
//      se usa directo para generar un documento.
//   3. Documentos generados (instancias reales, cada una atada a uno o
//      varios alumnos o a una estructura académica).
//
// 🆕 Rediseño (sesión 2026-11-01, a pedido del usuario: "lo más cómodo, lo
// menos saturado, siguiendo el color de la sección"): las pestañas son
// tarjetas violeta (Documentos) con su conteo y una línea de qué contienen
// — reemplazan a la vez la barra de pestañas y la tira "cómo funciona", que
// decían lo mismo dos veces. Cada pestaña es un BloqueFicha violeta, con las
// tarjetas/filas en blanco encima. Se conservan a propósito los textos que
// usa e2e/documentos.spec.ts ("+ Nueva desde cero", la etiqueta del select
// de tipo, "Crear y abrir el constructor").
export default function DocumentosPage() {
  // 🆕 Diálogo de confirmación propio (reemplaza window.confirm).
  const confirmar = useConfirmar();
  const { sesion } = useAuth();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("plantillas");

  const [tipos, setTipos] = useState<TipoDocumento[]>([]);
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([]);
  const [predeterminadas, setPredeterminadas] = useState<PlantillaDocumento[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoInstitucional[]>([]);
  const [totalDocumentos, setTotalDocumentos] = useState(0);
  const [paginaDocumentos, setPaginaDocumentos] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [searchPlantillas, setSearchPlantillas] = useState("");
  const [searchCatalogo, setSearchCatalogo] = useState("");
  const [searchDocumentos, setSearchDocumentos] = useState("");
  // 🆕 Escalabilidad (sesión 2026-11-01): búsqueda y estado se aplican en el
  // SERVIDOR (antes solo sobre la página de 50 ya cargada). El texto se
  // manda 300 ms después de dejar de escribir, no en cada tecla.
  const [busquedaAplicada, setBusquedaAplicada] = useState("");
  const [filtroEstado, setFiltroEstado] = useState<FiltroEstado>("todos");
  const [cargandoDocumentos, setCargandoDocumentos] = useState(false);
  // Total SIN filtros, para la tarjeta de la pestaña (con un filtro puesto,
  // `totalDocumentos` es el total filtrado).
  const [totalSinFiltro, setTotalSinFiltro] = useState(0);

  const [tipoNuevaPlantilla, setTipoNuevaPlantilla] = useState("");
  const [crearDesdeCeroAbierto, setCrearDesdeCeroAbierto] = useState(false);
  const [creandoPlantilla, setCreandoPlantilla] = useState(false);
  const [errorPlantilla, setErrorPlantilla] = useState<string | null>(null);

  const [clonandoId, setClonandoId] = useState<number | null>(null);
  const [errorClonar, setErrorClonar] = useState<string | null>(null);

  const [descartandoId, setDescartandoId] = useState<number | null>(null);
  const [errorDocumentos, setErrorDocumentos] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);

  const [activandoId, setActivandoId] = useState<number | null>(null);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);

  // Catálogo y plantillas: una vez (y tras clonar/eliminar, vía recarga).
  // 🆕 `cantidad_secciones` ya viene en el listado de plantillas (antes una
  // consulta extra por plantilla solo para contarlas).
  useEffect(() => {
    if (!sesion?.institucionId) return;
    Promise.all([
      apiClient.get<TipoDocumento[]>("/documentos/tipos?solo_activos=true"),
      apiClient.get<PlantillaDocumento[]>(`/documentos/plantillas?institucion_id=${sesion.institucionId}`),
      apiClient.get<PlantillaDocumento[]>("/documentos/plantillas/predeterminadas"),
    ])
      .then(([t, p, pred]) => {
        setTipos(t);
        setPlantillas(p);
        setPredeterminadas(pred);
      })
      .catch((err) => setError(err.message || "No se pudieron cargar los documentos."))
      .finally(() => setCargando(false));
  }, [sesion?.institucionId]);

  useEffect(() => {
    const t = setTimeout(() => setBusquedaAplicada(searchDocumentos.trim()), 300);
    return () => clearTimeout(t);
  }, [searchDocumentos]);

  // Documentos: paginados y filtrados en el servidor (docs/gaps-pendientes.md).
  useEffect(() => {
    if (!sesion?.institucionId) return;
    let vigente = true;
    const params = new URLSearchParams({
      institucion_id: String(sesion.institucionId),
      skip: String(paginaDocumentos * TAMANO_PAGINA),
      limit: String(TAMANO_PAGINA),
    });
    if (busquedaAplicada) params.set("q", busquedaAplicada);
    if (filtroEstado !== "todos") params.set("estado", filtroEstado === "borradores" ? "borrador" : "emitido");
    const sinFiltro = !busquedaAplicada && filtroEstado === "todos";
    setCargandoDocumentos(true);
    apiClient
      .get<RespuestaPaginada<DocumentoInstitucional>>(`/documentos/?${params.toString()}`)
      .then((d) => {
        if (!vigente) return;
        setDocumentos(d.items);
        setTotalDocumentos(d.total);
        if (sinFiltro) setTotalSinFiltro(d.total);
      })
      .catch((err) => vigente && setErrorDocumentos(err.message || "No se pudieron cargar los documentos."))
      .finally(() => vigente && setCargandoDocumentos(false));
    return () => {
      vigente = false;
    };
  }, [sesion?.institucionId, paginaDocumentos, recarga, busquedaAplicada, filtroEstado]);

  // Cambiar un filtro vuelve a la página 1 (en el handler, no en un efecto).
  function cambiarBusquedaDocumentos(v: string) {
    setSearchDocumentos(v);
    setPaginaDocumentos(0);
  }
  function cambiarFiltroEstado(v: FiltroEstado) {
    setFiltroEstado(v);
    setPaginaDocumentos(0);
  }

  // 🆕 (sesión 2026-11-01) Eliminar una plantilla propia (p. ej. un
  // duplicado clonado por accidente). Soft-delete en el backend: los
  // documentos ya emitidos con ella no cambian; responde 409 si todavía
  // tiene borradores en curso (ver crud.eliminar_plantilla_documento).
  async function eliminarPlantilla(p: PlantillaDocumento) {
    if (
      !(await confirmar({
        titulo: `¿Eliminar la plantilla «${p.nombre}»?`,
        mensaje: "Los documentos ya emitidos con ella no cambian.",
        textoConfirmar: "Eliminar plantilla",
        peligro: true,
      }))
    )
      return;
    setEliminandoId(p.id);
    setErrorPlantilla(null);
    try {
      await apiClient.delete(`/documentos/plantillas/${p.id}`);
      setPlantillas((prev) => prev.filter((x) => x.id !== p.id));
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo eliminar la plantilla.");
    } finally {
      setEliminandoId(null);
    }
  }

  async function activarPlantilla(p: PlantillaDocumento) {
    setActivandoId(p.id);
    setErrorPlantilla(null);
    try {
      const actualizada = await apiClient.patch<PlantillaDocumento>(`/documentos/plantillas/${p.id}`, { activa: true });
      // 🆕 (sesión 2026-11-01) Sin exclusividad por tipo: activar esta no
      // apaga ninguna otra, solo cambia ella.
      setPlantillas((prev) => prev.map((x) => (x.id === actualizada.id ? actualizada : x)));
    } catch (err: any) {
      setErrorPlantilla(err.message || "No se pudo activar la plantilla.");
    } finally {
      setActivandoId(null);
    }
  }

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
        // Nace INACTIVA a propósito: todavía no tiene ninguna sección y una
        // activa vacía generaría documentos en blanco. Se activa desde el
        // constructor una vez que de verdad tiene contenido.
        activa: false,
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
      // 🆕 (sesión 2026-11-01) Nace ACTIVA: una predeterminada ya trae todas
      // sus secciones y, sin exclusividad por tipo, no apaga ninguna otra.
      const payload: PlantillaDocumentoClonarRequest = { institucion_destino_id: sesion.institucionId, activar: true };
      const clon = await apiClient.post<PlantillaDocumento>(`/documentos/plantillas/${predeterminada.id}/clonar`, payload);
      router.push(`/documentos/plantillas/${clon.id}`);
    } catch (err: any) {
      setErrorClonar(err.message || "No se pudo clonar la plantilla.");
    } finally {
      setClonandoId(null);
    }
  }

  // 🆕 (sesión 2026-11-01) Descartar un BORRADOR (nunca emitido). El
  // backend lo rechaza con 409 si ya tiene versión; es soft-delete, la
  // auditoría de lecturas del borrador se conserva.
  async function descartarBorrador(d: DocumentoInstitucional) {
    const quien = d.estudiantes_resumen?.length ? ` de ${d.estudiantes_resumen.join(", ")}` : "";
    if (
      !(await confirmar({
        titulo: `¿Descartar el borrador «${d.titulo}»${quien}?`,
        mensaje: "Se pierde lo que se haya escrito en él. Esta acción no se puede deshacer.",
        textoConfirmar: "Descartar borrador",
        peligro: true,
      }))
    )
      return;
    setDescartandoId(d.id);
    setErrorDocumentos(null);
    try {
      await apiClient.delete(`/documentos/${d.id}`);
      // Si era el último de la página, retrocede una para no quedar en blanco.
      if (documentos.length === 1 && paginaDocumentos > 0) setPaginaDocumentos((p) => p - 1);
      else setRecarga((n) => n + 1);
    } catch (err: any) {
      setErrorDocumentos(err.message || "No se pudo descartar el borrador.");
    } finally {
      setDescartandoId(null);
    }
  }

  function nombreTipo(tipoId: number) {
    return tipos.find((t) => t.id === tipoId)?.nombre ?? `Tipo #${tipoId}`;
  }

  const plantillasFiltradas = useMemo(() => {
    const q = searchPlantillas.trim().toLowerCase();
    const lista = q
      ? plantillas.filter((p) => p.nombre.toLowerCase().includes(q) || nombreTipo(p.tipo_documento_id).toLowerCase().includes(q))
      : plantillas;
    // Agrupadas por tipo y, dentro de cada tipo, las activas primero.
    return lista.slice().sort((a, b) => {
      const ta = nombreTipo(a.tipo_documento_id);
      const tb = nombreTipo(b.tipo_documento_id);
      if (ta !== tb) return ta.localeCompare(tb, "es");
      if (a.activa !== b.activa) return a.activa ? -1 : 1;
      return a.nombre.localeCompare(b.nombre, "es");
    });
  }, [plantillas, searchPlantillas, tipos]);

  // Predeterminadas agrupadas por tipo, todas visibles (antes era un
  // acordeón con un solo grupo abierto: había que adivinar dónde estaba
  // cada formato). Buscando, solo quedan los grupos con resultado.
  const gruposCatalogo = useMemo(() => {
    const q = searchCatalogo.trim().toLowerCase();
    return tipos
      .map((t) => ({
        tipo: t,
        items: predeterminadas.filter(
          (pr) => pr.tipo_documento_id === t.id && (!q || pr.nombre.toLowerCase().includes(q) || t.nombre.toLowerCase().includes(q)),
        ),
      }))
      .filter((g) => g.items.length > 0);
  }, [tipos, predeterminadas, searchCatalogo]);

  // Una predeterminada ya clonada antes. 🆕 (sesión 2026-11-01) Primero por
  // `plantilla_origen_id` (exacto, sobrevive a un renombre); el nombre
  // "<nombre> (copia)" queda solo como respaldo para clones antiguos sin
  // origen registrado. Nunca bloquea clonar.
  const nombresPropios = useMemo(() => new Set(plantillas.map((p) => p.nombre)), [plantillas]);
  const origenesPropios = useMemo(
    () => new Set(plantillas.map((p) => p.plantilla_origen_id).filter((x): x is number => typeof x === "number")),
    [plantillas],
  );

  // 🆕 (sesión 2026-11-01) Posibles duplicados: dos plantillas propias
  // clonadas del MISMO formato (`plantilla_origen_id`), o del mismo tipo
  // cuyo nombre coincide al quitar "(copia)"/"(predeterminado)" y espacios
  // (cubre clones antiguos sin origen y uno renombrado frente a su copia).
  // Solo es una marca para revisar; nunca borra nada sola.
  const duplicadas = useMemo(() => {
    const grupos = new Map<string, number[]>();
    const agregar = (clave: string, id: number) => grupos.set(clave, [...(grupos.get(clave) ?? []), id]);
    for (const p of plantillas) {
      agregar(`nombre|${p.tipo_documento_id}|${clavePlantilla(p.nombre)}`, p.id);
      if (typeof p.plantilla_origen_id === "number") agregar(`origen|${p.plantilla_origen_id}`, p.id);
    }
    return new Set(Array.from(grupos.values()).filter((ids) => ids.length > 1).flat());
  }, [plantillas]);
  function yaClonada(pr: PlantillaDocumento) {
    return origenesPropios.has(pr.id) || nombresPropios.has(pr.nombre) || nombresPropios.has(`${pr.nombre} (copia)`);
  }

  // El servidor ya devuelve la página filtrada.
  const documentosFiltrados = documentos;
  const hayFiltroDocumentos = !!busquedaAplicada || filtroEstado !== "todos";

  const borradoresEnPagina = documentos.filter((d) => d.version_actual === null).length;

  const encabezado = (
    <EncabezadoPagina
      variante="destacado"
      icono={FolderOpen}
      acento="violeta"
      titulo="Documentos institucionales"
      descripcion="Clona un formato del catálogo, ajústalo en tus plantillas y genéralo para un alumno o un grupo."
      acciones={
        <Link href="/documentos/nuevo" className={claseBotonBanner("primario")}>
          <Plus size={15} aria-hidden="true" />
          Nuevo documento
        </Link>
      }
    />
  );

  if (cargando && plantillas.length === 0 && documentos.length === 0) {
    return (
      <div className={CLASE_CONTENEDOR_SECCION}>
        {encabezado}
        <EsqueletoLista cantidad={5} />
      </div>
    );
  }

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      {encabezado}

      <TextoError>{error}</TextoError>

      <div role="tablist" aria-label="Apartados de documentos" className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <TarjetaPestana
          activa={tab === "plantillas"}
          onClick={() => setTab("plantillas")}
          icono={LayoutTemplate}
          titulo="Mis plantillas"
          valor={plantillas.length}
          descripcion="Tus formatos editables; desde aquí se genera."
        />
        <TarjetaPestana
          activa={tab === "catalogo"}
          onClick={() => setTab("catalogo")}
          icono={Library}
          titulo="Catálogo para clonar"
          valor={predeterminadas.length}
          descripcion="Formatos listos de AuroraSoft."
        />
        <TarjetaPestana
          activa={tab === "generados"}
          onClick={() => setTab("generados")}
          icono={FileText}
          titulo="Documentos generados"
          valor={totalSinFiltro}
          descripcion={borradoresEnPagina > 0 ? `${borradoresEnPagina} en borrador` : "Borradores y emitidos por alumno."}
        />
      </div>

      {/* ===== Mis plantillas ===== */}
      {tab === "plantillas" && (
        <BloqueFicha
          acento="violeta"
          icono={LayoutTemplate}
          titulo="Mis plantillas"
          descripcion="Las plantillas activas son las que aparecen al crear un documento."
          acciones={
            <>
              <CampoBusqueda valor={searchPlantillas} onCambiar={setSearchPlantillas} placeholder="Buscar plantilla..." />
              <Boton variante="secundario" onClick={() => setCrearDesdeCeroAbierto((v) => !v)} className="!py-1.5">
                + Nueva desde cero
              </Boton>
            </>
          }
          cuerpoClassName="space-y-3"
        >
          {crearDesdeCeroAbierto && (
            <div className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-3.5 flex items-end gap-3 flex-wrap">
              <label className="flex flex-col gap-1 text-sm flex-1 min-w-[220px]">
                <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Nueva plantilla a partir de un tipo de documento</span>
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
              <p className="basis-full m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">
                ¿Prefieres partir de un formato ya armado? Usa el{" "}
                <button type="button" onClick={() => setTab("catalogo")} className={`font-semibold hover:underline ${VIOLETA.texto}`}>
                  catálogo para clonar
                </button>
                .
              </p>
            </div>
          )}
          <TextoError>{errorPlantilla}</TextoError>
          {tipos.length === 0 && (
            <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">
              Todavía no hay ningún tipo de documento en el catálogo (lo arma superadmin).
            </p>
          )}

          {plantillasFiltradas.length === 0 ? (
            plantillas.length === 0 ? (
              <VacioFicha icono={LayoutTemplate} texto="Tu institución todavía no tiene ninguna plantilla.">
                <button type="button" onClick={() => setTab("catalogo")} className={`mt-2 text-sm font-semibold hover:underline ${VIOLETA.texto}`}>
                  Clonar una del catálogo →
                </button>
              </VacioFicha>
            ) : (
              <VacioFicha icono={Search} texto="Ninguna plantilla coincide con la búsqueda." />
            )
          ) : (
            <div className="grid sm:grid-cols-2 gap-3">
              {plantillasFiltradas.map((p) => {
                const n = p.cantidad_secciones ?? undefined;
                return (
                  <article
                    key={p.id}
                    className={`rounded-xl border bg-surface dark:bg-surface-dark p-4 flex flex-col gap-2.5 ${
                      p.activa ? `border-acento-violeta/35 dark:border-acento-violeta-dark/35 border-l-4 ${VIOLETA.borde}` : "border-border dark:border-border-dark"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${VIOLETA.chip}`}>
                        <FileText size={17} aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="m-0 text-sm font-semibold text-ink dark:text-ink-dark leading-snug">{p.nombre}</h3>
                        <p className="m-0 mt-0.5 text-[12px] text-ink/50 dark:text-ink-dark/50">{nombreTipo(p.tipo_documento_id)}</p>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <PildoraEstado activa={p.activa} />
                        {duplicadas.has(p.id) && (
                          <span
                            className="inline-flex items-center gap-1 rounded-full border border-dashed border-ink/30 dark:border-ink-dark/30 px-2 py-0.5 text-[11.5px] font-semibold text-ink/60 dark:text-ink-dark/60"
                            title="Hay otra plantilla tuya del mismo tipo con el mismo nombre. Si la clonaste dos veces por accidente, elimina la que sobre."
                          >
                            <CopyCheck size={10} aria-hidden="true" />
                            Repetida
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-[12px] text-ink/50 dark:text-ink-dark/50">
                      {n !== undefined && n >= 0 && (
                        <span className={n === 0 ? "text-red-700 dark:text-red-300 font-medium" : ""}>
                          {n} {n === 1 ? "sección" : "secciones"}
                        </span>
                      )}
                      <span>Creada el {fechaCorta(p.creado_en)}</span>
                      {p.generar_automaticamente_al_finalizar_examen && (
                        <span className={`inline-flex items-center gap-1 font-medium ${VIOLETA.texto}`} title="Se genera sola al finalizar un examen">
                          <Zap size={11} aria-hidden="true" />
                          Automática
                        </span>
                      )}
                    </div>

                    {/* Activa + sin secciones = generaría un documento vacío. */}
                    {p.activa && n === 0 && (
                      <p className="m-0 text-[12px] text-red-700 dark:text-red-300 font-medium">
                        Sin secciones: no generará contenido. Agrégalas en Editar.
                      </p>
                    )}

                    <div className="flex gap-2 mt-auto pt-1">
                      <Link href={`/documentos/plantillas/${p.id}`} className={claseBoton("secundario", "flex-1 inline-flex items-center justify-center gap-1.5 !py-1.5")}>
                        <Pencil size={13} aria-hidden="true" />
                        Editar
                      </Link>
                      {p.activa ? (
                        <Link
                          href={`/documentos/nuevo?plantilla_id=${p.id}`}
                          className={claseBoton("primario", "flex-1 inline-flex items-center justify-center gap-1.5 !py-1.5")}
                        >
                          <Plus size={14} aria-hidden="true" />
                          Generar documento
                        </Link>
                      ) : (
                        // "Generar documento" solo funciona con una plantilla
                        // activa (documentos/nuevo solo lista las activas).
                        <Boton
                          variante="primario"
                          className="flex-1 inline-flex items-center justify-center gap-1.5 !py-1.5"
                          onClick={() => activarPlantilla(p)}
                          disabled={activandoId === p.id}
                        >
                          <Power size={13} aria-hidden="true" />
                          {activandoId === p.id ? "Activando..." : "Activar"}
                        </Boton>
                      )}
                      <button
                        type="button"
                        onClick={() => eliminarPlantilla(p)}
                        disabled={eliminandoId === p.id}
                        title="Eliminar plantilla"
                        aria-label={`Eliminar plantilla ${p.nombre}`}
                        className="shrink-0 rounded-lg border border-border dark:border-border-dark px-2.5 text-ink/45 hover:text-red-700 hover:border-red-300 hover:bg-red-50 dark:text-ink-dark/45 dark:hover:text-red-300 dark:hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </BloqueFicha>
      )}

      {/* ===== Catálogo ===== */}
      {tab === "catalogo" && (
        <BloqueFicha
          acento="violeta"
          icono={Library}
          titulo="Catálogo para clonar"
          descripcion="Clonar crea una copia editable para tu institución; el original nunca cambia."
          acciones={<CampoBusqueda valor={searchCatalogo} onCambiar={setSearchCatalogo} placeholder="Buscar formato..." />}
          cuerpoClassName="space-y-4"
        >
          <TextoError>{errorClonar}</TextoError>
          {gruposCatalogo.length === 0 ? (
            <VacioFicha
              icono={predeterminadas.length === 0 ? Library : Search}
              texto={predeterminadas.length === 0 ? "Todavía no hay ningún formato en el catálogo." : "Ningún formato coincide con la búsqueda."}
            />
          ) : (
            gruposCatalogo.map((g) => (
              <div key={g.tipo.id}>
                <h3 className="m-0 mb-2 flex items-center gap-2 text-[12px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
                  <span className={`h-1.5 w-1.5 rounded-full ${VIOLETA.solido}`} aria-hidden="true" />
                  {g.tipo.nombre}
                  <span className="font-semibold text-ink/30 dark:text-ink-dark/30">{g.items.length}</span>
                </h3>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {g.items.map((item) => (
                    <div
                      key={item.id}
                      className="rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3.5 py-3 flex flex-col gap-2.5"
                    >
                      <div className="flex items-start gap-2.5">
                        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${VIOLETA.chip}`}>
                          <FileText size={15} aria-hidden="true" />
                        </span>
                        <span className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-ink dark:text-ink-dark">{item.nombre}</span>
                      </div>
                      <div className="flex items-center justify-between gap-2 mt-auto">
                        {yaClonada(item) ? (
                          <span className="inline-flex items-center gap-1 text-[12px] font-medium text-ink/50 dark:text-ink-dark/50">
                            <CheckCircle2 size={12} aria-hidden="true" />
                            Ya en tus plantillas
                          </span>
                        ) : (
                          <span />
                        )}
                        <button
                          type="button"
                          onClick={() => clonarPlantilla(item)}
                          disabled={clonandoId !== null}
                          className={claseBoton("secundario", "inline-flex items-center gap-1.5 !px-3 !py-1.5 text-[12.5px]")}
                        >
                          <Copy size={13} aria-hidden="true" />
                          {clonandoId === item.id ? "Clonando..." : "Clonar"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </BloqueFicha>
      )}

      {/* ===== Documentos generados ===== */}
      {tab === "generados" && (
        <BloqueFicha
          acento="violeta"
          icono={FileText}
          titulo="Documentos generados"
          descripcion="Un borrador todavía no tiene PDF: ábrelo para completarlo y emitir su versión 1."
          acciones={
            <>
              <CampoBusqueda valor={searchDocumentos} onCambiar={cambiarBusquedaDocumentos} placeholder="Buscar por título o alumno..." />
              <ControlSegmentado<FiltroEstado>
                etiqueta="Estado"
                valor={filtroEstado}
                onCambiar={cambiarFiltroEstado}
                opciones={[
                  { valor: "todos", etiqueta: "Todos" },
                  { valor: "borradores", etiqueta: "Borradores" },
                  { valor: "emitidos", etiqueta: "Emitidos" },
                ]}
              />
            </>
          }
          cuerpoClassName="space-y-3"
        >
          <TextoError>{errorDocumentos}</TextoError>

          {cargandoDocumentos && documentos.length === 0 ? (
            <EsqueletoLista cantidad={3} />
          ) : documentos.length === 0 && !hayFiltroDocumentos ? (
            <VacioFicha icono={FileText} texto="Todavía no se generó ningún documento.">
              <Link href="/documentos/nuevo" className={`mt-2 inline-block text-sm font-semibold hover:underline ${VIOLETA.texto}`}>
                Crear el primero →
              </Link>
            </VacioFicha>
          ) : documentosFiltrados.length === 0 ? (
            <VacioFicha icono={Search} texto="Ningún documento coincide con el filtro." />
          ) : (
            <ul className="m-0 p-0 list-none rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark divide-y divide-border dark:divide-border-dark overflow-hidden">
              {documentosFiltrados.map((d) => {
                const borrador = d.version_actual === null;
                const alumnos = d.estudiantes_resumen ?? [];
                return (
                  <li key={d.id} className="flex items-center gap-3 px-3.5 py-3 hover:bg-mist/50 dark:hover:bg-surface-raised-dark transition-colors">
                    <span
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                        borrador ? "bg-border/60 text-ink/50 dark:bg-border-dark dark:text-ink-dark/60" : VIOLETA.chip
                      }`}
                    >
                      {borrador ? <FilePen size={16} aria-hidden="true" /> : <FileCheck2 size={16} aria-hidden="true" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/documentos/${d.id}`}
                        className="block truncate text-sm font-semibold text-ink dark:text-ink-dark hover:text-acento-violeta dark:hover:text-acento-violeta-dark"
                      >
                        {d.titulo}
                      </Link>
                      <p className="m-0 mt-0.5 flex items-center gap-x-2.5 gap-y-0.5 flex-wrap text-[12px] text-ink/50 dark:text-ink-dark/50">
                        {alumnos.length > 0 && (
                          <span className="inline-flex items-center gap-1 text-ink/70 dark:text-ink-dark/70 font-medium" title={alumnos.join(", ")}>
                            <Users size={11} aria-hidden="true" />
                            {alumnos.length <= 2 ? alumnos.join(", ") : `${alumnos.slice(0, 2).join(", ")} +${alumnos.length - 2}`}
                          </span>
                        )}
                        <span>{nombreTipo(d.tipo_documento_id)}</span>
                        <span>{fechaCorta(d.creado_en)}</span>
                      </p>
                    </div>
                    <span
                      className={`hidden sm:inline-flex shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${
                        borrador ? "border border-dashed border-ink/25 text-ink/55 dark:border-ink-dark/25 dark:text-ink-dark/55" : VIOLETA.chipSolido
                      }`}
                    >
                      {borrador ? "Borrador" : `Emitido v${d.version_actual}`}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      {borrador && (
                        <button
                          type="button"
                          onClick={() => descartarBorrador(d)}
                          disabled={descartandoId === d.id}
                          title="Descartar borrador"
                          aria-label={`Descartar borrador ${d.titulo}`}
                          className="rounded-lg p-1.5 text-ink/40 hover:text-red-700 hover:bg-red-50 dark:text-ink-dark/40 dark:hover:text-red-300 dark:hover:bg-red-500/10 disabled:opacity-40 transition-colors"
                        >
                          <Trash2 size={15} aria-hidden="true" />
                        </button>
                      )}
                      <Link
                        href={`/documentos/${d.id}`}
                        aria-label={`Abrir ${d.titulo}`}
                        className={`rounded-lg p-1.5 hover:bg-acento-violeta/10 dark:hover:bg-acento-violeta-dark/15 ${VIOLETA.texto}`}
                      >
                        <ArrowRight size={16} aria-hidden="true" />
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          {totalDocumentos > TAMANO_PAGINA && (
            <div className="flex items-center justify-between pt-1">
              <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">
                {paginaDocumentos * TAMANO_PAGINA + 1}–{Math.min((paginaDocumentos + 1) * TAMANO_PAGINA, totalDocumentos)} de {totalDocumentos}{" "}
                documentos
              </p>
              <div className="flex items-center gap-2">
                <Boton
                  variante="secundario"
                  className="!px-3 !py-1.5 text-xs"
                  onClick={() => setPaginaDocumentos((p) => Math.max(0, p - 1))}
                  disabled={paginaDocumentos === 0}
                >
                  Anterior
                </Boton>
                <Boton
                  variante="secundario"
                  className="!px-3 !py-1.5 text-xs"
                  onClick={() => setPaginaDocumentos((p) => p + 1)}
                  disabled={(paginaDocumentos + 1) * TAMANO_PAGINA >= totalDocumentos}
                >
                  Siguiente
                </Boton>
              </div>
            </div>
          )}
        </BloqueFicha>
      )}
    </div>
  );
}

// Nombre comparable para detectar duplicados: sin "(copia)",
// "(predeterminado)", mayúsculas ni espacios de más.
function clavePlantilla(nombre: string): string {
  return nombre
    .toLowerCase()
    .replace(/\((copia|predeterminad[oa])\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function fechaCorta(iso: string) {
  return new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
}

// Pestaña con forma de tarjeta violeta: ícono sólido + título + conteo +
// una línea de qué hay dentro. role="tab" para lectores de pantalla.
function TarjetaPestana({
  activa,
  onClick,
  icono: Icono,
  titulo,
  valor,
  descripcion,
}: {
  activa: boolean;
  onClick: () => void;
  icono: LucideIcon;
  titulo: string;
  valor: number;
  descripcion: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={activa}
      onClick={onClick}
      className={`text-left rounded-xl border px-4 py-3.5 flex items-center gap-3 transition-all ${
        activa
          ? `${VIOLETA.fondo} !border-acento-violeta ring-2 ring-acento-violeta/25 dark:!border-acento-violeta-dark dark:ring-acento-violeta-dark/25`
          : "bg-surface dark:bg-surface-dark border-border dark:border-border-dark hover:border-acento-violeta/40 dark:hover:border-acento-violeta-dark/40"
      }`}
    >
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${activa ? VIOLETA.chipSolido : VIOLETA.chip}`}
      >
        <Icono size={18} strokeWidth={2} aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="text-[13.5px] font-bold text-ink dark:text-ink-dark truncate">{titulo}</span>
          <span className={`font-display text-[17px] font-bold leading-none ${VIOLETA.texto}`}>{valor}</span>
        </span>
        <span className="block mt-0.5 text-[12px] text-ink/50 dark:text-ink-dark/50 truncate">{descripcion}</span>
      </span>
    </button>
  );
}

function PildoraEstado({ activa }: { activa: boolean }) {
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap ${
        activa ? VIOLETA.chipSolido : "border border-border dark:border-border-dark text-ink/50 dark:text-ink-dark/50"
      }`}
    >
      {activa ? "Activa" : "Inactiva"}
    </span>
  );
}

function CampoBusqueda({ valor, onCambiar, placeholder }: { valor: string; onCambiar: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative">
      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
      <input
        type="search"
        aria-label={placeholder}
        placeholder={placeholder}
        value={valor}
        onChange={(e) => onCambiar(e.target.value)}
        className="w-48 sm:w-56 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark pl-8 pr-2.5 py-1.5 text-[13px] focus:outline-none focus:ring-2 focus:ring-teal-400 dark:focus:ring-teal-accent-dark"
      />
    </div>
  );
}
