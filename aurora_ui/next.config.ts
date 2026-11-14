import type { NextConfig } from "next";

// 🆕 (sesión 2026-11-07, M2 de la revisión de seguridad) Cabeceras de
// seguridad para todas las páginas del frontend.
//
// 🆕 (sesión 2026-11-08) La CSP es OBLIGATORIA (Content-Security-Policy): el
// navegador bloquea lo que no esté permitido. Antes iba en solo-reporte; se
// impuso después de correr TODA la suite de Playwright sobre un build de
// producción con la CSP ya obligatoria (también el visor de PDF con react-pdf
// y su worker), sin ningún bloqueo — ver docs/multi-tenancy-y-permisos.md.
//
// Vuelta atrás sin tocar código: CSP_SOLO_REPORTE=1 en el entorno del BUILD
// (Vercel → Settings → Environment Variables, y redeploy) la devuelve a
// Content-Security-Policy-Report-Only.

const esDesarrollo = process.env.NODE_ENV !== "production";
const soloReporte = process.env.CSP_SOLO_REPORTE === "1";

// Origen del backend (sin /api): la app le hace fetch().
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
  // Imágenes: también de cualquier origen https. El logo del colegio
  // (Institucion.logo_url) puede ser una URL externa que pega el propio
  // colegio, y la barra lateral y el examen la muestran tal cual; una imagen
  // no ejecuta código, lo que la CSP protege de verdad son los scripts.
  `img-src 'self' data: blob: https: ${api}`.trim(),
  "font-src 'self' data:",
  `connect-src 'self' ${api}${esDesarrollo ? " ws: wss:" : ""}`.trim(),
  "worker-src 'self' blob:",
  "object-src 'none'",
  "frame-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

// 🆕 (sesión 2026-11-14, revisión de seguridad del piloto) HTTPS obligatorio.
// Detrás de Cloudflare, http://dominio servía la app por http y el login
// mandaba la contraseña sin cifrar hasta Cloudflare. El proxy dice por dónde
// entró el cliente en X-Forwarded-Proto: si fue "http", 308 a la misma URL en
// https (el backend hace lo mismo con /api, ver core/cabeceras_seguridad.py).
// En local no hay proxy ni esa cabecera, así que `next start`/Playwright por
// http://localhost siguen igual. HSTS: desde la primera visita por https, el
// navegador ya no intenta http durante un año (lo ignora si llega por http).
const HSTS = "max-age=31536000; includeSubDomains";

const nextConfig: NextConfig = {
  // Sin "X-Powered-By: Next.js": no regala la tecnología y versión a quien escanea.
  poweredByHeader: false,
  async redirects() {
    if (esDesarrollo) return [];
    return [
      {
        source: "/:path*",
        has: [
          { type: "header", key: "x-forwarded-proto", value: "http" },
          { type: "host", value: "(?<host>[A-Za-z0-9.-]+(?::[0-9]{1,5})?)" },
        ],
        destination: "https://:host/:path*",
        permanent: true,
      },
    ];
  },
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
          { key: soloReporte ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy", value: csp },
          ...(esDesarrollo ? [] : [{ key: "Strict-Transport-Security", value: HSTS }]),
        ],
      },
    ];
  },
};

export default nextConfig;
