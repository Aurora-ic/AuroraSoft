import { RequireAuth } from "@/contexts/AuthContext";
import { ShellMaster } from "@/components/superadmin/ShellMaster";
import { BloqueoInactividad } from "@/components/auth/BloqueoInactividad";

export default function MasterLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth rolesPermitidos={["superadmin"]}>
      <BloqueoInactividad>
        <ShellMaster>{children}</ShellMaster>
      </BloqueoInactividad>
    </RequireAuth>
  );
}
