"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";
import type {
  NivelEducativo,
  NivelEducativoCreate,
  Grado,
  GradoCreate,
  Seccion,
  SeccionCreate,
} from "@/types/api";

function FilaSeleccionable({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-card px-3 py-2 text-sm transition-colors ${
        activo ? "bg-teal-900 text-white" : "text-ink hover:bg-mist"
      }`}
    >
      {children}
    </button>
  );
}

export default function EstructuraAcademicaPage() {
  const { sesion } = useAuth();
  const esAdmin = sesion?.rol === "admin";

  // --- Niveles ---
  const [niveles, setNiveles] = useState<NivelEducativo[]>([]);
  const [cargandoNiveles, setCargandoNiveles] = useState(true);
  const [errorNiveles, setErrorNiveles] = useState<string | null>(null);
  const [nivelSeleccionado, setNivelSeleccionado] = useState<NivelEducativo | null>(null);
  const [formNivel, setFormNivel] = useState({ nombre: "", orden: "" });
  const [guardandoNivel, setGuardandoNivel] = useState(false);
  const [errorFormNivel, setErrorFormNivel] = useState<string | null>(null);

  // --- Grados (del nivel seleccionado) ---
  const [grados, setGrados] = useState<Grado[]>([]);
  const [cargandoGrados, setCargandoGrados] = useState(false);
  const [errorGrados, setErrorGrados] = useState<string | null>(null);
  const [gradoSeleccionado, setGradoSeleccionado] = useState<Grado | null>(null);
  const [formGrado, setFormGrado] = useState({ nombre: "", orden: "" });
  const [guardandoGrado, setGuardandoGrado] = useState(false);
  const [errorFormGrado, setErrorFormGrado] = useState<string | null>(null);

  // --- Secciones (del grado seleccionado) ---
  const [secciones, setSecciones] = useState<Seccion[]>([]);
  const [cargandoSecciones, setCargandoSecciones] = useState(false);
  const [errorSecciones, setErrorSecciones] = useState<string | null>(null);
  const [formSeccion, setFormSeccion] = useState({ nombre: "", turno: "", anio_escolar: "" });
  const [guardandoSeccion, setGuardandoSeccion] = useState(false);
  const [errorFormSeccion, setErrorFormSeccion] = useState<string | null>(null);

  useEffect(() => {
    if (!sesion?.institucionId) return;
    setCargandoNiveles(true);
    setErrorNiveles(null);
    apiClient
      .get<NivelEducativo[]>(`/admin/personas/academico/niveles/${sesion.institucionId}`)
      .then(setNiveles)
      .catch((err: any) => setErrorNiveles(err.message || "No se pudieron cargar los niveles educativos."))
      .finally(() => setCargandoNiveles(false));
  }, [sesion]);

  async function seleccionarNivel(nivel: NivelEducativo) {
    setNivelSeleccionado(nivel);
    setGradoSeleccionado(null);
    setGrados([]);
    setSecciones([]);
    setErrorSecciones(null);
    setCargandoGrados(true);
    setErrorGrados(null);
    try {
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivel.id}`);
      setGrados(datos);
    } catch (err: any) {
      setErrorGrados(err.message || "No se pudieron cargar los grados.");
    } finally {
      setCargandoGrados(false);
    }
  }

  async function seleccionarGrado(grado: Grado) {
    setGradoSeleccionado(grado);
    setSecciones([]);
    setCargandoSecciones(true);
    setErrorSecciones(null);
    try {
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${grado.id}`);
      setSecciones(datos);
    } catch (err: any) {
      setErrorSecciones(err.message || "No se pudieron cargar las secciones.");
    } finally {
      setCargandoSecciones(false);
    }
  }

  async function crearNivel(e: React.FormEvent) {
    e.preventDefault();
    if (!sesion?.institucionId) return;
    setGuardandoNivel(true);
    setErrorFormNivel(null);
    try {
      const payload: NivelEducativoCreate = {
        institucion_id: sesion.institucionId,
        nombre: formNivel.nombre,
        orden: formNivel.orden ? Number(formNivel.orden) : 0,
      };
      await apiClient.post<NivelEducativo>("/admin/personas/academico/niveles", payload);
      const datos = await apiClient.get<NivelEducativo[]>(
        `/admin/personas/academico/niveles/${sesion.institucionId}`,
      );
      setNiveles(datos);
      setFormNivel({ nombre: "", orden: "" });
    } catch (err: any) {
      setErrorFormNivel(err.message || "No se pudo crear el nivel educativo.");
    } finally {
      setGuardandoNivel(false);
    }
  }

  async function crearGrado(e: React.FormEvent) {
    e.preventDefault();
    if (!nivelSeleccionado) return;
    setGuardandoGrado(true);
    setErrorFormGrado(null);
    try {
      const payload: GradoCreate = {
        nivel_educativo_id: nivelSeleccionado.id,
        nombre: formGrado.nombre,
        orden: formGrado.orden ? Number(formGrado.orden) : 0,
      };
      await apiClient.post<Grado>("/admin/personas/academico/grados", payload);
      const datos = await apiClient.get<Grado[]>(`/admin/personas/academico/grados/${nivelSeleccionado.id}`);
      setGrados(datos);
      setFormGrado({ nombre: "", orden: "" });
    } catch (err: any) {
      setErrorFormGrado(err.message || "No se pudo crear el grado.");
    } finally {
      setGuardandoGrado(false);
    }
  }

  async function crearSeccion(e: React.FormEvent) {
    e.preventDefault();
    if (!gradoSeleccionado) return;
    const anio = Number(formSeccion.anio_escolar);
    if (!anio) {
      setErrorFormSeccion("Indica el año escolar.");
      return;
    }
    setGuardandoSeccion(true);
    setErrorFormSeccion(null);
    try {
      const payload: SeccionCreate = {
        grado_id: gradoSeleccionado.id,
        nombre: formSeccion.nombre,
        turno: formSeccion.turno || null,
        anio_escolar: anio,
      };
      await apiClient.post<Seccion>("/admin/personas/academico/secciones", payload);
      const datos = await apiClient.get<Seccion[]>(`/admin/personas/academico/secciones/${gradoSeleccionado.id}`);
      setSecciones(datos);
      setFormSeccion({ nombre: "", turno: "", anio_escolar: "" });
    } catch (err: any) {
      setErrorFormSeccion(err.message || "No se pudo crear la sección.");
    } finally {
      setGuardandoSeccion(false);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-teal-900 tracking-tight">Estructura académica</h1>
        <p className="mt-1 text-sm text-ink/60 max-w-2xl">
          Niveles, grados y secciones de tu institución — la base para matricular estudiantes e importarlos por
          Excel. Una sección existe para un año escolar concreto: para reabrir un grado en un año nuevo, crea
          secciones nuevas en vez de reutilizar las del año pasado.
          {!esAdmin && " Solo un administrador puede crear elementos nuevos; tú puedes consultarlos."}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
        {/* Niveles */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">Niveles educativos</h2>

          <TextoError>{errorNiveles}</TextoError>

          {cargandoNiveles ? (
            <p className="text-sm text-ink/40">Cargando…</p>
          ) : niveles.length === 0 ? (
            <p className="text-sm text-ink/40 italic">Todavía no hay niveles creados.</p>
          ) : (
            <div className="space-y-1">
              {niveles.map((nivel) => (
                <FilaSeleccionable
                  key={nivel.id}
                  activo={nivelSeleccionado?.id === nivel.id}
                  onClick={() => seleccionarNivel(nivel)}
                >
                  {nivel.nombre}
                </FilaSeleccionable>
              ))}
            </div>
          )}

          {esAdmin && (
            <form onSubmit={crearNivel} className="border-t border-border pt-4 space-y-3">
              <CampoEditable etiqueta="Nombre">
                <Input
                  required
                  placeholder="Secundaria"
                  value={formNivel.nombre}
                  onChange={(e) => setFormNivel({ ...formNivel, nombre: e.target.value })}
                />
              </CampoEditable>
              <CampoEditable etiqueta="Orden (opcional)">
                <Input
                  type="number"
                  placeholder="0"
                  value={formNivel.orden}
                  onChange={(e) => setFormNivel({ ...formNivel, orden: e.target.value })}
                />
              </CampoEditable>
              <TextoError>{errorFormNivel}</TextoError>
              <Boton type="submit" disabled={guardandoNivel} className="w-full">
                {guardandoNivel ? "Guardando…" : "+ Nuevo nivel"}
              </Boton>
            </form>
          )}
        </section>

        {/* Grados */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">
            Grados{nivelSeleccionado ? ` — ${nivelSeleccionado.nombre}` : ""}
          </h2>

          {!nivelSeleccionado ? (
            <p className="text-sm text-ink/40 italic">Selecciona un nivel educativo.</p>
          ) : (
            <>
              <TextoError>{errorGrados}</TextoError>

              {cargandoGrados ? (
                <p className="text-sm text-ink/40">Cargando…</p>
              ) : grados.length === 0 ? (
                <p className="text-sm text-ink/40 italic">Todavía no hay grados en este nivel.</p>
              ) : (
                <div className="space-y-1">
                  {grados.map((grado) => (
                    <FilaSeleccionable
                      key={grado.id}
                      activo={gradoSeleccionado?.id === grado.id}
                      onClick={() => seleccionarGrado(grado)}
                    >
                      {grado.nombre}
                    </FilaSeleccionable>
                  ))}
                </div>
              )}

              {esAdmin && (
                <form onSubmit={crearGrado} className="border-t border-border pt-4 space-y-3">
                  <CampoEditable etiqueta="Nombre">
                    <Input
                      required
                      placeholder="3°"
                      value={formGrado.nombre}
                      onChange={(e) => setFormGrado({ ...formGrado, nombre: e.target.value })}
                    />
                  </CampoEditable>
                  <CampoEditable etiqueta="Orden (opcional)">
                    <Input
                      type="number"
                      placeholder="0"
                      value={formGrado.orden}
                      onChange={(e) => setFormGrado({ ...formGrado, orden: e.target.value })}
                    />
                  </CampoEditable>
                  <TextoError>{errorFormGrado}</TextoError>
                  <Boton type="submit" disabled={guardandoGrado} className="w-full">
                    {guardandoGrado ? "Guardando…" : "+ Nuevo grado"}
                  </Boton>
                </form>
              )}
            </>
          )}
        </section>

        {/* Secciones */}
        <section className="bg-white rounded-card border border-border p-6 shadow-sm space-y-4">
          <h2 className="font-display text-lg font-semibold text-teal-900">
            Secciones{gradoSeleccionado ? ` — ${gradoSeleccionado.nombre}` : ""}
          </h2>

          {!gradoSeleccionado ? (
            <p className="text-sm text-ink/40 italic">Selecciona un grado.</p>
          ) : (
            <>
              <TextoError>{errorSecciones}</TextoError>

              {cargandoSecciones ? (
                <p className="text-sm text-ink/40">Cargando…</p>
              ) : secciones.length === 0 ? (
                <p className="text-sm text-ink/40 italic">Todavía no hay secciones en este grado.</p>
              ) : (
                <div className="space-y-1.5">
                  {secciones.map((seccion) => (
                    <div key={seccion.id} className="rounded-card border border-border px-3 py-2">
                      <div className="text-sm text-ink font-medium">{seccion.nombre}</div>
                      <div className="text-xs text-ink/50 mt-0.5">
                        Año {seccion.anio_escolar}
                        {seccion.turno ? ` · Turno ${seccion.turno}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {esAdmin && (
                <form onSubmit={crearSeccion} className="border-t border-border pt-4 space-y-3">
                  <CampoEditable etiqueta="Nombre">
                    <Input
                      required
                      placeholder="A"
                      value={formSeccion.nombre}
                      onChange={(e) => setFormSeccion({ ...formSeccion, nombre: e.target.value })}
                    />
                  </CampoEditable>
                  <div className="grid grid-cols-2 gap-3">
                    <CampoEditable etiqueta="Año escolar">
                      <Input
                        required
                        type="number"
                        placeholder="2026"
                        value={formSeccion.anio_escolar}
                        onChange={(e) => setFormSeccion({ ...formSeccion, anio_escolar: e.target.value })}
                      />
                    </CampoEditable>
                    <CampoEditable etiqueta="Turno (opcional)">
                      <Input
                        placeholder="Mañana"
                        value={formSeccion.turno}
                        onChange={(e) => setFormSeccion({ ...formSeccion, turno: e.target.value })}
                      />
                    </CampoEditable>
                  </div>
                  <TextoError>{errorFormSeccion}</TextoError>
                  <Boton type="submit" disabled={guardandoSeccion} className="w-full">
                    {guardandoSeccion ? "Guardando…" : "+ Nueva sección"}
                  </Boton>
                </form>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
