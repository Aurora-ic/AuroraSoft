import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { autenticarEnNavegador, crearAlumnoConConsentimiento, finalizarExamenCompleto } from "./helpers";

// 🆕 (sesión 2026-11-02) Aplicación individual desde el perfil (sesión
// 2026-11-01): el modal dice si el estudiante puede rendir la prueba, crea
// la campaña de un solo inscrito y da el enlace. Cubre también:
//   · la regla de reaplicación: con la prueba PENDIENTE ya no puede
//     rendirla otra vez;
//   · el interruptor de resultados ENCENDIDO: al terminar, el alumno ve su
//     resultado y el botón del PDF.
test.describe("Aplicación individual", () => {
  test("aplica una prueba desde el perfil, bloquea la reaplicación y muestra el resultado al alumno", async ({ page }) => {
    const fixtures = leerFixtures();
    const ctx = await request.newContext();
    const apellidos = `Individual ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", apellidos);

    await autenticarEnNavegador(page, fixtures.psicologoToken);
    await page.goto(`/estudiantes/${personaId}`);
    await expect(page.getByRole("heading", { name: "Pruebas aplicadas" })).toBeVisible();

    const dialogo = page.getByRole("dialog");
    await page.getByRole("button", { name: "Aplicar prueba" }).click();
    await dialogo.getByRole("radio", { name: new RegExp(`ZZPLAYWRIGHT-${fixtures.sello}`) }).click();
    await expect(dialogo.getByText(/Puede rendirla/)).toBeVisible();
    await dialogo.getByText("Ve su resultado al terminar").click();
    await dialogo.getByRole("button", { name: "Aplicar y generar enlace" }).click();

    const abrir = dialogo.getByRole("link", { name: "Abrir el examen en este equipo" });
    await expect(abrir).toBeVisible();
    const tokenExamen = (await abrir.getAttribute("href"))!.split("/examen/")[1];
    expect(tokenExamen).toBeTruthy();
    await dialogo.getByRole("button", { name: "Cerrar" }).click();

    // Con la prueba pendiente, no puede rendirla otra vez.
    await page.getByRole("button", { name: "Aplicar prueba" }).click();
    await dialogo.getByRole("radio", { name: new RegExp(`ZZPLAYWRIGHT-${fixtures.sello}`) }).click();
    await expect(dialogo.getByText(/No puede rendirla ahora/)).toBeVisible();
    await expect(dialogo.getByRole("button", { name: "Aplicar y generar enlace" })).toBeDisabled();
    await dialogo.getByRole("button", { name: "Cerrar" }).click();

    // El alumno termina y, con el interruptor encendido, ve su resultado.
    await finalizarExamenCompleto(ctx, tokenExamen, fixtures.preguntaIds, fixtures.opcionCorrectaIds);
    await ctx.dispose();
    await page.goto(`/examen/${tokenExamen}`);
    await expect(page.getByRole("heading", { name: "Evaluación finalizada" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tus resultados" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Descargar mi informe (PDF)" })).toBeVisible();
  });
});
