// A PROPÓSITO no importa RequireAuth ni SidebarEducativo. Esta es la
// única ruta de todo el sistema que un alumno abre sin sesión, con un
// link que expira. Que herede el layout de (educativo) por error es
// justo el bug que este grupo de rutas nuevo evita.

export default function ExamenLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-mist flex flex-col items-center px-4 py-10">
      <div className="w-full max-w-xl">{children}</div>
    </div>
  );
}
