"use client";

import { Copy, FilePlus2, LayoutTemplate } from "lucide-react";
import { LeyendaModos } from "@/components/documentos/ModoSeccion";
import { GuiaSeccion } from "@/components/ui/GuiaSeccion";

// 🆕 (2026-11-17, a pedido de la psicóloga del piloto) Inducción breve a
// Documentos: los tres conceptos (catálogo, plantilla, documento) y las 4
// maneras en que se llena una parte. La caja en sí es GuiaSeccion (la misma
// de Campañas, Casos en riesgo y Pruebas); la clave de localStorage es la de
// siempre, así quien ya la ocultó no la vuelve a ver.

const PASOS = [
  {
    icono: Copy,
    titulo: "1. Catálogo",
    texto: "Formatos listos (informe escolar, para padres, plan de intervención…). Clonas el que te sirva.",
  },
  {
    icono: LayoutTemplate,
    titulo: "2. Mis plantillas",
    texto: "Tu copia del formato: el molde. Decides qué partes tiene y en qué orden. Se arma una vez.",
  },
  {
    icono: FilePlus2,
    titulo: "3. Nuevo documento",
    texto: "Eliges la plantilla y el alumno, completas solo lo que te toca y generas el PDF.",
  },
];

export function GuiaDocumentos() {
  return (
    <GuiaSeccion clave="aurora.guia-documentos.oculta" titulo="¿Cómo funcionan los documentos?" pasos={PASOS}>
      <p className="m-0 mt-3.5 mb-2 text-[12.5px] font-semibold text-ink/70 dark:text-ink-dark/70">
        Cada parte de un documento lleva una etiqueta que dice cómo se llena:
      </p>
      <LeyendaModos />
    </GuiaSeccion>
  );
}
