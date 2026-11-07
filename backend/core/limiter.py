# core/limiter.py
import threading
import time

from fastapi import HTTPException, Request, status
from slowapi import Limiter

from core.almacen_seguridad import ALMACEN_SEGURIDAD_URL, PREFIJO, avisar_caida, cliente_redis
# 🆕 (sesión 2026-11-07, M5) La IP sale de core/ip_cliente.py — la misma
# fuente que la auditoría y el captcha. Antes era `get_remote_address` de
# slowapi (request.client a secas).
from core.ip_cliente import clave_ip, ip_real

# 🆕 (sesión 2026-11-02) Con ALMACEN_SEGURIDAD_URL los contadores van a Redis
# y todos los workers comparten el mismo cupo (ver core/almacen_seguridad.py).
# in_memory_fallback_enabled: si Redis se cae, slowapi sigue limitando con un
# contador en memoria en vez de dejar pasar todo o devolver 500.
if ALMACEN_SEGURIDAD_URL:
    limiter = Limiter(
        key_func=clave_ip,
        storage_uri=ALMACEN_SEGURIDAD_URL,
        storage_options={"socket_connect_timeout": 2, "socket_timeout": 2},
        in_memory_fallback_enabled=True,
        key_prefix=PREFIJO + "rl",
    )
else:
    limiter = Limiter(key_func=clave_ip)


# ==========================================
# ⏱️ C-12 — LÍMITES DE LOS ENDPOINTS PÚBLICOS DEL EXAMEN
# ==========================================
# Estos endpoints no exigen login (basta el token del enlace mágico), así que
# eran la superficie más expuesta del sistema y no tenían ningún límite.
#
# Se aplican DOS límites apilados a cada endpoint:
#
#   · POR TOKEN (estricto): frena el abuso de un enlace concreto — p. ej. un
#     script que llama a /finalizar o genera PDFs en bucle. Cada alumno tiene
#     su propio cupo, independiente del resto de la clase.
#
#   · POR IP (holgado): frena la enumeración de tokens (cada intento usa un
#     token distinto, así que el límite por token no lo detectaría). Es
#     holgado a propósito: en un colegio toda un aula suele salir a Internet
#     por la MISMA IP pública (NAT), y un límite ajustado bloquearía a 40
#     alumnos a la vez en mitad del examen.
#
# 🆕 (sesión 2026-11-07, A4 de la revisión de seguridad) Los límites por IP
# se subieron y la enumeración pasó a la `guardia_enumeracion` de abajo. Las
# cifras de antes (p. ej. guardar 1500/min por IP) suponían ~4 guardados por
# minuto por alumno, pero el frontend guarda CADA respuesta: un alumno rápido
# en una prueba larga hace 15-30 por minuto. Con 100 alumnos a la vez detrás
# de la IP del colegio ya se pasaba el cupo, y un 429 en /guardar hacía que el
# frontend le borrara la respuesta al alumno. La enumeración de tokens la
# frena ahora un contador de ENLACES INVÁLIDOS por IP (un alumno real casi
# nunca abre uno), así que el límite por IP general queda como red de
# seguridad contra abuso masivo, dimensionado para ~600 alumnos simultáneos
# detrás de una sola IP (un colegio grande en hora de examen):
#   guardar    600 alumnos x 30/min        -> 20000/min
#   comenzar   todos empiezan en el mismo minuto -> 2000/min
#   informe_pdf generar un PDF es caro       -> 300/min
# El límite POR TOKEN no cambia: es el que frena a un solo enlace en bucle.
#
# ⚠️ Despliegue: la IP sale de core/ip_cliente.ip_real — detrás de un proxy
# inverso hay que declararlo en PROXIES_CONFIABLES, o todos los alumnos
# compartirían la IP del proxy. El contador vive en Redis si
# ALMACEN_SEGURIDAD_URL está definida (compartido entre workers); si no, en
# la memoria de cada proceso, y con varios workers cada uno cuenta por separado.

def clave_por_token(request) -> str:
    """Agrupa el conteo por enlace mágico en vez de por IP."""
    return "token:" + str(request.path_params.get("token", ""))


LIMITES_EXAMEN = {
    #  endpoint              por token      por IP
    "intake":              ("10/minute",   "2000/minute"),  # mismo tier que "comenzar": se llama una vez, antes de él
    # 🆕 asentimiento_texto — se llama junto con "intake", antes de que el
    # alumno acepte nada; mismo tier por el mismo motivo.
    "asentimiento_texto":  ("10/minute",   "2000/minute"),
    "comenzar":            ("10/minute",   "2000/minute"),
    "preguntas":           ("30/minute",   "3000/minute"),
    "progreso":            ("30/minute",   "3000/minute"),
    "guardar":             ("120/minute",  "20000/minute"),
    "finalizar":           ("5/minute",    "2000/minute"),
    "estado_resultados":   ("30/minute",   "3000/minute"),
    "informe_pdf":         ("10/minute",   "300/minute"),   # generar un PDF es caro
    "campos_socio":        ("30/minute",   "3000/minute"),
}


