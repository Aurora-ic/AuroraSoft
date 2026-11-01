import Link from "next/link";

// 🆕 Migas de pan para pantallas anidadas (ficha del alumno, dashboard de
// campaña, detalle de documento...) — antes la única forma de "volver
// atrás" era el botón del navegador, sin ningún rastro visual de dónde
// estás parado. El último ítem (sin `href`) es la página actual.
export type MigaItem = { label: string; href?: string };

// `sinMargen`: dentro de CLASE_CONTENEDOR_SECCION (flex + gap) el mb-4 se
// SUMARÍA al gap — en un contenedor space-y se colapsaba y no se notaba.
export function Migas({ items, sinMargen = false }: { items: MigaItem[]; sinMargen?: boolean }) {
  return (
    <nav
      className={`flex items-center gap-1.5 text-xs text-ink/50 dark:text-ink-dark/50 flex-wrap ${sinMargen ? "-mb-1" : "mb-4"}`}
      aria-label="Ruta de navegación"
    >
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
