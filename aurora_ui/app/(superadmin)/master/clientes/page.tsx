"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, Search, X, ChevronRight, Mail } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { Badge } from "@/components/ui/Badge";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Migas } from "@/components/ui/Migas";
import { Iniciales } from "@/components/superadmin/Iniciales";
import { diasParaVencer, estadoLicencia, formatearFecha } from "@/components/superadmin/estadoLicencia";
import type { Institucion, InstitucionCreate } from "@/types/api";

type Filtro = "todas" | "activas" | "inactivas" | "vencidas";

const FILTROS: { valor: Filtro; label: string }[] = [
  { valor: "todas", label: "Todas" },
  { valor: "activas", label: "Plan activo" },
  { valor: "inactivas", label: "Plan inactivo" },
  { valor: "vencidas", label: "Licencia vencida" },
];

const FORM_VACIO = {
  nombre: "",
  tipo: "Colegio",
  direccion: "",
  telefono: "",
  email_contacto: "",
  limite_pruebas_mensual_por_alumno: "5",
};

// useSearchParams (?nueva=1, desde el botón "Nueva institución" del
// resumen) necesita un límite de Suspense en una página cliente.
export default function ClientesPage() {
  return (
    <Suspense>
      <ClientesContenido />
    </Suspense>
  );
}

