import type { TipoSeccionDocumento } from "@/types/api";

// 🆕 (2026-11-17, observaciones de la psicóloga del piloto) Lenguaje llano en
// todo Documentos. Antes los tipos se llamaban por su nombre técnico ("Texto
// libre", "Ficha imprimible en blanco", "Grupo de campos") y no quedaba
// claro cuál escribir, cuál salía solo ni cuál era para imprimir. Ahora cada
// tipo tiene un nombre que dice lo que es y pertenece a uno de 4 MODOS de
// llenado, que se ven igual (color + ícono + frase) en el constructor de
// plantillas, al crear un documento y al llenarlo. Los identificadores del
// backend (`texto_libre`, `ficha_imprimible`...) no cambian.

export const ETIQUETAS_TIPO_SECCION: Record<TipoSeccionDocumento, string> = {
  encabezado: "Encabezado con logo y título",
  datos_filiacion: "Datos del alumno (filiación)",
  datos_familiares: "Datos familiares del alumno",
  texto_libre: "Texto para redactar",
  tabla_dinamica: "Tabla para completar",
  resultados_prueba: "Resultado de una prueba",
  firma: "Firma de quien emite",
  grupo_campos: "Casillas de datos cortos",
  firma_doble: "Dos firmas",
  ficha_imprimible: "Formato en blanco para imprimir",
  grafico_barras: "Gráfico de barras",
  imagen_anexo: "Imagen adjunta",
  firma_triple: "Tres firmas",
  resultados_prueba_multiple: "Resultados de varias pruebas",
};

/** Cómo se llena una sección. Es lo PRIMERO que la psicóloga necesita saber
 *  de cada parte del documento. */
export type ModoSeccion = "escribes" | "eliges" | "automatica" | "imprimir";

export const MODO_TIPO_SECCION: Record<TipoSeccionDocumento, ModoSeccion> = {
  texto_libre: "escribes",
  grupo_campos: "escribes",
  tabla_dinamica: "escribes",
  imagen_anexo: "escribes",
  resultados_prueba: "eliges",
  resultados_prueba_multiple: "eliges",
  grafico_barras: "eliges",
  encabezado: "automatica",
  datos_filiacion: "automatica",
  datos_familiares: "automatica",
  firma: "automatica",
  firma_doble: "automatica",
  firma_triple: "automatica",
  ficha_imprimible: "imprimir",
};

export const INFO_MODO: Record<ModoSeccion, { etiqueta: string; frase: string }> = {
  escribes: { etiqueta: "Lo completas tú", frase: "En cada documento escribes o subes este contenido." },
  eliges: { etiqueta: "Eliges una prueba", frase: "En cada documento eliges qué prueba aplicada al alumno aparece." },
  automatica: { etiqueta: "Se llena solo", frase: "El sistema lo completa al generar el PDF. No escribes nada." },
  imprimir: { etiqueta: "Para imprimir en blanco", frase: "Sale vacío en el PDF para llenarlo a mano en papel." },
};

// Orden y grupos del catálogo al agregar una sección: primero lo que más se
// usa (lo que la psicóloga redacta), al final lo que solo se imprime.
export const GRUPOS_CATALOGO: { modo: ModoSeccion; titulo: string; tipos: TipoSeccionDocumento[] }[] = [
  { modo: "escribes", titulo: "Lo que completas en cada documento", tipos: ["texto_libre", "grupo_campos", "tabla_dinamica", "imagen_anexo"] },
  { modo: "eliges", titulo: "Resultados de pruebas", tipos: ["resultados_prueba", "resultados_prueba_multiple", "grafico_barras"] },
  {
    modo: "automatica",
    titulo: "Se llenan solos",
    tipos: ["encabezado", "datos_filiacion", "datos_familiares", "firma", "firma_doble", "firma_triple"],
  },
  { modo: "imprimir", titulo: "Para imprimir y llenar a mano", tipos: ["ficha_imprimible"] },
];

export const TIPOS_SECCION_ORDENADOS: TipoSeccionDocumento[] = GRUPOS_CATALOGO.flatMap((g) => g.tipos);

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

