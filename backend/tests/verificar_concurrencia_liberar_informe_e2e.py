"""Regresión dirigida de la carrera `liberar_informe`/`actualizar_revision_informe`
vs. `reprocesar`, encontrada en la auditoría de bugs/escalabilidad de la sesión
2026-10-16 (ver docs/informes-psicometricos.md, "Riesgo de pisada entre
liberar/revisión y reprocesar").

Contexto: tanto `liberar_informe` como `actualizar_revision_informe` escriben
`Inscripcion.informe_liberado`/`.resultado_visible_alumno` — los MISMOS dos
campos que `reprocesar_informe_de_inscripcion` recalcula tras corregir un
Baremo. `reprocesar` ya bloqueaba la fila (`crud.
bloquear_inscripcion_para_reprocesar`, `with_for_update().populate_existing()`),
pero `liberar_informe`/`actualizar_revision_informe` la leían con un `.first()`
plano, sin bloqueo — dos acciones casi simultáneas sobre la MISMA inscripción
(un admin corrigiendo un baremo vía reprocesar, un psicólogo liberando/revisando
el mismo caso) podían intercalarse de forma NO determinista: el orden real de
ejecución dependía del azar de scheduling, no de qué request llegó primero.

El arreglo: `liberar_informe`/`actualizar_revision_informe` ahora también usan
`crud.bloquear_inscripcion_para_reprocesar()` (mismo candado, reusado tal cual
— su lógica es completamente genérica, nada depende de quién lo llame) antes
de leer/escribir. Esto NO decide "de quién es la decisión clínica correcta"
(esa es una pregunta de coordinación operativa, no un bug de datos — ver el
acknowledgment ya existente sobre "no se puede recall un PDF ya descargado"
para el mismo tipo de límite aceptado) — lo que sí garantiza es que cada
acción siempre lee el estado YA confirmado por la otra antes de decidir, en
vez de una lectura obsoleta tomada antes de que la otra corriera.

Este archivo verifica el mecanismo de forma determinista (dos sesiones
SQLAlchemy reales, con barrera + sleep — mismo estilo que
`verificar_concurrencia_finalizar_e2e.py`/`verificar_concurrencia_campana_e2e.py`):
un hilo "reprocesador" retiene el informe bajo el candado, y un hilo
"liberador" que intenta el mismo candado debe esperar y, al conseguirlo, ver
el estado YA retenido por el reprocesador — nunca una lectura previa a esa
corrección.

Uso:
    python -m tests.verificar_concurrencia_liberar_informe_e2e
    python -m tests.verificar_concurrencia_liberar_informe_e2e --limpiar
"""

import argparse
import inspect
import os
import sys
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

import modulos.superadmin.crud  # noqa: E402,F401  (ver nota de import circular)
from core.database import SessionLocal  # noqa: E402
from modulos.educativo import crud as edu_crud, models as edu_models, router as edu_router  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

PREFIJO = "ZZLIBCONC"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def exigir(respuesta, esperado, contexto):
    if respuesta.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {respuesta.status_code}")
        print(f"   {respuesta.text[:400]}")
        sys.exit(1)
    return respuesta.json() if respuesta.text else None


