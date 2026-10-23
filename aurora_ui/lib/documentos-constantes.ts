import type { TipoSeccionDocumento } from "@/types/api";

export const ETIQUETAS_TIPO_SECCION: Record<TipoSeccionDocumento, string> = {
  encabezado: "Encabezado",
  datos_filiacion: "Datos de filiación",
  datos_familiares: "Datos familiares",
  texto_libre: "Texto libre",
  tabla_dinamica: "Tabla",
  resultados_prueba: "Resultados de una prueba (texto/nivel)",
  firma: "Firma",
  grupo_campos: "Grupo de campos (cuadro)",
  firma_doble: "Firma doble",
  ficha_imprimible: "Ficha imprimible en blanco",
  grafico_barras: "Gráfico de barras",
  imagen_anexo: "Imagen / anexo",
  firma_triple: "Firma triple",
  resultados_prueba_multiple: "Resultados de varias pruebas (consolidado)",
};

// Orden sugerido al elegir un tipo nuevo para agregar — los más comunes
// primero (datos de filiación, motivo, observación...), igual que describió
// el psicólogo al pedir esta pantalla.
export const TIPOS_SECCION_ORDENADOS: TipoSeccionDocumento[] = [
  "encabezado",
  "datos_filiacion",
  "datos_familiares",
  "texto_libre",
  "grupo_campos",
  "tabla_dinamica",
  "resultados_prueba",
  "resultados_prueba_multiple",
  "grafico_barras",
  "imagen_anexo",
  "firma",
  "firma_doble",
  "firma_triple",
  "ficha_imprimible",
];

// Tipos cuyo CONTENIDO (no la estructura) se llena documento por documento
// vía el PUT genérico de contenido de sección — el resto es automático
// (encabezado/firma/firma_doble/firma_triple/datos_filiacion/
// datos_familiares/resultados_prueba) o fijo por plantilla
// (ficha_imprimible). 'resultados_prueba_multiple' también se llena por
// documento, pero por su propio endpoint dedicado
// (ResultadosPruebaMultipleRequest), nunca por este genérico — no entra
// en esta lista a propósito.
export const TIPOS_CON_CONTENIDO_EDITABLE: TipoSeccionDocumento[] = [
  "texto_libre",
  "grupo_campos",
  "tabla_dinamica",
  "grafico_barras",
  "imagen_anexo",
];

// Tipos cuya PlantillaSeccion.config tiene un formulario propio en el
// constructor (ver EditorConfigSeccion en documentos/plantillas/[id]/
// page.tsx) — el resto (resultados_prueba/texto_libre/datos_filiacion/
// datos_familiares/grafico_barras/imagen_anexo) simplemente no necesita
// config, nunca llega al botón "Configurar" con un formulario real.
export const TIPOS_CON_CONFIG_SIMPLE: TipoSeccionDocumento[] = [
  "encabezado",
  "firma",
  "grupo_campos",
  "tabla_dinamica",
  "firma_doble",
  "firma_triple",
  "ficha_imprimible",
];
