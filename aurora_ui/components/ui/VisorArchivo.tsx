"use client";

// Visor de archivos reusable (informe PDF, documento institucional, evidencia
// del expediente) — reemplaza el patrón anterior de "descargar siempre a
// disco para poder ver el contenido". Usa react-pdf (envoltorio de pdf.js,
// el mismo motor que Chrome/Firefox usan nativamente) en vez de un
// <iframe>/<embed> apuntando al navegador: en móvil (Chrome Android, Safari
// iOS) el visor nativo de PDF suele forzar la descarga en vez de mostrarlo
// inline, mientras que react-pdf dibuja cada página en un <canvas> propio,
// controlado por esta app — funciona igual en cualquier dispositivo.
//
// El worker de pdf.js (pdf.worker.min.mjs) se sirve como asset estático
// desde /public — copiado a mano desde node_modules/pdfjs-dist/build/ al
// instalar el paquete (ver comentario de más abajo). Si se actualiza
// react-pdf/pdfjs-dist, hay que volver a copiarlo para que coincida la
// versión exacta del worker con la del paquete.
import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

export type ArchivoParaVisor = {
  blob: Blob;
  contentType: string | null;
  nombreArchivo: string;
};

function tipoDeArchivo(contentType: string | null): "pdf" | "imagen" | "otro" {
  if (!contentType) return "otro";
  if (contentType === "application/pdf") return "pdf";
  if (contentType.startsWith("image/")) return "imagen";
  return "otro";
}

function descargar(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

/** El renderizador en sí (páginas/imagen + controles de zoom y paginación),
 * sin ningún "chrome" de modal — se usa tal cual embebido en línea (ver
 * la ficha del alumno, panel "Revisar informe") y también por dentro de
 * <VisorArchivoModal> para el caso "Ver" rápido desde una lista. */
export function ContenidoVisorArchivo({
  archivo,
  cargando,
  error,
  alturaClase = "h-[70vh]",
}: {
  archivo: ArchivoParaVisor | null;
  cargando?: boolean;
  error?: string | null;
  alturaClase?: string;
}) {
  const [paginaActual, setPaginaActual] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);
  const [errorPdf, setErrorPdf] = useState<string | null>(null);
  const [urlImagen, setUrlImagen] = useState<string | null>(null);

  const tipo = tipoDeArchivo(archivo?.contentType ?? null);

  // Reinicia paginación/zoom cada vez que cambia el archivo mostrado (no al
  // cambiar de página/zoom, que es estado propio de este mismo archivo) —
  // ajuste de estado durante el render, no en un efecto (evita el
  // render-commit-efecto-render en cascada que un useEffect con setState
  // produciría acá, ver react-hooks/set-state-in-effect).
  const [archivoAnterior, setArchivoAnterior] = useState(archivo);
  if (archivo !== archivoAnterior) {
    setArchivoAnterior(archivo);
    setPaginaActual(1);
    setTotalPaginas(null);
    setZoom(1);
    setErrorPdf(null);
  }

  // Esto sí es un efecto legítimo (sincroniza con la API del navegador
  // URL.createObjectURL/revokeObjectURL, no solo deriva estado de props).
  useEffect(() => {
    if (!archivo || tipo !== "imagen") return;
    const url = URL.createObjectURL(archivo.blob);
    setUrlImagen(url);
    return () => URL.revokeObjectURL(url);
  }, [archivo, tipo]);

  const errorAMostrar = error || errorPdf;

  return (
    <div className="flex flex-col gap-2">
      {tipo === "pdf" && archivo && !cargando && !errorAMostrar && (
        <div className="flex items-center justify-end gap-3 text-xs text-ink/60 dark:text-ink-dark/60">
          <button onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} className="px-1.5 hover:text-ink">
            −
          </button>
          <span className="w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((z) => Math.min(2.5, z + 0.25))} className="px-1.5 hover:text-ink">
            +
          </button>
        </div>
      )}

      <div className={`${alturaClase} overflow-auto rounded-card border border-border dark:border-border-dark bg-mist/20 dark:bg-surface-raised-dark flex items-start justify-center p-3`}>
        {cargando && <p className="text-sm text-ink/60 dark:text-ink-dark/60 py-8">Cargando vista previa...</p>}
        {!cargando && errorAMostrar && <p className="text-sm text-red-700 dark:text-red-300 py-8 px-4 text-center">{errorAMostrar}</p>}

        {!cargando && !errorAMostrar && archivo && tipo === "pdf" && (
          <Document
            file={archivo.blob}
            onLoadSuccess={({ numPages }) => setTotalPaginas(numPages)}
            onLoadError={() => setErrorPdf("No se pudo mostrar el PDF en pantalla. Probá descargarlo.")}
            loading={<p className="text-sm text-ink/60 dark:text-ink-dark/60 py-8">Cargando documento...</p>}
          >
            <Page pageNumber={paginaActual} scale={zoom} renderTextLayer={false} renderAnnotationLayer={false} />
          </Document>
        )}

        {!cargando && !errorAMostrar && urlImagen && tipo === "imagen" && (
          // eslint-disable-next-line @next/next/no-img-element -- next/image no maneja blob: URLs dinámicas
          <img src={urlImagen} alt={archivo?.nombreArchivo || "archivo"} className="max-w-full max-h-full object-contain" />
        )}

        {!cargando && !errorAMostrar && archivo && tipo === "otro" && (
          <p className="text-sm text-ink/60 dark:text-ink-dark/60 py-8 text-center">
            Este tipo de archivo no se puede previsualizar. Descargalo para verlo.
          </p>
        )}

        {!cargando && !errorAMostrar && !archivo && (
          <p className="text-sm text-ink/50 dark:text-ink-dark/50 italic py-8">Sin archivo generado todavía.</p>
        )}
      </div>

      {tipo === "pdf" && totalPaginas !== null && totalPaginas > 1 && !cargando && !errorAMostrar && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPaginaActual((p) => Math.max(1, p - 1))}
            disabled={paginaActual <= 1}
            className="text-sm text-ink/70 dark:text-ink-dark/70 hover:text-ink disabled:opacity-30"
          >
            ← Anterior
          </button>
          <span className="text-xs text-ink/60 dark:text-ink-dark/60">
            Página {paginaActual} de {totalPaginas}
          </span>
          <button
            onClick={() => setPaginaActual((p) => Math.min(totalPaginas, p + 1))}
            disabled={paginaActual >= totalPaginas}
            className="text-sm text-ink/70 dark:text-ink-dark/70 hover:text-ink disabled:opacity-30"
          >
            Siguiente →
          </button>
        </div>
      )}
    </div>
  );
}

