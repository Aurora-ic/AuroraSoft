# core/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


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
# Las cifras dan margen de sobra a un uso normal: un examen de 40 ítems con
# autoguardado por respuesta son ~4 guardados/minuto por alumno.
#
# ⚠️ Despliegue: la IP sale de `request.client.host`. Detrás de un proxy
# inverso hay que arrancar uvicorn con --proxy-headers (y --forwarded-allow-ips)
# o todos los alumnos compartirían la IP del proxy. Y el contador vive en la
# memoria de cada proceso: con varios workers, cada uno cuenta por separado.

def clave_por_token(request) -> str:
    """Agrupa el conteo por enlace mágico en vez de por IP."""
    return "token:" + str(request.path_params.get("token", ""))


LIMITES_EXAMEN = {
    #  endpoint              por token      por IP
    "intake":              ("10/minute",   "300/minute"),  # mismo tier que "comenzar": se llama una vez, antes de él
    # 🆕 asentimiento_texto — se llama junto con "intake", antes de que el
    # alumno acepte nada; mismo tier por el mismo motivo.
    "asentimiento_texto":  ("10/minute",   "300/minute"),
    "comenzar":            ("10/minute",   "300/minute"),
    "preguntas":           ("30/minute",   "600/minute"),
    "progreso":            ("30/minute",   "600/minute"),
    "guardar":             ("120/minute",  "1500/minute"),
    "finalizar":           ("5/minute",    "300/minute"),
    "estado_resultados":   ("30/minute",   "900/minute"),
    "informe_pdf":         ("10/minute",   "120/minute"),   # generar un PDF es caro
    "campos_socio":        ("30/minute",   "600/minute"),
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
