"""Cabeceras de descarga seguras: nombre del archivo y tipo de contenido.

🆕 (sesión 2026-11-07, M7 de la revisión de seguridad previa al piloto)

1. **Nombre del archivo.** Cada endpoint armaba a mano
   `f'attachment; filename="{nombre}"'` con nombres que vienen de afuera: el
   nombre original de una evidencia subida o el nombre del alumno en el
   informe. Starlette codifica las cabeceras en Latin-1, así que:
   - un nombre con `’`, `Ł`, `—` o un emoji → UnicodeEncodeError → 500 (un
     alumno "O’Brien" no podía descargar su informe);
   - "José Peña" salía en Latin-1 crudo, que cada navegador interpreta a su
     manera;
   - una comilla `"` cortaba el parámetro, y un salto de línea llegaba tal
     cual a la cabecera.
   `content_disposition()` arma la forma de RFC 6266/5987: `filename="..."`
   en ASCII (sin tildes, sin comillas, sin controles) para clientes viejos y
   `filename*=UTF-8''...` con el nombre real codificado para los demás.

2. **Tipo de contenido.** Las evidencias se servían con el `content_type`
   guardado al subir; antes de la revisión (A1/M1) ese valor lo escribía el
   CLIENTE, así que una evidencia vieja podía tener `text/html`.
   `tipo_contenido_por_firma()` decide por los primeros bytes del archivo
   (PDF, PNG o JPEG, lo único que se acepta como evidencia) y si no
   reconoce nada devuelve `application/octet-stream`. Junto con el
   `nosniff` de core/cabeceras_seguridad.py, el navegador nunca interpreta
   una descarga como HTML.
"""
import os
import re
import unicodedata
from urllib.parse import quote

LARGO_MAXIMO_NOMBRE = 150

_CONTROLES = re.compile(r"[\x00-\x1f\x7f]")
_NO_ASCII_SEGURO = re.compile(r"[^A-Za-z0-9._\- ]+")

FIRMAS_PERMITIDAS = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def _limpiar_nombre(nombre, por_defecto):
    """Nombre real sin rutas, controles ni caracteres que rompen la cabecera."""
    nombre = nombre if isinstance(nombre, str) else ""
    nombre = nombre.replace("\\", "/").rsplit("/", 1)[-1]  # sin carpetas
    nombre = _CONTROLES.sub("", nombre)
    nombre = nombre.replace('"', "").replace(";", "_").strip(" .")
    if not nombre:
        nombre = por_defecto
    if len(nombre) > LARGO_MAXIMO_NOMBRE:
        base, extension = os.path.splitext(nombre)
        extension = extension[:15]
        nombre = base[: LARGO_MAXIMO_NOMBRE - len(extension)] + extension
    return nombre


def _version_ascii(nombre, por_defecto):
    """'Informe José Peña.pdf' → 'Informe_Jose_Pena.pdf'."""
    sin_tildes = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    ascii_ = _NO_ASCII_SEGURO.sub("_", sin_tildes).replace(" ", "_")
    ascii_ = re.sub(r"_+", "_", ascii_).strip("_.")
    return ascii_ or por_defecto


def content_disposition(nombre, por_defecto="archivo", disposicion="attachment"):
    """Valor de Content-Disposition válido para cualquier nombre."""
    limpio = _limpiar_nombre(nombre, por_defecto)
    ascii_ = _version_ascii(limpio, por_defecto)
    valor = f'{disposicion}; filename="{ascii_}"'
    if limpio != ascii_:
        valor += f"; filename*=UTF-8''{quote(limpio, safe='')}"
    return valor


def tipo_contenido_por_firma(contenido):
    """MIME según los primeros bytes; nunca el que declaró el cliente."""
    if isinstance(contenido, (bytes, bytearray)):
        for firma, tipo in FIRMAS_PERMITIDAS:
            if contenido.startswith(firma):
                return tipo
    return "application/octet-stream"
