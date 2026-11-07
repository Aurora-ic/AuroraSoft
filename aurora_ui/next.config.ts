import type { NextConfig } from "next";

// 🆕 (sesión 2026-11-07, M2 de la revisión de seguridad) Cabeceras de
// seguridad para todas las páginas del frontend.
//
// La CSP va en modo SOLO-REPORTE (Content-Security-Policy-Report-Only): el
// navegador no bloquea nada, solo avisa en la consola qué la violaría. Next
// mete scripts inline propios y react-pdf usa un worker (public/
// pdf.worker.min.mjs); antes de imponerla hay que ver en el piloto que no
// salga ningún aviso en las pantallas reales (examen, ficha, visor de PDF).
// Cuando esté limpia se cambia el nombre de la cabecera a
// Content-Security-Policy — ver docs/multi-tenancy-y-permisos.md.

const esDesarrollo = process.env.NODE_ENV !== "production";

// Origen del backend (sin /api): la app le hace fetch() y muestra sus logos.
function origenApi(): string {
  const url = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

const api = origenApi();

const csp = [
  "default-src 'self'",
  // Next inyecta scripts inline; en desarrollo además usa eval (recarga en caliente).
  `script-src 'self' 'unsafe-inline'${esDesarrollo ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${api}`.trim(),
  "font-src 'self' data:",
  `connect-src 'self' ${api}${esDesarrollo ? " ws: wss:" : ""}`.trim(),
  "worker-src 'self' blob:",
  "object-src 'none'",
  "frame-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  // Sin "X-Powered-By: Next.js": no regala la tecnología y versión a quien escanea.
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Nadie puede meter AuroraSoft dentro de un iframe (clickjacking).
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // La app no usa cámara, micrófono ni ubicación.
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
          { key: "Content-Security-Policy-Report-Only", value: csp },
        ],
      },
    ];
  },
};

export default nextConfig;
