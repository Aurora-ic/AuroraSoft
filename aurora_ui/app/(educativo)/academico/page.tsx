"use client";

import { useEffect, useState } from "react";
import { Pencil, Check, X, Trash2, Plus, ChevronRight, Info, Layers, GraduationCap, DoorOpen, Network, Users, type LucideIcon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { EncabezadoPagina, PastillaBanner } from "@/components/ui/Encabezado";
import type {
  NivelEducativo,
  NivelEducativoCreate,
  Grado,
  GradoCreate,
  Seccion,
  SeccionCreate,
  NivelEducativoUpdate,
  GradoUpdate,
  SeccionUpdate,
  ConteosEstructuraAcademica,
} from "@/types/api";

function FilaSeleccionable({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg px-3 py-2 text-sm transition-colors ${
        activo
          ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
          : "text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark"
      }`}
    >
      {children}
    </button>
  );
}

// 🆕 Edición en línea (sesión 2026-10-29) — antes un nombre u orden mal
// escrito no tenía arreglo desde la UI (solo existía crear). Un solo
// elemento se edita a la vez; el segundo campo es "Orden" para niveles y
// grados, y "Turno" para secciones (el año escolar no se edita, ver
// schemas.SeccionUpdate en el backend).
type TipoEditable = "nivel" | "grado" | "seccion";

function BotonEditar({ onClick, etiqueta }: { onClick: () => void; etiqueta: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={etiqueta}
      title={etiqueta}
      className="shrink-0 rounded-lg p-1.5 text-ink/35 dark:text-ink-dark/35 hover:bg-mist dark:hover:bg-surface-raised-dark hover:text-teal-700 dark:hover:text-teal-accent-dark transition-colors"
    >
      <Pencil size={14} aria-hidden="true" />
    </button>
  );
}

function BotonEliminar({ onClick, etiqueta }: { onClick: () => void; etiqueta: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={etiqueta}
      title={etiqueta}
      className="shrink-0 rounded-lg p-1.5 text-ink/35 dark:text-ink-dark/35 hover:bg-red-50 dark:hover:bg-red-500/15 hover:text-red-700 dark:hover:text-red-300 transition-colors"
    >
      <Trash2 size={14} aria-hidden="true" />
    </button>
  );
}

// 🆕 Confirmación en línea antes de borrar (sesión 2026-10-29) — el backend
// solo borra lo que nadie usa (sin grados/secciones/matrículas/evaluaciones,
// ver crud.eliminar_nivel_educativo); si algo lo bloquea, su mensaje 409 se
// muestra aquí mismo.
function ConfirmarEliminar({
  nombre,
  eliminando,
  error,
  onConfirmar,
  onCancelar,
}: {
  nombre: string;
  eliminando: boolean;
  error: string | null;
  onConfirmar: () => void;
  onCancelar: () => void;
}) {
  return (
    <div className="rounded-card border border-red-200 dark:border-red-500/30 bg-red-50/70 dark:bg-red-500/10 p-3 space-y-2" role="alertdialog" aria-label={`Eliminar ${nombre}`}>
      <p className="text-sm text-ink dark:text-ink-dark">
        ¿Eliminar <strong>{nombre}</strong>? Esta acción no se puede deshacer.
      </p>
      <TextoError className="text-xs">{error}</TextoError>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancelar}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink/60 dark:text-ink-dark/60 hover:bg-white dark:hover:bg-surface-dark"
        >
          Cancelar
        </button>
        <button
          type="button"
          onClick={onConfirmar}
          disabled={eliminando}
          className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
        >
          <Trash2 size={13} aria-hidden="true" />
          {eliminando ? "Eliminando…" : "Sí, eliminar"}
        </button>
      </div>
    </div>
  );
}

function EditorEnLinea({
  nombre,
  segundo,
  etiquetaSegundo,
  segundoEsNumero,
  guardando,
  error,
  onCambiar,
  onGuardar,
  onCancelar,
}: {
  nombre: string;
  segundo: string;
  etiquetaSegundo: string;
  segundoEsNumero: boolean;
  guardando: boolean;
  error: string | null;
  onCambiar: (campo: "nombre" | "segundo", valor: string) => void;
  onGuardar: () => void;
  onCancelar: () => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onGuardar();
      }}
      className="rounded-card border border-teal-400 dark:border-teal-accent-dark bg-teal-600/[0.04] dark:bg-teal-accent-dark/5 p-3 space-y-2.5"
    >
      <div className="grid grid-cols-[1fr_6rem] gap-2 text-sm">
        <CampoEditable etiqueta="Nombre">
          <Input required autoFocus value={nombre} onChange={(e) => onCambiar("nombre", e.target.value)} className="w-full" />
        </CampoEditable>
        <CampoEditable etiqueta={etiquetaSegundo}>
          <Input
            type={segundoEsNumero ? "number" : "text"}
            value={segundo}
            onChange={(e) => onCambiar("segundo", e.target.value)}
            className="w-full"
          />
        </CampoEditable>
      </div>
      <TextoError className="text-xs">{error}</TextoError>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancelar}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink/60 dark:text-ink-dark/60 hover:bg-mist dark:hover:bg-surface-raised-dark"
        >
          <X size={13} aria-hidden="true" />
          Cancelar
        </button>
        <button
          type="submit"
          disabled={guardando}
          className="inline-flex items-center gap-1 rounded-lg bg-accion px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-accion-hover disabled:opacity-50"
        >
          <Check size={13} aria-hidden="true" />
          {guardando ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
  );
}

// 🆕 Columna del explorador Nivel › Grado › Sección (sesión 2026-10-30) —
// cabecera con icono, contador y el botón "+ Agregar" (solo admin) que
// despliega el formulario de alta.
function Columna({
  icono: Icono,
  titulo,
  subtitulo,
  cantidad,
  totalEstudiantes,
  puedeAgregar,
  agregando,
  onAgregar,
  etiquetaAgregar,
  children,
}: {
  icono: LucideIcon;
  titulo: string;
  subtitulo?: string;
  cantidad: number | null;
  // Estudiantes matriculados en todo lo que lista la columna.
  totalEstudiantes?: number | null;
  puedeAgregar: boolean;
  agregando: boolean;
  onAgregar: () => void;
  etiquetaAgregar: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden">
      <header className="flex items-center justify-between gap-2 px-4 py-3 border-b border-border dark:border-border-dark bg-mist/60 dark:bg-surface-raised-dark">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
            <Icono size={16} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-sm font-semibold text-teal-900 dark:text-ink-dark leading-tight flex items-center gap-1.5">
              {titulo}
              {cantidad !== null && (
                <span className="rounded-full bg-border/80 dark:bg-border-dark px-1.5 text-[10.5px] font-bold text-ink/55 dark:text-ink-dark/60">
                  {cantidad}
                </span>
              )}
            </h2>
            {(subtitulo || (totalEstudiantes !== null && totalEstudiantes !== undefined)) && (
              <p className="m-0 text-[11.5px] text-ink/50 dark:text-ink-dark/50 truncate">
                {[
                  subtitulo,
                  totalEstudiantes !== null && totalEstudiantes !== undefined
                    ? `${totalEstudiantes} estudiante${totalEstudiantes === 1 ? "" : "s"}`
                    : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </div>
        </div>
        {puedeAgregar && (
          <button
            type="button"
            onClick={onAgregar}
            aria-expanded={agregando}
            className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors ${
              agregando
                ? "border-accion bg-accion text-white dark:border-teal-accent-dark dark:bg-teal-accent-dark dark:text-mist-dark"
                : "border-border bg-surface text-ink/70 hover:border-teal-400 hover:text-teal-700 dark:border-border-dark dark:bg-surface-dark dark:text-ink-dark/70 dark:hover:text-teal-accent-dark"
            }`}
          >
            {agregando ? <X size={13} aria-hidden="true" /> : <Plus size={13} aria-hidden="true" />}
            {agregando ? "Cerrar" : `Agregar ${etiquetaAgregar}`}
          </button>
        )}
      </header>
      <div className="p-3 space-y-3">{children}</div>
    </section>
  );
}

