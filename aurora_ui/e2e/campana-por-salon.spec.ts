import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { API, autenticarEnNavegador, crearAlumnoConConsentimiento } from "./helpers";

// 🆕 (sesión 2026-11-02) Campaña por salón (sesión 2026-11-01): marcar un
// salón matricula a todos sus alumnos que pueden rendir la prueba, y el
// salón avisa cuántos no pueden (aquí, uno sin consentimiento del
// apoderado), que quedan fuera.
test.describe("Campaña por salón", () => {
  test("marca un salón, avisa quién no puede rendirla y genera los links del resto", async ({ page }) => {
    const fixtures = leerFixtures();
    const ctx = await request.newContext();
    const hSuper = { Authorization: `Bearer ${fixtures.superadminToken}` };
    const hPsi = { Authorization: `Bearer ${fixtures.psicologoToken}` };

    // --- Un salón con 3 alumnos: 2 con consentimiento y 1 sin él ---
    const nombreNivel = `ZZPLAYWRIGHT NivelSalon ${fixtures.sello}`;
    const nombreGrado = `ZZPLAYWRIGHT GradoSalon ${fixtures.sello}`;
    const nivel = await (await ctx.post(`${API}/admin/personas/academico/niveles`, {
      headers: hSuper, data: { institucion_id: fixtures.institucionId, nombre: nombreNivel },
    })).json();
    const grado = await (await ctx.post(`${API}/admin/personas/academico/grados`, {
      headers: hSuper, data: { nivel_educativo_id: nivel.id, nombre: nombreGrado },
    })).json();
    const seccion = await (await ctx.post(`${API}/admin/personas/academico/secciones`, {
      headers: hSuper, data: { grado_id: grado.id, nombre: "S", anio_escolar: new Date().getFullYear() },
    })).json();
    const conConsentimiento = [];
    for (const n of [1, 2]) {
      conConsentimiento.push(
        await crearAlumnoConConsentimiento(ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", `Salon${n} ${fixtures.sello}`),
      );
    }
    const sinConsentimiento = await (await ctx.post(`${API}/admin/personas/`, {
      headers: hPsi,
      data: { institucion_id: fixtures.institucionId, nombres: "ZZPLAYWRIGHT", apellidos: `SalonSinCons ${fixtures.sello}`, tipo_perfil: "estudiante" },
    })).json();
    for (const id of [...conConsentimiento, sinConsentimiento.id]) {
      const r = await ctx.post(`${API}/admin/personas/${id}/matricula`, { headers: hPsi, data: { seccion_id: seccion.id } });
      expect(r.ok(), await r.text()).toBe(true);
    }
    await ctx.dispose();

    await autenticarEnNavegador(page, fixtures.psicologoToken);
    await page.goto("/campanas/nueva");
    await page.waitForLoadState("networkidle");
    await page.getByRole("radio", { name: new RegExp(`ZZPLAYWRIGHT-${fixtures.sello}`) }).click();

    const salon = page.getByLabel(new RegExp(`Salón ${nombreGrado} S`));
    const tarjeta = page.locator("label").filter({ has: salon });
    await expect(tarjeta.getByText(/3 alumnos/)).toBeVisible();
    await expect(tarjeta.getByText(/1 no pueden rendirla/)).toBeVisible();
    await salon.check();

    const nombreCampana = `ZZPLAYWRIGHT Salón ${fixtures.sello}`;
    await page.getByRole("button", { name: "Editar el nombre" }).click();
    await page.getByLabel("Nombre de la campaña").fill(nombreCampana);
    await page.getByRole("button", { name: "Crear campaña y generar links" }).click();

    await expect(page.getByRole("heading", { name: "¡Campaña lista!" })).toBeVisible();
    await expect(page.getByText("links generados", { exact: true }).locator("..")).toContainText(/^\s*2\s*links generados/);

    // En el dashboard están los dos con consentimiento y no el que no lo tiene.
    await page.getByRole("button", { name: "Ir al dashboard de la campaña" }).click();
    await expect(page.getByText(nombreCampana)).toBeVisible();
    await expect(page.getByText(new RegExp(`Salon1 ${fixtures.sello}`))).toBeVisible();
    await expect(page.getByText(new RegExp(`Salon2 ${fixtures.sello}`))).toBeVisible();
    await expect(page.getByText(new RegExp(`SalonSinCons ${fixtures.sello}`))).toHaveCount(0);
  });
});
