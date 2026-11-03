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
  const [tema, setTema] = useState<Tema>("claro");

  useEffect(() => {
    const guardado = localStorage.getItem(CLAVE_STORAGE);
    // localStorage no existe en el servidor (no puede ir en el valor inicial
    // de useState) y esto NO se puede diferir con setTimeout: el efecto de
    // abajo escribiría "claro" antes de leer la preferencia y la perdería.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (guardado === "oscuro" || guardado === "claro") setTema(guardado);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-tema", tema);
    localStorage.setItem(CLAVE_STORAGE, tema);
  }, [tema]);

  function alternarTema() {
    setTema((actual) => (actual === "claro" ? "oscuro" : "claro"));
  }

  return <ThemeContext.Provider value={{ tema, alternarTema }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
