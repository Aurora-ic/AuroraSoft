import { RequireAuth } from "@/contexts/AuthContext";
import { SidebarEducativo } from "@/components/educativo/Sidebar";
import { Topbar } from "@/components/educativo/Topbar";

// Este es el layout que Next.js realmente resuelve para /estudiantes,
// /campanas, /pruebas, /agenda y /casos-riesgo — el nombre entre paréntesis
// (educativo) es un route group, no aparece en la URL. Antes vivía vacío
// (passthrough) mientras app/educativo/layout.tsx (un segmento LITERAL, que
// ninguna página usa) tenía el guard y el sidebar de verdad, así que nunca
// se ejecutaban. Ver CLAUDE.md, "Known rough edges".
//
// 🆕 Bug real cerrado (hallazgo de QA manual, sesión 2026-10-19): "colegio"
// nunca estuvo en `rolesPermitidos`, así que CUALQUIER cuenta con ese rol
// se autenticaba bien (el backend lo acepta sin problema) pero quedaba
// expulsada al instante por este mismo guard apenas aterrizaba en
// /estudiantes — RequireAuth llama a cerrarSesion() cuando el rol no está
// en la lista, lo que se ve exactamente como "no puedo entrar". El backend
// sí está diseñado para que `colegio` entre con contenido redactado (ver
// redactar_resultados_dashboard_campana/nivel_visibilidad en
// docs/motor-documentos.md y docs/multi-tenancy-y-permisos.md) — el rol
// nunca debió haber quedado afuera de esta lista.
export default function EducativoLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth rolesPermitidos={["psicologo", "admin", "colegio"]}>
      <div className="flex h-screen bg-mist dark:bg-mist-dark">
        <SidebarEducativo />
        {/* 🆕 Topbar (sesión 2026-10-25) — persiste entre pantallas, por
            fuera del scroll del contenido (solo <main> scrollea). */}
        <div className="flex-1 min-w-0 flex flex-col h-screen">
          <Topbar />
          <main className="flex-1 overflow-y-auto p-8">{children}</main>
        </div>
      </div>
    </RequireAuth>
  );
}
