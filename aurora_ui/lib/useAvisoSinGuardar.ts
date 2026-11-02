"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useConfirmar } from "@/components/ui/DialogoConfirmacion";

// 🆕 (sesión 2026-11-01, punto 5 del análisis de UI/UX) Aviso al salir con
// cambios sin guardar. Antes un informe redactado durante 20 minutos se
// perdía con un clic en el menú. Cubre:
// - cerrar o recargar la pestaña (aviso nativo del navegador, el único
//   permitido ahí);
// - cualquier enlace interno (menú, migas, "Ver ficha"…): se intercepta el
//   clic en fase de captura, ANTES de que lo vea el <Link> de Next, y se
//   pregunta con el diálogo propio; si se confirma, se navega igual.
// No cubre el botón "Atrás" del navegador (Next no ofrece cómo bloquearlo).
export function useAvisoSinGuardar(hayCambios: boolean, mensaje = "Los cambios que no guardaste se perderán.") {
  const confirmar = useConfirmar();
  const router = useRouter();

  useEffect(() => {
    if (!hayCambios) return;

    function antesDeSalir(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }

    function alHacerClic(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const enlace = (e.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!enlace || enlace.target === "_blank" || enlace.hasAttribute("download")) return;
      const destino = new URL(enlace.href, window.location.href);
      if (destino.origin !== window.location.origin) return;
      if (destino.pathname === window.location.pathname && destino.search === window.location.search) return;
      e.preventDefault();
      e.stopPropagation();
      confirmar({
        titulo: "¿Salir sin guardar?",
        mensaje,
        textoConfirmar: "Salir sin guardar",
        textoCancelar: "Seguir editando",
        peligro: true,
      }).then((salir) => {
        if (salir) router.push(destino.pathname + destino.search + destino.hash);
      });
    }

    window.addEventListener("beforeunload", antesDeSalir);
    document.addEventListener("click", alHacerClic, true);
    return () => {
      window.removeEventListener("beforeunload", antesDeSalir);
      document.removeEventListener("click", alHacerClic, true);
    };
  }, [hayCambios, mensaje, confirmar, router]);
}
