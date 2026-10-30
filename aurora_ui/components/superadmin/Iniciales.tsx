// Avatar cuadrado con las iniciales de una institución — identifica cada
// fila del panel interno sin depender de que el colegio haya subido logo.
export function Iniciales({ nombre, grande = false }: { nombre: string; grande?: boolean }) {
  const iniciales = nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-lg bg-teal-900 font-bold text-white dark:bg-teal-accent-dark/20 dark:text-teal-accent-dark ${
        grande ? "h-14 w-14 text-lg" : "h-9 w-9 text-[12px]"
      }`}
    >
      {iniciales || "?"}
    </span>
  );
}
