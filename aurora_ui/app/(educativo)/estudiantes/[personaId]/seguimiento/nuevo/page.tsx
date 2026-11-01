"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NotebookPen, CalendarCheck2, Info } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Textarea } from "@/components/ui/Textarea";
import { Migas } from "@/components/ui/Migas";
import { EncabezadoPagina, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { TarjetaAlumnoLateral, CabeceraBloque, useAlumno } from "@/components/educativo/TarjetaAlumnoLateral";
import type { SesionSeguimiento, SesionSeguimientoCreate } from "@/types/api";

// Formulario real para el botón "Registrar sesión" de la ficha del alumno.
// POST /educativo/seguimiento/.
//
// Deliberadamente no pide fecha/estado: `SesionSeguimiento.fecha` la pone
// el backend sola (hoy) y `estado` nace en "Atendido" — `estado`/
// `acuerdos_compromisos`/`proxima_cita` solo son editables después, vía
// PATCH /educativo/seguimiento/{id} ("Editar" en el historial de la ficha
// del alumno, ver docs/frontend.md) — este formulario cubre el caso básico
// de dejar constancia de la sesión, no la edición posterior.
//
// 🆕 Rediseño (sesión 2026-10-31): mismo esquema que "Nueva cita" — bloque
// del formulario a la izquierda; a la derecha la tarjeta del alumno con UN
// dato de contexto (su última sesión, para retomar desde ahí).
// ⚠️ e2e/agenda-citas-seguimiento.spec.ts usa "Observaciones de la sesión",
// "Acción tomada (opcional)" y el botón "Guardar sesión" — no renombrarlos.

function fechaCorta(iso: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("es-PE", { day: "numeric", month: "short", year: "numeric" });
}

export default function NuevaSesionSeguimientoPage() {
  const params = useParams();
  const personaId = params.personaId as string;
  const router = useRouter();
  const { alumno, seccion } = useAlumno(personaId);

  const [observaciones, setObservaciones] = useState("");
  const [accionTomada, setAccionTomada] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // undefined = cargando, null = sin sesiones previas
  const [ultima, setUltima] = useState<SesionSeguimiento | null | undefined>(undefined);
  const [totalSesiones, setTotalSesiones] = useState(0);

  useEffect(() => {
    apiClient
      .get<SesionSeguimiento[]>(`/educativo/seguimiento/${personaId}`)
      .then((lista) => {
        setTotalSesiones(lista.length);
        setUltima([...lista].sort((a, b) => (a.fecha < b.fecha ? 1 : -1))[0] ?? null);
      })
      .catch(() => setUltima(null));
  }, [personaId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!observaciones.trim()) {
      setError("Describe lo observado durante la sesión.");
      return;
    }

    setGuardando(true);
    setError(null);
    try {
      const datos: SesionSeguimientoCreate = {
        persona_id: Number(personaId),
        observaciones,
        accion_tomada: accionTomada.trim() || undefined,
      };
      await apiClient.post("/educativo/seguimiento/", datos);
      router.push(`/estudiantes/${personaId}`);
    } catch (err) {
      setError((err instanceof Error && err.message) || "No se pudo registrar la sesión.");
    } finally {
      setGuardando(false);
    }
  }

  const nombre = alumno ? `${alumno.nombres} ${alumno.apellidos}` : "Alumno";
  const hoy = new Date().toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas
        sinMargen
        items={[
          { label: "Padrón", href: "/estudiantes" },
          { label: nombre, href: `/estudiantes/${personaId}` },
          { label: "Nueva sesión" },
        ]}
      />

      <EncabezadoPagina
        variante="destacado"
        icono={NotebookPen}
        acento="teal"
        titulo="Registrar sesión de seguimiento"
        descripcion={`Sesión con ${alumno ? nombre : "el alumno"}. Queda con la fecha de hoy y a tu nombre.`}
      />

      <TextoError>{error}</TextoError>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-5 items-start">
        <section className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
          <CabeceraBloque icono={NotebookPen} titulo="Registro de la sesión" descripcion="Lo trabajado y lo que se decidió." />
          <div className="p-4 space-y-4 text-sm">
            <p className="m-0 inline-flex items-center gap-1.5 rounded-lg bg-mist dark:bg-surface-raised-dark px-2.5 py-1 text-[12px] text-ink/60 dark:text-ink-dark/60">
              <CalendarCheck2 size={13} aria-hidden="true" className="text-teal-600 dark:text-teal-accent-dark" />
              <span className="capitalize">{hoy}</span> · se registra como <strong className="font-semibold">Atendido</strong>
            </p>

            <CampoEditable etiqueta="Observaciones de la sesión">
              <Textarea
                required
                rows={7}
                value={observaciones}
                onChange={(e) => setObservaciones(e.target.value)}
                placeholder="Qué se trabajó en la sesión, cómo respondió el estudiante..."
              />
            </CampoEditable>

            <CampoEditable etiqueta="Acción tomada (opcional)">
              <Textarea
                rows={2}
                value={accionTomada}
                onChange={(e) => setAccionTomada(e.target.value)}
                placeholder="Ej. derivado a psicología externa, se coordinó con el docente tutor..."
              />
            </CampoEditable>

            <p className="m-0 flex items-start gap-1.5 text-[11.5px] text-ink/45 dark:text-ink-dark/45">
              <Info size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
              Acuerdos, compromisos y la próxima cita se completan después con “Editar” en el historial de la ficha.
            </p>
          </div>
        </section>

        <aside className="lg:sticky lg:top-4 space-y-4">
          <TarjetaAlumnoLateral personaId={personaId} alumno={alumno} seccion={seccion}>
            <p className="m-0 mb-2 text-[10.5px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
              Última sesión{totalSesiones > 1 ? ` · ${totalSesiones} en total` : ""}
            </p>
            {ultima === undefined ? (
              <p className="m-0 text-[12px] text-ink/40 dark:text-ink-dark/40">—</p>
            ) : ultima === null ? (
              <p className="m-0 text-[12px] text-ink/45 dark:text-ink-dark/45">Esta será su primera sesión registrada.</p>
            ) : (
              <div className="text-[12px]">
                <p className="m-0 font-semibold text-ink dark:text-ink-dark">{fechaCorta(ultima.fecha)}</p>
                <p className="m-0 mt-1 text-ink/60 dark:text-ink-dark/60 line-clamp-4" title={ultima.observaciones}>
                  {ultima.observaciones}
                </p>
                {ultima.acuerdos_compromisos && (
                  <p className="m-0 mt-1.5 text-ink/55 dark:text-ink-dark/55 line-clamp-2">
                    <span className="font-semibold">Acuerdos:</span> {ultima.acuerdos_compromisos}
                  </p>
                )}
              </div>
            )}
          </TarjetaAlumnoLateral>

          <div className="flex flex-col gap-2">
            <Boton type="submit" disabled={guardando} className="w-full inline-flex items-center justify-center gap-2">
              <NotebookPen size={15} aria-hidden="true" />
              {guardando ? "Guardando..." : "Guardar sesión"}
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
