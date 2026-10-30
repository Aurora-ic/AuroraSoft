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
import { type TonoBadge } from "@/components/ui/Badge";
import { EncabezadoPagina, PastillaBanner } from "@/components/ui/Encabezado";
import { BloqueFicha, CuadriculaDatos, DatoFicha } from "@/components/educativo/BloqueFicha";
import {
  Settings,
  Building2,
  CalendarRange,
  ShieldCheck,
  Image as ImageIcon,
  UploadCloud,
  Lock,
  Phone,
  MapPin,
  Mail,
} from "lucide-react";
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

function diasHasta(fecha: Date): number {
  return Math.ceil((fecha.getTime() - Date.now()) / (24 * 60 * 60 * 1000));
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

  if (cargando) return <div className="text-sm text-ink/60 dark:text-ink-dark/60">Cargando...</div>;
  if (!institucion) return <TextoError>{error || "No se pudo cargar la institución."}</TextoError>;

  // Estado de la licencia, solo para mostrar — el dato y su gestión siguen
  // siendo exclusivos de superadmin (/master/clientes/[id]).
  const vencimiento = institucion.fecha_vencimiento_licencia ? new Date(institucion.fecha_vencimiento_licencia) : null;
  const diasParaVencer = vencimiento ? diasHasta(vencimiento) : null;
  const estadoLicencia: { texto: string; tono: TonoBadge } = !institucion.plan_activo
    ? { texto: "Plan inactivo", tono: "neutro" }
    : diasParaVencer !== null && diasParaVencer < 0
      ? { texto: "Licencia vencida", tono: "error" }
      : diasParaVencer !== null && diasParaVencer <= 30
        ? { texto: `Vence en ${diasParaVencer} día(s)`, tono: "neutro" }
        : { texto: "Licencia vigente", tono: "teal" };

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-4">
      <EncabezadoPagina variante="destacado"
        icono={Settings}
        acento="pizarra"
        titulo="Configuración de la institución"
        descripcion={institucion.nombre}
        acciones={
          <span className="inline-flex items-center gap-2">
            {!puedeEditar && (
              <PastillaBanner>
                <Lock size={12} aria-hidden="true" />
                Solo lectura
              </PastillaBanner>
            )}
            {/* El tono del Badge (teal/neutro/error) no se lee sobre el
                degradado — en la franja el estado va como pastilla con un
                punto de color. */}
            <PastillaBanner>
              <span
                aria-hidden="true"
                className={`h-2 w-2 rounded-full ${
                  estadoLicencia.tono === "error" ? "bg-red-400" : estadoLicencia.tono === "teal" ? "bg-teal-400" : "bg-white/60"
                }`}
              />
              {estadoLicencia.texto}
            </PastillaBanner>
          </span>
        }
      />

      {!puedeEditar && (
        <p className="m-0 text-xs text-ink/50 dark:text-ink-dark/50 italic">
          Estás viendo esta pantalla en modo lectura — solo el admin del colegio puede cambiar estas opciones.
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr] items-start">
        <BloqueFicha
          icono={Building2}
          titulo="Datos generales"
          descripcion="Los administra el equipo de AuroraSoft — si necesitás corregir alguno, contactanos."
        >
          <CuadriculaDatos>
            <DatoFicha etiqueta="Nombre" valor={institucion.nombre} ancho />
            <DatoFicha etiqueta="Tipo" valor={institucion.tipo} />
            <DatoFicha etiqueta="Teléfono" icono={Phone} valor={institucion.telefono} />
            <DatoFicha etiqueta="Dirección" icono={MapPin} valor={institucion.direccion} ancho />
            <DatoFicha etiqueta="Email de contacto" icono={Mail} valor={institucion.email_contacto} ancho />
            <DatoFicha etiqueta="Plan" valor={institucion.plan_activo ? "Activo" : "Inactivo"} />
            <DatoFicha
              etiqueta="Vencimiento de licencia"
              valor={vencimiento ? vencimiento.toLocaleDateString("es-PE") : "Sin vencimiento"}
            />
            <DatoFicha
              etiqueta="Límite de pruebas por alumno (cada 30 días)"
              valor={String(institucion.limite_pruebas_mensual_por_alumno)}
              ancho
            />
          </CuadriculaDatos>
        </BloqueFicha>

        <div className="flex flex-col gap-4">
          <BloqueFicha
            icono={CalendarRange}
            titulo="Año escolar activo"
            descripcion="El año que el resto de la app muestra por defecto."
          >
            <div className="flex items-end justify-between gap-3 flex-wrap">
              <div>
                <p className="m-0 text-[11px] font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Actual</p>
                <p className="m-0 font-display text-[28px] font-bold leading-none text-teal-900 dark:text-ink-dark">
                  {institucion.anio_escolar_activo ?? <span className="text-base text-ink/40 dark:text-ink-dark/40">No configurado</span>}
                </p>
              </div>
              {puedeEditar && (
                <form onSubmit={guardarAnioEscolar} className="flex items-end gap-2">
                  <label className="flex flex-col gap-1 text-[12px]">
                    <span className="text-ink/60 dark:text-ink-dark/60 font-medium">Nuevo año escolar</span>
                    <Input
                      type="number"
                      value={anioForm}
                      onChange={(e) => setAnioForm(e.target.value)}
                      min={2000}
                      max={2100}
                      className="w-28"
                    />
                  </label>
                  <Boton type="submit" disabled={guardandoAnio}>
                    {guardandoAnio ? "Guardando..." : "Activar"}
                  </Boton>
                </form>
              )}
            </div>
            <p className="m-0 mt-3 text-[11.5px] text-ink/50 dark:text-ink-dark/50">
              Cambiarlo es una acción explícita — nunca se activa solo al confirmar una promoción de estudiantes.
            </p>
            <TextoError className="mt-2">{errorAnio}</TextoError>
          </BloqueFicha>

          <BloqueFicha icono={ShieldCheck} titulo="Política de consentimientos">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p id="etiqueta-asentimiento" className="m-0 text-sm font-semibold text-ink dark:text-ink-dark">
                  Exigir también el asentimiento del propio estudiante
                </p>
                <p className="m-0 mt-1 text-[11.5px] text-ink/50 dark:text-ink-dark/50">
                  El consentimiento del apoderado siempre es obligatorio. Esta opción exige, además, el asentimiento vigente del
                  estudiante para matricularlo o para que siga rindiendo un examen ya empezado.
                </p>
              </div>
              {/* Interruptor accesible (role="switch") en vez del checkbox
                  suelto de antes — misma llamada, mismo valor. */}
              <button
                type="button"
                role="switch"
                aria-checked={institucion.exigir_asentimiento_estudiante}
                aria-labelledby="etiqueta-asentimiento"
                disabled={!puedeEditar || guardandoPolitica}
                onClick={() => alternarPolitica(!institucion.exigir_asentimiento_estudiante)}
                className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  institucion.exigir_asentimiento_estudiante
                    ? "bg-teal-600 dark:bg-teal-accent-dark"
                    : "bg-border dark:bg-border-dark"
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    institucion.exigir_asentimiento_estudiante ? "translate-x-[22px]" : "translate-x-0.5"
                  }`}
                />
              </button>
            </div>
            <TextoError className="mt-2">{errorPolitica}</TextoError>
          </BloqueFicha>
        </div>
      </div>

      <BloqueFicha
        icono={ImageIcon}
        titulo="Imágenes institucionales"
        descripcion="Se usan en los documentos generados (informes, fichas, plantillas). PNG o JPG, máx. 3 MB."
      >
        <div className="grid sm:grid-cols-3 gap-3">
          {TIPOS_BRANDING.map((tipo) => {
            const urlActual = urlBrandingActual(institucion, tipo);
            const idInput = `branding-${tipo}`;
            return (
              <div key={tipo} className="rounded-lg border border-border dark:border-border-dark overflow-hidden flex flex-col">
                <div className="h-28 bg-mist/50 dark:bg-surface-raised-dark flex items-center justify-center overflow-hidden p-2">
                  {urlActual ? (
                    // eslint-disable-next-line @next/next/no-img-element -- URL externa/propia, no un asset estático
                    <img
                      src={urlActual}
                      alt={ETIQUETAS_BRANDING[tipo].titulo}
                      className="max-h-full max-w-full object-contain"
                    />
                  ) : (
                    <span className="flex flex-col items-center gap-1 text-xs text-ink/35 dark:text-ink-dark/35">
                      <ImageIcon size={20} aria-hidden="true" />
                      Sin imagen
                    </span>
                  )}
                </div>
                <div className="p-3 flex flex-col gap-2 flex-1">
                  <div>
                    <p className="m-0 text-[13px] font-semibold text-ink dark:text-ink-dark">{ETIQUETAS_BRANDING[tipo].titulo}</p>
                    <p className="m-0 text-[11.5px] text-ink/50 dark:text-ink-dark/50">{ETIQUETAS_BRANDING[tipo].descripcion}</p>
                  </div>
                  {puedeEditar && (
                    <>
                      <input
                        id={idInput}
                        type="file"
                        accept=".png,.jpg,.jpeg"
                        disabled={subiendoBranding === tipo}
                        onChange={(e) => {
                          const archivo = e.target.files?.[0];
                          e.target.value = "";
                          if (archivo) subirBranding(tipo, archivo);
                        }}
                        className="sr-only"
                      />
                      <label
                        htmlFor={idInput}
                        className={`mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg border border-border dark:border-border-dark px-3 py-1.5 text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:border-teal-400 transition-colors ${
                          subiendoBranding === tipo ? "opacity-50 pointer-events-none" : "cursor-pointer"
                        }`}
                      >
                        <UploadCloud size={14} aria-hidden="true" />
                        {subiendoBranding === tipo ? "Subiendo..." : urlActual ? "Reemplazar imagen" : "Subir imagen"}
                      </label>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <TextoError className="mt-2">{errorBranding}</TextoError>
      </BloqueFicha>
    </div>
  );
}
