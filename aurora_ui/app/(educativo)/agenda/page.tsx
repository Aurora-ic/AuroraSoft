"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
  User,
  UsersRound,
  MapPin,
  Clock,
  X,
  Presentation,
  MessagesSquare,
  Handshake,
  Shapes,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Cita, CitaCreate, CitaUpdate, Persona } from "@/types/api";
import { EncabezadoPagina, claseBotonBanner } from "@/components/ui/Encabezado";

const TIPOS_ACTIVIDAD = ["Taller", "Charla", "Reunión", "Otro"];

const NOMBRES_DIA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const NOMBRES_DIA_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const INICIALES_DIA = ["L", "M", "M", "J", "V", "S", "D"];

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

// Semanas completas entre el lunes de hoy y el lunes de `fecha` — lo que
// necesita `semanaOffset` para saltar a la semana de un día elegido.
function offsetSemanasHasta(fecha: Date): number {
  const base = inicioDeSemana(new Date()).getTime();
  const destino = inicioDeSemana(fecha).getTime();
  return Math.round((destino - base) / (7 * 24 * 60 * 60 * 1000));
}

function fechaInputLocal(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function horaCorta(iso: string): string {
  return new Date(iso).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });
}

// 🆕 Duración (sesión 2026-10-30) — "08:00 – 08:45".
function rangoHorario(cita: Cita): string {
  const inicio = new Date(cita.fecha_hora);
  const fin = new Date(inicio.getTime() + (cita.duracion_minutos ?? 45) * 60_000);
  const f = (d: Date) => d.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });
  return `${f(inicio)} – ${f(fin)}`;
}

