import type { Metadata } from "next";
import "./globals.css"; // Solo un punto, porque este layout está al mismo nivel que globals.css
import { AuthProvider } from "@/contexts/AuthContext";
import { QueryProvider } from "@/contexts/QueryProvider";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { ProveedorConfirmacion } from "@/components/ui/DialogoConfirmacion";

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
    <html lang="es">
      <body>
        {/* 🆕 Fase 5 — QueryProvider por fuera de AuthProvider: no depende
            de la sesión, así que una pantalla nueva puede usar React Query
            para datos públicos (p.ej. el examen por token) sin necesitar
            auth. */}
        <ThemeProvider>
          <QueryProvider>
            <AuthProvider>
              {/* 🆕 Diálogo de confirmación propio (reemplaza window.confirm). */}
              <ProveedorConfirmacion>{children}</ProveedorConfirmacion>
            </AuthProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}