"""Verificación end-to-end de la Fase 1 — protección del estudiante en riesgo.

Cubre los ocho casos obligatorios contra el servidor real y la base real:

  1. Baremo marcado como alerta            -> se detecta, informe retenido
  2. Nivel con texto distinto + es_alerta   -> se sigue detectando
  3. Sin baremo aplicable                   -> NO es "sin riesgo", se retiene
  4. Error durante el cálculo               -> no queda bloqueado, se recupera
  5. Doble envío concurrente                -> idempotente, sin duplicados
  6. Alerta con creador activo              -> se le notifica
  7. Alerta con creador inactivo            -> respaldo institucional
  8. Aislamiento entre instituciones        -> nada se cruza

Uso:
    uvicorn main:app --port 8010            (con SMTP deshabilitado)
    python tests/verificar_fase1_e2e.py
    python tests/verificar_fase1_e2e.py --limpiar

IMPORTANTE: arranca el servidor con EMAIL_USUARIO y EMAIL_PASSWORD vacíos.
`enviar_correo` corta en seco sin credenciales, así que no sale ningún correo
real hacia direcciones de prueba.
"""

import argparse
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
from modulos.educativo import crud as edu_crud, models as edu_models  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

PREFIJO = "ZZF1"
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
    """Reintenta ante un 429.

    /auth/login y /auth/registro están limitados a 5 peticiones por minuto por
    IP, y el montaje de este escenario necesita más. El límite es correcto y no
    se toca: se espera a que se abra la ventana.
    """
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


def ejecutar(consulta, **params):
    with MOTOR.begin() as cx:
        cx.execute(text(consulta), params)


# ======================================================================
# Utilidades de montaje
# ======================================================================
def crear_prueba_con_baremos(headers, sello, sufijo, tramos):
    """Crea una prueba de 2 ítems (uno inverso) y le carga los tramos dados.

    `tramos` es una lista de (minimo, maximo, nivel, es_alerta). Si va vacía,
    la prueba queda deliberadamente SIN baremos (caso 3).
    Devuelve (prueba_id, dimension_id, preguntas_por_orden).
    """
    opciones = [
        {"texto_opcion": "Nunca", "valor_puntuacion": 0},
        {"texto_opcion": "A veces", "valor_puntuacion": 1},
        {"texto_opcion": "A menudo", "valor_puntuacion": 2},
        {"texto_opcion": "Siempre", "valor_puntuacion": 3},
    ]
    prueba = exigir(requests.post(
        f"{API}/educativo/pruebas/",
        json={"nombre_tecnico": f"{PREFIJO}-{sufijo}-{sello}",
              "nombre_publico": f"Prueba {sufijo}",
              "escala_minima": 0, "escala_maxima": 3, "modo_calculo": "likert_suma"},
        headers=headers, timeout=30), 200, f"Crear prueba {sufijo}")
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
        headers=headers, timeout=30), 200, f"Carga masiva {sufijo}")

    completa = exigir(requests.get(
        f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=headers, timeout=30),
        200, f"Ver prueba {sufijo}")
    dimension = completa["dimensiones"][0]
    preguntas = {p["orden"]: p for p in dimension["preguntas"]}

    for minimo, maximo, nivel, es_alerta in tramos:
        exigir(requests.post(
            f"{API}/educativo/baremos/",
            json={"dimension_id": dimension["id"], "puntaje_minimo": minimo,
                  "puntaje_maximo": maximo, "nivel": nivel, "es_alerta": es_alerta,
                  "interpretacion": f"Interpretación de {nivel}."},
            headers=headers, timeout=30), 200, f"Baremo {nivel}")

    return prueba["id"], dimension["id"], preguntas


