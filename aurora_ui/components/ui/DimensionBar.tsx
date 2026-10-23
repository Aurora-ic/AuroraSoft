type DimensionBarProps = {
  nombre: string;
  puntajeDirecto: number;
  minimo: number;
  maximo: number;
  nivel: string;
  // Autoritativo — nunca se infiere del texto de `nivel` (ver
  // docs/motor-scoring.md, "never infer risk from the text of nivel, which
  // is free text a psychologist can spell however they want": un tramo de
  // alerta real puede llamarse "Sin indicadores aparentes"). `undefined`
  // cuando el backend no lo manda (ej. snapshot viejo) se trata como "no
  // es alerta" — color neutro, nunca un falso ámbar.
  esAlerta?: boolean;
};

/** El elemento visual de referencia del portal: el rango real del
 * baremo (mínimo–máximo) con un marcador mostrando dónde cae el
 * puntaje del alumno. Pensado para listas/tablas con varios alumnos o
 * varias dimensiones, donde un color + posición se escanea más rápido
 * que leer cada puntaje en texto. */
export function DimensionBar({ nombre, puntajeDirecto, minimo, maximo, nivel, esAlerta }: DimensionBarProps) {
  const rango = Math.max(maximo - minimo, 1);
  const posicion = Math.min(Math.max(((puntajeDirecto - minimo) / rango) * 100, 0), 100);
  const color = esAlerta ? "bg-amber" : "bg-teal-600";

  return (
    <div className="w-full">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-sm text-ink">{nombre}</span>
        <span className="text-xs font-mono text-ink/60">{puntajeDirecto} / {maximo}</span>
      </div>
      <div className="relative h-2 rounded-full bg-border">
        <div className={`absolute -top-1 h-4 w-1 rounded-full ${color}`} style={{ left: `calc(${posicion}% - 2px)` }} title={`${nivel} — ${puntajeDirecto}`} />
      </div>
      <span className="text-xs font-mono text-ink/50 capitalize">{nivel}</span>
    </div>
  );
}
