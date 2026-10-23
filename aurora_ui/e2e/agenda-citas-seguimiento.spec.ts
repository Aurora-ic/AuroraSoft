import { test, expect, request } from "@playwright/test";
import { leerFixtures } from "./global-setup";
import { crearAlumnoConConsentimiento, autenticarEnNavegador } from "./helpers";

// 🆕 Cubre citas, sesiones de seguimiento y /agenda — tres pantallas
// listadas en docs/frontend.md/docs/gaps-pendientes.md como "sin ningún
// test automatizado, solo verificación manual puntual". Dos specs
// independientes (citas+agenda / sesiones) porque son dos sub-flujos
// reales distintos de la ficha del alumno, cada uno con su propio alumno
// para no competir por el mismo estado.

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10);
}

test.describe("Citas y agenda", () => {
  test("agenda una cita desde la ficha, la reprograma ahí y de nuevo desde /agenda", async ({ page }) => {
    const fixtures = leerFixtures();
    const token = fixtures.psicologoToken;

    const ctx = await request.newContext();
    const nombreAlumno = `Citas ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    await ctx.dispose();

    await autenticarEnNavegador(page, token);

    // --- Crear la cita desde la ficha del alumno ("+ Nueva Cita") ---
    await page.goto(`/estudiantes/${personaId}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: nombreAlumno })).toBeVisible();

    await page.getByRole("button", { name: "+ Nueva Cita" }).click();
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}/cita/nueva`));
    const motivoCita = `Entrevista de seguimiento ${fixtures.sello}`;
    await page.getByLabel("Motivo").fill(motivoCita);
    await page.getByLabel("Fecha").fill(hoyISO());
    await page.getByLabel("Hora").fill("10:00");
    await page.getByRole("button", { name: "Agendar cita" }).click();

    // Vuelve a la ficha -- la cita recién creada aparece "Programada".
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}$`));
    await expect(page.getByText(`Motivo: ${motivoCita}`)).toBeVisible();
    await expect(page.getByText("Programada")).toBeVisible();

    // --- Reprogramar desde la ficha (formulario inline) ---
    await page.getByRole("button", { name: "Reprogramar" }).click();
    await page.getByLabel("Nueva fecha").fill(hoyISO());
    await page.getByLabel("Nueva hora").fill("15:30");
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText("Reprogramar")).toBeVisible(); // el botón vuelve a aparecer tras guardar

    // --- La misma cita aparece en /agenda -- reprogramarla de nuevo, esta
    //     vez desde la grilla semanal (código distinto al de la ficha). ---
    await page.goto("/agenda");
    await page.waitForLoadState("networkidle");
    const tarjetaAgenda = page
      .locator("div")
      .filter({ hasText: motivoCita })
      .filter({ has: page.getByRole("button", { name: "Reprogramar" }) })
      .last();
    await expect(tarjetaAgenda).toBeVisible();

    await tarjetaAgenda.getByRole("button", { name: "Reprogramar" }).click();
    await tarjetaAgenda.locator('input[type="date"]').fill(hoyISO());
    await tarjetaAgenda.locator('input[type="time"]').fill("16:45");
    await tarjetaAgenda.getByRole("button", { name: "Guardar" }).click();
    await expect(tarjetaAgenda.getByText("16:45")).toBeVisible();

    // --- Cancelar desde /agenda -- la otra mitad de este control. ---
    page.once("dialog", (dialog) => dialog.accept());
    await tarjetaAgenda.getByRole("button", { name: "Cancelar" }).click();
    await expect(tarjetaAgenda.getByText("Cancelada")).toBeVisible();
  });
});

test.describe("Sesiones de seguimiento", () => {
  test("registra una sesión desde la ficha y la edita después", async ({ page }) => {
    const fixtures = leerFixtures();
    const token = fixtures.psicologoToken;

    const ctx = await request.newContext();
    const nombreAlumno = `Seguimiento ${fixtures.sello}`;
    const personaId = await crearAlumnoConConsentimiento(ctx, token, fixtures.institucionId, "ZZPLAYWRIGHT", nombreAlumno);
    await ctx.dispose();

    await autenticarEnNavegador(page, token);

    // --- Registrar la sesión desde la ficha ("+ Registrar Sesión") ---
    await page.goto(`/estudiantes/${personaId}`);
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "+ Registrar Sesión" }).click();
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}/seguimiento/nuevo`));

    const observacionesIniciales = `Primera sesión de seguimiento ${fixtures.sello}`;
    await page.getByLabel("Observaciones de la sesión").fill(observacionesIniciales);
    await page.getByLabel("Acción tomada (opcional)").fill("Se coordinó con el docente tutor.");
    await page.getByRole("button", { name: "Guardar sesión" }).click();

    // Vuelve a la ficha -- la sesión recién creada aparece en el historial,
    // nace en estado "Atendido" (ver docstring de seguimiento/nuevo/page.tsx).
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}$`));
    await expect(page.getByText(observacionesIniciales)).toBeVisible();
    await expect(page.getByText("Atendido")).toBeVisible();

    // --- Editar la sesión (los 5 campos que solo son editables después de
    //     creada -- observaciones/acción tomada/acuerdos/próxima cita/estado) ---
    await page.getByRole("button", { name: "Editar" }).click();
    const observacionesEditadas = `Sesión editada ${fixtures.sello}`;
    await page.getByLabel("Observaciones de la sesión").fill(observacionesEditadas);
    await page.getByLabel("Acuerdos y compromisos").fill("El estudiante se compromete a asistir semanalmente.");
    await page.getByLabel("Próxima cita — fecha").fill(hoyISO());
    await page.getByLabel("Próxima cita — hora").fill("09:00");
    await page.getByLabel("Estado").selectOption("En proceso");
    await page.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(page.getByText(observacionesEditadas)).toBeVisible();
    await expect(page.getByText("El estudiante se compromete a asistir semanalmente.")).toBeVisible();
    await expect(page.getByText("En proceso")).toBeVisible();
    await expect(page.getByText(/Próxima cita:/)).toBeVisible();
  });
});
