"use client";

// 🆕 (2026-11-18) Todas las hojas de un PDF, una debajo de otra, al ancho de
// la columna — para la vista previa del documento mientras se rellena.
// Mismo motor que PaginaPdf.tsx (react-pdf, cargado solo en el cliente).
//
// Sin parpadeo: cuando llega un PDF nuevo, se dibuja ESCONDIDO detrás del
// actual y recién cuando todas sus hojas están pintadas reemplaza al
// anterior. Así la vista previa nunca se queda en blanco mientras se
// actualiza y el desplazamiento de la columna se mantiene.
import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { EsqueletoHoja } from "@/components/ui/Esqueleto";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

function Hojas({
  archivo,
  ancho,
  onListo,
  onError,
}: {
  archivo: Blob;
  ancho: number;
  onListo?: () => void;
  onError: () => void;
}) {
  const [paginas, setPaginas] = useState(0);
  const [pintadas, setPintadas] = useState(0);
  // Se avisa UNA sola vez por capa (onListo cambia de identidad en cada render).
  const avisado = useRef(false);
  const refOnListo = useRef(onListo);
  useEffect(() => {
    refOnListo.current = onListo;
  });
  useEffect(() => {
    if (!avisado.current && paginas > 0 && pintadas >= paginas) {
      avisado.current = true;
      refOnListo.current?.();
    }
  }, [paginas, pintadas]);
  return (
    <Document
      file={archivo}
      onLoadSuccess={({ numPages }) => setPaginas(numPages)}
      onLoadError={onError}
      loading={<EsqueletoHoja />}
    >
      {Array.from({ length: paginas }).map((_, i) => (
        <div key={i} className="mb-3 overflow-hidden rounded-sm bg-white shadow-md ring-1 ring-black/5">
          <Page
            pageNumber={i + 1}
            width={ancho}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            onRenderSuccess={() => setPintadas((n) => n + 1)}
          />
        </div>
      ))}
    </Document>
  );
}

type Capa = { id: number; blob: Blob; lista: boolean };

export default function HojasPdf({
  archivo,
  ancho,
  onError,
}: {
  archivo: Blob;
  ancho: number;
  onError: () => void;
}) {
  // Cada PDF que llega es una "capa" con su propio <Document> montado. La
  // capa visible es la más nueva ya pintada; una más nueva todavía se dibuja
  // invisible encima y, al terminar, pasa al frente SIN volver a montarse
  // (misma key): por eso no hay parpadeo. Las capas viejas se descartan.
  const [capas, setCapas] = useState<Capa[]>([{ id: 1, blob: archivo, lista: false }]);
  const [ultimo, setUltimo] = useState<Blob>(archivo);
  if (archivo !== ultimo) {
    setUltimo(archivo);
    setCapas((prev) => [...prev, { id: (prev[prev.length - 1]?.id ?? 0) + 1, blob: archivo, lista: false }]);
  }

  const listas = capas.filter((c) => c.lista);
  const visibleId = listas.length ? listas[listas.length - 1].id : capas[0].id;

  function marcarLista(id: number) {
    setCapas((prev) => prev.filter((c) => c.id >= id).map((c) => (c.id === id ? { ...c, lista: true } : c)));
  }

  return (
    <div className="relative">
      {capas
        .filter((c) => c.id >= visibleId)
        .map((c) => (
          <div
            key={`${c.id}-${ancho}`}
            className={c.id === visibleId ? "" : "pointer-events-none absolute inset-x-0 top-0 opacity-0"}
            aria-hidden={c.id === visibleId ? undefined : true}
          >
            <Hojas
              archivo={c.blob}
              ancho={ancho}
              onListo={() => marcarLista(c.id)}
              onError={() => {
                if (c.id === visibleId) onError();
                else setCapas((prev) => prev.filter((x) => x.id !== c.id));
              }}
            />
          </div>
        ))}
    </div>
  );
}
