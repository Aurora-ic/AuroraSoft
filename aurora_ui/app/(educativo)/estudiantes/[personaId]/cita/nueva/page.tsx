"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { Migas } from "@/components/ui/Migas";
import type { Persona, CitaCreate } from "@/types/api";

// Formulario real para el botón "+ Nueva Cita" de la ficha del alumno, que
// hasta ahora navegaba a esta misma ruta sin que existiera ninguna página
// (404 silencioso). POST /admin/personas/citas/ ya existía en el backend
// (modulos/superadmin/router.py) sin ningún formulario que lo usara.
//
// Queda "de la mano" con /agenda: el backend siempre asigna
// `psicologo_id = usuario_actual.id` (quien agenda la cita queda como
// responsable), así que la cita creada aquí aparece de inmediato en la
// agenda de quien la crea (GET /admin/personas/citas/mi-agenda, filtrada
// por ese mismo psicologo_id) y puede cancelarse desde cualquiera de las
// dos pantallas (esta ficha o /agenda), ambas golpeando el mismo DELETE.
export default function NuevaCitaPage() {
  const params = useParams();
  const personaId = params.personaId as string;
  const router = useRouter();

  const [alumno, setAlumno] = useState<Persona | null>(null);
  const [motivo, setMotivo] = useState("");
  const [fecha, setFecha] = useState("");
  const [hora, setHora] = useState("");
  // 🆕 Duración (sesión 2026-10-30) — 45 min por defecto, igual que el backend.
  const [duracion, setDuracion] = useState("45");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Persona>(`/admin/personas/${personaId}/detalle`)
      .then(setAlumno)
      .catch(() => {
        // El encabezado con el nombre es solo un detalle de contexto — si
        // falla, el formulario sigue siendo perfectamente usable.
      });
  }, [personaId]);

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

    setGuardando(true);
    setError(null);
    try {
      const datos: CitaCreate = {
        persona_id: Number(personaId),
        motivo,
        fecha_hora: fechaHora.toISOString(),
        duracion_minutos: Number(duracion),
      };
      await apiClient.post("/admin/personas/citas/", datos);
      router.push(`/estudiantes/${personaId}`);
    } catch (err: any) {
      setError(err.message || "No se pudo agendar la cita.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <Migas
        items={[
          { label: "Padrón", href: "/estudiantes" },
          { label: alumno ? `${alumno.nombres} ${alumno.apellidos}` : "Alumno", href: `/estudiantes/${personaId}` },
          { label: "Nueva cita" },
        ]}
      />
      <div>
        <Link
          href={`/estudiantes/${personaId}`}
          className="text-sm text-teal-600 dark:text-teal-accent-dark hover:underline inline-block mb-1 font-medium"
        >
          ← Volver a la ficha
        </Link>
        <h1 className="font-display text-2xl text-teal-900 dark:text-ink-dark font-bold">
          Nueva cita{alumno ? ` — ${alumno.nombres} ${alumno.apellidos}` : ""}
        </h1>
        <p className="text-sm text-ink/60 dark:text-ink-dark/60 mt-1">
          Queda agendada a tu nombre y aparece de inmediato en tu{" "}
          <Link href="/agenda" className="underline hover:text-ink">
            agenda
          </Link>
          .
        </p>
      </div>

      <TextoError>{error}</TextoError>

      <form onSubmit={handleSubmit} className="bg-surface dark:bg-surface-dark p-6 rounded-card border border-border dark:border-border-dark space-y-4 shadow-sm">
        <CampoEditable etiqueta="Motivo">
          <Textarea
            required
            rows={3}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej. Entrevista de seguimiento por alerta en PHQ-9"
          />
        </CampoEditable>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
          <CampoEditable etiqueta="Fecha">
            <Input type="date" required value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </CampoEditable>
          <CampoEditable etiqueta="Hora">
            <Input type="time" required value={hora} onChange={(e) => setHora(e.target.value)} />
          </CampoEditable>
          <CampoEditable etiqueta="Duración" className="col-span-2 sm:col-span-1">
            <Select value={duracion} onChange={(e) => setDuracion(e.target.value)}>
              {[30, 45, 60, 90, 120].map((d) => (
                <option key={d} value={d}>
                  {d < 60 ? `${d} min` : d % 60 ? `${Math.floor(d / 60)} h ${d % 60} min` : `${d / 60} h`}
                </option>
              ))}
            </Select>
          </CampoEditable>
        </div>

        <Boton type="submit" disabled={guardando} className="w-full">
          {guardando ? "Agendando..." : "Agendar cita"}
        </Boton>
      </form>
    </div>
  );
}
