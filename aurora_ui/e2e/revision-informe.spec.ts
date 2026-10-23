import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import {
  crearAlumnoConConsentimiento, crearCampanaYMatricular,
  crearPruebaConBaremo, finalizarExamenCompleto, autenticarEnNavegador,
} from "./helpers";

test.describe("Revisar y liberar un informe retenido", () => {
  test("un informe retenido por alerta se libera desde la ficha del alumno", async ({ page }) => {
    const fixtures = leerFixtures();

    const ctx = await request.newContext();
    const token = fixtures.psicologoToken;

    // Prueba propia de este spec, con un baremo QUE SÍ ALERTA en todo el
    // rango -- a diferencia de los fixtures base (que siempre liberan
    // solos), esto deja la inscripción retenida al finalizar, que es
    // exactamente lo que hace falta para probar "liberar informe".
    const pruebaAlerta = await crearPruebaConBaremo(ctx, token, `ZZPLAYWRIGHT-ALERTA-${fixtures.sello}`, true);

    const nombreAlumno = `RevisionInforme ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    const tokenExamen = await crearCampanaYMatricular(
      ctx, token, fixtures.institucionId, pruebaAlerta.pruebaId, `ZZPLAYWRIGHT Campaña Alerta ${fixtures.sello}`, personaId,
    );
    await finalizarExamenCompleto(ctx, tokenExamen, pruebaAlerta.preguntaIds, pruebaAlerta.opcionCorrectaIds);
    await ctx.dispose();

    // Login en sí NO es lo que este spec prueba -- sesión inyectada
    // directamente, mismo motivo que campana-matricula.spec.ts.
    await autenticarEnNavegador(page, fixtures.psicologoToken);
    await page.goto("/estudiantes");
    await page.waitForLoadState("networkidle");
    await page.getByText(new RegExp(nombreAlumno)).click();
    await expect(page.getByRole("heading", { name: "Pruebas aplicadas" })).toBeVisible();

    // El informe nace RETENIDO (el baremo de este spec alerta siempre).
    await expect(page.getByText("Retenido")).toBeVisible();

    await page.getByRole("button", { name: "Revisar informe" }).click();
    await page.getByLabel("Informe liberado al alumno").check();
    await page.getByRole("button", { name: "Guardar revisión" }).click();

    await expect(page.getByText("Liberado")).toBeVisible();
    await expect(page.getByText("Retenido")).not.toBeVisible();
  });
});
