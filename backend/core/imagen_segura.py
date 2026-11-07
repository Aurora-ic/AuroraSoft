# core/imagen_segura.py
#
# 🆕 (sesión 2026-11-05, A1 de la revisión de seguridad previa al piloto)
# Único punto donde se decide si unos bytes son una imagen que AuroraSoft
# acepta abrir: PNG o JPEG, y no más grande que MAXIMO_PIXELES_IMAGEN.
#
# Por qué hacía falta: hasta ahora la subida solo miraba la EXTENSIÓN del
# nombre de archivo y el Content-Type que manda el cliente — ambos los
# escribe quien sube. Después, al generar el PDF, `PIL.Image.open()` (directo
# o vía reportlab) abría esos bytes con TODOS los formatos que Pillow conoce
# (decenas, varios con historial de CVEs) y sin ningún tope de píxeles. Un
# "logo.png" que en realidad era otro formato, o un PNG chico que se
# descomprime a gigas (bomba de descompresión), llegaba entero al parser.
#
# Dos usos, con distinto costo a propósito:
#   - `validar_imagen_para_subida()`: al subir. Abre restringido a PNG/JPEG,
#     revisa el tope de píxeles leyendo solo la cabecera, y recién después
#     decodifica la imagen completa (atrapa archivos truncados/corruptos).
#     Devuelve el content-type REAL, no el que declara el cliente.
#   - `dimensiones_imagen_segura()`: al dibujar un PDF. Solo cabecera
#     (formato + tope de píxeles) — reportlab decodifica igual después, y no
#     tiene sentido decodificar dos veces. Nunca lanza: devuelve None y el
#     generador omite la imagen o dibuja un aviso. Cubre lo que se subió
#     antes de este cambio y los logos externos (URLs de terceros).
import io
import logging

from fastapi import HTTPException, status
from PIL import Image

logger = logging.getLogger("aurorasoft")

FORMATOS_IMAGEN_PERMITIDOS = ("PNG", "JPEG")
# 50 MP: cubre la foto de un celular de gama alta (48 MP) y un escaneo A4 a
# 600 dpi (~35 MP). Decodificado en RGB son ~150 MB de memoria — el techo
# aceptable para el worker que arma el PDF.
MAXIMO_PIXELES_IMAGEN = 50_000_000

class ImagenNoValida(ValueError):
    """Los bytes no son un PNG/JPEG aceptable. El mensaje es apto para
    mostrarle al usuario."""


def _abrir_cabecera(contenido: bytes):
    """Abre SOLO como PNG/JPEG y revisa el tope de píxeles con lo que dice la
    cabecera, antes de decodificar nada. Devuelve la imagen abierta (sin
    decodificar) — el caller la cierra."""
    try:
        imagen = Image.open(io.BytesIO(contenido), formats=list(FORMATOS_IMAGEN_PERMITIDOS))
    except Exception:
        raise ImagenNoValida("El archivo no es una imagen PNG o JPEG válida.")
    ancho, alto = imagen.size
    if ancho <= 0 or alto <= 0:
        imagen.close()
        raise ImagenNoValida("La imagen no tiene dimensiones válidas.")
    if ancho * alto > MAXIMO_PIXELES_IMAGEN:
        imagen.close()
        raise ImagenNoValida(
            f"La imagen es demasiado grande ({ancho}×{alto} píxeles). "
            f"El máximo es {MAXIMO_PIXELES_IMAGEN // 1_000_000} megapíxeles."
        )
    return imagen


def inspeccionar_imagen(contenido: bytes) -> tuple[str, int, int]:
    """Validación completa (la de la subida). Devuelve (formato, ancho, alto)
    o lanza ImagenNoValida."""
    imagen = _abrir_cabecera(contenido)
    formato = imagen.format
    ancho, alto = imagen.size
    try:
        # verify() revisa la estructura (CRC de cada bloque PNG) sin
        # decodificar; deja la imagen inutilizable, por eso se reabre para
        # el load(), que sí decodifica todo y atrapa un JPEG truncado.
        imagen.verify()
    except Exception:
        raise ImagenNoValida("La imagen está dañada o incompleta.")
    finally:
        imagen.close()
    imagen = _abrir_cabecera(contenido)
    try:
        imagen.load()
    except Exception:
        raise ImagenNoValida("La imagen está dañada o incompleta.")
    finally:
        imagen.close()
    return formato, ancho, alto


_EXTENSIONES_POR_FORMATO = {
    "PNG": {".png"},
    "JPEG": {".jpg", ".jpeg"},
}
_CONTENT_TYPE_POR_FORMATO = {"PNG": "image/png", "JPEG": "image/jpeg"}


def validar_imagen_para_subida(contenido: bytes, extension_declarada: str) -> str:
    """Para los endpoints de subida, DESPUÉS de la lista blanca de extensión
    del nombre. Devuelve el content-type del formato REAL ('image/png' o
    'image/jpeg') para guardar con eso y no con lo que declaró el cliente.
    400 si no es un PNG/JPEG aceptable o si no coincide con la extensión.

    Se exige que la extensión coincida en vez de renombrarla al formato
    real: branding y firma usan una key fija por extensión y sirven la
    primera que exista (`leer_imagen_branding`/`leer_firma_usuario`), así
    que cambiar '.jpeg' por '.jpg' por nuestra cuenta podía dejar sirviendo
    una imagen anterior."""
    try:
        formato, _, _ = inspeccionar_imagen(contenido)
    except ImagenNoValida as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if extension_declarada.lower() not in _EXTENSIONES_POR_FORMATO[formato]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El archivo tiene extensión '{extension_declarada}' pero en realidad es una imagen {formato}. "
                f"Cámbiale la extensión a {' o '.join(sorted(_EXTENSIONES_POR_FORMATO[formato]))} y vuelve a subirlo."
            ),
        )
    return _CONTENT_TYPE_POR_FORMATO[formato]


def dimensiones_imagen_segura(contenido: bytes | None, contexto: str = "imagen") -> tuple[int, int] | None:
    """Para los generadores de PDF: (ancho, alto) si es un PNG/JPEG dentro del
    tope, None si no (y lo deja en el log). Nunca lanza."""
    if not contenido:
        return None
    try:
        imagen = _abrir_cabecera(contenido)
    except ImagenNoValida as exc:
        logger.warning("%s descartada al generar el PDF: %s", contexto, exc)
        return None
    try:
        return imagen.size
    finally:
        imagen.close()
