import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { crearAlumnoConConsentimiento, autenticarEnNavegador } from "./helpers";

test.describe("Crear campaña y matricular", () => {
  test("crea una campaña nueva, matricula un alumno del padrón y genera su link", async ({ page }) => {
    const fixtures = leerFixtures();

    // El alumno ya debe existir en el padrón ANTES de este flujo -- crearlo
    // es su propio flujo (estudiantes/nuevo), no lo que esta prueba verifica.
    const ctx = await request.newContext();
    await crearAlumnoConConsentimiento(ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", `Alumno ${fixtures.sello}`);
    await ctx.dispose();

    // Login en sí NO es lo que este spec prueba (eso es login.spec.ts) --
    // se entra con la sesión ya inyectada para no competir por el rate
    // limit de /auth/login.
    await autenticarEnNavegador(page, fixtures.psicologoToken);
    await page.goto("/campanas/nueva");
    await page.waitForLoadState("networkidle");
    // 🆕 (sesión 2026-11-01) Flujo nuevo en una sola pantalla: prueba →
    // salones (el alumno del fixture no tiene salón) → ajuste alumno por
    // alumno → detalles; la campaña se crea recién con el botón final.
    await page.getByRole("radio", { name: new RegExp(`ZZPLAYWRIGHT-${fixtures.sello}`) }).click();
    await page.getByRole("button", { name: "Ver y ajustar la lista" }).click();
    await page.getByLabel("Buscar alumno").fill(`Alumno ${fixtures.sello}`);
    await page.getByText(new RegExp(`Alumno ${fixtures.sello}`)).click();
    const nombreCampana = `ZZPLAYWRIGHT Campaña ${fixtures.sello}`;
    await page.getByRole("button", { name: "Editar el nombre" }).click();
    await page.getByLabel("Nombre de la campaña").fill(nombreCampana);
    await page.getByRole("button", { name: "Crear campaña y generar links" }).click();

    // El link mágico se generó.
    await expect(page.getByRole("heading", { name: "¡Campaña lista!" })).toBeVisible();
    await expect(page.getByText("links generados")).toBeVisible();
    await expect(page.getByRole("button", { name: "Copiar", exact: true })).toBeVisible();

    // El dashboard de la campaña refleja al alumno recién matriculado.
    await page.getByRole("button", { name: "Ir al dashboard de la campaña" }).click();
    await expect(page.getByText(nombreCampana)).toBeVisible();
    await expect(page.getByText(new RegExp(`Alumno ${fixtures.sello}`))).toBeVisible();
  });
});
