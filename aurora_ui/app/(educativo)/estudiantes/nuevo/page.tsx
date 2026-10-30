"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/AuthContext";
import { Boton } from "@/components/ui/Boton";
import { TextoError } from "@/components/ui/TextoError";
import { CampoEditable } from "@/components/ui/CampoEditable";
import { Input } from "@/components/ui/Input";

export default function RegistrarAlumnoPage() {
  const { sesion } = useAuth();
  const router = useRouter();
  const [nombres, setNombres] = useState("");
  const [apellidos, setApellidos] = useState("");
  const [documento, setDocumento] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sesion) return;

    try {
      await apiClient.post("/admin/personas/", {
        institucion_id: sesion.institucionId,
        nombres,
        apellidos,
        documento_identidad: documento,
      });
      router.push("/estudiantes");
    } catch (err: any) {
      setError(err.message || "Error al registrar");
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/estudiantes" className="text-sm text-teal-900 dark:text-ink-dark hover:underline">
          ← Volver al padrón
        </Link>
        <h1 className="font-display text-2xl text-teal-900 dark:text-ink-dark">Registrar Nuevo Alumno</h1>
      </div>

      <TextoError className="mb-4">{error}</TextoError>

      <form onSubmit={handleSubmit} className="bg-surface dark:bg-surface-dark p-6 rounded-card border border-border dark:border-border-dark space-y-4 shadow-sm">
        <CampoEditable etiqueta="Nombres">
          <Input type="text" required value={nombres} onChange={(e) => setNombres(e.target.value)} className="w-full" />
        </CampoEditable>

        <CampoEditable etiqueta="Apellidos">
          <Input type="text" required value={apellidos} onChange={(e) => setApellidos(e.target.value)} className="w-full" />
        </CampoEditable>

        <CampoEditable etiqueta="Documento de Identidad">
          <Input type="text" required value={documento} onChange={(e) => setDocumento(e.target.value)} className="w-full" />
        </CampoEditable>

        <Boton type="submit" className="w-full">
          Guardar Alumno
        </Boton>
      </form>
    </div>
  );
}