"""B3 de la revisión de seguridad (sesión 2026-11-08): las alertas por correo
no llevan el nombre del alumno por Redis ni lo escriben en los logs — ver
core/email_service.nombre_de_inscripcion.

Sin servidor ni base de desarrollo ni SMTP: la tabla real `edu_inscripciones`
en un SQLite en memoria, el envío de correo reemplazado por uno que guarda lo
que se habría enviado, y los logs capturados.

    python -m tests.test_alertas_sin_datos_alumno_unitario
"""
import inspect
import logging
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.database as database
from core import email_service
from modulos.educativo import models
from modulos.educativo import router as educativo_router

RESULTADOS = {"ok": 0, "fallo": 0}
NOMBRE = "Valentina ZZB3 Quispe"


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


class _CapturaLogs(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lineas = []

    def emit(self, registro):
        self.lineas.append(registro.getMessage())


def preparar():
    motor = create_engine("sqlite://")
    models.Inscripcion.__table__.create(motor)
    Sesion = sessionmaker(bind=motor)
    db = Sesion()
    insc = models.Inscripcion(evaluacion_id=1, token="tok-zzb3", nombre_completo=NOMBRE, estado="Finalizado")
    db.add(insc)
    db.commit()
    database.SessionLocal = Sesion  # nombre_de_inscripcion importa SessionLocal en cada llamada
    return insc.id


def correr(tarea, *args, envio_ok=True):
    enviados = []
    email_service.enviar_correo = lambda d, asunto, cuerpo: enviados.append((d, asunto, cuerpo)) or envio_ok
    captura = _CapturaLogs()
    logging.getLogger("aurorasoft").addHandler(captura)
    error = None
    try:
        tarea.apply(args=args, throw=True)
    except Exception as exc:  # noqa: BLE001 — el retry de Celery agota y relanza
        error = exc
    finally:
        logging.getLogger("aurorasoft").removeHandler(captura)
    return enviados, captura.lineas, error


def test_alerta_riesgo(insc_id):
    print("\n[1] enviar_alerta_riesgo con el id de la inscripción")
    enviados, logs, error = correr(email_service.enviar_alerta_riesgo,
                                  ["psi@ejemplo.pe"], insc_id, ["Severo"], [], [])
    comprobar("se envía un correo", len(enviados) == 1, error)
    comprobar("el correo SÍ lleva el nombre del alumno (lo busca el worker en la base)",
              enviados and NOMBRE in enviados[0][2])
    comprobar("el nivel de riesgo sigue en el correo", enviados and "Severo" in enviados[0][2])
    comprobar("ningún log menciona el nombre", all(NOMBRE not in l for l in logs), logs)

    print("\n[2] Sin destinatarios: el log de error dice la inscripción, no el nombre")
    _, logs, _ = correr(email_service.enviar_alerta_riesgo, [], insc_id, ["Severo"])
    comprobar("se registró el error", any("ningún destinatario" in l for l in logs), logs)
    comprobar("el error nombra la inscripción", any(f"inscripción {insc_id}" in l for l in logs), logs)
    comprobar("y no el nombre del alumno", all(NOMBRE not in l for l in logs), logs)

    print("\n[3] Todos los envíos fallan: el error que va al reintento (y a Sentry) no lleva el nombre")
    _, logs, error = correr(email_service.enviar_alerta_riesgo,
                            ["psi@ejemplo.pe"], insc_id, ["Severo"], envio_ok=False)
    comprobar("la tarea termina en error (reintento agotado)", error is not None)
    comprobar("el mensaje del error no tiene el nombre", NOMBRE not in str(error), str(error))
    comprobar("el mensaje del error sí identifica la inscripción", f"inscripción {insc_id}" in str(error), str(error))


def test_regresion(insc_id):
    print("\n[4] enviar_alerta_regresion_informe_liberado con el id")
    enviados, logs, error = correr(email_service.enviar_alerta_regresion_informe_liberado,
                                  "psi@ejemplo.pe", insc_id, 1)
    comprobar("se envía el aviso", len(enviados) == 1, error)
    comprobar("el aviso lleva el nombre del alumno", enviados and NOMBRE in enviados[0][2])
    comprobar("ningún log menciona el nombre", all(NOMBRE not in l for l in logs), logs)


def test_formato_anterior():
    print("\n[5] Compatibilidad: una alerta encolada con el formato viejo (nombre como texto)")
    enviados, logs, _ = correr(email_service.enviar_alerta_riesgo, ["psi@ejemplo.pe"], "Alumno Viejo ZZB3", ["Severo"])
    comprobar("se envía igual, con ese nombre en el correo", enviados and "Alumno Viejo ZZB3" in enviados[0][2])
    _, logs, _ = correr(email_service.enviar_alerta_riesgo, [], "Alumno Viejo ZZB3", ["Severo"])
    comprobar("y tampoco escribe ese nombre en los logs", all("Alumno Viejo ZZB3" not in l for l in logs), logs)
    enviados, _, _ = correr(email_service.enviar_alerta_riesgo, ["psi@ejemplo.pe"], 999999, ["Severo"])
    comprobar("id inexistente: se avisa igual, como 'sin nombre registrado'",
              enviados and "sin nombre registrado" in enviados[0][2])


def test_router():
    print("\n[6] El router encola el id, nunca el nombre")
    fuente = inspect.getsource(educativo_router)
    comprobar("ninguna tarea recibe inscripcion.nombre_completo", 'nombre_completo or "Evaluado"' not in fuente)
    comprobar("las 3 llamadas (finalizar, reprocesar, regresión) pasan inscripcion.id",
              fuente.count("inscripcion.id,  # B3: el id, nunca el nombre, viaja por Redis") == 3)


if __name__ == "__main__":
    insc_id = preparar()
    test_alerta_riesgo(insc_id)
    test_regresion(insc_id)
    test_formato_anterior()
    test_router()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO ALERTAS SIN DATOS DEL ALUMNO: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
