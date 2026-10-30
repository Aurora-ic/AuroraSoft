"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Plus, X, Eye, EyeOff, CircleCheck, Users } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { Badge } from "@/components/ui/Badge";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Migas } from "@/components/ui/Migas";
import { Iniciales } from "@/components/superadmin/Iniciales";
import { diasParaVencer, estadoLicencia, formatearFecha } from "@/components/superadmin/estadoLicencia";
import type { Institucion, InstitucionUpdate, Usuario, UsuarioCreate, Rol } from "@/types/api";

const ROLES_ASIGNABLES: Rol[] = ["admin", "psicologo", "colegio"];

// Nombre visible y alcance de cada rol — antes el <select> mostraba el
// identificador crudo ("psicologo"), sin decir qué puede ver cada uno.
const INFO_ROL: Record<Rol, { nombre: string; descripcion: string }> = {
  superadmin: { nombre: "Superadmin", descripcion: "Equipo AuroraSoft." },
  admin: { nombre: "Administrador", descripcion: "Gestiona todo el colegio: estudiantes, campañas, documentos y usuarios." },
  psicologo: { nombre: "Psicólogo", descripcion: "Trabajo clínico: campañas, casos en riesgo, informes, citas y seguimiento." },
  colegio: { nombre: "Colegio", descripcion: "Vista de dirección, sin acceso a contenido clínico." },
};

