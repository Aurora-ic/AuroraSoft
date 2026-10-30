"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Building2,
  CircleCheck,
  CircleAlert,
  CalendarClock,
  ChevronRight,
  Plus,
  type LucideIcon,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { claseBoton } from "@/components/ui/Boton";
import { Badge } from "@/components/ui/Badge";
import { TextoError } from "@/components/ui/TextoError";
import { DIAS_AVISO, diasParaVencer, estadoLicencia, formatearFecha } from "@/components/superadmin/estadoLicencia";
import { Iniciales } from "@/components/superadmin/Iniciales";
import type { Institucion } from "@/types/api";

// Landing del panel interno de AuroraSoft — conteos rápidos leídos del
// mismo GET /instituciones/ que /master/clientes ya usa para la lista
// completa, sin un endpoint de métricas aparte.
export default function MasterPage() {
  const { sesion } = useAuth();
  const [instituciones, setInstituciones] = useState<Institucion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Institucion[]>("/instituciones/")
      .then(setInstituciones)
      .catch((err) => setError(err.message || "No se pudo cargar el resumen de instituciones."));
  }, []);

  const lista = instituciones ?? [];
  const total = instituciones ? lista.length : null;
  const activas = instituciones ? lista.filter((i) => i.plan_activo).length : null;
  const vencidas = instituciones ? lista.filter((i) => estadoLicencia(i) === "vencida").length : null;
  const porVencer = instituciones ? lista.filter((i) => estadoLicencia(i) === "por_vencer").length : null;

  // Lo que el superadmin debería mirar primero: licencia vencida, por vencer
  // o plan inactivo. Ordenado por urgencia (vencidas primero).
  const atencion = lista
    .filter((i) => !i.plan_activo || ["vencida", "por_vencer"].includes(estadoLicencia(i)))
    .sort((a, b) => (diasParaVencer(a) ?? Infinity) - (diasParaVencer(b) ?? Infinity));

  const recientes = [...lista]
    .sort((a, b) => new Date(b.fecha_registro).getTime() - new Date(a.fecha_registro).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-ink/50 dark:text-ink-dark/50">Hola{sesion?.email ? `, ${sesion.email}` : ""}</p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-teal-900 dark:text-ink-dark mt-1">
            Resumen general
          </h1>
        </div>
        <Link href="/master/clientes?nueva=1" className={claseBoton("primario", "inline-flex items-center justify-center gap-1.5")}>
          <Plus size={16} strokeWidth={2.2} aria-hidden="true" />
          Nueva institución
        </Link>
      </div>

      <TextoError>{error}</TextoError>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <TarjetaMetrica icono={Building2} etiqueta="Instituciones" valor={total} detalle="Clientes registrados" />
        <TarjetaMetrica
          icono={CircleCheck}
          etiqueta="Con plan activo"
          valor={activas}
          detalle={total ? `${Math.round(((activas ?? 0) / total) * 100)}% del total` : "—"}
        />
        <TarjetaMetrica
          icono={CalendarClock}
          etiqueta="Por vencer"
          valor={porVencer}
          detalle={`En los próximos ${DIAS_AVISO} días`}
        />
        <TarjetaMetrica
          icono={CircleAlert}
          etiqueta="Licencia vencida"
          valor={vencidas}
          detalle="Requieren renovación"
          alerta={!!vencidas}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <Panel titulo="Atención requerida" className="lg:col-span-3">
          {instituciones === null ? (
            <FilasCargando />
          ) : atencion.length === 0 ? (
            <Vacio texto="Todo en orden: ninguna licencia vencida, por vencer ni plan inactivo." />
          ) : (
            <ul className="divide-y divide-border dark:divide-border-dark">
              {atencion.map((inst) => (
                <FilaInstitucion key={inst.id} inst={inst} />
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          titulo="Registradas recientemente"
          className="lg:col-span-2"
          accion={
            <Link href="/master/clientes" className="text-xs font-medium text-teal-700 dark:text-teal-accent-dark hover:underline">
              Ver todas
            </Link>
          }
        >
          {instituciones === null ? (
            <FilasCargando />
          ) : recientes.length === 0 ? (
            <Vacio texto="Todavía no hay instituciones registradas." />
          ) : (
            <ul className="divide-y divide-border dark:divide-border-dark">
              {recientes.map((inst) => (
                <li key={inst.id}>
                  <Link
                    href={`/master/clientes/${inst.id}`}
                    className="flex items-center gap-3 px-5 py-3 hover:bg-mist/60 dark:hover:bg-surface-raised-dark transition-colors"
                  >
                    <Iniciales nombre={inst.nombre} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink dark:text-ink-dark truncate">{inst.nombre}</p>
                      <p className="text-xs text-ink/50 dark:text-ink-dark/50">Desde {formatearFecha(inst.fecha_registro)}</p>
                    </div>
                    <ChevronRight size={16} className="text-ink/30 dark:text-ink-dark/30 shrink-0" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function TarjetaMetrica({
  icono: Icono,
  etiqueta,
  valor,
  detalle,
  alerta = false,
}: {
  icono: LucideIcon;
  etiqueta: string;
  valor: number | null;
  detalle: string;
  alerta?: boolean;
}) {
  return (
    <div className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 sm:p-5 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-ink/60 dark:text-ink-dark/60">{etiqueta}</p>
        <span
          className={`flex h-8 w-8 sm:h-9 sm:w-9 shrink-0 items-center justify-center rounded-lg ${
            alerta
              ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300"
              : "bg-teal-600/10 text-teal-700 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark"
          }`}
        >
          <Icono size={18} strokeWidth={2} aria-hidden="true" />
        </span>
      </div>
      {valor === null ? (
        <div className="mt-3 h-8 w-12 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
      ) : (
        <p
          className={`mt-2 font-display text-3xl font-semibold ${
            alerta ? "text-red-700 dark:text-red-300" : "text-teal-900 dark:text-ink-dark"
          }`}
        >
          {valor}
        </p>
      )}
      <p className="mt-1 text-xs text-ink/45 dark:text-ink-dark/45">{detalle}</p>
    </div>
  );
}

function Panel({
  titulo,
  accion,
  className = "",
  children,
}: {
  titulo: string;
  accion?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className={`rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark shadow-sm overflow-hidden ${className}`}
    >
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-border dark:border-border-dark">
        <h2 className="font-display text-base font-semibold text-teal-900 dark:text-ink-dark">{titulo}</h2>
        {accion}
      </div>
      {children}
    </section>
  );
}

function FilaInstitucion({ inst }: { inst: Institucion }) {
  const estado = estadoLicencia(inst);
  const dias = diasParaVencer(inst);
  return (
    <li>
      <Link
        href={`/master/clientes/${inst.id}`}
        className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:gap-3 hover:bg-mist/60 dark:hover:bg-surface-raised-dark transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Iniciales nombre={inst.nombre} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink dark:text-ink-dark truncate">{inst.nombre}</p>
            <p className="text-xs text-ink/50 dark:text-ink-dark/50">
              {estado === "vencida" && `Licencia vencida el ${formatearFecha(inst.fecha_vencimiento_licencia)}`}
              {estado === "por_vencer" && `Vence en ${dias} ${dias === 1 ? "día" : "días"}`}
              {(estado === "vigente" || estado === "sin_caducidad") && "Licencia en regla"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 pl-12 sm:pl-0">
          {!inst.plan_activo && <Badge tono="neutro">Plan inactivo</Badge>}
          {estado === "vencida" && <Badge tono="error">Vencida</Badge>}
          {estado === "por_vencer" && <Badge tono="teal-suave">Por vencer</Badge>}
        </div>
      </Link>
    </li>
  );
}

function FilasCargando() {
  return (
    <div className="p-5 space-y-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-9 w-9 animate-pulse rounded-lg bg-border/70 dark:bg-border-dark" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3.5 w-1/2 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
            <div className="h-3 w-1/3 animate-pulse rounded bg-border/70 dark:bg-border-dark" />
          </div>
        </div>
      ))}
    </div>
  );
}

function Vacio({ texto }: { texto: string }) {
  return <p className="px-5 py-8 text-center text-sm text-ink/50 dark:text-ink-dark/50">{texto}</p>;
}
