"use client";

import { useState } from "react";
import Link from "next/link";
import { Flag, Plus, UserRound } from "lucide-react";
import { EncabezadoPagina, ControlSegmentado, claseBotonBanner, CLASE_CONTENEDOR_SECCION } from "@/components/ui/Encabezado";
import { useAuth } from "@/contexts/AuthContext";
import { TextoError } from "@/components/ui/TextoError";
import { EsqueletoTarjetas } from "@/components/ui/Esqueleto";
import type { RespuestaPaginada } from "@/types/api";
import { estadoVisibleCampana, etiquetaEstadoCampana, claseBadgeEstadoCampana } from "@/lib/campanas";
import { useConsultaApi } from "@/lib/consultas";

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
  tipo?: "grupal" | "individual";
};

// 🆕 (sesión 2026-11-01) Las aplicaciones individuales (una prueba a un
// estudiante, desde su perfil) son campañas de un solo inscrito: se listan
// aquí, separadas de las grupales.
type TipoLista = "grupal" | "individual";

const TAMANO_PAGINA = 50;

export default function CampanasPage() {
  const { sesion } = useAuth();
  const [pagina, setPagina] = useState(0);
  const [tipo, setTipo] = useState<TipoLista>("grupal");

  // Nota: si sesion.rol es "superadmin", institucionId puede venir null (el
  // backend lo exige para ese rol) — esta pantalla no se usa para ese rol.
  //
  // 🆕 Paginación real (docs/gaps-pendientes.md): de a 50 con skip/limit.
  // 🆕 (2026-11-17, plan de UX fase 1) Con memoria entre pantallas
  // (lib/consultas.ts): al volver desde el dashboard de una campaña, la
  // lista se ve al instante. La clave incluye tipo y página, así que una
  // respuesta lenta de la otra pestaña nunca pisa la que se está viendo
  // (el bug de la sesión 2026-11-01). Un error se muestra (antes de la
  // auditoría 2026-10-16 un fallo quedaba igual a "no hay campañas").
  const consulta = useConsultaApi<RespuestaPaginada<Campana>>(
    sesion
      ? `/educativo/campanas/?institucion_id=${sesion.institucionId}&tipo=${tipo}&skip=${pagina * TAMANO_PAGINA}&limit=${TAMANO_PAGINA}`
      : null,
    { mensajeError: "No se pudieron cargar las campañas." },
  );
  const campanas = consulta.datos?.items ?? [];
  const total = consulta.datos?.total ?? 0;
  const cargando = consulta.cargando;
  const error = consulta.error;

  // STAFF_CLINICO del backend (superadmin/admin/psicologo) — "colegio"
  // puede ver el listado pero nunca crear campañas (ver campanas/nueva/page.tsx).
  const puedeCrearCampana = sesion?.rol === "psicologo" || sesion?.rol === "admin" || sesion?.rol === "superadmin";

  return (
    <div className={CLASE_CONTENEDOR_SECCION}>
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

      <div className="flex flex-wrap items-center justify-between gap-2">
        <ControlSegmentado<TipoLista>
          etiqueta="Tipo de campaña"
          valor={tipo}
          onCambiar={(v) => {
            setTipo(v);
            setPagina(0);
          }}
          opciones={[
            { valor: "grupal", etiqueta: "Grupales" },
            { valor: "individual", etiqueta: "Individuales" },
          ]}
        />
        {tipo === "individual" && (
          <p className="m-0 text-xs text-ink/55 dark:text-ink-dark/55">
            Se crean desde el perfil del estudiante con «Aplicar prueba». No cuentan en las estadísticas por salón.
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cargando && <EsqueletoTarjetas cantidad={4} />}
        {!cargando && campanas.map((campana) => (
          <Link
            key={campana.id}
            href={`/campanas/${campana.id}/dashboard`}
            className="rounded-xl border border-acento-azul/15 dark:border-acento-azul-dark/20 bg-acento-azul/[0.035] dark:bg-acento-azul-dark/[0.05] p-5 hover:border-acento-azul/50 hover:shadow-sm hover:-translate-y-px dark:hover:border-acento-azul-dark/50 transition-all"
          >
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="flex min-w-0 items-center gap-2.5 font-display text-base text-ink dark:text-ink-dark">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-acento-azul text-white dark:bg-acento-azul-dark dark:text-mist-dark">
                  {campana.tipo === "individual" ? <UserRound size={15} aria-hidden="true" /> : <Flag size={15} aria-hidden="true" />}
                </span>
                <span className="truncate">{campana.nombre_grupo}</span>
              </h2>
              {(() => {
                const estado = estadoVisibleCampana(campana.estado, campana.fecha_fin);
                return (
                  <span className={`text-xs rounded-full px-2 py-0.5 ${claseBadgeEstadoCampana(estado)}`}>
                    {etiquetaEstadoCampana(estado)}
                  </span>
                );
              })()}
            </div>
            <p className="pl-[2.6rem] text-xs text-ink/60 dark:text-ink-dark/60 font-mono">
              Creada {campana.fecha_creacion.slice(0, 10)}
              {campana.fecha_fin ? ` — cierra ${campana.fecha_fin.slice(0, 10)}` : ""}
            </p>
          </Link>
        ))}
      </div>

      {!cargando && !error && campanas.length === 0 && (
        <p className="text-sm text-ink/40 dark:text-ink-dark/40 mt-4">
          {tipo === "individual"
            ? "Todavía no hay aplicaciones individuales. Se crean desde el perfil del estudiante."
            : "Todavía no hay campañas creadas."}
        </p>
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