# core/captcha.py
#
# 🆕 Captcha de imagen para el login. El código se genera y se valida SOLO
# aquí, en el backend: la respuesta de GET /api/auth/captcha trae la imagen
# (PNG en data URL) y un `captcha_id` opaco, nunca el texto. El servidor
# guarda únicamente un HMAC del texto (con SECRET_KEY), así que ni siquiera
# un volcado de memoria del almacén deja leer los códigos vigentes.
#
# Reglas:
#   · Expira a los CAPTCHA_TTL_SEGUNDOS (5 min).
#   · Uso único: verificar_captcha() lo SACA del almacén antes de comparar,
#     acierte o no. Un intento fallido obliga a pedir uno nuevo, y uno ya
#     aceptado no se puede reutilizar para un segundo login.
#   · El almacén tiene tope (CAPTCHA_MAX_PENDIENTES): un script que pida
#     captchas en bucle no hace crecer la memoria sin límite (además del
#     rate limit del endpoint).
#
# ⚠️ Despliegue: igual que el contador de core/limiter.py, el almacén vive en
# la memoria del proceso. Con varios workers de uvicorn, un captcha emitido
# por un worker no lo conoce otro — en ese caso hay que fijar la sesión al
# mismo worker o mover el almacén a Redis.
#
# LOGIN_CAPTCHA_OBLIGATORIO=false lo apaga (p. ej. el uvicorn de :8010 que
# usan los verificar_*_e2e y la suite de Playwright, que inician sesión por
# script). Por defecto está ENCENDIDO.
import base64
import hashlib
import hmac
import io
import math
import os
import random
import secrets
import threading
import time
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core.security import SECRET_KEY

CAPTCHA_OBLIGATORIO = os.getenv("LOGIN_CAPTCHA_OBLIGATORIO", "true").strip().lower() not in ("false", "0", "no")
CAPTCHA_TTL_SEGUNDOS = 300
CAPTCHA_MAX_PENDIENTES = 10_000
LONGITUD_CODIGO = 5

# Sin caracteres que se confunden entre sí (0/O, 1/I/L, 5/S, 2/Z, 8/B):
# el captcha debe costarle a un bot, no a un psicólogo apurado.
_ALFABETO = "ACDEFGHJKMNPQRTUVWXY34679"

_ANCHO, _ALTO = 220, 70

_RUTAS_FUENTES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/courbd.ttf",
    "C:/Windows/Fonts/trebucbd.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
]
_FUENTES_DISPONIBLES = [r for r in _RUTAS_FUENTES if os.path.exists(r)]

# Tonos de la paleta de marca (teal/pino) + pizarra: legible para una
# persona, variado para un OCR.
_COLORES_TEXTO = [(15, 90, 79), (18, 121, 107), (11, 61, 52), (79, 100, 117), (42, 120, 214)]

_rng = random.SystemRandom()
_almacen: "OrderedDict[str, tuple[str, float]]" = OrderedDict()
_candado = threading.Lock()


class CaptchaInvalido(Exception):
    pass


def _huella(texto: str) -> str:
    return hmac.new(SECRET_KEY.encode(), texto.upper().encode(), hashlib.sha256).hexdigest()


def _fuente(tamano: int):
    if _FUENTES_DISPONIBLES:
        return ImageFont.truetype(_rng.choice(_FUENTES_DISPONIBLES), tamano)
    # Pillow ≥ 10.1 trae una fuente FreeType por defecto que acepta tamaño.
    return ImageFont.load_default(size=tamano)


