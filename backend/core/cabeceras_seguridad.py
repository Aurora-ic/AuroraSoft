"""Cabeceras de seguridad en todas las respuestas del backend.

🆕 (sesión 2026-11-07, M2 de la revisión de seguridad) El backend solo
devuelve JSON, PDFs e imágenes que el frontend pide con fetch() y muestra
desde un blob (react-pdf / <img src="blob:...">) — nunca se abre una página
del backend dentro de un iframe ni se ejecuta HTML suyo. Por eso puede usar
la política más cerrada posible:

- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; ...`
  — si alguna vez un archivo subido se sirviera como HTML por error, el
  navegador no ejecuta nada ni deja que otra web lo enmarque.
- `X-Frame-Options: DENY` — lo mismo para navegadores viejos.
- `X-Content-Type-Options: nosniff` — el navegador respeta el Content-Type
  real (las subidas ya se validan, ver core/imagen_segura.py).
- `Referrer-Policy: no-referrer` — las URLs del backend llevan ids y tokens
  (enlace del examen, firma); no se filtran a terceros.
- `Cache-Control: no-store` SOLO si el endpoint no puso uno propio — las
  respuestas llevan datos de menores (Ley 29733); ningún proxy ni el disco
  del navegador debe guardarlas.
- `Strict-Transport-Security` solo fuera de desarrollo (en local se sirve por
  http). El navegador lo ignora si llega por http, así que no estorba antes
  de tener HTTPS.

La excepción son /docs y /redoc en desarrollo: Swagger carga scripts de un
CDN y no funcionaría con `default-src 'none'`. Fuera de desarrollo esas
rutas no existen (ver main.py).

Middleware ASGI puro (como core/limite_cuerpo.py): se registra el ÚLTIMO en
main.py para quedar por fuera de CORS y del tope de cuerpo — así también
llevan cabeceras el preflight de CORS, un 413 o un 429.
"""

CSP_API = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'"
)
HSTS = "max-age=31536000; includeSubDomains"
RUTAS_DOCUMENTACION = ("/docs", "/redoc")


def cabeceras_para(path: str, es_desarrollo: bool) -> list[tuple[bytes, bytes]]:
    """Cabeceras que se agregan a una respuesta (sin tocar las que ya trae)."""
    cabeceras = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"cache-control", b"no-store"),
    ]
    es_documentacion = es_desarrollo and (
        path in RUTAS_DOCUMENTACION or path.startswith("/docs/")
    )
    if not es_documentacion:
        cabeceras.append((b"content-security-policy", CSP_API.encode()))
    if not es_desarrollo:
        cabeceras.append((b"strict-transport-security", HSTS.encode()))
    return cabeceras


class MiddlewareCabecerasSeguridad:
    def __init__(self, app, es_desarrollo: bool):
        self.app = app
        self.es_desarrollo = es_desarrollo

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra = cabeceras_para(scope.get("path", ""), self.es_desarrollo)

        async def send_con_cabeceras(mensaje):
            if mensaje["type"] == "http.response.start":
                existentes = list(mensaje.get("headers", []))
                presentes = {nombre.lower() for nombre, _ in existentes}
                # Lo que el endpoint ya decidió (p. ej. el Cache-Control
                # "private, no-store" de la firma) se respeta tal cual.
                existentes.extend(c for c in extra if c[0] not in presentes)
                mensaje = {**mensaje, "headers": existentes}
            await send(mensaje)

        await self.app(scope, receive, send_con_cabeceras)