// Convierte el datetime del backend al formato que acepta <input type="date">
// (mismo criterio que isoParaInputLocal en campanas/[id]/dashboard/page.tsx).
function isoParaInputFecha(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

const CLASE_TARJETA = "rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm";

export default function DetalleInstitucionPage() {
  const params = useParams();
  const institucionId = params.id as string;

  const [institucion, setInstitucion] = useState<Institucion | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    nombre: "", tipo: "", direccion: "", telefono: "", email_contacto: "",
    plan_activo: true, fecha_vencimiento_licencia: "", limite_pruebas_mensual_por_alumno: "5",
  });
  const [guardando, setGuardando] = useState(false);
  const [errorGuardar, setErrorGuardar] = useState<string | null>(null);
  const [guardadoOk, setGuardadoOk] = useState(false);

  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [cargandoUsuarios, setCargandoUsuarios] = useState(true);
  const [errorUsuarios, setErrorUsuarios] = useState<string | null>(null);

  const [mostrarFormUsuario, setMostrarFormUsuario] = useState(false);
  const [formUsuario, setFormUsuario] = useState({ email: "", password: "", nombre_completo: "", rol: "psicologo" as Rol });
  const [verPassword, setVerPassword] = useState(false);
  const [creandoUsuario, setCreandoUsuario] = useState(false);
  const [errorCrearUsuario, setErrorCrearUsuario] = useState<string | null>(null);

  function cargarInstitucion() {
    if (!institucionId) return;
    setCargando(true);
    setError(null);
    apiClient
      .get<Institucion[]>("/instituciones/")
      .then((todas) => {
        const encontrada = todas.find((i) => i.id === Number(institucionId));
        if (!encontrada) {
          setError("Institución no encontrada.");
          return;
        }
        setInstitucion(encontrada);
        setForm({
          nombre: encontrada.nombre,
          tipo: encontrada.tipo || "",
          direccion: encontrada.direccion || "",
          telefono: encontrada.telefono || "",
          email_contacto: encontrada.email_contacto || "",
          plan_activo: encontrada.plan_activo,
          fecha_vencimiento_licencia: isoParaInputFecha(encontrada.fecha_vencimiento_licencia),
          limite_pruebas_mensual_por_alumno: String(encontrada.limite_pruebas_mensual_por_alumno),
        });
      })
      .catch((err) => setError(err.message || "No se pudo cargar la institución."))
      .finally(() => setCargando(false));
  }

  function cargarUsuarios() {
    if (!institucionId) return;
    setCargandoUsuarios(true);
    setErrorUsuarios(null);
    apiClient
      .get<Usuario[]>(`/auth/usuarios/?institucion_id=${institucionId}`)
      .then(setUsuarios)
      .catch((err) => setErrorUsuarios(err.message || "No se pudo cargar el listado de usuarios."))
      .finally(() => setCargandoUsuarios(false));
  }

  useEffect(cargarInstitucion, [institucionId]);
  useEffect(cargarUsuarios, [institucionId]);

  // El aviso "Cambios guardados" se apaga solo a los pocos segundos.
  useEffect(() => {
    if (!guardadoOk) return;
    const t = setTimeout(() => setGuardadoOk(false), 3000);
    return () => clearTimeout(t);
  }, [guardadoOk]);

  async function guardarInstitucion(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true);
    setErrorGuardar(null);
    setGuardadoOk(false);
    try {
      const payload: InstitucionUpdate = {
        nombre: form.nombre,
        tipo: form.tipo || undefined,
        direccion: form.direccion.trim() || null,
        telefono: form.telefono.trim() || null,
        email_contacto: form.email_contacto.trim() || null,
        plan_activo: form.plan_activo,
        fecha_vencimiento_licencia: form.fecha_vencimiento_licencia
          ? new Date(form.fecha_vencimiento_licencia).toISOString()
          : null,
        limite_pruebas_mensual_por_alumno: Number(form.limite_pruebas_mensual_por_alumno) || 1,
      };
      const actualizada = await apiClient.patch<Institucion>(`/instituciones/${institucionId}`, payload);
      setInstitucion(actualizada);
      setGuardadoOk(true);
    } catch (err: any) {
      setErrorGuardar(err.message || "No se pudo guardar la institución.");
    } finally {
      setGuardando(false);
    }
  }

  async function crearUsuario(e: React.FormEvent) {
    e.preventDefault();
    setCreandoUsuario(true);
    setErrorCrearUsuario(null);
    try {
      const payload: UsuarioCreate = {
        email: formUsuario.email,
        password: formUsuario.password,
        nombre_completo: formUsuario.nombre_completo,
        rol: formUsuario.rol,
        institucion_id: Number(institucionId),
      };
      await apiClient.post("/auth/registro", payload);
      setMostrarFormUsuario(false);
      setVerPassword(false);
      setFormUsuario({ email: "", password: "", nombre_completo: "", rol: "psicologo" });
      cargarUsuarios();
    } catch (err: any) {
      setErrorCrearUsuario(err.message || "No se pudo crear el usuario.");
    } finally {
      setCreandoUsuario(false);
    }
  }

  async function alternarActivo(usuario: Usuario) {
    try {
      const actualizado = await apiClient.patch<Usuario>(`/auth/usuarios/${usuario.id}`, { activo: !usuario.activo });
      setUsuarios((prev) => prev.map((u) => (u.id === usuario.id ? actualizado : u)));
    } catch (err: any) {
      setErrorUsuarios(err.message || "No se pudo cambiar el estado del usuario.");
    }
  }

  if (cargando) {
    return (
      <div className="space-y-6">
        <div className={`${CLASE_TARJETA} p-6 flex items-center gap-4`}>
          <div className="h-14 w-14 animate-pulse rounded-lg bg-border/70 dark:bg-border-dark" />
          <div className="flex-1 space-y-2">
            <div className="h-5 w-1/3 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
            <div className="h-3.5 w-1/4 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
          </div>
        </div>
        <div className={`${CLASE_TARJETA} h-72 animate-pulse`} />
      </div>
    );
  }
  if (error && !institucion) return <TextoError>{error}</TextoError>;
  if (!institucion) return null;

  const estado = estadoLicencia(institucion);
  const dias = diasParaVencer(institucion);
  const activos = usuarios.filter((u) => u.activo).length;

  return (
    <div className="space-y-6">
      <Migas
        items={[
          { label: "Panel interno", href: "/master" },
          { label: "Instituciones", href: "/master/clientes" },
          { label: institucion.nombre },
        ]}
      />

      {/* Encabezado con el estado de un vistazo */}
      <div className={`${CLASE_TARJETA} p-5 sm:p-6 flex flex-col gap-4 sm:flex-row sm:items-center`}>
        <Iniciales nombre={institucion.nombre} grande />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-xl sm:text-2xl font-semibold text-teal-900 dark:text-ink-dark break-words">
            {institucion.nombre}
          </h1>
          <p className="mt-0.5 text-sm text-ink/55 dark:text-ink-dark/55">
            {institucion.tipo || "Colegio"} · Cliente desde {formatearFecha(institucion.fecha_registro)}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tono={institucion.plan_activo ? "teal" : "neutro"}>
              {institucion.plan_activo ? "Plan activo" : "Plan inactivo"}
            </Badge>
            {estado === "vencida" && <Badge tono="error">Licencia vencida</Badge>}
            {estado === "por_vencer" && (
              <Badge tono="teal-suave">
                Vence en {dias} {dias === 1 ? "día" : "días"}
              </Badge>
            )}
            {estado === "vigente" && <Badge tono="teal-suave">Licencia hasta {formatearFecha(institucion.fecha_vencimiento_licencia)}</Badge>}
            {estado === "sin_caducidad" && <Badge tono="neutro">Licencia sin caducidad</Badge>}
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-mist dark:bg-surface-raised-dark px-4 py-3 sm:flex-col sm:items-end sm:gap-0">
          <Users size={16} className="text-ink/45 dark:text-ink-dark/45 sm:hidden" aria-hidden="true" />
          <p className="font-display text-xl font-semibold text-teal-900 dark:text-ink-dark">
            {cargandoUsuarios ? "…" : usuarios.length}
          </p>
          <p className="text-xs text-ink/55 dark:text-ink-dark/55">
            {cargandoUsuarios ? "usuarios" : `usuarios · ${activos} activos`}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 items-start">
        {/* Datos de la institución */}
        <section className={`${CLASE_TARJETA} xl:col-span-3`}>
          <div className="px-5 py-4 border-b border-border dark:border-border-dark">
            <h2 className="font-display text-base font-semibold text-teal-900 dark:text-ink-dark">Datos de la institución</h2>
          </div>
          <form onSubmit={guardarInstitucion}>
            <div className="p-5 space-y-6 text-sm">
              <fieldset className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
                  Información general
                </legend>
                <CampoEditable etiqueta="Nombre" className="sm:col-span-2">
                  <Input required value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
                </CampoEditable>
                <CampoEditable etiqueta="Tipo">
                  <Input value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} />
                </CampoEditable>
                <CampoEditable etiqueta="Teléfono">
                  <Input value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />
                </CampoEditable>
                <CampoEditable etiqueta="Correo de contacto">
                  <Input type="email" value={form.email_contacto} onChange={(e) => setForm({ ...form, email_contacto: e.target.value })} />
                </CampoEditable>
                <CampoEditable etiqueta="Dirección">
                  <Input value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
                </CampoEditable>
              </fieldset>

              <fieldset className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <legend className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">
                  Plan y licencia
                </legend>
                <CampoEditable etiqueta="Vencimiento de licencia (opcional)">
                  <Input
                    type="date"
                    value={form.fecha_vencimiento_licencia}
                    onChange={(e) => setForm({ ...form, fecha_vencimiento_licencia: e.target.value })}
                  />
                </CampoEditable>
                <CampoEditable etiqueta="Límite de pruebas mensual por alumno">
                  <Input
                    type="number"
                    min={1}
                    value={form.limite_pruebas_mensual_por_alumno}
                    onChange={(e) => setForm({ ...form, limite_pruebas_mensual_por_alumno: e.target.value })}
                  />
                </CampoEditable>
                <label className="sm:col-span-2 flex items-center justify-between gap-4 rounded-card border border-border dark:border-border-dark px-4 py-3 cursor-pointer">
                  <span>
                    <span className="block font-medium text-ink dark:text-ink-dark">Plan activo</span>
                    <span className="block text-xs text-ink/50 dark:text-ink-dark/50">
                      Si se desactiva, el colegio deja de poder usar la plataforma.
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={form.plan_activo}
                    onChange={(e) => setForm({ ...form, plan_activo: e.target.checked })}
                  />
                  <span
                    aria-hidden="true"
                    className="relative h-6 w-11 shrink-0 rounded-full bg-border dark:bg-border-dark transition-colors peer-checked:bg-teal-600 dark:peer-checked:bg-teal-accent-dark peer-focus-visible:ring-2 peer-focus-visible:ring-teal-400 after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition-transform peer-checked:after:translate-x-5"
                  />
                </label>
              </fieldset>
            </div>
            <div className="flex flex-col-reverse gap-3 px-5 py-4 border-t border-border dark:border-border-dark sm:flex-row sm:items-center sm:justify-end">
              <div className="sm:mr-auto">
                <TextoError>{errorGuardar}</TextoError>
                {guardadoOk && (
                  <p className="flex items-center gap-1.5 text-sm font-medium text-teal-700 dark:text-teal-accent-dark" role="status">
                    <CircleCheck size={16} aria-hidden="true" />
                    Cambios guardados
                  </p>
                )}
              </div>
              <Boton type="submit" disabled={guardando}>
                {guardando ? "Guardando..." : "Guardar cambios"}
              </Boton>
            </div>
          </form>
        </section>

        {/* Usuarios */}
        <section className={`${CLASE_TARJETA} xl:col-span-2`}>
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
            <h2 className="font-display text-base font-semibold text-teal-900 dark:text-ink-dark">Usuarios</h2>
            {!mostrarFormUsuario && (
              <Boton
                variante="secundario"
                onClick={() => setMostrarFormUsuario(true)}
                className="inline-flex items-center gap-1.5 !px-3 !py-1.5"
              >
                <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
                Nuevo
              </Boton>
            )}
          </div>

          {mostrarFormUsuario && (
            <form onSubmit={crearUsuario} className="p-5 space-y-4 text-sm bg-mist/50 dark:bg-surface-raised-dark/50 border-b border-border dark:border-border-dark">
              <div className="flex items-center justify-between">
                <p className="font-semibold text-ink dark:text-ink-dark">Nuevo usuario</p>
                <button
                  type="button"
                  onClick={() => {
                    setMostrarFormUsuario(false);
                    setErrorCrearUsuario(null);
                  }}
                  aria-label="Cerrar formulario"
                  className="p-1 rounded-lg text-ink/50 dark:text-ink-dark/50 hover:bg-mist dark:hover:bg-surface-dark"
                >
                  <X size={16} aria-hidden="true" />
                </button>
              </div>
              <CampoEditable etiqueta="Nombre completo">
                <Input
                  required
                  value={formUsuario.nombre_completo}
                  onChange={(e) => setFormUsuario({ ...formUsuario, nombre_completo: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Correo">
                <Input
                  type="email"
                  required
                  value={formUsuario.email}
                  onChange={(e) => setFormUsuario({ ...formUsuario, email: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Contraseña inicial">
                <div className="relative">
                  <Input
                    type={verPassword ? "text" : "password"}
                    required
                    value={formUsuario.password}
                    onChange={(e) => setFormUsuario({ ...formUsuario, password: e.target.value })}
                    className="w-full pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setVerPassword((v) => !v)}
                    aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:hover:text-ink-dark"
                  >
                    {verPassword ? <EyeOff size={16} aria-hidden="true" /> : <Eye size={16} aria-hidden="true" />}
                  </button>
                </div>
              </CampoEditable>
              <CampoEditable etiqueta="Rol">
                <Select value={formUsuario.rol} onChange={(e) => setFormUsuario({ ...formUsuario, rol: e.target.value as Rol })}>
                  {ROLES_ASIGNABLES.map((r) => (
                    <option key={r} value={r}>
                      {INFO_ROL[r].nombre}
                    </option>
                  ))}
                </Select>
                <span className="text-xs text-ink/50 dark:text-ink-dark/50">{INFO_ROL[formUsuario.rol].descripcion}</span>
              </CampoEditable>
              <TextoError>{errorCrearUsuario}</TextoError>
              <Boton type="submit" disabled={creandoUsuario} className="w-full">
                {creandoUsuario ? "Creando..." : "Crear usuario"}
              </Boton>
            </form>
          )}

          <div className="px-5 pt-3">
            <TextoError>{errorUsuarios}</TextoError>
          </div>

          {cargandoUsuarios ? (
            <div className="px-5 pb-5 pt-2 space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 animate-pulse rounded-lg bg-border/60 dark:bg-border-dark" />
              ))}
            </div>
          ) : usuarios.length === 0 ? (
            <p className="px-5 pb-10 pt-6 text-center text-sm text-ink/50 dark:text-ink-dark/50">
              Esta institución todavía no tiene usuarios.
            </p>
          ) : (
            <ul className="divide-y divide-border dark:divide-border-dark pb-1">
              {usuarios.map((u) => (
                <li key={u.id} className={`flex items-center gap-3 px-5 py-3 ${u.activo ? "" : "opacity-60"}`}>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-mist dark:bg-surface-raised-dark text-[12px] font-bold text-teal-700 dark:text-teal-accent-dark">
                    {(u.nombre_completo?.[0] || u.email[0] || "?").toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink dark:text-ink-dark truncate">{u.nombre_completo}</p>
                    <p className="text-xs text-ink/55 dark:text-ink-dark/55 truncate" title={u.email}>
                      {u.email}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <Badge tono="teal-suave">{INFO_ROL[u.rol]?.nombre ?? u.rol}</Badge>
                      {!u.activo && <Badge tono="neutro">Desactivado</Badge>}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => alternarActivo(u)}
                    className={`shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                      u.activo
                        ? "text-ink/60 dark:text-ink-dark/60 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-500/10 dark:hover:text-red-300"
                        : "text-teal-700 dark:text-teal-accent-dark hover:bg-teal-600/10"
                    }`}
                  >
                    {u.activo ? "Desactivar" : "Reactivar"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
