"use client";

import { createContext, useContext, useEffect, useState } from "react";

// 🆕 Modo oscuro/claro explícito (sesión 2026-10-25, rediseño UI/UX a
// pedido del usuario) — por decisión del usuario, no del sistema
// operativo: persiste en localStorage y se aplica como `data-tema` en
// <html>, que es lo que `@custom-variant dark` (app/globals.css) usa para
// que cualquier `dark:` de Tailwind responda al toggle. Mismo patrón que
// AuthContext: Provider + hook, estado leído una vez al montar.
//
// Sin wrapper anti-flash en el <head> a propósito — es una herramienta
// interna para un puñado de usuarios por colegio, no un sitio público de
// alto tráfico; un parpadeo de medio segundo al cargar no justifica la
// complejidad de un script inline bloqueante antes de la hidratación.
type Tema = "claro" | "oscuro";

type ThemeContextValue = {
  tema: Tema;
  alternarTema: () => void;
};

const ThemeContext = createContext<ThemeContextValue>({
  tema: "claro",
  alternarTema: () => {},
});

const CLAVE_STORAGE = "aurora_tema";

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // 🔧 (2026-11-17, plan de UX fase 4) `null` = todavía sin leer la
  // preferencia. Antes el estado arrancaba en "claro" y el efecto que lo
  // aplicaba lo GUARDABA en localStorage en el mismo ciclo en que otro efecto
  // lo leía: en desarrollo (efectos dobles) la preferencia oscura se perdía,
  // y en producción quien usa modo oscuro veía un destello claro en cada
  // carga. Ahora: el <script> de app/layout.tsx pone `data-tema` antes del
  // primer pintado, aquí solo se lee, y localStorage se escribe únicamente
  // cuando la persona cambia el tema.
  const [tema, setTema] = useState<Tema | null>(null);

  useEffect(() => {
    let guardado: string | null = null;
    try {
      guardado = localStorage.getItem(CLAVE_STORAGE);
    } catch {
      // Sin almacenamiento (modo privado): claro.
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTema(guardado === "oscuro" ? "oscuro" : "claro");
  }, []);

  useEffect(() => {
    if (tema) document.documentElement.setAttribute("data-tema", tema);
  }, [tema]);

  function alternarTema() {
    const siguiente: Tema = (tema ?? "claro") === "claro" ? "oscuro" : "claro";
    setTema(siguiente);
    try {
      localStorage.setItem(CLAVE_STORAGE, siguiente);
    } catch {
      // Sin almacenamiento: dura esta visita.
    }
  }

  return <ThemeContext.Provider value={{ tema: tema ?? "claro", alternarTema }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
