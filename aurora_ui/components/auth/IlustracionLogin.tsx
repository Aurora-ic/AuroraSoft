// Ilustración del panel lateral del login. Minimalista a propósito: el
// estudiante al centro y, en una órbita suave, tres nodos que resumen lo que
// AuroraSoft acompaña alrededor de él — su expediente, su seguimiento en el
// tiempo y su bienestar — sin reducir la plataforma a "evaluar". Los arcos de
// fondo evocan una aurora. SVG en línea: escala nítido, no pesa como una
// imagen y usa la misma paleta de marca que el resto de la app.
export function IlustracionLogin({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 400 320"
      fill="none"
      role="img"
      aria-label="Ilustración: un estudiante al centro, acompañado por su expediente, su seguimiento y su bienestar"
      className={className}
    >
      <defs>
        <linearGradient id="il-aurora" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5EE0C6" stopOpacity="0" />
          <stop offset="0.5" stopColor="#5EE0C6" stopOpacity="0.55" />
          <stop offset="1" stopColor="#5EE0C6" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="il-centro" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5EE0C6" />
          <stop offset="1" stopColor="#12796B" />
        </linearGradient>
      </defs>

      {/* Arcos de aurora */}
      <path d="M30 150 Q200 40 370 150" stroke="url(#il-aurora)" strokeWidth="2" strokeLinecap="round" />
      <path d="M60 175 Q200 85 340 175" stroke="url(#il-aurora)" strokeWidth="1.5" strokeLinecap="round" opacity="0.6" />

      {/* Órbita */}
      <circle cx="200" cy="190" r="104" stroke="#FFFFFF" strokeOpacity="0.16" strokeWidth="1.5" strokeDasharray="2 7" strokeLinecap="round" />

      {/* Estudiante al centro */}
      <circle cx="200" cy="190" r="50" fill="#FFFFFF" fillOpacity="0.06" />
      <circle cx="200" cy="190" r="36" fill="url(#il-centro)" />
      <circle cx="200" cy="180" r="9" fill="#FFFFFF" />
      <path d="M184 206a16 13 0 0 1 32 0" fill="#FFFFFF" />

      {/* Nodo: expediente */}
      <g>
        <circle cx="110" cy="138" r="24" fill="#FFFFFF" fillOpacity="0.95" />
        <path d="M100 131h8l3 3h9v14h-20z" stroke="#12796B" strokeWidth="2.2" strokeLinejoin="round" />
      </g>

      {/* Nodo: seguimiento */}
      <g>
        <circle cx="290" cy="138" r="24" fill="#FFFFFF" fillOpacity="0.95" />
        <path d="M279 147l7-7 5 5 10-11" stroke="#12796B" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </g>

      {/* Nodo: bienestar */}
      <g>
        <circle cx="200" cy="294" r="20" fill="#FFFFFF" fillOpacity="0.95" />
        <path
          d="M200 302s-9-5.5-9-11.5a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-9 11.5-9 11.5z"
          fill="#2FB49D"
        />
      </g>

      {/* Destellos */}
      <circle cx="320" cy="66" r="3" fill="#5EE0C6" fillOpacity="0.7" />
      <circle cx="74" cy="236" r="2.5" fill="#FFFFFF" fillOpacity="0.4" />
      <circle cx="338" cy="248" r="2" fill="#FFFFFF" fillOpacity="0.35" />
    </svg>
  );
}
