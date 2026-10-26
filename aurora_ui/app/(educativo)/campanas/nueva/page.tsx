"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import type {
  Prueba,
  Evaluacion,
  EvaluacionCreate,
  Persona,
  MatriculaRosterResponse,
  ConsentimientosCombinados,
} from "@/types/api";

// Flujo en 3 pasos, uno a la vez — crear la campaña, matricular el padrón
// (o parte de él), y ver los links mágicos generados. Sin wizard de rutas
// separadas: todo en esta misma página, igual de simple que
// estudiantes/importar/page.tsx.
export default function NuevaCampanaPage() {
  const { sesion } = useAuth();
  const router = useRouter();

  const [pruebas, setPruebas] = useState<Prueba[]>([]);
  const [errorPruebas, setErrorPruebas] = useState<string | null>(null);

  const [form, setForm] = useState({ prueba_id: "", nombre_grupo: "", fecha_fin: "" });
  const [creando, setCreando] = useState(false);
  const [errorCrear, setErrorCrear] = useState<string | null>(null);
  const [campana, setCampana] = useState<Evaluacion | null>(null);

  const [personas, setPersonas] = useState<Persona[]>([]);
  const [errorPersonas, setErrorPersonas] = useState<string | null>(null);
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  const [matriculando, setMatriculando] = useState(false);
  const [errorMatricular, setErrorMatricular] = useState<string | null>(null);
  const [resultadoMatricula, setResultadoMatricula] = useState<MatriculaRosterResponse | null>(null);

  // Estado preventivo del consentimiento del apoderado (el único siempre
  // obligatorio, con o sin la política institucional de asentimiento) para
  // cada persona del padrón — así el psicólogo ve de antemano quién no tiene
  // consentimiento vigente, en vez de enterarse recién en el resultado de
  // "matricular-roster" (que ya existía, pero es post-hoc). Una llamada por
  // alumno (no hay endpoint batch todavía); aceptable porque esta pantalla
  // ya carga el padrón completo de una sola vez con el mismo costo.
  const [estadosConsentimiento, setEstadosConsentimiento] = useState<Map<number, boolean>>(new Map());
  const [cargandoConsentimientos, setCargandoConsentimientos] = useState(false);

  useEffect(() => {
    apiClient
      .get<Prueba[]>("/educativo/pruebas/")
      .then((datos) => setPruebas(datos.filter((p) => p.activa)))
      .catch((err) => setErrorPruebas(err.message || "No se pudo cargar el catálogo de pruebas."));
  }, []);

  async function crearCampana(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) {
      setErrorCrear("Tu sesión no tiene una institución asociada — esta pantalla es para admin/psicólogo de un colegio.");
      return;
    }
    setCreando(true);
    setErrorCrear(null);
    try {
      const payload: EvaluacionCreate = {
        prueba_id: Number(form.prueba_id),
        nombre_grupo: form.nombre_grupo,
        institucion_id: sesion.institucionId,
        fecha_fin: form.fecha_fin ? new Date(form.fecha_fin).toISOString() : null,
      };
      const nueva = await apiClient.post<Evaluacion>("/educativo/campanas/", payload);
      setCampana(nueva);
      // Cargar el padrón recién ahora -- no hace falta antes de tener campaña.
      // 🆕 Paginación real: este selector necesita el padrón COMPLETO (el
      // usuario elige a quién matricular), no una página de 50 — por eso
      // usa getTodasLasPaginas en vez de get.
      const datosPersonas = await apiClient.getTodasLasPaginas<Persona>(`/admin/personas/${sesion.institucionId}`);
      setPersonas(datosPersonas);
      cargarEstadosConsentimiento(datosPersonas);
    } catch (err: any) {
      setErrorCrear(err.message || "No se pudo crear la campaña.");
    } finally {
      setCreando(false);
    }
  }

  async function cargarEstadosConsentimiento(lista: Persona[]) {
    setCargandoConsentimientos(true);
    try {
      const resultados = await Promise.all(
        lista.map((p) =>
          apiClient
            .get<ConsentimientosCombinados>(`/admin/personas/${p.id}/consentimientos`)
            .then((r): [number, boolean] => [p.id, r.apoderado.tiene_consentimiento_vigente])
            .catch((): [number, boolean | null] => [p.id, null]),
        ),
      );
      setEstadosConsentimiento(
        new Map(resultados.filter((r): r is [number, boolean] => r[1] !== null)),
      );
    } finally {
      setCargandoConsentimientos(false);
    }
  }

  function alternarSeleccion(id: number) {
    setSeleccionadas((prev) => {
      const copia = new Set(prev);
      if (copia.has(id)) copia.delete(id);
      else copia.add(id);
      return copia;
    });
  }

  async function matricular() {
    if (!campana || seleccionadas.size === 0) return;
    setMatriculando(true);
    setErrorMatricular(null);
    try {
      const resultado = await apiClient.post<MatriculaRosterResponse>(
        `/educativo/campanas/${campana.id}/matricular-roster`,
        Array.from(seleccionadas),
      );
      setResultadoMatricula(resultado);
    } catch (err: any) {
      setErrorMatricular(err.message || "No se pudo matricular a los alumnos elegidos.");
    } finally {
      setMatriculando(false);
    }
  }

  // 🔧 El backend ya rechaza esto con 403 (`requerir_staff_clinico` en
  // POST /educativo/campanas/ y /matricular-roster — "colegio" nunca está
  // en esa lista), pero esta página no tenía su propio candado: desde que
  // el layout de (educativo) deja entrar a "colegio" (antes lo expulsaba
  // por error, ver app/(educativo)/layout.tsx), ese rol podía llegar hasta
  // acá, ver el padrón completo con los badges de consentimiento, y recién
  // enterarse de que no puede nada al enviar el formulario. Mismo criterio
  // que el resto de la app: gatear en la UI lo que el backend ya gatea.
  const puedeCrearCampana = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";
  if (!puedeCrearCampana) {
    return (
      <div className="max-w-3xl mx-auto">
        <TextoError>Esta sección es solo para psicólogos y administradores de tu institución.</TextoError>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="font-display text-2xl text-teal-900">Nueva campaña</h1>

      {/* Paso 1: crear la campaña */}
      {!campana && (
        <form onSubmit={crearCampana} className="bg-white rounded-card border border-border p-6 space-y-4">
          <TextoError>{errorPruebas}</TextoError>
          <CampoEditable etiqueta="Prueba">
            <Select
              required
              value={form.prueba_id}
              onChange={(e) => setForm({ ...form, prueba_id: e.target.value })}
            >
              <option value="">Elige una prueba...</option>
              {pruebas.map((p) => (
                <option key={p.id} value={p.id} title={p.nombre_publico}>
                  {p.nombre_corto || p.nombre_tecnico}
                </option>
              ))}
            </Select>
          </CampoEditable>
          <CampoEditable etiqueta="Nombre del grupo">
            <Input
              required
              value={form.nombre_grupo}
              onChange={(e) => setForm({ ...form, nombre_grupo: e.target.value })}
              placeholder='Ej. "3° A - Evaluación anual 2026"'
            />
          </CampoEditable>
          <CampoEditable etiqueta="Fecha de cierre (opcional)">
            <Input
              type="datetime-local"
              value={form.fecha_fin}
              onChange={(e) => setForm({ ...form, fecha_fin: e.target.value })}
            />
          </CampoEditable>

          <TextoError>{errorCrear}</TextoError>

          <Boton type="submit" disabled={creando}>
            {creando ? "Creando..." : "Crear campaña"}
          </Boton>
        </form>
      )}

      {/* Paso 2: matricular alumnos del padrón */}
      {campana && !resultadoMatricula && (
        <div className="bg-white rounded-card border border-border p-6 space-y-4">
          <p className="text-sm text-ink/70">
            Campaña <strong>{campana.nombre_grupo}</strong> creada. Elige a quién matricular:
          </p>
          <TextoError>{errorPersonas}</TextoError>
          {cargandoConsentimientos && (
            <p className="text-xs text-ink/50 italic">Verificando consentimiento vigente de cada alumno...</p>
          )}
          {personas.length === 0 ? (
            <p className="text-sm text-ink/60 italic">No hay estudiantes en el padrón de tu institución todavía.</p>
          ) : (
            <div className="max-h-80 overflow-y-auto border border-border rounded-card divide-y divide-border">
              {personas.map((p) => {
                const sinConsentimiento = estadosConsentimiento.get(p.id) === false;
                return (
                  <label key={p.id} className="flex items-center gap-3 p-2 text-sm hover:bg-mist/40 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={seleccionadas.has(p.id)}
                      onChange={() => alternarSeleccion(p.id)}
                    />
                    {p.nombres} {p.apellidos}
                    {p.codigo_institucional && (
                      <span className="text-ink/40 text-xs font-mono">({p.codigo_institucional})</span>
                    )}
                    {sinConsentimiento && (
                      <span className="ml-auto shrink-0 text-xs rounded-full px-2 py-0.5 font-medium bg-amber/15 text-amber">
                        Sin consentimiento del apoderado
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          )}

          <TextoError>{errorMatricular}</TextoError>

          {Array.from(seleccionadas).some((id) => estadosConsentimiento.get(id) === false) && (
            <p className="text-xs text-amber">
              Hay alumnos seleccionados sin consentimiento del apoderado vigente — puedes intentar matricularlos
              igual, pero el colegio quedará fuera de la lista de links generados hasta registrarlo en su ficha.
            </p>
          )}

          <div className="flex items-center gap-3">
            <Boton onClick={matricular} disabled={matriculando || seleccionadas.size === 0}>
              {matriculando ? "Matriculando..." : `Matricular ${seleccionadas.size} alumno(s)`}
            </Boton>
            <Link href={`/campanas/${campana.id}/dashboard`} className="text-sm text-teal-600 hover:underline font-medium">
              Omitir por ahora, ir al dashboard →
            </Link>
          </div>
        </div>
      )}

      {/* Paso 3: resultado + links mágicos */}
      {campana && resultadoMatricula && (
        <div className="bg-white rounded-card border border-border p-6 space-y-4">
          <p className="text-sm text-ink/70">
            {resultadoMatricula.generados.length} link(s) generado(s)
            {resultadoMatricula.rechazados.length > 0 && `, ${resultadoMatricula.rechazados.length} rechazado(s)`}.
          </p>

          {resultadoMatricula.rechazados.length > 0 && (
            <ul className="text-sm text-amber-700 space-y-1">
              {resultadoMatricula.rechazados.map((r) => (
                <li key={r.persona_id}>
                  {r.nombre}: {r.motivo}
                </li>
              ))}
            </ul>
          )}

          {resultadoMatricula.generados.length > 0 && (
            <div className="space-y-1 max-h-80 overflow-y-auto">
              {resultadoMatricula.generados.map((ins) => {
                const url = typeof window !== "undefined" ? `${window.location.origin}/examen/${ins.token}` : "";
                return (
                  <div key={ins.id} className="flex items-center justify-between gap-2 text-sm border-b border-border py-1">
                    <span>{ins.nombre_completo}</span>
                    <button
                      onClick={() => navigator.clipboard.writeText(url)}
                      className="text-teal-600 hover:underline font-mono text-xs"
                    >
                      Copiar link
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <Boton onClick={() => router.push(`/campanas/${campana.id}/dashboard`)}>Ir al dashboard de la campaña</Boton>
        </div>
      )}
    </div>
  );
}
