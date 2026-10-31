const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

// "ngrok-skip-browser-warning" (presente en los 4 fetch de este archivo):
// solo importa cuando API_URL apunta a un túnel ngrok free tier (pruebas
// temporales) — sin este header, ngrok devuelve su propia página HTML de
// advertencia en vez de reenviar la request al backend real, y el fetch
// recibe HTML donde esperaba JSON. No-op contra cualquier otro backend.

function obtenerToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("aurora_token");
}

export function guardarToken(token: string) {
  localStorage.setItem("aurora_token", token);
}

export function borrarToken() {
  localStorage.removeItem("aurora_token");
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

// 🆕 Un 401 (token expirado, o revocado por un cambio de contraseña — ver
// la verificación de versión de credencial en docs/multi-tenancy-y-permisos.md)
// antes se propagaba como un ApiError más: cada page.tsx decidía (o, varias
// veces, NO decidía) qué hacer con él, y páginas sin su propio .catch()
// terminaban mostrando un estado vacío ("no hay casos pendientes") en vez de
// avisar que la sesión ya no es válida. api-client.ts no puede usar
// useRouter() directamente (no es un componente), así que avisa con un
// evento global; AuthContext.tsx lo escucha y cierra sesión/redirige — un
// solo lugar decide qué pasa con un 401, en vez de cada página por separado.
function avisarNoAutorizado() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("aurora:no-autorizado"));
  }
}

// 🆕 Bug real (hallazgo de sesión, reportado por el usuario con captura:
// "[object Object]" en vez de un mensaje) — `detail` de un error del
// backend NO siempre es un string. Un `raise HTTPException(detail="...")`
// escrito a mano sí lo es, pero un 422 que dispara la validación nativa de
// Pydantic (ej. `titulo: str = Field(min_length=2)`) trae
// `detail: [{"loc": [...], "msg": "...", "type": "..."}, ...]` — una LISTA.
// `new Error(listaDeObjetos)` coacciona ese array con `Array.prototype.
// toString()`, que junta cada item con ",": como un objeto plano no tiene
// `toString()` propio, el resultado es literalmente "[object Object]" (o
// "[object Object],[object Object]" con más de un error). Afecta a
// CUALQUIER POST/PATCH/PUT de la app que dispare una validación de Pydantic,
// no solo a un formulario puntual — por eso se arregla acá, en el único
// lugar que construye el mensaje, no en cada página que lo muestra.
function extraerMensajeError(cuerpo: any): string {
  const detail = cuerpo?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const mensajes = detail.map((d) => (typeof d?.msg === "string" ? d.msg : null)).filter(Boolean);
    if (mensajes.length > 0) return mensajes.join(" — ");
  }
  return "Error inesperado del servidor.";
}

async function lanzarSiError(res: Response): Promise<void> {
  if (res.ok) return;
  if (res.status === 401) avisarNoAutorizado();
  const cuerpo = await res.json().catch(() => ({}));
  throw new ApiError(res.status, extraerMensajeError(cuerpo));
}

// 🆕 Distinto del bug de arriba: acá `fetch()` ni siquiera llega a recibir
// una respuesta (backend caído, sin conexión, CORS) -- el navegador tira un
// TypeError genérico cuyo .message es literalmente "Failed to fetch" (en
// inglés, sea cual sea el idioma de la UI, porque es el motor del
// navegador, no texto nuestro). lanzarSiError() nunca llega a correr para
// este caso porque el propio `fetch()` es el que rechaza. Se traduce acá,
// en el único lugar que hace el fetch real, para que las ~15 pantallas que
// consumen apiClient no tengan que reconocer un TypeError de red aparte de
// un ApiError de negocio.
async function fetchSeguro(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "No se pudo conectar con el servidor. Verifica tu conexión e inténtalo de nuevo.");
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = obtenerToken();
  const res = await fetchSeguro(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "ngrok-skip-browser-warning": "true",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  await lanzarSiError(res);
  if (res.status === 204) return undefined as T;
  return res.json();
}

