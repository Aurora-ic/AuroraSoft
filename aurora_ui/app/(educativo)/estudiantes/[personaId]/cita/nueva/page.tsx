"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { CalendarPlus, CalendarDays, Clock } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Migas } from "@/components/ui/Migas";
import { EncabezadoPagina, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { TarjetaAlumnoLateral, CabeceraBloque, useAlumno } from "@/components/educativo/TarjetaAlumnoLateral";
import type { Cita, CitaCreate } from "@/types/api";

// Formulario real para el botón "Nueva cita" de la ficha del alumno.
// POST /admin/personas/citas/ — el backend asigna `psicologo_id =
// usuario_actual.id`, así que la cita aparece de inmediato en la agenda de
// quien la crea y puede cancelarse desde la ficha o desde /agenda.
//
// 🆕 Rediseño (sesión 2026-10-31): mismo esquema que "Registrar alumno" —
// formulario en un bloque a la izquierda y, a la derecha, la tarjeta del
// alumno con UN dato de contexto: sus próximas citas (para no agendar dos
// veces lo mismo). Duración en botones rápidos (como en la Agenda) y
// atajos Hoy/Mañana para la fecha.
// ⚠️ e2e/agenda-citas-seguimiento.spec.ts usa las etiquetas "Motivo",
// "Fecha", "Hora" y el botón "Agendar cita" — no renombrarlos.

const DURACIONES = [30, 45, 60, 90];

function textoDuracion(min: number): string {
  if (min < 60) return `${min} min`;
  return min % 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min / 60} h`;
}

function fechaIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function NuevaCitaPage() {
  const params = useParams();
  const personaId = params.personaId as string;
  const router = useRouter();
  const { alumno, seccion } = useAlumno(personaId);

  const [motivo, setMotivo] = useState("");
  const [fecha, setFecha] = useState("");
  const [hora, setHora] = useState("");
  // Duración — 45 min por defecto, igual que el backend.
  const [duracion, setDuracion] = useState("45");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proximas, setProximas] = useState<Cita[] | null>(null);

  useEffect(() => {
    apiClient
      .get<Cita[]>(`/admin/personas/${personaId}/citas`)
      .then((citas) => {
        const ahora = Date.now();
        setProximas(
          citas
            .filter((c) => c.estado === "Programada" && new Date(c.fecha_hora).getTime() >= ahora)
            .sort((a, b) => (a.fecha_hora < b.fecha_hora ? -1 : 1))
            .slice(0, 3),
        );
      })
      .catch(() => setProximas(null));
  }, [personaId]);

  const hoy = new Date();
  const manana = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() + 1);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!fecha || !hora) {
      setError("Indica la fecha y la hora de la cita.");
      return;
    }
    const fechaHora = new Date(`${fecha}T${hora}`);
    if (Number.isNaN(fechaHora.getTime())) {
      setError("La fecha u hora ingresadas no son válidas.");
      return;
    }
    const duracionMin = Number(duracion);
    if (!duracionMin || duracionMin < 5 || duracionMin > 720) {
      setError("La duración debe estar entre 5 y 720 minutos.");
      return;
    }

    setGuardando(true);
    setError(null);
    try {
      const datos: CitaCreate = {
        persona_id: Number(personaId),
        motivo,
        fecha_hora: fechaHora.toISOString(),
        duracion_minutos: duracionMin,
      };
      await apiClient.post("/admin/personas/citas/", datos);
      router.push(`/estudiantes/${personaId}`);
    } catch (err) {
      setError((err instanceof Error && err.message) || "No se pudo agendar la cita.");
    } finally {
      setGuardando(false);
    }
  }

  const nombre = alumno ? `${alumno.nombres} ${alumno.apellidos}` : "Alumno";
  const claseChip = (activo: boolean) =>
    `rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
      activo
        ? "border-accion bg-accion text-white dark:border-teal-accent-dark dark:bg-teal-accent-dark dark:text-mist-dark"
        : "border-border dark:border-border-dark text-ink/70 dark:text-ink-dark/70 hover:border-teal-400"
    }`;

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas
        sinMargen
        items={[
          { label: "Padrón", href: "/estudiantes" },
          { label: nombre, href: `/estudiantes/${personaId}` },
          { label: "Nueva cita" },
        ]}
      />

      <EncabezadoPagina
        variante="destacado"
        icono={CalendarPlus}
        acento="teal"
        titulo="Nueva cita"
        descripcion={`Cita individual con ${alumno ? nombre : "el alumno"}. Queda agendada a tu nombre y aparece de inmediato en tu agenda.`}
        acciones={
          <Link href="/agenda" className={claseBotonBanner("secundario")}>
            <CalendarDays size={15} aria-hidden="true" />
            Ver mi agenda
          </Link>
        }
      />

      <TextoError>{error}</TextoError>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-5 items-start">
        <section className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
          <CabeceraBloque icono={CalendarPlus} titulo="Detalles de la cita" descripcion="Para qué es y cuándo." />
          <div className="p-4 space-y-4 text-sm">
            <CampoEditable etiqueta="Motivo">
              <Textarea
                required
                rows={3}
                value={motivo}
                onChange={(e) => setMotivo(e.target.value)}
                placeholder="Ej. Entrevista de seguimiento por alerta en PHQ-9"
              />
            </CampoEditable>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <CampoEditable etiqueta="Fecha">
                  <Input type="date" required value={fecha} onChange={(e) => setFecha(e.target.value)} />
                </CampoEditable>
                <div className="flex gap-1.5">
                  <button type="button" onClick={() => setFecha(fechaIso(hoy))} aria-pressed={fecha === fechaIso(hoy)} className={claseChip(fecha === fechaIso(hoy))}>
                    Hoy
                  </button>
                  <button
                    type="button"
                    onClick={() => setFecha(fechaIso(manana))}
                    aria-pressed={fecha === fechaIso(manana)}
                    className={claseChip(fecha === fechaIso(manana))}
                  >
                    Mañana
                  </button>
                </div>
              </div>
              <CampoEditable etiqueta="Hora">
                <Input type="time" required value={hora} onChange={(e) => setHora(e.target.value)} />
              </CampoEditable>
            </div>

            <div className="flex flex-col gap-1">
              <span className="text-ink/70 dark:text-ink-dark/70 font-medium">Duración</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {DURACIONES.map((d) => (
                  <button key={d} type="button" onClick={() => setDuracion(String(d))} aria-pressed={duracion === String(d)} className={claseChip(duracion === String(d))}>
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
        </section>

        <aside className="lg:sticky lg:top-4 space-y-4">
          <TarjetaAlumnoLateral personaId={personaId} alumno={alumno} seccion={seccion}>
            <p className="m-0 mb-2 text-[10.5px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Próximas citas</p>
            {proximas === null ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">—</p>
            ) : proximas.length === 0 ? (
              <p className="m-0 text-[12px] text-ink/45 dark:text-ink-dark/45">No tiene citas programadas.</p>
            ) : (
              <ul className="m-0 list-none p-0 space-y-2">
                {proximas.map((c) => {
                  const f = new Date(c.fecha_hora);
                  return (
                    <li key={c.id} className="flex items-start gap-2 text-[12px]">
                      <Clock size={13} aria-hidden="true" className="mt-0.5 shrink-0 text-teal-600 dark:text-teal-accent-dark" />
                      <span className="min-w-0">
                        <span className="block font-semibold text-ink dark:text-ink-dark">
                          {f.toLocaleDateString("es-PE", { weekday: "short", day: "numeric", month: "short" })} ·{" "}
                          {f.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                        <span className="block truncate text-ink/55 dark:text-ink-dark/55" title={c.motivo}>
                          {c.motivo}
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </TarjetaAlumnoLateral>

          <div className="flex flex-col gap-2">
            <Boton type="submit" disabled={guardando} className="w-full inline-flex items-center justify-center gap-2">
              <CalendarPlus size={15} aria-hidden="true" />
              {guardando ? "Agendando..." : "Agendar cita"}
            </Boton>
            <Link href={`/estudiantes/${personaId}`} className={claseBoton("secundario", "w-full text-center")}>
              Cancelar
            </Link>
          </div>
        </aside>
      </form>
    </div>
  );
}
