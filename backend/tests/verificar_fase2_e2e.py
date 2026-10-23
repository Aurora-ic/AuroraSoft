"""Verificación end-to-end de la Fase 2 — integridad, tenencia y privacidad.

Ejecuta los 15 intentos de manipulación obligatorios contra el servidor real:

  B-7  · opción de otra pregunta / de otra prueba / de otra institución
  B-8  · consentimiento cruzado e inscripción con consentimiento ajeno
  B-11 · captura de fecha e IP, y revocación conservando historial
  B-12 · anonimización sin rol y entre instituciones
  C-7  · documento repetido en la misma institución y en otra distinta
  C-8  · ficha que excluye eliminados y anonimizados
  C-15 · doble inscripción en una campaña

Uso:
    uvicorn main:app --port 8010          (con SMTP deshabilitado)
    python tests/verificar_fase2_e2e.py
    python tests/verificar_fase2_e2e.py --limpiar
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

PREFIJO = "ZZF2"
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
    for _ in range(6):
        r = metodo(url, timeout=30, **kwargs)
        if r.status_code != 429:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def sql_uno(consulta, **params):
    with MOTOR.connect() as cx:
        fila = cx.execute(text(consulta), params).fetchone()
    return fila


def ejecutar(consulta, **params):
    with MOTOR.begin() as cx:
        cx.execute(text(consulta), params)


# ======================================================================
def montar_colegio(h_super, letra, sello):
    inst = exigir(requests.post(
        f"{API}/instituciones/",
        json={"nombre": f"{PREFIJO} Colegio {letra} {sello}", "tipo": "Colegio"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")

    usuarios = {}
    for rol in ("psicologo", "admin"):
        correo = f"{PREFIJO.lower()}.{rol}.{letra.lower()}.{sello}@ejemplo.com"
        u = exigir(pedir_con_reintento(
            requests.post, f"{API}/auth/registro", f"registro {rol}{letra}",
            json={"email": correo, "password": "ClaveDePrueba123",
                  "nombre_completo": f"{PREFIJO} {rol} {letra}", "rol": rol,
                  "institucion_id": inst["id"]},
            headers=h_super), 200, f"Usuario {rol} {letra}")
        tok = exigir(pedir_con_reintento(
            requests.post, f"{API}/auth/login", f"login {rol}{letra}",
            data={"username": correo, "password": "ClaveDePrueba123"}),
            200, f"Login {rol} {letra}")["access_token"]
        usuarios[rol] = {"id": u["id"], "email": correo,
                         "headers": {"Authorization": f"Bearer {tok}"}}
    return inst["id"], usuarios


def crear_prueba(headers, sello, sufijo):
    """Prueba de 1 ítem con opciones 0..3. Devuelve (prueba_id, pregunta, dimension_id)."""
    opciones = [{"texto_opcion": t, "valor_puntuacion": v}
                for t, v in [("Nunca", 0), ("A veces", 1), ("A menudo", 2), ("Siempre", 3)]]
    prueba = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-{sufijo}-{sello}",
              "nombre_publico": f"Prueba {sufijo}",
              "escala_minima": 0, "escala_maxima": 3},
        headers=headers, timeout=30), 200, f"Prueba {sufijo}")
    exigir(requests.post(
        f"{API}/educativo/pruebas/carga-masiva/",
        json={"prueba_id": prueba["id"],
              "dimensiones": [{"nombre": "Ansiedad", "descripcion": "d"}],
              "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1,
                             "nombre_dimension": "Ansiedad", "es_inverso": False,
                             "opciones": opciones},
                            {"texto_pregunta": "Ítem 2", "orden": 2,
                             "nombre_dimension": "Ansiedad", "es_inverso": False,
                             "opciones": opciones}]},
        headers=headers, timeout=30), 200, f"Carga {sufijo}")
    completa = exigir(requests.get(
        f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=headers, timeout=30),
        200, f"Detalle {sufijo}")
    dim = completa["dimensiones"][0]
    exigir(requests.post(
        f"{API}/educativo/baremos/",
        json={"dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 20,
              "nivel": "Normal", "es_alerta": False},
        headers=headers, timeout=30), 200, "Baremo")
    return prueba["id"], {p["orden"]: p for p in dim["preguntas"]}, dim["id"]


def crear_persona(headers, inst_id, sello, etiqueta, dni):
    return exigir(requests.post(
        f"{API}/admin/personas/",
        json={"institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}",
              "apellidos": "Alumno", "documento_identidad": dni, "genero": "Femenino"},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")


def dar_consentimiento(headers, persona_id, inst_id):
    return exigir(requests.post(
        f"{API}/admin/personas/{persona_id}/consentimiento",
        json={"persona_id": persona_id, "institucion_id": inst_id,
              "otorgado_por_nombre": "Madre de familia", "tipo_otorgante": "apoderado",
              "referencia_documento": "Ficha 2026"},
        headers=headers, timeout=30), 200, "Consentimiento")


def crear_campana_y_matricular(headers, inst_id, prueba_id, persona_id, etiqueta):
    campana = exigir(requests.post(
        f"{API}/educativo/campanas/",
        json={"prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta}",
              "institucion_id": inst_id}, headers=headers, timeout=30),
        200, f"Campaña {etiqueta}")
    mat = exigir(requests.post(
        f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
        json=[persona_id], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    return campana["id"], mat


# ======================================================================
def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje de dos colegios independientes")
    tok_super = exigir(pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login superadmin",
        data={"username": os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
              "password": os.getenv("SUPERADMIN_PASSWORD")}),
        200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a, users_a = montar_colegio(h_super, "A", sello)
    inst_b, users_b = montar_colegio(h_super, "B", sello)
    h_a, h_b = users_a["psicologo"]["headers"], users_b["psicologo"]["headers"]
    h_admin_a = users_a["admin"]["headers"]
    comprobar("Colegios A y B montados", True, f"A={inst_a} B={inst_b}")

    prueba_a, preg_a, _ = crear_prueba(h_a, sello, "A")
    prueba_b, preg_b, _ = crear_prueba(h_b, sello, "B")

    persona_a = crear_persona(h_a, inst_a, sello, "Ana", f"{sello}01")
    persona_b = crear_persona(h_b, inst_b, sello, "Beto", f"{sello}02")
    dar_consentimiento(h_a, persona_a["id"], inst_a)
    dar_consentimiento(h_b, persona_b["id"], inst_b)

    camp_a, mat_a = crear_campana_y_matricular(h_a, inst_a, prueba_a, persona_a["id"], "A")
    token_a = mat_a["generados"][0]["token"]

    exigir(requests.post(
        f"{API}/educativo/comenzar-test/{token_a}",
        json={"nombre_completo": "Ana", "edad": 15, "sexo": "Femenino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30),
        200, "Comenzar test A")

    # ==================================================================
    print("\nB-7 · Integridad de respuestas del examen")

    def opcion_de(preguntas, orden, valor):
        return next(o["id"] for o in preguntas[orden]["opciones"] if o["valor_puntuacion"] == valor)

    def guardar(token, pregunta_id, opcion_id):
        return requests.post(f"{API}/educativo/examen/{token}/guardar",
                             json={"respuestas": [{"pregunta_id": pregunta_id,
                                                   "opcion_id": opcion_id}]}, timeout=30)

    # Línea base válida
    r = guardar(token_a, preg_a[1]["id"], opcion_de(preg_a, 1, 1))
    comprobar("Una respuesta legítima se guarda (200)", r.status_code == 200,
              f"status {r.status_code}")
    insc_a = sql_uno("select id from edu_inscripciones where token=:t", t=token_a)[0]
    puntaje_base = sql_uno(
        "select puntaje_obtenido from edu_respuestas_alumno where inscripcion_id=:i", i=insc_a)[0]
    comprobar("El puntaje guardado es el de la BD", puntaje_base == 1, f"valor {puntaje_base}")

    # 1. Opción de OTRA PREGUNTA de la misma prueba
    r = guardar(token_a, preg_a[1]["id"], opcion_de(preg_a, 2, 3))
    comprobar("Opción de otra pregunta: rechazada (400)", r.status_code == 400,
              f"status {r.status_code}")

    # 2. Opción de OTRA PRUEBA (de la misma institución no, de la B: otra institución)
    r = guardar(token_a, preg_a[1]["id"], opcion_de(preg_b, 1, 3))
    comprobar("Opción de otra prueba/institución: rechazada (400)", r.status_code == 400,
              f"status {r.status_code}")

    # 3. Pregunta de otra prueba con su propia opción (par coherente pero ajeno)
    r = guardar(token_a, preg_b[1]["id"], opcion_de(preg_b, 1, 3))
    comprobar("Pregunta+opción de otra prueba: rechazada (400)", r.status_code == 400,
              f"status {r.status_code}")

    # 4. IDs inexistentes
    r = guardar(token_a, 9999999, 9999999)
    comprobar("IDs inexistentes: rechazados (400)", r.status_code == 400,
              f"status {r.status_code}")

    # 5. Atomicidad: lote con una válida y una manipulada
    r = requests.post(f"{API}/educativo/examen/{token_a}/guardar", json={"respuestas": [
        {"pregunta_id": preg_a[2]["id"], "opcion_id": opcion_de(preg_a, 2, 3)},   # válida
        {"pregunta_id": preg_a[1]["id"], "opcion_id": opcion_de(preg_b, 1, 3)},   # ajena
    ]}, timeout=30)
    comprobar("Lote mixto: rechazado entero (400)", r.status_code == 400,
              f"status {r.status_code}")
    filas = sql_uno("select count(*), max(puntaje_obtenido) from edu_respuestas_alumno "
                    "where inscripcion_id=:i", i=insc_a)
    comprobar("No se aplicó la parte válida del lote rechazado", filas[0] == 1,
              f"{filas[0]} respuesta(s)")
    comprobar("La respuesta anterior NO se borró", filas[1] == puntaje_base,
              f"puntaje conservado {filas[1]}")

    # 6. Dos respuestas para la misma pregunta
    r = requests.post(f"{API}/educativo/examen/{token_a}/guardar", json={"respuestas": [
        {"pregunta_id": preg_a[1]["id"], "opcion_id": opcion_de(preg_a, 1, 0)},
        {"pregunta_id": preg_a[1]["id"], "opcion_id": opcion_de(preg_a, 1, 3)},
    ]}, timeout=30)
    comprobar("Respuesta duplicada en el mismo lote: rechazada (400)",
              r.status_code == 400, f"status {r.status_code}")

    # ==================================================================
    print("\nB-8 · Consentimiento cruzado entre instituciones")

    # El psicólogo de A apunta la RUTA a su alumna y el BODY al alumno de B
    r = requests.post(
        f"{API}/admin/personas/{persona_a['id']}/consentimiento",
        json={"persona_id": persona_b["id"],      # 👈 alumno de OTRO colegio
              "institucion_id": inst_b,           # 👈 institución ajena
              "otorgado_por_nombre": "Intruso", "tipo_otorgante": "apoderado"},
        headers=h_a, timeout=30)
    # Se rechaza por duplicado (Ana ya tiene uno) o se acepta pero atribuido a Ana;
    # lo inadmisible sería que se creara para Beto/colegio B.
    creado_para_b = sql_uno(
        "select count(*) from consentimientos_informados "
        "where persona_id=:p and otorgado_por_nombre='Intruso'", p=persona_b["id"])[0]
    comprobar("El body NO puede crear consentimiento para otro colegio",
              creado_para_b == 0, f"status {r.status_code}, creados para B: {creado_para_b}")

    # Lo mismo sobre una persona sin consentimiento previo
    persona_a2 = crear_persona(h_a, inst_a, sello, "Carla", f"{sello}03")
    r = requests.post(
        f"{API}/admin/personas/{persona_a2['id']}/consentimiento",
        json={"persona_id": persona_b["id"], "institucion_id": inst_b,
              "otorgado_por_nombre": "Intruso2", "tipo_otorgante": "apoderado"},
        headers=h_a, timeout=30)
    destino = sql_uno(
        "select persona_id, institucion_id from consentimientos_informados "
        "where otorgado_por_nombre='Intruso2'")
    comprobar("El consentimiento se atribuye a la persona de la RUTA",
              destino is not None and destino[0] == persona_a2["id"] and destino[1] == inst_a,
              f"quedó en persona={destino[0] if destino else None} inst={destino[1] if destino else None}")

    # Escritura directa cruzada: A intenta sobre una persona de B
    r = requests.post(
        f"{API}/admin/personas/{persona_b['id']}/consentimiento",
        json={"persona_id": persona_b["id"], "institucion_id": inst_b,
              "otorgado_por_nombre": "X", "tipo_otorgante": "apoderado"},
        headers=h_a, timeout=30)
    comprobar("A no puede tocar el consentimiento de un alumno de B (403)",
              r.status_code == 403, f"status {r.status_code}")

    # Un consentimiento de A no habilita una inscripción de B
    persona_compartida = crear_persona(h_b, inst_b, sello, "Dual", f"{sello}04")
    ejecutar("""insert into consentimientos_informados
                (persona_id, institucion_id, otorgado_por_nombre, tipo_otorgante,
                 registrado_por_usuario_id, revocado)
                values (:p, :i, 'Consentimiento del colegio A', 'apoderado', :u, false)""",
             p=persona_compartida["id"], i=inst_a, u=users_a["psicologo"]["id"])
    camp_b, mat_b = crear_campana_y_matricular(
        h_b, inst_b, prueba_b, persona_compartida["id"], "B-cruce")
    comprobar("Un consentimiento del colegio A no habilita una matrícula en B",
              not mat_b["generados"] and mat_b["rechazados"],
              str(mat_b["rechazados"])[:110])

    # ==================================================================
    print("\nB-11 · Auditoría del consentimiento")

    audit = sql_uno("""select fecha_otorgamiento, ip_registro, registrado_por_usuario_id,
                              otorgado_por_nombre, tipo_otorgante, revocado
                       from consentimientos_informados where persona_id=:p""",
                    p=persona_a["id"])
    comprobar("Se registra la fecha de otorgamiento", audit[0] is not None, str(audit[0]))
    comprobar("Se registra la IP de origen", audit[1] is not None, f"ip={audit[1]}")
    comprobar("Se registra quién lo tramitó", audit[2] == users_a["psicologo"]["id"])
    comprobar("Se registra quién otorgó y en qué calidad",
              audit[3] == "Madre de familia" and audit[4] == "apoderado")

    insc_audit = sql_uno("""select acepto_asentimiento, fecha_asentimiento, ip_asentimiento
                            from edu_inscripciones where id=:i""", i=insc_a)
    comprobar("La aceptación del alumno queda fechada",
              insc_audit[0] is True and insc_audit[1] is not None, f"fecha={insc_audit[1]}")
    comprobar("La aceptación del alumno registra su IP",
              insc_audit[2] is not None, f"ip={insc_audit[2]}")

    # Revocación conservando historial
    antes = sql_uno("select count(*) from consentimientos_informados where persona_id=:p",
                    p=persona_a["id"])[0]
    exigir(requests.post(f"{API}/admin/personas/{persona_a['id']}/consentimiento/revocar",
                         headers=h_a, timeout=30), 200, "Revocar")
    despues = sql_uno("""select count(*), sum(case when revocado then 1 else 0 end),
                                max(revocado_por_usuario_id), max(ip_revocacion),
                                max(fecha_revocacion)
                         from consentimientos_informados where persona_id=:p""",
                      p=persona_a["id"])
    comprobar("La revocación NO borra el registro histórico",
              despues[0] == antes, f"{antes} -> {despues[0]} filas")
    comprobar("Queda marcado como revocado", despues[1] == antes)
    comprobar("Se registra quién revocó", despues[2] == users_a["psicologo"]["id"])
    comprobar("Se registra la IP y la fecha de revocación",
              despues[3] is not None and despues[4] is not None,
              f"ip={despues[3]}")

    estado = exigir(requests.get(f"{API}/admin/personas/{persona_a['id']}/consentimiento",
                                 headers=h_a, timeout=30), 200, "Estado consentimiento")
    comprobar("El endpoint expone el historial completo",
              estado["tiene_consentimiento_vigente"] is False and len(estado["historial"]) >= 1,
              f"{len(estado['historial'])} evento(s)")

    # ==================================================================
    print("\nB-12 · Anonimización ARCO")

    persona_arco = crear_persona(h_a, inst_a, sello, "Elena", f"{sello}05")

    r = requests.post(f"{API}/admin/personas/{persona_arco['id']}/anonimizar-arco",
                      headers=h_a, timeout=30)
    comprobar("Un psicólogo NO puede anonimizar (403)", r.status_code == 403,
              f"status {r.status_code}")
    sigue = sql_uno("select nombres from personas where id=:i", i=persona_arco["id"])[0]
    comprobar("Los datos siguen intactos tras el intento", sigue.startswith(PREFIJO), sigue)

    r = requests.post(f"{API}/admin/personas/{persona_b['id']}/anonimizar-arco",
                      headers=h_admin_a, timeout=30)
    comprobar("Un admin de A NO puede anonimizar a un alumno de B (403)",
              r.status_code == 403, f"status {r.status_code}")

    r = requests.post(
        f"{API}/admin/personas/{persona_arco['id']}/anonimizar-arco"
        f"?referencia_solicitud=Solicitud-ARCO-{sello}",
        headers=h_admin_a, timeout=30)
    comprobar("El admin de la institución SÍ puede anonimizar (200)",
              r.status_code == 200, f"status {r.status_code}")
    anon = sql_uno("select nombres, apellidos, documento_identidad, email, activo "
                   "from personas where id=:i", i=persona_arco["id"])
    comprobar("La PII queda borrada pero la fila permanece (no es borrado físico)",
              anon is not None and anon[0] == "ANONIMO" and anon[2] is None
              and anon[3] is None and anon[4] is False,
              f"{anon[0]} {anon[1]}")

    bitacora = sql_uno("""select accion, persona_id, institucion_id, ejecutado_por_usuario_id,
                                 rol_ejecutor, ip_solicitante, detalle, fecha
                          from auditoria_arco where persona_id=:p""", p=persona_arco["id"])
    comprobar("La acción queda en la bitácora ARCO", bitacora is not None)
    comprobar("La bitácora identifica al responsable",
              bitacora[3] == users_a["admin"]["id"] and bitacora[4] == "admin")
    comprobar("La bitácora registra institución, IP y fecha",
              bitacora[2] == inst_a and bitacora[5] is not None and bitacora[7] is not None,
              f"inst={bitacora[2]} ip={bitacora[5]}")
    comprobar("La bitácora conserva la referencia de la solicitud",
              f"Solicitud-ARCO-{sello}" in (bitacora[6] or ""), (bitacora[6] or "")[:80])

    # ==================================================================
    print("\nC-7 · Unicidad del documento por institución")

    dni_compartido = f"{sello}99"
    r = requests.post(f"{API}/admin/personas/",
                      json={"institucion_id": inst_a, "nombres": f"{PREFIJO} Uno",
                            "apellidos": "Doc", "documento_identidad": dni_compartido},
                      headers=h_a, timeout=30)
    comprobar("Primer alumno con ese documento en A (200)", r.status_code == 200,
              f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/",
                      json={"institucion_id": inst_a, "nombres": f"{PREFIJO} Dos",
                            "apellidos": "Doc", "documento_identidad": dni_compartido},
                      headers=h_a, timeout=30)
    comprobar("Documento repetido DENTRO de la misma institución: rechazado (409)",
              r.status_code == 409, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/",
                      json={"institucion_id": inst_b, "nombres": f"{PREFIJO} Tres",
                            "apellidos": "Doc", "documento_identidad": dni_compartido},
                      headers=h_b, timeout=30)
    comprobar("MISMO documento en OTRA institución: permitido (200)",
              r.status_code == 200, f"status {r.status_code}")
    cuantos = sql_uno("select count(*) from personas where documento_identidad=:d",
                      d=dni_compartido)[0]
    comprobar("Conviven dos alumnos con el mismo DNI en colegios distintos",
              cuantos == 2, f"{cuantos} registros")

    # ==================================================================
    print("\nC-15 · Doble inscripción en una campaña")

    # Alumno propio y con consentimiento VIGENTE: así el único motivo posible
    # de rechazo es el duplicado, y no un candado anterior de la cadena.
    persona_dup = crear_persona(h_a, inst_a, sello, "Hugo", f"{sello}08")
    dar_consentimiento(h_a, persona_dup["id"], inst_a)
    camp_dup, mat_dup = crear_campana_y_matricular(
        h_a, inst_a, prueba_a, persona_dup["id"], "Dup")
    comprobar("Primera matrícula del alumno: aceptada",
              len(mat_dup["generados"]) == 1, str(mat_dup["rechazados"])[:80])

    r = requests.post(f"{API}/educativo/campanas/{camp_dup}/matricular-roster",
                      json=[persona_dup["id"]], headers=h_a, timeout=30)
    cuerpo = r.json()
    motivo = (cuerpo["rechazados"] or [{}])[0].get("motivo", "")
    comprobar("Rematricular al mismo alumno: rechazado por DUPLICADO",
              not cuerpo["generados"] and "ya está matriculado" in motivo,
              motivo[:110])
    n_insc = sql_uno("select count(*) from edu_inscripciones where evaluacion_id=:e "
                     "and persona_id=:p", e=camp_dup, p=persona_dup["id"])[0]
    comprobar("Sigue habiendo una sola inscripción", n_insc == 1, f"{n_insc} fila(s)")

    conflicto = None
    try:
        ejecutar("""insert into edu_inscripciones (evaluacion_id, persona_id, token, estado)
                    values (:e, :p, :t, 'Pendiente')""",
                 e=camp_dup, p=persona_dup["id"], t=f"forzado-{sello}")
    except Exception as exc:
        conflicto = type(exc).__name__
    comprobar("La BD rechaza el duplicado aunque se intente por SQL directo",
              conflicto is not None, conflicto or "el INSERT pasó")

    # ==================================================================
    print("\nC-8 · Registros eliminados y anonimizados")

    persona_baja = crear_persona(h_a, inst_a, sello, "Fabio", f"{sello}06")
    dar_consentimiento(h_a, persona_baja["id"], inst_a)
    camp_baja, mat_baja = crear_campana_y_matricular(
        h_a, inst_a, prueba_a, persona_baja["id"], "Baja")
    token_baja = mat_baja["generados"][0]["token"]
    insc_baja = mat_baja["generados"][0]["id"]

    ficha = exigir(requests.get(f"{API}/admin/personas/{persona_baja['id']}/ficha-completa",
                                headers=h_a, timeout=30), 200, "Ficha antes")
    comprobar("Antes de la baja, la evaluación aparece en la ficha",
              len(ficha["historial_evaluaciones"]) == 1)

    exigir(requests.delete(f"{API}/educativo/alumnos/{insc_baja}/soft-delete",
                           headers=h_a, timeout=30), 200, "Soft delete")
    ficha = exigir(requests.get(f"{API}/admin/personas/{persona_baja['id']}/ficha-completa",
                                headers=h_a, timeout=30), 200, "Ficha después")
    comprobar("Tras el borrado lógico, la ficha ya NO la muestra",
              len(ficha["historial_evaluaciones"]) == 0,
              f"{len(ficha['historial_evaluaciones'])} evaluación(es)")

    r = requests.get(f"{API}/educativo/examen/{token_baja}/preguntas", timeout=30)
    comprobar("El link mágico de una inscripción eliminada deja de servir (410)",
              r.status_code == 410, f"status {r.status_code}")

    auditoria_baja = sql_uno("select accion, ejecutado_por_usuario_id from auditoria_arco "
                             "where inscripcion_id=:i", i=insc_baja)
    comprobar("El borrado lógico también queda auditado",
              auditoria_baja is not None and auditoria_baja[0] == "soft_delete_inscripcion")

    # Anonimización de inscripción
    persona_anon = crear_persona(h_a, inst_a, sello, "Gina", f"{sello}07")
    dar_consentimiento(h_a, persona_anon["id"], inst_a)
    camp_anon, mat_anon = crear_campana_y_matricular(
        h_a, inst_a, prueba_a, persona_anon["id"], "Anon")
    insc_anon = mat_anon["generados"][0]["id"]

    exigir(requests.post(f"{API}/educativo/alumnos/{insc_anon}/anonimizar-arco",
                         headers=h_admin_a, timeout=30), 200, "Anonimizar inscripción")
    ficha = exigir(requests.get(f"{API}/admin/personas/{persona_anon['id']}/ficha-completa",
                                headers=h_a, timeout=30), 200, "Ficha anonimizada")
    comprobar("Una inscripción anonimizada no reaparece en la ficha",
              len(ficha["historial_evaluaciones"]) == 0,
              f"{len(ficha['historial_evaluaciones'])} evaluación(es)")

    padron = exigir(requests.get(f"{API}/admin/personas/{inst_a}", headers=h_a, timeout=30),
                    200, "Padrón")
    ids_padron = {p["id"] for p in padron}
    comprobar("El padrón no lista a la persona anonimizada",
              persona_arco["id"] not in ids_padron)
    comprobar("El padrón sí lista a las personas activas",
              persona_a["id"] in ids_padron and persona_baja["id"] in ids_padron)

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E FASE 2: {total - len(fallos)}/{total} comprobaciones superadas")
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
            "DELETE FROM auditoria_arco WHERE persona_id IN (SELECT id FROM personas WHERE nombres LIKE 'ZZF2%')",
            """DELETE FROM auditoria_arco WHERE institucion_id IN (
                   SELECT id FROM instituciones WHERE nombre LIKE 'ZZF2%')""",
            """DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF2%')""",
            """DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF2%')""",
            """DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF2%')""",
            """DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                   SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF2%')""",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF2%'",
            """DELETE FROM edu_baremos WHERE dimension_id IN (
                   SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p
                   ON d.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZF2%')""",
            """DELETE FROM edu_opciones WHERE pregunta_id IN (
                   SELECT pr.id FROM edu_preguntas pr JOIN edu_pruebas p
                   ON pr.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZF2%')""",
            """DELETE FROM edu_preguntas WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF2%')""",
            """DELETE FROM edu_dimensiones WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF2%')""",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF2%'",
            """DELETE FROM consentimientos_informados WHERE persona_id IN (
                   SELECT id FROM personas WHERE nombres LIKE 'ZZF2%' OR nombres = 'ANONIMO')""",
            "DELETE FROM personas WHERE nombres LIKE 'ZZF2%' OR apellidos LIKE 'ARCO_%'",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzf2%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZF2%'",
        ]:
            cx.execute(text(consulta))
    print("Datos ZZF2 eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    parser.add_argument("--limpiar", action="store_true")
    args = parser.parse_args()

    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
