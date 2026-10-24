"use client";

// 🆕 Pantalla de aterrizaje tras el login (reemplaza el salto directo a
// /estudiantes, un listado crudo sin ningún "qué tengo que atender hoy").
// Reusa 3 endpoints que ya existían — ninguno nuevo en el backend:
//   - GET /educativo/casos-pendientes (worklist clínico: alumnos con
//     es_alerta=True sin ninguna sesión de seguimiento posterior —
//     requerir_staff_clinico, "colegio" no lo ve, el backend ya lo bloquea).
//   - GET /admin/personas/citas/mi-agenda (mismo que ya usa el badge del sidebar).
//   - GET /educativo/campanas/ (paginado, filtramos estado="activa" en cliente).
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import type { Cita, Evaluacion, RespuestaPaginada } from "@/types/api";

type CasoPendiente = {
  persona_id: number;
  nombre_completo: string;
  nivel_alerta: string;
  [clave: string]: unknown;
};

function esHoy(fechaIso: string): boolean {
  const fecha = new Date(fechaIso);
  const hoy = new Date();
  return (
    fecha.getFullYear() === hoy.getFullYear() &&
    fecha.getMonth() === hoy.getMonth() &&
    fecha.getDate() === hoy.getDate()
  );
}

function cierraEnMenosDe(fechaIso: string | null, dias: number): boolean {
  if (!fechaIso) return false;
  const limite = new Date();
  limite.setDate(limite.getDate() + dias);
  return new Date(fechaIso) <= limite;
}

function TarjetaResumen({
  titulo,
  valor,
  enlace,
  vacio,
  children,
}: {
  titulo: string;
  valor: number | null;
  enlace: string;
  vacio: string;
  children?: React.ReactNode;
}) {
  return (
    <Link
      href={enlace}
      className="bg-white rounded-card border border-border p-5 shadow-sm space-y-3 hover:border-teal-400 transition-colors block"
    >
      <div className="flex items-baseline justify-between">
        <p className="text-sm font-medium text-ink/60">{titulo}</p>
        <span className="font-display text-3xl text-teal-900">{valor ?? "—"}</span>
      </div>
      {valor === 0 ? <p className="text-xs text-ink/40 italic">{vacio}</p> : children}
    </Link>
  );
}

export default function InicioPage() {
  const { sesion } = useAuth();
  const vePerfilClinico = sesion?.rol === "psicologo" || sesion?.rol === "admin";

  const [casos, setCasos] = useState<CasoPendiente[] | null>(null);
  const [errorCasos, setErrorCasos] = useState<string | null>(null);

  const [citas, setCitas] = useState<Cita[] | null>(null);
  const [errorCitas, setErrorCitas] = useState<string | null>(null);

  const [campanas, setCampanas] = useState<Evaluacion[] | null>(null);
  const [errorCampanas, setErrorCampanas] = useState<string | null>(null);

  useEffect(() => {
    if (vePerfilClinico) {
      apiClient
        .get<CasoPendiente[]>("/educativo/casos-pendientes")
        .then(setCasos)
        .catch((err) => setErrorCasos(err.message || "No se pudieron cargar los casos pendientes."));
    }

    apiClient
      .get<Cita[]>("/admin/personas/citas/mi-agenda")
      .then(setCitas)
      .catch((err) => setErrorCitas(err.message || "No se pudo cargar la agenda."));

    if (sesion?.institucionId) {
      apiClient
        .get<RespuestaPaginada<Evaluacion>>(`/educativo/campanas/?institucion_id=${sesion.institucionId}&limit=200`)
        .then((r) => setCampanas(r.items))
        .catch((err) => setErrorCampanas(err.message || "No se pudieron cargar las campañas."));
    }
  }, [vePerfilClinico, sesion?.institucionId]);

  const citasHoy = (citas ?? []).filter((c) => c.estado === "Programada" && esHoy(c.fecha_hora));
  const campanasActivas = (campanas ?? []).filter((c) => c.estado === "activa");
  const campanasPorCerrar = campanasActivas.filter((c) => cierraEnMenosDe(c.fecha_fin, 7));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl text-teal-900 font-semibold">Inicio</h1>
        <p className="text-sm text-ink/60">Lo que necesitás atender hoy.</p>
      </div>

      <div className={`grid gap-4 ${vePerfilClinico ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {vePerfilClinico && (
          <TarjetaResumen
            titulo="Casos en riesgo sin seguimiento"
            valor={casos?.length ?? null}
            enlace="/casos-riesgo"
            vacio="Sin casos pendientes."
          >
            {casos && casos.length > 0 && (
              <ul className="text-xs text-ink/70 space-y-1">
                {casos.slice(0, 3).map((c) => (
                  <li key={c.persona_id} className="truncate">
                    {c.nombre_completo} — <span className="font-medium">{c.nivel_alerta}</span>
                  </li>
                ))}
                {casos.length > 3 && <li className="text-ink/40">+{casos.length - 3} más</li>}
              </ul>
            )}
            <TextoError className="text-xs">{errorCasos}</TextoError>
          </TarjetaResumen>
        )}

        <TarjetaResumen
          titulo="Citas de hoy"
          valor={citas ? citasHoy.length : null}
          enlace="/agenda"
          vacio="Sin citas agendadas para hoy."
        >
          {citasHoy.length > 0 && (
            <ul className="text-xs text-ink/70 space-y-1">
              {citasHoy.slice(0, 3).map((c) => (
                <li key={c.id} className="truncate">
                  {new Date(c.fecha_hora).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })} —{" "}
                  {c.titulo || c.motivo}
                </li>
              ))}
              {citasHoy.length > 3 && <li className="text-ink/40">+{citasHoy.length - 3} más</li>}
            </ul>
          )}
          <TextoError className="text-xs">{errorCitas}</TextoError>
        </TarjetaResumen>

        <TarjetaResumen
          titulo="Campañas activas"
          valor={campanas ? campanasActivas.length : null}
          enlace="/campanas"
          vacio="Sin campañas activas."
        >
          {campanasPorCerrar.length > 0 && (
            <p className="text-xs text-ink/70">
              <span className="font-medium text-teal-900">{campanasPorCerrar.length}</span> cierra
              {campanasPorCerrar.length === 1 ? "" : "n"} en los próximos 7 días.
            </p>
          )}
          <TextoError className="text-xs">{errorCampanas}</TextoError>
        </TarjetaResumen>
      </div>
    </div>
  );
}
