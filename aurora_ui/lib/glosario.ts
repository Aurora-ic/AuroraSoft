// 🆕 (sesión 2026-11-02) Glosario de términos que aparecen en las pantallas
// y no todo el personal conoce, sobre todo el rol de dirección (`colegio`).
// Lo usan el Centro de ayuda (components/educativo/CentroAyuda.tsx) y la
// ayuda junto a cada término (components/ui/TerminoAyuda.tsx), así que las
// dos dicen siempre lo mismo.
//
// Cada definición describe CÓMO FUNCIONA EL SISTEMA hoy (verificado contra
// el backend: crud.alumno_puede_ver_resultados, el historial filtrado a
// informe_liberado para `colegio`, estado_interpretacion, ReglaInterpretacion
// de ámbito ítem). Ninguna dice qué puntaje o tramo es de riesgo en una
// prueba concreta: eso lo define el baremo de cada instrumento.

export type ClaveTermino =
  | "baremo"
  | "en_alerta"
  | "retenido"
  | "liberado"
  | "interpretacion_incompleta"
  | "urgente"
  | "consentimiento"
  | "asentimiento"
  | "resultados_confidenciales";

export const GLOSARIO: Record<ClaveTermino, { termino: string; definicion: string }> = {
  baremo: {
    termino: "Baremo",
    definicion:
      "Tabla de referencia de cada prueba que convierte el puntaje del estudiante en un nivel (por ejemplo, «Leve» o «Moderado»), según su edad, sexo o nivel educativo cuando la prueba los distingue.",
  },
  en_alerta: {
    termino: "En alerta",
    definicion:
      "El resultado de alguna dimensión cayó en un tramo que el baremo de la prueba marca como de alerta, o se activó una regla de la prueba (por ejemplo, un ítem crítico). El informe queda retenido y el caso aparece en Casos en riesgo para que un profesional lo atienda.",
  },
  retenido: {
    termino: "Informe retenido",
    definicion:
      "Todavía no lo revisó un profesional. Queda así cuando hay una alerta o la interpretación quedó incompleta. Mientras está retenido, la dirección no lo ve. Se libera desde la ficha del alumno, en «Revisar informe».",
  },
  liberado: {
    termino: "Informe liberado",
    definicion:
      "Un profesional lo revisó, o no tenía nada que revisar (sin alertas). La dirección ya puede verlo.",
  },
  interpretacion_incompleta: {
    termino: "Interpretación incompleta",
    definicion:
      "Alguna dimensión no encontró un baremo que corresponda al estudiante (por su edad, sexo o nivel), así que no se pudo ubicar en un nivel. No significa «sin riesgo»: el informe queda retenido para que un profesional lo revise.",
  },
  urgente: {
    termino: "Urgente",
    definicion:
      "Se activó una regla de ítem crítico de la prueba: una respuesta concreta que la prueba indica revisar de inmediato, sin importar el puntaje total. Estos casos van primero en la bandeja.",
  },
  consentimiento: {
    termino: "Consentimiento",
    definicion:
      "Autorización del padre, madre o apoderado para que el estudiante sea evaluado. Sin un consentimiento vigente, el estudiante no puede rendir pruebas.",
  },
  asentimiento: {
    termino: "Asentimiento",
    definicion:
      "Aceptación del propio estudiante, que marca antes de empezar el examen. Si el colegio lo exige, además debe estar registrado por adelantado en su ficha.",
  },
  resultados_confidenciales: {
    termino: "Resultados confidenciales",
    definicion:
      "Los resultados individuales (niveles, informes retenidos y notas de seguimiento) son información clínica: solo los ve el equipo de psicología. La dirección ve la participación de cada estudiante y los informes ya liberados.",
  },
};
