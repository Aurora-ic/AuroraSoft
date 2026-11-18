import type { ButtonHTMLAttributes } from "react";

export type VarianteBoton = "primario" | "secundario";

const CLASES_BASE =
  "rounded-card text-sm px-4 py-2 font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed";

const CLASES_VARIANTE: Record<VarianteBoton, string> = {
  // 🆕 (2026-11-17) `accion` y `seccion-claro` toman el tono de la sección
  // en la que se está (app/globals.css); en Estudiantes/Inicio, el de antes.
  primario: "bg-accion dark:bg-seccion-claro text-white dark:text-mist-dark hover:bg-accion-hover dark:hover:opacity-90 shadow-sm",
  secundario:
    "border border-border dark:border-border-dark bg-surface dark:bg-surface-dark text-ink dark:text-ink-dark hover:bg-mist dark:hover:bg-surface-raised-dark",
};

/** Las mismas clases que usa <Boton>, para cuando la acción es en realidad
 * un <Link> de navegación con apariencia de botón (ej. "Importar Excel",
 * "Ver en el padrón") — evita que ese caso reinvente el estilo aparte y se
 * desalinee del resto. */
export function claseBoton(variante: VarianteBoton = "primario", className = ""): string {
  return `${CLASES_BASE} ${CLASES_VARIANTE[variante]} ${className}`.trim();
}

type BotonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: VarianteBoton;
};

export function Boton({ variante = "primario", className = "", ...props }: BotonProps) {
  return <button className={claseBoton(variante, className)} {...props} />;
}
