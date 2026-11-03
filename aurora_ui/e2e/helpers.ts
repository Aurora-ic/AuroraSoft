import { request, type APIRequestContext } from "@playwright/test";

// Helpers de setup vía API directa (nunca vía UI) — mismo criterio que los
// scripts verificar_*_e2e.py del backend: arman el estado previo con
// llamadas HTTP puras y dejan que el test (la UI, Playwright) solo
// ejercite el flujo que de verdad se quiere probar. aurora_ui/ y backend/
// son proyectos independientes (ver CLAUDE.md) -- esto nunca lee el .env
// del backend directamente, solo variables de entorno propias de esta
// suite (ver playwright.config.ts / README de e2e/).

export const API = process.env.PLAYWRIGHT_API_URL || "http://127.0.0.1:8010/api";

// 🆕 (sesión 2026-11-01) Si están definidas, se usa la cuenta superadmin
// DEDICADA a e2e (E2E_SUPERADMIN_EMAIL/E2E_SUPERADMIN_PASSWORD, la misma
// que usan los tests del backend — ver backend/tests/__init__.py y
// backend/seeds/seed_superadmin_e2e.py) en vez del superadmin real, cuya
// contraseña puede haber cambiado en la BD.
export function emailSuperadmin(): string {
  return process.env.E2E_SUPERADMIN_EMAIL || process.env.SUPERADMIN_EMAIL || "admin@aurorasoft.com";
}

export function requerirPasswordSuperadmin(): string {
  const clave = process.env.E2E_SUPERADMIN_EMAIL ? process.env.E2E_SUPERADMIN_PASSWORD : process.env.SUPERADMIN_PASSWORD;
  if (!clave) {
    throw new Error(
      "Define E2E_SUPERADMIN_EMAIL/E2E_SUPERADMIN_PASSWORD (recomendado) o SUPERADMIN_PASSWORD como variables de entorno " +
        "antes de correr `npm run test:e2e` -- ver e2e/README.md.",
    );
  }
  return clave;
}

export async function login(_ctx: APIRequestContext, email: string, password: string): Promise<string> {
  // 🆕 (sesión 2026-11-02) Cada login en su PROPIO contexto: un
  // APIRequestContext guarda cookies como un navegador, y el backend revoca
  // la sesión cuya cookie de renovación llega a un login nuevo (el caso real
  // es desbloquear la pantalla — ver backend/core/sesiones.py). Con un solo
  // contexto, el login del psicólogo revocaba la sesión del superadmin del
  // mismo setup y su token cacheado moría.
  const aislado = await request.newContext();
  try {
    const res = await aislado.post(`${API}/auth/login`, { form: { username: email, password } });
    if (!res.ok()) throw new Error(`Login falló para ${email}: ${res.status()} ${await res.text()}`);
    const body = await res.json();
    return body.access_token as string;
  } finally {
    await aislado.dispose();
  }
}

// Lo que estos helpers leen de GET /educativo/pruebas/{id}/completa.
type PruebaCompletaApi = {
  dimensiones: { id: number; preguntas: { id: number; orden: number; opciones: { id: number; valor_puntuacion: number }[] }[] }[];
};

