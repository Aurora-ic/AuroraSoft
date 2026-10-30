import { RequireAuth } from "@/contexts/AuthContext";
import { ShellMaster } from "@/components/superadmin/ShellMaster";

export default function MasterLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth rolesPermitidos={["superadmin"]}>
      <ShellMaster>{children}</ShellMaster>
    </RequireAuth>
  );
}