// multipart/form-data (subida de archivos) — nunca pasa por request(), que
// fuerza Content-Type: application/json; el navegador debe poner su propio
// boundary, así que aquí no se fija Content-Type en absoluto.
async function requestForm<T>(path: string, formData: FormData, method: "POST" | "PATCH" = "POST"): Promise<T> {
  const token = obtenerToken();
  const res = await fetchSeguro(path, {
    method,
    headers: {
      "ngrok-skip-browser-warning": "true",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });
  await lanzarSiError(res);
  return res.json();
}

// Descarga binaria (ej. la plantilla .xlsx) — la respuesta nunca es JSON.
async function requestBlob(path: string): Promise<Blob> {
  const token = obtenerToken();
  const res = await fetchSeguro(path, {
    headers: {
      "ngrok-skip-browser-warning": "true",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  await lanzarSiError(res);
  return res.blob();
}

// 🆕 Paginación real (docs/gaps-pendientes.md) — algunas pantallas
// (selector de alumnos al crear campaña/documento) necesitan el padrón
// COMPLETO para que el usuario busque/elija entre todos, no una página de
// la tabla. Pide páginas de 200 (el tope real del backend) hasta cubrir
// `total`, en vez de asumir que una sola página alcanza — así no trunca en
// silencio el padrón de un colegio con más de 200 alumnos.
async function obtenerTodasLasPaginas<T>(path: string): Promise<T[]> {
  const separador = path.includes("?") ? "&" : "?";
  const items: T[] = [];
  let skip = 0;
  const limite = 200;
  // Cota de seguridad (50 páginas = 10.000 filas) para nunca loopear sin fin
  // si el backend devolviera un `total` inconsistente.
  for (let i = 0; i < 50; i++) {
    const pagina = await request<{ total: number; items: T[] }>(`${path}${separador}skip=${skip}&limit=${limite}`);
    items.push(...pagina.items);
    if (items.length >= pagina.total || pagina.items.length === 0) break;
    skip += limite;
  }
  return items;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  getTodasLasPaginas: <T>(path: string) => obtenerTodasLasPaginas<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, formData: FormData) => requestForm<T>(path, formData, "POST"),
  descargarArchivo: (path: string) => requestBlob(path),
};

// Dispara la descarga de un Blob en el navegador con el nombre indicado —
// usado para la plantilla de importación, que el backend sirve como
// StreamingResponse binario, no como JSON.
export function descargarBlob(blob: Blob, nombreArchivo: string) {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}

// --- Login: el backend usa OAuth2PasswordRequestForm (form-urlencoded,
// campo "username" para el email) — no manda JSON como el resto. -------

// 🆕 Captcha del login (backend/core/captcha.py). La respuesta trae solo la
// imagen y un id opaco — el texto correcto nunca llega al navegador.
export type CaptchaLogin = { habilitado: boolean; captcha_id: string | null; imagen: string | null };

export async function obtenerCaptcha(): Promise<CaptchaLogin> {
  const res = await fetchSeguro("/auth/captcha", {
    headers: { "ngrok-skip-browser-warning": "true" },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(
      res.status,
      res.status === 429 ? "Pediste demasiados códigos seguidos. Espera un momento." : "No se pudo cargar el código de verificación.",
    );
  }
  return res.json();
}

// 🆕 "Olvidé mi contraseña" (backend: POST /auth/solicitar-recuperacion y
// /auth/resetear-password). Públicas, sin token. El backend responde lo
// mismo exista o no la cuenta, y solo envía el correo a un superadmin.
async function postPublico(path: string, cuerpo: unknown, mensaje429: string): Promise<{ mensaje: string }> {
  const res = await fetchSeguro(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
    body: JSON.stringify(cuerpo),
  });
  if (!res.ok) {
    const datos = await res.json().catch(() => ({}));
    throw new ApiError(res.status, res.status === 429 ? mensaje429 : extraerMensajeError(datos));
  }
  return res.json();
}

export function solicitarRecuperacion(email: string) {
  return postPublico(
    "/auth/solicitar-recuperacion",
    { email },
    "Ya pediste varios enlaces seguidos. Espera un minuto antes de volver a intentarlo.",
  );
}

export function resetearPassword(token: string, nuevaPassword: string) {
  return postPublico(
    "/auth/resetear-password",
    { token, nueva_password: nuevaPassword },
    "Demasiados intentos. Espera un momento antes de volver a intentarlo.",
  );
}

export type RespuestaCaptcha = { captchaId: string; respuesta: string };

export async function login(email: string, password: string, captcha?: RespuestaCaptcha) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  if (captcha) {
    body.set("captcha_id", captcha.captchaId);
    body.set("captcha_respuesta", captcha.respuesta);
  }

  const res = await fetchSeguro("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "ngrok-skip-browser-warning": "true",
    },
    body,
  });
  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    // 🆕 Bug de UX real (hallazgo de auditoría, sesión 2026-10-16/17): un 429
    // de rate limit lo arma `slowapi` con `{"error": "Rate limit exceeded: ..."}`
    // — nunca `.detail` — así que sin este caso especial caía en el mismo
    // fallback que un 401 de credenciales reales, y un usuario que solo
    // falló un par de veces veía "Email o contraseña incorrectos" en vez de
    // que se le avise que debe esperar antes de reintentar.
    const mensaje =
      res.status === 429
        ? "Demasiados intentos. Espera un momento antes de volver a intentarlo."
        : (typeof cuerpo.detail === "string" && cuerpo.detail.trim() ? cuerpo.detail : "Email o contraseña incorrectos.");
    throw new ApiError(res.status, mensaje);
  }
  const data: { access_token: string; token_type: string } = await res.json();
  guardarToken(data.access_token);
  return data;
}