def pedir_con_reintento(metodo, url, contexto, **kwargs):
    for intento in range(8):
        respuesta = metodo(url, timeout=30, **kwargs)
        if respuesta.status_code != 429:
            return respuesta
        espera = 13
        print(f"    (429 en {contexto}; esperando {espera}s a que se abra la ventana)")
        time.sleep(espera)
    return respuesta


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ------------------------------------------------------------------
    print("\n0 · Montaje: institución, psicólogo, prueba con baremo de alerta, examen finalizado y retenido")

    tok_super = exigir(pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login superadmin",
        data={"username": os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
              "password": os.getenv("SUPERADMIN_PASSWORD")}),
        200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst = exigir(requests.post(
        f"{API}/instituciones/",
        json={"nombre": f"{PREFIJO} Colegio {sello}", "tipo": "Colegio",
              "email_contacto": f"contacto.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    inst_id = inst["id"]
    correo_psi = f"{PREFIJO.lower()}.psicologo.{sello}@ejemplo.com"
    exigir(pedir_con_reintento(
        requests.post, f"{API}/auth/registro", "registro psicólogo",
        json={"email": correo_psi, "password": "ClaveDePrueba123",
              "nombre_completo": f"{PREFIJO} Psicólogo", "rol": "psicologo",
              "institucion_id": inst_id},
        headers=h_super), 200, "Usuario psicólogo")
    tok_psi = exigir(pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login psicólogo",
        data={"username": correo_psi, "password": "ClaveDePrueba123"}),
        200, "Login psicólogo")["access_token"]
    h_psi = {"Authorization": f"Bearer {tok_psi}"}

    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    prueba = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba candado compartido",
              "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=h_psi, timeout=30), 200, "Crear prueba")
    exigir(requests.post(
        f"{API}/educativo/pruebas/carga-masiva/",
        json={"prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
              "preguntas": [{"texto_pregunta": "i1", "orden": 1, "nombre_dimension": "D", "opciones": opciones}]},
        headers=h_psi, timeout=30), 200, "Carga masiva")
    completa = exigir(requests.get(
        f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=h_psi, timeout=30), 200, "Ver prueba")
    dimension = completa["dimensiones"][0]
    pregunta = dimension["preguntas"][0]
    exigir(requests.post(
        f"{API}/educativo/baremos/",
        json={"dimension_id": dimension["id"], "puntaje_minimo": 0, "puntaje_maximo": 1,
              "nivel": "Alto", "es_alerta": True, "interpretacion": "Alerta."},
        headers=h_psi, timeout=30), 200, "Baremo de alerta")

    campana = exigir(requests.post(
        f"{API}/educativo/campanas/",
        json={"prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Campaña")
    persona = exigir(requests.post(
        f"{API}/admin/personas/",
        json={"institucion_id": inst_id, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba"},
        headers=h_psi, timeout=30), 200, "Persona")
    exigir(requests.post(
        f"{API}/admin/personas/{persona['id']}/consentimiento",
        json={"persona_id": persona["id"], "institucion_id": inst_id,
              "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=h_psi, timeout=30), 200, "Consentimiento")
    matricula = exigir(requests.post(
        f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
        json=[persona["id"]], headers=h_psi, timeout=30), 200, "Matrícula")
    token = matricula["generados"][0]["token"]
    inscripcion_id = matricula["generados"][0]["id"]

    exigir(requests.post(
        f"{API}/educativo/comenzar-test/{token}",
        json={"nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar test")
    opcion_si = next(o["id"] for o in pregunta["opciones"] if o["valor_puntuacion"] == 1)
    exigir(requests.post(
        f"{API}/educativo/examen/{token}/guardar",
        json={"respuestas": [{"pregunta_id": pregunta["id"], "opcion_id": opcion_si}]}, timeout=30),
        200, "Guardar respuesta")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=30), 200, "Finalizar")

    estado_inicial = sql_uno("select informe_liberado from edu_inscripciones where id=:i", i=inscripcion_id)[0]
    comprobar("La inscripción de prueba nace retenida (alerta)", estado_inicial is False,
              f"informe_liberado={estado_inicial!r}")

    # ==================================================================
    print("\nMecanismo, determinista (dos sesiones ORM reales, sin HTTP)")

    fuente_liberar = inspect.getsource(edu_router.liberar_informe)
    comprobar(
        "liberar_informe usa crud.bloquear_inscripcion_para_reprocesar antes de escribir "
        "(si esto cambia por una consulta inline, revisar que esta prueba siga "
        "ejercitando el código real y no una copia)",
        "bloquear_inscripcion_para_reprocesar(" in fuente_liberar,
    )
    fuente_revision = inspect.getsource(edu_router.actualizar_revision_informe)
    comprobar(
        "actualizar_revision_informe también usa crud.bloquear_inscripcion_para_reprocesar",
        "bloquear_inscripcion_para_reprocesar(" in fuente_revision,
    )

    trazas = []
    traza_lock = threading.Lock()
    t_inicio = time.perf_counter()

    def trazar(msg):
        with traza_lock:
            trazas.append(f"+{time.perf_counter()-t_inicio:.4f} {msg}")

    barrera = threading.Barrier(2)
    resultado_liberador = {}

    def hilo_reprocesador(espera_antes_de_confirmar):
        db = SessionLocal()
        try:
            barrera.wait()
            trazar("[REPROCESADOR] intentando adquirir el candado")
            fila = edu_crud.bloquear_inscripcion_para_reprocesar(db, inscripcion_id)
            trazar("[REPROCESADOR] candado adquirido")
            time.sleep(espera_antes_de_confirmar)
            # Simula lo que reprocesar_informe_de_inscripcion escribiría tras
            # recalcular: ambos campos pasan (o se mantienen) en False.
            fila.informe_liberado = False
            fila.resultado_visible_alumno = False
            db.commit()
            trazar("[REPROCESADOR] COMMIT hecho (retenido)")
        finally:
            db.close()

    def hilo_liberador(espera_antes_de_intentar):
        db = SessionLocal()
        try:
            barrera.wait()
            time.sleep(espera_antes_de_intentar)  # deja que el reprocesador adquiera el candado primero
            trazar("[LIBERADOR] intentando adquirir el candado (debería esperar al reprocesador)")
            fila = edu_crud.bloquear_inscripcion_para_reprocesar(db, inscripcion_id)
            trazar(f"[LIBERADOR] candado adquirido, informe_liberado visto = {fila.informe_liberado}")
            resultado_liberador["informe_liberado_visto"] = fila.informe_liberado
        finally:
            db.rollback()
            db.close()

    th_reprocesador = threading.Thread(target=hilo_reprocesador, args=(0.4,))
    th_liberador = threading.Thread(target=hilo_liberador, args=(0.1,))
    th_reprocesador.start()
    th_liberador.start()
    th_reprocesador.join()
    th_liberador.join()

    for linea in trazas:
        print("    " + linea)

    comprobar(
        "El liberador ve el estado YA confirmado por el reprocesador (retenido), no una "
        "lectura obsoleta de antes de esa corrección — antes del arreglo, liberar_informe/"
        "actualizar_revision_informe no bloqueaban esta fila en absoluto, así que esta "
        "lectura podía llegar obsoleta y una escritura posterior pisaba la retención sin que "
        "nadie lo notara",
        resultado_liberador.get("informe_liberado_visto") is False,
        f"informe_liberado visto por el liberador = {resultado_liberador.get('informe_liberado_visto')!r}",
    )

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO CONCURRENCIA LIBERAR/REVISION vs REPROCESAR: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


def sql(consulta, **params):
    with MOTOR.connect() as cx:
        return cx.execute(text(consulta), params).fetchall()


def sql_uno(consulta, **params):
    filas = sql(consulta, **params)
    return filas[0] if filas else None


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    with motor.begin() as cx:
        for consulta in [
            f"""DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                   SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%')""",
            f"DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%'",
            f"""DELETE FROM edu_baremos WHERE dimension_id IN (
                   SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p
                   ON d.prueba_id=p.id WHERE p.nombre_tecnico LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_opciones WHERE pregunta_id IN (
                   SELECT pr.id FROM edu_preguntas pr JOIN edu_pruebas p
                   ON pr.prueba_id=p.id WHERE p.nombre_tecnico LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_preguntas WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_dimensiones WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')""",
            f"DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%'",
            f"""DELETE FROM consentimientos_informados WHERE persona_id IN (
                   SELECT id FROM personas WHERE nombres LIKE '{PREFIJO}%')""",
            f"DELETE FROM personas WHERE nombres LIKE '{PREFIJO}%'",
            f"DELETE FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%'",
            f"DELETE FROM instituciones WHERE nombre LIKE '{PREFIJO}%'",
        ]:
            cx.execute(text(consulta))
    print(f"Datos {PREFIJO} eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