// Gestión de instituciones cliente — el CRUD que superadmin ya hacía a mano
// vía Swagger (POST/GET /instituciones/), ahora con UI real. Acotado a
// datos administrativos del colegio (nombre, contacto, plan/licencia);
// gestionar los usuarios de CADA institución vive en
// /master/clientes/[id], un nivel más abajo.
function ClientesContenido() {
  const searchParams = useSearchParams();
  const [instituciones, setInstituciones] = useState<Institucion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");

  const [mostrarForm, setMostrarForm] = useState(searchParams.get("nueva") === "1");
  const [form, setForm] = useState(FORM_VACIO);
  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState<string | null>(null);

  function cargar() {
    setCargando(true);
    setError(null);
    apiClient
      .get<Institucion[]>("/instituciones/")
      .then(setInstituciones)
      .catch((err) => setError(err.message || "No se pudo cargar el listado de instituciones."))
      .finally(() => setCargando(false));
  }

  useEffect(cargar, []);

  async function crearInstitucion(e: React.FormEvent) {
    e.preventDefault();
    setCreando(true);
    setErrorCrear(null);
    try {
      const payload: InstitucionCreate = {
        nombre: form.nombre,
        tipo: form.tipo || undefined,
        direccion: form.direccion.trim() || null,
        telefono: form.telefono.trim() || null,
        email_contacto: form.email_contacto.trim() || null,
        limite_pruebas_mensual_por_alumno: Number(form.limite_pruebas_mensual_por_alumno) || 5,
      };
      await apiClient.post("/instituciones/", payload);
      setMostrarForm(false);
      setForm(FORM_VACIO);
      cargar();
    } catch (err: any) {
      setErrorCrear(err.message || "No se pudo crear la institución.");
    } finally {
      setCreando(false);
    }
  }

  const termino = busqueda.trim().toLowerCase();
  const visibles = instituciones.filter((inst) => {
    if (filtro === "activas" && !inst.plan_activo) return false;
    if (filtro === "inactivas" && inst.plan_activo) return false;
    if (filtro === "vencidas" && estadoLicencia(inst) !== "vencida") return false;
    if (!termino) return true;
    return [inst.nombre, inst.tipo, inst.email_contacto].some((v) => v?.toLowerCase().includes(termino));
  });

  function conteo(f: Filtro): number {
    if (f === "activas") return instituciones.filter((i) => i.plan_activo).length;
    if (f === "inactivas") return instituciones.filter((i) => !i.plan_activo).length;
    if (f === "vencidas") return instituciones.filter((i) => estadoLicencia(i) === "vencida").length;
    return instituciones.length;
  }

  return (
    <div className="space-y-6">
      <div>
        <Migas items={[{ label: "Panel interno", href: "/master" }, { label: "Instituciones" }]} />
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-teal-900 dark:text-ink-dark">
              Instituciones cliente
            </h1>
            <p className="mt-1 text-sm text-ink/55 dark:text-ink-dark/55">
              Colegios con acceso a AuroraSoft, su plan y su licencia.
            </p>
          </div>
          {!mostrarForm && (
            <Boton onClick={() => setMostrarForm(true)} className="inline-flex items-center justify-center gap-1.5">
              <Plus size={16} strokeWidth={2.2} aria-hidden="true" />
              Nueva institución
            </Boton>
          )}
        </div>
      </div>

      {mostrarForm && (
        <form
          onSubmit={crearInstitucion}
          className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm"
        >
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
            <h2 className="font-display text-base font-semibold text-teal-900 dark:text-ink-dark">Nueva institución</h2>
            <button
              type="button"
              onClick={() => {
                setMostrarForm(false);
                setErrorCrear(null);
              }}
              aria-label="Cerrar formulario"
              className="p-1.5 rounded-lg text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-raised-dark"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <CampoEditable etiqueta="Nombre" className="sm:col-span-2">
              <Input required value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Ej. Colegio San Martín" />
            </CampoEditable>
            <CampoEditable etiqueta="Tipo">
              <Input value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} placeholder="Colegio" />
            </CampoEditable>
            <CampoEditable etiqueta="Límite de pruebas mensual por alumno">
              <Input
                type="number"
                min={1}
                value={form.limite_pruebas_mensual_por_alumno}
                onChange={(e) => setForm({ ...form, limite_pruebas_mensual_por_alumno: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Correo de contacto (opcional)">
              <Input type="email" value={form.email_contacto} onChange={(e) => setForm({ ...form, email_contacto: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Teléfono (opcional)">
              <Input value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Dirección (opcional)" className="sm:col-span-2">
              <Input value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
            </CampoEditable>
          </div>
          <div className="flex flex-col-reverse gap-3 px-5 py-4 border-t border-border dark:border-border-dark sm:flex-row sm:items-center sm:justify-end">
            <TextoError className="sm:mr-auto">{errorCrear}</TextoError>
            <Boton type="button" variante="secundario" onClick={() => setMostrarForm(false)}>
              Cancelar
            </Boton>
            <Boton type="submit" disabled={creando}>
              {creando ? "Creando..." : "Crear institución"}
            </Boton>
          </div>
        </form>
      )}

      <TextoError>{error}</TextoError>

      <section className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden">
        {/* Buscador + filtros */}
        <div className="flex flex-col gap-3 p-4 border-b border-border dark:border-border-dark lg:flex-row lg:items-center">
          <div className="relative lg:w-80">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink/35 dark:text-ink-dark/35" aria-hidden="true" />
            <Input
              type="search"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por nombre, tipo o correo"
              aria-label="Buscar institución"
              className="w-full pl-9"
            />
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 lg:pb-0 lg:ml-auto">
            {FILTROS.map((f) => (
              <button
                key={f.valor}
                type="button"
                onClick={() => setFiltro(f.valor)}
                aria-pressed={filtro === f.valor}
                className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                  filtro === f.valor
                    ? "bg-teal-900 text-white dark:bg-teal-accent-dark dark:text-mist-dark"
                    : "bg-mist text-ink/65 hover:bg-border dark:bg-surface-raised-dark dark:text-ink-dark/65 dark:hover:bg-border-dark"
                }`}
              >
                {f.label}
                <span className="ml-1.5 opacity-70">{cargando ? "·" : conteo(f.valor)}</span>
              </button>
            ))}
          </div>
        </div>

        {cargando ? (
          <div className="p-5 space-y-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="h-9 w-9 animate-pulse rounded-lg bg-border/70 dark:bg-border-dark" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3.5 w-1/3 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
                  <div className="h-3 w-1/4 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
                </div>
              </div>
            ))}
          </div>
        ) : visibles.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-ink/50 dark:text-ink-dark/50">
            {instituciones.length === 0
              ? "Todavía no hay instituciones registradas."
              : "Ninguna institución coincide con la búsqueda o el filtro."}
          </p>
        ) : (
          <>
            {/* Tabla (escritorio) */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-mist/70 dark:bg-surface-raised-dark text-left text-xs font-semibold uppercase tracking-wide text-ink/50 dark:text-ink-dark/50">
                    <th className="px-5 py-3">Institución</th>
                    <th className="px-5 py-3">Contacto</th>
                    <th className="px-5 py-3">Plan</th>
                    <th className="px-5 py-3">Licencia</th>
                    <th className="px-5 py-3"><span className="sr-only">Acciones</span></th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((inst) => (
                    <tr
                      key={inst.id}
                      className="border-t border-border dark:border-border-dark hover:bg-mist/50 dark:hover:bg-surface-raised-dark/60 transition-colors"
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <Iniciales nombre={inst.nombre} />
                          <div className="min-w-0">
                            <p className="font-medium text-ink dark:text-ink-dark">{inst.nombre}</p>
                            <p className="text-xs text-ink/50 dark:text-ink-dark/50">{inst.tipo || "Colegio"}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-3 text-xs text-ink/70 dark:text-ink-dark/70">
                        {inst.email_contacto || <span className="italic text-ink/40 dark:text-ink-dark/40">Sin correo</span>}
                      </td>
                      <td className="px-5 py-3">
                        <Badge tono={inst.plan_activo ? "teal" : "neutro"}>{inst.plan_activo ? "Activo" : "Inactivo"}</Badge>
                      </td>
                      <td className="px-5 py-3 text-xs">
                        <TextoLicencia inst={inst} />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <Link
                          href={`/master/clientes/${inst.id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline"
                        >
                          Administrar
                          <ChevronRight size={14} aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Tarjetas (móvil) */}
            <ul className="md:hidden divide-y divide-border dark:divide-border-dark">
              {visibles.map((inst) => (
                <li key={inst.id}>
                  <Link
                    href={`/master/clientes/${inst.id}`}
                    className="block px-4 py-4 hover:bg-mist/50 dark:hover:bg-surface-raised-dark/60"
                  >
                    <div className="flex items-start gap-3">
                      <Iniciales nombre={inst.nombre} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium text-ink dark:text-ink-dark">{inst.nombre}</p>
                          <Badge tono={inst.plan_activo ? "teal" : "neutro"}>{inst.plan_activo ? "Activo" : "Inactivo"}</Badge>
                        </div>
                        <p className="text-xs text-ink/50 dark:text-ink-dark/50">{inst.tipo || "Colegio"}</p>
                        <div className="mt-2 space-y-1 text-xs text-ink/65 dark:text-ink-dark/65">
                          {inst.email_contacto && (
                            <p className="flex items-center gap-1.5 truncate">
                              <Mail size={13} aria-hidden="true" />
                              {inst.email_contacto}
                            </p>
                          )}
                          <p>
                            Licencia: <TextoLicencia inst={inst} />
                          </p>
                        </div>
                      </div>
                      <ChevronRight size={16} className="mt-1 text-ink/30 dark:text-ink-dark/30 shrink-0" aria-hidden="true" />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function TextoLicencia({ inst }: { inst: Institucion }) {
  const estado = estadoLicencia(inst);
  if (estado === "sin_caducidad") return <span className="italic text-ink/40 dark:text-ink-dark/40">Sin caducidad</span>;
  const fecha = formatearFecha(inst.fecha_vencimiento_licencia);
  if (estado === "vencida") return <span className="font-medium text-red-700 dark:text-red-300">{fecha} (vencida)</span>;
  if (estado === "por_vencer") {
    const dias = diasParaVencer(inst);
    return (
      <span className="font-medium text-ink dark:text-ink-dark">
        {fecha} <span className="text-ink/50 dark:text-ink-dark/50 font-normal">· vence en {dias} {dias === 1 ? "día" : "días"}</span>
      </span>
    );
  }
  return <span className="text-ink/70 dark:text-ink-dark/70">{fecha}</span>;
}
