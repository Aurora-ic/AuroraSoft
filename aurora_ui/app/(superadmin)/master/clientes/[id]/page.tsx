"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { Badge } from "@/components/ui/Badge";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { TheadFila, Th } from "@/components/ui/Tabla";
import type { Institucion, InstitucionUpdate, Usuario, UsuarioCreate, Rol } from "@/types/api";

const ROLES_ASIGNABLES: Rol[] = ["admin", "psicologo", "colegio"];

// Convierte el datetime del backend al formato que acepta <input type="date">
// (mismo criterio que isoParaInputLocal en campanas/[id]/dashboard/page.tsx).
function isoParaInputFecha(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

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

  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [cargandoUsuarios, setCargandoUsuarios] = useState(true);
  const [errorUsuarios, setErrorUsuarios] = useState<string | null>(null);

  const [mostrarFormUsuario, setMostrarFormUsuario] = useState(false);
  const [formUsuario, setFormUsuario] = useState({ email: "", password: "", nombre_completo: "", rol: "psicologo" as Rol });
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

  async function guardarInstitucion(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true);
    setErrorGuardar(null);
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

  if (cargando) return <p className="text-sm text-ink/40">Cargando...</p>;
  if (error && !institucion) return <TextoError>{error}</TextoError>;
  if (!institucion) return null;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <Link href="/master/clientes" className="text-xs text-ink/50 hover:underline">
          ← Instituciones
        </Link>
        <h1 className="font-display text-2xl text-teal-900 mt-1">{institucion.nombre}</h1>
      </div>

      <section className="bg-white rounded-card border border-border p-6 space-y-4">
        <h2 className="font-display text-lg font-semibold text-teal-900">Datos de la institución</h2>
        <form onSubmit={guardarInstitucion} className="space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <CampoEditable etiqueta="Nombre">
              <Input required value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Tipo">
              <Input value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Dirección">
              <Input value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Teléfono">
              <Input value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Correo de contacto">
              <Input type="email" value={form.email_contacto} onChange={(e) => setForm({ ...form, email_contacto: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Límite de pruebas mensual por alumno">
              <Input
                type="number"
                min={1}
                value={form.limite_pruebas_mensual_por_alumno}
                onChange={(e) => setForm({ ...form, limite_pruebas_mensual_por_alumno: e.target.value })}
              />
            </CampoEditable>
            <CampoEditable etiqueta="Vencimiento de licencia (opcional)">
              <Input
                type="date"
                value={form.fecha_vencimiento_licencia}
                onChange={(e) => setForm({ ...form, fecha_vencimiento_licencia: e.target.value })}
              />
            </CampoEditable>
            <label className="flex items-center gap-2 text-sm pt-6">
              <input
                type="checkbox"
                checked={form.plan_activo}
                onChange={(e) => setForm({ ...form, plan_activo: e.target.checked })}
              />
              Plan activo
            </label>
          </div>
          <TextoError>{errorGuardar}</TextoError>
          <Boton type="submit" disabled={guardando}>
            {guardando ? "Guardando..." : "Guardar cambios"}
          </Boton>
        </form>
      </section>

      <section className="bg-white rounded-card border border-border p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold text-teal-900">Usuarios</h2>
          <Boton variante="secundario" onClick={() => setMostrarFormUsuario((v) => !v)}>
            {mostrarFormUsuario ? "Cancelar" : "+ Nuevo usuario"}
          </Boton>
        </div>

        {mostrarFormUsuario && (
          <form onSubmit={crearUsuario} className="space-y-3 border-b border-border pb-4">
            <div className="grid sm:grid-cols-2 gap-3">
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
                <Input
                  type="password"
                  required
                  value={formUsuario.password}
                  onChange={(e) => setFormUsuario({ ...formUsuario, password: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Rol">
                <Select value={formUsuario.rol} onChange={(e) => setFormUsuario({ ...formUsuario, rol: e.target.value as Rol })}>
                  {ROLES_ASIGNABLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </Select>
              </CampoEditable>
            </div>
            <TextoError>{errorCrearUsuario}</TextoError>
            <Boton type="submit" disabled={creandoUsuario}>
              {creandoUsuario ? "Creando..." : "Crear usuario"}
            </Boton>
          </form>
        )}

        <TextoError>{errorUsuarios}</TextoError>

        {cargandoUsuarios ? (
          <p className="text-sm text-ink/40">Cargando...</p>
        ) : usuarios.length === 0 ? (
          <p className="text-sm text-ink/60 italic">Esta institución todavía no tiene usuarios.</p>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead>
              <TheadFila>
                <Th className="px-3 py-2">Nombre</Th>
                <Th className="px-3 py-2">Correo</Th>
                <Th className="px-3 py-2">Rol</Th>
                <Th className="px-3 py-2">Estado</Th>
                <Th className="px-3 py-2"></Th>
              </TheadFila>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2">{u.nombre_completo}</td>
                  <td className="px-3 py-2 text-xs text-ink/70">{u.email}</td>
                  <td className="px-3 py-2 text-xs">{u.rol}</td>
                  <td className="px-3 py-2">
                    <Badge tono={u.activo ? "teal" : "neutro"}>{u.activo ? "Activo" : "Desactivado"}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => alternarActivo(u)} className="text-xs text-teal-700 hover:underline">
                      {u.activo ? "Desactivar" : "Reactivar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
