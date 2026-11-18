// 🆕 Estados de carga con forma (sesión 2026-10-24) — antes varias
// pantallas iban de vacío a lleno con solo un texto "Cargando..." (o, en
// documentos/page.tsx, la página entera reemplazada por una línea), sin
// ningún indicio de la forma real del contenido que está por aparecer. Se
// siente "trabado" un instante en conexiones lentas. No reemplaza ningún
// mensaje de error/vacío existente — solo el estado intermedio mientras
// `cargando` es true.
function Barra({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-border/70 dark:bg-border-dark ${className}`} />;
}

export function EsqueletoFilasTabla({ filas = 5, columnas = 4 }: { filas?: number; columnas?: number }) {
  return (
    <>
      {Array.from({ length: filas }).map((_, i) => (
        <tr key={i}>
          {Array.from({ length: columnas }).map((__, j) => (
            <td key={j} className="px-5 py-3">
              <Barra className="h-4 w-full max-w-[12rem]" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function EsqueletoTarjetas({ cantidad = 4 }: { cantidad?: number }) {
  return (
    <>
      {Array.from({ length: cantidad }).map((_, i) => (
        <div key={i} className="bg-surface dark:bg-surface-dark rounded-card border border-border dark:border-border-dark p-5 space-y-3">
          <div className="flex items-center justify-between">
            <Barra className="h-4 w-2/5" />
            <Barra className="h-4 w-16 rounded-full" />
          </div>
          <Barra className="h-3 w-3/5" />
        </div>
      ))}
    </>
  );
}

export function EsqueletoLista({ cantidad = 5 }: { cantidad?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: cantidad }).map((_, i) => (
        <div key={i} className="rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-4 flex items-center justify-between gap-3">
          <div className="space-y-1.5 flex-1">
            <Barra className="h-4 w-1/3" />
            <Barra className="h-3 w-1/2" />
          </div>
          <Barra className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

// 🆕 (2026-11-17, plan de UX fase 1) Piezas para las pantallas que aún
// mostraban un "Cargando…" suelto. Misma barra animada que las de arriba.

/** Un bloque (tarjeta) con título y algunas líneas: formularios, paneles. */
export function EsqueletoBloque({ lineas = 3, className = "" }: { lineas?: number; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`rounded-card border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-5 space-y-3 ${className}`}
    >
      <div className="flex items-center gap-3">
        <Barra className="h-8 w-8 rounded-lg" />
        <Barra className="h-4 w-1/3" />
      </div>
      {Array.from({ length: lineas }).map((_, i) => (
        <Barra key={i} className={`h-3 ${i % 3 === 2 ? "w-2/5" : i % 2 ? "w-3/4" : "w-full"}`} />
      ))}
    </div>
  );
}

/** Fila de etiquetas tipo "chip" (listas de grados, secciones, filtros). */
export function EsqueletoChips({ cantidad = 4 }: { cantidad?: number }) {
  return (
    <div aria-hidden="true" className="flex flex-wrap gap-2">
      {Array.from({ length: cantidad }).map((_, i) => (
        <Barra key={i} className={`h-8 rounded-lg ${i % 2 ? "w-28" : "w-20"}`} />
      ))}
    </div>
  );
}

/** Texto para lectores de pantalla mientras algo carga (lo visual es la silueta). */
export function AvisoCargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p role="status" className="sr-only">
      {texto}
    </p>
  );
}

/** Unas líneas sueltas (listas chicas dentro de un bloque). */
export function EsqueletoLineas({ cantidad = 3 }: { cantidad?: number }) {
  return (
    <div aria-hidden="true" className="space-y-2.5">
      {Array.from({ length: cantidad }).map((_, i) => (
        <div key={i} className="flex items-center gap-2">
          <Barra className="h-6 w-6 rounded-md" />
          <Barra className={`h-3 ${i % 2 ? "w-1/2" : "w-3/4"}`} />
        </div>
      ))}
    </div>
  );
}

/** La grilla de 7 días de la Agenda, con algunas citas fantasma. */
export function EsqueletoSemana() {
  return (
    <div aria-hidden="true" className="grid grid-cols-1 md:grid-cols-7 md:divide-x divide-border dark:divide-border-dark">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="p-3 space-y-2.5 min-h-[10rem]">
          <Barra className="h-3 w-12" />
          {Array.from({ length: (i * 2) % 3 }).map((__, j) => (
            <Barra key={j} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      ))}
    </div>
  );
}

/** Una hoja A4 en blanco con líneas: mientras abre un PDF en el visor. */
export function EsqueletoHoja() {
  return (
    <div className="py-4">
      <AvisoCargando texto="Cargando documento…" />
      <div
        aria-hidden="true"
        className="mx-auto aspect-[1/1.414] w-full max-w-[34rem] rounded-md border border-border dark:border-border-dark bg-surface dark:bg-surface-dark p-[8%] space-y-3 shadow-sm"
      >
        <Barra className="h-5 w-1/2 mx-auto" />
        <div className="h-3" />
        {Array.from({ length: 9 }).map((_, i) => (
          <Barra key={i} className={`h-2.5 ${i % 4 === 3 ? "w-2/3" : "w-full"}`} />
        ))}
      </div>
    </div>
  );
}
