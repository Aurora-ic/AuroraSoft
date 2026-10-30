"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ShieldCheck, FileSignature, Baby, Building2, Layers, History, Info, Lock, ChevronDown } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Textarea } from "@/components/ui/Textarea";
import { EncabezadoPagina, ControlSegmentado } from "@/components/ui/Encabezado";
import type {
  AsentimientoInformadoTexto,
  AsentimientoInformadoTextoCreate,
  NivelEducativo,
  TipoTextoConsentimiento,
} from "@/types/api";

// Modelos de CONSENTIMIENTO (lo firma el apoderado) y ASENTIMIENTO (lo
// acepta el propio alumno) de cada colegio — versionados, nunca editados.
//
// Historia: esta pantalla nació (sesión 2026-10-18) solo para el texto de
// asentimiento que el alumno ve al abrir su link de examen; antes era una
// constante fija en el frontend. 🆕 Sesión 2026-10-30, a pedido del
// usuario: también el modelo de consentimiento del apoderado (se muestra al
// registrarlo en la ficha y se imprime como PDF para firmar), y uno
// distinto por NIVEL educativo si el colegio quiere — si un nivel no tiene
// el suyo, usa el general del colegio, y si tampoco hay, el global por
// defecto (crud.resolver_texto_consentimiento_activo en el backend).
//
// Crear una versión nueva desactiva la anterior DEL MISMO ámbito (tipo +
// nivel); nunca se edita una existente — el snapshot de qué versión vio un
// alumno (Inscripcion.asentimiento_texto_version_id) o respaldó un
// consentimiento registrado (ConsentimientoInformado.texto_version_id) queda
// fijo para siempre.

// Mismos marcadores que reemplaza core/pdf_consentimiento.py (MARCADORES).
const MARCADORES: { clave: string; descripcion: string }[] = [
  { clave: "alumno", descripcion: "Nombre completo del estudiante" },
  { clave: "documento_alumno", descripcion: "Documento de identidad del estudiante" },
  { clave: "grado_seccion", descripcion: "Nivel · grado · sección" },
  { clave: "nivel", descripcion: "Nivel educativo" },
  { clave: "institucion", descripcion: "Nombre del colegio" },
  { clave: "fecha", descripcion: "Fecha de emisión" },
];

const INFO_TIPO: Record<TipoTextoConsentimiento, { titulo: string; uso: string }> = {
  apoderado: {
    titulo: "Consentimiento del apoderado",
    uso: "Se muestra al registrar el consentimiento en la ficha del alumno y se imprime como PDF para que el apoderado lo firme.",
  },
  asentimiento: {
    titulo: "Asentimiento del estudiante",
    uso: "Es el texto que el alumno lee y acepta al abrir su link de evaluación (y el PDF de asentimiento desde su ficha).",
  },
};

// "general" = modelo del colegio sin nivel; si no, el id del nivel.
type Ambito = "general" | number;

