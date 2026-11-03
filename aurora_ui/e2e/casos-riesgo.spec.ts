import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import {
  autenticarEnNavegador, crearAlumnoConConsentimiento, crearCampanaYMatricular,
  crearPruebaConBaremo, finalizarExamenCompleto,
} from "./helpers";

// 🆕 (sesión 2026-11-02) Bandeja de casos en riesgo (sesión 2026-11-01):
// una evaluación en alerta crea su caso, se cambia de estado en el lugar y
// solo sale de la bandeja al cerrarla con motivo. De paso cubre el
// interruptor de resultados APAGADO (lo normal): el alumno ve el
// agradecimiento, nunca su resultado ni el PDF.
test.describe("Casos en riesgo", () => {
  test("una alerta crea el caso, cambia de estado y sale de la bandeja al cerrarlo", async ({ page }) => {
    const fixtures = leerFixtures();
    const ctx = await request.newContext();
    const token = fixtures.psicologoToken;
    const prueba = await crearPruebaConBaremo(ctx, token, `ZZPLAYWRIGHT-CASO-${fixtures.sello}`, true);
    const apellidos = `CasoRiesgo ${fixtures.sello}`;
    const nombreCompleto = `ZZPLAYWRIGHT ${apellidos}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", apellidos);
    const tokenExamen = await crearCampanaYMatricular(
      ctx, token, fixtures.institucionId, prueba.pruebaId, `ZZPLAYWRIGHT Campaña Caso ${fixtures.sello}`, personaId,
    );
    await finalizarExamenCompleto(ctx, tokenExamen, prueba.preguntaIds, prueba.opcionCorrectaIds);
    await ctx.dispose();

    // Interruptor apagado (por defecto): el alumno solo ve el agradecimiento.
    await page.goto(`/examen/${tokenExamen}`);
    await expect(page.getByRole("heading", { name: "Evaluación finalizada" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Tus resultados" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Descargar mi informe (PDF)" })).toHaveCount(0);

    await autenticarEnNavegador(page, token);
    await page.goto("/casos-riesgo");
    await page.getByLabel("Buscar alumno").fill(apellidos);
    const tarjeta = page.locator("article").filter({ hasText: nombreCompleto });
    await expect(tarjeta).toHaveCount(1);
    await expect(tarjeta.getByText("Alerta", { exact: true })).toBeVisible();

    // Estado en el lugar: Nuevo → En atención.
    const estado = page.getByLabel(`Estado del caso de ${nombreCompleto}`);
    await expect(estado).toHaveValue("nuevo");
    const cambio = page.waitForResponse((r) => r.request().method() === "PATCH" && /\/casos-riesgo\/\d+$/.test(r.url()));
    await estado.selectOption("en_atencion");
    expect((await cambio).status()).toBe(200);
    await expect(estado).toHaveValue("en_atencion");

    // Cerrar exige motivo; al cerrarlo sale de la bandeja de abiertos.
    await estado.selectOption("cerrado");
    const cerrar = tarjeta.getByRole("button", { name: "Cerrar caso" });
    await expect(cerrar).toBeDisabled();
    await tarjeta.getByLabel("Motivo del cierre").fill("Síntomas remitidos tras la intervención (Playwright).");
    await cerrar.click();
    await expect(page.locator("article").filter({ hasText: nombreCompleto })).toHaveCount(0);

    // …y aparece al filtrar por "Cerrado", con su motivo.
    await page.getByLabel("Filtrar por estado").selectOption("cerrado");
    const cerrada = page.locator("article").filter({ hasText: nombreCompleto });
    await expect(cerrada.getByText(/Síntomas remitidos tras la intervención/)).toBeVisible();
  });
});