/** Modal de "Ver" rápido desde un botón de lista (pruebas aplicadas,
 * documentos, evidencia) — carga perezosa: el caller solo pasa `archivo`
 * cuando ya tiene el Blob (normalmente el mismo que usaría para descargar),
 * `cargando` mientras lo trae, y controla abierto/cerrado con `abierto`. */
export function VisorArchivoModal({
  abierto,
  onCerrar,
  archivo,
  cargando,
  error,
  titulo,
}: {
  abierto: boolean;
  onCerrar: () => void;
  archivo: ArchivoParaVisor | null;
  cargando?: boolean;
  error?: string | null;
  titulo?: string;
}) {
  if (!abierto) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4" onClick={onCerrar}>
      <div
        className="bg-surface dark:bg-surface-dark rounded-card shadow-lg max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border dark:border-border-dark px-4 py-3 gap-3">
          <span className="text-sm font-semibold text-teal-900 dark:text-ink-dark truncate">
            {titulo || archivo?.nombreArchivo || "Vista previa"}
          </span>
          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={() => archivo && descargar(archivo.blob, archivo.nombreArchivo)}
              disabled={!archivo}
              className="text-xs text-teal-600 dark:text-teal-accent-dark hover:underline font-medium disabled:opacity-40"
            >
              Descargar
            </button>
            <button onClick={onCerrar} className="text-ink/60 dark:text-ink-dark/60 hover:text-ink text-xl leading-none px-1" aria-label="Cerrar">
              ×
            </button>
          </div>
        </div>

        <div className="p-4 overflow-auto">
          <ContenidoVisorArchivo archivo={archivo} cargando={cargando} error={error} alturaClase="h-[75vh]" />
        </div>
      </div>
    </div>
  );
}
