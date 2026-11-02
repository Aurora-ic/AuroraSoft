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
    // 🔧 (sesión 2026-11-02) El panel se rediseñó: "Resumen general" y el
    // botón "Nueva institución" lleva directo al formulario ya abierto.
    await expect(page.getByRole("heading", { name: "Resumen general" })).toBeVisible();
    await page.getByRole("link", { name: "Nueva institución" }).click();

    // --- Paso 2: /master/clientes -- crear una institución nueva ---
    await page.waitForURL(/\/master\/clientes/);
    const nombreInstitucion = `ZZPLAYWRIGHT Master ${fixtures.sello}`;
    await page.getByLabel("Nombre").fill(nombreInstitucion);
    await page.getByLabel("Correo de contacto (opcional)").fill(`zzpw.${fixtures.sello.toLowerCase()}.master@ejemplo.com`);
    await page.getByRole("button", { name: "Crear institución" }).click();

    await expect(page.locator("tr", { hasText: nombreInstitucion })).toBeVisible();

    // --- Paso 3: /master/clientes/[id] -- editar los datos administrativos ---
    const filaInstitucion = page.locator("tr", { hasText: nombreInstitucion });
    await filaInstitucion.getByRole("link", { name: "Administrar" }).click();
    await page.waitForURL(/\/master\/clientes\/\d+$/);
    await expect(page.getByRole("heading", { name: nombreInstitucion })).toBeVisible();

    await page.getByLabel("Teléfono").fill("+51 999 888 777");
    // El checkbox es sr-only bajo un interruptor dibujado: se hace clic en la
    // etiqueta visible, como un usuario.
    await page.locator("label", { hasText: "Si se desactiva, el colegio deja de poder usar la plataforma." }).click();
    await expect(page.getByLabel("Plan activo")).not.toBeChecked();
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    await expect(page.getByLabel("Teléfono")).toHaveValue("+51 999 888 777");

    // --- Paso 4: gestionar usuarios de esta institución ---
    await page.getByRole("button", { name: "Nuevo", exact: true }).click();
    const correoUsuario = `zzpw.${fixtures.sello.toLowerCase()}.master.usuario@ejemplo.com`;
    const nombreUsuario = `ZZPLAYWRIGHT Usuario Master ${fixtures.sello}`;
    await page.getByLabel("Nombre completo").fill(nombreUsuario);
    await page.getByLabel("Correo", { exact: true }).fill(correoUsuario);
    await page.getByLabel("Contraseña inicial").fill("ClaveDePrueba123");
    await page.getByLabel("Rol").selectOption("psicologo");
    await page.getByRole("button", { name: "Crear usuario" }).click();

    await expect(page.getByText(nombreUsuario)).toBeVisible();
    await expect(page.getByText(correoUsuario)).toBeVisible();

    // --- Desactivar / reactivar el usuario recién creado (ahora una lista,
    //     con insignia solo cuando está desactivado) ---
    const filaUsuario = page.locator("li", { hasText: correoUsuario });
    await expect(filaUsuario.getByText("Desactivado")).toHaveCount(0);
    await filaUsuario.getByRole("button", { name: "Desactivar" }).click();
    await expect(filaUsuario.getByText("Desactivado")).toBeVisible();
    await filaUsuario.getByRole("button", { name: "Reactivar" }).click();
    await expect(filaUsuario.getByRole("button", { name: "Desactivar" })).toBeVisible();
    await expect(filaUsuario.getByText("Desactivado")).toHaveCount(0);
  });
});