// Qué hace cada tipo, en una línea y sin jerga.
export const DESCRIPCION_TIPO_SECCION: Record<TipoSeccionDocumento, string> = {
  encabezado: "El logo del colegio y el título del documento, arriba de la primera página.",
  datos_filiacion: "Nombre, edad, DNI y grado del alumno, tomados de su ficha. Tú solo agregas el diagnóstico presuntivo y la fecha.",
  datos_familiares: "Padres, hermanos y apoderado, tomados de la ficha del alumno.",
  texto_libre: "Un espacio para redactar párrafos: motivo, observaciones, conclusiones, recomendaciones…",
  tabla_dinamica: "Una tabla con columnas fijas donde agregas las filas que necesites.",
  resultados_prueba: "El puntaje y la interpretación de UNA prueba que el alumno ya rindió.",
  firma: "Tu nombre y cargo con la línea de firma.",
  grupo_campos: "Varias casillas cortas con su nombre (ej. Fecha, Lugar, Duración) que completas.",
  firma_doble: "Dos firmas lado a lado: la tuya y la de otro cargo (ej. Dirección).",
  ficha_imprimible: "Un formato vacío (casilleros, líneas, preguntas) que se imprime y se llena a mano. En el sistema no se escribe nada.",
  grafico_barras: "Un gráfico con los puntajes de una prueba del alumno, o con valores que escribes.",
  imagen_anexo: "Una foto, dibujo o captura que subes (JPG o PNG).",
  firma_triple: "Tres firmas: la tuya y dos cargos más.",
  resultados_prueba_multiple: "Varias pruebas del alumno juntas en una sola parte.",
};

// Para qué se usa, con ejemplos reales de un informe escolar.
export const EJEMPLO_TIPO_SECCION: Record<TipoSeccionDocumento, string> = {
  encabezado: "Va una sola vez, al inicio.",
  datos_filiacion: "Bloque «I. Datos de filiación» de un informe.",
  datos_familiares: "Bloque «Composición familiar» de un informe.",
  texto_libre: "Motivo de consulta, Observación de conducta, Conclusiones, Recomendaciones.",
  tabla_dinamica: "Registro de sesiones: Fecha · Actividad · Observación.",
  resultados_prueba: "«Resultados del PHQ-9».",
  firma: "Cierre de cualquier informe.",
  grupo_campos: "Datos de la sesión: Fecha · Lugar · Duración · Asistentes.",
  firma_doble: "Psicóloga + Dirección.",
  ficha_imprimible: "Lista de cotejo, hoja de asistencia o ficha de observación que llenas a mano.",
  grafico_barras: "Perfil de puntajes por dimensión.",
  imagen_anexo: "Dibujo de la figura humana, foto de una evidencia.",
  firma_triple: "Psicóloga + Tutor + Dirección.",
  resultados_prueba_multiple: "Informe psicométrico con varias pruebas.",
};

// De dónde sale una sección automática, para explicarlo al llenar.
export const ORIGEN_AUTOMATICA: Partial<Record<TipoSeccionDocumento, string>> = {
  encabezado: "Sale del logo del colegio y del título de este documento.",
  datos_filiacion: "Sale de la ficha del alumno.",
  datos_familiares: "Sale de la ficha del alumno (Datos familiares y Composición familiar). Si falta algo, complétalo en su ficha.",
  firma: "Sale de tu nombre, cargo y firma registrados en tu cuenta.",
  firma_doble: "Tu firma sale de tu cuenta; la otra lleva el cargo configurado en la plantilla.",
  firma_triple: "Tu firma sale de tu cuenta; las otras llevan los cargos configurados en la plantilla.",
  ficha_imprimible: "Sale en blanco en el PDF para llenarlo a mano. Aquí no se escribe nada.",
};

/** Lo que se le dice a quien llena una sección si la plantilla no trae una
 *  instrucción propia (`config.ayuda`). */
export function instruccionPorDefecto(tipo: TipoSeccionDocumento, titulo: string | null): string {
  const nombre = titulo?.trim() ? `«${titulo.trim()}»` : "esta parte";
  switch (tipo) {
    case "texto_libre":
      return `Redacta ${nombre}. Saldrá en el PDF tal como lo escribas.`;
    case "grupo_campos":
      return "Completa cada casilla. Las que dejes vacías salen en blanco en el PDF.";
    case "tabla_dinamica":
      return "Agrega una fila por cada registro y completa sus columnas.";
    case "imagen_anexo":
      return "Sube la imagen que va en esta parte del documento.";
    case "resultados_prueba":
      return "Elige cuál de las pruebas que rindió el alumno aparece aquí.";
    case "resultados_prueba_multiple":
      return "Marca todas las pruebas del alumno que quieres incluir.";
    case "grafico_barras":
      return "Elige una prueba del alumno para graficar, o escribe tú los valores.";
    case "datos_filiacion":
      return "Nombre, edad, documento y grado salen solos de la ficha del alumno. Aquí completas solo estos campos.";
    default:
      return "";
  }
}
