import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { crearAlumnoConConsentimiento, autenticarEnNavegador } from "./helpers";

// 🆕 Cubre "Datos de filiación del estudiante" en la ficha del alumno —
// datos familiares y antecedentes clínicos externos (PersonaDatosFamiliares/
// PersonaAntecedentesClinicos), listado en docs/frontend.md/docs/gaps-
// pendientes.md como verificado solo contra un backend real vía llamadas
// HTTP simuladas, sin click-through real en un navegador. Identidad y
// Contactos familiares quedan fuera a propósito -- son el mismo patrón de
// formulario ya cubierto en espíritu por este mismo spec, y el objetivo acá
// es cerrar el hueco real (los dos sub-bloques que nunca tuvieron NINGUNA
// verificación, ni manual ni automatizada, más allá de "compila").
test.describe("Datos de filiación del estudiante", () => {
  test("edita datos familiares y antecedentes clínicos externos desde la ficha", async ({ page }) => {
    const fixtures = leerFixtures();
    const token = fixtures.psicologoToken;

    const ctx = await request.newContext();
    const nombreAlumno = `Filiacion ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    await ctx.dispose();

    await autenticarEnNavegador(page, token);
    await page.goto(`/estudiantes/${personaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: nombreAlumno })).toBeVisible();

    // --- Datos familiares --- "Editar" es ambiguo en la página (Identidad/
    // Datos familiares/Antecedentes tienen los tres un botón "Editar"), así
    // que se ubica por el <h3> hermano dentro de la misma fila flex.
    const filaDatosFamiliares = page.getByRole("heading", { name: "Datos familiares", level: 3 }).locator("..");
    await filaDatosFamiliares.getByRole("button", { name: "Editar" }).click();

    await page.getByLabel("Número de hermanos").fill("2");
    await page.getByLabel("Vive con").fill("Ambos padres");
    await page.getByLabel("Lugar de nacimiento").fill("Lima");
    await page.getByLabel("Lugar de procedencia").fill("Arequipa");
    // Único formulario abierto en este momento -- "Guardar cambios" no es
    // ambiguo todavía (Identidad/Antecedentes no están en edición).
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("Ambos padres")).toBeVisible();
    await expect(page.getByText("Arequipa")).toBeVisible();

    // --- Antecedentes clínicos externos ---
    const filaAntecedentes = page.getByRole("heading", { name: "Antecedentes clínicos externos", level: 3 }).locator("..");
    await filaAntecedentes.getByRole("button", { name: "Editar" }).click();

    await page.getByLabel("Recibe terapia psicológica externa").selectOption("true");
    // "Detalle" se repite (terapia psicológica / atención psiquiátrica) --
    // mismo orden fijo del formulario, ver page.tsx.
    await page.getByLabel("Detalle").first().fill("Terapia semanal por ansiedad");
    await page.getByLabel("Recibe atención psiquiátrica externa").selectOption("false");
    await page.getByLabel("Diagnóstico reportado").fill("Trastorno de ansiedad generalizada (reportado por la familia)");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText("Terapia semanal por ansiedad")).toBeVisible();
    await expect(page.getByText("Trastorno de ansiedad generalizada (reportado por la familia)")).toBeVisible();
  });
});
