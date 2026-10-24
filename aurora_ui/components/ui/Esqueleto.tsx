// 🆕 Estados de carga con forma (sesión 2026-10-24) — antes varias
// pantallas iban de vacío a lleno con solo un texto "Cargando..." (o, en
// documentos/page.tsx, la página entera reemplazada por una línea), sin
// ningún indicio de la forma real del contenido que está por aparecer. Se
// siente "trabado" un instante en conexiones lentas. No reemplaza ningún
// mensaje de error/vacío existente — solo el estado intermedio mientras
// `cargando` es true.
function Barra({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-border/70 ${className}`} />;
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
        <div key={i} className="bg-white rounded-card border border-border p-5 space-y-3">
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
        <div key={i} className="rounded-card border border-border bg-white p-4 flex items-center justify-between gap-3">
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
