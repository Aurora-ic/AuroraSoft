"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  UserPlus,
  Upload,
  IdCard,
  UserRound,
  GraduationCap,
  CheckCircle2,
  Circle,
  Info,
  type LucideIcon,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton, claseBoton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Migas } from "@/components/ui/Migas";
import { EncabezadoPagina, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import type { Grado, MatriculaCreate, MatriculaResponse, NivelEducativo, Persona, Seccion } from "@/types/api";

// 🆕 Rediseño (sesión 2026-10-31) — antes eran 3 campos sueltos (nombres,
// apellidos, documento) y volvía al padrón, donde el alumno nuevo aparecía
// de inmediato como "Datos incompletos" y "Sin matrícula". Ahora el mismo
// POST /admin/personas/ manda también los campos opcionales que
// PersonaCreate ya aceptaba (código, fecha de nacimiento, género, correo) y,
// si se elige una sección, una segunda llamada a POST /{id}/matricula — la
// misma que usa la ficha. Nada nuevo en el backend.

const GENEROS = ["Femenino", "Masculino", "Otro"];

type Formulario = {
  nombres: string;
  apellidos: string;
  documento_identidad: string;
  codigo_institucional: string;
  fecha_nacimiento: string;
  genero: string;
  email: string;
};

const VACIO: Formulario = {
  nombres: "",
  apellidos: "",
  documento_identidad: "",
  codigo_institucional: "",
  fecha_nacimiento: "",
  genero: "",
  email: "",
};

function hoyIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function Bloque({
  icono: Icono,
  titulo,
  descripcion,
  opcional = false,
  children,
}: {
  icono: LucideIcon;
  titulo: string;
  descripcion: string;
  opcional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
      <header className="flex items-center gap-2.5 px-4 py-3 bg-teal-600/[0.08] dark:bg-teal-accent-dark/[0.08] border-b border-teal-600/15 dark:border-teal-accent-dark/20">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-600 text-white dark:bg-teal-accent-dark dark:text-mist-dark">
          <Icono size={16} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="m-0 flex items-center gap-2 text-[14px] font-bold text-teal-900 dark:text-ink-dark">
            {titulo}
            {opcional && (
              <span className="rounded-full bg-border/70 dark:bg-border-dark px-2 py-px text-[10px] font-semibold uppercase tracking-wide text-ink/50 dark:text-ink-dark/50">
                Opcional
              </span>
            )}
          </h2>
          <p className="m-0 text-[12px] text-ink/50 dark:text-ink-dark/50">{descripcion}</p>
        </div>
      </header>
      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">{children}</div>
    </section>
  );
}

function ItemCompleto({ hecho, texto }: { hecho: boolean; texto: string }) {
  const Icono = hecho ? CheckCircle2 : Circle;
  return (
    <li className={`flex items-center gap-2 ${hecho ? "text-teal-800 dark:text-teal-accent-dark" : "text-ink/45 dark:text-ink-dark/45"}`}>
      <Icono size={14} aria-hidden="true" className="shrink-0" />
      <span>{texto}</span>
      <span className="sr-only">{hecho ? "(completo)" : "(pendiente)"}</span>
    </li>
  );
}

export default function RegistrarAlumnoPage() {
  const { sesion } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState<Formulario>(VACIO);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Alumno ya creado pero la matrícula falló: no se vuelve a crear (sería un
  // 409 por documento duplicado), se ofrece terminar desde la ficha.
  const [creadoSinMatricula, setCreadoSinMatricula] = useState<Persona | null>(null);

  // --- Matrícula opcional: nivel → grado → sección (mismos endpoints que la
  // Estructura académica y la ficha). ---
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [grados, setGrados] = useState<Grado[]>([]);
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [nivelId, setNivelId] = useState("");
  const [gradoId, setGradoId] = useState("");
  const [seccionId, setSeccionId] = useState("");

  useEffect(() => {
    if (!sesion?.institucionId) return;
    apiClient
      .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
      .then((n) => setNiveles(n.filter((x) => x.activo)))
      .catch(() => setNiveles([]));
  }, [sesion?.institucionId]);

  function elegirNivel(id: string) {
    setNivelId(id);
    setGradoId("");
    setSeccionId("");
    setGrados([]);
    setSecciones([]);
    if (!id) return;
    apiClient
      .get<Grado[]>(`/admin/personas/academico/grados/${id}`)
      .then((g) => setGrados(g.filter((x) => x.activo)))
      .catch(() => setGrados([]));
  }

  function elegirGrado(id: string) {
    setGradoId(id);
    setSeccionId("");
    setSecciones([]);
    if (!id) return;
    apiClient
      .get<Seccion[]>(`/admin/personas/academico/secciones/${id}`)
      .then((s) => setSecciones(s.filter((x) => x.activo).sort((a, b) => b.anio_escolar - a.anio_escolar || a.nombre.localeCompare(b.nombre))))
      .catch(() => setSecciones([]));
  }

  const nivel = niveles.find((n) => String(n.id) === nivelId);
  const grado = grados.find((g) => String(g.id) === gradoId);
  const seccion = secciones.find((s) => String(s.id) === seccionId);
  const ubicacion = seccion ? [nivel?.nombre, grado?.nombre, seccion.nombre].filter(Boolean).join(" · ") : null;

  // Mismo criterio que la tarjeta "Datos incompletos" del Padrón (y la
  // importación por Excel): género y fecha de nacimiento.
  const completitud = useMemo(
    () => ({
      identidad: !!form.nombres.trim() && !!form.apellidos.trim() && !!form.documento_identidad.trim(),
      fecha: !!form.fecha_nacimiento,
      genero: !!form.genero,
      matricula: !!seccion,
    }),
    [form, seccion],
  );

  const iniciales = `${form.nombres.trim()[0] ?? ""}${form.apellidos.trim()[0] ?? ""}`.toUpperCase();
  const set = (campo: keyof Formulario) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [campo]: e.target.value }));

  // 🔧 Mismo candado que el botón "Registrar alumno" del Padrón (oculto para
  // "colegio"). Ojo: a diferencia de /importar/*, POST /admin/personas/ hoy
  // NO excluye a "colegio" en el backend (ver tests/matriz_permisos_esperada.json)
  // — esto solo evita ofrecer la pantalla; el candado real es del backend.
  const puedeRegistrar = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  if (!puedeRegistrar) {
    return (
      <div className="max-w-xl mx-auto">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion) return;
    setGuardando(true);
    setError(null);
    try {
      const nueva = await apiClient.post<Persona>("/admin/personas/", {
        institucion_id: sesion.institucionId,
        nombres: form.nombres.trim(),
        apellidos: form.apellidos.trim(),
        documento_identidad: form.documento_identidad.trim(),
        codigo_institucional: form.codigo_institucional.trim() || null,
        fecha_nacimiento: form.fecha_nacimiento || null,
        genero: form.genero || null,
        email: form.email.trim() || null,
      });
      if (seccionId) {
        try {
          const payload: MatriculaCreate = { seccion_id: Number(seccionId) };
          await apiClient.post<MatriculaResponse>(`/admin/personas/${nueva.id}/matricula`, payload);
        } catch (err) {
          setCreadoSinMatricula(nueva);
          setError(`El alumno se registró, pero no se pudo matricular: ${(err instanceof Error && err.message) || "error desconocido"}.`);
          return;
        }
      }
      router.push(`/estudiantes/${nueva.id}`);
    } catch (err) {
      setError((err instanceof Error && err.message) || "No se pudo registrar al alumno.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
      <Migas sinMargen items={[{ label: "Padrón", href: "/estudiantes" }, { label: "Registrar alumno" }]} />

      <EncabezadoPagina
        variante="destacado"
        icono={UserPlus}
        acento="teal"
        titulo="Registrar alumno"
        descripcion="Da de alta a un estudiante en el padrón. Solo nombres, apellidos y documento son obligatorios; lo demás puedes completarlo después en su ficha."
        acciones={
          <Link href="/estudiantes/importar" className={claseBotonBanner("secundario")}>
            <Upload size={15} aria-hidden="true" />
            ¿Son varios? Importar Excel
          </Link>
        }
      />

      {creadoSinMatricula ? (
        <div className="rounded-xl border border-red-200 dark:border-red-500/30 bg-red-50 dark:bg-red-500/10 p-4 flex flex-wrap items-center justify-between gap-3">
          <p className="m-0 text-sm text-red-800 dark:text-red-200">{error}</p>
          <Link href={`/estudiantes/${creadoSinMatricula.id}`} className={claseBoton("primario")}>
            Ir a la ficha y matricular
          </Link>
        </div>
      ) : (
        <TextoError>{error}</TextoError>
      )}

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-5 items-start">
        <div className="space-y-4">
          <Bloque icono={IdCard} titulo="Identidad" descripcion="Cómo se identifica al estudiante en el colegio.">
            <CampoEditable etiqueta="Nombres">
              <Input required autoFocus value={form.nombres} onChange={set("nombres")} className="w-full" autoComplete="off" />
            </CampoEditable>
            <CampoEditable etiqueta="Apellidos">
              <Input required value={form.apellidos} onChange={set("apellidos")} className="w-full" autoComplete="off" />
            </CampoEditable>
            <CampoEditable etiqueta="Documento de identidad">
              <Input
                required
                inputMode="numeric"
                placeholder="DNI o carné de extranjería"
                value={form.documento_identidad}
                onChange={set("documento_identidad")}
                className="w-full"
                autoComplete="off"
              />
            </CampoEditable>
            <CampoEditable etiqueta="Código institucional">
              <Input
                placeholder="Código de matrícula o legajo"
                value={form.codigo_institucional}
                onChange={set("codigo_institucional")}
                className="w-full"
                autoComplete="off"
              />
            </CampoEditable>
            <p className="m-0 sm:col-span-2 text-[11.5px] text-ink/45 dark:text-ink-dark/45">
              <span className="text-red-600 dark:text-red-300">*</span> Nombres, apellidos y documento son obligatorios. El documento y el
              código no pueden repetirse dentro del colegio.
            </p>
          </Bloque>

          <Bloque icono={UserRound} titulo="Datos personales" descripcion="Sin estos dos primeros, el alumno figura con datos incompletos en el padrón.">
            <CampoEditable etiqueta="Fecha de nacimiento">
              <Input type="date" max={hoyIso()} value={form.fecha_nacimiento} onChange={set("fecha_nacimiento")} className="w-full" />
            </CampoEditable>
            <CampoEditable etiqueta="Género">
              <Select value={form.genero} onChange={set("genero")} className="w-full">
                <option value="">Sin especificar</option>
                {GENEROS.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </Select>
            </CampoEditable>
            <CampoEditable etiqueta="Correo electrónico" className="sm:col-span-2">
              <Input type="email" placeholder="nombre@correo.com" value={form.email} onChange={set("email")} className="w-full" autoComplete="off" />
            </CampoEditable>
          </Bloque>

          <Bloque icono={GraduationCap} titulo="Matrícula" descripcion="Asígnalo ya a su sección, o hazlo luego desde su ficha." opcional>
            {niveles.length === 0 ? (
              <p className="m-0 sm:col-span-2 flex items-start gap-2 text-[12.5px] text-ink/55 dark:text-ink-dark/55">
                <Info size={14} aria-hidden="true" className="mt-0.5 shrink-0" />
                <span>
                  Tu institución todavía no tiene niveles creados.{" "}
                  <Link href="/academico" className="font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
                    Ir a Estructura académica
                  </Link>
                </span>
              </p>
            ) : (
              <>
                <CampoEditable etiqueta="Nivel">
                  <Select value={nivelId} onChange={(e) => elegirNivel(e.target.value)} className="w-full">
                    <option value="">Sin matrícula por ahora</option>
                    {niveles.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.nombre}
                      </option>
                    ))}
                  </Select>
                </CampoEditable>
                <CampoEditable etiqueta="Grado">
                  <Select value={gradoId} onChange={(e) => elegirGrado(e.target.value)} disabled={!nivelId} className="w-full">
                    <option value="">{nivelId ? "Elige un grado..." : "—"}</option>
                    {grados.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.nombre}
                      </option>
                    ))}
                  </Select>
                </CampoEditable>
                <CampoEditable etiqueta="Sección" className="sm:col-span-2">
                  <Select value={seccionId} onChange={(e) => setSeccionId(e.target.value)} disabled={!gradoId} className="w-full">
                    <option value="">{gradoId ? (secciones.length ? "Elige una sección..." : "Este grado no tiene secciones") : "—"}</option>
                    {secciones.map((s) => (
                      <option key={s.id} value={s.id}>
                        Sección {s.nombre} · {s.anio_escolar}
                        {s.turno ? ` · Turno ${s.turno}` : ""}
                      </option>
                    ))}
                  </Select>
                </CampoEditable>
              </>
            )}
          </Bloque>
        </div>

        {/* --- Columna lateral: vista previa + acciones (fija al hacer scroll) --- */}
        <aside className="lg:sticky lg:top-4 space-y-4">
          <div className="rounded-xl border border-teal-600/15 dark:border-teal-accent-dark/20 bg-teal-600/[0.035] dark:bg-teal-accent-dark/[0.05] shadow-sm overflow-hidden">
            <div className="h-1.5 bg-gradient-to-r from-teal-900 via-teal-600 to-teal-400 dark:from-teal-accent-dark/60 dark:to-teal-accent-dark/20" />
            <div className="p-4">
              <p className="m-0 text-[10.5px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Vista previa en el padrón</p>
              <div className="mt-3 flex items-center gap-3">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-teal-900 to-teal-600 font-display text-[16px] font-bold text-white dark:from-teal-accent-dark/40 dark:to-teal-accent-dark/10 dark:text-teal-accent-dark">
                  {iniciales || <UserRound size={20} aria-hidden="true" />}
                </span>
                <div className="min-w-0">
                  <p className={`m-0 font-display text-[16px] font-bold leading-tight break-words ${form.nombres || form.apellidos ? "text-teal-900 dark:text-ink-dark" : "text-ink/30 dark:text-ink-dark/30"}`}>
                    {form.nombres || form.apellidos ? `${form.nombres} ${form.apellidos}`.trim() : "Nombre del alumno"}
                  </p>
                  <p className="m-0 mt-0.5 font-mono text-[11.5px] text-ink/50 dark:text-ink-dark/50">{form.documento_identidad || "Sin documento"}</p>
                </div>
              </div>
              <p className={`m-0 mt-3 rounded-lg px-2.5 py-1.5 text-[12px] ${ubicacion ? "bg-teal-600/10 text-teal-800 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark" : "bg-mist dark:bg-surface-raised-dark text-ink/50 dark:text-ink-dark/50"}`}>
                <GraduationCap size={12} aria-hidden="true" className="inline -mt-0.5 mr-1" />
                {ubicacion ?? "Sin matrícula"}
              </p>

              <ul className="m-0 mt-4 list-none p-0 space-y-1.5 text-[12.5px]">
                <ItemCompleto hecho={completitud.identidad} texto="Identidad (obligatoria)" />
                <ItemCompleto hecho={completitud.fecha} texto="Fecha de nacimiento" />
                <ItemCompleto hecho={completitud.genero} texto="Género" />
                <ItemCompleto hecho={completitud.matricula} texto="Matrícula en una sección" />
              </ul>
              {completitud.identidad && (!completitud.fecha || !completitud.genero) && (
                <p className="m-0 mt-2 text-[11.5px] text-ink/45 dark:text-ink-dark/45">Aparecerá en el filtro “Datos incompletos” del padrón.</p>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Boton type="submit" disabled={guardando || !!creadoSinMatricula} className="w-full inline-flex items-center justify-center gap-2">
              <UserPlus size={15} aria-hidden="true" />
              {guardando ? "Registrando…" : seccionId ? "Registrar y matricular" : "Registrar alumno"}
            </Boton>
            <Link href="/estudiantes" className={claseBoton("secundario", "w-full text-center")}>
              Cancelar
            </Link>
          </div>
        </aside>
      </form>
    </div>
  );
}
