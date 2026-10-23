import { test, expect } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { autenticarEnNavegador } from "./helpers";

// 🆕 Cubre el back-office interno de AuroraSoft (/master, /master/clientes,
// /master/clientes/[id]) -- listado en docs/frontend.md/docs/gaps-
// pendientes.md como sin ningún click-through real. Sesión de superadmin
// (no psicólogo, a diferencia del resto de specs) -- usa fixtures.
// superadminToken, YA logueado por global-setup, para no sumar otro login
// real al mismo rate limit de /auth/login que comparte toda la suite.
test.describe("Back-office interno (/master)", () => {
  test("crea una institución, la edita y gestiona sus usuarios", async ({ page }) => {
    const fixtures = leerFixtures();
    await autenticarEnNavegador(page, fixtures.superadminToken);

    // --- Paso 1: /master -- landing con conteos ---
    await page.goto("/master");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: "Panel interno" })).toBeVisible();
    await expect(page.getByText("Instituciones")).toBeVisible();
    await page.getByRole("link", { name: "Gestionar instituciones →" }).click();

    // --- Paso 2: /master/clientes -- crear una institución nueva ---
    await page.waitForURL(/\/master\/clientes$/);
    await page.getByRole("button", { name: "+ Nueva institución" }).click();
    const nombreInstitucion = `ZZPLAYWRIGHT Master ${fixtures.sello}`;
    await page.getByLabel("Nombre").fill(nombreInstitucion);
    await page.getByLabel("Correo de contacto (opcional)").fill(`zzpw.${fixtures.sello.toLowerCase()}.master@ejemplo.com`);
    await page.getByRole("button", { name: "Crear institución" }).click();

    await expect(page.getByText(nombreInstitucion)).toBeVisible();

    // --- Paso 3: /master/clientes/[id] -- editar los datos administrativos ---
    const filaInstitucion = page.locator("tr", { hasText: nombreInstitucion });
    await filaInstitucion.getByRole("link", { name: "Administrar →" }).click();
    await page.waitForURL(/\/master\/clientes\/\d+$/);
    await expect(page.getByRole("heading", { name: nombreInstitucion })).toBeVisible();

    await page.getByLabel("Teléfono").fill("+51 999 888 777");
    await page.getByLabel("Plan activo").uncheck();
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByLabel("Teléfono")).toHaveValue("+51 999 888 777");

    // --- Paso 4: gestionar usuarios de esta institución ---
    await page.getByRole("button", { name: "+ Nuevo usuario" }).click();
    const correoUsuario = `zzpw.${fixtures.sello.toLowerCase()}.master.usuario@ejemplo.com`;
    const nombreUsuario = `ZZPLAYWRIGHT Usuario Master ${fixtures.sello}`;
    await page.getByLabel("Nombre completo").fill(nombreUsuario);
    await page.getByLabel("Correo").fill(correoUsuario);
    await page.getByLabel("Contraseña inicial").fill("ClaveDePrueba123");
    await page.getByLabel("Rol").selectOption("psicologo");
    await page.getByRole("button", { name: "Crear usuario" }).click();

    await expect(page.getByText(nombreUsuario)).toBeVisible();
    await expect(page.getByText(correoUsuario)).toBeVisible();
    await expect(page.getByText("Activo", { exact: true })).toBeVisible();

    // --- Desactivar / reactivar el usuario recién creado ---
    const filaUsuario = page.locator("tr", { hasText: correoUsuario });
    await filaUsuario.getByRole("button", { name: "Desactivar" }).click();
    await expect(filaUsuario.getByText("Desactivado")).toBeVisible();
    await filaUsuario.getByRole("button", { name: "Reactivar" }).click();
    await expect(filaUsuario.getByText("Activo", { exact: true })).toBeVisible();
  });
});