// 🆕 Recuento de estudiantes (activos, con matrícula vigente) al lado
// derecho de cada fila — ver GET /admin/personas/academico/conteos. `null`
// mientras carga: no se muestra un "0" que todavía no es real.
function Recuento({ n, activo = false }: { n: number | null; activo?: boolean }) {
  if (n === null) return null;
  return (
    <span
      title={`${n} estudiante${n === 1 ? "" : "s"} matriculado${n === 1 ? "" : "s"}`}
      className={`inline-flex min-w-[2rem] items-center justify-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums ${
        activo
          ? "bg-white/20 text-white dark:bg-mist-dark/25 dark:text-mist-dark"
          : n === 0
            ? "bg-border/60 text-ink/40 dark:bg-border-dark dark:text-ink-dark/40"
            : "bg-teal-600/10 text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
      }`}
    >
      <Users size={11} aria-hidden="true" />
      {n}
    </span>
  );
}

function VacioColumna({ texto }: { texto: string }) {
  return (
    <p className="m-0 rounded-lg border border-dashed border-border dark:border-border-dark px-3 py-5 text-center text-[12.5px] text-ink/45 dark:text-ink-dark/45">
      {texto}
    </p>
  );
}

// Mismo criterio de orden que el backend (orden, luego nombre) — tras editar
// se reordena localmente en vez de volver a pedir la lista.
function ordenarPorOrden<T extends { orden: number; nombre: string }>(lista: T[]): T[] {
  return [...lista].sort((a, b) => a.orden - b.orden || a.nombre.localeCompare(b.nombre));
}

