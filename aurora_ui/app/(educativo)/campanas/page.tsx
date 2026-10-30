"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Flag, Plus } from "lucide-react";
import { EncabezadoPagina, claseBotonBanner } from "@/components/ui/Encabezado";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { EsqueletoTarjetas } from "@/components/ui/Esqueleto";
import type { RespuestaPaginada } from "@/types/api";
import { estadoVisibleCampana, etiquetaEstadoCampana, claseBadgeEstadoCampana } from "@/lib/campanas";

// Refleja schemas.EvaluacionResponse tal cual está en el backend —
// no tiene "nombre_grupo" separado de nombre de prueba, ni conteo de
// matriculados ni fecha_inicio. Si quieres mostrar el nombre de la
// prueba o el total matriculado, hay que pedirlo aparte o ampliar el
// schema en el backend (no lo agrego yo aquí para no inventar un
// endpoint que no existe).
//
// 🆕 `activo` ya NO se usa para el badge (hallazgo real: ni cerrar_campana
// ni cancelar_campana lo tocan nunca — ver crud.py, `_cerrar_o_cancelar_
// campana` solo mueve `estado`. Confirmado contra la BD real: 2 campañas
// canceladas seguían con activo=True). Se mantiene en el tipo porque el
// backend lo sigue devolviendo, pero la fuente de verdad es `estado` +
// `fecha_fin` (ver lib/campanas.ts).
type Campana = {
  id: number;
  prueba_id: number;
  nombre_grupo: string;
  activo: boolean;
  estado: string;
  fecha_fin: string | null;
  fecha_creacion: string;
};

const TAMANO_PAGINA = 50;

export default function CampanasPage() {
  const { sesion } = useAuth();
  const [campanas, setCampanas] = useState<Campana[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sesion) return;
    setCargando(true);
    // Nota: si sesion.rol es "superadmin", institucionId puede venir null
    // (el backend lo exige para ese rol) — en ese caso esta pantalla
    // no debería usarse igual, un superadmin no opera desde (educativo).
    //
    // 🆕 Esta llamada no tenía .catch(): un fallo de red/servidor dejaba
    // `campanas=[]` sin ningún aviso, idéntico a "todavía no hay campañas
    // creadas". Un 401 ya se resuelve aparte (ver lib/api-client.ts/
    // AuthContext.tsx: cierra sesión y redirige); este mensaje cubre el
    // resto de fallas.
    //
    // 🆕 Paginación real (docs/gaps-pendientes.md) — antes pedía toda
    // campaña creada sin tope; ahora pide de a 50 con skip/limit.
    apiClient
      .get<RespuestaPaginada<Campana>>(
        `/educativo/campanas/?institucion_id=${sesion.institucionId}&skip=${pagina * TAMANO_PAGINA}&limit=${TAMANO_PAGINA}`,
      )
      .then((res) => {
        setCampanas(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(err.message || "No se pudieron cargar las campañas."))
      .finally(() => setCargando(false));
  }, [sesion, pagina]);

  // STAFF_CLINICO del backend (superadmin/admin/psicologo) — "colegio"
  // puede ver el listado pero nunca crear campañas (ver campanas/nueva/page.tsx).
  const puedeCrearCampana = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";

  return (
    <div className="max-w-6xl mx-auto flex flex-col gap-4">
      <EncabezadoPagina variante="destacado"
        icono={Flag}
        acento="azul"
        titulo="Campañas"
        descripcion="Cada campaña aplica una prueba a un grupo de alumnos con su link personal."
        acciones={
          puedeCrearCampana && (
            <Link href="/campanas/nueva" className={claseBotonBanner("primario")}>
              <Plus size={15} strokeWidth={2.4} aria-hidden="true" />
              Nueva campaña
            </Link>
          )
        }
      />

      <TextoError className="mb-4">{error}</TextoError>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cargando && <EsqueletoTarjetas cantidad={4} />}
        {!cargando && campanas.map((campana) => (
          <Link
            key={campana.id}
            href={`/campanas/${campana.id}/dashboard`}
            className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-5 hover:border-teal-400 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <h2 className="font-display text-base text-ink dark:text-ink-dark">{campana.nombre_grupo}</h2>
              {(() => {
                const estado = estadoVisibleCampana(campana.estado, campana.fecha_fin);
                return (
                  <span className={`text-xs rounded-full px-2 py-0.5 ${claseBadgeEstadoCampana(estado)}`}>
                    {etiquetaEstadoCampana(estado)}
                  </span>
                );
              })()}
            </div>
            <p className="text-xs text-ink/60 dark:text-ink-dark/60 font-mono">
              Creada {campana.fecha_creacion.slice(0, 10)}
              {campana.fecha_fin ? ` — cierra ${campana.fecha_fin.slice(0, 10)}` : ""}
            </p>
          </Link>
        ))}
      </div>

      {!cargando && !error && campanas.length === 0 && (
        <p className="text-sm text-ink/40 dark:text-ink-dark/40 mt-4">Todavía no hay campañas creadas.</p>
      )}

      {!cargando && !error && total > 0 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-ink/50 dark:text-ink-dark/50">
            {pagina * TAMANO_PAGINA + 1}–{Math.min((pagina + 1) * TAMANO_PAGINA, total)} de {total} campañas
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPagina((p) => Math.max(0, p - 1))}
              disabled={pagina === 0}
              className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Anterior
            </button>
            <button
              onClick={() => setPagina((p) => p + 1)}
              disabled={(pagina + 1) * TAMANO_PAGINA >= total}
              className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-3 py-1.5 text-xs font-medium text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}