import { RequireAuth } from "@/contexts/AuthContext";

export default function MasterLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth rolesPermitidos={["superadmin"]}>
      <div className="min-h-screen bg-mist">
        <header className="border-b border-border bg-white px-8 py-4">
          <span className="font-display text-lg text-teal-900">AuroraSoft — Panel interno</span>
        </header>
        <main className="p-8">{children}</main>
      </div>
    </RequireAuth>
  );
}