def _dibujar(codigo: str) -> bytes:
    imagen = Image.new("RGB", (_ANCHO, _ALTO), (247, 250, 249))
    dibujo = ImageDraw.Draw(imagen)

    # Ruido de fondo: puntos y arcos tenues.
    for _ in range(260):
        x, y = _rng.randrange(_ANCHO), _rng.randrange(_ALTO)
        tono = _rng.randint(170, 220)
        dibujo.point((x, y), fill=(tono, tono + 10 if tono < 245 else tono, tono))
    for _ in range(4):
        x0, y0 = _rng.randint(-40, _ANCHO // 2), _rng.randint(-30, _ALTO // 2)
        x1, y1 = x0 + _rng.randint(80, 200), y0 + _rng.randint(40, 90)
        dibujo.arc((x0, y0, x1, y1), _rng.randint(0, 180), _rng.randint(180, 360), fill=(190, 210, 204), width=2)

    # Cada carácter con su propia fuente, tamaño, color y rotación; recortado
    # a su glifo real para que todos queden dentro del lienzo y a la vista.
    capas = []
    for caracter in codigo:
        tamano = _rng.randint(36, 44)
        capa = Image.new("RGBA", (tamano * 2, tamano * 2), (0, 0, 0, 0))
        ImageDraw.Draw(capa).text((tamano // 2, tamano // 4), caracter, font=_fuente(tamano), fill=_rng.choice(_COLORES_TEXTO) + (255,))
        capa = capa.crop(capa.getbbox())
        capas.append(capa.rotate(_rng.uniform(-25, 25), resample=Image.BICUBIC, expand=True))
    ancho_total = sum(c.width for c in capas) - 6 * (len(capas) - 1)  # se solapan un poco
    x = max(4, (_ANCHO - ancho_total) // 2)
    for capa in capas:
        y = (_ALTO - capa.height) // 2 + _rng.randint(-7, 7)
        imagen.paste(capa, (x, max(0, min(y, _ALTO - capa.height))), capa)
        x += capa.width - 6

    # Distorsión en onda (desplaza columnas verticalmente): rompe la línea
    # base recta que aprovechan los OCR.
    amplitud, periodo, fase = _rng.uniform(2.5, 4.5), _rng.uniform(40, 70), _rng.uniform(0, math.pi * 2)
    ondulada = Image.new("RGB", imagen.size, (247, 250, 249))
    for columna in range(_ANCHO):
        desplazamiento = int(amplitud * math.sin(2 * math.pi * columna / periodo + fase))
        franja = imagen.crop((columna, 0, columna + 1, _ALTO))
        ondulada.paste(franja, (columna, desplazamiento))
    imagen = ondulada
    dibujo = ImageDraw.Draw(imagen)

    # Dos trazos que cruzan los caracteres.
    for _ in range(2):
        puntos = [(0, _rng.randint(10, _ALTO - 10))]
        for i in range(1, 5):
            puntos.append((i * _ANCHO // 4, _rng.randint(10, _ALTO - 10)))
        dibujo.line(puntos, fill=_rng.choice(_COLORES_TEXTO), width=2, joint="curve")

    imagen = imagen.filter(ImageFilter.SMOOTH)
    salida = io.BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _purgar_vencidos(ahora: float) -> None:
    vencidos = [cid for cid, (_, expira) in _almacen.items() if expira <= ahora]
    for cid in vencidos:
        del _almacen[cid]


def generar_captcha() -> dict:
    """Crea un captcha nuevo y devuelve {captcha_id, imagen}. El texto nunca
    sale de esta función."""
    codigo = "".join(_rng.choice(_ALFABETO) for _ in range(LONGITUD_CODIGO))
    png = _dibujar(codigo)
    captcha_id = secrets.token_urlsafe(24)
    ahora = time.monotonic()
    with _candado:
        _purgar_vencidos(ahora)
        while len(_almacen) >= CAPTCHA_MAX_PENDIENTES:
            _almacen.popitem(last=False)  # el más antiguo
        _almacen[captcha_id] = (_huella(codigo), ahora + CAPTCHA_TTL_SEGUNDOS)
    return {"captcha_id": captcha_id, "imagen": "data:image/png;base64," + base64.b64encode(png).decode()}


def verificar_captcha(captcha_id: str | None, respuesta: str | None) -> None:
    """Consume el captcha (uso único, acierte o no) y lanza CaptchaInvalido si
    falta, venció o no coincide. No distingue mayúsculas/minúsculas ni
    espacios alrededor."""
    if not captcha_id or not respuesta or not respuesta.strip():
        raise CaptchaInvalido("Ingresa el código de verificación que aparece en la imagen.")
    with _candado:
        entrada = _almacen.pop(captcha_id, None)
    if entrada is None:
        raise CaptchaInvalido("El código de verificación ya no es válido. Usa el nuevo código que aparece en la imagen.")
    huella, expira = entrada
    if expira <= time.monotonic():
        raise CaptchaInvalido("El código de verificación venció. Usa el nuevo código que aparece en la imagen.")
    if not hmac.compare_digest(huella, _huella(respuesta.strip())):
        raise CaptchaInvalido("El código de verificación no coincide. Inténtalo con el nuevo código.")
