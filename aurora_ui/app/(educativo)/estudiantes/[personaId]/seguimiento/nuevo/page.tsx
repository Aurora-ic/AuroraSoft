"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Textarea } from "@/components/ui/Textarea";
import { Migas } from "@/components/ui/Migas";
import type { Persona, SesionSeguimientoCreate } from "@/types/api";

// Formulario real para el botón "+ Registrar Sesión" de la ficha del
// alumno, que hasta ahora navegaba a esta misma ruta sin que existiera
// ninguna página (404 silencioso). POST /educativo/seguimiento/ ya existía
// en el backend (modulos/educativo/router.py) sin ningún formulario que lo
// usara.
//
// Deliberadamente no pide fecha/estado: `SesionSeguimiento.fecha` la pone
// el backend sola (hoy) y `estado` nace en "Atendido" — `estado`/
// `acuerdos_compromisos`/`proxima_cita` solo son editables después, vía
// PATCH /educativo/seguimiento/{id} ("Editar" en el historial de la ficha
// del alumno, ver docs/frontend.md) — este formulario cubre el caso básico
// de dejar constancia de la sesión, no la edición posterior.
export default function NuevaSesionSeguimientoPage() {
  const params = useParams();
  const personaId = params.personaId as string;
  const router = useRouter();

  const [alumno, setAlumno] = useState<Persona | null>(null);
  const [observaciones, setObservaciones] = useState("");
  const [accionTomada, setAccionTomada] = useState("");
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
    } catch (err: any) {
      setError(err.message || "No se pudo registrar la sesión.");
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
          { label: "Nueva sesión" },
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
          Registrar sesión de seguimiento{alumno ? ` — ${alumno.nombres} ${alumno.apellidos}` : ""}
        </h1>
        <p className="text-sm text-ink/60 dark:text-ink-dark/60 mt-1">Queda con la fecha de hoy y a tu nombre.</p>
      </div>

      <TextoError>{error}</TextoError>

      <form onSubmit={handleSubmit} className="bg-surface dark:bg-surface-dark p-6 rounded-card border border-border dark:border-border-dark space-y-4 shadow-sm">
        <CampoEditable etiqueta="Observaciones de la sesión">
          <Textarea
            required
            rows={5}
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

        <Boton type="submit" disabled={guardando} className="w-full">
          {guardando ? "Guardando..." : "Guardar sesión"}
        </Boton>
      </form>
    </div>
  );
}
