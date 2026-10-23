import fs from "fs";
import path from "path";
import { request } from "@playwright/test";
import { crearFixturesBase } from "./helpers";

// Corre UNA VEZ antes de toda la suite -- crea la institución/psicólogo/
// prueba compartidos por los 4 specs y los deja en un archivo que cada
// spec lee en su propio test.beforeAll. Un sello por ejecución (timestamp)
// para no chocar entre corridas -- la limpieza es manual, ver e2e/README.md
// (mismo criterio que --limpiar en los e2e del backend).
const RUTA_FIXTURES = path.join(__dirname, ".fixtures.json");

export default async function globalSetup() {
  const sello = Date.now().toString(36).toUpperCase();
  const ctx = await request.newContext();
  try {
    const fixtures = await crearFixturesBase(ctx, sello);
    fs.writeFileSync(RUTA_FIXTURES, JSON.stringify(fixtures, null, 2));
    console.log(`[global-setup] Fixtures ZZPLAYWRIGHT ${sello} creadas (institución ${fixtures.institucionId}).`);
  } finally {
    await ctx.dispose();
  }
}

export function leerFixtures() {
  return JSON.parse(fs.readFileSync(RUTA_FIXTURES, "utf-8"));
}
