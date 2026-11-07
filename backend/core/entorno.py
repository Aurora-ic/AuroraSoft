"""Una sola lectura de ENTORNO para todo el backend.

🆕 (sesión 2026-11-07, M3 de la revisión de seguridad) Antes cada archivo
leía ENTORNO con "development" como valor por defecto: si en el servidor faltaba la
variable (un .env incompleto, un contenedor sin ella), el backend arrancaba
en modo DESARROLLO — Swagger abierto, `/openapi.json` publicado, cookies de
sesión sin `Secure` y sin HSTS. Fallaba abierto.

Ahora el valor por defecto es "production": si falta, el backend se comporta
como producción. Desarrollo hay que pedirlo explícitamente con
`ENTORNO=development` (el .env local ya lo tiene). Cualquier valor que no sea
exactamente "development" (sin importar mayúsculas/espacios) cuenta como
producción — un "dev" o "desarrollo" mal escrito tampoco abre nada.

`load_dotenv()` tiene que haber corrido antes de importar este módulo
(main.py lo hace en su primera línea útil).
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv()  # idempotente; por si este módulo se importa antes que main.py

logger = logging.getLogger("aurorasoft")

VALORES_CONOCIDOS = ("development", "staging", "production")

_crudo = os.getenv("ENTORNO")
ENTORNO = (_crudo or "production").strip().lower()

if _crudo is None:
    logger.warning("ENTORNO no está definida: se asume 'production' (Swagger y /openapi.json apagados).")
elif ENTORNO not in VALORES_CONOCIDOS:
    logger.warning(
        "ENTORNO=%r no es un valor conocido %s: se trata como producción.",
        _crudo, VALORES_CONOCIDOS,
    )

ES_DESARROLLO = ENTORNO == "development"
