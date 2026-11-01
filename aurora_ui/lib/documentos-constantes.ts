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

// 🆕 (sesión 2026-11-01) Una línea por tipo: qué hace la sección y quién la
// llena. La usan el constructor (al elegir qué agregar) y el editor del
// documento (para explicar las secciones que se completan solas en vez de
// mostrar solo su título sin nada debajo).
export const DESCRIPCION_TIPO_SECCION: Record<TipoSeccionDocumento, string> = {
  encabezado: "Membrete y título del documento. Se arma solo al generar.",
  datos_filiacion: "Datos del alumno desde su ficha; en cada documento solo completas los campos profesionales.",
  datos_familiares: "Composición familiar tomada de la ficha del alumno. Se llena sola.",
  texto_libre: "Párrafos que escribes en cada documento (admite viñetas y negrita).",
  tabla_dinamica: "Tabla con columnas fijas: filas libres o una fila por alumno.",
  resultados_prueba: "Resultado de una prueba aplicada al alumno, elegida de su historial.",
  firma: "Nombre y cargo de quien genera el documento. Se completa sola.",
  grupo_campos: "Cuadro de campos con etiqueta (ej. Nombre, Edad) que llenas en cada documento.",
  firma_doble: "Dos bloques de firma lado a lado. Se completan solos.",
  ficha_imprimible: "Formulario en blanco para imprimir y llenar a mano. Sale tal como se configuró.",
  grafico_barras: "Gráfico desde una prueba vinculada o con valores que cargas a mano.",
  imagen_anexo: "Una imagen (JPG o PNG) que subes en cada documento.",
  firma_triple: "Tres bloques de firma. Se completan solos.",
  resultados_prueba_multiple: "Varias pruebas del alumno consolidadas en una sola sección.",
};
