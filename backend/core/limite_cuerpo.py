# core/limite_cuerpo.py
#
# 🆕 (sesión 2026-11-05, A2 de la revisión de seguridad previa al piloto)
# Tope de tamaño del cuerpo de TODA petición, aplicado ANTES de que FastAPI
# lo lea.
#
# Por qué no alcanzaba con `core/subida_archivos.leer_archivo_con_limite`:
# FastAPI lee el formulario multipart COMPLETO (`await request.form()`, que
# Starlette vuelca a un temporal en disco) antes de resolver `Depends(...)`
# — ver `get_request_handler` en fastapi/routing.py. Ese tope corre dentro
# del endpoint, o sea DESPUÉS de haber escrito todo el cuerpo a disco y
# antes incluso de saber si hay sesión. Cualquiera, sin iniciar sesión, podía
# mandar varios GB a una ruta de subida y llenar el disco del servidor.
# `leer_archivo_con_limite` se queda: es el tope exacto del endpoint (con su
# mensaje propio); este middleware es la barrera previa, gruesa.
#
# Dos cortes:
#   - `Content-Length` declarado mayor al tope -> 413 sin leer ni un byte.
#   - sin `Content-Length` (transfer-encoding chunked) -> se cuentan los
#     bytes a medida que la app los pide y se corta con 413 apenas el
#     acumulado supera el tope.
#
# El tope de cada ruta de subida lo arma `main.py` a partir del tope del
# propio endpoint + `MARGEN_MULTIPART_BYTES` (las cabeceras y separadores del
# multipart ocupan algo más que el archivo). El resto de las rutas usa
# `LIMITE_CUERPO_POR_DEFECTO_BYTES`. tests/test_limite_cuerpo_unitario.py
# falla si aparece una ruta con UploadFile sin su tope declarado.
import json
import re

from fastapi import HTTPException, status

LIMITE_CUERPO_POR_DEFECTO_BYTES = 1 * 1024 * 1024  # 1 MiB — el JSON más grande de la API es texto de pocos KB
MARGEN_MULTIPART_BYTES = 64 * 1024  # cabeceras y separadores del multipart


def _detalle_413(limite_bytes: int) -> str:
    if limite_bytes >= 1024 * 1024:
        cifra = f"{limite_bytes / (1024 * 1024):.0f} MB"
    else:
        cifra = f"{limite_bytes // 1024} KB"
    return f"La petición supera el tamaño máximo permitido ({cifra})."


def _patron_de_plantilla(plantilla: str) -> "re.Pattern[str]":
    """'/api/x/{id}/firma' -> ^/api/x/[^/]+/firma$ (mismo formato de ruta
    que `APIRoute.path`, así la tabla de main.py se escribe con las rutas tal
    cual las lista FastAPI)."""
    partes = re.split(r"(\{[^}]+\})", plantilla)
    cuerpo = "".join("[^/]+" if p.startswith("{") else re.escape(p) for p in partes)
    return re.compile(f"^{cuerpo}$")


class MiddlewareLimiteCuerpo:
    """Middleware ASGI puro (no `BaseHTTPMiddleware`: ese envoltorio lee y
    re-empaqueta el cuerpo, justo lo que aquí se quiere evitar)."""

    def __init__(self, app, limites_por_ruta: dict, limite_por_defecto: int = LIMITE_CUERPO_POR_DEFECTO_BYTES):
        self.app = app
        self.limite_por_defecto = limite_por_defecto
        self.reglas = [(_patron_de_plantilla(ruta), limite) for ruta, limite in limites_por_ruta.items()]

    def _limite_para(self, ruta: str) -> int:
        for patron, limite in self.reglas:
            if patron.match(ruta):
                return limite
        return self.limite_por_defecto

    async def _responder(self, send, status_code: int, detalle: str) -> None:
        cuerpo = json.dumps({"detail": detalle}, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(cuerpo)).encode()),
                (b"connection", b"close"),
            ],
        })
        await send({"type": "http.response.body", "body": cuerpo})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limite = self._limite_para(scope.get("path", ""))

        declarado = None
        for nombre, valor in scope.get("headers", []):
            if nombre == b"content-length":
                declarado = valor
                break
        if declarado is not None:
            texto = declarado.decode("latin-1").strip()
            if not texto.isdigit():
                await self._responder(send, status.HTTP_400_BAD_REQUEST, "Cabecera Content-Length inválida.")
                return
            if int(texto) > limite:
                await self._responder(send, status.HTTP_413_CONTENT_TOO_LARGE, _detalle_413(limite))
                return

        recibidos = 0

        async def receive_con_tope():
            nonlocal recibidos
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                recibidos += len(mensaje.get("body", b""))
                if recibidos > limite:
                    # HTTPException y no una excepción propia: FastAPI
                    # convierte cualquier otra excepción al leer el cuerpo en
                    # un 400 genérico ("There was an error parsing the
                    # body"), pero deja pasar HTTPException tal cual.
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=_detalle_413(limite),
                    )
            return mensaje

        await self.app(scope, receive_con_tope, send)