def montar_alumno(headers, inst_id, prueba_id, sello, etiqueta, dni):
    """Crea campaña + persona + consentimiento + matrícula. Devuelve (token, campana_id, persona_id)."""
    campana = exigir(requests.post(
        f"{API}/educativo/campanas/",
        json={"prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta}",
              "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona = exigir(requests.post(
        f"{API}/admin/personas/",
        json={"institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}",
              "apellidos": "Alumno", "documento_identidad": dni, "genero": "Femenino"},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    exigir(requests.post(
        f"{API}/admin/personas/{persona['id']}/consentimiento",
        json={"persona_id": persona["id"], "institucion_id": inst_id,
              "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    matricula = exigir(requests.post(
        f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
        json=[persona["id"]], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    return matricula["generados"][0]["token"], campana["id"], persona["id"]


def responder_examen(token, preguntas, valor_q1, valor_q2):
    exigir(requests.post(
        f"{API}/educativo/comenzar-test/{token}",
        json={"nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30),
        200, "Comenzar test")

    def opcion(orden, valor):
        return next(o["id"] for o in preguntas[orden]["opciones"] if o["valor_puntuacion"] == valor)

    exigir(requests.post(
        f"{API}/educativo/examen/{token}/guardar",
        json={"respuestas": [
            {"pregunta_id": preguntas[1]["id"], "opcion_id": opcion(1, valor_q1)},
            {"pregunta_id": preguntas[2]["id"], "opcion_id": opcion(2, valor_q2)},
        ]}, timeout=30), 200, "Guardar respuestas")


def estado_inscripcion(token):
    return sql_uno("""
        select id, estado, resultado_visible_alumno, informe_liberado,
               estado_interpretacion, dimensiones_sin_baremo
        from edu_inscripciones where token = :t""", t=token)


# ======================================================================
def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ------------------------------------------------------------------
    print("\n0 · Montaje: dos instituciones aisladas, con psicólogo y admin")

    tok_super = exigir(pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login superadmin",
        data={"username": os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
              "password": os.getenv("SUPERADMIN_PASSWORD")}),
        200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    def crear_colegio(letra):
        inst = exigir(requests.post(
            f"{API}/instituciones/",
            json={"nombre": f"{PREFIJO} Colegio {letra} {sello}", "tipo": "Colegio",
                  "email_contacto": f"contacto.{letra.lower()}{sello}@ejemplo.com"},
            headers=h_super, timeout=30), 201, f"Institución {letra}")
        usuarios = {}
        for rol in ("psicologo", "admin"):
            correo = f"{PREFIJO.lower()}.{rol}.{letra.lower()}.{sello}@ejemplo.com"
            u = exigir(pedir_con_reintento(
                requests.post, f"{API}/auth/registro", f"registro {rol} {letra}",
                json={"email": correo, "password": "ClaveDePrueba123",
                      "nombre_completo": f"{PREFIJO} {rol} {letra}", "rol": rol,
                      "institucion_id": inst["id"]},
                headers=h_super), 200, f"Usuario {rol} {letra}")
            tok = exigir(pedir_con_reintento(
                requests.post, f"{API}/auth/login", f"login {rol} {letra}",
                data={"username": correo, "password": "ClaveDePrueba123"}),
                200, f"Login {rol} {letra}")["access_token"]
            usuarios[rol] = {"id": u["id"], "email": correo,
                             "headers": {"Authorization": f"Bearer {tok}"}}
        return inst["id"], usuarios

    inst_a, users_a = crear_colegio("A")
    inst_b, users_b = crear_colegio("B")
    h_psi_a = users_a["psicologo"]["headers"]
    h_psi_b = users_b["psicologo"]["headers"]
    comprobar("Dos instituciones con psicólogo y admin activos", True,
              f"A={inst_a} B={inst_b}")

    # ==================================================================
    print("\nCASO 1 · Baremo marcado explícitamente como alerta")
    # Tramos: 0-2 sin alerta · 3-5 sin alerta · 6-8 CON alerta
    prueba1, _, preg1 = crear_prueba_con_baremos(h_psi_a, sello, "C1", [
        (0, 2, "Bajo", False), (3, 5, "Medio", False), (6, 8, "Alto", True)])
    tok1, camp1, _ = montar_alumno(h_psi_a, inst_a, prueba1, sello, "C1", f"{sello}101")
    responder_examen(tok1, preg1, 3, 0)   # 3 + (0+3-0)=3 -> 6 -> tramo de alerta

    r = requests.post(f"{API}/educativo/examen/{tok1}/finalizar", timeout=60)
    comprobar("Finaliza correctamente (200)", r.status_code == 200, f"status {r.status_code}")
    devueltos = r.json()
    est = estado_inscripcion(tok1)
    comprobar("Se detecta la alerta y el informe queda RETENIDO",
              est[2] is False and est[3] is False,
              f"visible={est[2]} liberado={est[3]}")
    comprobar("No se devuelve ningún diagnóstico al alumno", devueltos == [])
    comprobar("El diagnóstico queda marcado con es_alerta=True",
              sql_uno("select es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i",
                      i=est[0])[0] is True)
    comprobar("La interpretación se considera COMPLETA (hubo baremo)",
              est[4] == "completa", f"estado_interpretacion={est[4]!r}")
    r = requests.get(f"{API}/educativo/examen/{tok1}/informe-pdf", timeout=60)
    comprobar("El PDF del alumno está bloqueado", r.status_code == 403, f"status {r.status_code}")

    # ==================================================================
    print("\nCASO 2 · Texto del nivel irrelevante: manda el indicador")
    # "Sin indicadores aparentes" CON alerta  vs  "alto" SIN alerta.
    # Con la lógica antigua el resultado habría sido exactamente el inverso.
    prueba2, _, preg2 = crear_prueba_con_baremos(h_psi_a, sello, "C2", [
        (0, 5, "alto", False),                       # texto alarmante, NO es alerta
        (6, 8, "Sin indicadores aparentes", True)])  # texto inocuo, SÍ es alerta
    tok2, _, _ = montar_alumno(h_psi_a, inst_a, prueba2, sello, "C2", f"{sello}102")
    responder_examen(tok2, preg2, 3, 0)   # -> 6 -> tramo "Sin indicadores aparentes"

    exigir(requests.post(f"{API}/educativo/examen/{tok2}/finalizar", timeout=60), 200, "Finalizar C2")
    est2 = estado_inscripcion(tok2)
    nivel2 = sql_uno("select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i",
                     i=est2[0])
    comprobar("Un nivel de texto inocuo pero marcado SÍ retiene el informe",
              est2[2] is False and est2[3] is False,
              f"nivel={nivel2[0]!r} es_alerta={nivel2[1]} visible={est2[2]}")

    # El inverso: texto "alto" sin marcar NO debe retener
    tok2b, _, _ = montar_alumno(h_psi_a, inst_a, prueba2, sello, "C2b", f"{sello}103")
    responder_examen(tok2b, preg2, 1, 2)  # 1 + (3-2)=1 -> 2 -> tramo "alto" sin alerta
    exigir(requests.post(f"{API}/educativo/examen/{tok2b}/finalizar", timeout=60), 200, "Finalizar C2b")
    est2b = estado_inscripcion(tok2b)
    nivel2b = sql_uno("select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i",
                      i=est2b[0])
    comprobar("Un nivel llamado 'alto' pero NO marcado se entrega con normalidad",
              est2b[2] is True and est2b[3] is True,
              f"nivel={nivel2b[0]!r} es_alerta={nivel2b[1]} visible={est2b[2]}")

    # ==================================================================
    print("\nCASO 3 · Sin baremo aplicable: no es 'sin riesgo'")
    prueba3, _, preg3 = crear_prueba_con_baremos(h_psi_a, sello, "C3", [])  # sin baremos
    tok3, _, _ = montar_alumno(h_psi_a, inst_a, prueba3, sello, "C3", f"{sello}104")
    responder_examen(tok3, preg3, 2, 1)

    exigir(requests.post(f"{API}/educativo/examen/{tok3}/finalizar", timeout=60), 200, "Finalizar C3")
    est3 = estado_inscripcion(tok3)
    comprobar("NO se declara al alumno sin riesgo: el informe queda retenido",
              est3[2] is False and est3[3] is False,
              f"visible={est3[2]} liberado={est3[3]}")
    comprobar("Se registra la interpretación como INCOMPLETA",
              est3[4] == "incompleta", f"estado_interpretacion={est3[4]!r}")
    comprobar("Se deja constancia de qué dimensión faltó interpretar",
              est3[5] is not None and "Ansiedad" in est3[5], f"dimensiones_sin_baremo={est3[5]!r}")
    comprobar("No se inventó ningún diagnóstico",
              sql_uno("select count(*) from edu_diagnosticos_alumno where inscripcion_id=:i",
                      i=est3[0])[0] == 0)
    comprobar("El puntaje sí se calculó y conservó",
              sql_uno("select count(*) from edu_resultados_dimensiones where inscripcion_id=:i",
                      i=est3[0])[0] == 1)

    estado_api = exigir(requests.get(
        f"{API}/educativo/examen/{tok3}/estado-resultados", timeout=30), 200, "Estado C3")
    comprobar("El endpoint de estado expone 'incompleta' al backend/frontend",
              estado_api["estado_interpretacion"] == "incompleta")
    comprobar("Al alumno se le dice 'en revisión', sin revelar el motivo técnico",
              "revis" in estado_api["mensaje"].lower()
              and "baremo" not in estado_api["mensaje"].lower())

    # Caso de contraste: resultado válido SIN alerta -> sí se entrega
    tok3b, _, _ = montar_alumno(h_psi_a, inst_a, prueba1, sello, "C3b", f"{sello}105")
    responder_examen(tok3b, preg1, 0, 3)   # 0 + (3-3)=0 -> 0 -> tramo "Bajo"
    exigir(requests.post(f"{API}/educativo/examen/{tok3b}/finalizar", timeout=60), 200, "Finalizar C3b")
    est3b = estado_inscripcion(tok3b)
    comprobar("Contraste: resultado válido y sin alerta SÍ se entrega",
              est3b[2] is True and est3b[3] is True and est3b[4] == "completa",
              f"visible={est3b[2]} interpretacion={est3b[4]}")

    # ==================================================================
    print("\nCASO 4 · Error durante el cálculo: no bloquea al alumno")
    prueba4, _, preg4 = crear_prueba_con_baremos(h_psi_a, sello, "C4", [
        (0, 2, "Bajo", False), (3, 8, "Alto", True)])
    tok4, camp4, _ = montar_alumno(h_psi_a, inst_a, prueba4, sello, "C4", f"{sello}106")
    responder_examen(tok4, preg4, 3, 0)

    # Provocamos un fallo REAL en pleno cálculo, no simulado: corrompemos los
    # puntajes guardados para que la suma por dimensión desborde el entero de
    # PostgreSQL al insertar el ResultadoDimension. Es el tipo de error de
    # datos que antes dejaba al alumno finalizado y sin resultados.
    # Solo el ítem DIRECTO: al inverso se le aplica (min+max)-valor, que
    # compensaría la suma y no llegaría a desbordar.
    # Desde C-1 (Fase 3) los puntajes son NUMERIC(12,4), máx. 99 999 999.9999:
    # el valor cabe en la respuesta pero la suma (99 999 999 + 3) desborda el
    # puntaje directo, que es el fallo real que se quiere provocar.
    insc4 = estado_inscripcion(tok4)[0]
    ejecutar("""update edu_respuestas_alumno set puntaje_obtenido = 99999999
                where inscripcion_id = :i
                  and pregunta_id in (select id from edu_preguntas
                                      where es_inverso = false)""", i=insc4)

    r = requests.post(f"{API}/educativo/examen/{tok4}/finalizar", timeout=60)
    comprobar("El fallo de cálculo devuelve 500", r.status_code == 500, f"status {r.status_code}")
    cuerpo = r.json() if r.text else {}
    detalle = cuerpo.get("detail", "") if isinstance(cuerpo, dict) else ""
    comprobar("El mensaje le dice al alumno que sus respuestas están a salvo",
              "guardadas" in detalle.lower(), detalle[:90])

    est4 = estado_inscripcion(tok4)
    comprobar("La inscripción NO queda marcada como Finalizado",
              est4[1] != "Finalizado", f"estado={est4[1]!r}")
    comprobar("La transacción se revirtió: no quedaron puntajes a medias",
              sql_uno("select count(*) from edu_resultados_dimensiones where inscripcion_id=:i",
                      i=est4[0])[0] == 0)

    # Reparamos la causa y reintentamos: debe completarse
    ejecutar("update edu_respuestas_alumno set puntaje_obtenido = 3 "
             "where inscripcion_id = :i", i=insc4)
    r = requests.post(f"{API}/educativo/examen/{tok4}/finalizar", timeout=60)
    comprobar("Tras reparar la causa, el reintento SÍ funciona (200)",
              r.status_code == 200, f"status {r.status_code}")
    est4b = estado_inscripcion(tok4)
    comprobar("Ahora sí queda finalizado y con su alerta detectada",
              est4b[1] == "Finalizado" and est4b[2] is False,
              f"estado={est4b[1]} visible={est4b[2]}")

    # ==================================================================
    print("\nCASO 5 · Doble envío concurrente")
    prueba5, _, preg5 = crear_prueba_con_baremos(h_psi_a, sello, "C5", [
        (0, 2, "Bajo", False), (3, 8, "Alto", True)])
    tok5, _, _ = montar_alumno(h_psi_a, inst_a, prueba5, sello, "C5", f"{sello}107")
    responder_examen(tok5, preg5, 3, 0)

    respuestas_concurrentes = []
    barrera = threading.Barrier(2)

    def finalizar_en_paralelo():
        barrera.wait()
        try:
            r = requests.post(f"{API}/educativo/examen/{tok5}/finalizar", timeout=60)
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
    est5 = estado_inscripcion(tok5)
    n_result = sql_uno("select count(*) from edu_resultados_dimensiones where inscripcion_id=:i",
                       i=est5[0])[0]
    n_diag = sql_uno("select count(*) from edu_diagnosticos_alumno where inscripcion_id=:i",
                     i=est5[0])[0]
    comprobar("No se duplican los puntajes por dimensión", n_result == 1, f"{n_result} fila(s)")
    comprobar("No se duplican los diagnósticos", n_diag == 1, f"{n_diag} fila(s)")
    comprobar("La alerta se aplicó una sola vez y el informe está retenido",
              est5[2] is False and est5[3] is False)

    # ==================================================================
    print("\nCASO 6 · Alerta con creador activo")
    db = SessionLocal()
    try:
        evaluacion1 = db.query(edu_models.Evaluacion).filter(
            edu_models.Evaluacion.id == camp1).first()
        destinatarios, motivos = edu_crud.obtener_destinatarios_alerta(db, evaluacion1)
        comprobar("El creador activo recibe la alerta",
                  users_a["psicologo"]["email"] in destinatarios,
                  f"destinatarios: {destinatarios}")
        comprobar("El admin de la institución también la recibe (respaldo)",
                  users_a["admin"]["email"] in destinatarios)
        comprobar("El motivo del primer destinatario es 'creador de la campaña'",
                  motivos[0] == "creador de la campaña", f"motivos: {motivos}")

        # ==============================================================
        print("\nCASO 7 · Alerta con creador inactivo")
        ejecutar("update auth_usuarios set activo = false where id = :i",
                 i=users_a["psicologo"]["id"])
        db.expire_all()
        destinatarios_i, motivos_i = edu_crud.obtener_destinatarios_alerta(db, evaluacion1)
        comprobar("El creador inactivo ya NO recibe la alerta",
                  users_a["psicologo"]["email"] not in destinatarios_i,
                  f"destinatarios: {destinatarios_i}")
        comprobar("El respaldo institucional sí la recibe: la alerta no se pierde",
                  users_a["admin"]["email"] in destinatarios_i and len(destinatarios_i) >= 1)
        comprobar("El motivo declara que es respaldo institucional",
                  any("respaldo institucional" in m for m in motivos_i), f"motivos: {motivos_i}")

        # Sin ningún usuario activo -> último recurso: contacto del colegio
        ejecutar("update auth_usuarios set activo = false where institucion_id = :i", i=inst_a)
        db.expire_all()
        destinatarios_u, motivos_u = edu_crud.obtener_destinatarios_alerta(db, evaluacion1)
        comprobar("Sin ningún usuario activo se usa el contacto del colegio",
                  len(destinatarios_u) == 1 and "contacto" in motivos_u[0],
                  f"{destinatarios_u} / {motivos_u}")

        ejecutar("update auth_usuarios set activo = true where institucion_id = :i", i=inst_a)
        db.expire_all()

        # ==============================================================
        print("\nCASO 8 · Aislamiento entre instituciones")
        destinatarios_a, _ = edu_crud.obtener_destinatarios_alerta(db, evaluacion1)
        correos_b = {users_b["psicologo"]["email"], users_b["admin"]["email"]}
        comprobar("Ningún usuario del colegio B recibe alertas del colegio A",
                  not (set(destinatarios_a) & correos_b),
                  f"A={destinatarios_a}")
    finally:
        db.close()

    est1 = estado_inscripcion(tok1)
    r = requests.get(f"{API}/educativo/campanas/{camp1}/dashboard", headers=h_psi_b, timeout=30)
    comprobar("B no puede ver el dashboard de una campaña de A (403)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/educativo/inscripciones/{est1[0]}/informe-pdf",
                     headers=h_psi_b, timeout=60)
    comprobar("B no puede descargar el informe de un alumno de A (403)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/educativo/campanas/{camp1}/links", headers=h_psi_b, timeout=30)
    comprobar("B no puede ver los links mágicos de A (403)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.patch(f"{API}/educativo/inscripciones/{est1[0]}/liberar-informe",
                       json={}, headers=h_psi_b, timeout=30)
    comprobar("B no puede liberar el informe retenido de un alumno de A (403)",
              r.status_code == 403, f"status {r.status_code}")
    est1_tras = estado_inscripcion(tok1)
    comprobar("El informe de A sigue retenido tras el intento de B",
              est1_tras[3] is False)

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E FASE 1: {total - len(fallos)}/{total} comprobaciones superadas")
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
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF1%')""",
            """DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF1%')""",
            """DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN (
                   SELECT i.id FROM edu_inscripciones i JOIN edu_evaluaciones e
                   ON i.evaluacion_id=e.id WHERE e.nombre_grupo LIKE 'ZZF1%')""",
            """DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                   SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF1%')""",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF1%'",
            """DELETE FROM edu_baremos WHERE dimension_id IN (
                   SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p
                   ON d.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZF1%')""",
            """DELETE FROM edu_opciones WHERE pregunta_id IN (
                   SELECT pr.id FROM edu_preguntas pr JOIN edu_pruebas p
                   ON pr.prueba_id=p.id WHERE p.nombre_tecnico LIKE 'ZZF1%')""",
            """DELETE FROM edu_preguntas WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF1%')""",
            """DELETE FROM edu_dimensiones WHERE prueba_id IN (
                   SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF1%')""",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF1%'",
            """DELETE FROM consentimientos_informados WHERE persona_id IN (
                   SELECT id FROM personas WHERE nombres LIKE 'ZZF1%')""",
            "DELETE FROM personas WHERE nombres LIKE 'ZZF1%'",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzf1%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZF1%'",
        ]:
            cx.execute(text(consulta))
    print("Datos ZZF1 eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    parser.add_argument("--limpiar", action="store_true")
    args = parser.parse_args()

    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
