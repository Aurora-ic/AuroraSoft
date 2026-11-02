# core/almacen_seguridad.py
#
# 🆕 (sesión 2026-11-02) Almacén COMPARTIDO de los contadores de seguridad:
# el rate limit (core/limiter.py), el almacén de captchas y los contadores
# del captcha adaptativo (core/captcha.py).
#
# Antes los tres vivían en la memoria de cada proceso de uvicorn. Con más de
# un worker en producción no se compartían: un captcha emitido por un worker
# no lo conocía otro, y cada worker contaba los intentos por separado (un
# atacante tenía N veces el cupo de login).
#
# ALMACEN_SEGURIDAD_URL=redis://host:6379/2 → los tres van a Redis (el mismo
# servidor que ya usa Celery, en OTRA base: db 0/1 son de Celery).
# Sin la variable → memoria del proceso, exactamente como antes (desarrollo,
# tests unitarios). En producción con varios workers la variable es
# OBLIGATORIA en la práctica — main.py avisa en el log al arrancar si falta.
#
# Si Redis se cae en pleno uso, cada operación vuelve a la memoria del
# proceso (y lo deja en el log) en vez de tumbar el login: perder la
# coordinación entre workers unos minutos es mejor que nadie pueda entrar.
import logging
import os

logger = logging.getLogger(__name__)

ALMACEN_SEGURIDAD_URL = (os.getenv("ALMACEN_SEGURIDAD_URL") or "").strip() or None

# Prefijo de todas las claves, para no chocar con nada más en esa base.
PREFIJO = "aurora:seg:"

_cliente = None


def cliente_redis():
    """Cliente Redis compartido, o None si no hay ALMACEN_SEGURIDAD_URL."""
    global _cliente
    if ALMACEN_SEGURIDAD_URL is None:
        return None
    if _cliente is None:
        import redis

        # Timeouts cortos por el mismo motivo que core/cola_tareas.py: un
        # Redis inalcanzable no debe dejar colgado un login.
        _cliente = redis.Redis.from_url(
            ALMACEN_SEGURIDAD_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
    return _cliente


def avisar_caida(operacion: str, exc: Exception) -> None:
    logger.warning(
        "Almacén de seguridad (Redis) no disponible en %s: %s — se usa la memoria del proceso.",
        operacion,
        exc,
    )
