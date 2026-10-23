# ============================================================
# DESCARGA SEGURA DEL LOGO INSTITUCIONAL (C-11 · anti-SSRF)
# Archivo: core/url_segura.py
# ============================================================
"""
El logo de la institución se descarga en el servidor al generar el PDF, y el
PDF del alumno se genera en un endpoint PÚBLICO (basta el token del examen).
Con `urlopen(logo_url)` sin más, cualquiera con un token podía hacer que el
servidor pidiera `http://169.254.169.254/latest/meta-data/` (credenciales de la
nube), `http://localhost:5432` o cualquier servicio de la red interna.

ESTRATEGIA
1. Solo `https`, solo puerto 443, sin usuario:contraseña en la URL.
2. El host se resuelve ANTES de conectar y se rechaza si CUALQUIERA de sus
   direcciones no es pública (`ipaddress.is_global`): loopback, privadas,
   link-local (metadata), CGNAT, reservadas, documentación, multicast...
3. Se conecta a la IP YA VALIDADA (no se vuelve a resolver el nombre). Evita
   el "DNS rebinding": un dominio que responde con una IP pública a la
   validación y con 127.0.0.1 a la conexión real. El certificado TLS se sigue
   verificando contra el nombre del host (SNI).
4. No se siguen redirecciones: un 3xx se trata como fallo. Si no, una URL
   pública podría redirigir a la red interna.
5. Solo `Content-Type: image/*`, tamaño máximo y timeout.

Si algo falla, el logo simplemente no se incluye: un logo nunca debe impedir
que se genere un informe clínico.
"""

import http.client
import ipaddress
import logging
import socket
import ssl
from urllib.parse import urlsplit

logger = logging.getLogger("aurorasoft")

TAMANO_MAXIMO_LOGO = 2 * 1024 * 1024   # 2 MiB
TIMEOUT_SEGUNDOS = 5
PUERTO_HTTPS = 443


class UrlNoPermitida(ValueError):
    """La URL no supera la política de seguridad para recursos externos."""


def _es_direccion_publica(ip_texto: str) -> bool:
    # Las IPv6 con zona ("fe80::1%eth0") traen un sufijo que ipaddress no acepta
    direccion = ipaddress.ip_address(ip_texto.split("%", 1)[0])
    # ::ffff:127.0.0.1 es 127.0.0.1 disfrazada de IPv6
    if isinstance(direccion, ipaddress.IPv6Address) and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return direccion.is_global and not direccion.is_multicast


def validar_url_logo(url: str, resolver=socket.getaddrinfo):
    """Valida la URL y devuelve (host, ip_validada, ruta).

    Lanza UrlNoPermitida con un motivo legible si no cumple la política.
    `resolver` es inyectable para poder probar sin red; en producción es el
    resolvedor del sistema.
    """
    if not url or not isinstance(url, str):
        raise UrlNoPermitida("La URL del logo está vacía.")

    partes = urlsplit(url.strip())

    if partes.scheme != "https":
        raise UrlNoPermitida("El logo debe servirse por https.")
    if partes.username or partes.password:
        raise UrlNoPermitida("La URL del logo no puede incluir usuario ni contraseña.")
    host = partes.hostname
    if not host:
        raise UrlNoPermitida("La URL del logo no tiene un servidor válido.")
    try:
        puerto = partes.port or PUERTO_HTTPS
    except ValueError:
        raise UrlNoPermitida("El puerto de la URL del logo no es válido.")
    if puerto != PUERTO_HTTPS:
        raise UrlNoPermitida("El logo solo puede descargarse del puerto 443.")

    try:
        registros = resolver(host, PUERTO_HTTPS, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise UrlNoPermitida("No se pudo resolver el servidor del logo.")

    direcciones = sorted({registro[4][0] for registro in registros})
    if not direcciones:
        raise UrlNoPermitida("No se pudo resolver el servidor del logo.")

    # TODAS deben ser públicas: basta una interna para rechazar, porque el
    # sistema operativo podría conectar a cualquiera de ellas.
    for ip in direcciones:
        try:
            publica = _es_direccion_publica(ip)
        except ValueError:
            publica = False
        if not publica:
            raise UrlNoPermitida(
                "El servidor del logo apunta a una dirección interna o reservada."
            )

    ruta = partes.path or "/"
    if partes.query:
        ruta = f"{ruta}?{partes.query}"
    return host, direcciones[0], ruta


class _ConexionHTTPSFijada(http.client.HTTPSConnection):
    """HTTPSConnection que conecta a una IP ya validada, no al nombre.

    El nombre solo se usa para SNI y para verificar el certificado, así que
    la validación TLS sigue siendo completa.
    """

    def __init__(self, host, ip, timeout):
        super().__init__(host, PUERTO_HTTPS, timeout=timeout,
                         context=ssl.create_default_context())
        self._ip_fijada = ip

    def connect(self):
        socket_crudo = socket.create_connection((self._ip_fijada, self.port), self.timeout)
        self.sock = self._context.wrap_socket(socket_crudo, server_hostname=self.host)


def _abrir_conexion(host, ip, timeout):
    """Punto de extensión aislado para poder probar la lógica HTTP sin red."""
    return _ConexionHTTPSFijada(host, ip, timeout)


def descargar_logo_seguro(url: str, resolver=socket.getaddrinfo):
    """Descarga el logo aplicando toda la política. Devuelve bytes o None.

    Nunca lanza: registra el motivo en el log y devuelve None, para que el PDF
    se genere igualmente sin logo.
    """
    try:
        host, ip, ruta = validar_url_logo(url, resolver=resolver)
    except UrlNoPermitida as exc:
        logger.warning("Logo institucional descartado (%s): %s", exc, url)
        return None

    conexion = None
    try:
        conexion = _abrir_conexion(host, ip, TIMEOUT_SEGUNDOS)
        conexion.request("GET", ruta, headers={
            "Host": host,
            "User-Agent": "AuroraSoft-Informes/1.0",
            "Accept": "image/*",
        })
        respuesta = conexion.getresponse()

        # http.client NUNCA sigue redirecciones: un 3xx llega aquí tal cual.
        if respuesta.status != 200:
            logger.warning("Logo institucional descartado: HTTP %s en %s",
                           respuesta.status, host)
            return None

        tipo = (respuesta.getheader("Content-Type") or "").split(";")[0].strip().lower()
        if not tipo.startswith("image/"):
            logger.warning("Logo institucional descartado: Content-Type '%s' no es imagen", tipo)
            return None

        contenido = respuesta.read(TAMANO_MAXIMO_LOGO + 1)
        if len(contenido) > TAMANO_MAXIMO_LOGO:
            logger.warning("Logo institucional descartado: supera %s bytes", TAMANO_MAXIMO_LOGO)
            return None
        return contenido
    except Exception as exc:  # red, TLS, timeout...
        logger.warning("No se pudo descargar el logo institucional de %s: %s", host, exc)
        return None
    finally:
        if conexion is not None:
            conexion.close()
