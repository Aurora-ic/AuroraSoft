import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { crearAlumnoConConsentimiento, crearTipoDocumento, autenticarEnNavegador } from "./helpers";

// 🆕 Cubre las 4 rutas del motor de documentos institucionales que nunca
// habían tenido un click-through real (docs/frontend.md/docs/gaps-
// pendientes.md): /documentos (crear plantilla), el constructor
// (/documentos/plantillas/[id]), crear un documento (/documentos/nuevo) y
// el editor de contenido + generar (/documentos/[id]). Un solo spec de
// punta a punta, porque las 4 pantallas son pasos consecutivos del mismo
// flujo real -- no cuatro flujos independientes.
test.describe("Motor de documentos institucionales", () => {
  test("crea una plantilla, agrega una sección, genera un documento y lo emite", async ({ page }) => {
    const fixtures = leerFixtures();
    const token = fixtures.psicologoToken;

    // Lo que NO es el flujo bajo prueba se arma por API: el TipoDocumento
    // (sin UI, solo-superadmin) y el alumno destinatario del documento.
    const ctx = await request.newContext();
    // El id no hace falta después: el <select> de /documentos lo trae de
    // GET /documentos/tipos y se elige por nombre, no por id.
    await crearTipoDocumento(ctx, fixtures.superadminToken, fixtures.sello);
    const nombreAlumno = `Documentos ${fixtures.sello}`;
    await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    await ctx.dispose();

    // Login en sí NO es lo que este spec prueba -- sesión inyectada
    // directamente, mismo criterio que el resto de specs.
    await autenticarEnNavegador(page, token);

    // --- Paso 1: /documentos -- crear una plantilla a partir del tipo recién creado ---
    // 🆕 Rediseño en pestañas (sesión 2026-10-25, docs/frontend.md): el
    // formulario "nueva desde cero" vive en la pestaña "Mis plantillas"
    // (activa por defecto) detrás de un toggle, para no competir en
    // pantalla con el catálogo para clonar.
    await page.goto("/documentos");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "+ Nueva desde cero" }).click();
    await page.getByLabel("Nueva plantilla a partir de un tipo de documento").selectOption({ label: `ZZPLAYWRIGHT Tipo ${fixtures.sello}` });
    await page.getByRole("button", { name: "Crear y abrir el constructor" }).click();

    // --- Paso 2: el constructor (/documentos/plantillas/[id]) -- agregar una sección "Texto libre" ---
    await page.waitForURL(/\/documentos\/plantillas\/\d+/);
    await expect(page.getByRole("heading", { name: /nueva plantilla/i })).toBeVisible();
    const tituloSeccion = `Motivo de evaluación ${fixtures.sello}`;
    // "Tipo" ya nace en "Texto libre" (el default del formulario) -- no hace
    // falta tocar el <select>, solo el título y agregar.
    await page.getByLabel("Título (opcional)").fill(tituloSeccion);
    await page.getByRole("button", { name: "+ Agregar sección" }).click();
    // El título de la sección se edita inline (su nombre accesible queda
    // fijo como "(sin título propio)" — lo que cambia es el VALOR del
    // campo, nunca texto estático), por eso se verifica con toHaveValue,
    // no con getByText.
    const filaSeccion = page.getByRole("textbox", { name: "(sin título propio)" }).locator("..");
    await expect(filaSeccion.getByRole("textbox", { name: "(sin título propio)" })).toHaveValue(tituloSeccion);
    // Acotado a la fila de la sección -- "Texto libre" a secas también
    // matchea la <option> del <select> "Tipo" en el resto de la pantalla.
    await expect(filaSeccion.getByText("Texto libre")).toBeVisible();

    const urlPlantilla = page.url();
    const plantillaId = urlPlantilla.match(/\/documentos\/plantillas\/(\d+)/)?.[1];
    if (!plantillaId) throw new Error(`No se pudo extraer el id de la plantilla de ${urlPlantilla}`);

    // --- Paso 3: /documentos/nuevo -- crear un DocumentoInstitucional para el alumno ---
    await page.goto("/documentos/nuevo");
    await page.waitForLoadState("networkidle");
    // Nombre autogenerado por crearPlantilla() en /documentos: `${tipo.nombre} — nueva plantilla`.
    await page.getByLabel("Plantilla").selectOption({ label: `ZZPLAYWRIGHT Tipo ${fixtures.sello} — nueva plantilla` });
    const tituloDocumento = `Documento de prueba ${fixtures.sello}`;
    await page.getByLabel("Título").fill(tituloDocumento);
    // Alcance ya nace en "Uno o varios alumnos" (default) -- solo falta
    // buscar y marcar al alumno recién creado.
    await page.getByPlaceholder("Buscar por nombre o apellido...").fill(nombreAlumno);
    await page.getByText(nombreAlumno).click();
    await page.getByRole("button", { name: "Crear documento" }).click();

    // --- Paso 4: el editor de contenido (/documentos/[id]) -- llenar la sección, generar ---
    await page.waitForURL(/\/documentos\/\d+$/);
    await expect(page.getByRole("heading", { name: tituloDocumento })).toBeVisible();
    await expect(page.getByText(nombreAlumno)).toBeVisible();
    await expect(page.getByText(tituloSeccion)).toBeVisible();

    const contenidoTexto = `El estudiante fue evaluado el ${fixtures.sello} en el marco de la campaña de tamizaje institucional.`;
    await page.getByRole("textbox").first().fill(contenidoTexto);
    await page.getByRole("button", { name: "Guardar" }).click();

    await page.getByRole("button", { name: "Generar versión 1" }).click();
    await expect(page.getByText(/^v1 —/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Descargar PDF" })).toBeVisible();

    // Reemisión real (v2) -- la otra mitad del motor de versionado que
    // tampoco tenía click-through, ver "Generar/reemitir" en docs/motor-documentos.md.
    await page.getByRole("button", { name: /Reemitir \(v2\)/ }).click();
    await page.getByPlaceholder("Motivo de la reemisión...").fill(`Corrección de prueba ${fixtures.sello}`);
    await page.getByRole("button", { name: "Confirmar reemisión" }).click();
    await expect(page.getByText(/^v2 —/)).toBeVisible();
    // v1 sigue listada e intacta -- una reemisión nunca borra la versión anterior.
    await expect(page.getByText(/^v1 —/)).toBeVisible();
  });
});
