"""Sentry con lo mínimo indispensable: el error y dónde ocurrió, nunca datos
de alumnos ni credenciales.

🆕 (sesión 2026-11-07, M4 de la revisión de seguridad previa al piloto)
Antes main.py y migraciones/env.py llamaban a `sentry_sdk.init()` con los
valores por defecto más `traces_sample_rate=1.0`:

- `include_local_variables` (por defecto True) adjunta las variables locales
  de cada frame del stack trace: un error en el scoring o en el PDF mandaba a
  un tercero (Sentry, fuera del Perú) nombres, DNI, respuestas y diagnósticos
  de menores — Ley 29733.
- El cuerpo de la petición (`max_request_body_size`, por defecto "medium")
  viajaba también: respuestas del examen, datos de filiación.
- La URL del examen ES la credencial del alumno (`/examen/{token}/...`), y
  la de la firma lleva su token: quedaban en `request.url`, en el nombre de
  la transacción, en los breadcrumbs y en el mensaje de log
  "Error no manejado en {path}".
- El 100 % de las trazas: en el plan gratuito agota la cuota en horas y
  multiplica lo que se envía.
- El worker de Celery (informes PDF, correos de alerta) no reportaba nada.

Ahora todo pasa por `iniciar_sentry(componente)`. Sin `SENTRY_DSN` no hace
nada. Lo que se envía pasa por `limpiar_evento` (before_send), que se queda
solo con método + URL sin query y con los tokens tapados, y borra cookies,
cabeceras, cuerpo, usuario, variables locales y argumentos de tareas aunque
una integración los vuelva a poner.
"""
import logging
import os
import re

from core.entorno import ENTORNO

logger = logging.getLogger("aurorasoft")

TAPADO = "[tapado]"

# Rutas cuyo segmento es una credencial: el enlace del examen y la firma.
_PATRONES_RUTA = (
    re.compile(r"(/examen/)[^/?#\s]+"),
    re.compile(r"(/comenzar-test/)[^/?#\s]+"),
    re.compile(r"(/firma/)[^/?#\s]+"),
)
# Red de seguridad para cualquier otro token largo (hex, urlsafe, JWT)
# que aparezca en un texto: 24+ caracteres sin espacios de ese alfabeto.
_PATRON_TOKEN_SUELTO = re.compile(r"\b[A-Za-z0-9_\-]{24,}(?:\.[A-Za-z0-9_\-]{8,}){0,2}\b")
_PATRON_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PATRON_DNI = re.compile(r"\b\d{8}\b")

# Únicas cabeceras que se conservan: no identifican a nadie.
CABECERAS_PERMITIDAS = {"user-agent", "content-type", "content-length", "accept", "origin"}


def tapar_texto(texto):
    """Quita tokens de ruta, tokens sueltos, correos y DNI de un texto."""
    if not isinstance(texto, str) or not texto:
        return texto
    for patron in _PATRONES_RUTA:
        texto = patron.sub(lambda m: m.group(1) + TAPADO, texto)
    texto = _PATRON_TOKEN_SUELTO.sub(TAPADO, texto)
    texto = _PATRON_EMAIL.sub("[correo]", texto)
    texto = _PATRON_DNI.sub("[dni]", texto)
    return texto


def _limpiar_request(request):
    if not isinstance(request, dict):
        return {}
    limpio = {}
    if "method" in request:
        limpio["method"] = request["method"]
    if isinstance(request.get("url"), str):
        limpio["url"] = tapar_texto(request["url"].split("?", 1)[0])
    cabeceras = request.get("headers")
    if isinstance(cabeceras, dict):
        limpio["headers"] = {k: v for k, v in cabeceras.items() if k.lower() in CABECERAS_PERMITIDAS}
    # Fuera a propósito: cookies, data (cuerpo), query_string, env (IP).
    return limpio


