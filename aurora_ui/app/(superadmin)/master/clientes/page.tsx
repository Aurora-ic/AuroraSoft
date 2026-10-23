"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { Badge } from "@/components/ui/Badge";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { TheadFila, Th } from "@/components/ui/Tabla";
import type { Institucion, InstitucionCreate } from "@/types/api";

// Gestión de instituciones cliente — el CRUD que superadmin ya hacía a mano
// vía Swagger (POST/GET /instituciones/), ahora con UI real. Acotado a
// datos administrativos del colegio (nombre, contacto, plan/licencia);
// gestionar los usuarios de CADA institución vive en
// /master/clientes/[id], un nivel más abajo.
export default function ClientesPage() {
  const [instituciones, setInstituciones] = useState<Institucion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [mostrarForm, setMostrarForm] = useState(false);
  const [form, setForm] = useState({
    nombre: "",
    tipo: "Colegio",
    direccion: "",
    telefono: "",
    email_contacto: "",
    limite_pruebas_mensual_por_alumno: "5",
  });
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
      setForm({ nombre: "", tipo: "Colegio", direccion: "", telefono: "", email_contacto: "", limite_pruebas_mensual_por_alumno: "5" });
      cargar();
    } catch (err: any) {
      setErrorCrear(err.message || "No se pudo crear la institución.");
    } finally {
      setCreando(false);
    }
  }

  function licenciaVencida(institucion: Institucion): boolean {
    if (!institucion.fecha_vencimiento_licencia) return false;
    return new Date(institucion.fecha_vencimiento_licencia).getTime() < Date.now();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/master" className="text-xs text-ink/50 hover:underline">
            ← Panel interno
          </Link>
          <h1 className="font-display text-2xl text-teal-900 mt-1">Instituciones cliente</h1>
        </div>
        <Boton onClick={() => setMostrarForm((v) => !v)}>{mostrarForm ? "Cancelar" : "+ Nueva institución"}</Boton>
      </div>

      {mostrarForm && (
        <form onSubmit={crearInstitucion} className="bg-white rounded-card border border-border p-6 space-y-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <CampoEditable etiqueta="Nombre">
              <Input required value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Tipo">
              <Input value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} placeholder="Colegio" />
            </CampoEditable>
            <CampoEditable etiqueta="Dirección (opcional)">
              <Input value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Teléfono (opcional)">
              <Input value={form.telefono} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />
            </CampoEditable>
            <CampoEditable etiqueta="Correo de contacto (opcional)">
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
          </div>
          <TextoError>{errorCrear}</TextoError>
          <Boton type="submit" disabled={creando}>
            {creando ? "Creando..." : "Crear institución"}
          </Boton>
        </form>
      )}

      <TextoError>{error}</TextoError>

      {cargando ? (
        <p className="text-sm text-ink/40">Cargando...</p>
      ) : instituciones.length === 0 ? (
        <p className="text-sm text-ink/60 italic">Todavía no hay instituciones registradas.</p>
      ) : (
        <div className="rounded-card border border-border bg-white shadow-sm overflow-hidden">
          <table className="w-full text-sm border-collapse">
            <thead>
              <TheadFila>
                <Th className="px-5 py-3">Nombre</Th>
                <Th className="px-5 py-3">Contacto</Th>
                <Th className="px-5 py-3">Plan</Th>
                <Th className="px-5 py-3">Licencia</Th>
                <Th className="px-5 py-3"></Th>
              </TheadFila>
            </thead>
            <tbody>
              {instituciones.map((inst) => (
                <tr key={inst.id} className="border-b border-border last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-medium text-ink">{inst.nombre}</p>
                    <p className="text-xs text-ink/50">{inst.tipo || "Colegio"}</p>
                  </td>
                  <td className="px-5 py-3 text-xs text-ink/70">
                    {inst.email_contacto || <span className="italic text-ink/40">Sin correo</span>}
                  </td>
                  <td className="px-5 py-3">
                    <Badge tono={inst.plan_activo ? "teal" : "neutro"}>{inst.plan_activo ? "Activo" : "Inactivo"}</Badge>
                  </td>
                  <td className="px-5 py-3 text-xs">
                    {inst.fecha_vencimiento_licencia ? (
                      <span className={licenciaVencida(inst) ? "text-red-700 font-medium" : "text-ink/70"}>
                        {new Date(inst.fecha_vencimiento_licencia).toLocaleDateString("es-PE")}
                        {licenciaVencida(inst) ? " (vencida)" : ""}
                      </span>
                    ) : (
                      <span className="italic text-ink/40">Sin caducidad</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Link href={`/master/clientes/${inst.id}`} className="text-xs text-teal-700 hover:underline font-medium">
                      Administrar →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
