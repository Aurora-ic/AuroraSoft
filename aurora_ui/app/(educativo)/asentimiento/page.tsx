"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Textarea } from "@/components/ui/Textarea";
import type { AsentimientoInformadoTexto, AsentimientoInformadoTextoCreate } from "@/types/api";

// 🆕 Configuración mínima del texto de asentimiento informado que el
// alumno ve al abrir su link de examen (ver docs/gaps-pendientes.md) —
// antes era una constante fija en el frontend, sin fuente editable ni
// versionada. Cada institución puede tener su propia versión activa (si
// nunca crea una, el examen público usa la GLOBAL por defecto); crear una
// versión nueva desactiva la anterior, nunca se edita una ya existente —
// el snapshot de qué versión aceptó cada alumno (Inscripcion.
// asentimiento_texto_version_id) queda fijo para siempre.
export default function AsentimientoInformadoPage() {
  const { sesion } = useAuth();
  const puedeEditar = sesion?.rol === "admin" || sesion?.rol === "superadmin";

  const [versiones, setVersiones] = useState<AsentimientoInformadoTexto[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [contenido, setContenido] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorGuardar, setErrorGuardar] = useState<string | null>(null);

  function cargar() {
    if (!sesion?.institucionId) return;
    setCargando(true);
    setError(null);
    apiClient
      .get<AsentimientoInformadoTexto[]>(`/educativo/asentimiento-textos?institucion_id=${sesion.institucionId}`)
      .then((datos) => {
        setVersiones(datos);
        const activa = datos.find((v) => v.activo);
        if (activa) setContenido(activa.contenido);
      })
      .catch((err: any) => setError(err.message || "No se pudo cargar el historial de versiones."))
      .finally(() => setCargando(false));
  }

  // 🔧 GET /educativo/asentimiento-textos también exige SOLO_ADMINISTRATIVO
  // (admin/superadmin) en el backend, no solo el POST — probado en vivo:
  // un psicólogo u otro rol que llegue a esta pantalla recibía siempre un
  // 403 ("No se pudo cargar el historial de versiones.") porque esta página
  // solo gateaba el FORMULARIO (puedeEditar) y no el fetch mismo, al
  // contrario del mismo patrón ya usado para la autorización de acceso del
  // colegio en la ficha del alumno. Para quien no puede editar, ni siquiera
  // se intenta pedir el historial — se muestra directamente el mensaje de
  // "contacta a tu administrador".
  useEffect(() => {
    if (!puedeEditar) {
      setCargando(false);
      return;
    }
    cargar();
  }, [sesion?.institucionId, puedeEditar]);

  async function guardarNuevaVersion(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) return;
    setGuardando(true);
    setErrorGuardar(null);
    try {
      const payload: AsentimientoInformadoTextoCreate = {
        institucion_id: sesion.institucionId,
        contenido,
      };
      await apiClient.post("/educativo/asentimiento-textos", payload);
      cargar();
    } catch (err: any) {
      setErrorGuardar(err.message || "No se pudo guardar la nueva versión.");
    } finally {
      setGuardando(false);
    }
  }

  const versionActiva = versiones?.find((v) => v.activo) ?? null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl text-teal-900">Asentimiento informado</h1>
        <p className="text-sm text-ink/60 mt-1">
          El texto que cada alumno ve antes de aceptar y comenzar su evaluación. Un párrafo por línea.
        </p>
      </div>

      <TextoError>{error}</TextoError>

      {cargando ? (
        <p className="text-sm text-ink/40">Cargando...</p>
      ) : (
        <>
          <section className="bg-white rounded-card border border-border p-6 space-y-4">
            <h2 className="font-display text-lg font-semibold text-teal-900">
              {versionActiva ? `Versión activa: v${versionActiva.version}` : "Sin versión propia — se usa el texto global por defecto"}
            </h2>

            {puedeEditar ? (
              <form onSubmit={guardarNuevaVersion} className="space-y-3">
                <Textarea
                  required
                  rows={10}
                  value={contenido}
                  onChange={(e) => setContenido(e.target.value)}
                  placeholder="Un párrafo por línea..."
                  className="w-full"
                />
                <p className="text-xs text-ink/50">
                  Guardar crea una versión NUEVA y desactiva la anterior — nunca se edita una versión ya existente, para
                  que quede registro de qué texto aceptó cada alumno en su momento.
                </p>
                <TextoError>{errorGuardar}</TextoError>
                <Boton type="submit" disabled={guardando || !contenido.trim()}>
                  {guardando ? "Guardando..." : "Guardar nueva versión"}
                </Boton>
              </form>
            ) : (
              <p className="text-sm text-ink/80 whitespace-pre-line">
                {versionActiva ? versionActiva.contenido : "Contacta a tu administrador para configurar un texto propio."}
              </p>
            )}
          </section>

          {versiones && versiones.length > 0 && (
            <section className="bg-white rounded-card border border-border p-6 space-y-3">
              <h2 className="font-display text-lg font-semibold text-teal-900">Historial de versiones</h2>
              <div className="divide-y divide-border">
                {versiones
                  .slice()
                  .sort((a, b) => b.version - a.version)
                  .map((v) => (
                    <div key={v.id} className="py-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-ink">
                          v{v.version} {v.activo && <span className="text-xs text-teal-700 font-semibold">(activa)</span>}
                        </span>
                        <span className="text-xs text-ink/50">{new Date(v.creado_en).toLocaleString("es-PE")}</span>
                      </div>
                      <p className="text-xs text-ink/70 whitespace-pre-line mt-1">{v.contenido}</p>
                    </div>
                  ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
