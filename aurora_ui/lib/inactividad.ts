// 🆕 (sesión 2026-11-01, punto 3 del análisis de UI/UX) Bloqueo por
// inactividad — estado compartido entre pestañas vía localStorage. Ver
// components/auth/BloqueoInactividad.tsx.
//
// Por qué: el token dura 7 días (backend/core/security.py) y en un colegio
// la computadora de la sala de profesores es compartida; sin esto,
// cualquiera que se sentara frente a una sesión abierta veía expedientes
// clínicos. Se BLOQUEA (la pantalla queda cubierta y hay que reingresar la
// contraseña), no se cierra la sesión: lo que se estaba escribiendo sigue en
// la página al desbloquear.

// 15 min (sesión 2026-11-02, antes 20): el estándar de la industria para
// datos sensibles — PCI DSS 4.0 req. 8.2.8 y la línea base FedRAMP del
// control AC-11 de NIST SP 800-53 fijan 15 min; en historias clínicas
// electrónicas lo habitual es 10–15. Aquí el costo de un valor corto es bajo:
// se BLOQUEA (no se pierde lo escrito) y teclear, desplazarse o mover el ratón
// cuentan como actividad, así que redactar un informe largo nunca bloquea.
export const MINUTOS_INACTIVIDAD = 15;
export const SEGUNDOS_AVISO = 60;

const CLAVE_ACTIVIDAD = "aurora_ultima_actividad";
const CLAVE_BLOQUEO = "aurora_bloqueado";

export const LIMITE_MS = MINUTOS_INACTIVIDAD * 60 * 1000;

export function leerUltimaActividad(): number | null {
  if (typeof window === "undefined") return null;
  const valor = Number(localStorage.getItem(CLAVE_ACTIVIDAD));
  return Number.isFinite(valor) && valor > 0 ? valor : null;
}

export function marcarActividad(): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CLAVE_ACTIVIDAD, String(Date.now()));
}

export function estaBloqueado(): boolean {
  return typeof window !== "undefined" && localStorage.getItem(CLAVE_BLOQUEO) === "1";
}

export function bloquear(): void {
  localStorage.setItem(CLAVE_BLOQUEO, "1");
}

/** Login correcto (en la pantalla de login o al desbloquear): actividad
 * nueva y sin bloqueo. */
export function reiniciarInactividad(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CLAVE_BLOQUEO);
  marcarActividad();
}

/** Cerrar sesión: no queda nada que bloquear. */
export function olvidarInactividad(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(CLAVE_BLOQUEO);
  localStorage.removeItem(CLAVE_ACTIVIDAD);
}

export const CLAVES_INACTIVIDAD = [CLAVE_ACTIVIDAD, CLAVE_BLOQUEO];