def _limpiar_stacktrace(stacktrace):
    if isinstance(stacktrace, dict):
        for frame in stacktrace.get("frames") or []:
            if isinstance(frame, dict):
                frame.pop("vars", None)


def limpiar_evento(evento, _hint=None):
    """before_send / before_send_transaction de Sentry."""
    if not isinstance(evento, dict):
        return evento
    if "request" in evento:
        evento["request"] = _limpiar_request(evento["request"])
    evento.pop("user", None)
    evento.pop("server_name", None)  # nombre de la máquina: no aporta y la identifica
    if isinstance(evento.get("transaction"), str):
        evento["transaction"] = tapar_texto(evento["transaction"])

    contextos = evento.get("contexts")
    if isinstance(contextos, dict):
        # La integración de Celery adjunta args/kwargs de la tarea.
        contextos.pop("celery-job", None)

    excepciones = (evento.get("exception") or {}).get("values") or []
    for exc in excepciones:
        if isinstance(exc, dict):
            exc["value"] = tapar_texto(exc.get("value"))
            _limpiar_stacktrace(exc.get("stacktrace"))
    for hilo in (evento.get("threads") or {}).get("values") or []:
        if isinstance(hilo, dict):
            _limpiar_stacktrace(hilo.get("stacktrace"))

    if isinstance(evento.get("logentry"), dict):
        evento["logentry"]["message"] = tapar_texto(evento["logentry"].get("message"))
        evento["logentry"].pop("params", None)
        evento["logentry"].pop("formatted", None)
    if isinstance(evento.get("message"), str):
        evento["message"] = tapar_texto(evento["message"])
    evento.pop("extra", None)

    migas = evento.get("breadcrumbs")
    valores = migas.get("values") if isinstance(migas, dict) else migas
    if isinstance(valores, list):
        limpias = [limpiar_miga(m, None) for m in valores]
        limpias = [m for m in limpias if m is not None]
        if isinstance(migas, dict):
            migas["values"] = limpias
        else:
            evento["breadcrumbs"] = limpias
    return evento


def limpiar_miga(miga, _hint=None):
    """before_breadcrumb: sin SQL (lleva datos de búsqueda) y sin tokens."""
    if not isinstance(miga, dict):
        return miga
    if miga.get("category") == "query":
        return None
    if isinstance(miga.get("message"), str):
        miga["message"] = tapar_texto(miga["message"])
    datos = miga.get("data")
    if isinstance(datos, dict):
        miga["data"] = {
            k: tapar_texto(v.split("?", 1)[0]) if k == "url" and isinstance(v, str) else v
            for k, v in datos.items()
            if k in ("url", "method", "status_code", "reason")
        }
    return miga


def _tasa_trazas():
    try:
        tasa = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0"))
    except ValueError:
        return 0.0
    return min(max(tasa, 0.0), 1.0)


def opciones_sentry(componente):
    """Argumentos de sentry_sdk.init() — separados para poder probarlos."""
    return dict(
        dsn=os.getenv("SENTRY_DSN"),
        environment=ENTORNO,
        release=os.getenv("SENTRY_RELEASE") or None,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        max_breadcrumbs=30,
        # Por defecto 0: solo errores. Para medir rendimiento en el piloto,
        # SENTRY_TRACES_SAMPLE_RATE=0.05 o similar (las trazas pasan por el
        # mismo limpiar_evento).
        traces_sample_rate=_tasa_trazas(),
        before_send=limpiar_evento,
        before_send_transaction=limpiar_evento,
        before_breadcrumb=limpiar_miga,
    )


def iniciar_sentry(componente):
    """Activa Sentry si hay SENTRY_DSN. componente: 'api', 'worker', 'beat', 'migraciones'."""
    if not os.getenv("SENTRY_DSN"):
        return False
    import sentry_sdk

    sentry_sdk.init(**opciones_sentry(componente))
    sentry_sdk.set_tag("componente", componente)
    logger.info("Sentry activo para '%s' (entorno %s).", componente, ENTORNO)
    return True
