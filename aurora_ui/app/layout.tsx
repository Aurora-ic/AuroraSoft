import type { Metadata } from "next";
import "./globals.css"; // Solo un punto, porque este layout está al mismo nivel que globals.css
import { AuthProvider } from "@/contexts/AuthContext";
import { QueryProvider } from "@/contexts/QueryProvider";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ProveedorConfirmacion } from "@/components/ui/DialogoConfirmacion";
import { ProveedorAvisos } from "@/components/ui/Avisos";

export const metadata: Metadata = {
  title: "AuroraSoft",
  description: "Panel de Control Psicométrico",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: el script de abajo pone data-tema antes de
    // que React hidrate, a propósito.
    <html lang="es" suppressHydrationWarning>
      <head>
        {/* 🆕 (2026-11-17) Tema oscuro aplicado ANTES del primer pintado (sin
            destello claro). La CSP ya permite scripts en línea
            ('unsafe-inline', next.config.ts). Ver contexts/ThemeContext.tsx. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "try{if(localStorage.getItem('aurora_tema')==='oscuro')document.documentElement.setAttribute('data-tema','oscuro')}catch(e){}",
          }}
        />
      </head>
      <body>
        {/* 🆕 Fase 5 — QueryProvider por fuera de AuthProvider: no depende
            de la sesión, así que una pantalla nueva puede usar React Query
            para datos públicos (p.ej. el examen por token) sin necesitar
            auth. */}
        <ThemeProvider>
          <QueryProvider>
            <AuthProvider>
              {/* 🆕 Diálogo de confirmación propio (reemplaza window.confirm). */}
              <ProveedorConfirmacion>
                {/* 🆕 (2026-11-17) Avisos de "listo" (components/ui/Avisos.tsx). */}
                <ProveedorAvisos>{children}</ProveedorAvisos>
              </ProveedorConfirmacion>
            </AuthProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}