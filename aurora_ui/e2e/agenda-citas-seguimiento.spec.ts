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

    await page.getByRole("button", { name: "Nueva cita" }).first().click();
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}/cita/nueva`));
    const motivoCita = `Entrevista de seguimiento ${fixtures.sello}`;
    await page.getByLabel("Motivo").fill(motivoCita);
    await page.getByLabel("Fecha").fill(hoyISO());
    await page.getByLabel("Hora").fill("10:00");
    await page.getByRole("button", { name: "Agendar cita" }).click();

    // Vuelve a la ficha -- la cita recién creada aparece "Programada".
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}$`));
    // 🔧 (sesión 2026-11-02) La ficha rediseñada repite textos en varios
    // bloques (indicadores, citas, agenda): se acota al bloque "Citas programadas".
    const bloqueCitas = page.locator("section", { has: page.getByRole("heading", { name: "Citas programadas" }) });
    await expect(bloqueCitas.getByText(`Motivo: ${motivoCita}`)).toBeVisible();
    await expect(bloqueCitas.getByText("Programada", { exact: true })).toBeVisible();

    // --- Reprogramar desde la ficha (formulario inline) ---
    await bloqueCitas.getByRole("button", { name: "Reprogramar" }).click();
    await bloqueCitas.getByLabel("Nueva fecha").fill(hoyISO());
    await bloqueCitas.getByLabel("Nueva hora").fill("15:30");
    await bloqueCitas.getByRole("button", { name: "Guardar" }).click();
    await expect(bloqueCitas.getByRole("button", { name: "Reprogramar" })).toBeVisible(); // vuelve a aparecer tras guardar

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
    // 🔧 (sesión 2026-11-02) Al abrir el formulario el botón "Reprogramar" se
    // oculta, así que `tarjetaAgenda` deja de coincidir: la tarjeta en
    // edición se ubica por el motivo + el campo de fecha.
    const tarjetaEnEdicion = page
      .locator("div")
      .filter({ hasText: motivoCita })
      .filter({ has: page.locator('input[type="date"]') })
      .last();
    await tarjetaEnEdicion.locator('input[type="date"]').fill(hoyISO());
    await tarjetaEnEdicion.locator('input[type="time"]').fill("16:45");
    await tarjetaEnEdicion.getByRole("button", { name: "Guardar" }).click();
    // La agenda muestra la hora en 12 h con rango ("04:45 p. m. – 05:30 p. m.").
    await expect(tarjetaAgenda.getByText(/04:45\s*p\.\s*m\./)).toBeVisible();

    // --- Cancelar desde /agenda -- la otra mitad de este control. ---
    // 🆕 (sesión 2026-11-01) Diálogo de confirmación propio, ya no window.confirm.
    await tarjetaAgenda.getByRole("button", { name: "Cancelar" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Cancelar cita" }).click();
    // Cancelada, la cita sale de la agenda (GET /citas/mi-agenda ya no la
    // devuelve; el diálogo lo avisa: "sale de la agenda del día").
    await expect(page.getByText(motivoCita)).toHaveCount(0);
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
    await page.getByRole("button", { name: "Registrar sesión" }).first().click();
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}/seguimiento/nuevo`));

    const observacionesIniciales = `Primera sesión de seguimiento ${fixtures.sello}`;
    await page.getByLabel("Observaciones de la sesión").fill(observacionesIniciales);
    await page.getByLabel("Acción tomada (opcional)").fill("Se coordinó con el docente tutor.");
    await page.getByRole("button", { name: "Guardar sesión" }).click();

    // Vuelve a la ficha -- la sesión recién creada aparece en el historial,
    // nace en estado "Atendido" (ver docstring de seguimiento/nuevo/page.tsx).
    await page.waitForURL(new RegExp(`/estudiantes/${personaId}$`));
    // 🔧 Acotado al bloque del historial de sesiones (la ficha repite textos).
    const bloqueSesiones = page.locator("section", { has: page.getByRole("heading", { name: "Historial de sesiones de seguimiento" }) });
    await expect(bloqueSesiones.getByText(observacionesIniciales)).toBeVisible();
    await expect(bloqueSesiones.getByText("Atendido", { exact: true })).toBeVisible();

    // --- Editar la sesión (los 5 campos que solo son editables después de
    //     creada -- observaciones/acción tomada/acuerdos/próxima cita/estado) ---
    await bloqueSesiones.getByRole("button", { name: "Editar" }).click();
    const observacionesEditadas = `Sesión editada ${fixtures.sello}`;
    await bloqueSesiones.getByLabel("Observaciones de la sesión").fill(observacionesEditadas);
    await bloqueSesiones.getByLabel("Acuerdos y compromisos").fill("El estudiante se compromete a asistir semanalmente.");
    await bloqueSesiones.getByLabel("Próxima cita — fecha").fill(hoyISO());
    await bloqueSesiones.getByLabel("Próxima cita — hora").fill("09:00");
    await bloqueSesiones.getByLabel("Estado").selectOption("En proceso");
    await bloqueSesiones.getByRole("button", { name: "Guardar cambios" }).click();

    await expect(bloqueSesiones.getByText(observacionesEditadas)).toBeVisible();
    await expect(bloqueSesiones.getByText("El estudiante se compromete a asistir semanalmente.")).toBeVisible();
    await expect(bloqueSesiones.getByText("En proceso", { exact: true })).toBeVisible();
    await expect(bloqueSesiones.getByText(/Próxima cita:/)).toBeVisible();
  });
});
