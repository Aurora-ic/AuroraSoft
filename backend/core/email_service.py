import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

from core.cola_tareas import app as celery_app

logger = logging.getLogger("aurorasoft")

# Configuración de Servidor SMTP y Credenciales desde .env
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USUARIO = os.getenv("EMAIL_USUARIO", "")       # Tu correo real autenticado
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")     # Tu contraseña de aplicación

# Configuración de Remitente y Frontend
EMAIL_REMITENTE = os.getenv("EMAIL_REMITENTE", f"AuroraSoft <{EMAIL_USUARIO}>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> bool:
    """Función genérica de envío — la reutilizas para recuperación, notificaciones, etc."""
    if not EMAIL_USUARIO or not EMAIL_PASSWORD:
        logger.warning("⚠️ [EMAIL SERVICE] Credenciales de correo (EMAIL_USUARIO/EMAIL_PASSWORD) no configuradas.")
        return False

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = EMAIL_REMITENTE
    mensaje["To"] = destinatario
    mensaje.attach(MIMEText(cuerpo_html, "html"))

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as servidor:
            servidor.starttls()
            # Se autentica usando EMAIL_USUARIO y EMAIL_PASSWORD
            servidor.login(EMAIL_USUARIO, EMAIL_PASSWORD)
            servidor.sendmail(EMAIL_USUARIO, destinatario, mensaje.as_string())
            
        logger.info(f"Correo enviado exitosamente a {destinatario}")
        return True
    except Exception as e:
        logger.error(f"Error enviando correo a {destinatario}: {e}", exc_info=True)
        return False


def enviar_correo_recuperacion(destinatario: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/resetear-password?token={token}"
    cuerpo = f"""
    <p>Recibimos una solicitud para restablecer tu contraseña de AuroraSoft.</p>
    <p><a href="{link}">Haz clic aquí para crear una nueva contraseña</a></p>
    <p>Este link expira en 1 hora. Si no lo solicitaste, ignora este correo.</p>
    """
    return enviar_correo(destinatario, "Recupera tu contraseña — AuroraSoft", cuerpo)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def enviar_alerta_riesgo(
    self,
    destinatarios,
    nombre_alumno: str,
    dimensiones_en_riesgo: list,
    dimensiones_sin_baremo: list = None,
    reglas_con_error: list = None,
) -> bool:
    """Avisa de un resultado que exige revisión profesional.

    `destinatarios` acepta un correo suelto o una lista: la alerta se manda a
    toda la cadena de respaldo institucional (C-13), no solo al creador de la
    campaña, para que un usuario desactivado no silencie un caso crítico.

    Cubre los dos motivos de retención:
      - el alumno alcanzó un tramo marcado como alerta;
      - la interpretación no pudo completarse por falta de baremo, que no es
        un resultado "sin riesgo" sino un caso pendiente de revisar.

    🆕 Fase 2 (Celery, ver core/cola_tareas.py) — tarea real con reintento.
    `self.request.id` (el job_id real) y `self.request.retries` no se
    registran en `RegistroTareaAsincrona`: esa bitácora es solo para las dos
    tareas de generación de contenido (informe/documento), nunca para
    emails, que no tienen una fila propia que actualizar.
    """
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]
    destinatarios = [d for d in (destinatarios or []) if d]

    if not destinatarios:
        logger.error(
            "No hay ningún destinatario para la alerta de '%s'. El caso queda "
            "retenido en la plataforma pero nadie ha sido notificado.",
            nombre_alumno or "evaluado sin nombre",
        )
        return False

    # 🔒 Fase 4 — `nombre_alumno` y los nombres de dimensión llegan de datos
    # cargados por el colegio (matrícula, carga masiva de pruebas): nada
    # impide que alguien escriba "<script>..." como nombre. Antes se
    # interpolaban tal cual en un correo HTML — inyección hacia quien lo abre
    # (el psicólogo o admin que recibe la alerta). Se escapan aquí, en el
    # borde de salida, para no tener que auditar cada punto de entrada.
    nombre_seguro = escape(nombre_alumno) if nombre_alumno else "sin nombre registrado"

    secciones = []
    if dimensiones_en_riesgo:
        filas = "".join(f"<li>{escape(d)}</li>" for d in dimensiones_en_riesgo)
        secciones.append(
            "<p>Obtuvo un nivel que requiere atención en:</p>"
            f"<ul>{filas}</ul>"
        )
    if dimensiones_sin_baremo:
        filas = "".join(f"<li>{escape(d)}</li>" for d in dimensiones_sin_baremo)
        secciones.append(
            "<p><strong>No se pudo interpretar</strong> el resultado de estas "
            "dimensiones porque no hay un baremo aplicable cargado:</p>"
            f"<ul>{filas}</ul>"
            "<p>El informe queda retenido hasta que se complete la configuración "
            "y se revise el caso. Esto <em>no</em> significa que el alumno no "
            "tenga riesgo: significa que todavía no se ha podido determinar.</p>"
        )
    if reglas_con_error:
        filas = "".join(f"<li>{escape(r)}</li>" for r in reglas_con_error)
        secciones.append(
            "<p><strong>Una regla de interpretación configurada para esta prueba "
            "no se pudo evaluar</strong>:</p>"
            f"<ul>{filas}</ul>"
            "<p>El informe queda retenido hasta que se revise la configuración de "
            "esa regla. Esto <em>no</em> significa que el alumno no tenga riesgo.</p>"
        )

    cuerpo = (
        f"<p>El estudiante <strong>{nombre_seguro}</strong> "
        "tiene un resultado pendiente de revisión profesional.</p>"
        + "".join(secciones)
        + "<p>Revisa su informe completo en la plataforma.</p>"
    )

    enviados = [
        enviar_correo(correo, "⚠️ Resultado que requiere atención — AuroraSoft", cuerpo)
        for correo in destinatarios
    ]
    if not any(enviados):
        # 🆕 Reintenta SOLO cuando TODOS los envíos fallaron: en ese caso
        # nadie recibió nada todavía, así que reintentar el lote completo
        # no duplica ningún correo ya entregado. Si al menos uno tuvo
        # éxito, no se reintenta — eso reenviaría a quien ya lo recibió.
        try:
            raise RuntimeError(
                f"Los {len(destinatarios)} envío(s) de la alerta de riesgo de "
                f"'{nombre_alumno}' fallaron."
            )
        except RuntimeError as exc:
            raise self.retry(exc=exc)
    return any(enviados)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def enviar_alerta_regresion_informe_liberado(
    self,
    destinatario: str,
    nombre_alumno: str,
    numero_version_anterior: int,
) -> bool:
    """Avisa a quien había liberado un informe que un reproceso lo retuvo de nuevo.

    Riesgo documentado en docs/gaps-pendientes.md: un reproceso puede
    corregir un baremo y retener de nuevo un informe que ya estaba
    liberado y visible — es decir, un resultado que el alumno/apoderado
    pudo haber descargado antes de la corrección. Este correo NO resuelve
    ese riesgo de fondo (no hay forma de invalidar un PDF que ya salió de
    la plataforma), pero asegura que la persona con más contexto real —
    quien lo liberó originalmente — se entere puntualmente, en vez de
    depender de que alguien note la regresión revisando el historial de
    versiones a mano.

    Independiente de `enviar_alerta_riesgo`: esa otra alerta va a la
    cadena de respaldo institucional (creador de campaña, admins, etc.) y
    nunca asume que el destinatario fue quien liberó el informe antes.

    🆕 Fase 2 (Celery) — un único destinatario, así que a diferencia de
    `enviar_alerta_riesgo` acá no hay ambigüedad de "algunos sí, algunos
    no": si falla, reintentar es siempre seguro (nadie lo recibió).
    """
    nombre_seguro = escape(nombre_alumno) if nombre_alumno else "sin nombre registrado"
    cuerpo = (
        f"<p>El informe de <strong>{nombre_seguro}</strong> que tú liberaste "
        f"(versión {int(numero_version_anterior)}) acaba de quedar retenido de "
        "nuevo tras un reproceso que corrigió su interpretación.</p>"
        "<p><strong>Importante:</strong> si el alumno o su apoderado ya habían "
        "descargado el informe anterior, esa copia sigue en su poder — la "
        "plataforma no tiene forma de invalidarla ni de retirarla de "
        "circulación. Si corresponde, contáctalos directamente para aclarar "
        "la corrección.</p>"
        "<p>Revisa el caso actualizado en la plataforma.</p>"
    )
    exito = enviar_correo(
        destinatario, "⚠️ Un informe que liberaste quedó retenido de nuevo — AuroraSoft", cuerpo,
    )
    if not exito:
        try:
            raise RuntimeError(f"Falló el envío del aviso de regresión a {destinatario}.")
        except RuntimeError as exc:
            raise self.retry(exc=exc)
    return exito