export default function ConsentimientoYAsentimientoPage() {
  const { sesion } = useAuth();
  const puedeEditar = sesion?.rol === "admin" || sesion?.rol === "superadmin";

  const [tipo, setTipo] = useState<TipoTextoConsentimiento>("apoderado");
  const [ambito, setAmbito] = useState<Ambito>("general");

  const [versiones, setVersiones] = useState<AsentimientoInformadoTexto[] | null>(null);
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [contenido, setContenido] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorGuardar, setErrorGuardar] = useState<string | null>(null);
  const [mostrarHistorial, setMostrarHistorial] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function cargar() {
    if (!sesion?.institucionId) return;
    setCargando(true);
    setError(null);
    apiClient
      .get<AsentimientoInformadoTexto[]>(`/educativo/asentimiento-textos?institucion_id=${sesion.institucionId}`)
      .then(setVersiones)
      .catch((err: any) => setError(err.message || "No se pudo cargar el historial de versiones."))
      .finally(() => setCargando(false));
  }

  // 🔧 GET /educativo/asentimiento-textos exige SOLO_ADMINISTRATIVO
  // (admin/superadmin) en el backend, no solo el POST — para quien no puede
  // editar, ni siquiera se intenta pedir el historial (antes recibía siempre
  // un 403); se le muestra directamente el mensaje de "contacta a tu
  // administrador".
  useEffect(() => {
    if (!puedeEditar) {
      setCargando(false);
      return;
    }
    cargar();
    if (sesion?.institucionId) {
      apiClient
        .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
        .then(setNiveles)
        .catch(() => setNiveles([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sesion?.institucionId, puedeEditar]);

  const nivelDe = (a: Ambito) => (a === "general" ? null : a);

  // Versiones del tipo elegido, agrupadas por ámbito.
  const porAmbito = useMemo(() => {
    const mapa = new Map<string, AsentimientoInformadoTexto[]>();
    for (const v of versiones ?? []) {
      if (v.tipo_texto !== tipo) continue;
      const clave = v.nivel_educativo_id === null ? "general" : String(v.nivel_educativo_id);
      mapa.set(clave, [...(mapa.get(clave) ?? []), v]);
    }
    mapa.forEach((lista) => lista.sort((a, b) => b.version - a.version));
    return mapa;
  }, [versiones, tipo]);

  const activaDe = (a: Ambito) => (porAmbito.get(String(a)) ?? []).find((v) => v.activo) ?? null;
  const activaGeneral = activaDe("general");
  const activaAmbito = activaDe(ambito);
  const historialAmbito = porAmbito.get(String(ambito)) ?? [];

  // Lo que hoy rige en el ámbito elegido (propio o heredado).
  const heredadaDe = ambito !== "general" && !activaAmbito ? activaGeneral : null;

  // Al cambiar de tipo/ámbito (o al recargar), el editor parte del texto
  // vigente: el propio, o el heredado como punto de partida. Ajuste de
  // estado derivado durante el render (mismo patrón que Sidebar.tsx).
  const claveEditor = `${tipo}|${ambito}|${activaAmbito?.id ?? "-"}|${heredadaDe?.id ?? "-"}`;
  const [claveEditorAnterior, setClaveEditorAnterior] = useState("");
  if (versiones && claveEditor !== claveEditorAnterior) {
    setClaveEditorAnterior(claveEditor);
    setContenido((activaAmbito ?? heredadaDe)?.contenido ?? "");
    setErrorGuardar(null);
  }

  async function guardarNuevaVersion(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) return;
    setGuardando(true);
    setErrorGuardar(null);
    try {
      const payload: AsentimientoInformadoTextoCreate = {
        institucion_id: sesion.institucionId,
        contenido,
        tipo_texto: tipo,
        nivel_educativo_id: nivelDe(ambito),
      };
      await apiClient.post("/educativo/asentimiento-textos", payload);
      cargar();
    } catch (err: any) {
      setErrorGuardar(err.message || "No se pudo guardar la nueva versión.");
    } finally {
      setGuardando(false);
    }
  }

  function insertarMarcador(clave: string) {
    const marcador = `{{${clave}}}`;
    const ta = textareaRef.current;
    if (!ta) {
      setContenido((c) => c + marcador);
      return;
    }
    const ini = ta.selectionStart ?? contenido.length;
    const fin = ta.selectionEnd ?? contenido.length;
    const nuevo = contenido.slice(0, ini) + marcador + contenido.slice(fin);
    setContenido(nuevo);
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(ini + marcador.length, ini + marcador.length);
    });
  }

  const nombreAmbito = ambito === "general" ? "General del colegio" : niveles.find((n) => n.id === ambito)?.nombre ?? "Nivel";
  const sinCambios = (activaAmbito?.contenido ?? null) === contenido;

  // ------------------------------------------------------------------
  if (!puedeEditar) {
    return (
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        <EncabezadoPagina variante="destacado" icono={ShieldCheck} acento="violeta" titulo="Consentimiento y asentimiento" />
        <div className="flex items-start gap-3 rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-5">
          <Lock size={18} className="mt-0.5 shrink-0 text-ink/40 dark:text-ink-dark/40" aria-hidden="true" />
          <p className="m-0 text-sm text-ink/70 dark:text-ink-dark/70">
            Los modelos de consentimiento y asentimiento los configura el administrador de tu colegio. Contacta a tu
            administrador para configurar un texto propio. Desde la ficha de cada alumno puedes ver el modelo que le corresponde
            y descargarlo en PDF para firmar.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-4">
      <EncabezadoPagina variante="destacado"
        icono={ShieldCheck}
        acento="violeta"
        titulo="Consentimiento y asentimiento"
        descripcion="Los modelos de tu colegio — uno general y, si lo necesitas, uno distinto por nivel educativo."
      />

      <ControlSegmentado<TipoTextoConsentimiento>
        etiqueta="Tipo de modelo"
        valor={tipo}
        onCambiar={(t) => {
          setTipo(t);
          setMostrarHistorial(false);
        }}
        className="self-start"
        opciones={[
          { valor: "apoderado", etiqueta: "Consentimiento (apoderado)", icono: FileSignature },
          { valor: "asentimiento", etiqueta: "Asentimiento (estudiante)", icono: Baby },
        ]}
      />

      <p className="m-0 -mt-1 flex items-start gap-1.5 text-[12px] text-ink/55 dark:text-ink-dark/55">
        <Info size={13} className="mt-px shrink-0" aria-hidden="true" />
        {INFO_TIPO[tipo].uso}
      </p>

      <TextoError>{error}</TextoError>

      {cargando ? (
        <p className="text-sm text-ink/40 dark:text-ink-dark/40">Cargando...</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr] items-start">
          {/* ---------------- Ámbitos ---------------- */}
          <nav aria-label="Ámbito del modelo" className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-2">
            {(["general", ...niveles.map((n) => n.id)] as Ambito[]).map((a) => {
              const activa = activaDe(a);
              const seleccionado = a === ambito;
              const esGeneral = a === "general";
              const nombre = esGeneral ? "General del colegio" : niveles.find((n) => n.id === a)?.nombre ?? "Nivel";
              const Icono = esGeneral ? Building2 : Layers;
              return (
                <button
                  key={String(a)}
                  type="button"
                  onClick={() => {
                    setAmbito(a);
                    setMostrarHistorial(false);
                  }}
                  aria-current={seleccionado ? "true" : undefined}
                  className={`w-full text-left flex items-center gap-2.5 rounded-lg px-2.5 py-2 transition-colors ${
                    seleccionado
                      ? "bg-teal-600/[0.08] ring-1 ring-teal-600/40 dark:bg-teal-accent-dark/10 dark:ring-teal-accent-dark/40"
                      : "hover:bg-mist dark:hover:bg-surface-raised-dark"
                  } ${!esGeneral ? "ml-3 w-[calc(100%-0.75rem)]" : ""}`}
                >
                  <Icono size={15} className="shrink-0 text-teal-700 dark:text-teal-accent-dark" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-ink dark:text-ink-dark">{nombre}</span>
                    <span className="block text-[11px] text-ink/50 dark:text-ink-dark/50">
                      {activa ? `Modelo propio · v${activa.version}` : esGeneral ? "Usa el modelo por defecto" : "Usa el general"}
                    </span>
                  </span>
                  <span
                    aria-hidden="true"
                    className={`h-2 w-2 shrink-0 rounded-full ${activa ? "bg-teal-600 dark:bg-teal-accent-dark" : "bg-border dark:bg-border-dark"}`}
                  />
                </button>
              );
            })}
            {niveles.length === 0 && (
              <p className="m-0 px-2.5 py-2 text-[11.5px] text-ink/45 dark:text-ink-dark/45">
                Crea niveles en Estructura académica para tener un modelo distinto por nivel.
              </p>
            )}
          </nav>

          {/* ---------------- Editor ---------------- */}
          <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark overflow-hidden min-w-0">
            <header className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-border dark:border-border-dark bg-mist/50 dark:bg-surface-raised-dark">
              <div className="min-w-0">
                <h2 className="m-0 text-[15px] font-bold text-teal-900 dark:text-ink-dark">
                  {INFO_TIPO[tipo].titulo} — {nombreAmbito}
                </h2>
                <p className="m-0 text-[11.5px] text-ink/55 dark:text-ink-dark/55">
                  {activaAmbito
                    ? `Versión activa: v${activaAmbito.version}, desde el ${new Date(activaAmbito.creado_en).toLocaleDateString("es-PE")}`
                    : heredadaDe
                      ? `Sin modelo propio: hoy rige el general del colegio (v${heredadaDe.version}). Lo de abajo es un punto de partida.`
                      : ambito === "general"
                        ? "Sin modelo propio: rige el modelo por defecto de AuroraSoft, si existe."
                        : "Sin modelo propio ni general: rige el modelo por defecto de AuroraSoft, si existe."}
                </p>
              </div>
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                  activaAmbito
                    ? "bg-teal-600/10 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
                    : "bg-border text-ink/60 dark:bg-border-dark dark:text-ink-dark/60"
                }`}
              >
                {activaAmbito ? "Propio" : "Heredado"}
              </span>
            </header>

            <form onSubmit={guardarNuevaVersion} className="p-4 space-y-3">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45 mr-1">
                  Insertar dato:
                </span>
                {MARCADORES.map((m) => (
                  <button
                    key={m.clave}
                    type="button"
                    title={m.descripcion}
                    onClick={() => insertarMarcador(m.clave)}
                    className="rounded-md border border-border dark:border-border-dark px-2 py-0.5 font-mono text-[11px] text-teal-800 dark:text-teal-accent-dark hover:border-teal-400 hover:bg-teal-600/5"
                  >
                    {`{{${m.clave}}}`}
                  </button>
                ))}
              </div>
              <Textarea
                ref={textareaRef}
                required
                rows={14}
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                placeholder="Un párrafo por línea..."
                className="w-full font-[inherit] leading-relaxed"
              />
              <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50">
                Un párrafo por línea. Los datos entre llaves se completan solos en el PDF con los del alumno. Guardar crea una
                versión NUEVA de este ámbito y desactiva la anterior — nunca se edita una versión ya existente, para que quede
                registro de qué texto se usó en cada caso.
              </p>
              <TextoError>{errorGuardar}</TextoError>
              <div className="flex items-center gap-3 flex-wrap">
                <Boton type="submit" disabled={guardando || contenido.trim().length < 10 || sinCambios}>
                  {guardando
                    ? "Guardando..."
                    : activaAmbito
                      ? "Guardar nueva versión"
                      : ambito === "general"
                        ? "Crear modelo del colegio"
                        : `Crear modelo propio para ${nombreAmbito}`}
                </Boton>
                {sinCambios && activaAmbito && (
                  <span className="text-xs text-ink/45 dark:text-ink-dark/45">Sin cambios respecto de la versión activa.</span>
                )}
              </div>
            </form>

            {historialAmbito.length > 0 && (
              <div className="border-t border-border dark:border-border-dark">
                <button
                  type="button"
                  onClick={() => setMostrarHistorial((v) => !v)}
                  aria-expanded={mostrarHistorial}
                  className="w-full flex items-center gap-2 px-4 py-2.5 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70 hover:bg-mist/60 dark:hover:bg-surface-raised-dark"
                >
                  <History size={14} aria-hidden="true" />
                  Historial de versiones ({historialAmbito.length})
                  <ChevronDown size={14} aria-hidden="true" className={`ml-auto transition-transform ${mostrarHistorial ? "rotate-180" : ""}`} />
                </button>
                {mostrarHistorial && (
                  <div className="divide-y divide-border dark:divide-border-dark max-h-96 overflow-y-auto">
                    {historialAmbito.map((v) => (
                      <div key={v.id} className="px-4 py-3 text-sm">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-ink dark:text-ink-dark">
                            v{v.version}{" "}
                            {v.activo && (
                              <span className="ml-1 rounded-full bg-teal-600/10 px-2 py-0.5 text-[10.5px] font-semibold text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark">
                                activa
                              </span>
                            )}
                          </span>
                          <span className="text-xs text-ink/50 dark:text-ink-dark/50">{new Date(v.creado_en).toLocaleString("es-PE")}</span>
                        </div>
                        <p className="m-0 mt-1 text-xs text-ink/70 dark:text-ink-dark/70 whitespace-pre-line line-clamp-6">{v.contenido}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
