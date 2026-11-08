import { test, expect, request, type Page } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import {
  crearAlumnoConConsentimiento, crearCampanaYMatricular,
  crearPruebaConBaremo, finalizarExamenCompleto, autenticarEnNavegador, esperarInformeGenerado,
} from "./helpers";

// 🆕 (sesión 2026-11-07, M2 de la revisión de seguridad) Cabeceras del
// frontend (next.config.ts). 🆕 (sesión 2026-11-08) La CSP ya es obligatoria:
// el navegador bloquea y dispara `securitypolicyviolation` por cada bloqueo. Este spec recorre las pantallas con más riesgo de chocar con la
// CSP — login, examen público y el visor de PDF (react-pdf + su worker) —
// y falla si aparece alguna violación. Así se sabe cuándo se puede pasar de
// Report-Only a Content-Security-Policy de verdad.

const VIOLACIONES_INIT = () => {
  (window as unknown as { __violacionesCsp: string[] }).__violacionesCsp = [];
  document.addEventListener("securitypolicyviolation", (e) => {
    (window as unknown as { __violacionesCsp: string[] }).__violacionesCsp.push(
      `${e.effectiveDirective} bloquearía ${e.blockedURI || "(inline)"} en ${e.documentURI}`,
    );
  });
};

async function violaciones(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __violacionesCsp?: string[] }).__violacionesCsp ?? []);
}

test.describe("Cabeceras de seguridad del frontend", () => {
  test("las páginas llevan las cabeceras y no anuncian Next.js", async ({ page }) => {
    const respuesta = await page.goto("/");
    expect(respuesta).not.toBeNull();
    const h = respuesta!.headers();
    expect(h["x-powered-by"]).toBeUndefined();
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["x-frame-options"]).toBe("DENY");
    expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(h["permissions-policy"]).toContain("camera=()");
    // 🆕 (sesión 2026-11-08) CSP obligatoria (antes solo-reporte).
    const csp = h["content-security-policy"];
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    // La app tiene que poder hablar con el backend configurado.
    const apiOrigen = new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010/api").origin;
    expect(csp).toMatch(new RegExp(`connect-src [^;]*${apiOrigen.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
    expect(h["content-security-policy-report-only"]).toBeUndefined();
    // Los scripts siguen limitados al propio sitio (sin orígenes externos).
    expect(csp).toMatch(/script-src 'self' 'unsafe-inline'(;| 'unsafe-eval';)/);
  });

  test("login, examen y visor de PDF no violan la CSP", async ({ page }) => {
    const fixtures = leerFixtures();
    await page.addInitScript(VIOLACIONES_INIT);
    const encontradas: string[] = [];

    await page.goto("/");
    await page.waitForLoadState("networkidle");
    encontradas.push(...(await violaciones(page)));

    await page.goto("/examen/zz-enlace-que-no-existe");
    await page.waitForLoadState("networkidle");
    encontradas.push(...(await violaciones(page)));

    // Un informe real para abrir el visor de PDF (react-pdf + worker).
    const ctx = await request.newContext();
    const token = fixtures.psicologoToken;
    const prueba = await crearPruebaConBaremo(ctx, token, `ZZPLAYWRIGHT-CSP-${fixtures.sello}`, true);
    const nombreAlumno = `CabecerasCsp ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    const tokenExamen = await crearCampanaYMatricular(
      ctx, token, fixtures.institucionId, prueba.pruebaId, `ZZPLAYWRIGHT Campaña CSP ${fixtures.sello}`, personaId,
    );
    await finalizarExamenCompleto(ctx, tokenExamen, prueba.preguntaIds, prueba.opcionCorrectaIds);
    await esperarInformeGenerado(ctx, token, personaId);
    await ctx.dispose();

    await autenticarEnNavegador(page, token);
    await page.goto("/estudiantes");
    await page.waitForLoadState("networkidle");
    encontradas.push(...(await violaciones(page)));
    await page.getByText(new RegExp(nombreAlumno)).click();
    await expect(page.getByRole("heading", { name: "Pruebas aplicadas" })).toBeVisible();
    await page.getByRole("button", { name: "Revisar informe" }).click();
    // react-pdf dibuja cada página en un <canvas>: si el worker no cargó, no aparece.
    await expect(page.locator("canvas").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    encontradas.push(...(await violaciones(page)));

    expect(encontradas, `Violaciones de la CSP:\n${encontradas.join("\n")}`).toEqual([]);
  });
});
