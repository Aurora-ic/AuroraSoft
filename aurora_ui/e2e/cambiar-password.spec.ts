import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { API, emailSuperadmin, login, requerirPasswordSuperadmin } from "./helpers";

// 🆕 (2026-11-15) "Cambiar contraseña" desde la barra lateral (cualquier rol)
// y la pantalla de "¿Olvidaste tu contraseña?" abierta a toda cuenta. El
// detalle del backend (sesiones revocadas, enlaces anulados, tope por
// cuenta) lo cubre backend/tests/verificar_password_e2e.py; aquí, que la
// persona de verdad pueda hacerlo desde la pantalla.

const CLAVE_INICIAL = "ClaveInicial123";
const CLAVE_NUEVA = "ClaveNueva2026x";

test("cambiar contraseña desde la barra lateral", async ({ page }) => {
  const fixtures = leerFixtures();
  const ctx = await request.newContext();
  const tokenSuper = await login(ctx, emailSuperadmin(), requerirPasswordSuperadmin());
  const email = `zzplaywright.clave.${Date.now().toString(36)}@ejemplo.com`;
  const alta = await ctx.post(`${API}/auth/registro`, {
    headers: { Authorization: `Bearer ${tokenSuper}` },
    data: { email, password: CLAVE_INICIAL, nombre_completo: "ZZPLAYWRIGHT Interna", rol: "psicologo", institucion_id: fixtures.institucionId },
  });
  expect(alta.ok(), await alta.text()).toBeTruthy();

  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(CLAVE_INICIAL);
  await page.getByRole("button", { name: "Ingresar al sistema" }).click();
  await expect(page).toHaveURL(/\/inicio/);

  await page.getByRole("button", { name: "Cambiar contraseña" }).click();
  const dialogo = page.getByRole("dialog", { name: "Cambiar contraseña" });
  await expect(dialogo).toBeVisible();

  // Validación en la pantalla, sin ir al servidor.
  await dialogo.getByLabel("Contraseña actual").fill(CLAVE_INICIAL);
  await dialogo.getByLabel("Nueva contraseña", { exact: true }).fill("corta");
  await dialogo.getByLabel("Repite la nueva contraseña").fill("corta");
  await dialogo.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(dialogo.getByText("La contraseña debe tener al menos 8 caracteres.")).toBeVisible();

  // Actual equivocada: error en el campo y la sesión sigue (400, no 401).
  await dialogo.getByLabel("Contraseña actual").fill("NoEsLaMia999");
  await dialogo.getByLabel("Nueva contraseña", { exact: true }).fill(CLAVE_NUEVA);
  await dialogo.getByLabel("Repite la nueva contraseña").fill(CLAVE_NUEVA);
  await dialogo.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(dialogo.getByText("La contraseña actual no es correcta.")).toBeVisible();
  await expect(page).toHaveURL(/\/inicio/);

  await dialogo.getByLabel("Contraseña actual").fill(CLAVE_INICIAL);
  await dialogo.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page.getByRole("dialog", { name: "Contraseña actualizada" })).toBeVisible();
  await page.getByRole("button", { name: "Listo" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // Esta sesión sigue viva tras recargar.
  await page.reload();
  await expect(page).toHaveURL(/\/inicio/);
  await expect(page.getByRole("button", { name: "Cambiar contraseña" })).toBeVisible();

  // Que la clave vieja ya no entre y la nueva sí lo prueba
  // backend/tests/verificar_password_e2e.py: aquí dos logins más chocarían
  // con el rate limit de /auth/login (5/min) que comparte toda la suite.
  await ctx.dispose();
});

test("¿Olvidaste tu contraseña? ya no dice que es solo para el superadmin", async ({ page }) => {
  await page.goto("/recuperar-password");
  await expect(page.getByText("El mismo correo con el que inicias sesión en AuroraSoft.")).toBeVisible();
  await page.getByLabel("Correo electrónico").fill("zzplaywright.nadie@ejemplo.com");
  await page.getByRole("button", { name: "Enviar enlace de recuperación" }).click();
  await expect(page.getByText("corresponde a una cuenta activa de AuroraSoft", { exact: false })).toBeVisible();
  await expect(page.getByText("Pide al administrador de tu institución que restablezca")).toHaveCount(0);
});
