# core/ip_cliente.py
#
# 🆕 (sesión 2026-11-07, M5 de la revisión de seguridad previa al piloto)
# ÚNICA fuente de "la IP del cliente" en todo el backend: rate limit
# (core/limiter.py), captcha adaptativo del login (modulos/auth/router.py) y
# registros de auditoría de la Ley 29733 (core/deps.ip_del_cliente).
#
# El problema que cierra: `ip_del_cliente` tomaba el primer salto de
# `X-Forwarded-For` SIEMPRE que la cabecera viniera — y esa cabecera la
# escribe cualquiera (`curl -H "X-Forwarded-For: 1.2.3.4"`). Se podía firmar
# un consentimiento o una lectura de expediente con la IP que uno quisiera.
# Además el rate limit y el captcha usaban otra fuente (`request.client`),
# así que la auditoría y los límites ni siquiera coincidían entre sí.
#
# Ahora `X-Forwarded-For` solo se cree si la conexión llega desde un proxy
# declarado en PROXIES_CONFIABLES (IPs o redes CIDR separadas por coma). Se
# recorre de derecha a izquierda saltando los proxies confiables, y la
# primera IP que NO es un proxy es el cliente: lo que el cliente haya puesto
# más a la izquierda es inventable y nunca se usa.
#
#   PROXIES_CONFIABLES vacía (default)  -> se usa la IP de la conexión y se
#                                          ignora X-Forwarded-For. Correcto si
#                                          el backend recibe tráfico directo.
#   PROXIES_CONFIABLES=127.0.0.1        -> Caddy/nginx en la misma máquina.
#   PROXIES_CONFIABLES=172.16.0.0/12    -> proxy en otro contenedor de Docker.
#
# Ojo con uvicorn: trae --proxy-headers ACTIVADO por defecto, confiando solo
# en 127.0.0.1 (FORWARDED_ALLOW_IPS). Con un proxy en la misma máquina,
# uvicorn ya reescribe `request.client` con la IP real antes de llegar aquí,
# y este módulo la ve como "conexión directa" — el resultado es el mismo.
import ipaddress
import logging
import os
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("aurorasoft")


def _leer_proxies(texto: str) -> tuple:
    redes = []
    for parte in (texto or "").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            logger.warning("PROXIES_CONFIABLES: '%s' no es una IP ni una red válida; se ignora.", parte)
    return tuple(redes)


@lru_cache(maxsize=1)
def proxies_confiables() -> tuple:
    return _leer_proxies(os.getenv("PROXIES_CONFIABLES", ""))


def _es_proxy(ip: str, redes) -> bool:
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(direccion in red for red in redes)


def _normalizar(ip: str) -> Optional[str]:
    """Una IP válida en forma canónica, o None. Nunca se guarda en la
    auditoría un texto arbitrario que vino en una cabecera."""
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def ip_real(request, redes=None) -> Optional[str]:
    """IP del cliente según la política de arriba; None si no hay conexión
    utilizable (se guarda NULL antes que inventar un dato de auditoría).
    `redes` es inyectable para los tests."""
    redes = proxies_confiables() if redes is None else redes
    conexion = request.client.host if request.client else None
    if not conexion:
        return None
    if not redes or not _es_proxy(conexion, redes):
        return _normalizar(conexion) or conexion
    saltos = [s.strip() for s in request.headers.get("x-forwarded-for", "").split(",") if s.strip()]
    for salto in reversed(saltos):
        if not _es_proxy(salto, redes):
            return _normalizar(salto)
    # Todos los saltos son proxies (o no hay cabecera): el cliente más
    # cercano que conocemos es la propia conexión.
    return _normalizar(conexion) or conexion


def clave_ip(request) -> str:
    """Para slowapi, que necesita siempre un texto."""
    return ip_real(request) or "desconocida"
