import { test, expect } from "@playwright/test";
import { leerFixtures } from "./global-setup";

test.describe("Login", () => {
  test("credenciales correctas entra y redirige a /inicio", async ({ page }) => {
    const fixtures = leerFixtures();
    await page.goto("/");
    // Espera a que React hidrate antes de interactuar -- sin esto, un click
    // demasiado temprano puede disparar el submit nativo del <form> (sin
    // onSubmit todavía enganchado) en vez del handler real.
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Correo electrónico").fill(fixtures.psicologoEmail);
    await page.getByLabel("Contraseña", { exact: true }).fill(fixtures.psicologoPassword);
    await page.getByRole("button", { name: "Ingresar al sistema" }).click();
    await expect(page).toHaveURL(/\/inicio/);
  });

  test("credenciales incorrectas muestra un error y no entra", async ({ page }) => {
    const fixtures = leerFixtures();
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.getByLabel("Correo electrónico").fill(fixtures.psicologoEmail);
    await page.getByLabel("Contraseña", { exact: true }).fill("ClaveIncorrecta999");
    await page.getByRole("button", { name: "Ingresar al sistema" }).click();
    // El backend responde 401 con detail="Email o contraseña incorrectos"
    // (core/security.verify_password) -- AuthContext.login lo pasa tal
    // cual a mensajeError (ver app/page.tsx), nunca el genérico "Credenciales
    // incorrectas o error de conexión" (ese es solo el fallback si el error
    // no trae ".detail", ej. un fallo de red real).
    await expect(page.getByText(/email o contraseña incorrectos/i)).toBeVisible();
    await expect(page).toHaveURL("/");
  });
});
