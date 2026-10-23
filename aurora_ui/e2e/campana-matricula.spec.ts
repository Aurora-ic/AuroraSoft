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
    // Sin nombre_corto cargado, el <option> muestra nombre_tecnico tal cual.
    await page.getByLabel("Prueba").selectOption({ label: `ZZPLAYWRIGHT-${fixtures.sello}` });
    const nombreCampana = `ZZPLAYWRIGHT Campaña ${fixtures.sello}`;
    await page.getByLabel("Nombre del grupo").fill(nombreCampana);
    await page.getByRole("button", { name: "Crear campaña" }).click();

    // Paso 2: elegir a quién matricular -- busca al alumno recién creado en
    // la lista del padrón y lo marca.
    await expect(page.getByText(nombreCampana)).toBeVisible();
    await page.getByText(new RegExp(`Alumno ${fixtures.sello}`)).click();
    await page.getByRole("button", { name: /Matricular 1 alumno/ }).click();

    // Paso 3: el link mágico se generó.
    await expect(page.getByText(/1 link\(s\) generado\(s\)/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Copiar link" })).toBeVisible();

    // El dashboard de la campaña refleja al alumno recién matriculado.
    await page.getByRole("button", { name: "Ir al dashboard de la campaña" }).click();
    await expect(page.getByText(nombreCampana)).toBeVisible();
    await expect(page.getByText(new RegExp(`Alumno ${fixtures.sello}`))).toBeVisible();
  });
});
