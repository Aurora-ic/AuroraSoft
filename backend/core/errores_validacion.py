"""Respuesta 422 sin devolver lo que mandó el cliente.

🆕 (sesión 2026-11-07, revisión de seguridad previa al piloto) El manejador
por defecto de FastAPI responde un 422 con `exc.errors()` tal cual, y cada
error de Pydantic v2 trae `input`: el valor recibido. Con eso:

- `POST /auth/resetear-password` con una contraseña nueva de 7 caracteres
  devolvía la contraseña en la respuesta;
- un alta de alumno mal formada devolvía el cuerpo entero (nombres, DNI,
  datos familiares) — que además queda en logs de proxies, en Sentry si una
  integración lo captura, y en las herramientas del navegador.

Aquí se conserva lo que el frontend usa (`msg`, ver
aurora_ui/lib/api-client.extraerMensajeError) y lo que sirve para depurar
sin datos (`type`, `loc`, `ctx` con el límite que se violó), y se quitan
`input` y `url` (un enlace a la documentación de Pydantic, en inglés).
"""
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

CAMPOS_PERMITIDOS = ("type", "loc", "msg", "ctx")


def limpiar_errores(errores):
    limpios = []
    for error in errores:
        if not isinstance(error, dict):
            continue
        limpio = {k: error[k] for k in CAMPOS_PERMITIDOS if k in error}
        ctx = limpio.get("ctx")
        if isinstance(ctx, dict):
            # `error` es la excepción del validador (su texto ya está en msg);
            # el resto son los límites (min_length, pattern, ...), sin datos.
            limpio["ctx"] = {k: v for k, v in ctx.items() if k != "error"} or None
            if limpio["ctx"] is None:
                del limpio["ctx"]
        limpios.append(limpio)
    return limpios


async def manejador_validacion(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(limpiar_errores(exc.errors()))})
