"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Bell, Siren, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { apiClient } from "@/lib/api-client";

// 🆕 (sesión 2026-11-02) Aviso dentro de la app al responsable cuando entra
// un caso URGENTE (decisión del usuario: por la misma app). Antes solo
// existía el correo de alerta de riesgo, que va a la cadena institucional y
// no necesariamente a quien tiene que atender el caso.
//
// - Campana en la barra superior con el número de casos urgentes sin
//   atender (en "Nuevo") que son tuyos o no tienen responsable
//   (GET /educativo/casos-riesgo/avisos, cada minuto).
// - Cuando aparece uno que todavía no te mostró, sale además un aviso
//   emergente. Los ya mostrados se recuerdan en este navegador.
// - El aviso se apaga solo cuando alguien atiende el caso (lo saca de
//   "Nuevo" en Casos en riesgo): no hace falta "marcarlo como leído".
// - Urgente en ROJO, el mismo color de triaje que la bandeja.

export const CLAVE_AVISOS_URGENTES = ["avisos-urgentes"];
const CLAVE_VISTOS = "aurora_avisos_urgentes_vistos";
const ROLES_CON_AVISOS = ["psicologo", "admin"];

type AvisoCaso = { id: number; persona_id: number; nombre_completo: string; creado_en: string; asignado_a_mi: boolean };
type Avisos = { total: number; casos: AvisoCaso[] };

function leerVistos(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_VISTOS) || "[]"));
  } catch {
    return new Set();
  }
}

