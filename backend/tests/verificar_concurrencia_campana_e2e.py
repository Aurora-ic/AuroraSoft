"""Regresión dirigida de la carrera `actualizar_campana` (cambio de `prueba_id`)
vs. `matricular_roster_en_campana`, encontrada en la auditoría de bugs/
escalabilidad de la sesión 2026-10-16 (ver docs/informes-psicometricos.md,
"Ciclo de vida de campaña y reproceso de informe").

Contexto: `actualizar_campana` solo permite cambiar `Evaluacion.prueba_id`
cuando `contar_inscripciones_de_campana()` (un `COUNT` plano, sin bloqueo)
devuelve 0 — el candado 409 existe específicamente para que un link mágico ya
emitido no quede huérfano de su prueba/preguntas/baremos originales (todo el
flujo de examen resuelve `evaluacion.prueba_id` EN VIVO, nunca un snapshot
tomado al matricular). `matricular_roster_en_campana` tampoco bloqueaba la fila
de `Evaluacion` al crear inscripciones nuevas. Dos requests casi simultáneos —
uno cambiando `prueba_id`, otro matriculando al primer alumno de la campaña —
podían pasar AMBOS su propio chequeo antes de que cualquiera confirmara: el
`COUNT` del editor leía 0 (la inscripción del matriculador todavía no existía
en ese instante), así que el 409 nunca se disparaba aunque, microsegundos
después, la campaña terminara con inscripciones Y una prueba distinta de la
que esas inscripciones asumían.

El arreglo (`crud.bloquear_evaluacion_para_editar`, mismo mecanismo que
`bloquear_inscripcion_para_finalizar`/`bloquear_inscripcion_para_reprocesar`)
hace que ambas rutas bloqueen la MISMA fila de `Evaluacion` con
`with_for_update()` antes de leer/decidir nada — quien llega segundo espera a
que el primero confirme y entonces ve el estado YA COMMITEADO, nunca una
lectura obsoleta.

Este archivo reproduce el mecanismo de forma determinista (dos sesiones
SQLAlchemy reales, con barrera + sleep — no depende de que una carrera real
ocurra por azar, mismo estilo que `verificar_concurrencia_finalizar_e2e.py`):
un hilo "matriculador" inserta una `Inscripcion` real bajo el candado, y un
hilo "editor" que intenta adquirir el mismo candado debe esperar y, al
conseguirlo, ver el conteo YA actualizado (1, no 0) — exactamente la lectura
que antes del arreglo podía llegar obsoleta.

Uso:
    python -m tests.verificar_concurrencia_campana_e2e
    python -m tests.verificar_concurrencia_campana_e2e --limpiar
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

PREFIJO = "ZZCAMPCONC"
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
    for intento in range(6):
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
    print("\n0 · Montaje mínimo: institución, psicólogo, prueba, campaña sin inscripciones")

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

    prueba = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-{sello}",
              "nombre_publico": "Prueba concurrencia campaña",
              "escala_minima": 0, "escala_maxima": 3, "modo_calculo": "likert_suma"},
        headers=h_psi, timeout=30), 200, "Crear prueba")

    campana = exigir(requests.post(
        f"{API}/educativo/campanas/",
        json={"prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña {sello}",
              "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Campaña")
    evaluacion_id = campana["id"]
    comprobar("Campaña de prueba montada sin inscripciones",
              edu_crud.contar_inscripciones_de_campana(SessionLocal(), evaluacion_id) == 0)

    # ==================================================================
    print("\nMecanismo, determinista (dos sesiones ORM reales, sin HTTP)")

    fuente_router_editar = inspect.getsource(edu_router.editar_campana)
    comprobar(
        "editar_campana delega en crud.actualizar_campana (el candado vive ahí, no en el router)",
        "crud.actualizar_campana(" in fuente_router_editar,
    )
    fuente_crud_actualizar = inspect.getsource(edu_crud.actualizar_campana)
    comprobar(
        "actualizar_campana usa bloquear_evaluacion_para_editar al cambiar prueba_id "
        "(si esto cambia por una consulta inline, revisar que esta prueba siga "
        "ejercitando el código real y no una copia)",
        "bloquear_evaluacion_para_editar(" in fuente_crud_actualizar,
    )
    fuente_crud_matricular = inspect.getsource(edu_crud.matricular_roster_en_campana)
    comprobar(
        "matricular_roster_en_campana también usa bloquear_evaluacion_para_editar "
        "para obtener la Evaluacion (misma fila, mismo candado que el editor)",
        "bloquear_evaluacion_para_editar(" in fuente_crud_matricular,
    )

    trazas = []
    traza_lock = threading.Lock()
    t_inicio = time.perf_counter()

    def trazar(msg):
        with traza_lock:
            trazas.append(f"+{time.perf_counter()-t_inicio:.4f} {msg}")

    barrera = threading.Barrier(2)
    resultado_editor = {}

    def hilo_matriculador(espera_antes_de_confirmar):
        db = SessionLocal()
        try:
            barrera.wait()
            trazar("[MATRICULADOR] intentando adquirir el candado")
            evaluacion = edu_crud.bloquear_evaluacion_para_editar(db, evaluacion_id)
            trazar("[MATRICULADOR] candado adquirido")
            time.sleep(espera_antes_de_confirmar)
            nueva = edu_models.Inscripcion(
                evaluacion_id=evaluacion.id,
                token=f"{PREFIJO}-{sello}-matric",
                estado="Pendiente",
            )
            db.add(nueva)
            db.commit()
            trazar("[MATRICULADOR] COMMIT hecho (1 inscripción creada)")
        finally:
            db.close()

    def hilo_editor(espera_antes_de_intentar):
        db = SessionLocal()
        try:
            barrera.wait()
            time.sleep(espera_antes_de_intentar)  # deja que el matriculador adquiera el candado primero
            trazar("[EDITOR] intentando adquirir el candado (debería esperar al matriculador)")
            edu_crud.bloquear_evaluacion_para_editar(db, evaluacion_id)
            trazar("[EDITOR] candado adquirido")
            conteo = edu_crud.contar_inscripciones_de_campana(db, evaluacion_id)
            trazar(f"[EDITOR] conteo de inscripciones = {conteo}")
            resultado_editor["conteo"] = conteo
        finally:
            db.rollback()
            db.close()

    th_matriculador = threading.Thread(target=hilo_matriculador, args=(0.4,))
    th_editor = threading.Thread(target=hilo_editor, args=(0.1,))
    th_matriculador.start()
    th_editor.start()
    th_matriculador.join()
    th_editor.join()

    for linea in trazas:
        print("    " + linea)

    comprobar(
        "El editor ve el conteo YA confirmado por el matriculador (1), no una "
        "lectura obsoleta de 0 — antes del arreglo esta ventana permitía que "
        "actualizar_campana cambiara prueba_id aunque ya existiera una "
        "inscripción, saltándose el 409 que existe justo para impedirlo",
        resultado_editor.get("conteo") == 1,
        f"conteo visto por el editor = {resultado_editor.get('conteo')!r}",
    )

    # ==================================================================
    print("\nEnd-to-end real: una vez matriculado un alumno, el PATCH de prueba_id "
          "sigue siendo rechazado — confirma que el candado no rompió el 409 de siempre")

    conteo_final = edu_crud.contar_inscripciones_de_campana(SessionLocal(), evaluacion_id)
    comprobar("Quedó 1 inscripción real tras el hilo matriculador", conteo_final == 1,
              f"conteo={conteo_final}")

    prueba2 = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-B-{sello}",
              "nombre_publico": "Prueba concurrencia campaña (alterna)",
              "escala_minima": 0, "escala_maxima": 3, "modo_calculo": "likert_suma"},
        headers=h_psi, timeout=30), 200, "Crear segunda prueba")

    r_patch = requests.patch(
        f"{API}/educativo/campanas/{evaluacion_id}",
        json={"prueba_id": prueba2["id"]}, headers=h_psi, timeout=30)
    comprobar("PATCH prueba_id con inscripciones ya existentes -> 409 (candado sigue funcionando end-to-end)",
              r_patch.status_code == 409, f"status={r_patch.status_code} body={r_patch.text[:200]}")

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO CONCURRENCIA CAMPAÑA: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    with motor.begin() as cx:
        for consulta in [
            f"""DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                   SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%')""",
            f"DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%'",
            f"""DELETE FROM edu_preguntas WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')""",
            f"""DELETE FROM edu_dimensiones WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')""",
            f"DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%'",
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
