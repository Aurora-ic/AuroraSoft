import Link from "next/link";

// 🆕 Migas de pan para pantallas anidadas (ficha del alumno, dashboard de
// campaña, detalle de documento...) — antes la única forma de "volver
// atrás" era el botón del navegador, sin ningún rastro visual de dónde
// estás parado. El último ítem (sin `href`) es la página actual.
export type MigaItem = { label: string; href?: string };

export function Migas({ items }: { items: MigaItem[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-xs text-ink/50 dark:text-ink-dark/50 mb-4 flex-wrap" aria-label="Ruta de navegación">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <span className="text-ink/30 dark:text-ink-dark/30">/</span>}
          {item.href ? (
            <Link href={item.href} className="hover:text-teal-700 dark:hover:text-teal-accent-dark hover:underline">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink/70 dark:text-ink-dark/70 font-medium truncate max-w-xs">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
