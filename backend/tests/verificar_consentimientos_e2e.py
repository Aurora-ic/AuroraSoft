"""Verificación end-to-end — Consentimientos del estudiante y del apoderado.

Cubre los 28 casos de prueba obligatorios de la fase, agrupados:
  1-5   básicos: crear, independencia, vigencia, historial
  6-9   revocación: no borra, bloquea nuevas aplicaciones
  10-12 renovación: el anterior queda histórico, solo el nuevo es vigente
  13-17 seguridad / multi-tenancy (no reintroducir B-8)
  18    tipo_perfil != estudiante no puede recibir MatriculaAcademica
  19-23 relación con la aplicación de pruebas (bloqueo/permiso/histórico)
  24-27 historial psicométrico: contexto histórico inmutable
  28    ficha del estudiante muestra ambos consentimientos

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_consentimientos_e2e.py
    python tests/verificar_consentimientos_e2e.py --limpiar
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

PREFIJO = "ZZCONS"
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


def crear_prueba_simple(headers, sello, sufijo):
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sufijo}-{sello}", "nombre_publico": f"Prueba {sufijo}"},
        headers=headers, timeout=30), 200, f"Prueba {sufijo}")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "D", "opciones": opciones}]},
        headers=headers, timeout=30), 200, f"Carga {sufijo}")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa",
                                  headers=headers, timeout=30), 200, f"Detalle {sufijo}")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Normal"},
        headers=headers, timeout=30), 200, f"Baremo {sufijo}")
    return prueba["id"], pregs


def crear_persona(headers, inst_id, sello, etiqueta, tipo_perfil="estudiante"):
    return exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "tipo_perfil": tipo_perfil},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")


def dar_consentimiento_apoderado(headers, persona_id, nombre="Madre de familia"):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": 0,  # ignorados por el backend (B-8)
        "otorgado_por_nombre": nombre, "tipo_otorgante": "apoderado",
        "otorgante_relacion": "madre", "otorgante_documento": "12345678"},
        headers=headers, timeout=30), 200, "Consentimiento apoderado")


def dar_consentimiento_estudiante(headers, persona_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento/asentimiento", json={
        "referencia_documento": "Asentimiento firmado en clase"},
        headers=headers, timeout=30), 200, "Consentimiento estudiante")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    # rol "admin": la estructura académica (niveles/grados/secciones) exige
    # admin o superadmin, igual que en el Núcleo del Estudiante.
    correo_a = f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro A", json={
        "email": correo_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} A",
        "rol": "admin", "institucion_id": inst_a}, headers=h_super), 200, "Registro A")
    h_a = {"Authorization": f"Bearer {exigir(login(correo_a, 'ClaveDePrueba123'), 200, 'login A')['access_token']}"}

    correo_b = f"{PREFIJO.lower()}.b.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro B", json={
        "email": correo_b, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} B",
        "rol": "admin", "institucion_id": inst_b}, headers=h_super), 200, "Registro B")
    h_b = {"Authorization": f"Bearer {exigir(login(correo_b, 'ClaveDePrueba123'), 200, 'login B')['access_token']}"}

    persona_a = crear_persona(h_a, inst_a, sello, "P1")

    # ==================================================================
    print("\n1-5 · Consentimientos básicos: crear, independencia, vigencia, historial")
    c_apoderado = dar_consentimiento_apoderado(h_a, persona_a["id"])
    comprobar("[1] Se crea el consentimiento de apoderado", c_apoderado["tipo_consentimiento"] == "apoderado")
    comprobar("[1] Queda vigente", c_apoderado["estado"] == "vigente")

    combinado = exigir(requests.get(f"{API}/admin/personas/{persona_a['id']}/consentimientos",
                                    headers=h_a, timeout=30), 200, "Consentimientos combinados")
    comprobar("[4] Apoderado vigente=True, estudiante vigente=False (todavía no se creó)",
              combinado["apoderado"]["tiene_consentimiento_vigente"] is True
              and combinado["asentimiento"]["tiene_consentimiento_vigente"] is False)

    c_estudiante = dar_consentimiento_estudiante(h_a, persona_a["id"])
    comprobar("[2] Se crea el asentimiento del estudiante, independiente", c_estudiante["tipo_consentimiento"] == "asentimiento")
    combinado2 = exigir(requests.get(f"{API}/admin/personas/{persona_a['id']}/consentimientos",
                                     headers=h_a, timeout=30), 200, "Consentimientos combinados 2")
    comprobar(
        "[3] Registrar el consentimiento del estudiante NO creó ni modificó el del apoderado "
        "(sigue vigente, con el MISMO id de antes) — y viceversa, son registros distintos",
        combinado2["apoderado"]["tiene_consentimiento_vigente"] is True
        and combinado2["asentimiento"]["tiene_consentimiento_vigente"] is True
        and combinado2["apoderado"]["historial"][0]["id"] == c_apoderado["id"]
        and combinado2["apoderado"]["historial"][0]["id"] != combinado2["asentimiento"]["historial"][0]["id"],
    )
    comprobar("[5] El historial trae ambos tipos con al menos 1 evento cada uno",
              len(combinado2["apoderado"]["historial"]) >= 1 and len(combinado2["asentimiento"]["historial"]) >= 1)

    r = requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento", json={
        "persona_id": persona_a["id"], "institucion_id": inst_a,
        "otorgado_por_nombre": "Otro", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30)
    comprobar("Un segundo consentimiento de apoderado VIGENTE se rechaza con 409 (uno a la vez por tipo)",
              r.status_code == 409, f"status {r.status_code}")

    # ==================================================================
    print("\n6-9 · Revocación")
    antes_apoderado = sql_uno(
        "select count(*) from consentimientos_informados where persona_id=:p and tipo_consentimiento='apoderado'",
        p=persona_a["id"])[0]
    rev_apoderado = exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/revocar",
                                         headers=h_a, timeout=30), 200, "Revocar apoderado")
    comprobar("[6] El consentimiento de apoderado queda revocado", rev_apoderado["estado"] == "revocado")
    despues_apoderado = sql_uno(
        "select count(*) from consentimientos_informados where persona_id=:p and tipo_consentimiento='apoderado'",
        p=persona_a["id"])[0]
    comprobar("[8] La revocación NO borra el registro histórico (mismo conteo de filas)",
              despues_apoderado == antes_apoderado, f"{antes_apoderado} -> {despues_apoderado}")

    rev_estudiante = exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/asentimiento/revocar",
                                          headers=h_a, timeout=30), 200, "Revocar estudiante")
    comprobar("[7] El consentimiento del estudiante queda revocado, independiente del de apoderado",
              rev_estudiante["estado"] == "revocado" and rev_estudiante["id"] != rev_apoderado["id"])

    # [9] La revocación bloquea NUEVAS aplicaciones que requieran ese consentimiento
    prueba_id, pregs = crear_prueba_simple(h_a, sello, "APL")
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña")
    mat_bloqueada = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                         json=[persona_a["id"]], headers=h_a, timeout=30), 200, "Matrícula bloqueada")
    comprobar("[9][19] Sin consentimiento vigente, la matrícula (aplicación) se rechaza",
              not mat_bloqueada["generados"] and mat_bloqueada["rechazados"],
              str(mat_bloqueada["rechazados"]))

    # ==================================================================
    print("\n10-12 · Renovación")
    c_apoderado_2 = dar_consentimiento_apoderado(h_a, persona_a["id"], nombre="Padre de familia (renovación)")
    comprobar("[10] Se puede crear un nuevo consentimiento tras la revocación", c_apoderado_2["estado"] == "vigente")
    comprobar("Es un registro NUEVO, no el mismo id que el revocado", c_apoderado_2["id"] != rev_apoderado["id"])

    historial_apoderado = exigir(requests.get(f"{API}/admin/personas/{persona_a['id']}/consentimientos",
                                              headers=h_a, timeout=30), 200, "Historial tras renovar")["apoderado"]
    comprobar("[11] El consentimiento anterior sigue en el historial, como revocado",
              any(h["id"] == rev_apoderado["id"] and h["estado"] == "revocado" for h in historial_apoderado["historial"]))
    vigentes_apoderado = [h for h in historial_apoderado["historial"] if h["estado"] == "vigente"]
    comprobar("[12] Solo el consentimiento NUEVO cuenta como vigente (exactamente uno)",
              len(vigentes_apoderado) == 1 and vigentes_apoderado[0]["id"] == c_apoderado_2["id"])

    # ==================================================================
    print("\n13-17 · Seguridad / multi-tenancy (no reintroducir B-8)")
    persona_b = crear_persona(h_b, inst_b, sello, "PB")

    r = requests.post(f"{API}/admin/personas/{persona_b['id']}/consentimiento", json={
        "persona_id": persona_b["id"], "institucion_id": inst_b,
        "otorgado_por_nombre": "Intruso", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30)
    comprobar("[13] A no puede crear consentimiento de apoderado para un alumno de B (403)",
              r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/{persona_b['id']}/consentimiento/asentimiento",
                       json={}, headers=h_a, timeout=30)
    comprobar("[13] Tampoco el del propio estudiante (403)", r.status_code == 403, f"status {r.status_code}")

    # (libera el cupo "un vigente por tipo" de A para poder probar la creación de [14])
    exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/revocar",
                         headers=h_a, timeout=30), 200, "Revocar antes de probar institucion_id ajeno")
    r = requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento", json={
        "persona_id": persona_a["id"], "institucion_id": inst_b,  # 👈 institucion_id ajeno en el body
        "otorgado_por_nombre": "Probando institucion_id ajeno", "tipo_otorgante": "apoderado"},
        headers=h_a, timeout=30)
    comprobar("[14] Un institucion_id ajeno en el BODY se ignora — el consentimiento se crea igual bajo A",
              r.status_code == 200 and sql_uno(
                  "select institucion_id from consentimientos_informados where id=:i", i=r.json()["id"])[0] == inst_a)
    # limpiar: esa creación deja otro vigente de apoderado; se revoca para no interferir más abajo
    requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/revocar", headers=h_a, timeout=30)

    r = requests.get(f"{API}/admin/personas/{persona_b['id']}/consentimiento", headers=h_a, timeout=30)
    comprobar("[15] A no puede CONSULTAR el consentimiento (apoderado) de un alumno de B (403)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/admin/personas/{persona_b['id']}/consentimientos", headers=h_a, timeout=30)
    comprobar("[15] Tampoco la vista combinada (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/{persona_b['id']}/consentimiento/revocar", headers=h_a, timeout=30)
    comprobar("[16] A no puede REVOCAR el consentimiento de un alumno de B (403)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_b['id']}/consentimiento/asentimiento/revocar", headers=h_a, timeout=30)
    comprobar("[16] Tampoco el del estudiante (403)", r.status_code == 403, f"status {r.status_code}")

    # [17] Un consentimiento de A no habilita una matrícula en B — mismo patrón que B-8 (Fase 2)
    usuario_a_id = sql_uno("select id from auth_usuarios where email=:e", e=correo_a)[0]
    with MOTOR.begin() as c:
        c.execute(text("""insert into consentimientos_informados
                          (persona_id, institucion_id, tipo_consentimiento, estado,
                           otorgado_por_nombre, tipo_otorgante, registrado_por_usuario_id, revocado)
                          values (:p, :i, 'apoderado', 'vigente', 'Consentimiento de A', 'apoderado', :u, false)"""),
                  {"p": persona_b["id"], "i": inst_a, "u": usuario_a_id})
    prueba_b_id, pregs_b = crear_prueba_simple(h_b, sello, "CRUCE")
    campana_b = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_b_id, "nombre_grupo": f"{PREFIJO} Cruce {sello}", "institucion_id": inst_b},
        headers=h_b, timeout=30), 200, "Campaña B")
    mat_cruce = exigir(requests.post(f"{API}/educativo/campanas/{campana_b['id']}/matricular-roster",
                                     json=[persona_b["id"]], headers=h_b, timeout=30), 200, "Matrícula cruce")
    comprobar("[17] Un consentimiento del colegio A NO habilita una matrícula en el colegio B",
              not mat_cruce["generados"] and mat_cruce["rechazados"], str(mat_cruce["rechazados"]))

    # ==================================================================
    print("\n18 · Integridad del estudiante — tipo_perfil")
    persona_no_estudiante = crear_persona(h_a, inst_a, sello, "PAC", tipo_perfil="paciente")
    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": f"{PREFIJO}-Nivel-{sello}"}, headers=h_a, timeout=30), 200, "Nivel")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "1°"}, headers=h_a, timeout=30), 200, "Grado")
    seccion = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "anio_escolar": 2026}, headers=h_a, timeout=30), 200, "Sección")
    r = requests.post(f"{API}/admin/personas/{persona_no_estudiante['id']}/matricula",
                       json={"seccion_id": seccion["id"]}, headers=h_a, timeout=30)
    comprobar("[18] Matricular en una sección a alguien con tipo_perfil='paciente' se rechaza (400)",
              r.status_code == 400, f"status {r.status_code}: {r.text[:200]}")

    # ==================================================================
    print("\n19-23 · Relación con la aplicación de pruebas")
    dar_consentimiento_apoderado(h_a, persona_a["id"], nombre="Madre (para aplicar)")
    exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/matricula",
                         json={"seccion_id": seccion["id"]}, headers=h_a, timeout=30), 200, "Matricular en sección")

    mat_ok = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                  json=[persona_a["id"]], headers=h_a, timeout=30), 200, "Matrícula permitida")
    comprobar("[20] Con consentimiento vigente, la aplicación SÍ se permite", len(mat_ok["generados"]) == 1)
    token_1 = mat_ok["generados"][0]["token"]
    insc_1_id, consentimiento_snap_1 = sql_uno(
        "select id, consentimiento_apoderado_id from edu_inscripciones where token=:t", t=token_1)
    consentimiento_vigente_id = sql_uno(
        "select id from consentimientos_informados where persona_id=:p and tipo_consentimiento='apoderado' and estado='vigente'",
        p=persona_a["id"])[0]
    comprobar("[20][24] La inscripción guarda el snapshot del consentimiento que estaba vigente al aplicar",
              consentimiento_snap_1 == consentimiento_vigente_id)

    def opcion_de(pregs_dict, valor):
        return next(o["id"] for o in pregs_dict[1]["opciones"] if o["valor_puntuacion"] == valor)

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token_1}", json={
        "nombre_completo": "x", "edad": 1, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar aplicación 1")
    exigir(requests.post(f"{API}/educativo/examen/{token_1}/guardar", json={"respuestas": [
        {"pregunta_id": pregs[1]["id"], "opcion_id": opcion_de(pregs, 1)}]}, timeout=30), 200, "Guardar 1")
    exigir(requests.post(f"{API}/educativo/examen/{token_1}/finalizar", timeout=60), 200, "[22] Finalizar aplicación 1")

    seccion_snap_antes, grado_seccion_antes = sql_uno(
        "select seccion_id, grado_seccion_historico from edu_inscripciones where id=:i", i=insc_1_id)

    # [21] Revocar y volver a intentar matricular: la NUEVA aplicación se bloquea
    exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/revocar",
                         headers=h_a, timeout=30), 200, "Revocar tras aplicación 1")
    mat_bloqueada_2 = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                           json=[persona_a["id"]], headers=h_a, timeout=30), 200, "Nueva matrícula bloqueada")
    comprobar("[21] Revocado ANTES de una nueva aplicación: esa nueva aplicación se bloquea",
              not mat_bloqueada_2["generados"], str(mat_bloqueada_2["rechazados"]))

    # [22][24][25][26] La aplicación #1, ya finalizada, permanece intacta pese a la revocación posterior
    insc_1_tras_revocar = sql_uno(
        "select persona_id, seccion_id, grado_seccion_historico, consentimiento_apoderado_id, estado "
        "from edu_inscripciones where id=:i", i=insc_1_id)
    comprobar(
        "[22] La aplicación histórica sigue 'Finalizado' tras la revocación posterior (no se invalida)",
        insc_1_tras_revocar[4] == "Finalizado",
    )
    comprobar(
        "[24] Sigue apuntando al MISMO consentimiento histórico (aunque ahora esté revocado)",
        insc_1_tras_revocar[3] == consentimiento_vigente_id,
    )
    comprobar("[25] Conserva su sección/grado histórico, sin cambios", (insc_1_tras_revocar[1], insc_1_tras_revocar[2]) == (seccion_snap_antes, grado_seccion_antes))
    comprobar("[26] Sigue asociada al mismo estudiante", insc_1_tras_revocar[0] == persona_a["id"])

    diagnosticos_1 = sql_uno("select count(*) from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_1_id)[0]
    comprobar("[27] El resultado/diagnóstico de la aplicación #1 sigue existiendo, ajeno al consentimiento actual",
              diagnosticos_1 >= 1)
    r = requests.get(f"{API}/educativo/inscripciones/{insc_1_id}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[27] El informe histórico sigue siendo generable pese a que el consentimiento actual esté revocado",
              r.status_code == 200 and r.content[:4] == b"%PDF", f"status {r.status_code}")

    # [23] Renovación posterior: la NUEVA aplicación usa el nuevo consentimiento.
    # Se usa una campaña de una prueba DISTINTA a propósito: por un lado,
    # C-15 (Fase 2) ya impide dos cupos del mismo alumno en la MISMA
    # campaña; por otro, `puede_aplicar_prueba` impide reaplicar la MISMA
    # prueba antes de `dias_minimos_entre_aplicaciones`. Ninguna de las dos
    # reglas tiene que ver con el consentimiento — no queremos que esos
    # candados, correctos, se confundan con el que esta prueba demuestra.
    c_apoderado_3 = dar_consentimiento_apoderado(h_a, persona_a["id"], nombre="Madre (segunda renovación)")
    prueba_id_2, pregs_2 = crear_prueba_simple(h_a, sello, "APL2")
    campana2 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id_2, "nombre_grupo": f"{PREFIJO} Campaña2 {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña 2 (para la renovación)")
    mat_2 = exigir(requests.post(f"{API}/educativo/campanas/{campana2['id']}/matricular-roster",
                                 json=[persona_a["id"]], headers=h_a, timeout=30), 200, "Matrícula tras renovar")
    comprobar("[23] Tras renovar, la matrícula ahora sí se permite", len(mat_2["generados"]) == 1)
    token_2 = mat_2["generados"][0]["token"]
    consentimiento_snap_2 = sql_uno(
        "select consentimiento_apoderado_id from edu_inscripciones where token=:t", t=token_2)[0]
    comprobar("[23] La aplicación NUEVA usa el consentimiento NUEVO, no el revocado",
              consentimiento_snap_2 == c_apoderado_3["id"] and consentimiento_snap_2 != consentimiento_vigente_id)

    # ==================================================================
    print("\n28 · Ficha del estudiante")
    ficha = exigir(requests.get(f"{API}/admin/personas/{persona_a['id']}/ficha-completa",
                                headers=h_a, timeout=30), 200, "Ficha completa")
    comprobar("[28] La ficha trae la sección 'consentimientos' con apoderado y asentimiento",
              "apoderado" in ficha["consentimientos"] and "asentimiento" in ficha["consentimientos"])
    comprobar("[28] Refleja el estado ACTUAL: apoderado vigente (tras la renovación), estudiante revocado",
              ficha["consentimientos"]["apoderado"]["tiene_consentimiento_vigente"] is True
              and ficha["consentimientos"]["asentimiento"]["tiene_consentimiento_vigente"] is False)
    comprobar("[28] El historial de apoderado en la ficha tiene varios eventos (revocaciones + renovaciones)",
              len(ficha["consentimientos"]["apoderado"]["historial"]) >= 3)
    comprobar("[28] La ficha sigue trayendo las 2 aplicaciones en su historial de evaluaciones",
              len(ficha["historial_evaluaciones"]) == 2)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E CONSENTIMIENTOS: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZCONS%'"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE nivel_educativo_id IN ({niveles})"
    secciones = f"SELECT id FROM secciones WHERE grado_id IN ({grados})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZCONS%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZCONS%'"
    with motor.begin() as c:
        for q in [
            f"UPDATE edu_inscripciones SET consentimiento_apoderado_id=NULL, consentimiento_asentimiento_id=NULL "
            f"WHERE evaluacion_id IN ({campanas})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZCONS%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZCONS%'",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE id IN ({secciones})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
            "DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE 'zzcons%')",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzcons%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZCONS%'",
        ]:
            c.execute(text(q))
    print("Datos ZZCONS eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
