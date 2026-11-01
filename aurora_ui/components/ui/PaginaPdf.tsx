"use client";

// 🆕 (sesión 2026-11-01) Única pieza que importa react-pdf/pdf.js. Vive
// aparte para que VisorArchivo.tsx la cargue con next/dynamic({ ssr: false }):
// pdf.js toca `window` al evaluarse el módulo, y como VisorArchivo se
// importaba a nivel de módulo desde /documentos/[id] y la ficha del alumno,
// cada render en el servidor dejaba un "ReferenceError: window is not
// defined" (unhandledRejection) en el log de Next.
//
// El worker de pdf.js (pdf.worker.min.mjs) se sirve como asset estático
// desde /public — copiado a mano desde node_modules/pdfjs-dist/build/. Si se
// actualiza react-pdf/pdfjs-dist, hay que volver a copiarlo para que
// coincida la versión exacta del worker con la del paquete.
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

export default function PaginaPdf({
  archivo,
  pagina,
  zoom,
  onCargado,
  onError,
}: {
  archivo: Blob;
  pagina: number;
  zoom: number;
  onCargado: (totalPaginas: number) => void;
  onError: () => void;
}) {
  return (
    <Document
      file={archivo}
      onLoadSuccess={({ numPages }) => onCargado(numPages)}
      onLoadError={onError}
      loading={<p className="text-sm text-ink/60 dark:text-ink-dark/60 py-8">Cargando documento...</p>}
    >
      <Page pageNumber={pagina} scale={zoom} renderTextLayer={false} renderAnnotationLayer={false} />
    </Document>
  );
}
