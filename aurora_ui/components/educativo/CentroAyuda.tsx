"use client";

import { useState } from "react";
import { X, ChevronDown, HelpCircle } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { GLOSARIO } from "@/lib/glosario";

// 🆕 Centro de ayuda (sesión 2026-10-25, a pedido del usuario — "centro de
// ayuda o ayuda como mayormente para en las apps"). Panel lateral con
// preguntas reales sobre flujos que ya existen en el sistema — nada
// inventado: cada respuesta es literalmente cómo funciona hoy la pantalla
// correspondiente.
//
// 🆕 (sesión 2026-11-02) Ampliado de 5 a 12 preguntas y con un glosario
// (lib/glosario.ts, el mismo que muestra el "?" junto a cada término).
// También se corrigió:
//   · dos respuestas que habían quedado viejas: desde 2026-11-01 una plantilla
//     clonada nace ACTIVA y puede haber varias activas del mismo tipo;
//   · el voseo ("elegí", "podés") por el tuteo del resto de la app.
// Las preguntas de "Para la dirección" van primero cuando entra el rol
// `colegio`, que es quien más las necesita.
type Pregunta = { pregunta: string; respuesta: string; grupo: "uso" | "resultados" | "direccion" };

const PREGUNTAS: Pregunta[] = [
  {
    grupo: "direccion",
    pregunta: "¿Por qué no veo los resultados de los estudiantes?",
    respuesta:
      "Los resultados individuales (niveles, informes retenidos y notas de seguimiento) son información clínica y solo los ve el equipo de psicología. Como dirección ves la participación de cada estudiante (quién rindió y quién falta) y los informes que un profesional ya liberó.",
  },
  {
    grupo: "direccion",
    pregunta: "¿Qué diferencia hay entre consentimiento y asentimiento?",
    respuesta:
      "El consentimiento lo da el padre, madre o apoderado, y sin él el estudiante no puede rendir pruebas. El asentimiento es la aceptación del propio estudiante: la marca al empezar el examen y, si el colegio lo exige, además debe estar registrada en su ficha.",
  },
  {
    grupo: "uso",
    pregunta: "¿Cómo creo una campaña de evaluación?",
    respuesta:
      "Campañas → Nueva campaña → elige la prueba y marca los salones: se incluye a todos sus estudiantes que pueden rendirla. También puedes ajustar la lista estudiante por estudiante. Para un solo estudiante, usa «Aplicar prueba» desde su perfil. Cada estudiante recibe su propio enlace y rinde sin necesitar una cuenta.",
  },
  {
    grupo: "uso",
    pregunta: "¿Cuándo puede un estudiante volver a rendir la misma prueba?",
    respuesta:
      "Cada prueba tiene un tiempo mínimo entre aplicaciones, que se ve en el catálogo de Pruebas. Además, no puede tener la misma prueba pendiente en otra campaña. Al crear la campaña, quien no puede rendirla aparece bloqueado con el motivo y la fecha desde la que vuelve a estar disponible.",
  },
  {
    grupo: "resultados",
    pregunta: "¿Por qué un informe aparece «retenido»?",
    respuesta:
      "Porque el resultado tiene una alerta o la interpretación quedó incompleta. El informe queda retenido hasta que un profesional lo revisa y lo libera desde la ficha del alumno, en «Revisar informe». Mientras tanto, la dirección no lo ve.",
  },
  {
    grupo: "resultados",
    pregunta: "¿Qué ve el estudiante al terminar su examen?",
    respuesta:
      "Depende del interruptor «Los estudiantes ven su resultado», que se elige al crear la campaña y se puede cambiar en su panel. Encendido: ve su resumen y puede descargar su informe en PDF, también si hay una alerta. Apagado: solo ve un mensaje de agradecimiento.",
  },
  {
    grupo: "resultados",
    pregunta: "¿Cómo se ordenan los casos en riesgo?",
    respuesta:
      "Primero los urgentes (se activó un ítem crítico), luego los de alerta (el baremo marcó alerta) y al final los de seguimiento (antecedentes clínicos externos). Dentro de cada nivel va primero el que lleva más tiempo sin seguimiento. Un caso sale de la bandeja solo cuando lo cierras, indicando el motivo.",
  },
  {
    grupo: "resultados",
    pregunta: "¿Qué significa «Interpretación incompleta»?",
    respuesta:
      "Que alguna dimensión no encontró un baremo que corresponda al estudiante, así que no se pudo ubicar en un nivel. No significa «sin riesgo»: el informe queda retenido para que un profesional lo revise.",
  },
  {
    grupo: "uso",
    pregunta: "¿Qué significa que una campaña esté «Vencida»?",
    respuesta:
      "Que ya pasó su fecha de cierre sin que nadie la cerrara a mano. Deja de aceptar matrículas y exámenes nuevos automáticamente. Puedes editarla para extender la fecha, o cerrarla formalmente desde su panel.",
  },
  {
    grupo: "uso",
    pregunta: "¿Cómo uso una plantilla del catálogo?",
    respuesta:
      "Documentos → pestaña «Catálogo para clonar» → Clonar. La copia queda en «Mis plantillas», ya activa, y puedes ajustarla en el constructor sin tocar el original.",
  },
  {
    grupo: "uso",
    pregunta: "¿Por qué no puedo generar un documento desde una plantilla «Inactiva»?",
    respuesta:
      "Una plantilla inactiva no se usa para documentos nuevos. Actívala desde su tarjeta o desde el constructor. Puede haber varias plantillas activas del mismo tipo, así que activar una no apaga las demás.",
  },
  {
    grupo: "uso",
    pregunta: "¿Por qué se bloqueó mi sesión?",
    respuesta:
      "Tras 15 minutos sin actividad, la pantalla se bloquea para proteger los datos de los estudiantes, sobre todo en computadoras compartidas. Lo que estabas escribiendo sigue ahí: ingresa tu contraseña para continuar.",
  },
];