function textoDuracion(min: number): string {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

// Ids de las citas PROGRAMADAS de un mismo día que se superponen en el
// tiempo con alguna otra — solo un aviso visual, nunca bloquea nada.
function idsQueSeCruzan(citasDelDia: Cita[]): Set<number> {
  const prog = citasDelDia.filter((c) => c.estado === "Programada");
  const ids = new Set<number>();
  for (let i = 0; i < prog.length; i++) {
    const ai = new Date(prog[i].fecha_hora).getTime();
    const af = ai + (prog[i].duracion_minutos ?? 45) * 60_000;
    for (let j = i + 1; j < prog.length; j++) {
      const bi = new Date(prog[j].fecha_hora).getTime();
      const bf = bi + (prog[j].duracion_minutos ?? 45) * 60_000;
      if (ai < bf && bi < af) {
        ids.add(prog[i].id);
        ids.add(prog[j].id);
      }
    }
  }
  return ids;
}

const DURACIONES_RAPIDAS = [30, 45, 60, 90];

// --- Codificación visual por tipo de evento ---
// 🆕 Agenda tipo calendario (sesión 2026-10-30). Dos colores validados con
// el validador de paleta (daltonismo/visión normal/contraste, claro y
// oscuro): teal = cita individual, azul = actividad grupal. El tipo de
// actividad (Taller/Charla/Reunión/Otro) va por ícono + etiqueta, nunca por
// un tercer/cuarto color — con 4 tonos fríos no hubo combinación que
// pasara la separación para daltonismo. El ámbar sigue reservado para
// alerta clínica: nada de esta pantalla lo usa.
type Categoria = "individual" | "grupal";

const ESTILO_CATEGORIA: Record<Categoria, { borde: string; texto: string; fondo: string; muestra: string }> = {
  individual: {
    borde: "border-l-teal-600 dark:border-l-teal-accent-dark",
    texto: "text-teal-700 dark:text-teal-accent-dark",
    fondo: "bg-teal-600/[0.05] dark:bg-teal-accent-dark/[0.07]",
    muestra: "bg-teal-600 dark:bg-teal-accent-dark",
  },
  grupal: {
    borde: "border-l-[#2a78d6] dark:border-l-[#5598e7]",
    texto: "text-[#1f63b8] dark:text-[#5598e7]",
    fondo: "bg-[#2a78d6]/[0.06] dark:bg-[#5598e7]/[0.08]",
    muestra: "bg-[#2a78d6] dark:bg-[#5598e7]",
  },
};

const ICONO_TIPO: Record<string, LucideIcon> = {
  Taller: Presentation,
  Charla: MessagesSquare,
  Reunión: Handshake,
};

function categoriaDe(cita: Cita): Categoria {
  return cita.persona_id === null ? "grupal" : "individual";
}

function iconoDe(cita: Cita): LucideIcon {
  if (cita.persona_id !== null) return User;
  return ICONO_TIPO[cita.tipo_actividad ?? ""] ?? Shapes;
}

// Vista semanal hecha a mano (sin librería de calendario) — basta para lo
// que un psicólogo necesita de su agenda: ver de un vistazo qué tiene esta
// semana, moverse semana a semana, reprogramar/cancelar sin salir de aquí.
//
// ⚠️ e2e/agenda-citas-seguimiento.spec.ts ubica la tarjeta de una cita como
// el <div> MÁS PROFUNDO que contiene a la vez el motivo y el botón
// "Reprogramar", y dentro de él el formulario de reprogramación, la hora
// ("16:45", una sola vez) y "Cancelar"/"Cancelada" — no envolver el
// contenido de la tarjeta en un <div> interno.
export default function AgendaPage() {
  const { sesion } = useAuth();
  const [citas, setCitas] = useState<Cita[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [semanaOffset, setSemanaOffset] = useState(0);

  // Mes que muestra el mini calendario — se mueve solo con sus flechas, o
  // se re-sincroniza al navegar semanas con `irASemana`/`irAFecha`.
  const [mesMini, setMesMini] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  const [mostrarIndividuales, setMostrarIndividuales] = useState(true);
  const [mostrarGrupales, setMostrarGrupales] = useState(true);

  const [reprogramandoId, setReprogramandoId] = useState<number | null>(null);
  const [formReprogramar, setFormReprogramar] = useState({ fecha: "", hora: "", titulo: "", tipo_actividad: "", lugar: "", duracion: "45" });
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
    duracion: string;
    participantes_ids: Set<number>;
  } | null>(null);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [cargandoPersonas, setCargandoPersonas] = useState(false);
  const [errorPersonas, setErrorPersonas] = useState<string | null>(null);
  const [filtroPersonas, setFiltroPersonas] = useState("");
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

  // Esc cierra el modal de nueva actividad.
  useEffect(() => {
    if (!formularioActividad) return;
    function alPresionar(e: KeyboardEvent) {
      if (e.key === "Escape") setFormularioActividad(null);
    }
    window.addEventListener("keydown", alPresionar);
    return () => window.removeEventListener("keydown", alPresionar);
  }, [formularioActividad]);

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

  const citasFiltradas = useMemo(
    () =>
      citas.filter((c) => {
        const cat = categoriaDe(c);
        return (cat === "individual" && mostrarIndividuales) || (cat === "grupal" && mostrarGrupales);
      }),
    [citas, mostrarIndividuales, mostrarGrupales],
  );

  const citasPorDia = useMemo(() => {
    const mapa = new Map<number, Cita[]>();
    for (const dia of diasVisibles) {
      const delDia = citasFiltradas
        .filter((c) => mismoDia(new Date(c.fecha_hora), dia))
        .sort((a, b) => new Date(a.fecha_hora).getTime() - new Date(b.fecha_hora).getTime());
      mapa.set(dia.getTime(), delDia);
    }
    return mapa;
  }, [citasFiltradas, diasVisibles]);

  // Días con al menos una cita (filtrada) — los puntitos del mini calendario.
  const diasConCitas = useMemo(() => {
    const s = new Set<string>();
    citasFiltradas.forEach((c) => s.add(fechaInputLocal(new Date(c.fecha_hora))));
    return s;
  }, [citasFiltradas]);

  // Celdas del mini calendario: siempre 6 filas x 7 (lunes a domingo).
  const celdasMes = useMemo(() => {
    const primero = inicioDeSemana(mesMini);
    return Array.from({ length: 42 }, (_, i) => {
      const d = new Date(primero);
      d.setDate(d.getDate() + i);
      return d;
    });
  }, [mesMini]);

  function irASemana(offset: number) {
    setSemanaOffset(offset);
    const lunes = inicioDeSemana(new Date());
    lunes.setDate(lunes.getDate() + offset * 7);
    setMesMini(new Date(lunes.getFullYear(), lunes.getMonth(), 1));
  }

  function irAFecha(fecha: Date) {
    setSemanaOffset(offsetSemanasHasta(fecha));
    setMesMini(new Date(fecha.getFullYear(), fecha.getMonth(), 1));
  }

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
      duracion: String(cita.duracion_minutos ?? 45),
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
    const { fecha, hora, titulo, tipo_actividad, lugar, duracion } = formReprogramar;
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
      const payload: CitaUpdate = { fecha_hora: fechaHora.toISOString(), duracion_minutos: Number(duracion) || 45 };
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

  // `fecha` opcional: el "+" de cada día de la semana abre el formulario
  // con ese día ya puesto (como al hacer clic en un día de un calendario).
  function abrirFormularioActividad(fecha?: Date) {
    setFormularioActividad({
      titulo: "",
      tipo_actividad: "Taller",
      fecha: fecha ? fechaInputLocal(fecha) : "",
      hora: "",
      lugar: "",
      duracion: "60",
      participantes_ids: new Set(),
    });
    setErrorFormularioActividad(null);
    setFiltroPersonas("");
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
    const { titulo, tipo_actividad, fecha, hora, lugar, duracion, participantes_ids } = formularioActividad;
    if (!titulo.trim() || !fecha || !hora) {
      setErrorFormularioActividad("Indica al menos el título, la fecha y la hora.");
      return;
    }
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) {
      setErrorFormularioActividad("La fecha u hora ingresadas no son válidas.");
      return;
    }
    const duracionMin = Number(duracion);
    if (!duracionMin || duracionMin < 5 || duracionMin > 720) {
      setErrorFormularioActividad("La duración debe estar entre 5 y 720 minutos.");
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
        duracion_minutos: duracionMin,
        participantes_ids: Array.from(participantes_ids),
      };
      await apiClient.post("/admin/personas/citas/", payload);
      setFormularioActividad(null);
      // Salta a la semana de la actividad recién creada para que se vea.
      irAFecha(fechaHora);
      cargar();
    } catch (err: any) {
      setErrorFormularioActividad(err.message || "No se pudo crear la actividad.");
    } finally {
      setGuardandoActividad(false);
    }
  }

  const hoy = new Date();
  const finSemana = diasVisibles[6];

  // Próximas (desde ahora), filtradas — el panel lateral, máx. 5.
  const ahora = hoy.getTime();
  const proximas = citasFiltradas
    .filter((c) => c.estado === "Programada" && new Date(c.fecha_hora).getTime() >= ahora)
    .sort((a, b) => new Date(a.fecha_hora).getTime() - new Date(b.fecha_hora).getTime())
    .slice(0, 5);

  const totalIndividuales = citas.filter((c) => c.persona_id !== null).length;
  const totalGrupales = citas.length - totalIndividuales;

  const personasFiltradasModal = filtroPersonas.trim()
    ? personas.filter((p) => `${p.nombres} ${p.apellidos}`.toLowerCase().includes(filtroPersonas.trim().toLowerCase()))
    : personas;

  const claseNav =
    "inline-flex items-center justify-center rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark transition-colors disabled:opacity-40";
  const claseInputCompacto =
    "w-full rounded border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-teal-400";

  const rangoSemana = `${inicioSemanaVisible.toLocaleDateString("es-PE", { day: "numeric", month: "short" })} → ${finSemana.toLocaleDateString("es-PE", { day: "numeric", month: "short", year: "numeric" })}`;

  const filtrosTipo = [
    { cat: "individual" as const, etiqueta: "Citas individuales", icono: User, valor: mostrarIndividuales, set: setMostrarIndividuales, n: totalIndividuales },
    { cat: "grupal" as const, etiqueta: "Actividades grupales", icono: UsersRound, valor: mostrarGrupales, set: setMostrarGrupales, n: totalGrupales },
  ];

  return (
    <div className="max-w-[90rem] mx-auto flex flex-col gap-4">
      <EncabezadoPagina
        variante="destacado"
        acento="pizarra"
        icono={CalendarDays}
        titulo="Mi agenda"
        descripcion="Tus citas individuales y las actividades grupales de todo tu equipo."
        acciones={
          <button type="button" onClick={() => abrirFormularioActividad()} className={claseBotonBanner("primario")}>
            <Plus size={15} strokeWidth={2.4} aria-hidden="true" />
            Nueva actividad
          </button>
        }
      />
      <div className="grid gap-4 xl:grid-cols-[17.5rem_1fr] items-start">
        {/* ======================= PANEL LATERAL ======================= */}
        <aside className="flex flex-col gap-4 xl:sticky xl:top-0">
          <div className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
            {/* --- Mini calendario --- */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <button
                  type="button"
                  onClick={() => setMesMini((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                  className="rounded-md p-1 text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
                  aria-label="Mes anterior"
                >
                  <ChevronLeft size={15} aria-hidden="true" />
                </button>
                <p className="m-0 text-[12px] font-bold uppercase tracking-wide text-ink/70 dark:text-ink-dark/70">
                  {mesMini.toLocaleDateString("es-PE", { month: "long", year: "numeric" })}
                </p>
                <button
                  type="button"
                  onClick={() => setMesMini((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
                  className="rounded-md p-1 text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
                  aria-label="Mes siguiente"
                >
                  <ChevronRight size={15} aria-hidden="true" />
                </button>
              </div>
              <div className="grid grid-cols-7 text-center">
                {INICIALES_DIA.map((d, i) => (
                  <span key={i} className="py-1 text-[10.5px] font-semibold text-ink/40 dark:text-ink-dark/40">
                    {d}
                  </span>
                ))}
                {celdasMes.map((d) => {
                  const enMes = d.getMonth() === mesMini.getMonth();
                  const enSemana = d >= inicioSemanaVisible && d <= finSemana;
                  const esHoy = mismoDia(d, hoy);
                  const tieneCitas = diasConCitas.has(fechaInputLocal(d));
                  return (
                    <button
                      key={d.getTime()}
                      type="button"
                      onClick={() => irAFecha(d)}
                      aria-label={d.toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" })}
                      className={`relative h-8 text-[12px] transition-colors ${
                        enSemana ? "bg-teal-600/[0.08] dark:bg-teal-accent-dark/10" : "rounded-lg hover:bg-mist dark:hover:bg-surface-raised-dark"
                      } ${enSemana && d.getDay() === 1 ? "rounded-l-lg" : ""} ${enSemana && d.getDay() === 0 ? "rounded-r-lg" : ""}`}
                    >
                      <span
                        className={`inline-flex h-6 w-6 items-center justify-center rounded-full ${
                          esHoy
                            ? "bg-accion text-white font-bold dark:bg-teal-accent-dark dark:text-mist-dark"
                            : enMes
                              ? "text-ink dark:text-ink-dark"
                              : "text-ink/25 dark:text-ink-dark/25"
                        }`}
                      >
                        {d.getDate()}
                      </span>
                      {tieneCitas && !esHoy && (
                        <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 h-1 w-1 rounded-full bg-teal-600 dark:bg-teal-accent-dark" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* --- Filtros por tipo (muestra de color + ícono + conteo) --- */}
            <div className="mt-4 pt-4 border-t border-border dark:border-border-dark space-y-1">
              <p className="m-0 mb-1.5 text-[10.5px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Mostrar</p>
              {filtrosTipo.map((f) => (
                <label
                  key={f.cat}
                  className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[12.5px] text-ink/80 dark:text-ink-dark/80 hover:bg-mist dark:hover:bg-surface-raised-dark cursor-pointer"
                >
                  <input type="checkbox" checked={f.valor} onChange={(e) => f.set(e.target.checked)} className="sr-only peer" />
                  <span
                    aria-hidden="true"
                    className={`flex h-4 w-4 items-center justify-center rounded ${
                      f.valor ? ESTILO_CATEGORIA[f.cat].muestra : "border border-border dark:border-border-dark"
                    } peer-focus-visible:ring-2 peer-focus-visible:ring-teal-400`}
                  >
                    {f.valor && <span className="block h-1.5 w-1.5 rounded-sm bg-white" />}
                  </span>
                  <f.icono size={13} className={ESTILO_CATEGORIA[f.cat].texto} aria-hidden="true" />
                  <span className="flex-1">{f.etiqueta}</span>
                  <span className="text-[11px] font-semibold text-ink/40 dark:text-ink-dark/40">{f.n}</span>
                </label>
              ))}
            </div>
          </div>

          {/* --- Próximas --- */}
          <div className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4">
            <p className="m-0 mb-2.5 text-[10.5px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Próximas</p>
            {cargando ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">Cargando...</p>
            ) : proximas.length === 0 ? (
              <p className="m-0 text-[12px] italic text-ink/40 dark:text-ink-dark/40">Nada agendado de aquí en adelante.</p>
            ) : (
              <ul className="m-0 p-0 list-none flex flex-col gap-1">
                {proximas.map((c) => {
                  const cat = categoriaDe(c);
                  const Icono = iconoDe(c);
                  const f = new Date(c.fecha_hora);
                  return (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => irAFecha(f)}
                        className="w-full text-left flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-mist dark:hover:bg-surface-raised-dark"
                      >
                        <span className="flex w-9 shrink-0 flex-col items-center rounded-md border border-border dark:border-border-dark py-0.5">
                          <span className="text-[9px] font-bold uppercase text-ink/45 dark:text-ink-dark/45">
                            {NOMBRES_DIA_CORTO[(f.getDay() + 6) % 7]}
                          </span>
                          <span className="font-display text-[15px] font-bold leading-none text-ink dark:text-ink-dark">{f.getDate()}</span>
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={`flex items-center gap-1 text-[11px] font-semibold ${ESTILO_CATEGORIA[cat].texto}`}>
                            <Icono size={11} aria-hidden="true" />
                            {horaCorta(c.fecha_hora)}
                          </span>
                          <span className="block truncate text-[12.5px] font-medium text-ink dark:text-ink-dark">
                            {cat === "grupal" ? c.titulo : c.persona_nombre || "Cita individual"}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>

        {/* ======================= VISTA SEMANAL ======================= */}
        <section className="rounded-xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark overflow-hidden min-w-0">
          <header className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-border dark:border-border-dark">
            <div className="min-w-0">
              <p className="m-0 text-[15px] font-semibold text-teal-700 dark:text-teal-accent-dark">{rangoSemana}</p>
              <p className="m-0 text-[11.5px] text-ink/50 dark:text-ink-dark/50">
                Las citas individuales se agendan desde la ficha del alumno; talleres y charlas, aquí — las ve todo tu equipo.
              </p>
            </div>
            <div className="inline-flex items-center gap-1">
              <button onClick={() => irASemana(semanaOffset - 1)} className={`${claseNav} h-9 w-9`} aria-label="Semana anterior" title="Semana anterior">
                <ChevronLeft size={16} aria-hidden="true" />
              </button>
              <button onClick={() => irASemana(0)} className={`${claseNav} h-9 px-3 text-[12.5px] font-semibold`} disabled={semanaOffset === 0}>
                Hoy
              </button>
              <button onClick={() => irASemana(semanaOffset + 1)} className={`${claseNav} h-9 w-9`} aria-label="Semana siguiente" title="Semana siguiente">
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </div>
          </header>

          <TextoError className="px-4 pt-3">{error}</TextoError>

          {cargando ? (
            <p className="m-0 p-4 text-sm text-ink/40 dark:text-ink-dark/40">Cargando...</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-7 md:divide-x divide-border dark:divide-border-dark">
              {diasVisibles.map((dia, i) => {
                const esHoy = mismoDia(dia, hoy);
                const esFinDeSemana = i >= 5;
                const citasDelDia = citasPorDia.get(dia.getTime()) ?? [];
                const cruzadas = idsQueSeCruzan(citasDelDia);
                return (
                  <div
                    key={dia.getTime()}
                    className={`group/dia relative flex flex-col border-b md:border-b-0 border-border dark:border-border-dark md:min-h-[30rem] ${
                      esHoy
                        ? "bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05]"
                        : esFinDeSemana
                          ? "bg-mist/40 dark:bg-surface-raised-dark/50"
                          : ""
                    }`}
                  >
                    {/* Encabezado del día — número grande, como un calendario de pared */}
                    <div className="flex items-center gap-3 md:flex-col md:gap-0 px-3 py-2.5 md:py-4">
                      <span
                        className={`font-display text-[26px] md:text-[34px] font-bold leading-none ${
                          esHoy ? "text-teal-600 dark:text-teal-accent-dark" : "text-ink/30 dark:text-ink-dark/30"
                        }`}
                      >
                        {dia.getDate()}
                      </span>
                      <span
                        className={`text-[11px] font-bold uppercase tracking-wider md:mt-1 ${
                          esHoy ? "text-teal-700 dark:text-teal-accent-dark" : "text-ink/45 dark:text-ink-dark/45"
                        }`}
                      >
                        <span className="md:hidden">{NOMBRES_DIA[i]}</span>
                        <span className="hidden md:inline">{NOMBRES_DIA_CORTO[i]}</span>
                      </span>
                      {citasDelDia.length === 0 && (
                        <span className="md:hidden ml-auto text-[11px] italic text-ink/30 dark:text-ink-dark/30">Sin citas</span>
                      )}
                      <button
                        type="button"
                        onClick={() => abrirFormularioActividad(dia)}
                        aria-label={`Nueva actividad el ${NOMBRES_DIA[i].toLowerCase()} ${dia.getDate()}`}
                        title="Nueva actividad este día"
                        className={`${citasDelDia.length === 0 ? "" : "ml-auto"} md:ml-0 md:absolute md:top-2 md:right-2 flex h-7 w-7 items-center justify-center rounded-full text-ink/40 dark:text-ink-dark/40 hover:bg-accion hover:text-white dark:hover:bg-teal-accent-dark dark:hover:text-mist-dark md:opacity-0 md:group-hover/dia:opacity-100 focus:opacity-100 transition-all`}
                      >
                        <Plus size={15} aria-hidden="true" />
                      </button>
                    </div>

                    <div className="flex-1 space-y-2 px-2 pb-3">
                      {citasDelDia.map((cita) => {
                        const esGrupal = cita.persona_id === null;
                        const cat = categoriaDe(cita);
                        const estilo = ESTILO_CATEGORIA[cat];
                        const Icono = iconoDe(cita);
                        const cancelada = cita.estado === "Cancelada";
                        return (
                        <div
                          key={cita.id}
                          className={`rounded-md border-l-[3px] px-2 py-1.5 text-xs space-y-1 ${
                            cancelada ? "border-l-border dark:border-l-border-dark bg-mist/60 dark:bg-surface-raised-dark" : `${estilo.borde} ${estilo.fondo}`
                          }`}
                        >
                          <p className="m-0 flex items-center gap-1 font-mono text-[11px] text-ink/60 dark:text-ink-dark/60">
                            <Clock size={10} aria-hidden="true" className="shrink-0" />
                            {rangoHorario(cita)}
                          </p>
                          {cruzadas.has(cita.id) && (
                            <p className="m-0 inline-flex items-center gap-1 rounded bg-red-50 dark:bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">
                              <AlertTriangle size={10} aria-hidden="true" />
                              Se cruza con otra cita
                            </p>
                          )}
                          <p
                            className={`m-0 flex items-start gap-1 font-semibold leading-snug ${
                              cancelada ? "text-ink/40 dark:text-ink-dark/40 line-through" : estilo.texto
                            }`}
                          >
                            <Icono size={12} aria-hidden="true" className="mt-px shrink-0" />
                            <span className="min-w-0 break-words">{esGrupal ? cita.titulo : cita.motivo}</span>
                          </p>
                          {!esGrupal && cita.persona_nombre && (
                            <p className="m-0 text-ink/60 dark:text-ink-dark/60 leading-snug">
                              con{" "}
                              <Link
                                href={`/estudiantes/${cita.persona_id}`}
                                className="font-semibold text-ink dark:text-ink-dark hover:text-teal-700 dark:hover:text-teal-accent-dark hover:underline"
                              >
                                {cita.persona_nombre}
                              </Link>
                            </p>
                          )}
                          {esGrupal && (
                            <p className="m-0 text-[10.5px] font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
                              {cita.tipo_actividad || "Actividad"}
                            </p>
                          )}
                          {esGrupal && cita.lugar && (
                            <p className="m-0 flex items-center gap-1 text-ink/55 dark:text-ink-dark/55">
                              <MapPin size={10} aria-hidden="true" className="shrink-0" />
                              {cita.lugar}
                            </p>
                          )}
                          {esGrupal && cita.participantes.length > 0 && (
                            <p
                              className="m-0 flex items-center gap-1 text-ink/55 dark:text-ink-dark/55"
                              title={cita.participantes.map((p) => p.nombre_completo).join(", ")}
                            >
                              <UsersRound size={10} aria-hidden="true" className="shrink-0" />
                              {cita.participantes.length} asistente(s)
                            </p>
                          )}
                          {cita.estado === "Programada" && reprogramandoId !== cita.id && (
                            <div className="flex items-center gap-2.5 pt-0.5 text-[11px] font-semibold">
                              <button onClick={() => abrirReprogramar(cita)} className="text-teal-700 dark:text-teal-accent-dark hover:underline">
                                {esGrupal ? "Editar" : "Reprogramar"}
                              </button>
                              <button onClick={() => cancelar(cita.id)} className="text-ink/50 dark:text-ink-dark/50 hover:text-ink dark:hover:text-ink-dark hover:underline">
                                Cancelar
                              </button>
                            </div>
                          )}
                          {cita.estado !== "Programada" && (
                            <p className="m-0 text-ink/40 dark:text-ink-dark/40 italic">{cita.estado}</p>
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
                              className="space-y-1.5 border-t border-border dark:border-border-dark pt-1.5"
                            >
                              {esGrupal && (
                                <>
                                  <input
                                    type="text"
                                    required
                                    placeholder="Título"
                                    value={formReprogramar.titulo}
                                    onChange={(e) => setFormReprogramar((f) => ({ ...f, titulo: e.target.value }))}
                                    className={claseInputCompacto}
                                  />
                                  <select
                                    value={formReprogramar.tipo_actividad}
                                    onChange={(e) => setFormReprogramar((f) => ({ ...f, tipo_actividad: e.target.value }))}
                                    className={claseInputCompacto}
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
                                    className={claseInputCompacto}
                                  />
                                </>
                              )}
                              <input
                                type="date"
                                required
                                value={formReprogramar.fecha}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, fecha: e.target.value }))}
                                className={claseInputCompacto}
                              />
                              <input
                                type="time"
                                required
                                value={formReprogramar.hora}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, hora: e.target.value }))}
                                className={claseInputCompacto}
                              />
                              <select
                                aria-label="Duración"
                                value={formReprogramar.duracion}
                                onChange={(e) => setFormReprogramar((f) => ({ ...f, duracion: e.target.value }))}
                                className={claseInputCompacto}
                              >
                                {Array.from(new Set([...DURACIONES_RAPIDAS, 120, Number(formReprogramar.duracion) || 45]))
                                  .sort((a, b) => a - b)
                                  .map((d) => (
                                    <option key={d} value={d}>
                                      {textoDuracion(d)}
                                    </option>
                                  ))}
                              </select>
                              <div className="flex items-center gap-2">
                                <button
                                  type="submit"
                                  disabled={guardando}
                                  className="rounded bg-accion dark:bg-teal-accent-dark px-2 py-1 text-white dark:text-mist-dark hover:bg-accion-hover disabled:opacity-40"
                                >
                                  {guardando ? "..." : "Guardar"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setReprogramandoId(null)}
                                  className="text-ink/50 dark:text-ink-dark/50 hover:text-ink dark:hover:text-ink-dark hover:underline"
                                >
                                  Cancelar
                                </button>
                              </div>
                            </form>
                          )}
                        </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* ======================= MODAL: NUEVA ACTIVIDAD ======================= */}
      {formularioActividad && (
        <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center p-4 overflow-y-auto">
          <div className="fixed inset-0 bg-ink/45" aria-hidden="true" onClick={() => setFormularioActividad(null)} />
          <form
            onSubmit={guardarActividad}
            role="dialog"
            aria-modal="true"
            aria-labelledby="titulo-nueva-actividad"
            className="relative w-full max-w-2xl rounded-2xl border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-xl text-sm"
          >
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
              <h2 id="titulo-nueva-actividad" className="m-0 flex items-center gap-2 font-display text-[17px] text-teal-900 dark:text-ink-dark font-semibold">
                <span className={`flex h-7 w-7 items-center justify-center rounded-lg text-white ${ESTILO_CATEGORIA.grupal.muestra}`}>
                  <UsersRound size={15} aria-hidden="true" />
                </span>
                Nueva actividad grupal
              </h2>
              <button
                type="button"
                onClick={() => setFormularioActividad(null)}
                className="rounded-lg p-1.5 text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
                aria-label="Cerrar"
              >
                <X size={17} aria-hidden="true" />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div className="grid sm:grid-cols-2 gap-3">
                <CampoEditable etiqueta="Título (obligatorio)" className="sm:col-span-2">
                  <Input
                    required
                    autoFocus
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
                <CampoEditable etiqueta="Lugar (opcional)">
                  <Input
                    placeholder="Ej. Auditorio"
                    value={formularioActividad.lugar}
                    onChange={(e) => setFormularioActividad({ ...formularioActividad, lugar: e.target.value })}
                  />
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
                <div className="sm:col-span-2 flex flex-col gap-1">
                  <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Duración</span>
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {DURACIONES_RAPIDAS.map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => setFormularioActividad({ ...formularioActividad, duracion: String(d) })}
                        aria-pressed={formularioActividad.duracion === String(d)}
                        className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                          formularioActividad.duracion === String(d)
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
                        value={formularioActividad.duracion}
                        onChange={(e) => setFormularioActividad({ ...formularioActividad, duracion: e.target.value })}
                        className="w-20"
                      />
                      min
                    </span>
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-xs font-medium text-ink/50 dark:text-ink-dark/50 uppercase tracking-wide">
                    Estudiantes asistentes (opcional)
                    {formularioActividad.participantes_ids.size > 0 && (
                      <span className="normal-case tracking-normal font-semibold text-teal-700 dark:text-teal-accent-dark">
                        {" "}
                        · {formularioActividad.participantes_ids.size} seleccionado(s)
                      </span>
                    )}
                  </span>
                  {personas.length > 8 && (
                    <input
                      type="search"
                      aria-label="Buscar estudiante"
                      placeholder="Buscar…"
                      value={filtroPersonas}
                      onChange={(e) => setFiltroPersonas(e.target.value)}
                      className="w-40 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark px-2.5 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-teal-400"
                    />
                  )}
                </div>
                <TextoError>{errorPersonas}</TextoError>
                {cargandoPersonas ? (
                  <p className="text-xs text-ink/40 dark:text-ink-dark/40">Cargando padrón...</p>
                ) : personas.length === 0 ? (
                  <p className="text-xs text-ink/40 dark:text-ink-dark/40 italic">No hay estudiantes en el padrón todavía.</p>
                ) : (
                  <div className="max-h-52 overflow-y-auto rounded-lg border border-border dark:border-border-dark grid sm:grid-cols-2">
                    {personasFiltradasModal.map((p) => (
                      <label
                        key={p.id}
                        className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-ink dark:text-ink-dark hover:bg-mist/60 dark:hover:bg-surface-raised-dark cursor-pointer border-b border-border/60 dark:border-border-dark"
                      >
                        <input
                          type="checkbox"
                          checked={formularioActividad.participantes_ids.has(p.id)}
                          onChange={() => alternarParticipante(p.id)}
                          className="accent-teal-600"
                        />
                        {p.nombres} {p.apellidos}
                      </label>
                    ))}
                  </div>
                )}
              </div>

              <TextoError>{errorFormularioActividad}</TextoError>
            </div>

            <div className="flex items-center justify-end gap-3 px-5 py-3.5 border-t border-border dark:border-border-dark bg-mist/40 dark:bg-surface-raised-dark rounded-b-2xl">
              <button
                type="button"
                onClick={() => setFormularioActividad(null)}
                className="text-sm font-medium text-ink/60 dark:text-ink-dark/60 hover:underline"
              >
                Cancelar
              </button>
              <Boton type="submit" disabled={guardandoActividad}>
                {guardandoActividad ? "Creando..." : "Crear actividad"}
              </Boton>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
