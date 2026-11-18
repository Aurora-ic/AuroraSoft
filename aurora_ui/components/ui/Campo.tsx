// Extraído de estudiantes/[personaId]/page.tsx (fase 6 del plan de
// remodelación) — vivía declarado localmente en esa página y se habría
// reescrito a mano otra vez en la ficha de documentos. Corte-y-pega de una
// función pura, cero cambio de comportamiento.
export function Campo({
  etiqueta,
  valor,
  className = "",
}: {
  etiqueta: string;
  valor?: string | null;
  className?: string;
}) {
  return (
    <div className={className}>
      <span className="block text-xs font-medium text-ink/65 dark:text-ink-dark/55 uppercase tracking-wide">{etiqueta}</span>
      <span className="block text-ink dark:text-ink-dark mt-0.5">{valor || "—"}</span>
    </div>
  );
}
