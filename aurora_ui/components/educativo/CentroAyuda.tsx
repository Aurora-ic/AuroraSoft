"use client";

import { useState } from "react";
import { X, ChevronDown, HelpCircle } from "lucide-react";

// 🆕 Centro de ayuda (sesión 2026-10-25, a pedido del usuario — "centro de
// ayuda o ayuda como mayormente para en las apps"). Panel lateral con
// preguntas reales sobre flujos que ya existen en el sistema — nada
// inventado: cada respuesta es literalmente cómo funciona hoy la pantalla
// correspondiente (ver docs/motor-documentos.md para clonar/activar,
// docs/informes-psicometricos.md para "retenido", lib/campanas.ts para
// "vencida"). El dato de contacto queda entre corchetes a propósito — no
// hay un correo/canal de soporte real definido todavía, y poner uno
// inventado sería peor que no poner nada.
const PREGUNTAS: { pregunta: string; respuesta: string }[] = [
  {
    pregunta: "¿Cómo creo una campaña de evaluación?",
    respuesta:
      "Campañas → Nueva campaña → elegí la prueba y a quién va (uno o varios alumnos, o un salón completo). Se generan los links mágicos para que cada estudiante rinda sin necesitar una cuenta.",
  },
  {
    pregunta: "¿Por qué un informe aparece \"retenido\"?",
    respuesta:
      "Cuando el resultado indica un nivel de alerta, el informe queda retenido hasta que un profesional lo revisa y lo libera manualmente desde la ficha del alumno — nunca se entrega de forma automática en ese caso.",
  },
  {
    pregunta: "¿Cómo clono una plantilla del catálogo?",
    respuesta:
      "Documentos → pestaña \"Catálogo para clonar\" → Clonar a mi institución. La copia nace inactiva a propósito, para no reemplazar sin querer la plantilla que ya usás — activala desde el constructor cuando esté lista.",
  },
  {
    pregunta: "¿Qué significa que una campaña esté \"Vencida\"?",
    respuesta:
      "Que ya pasó su fecha de cierre sin que nadie la cerrara a mano. Deja de aceptar matrículas o exámenes nuevos automáticamente. Podés editarla para extender la fecha, o cerrarla formalmente desde su panel.",
  },
  {
    pregunta: "¿Por qué no puedo generar un documento desde una plantilla \"Inactiva\"?",
    respuesta:
      "Solo la plantilla activa de cada tipo de documento se usa para generar documentos nuevos — es a propósito, para que nunca haya dos plantillas del mismo tipo compitiendo. Activala desde su tarjeta o desde el constructor.",
  },
];

export function CentroAyuda({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const [preguntaAbierta, setPreguntaAbierta] = useState<number | null>(0);

  if (!abierto) return null;

  return (
    <>
      <div
        onClick={onCerrar}
        aria-hidden="true"
        className="fixed inset-0 bg-ink/35 dark:bg-black/55 z-40"
      />
      <div
        role="dialog"
        aria-label="Centro de ayuda"
        className="fixed top-0 right-0 h-screen w-full max-w-[400px] bg-surface dark:bg-surface-dark z-50 shadow-2xl flex flex-col"
      >
        <div className="flex items-center justify-between gap-3 px-6 py-5 border-b border-border dark:border-border-dark">
          <h2 className="font-display text-[17px] font-bold text-ink dark:text-ink-dark flex items-center gap-2">
            <HelpCircle size={19} strokeWidth={2} className="text-teal-600 dark:text-teal-accent-dark" aria-hidden="true" />
            Centro de ayuda
          </h2>
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar"
            className="text-ink/40 dark:text-ink-dark/40 hover:text-ink dark:hover:text-ink-dark p-1 rounded-lg"
          >
            <X size={18} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-2.5">
          {PREGUNTAS.map((item, idx) => {
            const abiertaEsta = preguntaAbierta === idx;
            return (
              <div key={idx} className="border border-border dark:border-border-dark rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setPreguntaAbierta(abiertaEsta ? null : idx)}
                  aria-expanded={abiertaEsta}
                  className="w-full flex items-center justify-between gap-3 bg-mist dark:bg-surface-raised-dark px-4 py-3 text-left"
                >
                  <span className="text-[12.5px] font-semibold text-ink dark:text-ink-dark">{item.pregunta}</span>
                  <ChevronDown
                    size={14}
                    strokeWidth={2.4}
                    aria-hidden="true"
                    className={`flex-shrink-0 text-ink/50 dark:text-ink-dark/50 transition-transform ${abiertaEsta ? "rotate-180" : ""}`}
                  />
                </button>
                {abiertaEsta && (
                  <p className="m-0 px-4 py-3 text-[12px] leading-relaxed text-ink/65 dark:text-ink-dark/65">
                    {item.respuesta}
                  </p>
                )}
              </div>
            );
          })}
          <p className="mt-1 px-0.5 text-[11.5px] leading-relaxed text-ink/40 dark:text-ink-dark/40">
            ¿No encontraste lo que buscabas? Escribinos a auroraintegratedconsulting@gmail.com.
          </p>
        </div>
      </div>
    </>
  );
}
