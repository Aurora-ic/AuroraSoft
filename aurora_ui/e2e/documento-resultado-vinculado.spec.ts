import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import {
  API, autenticarEnNavegador, crearAlumnoConConsentimiento, crearCampanaYMatricular,
  crearPruebaConBaremo, crearTipoDocumento, esperarInformeGenerado, finalizarExamenCompleto,
} from "./helpers";

// 🆕 (sesión 2026-11-02) Vincular a mano el resultado de una prueba a un
// documento, junto con contenido propio (p. ej. una prueba proyectiva que el
// motor no corrige): el caso por el que un colegio combina las dos cosas en
// el mismo informe. Backend y pantalla ya existían (PUT/DELETE
// .../resultados-prueba, EditorResultadoVinculable); este spec es su primer
// recorrido real en el navegador.
test.describe("Documento con un resultado de prueba vinculado", () => {
  test("vincula la prueba del alumno, la quita y la vuelve a vincular, y emite el documento", async ({ page }) => {
    const fixtures = leerFixtures();
    const token = fixtures.psicologoToken;
    const h = { Authorization: `Bearer ${token}` };
    const ctx = await request.newContext();

    // --- Lo que no es el flujo bajo prueba, por API ---
    const tipoId = await crearTipoDocumento(ctx, fixtures.superadminToken, `${fixtures.sello}V`);
    const prueba = await crearPruebaConBaremo(ctx, token, `ZZPLAYWRIGHT-VINC-${fixtures.sello}`, false);
    const apellidos = `Vinculo ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", apellidos);
    const tokenExamen = await crearCampanaYMatricular(
      ctx, token, fixtures.institucionId, prueba.pruebaId, `ZZPLAYWRIGHT Campaña Vínculo ${fixtures.sello}`, personaId,
    );
    await finalizarExamenCompleto(ctx, tokenExamen, prueba.preguntaIds, prueba.opcionCorrectaIds);
    await esperarInformeGenerado(ctx, token, personaId);

    const ok = async <T = { id: number }>(r: Awaited<ReturnType<typeof ctx.post>>, que: string): Promise<T> => {
      if (!r.ok()) throw new Error(`${que}: ${r.status()} ${await r.text()}`);
      return r.json() as Promise<T>;
    };
    const plantilla = await ok(await ctx.post(`${API}/documentos/plantillas`, {
      headers: h, data: { nombre: `ZZPLAYWRIGHT Informe combinado ${fixtures.sello}`, tipo_documento_id: tipoId, institucion_id: fixtures.institucionId, activa: true },
    }), "plantilla");
    await ok(await ctx.post(`${API}/documentos/plantillas/${plantilla.id}/secciones`, {
      headers: h, data: { orden: 0, tipo_seccion: "texto_libre", titulo: "Prueba proyectiva: observaciones" },
    }), "sección texto");
    await ok(await ctx.post(`${API}/documentos/plantillas/${plantilla.id}/secciones`, {
      headers: h, data: { orden: 1, tipo_seccion: "resultados_prueba", titulo: "Resultado psicométrico" },
    }), "sección resultados");
    const documento = await ok(await ctx.post(`${API}/documentos/`, {
      headers: h,
      data: {
        tipo_documento_id: tipoId, plantilla_documento_id: plantilla.id, alcance: "personas_especificas",
        titulo: `ZZPLAYWRIGHT Informe combinado ${fixtures.sello}`, personas_ids: [personaId],
      },
    }), "documento");

    // --- El flujo real, en el navegador ---
    await autenticarEnNavegador(page, token);
    await page.goto(`/documentos/${documento.id}`);
    // Primera carga del documento: en el entorno de desarrollo cada consulta
    // tarda cientos de ms, así que se le da más margen que el de 5 s.
    await expect(page.getByText("Resultado psicométrico")).toBeVisible({ timeout: 30_000 });

    // Sin vínculo todavía: se elige la aplicación real del alumno.
    await expect(page.getByText("Ninguna todavía. Elige una:")).toBeVisible();
    await page.getByRole("button", { name: "Vincular" }).click();
    await expect(page.getByText("Prueba vinculada")).toBeVisible();
    const quitar = page.getByRole("button", { name: "Quitar" });
    await expect(quitar).toBeVisible();

    // Quitar y volver a vincular.
    await quitar.click();
    await expect(page.getByText("Ninguna todavía. Elige una:")).toBeVisible();
    await page.getByRole("button", { name: "Vincular" }).click();
    await expect(page.getByRole("button", { name: "Quitar" })).toBeVisible();

    // El vínculo quedó guardado en el servidor (no solo en pantalla).
    const secciones = await ok<{ inscripciones_vinculadas?: number[] }[]>(await ctx.get(`${API}/documentos/${documento.id}/secciones`, { headers: h }), "secciones");
    const vinculadas = secciones.flatMap((s) => s.inscripciones_vinculadas ?? []);
    expect(vinculadas.length).toBe(1);

    // El contenido propio de la prueba proyectiva, en la otra sección.
    await page.getByRole("textbox").first().fill(`Dibujo de la figura humana: trazos firmes, sin indicadores a destacar (${fixtures.sello}).`);
    await page.getByRole("button", { name: "Guardar" }).first().click();
    // Se espera a que termine de guardar antes de emitir, como haría una persona.
    await expect(page.getByRole("button", { name: "Guardando..." })).toHaveCount(0, { timeout: 30_000 });

    await page.getByRole("button", { name: "Generar versión 1" }).click();
    // Generar el PDF es lo más lento del flujo (más aún en el entorno de desarrollo).
    await expect(page.getByText(/^v1 —/)).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("button", { name: "Descargar PDF" })).toBeVisible();
    await ctx.dispose();
  });
});