const GRUPOS: { clave: Pregunta["grupo"]; titulo: string }[] = [
  { clave: "direccion", titulo: "Para la dirección" },
  { clave: "resultados", titulo: "Resultados e informes" },
  { clave: "uso", titulo: "Uso del sistema" },
];

export function CentroAyuda({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const { sesion } = useAuth();
  const [preguntaAbierta, setPreguntaAbierta] = useState<string | null>(null);
  const [glosarioAbierto, setGlosarioAbierto] = useState(false);

  if (!abierto) return null;

  // La dirección ve primero sus preguntas; el resto, en el orden de trabajo.
  const orden = sesion?.rol === "colegio" ? GRUPOS : [GRUPOS[1], GRUPOS[2], GRUPOS[0]];

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

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">
          {orden.map((grupo) => (
            <section key={grupo.clave} className="flex flex-col gap-2.5">
              <h3 className="m-0 text-[11px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">{grupo.titulo}</h3>
              {PREGUNTAS.filter((p) => p.grupo === grupo.clave).map((item) => {
                const abiertaEsta = preguntaAbierta === item.pregunta;
                return (
                  <div key={item.pregunta} className="border border-border dark:border-border-dark rounded-xl overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setPreguntaAbierta(abiertaEsta ? null : item.pregunta)}
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
                      <p className="m-0 px-4 py-3 text-[12px] leading-relaxed text-ink/65 dark:text-ink-dark/65">{item.respuesta}</p>
                    )}
                  </div>
                );
              })}
            </section>
          ))}

          <section className="flex flex-col gap-2.5">
            <h3 className="m-0 text-[11px] font-bold uppercase tracking-wide text-ink/45 dark:text-ink-dark/45">Glosario</h3>
            <div className="border border-border dark:border-border-dark rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => setGlosarioAbierto((v) => !v)}
                aria-expanded={glosarioAbierto}
                className="w-full flex items-center justify-between gap-3 bg-mist dark:bg-surface-raised-dark px-4 py-3 text-left"
              >
                <span className="text-[12.5px] font-semibold text-ink dark:text-ink-dark">Términos que aparecen en las pantallas</span>
                <ChevronDown
                  size={14}
                  strokeWidth={2.4}
                  aria-hidden="true"
                  className={`flex-shrink-0 text-ink/50 dark:text-ink-dark/50 transition-transform ${glosarioAbierto ? "rotate-180" : ""}`}
                />
              </button>
              {glosarioAbierto && (
                <dl className="m-0 px-4 py-3 flex flex-col gap-3">
                  {Object.values(GLOSARIO).map((t) => (
                    <div key={t.termino}>
                      <dt className="text-[12px] font-semibold text-ink dark:text-ink-dark">{t.termino}</dt>
                      <dd className="m-0 mt-0.5 text-[12px] leading-relaxed text-ink/65 dark:text-ink-dark/65">{t.definicion}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </section>

          <p className="mt-1 px-0.5 text-[12px] leading-relaxed text-ink/40 dark:text-ink-dark/40">
            ¿No encontraste lo que buscabas? Escríbenos a auroraintegratedconsulting@gmail.com.
          </p>
        </div>
      </div>
    </>
  );
}
