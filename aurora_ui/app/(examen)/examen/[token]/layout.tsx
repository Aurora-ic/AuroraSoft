// A PROPÓSITO no importa RequireAuth ni SidebarEducativo. Esta es la
// única ruta de todo el sistema que un alumno abre sin sesión, con un
// link que expira. Que herede el layout de (educativo) por error es
// justo el bug que este grupo de rutas nuevo evita.

export default function ExamenLayout({ children }: { children: React.ReactNode }) {
  return (
    // 🆕 Siempre en modo CLARO (sesión 2026-10-30): el tema oscuro es una
    // preferencia del staff guardada en el navegador; si un psicólogo con
    // modo oscuro abre el link en su equipo, el texto heredado del <body>
    // quedaba claro sobre tarjetas blancas. El alumno ve siempre lo mismo.
    <div className="min-h-screen bg-mist text-ink [color-scheme:light] flex flex-col items-center px-4 py-10">
      <div className="w-full max-w-xl">{children}</div>
    </div>
  );
}
