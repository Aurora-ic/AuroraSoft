"use client";

import { useEffect, useMemo, useState } from "react";
import { User, UsersRound, X, Search, School, GraduationCap, ListChecks, Check } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type { CitaCreate, Persona } from "@/types/api";

// 🆕 (sesión 2026-10-31, a pedido del usuario) Un solo modal para lo que se
// agenda desde la Agenda, con dos modos:
// - "individual": cita con UN estudiante — antes solo se podía desde su
//   ficha (estudiantes/[id]/cita/nueva); ahora también aquí, buscándolo.
//   Mismo payload que esa pantalla: persona_id + motivo + fecha + duración.
// - "grupal": taller/charla/reunión. Los asistentes ya no se marcan solo
//   uno por uno: "Por salón" (grado completo o secciones), "Todo el
//   colegio" o "Uno por uno" — se combinan, y todo termina en el mismo
//   `participantes_ids` de siempre (el backend no cambió: crud.crear_cita
//   descarta en silencio a cualquiera que no sea de la institución).
// Las secciones salen de `seccion_actual`, que ya viene en el padrón: no
// hay llamadas extra por salón.

export type ModoActividad = "individual" | "grupal";

export type InicialActividad = {
  modo: ModoActividad;
  fecha?: string; // "AAAA-MM-DD"
  persona?: Persona | null;
};

const TIPOS_ACTIVIDAD = ["Taller", "Charla", "Reunión", "Otro"];
const DURACIONES_RAPIDAS = [30, 45, 60, 90];
const DURACION_POR_MODO: Record<ModoActividad, string> = { individual: "45", grupal: "60" };

const COLOR_MODO: Record<ModoActividad, string> = {
  individual: "bg-teal-600 dark:bg-teal-accent-dark",
  grupal: "bg-[#2a78d6] dark:bg-[#5598e7]",
};

type PestanaAsistentes = "salon" | "colegio" | "uno";

