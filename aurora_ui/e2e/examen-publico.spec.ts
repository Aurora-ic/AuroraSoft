import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { crearAlumnoConConsentimiento, crearCampanaYMatricular } from "./helpers";

test.describe("Flujo público del examen", () => {
  test("un alumno recién matriculado completa el examen de punta a punta", async ({ page }) => {
    // finalizar() pide confirmación con window.confirm(...) antes de llamar
    // a la API -- sin un handler explícito, Playwright puede descartarlo
    // (confirm() devuelve false) de forma no determinística según la
    // corrida, dejando el examen sin finalizar nunca. Se acepta siempre.
    page.on("dialog", (d) => d.accept());
    const fixtures = leerFixtures();

    // Todo lo previo al link mágico (alumno, campaña, matrícula) se arma
    // por API -- lo que esta prueba verifica es SOLO lo que pasa en
    // /examen/[token], sin sesión, con el token real generado.
    const ctx = await request.newContext();
    const personaId = await crearAlumnoConConsentimiento(
      ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", `ExamenAlumno ${fixtures.sello}`,
    );
    const tokenExamen = await crearCampanaYMatricular(
      ctx, fixtures.psicologoToken, fixtures.institucionId, fixtures.pruebaId,
      `ZZPLAYWRIGHT Campaña Examen ${fixtures.sello}`, personaId,
    );
    await ctx.dispose();

    await page.goto(`/examen/${tokenExamen}`);
    await page.waitForLoadState("networkidle");

    // "Antes de comenzar" -- nombre ya viene conocido del padrón (solo
    // <p>, no <input>), edad/sexo/nivel sí se preguntan.
    await page.getByLabel("Edad").fill("15");
    const sexo = page.getByLabel("Sexo");
    if (await sexo.count()) await sexo.selectOption("Femenino");
    const nivel = page.getByLabel("Nivel");
    if (await nivel.count()) await nivel.selectOption("Secundaria");
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Comenzar" }).click();

    // La prueba de fixtures no tiene campos sociodemográficos propios --
    // pasa directo a "preguntas". Responde cada ítem con "Sí" (índice 1,
    // misma opción que el baremo "Bajo" sin alerta cubre entero).
    await expect(page.getByRole("heading", { name: "Evaluación", exact: true })).toBeVisible();

    // 🆕 (sesión 2026-11-01) Si la prueba tiene instrucciones, se muestran
    // antes de la primera pregunta (la de fixtures puede no tenerlas).
    const comenzar = page.getByRole("button", { name: "Comenzar las preguntas" });
    if (await comenzar.isVisible()) await comenzar.click();

    // Una pregunta por pantalla: responde "Sí" y avanza hasta la última,
    // donde el botón pasa a "Revisar y finalizar".
    for (let i = 0; i < 3; i++) {
      await page.getByRole("radio", { name: "Sí" }).check();
      const siguiente = page.getByRole("button", { name: "Siguiente" });
      if (await siguiente.isVisible()) await siguiente.click();
    }

    // Cada respuesta se autoguarda con su propio POST /guardar (ver
    // "se guardan automáticamente" en la UI) -- hay que esperar a que los 3
    // terminen antes de finalizar, o el backend puede ver menos de 3
    // respondidas todavía si el último autoguardado no llegó.
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("3 de 3 respondidas")).toBeVisible();

    await page.getByRole("button", { name: "Revisar y finalizar" }).click();
    await expect(page.getByRole("heading", { name: "Revisión final" })).toBeVisible();
    await page.getByRole("button", { name: "Finalizar evaluación" }).click();
    await expect(page.getByRole("heading", { name: "Evaluación finalizada" })).toBeVisible();
    // Solo agradecimiento: ni niveles ni descarga del informe.
    await expect(page.getByText("Nivel:")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Descargar/ })).toHaveCount(0);
  });
});