export function AvisosUrgentes() {
  const { sesion } = useAuth();
  const habilitado = !!sesion && ROLES_CON_AVISOS.includes(sesion.rol);
  const { data } = useQuery({
    queryKey: CLAVE_AVISOS_URGENTES,
    queryFn: () => apiClient.get<Avisos>("/educativo/casos-riesgo/avisos"),
    enabled: habilitado,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
  const [abierto, setAbierto] = useState(false);
  const [vistos, setVistos] = useState<Set<number>>(leerVistos);
  const contenedor = useRef<HTMLDivElement>(null);

  const casos = data?.casos ?? [];
  const nuevos = casos.filter((c) => !vistos.has(c.id));

  function marcarVistos(ids: number[]) {
    setVistos((previos) => {
      const siguiente = new Set(previos);
      ids.forEach((id) => siguiente.add(id));
      // Solo se guardan los que siguen pendientes: la lista no crece sin fin.
      const vigentes = [...siguiente].filter((id) => casos.some((c) => c.id === id));
      try {
        localStorage.setItem(CLAVE_VISTOS, JSON.stringify(vigentes));
      } catch {
        // sin almacenamiento: el aviso puede repetirse, nada más
      }
      return siguiente;
    });
  }

  // El aviso emergente se retira solo a los 12 s (queda en la campana).
  const idsNuevos = nuevos.map((c) => c.id).join(",");
  useEffect(() => {
    if (!idsNuevos) return;
    const t = setTimeout(() => marcarVistos(idsNuevos.split(",").map(Number)), 12_000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsNuevos]);

  useEffect(() => {
    if (!abierto) return;
    function alTeclado(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    function alClicFuera(e: MouseEvent) {
      if (contenedor.current && !contenedor.current.contains(e.target as Node)) setAbierto(false);
    }
    document.addEventListener("keydown", alTeclado);
    document.addEventListener("mousedown", alClicFuera);
    return () => {
      document.removeEventListener("keydown", alTeclado);
      document.removeEventListener("mousedown", alClicFuera);
    };
  }, [abierto]);

  if (!habilitado) return null;
  const total = data?.total ?? 0;

  return (
    <>
      <div ref={contenedor} className="relative">
        <button
          type="button"
          onClick={() => {
            setAbierto((v) => !v);
            if (nuevos.length) marcarVistos(nuevos.map((c) => c.id));
          }}
          aria-expanded={abierto}
          aria-label={total > 0 ? `Casos urgentes sin atender: ${total}` : "Casos urgentes: ninguno sin atender"}
          className="relative text-ink/60 dark:text-ink-dark/60 hover:text-ink dark:hover:text-ink-dark hover:bg-mist dark:hover:bg-surface-dark p-2 rounded-lg transition-colors"
        >
          <Bell size={18} strokeWidth={1.9} aria-hidden="true" />
          {total > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-bold text-white ring-2 ring-surface dark:ring-surface-raised-dark">
              {total > 9 ? "9+" : total}
            </span>
          )}
        </button>

        {abierto && (
          <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[90vw] overflow-hidden rounded-xl border border-border bg-surface shadow-xl dark:border-border-dark dark:bg-surface-raised-dark">
            <p className="m-0 border-b border-border px-4 py-3 text-[13px] font-bold text-ink dark:border-border-dark dark:text-ink-dark">
              Casos urgentes sin atender
            </p>
            {casos.length === 0 ? (
              <p className="m-0 px-4 py-4 text-[12.5px] text-ink/60 dark:text-ink-dark/60">
                No hay casos urgentes nuevos para ti. Te avisaremos aquí cuando entre uno.
              </p>
            ) : (
              <ul className="m-0 max-h-80 list-none divide-y divide-border overflow-y-auto p-0 dark:divide-border-dark">
                {casos.map((c) => (
                  <li key={c.id}>
                    <Link
                      href={`/estudiantes/${c.persona_id}`}
                      onClick={() => setAbierto(false)}
                      className="flex items-start gap-2.5 px-4 py-3 hover:bg-mist dark:hover:bg-surface-dark"
                    >
                      <Siren size={15} aria-hidden="true" className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" />
                      <span className="min-w-0">
                        <span className="block truncate text-[13px] font-semibold text-ink dark:text-ink-dark">{c.nombre_completo}</span>
                        <span className="block text-[12px] text-ink/55 dark:text-ink-dark/55">
                          {c.asignado_a_mi ? "Asignado a ti" : "Sin responsable"} · {new Date(c.creado_en).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" })}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Link
              href="/casos-riesgo"
              onClick={() => setAbierto(false)}
              className="block border-t border-border px-4 py-2.5 text-center text-[12.5px] font-semibold text-teal-700 hover:bg-mist dark:border-border-dark dark:text-teal-accent-dark dark:hover:bg-surface-dark"
            >
              Ir a Casos en riesgo
            </Link>
          </div>
        )}
      </div>

      {nuevos.length > 0 && !abierto && (
        <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-[80] w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-red-200 bg-surface p-4 shadow-xl dark:border-red-500/40 dark:bg-surface-raised-dark">
          <div className="flex items-start gap-2.5">
            <Siren size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" />
            <div className="min-w-0 flex-1">
              <p className="m-0 text-[13px] font-bold text-ink dark:text-ink-dark">
                {nuevos.length === 1 ? "Nuevo caso urgente" : `${nuevos.length} casos urgentes nuevos`}
              </p>
              <p className="m-0 mt-0.5 truncate text-[12.5px] text-ink/65 dark:text-ink-dark/65">{nuevos.map((c) => c.nombre_completo).join(", ")}</p>
              <Link
                href="/casos-riesgo"
                onClick={() => marcarVistos(nuevos.map((c) => c.id))}
                className="mt-1.5 inline-block text-[12.5px] font-semibold text-teal-700 hover:underline dark:text-teal-accent-dark"
              >
                Ver en Casos en riesgo
              </Link>
            </div>
            <button
              type="button"
              onClick={() => marcarVistos(nuevos.map((c) => c.id))}
              aria-label="Cerrar aviso"
              className="shrink-0 rounded p-0.5 text-ink/40 hover:text-ink dark:text-ink-dark/40 dark:hover:text-ink-dark"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
