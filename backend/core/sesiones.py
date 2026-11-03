# core/sesiones.py
#
# 🆕 (sesión 2026-11-02) Sesiones del lado del servidor. Antes:
#   · un JWT de 7 días, guardado en localStorage (legible por cualquier
#     script inyectado en la página);
#   · "cerrar sesión" solo lo borraba del navegador — seguía valiendo;
#   · el bloqueo por inactividad existía solo en el navegador: quitar la
#     capa con las herramientas de desarrollo devolvía la sesión entera.
#
# Ahora (ver también modulos/auth/models.py:SesionUsuario):
#   · ACCESO: JWT de ACCESS_TOKEN_MINUTOS (15) con `sid`, en la cookie
#     httpOnly `aurora_sesion` (path /api). Cada petición comprueba la fila
#     de la sesión en la misma consulta que ya trae al usuario (core/deps.py).
#   · RENOVACIÓN: valor aleatorio en la cookie httpOnly `aurora_renovacion`,
#     path /api/auth (solo viaja a login/renovar/bloquear/cerrar). En la BD
#     solo su SHA-256. Vida máxima SESION_HORAS (12) y caduca si pasa
#     SESION_INACTIVIDAD_MINUTOS (60) sin renovarse.
#   · CSRF: con cookies, el navegador las adjunta solo. Toda petición que
#     cambia algo y se autentica por cookie exige la cabecera
#     `X-Aurora-Cliente` — un formulario de otro sitio no puede ponerla, y un
#     fetch de otro origen con esa cabecera dispara un preflight que el CORS
#     (lista explícita de orígenes) rechaza. Más SameSite=Lax.
#   · `Authorization: Bearer` sigue aceptándose (Swagger, los e2e, scripts):
#     agregar primero, retirar después. Para esa vía no aplica el CSRF (un
#     navegador nunca la adjunta solo).
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response

COOKIE_ACCESO = "aurora_sesion"
COOKIE_RENOVACION = "aurora_renovacion"
CABECERA_CSRF = "x-aurora-cliente"
PATH_ACCESO = "/api"
PATH_RENOVACION = "/api/auth"

SESION_HORAS = float(os.getenv("SESION_HORAS", "12"))
SESION_INACTIVIDAD_MINUTOS = float(os.getenv("SESION_INACTIVIDAD_MINUTOS", "60"))

_ENTORNO = os.getenv("ENTORNO", "development")
# Secure por defecto fuera de desarrollo (HTTPS). En desarrollo, localhost
# por HTTP no podría guardar una cookie Secure en todos los navegadores.
COOKIE_SECURE = os.getenv("SESION_COOKIE_SECURE", "false" if _ENTORNO == "development" else "true").strip().lower() in ("true", "1", "si", "sí")
# 'lax' sirve mientras frontend y API compartan sitio (app.x.pe/api.x.pe, o
# localhost:3000/localhost:8000 — el puerto no cuenta). Si la API vive en
# otro sitio (un túnel ngrok), hace falta 'none' (y entonces Secure).
COOKIE_SAMESITE = os.getenv("SESION_COOKIE_SAMESITE", "lax").strip().lower()

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def nuevo_id_sesion() -> str:
    return secrets.token_urlsafe(32)


def nuevo_token_renovacion() -> str:
    return secrets.token_urlsafe(48)


def hash_renovacion(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def fijar_cookies(respuesta: Response, token_acceso: str, token_renovacion: Optional[str], minutos_acceso: float) -> None:
    respuesta.set_cookie(
        COOKIE_ACCESO, token_acceso, max_age=int(minutos_acceso * 60), path=PATH_ACCESO,
        httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
    )
    if token_renovacion is not None:
        respuesta.set_cookie(
            COOKIE_RENOVACION, token_renovacion, max_age=int(SESION_HORAS * 3600), path=PATH_RENOVACION,
            httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE,
        )


def borrar_cookies(respuesta: Response) -> None:
    respuesta.delete_cookie(COOKIE_ACCESO, path=PATH_ACCESO, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)
    respuesta.delete_cookie(COOKIE_RENOVACION, path=PATH_RENOVACION, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE)


def peticion_csrf_valida(request: Request) -> bool:
    """True si la petición no cambia nada o trae la cabecera anti-CSRF."""
    return request.method.upper() in METODOS_SEGUROS or bool(request.headers.get(CABECERA_CSRF))


def motivo_sesion_invalida(sesion, usuario, ahora: Optional[datetime] = None) -> Optional[str]:
    """None si la sesión sigue viva para EMITIR o ACEPTAR un acceso; si no,
    el motivo (para el log y los tests). No mira la inactividad: eso solo
    se exige al renovar (`motivo_renovacion_invalida`)."""
    ahora = ahora or ahora_utc()
    if sesion is None:
        return "inexistente"
    if sesion.revocada_en is not None:
        return "revocada"
    if sesion.bloqueada_en is not None:
        return "bloqueada"
    if sesion.expira_en <= ahora:
        return "vencida"
    if usuario is None or not usuario.activo:
        return "usuario_inactivo"
    if (sesion.token_version or 0) != (usuario.token_version or 0):
        return "credenciales_cambiadas"
    return None


def motivo_renovacion_invalida(sesion, usuario, ahora: Optional[datetime] = None) -> Optional[str]:
    ahora = ahora or ahora_utc()
    motivo = motivo_sesion_invalida(sesion, usuario, ahora)
    if motivo:
        return motivo
    if sesion.ultimo_uso + timedelta(minutes=SESION_INACTIVIDAD_MINUTOS) <= ahora:
        return "inactiva"
    return None
