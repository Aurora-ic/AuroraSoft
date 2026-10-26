"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TextoError } from "@/components/ui/TextoError";
import { ETIQUETAS_TIPO_SECCION, TIPOS_SECCION_ORDENADOS, TIPOS_CON_CONFIG_SIMPLE } from "@/lib/documentos-constantes";
import { Migas } from "@/components/ui/Migas";
import type {
  PlantillaDocumento,
  PlantillaDocumentoUpdate,
  PlantillaSeccion,
  PlantillaSeccionCreate,
  TipoSeccionDocumento,
  Institucion,
} from "@/types/api";

const FUENTES = ["Arial", "Helvetica", "Times New Roman"];

// El constructor: tipografía del documento (cuerpo + subtítulo + título por
// separado), membrete/pie/fondo del colegio (admin/superadmin), y la lista
// ordenada de secciones — agregar, reordenar, configurar, borrar. Cada
// sección usa uno de los 13 tipos ya cerrados del motor (ver
// docs/motor-documentos.md); el contenido real de cada documento se llena
// aparte, en /documentos/[id].
export default function ConstructorPlantillaPage() {
  const params = useParams();
  const plantillaId = params.id as string;
  const { sesion } = useAuth();

  const [plantilla, setPlantilla] = useState<PlantillaDocumento | null>(null);
  const [secciones, setSecciones] = useState<PlantillaSeccion[]>([]);
  const [institucion, setInstitucion] = useState<Institucion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState<PlantillaDocumentoUpdate | null>(null);
  const [guardandoForm, setGuardandoForm] = useState(false);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  const [nuevoTipo, setNuevoTipo] = useState<TipoSeccionDocumento>("texto_libre");
  const [nuevoTitulo, setNuevoTitulo] = useState("");
  const [agregando, setAgregando] = useState(false);
  const [errorAgregar, setErrorAgregar] = useState<string | null>(null);

  const [seccionAbierta, setSeccionAbierta] = useState<number | null>(null);
  const [configTexto, setConfigTexto] = useState<Record<number, string>>({});
  const [errorSeccionId, setErrorSeccionId] = useState<number | null>(null);

  const [subiendoBranding, setSubiendoBranding] = useState<"encabezado" | "pie" | "fondo" | null>(null);
  const [errorBranding, setErrorBranding] = useState<string | null>(null);

  function cargar() {
    setCargando(true);
    Promise.all([
      apiClient.get<PlantillaDocumento>(`/documentos/plantillas/${plantillaId}`),
      apiClient.get<PlantillaSeccion[]>(`/documentos/plantillas/${plantillaId}/secciones`),
      apiClient.get<Institucion>("/instituciones/me"),
    ])
      .then(([p, s, inst]) => {
        setPlantilla(p);
        setForm({
          nombre: p.nombre,
          fuente: p.fuente,
          tamano_pt: p.tamano_pt,
          interlineado: p.interlineado,
          justificado: p.justificado,
          titulo_negrita: p.titulo_negrita,
          titulo_cursiva: p.titulo_cursiva,
          titulo_tamano_pt: p.titulo_tamano_pt,
          subtitulo_tamano_pt: p.subtitulo_tamano_pt,
          mostrar_fondo_institucion: p.mostrar_fondo_institucion,
        });
        setSecciones(s.slice().sort((a, b) => a.orden - b.orden));
        setInstitucion(inst);
      })
      .catch((err) => setError(err.message || "No se pudo cargar la plantilla."))
      .finally(() => setCargando(false));
  }

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plantillaId]);

  // 🆕 Activar/desactivar — hallazgo real (sesión 2026-10-25): esta
  // pantalla no mostraba el estado activa/inactiva en ningún lado, ni
  // daba forma de cambiarlo. Resultado real en la BD de producción: una
  // plantilla recién clonada queda inactiva por diseño (clonar_plantilla_
  // documento, activar=False por defecto, para no reemplazar sin querer
  // la que ya estaba en uso) y nada en pantalla lo explicaba ni ofrecía
  // activarla — y, al revés, "+ Nueva desde cero" crea con activa=True
  // por defecto y la exclusividad de una sola activa por tipo apagaba en
  // silencio la que ya estaba bien armada, dejando activa una plantilla
  // recién creada sin ninguna sección. Acción propia (no mezclada con
  // "Guardar formato") porque activar tiene un efecto colateral real:
  // desactiva cualquier otra plantilla activa de esta institución para el
  // mismo tipo de documento (ver _desactivar_plantillas_activas, crud.py).
  const [alternandoActiva, setAlternandoActiva] = useState(false);
  const [errorActiva, setErrorActiva] = useState<string | null>(null);

  async function alternarActiva() {
    setAlternandoActiva(true);
    setErrorActiva(null);
    try {
      const actualizada = await apiClient.patch<PlantillaDocumento>(`/documentos/plantillas/${plantillaId}`, {
        activa: !plantilla?.activa,
      });
      setPlantilla(actualizada);
    } catch (err: any) {
      setErrorActiva(err.message || "No se pudo cambiar el estado.");
    } finally {
      setAlternandoActiva(false);
    }
  }

  async function guardarForm(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setGuardandoForm(true);
    setErrorForm(null);
    try {
      const actualizada = await apiClient.patch<PlantillaDocumento>(`/documentos/plantillas/${plantillaId}`, form);
      setPlantilla(actualizada);
    } catch (err: any) {
      setErrorForm(err.message || "No se pudo guardar.");
    } finally {
      setGuardandoForm(false);
    }
  }

  async function subirBranding(tipo: "encabezado" | "pie" | "fondo", archivo: File) {
    if (!sesion?.institucionId) return;
    setSubiendoBranding(tipo);
    setErrorBranding(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const inst = await apiClient.postForm<Institucion>(`/instituciones/${sesion.institucionId}/branding/${tipo}`, fd);
      setInstitucion(inst);
    } catch (err: any) {
      setErrorBranding(err.message || "No se pudo subir la imagen. Si el backend corre en localhost, esto está bloqueado a propósito (protección anti-SSRF) hasta tener un dominio público real.");
    } finally {
      setSubiendoBranding(null);
    }
  }

  async function agregarSeccion() {
    setAgregando(true);
    setErrorAgregar(null);
    try {
      const payload: PlantillaSeccionCreate = {
        orden: secciones.length,
        tipo_seccion: nuevoTipo,
        titulo: nuevoTitulo || null,
      };
      const creada = await apiClient.post<PlantillaSeccion>(`/documentos/plantillas/${plantillaId}/secciones`, payload);
      setSecciones([...secciones, creada]);
      setNuevoTitulo("");
    } catch (err: any) {
      setErrorAgregar(err.message || "No se pudo agregar la sección.");
    } finally {
      setAgregando(false);
    }
  }

  async function moverSeccion(seccion: PlantillaSeccion, direccion: -1 | 1) {
    const idx = secciones.findIndex((s) => s.id === seccion.id);
    const vecino = secciones[idx + direccion];
    if (!vecino) return;
    try {
      const [a, b] = await Promise.all([
        apiClient.patch<PlantillaSeccion>(`/documentos/secciones/${seccion.id}`, { orden: vecino.orden }),
        apiClient.patch<PlantillaSeccion>(`/documentos/secciones/${vecino.id}`, { orden: seccion.orden }),
      ]);
      const copia = secciones.slice();
      copia[idx] = b;
      copia[idx + direccion] = a;
      setSecciones(copia.sort((x, y) => x.orden - y.orden));
    } catch (err: any) {
      setError(err.message || "No se pudo reordenar.");
    }
  }

  async function borrarSeccion(seccion: PlantillaSeccion) {
    if (!confirm(`¿Borrar la sección "${seccion.titulo || ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion]}"?`)) return;
    try {
      await apiClient.delete(`/documentos/secciones/${seccion.id}`);
      setSecciones(secciones.filter((s) => s.id !== seccion.id));
    } catch (err: any) {
      setError(err.message || "No se pudo borrar — puede que ya tenga contenido o un resultado vinculado en algún documento.");
    }
  }

  function abrirConfig(seccion: PlantillaSeccion) {
    setSeccionAbierta(seccionAbierta === seccion.id ? null : seccion.id);
    if (!(seccion.id in configTexto)) {
      setConfigTexto({ ...configTexto, [seccion.id]: JSON.stringify(seccion.config ?? {}, null, 2) });
    }
  }

  async function guardarTitulo(seccion: PlantillaSeccion, titulo: string) {
    try {
      const actualizada = await apiClient.patch<PlantillaSeccion>(`/documentos/secciones/${seccion.id}`, { titulo: titulo || null });
      setSecciones(secciones.map((s) => (s.id === seccion.id ? actualizada : s)));
    } catch (err: any) {
      setError(err.message || "No se pudo guardar el título.");
    }
  }

  async function guardarConfigJson(seccion: PlantillaSeccion) {
    setErrorSeccionId(null);
    try {
      const config = JSON.parse(configTexto[seccion.id] || "{}");
      const actualizada = await apiClient.patch<PlantillaSeccion>(`/documentos/secciones/${seccion.id}`, { config });
      setSecciones(secciones.map((s) => (s.id === seccion.id ? actualizada : s)));
    } catch (err: any) {
      setErrorSeccionId(seccion.id);
      setError(err instanceof SyntaxError ? "El JSON de configuración no es válido." : err.message || "No se pudo guardar.");
    }
  }

  // --- Config simple: encabezado / firma / grupo_campos (ver docstring de
  // PlantillaSeccion.config en el backend) ---
  async function guardarConfigObjeto(seccion: PlantillaSeccion, config: Record<string, unknown>) {
    try {
      const actualizada = await apiClient.patch<PlantillaSeccion>(`/documentos/secciones/${seccion.id}`, { config });
      setSecciones(secciones.map((s) => (s.id === seccion.id ? actualizada : s)));
      setConfigTexto({ ...configTexto, [seccion.id]: JSON.stringify(config, null, 2) });
    } catch (err: any) {
      setError(err.message || "No se pudo guardar.");
    }
  }

  if (cargando) return <div className="text-sm text-ink/60 dark:text-ink-dark/60">Cargando...</div>;
  if (!plantilla || !form) return <div><TextoError>{error}</TextoError></div>;

  const puedeEditarBranding = sesion?.rol === "admin" || sesion?.rol === "superadmin";

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <Migas items={[{ label: "Documentos", href: "/documentos" }, { label: plantilla.nombre }]} />
      <div>
        <Link href="/documentos" className="text-xs text-ink/50 dark:text-ink-dark/50 hover:underline">
          ← Documentos
        </Link>
        <h1 className="font-display text-2xl text-teal-900 dark:text-teal-accent-dark mt-1">{plantilla.nombre}</h1>
      </div>

      {/* 🆕 Estado activa/inactiva — ver docstring de alternarActiva() más
          arriba. Antes esta pantalla no lo mostraba en ningún lado. */}
      <div className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-4 flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <span
            className={`text-xs font-semibold rounded-full px-2.5 py-0.5 mt-0.5 whitespace-nowrap ${
              plantilla.activa ? "bg-teal-600 text-white" : "bg-mist dark:bg-surface-dark border border-border dark:border-border-dark text-ink/50 dark:text-ink-dark/50"
            }`}
          >
            {plantilla.activa ? "Activa" : "Inactiva"}
          </span>
          <div className="text-xs text-ink/55 dark:text-ink-dark/55 max-w-md">
            {plantilla.institucion_id === null ? (
              <p>
                Plantilla predeterminada del catálogo global — varias pueden estar activas a la vez para el mismo tipo
                de documento, es un menú, no compite con las demás.
              </p>
            ) : (
              <>
                <p>
                  Solo la plantilla <strong>activa</strong> de cada tipo de documento aparece al crear un documento
                  nuevo. Activar esta desactiva automáticamente cualquier otra plantilla activa del mismo tipo en tu
                  institución.
                </p>
                {plantilla.activa && secciones.length === 0 && (
                  <p className="text-red-700 font-medium mt-1">
                    ⚠ Está activa pero no tiene ninguna sección — un documento generado con ella saldría vacío.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
        <Boton variante={plantilla.activa ? "secundario" : "primario"} onClick={alternarActiva} disabled={alternandoActiva}>
          {alternandoActiva ? "Guardando..." : plantilla.activa ? "Desactivar" : "Activar"}
        </Boton>
      </div>
      <TextoError>{errorActiva}</TextoError>

      <TextoError>{error}</TextoError>

      {/* Tipografía y datos de la plantilla */}
      <form onSubmit={guardarForm} className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-4">
        <h2 className="font-display text-lg text-teal-900 dark:text-teal-accent-dark font-semibold border-b border-border dark:border-border-dark pb-2">
          Formato del documento
        </h2>

        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Nombre de la plantilla</span>
          <Input value={form.nombre ?? ""} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
        </label>

        <div className="grid sm:grid-cols-3 gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Tipo de letra</span>
            <Select value={form.fuente} onChange={(e) => setForm({ ...form, fuente: e.target.value })}>
              {FUENTES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Tamaño del cuerpo (pt)</span>
            <Input type="number" min={6} max={48} value={form.tamano_pt} onChange={(e) => setForm({ ...form, tamano_pt: Number(e.target.value) })} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Interlineado</span>
            <Input type="number" step={0.05} min={1} max={3} value={form.interlineado} onChange={(e) => setForm({ ...form, interlineado: Number(e.target.value) })} />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={!!form.justificado} onChange={(e) => setForm({ ...form, justificado: e.target.checked })} />
          Texto justificado
        </label>

        <div className="border-t border-border dark:border-border-dark pt-4 space-y-3">
          <p className="text-sm font-medium text-ink/70 dark:text-ink-dark/70">Título del documento (el grande, arriba de todo)</p>
          <div className="flex items-center gap-4 flex-wrap text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={!!form.titulo_negrita} onChange={(e) => setForm({ ...form, titulo_negrita: e.target.checked })} />
              Negrita
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={!!form.titulo_cursiva} onChange={(e) => setForm({ ...form, titulo_cursiva: e.target.checked })} />
              Cursiva
            </label>
            <label className="flex items-center gap-2">
              <span className="text-ink/70 dark:text-ink-dark/70">Tamaño (pt)</span>
              <Input
                type="number"
                min={6}
                max={72}
                className="w-20"
                placeholder="Auto"
                value={form.titulo_tamano_pt ?? ""}
                onChange={(e) => setForm({ ...form, titulo_tamano_pt: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
          </div>
          <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">Vacío = automático (tamaño del cuerpo + 5pt).</p>
        </div>

        <div className="border-t border-border dark:border-border-dark pt-4 space-y-3">
          <p className="text-sm font-medium text-ink/70 dark:text-ink-dark/70">Subtítulo de cada sección (ej. &quot;ANTECEDENTES FAMILIARES&quot;)</p>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-ink/70 dark:text-ink-dark/70">Tamaño (pt)</span>
            <Input
              type="number"
              min={6}
              max={48}
              className="w-20"
              placeholder="Auto"
              value={form.subtitulo_tamano_pt ?? ""}
              onChange={(e) => setForm({ ...form, subtitulo_tamano_pt: e.target.value ? Number(e.target.value) : null })}
            />
          </label>
          <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic">Vacío = automático (tamaño del cuerpo + 1pt). Siempre en negrita.</p>
        </div>

        <TextoError>{errorForm}</TextoError>
        <Boton type="submit" disabled={guardandoForm}>
          {guardandoForm ? "Guardando..." : "Guardar formato"}
        </Boton>
      </form>

      {/* Membrete / pie / fondo de página del colegio */}
      {puedeEditarBranding && (
        <section className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-4">
          <h2 className="font-display text-lg text-teal-900 dark:text-teal-accent-dark font-semibold border-b border-border dark:border-border-dark pb-2">
            Encabezado, pie y fondo de página
          </h2>
          <p className="text-xs text-ink/50 dark:text-ink-dark/50">
            Una imagen para el membrete (arriba de cada página), otra para el pie (abajo) y otra para el fondo de
            página completa — vale para todos los documentos de tu institución, no solo esta plantilla.
          </p>
          <TextoError>{errorBranding}</TextoError>
          <div className="grid sm:grid-cols-3 gap-4">
            {(["encabezado", "pie", "fondo"] as const).map((tipo) => {
              const urlActual =
                tipo === "encabezado"
                  ? institucion?.logo_url
                  : tipo === "pie"
                  ? institucion?.logo_pie_pagina_url
                  : institucion?.fondo_documento_url;
              return (
                <div key={tipo} className="space-y-2">
                  <span className="text-sm font-medium text-ink/70 dark:text-ink-dark/70 capitalize">{tipo}</span>
                  {urlActual ? (
                    <p className="text-xs text-teal-700 dark:text-teal-accent-dark">Imagen cargada ✓</p>
                  ) : (
                    <p className="text-xs text-ink/40 dark:text-ink-dark/40 italic">Sin imagen todavía</p>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    disabled={subiendoBranding === tipo}
                    onChange={(e) => e.target.files?.[0] && subirBranding(tipo, e.target.files[0])}
                    className="text-xs"
                  />
                </div>
              );
            })}
          </div>

          <div className="border-t border-border dark:border-border-dark pt-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!form.mostrar_fondo_institucion}
                onChange={(e) => setForm({ ...form, mostrar_fondo_institucion: e.target.checked })}
              />
              Mostrar el fondo de página en ESTA plantilla
            </label>
            <p className="text-xs text-ink/50 dark:text-ink-dark/50 italic mt-1">
              Apagado por defecto: un fondo detrás del texto afecta la legibilidad, así que cada plantilla lo activa
              a propósito. Se guarda junto con el resto del formato, con el botón &quot;Guardar formato&quot; de arriba.
            </p>
          </div>
        </section>
      )}

      {/* Secciones */}
      <section className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-6 space-y-4">
        <h2 className="font-display text-lg text-teal-900 dark:text-teal-accent-dark font-semibold border-b border-border dark:border-border-dark pb-2">Secciones</h2>

        <div className="flex items-end gap-3 flex-wrap border-b border-border dark:border-border-dark pb-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Tipo</span>
            <Select value={nuevoTipo} onChange={(e) => setNuevoTipo(e.target.value as TipoSeccionDocumento)}>
              {TIPOS_SECCION_ORDENADOS.map((t) => (
                <option key={t} value={t}>
                  {ETIQUETAS_TIPO_SECCION[t]}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-sm flex-1 min-w-[160px]">
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Título (opcional)</span>
            <Input value={nuevoTitulo} onChange={(e) => setNuevoTitulo(e.target.value)} placeholder="Ej. Motivo de evaluación" />
          </label>
          <Boton onClick={agregarSeccion} disabled={agregando}>
            {agregando ? "Agregando..." : "+ Agregar sección"}
          </Boton>
        </div>
        <TextoError>{errorAgregar}</TextoError>

        {secciones.length === 0 ? (
          <p className="text-sm text-ink/60 dark:text-ink-dark/60 italic py-2">Esta plantilla todavía no tiene secciones.</p>
        ) : (
          <div className="space-y-2">
            {secciones.map((seccion, idx) => (
              <div key={seccion.id} className="border border-border dark:border-border-dark rounded-card">
                <div className="flex items-center gap-2 p-3">
                  <div className="flex flex-col">
                    <button type="button" disabled={idx === 0} onClick={() => moverSeccion(seccion, -1)} className="text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:text-ink-dark disabled:opacity-20 text-xs leading-none">
                      ▲
                    </button>
                    <button type="button" disabled={idx === secciones.length - 1} onClick={() => moverSeccion(seccion, 1)} className="text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:text-ink-dark disabled:opacity-20 text-xs leading-none">
                      ▼
                    </button>
                  </div>
                  <span className="text-xs font-mono text-ink/40 dark:text-ink-dark/40 w-6">{idx + 1}.</span>
                  <span className="text-xs bg-mist dark:bg-surface-dark text-ink/60 dark:text-ink-dark/60 rounded px-2 py-0.5">{ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion]}</span>
                  <Input
                    value={seccion.titulo ?? ""}
                    placeholder="(sin título propio)"
                    onChange={(e) => setSecciones(secciones.map((s) => (s.id === seccion.id ? { ...s, titulo: e.target.value } : s)))}
                    onBlur={(e) => guardarTitulo(seccion, e.target.value)}
                    className="flex-1 text-sm"
                  />
                  {TIPOS_CON_CONFIG_SIMPLE.includes(seccion.tipo_seccion) && (
                    <button type="button" onClick={() => abrirConfig(seccion)} className="text-xs text-teal-700 dark:text-teal-accent-dark hover:underline whitespace-nowrap">
                      Configurar
                    </button>
                  )}
                  <button type="button" onClick={() => borrarSeccion(seccion)} className="text-xs text-red-600 hover:underline whitespace-nowrap">
                    Borrar
                  </button>
                </div>

                {seccionAbierta === seccion.id && (
                  <div className="border-t border-border dark:border-border-dark p-3 bg-mist/30 dark:bg-surface-dark/30">
                    <EditorConfigSeccion
                      seccion={seccion}
                      configTexto={configTexto[seccion.id] ?? "{}"}
                      onCambiarTexto={(v) => setConfigTexto({ ...configTexto, [seccion.id]: v })}
                      onGuardarJson={() => guardarConfigJson(seccion)}
                      onGuardarObjeto={(config) => guardarConfigObjeto(seccion, config)}
                      error={errorSeccionId === seccion.id}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// Formulario de `config` por tipo_seccion — uno estructurado por cada tipo
// que de verdad lo necesita (ver TIPOS_CON_CONFIG_SIMPLE); los seis
// restantes no tienen ningún formulario propio porque su config no existe
// o se resuelve del todo en el backend.
function EditorConfigSeccion({
  seccion,
  configTexto,
  onCambiarTexto,
  onGuardarJson,
  onGuardarObjeto,
  error,
}: {
  seccion: PlantillaSeccion;
  configTexto: string;
  onCambiarTexto: (v: string) => void;
  onGuardarJson: () => void;
  onGuardarObjeto: (config: Record<string, unknown>) => void;
  error: boolean;
}) {
  if (seccion.tipo_seccion === "encabezado") {
    const config = (seccion.config ?? {}) as { mostrar_anio_oficial?: boolean; mostrar_emisor?: boolean };
    return (
      <div className="space-y-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={!!config.mostrar_anio_oficial}
            onChange={(e) => onGuardarObjeto({ ...config, mostrar_anio_oficial: e.target.checked })}
          />
          Mostrar el año oficial (ej. &quot;Año de la Esperanza...&quot;)
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={config.mostrar_emisor !== false}
            onChange={(e) => onGuardarObjeto({ ...config, mostrar_emisor: e.target.checked })}
          />
          Mostrar &quot;DE: quien generó la versión&quot; bajo el título (apágalo si el documento ya firma al final)
        </label>
      </div>
    );
  }

  if (seccion.tipo_seccion === "firma") {
    const config = (seccion.config ?? {}) as { lineas_fijas?: string[] };
    const lineas = config.lineas_fijas ?? [];
    return (
      <EditorListaTexto
        etiqueta="Líneas fijas debajo del cargo (ej. «Departamento de Psicología»)"
        valores={lineas}
        onCambiar={(v) => onGuardarObjeto({ ...config, lineas_fijas: v })}
      />
    );
  }

  if (seccion.tipo_seccion === "grupo_campos") {
    const config = (seccion.config ?? {}) as { campos?: { etiqueta: string }[] };
    const etiquetas = (config.campos ?? []).map((c) => c.etiqueta);
    return (
      <EditorListaTexto
        etiqueta="Campos del cuadro (ej. «Nombre», «Edad», «Grado»)"
        valores={etiquetas}
        onCambiar={(v) => onGuardarObjeto({ campos: v.map((etiqueta) => ({ etiqueta })) })}
      />
    );
  }

  if (seccion.tipo_seccion === "tabla_dinamica") {
    return <EditorTablaDinamicaConfig config={(seccion.config ?? {}) as ConfigTablaDinamica} onGuardar={onGuardarObjeto} />;
  }

  if (seccion.tipo_seccion === "firma_doble") {
    return <EditorFirmaDobleConfig config={(seccion.config ?? {}) as ConfigFirmaDoble} onGuardar={onGuardarObjeto} />;
  }

  if (seccion.tipo_seccion === "firma_triple") {
    return <EditorFirmaTripleConfig config={(seccion.config ?? {}) as ConfigFirmaTriple} onGuardar={onGuardarObjeto} />;
  }

  if (seccion.tipo_seccion === "ficha_imprimible") {
    return <EditorFichaImprimibleConfig config={(seccion.config ?? {}) as ConfigFichaImprimible} onGuardar={onGuardarObjeto} />;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink/50 dark:text-ink-dark/50">
        Configuración avanzada en JSON — ver la sección &quot;{ETIQUETAS_TIPO_SECCION[seccion.tipo_seccion]}&quot; en
        docs/motor-documentos.md para el formato exacto.
      </p>
      <textarea
        rows={6}
        value={configTexto}
        onChange={(e) => onCambiarTexto(e.target.value)}
        className={`w-full rounded-card border px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-teal-400 ${
          error ? "border-red-400" : "border-border dark:border-border-dark"
        }`}
      />
      <Boton onClick={onGuardarJson}>Guardar configuración</Boton>
    </div>
  );
}

function EditorListaTexto({
  etiqueta,
  valores,
  onCambiar,
}: {
  etiqueta: string;
  valores: string[];
  onCambiar: (valores: string[]) => void;
}) {
  const [nuevo, setNuevo] = useState("");
  return (
    <div className="space-y-2 text-sm">
      <span className="text-ink/70 dark:text-ink-dark/70 font-medium">{etiqueta}</span>
      {valores.map((v, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            value={v}
            onChange={(e) => onCambiar(valores.map((x, j) => (j === i ? e.target.value : x)))}
            className="flex-1"
          />
          <button type="button" onClick={() => onCambiar(valores.filter((_, j) => j !== i))} className="text-xs text-red-600 hover:underline">
            Quitar
          </button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Input value={nuevo} onChange={(e) => setNuevo(e.target.value)} placeholder="Agregar..." className="flex-1" />
        <Boton
          type="button"
          onClick={() => {
            if (!nuevo.trim()) return;
            onCambiar([...valores, nuevo.trim()]);
            setNuevo("");
          }}
        >
          + Agregar
        </Boton>
      </div>
    </div>
  );
}

// --- tabla_dinamica / firma_doble / ficha_imprimible — ver docstring de
// PlantillaSeccion.config en backend/modulos/documentos/models.py para el
// shape exacto de cada uno. ---

type ConfigTablaDinamica = {
  columnas?: { titulo: string; origen?: "automatico" | "libre"; campo_automatico?: string }[];
  filas_desde_lista_estudiantes?: boolean;
};

function EditorTablaDinamicaConfig({ config, onGuardar }: { config: ConfigTablaDinamica; onGuardar: (c: Record<string, unknown>) => void }) {
  const columnas = config.columnas ?? [];
  function actualizarColumnas(nuevas: ConfigTablaDinamica["columnas"]) {
    onGuardar({ ...config, columnas: nuevas });
  }
  return (
    <div className="space-y-3 text-sm">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={!!config.filas_desde_lista_estudiantes}
          onChange={(e) => onGuardar({ ...config, filas_desde_lista_estudiantes: e.target.checked })}
        />
        Una fila por cada estudiante de la lista congelada del documento (en vez de filas libres)
      </label>

      <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Columnas</span>
      {columnas.map((col, i) => (
        <div key={i} className="flex items-center gap-2 flex-wrap border border-border dark:border-border-dark rounded-card p-2">
          <Input
            placeholder="Título de la columna"
            value={col.titulo}
            onChange={(e) => actualizarColumnas(columnas.map((c, j) => (j === i ? { ...c, titulo: e.target.value } : c)))}
            className="flex-1 min-w-[140px]"
          />
          <Select
            value={col.origen ?? "libre"}
            onChange={(e) => actualizarColumnas(columnas.map((c, j) => (j === i ? { ...c, origen: e.target.value as "automatico" | "libre" } : c)))}
          >
            <option value="libre">Libre (lo llena la psicóloga)</option>
            <option value="automatico">Automático</option>
          </Select>
          {col.origen === "automatico" && (
            <Select
              value={col.campo_automatico ?? "nombre_completo"}
              onChange={(e) => actualizarColumnas(columnas.map((c, j) => (j === i ? { ...c, campo_automatico: e.target.value } : c)))}
            >
              <option value="nombre_completo">Nombre completo</option>
              <option value="grado_seccion">Grado y sección</option>
            </Select>
          )}
          <button type="button" onClick={() => actualizarColumnas(columnas.filter((_, j) => j !== i))} className="text-xs text-red-600 hover:underline">
            Quitar
          </button>
        </div>
      ))}
      <Boton type="button" onClick={() => actualizarColumnas([...columnas, { titulo: "", origen: "libre" }])}>
        + Agregar columna
      </Boton>
    </div>
  );
}

type ConfigFirmaDoble = {
  izquierda?: { lineas_fijas?: string[] };
  derecha?: { cargo_fijo?: string; lineas_fijas?: string[] };
};

function EditorFirmaDobleConfig({ config, onGuardar }: { config: ConfigFirmaDoble; onGuardar: (c: Record<string, unknown>) => void }) {
  const izquierda = config.izquierda ?? {};
  const derecha = config.derecha ?? {};
  return (
    <div className="grid sm:grid-cols-2 gap-4 text-sm">
      <div className="space-y-2">
        <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Izquierda (siempre nombre/cargo del usuario responsable)</span>
        <EditorListaTexto
          etiqueta="Líneas fijas"
          valores={izquierda.lineas_fijas ?? []}
          onCambiar={(v) => onGuardar({ ...config, izquierda: { ...izquierda, lineas_fijas: v } })}
        />
      </div>
      <div className="space-y-2">
        <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Derecha (nunca lleva nombre de una persona)</span>
        <label className="flex flex-col gap-1">
          <span className="text-ink/70 dark:text-ink-dark/70 text-xs">Cargo (en negrita, ej. «Convivencia escolar»)</span>
          <Input
            value={derecha.cargo_fijo ?? ""}
            onChange={(e) => onGuardar({ ...config, derecha: { ...derecha, cargo_fijo: e.target.value } })}
          />
        </label>
        <EditorListaTexto
          etiqueta="Líneas fijas"
          valores={derecha.lineas_fijas ?? []}
          onCambiar={(v) => onGuardar({ ...config, derecha: { ...derecha, lineas_fijas: v } })}
        />
      </div>
    </div>
  );
}

type ConfigFirmaTriple = {
  izquierda?: { lineas_fijas?: string[] };
  derecha?: { cargo_fijo?: string; lineas_fijas?: string[] };
  centro?: { cargo_fijo?: string; lineas_fijas?: string[] };
};

// Igual que firma_doble (izquierda/derecha lado a lado) más un tercer
// bloque "centro", debajo y centrado a todo el ancho en el PDF — ver
// _renderizar_firma_triple en pdf_generador.py.
function EditorFirmaTripleConfig({ config, onGuardar }: { config: ConfigFirmaTriple; onGuardar: (c: Record<string, unknown>) => void }) {
  const izquierda = config.izquierda ?? {};
  const derecha = config.derecha ?? {};
  const centro = config.centro ?? {};
  return (
    <div className="space-y-4 text-sm">
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Izquierda (siempre nombre/cargo del usuario responsable)</span>
          <EditorListaTexto
            etiqueta="Líneas fijas"
            valores={izquierda.lineas_fijas ?? []}
            onCambiar={(v) => onGuardar({ ...config, izquierda: { ...izquierda, lineas_fijas: v } })}
          />
        </div>
        <div className="space-y-2">
          <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Derecha (nunca lleva nombre de una persona)</span>
          <label className="flex flex-col gap-1">
            <span className="text-ink/70 dark:text-ink-dark/70 text-xs">Cargo (en negrita)</span>
            <Input
              value={derecha.cargo_fijo ?? ""}
              onChange={(e) => onGuardar({ ...config, derecha: { ...derecha, cargo_fijo: e.target.value } })}
            />
          </label>
          <EditorListaTexto
            etiqueta="Líneas fijas"
            valores={derecha.lineas_fijas ?? []}
            onCambiar={(v) => onGuardar({ ...config, derecha: { ...derecha, lineas_fijas: v } })}
          />
        </div>
      </div>
      <div className="space-y-2 border-t border-border dark:border-border-dark pt-3">
        <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Centro (debajo, centrado a todo el ancho — tampoco lleva nombre de una persona)</span>
        <label className="flex flex-col gap-1">
          <span className="text-ink/70 dark:text-ink-dark/70 text-xs">Cargo (en negrita)</span>
          <Input
            value={centro.cargo_fijo ?? ""}
            onChange={(e) => onGuardar({ ...config, centro: { ...centro, cargo_fijo: e.target.value } })}
          />
        </label>
        <EditorListaTexto
          etiqueta="Líneas fijas"
          valores={centro.lineas_fijas ?? []}
          onCambiar={(v) => onGuardar({ ...config, centro: { ...centro, lineas_fijas: v } })}
        />
      </div>
    </div>
  );
}

type ConfigFichaImprimible = {
  campos_encabezado?: string[];
  leyenda?: string;
  columnas?: string[];
  filas?: string[];
  listas_checkbox?: { titulo: string; opciones: string[] }[];
  preguntas_abiertas?: string[];
  firmas_en_blanco?: string[];
};

function EditorFichaImprimibleConfig({ config, onGuardar }: { config: ConfigFichaImprimible; onGuardar: (c: Record<string, unknown>) => void }) {
  const listas = config.listas_checkbox ?? [];
  function actualizarListas(nuevas: ConfigFichaImprimible["listas_checkbox"]) {
    onGuardar({ ...config, listas_checkbox: nuevas });
  }
  return (
    <div className="space-y-4 text-sm">
      <p className="text-xs text-ink/50 dark:text-ink-dark/50">
        Formulario EN BLANCO para imprimir y completar a mano — nunca se llena desde la app, lo que configurás acá es
        exactamente lo que sale impreso.
      </p>
      <EditorListaTexto
        etiqueta="Campos del encabezado (línea en blanco para escribir, ej. «Estudiante»)"
        valores={config.campos_encabezado ?? []}
        onCambiar={(v) => onGuardar({ ...config, campos_encabezado: v })}
      />
      <label className="flex flex-col gap-1">
        <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Leyenda (línea fija, ej. la escala de valoración)</span>
        <Input value={config.leyenda ?? ""} onChange={(e) => onGuardar({ ...config, leyenda: e.target.value })} />
      </label>
      <div className="grid sm:grid-cols-2 gap-4">
        <EditorListaTexto
          etiqueta="Columnas de la tabla de verificación (ej. «Logrado», «En proceso»)"
          valores={config.columnas ?? []}
          onCambiar={(v) => onGuardar({ ...config, columnas: v })}
        />
        <EditorListaTexto
          etiqueta="Filas de la tabla (un indicador por fila)"
          valores={config.filas ?? []}
          onCambiar={(v) => onGuardar({ ...config, filas: v })}
        />
      </div>

      <div className="space-y-2">
        <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Listas de opciones con casillero [ ]</span>
        {listas.map((lista, i) => (
          <div key={i} className="border border-border dark:border-border-dark rounded-card p-2 space-y-2">
            <div className="flex items-center gap-2">
              <Input
                placeholder="Título de la lista"
                value={lista.titulo}
                onChange={(e) => actualizarListas(listas.map((l, j) => (j === i ? { ...l, titulo: e.target.value } : l)))}
                className="flex-1"
              />
              <button type="button" onClick={() => actualizarListas(listas.filter((_, j) => j !== i))} className="text-xs text-red-600 hover:underline">
                Quitar lista
              </button>
            </div>
            <EditorListaTexto
              etiqueta="Opciones"
              valores={lista.opciones}
              onCambiar={(v) => actualizarListas(listas.map((l, j) => (j === i ? { ...l, opciones: v } : l)))}
            />
          </div>
        ))}
        <Boton type="button" onClick={() => actualizarListas([...listas, { titulo: "", opciones: [] }])}>
          + Agregar lista de opciones
        </Boton>
      </div>

      <EditorListaTexto
        etiqueta="Preguntas abiertas (etiqueta + espacio en blanco para responder)"
        valores={config.preguntas_abiertas ?? []}
        onCambiar={(v) => onGuardar({ ...config, preguntas_abiertas: v })}
      />
      <EditorListaTexto
        etiqueta="Firmas en blanco (etiqueta + línea de firma, sin nombre real)"
        valores={config.firmas_en_blanco ?? []}
        onCambiar={(v) => onGuardar({ ...config, firmas_en_blanco: v })}
      />
    </div>
  );
}
