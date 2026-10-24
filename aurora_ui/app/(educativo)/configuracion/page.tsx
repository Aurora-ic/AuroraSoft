"use client";

// 🆕 Pantalla de autoservicio para el admin del propio colegio — el
// backend ya tenía estos 3 endpoints desde antes (año escolar activo,
// política de consentimientos, branding autoalojado) pero nada en el
// frontend los llamaba. `PATCH /instituciones/{id}` (nombre/dirección/
// teléfono/email/licencia/plan) sigue siendo exclusivo de superadmin —
// eso ya tiene su propia UI en /master/clientes/[id], no se duplica acá.
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { Campo } from "@/components/ui/Campo";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import type { Institucion } from "@/types/api";

const TIPOS_BRANDING = ["encabezado", "pie", "fondo"] as const;
type TipoBranding = (typeof TIPOS_BRANDING)[number];

const ETIQUETAS_BRANDING: Record<TipoBranding, { titulo: string; descripcion: string }> = {
  encabezado: { titulo: "Logo de encabezado", descripcion: "Encabezado de los documentos e informes generados." },
  pie: { titulo: "Pie de página", descripcion: "Franja en el pie de página de los documentos." },
  fondo: { titulo: "Fondo de página completa", descripcion: "Solo se usa en plantillas que lo activen explícitamente." },
};

function urlBrandingActual(institucion: Institucion, tipo: TipoBranding): string | null {
  if (tipo === "encabezado") return institucion.logo_url ?? null;
  if (tipo === "pie") return institucion.logo_pie_pagina_url ?? null;
  return institucion.fondo_documento_url ?? null;
}

