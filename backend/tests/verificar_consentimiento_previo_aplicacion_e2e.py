"""Verificación previa (Sección 0 de la fase de importación Excel):
¿qué pasa si el consentimiento se revoca DESPUÉS de crear la inscripción
pero ANTES de que el alumno empiece a rendir?

Escenario exacto pedido:
  1. existe consentimiento vigente
  2. se crea una inscripción (matrícula por padrón)
  3. el consentimiento utilizado queda asociado (snapshot) a la inscripción
  4. el consentimiento se revoca ANTES de que el estudiante inicie la prueba
  5. se intenta comenzar la prueba

Regla deseada, y lo que este script demuestra que YA CUMPLE el código
existente (comenzar-test ya revalida vigencia en vivo, independientemente
del snapshot — ver core/deps y router.py validar_y_comenzar_evaluacion):
  - la inscripción conserva su snapshot histórico (no se borra ni se pisa);
  - comenzar la prueba se BLOQUEA (403) porque el consentimiento vigente en
    ESE momento ya no existe;
  - tras una renovación, comenzar la prueba se vuelve a permitir, y el
    snapshot ORIGINAL de la inscripción (el de cuando se matriculó) NO se
    reescribe con el consentimiento renovado — sigue señalando al consentimiento
    que estaba vigente cuando se creó la inscripción, no al más reciente.

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_consentimiento_previo_aplicacion_e2e.py
    python tests/verificar_consentimiento_previo_aplicacion_e2e.py --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

PREFIJO = "ZZPREV"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:400]}")
        sys.exit(1)
    return r.json() if r.text else None


def sql_uno(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchone()


def pedir(metodo, url, contexto="", **kw):
    for _ in range(8):
        r = metodo(url, timeout=30, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}"}, headers=h_super, timeout=30), 201, "Institución")["id"]
    correo = f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} A",
        "rol": "admin", "institucion_id": inst}, headers=h_super), 200, "Registro")
    h = {"Authorization": f"Bearer {exigir(login(correo, 'ClaveDePrueba123'), 200, 'login')['access_token']}"}

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba",
        "documento_identidad": f"{sello}DNI"}, headers=h, timeout=30), 200, "Persona")

    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba"}, headers=h, timeout=30), 200, "Prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "D", "opciones": opciones}]},
        headers=h, timeout=30), 200, "Carga masiva")
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst},
        headers=h, timeout=30), 200, "Campaña")

    # ------------------------------------------------------------
    print("\n1 · [1] Existe consentimiento vigente")
    consent = exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst,
        "otorgado_por_nombre": "Madre", "tipo_otorgante": "apoderado"}, headers=h, timeout=30), 200, "Consentimiento")
    comprobar("[1] El consentimiento queda vigente", consent["estado"] == "vigente")

    print("\n2-3 · [2][3] Se crea la inscripción y el consentimiento usado queda asociado")
    mat = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                               json=[persona["id"]], headers=h, timeout=30), 200, "Matrícula")
    comprobar("[2] La inscripción se crea", len(mat["generados"]) == 1)
    token = mat["generados"][0]["token"]
    insc_id, snap_id = sql_uno(
        "select id, consentimiento_apoderado_id from edu_inscripciones where token=:t", t=token)
    comprobar("[3] El consentimiento vigente queda asociado (snapshot) a la inscripción",
              snap_id == consent["id"])

    print("\n4 · [4] El consentimiento se revoca ANTES de que el alumno inicie la prueba")
    revocado = exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento/revocar",
                                    headers=h, timeout=30), 200, "Revocar")
    comprobar("Queda revocado", revocado["id"] == consent["id"] and revocado["estado"] == "revocado")

    snap_tras_revocar = sql_uno(
        "select consentimiento_apoderado_id from edu_inscripciones where id=:i", i=insc_id)[0]
    comprobar(
        "La revocación NO reescribe el snapshot histórico de la inscripción (sigue señalando al mismo consentimiento)",
        snap_tras_revocar == consent["id"],
    )

    print("\n5 · [5] Se intenta comenzar la prueba")
    r = requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "x", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30)
    comprobar(
        "REGLA DESEADA — una aplicación que TODAVÍA NO HA COMENZADO revalida la vigencia "
        "en vivo y se BLOQUEA (403) si el consentimiento requerido está revocado, "
        "aunque la inscripción ya existiera de antes",
        r.status_code == 403, f"status {r.status_code}: {r.text[:200]}",
    )
    estado_tras_bloqueo = sql_uno("select estado from edu_inscripciones where id=:i", i=insc_id)[0]
    comprobar(
        "El bloqueo NO altera el estado de la inscripción (sigue 'Pendiente', no se corrompe ni se finaliza)",
        estado_tras_bloqueo == "Pendiente", f"estado={estado_tras_bloqueo}",
    )

    print("\n6 · Renovación: comenzar la prueba vuelve a permitirse")
    consent_2 = exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst,
        "otorgado_por_nombre": "Madre (renovado)", "tipo_otorgante": "apoderado"},
        headers=h, timeout=30), 200, "Consentimiento renovado")
    r = requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "x", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30)
    comprobar(
        "REGLA DESEADA — tras renovar, la MISMA inscripción (que seguía 'Pendiente') "
        "ya puede comenzar: la revalidación en vivo vuelve a encontrar un consentimiento vigente",
        r.status_code == 200, f"status {r.status_code}: {r.text[:200]}",
    )
    snap_tras_renovar = sql_uno(
        "select consentimiento_apoderado_id from edu_inscripciones where id=:i", i=insc_id)[0]
    comprobar(
        "El snapshot de la inscripción NO se actualiza al consentimiento renovado — sigue fijo "
        "en el que estaba vigente cuando la inscripción se CREÓ (no cuando se comenzó a rendir); "
        "la revalidación en vivo es lo que decide el acceso, no el snapshot",
        snap_tras_renovar == consent["id"] and snap_tras_renovar != consent_2["id"],
        f"snapshot={snap_tras_renovar}, original={consent['id']}, renovado={consent_2['id']}",
    )
    estado_tras_comenzar = sql_uno("select estado from edu_inscripciones where id=:i", i=insc_id)[0]
    comprobar("La inscripción avanzó a 'En Progreso'", estado_tras_comenzar == "En Progreso")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO — VERIFICACIÓN PREVIA DE CONSENTIMIENTO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZPREV%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZPREV%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZPREV%'"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZPREV%'",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZPREV%'",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzprev%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZPREV%'",
        ]:
            c.execute(text(q))
    print("Datos ZZPREV eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
