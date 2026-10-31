// Ilustración del panel lateral del login: un informe con gráfico de
// dimensiones, el grupo evaluado y el escudo de revisión profesional — las
// tres ideas del producto (evaluar, interpretar, cuidar). SVG en línea a
// propósito: escala nítido en cualquier pantalla, no pesa como una imagen y
// usa la misma paleta de marca que el resto de la app.
export function IlustracionLogin({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 420 320" fill="none" role="img" aria-label="Ilustración: informe psicométrico con gráficos y revisión profesional" className={className}>
      <defs>
        <linearGradient id="il-barra" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5EE0C6" />
          <stop offset="1" stopColor="#2FB49D" />
        </linearGradient>
        <linearGradient id="il-escudo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5EE0C6" />
          <stop offset="1" stopColor="#12796B" />
        </linearGradient>
      </defs>

      {/* Hoja de informe, detrás */}
      <g transform="rotate(-7 120 170)">
        <rect x="40" y="70" width="170" height="210" rx="14" fill="#FFFFFF" fillOpacity="0.08" stroke="#FFFFFF" strokeOpacity="0.18" />
        <rect x="60" y="94" width="80" height="8" rx="4" fill="#FFFFFF" fillOpacity="0.35" />
        {[120, 136, 152, 168, 184, 200, 216].map((y, i) => (
          <rect key={y} x="60" y={y} width={i % 3 === 2 ? 90 : 130} height="5" rx="2.5" fill="#FFFFFF" fillOpacity="0.16" />
        ))}
        <rect x="60" y="238" width="60" height="22" rx="6" fill="#FFFFFF" fillOpacity="0.12" />
      </g>

      {/* Tarjeta principal: resultados por dimensión */}
      <g>
        <rect x="120" y="40" width="250" height="190" rx="18" fill="#FFFFFF" fillOpacity="0.96" />
        <rect x="142" y="62" width="96" height="9" rx="4.5" fill="#0B3D34" fillOpacity="0.85" />
        <rect x="142" y="78" width="60" height="6" rx="3" fill="#0B3D34" fillOpacity="0.25" />
        <circle cx="338" cy="72" r="12" fill="#E6F4F1" />
        <path d="M332 72.5l4 4 7.5-8" stroke="#12796B" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />

        {/* eje */}
        <line x1="146" y1="200" x2="346" y2="200" stroke="#0B3D34" strokeOpacity="0.12" strokeWidth="2" />
        {[
          { x: 156, h: 62 },
          { x: 192, h: 92 },
          { x: 228, h: 48 },
          { x: 264, h: 104 },
          { x: 300, h: 74 },
        ].map((b) => (
          <rect key={b.x} x={b.x} y={200 - b.h} width="24" height={b.h} rx="6" fill="url(#il-barra)" />
        ))}
        {/* tendencia */}
        <path d="M168 128 L204 104 L240 146 L276 92 L312 116" stroke="#0F5A4F" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        {[
          [168, 128],
          [204, 104],
          [240, 146],
          [276, 92],
          [312, 116],
        ].map(([cx, cy]) => (
          <circle key={cx} cx={cx} cy={cy} r="4" fill="#FFFFFF" stroke="#0F5A4F" strokeWidth="2.5" />
        ))}
      </g>

      {/* Grupo evaluado */}
      <g>
        <rect x="58" y="214" width="150" height="62" rx="14" fill="#FFFFFF" fillOpacity="0.96" />
        {[86, 110, 134].map((cx, i) => (
          <g key={cx}>
            <circle cx={cx} cy="245" r="15" fill={["#CDEFE8", "#D9E8F7", "#EEDCF1"][i]} stroke="#FFFFFF" strokeWidth="3" />
            <circle cx={cx} cy="240" r="5" fill={["#12796B", "#2A78D6", "#A24FB0"][i]} />
            <path d={`M${cx - 8} 254 a8 7 0 0 1 16 0`} fill={["#12796B", "#2A78D6", "#A24FB0"][i]} />
          </g>
        ))}
        <rect x="158" y="236" width="34" height="7" rx="3.5" fill="#0B3D34" fillOpacity="0.7" />
        <rect x="158" y="249" width="24" height="5" rx="2.5" fill="#0B3D34" fillOpacity="0.25" />
      </g>

      {/* Escudo: revisión profesional antes de publicar */}
      <g>
        <circle cx="352" cy="232" r="40" fill="#0B3D34" fillOpacity="0.35" />
        <path d="M352 200l26 10v20c0 17-11 29-26 35-15-6-26-18-26-35v-20l26-10z" fill="url(#il-escudo)" stroke="#FFFFFF" strokeWidth="3" strokeLinejoin="round" />
        <path d="M341 232l8 8 14-15" stroke="#FFFFFF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </g>

      {/* Destellos */}
      <circle cx="96" cy="44" r="4" fill="#5EE0C6" fillOpacity="0.7" />
      <circle cx="392" cy="140" r="3" fill="#FFFFFF" fillOpacity="0.5" />
      <circle cx="30" cy="180" r="2.5" fill="#FFFFFF" fillOpacity="0.4" />
    </svg>
  );
}
