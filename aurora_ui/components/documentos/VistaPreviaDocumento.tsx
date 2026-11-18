"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { EyeOff, Maximize2, RefreshCw } from "lucide-react";
import { apiClient, estadoHttpDe, mensajeDe } from "@/lib/api-client";
import { ACENTOS } from "@/lib/acentos";
import { EsqueletoHoja } from "@/components/ui/Esqueleto";
import { TextoError } from "@/components/ui/TextoError";

// 🆕 (2026-11-18, opción A del plan de Documentos, pedido de la psicóloga
// del piloto: "ver cómo está quedando el documento mientras lo relleno").
//
// Es el PDF REAL del borrador (GET /documentos/{id}/vista-previa: el mismo
// armado y el mismo dibujante que una emisión, con marca BORRADOR, sin
// versión ni correlativo — ver crud.generar_vista_previa_documento), no una
// imitación en HTML: lo que se ve aquí es exactamente lo que se emitirá.
//
// Se vuelve a pedir cuando cambia `firma` (el contenido guardado) y no hay
// nada pendiente de guardar — es decir, poco después de cada guardado
// automático. Una respuesta vieja nunca pisa a una nueva.

const HojasPdf = dynamic(() => import("./HojasPdf"), { ssr: false, loading: () => <EsqueletoHoja /> });

const VIOLETA = ACENTOS.violeta;
const ESPERA_MS = 700;

export function useVistaPreviaPdf(documentoId: number | string, firma: string, listo: boolean, activa: boolean) {
  const [pdf, setPdf] = useState<Blob | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actualizadoEn, setActualizadoEn] = useState<Date | null>(null);
  const ultimaFirma = useRef<string | null>(null);
  const turno = useRef(0);

  async function pedir() {
    const mio = ++turno.current;
    setCargando(true);
    setError(null);
    try {
      const blob = await apiClient.descargarArchivo(`/documentos/${documentoId}/vista-previa`);
      if (mio !== turno.current) return;
      setPdf(blob);
      setActualizadoEn(new Date());
    } catch (err) {
      if (mio !== turno.current) return;
      ultimaFirma.current = null; // que el próximo guardado reintente
      setError(
        estadoHttpDe(err) === 429
          ? "Se actualizó muchas veces seguidas. Espera un minuto y pulsa «Actualizar»."
          : mensajeDe(err) || "No se pudo armar la vista previa.",
      );
    } finally {
      if (mio === turno.current) setCargando(false);
    }
  }

  useEffect(() => {
    if (!activa || !listo || firma === ultimaFirma.current) return;
    const t = setTimeout(() => {
      ultimaFirma.current = firma;
      void pedir();
    }, ESPERA_MS);
    return () => clearTimeout(t);
    // pedir solo usa refs y setters estables
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activa, listo, firma, documentoId]);

  return { pdf, cargando, error, actualizadoEn, recargar: () => void pedir() };
}

export function PanelVistaPrevia({
  vista,
  pendiente,
  onAmpliar,
  onOcultar,
}: {
  vista: ReturnType<typeof useVistaPreviaPdf>;
  /** Hay cambios todavía sin guardar (la vista previa los mostrará al guardarse). */
  pendiente: boolean;
  onAmpliar: () => void;
  onOcultar: () => void;
}) {
  const refCuerpo = useRef<HTMLDivElement>(null);
  const [ancho, setAncho] = useState(0);

  // Las hojas se dibujan al ancho de la columna (medido, con un respiro para
  // no redibujar en cada píxel mientras se cambia el tamaño de la ventana).
  useEffect(() => {
    const el = refCuerpo.current;
    if (!el) return;
    let t: ReturnType<typeof setTimeout> | undefined;
    const medir = () => {
      clearTimeout(t);
      t = setTimeout(() => setAncho(Math.max(240, Math.floor(el.clientWidth - 24))), 150);
    };
    medir();
    const obs = new ResizeObserver(medir);
    obs.observe(el);
    return () => {
      clearTimeout(t);
      obs.disconnect();
    };
  }, []);

  const estado = vista.cargando
    ? "Actualizando…"
    : pendiente
      ? "Se actualiza al guardar lo que escribes."
      : vista.actualizadoEn
        ? `Al día · ${vista.actualizadoEn.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}`
        : "";

  return (
    <section
      aria-label="Vista previa del documento"
      className={`flex flex-col overflow-hidden rounded-xl border ${VIOLETA.fondoSuave} lg:sticky lg:top-4 lg:h-[calc(100vh-7.5rem)]`}
    >
      <header className={`flex flex-wrap items-center justify-between gap-2 border-b px-3.5 py-2.5 ${VIOLETA.cabecera}`}>
        <div className="min-w-0">
          <h2 className="text-[13.5px] font-bold text-ink dark:text-ink-dark">Así queda el PDF</h2>
          <p role="status" aria-live="polite" className="text-[11.5px] text-ink/65 dark:text-ink-dark/55">
            {estado}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <BotonPanel onClick={vista.recargar} etiqueta="Actualizar" icono={RefreshCw} girar={vista.cargando} />
          <BotonPanel onClick={onAmpliar} etiqueta="Ampliar" icono={Maximize2} desactivado={!vista.pdf} />
          <BotonPanel onClick={onOcultar} etiqueta="Ocultar" icono={EyeOff} />
        </div>
      </header>
      <p className="border-b border-acento-violeta/10 px-3.5 py-1.5 text-[11.5px] text-ink/65 dark:border-acento-violeta-dark/15 dark:text-ink-dark/55">
        La marca «BORRADOR» y el número «se asigna al emitir» solo salen aquí: el documento emitido no los lleva.
      </p>
      <div ref={refCuerpo} className="min-h-[24rem] flex-1 overflow-y-auto bg-ink/[0.06] p-3 dark:bg-black/25">
        <TextoError className="mb-3">{vista.error}</TextoError>
        {vista.pdf && ancho > 0 ? (
          <HojasPdf archivo={vista.pdf} ancho={ancho} onError={() => undefined} />
        ) : !vista.error ? (
          <EsqueletoHoja />
        ) : null}
      </div>
    </section>
  );
}

function BotonPanel({
  onClick,
  etiqueta,
  icono: Icono,
  desactivado = false,
  girar = false,
}: {
  onClick: () => void;
  etiqueta: string;
  icono: typeof RefreshCw;
  desactivado?: boolean;
  girar?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={desactivado}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] font-semibold text-ink/70 hover:bg-ink/5 disabled:opacity-40 dark:text-ink-dark/70 dark:hover:bg-white/5"
    >
      <Icono size={13} className={girar ? "animate-spin" : ""} aria-hidden="true" />
      {etiqueta}
    </button>
  );
}