def limite_token(nombre: str) -> str:
    return LIMITES_EXAMEN[nombre][0]


def limite_ip(nombre: str) -> str:
    return LIMITES_EXAMEN[nombre][1]


def ambito_ip(nombre: str) -> str:
    """Ámbito FIJO para el límite por IP.

    ⚠️ slowapi usa por defecto la RUTA de la URL como ámbito del contador, y en
    estos endpoints la ruta incluye el token (/examen/<token>/...). Con
    @limiter.limit el límite "por IP" se contaba en realidad por (IP, token):
    cada intento de enumeración con un token nuevo abría un contador nuevo y
    el límite no saltaba nunca. Se detectó en las pruebas E2E de la Fase 3.
    Con shared_limit + este ámbito, todas las peticiones de una IP a un mismo
    endpoint comparten contador, sea cual sea el token.
    """
    return f"examen-ip:{nombre}"


# ==========================================
# 🆕 (sesión 2026-11-07, A4) GUARDIA CONTRA LA ENUMERACIÓN DE ENLACES
# ==========================================
# Cuenta, por IP, los enlaces de examen INVÁLIDOS (respuestas 404 de los
# endpoints públicos del examen). Pasado el umbral, esa IP recibe 429 en
# TODOS los endpoints del examen — también con un enlace válido: si no, el
# 429 para los inválidos frente al 200 para los válidos le diría al
# atacante cuál acertó. Un alumno real casi nunca abre un enlace inválido
# (a lo más un par, por un enlace mal copiado), así que el bloqueo solo toca
# a la red de quien está probando tokens. Se aplica como dependencia con
# `yield`: ve la excepción 404 que lanza el endpoint, la cuenta y la deja
# seguir igual.
UMBRAL_ENLACES_INVALIDOS = 30
VENTANA_ENLACES_INVALIDOS_SEGUNDOS = 600

_invalidos_en_memoria: dict = {}
_candado_memoria = threading.Lock()


def _clave_invalidos(ip: str) -> str:
    return f"{PREFIJO}enlaces-invalidos:{ip}"


def contar_enlaces_invalidos(ip: str) -> int:
    redis = cliente_redis()
    if redis is not None:
        try:
            return int(redis.get(_clave_invalidos(ip)) or 0)
        except Exception as exc:  # noqa: BLE001
            avisar_caida("contar_enlaces_invalidos", exc)
    with _candado_memoria:
        cantidad, vence = _invalidos_en_memoria.get(ip, (0, 0.0))
        return cantidad if vence > time.monotonic() else 0


def registrar_enlace_invalido(ip: str) -> int:
    redis = cliente_redis()
    if redis is not None:
        try:
            clave = _clave_invalidos(ip)
            tuberia = redis.pipeline()
            # SET NX EX crea la clave con su vencimiento solo la PRIMERA vez:
            # la ventana empieza con el primer inválido y no se estira con
            # cada intento nuevo. (Más compatible que EXPIRE ... NX, que
            # exige Redis 7.)
            tuberia.set(clave, 0, ex=VENTANA_ENLACES_INVALIDOS_SEGUNDOS, nx=True)
            tuberia.incr(clave)
            return int(tuberia.execute()[1])
        except Exception as exc:  # noqa: BLE001
            avisar_caida("registrar_enlace_invalido", exc)
    with _candado_memoria:
        ahora = time.monotonic()
        cantidad, vence = _invalidos_en_memoria.get(ip, (0, 0.0))
        if vence <= ahora:
            cantidad, vence = 0, ahora + VENTANA_ENLACES_INVALIDOS_SEGUNDOS
        _invalidos_en_memoria[ip] = (cantidad + 1, vence)
        return cantidad + 1


def guardia_enumeracion(request: Request):
    """Dependencia de los endpoints públicos del examen (ver arriba)."""
    ip = ip_real(request) or "desconocida"
    if contar_enlaces_invalidos(ip) >= UMBRAL_ENLACES_INVALIDOS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Se intentaron demasiados enlaces de evaluación inválidos desde esta red. "
                "Espera unos minutos y vuelve a abrir tu enlace."
            ),
        )
    try:
        yield
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            registrar_enlace_invalido(ip)
        raise
