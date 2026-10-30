// Rojo estándar de Tailwind — deliberadamente NO el ámbar de marca, que
// queda reservado en exclusiva para alertas de riesgo clínico real. Un
// error de red, de validación o de formulario nunca es eso.
export function TextoError({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  if (!children) return null;
  return <p className={`text-sm text-red-700 dark:text-red-300 ${className}`.trim()}>{children}</p>;
}
