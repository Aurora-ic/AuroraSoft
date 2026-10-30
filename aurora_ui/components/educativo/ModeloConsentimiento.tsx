"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { FileDown, FileText, ChevronDown } from "lucide-react";
import { ApiError, apiClient, descargarBlob } from "@/lib/api-client";
import type { TextoConsentimientoVigente, TipoTextoConsentimiento } from "@/types/api";

// 🆕 Modelo de consentimiento/asentimiento del colegio dentro de la ficha
// del alumno (sesión 2026-10-30). Muestra QUÉ texto le corresponde a este
// alumno hoy (el de su nivel, el general del colegio o el global — ver
// GET /educativo/modelos-consentimiento/vigente), lo despliega al registrar
// (la versión que se ve aquí es la que el backend guarda en
// ConsentimientoInformado.texto_version_id), y genera el PDF para imprimir y
// firmar con los datos del alumno ya completados. El escaneado firmado se
// sube después como evidencia, con el control que ya existía en la ficha.

const ETIQUETA_ORIGEN: Record<TextoConsentimientoVigente["origen"], string> = {
  nivel: "modelo de su nivel",
  colegio: "modelo general del colegio",
  global: "modelo por defecto de AuroraSoft",
};

// Resalta los marcadores ({{alumno}}...) que el PDF reemplaza con datos reales.
function TextoConMarcadores({ texto }: { texto: string }) {
  const partes = texto.split(/(\{\{\s*[a-z_]+\s*\}\})/g);
  return (
    <>
      {partes.map((p, i) =>
        /^\{\{/.test(p) ? (
          <span key={i} className="rounded bg-teal-600/10 dark:bg-teal-accent-dark/15 px-1 font-mono text-[11px] text-teal-800 dark:text-teal-accent-dark">
            {p}
          </span>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

export function ModeloConsentimiento({
  personaId,
  tipo,
  expandido = false,
}: {
  personaId: string | number;
  tipo: TipoTextoConsentimiento;
  // true mientras se está registrando: el texto se muestra abierto.
  expandido?: boolean;
}) {
  const [modelo, setModelo] = useState<TextoConsentimientoVigente | null>(null);
  const [estado, setEstado] = useState<"cargando" | "listo" | "sin_modelo" | "error">("cargando");
  const [abierto, setAbierto] = useState(expandido);
  const [descargando, setDescargando] = useState(false);
  const [errorPdf, setErrorPdf] = useState<string | null>(null);

  // Abrir el registro despliega el texto; cerrarlo lo deja como esté.
  const [expandidoAnterior, setExpandidoAnterior] = useState(expandido);
  if (expandido !== expandidoAnterior) {
    setExpandidoAnterior(expandido);
    if (expandido) setAbierto(true);
  }

  useEffect(() => {
    let vigente = true;
    apiClient
      .get<TextoConsentimientoVigente>(`/educativo/modelos-consentimiento/vigente?persona_id=${personaId}&tipo_texto=${tipo}`)
      .then((m) => {
        if (!vigente) return;
        setModelo(m);
        setEstado("listo");
      })
      .catch((err: unknown) => {
        if (!vigente) return;
        setEstado(err instanceof ApiError && err.status === 404 ? "sin_modelo" : "error");
      });
    return () => {
      vigente = false;
    };
  }, [personaId, tipo]);

  async function descargarPdf() {
    setDescargando(true);
    setErrorPdf(null);
    try {
      const blob = await apiClient.descargarArchivo(`/educativo/modelos-consentimiento/pdf?persona_id=${personaId}&tipo_texto=${tipo}`);
      descargarBlob(blob, `${tipo === "apoderado" ? "consentimiento" : "asentimiento"}_${personaId}.pdf`);
    } catch (err: unknown) {
      setErrorPdf(err instanceof Error && err.message ? err.message : "No se pudo generar el PDF.");
    } finally {
      setDescargando(false);
    }
  }

  if (estado === "cargando" || estado === "error") return null;

  if (estado === "sin_modelo" || !modelo) {
    return (
      <p className="m-0 flex items-center gap-1.5 text-[11.5px] text-ink/50 dark:text-ink-dark/50">
        <FileText size={13} aria-hidden="true" />
        Tu colegio todavía no configuró el modelo de {tipo === "apoderado" ? "consentimiento" : "asentimiento"}.{" "}
        <Link href="/asentimiento" className="font-semibold text-teal-700 dark:text-teal-accent-dark hover:underline">
          Configurarlo
        </Link>
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-border dark:border-border-dark bg-mist/30 dark:bg-surface-raised-dark/40">
      <div className="flex items-center justify-between gap-2 flex-wrap px-3 py-2">
        <button
          type="button"
          onClick={() => setAbierto((v) => !v)}
          aria-expanded={abierto}
          className="flex items-center gap-1.5 text-xs text-ink/70 dark:text-ink-dark/70 hover:text-teal-700 dark:hover:text-teal-accent-dark"
        >
          <ChevronDown size={13} aria-hidden="true" className={`transition-transform ${abierto ? "rotate-180" : ""}`} />
          <FileText size={13} aria-hidden="true" />
          <span>
            <strong className="font-semibold">Modelo v{modelo.version}</strong> · {ETIQUETA_ORIGEN[modelo.origen]}
          </span>
        </button>
        <button
          type="button"
          onClick={descargarPdf}
          disabled={descargando}
          className="inline-flex items-center gap-1.5 rounded-lg border border-border dark:border-border-dark bg-surface dark:bg-surface-dark px-2.5 py-1 text-xs font-semibold text-teal-700 dark:text-teal-accent-dark hover:border-teal-400 disabled:opacity-50"
        >
          <FileDown size={13} aria-hidden="true" />
          {descargando ? "Generando…" : "PDF para firmar"}
        </button>
      </div>
      {errorPdf && <p className="m-0 px-3 pb-2 text-xs text-red-700 dark:text-red-300">{errorPdf}</p>}
      {abierto && (
        <div className="border-t border-border dark:border-border-dark px-3 py-2.5 max-h-64 overflow-y-auto space-y-1.5">
          {modelo.contenido
            .split("\n")
            .filter((l) => l.trim())
            .map((linea, i) => (
              <p key={i} className="m-0 text-[12.5px] leading-relaxed text-ink/80 dark:text-ink-dark/80">
                <TextoConMarcadores texto={linea} />
              </p>
            ))}
          {expandido && (
            <p className="m-0 pt-1 text-[11px] italic text-ink/45 dark:text-ink-dark/45">
              Al registrar, queda guardado que se usó esta versión del modelo.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
