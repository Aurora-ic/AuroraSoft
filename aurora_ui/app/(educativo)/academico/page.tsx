"use client";

import { useEffect, useState } from "react";
import { Pencil, Check, X, Trash2 } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
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
      className={`w-full text-left rounded-card px-3 py-2 text-sm transition-colors ${
        activo ? "bg-teal-900 text-white" : "text-ink hover:bg-mist"
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
      className="shrink-0 rounded-lg p-1.5 text-ink/35 hover:bg-mist hover:text-teal-700 transition-colors"
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
      className="shrink-0 rounded-lg p-1.5 text-ink/35 hover:bg-red-50 hover:text-red-700 transition-colors"
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
    <div className="rounded-card border border-red-200 bg-red-50/70 p-3 space-y-2" role="alertdialog" aria-label={`Eliminar ${nombre}`}>
      <p className="text-sm text-ink">
        ¿Eliminar <strong>{nombre}</strong>? Esta acción no se puede deshacer.
      </p>
      <TextoError className="text-xs">{error}</TextoError>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancelar}
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink/60 hover:bg-white"
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
      className="rounded-card border border-teal-400 bg-teal-600/[0.04] p-3 space-y-2.5"
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
          className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-ink/60 hover:bg-mist"
        >
          <X size={13} aria-hidden="true" />
          Cancelar
        </button>
        <button
          type="submit"
          disabled={guardando}
          className="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-teal-900 disabled:opacity-50"
        >
          <Check size={13} aria-hidden="true" />
          {guardando ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </form>
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

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-teal-900 tracking-tight">Estructura académica</h1>
        <p className="mt-1 text-sm text-ink/60 max-w-2xl">
          Niveles, grados y secciones de tu institución — la base para matricular estudiantes e importarlos por
          Excel. Una sección existe para un año escolar concreto: para reabrir un grado en un año nuevo, crea
          secciones nuevas en vez de reutilizar las del año pasado.
          {!esAdmin && " Solo un administrador puede crear elementos nuevos; tú puedes consultarlos."}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
        {/* Niveles */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">Niveles educativos</h2>

          <TextoError>{errorNiveles}</TextoError>

          {cargandoNiveles ? (
            <p className="text-sm text-ink/40">Cargando…</p>
          ) : niveles.length === 0 ? (
            <p className="text-sm text-ink/40 italic">Todavía no hay niveles creados.</p>
          ) : (
            <div className="space-y-1">
              {niveles.map((nivel) =>
                estaEditando("nivel", nivel.id) ? (
                  <div key={nivel.id}>{editorPara("nivel")}</div>
                ) : confirmandoEliminar("nivel", nivel.id) ? (
                  <div key={nivel.id}>{confirmacionPara(nivel.nombre)}</div>
                ) : (
                  <div key={nivel.id} className="flex items-center gap-1">
                    <FilaSeleccionable activo={nivelSeleccionado?.id === nivel.id} onClick={() => seleccionarNivel(nivel)}>
                      <span className="flex items-center justify-between gap-2">
                        {nivel.nombre}
                        {esAdmin && <span className="text-[11px] opacity-50">orden {nivel.orden}</span>}
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

          {esAdmin && (
            <form onSubmit={crearNivel} className="border-t border-border pt-4 space-y-3">
              <CampoEditable etiqueta="Nombre">
                <Input
                  required
                  placeholder="Secundaria"
                  value={formNivel.nombre}
                  onChange={(e) => setFormNivel({ ...formNivel, nombre: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Orden (opcional)">
                <Input
                  type="number"
                  placeholder="0"
                  value={formNivel.orden}
                  onChange={(e) => setFormNivel({ ...formNivel, orden: e.target.value })}
                />
              </CampoEditable>
              <TextoError>{errorFormNivel}</TextoError>
              <Boton type="submit" disabled={guardandoNivel} className="w-full">
                {guardandoNivel ? "Guardando…" : "+ Nuevo nivel"}
              </Boton>
            </form>
          )}
        </section>

        {/* Grados */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">
            Grados{nivelSeleccionado ? ` — ${nivelSeleccionado.nombre}` : ""}
          </h2>

          {!nivelSeleccionado ? (
            <p className="text-sm text-ink/40 italic">Selecciona un nivel educativo.</p>
          ) : (
            <>
              <TextoError>{errorGrados}</TextoError>

              {cargandoGrados ? (
                <p className="text-sm text-ink/40">Cargando…</p>
              ) : grados.length === 0 ? (
                <p className="text-sm text-ink/40 italic">Todavía no hay grados en este nivel.</p>
              ) : (
                <div className="space-y-1">
                  {grados.map((grado) =>
                    estaEditando("grado", grado.id) ? (
                      <div key={grado.id}>{editorPara("grado")}</div>
                    ) : confirmandoEliminar("grado", grado.id) ? (
                      <div key={grado.id}>{confirmacionPara(`el grado ${grado.nombre}`)}</div>
                    ) : (
                      <div key={grado.id} className="flex items-center gap-1">
                        <FilaSeleccionable activo={gradoSeleccionado?.id === grado.id} onClick={() => seleccionarGrado(grado)}>
                          <span className="flex items-center justify-between gap-2">
                            {grado.nombre}
                            {esAdmin && <span className="text-[11px] opacity-50">orden {grado.orden}</span>}
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

              {esAdmin && (
                <form onSubmit={crearGrado} className="border-t border-border pt-4 space-y-3">
                  <CampoEditable etiqueta="Nombre">
                    <Input
                      required
                      placeholder="3°"
                      value={formGrado.nombre}
                      onChange={(e) => setFormGrado({ ...formGrado, nombre: e.target.value })}
                    />
                  </CampoEditable>
                  <CampoEditable etiqueta="Orden (opcional)">
                    <Input
                      type="number"
                      placeholder="0"
                      value={formGrado.orden}
                      onChange={(e) => setFormGrado({ ...formGrado, orden: e.target.value })}
                    />
                  </CampoEditable>
                  <TextoError>{errorFormGrado}</TextoError>
                  <Boton type="submit" disabled={guardandoGrado} className="w-full">
                    {guardandoGrado ? "Guardando…" : "+ Nuevo grado"}
                  </Boton>
                </form>
              )}
            </>
          )}
        </section>

        {/* Secciones */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">
            Secciones{gradoSeleccionado ? ` — ${gradoSeleccionado.nombre}` : ""}
          </h2>

          {!gradoSeleccionado ? (
            <p className="text-sm text-ink/40 italic">Selecciona un grado.</p>
          ) : (
            <>
              <TextoError>{errorSecciones}</TextoError>

              {cargandoSecciones ? (
                <p className="text-sm text-ink/40">Cargando…</p>
              ) : secciones.length === 0 ? (
                <p className="text-sm text-ink/40 italic">Todavía no hay secciones en este grado.</p>
              ) : (
                <div className="space-y-1.5">
                  {secciones.map((seccion) =>
                    estaEditando("seccion", seccion.id) ? (
                      <div key={seccion.id}>{editorPara("seccion")}</div>
                    ) : confirmandoEliminar("seccion", seccion.id) ? (
                      <div key={seccion.id}>{confirmacionPara(`la sección ${seccion.nombre} (${seccion.anio_escolar})`)}</div>
                    ) : (
                      <div key={seccion.id} className="flex items-center gap-2 rounded-card border border-border px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-ink font-medium">{seccion.nombre}</div>
                          <div className="text-xs text-ink/50 mt-0.5">
                            Año {seccion.anio_escolar}
                            {seccion.turno ? ` · Turno ${seccion.turno}` : ""}
                          </div>
                        </div>
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

              {esAdmin && (
                <form onSubmit={crearSeccion} className="border-t border-border pt-4 space-y-3">
                  <CampoEditable etiqueta="Nombre">
                    <Input
                      required
                      placeholder="A"
                      value={formSeccion.nombre}
                      onChange={(e) => setFormSeccion({ ...formSeccion, nombre: e.target.value })}
                    />
                  </CampoEditable>
                  <div className="grid grid-cols-2 gap-3">
                    <CampoEditable etiqueta="Año escolar">
                      <Input
                        required
                        type="number"
                        placeholder="2026"
                        value={formSeccion.anio_escolar}
                        onChange={(e) => setFormSeccion({ ...formSeccion, anio_escolar: e.target.value })}
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Turno (opcional)">
                      <Input
                        placeholder="Mañana"
                        value={formSeccion.turno}
                        onChange={(e) => setFormSeccion({ ...formSeccion, turno: e.target.value })}
                      />
                    </CampoEditable>
                  </div>
                  <TextoError>{errorFormSeccion}</TextoError>
                  <Boton type="submit" disabled={guardandoSeccion} className="w-full">
                    {guardandoSeccion ? "Guardando…" : "+ Nueva sección"}
                  </Boton>
                </form>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
