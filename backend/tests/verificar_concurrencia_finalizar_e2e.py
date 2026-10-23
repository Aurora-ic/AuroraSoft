"""Regresión dirigida del bug de doble envío concurrente en `finalizar_examen_seguro`.

Contexto (ver comentario en `modulos/educativo/router.py:finalizar_examen_seguro`,
Fase 2): la Fase 1 (sin bloqueo) y la Fase 2 (con `with_for_update()`) del
endpoint consultan la MISMA entidad `Inscripcion` en la MISMA `Session`. Antes
del arreglo, cuando dos envíos llegaban casi al mismo tiempo, el "perdedor"
esperaba correctamente a que Postgres liberara el candado de fila — pero al
desbloquearse, SQLAlchemy le devolvía el MISMO objeto Python que ya tenía en
su identity map desde la Fase 1 (sin refrescar sus atributos con la fila
recién confirmada), así que el candado de idempotencia
(`if inscripcion.estado == "Finalizado"`) nunca se disparaba para el
perdedor: recalculaba todo de nuevo, confirmaba una segunda vez, y disparaba
efectos secundarios duplicados (alerta de riesgo enviada dos veces, intento
duplicado de generar el informe -> UniqueViolation en
`uq_edu_informes_inscripcion`). El arreglo agrega `.populate_existing()` a la
consulta de la Fase 2 para forzar que SIEMPRE traiga el estado fresco.

Este archivo verifica el arreglo en dos niveles:

  PARTE A — mecanismo, determinista: dos sesiones SQLAlchemy reales, con
  temporización controlada (barrera + sleep, no depende de que una carrera
  real ocurra por azar), reproducen EXACTAMENTE la forma de las dos consultas
  del router (Fase 1 sin bloqueo + Fase 2 con `with_for_update()
  .populate_existing()`) sobre una fila real de prueba, y confirman que la
  Fase 2 del "perdedor" ve el valor recién confirmado por el "ganador", no el
  valor obsoleto de su Fase 1.

  PARTE B — end-to-end, realista: como el CASO 5 de `verificar_fase1_e2e.py`
  pero además confirma que el informe (edu_informes/edu_informe_versiones) y
  la alerta se generan UNA sola vez, no dos.

Uso:
    uvicorn main:app --port 8010            (con SMTP deshabilitado)
    python -m tests.verificar_concurrencia_finalizar_e2e
    python -m tests.verificar_concurrencia_finalizar_e2e --limpiar
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

PREFIJO = "ZZCONC"
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


def sql(consulta, **params):
    with MOTOR.connect() as cx:
        return cx.execute(text(consulta), params).fetchall()


def sql_uno(consulta, **params):
    filas = sql(consulta, **params)
    return filas[0] if filas else None


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ------------------------------------------------------------------
    print("\n0 · Montaje mínimo: institución, psicólogo, prueba con baremo de alerta")

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

    opciones = [
        {"texto_opcion": "Nunca", "valor_puntuacion": 0},
        {"texto_opcion": "A veces", "valor_puntuacion": 1},
        {"texto_opcion": "A menudo", "valor_puntuacion": 2},
        {"texto_opcion": "Siempre", "valor_puntuacion": 3},
    ]
    prueba = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-{sello}",
              "nombre_publico": "Prueba concurrencia",
              "escala_minima": 0, "escala_maxima": 3, "modo_calculo": "likert_suma"},
        headers=h_psi, timeout=30), 200, "Crear prueba")
    exigir(requests.post(
        f"{API}/educativo/pruebas/carga-masiva/",
        json={"prueba_id": prueba["id"],
              "dimensiones": [{"nombre": "Ansiedad", "descripcion": "dim"}],
              "preguntas": [
                  {"texto_pregunta": "Me siento nervioso", "orden": 1,
                   "nombre_dimension": "Ansiedad", "es_inverso": False, "opciones": opciones},
                  {"texto_pregunta": "Me siento tranquilo", "orden": 2,
                   "nombre_dimension": "Ansiedad", "es_inverso": True, "opciones": opciones},
              ]},
        headers=h_psi, timeout=30), 200, "Carga masiva")
    completa = exigir(requests.get(
        f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=h_psi, timeout=30),
        200, "Ver prueba")
    dimension = completa["dimensiones"][0]
    preguntas = {p["orden"]: p for p in dimension["preguntas"]}
    for minimo, maximo, nivel, es_alerta in [(0, 2, "Bajo", False), (3, 8, "Alto", True)]:
        exigir(requests.post(
            f"{API}/educativo/baremos/",
            json={"dimension_id": dimension["id"], "puntaje_minimo": minimo,
                  "puntaje_maximo": maximo, "nivel": nivel, "es_alerta": es_alerta,
                  "interpretacion": f"Interpretación de {nivel}."},
            headers=h_psi, timeout=30), 200, f"Baremo {nivel}")

    campana = exigir(requests.post(
        f"{API}/educativo/campanas/",
        json={"prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña",
              "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Campaña")
    persona = exigir(requests.post(
        f"{API}/admin/personas/",
        json={"institucion_id": inst_id, "nombres": f"{PREFIJO} Alumno",
              "apellidos": "Prueba", "documento_identidad": f"{sello}901", "genero": "Femenino"},
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

    insc = sql_uno("select id, estado from edu_inscripciones where token=:t", t=token)
    inscripcion_id, estado_original = insc[0], insc[1]
    comprobar("Inscripción de prueba montada", estado_original != "Finalizado",
              f"id={inscripcion_id} estado={estado_original!r}")

    # ==================================================================
    print("\nPARTE A · Mecanismo, determinista (dos sesiones ORM reales, sin HTTP)")

    fuente_router = inspect.getsource(edu_router.finalizar_examen_seguro)
    comprobar(
        "El router obtiene la inscripción vía "
        "crud.bloquear_inscripcion_para_finalizar() (si esto cambia por una "
        "consulta inline, revisar que la Parte A de abajo siga probando el "
        "código real y no una copia)",
        "crud.bloquear_inscripcion_para_finalizar(" in fuente_router,
    )

    resultado_perdedor = {}
    barrera = threading.Barrier(2)

    trazas = []
    traza_lock = threading.Lock()

    def trazar(msg):
        with traza_lock:
            trazas.append(f"+{time.perf_counter()-t_inicio:.4f} {msg}")

    t_inicio = time.perf_counter()

    def hilo_ganador(espera_antes_de_confirmar):
        db = SessionLocal()
        try:
            # Fase 1 (sin bloqueo) — igual que el router, propia sesión.
            f1 = db.query(edu_models.Inscripcion).filter(
                edu_models.Inscripcion.id == inscripcion_id).first()
            trazar(f"[GANADOR] Fase1 estado={f1.estado}")
            barrera.wait()
            trazar("[GANADOR] pasó la barrera, entrando a Fase2")
            # Fase 2 (con bloqueo) — la MISMA función que usa el router, no
            # una copia de su consulta.
            fila = edu_crud.bloquear_inscripcion_para_finalizar(db=db, token=token)
            trazar(f"[GANADOR] Fase2 devolvió estado={fila.estado} mismo_obj={fila is f1}")
            time.sleep(espera_antes_de_confirmar)
            # 🆕 Cierre de gap (docs/gaps-pendientes.md) — ya no puede ser un
            # string inventado como "ZZCONC_GANADOR": ck_inscripciones_
            # estado_valido ahora lo rechazaría (CheckViolation). Se usa
            # "Finalizado", un valor real y distinto de estado_original, que
            # sigue sirviendo igual de bien para distinguir "el perdedor vio
            # el valor confirmado por el ganador" de "vio su propia Fase 1".
            fila.estado = "Finalizado"
            db.commit()
            trazar("[GANADOR] COMMIT hecho")
        finally:
            db.close()

    def hilo_perdedor(espera_antes_de_fase2):
        db = SessionLocal()
        try:
            # Fase 1 (sin bloqueo) — carga el objeto en el identity map ANTES
            # de que el ganador confirme; esta es la lectura que quedaba
            # "pegada" antes del arreglo.
            f1 = db.query(edu_models.Inscripcion).filter(
                edu_models.Inscripcion.id == inscripcion_id).first()
            trazar(f"[PERDEDOR] Fase1 estado={f1.estado}")
            barrera.wait()
            trazar("[PERDEDOR] pasó la barrera, durmiendo antes de Fase2")
            time.sleep(espera_antes_de_fase2)  # deja tiempo a que el ganador confirme
            trazar("[PERDEDOR] despertó, entrando a Fase2")
            # Fase 2 (con bloqueo) — debe traer el estado YA confirmado por
            # el ganador, no el que esta sesión vio en su propia Fase 1.
            fila = edu_crud.bloquear_inscripcion_para_finalizar(db=db, token=token)
            trazar(f"[PERDEDOR] Fase2 devolvió estado={fila.estado} mismo_obj={fila is f1}")
            resultado_perdedor["estado"] = fila.estado
        finally:
            db.rollback()
            db.close()

    th_ganador = threading.Thread(target=hilo_ganador, args=(0.3,))
    th_perdedor = threading.Thread(target=hilo_perdedor, args=(0.6,))
    th_ganador.start()
    th_perdedor.start()
    th_ganador.join()
    th_perdedor.join()

    for linea in trazas:
        print("    " + linea)

    comprobar(
        "La Fase 2 del perdedor ve el estado YA confirmado por el ganador "
        "(no el valor obsoleto de su propia Fase 1) — antes del arreglo esto "
        "fallaba de forma determinista, no solo bajo carrera de red",
        resultado_perdedor.get("estado") == "Finalizado",
        f"vio estado={resultado_perdedor.get('estado')!r}",
    )

    # Restaurar antes de la Parte B (que necesita la inscripción sin finalizar).
    db_restaurar = SessionLocal()
    try:
        fila = db_restaurar.query(edu_models.Inscripcion).filter(
            edu_models.Inscripcion.id == inscripcion_id).first()
        fila.estado = estado_original
        db_restaurar.commit()
    finally:
        db_restaurar.close()

    # ==================================================================
    print("\nPARTE B · End-to-end: doble envío HTTP real + efectos secundarios únicos")

    exigir(requests.post(
        f"{API}/educativo/comenzar-test/{token}",
        json={"nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30),
        200, "Comenzar test")

    def opcion(orden, valor):
        return next(o["id"] for o in preguntas[orden]["opciones"] if o["valor_puntuacion"] == valor)

    # 3 + (0+3-0)=3 -> 6 -> tramo "Alto" con alerta, para ejercitar también
    # el envío de la alerta (y no solo la generación del informe).
    exigir(requests.post(
        f"{API}/educativo/examen/{token}/guardar",
        json={"respuestas": [
            {"pregunta_id": preguntas[1]["id"], "opcion_id": opcion(1, 3)},
            {"pregunta_id": preguntas[2]["id"], "opcion_id": opcion(2, 0)},
        ]}, timeout=30), 200, "Guardar respuestas")

    respuestas_concurrentes = []
    barrera2 = threading.Barrier(2)

    def finalizar_en_paralelo():
        barrera2.wait()
        try:
            r = requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60)
            respuestas_concurrentes.append(r.status_code)
        except Exception as exc:  # noqa: BLE001
            respuestas_concurrentes.append(f"error: {exc}")

    hilos = [threading.Thread(target=finalizar_en_paralelo) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    comprobar("Exactamente una petición gana (200) y la otra es rechazada (400)",
              sorted(respuestas_concurrentes) == [200, 400],
              f"códigos: {sorted(respuestas_concurrentes)}")

    n_result = sql_uno(
        "select count(*) from edu_resultados_dimensiones where inscripcion_id=:i",
        i=inscripcion_id)[0]
    n_diag = sql_uno(
        "select count(*) from edu_diagnosticos_alumno where inscripcion_id=:i",
        i=inscripcion_id)[0]
    comprobar("No se duplican los puntajes por dimensión", n_result == 1, f"{n_result} fila(s)")
    comprobar("No se duplican los diagnósticos", n_diag == 1, f"{n_diag} fila(s)")

    estado_final = sql_uno(
        "select estado, resultado_visible_alumno, informe_liberado "
        "from edu_inscripciones where id=:i", i=inscripcion_id)
    comprobar("La inscripción queda Finalizado con el informe retenido (alerta)",
              estado_final[0] == "Finalizado" and estado_final[1] is False and estado_final[2] is False,
              f"estado={estado_final[0]} visible={estado_final[1]} liberado={estado_final[2]}")

    # El informe se genera en BackgroundTasks (después de la respuesta HTTP);
    # se espera activamente en vez de un sleep fijo para no ser flaky.
    limite = time.time() + 20
    n_informes = n_versiones = -1
    while time.time() < limite:
        n_informes = sql_uno(
            "select count(*) from edu_informes where inscripcion_id=:i", i=inscripcion_id)[0]
        if n_informes >= 1:
            n_versiones = sql_uno(
                "select count(*) from edu_informe_versiones v join edu_informes i "
                "on i.id = v.informe_id where i.inscripcion_id=:i", i=inscripcion_id)[0]
            break
        time.sleep(0.5)

    comprobar("Se crea exactamente UN registro de informe (edu_informes), no dos",
              n_informes == 1, f"{n_informes} registro(s)")
    comprobar("Se genera exactamente UNA versión del informe (edu_informe_versiones), "
              "no dos — antes del arreglo el segundo intento chocaba con "
              "uq_edu_informes_inscripcion (UniqueViolation)",
              n_versiones == 1, f"{n_versiones} versión(es)")

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO CONCURRENCIA FINALIZAR: {total - len(fallos)}/{total} comprobaciones superadas")
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
            """DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZCONC%')""",
            """DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZCONC%')""",
            """DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZCONC%')""",
            # edu_informes/edu_informe_versiones caen solas por ON DELETE CASCADE
            # desde edu_inscripciones (ver comentario en modulos/educativo/models.py:Informe).
            """DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                   SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZCONC%')""",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZCONC%'",
            """DELETE FROM edu_baremos WHERE dimension_id IN (
                   SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p
                   ON d.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZCONC%')""",
            """DELETE FROM edu_opciones WHERE pregunta_id IN (
                   SELECT pr.id FROM edu_preguntas pr JOIN edu_pruebas p
                   ON pr.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZCONC%')""",
            """DELETE FROM edu_preguntas WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZCONC%')""",
            """DELETE FROM edu_dimensiones WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZCONC%')""",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZCONC%'",
            """DELETE FROM consentimientos_informados WHERE persona_id IN (
                   SELECT id FROM personas WHERE nombres LIKE 'ZZCONC%')""",
            "DELETE FROM personas WHERE nombres LIKE 'ZZCONC%'",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzconc%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZCONC%'",
        ]:
            cx.execute(text(consulta))
    print("Datos ZZCONC eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
