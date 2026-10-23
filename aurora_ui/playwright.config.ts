import { defineConfig, devices } from "@playwright/test";

// e2e de los flujos críticos del frontend — primera suite de tests que
// tiene aurora_ui (antes todo se verificaba con tsc/eslint/build + pruebas
// manuales contra un backend real, nunca una prueba automatizada de UI).
// Mismo criterio que el backend (ver CLAUDE.md): casi todo e2e contra un
// servidor real, nada de mocks — necesita `uvicorn main:app --port 8010`
// (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos) y `npm run dev` corriendo
// antes de `npm run test:e2e`.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false, // los tests comparten el mismo backend/BD -- evita carreras entre ellos
  // 🔒 fullyParallel:false por sí solo NO alcanza -- Playwright sigue
  // corriendo archivos DISTINTOS en paralelo entre sí (workers > 1), y como
  // todos los specs comparten la misma institución/padrón de los fixtures
  // (ver global-setup.ts), eso produce colisiones reales (ej. dos alumnos
  // con "Alumno {sello}" en el nombre, visibles al mismo tiempo en el
  // padrón, rompiendo un locator que esperaba uno solo).
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    // 🔒 "localhost", nunca "127.0.0.1" -- `next dev` (Next.js 16) bloquea
    // por defecto los recursos de dev (webpack-hmr, el bundle de cliente)
    // para cualquier origen que no sea "localhost" (ver `allowedDevOrigins`
    // en next.config.js). Con 127.0.0.1 la página carga pero NUNCA
    // hidrata -- cualquier click dispara el submit nativo del <form> en
    // vez del handler de React, que es justo el síntoma que esto evitó.
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