export default function ConfiguracionPage() {
  const { sesion } = useAuth();
  // superadmin no llega a esta ruta (route group "(educativo)" no lo
  // incluye) — acá el único rol que puede escribir es "admin", mismo
  // criterio que SOLO_ADMINISTRATIVO en el backend.
  const puedeEditar = sesion?.rol === "admin";

  const [institucion, setInstitucion] = useState<Institucion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [anioForm, setAnioForm] = useState("");
  const [guardandoAnio, setGuardandoAnio] = useState(false);
  const [errorAnio, setErrorAnio] = useState<string | null>(null);

  const [guardandoPolitica, setGuardandoPolitica] = useState(false);
  const [errorPolitica, setErrorPolitica] = useState<string | null>(null);

  const [subiendoBranding, setSubiendoBranding] = useState<TipoBranding | null>(null);
  const [errorBranding, setErrorBranding] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Institucion>("/instituciones/me")
      .then((data) => {
        setInstitucion(data);
        setAnioForm(data.anio_escolar_activo ? String(data.anio_escolar_activo) : "");
      })
      .catch((err) => setError(err.message || "No se pudo cargar la información de la institución."))
      .finally(() => setCargando(false));
  }, []);

  async function guardarAnioEscolar(e: React.FormEvent) {
    e.preventDefault();
    if (!institucion) return;
    const anio = Number(anioForm);
    if (!anio || anio < 2000 || anio > 2100) {
      setErrorAnio("Indica un año válido (entre 2000 y 2100).");
      return;
    }
    setGuardandoAnio(true);
    setErrorAnio(null);
    try {
      const actualizada = await apiClient.patch<Institucion>(
        `/instituciones/${institucion.id}/anio-escolar-activo`,
        { anio_escolar: anio },
      );
      setInstitucion(actualizada);
    } catch (err: any) {
      setErrorAnio(err.message || "No se pudo activar el año escolar.");
    } finally {
      setGuardandoAnio(false);
    }
  }

  async function alternarPolitica(valor: boolean) {
    if (!institucion) return;
    setGuardandoPolitica(true);
    setErrorPolitica(null);
    try {
      const actualizada = await apiClient.patch<Institucion>(
        `/instituciones/${institucion.id}/politica-consentimientos`,
        { exigir_asentimiento_estudiante: valor },
      );
      setInstitucion(actualizada);
    } catch (err: any) {
      setErrorPolitica(err.message || "No se pudo actualizar la política.");
    } finally {
      setGuardandoPolitica(false);
    }
  }

  async function subirBranding(tipo: TipoBranding, archivo: File) {
    if (!institucion) return;
    setSubiendoBranding(tipo);
    setErrorBranding(null);
    try {
      const fd = new FormData();
      fd.append("archivo", archivo);
      const actualizada = await apiClient.postForm<Institucion>(
        `/instituciones/${institucion.id}/branding/${tipo}`,
        fd,
      );
      setInstitucion(actualizada);
    } catch (err: any) {
      setErrorBranding(err.message || "No se pudo subir la imagen.");
    } finally {
      setSubiendoBranding(null);
    }
  }

  if (cargando) return <div className="text-sm text-ink/60">Cargando...</div>;
  if (!institucion) return <TextoError>{error || "No se pudo cargar la institución."}</TextoError>;

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="font-display text-2xl text-teal-900 font-semibold">Configuración de la institución</h1>
      {!puedeEditar && (
        <p className="text-xs text-ink/50 italic">
          Estás viendo esta pantalla en modo lectura — solo el admin del colegio puede cambiar estas opciones.
        </p>
      )}

      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">Datos generales</h2>
        <p className="text-xs text-ink/50 italic">
          Estos datos los administra el equipo de AuroraSoft directamente — si necesitás corregir alguno, contactanos.
        </p>
        <div className="grid sm:grid-cols-2 gap-4 text-sm">
          <Campo etiqueta="Nombre" valor={institucion.nombre} />
          <Campo etiqueta="Tipo" valor={institucion.tipo || "—"} />
          <Campo etiqueta="Dirección" valor={institucion.direccion || "—"} />
          <Campo etiqueta="Teléfono" valor={institucion.telefono || "—"} />
          <Campo etiqueta="Email de contacto" valor={institucion.email_contacto || "—"} />
          <Campo etiqueta="Plan" valor={institucion.plan_activo ? "Activo" : "Inactivo"} />
          <Campo
            etiqueta="Vencimiento de licencia"
            valor={
              institucion.fecha_vencimiento_licencia
                ? new Date(institucion.fecha_vencimiento_licencia).toLocaleDateString("es-PE")
                : "Sin vencimiento"
            }
          />
          <Campo
            etiqueta="Límite de pruebas por alumno (cada 30 días)"
            valor={String(institucion.limite_pruebas_mensual_por_alumno)}
          />
        </div>
      </section>

      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">Año escolar activo</h2>
        <p className="text-xs text-ink/50 italic">
          Determina qué año muestra el resto de la app por defecto. Cambiarlo es una acción explícita — nunca se
          activa solo al confirmar una promoción de estudiantes.
        </p>
        <p className="text-sm">
          Año activo actual:{" "}
          <strong className="text-teal-900">{institucion.anio_escolar_activo ?? "No configurado"}</strong>
        </p>
        {puedeEditar && (
          <form onSubmit={guardarAnioEscolar} className="flex items-end gap-3 flex-wrap">
            <CampoEditable etiqueta="Nuevo año escolar">
              <Input
                type="number"
                value={anioForm}
                onChange={(e) => setAnioForm(e.target.value)}
                min={2000}
                max={2100}
              />
            </CampoEditable>
            <Boton type="submit" disabled={guardandoAnio}>
              {guardandoAnio ? "Guardando..." : "Activar"}
            </Boton>
          </form>
        )}
        <TextoError>{errorAnio}</TextoError>
      </section>

      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Política de consentimientos
        </h2>
        <p className="text-xs text-ink/50 italic">
          El consentimiento del apoderado siempre es obligatorio para evaluar a un estudiante. Esta opción exige,
          además, el asentimiento vigente del propio estudiante para matricularlo o para que siga rindiendo un
          examen ya empezado.
        </p>
        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={institucion.exigir_asentimiento_estudiante}
            disabled={!puedeEditar || guardandoPolitica}
            onChange={(e) => alternarPolitica(e.target.checked)}
          />
          Exigir también el asentimiento del propio estudiante
        </label>
        <TextoError>{errorPolitica}</TextoError>
      </section>

      <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
        <h2 className="font-display text-xl text-teal-900 font-semibold border-b border-border pb-2">
          Imágenes institucionales
        </h2>
        <p className="text-xs text-ink/50 italic">
          Se usan en los documentos generados (informes, fichas, plantillas). PNG o JPG, máx. 3 MB.
        </p>
        <div className="grid sm:grid-cols-3 gap-4">
          {TIPOS_BRANDING.map((tipo) => {
            const urlActual = urlBrandingActual(institucion, tipo);
            return (
              <div key={tipo} className="space-y-2">
                <p className="text-sm font-medium text-ink/80">{ETIQUETAS_BRANDING[tipo].titulo}</p>
                <p className="text-xs text-ink/50">{ETIQUETAS_BRANDING[tipo].descripcion}</p>
                <div className="h-24 rounded-card border border-border bg-mist/30 flex items-center justify-center overflow-hidden">
                  {urlActual ? (
                    // eslint-disable-next-line @next/next/no-img-element -- URL externa/propia, no un asset estático
                    <img
                      src={urlActual}
                      alt={ETIQUETAS_BRANDING[tipo].titulo}
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <span className="text-xs text-ink/40">Sin imagen</span>
                  )}
                </div>
                {puedeEditar && (
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg"
                    disabled={subiendoBranding === tipo}
                    onChange={(e) => {
                      const archivo = e.target.files?.[0];
                      e.target.value = "";
                      if (archivo) subirBranding(tipo, archivo);
                    }}
                    className="block w-full text-xs text-ink/70 file:mr-2 file:rounded-full file:border-0 file:bg-teal-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-teal-700 hover:file:bg-teal-100"
                  />
                )}
                {subiendoBranding === tipo && <p className="text-xs text-ink/50">Subiendo...</p>}
              </div>
            );
          })}
        </div>
        <TextoError>{errorBranding}</TextoError>
      </section>
    </div>
  );
}