export default function EstructuraAcademicaPage() {
  const { sesion } = useAuth();
  const esAdmin = sesion?.rol === "admin";

  // --- Niveles ---
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [cargandoNiveles, setCargandoNiveles] = useState(true);
  const [errorNiveles, setErrorNiveles] = useState<string | null>(null);
  const [nivelSeleccionado, setNivelSeleccionado] = useState<NivelEducativo | null>(null);
  const [formNivel, setFormNivel] = useState({ nombre: "", orden: "" });
  const [guardandoNivel, setGuardandoNivel] = useState(false);
  const [errorFormNivel, setErrorFormNivel] = useState<string | null>(null);

  // --- Grados (del nivel seleccionado) ---
  const [grados, setGrados] = useState<Grado[]>([]);
  const [cargandoGrados, setCargandoGrados] = useState(false);
  const [errorGrados, setErrorGrados] = useState<string | null>(null);
  const [gradoSeleccionado, setGradoSeleccionado] = useState<Grado | null>(null);
  const [formGrado, setFormGrado] = useState({ nombre: "", orden: "" });
  const [guardandoGrado, setGuardandoGrado] = useState(false);
  const [errorFormGrado, setErrorFormGrado] = useState<string | null>(null);

  // --- Secciones (del grado seleccionado) ---
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [cargandoSecciones, setCargandoSecciones] = useState(false);
  const [errorSecciones, setErrorSecciones] = useState<string | null>(null);
  const [formSeccion, setFormSeccion] = useState({ nombre: "", turno: "", anio_escolar: "" });
  const [guardandoSeccion, setGuardandoSeccion] = useState(false);
  const [errorFormSeccion, setErrorFormSeccion] = useState<string | null>(null);

  // 🆕 Los formularios de alta van plegados detrás de "+ Agregar" (sesión
  // 2026-10-30, "optimizando espacios") — antes las 3 columnas mostraban
  // siempre su formulario abierto, aunque casi nunca se crea nada.
  const [formAbierto, setFormAbierto] = useState<TipoEditable | null>(null);

  // --- 🆕 Recuento de estudiantes por nivel/grado/sección (claves = id) ---
  const [conteos, setConteos] = useState<ConteosEstructuraAcademica | null>(null);

  // --- Edición en línea (un elemento a la vez) ---
  const [editando, setEditando] = useState<{ tipo: TipoEditable; id: number } | null>(null);
  const [formEdicion, setFormEdicion] = useState({ nombre: "", segundo: "" });
  const [guardandoEdicion, setGuardandoEdicion] = useState(false);
  const [errorEdicion, setErrorEdicion] = useState<string | null>(null);

  // --- Eliminación (un elemento a la vez, con confirmación en línea) ---
  const [eliminandoItem, setEliminandoItem] = useState<{ tipo: TipoEditable; id: number } | null>(null);
  const [borrando, setBorrando] = useState(false);
  const [errorEliminar, setErrorEliminar] = useState<string | null>(null);

  function pedirEliminar(tipo: TipoEditable, id: number) {
    setEditando(null);
    setEliminandoItem({ tipo, id });
    setErrorEliminar(null);
  }

  function confirmandoEliminar(tipo: TipoEditable, id: number) {
    return eliminandoItem?.tipo === tipo && eliminandoItem.id === id;
  }

  async function confirmarEliminar() {
    if (!eliminandoItem) return;
    const { tipo, id } = eliminandoItem;
    setBorrando(true);
    setErrorEliminar(null);
    try {
      if (tipo === "nivel") {
        await apiClient.delete(`/admin/personas/academico/niveles/${id}`);
        setNiveles((prev) => prev.filter((n) => n.id !== id));
        if (nivelSeleccionado?.id === id) {
          setNivelSeleccionado(null);
          setGrados([]);
          setGradoSeleccionado(null);
          setSecciones([]);
        }
      } else if (tipo === "grado") {
        await apiClient.delete(`/admin/personas/academico/grados/${id}`);
        setGrados((prev) => prev.filter((g) => g.id !== id));
        if (gradoSeleccionado?.id === id) {
          setGradoSeleccionado(null);
          setSecciones([]);
        }
      } else {
        await apiClient.delete(`/admin/personas/academico/secciones/${id}`);
        setSecciones((prev) => prev.filter((s) => s.id !== id));
      }
      setEliminandoItem(null);
    } catch (err: any) {
      setErrorEliminar(err.message || "No se pudo eliminar.");
    } finally {
      setBorrando(false);
    }
  }

  function confirmacionPara(nombre: string) {
    return (
      <ConfirmarEliminar
        nombre={nombre}
        eliminando={borrando}
        error={errorEliminar}
        onConfirmar={confirmarEliminar}
        onCancelar={() => setEliminandoItem(null)}
      />
    );
  }

  function empezarEdicion(tipo: TipoEditable, id: number, nombre: string, segundo: string) {
    setEliminandoItem(null);
    setEditando({ tipo, id });
    setFormEdicion({ nombre, segundo });
    setErrorEdicion(null);
  }

  function cancelarEdicion() {
    setEditando(null);
    setErrorEdicion(null);
  }

  function estaEditando(tipo: TipoEditable, id: number) {
    return editando?.tipo === tipo && editando.id === id;
  }

  async function guardarEdicion() {
    if (!editando) return;
    setGuardandoEdicion(true);
    setErrorEdicion(null);
    try {
      if (editando.tipo === "nivel") {
        const payload: NivelEducativoUpdate = {
          nombre: formEdicion.nombre,
          orden: formEdicion.segundo ? Number(formEdicion.segundo) : 0,
        };
        const nivel = await apiClient.patch<NivelEducativo>(`/admin/personas/academico/niveles/${editando.id}`, payload);
        setNiveles((prev) => ordenarPorOrden(prev.map((n) => (n.id === nivel.id ? nivel : n))));
        if (nivelSeleccionado?.id === nivel.id) setNivelSeleccionado(nivel);
      } else if (editando.tipo === "grado") {
        const payload: GradoUpdate = {
          nombre: formEdicion.nombre,
          orden: formEdicion.segundo ? Number(formEdicion.segundo) : 0,
        };
        const grado = await apiClient.patch<Grado>(`/admin/personas/academico/grados/${editando.id}`, payload);
        setGrados((prev) => ordenarPorOrden(prev.map((g) => (g.id === grado.id ? grado : g))));
        if (gradoSeleccionado?.id === grado.id) setGradoSeleccionado(grado);
      } else {
        const payload: SeccionUpdate = { nombre: formEdicion.nombre, turno: formEdicion.segundo || null };
        const seccion = await apiClient.patch<Seccion>(`/admin/personas/academico/secciones/${editando.id}`, payload);
        setSecciones((prev) => prev.map((s) => (s.id === seccion.id ? seccion : s)));
      }
      setEditando(null);
    } catch (err: any) {
      setErrorEdicion(err.message || "No se pudieron guardar los cambios.");
    } finally {
      setGuardandoEdicion(false);
    }
  }

  function editorPara(tipo: TipoEditable) {
    return (
      <EditorEnLinea
        nombre={formEdicion.nombre}
        segundo={formEdicion.segundo}
        etiquetaSegundo={tipo === "seccion" ? "Turno" : "Orden"}
        segundoEsNumero={tipo !== "seccion"}
        guardando={guardandoEdicion}
        error={errorEdicion}
        onCambiar={(campo, valor) => setFormEdicion((f) => ({ ...f, [campo]: valor }))}
        onGuardar={guardarEdicion}
        onCancelar={cancelarEdicion}
      />
    );
  }

  useEffect(() => {
    if (!sesion?.institucionId) return;
    setCargandoNiveles(true);
    setErrorNiveles(null);
    apiClient
      .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
      .then(setNiveles)
      .catch((err: any) => setErrorNiveles(err.message || "No se pudieron cargar los niveles educativos."))
      .finally(() => setCargandoNiveles(false));
    apiClient
      .get<ConteosEstructuraAcademica>(`/admin/personas/academico/conteos/${sesion.institucionId}`)
      .then(setConteos)
      // Un recuento que no carga no debe romper la pantalla: solo no se muestra.
      .catch(() => setConteos(null));
  }, [sesion]);

  async function seleccionarNivel(nivel: NivelEducativo) {
    setNivelSeleccionado(nivel);
    setGradoSeleccionado(null);
    setGrados([]);
    setSecciones([]);
    setErrorSecciones(null);
    setCargandoGrados(true);
    setErrorGrados(null);
    try {
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivel.id}`);
      setGrados(datos);
    } catch (err: any) {
      setErrorGrados(err.message || "No se pudieron cargar los grados.");
    } finally {
      setCargandoGrados(false);
    }
  }

  async function seleccionarGrado(grado: Grado) {
    setGradoSeleccionado(grado);
    setSecciones([]);
    setCargandoSecciones(true);
    setErrorSecciones(null);
    try {
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${grado.id}`);
      setSecciones(datos);
    } catch (err: any) {
      setErrorSecciones(err.message || "No se pudieron cargar las secciones.");
    } finally {
      setCargandoSecciones(false);
    }
  }

  async function crearNivel(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) return;
    setGuardandoNivel(true);
    setErrorFormNivel(null);
    try {
      const payload: NivelEducativoCreate = {
        institucion_id: sesion.institucionId,
        nombre: formNivel.nombre,
        orden: formNivel.orden ? Number(formNivel.orden) : 0,
      };
      await apiClient.post<NivelEducativo>("/admin/personas/academico/niveles", payload);
      const datos = await apiClient.get<NivelEducativo[]>(
        `/admin/personas/academico/niveles/${sesion.institucionId}`,
      );
      setNiveles(datos);
      setFormNivel({ nombre: "", orden: "" });
    } catch (err: any) {
      setErrorFormNivel(err.message || "No se pudo crear el nivel educativo.");
    } finally {
      setGuardandoNivel(false);
    }
  }

  async function crearGrado(e: React.FormEvent) {
    e.preventDefault();
    if (!nivelSeleccionado) return;
    setGuardandoGrado(true);
    setErrorFormGrado(null);
    try {
      const payload: GradoCreate = {
        nivel_educativo_id: nivelSeleccionado.id,
        nombre: formGrado.nombre,
        orden: formGrado.orden ? Number(formGrado.orden) : 0,
      };
      await apiClient.post<Grado>("/admin/personas/academico/grados", payload);
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelSeleccionado.id}`);
      setGrados(datos);
      setFormGrado({ nombre: "", orden: "" });
    } catch (err: any) {
      setErrorFormGrado(err.message || "No se pudo crear el grado.");
    } finally {
      setGuardandoGrado(false);
    }
  }

  async function crearSeccion(e: React.FormEvent) {
    e.preventDefault();
    if (!gradoSeleccionado) return;
    const anio = Number(formSeccion.anio_escolar);
    if (!anio) {
      setErrorFormSeccion("Indica el año escolar.");
      return;
    }
    setGuardandoSeccion(true);
    setErrorFormSeccion(null);
    try {
      const payload: SeccionCreate = {
        grado_id: gradoSeleccionado.id,
        nombre: formSeccion.nombre,
        turno: formSeccion.turno || null,
        anio_escolar: anio,
      };
      await apiClient.post<Seccion>("/admin/personas/academico/secciones", payload);
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoSeleccionado.id}`);
      setSecciones(datos);
      setFormSeccion({ nombre: "", turno: "", anio_escolar: "" });
    } catch (err: any) {
      setErrorFormSeccion(err.message || "No se pudo crear la sección.");
    } finally {
      setGuardandoSeccion(false);
    }
  }

  const contarNivel = (id: number) => (conteos ? conteos.niveles[String(id)] ?? 0 : null);
  const contarGrado = (id: number) => (conteos ? conteos.grados[String(id)] ?? 0 : null);
  const contarSeccion = (id: number) => (conteos ? conteos.secciones[String(id)] ?? 0 : null);

  // Ruta de la selección actual — Nivel › Grado, visible arriba de las 3
  // columnas para no tener que leer los títulos de cada una.
  const ruta = [nivelSeleccionado?.nombre, gradoSeleccionado?.nombre].filter(Boolean) as string[];

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-4">
      <EncabezadoPagina variante="destacado"
        icono={Network}
        acento="teal"
        titulo="Estructura académica"
        acciones={
          conteos && (
            <PastillaBanner>
              <Users size={14} aria-hidden="true" />
              <strong className="font-display text-[15px]">{conteos.total}</strong>
              estudiante{conteos.total === 1 ? "" : "s"} matriculado{conteos.total === 1 ? "" : "s"}
            </PastillaBanner>
          )
        }
        descripcion={
          <>
            Niveles, grados y secciones — la base para matricular e importar estudiantes.
            {!esAdmin && " Solo un administrador puede crear o editar elementos."}
          </>
        }
      />

      <div className="flex items-start gap-2 rounded-xl border border-teal-600/15 dark:border-border-dark bg-teal-600/[0.04] dark:bg-surface-dark px-3.5 py-2.5 text-[12px] text-ink/65 dark:text-ink-dark/65">
        <Info size={14} className="mt-0.5 shrink-0 text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
        <span>
          Una sección existe para un año escolar concreto: para reabrir un grado en un año nuevo, crea secciones nuevas en vez de
          reutilizar las del año pasado.
        </span>
      </div>

      <nav aria-label="Selección actual" className="flex items-center gap-1.5 flex-wrap text-[12.5px]">
        <button
          type="button"
          onClick={() => {
            setNivelSeleccionado(null);
            setGradoSeleccionado(null);
            setGrados([]);
            setSecciones([]);
          }}
          className="font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
        >
          Todos los niveles
        </button>
        {ruta.map((parte, i) => (
          <span key={parte + i} className="flex items-center gap-1.5">
            <ChevronRight size={13} className="text-ink/30 dark:text-ink-dark/30" aria-hidden="true" />
            <span className={i === ruta.length - 1 ? "font-semibold text-ink dark:text-ink-dark" : "text-ink/60 dark:text-ink-dark/60"}>
              {parte}
            </span>
          </span>
        ))}
      </nav>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
        {/* Niveles */}
        <Columna
          icono={Layers}
          titulo="Niveles educativos"
          cantidad={cargandoNiveles ? null : niveles.length}
          totalEstudiantes={conteos ? conteos.total : null}
          puedeAgregar={esAdmin}
          agregando={formAbierto === "nivel"}
          onAgregar={() => setFormAbierto((f) => (f === "nivel" ? null : "nivel"))}
          etiquetaAgregar="nivel"
        >
          {esAdmin && formAbierto === "nivel" && (
            <form onSubmit={crearNivel} className="rounded-lg border border-teal-400/50 dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark p-3 space-y-2.5 text-sm">
              <div className="grid grid-cols-[1fr_5.5rem] gap-2">
                <CampoEditable etiqueta="Nombre">
                  <Input
                    required
                    autoFocus
                    placeholder="Secundaria"
                    value={formNivel.nombre}
                    onChange={(e) => setFormNivel({ ...formNivel, nombre: e.target.value })}
                    className="w-full"
                  />
                </CampoEditable>
                <CampoEditable etiqueta="Orden">
                  <Input
                    type="number"
                    placeholder="0"
                    value={formNivel.orden}
                    onChange={(e) => setFormNivel({ ...formNivel, orden: e.target.value })}
                    className="w-full"
                  />
                </CampoEditable>
              </div>
              <TextoError className="text-xs">{errorFormNivel}</TextoError>
              <Boton type="submit" disabled={guardandoNivel} className="w-full">
                {guardandoNivel ? "Guardando…" : "Crear nivel"}
              </Boton>
            </form>
          )}

          <TextoError>{errorNiveles}</TextoError>

          {cargandoNiveles ? (
            <p className="text-sm text-ink/40 dark:text-ink-dark/40">Cargando…</p>
          ) : niveles.length === 0 ? (
            <VacioColumna texto="Todavía no hay niveles creados." />
          ) : (
            <div className="space-y-0.5">
              {niveles.map((nivel) =>
                estaEditando("nivel", nivel.id) ? (
                  <div key={nivel.id}>{editorPara("nivel")}</div>
                ) : confirmandoEliminar("nivel", nivel.id) ? (
                  <div key={nivel.id}>{confirmacionPara(nivel.nombre)}</div>
                ) : (
                  <div key={nivel.id} className="flex items-center gap-0.5">
                    <FilaSeleccionable activo={nivelSeleccionado?.id === nivel.id} onClick={() => seleccionarNivel(nivel)}>
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate">{nivel.nombre}</span>
                        <span className="flex items-center gap-1.5 shrink-0">
                          {esAdmin && <span className="text-[11px] opacity-50">orden {nivel.orden}</span>}
                          <Recuento n={contarNivel(nivel.id)} activo={nivelSeleccionado?.id === nivel.id} />
                          <ChevronRight size={14} className="opacity-40" aria-hidden="true" />
                        </span>
                      </span>
                    </FilaSeleccionable>
                    {esAdmin && (
                      <>
                        <BotonEditar
                          etiqueta={`Editar ${nivel.nombre}`}
                          onClick={() => empezarEdicion("nivel", nivel.id, nivel.nombre, String(nivel.orden))}
                        />
                        <BotonEliminar etiqueta={`Eliminar ${nivel.nombre}`} onClick={() => pedirEliminar("nivel", nivel.id)} />
                      </>
                    )}
                  </div>
                ),
              )}
            </div>
          )}
        </Columna>

        {/* Grados */}
        <Columna
          icono={GraduationCap}
          titulo="Grados"
          subtitulo={nivelSeleccionado?.nombre}
          cantidad={!nivelSeleccionado || cargandoGrados ? null : grados.length}
          totalEstudiantes={nivelSeleccionado ? contarNivel(nivelSeleccionado.id) : null}
          puedeAgregar={esAdmin && !!nivelSeleccionado}
          agregando={formAbierto === "grado"}
          onAgregar={() => setFormAbierto((f) => (f === "grado" ? null : "grado"))}
          etiquetaAgregar="grado"
        >
          {!nivelSeleccionado ? (
            <VacioColumna texto="Selecciona un nivel educativo." />
          ) : (
            <>
              {esAdmin && formAbierto === "grado" && (
                <form onSubmit={crearGrado} className="rounded-lg border border-teal-400/50 dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark p-3 space-y-2.5 text-sm">
                  <div className="grid grid-cols-[1fr_5.5rem] gap-2">
                    <CampoEditable etiqueta="Nombre">
                      <Input
                        required
                        autoFocus
                        placeholder="3°"
                        value={formGrado.nombre}
                        onChange={(e) => setFormGrado({ ...formGrado, nombre: e.target.value })}
                        className="w-full"
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Orden">
                      <Input
                        type="number"
                        placeholder="0"
                        value={formGrado.orden}
                        onChange={(e) => setFormGrado({ ...formGrado, orden: e.target.value })}
                        className="w-full"
                      />
                    </CampoEditable>
                  </div>
                  <TextoError className="text-xs">{errorFormGrado}</TextoError>
                  <Boton type="submit" disabled={guardandoGrado} className="w-full">
                    {guardandoGrado ? "Guardando…" : "Crear grado"}
                  </Boton>
                </form>
              )}

              <TextoError>{errorGrados}</TextoError>

              {cargandoGrados ? (
                <p className="text-sm text-ink/40 dark:text-ink-dark/40">Cargando…</p>
              ) : grados.length === 0 ? (
                <VacioColumna texto="Todavía no hay grados en este nivel." />
              ) : (
                <div className="space-y-0.5">
                  {grados.map((grado) =>
                    estaEditando("grado", grado.id) ? (
                      <div key={grado.id}>{editorPara("grado")}</div>
                    ) : confirmandoEliminar("grado", grado.id) ? (
                      <div key={grado.id}>{confirmacionPara(`el grado ${grado.nombre}`)}</div>
                    ) : (
                      <div key={grado.id} className="flex items-center gap-0.5">
                        <FilaSeleccionable activo={gradoSeleccionado?.id === grado.id} onClick={() => seleccionarGrado(grado)}>
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate">{grado.nombre}</span>
                            <span className="flex items-center gap-1.5 shrink-0">
                              {esAdmin && <span className="text-[11px] opacity-50">orden {grado.orden}</span>}
                              <Recuento n={contarGrado(grado.id)} activo={gradoSeleccionado?.id === grado.id} />
                              <ChevronRight size={14} className="opacity-40" aria-hidden="true" />
                            </span>
                          </span>
                        </FilaSeleccionable>
                        {esAdmin && (
                          <>
                            <BotonEditar
                              etiqueta={`Editar ${grado.nombre}`}
                              onClick={() => empezarEdicion("grado", grado.id, grado.nombre, String(grado.orden))}
                            />
                            <BotonEliminar etiqueta={`Eliminar ${grado.nombre}`} onClick={() => pedirEliminar("grado", grado.id)} />
                          </>
                        )}
                      </div>
                    ),
                  )}
                </div>
              )}
            </>
          )}
        </Columna>

        {/* Secciones */}
        <Columna
          icono={DoorOpen}
          titulo="Secciones"
          subtitulo={gradoSeleccionado?.nombre}
          cantidad={!gradoSeleccionado || cargandoSecciones ? null : secciones.length}
          totalEstudiantes={gradoSeleccionado ? contarGrado(gradoSeleccionado.id) : null}
          puedeAgregar={esAdmin && !!gradoSeleccionado}
          agregando={formAbierto === "seccion"}
          onAgregar={() => setFormAbierto((f) => (f === "seccion" ? null : "seccion"))}
          etiquetaAgregar="sección"
        >
          {!gradoSeleccionado ? (
            <VacioColumna texto="Selecciona un grado." />
          ) : (
            <>
              {esAdmin && formAbierto === "seccion" && (
                <form onSubmit={crearSeccion} className="rounded-lg border border-teal-400/50 dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark p-3 space-y-2.5 text-sm">
                  <div className="grid grid-cols-3 gap-2">
                    <CampoEditable etiqueta="Nombre">
                      <Input
                        required
                        autoFocus
                        placeholder="A"
                        value={formSeccion.nombre}
                        onChange={(e) => setFormSeccion({ ...formSeccion, nombre: e.target.value })}
                        className="w-full"
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Año">
                      <Input
                        required
                        type="number"
                        placeholder="2026"
                        value={formSeccion.anio_escolar}
                        onChange={(e) => setFormSeccion({ ...formSeccion, anio_escolar: e.target.value })}
                        className="w-full"
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Turno">
                      <Input
                        placeholder="Mañana"
                        value={formSeccion.turno}
                        onChange={(e) => setFormSeccion({ ...formSeccion, turno: e.target.value })}
                        className="w-full"
                      />
                    </CampoEditable>
                  </div>
                  <TextoError className="text-xs">{errorFormSeccion}</TextoError>
                  <Boton type="submit" disabled={guardandoSeccion} className="w-full">
                    {guardandoSeccion ? "Guardando…" : "Crear sección"}
                  </Boton>
                </form>
              )}

              <TextoError>{errorSecciones}</TextoError>

              {cargandoSecciones ? (
                <p className="text-sm text-ink/40 dark:text-ink-dark/40">Cargando…</p>
              ) : secciones.length === 0 ? (
                <VacioColumna texto="Todavía no hay secciones en este grado." />
              ) : (
                <div className="space-y-1.5">
                  {secciones.map((seccion) =>
                    estaEditando("seccion", seccion.id) ? (
                      <div key={seccion.id}>{editorPara("seccion")}</div>
                    ) : confirmandoEliminar("seccion", seccion.id) ? (
                      <div key={seccion.id}>{confirmacionPara(`la sección ${seccion.nombre} (${seccion.anio_escolar})`)}</div>
                    ) : (
                      <div
                        key={seccion.id}
                        className="flex items-center gap-2 rounded-lg border border-border dark:border-border-dark px-3 py-2"
                      >
                        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark font-display text-[13px] font-bold">
                          {seccion.nombre.slice(0, 2)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-ink dark:text-ink-dark font-semibold truncate">Sección {seccion.nombre}</div>
                          <div className="text-[11.5px] text-ink/50 dark:text-ink-dark/50">
                            Año {seccion.anio_escolar}
                            {seccion.turno ? ` · Turno ${seccion.turno}` : ""}
                          </div>
                        </div>
                        <Recuento n={contarSeccion(seccion.id)} />
                        {esAdmin && (
                          <>
                            <BotonEditar
                              etiqueta={`Editar sección ${seccion.nombre}`}
                              onClick={() => empezarEdicion("seccion", seccion.id, seccion.nombre, seccion.turno ?? "")}
                            />
                            <BotonEliminar
                              etiqueta={`Eliminar sección ${seccion.nombre}`}
                              onClick={() => pedirEliminar("seccion", seccion.id)}
                            />
                          </>
                        )}
                      </div>
                    ),
                  )}
                </div>
              )}
            </>
          )}
        </Columna>
      </div>
    </div>
  );
}
