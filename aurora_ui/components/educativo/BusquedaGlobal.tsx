"use client";

// 🆕 Buscador único (Ctrl+K / Cmd+K) para encontrar un alumno desde
// cualquier pantalla, sin tener que ir primero al Padrón. Reusa el mismo
// endpoint que ya usa esa pantalla (apiClient.getTodasLasPaginas sobre
// /admin/personas/{institucion_id}) — ningún endpoint nuevo en el backend.
//
// Primer uso real de @tanstack/react-query en este proyecto (ver
// contexts/QueryProvider.tsx: ya estaba cableado desde la fase 5 del plan
// de remodelación, pero ninguna pantalla lo usaba todavía — las páginas ya
// escritas siguen con su propio useState+useEffect, solo el código NUEVO
// adopta useQuery). `enabled: abierto` + `staleTime` de 5 min: el padrón
// se trae una sola vez por apertura y se reutiliza mientras la caché siga
// fresca, sin tener que volver a pedirlo cada vez que se abre el buscador.
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import type { Persona } from "@/types/api";

function formatearSeccion(seccion: Persona["seccion_actual"]): string | null {
  if (!seccion) return null;
  const partes = [seccion.nivel_educativo, seccion.grado, seccion.seccion].filter(Boolean);
  return partes.length > 0 ? partes.join(" · ") : null;
}

export function BusquedaGlobal() {
  const { sesion } = useAuth();
  const router = useRouter();
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const {
    data: personas,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["busqueda-global-personas", sesion?.institucionId],
    queryFn: () =>
      apiClient.getTodasLasPaginas<Persona>(`/admin/personas/${sesion!.institucionId}?incluir_inactivas=true`),
    enabled: abierto && !!sesion?.institucionId,
    staleTime: 5 * 60 * 1000,
  });

  // Atajo global — funciona en cualquier pantalla dentro de (educativo), ver
  // EducativoLayout. preventDefault() porque Chrome usa la misma combinación
  // para el buscador de la barra de direcciones; interceptarla acá es el
  // mismo patrón que ya usan Linear/GitHub/Notion/Vercel.
  useEffect(() => {
    function alTeclear(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAbierto((v) => !v);
      } else if (e.key === "Escape") {
        setAbierto(false);
      }
    }
    window.addEventListener("keydown", alTeclear);
    return () => window.removeEventListener("keydown", alTeclear);
  }, []);

  // Limpia el texto de la búsqueda anterior ajustando el estado durante el
  // render (no en un efecto, ver react-hooks/set-state-in-effect) en cuanto
  // el modal pasa de cerrado a abierto.
  const [abiertoAnterior, setAbiertoAnterior] = useState(abierto);
  if (abierto !== abiertoAnterior) {
    setAbiertoAnterior(abierto);
    if (abierto) setTexto("");
  }

  // Esto sí es un efecto legítimo (foco del DOM, un sistema externo a React).
  useEffect(() => {
    if (!abierto) return;
    const id = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(id);
  }, [abierto]);

  const resultados = useMemo(() => {
    const q = texto.trim().toLowerCase();
    if (!q || !personas) return [];
    return personas
      .filter(
        (p) =>
          p.nombres.toLowerCase().includes(q) ||
          p.apellidos.toLowerCase().includes(q) ||
          (p.documento_identidad ?? "").toLowerCase().includes(q) ||
          (p.codigo_institucional ?? "").toLowerCase().includes(q),
      )
      .slice(0, 20);
  }, [texto, personas]);

  function irAAlumno(personaId: number) {
    setAbierto(false);
    router.push(`/estudiantes/${personaId}`);
  }

  if (!sesion) return null;

  return (
    <>
      <button
        onClick={() => setAbierto(true)}
        className="w-full flex items-center justify-between gap-2 rounded-card border border-border bg-mist/50 px-3 py-2 text-sm text-ink/50 hover:bg-mist transition-colors"
      >
        <span>Buscar alumno...</span>
        <kbd className="text-[10px] font-mono bg-white border border-border rounded px-1.5 py-0.5">Ctrl K</kbd>
      </button>

      {abierto && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-ink/60 pt-24 px-4"
          onClick={() => setAbierto(false)}
        >
          <div
            className="bg-white rounded-card shadow-lg w-full max-w-lg overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <input
              ref={inputRef}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="Buscar por nombre, apellido, documento o código..."
              className="w-full px-4 py-3 text-sm border-b border-border outline-none"
            />
            <div className="max-h-80 overflow-auto">
              {isLoading && <p className="text-sm text-ink/50 px-4 py-6 text-center">Cargando padrón...</p>}
              {isError && <p className="text-sm text-red-700 px-4 py-6 text-center">No se pudo cargar el padrón.</p>}
              {!isLoading && !isError && texto.trim() && resultados.length === 0 && (
                <p className="text-sm text-ink/50 px-4 py-6 text-center">Sin resultados.</p>
              )}
              {!texto.trim() && (
                <p className="text-xs text-ink/40 px-4 py-6 text-center">
                  Escribí para buscar un alumno por nombre, apellido, documento o código.
                </p>
              )}
              {resultados.map((p) => {
                const seccion = formatearSeccion(p.seccion_actual);
                return (
                  <button
                    key={p.id}
                    onClick={() => irAAlumno(p.id)}
                    className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-mist/60 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-ink truncate">
                        {p.nombres} {p.apellidos}
                      </p>
                      <p className="text-xs text-ink/50 truncate">
                        {[p.documento_identidad, p.codigo_institucional, seccion].filter(Boolean).join(" · ") || "—"}
                      </p>
                    </div>
                    {!p.activo && (
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-ink/10 text-ink/50 shrink-0">
                        Inactivo
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
