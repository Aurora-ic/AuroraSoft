import type { ReactNode } from "react";

// Extrae el patrón "<label><span etiqueta/><Input/Select/Textarea/></label>"
// que ya se repetía a mano (Datos generales, Contacto familiar) en
// estudiantes/[personaId]/page.tsx — mismas clases, cero cambio visual.
// `children` es el control real (Input/Select/Textarea), nunca HTML crudo,
// para que la validación/estilo del control siga viviendo en un solo sitio.
export function CampoEditable({
  etiqueta,
  children,
  className = "",
}: {
  etiqueta: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex flex-col gap-1 ${className}`}>
      <span className="text-ink/70 dark:text-ink-dark/70 font-medium">{etiqueta}</span>
      {children}
    </label>
  );
}