function textoDuracion(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function ubicacionDe(p: Persona): string | null {
  const s = p.seccion_actual;
  return s ? [s.nivel_educativo, s.grado, s.seccion].filter(Boolean).join(" · ") : null;
}

function coincide(p: Persona, texto: string): boolean {
  const t = texto.trim().toLowerCase();
  if (!t) return true;
  return `${p.nombres} ${p.apellidos}`.toLowerCase().includes(t) || (p.documento_identidad ?? "").toLowerCase().includes(t);
}

type GrupoGrado = {
  clave: string;
  etiqueta: string; // "Secundaria · 3°"
  ids: number[];
  secciones: { id: number; nombre: string; ids: number[] }[];
};

// Checkbox con estado "parcial" (algunos del grupo marcados).
function CasillaGrupo({
  ids,
  seleccion,
  onCambiar,
  children,
  className = "",
}: {
  ids: number[];
  seleccion: Set<number>;
  onCambiar: (ids: number[], marcar: boolean) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const marcados = ids.filter((id) => seleccion.has(id)).length;
  const todos = ids.length > 0 && marcados === ids.length;
  const parcial = marcados > 0 && !todos;
  return (
    <label className={`flex items-center gap-2 cursor-pointer ${className}`}>
      <input
        type="checkbox"
        checked={todos}
        ref={(el) => {
          if (el) el.indeterminate = parcial;
        }}
        onChange={() => onCambiar(ids, !todos)}
        className="accent-[#2a78d6] h-4 w-4 shrink-0"
      />
      {children}
    </label>
  );
}

export function ModalNuevaActividad({
  inicial,
  personas,
  cargandoPersonas,
  errorPersonas,
  onCerrar,
  onCreada,
}: {
  inicial: InicialActividad;
  personas: Persona[];
  cargandoPersonas: boolean;
  errorPersonas: string | null;
  onCerrar: () => void;
  onCreada: (fechaHora: Date) => void;
}) {
  const [modo, setModo] = useState<ModoActividad>(inicial.modo);
  const [fecha, setFecha] = useState(inicial.fecha ?? "");
  const [hora, setHora] = useState("");
  const [duracion, setDuracion] = useState(DURACION_POR_MODO[inicial.modo]);
  // individual
  const [persona, setPersona] = useState<Persona | null>(inicial.persona ?? null);
  const [busquedaAlumno, setBusquedaAlumno] = useState("");
  const [motivo, setMotivo] = useState("");
  // grupal
  const [titulo, setTitulo] = useState("");
  const [tipo, setTipo] = useState("Taller");
  const [lugar, setLugar] = useState("");
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [pestana, setPestana] = useState<PestanaAsistentes>("salon");
  const [filtroUno, setFiltroUno] = useState("");

  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Esc cierra el modal.
  useEffect(() => {
    function alPresionar(e: KeyboardEvent) {
      if (e.key === "Escape") onCerrar();
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [onCerrar]);

  function cambiarModo(nuevo: ModoActividad) {
    // La duración por defecto sigue al modo mientras no se haya tocado.
    if (duracion === DURACION_POR_MODO[modo]) setDuracion(DURACION_POR_MODO[nuevo]);
    setModo(nuevo);
    setError(null);
  }

  // --- Grados y secciones a partir del padrón (seccion_actual) ---
  const grados = useMemo<GrupoGrado[]>(() => {
    const mapa = new Map<string, GrupoGrado & { orden: [number, number] }>();
    for (const p of personas) {
      const s = p.seccion_actual;
      if (!s) continue;
      const clave = `${s.nivel_educativo_id ?? "x"}-${s.grado_id ?? "x"}`;
      const g =
        mapa.get(clave) ??
        (() => {
          const nuevo = {
            clave,
            etiqueta: [s.nivel_educativo, s.grado].filter(Boolean).join(" · ") || "Sin grado",
            ids: [] as number[],
            secciones: [] as GrupoGrado["secciones"],
            orden: [s.nivel_educativo_id ?? 0, s.grado_id ?? 0] as [number, number],
          };
          mapa.set(clave, nuevo);
          return nuevo;
        })();
      g.ids.push(p.id);
      const sec =
        g.secciones.find((x) => x.id === s.seccion_id) ??
        (() => {
          const nueva = { id: s.seccion_id, nombre: s.seccion ?? "—", ids: [] as number[] };
          g.secciones.push(nueva);
          return nueva;
        })();
      sec.ids.push(p.id);
    }
    return Array.from(mapa.values())
      .sort((a, b) => a.orden[0] - b.orden[0] || a.orden[1] - b.orden[1])
      .map((g) => ({ ...g, secciones: g.secciones.sort((a, b) => a.nombre.localeCompare(b.nombre)) }));
  }, [personas]);

  const sinMatricula = useMemo(() => personas.filter((p) => !p.seccion_actual).length, [personas]);
  const todosLosIds = useMemo(() => personas.map((p) => p.id), [personas]);

  function cambiarGrupo(ids: number[], marcar: boolean) {
    setSeleccion((prev) => {
      const copia = new Set(prev);
      ids.forEach((id) => (marcar ? copia.add(id) : copia.delete(id)));
      return copia;
    });
  }

  const resultadosAlumno = useMemo(
    () => (busquedaAlumno.trim() ? personas.filter((p) => coincide(p, busquedaAlumno)).slice(0, 8) : []),
    [personas, busquedaAlumno],
  );
  const listaUno = useMemo(() => personas.filter((p) => coincide(p, filtroUno)), [personas, filtroUno]);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    if (modo === "individual" && !persona) return setError("Elige al estudiante de la cita.");
    if (modo === "individual" && !motivo.trim()) return setError("Indica el motivo de la cita.");
    if (modo === "grupal" && !titulo.trim()) return setError("Indica el título de la actividad.");
    if (!fecha || !hora) return setError("Indica la fecha y la hora.");
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) return setError("La fecha u hora ingresadas no son válidas.");
    const duracionMin = Number(duracion);
    if (!duracionMin || duracionMin < 5 || duracionMin > 720) return setError("La duración debe estar entre 5 y 720 minutos.");

    const payload: CitaCreate =
      modo === "individual"
        ? { persona_id: persona!.id, motivo: motivo.trim(), fecha_hora: fechaHora.toISOString(), duracion_minutos: duracionMin }
        : {
            motivo: titulo.trim(),
            titulo: titulo.trim(),
            tipo_actividad: tipo,
            lugar: lugar.trim() || null,
            fecha_hora: fechaHora.toISOString(),
            duracion_minutos: duracionMin,
            participantes_ids: Array.from(seleccion),
          };

    setGuardando(true);
    setError(null);
    try {
      await apiClient.post("/admin/personas/citas/", payload);
      onCreada(fechaHora);
    } catch (err) {
      setError((err instanceof Error && err.message) || "No se pudo agendar.");
    } finally {
      setGuardando(false);
    }
  }

  const clasePestana = (activa: boolean) =>
    `inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
      activa
        ? "bg-surface dark:bg-surface-dark text-[#1f63b8] dark:text-[#5598e7] shadow-sm"
        : "text-ink/55 dark:text-ink-dark/55 hover:text-ink dark:hover:text-ink-dark"
    }`;

  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 overflow-y-auto">
      <div className="fixed inset-0 bg-ink/45" aria-hidden="true" onClick={onCerrar} />
      <form
        onSubmit={guardar}
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-nueva-actividad"
        className="relative w-full max-w-3xl rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-xl text-sm"
      >
        {/* --- Cabecera + selector de modo --- */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
          <h2 id="titulo-nueva-actividad" className="m-0 flex items-center gap-2 font-display text-[17px] text-teal-900 dark:text-ink-dark font-semibold">
            <span className={`flex h-7 w-7 items-center justify-center rounded-lg text-white ${COLOR_MODO[modo]}`}>
              {modo === "individual" ? <User size={15} aria-hidden="true" /> : <UsersRound size={15} aria-hidden="true" />}
            </span>
            {modo === "individual" ? "Nueva cita individual" : "Nueva actividad grupal"}
          </h2>
          <div className="flex items-center gap-2">
            <div role="radiogroup" aria-label="Tipo" className="inline-flex rounded-xl bg-mist dark:bg-surface-raised-dark p-1">
              {(["individual", "grupal"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={modo === m}
                  onClick={() => cambiarModo(m)}
                  className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    modo === m ? "bg-surface dark:bg-surface-dark text-teal-900 dark:text-ink-dark shadow-sm" : "text-ink/55 dark:text-ink-dark/55"
                  }`}
                >
                  <span aria-hidden="true" className={`h-2 w-2 rounded-full ${COLOR_MODO[m]}`} />
                  {m === "individual" ? "Cita individual" : "Actividad grupal"}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onCerrar}
              className="rounded-lg p-1.5 text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
              aria-label="Cerrar"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* --- Estudiante (individual) --- */}
          {modo === "individual" && (
            <div className="flex flex-col gap-1">
              <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Estudiante</span>
              {persona ? (
                <div className="flex items-center gap-3 rounded-xl border border-teal-600/30 bg-teal-600/[0.05] dark:border-teal-accent-dark/30 dark:bg-teal-accent-dark/10 px-3 py-2.5">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-teal-600/15 text-[12px] font-bold text-teal-800 dark:text-teal-accent-dark">
                    {`${persona.nombres[0] ?? ""}${persona.apellidos[0] ?? ""}`.toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="m-0 font-semibold text-teal-900 dark:text-ink-dark truncate">
                      {persona.nombres} {persona.apellidos}
                    </p>
                    <p className="m-0 text-[11.5px] text-ink/55 dark:text-ink-dark/55">{ubicacionDe(persona) ?? "Sin matrícula"}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPersona(null)}
                    className="text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
                  >
                    Cambiar
                  </button>
                </div>
              ) : (
                <div>
                  <div className="relative">
                    <Search size={14} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" />
                    <Input
                      autoFocus
                      aria-label="Buscar estudiante"
                      placeholder={cargandoPersonas ? "Cargando padrón..." : "Busca por nombre, apellido o documento"}
                      value={busquedaAlumno}
                      onChange={(e) => setBusquedaAlumno(e.target.value)}
                      className="w-full pl-9"
                    />
                  </div>
                  {resultadosAlumno.length > 0 && (
                    <ul className="m-0 mt-1.5 list-none p-0 max-h-56 overflow-y-auto rounded-lg border border-border dark:border-border-dark divide-y divide-border/70 dark:divide-border-dark">
                      {resultadosAlumno.map((p) => (
                        <li key={p.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setPersona(p);
                              setBusquedaAlumno("");
                            }}
                            className="w-full text-left flex items-center justify-between gap-3 px-3 py-2 hover:bg-mist dark:hover:bg-surface-raised-dark"
                          >
                            <span className="font-medium text-ink dark:text-ink-dark truncate">
                              {p.nombres} {p.apellidos}
                            </span>
                            <span className="shrink-0 text-[11px] text-ink/45 dark:text-ink-dark/45">{ubicacionDe(p) ?? "Sin matrícula"}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {busquedaAlumno.trim() && resultadosAlumno.length === 0 && !cargandoPersonas && (
                    <p className="m-0 mt-1.5 text-xs text-ink/45 dark:text-ink-dark/45">Ningún estudiante activo coincide.</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* --- Datos de la cita / actividad --- */}
          <div className="grid sm:grid-cols-2 gap-3">
            {modo === "individual" ? (
              <CampoEditable etiqueta="Motivo" className="sm:col-span-2">
                <Input required placeholder="Ej. Seguimiento de resultados" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </CampoEditable>
            ) : (
              <>
                <CampoEditable etiqueta="Título (obligatorio)" className="sm:col-span-2">
                  <Input
                    required
                    autoFocus
                    placeholder="Ej. Taller de habilidades sociales"
                    value={titulo}
                    onChange={(e) => setTitulo(e.target.value)}
                  />
                </CampoEditable>
                <CampoEditable etiqueta="Tipo">
                  <Select value={tipo} onChange={(e) => setTipo(e.target.value)}>
                    {TIPOS_ACTIVIDAD.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </Select>
                </CampoEditable>
                <CampoEditable etiqueta="Lugar (opcional)">
                  <Input placeholder="Ej. Auditorio" value={lugar} onChange={(e) => setLugar(e.target.value)} />
                </CampoEditable>
              </>
            )}
            <CampoEditable etiqueta="Fecha">
              <Input type="date" required value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </CampoEditable>
            <CampoEditable etiqueta="Hora">
              <Input type="time" required value={hora} onChange={(e) => setHora(e.target.value)} />
            </CampoEditable>
            <div className="sm:col-span-2 flex flex-col gap-1">
              <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Duración</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {DURACIONES_RAPIDAS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDuracion(String(d))}
                    aria-pressed={duracion === String(d)}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      duracion === String(d)
                        ? "border-accion bg-accion text-white dark:border-teal-accent-dark dark:bg-teal-accent-dark dark:text-mist-dark"
                        : "border-border dark:border-border-dark text-ink/70 dark:text-ink-dark/70 hover:border-teal-400"
                    }`}
                  >
                    {textoDuracion(d)}
                  </button>
                ))}
                <span className="flex items-center gap-1.5 text-xs text-ink/50 dark:text-ink-dark/50">
                  u otra:
                  <Input
                    type="number"
                    min={5}
                    max={720}
                    aria-label="Duración en minutos"
                    value={duracion}
                    onChange={(e) => setDuracion(e.target.value)}
                    className="w-20"
                  />
                  min
                </span>
              </div>
            </div>
          </div>

          {/* --- Asistentes (grupal) --- */}
          {modo === "grupal" && (
            <div className="rounded-xl border border-border dark:border-border-dark overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 bg-mist/60 dark:bg-surface-raised-dark border-b border-border dark:border-border-dark">
                <div className="min-w-0">
                  <p className="m-0 text-[12.5px] font-bold text-teal-900 dark:text-ink-dark">
                    Asistentes <span className="font-normal text-ink/50 dark:text-ink-dark/50">(opcional)</span>
                  </p>
                  <p className="m-0 text-[11.5px] text-ink/55 dark:text-ink-dark/55" aria-live="polite">
                    {seleccion.size === 0 ? (
                      "Nadie seleccionado — puedes crearla sin asistentes."
                    ) : (
                      <>
                        <strong className="text-[#1f63b8] dark:text-[#5598e7]">{seleccion.size}</strong> estudiante(s) seleccionado(s) ·{" "}
                        <button type="button" onClick={() => setSeleccion(new Set())} className="font-semibold underline hover:no-underline">
                          quitar todos
                        </button>
                      </>
                    )}
                  </p>
                </div>
                <div role="tablist" aria-label="Elegir asistentes" className="inline-flex rounded-xl bg-border/50 dark:bg-surface-dark p-1">
                  <button type="button" role="tab" aria-selected={pestana === "salon"} onClick={() => setPestana("salon")} className={clasePestana(pestana === "salon")}>
                    <GraduationCap size={13} aria-hidden="true" />
                    Por salón
                  </button>
                  <button type="button" role="tab" aria-selected={pestana === "colegio"} onClick={() => setPestana("colegio")} className={clasePestana(pestana === "colegio")}>
                    <School size={13} aria-hidden="true" />
                    Todo el colegio
                  </button>
                  <button type="button" role="tab" aria-selected={pestana === "uno"} onClick={() => setPestana("uno")} className={clasePestana(pestana === "uno")}>
                    <ListChecks size={13} aria-hidden="true" />
                    Uno por uno
                  </button>
                </div>
              </div>

              <div className="p-3">
                <TextoError>{errorPersonas}</TextoError>
                {cargandoPersonas ? (
                  <p className="m-0 text-xs text-ink/40 dark:text-ink-dark/40">Cargando padrón...</p>
                ) : personas.length === 0 ? (
                  <p className="m-0 text-xs italic text-ink/40 dark:text-ink-dark/40">No hay estudiantes activos en el padrón todavía.</p>
                ) : pestana === "salon" ? (
                  grados.length === 0 ? (
                    <p className="m-0 text-xs italic text-ink/45 dark:text-ink-dark/45">Ningún estudiante tiene matrícula vigente todavía — usa “Uno por uno”.</p>
                  ) : (
                    <div className="max-h-64 overflow-y-auto space-y-2 pr-1">
                      {grados.map((g) => (
                        <div key={g.clave} className="rounded-lg border border-border dark:border-border-dark">
                          <CasillaGrupo
                            ids={g.ids}
                            seleccion={seleccion}
                            onCambiar={cambiarGrupo}
                            className="px-3 py-2 bg-mist/40 dark:bg-surface-raised-dark rounded-t-lg"
                          >
                            <span className="flex-1 text-[12.5px] font-semibold text-ink dark:text-ink-dark">{g.etiqueta} — grado completo</span>
                            <span className="text-[11px] font-semibold text-ink/45 dark:text-ink-dark/45">{g.ids.length}</span>
                          </CasillaGrupo>
                          <div className="flex flex-wrap gap-1.5 px-3 py-2">
                            {g.secciones.map((s) => {
                              const marcados = s.ids.filter((id) => seleccion.has(id)).length;
                              const todos = marcados === s.ids.length;
                              return (
                                <button
                                  key={s.id}
                                  type="button"
                                  aria-pressed={todos}
                                  onClick={() => cambiarGrupo(s.ids, !todos)}
                                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold transition-colors ${
                                    todos
                                      ? "border-[#2a78d6] bg-[#2a78d6] text-white dark:border-[#5598e7] dark:bg-[#5598e7] dark:text-surface-dark"
                                      : marcados > 0
                                        ? "border-[#2a78d6]/60 bg-[#2a78d6]/10 text-[#1f63b8] dark:text-[#5598e7]"
                                        : "border-border dark:border-border-dark text-ink/70 dark:text-ink-dark/70 hover:border-[#2a78d6]/60"
                                  }`}
                                >
                                  {todos && <Check size={12} strokeWidth={3} aria-hidden="true" />}
                                  Sección {s.nombre}
                                  <span className={todos ? "opacity-80" : "text-ink/40 dark:text-ink-dark/40"}>
                                    {marcados > 0 && !todos ? `${marcados}/${s.ids.length}` : s.ids.length}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                      {sinMatricula > 0 && (
                        <p className="m-0 text-[11.5px] text-ink/45 dark:text-ink-dark/45">
                          {sinMatricula} estudiante(s) sin matrícula no aparecen aquí — búscalos en “Uno por uno”.
                        </p>
                      )}
                    </div>
                  )
                ) : pestana === "colegio" ? (
                  <CasillaGrupo
                    ids={todosLosIds}
                    seleccion={seleccion}
                    onCambiar={cambiarGrupo}
                    className="rounded-lg border border-border dark:border-border-dark px-3 py-3 hover:bg-mist/50 dark:hover:bg-surface-raised-dark"
                  >
                    <span className="flex-1">
                      <span className="block text-[13px] font-semibold text-ink dark:text-ink-dark">Todos los estudiantes activos</span>
                      <span className="block text-[11.5px] text-ink/50 dark:text-ink-dark/50">
                        {todosLosIds.length} estudiante(s) del padrón, de todos los niveles y grados.
                      </span>
                    </span>
                  </CasillaGrupo>
                ) : (
                  <div>
                    <div className="relative mb-2">
                      <Search size={14} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" />
                      <Input
                        aria-label="Filtrar estudiantes"
                        placeholder="Buscar…"
                        value={filtroUno}
                        onChange={(e) => setFiltroUno(e.target.value)}
                        className="w-full pl-9"
                      />
                    </div>
                    <div className="max-h-56 overflow-y-auto rounded-lg border border-border dark:border-border-dark grid sm:grid-cols-2">
                      {listaUno.map((p) => (
                        <label
                          key={p.id}
                          className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-ink dark:text-ink-dark hover:bg-mist/60 dark:hover:bg-surface-raised-dark cursor-pointer border-b border-border/60 dark:border-border-dark"
                        >
                          <input type="checkbox" checked={seleccion.has(p.id)} onChange={() => cambiarGrupo([p.id], !seleccion.has(p.id))} className="accent-[#2a78d6]" />
                          <span className="min-w-0 flex-1 truncate">
                            {p.nombres} {p.apellidos}
                          </span>
                          <span className="shrink-0 text-[10.5px] text-ink/40 dark:text-ink-dark/40">{ubicacionDe(p) ?? "—"}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <TextoError>{error}</TextoError>
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-3.5 border-t border-border dark:border-border-dark bg-mist/40 dark:bg-surface-raised-dark rounded-b-2xl">
          <button type="button" onClick={onCerrar} className="text-sm font-medium text-ink/60 dark:text-ink-dark/60 hover:underline">
            Cancelar
          </button>
          <Boton type="submit" disabled={guardando}>
            {guardando
              ? "Guardando..."
              : modo === "individual"
                ? "Agendar cita"
                : seleccion.size > 0
                  ? `Crear actividad (${seleccion.size} asistentes)`
                  : "Crear actividad"}
          </Boton>
        </div>
      </form>
    </div>
  );
}
