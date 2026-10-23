"use client";

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Cita, CitaCreate, CitaUpdate, Persona } from "@/types/api";

const TIPOS_ACTIVIDAD = ["Taller", "Charla", "Reunión", "Otro"];

const NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

function inicioDeSemana(fecha: Date): Date {
  const d = new Date(fecha);
  d.setHours(0, 0, 0, 0);
  // getDay(): 0=domingo..6=sábado -> distancia hasta el lunes anterior (o el mismo día).
  const distanciaHastaLunes = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - distanciaHastaLunes);
  return d;
}

function mismoDia(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// Vista semanal hecha a mano (sin librería de calendario) — basta para lo
// que un psicólogo necesita de su agenda: ver de un vistazo qué tiene esta
// semana, moverse semana a semana, reprogramar/cancelar sin salir de aquí.
export default function AgendaPage() {
  const { sesion } = useAuth();
  const [citas, setCitas] = useState<Cita[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [semanaOffset, setSemanaOffset] = useState(0);

  const [reprogramandoId, setReprogramandoId] = useState<number | null>(null);
  const [formReprogramar, setFormReprogramar] = useState({ fecha: "", hora: "", titulo: "", tipo_actividad: "", lugar: "" });
  const [guardando, setGuardando] = useState(false);

  // --- Actividad grupal (taller, charla, otro) — a diferencia de una cita
  // individual, NO se agenda "poniendo en cada estudiante" uno por uno:
  // se crea directamente aquí, en la agenda, con una lista de asistentes
  // OPCIONAL (puede quedar vacía). Es visible para todo el staff de la
  // institución apenas se crea (GET /citas/mi-agenda ya la incluye),
  // mientras que una cita individual sigue siendo privada de quien la
  // agendó. ---
  const [formularioActividad, setFormularioActividad] = useState<{
    titulo: string;
    tipo_actividad: string;
    fecha: string;
    hora: string;
    lugar: string;
    participantes_ids: Set<number>;
  } | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [cargandoPersonas, setCargandoPersonas] = useState(false);
  const [errorPersonas, setErrorPersonas] = useState<string | null>(null);
  const [guardandoActividad, setGuardandoActividad] = useState(false);
  const [errorFormularioActividad, setErrorFormularioActividad] = useState<string | null>(null);

  function cargar() {
    setCargando(true);
    setError(null);
    apiClient
      .get<Cita[]>("/admin/personas/citas/mi-agenda")
      .then(setCitas)
      .catch((err) => setError(err.message || "No se pudo cargar la agenda."))
      .finally(() => setCargando(false));
  }

  useEffect(cargar, []);

  const inicioSemanaVisible = useMemo(() => {
    const hoy = inicioDeSemana(new Date());
    hoy.setDate(hoy.getDate() + semanaOffset * 7);
    return hoy;
  }, [semanaOffset]);

  const diasVisibles = useMemo(
    () => Array.from({ length: 7 }, (_, i) => {
      const d = new Date(inicioSemanaVisible);
      d.setDate(d.getDate() + i);
      return d;
    }),
    [inicioSemanaVisible],
  );

  const citasPorDia = useMemo(() => {
    const mapa = new Map<number, Cita[]>();
    for (const dia of diasVisibles) {
      const delDia = citas
        .filter((c) => mismoDia(new Date(c.fecha_hora), dia))
        .sort((a, b) => new Date(a.fecha_hora).getTime() - new Date(b.fecha_hora).getTime());
      mapa.set(dia.getTime(), delDia);
    }
    return mapa;
  }, [citas, diasVisibles]);

  async function cancelar(citaId: number) {
    if (!window.confirm("¿Cancelar esta cita?")) return;
    try {
      await apiClient.delete(`/admin/personas/citas/${citaId}`);
      cargar();
    } catch (err: any) {
      setError(err.message || "No se pudo cancelar la cita.");
    }
  }

  function abrirReprogramar(cita: Cita) {
    const fechaHora = new Date(cita.fecha_hora);
    setFormReprogramar({
      fecha: Number.isNaN(fechaHora.getTime()) ? "" : fechaHora.toISOString().slice(0, 10),
      hora: Number.isNaN(fechaHora.getTime()) ? "" : fechaHora.toTimeString().slice(0, 5),
      titulo: cita.titulo ?? "",
      tipo_actividad: cita.tipo_actividad ?? "",
      lugar: cita.lugar ?? "",
    });
    setError(null);
    setReprogramandoId(cita.id);
  }

  // Para una cita individual solo reprograma fecha/hora, igual que siempre.
  // Para una actividad grupal (persona_id null) también deja editar
  // título/tipo/lugar -- el mismo botón pasa a mostrarse como "Editar" en
  // ese caso (ver JSX más abajo).
  async function guardarReprogramacion(e: React.FormEvent, cita: Cita) {
    e.preventDefault();
    const { fecha, hora, titulo, tipo_actividad, lugar } = formReprogramar;
    if (!fecha || !hora) {
      setError("Indica la fecha y la hora.");
      return;
    }
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) {
      setError("La fecha u hora ingresadas no son válidas.");
      return;
    }
    const esGrupal = cita.persona_id === null;
    if (esGrupal && !titulo.trim()) {
      setError("El título de la actividad no puede quedar vacío.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const payload: CitaUpdate = { fecha_hora: fechaHora.toISOString() };
      if (esGrupal) {
        payload.titulo = titulo;
        payload.tipo_actividad = tipo_actividad || null;
        payload.lugar = lugar || null;
      }
      await apiClient.patch(`/admin/personas/citas/${cita.id}`, payload);
      setReprogramandoId(null);
      cargar();
    } catch (err: any) {
      setError(err.message || "No se pudo guardar los cambios.");
    } finally {
      setGuardando(false);
    }
  }

  function abrirFormularioActividad() {
    setFormularioActividad({ titulo: "", tipo_actividad: "Taller", fecha: "", hora: "", lugar: "", participantes_ids: new Set() });
    setErrorFormularioActividad(null);
    // Carga perezosa del padrón — solo cuando de verdad se va a elegir
    // asistentes, no en cada carga de la agenda.
    if (personas.length === 0 && sesion?.institucionId) {
      setCargandoPersonas(true);
      apiClient
        .getTodasLasPaginas<Persona>(`/admin/personas/${sesion.institucionId}`)
        .then(setPersonas)
        .catch((err: any) => setErrorPersonas(err.message || "No se pudo cargar el padrón."))
        .finally(() => setCargandoPersonas(false));
    }
  }

  function alternarParticipante(personaId: number) {
    setFormularioActividad((f) => {
      if (!f) return f;
      const copia = new Set(f.participantes_ids);
      if (copia.has(personaId)) copia.delete(personaId);
      else copia.add(personaId);
      return { ...f, participantes_ids: copia };
    });
  }

  async function guardarActividad(e: React.FormEvent) {
    e.preventDefault();
    if (!formularioActividad) return;
    const { titulo, tipo_actividad, fecha, hora, lugar, participantes_ids } = formularioActividad;
    if (!titulo.trim() || !fecha || !hora) {
      setErrorFormularioActividad("Indica al menos el título, la fecha y la hora.");
      return;
    }
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) {
      setErrorFormularioActividad("La fecha u hora ingresadas no son válidas.");
      return;
    }
    setGuardandoActividad(true);
    setErrorFormularioActividad(null);
    try {
      const payload: CitaCreate = {
        motivo: titulo,
        titulo,
        tipo_actividad,
        lugar: lugar || null,
        fecha_hora: fechaHora.toISOString(),
        participantes_ids: Array.from(participantes_ids),
      };
      await apiClient.post("/admin/personas/citas/", payload);
      setFormularioActividad(null);
      cargar();
    } catch (err: any) {
      setErrorFormularioActividad(err.message || "No se pudo crear la actividad.");
    } finally {
      setGuardandoActividad(false);
    }
  }

  const hoy = new Date();
  const finSemana = diasVisibles[6];

  return (
    <div>
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <h1 className="font-display text-2xl text-teal-900">Mi agenda</h1>
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => setSemanaOffset((v) => v - 1)}
            className="rounded-card border border-border px-3 py-1.5 hover:bg-mist"
          >
            ← Anterior
          </button>
          <button
            onClick={() => setSemanaOffset(0)}
            className="rounded-card border border-border px-3 py-1.5 hover:bg-mist disabled:opacity-40"
            disabled={semanaOffset === 0}
          >
            Esta semana
          </button>
          <button
            onClick={() => setSemanaOffset((v) => v + 1)}
            className="rounded-card border border-border px-3 py-1.5 hover:bg-mist"
          >
            Siguiente →
          </button>
          {!formularioActividad && <Boton onClick={abrirFormularioActividad}>+ Nueva actividad</Boton>}
        </div>
      </div>
      <p className="text-sm text-ink/60 mb-6">
        {inicioSemanaVisible.toLocaleDateString("es-PE", { day: "numeric", month: "long" })} –{" "}
        {finSemana.toLocaleDateString("es-PE", { day: "numeric", month: "long", year: "numeric" })}. Para una cita
        individual, hazlo desde la ficha del alumno correspondiente (botón &quot;+ Nueva Cita&quot;). Para un taller,
        charla u otra actividad que no es de un solo alumno, usa &quot;+ Nueva actividad&quot; aquí mismo — la ven
        todos en tu institución, no solo quien la crea.
      </p>

      {formularioActividad && (
        <form
          onSubmit={guardarActividad}
          className="bg-white rounded-card border border-border p-5 mb-6 space-y-4 text-sm"
        >
          <h2 className="font-display text-lg text-teal-900 font-semibold">Nueva actividad grupal</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <CampoEditable etiqueta="Título (obligatorio)">
              <Input
                required
                placeholder="Ej. Taller de habilidades sociales"
                value={formularioActividad.titulo}
                onChange={(e) => setFormularioActividad({ ...formularioActividad, titulo: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Tipo">
              <Select
                value={formularioActividad.tipo_actividad}
                onChange={(e) => setFormularioActividad({ ...formularioActividad, tipo_actividad: e.target.value })}
              >
                {TIPOS_ACTIVIDAD.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </Select>
            </CampoEditable>
            <CampoEditable etiqueta="Fecha">
              <Input
                type="date"
                required
                value={formularioActividad.fecha}
                onChange={(e) => setFormularioActividad({ ...formularioActividad, fecha: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Hora">
              <Input
                type="time"
                required
                value={formularioActividad.hora}
                onChange={(e) => setFormularioActividad({ ...formularioActividad, hora: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Lugar (opcional)" className="sm:col-span-2">
              <Input
                placeholder="Ej. Auditorio, Sala de usos múltiples..."
                value={formularioActividad.lugar}
                onChange={(e) => setFormularioActividad({ ...formularioActividad, lugar: e.target.value })}
              />
            </CampoEditable>
          </div>

          <div>
            <span className="block text-xs font-medium text-ink/50 uppercase tracking-wide mb-1.5">
              Estudiantes asistentes (opcional)
            </span>
            <TextoError>{errorPersonas}</TextoError>
            {cargandoPersonas ? (
              <p className="text-xs text-ink/40">Cargando padrón...</p>
            ) : personas.length === 0 ? (
              <p className="text-xs text-ink/40 italic">No hay estudiantes en el padrón todavía.</p>
            ) : (
              <div className="max-h-48 overflow-y-auto border border-border rounded-card divide-y divide-border">
                {personas.map((p) => (
                  <label key={p.id} className="flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-mist/40 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formularioActividad.participantes_ids.has(p.id)}
                      onChange={() => alternarParticipante(p.id)}
                    />
                    {p.nombres} {p.apellidos}
                  </label>
                ))}
              </div>
            )}
            {formularioActividad.participantes_ids.size > 0 && (
              <p className="text-xs text-ink/50 mt-1">
                {formularioActividad.participantes_ids.size} estudiante(s) seleccionado(s).
              </p>
            )}
          </div>

          <TextoError>{errorFormularioActividad}</TextoError>

          <div className="flex items-center gap-3">
            <Boton type="submit" disabled={guardandoActividad}>
              {guardandoActividad ? "Creando..." : "Crear actividad"}
            </Boton>
            <button
              type="button"
              onClick={() => setFormularioActividad(null)}
              className="text-sm text-ink/60 hover:underline"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <TextoError className="mb-4">{error}</TextoError>

      {cargando ? (
        <p className="text-sm text-ink/40">Cargando...</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-7 gap-3">
          {diasVisibles.map((dia, i) => {
            const esHoy = mismoDia(dia, hoy);
            const citasDelDia = citasPorDia.get(dia.getTime()) ?? [];
            return (
              <div
                key={dia.getTime()}
                className={`rounded-card border p-2 min-h-32 ${esHoy ? "border-teal-400 bg-teal-400/5" : "border-border bg-white"}`}
              >
                <p className={`text-xs font-semibold mb-2 ${esHoy ? "text-teal-900" : "text-ink/60"}`}>
                  {NOMBRES_DIA[i]} {dia.getDate()}
                </p>
                <div className="space-y-2">
                  {citasDelDia.map((cita) => {
                    const esGrupal = cita.persona_id === null;
                    return (
                    <div
                      key={cita.id}
                      className={`rounded-card border p-2 text-xs space-y-1.5 ${esGrupal ? "border-teal-400/60 bg-teal-400/5" : "border-border bg-white"}`}
                    >
                      <p className="font-mono text-ink/70">
                        {new Date(cita.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                      </p>
                      {esGrupal && (
                        <span className="inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium bg-teal-600/10 text-teal-900">
                          {cita.tipo_actividad || "Actividad"}
                        </span>
                      )}
                      <p className={cita.estado === "Cancelada" ? "text-ink/40 line-through" : "text-ink"}>
                        {esGrupal ? cita.titulo : cita.motivo}
                      </p>
                      {esGrupal && cita.lugar && <p className="text-ink/50">📍 {cita.lugar}</p>}
                      {esGrupal && cita.participantes.length > 0 && (
                        <p className="text-ink/50">
                          {cita.participantes.length} asistente(s): {cita.participantes.map((p) => p.nombre_completo).join(", ")}
                        </p>
                      )}
                      {cita.estado === "Programada" && reprogramandoId !== cita.id && (
                        <div className="flex items-center gap-2 pt-0.5">
                          <button onClick={() => abrirReprogramar(cita)} className="text-teal-700 hover:underline">
                            {esGrupal ? "Editar" : "Reprogramar"}
                          </button>
                          <button onClick={() => cancelar(cita.id)} className="text-ink/50 hover:text-ink hover:underline">
                            Cancelar
                          </button>
                        </div>
                      )}
                      {cita.estado !== "Programada" && (
                        <p className="text-ink/40 italic">{cita.estado}</p>
                      )}

                      {reprogramandoId === cita.id && (
                        // Deliberadamente SIN <Input/>/<Boton/>: esta celda de
                        // calendario necesita controles más compactos
                        // (px-1.5/py-1) que el tamaño fijo que esos
                        // componentes ya traen — pasar ese tamaño por
                        // className no lo sobrescribiría de forma confiable
                        // (misma especificidad CSS que su clase base), mismo
                        // criterio que la fila de "Reprocesar" del dashboard
                        // de campaña.
                        <form
                          onSubmit={(e) => guardarReprogramacion(e, cita)}
                          className="space-y-1.5 border-t border-border pt-1.5"
                        >
                          {esGrupal && (
                            <>
                              <input
                                type="text"
                                required
                                placeholder="Título"
                                value={formReprogramar.titulo}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, titulo: e.target.value }))}
                                className="w-full rounded border border-border px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400"
                              />
                              <select
                                value={formReprogramar.tipo_actividad}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, tipo_actividad: e.target.value }))}
                                className="w-full rounded border border-border px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400"
                              >
                                {TIPOS_ACTIVIDAD.map((t) => (
                                  <option key={t} value={t}>
                                    {t}
                                  </option>
                                ))}
                              </select>
                              <input
                                type="text"
                                placeholder="Lugar (opcional)"
                                value={formReprogramar.lugar}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, lugar: e.target.value }))}
                                className="w-full rounded border border-border px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400"
                              />
                            </>
                          )}
                          <input
                            type="date"
                            required
                            value={formReprogramar.fecha}
                            onChange={(e) => setFormReprogramar((f) => ({ ...f, fecha: e.target.value }))}
                            className="w-full rounded border border-border px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400"
                          />
                          <input
                            type="time"
                            required
                            value={formReprogramar.hora}
                            onChange={(e) => setFormReprogramar((f) => ({ ...f, hora: e.target.value }))}
                            className="w-full rounded border border-border px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400"
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="submit"
                              disabled={guardando}
                              className="rounded bg-teal-600 px-2 py-1 text-white hover:bg-teal-900 disabled:opacity-40"
                            >
                              {guardando ? "..." : "Guardar"}
                            </button>
                            <button
                              type="button"
                              onClick={() => setReprogramandoId(null)}
                              className="text-ink/50 hover:text-ink hover:underline"
                            >
                              Cancelar
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                    );
                  })}
                  {citasDelDia.length === 0 && <p className="text-xs text-ink/30 italic">Sin citas</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
