# core/branding.py
#
# Validación y resolución de URL pública COMPARTIDAS por todo endpoint que
# deja subir una imagen y la sirve desde el propio dominio del backend
# (branding institucional: encabezado/pie del motor de documentos; firma
# personal de un usuario; lo que siga). Antes vivía duplicado dentro de
# modulos/instituciones/crud.py — factorizado aquí en cuanto apareció el
# segundo consumidor (modulos/auth), para que el tercero no vuelva a copiar
# el mismo bloque de nuevo.
#
# El storage real (dónde se guardan los bytes) y la columna de BD que
# termina apuntando a la URL pública siguen siendo decisión de cada módulo
# llamador — esto solo valida y arma la URL.
import os
from fastapi import HTTPException, status

EXTENSIONES_IMAGEN_PERMITIDAS = {".png", ".jpg", ".jpeg"}
TAMANO_MAXIMO_IMAGEN_BYTES = 3 * 1024 * 1024  # 3 MB — de sobra para un banner/membrete/firma


def extension_imagen_segura(nombre_archivo: str) -> str:
    extension = os.path.splitext(nombre_archivo or "")[1].lower()
    if extension not in EXTENSIONES_IMAGEN_PERMITIDAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensión no permitida. Usa una de: {', '.join(sorted(EXTENSIONES_IMAGEN_PERMITIDAS))}.",
        )
    return extension


def validar_imagen_subida(contenido: bytes, content_type: str) -> None:
    if len(contenido) > TAMANO_MAXIMO_IMAGEN_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La imagen supera el tamaño máximo permitido ({TAMANO_MAXIMO_IMAGEN_BYTES // (1024*1024)} MB).",
        )
    if not (content_type or "").startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser una imagen.")


def content_type_por_extension(extension: str) -> str:
    return "image/png" if extension == ".png" else "image/jpeg"


def resolver_url_publica(ruta: str) -> str:
    """`ruta` ej. '/api/instituciones/5/branding/encabezado' -> URL pública
    completa, ya validada contra la misma protección anti-SSRF que
    `descargar_logo_seguro()` le exigirá después al descargarla de vuelta
    (core/url_segura.py: https, puerto 443, dirección pública). Lanza
    HTTPException 503 si PUBLIC_BACKEND_URL no está configurada, o 422 si
    está configurada pero no pasa esa validación (ej. apunta a localhost)."""
    base_publica = (os.getenv("PUBLIC_BACKEND_URL") or "").rstrip("/")
    if not base_publica:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "El servidor no tiene configurada PUBLIC_BACKEND_URL (el dominio público real de este "
                "backend), así que una imagen subida aquí nunca podría descargarse de vuelta al generar un "
                "PDF (la protección contra SSRF exige una URL https pública). Configura esa variable de "
                "entorno con el dominio real desplegado, o sube la imagen a tu propio hosting externo y "
                "pégala directamente en el campo de URL correspondiente."
            ),
        )

    from core.url_segura import UrlNoPermitida, validar_url_logo

    url_publica = f"{base_publica}{ruta}"
    try:
        validar_url_logo(url_publica)
    except UrlNoPermitida as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"PUBLIC_BACKEND_URL ('{base_publica}') no pasa la misma validación anti-SSRF que se le "
                f"exige a cualquier logo (debe ser https, puerto 443, dirección pública — nunca localhost "
                f"ni una IP privada): {exc}"
            ),
        )
    return url_publica
