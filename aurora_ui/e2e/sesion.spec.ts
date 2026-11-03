import { test, expect, type Page } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { API } from "./helpers";

// 🆕 (sesión 2026-11-02) Sesiones de servidor (backend/core/sesiones.py):
// el token vive en cookies httpOnly (no en localStorage), el bloqueo por
// inactividad bloquea la sesión EN EL SERVIDOR, y cerrar sesión la revoca.
// Un solo test con dos logins reales (login + desbloqueo) para no gastar el
// rate limit de /auth/login (5/min).

async function cookieAcceso(page: Page) {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name === "aurora_sesion");
}

async function estadoDeToken(page: Page, token: string) {
  const res = await page.request.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } });
  return res.status();
}

test("sesión: cookies httpOnly, bloqueo en el servidor y cierre que revoca", async ({ page }) => {
  const fixtures = leerFixtures();
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.getByLabel("Correo electrónico").fill(fixtures.psicologoEmail);
  await page.getByLabel("Contraseña", { exact: true }).fill(fixtures.psicologoPassword);
  await page.getByRole("button", { name: "Ingresar al sistema" }).click();
  await expect(page).toHaveURL(/\/inicio/);

  // 1 · El token está en una cookie httpOnly; JavaScript no lo ve.
  const acceso = await cookieAcceso(page);
  expect(acceso, "cookie de acceso").toBeTruthy();
  expect(acceso!.httpOnly).toBe(true);
  const renovacion = (await page.context().cookies()).find((c) => c.name === "aurora_renovacion");
  expect(renovacion?.httpOnly).toBe(true);
  expect(renovacion?.path).toBe("/api/auth");
  const visto = await page.evaluate(() => ({
    cookies: document.cookie,
    tokenViejo: localStorage.getItem("aurora_token"),
    sesion: JSON.parse(localStorage.getItem("aurora_sesion") || "null"),
    todo: JSON.stringify(localStorage),
  }));
  expect(visto.cookies).not.toContain("aurora_sesion=");
  expect(visto.tokenViejo).toBeNull();
  expect(visto.sesion?.rol).toBe("psicologo");
  expect(visto.todo).not.toContain(acceso!.value);
  expect(await estadoDeToken(page, acceso!.value)).toBe(200);

  // 1b · Acceso vencido (se simula borrando su cookie): la app renueva sola
  // con la cookie de renovación y sigue en la página, sin pedir login.
  await page.context().clearCookies({ name: "aurora_sesion" });
  const renovo = page.waitForResponse((r) => r.url().endsWith("/auth/renovar"));
  await page.reload();
  expect((await renovo).status()).toBe(200);
  await expect(page).toHaveURL(/\/inicio/);
  await expect.poll(async () => (await cookieAcceso(page))?.value).toBeTruthy();

  // 2 · Inactividad: la pantalla se bloquea y la sesión queda bloqueada en el servidor.
  const avisoBloqueo = page.waitForRequest((r) => r.url().endsWith("/auth/bloquear") && r.method() === "POST");
  await page.evaluate(() => localStorage.setItem("aurora_ultima_actividad", String(Date.now() - 60 * 60 * 1000)));
  await expect(page.getByRole("heading", { name: "Sesión bloqueada" })).toBeVisible();
  await avisoBloqueo;
  const accesoAlBloquear = (await cookieAcceso(page))!;
  await expect.poll(() => estadoDeToken(page, accesoAlBloquear.value)).toBe(401);
  expect(await estadoDeToken(page, acceso!.value)).toBe(401);

  // 3 · Desbloquear con la contraseña: sesión nueva, la página sigue ahí.
  await page.getByLabel("Contraseña", { exact: true }).fill(fixtures.psicologoPassword);
  await page.getByRole("button", { name: "Desbloquear" }).click();
  await expect(page.getByRole("heading", { name: "Sesión bloqueada" })).toBeHidden();
  await expect(page).toHaveURL(/\/inicio/);
  const accesoNuevo = await cookieAcceso(page);
  expect(accesoNuevo!.value).not.toBe(accesoAlBloquear.value);
  expect(await estadoDeToken(page, accesoNuevo!.value)).toBe(200);

  // 4 · Cerrar sesión revoca en el servidor: el token copiado ya no sirve.
  const cierre = page.waitForResponse((r) => r.url().endsWith("/auth/cerrar-sesion"));
  await page.getByRole("button", { name: "Cerrar sesión" }).first().click();
  expect((await cierre).status()).toBe(204);
  await expect(page).toHaveURL("/");
  expect(await estadoDeToken(page, accesoNuevo!.value)).toBe(401);
  expect(await cookieAcceso(page)).toBeUndefined();
});