function auth(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export type FixturesE2E = {
  sello: string;
  institucionId: number;
  psicologoEmail: string;
  psicologoPassword: string;
  // 🔒 Cacheado aquí a propósito: /auth/login tiene rate limit (5/min, ver
  // core.limiter) y con 4 specs cada uno pidiendo su propio token la suite
  // entera lo superaba sola. Cada spec reusa ESTE token para su setup por
  // API en vez de volver a loguearse -- solo login.spec.ts golpea el
  // endpoint de login de verdad (es lo que prueba).
  psicologoToken: string;
  // 🆕 Mismo criterio que psicologoToken -- crearFixturesBase ya hace un
  // login de superadmin para crear la institución; cachearlo acá evita que
  // cada spec que necesita algo solo-superadmin (crear un TipoDocumento,
  // /master) tenga que loguearse de nuevo y sumar al mismo rate limit.
  superadminToken: string;
  pruebaId: number;
  dimensionId: number;
  preguntaIds: number[];
  opcionCorrectaIds: number[]; // la opción con valor_puntuacion=1, en el mismo orden que preguntaIds
};

/** Crea una institución + psicólogo + una prueba mínima (1 dimensión,
 * correcto_incorrecto, 3 ítems, un único baremo que cubre todo el rango sin
 * alerta) -- exactamente el mismo patrón que crear_prueba_con_un_baremo en
 * tests/verificar_reproceso_informe_e2e.py del backend, portado a Node. */
export async function crearFixturesBase(ctx: APIRequestContext, sello: string): Promise<FixturesE2E> {
  const tokenSuper = await login(ctx, emailSuperadmin(), requerirPasswordSuperadmin());
  const hSuper = auth(tokenSuper);

  const institucion = await (
    await ctx.post(`${API}/instituciones/`, {
      headers: hSuper,
      data: { nombre: `ZZPLAYWRIGHT ${sello}`, email_contacto: `zzpw.${sello.toLowerCase()}@ejemplo.com` },
    })
  ).json();

  const psicologoEmail = `zzpw.${sello.toLowerCase()}.psi@ejemplo.com`;
  const psicologoPassword = "ClaveDePrueba123";
  await ctx.post(`${API}/auth/registro`, {
    headers: hSuper,
    data: {
      email: psicologoEmail, password: psicologoPassword, nombre_completo: `ZZPLAYWRIGHT Psi ${sello}`,
      rol: "psicologo", institucion_id: institucion.id,
    },
  });
  const tokenPsi = await login(ctx, psicologoEmail, psicologoPassword);
  const hPsi = auth(tokenPsi);

  const prueba = await (
    await ctx.post(`${API}/educativo/pruebas/`, {
      headers: hPsi,
      data: {
        nombre_tecnico: `ZZPLAYWRIGHT-${sello}`, nombre_publico: "Prueba de prueba (Playwright)",
        escala_minima: 0, escala_maxima: 1, modo_calculo: "correcto_incorrecto",
      },
    })
  ).json();

  const opciones = [{ texto_opcion: "No", valor_puntuacion: 0 }, { texto_opcion: "Sí", valor_puntuacion: 1 }];
  const preguntasCarga = [1, 2, 3].map((i) => ({ texto_pregunta: `Ítem ${i}`, orden: i, nombre_dimension: "D", opciones }));
  await ctx.post(`${API}/educativo/pruebas/carga-masiva/`, {
    headers: hPsi,
    data: { prueba_id: prueba.id, dimensiones: [{ nombre: "D" }], preguntas: preguntasCarga },
  });

  const detalle: PruebaCompletaApi = await (await ctx.get(`${API}/educativo/pruebas/${prueba.id}/completa`, { headers: hPsi })).json();
  const dim = detalle.dimensiones[0];
  await ctx.post(`${API}/educativo/baremos/`, {
    headers: hPsi,
    data: { dimension_id: dim.id, puntaje_minimo: 0, puntaje_maximo: 3, nivel: "Bajo", es_alerta: false },
  });

  const preguntasOrdenadas = [...dim.preguntas].sort((a, b) => a.orden - b.orden);
  return {
    sello,
    institucionId: institucion.id,
    psicologoEmail,
    psicologoPassword,
    psicologoToken: tokenPsi,
    superadminToken: tokenSuper,
    pruebaId: prueba.id,
    dimensionId: dim.id,
    preguntaIds: preguntasOrdenadas.map((p) => p.id),
    opcionCorrectaIds: preguntasOrdenadas.map((p) => p.opciones.find((o) => o.valor_puntuacion === 1)!.id),
  };
}

/** Deja la sesión puesta en el navegador ANTES de navegar, para que los
 * specs que no están probando el login en sí mismos no tengan que repetir
 * el formulario (y, sobre todo, no vuelvan a golpear /auth/login, que tiene
 * rate limit). Solo login.spec.ts debe loguearse por la UI de verdad.
 *
 * 🆕 (sesión 2026-11-02) El token ya no vive en localStorage: va en la
 * cookie httpOnly `aurora_sesion` (backend/core/sesiones.py). Se pone esa
 * cookie (en localhost Y 127.0.0.1: las cookies no distinguen puerto, y el
 * frontend puede apuntar a cualquiera de los dos) más la sesión pública que
 * AuthContext lee para pintar la interfaz. No hay cookie de renovación: el
 * acceso dura 15 min, de sobra para un spec. */
export async function autenticarEnNavegador(page: import("@playwright/test").Page, token: string) {
  const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
  await page.context().addCookies(
    ["localhost", "127.0.0.1"].map((domain) => ({
      name: "aurora_sesion", value: token, domain, path: "/api", httpOnly: true, sameSite: "Lax" as const,
    })),
  );
  const sesion = { email: payload.sub, rol: payload.rol, institucionId: payload.institucion_id ?? null };
  await page.addInitScript((s) => {
    window.localStorage.setItem("aurora_sesion", s);
  }, JSON.stringify(sesion));
}

export type PruebaConBaremo = {
  pruebaId: number;
  preguntaIds: number[];
  opcionCorrectaIds: number[]; // la opción con valor_puntuacion=1, mismo orden que preguntaIds
};

/** Variante de la prueba de `crearFixturesBase` con control sobre
 * `es_alerta` del único baremo -- usada por los specs que necesitan un
 * examen que quede RETENIDO al finalizar (para probar revisar/liberar
 * informe), a diferencia del baremo "Bajo" sin alerta de los fixtures
 * base, que siempre libera solo. */
export async function crearPruebaConBaremo(
  ctx: APIRequestContext, token: string, nombreTecnico: string, esAlerta: boolean,
): Promise<PruebaConBaremo> {
  const h = auth(token);
  const prueba = await (
    await ctx.post(`${API}/educativo/pruebas/`, {
      headers: h,
      data: {
        nombre_tecnico: nombreTecnico, nombre_publico: "Prueba de prueba (Playwright)",
        escala_minima: 0, escala_maxima: 1, modo_calculo: "correcto_incorrecto",
      },
    })
  ).json();

  const opciones = [{ texto_opcion: "No", valor_puntuacion: 0 }, { texto_opcion: "Sí", valor_puntuacion: 1 }];
  const preguntasCarga = [1, 2, 3].map((i) => ({ texto_pregunta: `Ítem ${i}`, orden: i, nombre_dimension: "D", opciones }));
  await ctx.post(`${API}/educativo/pruebas/carga-masiva/`, {
    headers: h, data: { prueba_id: prueba.id, dimensiones: [{ nombre: "D" }], preguntas: preguntasCarga },
  });

  const detalle: PruebaCompletaApi = await (await ctx.get(`${API}/educativo/pruebas/${prueba.id}/completa`, { headers: h })).json();
  const dim = detalle.dimensiones[0];
  await ctx.post(`${API}/educativo/baremos/`, {
    headers: h,
    data: { dimension_id: dim.id, puntaje_minimo: 0, puntaje_maximo: 3, nivel: esAlerta ? "Alto" : "Bajo", es_alerta: esAlerta },
  });

  const preguntasOrdenadas = [...dim.preguntas].sort((a, b) => a.orden - b.orden);
  return {
    pruebaId: prueba.id,
    preguntaIds: preguntasOrdenadas.map((p) => p.id),
    opcionCorrectaIds: preguntasOrdenadas.map((p) => p.opciones.find((o) => o.valor_puntuacion === 1)!.id),
  };
}

/** Finaliza un examen completo vía API (guardar respuestas + finalizar) --
 * usado para dejar una Inscripcion YA "Finalizado" sin que completar el
 * examen sea lo que el spec está probando. */
export async function finalizarExamenCompleto(
  ctx: APIRequestContext, tokenExamen: string, preguntaIds: number[], opcionIds: number[],
): Promise<void> {
  // 🆕 (sesión 2026-11-02) Cada paso comprueba su respuesta: antes un fallo
  // (p. ej. un campo nuevo exigido por comenzar-test) se perdía en silencio
  // y el spec fallaba mucho después, buscando un informe que nunca existió.
  async function paso(nombre: string, res: Awaited<ReturnType<APIRequestContext["post"]>>) {
    if (!res.ok()) throw new Error(`Examen ${tokenExamen}: ${nombre} falló (${res.status()}): ${await res.text()}`);
  }
  await paso("comenzar-test", await ctx.post(`${API}/educativo/comenzar-test/${tokenExamen}`, {
    data: { nombre_completo: "ZZPLAYWRIGHT Alumno", edad: 15, sexo: "Femenino", poblacion: "Secundaria", acepta_terminos: true },
  }));
  const respuestas = preguntaIds.map((pid, i) => ({ pregunta_id: pid, opcion_id: opcionIds[i] }));
  await paso("guardar", await ctx.post(`${API}/educativo/examen/${tokenExamen}/guardar`, { data: { respuestas } }));
  await paso("finalizar", await ctx.post(`${API}/educativo/examen/${tokenExamen}/finalizar`));
}

/** El informe de un examen finalizado lo genera el worker de Celery, en
 * segundo plano, y la ficha del alumno solo lista informes YA generados.
 * Sin esperar, un spec que abre la ficha justo después de finalizar puede
 * no ver nada (depende de cuánta cola tenga el worker). Requiere un worker
 * corriendo -- ver e2e/README.md. */
export async function esperarInformeGenerado(
  ctx: APIRequestContext, token: string, personaId: number, minimo = 1, timeoutMs = 60_000,
): Promise<void> {
  const limite = Date.now() + timeoutMs;
  while (Date.now() < limite) {
    const res = await ctx.get(`${API}/educativo/personas/${personaId}/informes`, { headers: auth(token) });
    if (res.ok() && (await res.json()).length >= minimo) return;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`El informe de la persona ${personaId} no se generó en ${timeoutMs / 1000} s. ¿Está corriendo el worker de Celery?`);
}

/** Crea un alumno en el padrón + consentimiento del apoderado vía API --
 * usado por los specs que necesitan un alumno YA MATRICULABLE sin que
 * crearlo sea lo que se está probando. */
export async function crearAlumnoConConsentimiento(
  ctx: APIRequestContext, token: string, institucionId: number, nombres: string, apellidos: string,
): Promise<number> {
  const h = auth(token);
  const persona = await (
    await ctx.post(`${API}/admin/personas/`, {
      headers: h, data: { institucion_id: institucionId, nombres, apellidos, tipo_perfil: "estudiante" },
    })
  ).json();
  await ctx.post(`${API}/admin/personas/${persona.id}/consentimiento`, {
    headers: h,
    data: { persona_id: persona.id, institucion_id: institucionId, otorgado_por_nombre: "Apoderado de prueba", tipo_otorgante: "apoderado" },
  });
  return persona.id;
}

/** Crea un `TipoDocumento` (catálogo global, solo-superadmin — no tiene UI,
 * "el platform owner decide la taxonomía global, cada colegio decide su
 * propia estructura" (docs/motor-documentos.md)) -- necesario para que el
 * spec de documentos pueda armar una `PlantillaDocumento` propia desde
 * /documentos, mismo criterio que el resto de helpers: lo que NO es el
 * flujo bajo prueba se arma por API.
 *
 * Recibe el token de superadmin YA logueado (fixtures.superadminToken) en
 * vez de loguearse de nuevo -- /auth/login tiene rate limit (5/min) y cada
 * login de más suma contra el mismo límite que ya comparte toda la suite. */
export async function crearTipoDocumento(ctx: APIRequestContext, tokenSuperadmin: string, sello: string): Promise<number> {
  const tipo = await (
    await ctx.post(`${API}/documentos/tipos`, {
      headers: auth(tokenSuperadmin),
      data: {
        clave: `zzplaywright-${sello.toLowerCase()}`,
        nombre: `ZZPLAYWRIGHT Tipo ${sello}`,
        alcances_permitidos: "personas_especificas, estructura_academica",
        visibilidades_permitidas: "confidencial_clinico, compartible_colegio",
      },
    })
  ).json();
  return tipo.id as number;
}

/** Crea una campaña + matricula a `personaId` y devuelve el token mágico
 * del examen -- para los specs que necesitan un examen YA EN CURSO sin que
 * crear la campaña sea lo que se está probando. */
export async function crearCampanaYMatricular(
  ctx: APIRequestContext, token: string, institucionId: number, pruebaId: number, nombreGrupo: string, personaId: number,
): Promise<string> {
  const h = auth(token);
  const campana = await (
    await ctx.post(`${API}/educativo/campanas/`, { headers: h, data: { prueba_id: pruebaId, nombre_grupo: nombreGrupo, institucion_id: institucionId } })
  ).json();
  const matricula = await (
    await ctx.post(`${API}/educativo/campanas/${campana.id}/matricular-roster`, { headers: h, data: [personaId] })
  ).json();
  return matricula.generados[0].token as string;
}
