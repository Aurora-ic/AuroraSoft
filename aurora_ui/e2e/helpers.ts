import type { APIRequestContext } from "@playwright/test";

// Helpers de setup vía API directa (nunca vía UI) — mismo criterio que los
// scripts verificar_*_e2e.py del backend: arman el estado previo con
// llamadas HTTP puras y dejan que el test (la UI, Playwright) solo
// ejercite el flujo que de verdad se quiere probar. aurora_ui/ y backend/
// son proyectos independientes (ver CLAUDE.md) -- esto nunca lee el .env
// del backend directamente, solo variables de entorno propias de esta
// suite (ver playwright.config.ts / README de e2e/).

export const API = process.env.PLAYWRIGHT_API_URL || "http://127.0.0.1:8010/api";

export function requerirPasswordSuperadmin(): string {
  const clave = process.env.SUPERADMIN_PASSWORD;
  if (!clave) {
    throw new Error(
      "Define SUPERADMIN_PASSWORD (la misma del backend) como variable de entorno antes de correr " +
        "`npm run test:e2e` -- ver e2e/README.md.",
    );
  }
  return clave;
}

export async function login(ctx: APIRequestContext, email: string, password: string): Promise<string> {
  const res = await ctx.post(`${API}/auth/login`, { form: { username: email, password } });
  if (!res.ok()) throw new Error(`Login falló para ${email}: ${res.status()} ${await res.text()}`);
  const body = await res.json();
  return body.access_token as string;
}

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
  const tokenSuper = await login(ctx, process.env.SUPERADMIN_EMAIL || "admin@aurorasoft.com", requerirPasswordSuperadmin());
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

  const detalle = await (await ctx.get(`${API}/educativo/pruebas/${prueba.id}/completa`, { headers: hPsi })).json();
  const dim = detalle.dimensiones[0];
  await ctx.post(`${API}/educativo/baremos/`, {
    headers: hPsi,
    data: { dimension_id: dim.id, puntaje_minimo: 0, puntaje_maximo: 3, nivel: "Bajo", es_alerta: false },
  });

  const preguntasOrdenadas = [...dim.preguntas].sort((a: any, b: any) => a.orden - b.orden);
  return {
    sello,
    institucionId: institucion.id,
    psicologoEmail,
    psicologoPassword,
    psicologoToken: tokenPsi,
    superadminToken: tokenSuper,
    pruebaId: prueba.id,
    dimensionId: dim.id,
    preguntaIds: preguntasOrdenadas.map((p: any) => p.id),
    opcionCorrectaIds: preguntasOrdenadas.map((p: any) => p.opciones.find((o: any) => o.valor_puntuacion === 1).id),
  };
}

/** Inyecta la sesión directamente en localStorage (mismo criterio que
 * AuthContext -- ver contexts/AuthContext.tsx: decodifica el JWT en el
 * cliente, sin ningún round-trip) ANTES de navegar, para que los specs
 * que no están probando el login en sí mismos no tengan que repetir el
 * formulario (y, sobre todo, no vuelvan a golpear /auth/login, que tiene
 * rate limit). Solo login.spec.ts debe loguearse por la UI de verdad. */
export async function autenticarEnNavegador(page: import("@playwright/test").Page, token: string) {
  await page.addInitScript((t) => {
    window.localStorage.setItem("aurora_token", t);
  }, token);
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

  const detalle = await (await ctx.get(`${API}/educativo/pruebas/${prueba.id}/completa`, { headers: h })).json();
  const dim = detalle.dimensiones[0];
  await ctx.post(`${API}/educativo/baremos/`, {
    headers: h,
    data: { dimension_id: dim.id, puntaje_minimo: 0, puntaje_maximo: 3, nivel: esAlerta ? "Alto" : "Bajo", es_alerta: esAlerta },
  });

  const preguntasOrdenadas = [...dim.preguntas].sort((a: any, b: any) => a.orden - b.orden);
  return {
    pruebaId: prueba.id,
    preguntaIds: preguntasOrdenadas.map((p: any) => p.id),
    opcionCorrectaIds: preguntasOrdenadas.map((p: any) => p.opciones.find((o: any) => o.valor_puntuacion === 1).id),
  };
}

/** Finaliza un examen completo vía API (guardar respuestas + finalizar) --
 * usado para dejar una Inscripcion YA "Finalizado" sin que completar el
 * examen sea lo que el spec está probando. */
export async function finalizarExamenCompleto(
  ctx: APIRequestContext, tokenExamen: string, preguntaIds: number[], opcionIds: number[],
): Promise<void> {
  await ctx.post(`${API}/educativo/comenzar-test/${tokenExamen}`, {
    data: { nombre_completo: "ZZPLAYWRIGHT Alumno", edad: 15, sexo: "Femenino", poblacion: "Secundaria", acepta_terminos: true },
  });
  const respuestas = preguntaIds.map((pid, i) => ({ pregunta_id: pid, opcion_id: opcionIds[i] }));
  await ctx.post(`${API}/educativo/examen/${tokenExamen}/guardar`, { data: { respuestas } });
  await ctx.post(`${API}/educativo/examen/${tokenExamen}/finalizar`);
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
