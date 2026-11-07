"""Validación de CORS_ALLOWED_ORIGINS al arrancar.

🆕 (sesión 2026-11-07, B de la revisión de seguridad previa al piloto) Antes
main.py hacía `.split(",")` y le pasaba el resultado tal cual a
CORSMiddleware, que corre con `allow_credentials=True` (la sesión viaja en
cookies httpOnly, core/sesiones.py). Problemas:

- Un `*` en la lista hace que Starlette RESPONDA con el origen de quien
  pregunte y `Access-Control-Allow-Credentials: true`: cualquier web podría
  leer la API con las cookies del psicólogo que la visita.
- `"null"` es el origen de iframes sandbox y archivos locales: lo mismo.
- Un espacio (`"a, b"`) o una barra final (`https://x.pe/`) hacen que ese
  origen nunca coincida, y el frontend falla sin un error claro.
- Fuera de desarrollo, un origen `http://` deja leer la API a una página
  servida sin cifrar (o a cualquier cosa que escuche en localhost).

`origenes_cors()` normaliza lo inofensivo (espacios, barra final,
duplicados, mayúsculas del host) y para todo lo demás NO arranca: un
RuntimeError con el motivo, mejor que un CORS abierto en producción.
"""
import logging
from urllib.parse import urlsplit

logger = logging.getLogger("aurorasoft")

POR_DEFECTO = "http://localhost:3000"


class OrigenCorsInvalido(RuntimeError):
    pass


def _normalizar(origen, es_desarrollo):
    if origen in ("*", "null"):
        raise OrigenCorsInvalido(
            f"CORS_ALLOWED_ORIGINS no puede incluir {origen!r}: con cookies de sesión "
            "dejaría a cualquier web usar la API como el usuario. Lista los orígenes exactos."
        )
    sin_barra = origen.rstrip("/")
    partes = urlsplit(sin_barra)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise OrigenCorsInvalido(
            f"Origen CORS inválido {origen!r}: debe ser esquema://host[:puerto], p. ej. https://app.aurorasoft.pe"
        )
    if partes.path or partes.query or partes.fragment or partes.username or partes.password:
        raise OrigenCorsInvalido(
            f"Origen CORS inválido {origen!r}: solo esquema, host y puerto (sin ruta, '?', '#' ni usuario)."
        )
    if "*" in partes.hostname:
        raise OrigenCorsInvalido(f"Origen CORS inválido {origen!r}: no se aceptan comodines en el host.")
    if not es_desarrollo and partes.scheme != "https":
        raise OrigenCorsInvalido(
            f"Origen CORS {origen!r} usa http fuera de desarrollo: solo https."
        )
    try:
        puerto = partes.port
    except ValueError:
        raise OrigenCorsInvalido(f"Origen CORS inválido {origen!r}: el puerto no es un número válido.")
    normalizado = f"{partes.scheme}://{partes.hostname}" + (f":{puerto}" if puerto else "")
    if normalizado != origen:
        logger.warning("Origen CORS %r normalizado a %r.", origen, normalizado)
    return normalizado


def origenes_cors(valor, es_desarrollo):
    """Lista final para CORSMiddleware, o OrigenCorsInvalido si algo no sirve."""
    if valor is None:
        valor = POR_DEFECTO if es_desarrollo else ""
    resultado = []
    for crudo in valor.split(","):
        origen = crudo.strip()
        if not origen:
            continue
        normalizado = _normalizar(origen, es_desarrollo)
        if normalizado not in resultado:
            resultado.append(normalizado)
    if not resultado:
        raise OrigenCorsInvalido(
            "CORS_ALLOWED_ORIGINS está vacía: define el origen del frontend (p. ej. https://app.aurorasoft.pe)."
        )
    return resultado
