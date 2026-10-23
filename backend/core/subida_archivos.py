# core/subida_archivos.py
#
# Lectura ACOTADA de archivos subidos por el cliente — hallazgo de auditoría
# (sesión 2026-10-16): los endpoints de subida (branding, firma de usuario,
# imagen de sección del motor de documentos, evidencia de consentimiento, y
# los dos de importación de Excel) leían el cuerpo COMPLETO
# (`await archivo.read()` / `archivo.file.read()`) y solo comparaban su
# tamaño DESPUÉS, con todo ya materializado en memoria — sin ningún límite
# global de `Content-Length`, una subida de varios GB podía consumir toda
# esa memoria antes de que el límite real (3-10 MB según el endpoint)
# llegara a rechazarla. Mismo criterio que `core/url_segura.
# descargar_logo_seguro()` ya usa para una descarga remota: leer en bloques
# y cortar apenas se supera el límite, nunca esperar a terminar de leer todo
# para recién ahí decidir.
from fastapi import HTTPException, UploadFile, status

TAMANO_CHUNK_LECTURA = 256 * 1024  # 256 KiB por bloque


def leer_archivo_con_limite(archivo: UploadFile, limite_bytes: int, nombre_campo: str = "archivo") -> bytes:
    """Lee el cuerpo de `archivo` en bloques de `TAMANO_CHUNK_LECTURA`,
    cortando apenas el acumulado supera `limite_bytes` — nunca mantiene en
    memoria más que `limite_bytes` más un bloque de margen, sin importar
    cuánto pese el cuerpo real de la petición.

    Usa `archivo.file` (la interfaz SÍNCRONA que Starlette ya expone sobre
    el `SpooledTemporaryFile`/`BytesIO` subyacente) en vez de `await
    archivo.read()` — funciona igual desde un endpoint `async def` o uno
    `def` normal, sin necesitar dos variantes; la operación es breve y
    acotada, así que no vale la pena la complejidad de un `read()` async
    por bloques.
    """
    archivo.file.seek(0)
    partes = []
    total = 0
    while True:
        bloque = archivo.file.read(TAMANO_CHUNK_LECTURA)
        if not bloque:
            break
        total += len(bloque)
        if total > limite_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"El {nombre_campo} supera el tamaño máximo permitido "
                    f"({limite_bytes // (1024 * 1024)} MB)."
                ),
            )
        partes.append(bloque)
    return b"".join(partes)
