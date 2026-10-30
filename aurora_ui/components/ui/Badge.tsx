export type TonoBadge = "teal" | "teal-suave" | "neutro" | "error" | "riesgo";

const CLASES_TONO: Record<TonoBadge, string> = {
  teal: "bg-teal-600/10 text-teal-900 dark:bg-teal-accent-dark/15 dark:text-teal-accent-dark",
  "teal-suave": "bg-teal-400/20 text-teal-900 dark:bg-teal-accent-dark/10 dark:text-teal-accent-dark",
  neutro: "bg-border text-ink/60 dark:bg-border-dark dark:text-ink-dark/60",
  error: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
  // Único tono cálido del sistema — resérvalo para una alerta de riesgo
  // clínico real (es_alerta, el nivel de un baremo, un caso pendiente de
  // seguimiento), nunca para un estado común ("nuevo", "activo"...) ni para
  // llamar la atención sobre algo que en realidad no es un riesgo.
  riesgo: "bg-amber/15 text-amber",
};

export function Badge({ tono = "neutro", children }: { tono?: TonoBadge; children: React.ReactNode }) {
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${CLASES_TONO[tono]}`}>
      {children}
    </span>
  );
}
