import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { API, crearAlumnoConConsentimiento, finalizarExamenCompleto, autenticarEnNavegador } from "./helpers";

// 🆕 Cubre "Dashboard por salón o grado" en /pruebas — el último de los
// gaps documentados en docs/frontend.md/docs/gaps-pendientes.md sin ningún
// test automatizado. Tres piezas reales: el dashboard académico en sí
// (cruza TODAS las campañas de un salón para una prueba), "Ver tendencia en
// el tiempo" (solo aplica a UN salón puntual) y "Comparar con otra sección
// del mismo grado". La estructura académica (nivel/grado/2 secciones) y la
// matrícula académica de cada alumno (distinta de la matrícula de campaña)
// se arman por API -- lo que SÍ se prueba es la pantalla en sí.
test.describe("Dashboard académico", () => {
  test("ve el dashboard de un salón, su tendencia y lo compara con otra sección", async ({ page }) => {
    const fixtures = leerFixtures();
    const ctx = await request.newContext();
    const hSuper = { Authorization: `Bearer ${fixtures.superadminToken}` };
    const hPsi = { Authorization: `Bearer ${fixtures.psicologoToken}` };
    const anioEscolar = new Date().getFullYear();

    // --- Estructura académica (solo-administrativo -- token superadmin) ---
    const nombreNivel = `ZZPLAYWRIGHT Nivel ${fixtures.sello}`;
    const nombreGrado = `ZZPLAYWRIGHT Grado ${fixtures.sello}`;
    const nivel = await (
      await ctx.post(`${API}/admin/personas/academico/niveles`, {
        headers: hSuper, data: { institucion_id: fixtures.institucionId, nombre: nombreNivel },
      })
    ).json();
    const grado = await (
      await ctx.post(`${API}/admin/personas/academico/grados`, {
        headers: hSuper, data: { nivel_educativo_id: nivel.id, nombre: nombreGrado },
      })
    ).json();
    const seccionA = await (
      await ctx.post(`${API}/admin/personas/academico/secciones`, {
        headers: hSuper, data: { grado_id: grado.id, nombre: "A", anio_escolar: anioEscolar },
      })
    ).json();
    const seccionB = await (
      await ctx.post(`${API}/admin/personas/academico/secciones`, {
        headers: hSuper, data: { grado_id: grado.id, nombre: "B", anio_escolar: anioEscolar },
      })
    ).json();

    // --- Dos alumnos, cada uno matriculado académicamente en una sección distinta ---
    const nombreAlumnoA = `DashAcadA ${fixtures.sello}`;
    const nombreAlumnoB = `DashAcadB ${fixtures.sello}`;
    const personaA = await crearAlumnoConConsentimiento(ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumnoA);
    const personaB = await crearAlumnoConConsentimiento(ctx, fixtures.psicologoToken, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumnoB);
    await ctx.post(`${API}/admin/personas/${personaA}/matricula`, { headers: hPsi, data: { seccion_id: seccionA.id } });
    await ctx.post(`${API}/admin/personas/${personaB}/matricula`, { headers: hPsi, data: { seccion_id: seccionB.id } });

    // --- Una campaña con la prueba compartida, matriculando a cada alumno
    //     POR SEPARADO (nunca los dos en el mismo POST) -- InscripcionResponse
    //     no trae persona_id, así que es la única forma de mapear sin
    //     ambigüedad qué token le corresponde a cuál. ---
    const campana = await (
      await ctx.post(`${API}/educativo/campanas/`, {
        headers: hPsi,
        data: { prueba_id: fixtures.pruebaId, nombre_grupo: `ZZPLAYWRIGHT Dash Acad ${fixtures.sello}`, institucion_id: fixtures.institucionId },
      })
    ).json();
    const matriculaA = await (
      await ctx.post(`${API}/educativo/campanas/${campana.id}/matricular-roster`, { headers: hPsi, data: [personaA] })
    ).json();
    const matriculaB = await (
      await ctx.post(`${API}/educativo/campanas/${campana.id}/matricular-roster`, { headers: hPsi, data: [personaB] })
    ).json();
    await finalizarExamenCompleto(ctx, matriculaA.generados[0].token, fixtures.preguntaIds, fixtures.opcionCorrectaIds);
    await finalizarExamenCompleto(ctx, matriculaB.generados[0].token, fixtures.preguntaIds, fixtures.opcionCorrectaIds);
    await ctx.dispose();

    await autenticarEnNavegador(page, fixtures.psicologoToken);
    await page.goto("/pruebas");
    await page.waitForLoadState("networkidle");

    // --- Dashboard por salón o grado: elegir prueba + nivel + grado + sección A ---
    await page.getByLabel("Prueba").selectOption({ label: `ZZPLAYWRIGHT-${fixtures.sello}` });
    await page.getByLabel("Nivel").selectOption({ label: nombreNivel });
    await page.getByLabel("Grado").selectOption({ label: nombreGrado });
    await page.getByLabel("Sección").selectOption({ label: `A (${anioEscolar})` });
    await page.getByRole("button", { name: "Ver dashboard" }).click();

    await expect(page.getByText(/1 finalizado/)).toBeVisible();
    await expect(page.getByText(nombreAlumnoA)).toBeVisible();

    // --- Tendencia en el tiempo: una sola campaña todavía no alcanza para
    //     mostrar una evolución -- el propio mensaje de "hace falta al
    //     menos dos" es el comportamiento correcto a esta escala. ---
    await page.getByRole("button", { name: "Ver tendencia en el tiempo" }).click();
    await expect(page.getByText(/hace falta al menos dos/)).toBeVisible();

    // --- Comparar con la sección B del mismo grado -- este <Select> no
    //     tiene <label> asociado (a diferencia del de arriba), así que se
    //     ubica por el texto hermano "Comparar con otra sección..." en vez
    //     de getByLabel. ---
    const bloqueComparar = page.getByText("Comparar con otra sección del mismo grado", { exact: true }).locator("..");
    await bloqueComparar.locator("select").selectOption({ label: `B (${anioEscolar})` });
    await bloqueComparar.getByRole("button", { name: "Comparar" }).click();
    await expect(page.getByText(/finalizado\(s\) de/)).toHaveCount(2);
  });
});
