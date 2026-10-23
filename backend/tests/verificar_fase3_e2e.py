"""Verificación end-to-end de la Fase 3 contra el servidor real.

  C-1  puntaje decimal real, de la opción al informe
  C-3  correo duplicado -> 409
  C-4  JWT antiguo rechazado tras cambiar la contraseña; el nuevo, aceptado
  C-5  examen en progreso reanudable / finalizado / vencido / eliminado
  C-6  superadmin consultando usuarios por institución
  C-11 logo interno rechazado al guardar y nunca descargado al generar
  C-12 rate limiting del examen (por token, aislado entre alumnos, y por IP)
  C-16 FK nuevas sin 500 · C-17 institución y licencia
  +    campaña con la prueba privada de otro colegio

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_fase3_e2e.py
    python tests/verificar_fase3_e2e.py --limpiar
"""

import argparse
import http.server
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

PREFIJO = "ZZF3"
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


def pedir(metodo, url, contexto="", **kw):
    """Reintenta SOLO ante 429 de /auth (5/min por IP): el límite es correcto."""
    for _ in range(8):
        r = metodo(url, timeout=60, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def sql_uno(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchone()


def ejecutar(consulta, **p):
    with MOTOR.begin() as c:
        c.execute(text(consulta), p)


def login(email, clave):
    r = pedir(requests.post, f"{API}/auth/login", f"login {email}",
              data={"username": email, "password": clave})
    return r


# ======================================================================
def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    # ---------------- C-17 · institución y licencia ----------------
    print("\nC-17 · Creación de institución respetando la licencia")
    vence = (datetime.utcnow() + timedelta(days=90)).replace(microsecond=0)
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio A {sello}", "plan_activo": True,
        "fecha_vencimiento_licencia": vence.isoformat(),
        "limite_pruebas_mensual_por_alumno": 7,
    }, headers=h_super, timeout=30), 201, "Institución A")
    inst_a = inst["id"]
    fila = sql_uno("select plan_activo, fecha_vencimiento_licencia, limite_pruebas_mensual_por_alumno "
                   "from instituciones where id=:i", i=inst_a)
    comprobar("Se guardan plan, vencimiento y límite enviados",
              tuple(fila) == (True, vence, 7), str(tuple(fila)))
    comprobar("La respuesta refleja el límite real (7, no 100)",
              inst["limite_pruebas_mensual_por_alumno"] == 7)

    por_defecto = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")
    inst_b = por_defecto["id"]
    comprobar("Sin datos de licencia: activa, sin caducidad, límite 5",
              (por_defecto["plan_activo"], por_defecto["fecha_vencimiento_licencia"],
               por_defecto["limite_pruebas_mensual_por_alumno"]) == (True, None, 5))

    r = requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} X", "limite_pruebas_mensual_por_alumno": 0}, headers=h_super, timeout=30)
    comprobar("Un límite mensual de 0 se rechaza (422)", r.status_code == 422, f"status {r.status_code}")

    inactiva = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio Inactivo {sello}", "plan_activo": False},
        headers=h_super, timeout=30), 201, "Institución inactiva")

    # ---------------- Usuarios ----------------
    def crear_usuario(correo, rol, inst_id):
        return pedir(requests.post, f"{API}/auth/registro", f"registro {rol}", json={
            "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} {rol}",
            "rol": rol, "institucion_id": inst_id}, headers=h_super)

    correo_psi = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(crear_usuario(correo_psi, "psicologo", inst_a), 200, "psicólogo A")
    correo_psi_b = f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com"
    exigir(crear_usuario(correo_psi_b, "psicologo", inst_b), 200, "psicólogo B")
    correo_inact = f"{PREFIJO.lower()}.inact.{sello}@ejemplo.com"
    exigir(crear_usuario(correo_inact, "psicologo", inactiva["id"]), 200, "psicólogo inactivo")

    tok_a = exigir(login(correo_psi, "ClaveDePrueba123"), 200, "login A")["access_token"]
    h_a = {"Authorization": f"Bearer {tok_a}"}
    h_b = {"Authorization": f"Bearer {exigir(login(correo_psi_b, 'ClaveDePrueba123'), 200, 'login B')['access_token']}"}

    tok_inact = exigir(login(correo_inact, "ClaveDePrueba123"), 200, "login inactivo")["access_token"]
    r = requests.get(f"{API}/instituciones/me", headers={"Authorization": f"Bearer {tok_inact}"}, timeout=30)
    comprobar("Una institución creada con plan_activo=false bloquea a sus usuarios (403)",
              r.status_code == 403, f"status {r.status_code}")

    # ---------------- C-3 · correo duplicado ----------------
    print("\nC-3 · Correo duplicado")
    r = crear_usuario(correo_psi, "psicologo", inst_a)
    comprobar("Mismo correo: 409, no 500", r.status_code == 409, f"status {r.status_code}")
    comprobar("Mensaje claro y sin datos de la otra cuenta",
              "ya está en uso" in r.json().get("detail", "") and str(inst_a) not in r.json()["detail"],
              r.json().get("detail", ""))
    r = crear_usuario(correo_psi.upper(), "psicologo", inst_b)
    comprobar("Mismo correo en MAYÚSCULAS y en otro colegio: también 409",
              r.status_code == 409, f"status {r.status_code}")

    # ---------------- C-6 · superadmin y usuarios ----------------
    print("\nC-6 · Superadmin consultando usuarios por institución")
    r = requests.get(f"{API}/auth/usuarios/", params={"institucion_id": inst_a}, headers=h_super, timeout=30)
    usuarios = r.json() if r.status_code == 200 else []
    comprobar("El superadmin lista los usuarios de una institución (200)",
              r.status_code == 200 and any(u["email"] == correo_psi for u in usuarios),
              f"status {r.status_code}, {len(usuarios)} usuario(s)")
    comprobar("...y solo los de esa institución",
              all(u["institucion_id"] == inst_a for u in usuarios))
    r = requests.get(f"{API}/auth/usuarios/", headers=h_super, timeout=30)
    comprobar("Sin ?institucion_id el superadmin recibe 400 explicativo", r.status_code == 400)
    r = requests.get(f"{API}/auth/usuarios/", params={"institucion_id": 999999}, headers=h_super, timeout=30)
    comprobar("Institución inexistente: 404", r.status_code == 404)

    correo_admin_b = f"{PREFIJO.lower()}.adminb.{sello}@ejemplo.com"
    exigir(crear_usuario(correo_admin_b, "admin", inst_b), 200, "admin B")
    h_admin_b = {"Authorization": f"Bearer {exigir(login(correo_admin_b, 'ClaveDePrueba123'), 200, 'login admin B')['access_token']}"}
    r = requests.get(f"{API}/auth/usuarios/", params={"institucion_id": inst_a}, headers=h_admin_b, timeout=30)
    vistos = r.json() if r.status_code == 200 else []
    comprobar("Un admin que pide OTRA institución solo ve la suya",
              r.status_code == 200 and vistos and all(u["institucion_id"] == inst_b for u in vistos),
              f"{len(vistos)} usuario(s) de B")
    r = requests.get(f"{API}/auth/usuarios/", headers=h_b, timeout=30)
    comprobar("Un psicólogo sigue sin acceso al listado (403)", r.status_code == 403)

    # ---------------- C-4 · JWT versionado ----------------
    print("\nC-4 · Invalidación de JWT al cambiar la contraseña")
    r = requests.get(f"{API}/instituciones/me", headers=h_a, timeout=30)
    comprobar("JWT antiguo funciona ANTES del cambio", r.status_code == 200)

    exigir(pedir(requests.post, f"{API}/auth/solicitar-recuperacion", "recuperación",
                 json={"email": correo_psi}), 200, "Solicitar recuperación")
    token_reset = sql_uno("select t.token from auth_tokens_recuperacion t join auth_usuarios u "
                          "on u.id=t.usuario_id where u.email=:e and t.usado=false "
                          "order by t.id desc", e=correo_psi)
    comprobar("La solicitud (con envío en segundo plano) genera el enlace", token_reset is not None)
    exigir(requests.post(f"{API}/auth/resetear-password",
                         json={"token": token_reset[0], "nueva_password": "NuevaClave456"}, timeout=30),
           200, "Resetear contraseña")

    r = requests.get(f"{API}/instituciones/me", headers=h_a, timeout=30)
    comprobar("JWT antiguo RECHAZADO tras el cambio (401)", r.status_code == 401, f"status {r.status_code}")
    comprobar("La contraseña antigua ya no inicia sesión",
              login(correo_psi, "ClaveDePrueba123").status_code == 401)
    tok_a = exigir(login(correo_psi, "NuevaClave456"), 200, "login nueva clave")["access_token"]
    h_a = {"Authorization": f"Bearer {tok_a}"}
    comprobar("JWT nuevo ACEPTADO (200)",
              requests.get(f"{API}/instituciones/me", headers=h_a, timeout=30).status_code == 200)
    comprobar("El enlace de recuperación usado no sirve dos veces",
              requests.post(f"{API}/auth/resetear-password", json={
                  "token": token_reset[0], "nueva_password": "OtraClave789"}, timeout=30).status_code == 400)

    # ---------------- Aislamiento: prueba ajena ----------------
    print("\nAislamiento · campaña con la prueba privada de otro colegio")
    prueba_b = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-PRIVADA-B-{sello}", "nombre_publico": "Privada de B"},
        headers=h_b, timeout=30), 200, "Prueba privada B")
    r = requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_b["id"], "nombre_grupo": f"{PREFIJO} robo", "institucion_id": inst_a},
        headers=h_a, timeout=30)
    comprobar("A NO puede lanzar una campaña con la prueba privada de B (404)",
              r.status_code == 404, f"status {r.status_code}")

    # ---------------- C-16 · FK nuevas sin 500 ----------------
    print("\nC-16 · Claves foráneas nuevas sin errores 500")
    r = requests.post(f"{API}/educativo/campos-socio/", json={
        "pregunta": "¿Con quién vives?", "tipo_respuesta": "texto", "cliente_id": 999999},
        headers=h_super, timeout=30)
    comprobar("campos-socio con institución inexistente: 404, no 500", r.status_code == 404,
              f"status {r.status_code}")

    # ---------------- C-1 · puntaje decimal ----------------
    print("\nC-1 · Puntaje decimal real, de la opción al informe")
    opciones = [{"texto_opcion": t, "valor_puntuacion": v}
                for t, v in [("Nada", 0), ("Algo", 0.5), ("Bastante", 1.25), ("Mucho", 2.75)]]
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-DECIMAL-{sello}", "nombre_publico": "Escala ponderada",
        "escala_minima": 0, "escala_maxima": 3}, headers=h_a, timeout=30), 200, "Prueba decimal")
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "Bienestar"}],
        "preguntas": [
            {"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "Bienestar", "opciones": opciones},
            {"texto_pregunta": "Ítem 2", "orden": 2, "nombre_dimension": "Bienestar", "opciones": opciones},
        ]}, headers=h_a, timeout=30), 200, "Carga decimal")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa",
                                  headers=h_a, timeout=30), 200, "Detalle decimal")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    for mn, mx, nivel in [(0, 1.74, "Bajo"), (1.75, 1.99, "Justo en el umbral decimal"), (2, 6, "Alto")]:
        exigir(requests.post(f"{API}/educativo/baremos/", json={
            "dimension_id": dim["id"], "puntaje_minimo": mn, "puntaje_maximo": mx, "nivel": nivel},
            headers=h_a, timeout=30), 200, f"Baremo {nivel}")

    def opcion(orden, valor):
        return next(o["id"] for o in pregs[orden]["opciones"] if abs(o["valor_puntuacion"] - valor) < 1e-9)

    token_d = montar_y_comenzar(h_a, inst_a, prueba["id"], sello, "Decimal", f"{sello}D1")
    exigir(requests.post(f"{API}/educativo/examen/{token_d}/guardar", json={"respuestas": [
        {"pregunta_id": pregs[1]["id"], "opcion_id": opcion(1, 0.5)},
        {"pregunta_id": pregs[2]["id"], "opcion_id": opcion(2, 1.25)},
    ]}, timeout=30), 200, "Guardar decimal")
    exigir(requests.post(f"{API}/educativo/examen/{token_d}/finalizar", timeout=60), 200, "Finalizar decimal")

    insc_d, camp_d = sql_uno("select id, evaluacion_id from edu_inscripciones where token=:t", t=token_d)
    puntaje = sql_uno("select puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i", i=insc_d)[0]
    comprobar("Se guarda el decimal exacto: 0.5 + 1.25 = 1.75 (antes se truncaba a 1)",
              float(puntaje) == 1.75, f"BD: {puntaje}")
    nivel = sql_uno("select nivel from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_d)
    comprobar("El baremo decimal interpreta 1.75 en su tramo correcto",
              nivel and nivel[0] == "Justo en el umbral decimal", str(nivel))
    dash = exigir(requests.get(f"{API}/educativo/campanas/{camp_d}/dashboard", headers=h_a, timeout=30),
                  200, "Dashboard decimal")
    comprobar("El dashboard devuelve 1.75", dash["alumnos"][0]["resultados"][0]["puntaje_directo"] == 1.75)
    r = requests.get(f"{API}/educativo/inscripciones/{insc_d}/informe-pdf", headers=h_a, timeout=60)
    comprobar("El PDF con puntaje decimal se genera", r.status_code == 200 and r.content[:4] == b"%PDF",
              f"status {r.status_code}")
    r = requests.get(f"{API}/educativo/campanas/{camp_d}/exportar-excel", headers=h_a, timeout=60)
    comprobar("El Excel con puntaje decimal se genera", r.status_code == 200 and r.content[:2] == b"PK")

    # ---------------- C-5 · reanudar examen ----------------
    print("\nC-5 · Reanudación del examen en sus cuatro estados")
    prueba_r = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-REANUDA-{sello}", "nombre_publico": "Reanudable"},
        headers=h_a, timeout=30), 200, "Prueba reanudable")
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_r["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D",
                       "opciones": [{"texto_opcion": "No", "valor_puntuacion": 0},
                                    {"texto_opcion": "Sí", "valor_puntuacion": 1}]}
                      for i in (1, 2, 3)]}, headers=h_a, timeout=30), 200, "Carga reanudable")
    det_r = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_r['id']}/completa", headers=h_a, timeout=30),
                   200, "Detalle reanudable")
    dim_r = det_r["dimensiones"][0]
    pregs_r = {p["orden"]: p for p in dim_r["preguntas"]}
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_r["id"], "puntaje_minimo": 0, "puntaje_maximo": 3, "nivel": "Normal"},
        headers=h_a, timeout=30), 200, "Baremo reanudable")

    formulario = {"nombre_completo": "Alumna", "edad": 15, "sexo": "Femenino",
                  "poblacion": "Secundaria", "acepta_terminos": True}
    token_p = montar_y_comenzar(h_a, inst_a, prueba_r["id"], sello, "Progreso", f"{sello}P1")
    exigir(requests.post(f"{API}/educativo/examen/{token_p}/guardar", json={"respuestas": [
        {"pregunta_id": pregs_r[1]["id"], "opcion_id": pregs_r[1]["opciones"][1]["id"]}]},
        timeout=30), 200, "Guardar 1 de 3")

    # El alumno recarga la página: vuelve a pasar por comenzar-test
    r = requests.post(f"{API}/educativo/comenzar-test/{token_p}",
                      json={**formulario, "edad": 99, "poblacion": "Universitario"}, timeout=30)
    comprobar("EN PROGRESO: recargar el enlace REANUDA (200, antes 400)", r.status_code == 200,
              f"status {r.status_code}")
    datos = sql_uno("select estado, edad, poblacion from edu_inscripciones where token=:t", t=token_p)
    comprobar("Reanudar no permite cambiar edad/población a mitad del examen",
              tuple(datos) == ("En Progreso", 15, "Secundaria"), str(tuple(datos)))
    prog = exigir(requests.get(f"{API}/educativo/examen/{token_p}/progreso", timeout=30), 200, "Progreso")
    comprobar("/progreso devuelve lo ya contestado para retomar",
              prog["respuestas"] == [{"pregunta_id": pregs_r[1]["id"],
                                      "opcion_id": pregs_r[1]["opciones"][1]["id"]}], str(prog))
    comprobar("/progreso no expone puntajes", "puntaje" not in str(prog).lower())
    exigir(requests.post(f"{API}/educativo/examen/{token_p}/guardar", json={"respuestas": [
        {"pregunta_id": pregs_r[i]["id"], "opcion_id": pregs_r[i]["opciones"][0]["id"]} for i in (2, 3)]},
        timeout=30), 200, "Guardar el resto")
    exigir(requests.post(f"{API}/educativo/examen/{token_p}/finalizar", timeout=60), 200, "Finalizar")

    r = requests.post(f"{API}/educativo/comenzar-test/{token_p}", json=formulario, timeout=30)
    comprobar("FINALIZADO: no se puede volver a empezar (409)", r.status_code == 409, f"status {r.status_code}")
    r = requests.post(f"{API}/educativo/examen/{token_p}/guardar", json={"respuestas": [
        {"pregunta_id": pregs_r[1]["id"], "opcion_id": pregs_r[1]["opciones"][0]["id"]}]}, timeout=30)
    comprobar("FINALIZADO: no se pueden modificar respuestas (400)", r.status_code == 400)
    r = requests.post(f"{API}/educativo/examen/{token_p}/finalizar", timeout=30)
    comprobar("FINALIZADO: el doble envío sigue rechazado (400)", r.status_code == 400)
    r = requests.get(f"{API}/educativo/examen/{token_p}/progreso", timeout=30)
    comprobar("FINALIZADO: /progreso no lo reabre (409)", r.status_code == 409)

    token_v = montar_y_comenzar(h_a, inst_a, prueba_r["id"], sello, "Vencida", f"{sello}V1")
    camp_v = sql_uno("select evaluacion_id from edu_inscripciones where token=:t", t=token_v)[0]
    ejecutar("update edu_evaluaciones set fecha_fin=:f where id=:i",
             f=datetime.utcnow() - timedelta(hours=1), i=camp_v)
    r = requests.post(f"{API}/educativo/comenzar-test/{token_v}", json=formulario, timeout=30)
    comprobar("VENCIDA: reanudar sigue bloqueado (410)", r.status_code == 410, f"status {r.status_code}")
    comprobar("VENCIDA: /progreso también (410)",
              requests.get(f"{API}/educativo/examen/{token_v}/progreso", timeout=30).status_code == 410)

    token_e = montar_y_comenzar(h_a, inst_a, prueba_r["id"], sello, "Eliminada", f"{sello}E1")
    insc_e = sql_uno("select id from edu_inscripciones where token=:t", t=token_e)[0]
    exigir(requests.delete(f"{API}/educativo/alumnos/{insc_e}/soft-delete", headers=h_a, timeout=30),
           200, "Soft delete")
    r = requests.post(f"{API}/educativo/comenzar-test/{token_e}", json=formulario, timeout=30)
    comprobar("ELIMINADA: sigue devolviendo 410", r.status_code == 410, f"status {r.status_code}")

    # ---------------- C-11 · logo ----------------
    print("\nC-11 · Logo institucional sin SSRF")
    for url, nombre in [("https://169.254.169.254/latest/meta-data/", "metadata"),
                        ("https://127.0.0.1/logo.png", "loopback"),
                        ("https://192.168.0.10/logo.png", "IP privada"),
                        ("http://ejemplo.com/logo.png", "http sin cifrar")]:
        r = requests.patch(f"{API}/instituciones/{inst_a}", json={"logo_url": url}, headers=h_super, timeout=30)
        comprobar(f"Guardar un logo en {nombre}: rechazado (422)", r.status_code == 422, f"status {r.status_code}")

    peticiones = []

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            peticiones.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
        def log_message(self, *a):
            pass

    interno = http.server.HTTPServer(("127.0.0.1", 0), Manejador)
    threading.Thread(target=interno.serve_forever, daemon=True).start()
    try:
        # Dato "heredado": guardado directamente, saltándose la validación de escritura
        ejecutar("update instituciones set logo_url=:u where id=:i",
                 u=f"http://127.0.0.1:{interno.server_address[1]}/latest/meta-data", i=inst_a)
        ejecutar("update edu_inscripciones set informe_liberado=true, resultado_visible_alumno=true "
                 "where id=:i", i=insc_d)
        r = requests.get(f"{API}/educativo/examen/{token_d}/informe-pdf", timeout=60)
        comprobar("El PDF PÚBLICO del alumno se genera igualmente (200)",
                  r.status_code == 200 and r.content[:4] == b"%PDF", f"status {r.status_code}")
        comprobar("...y el servicio interno NO recibió ninguna petición",
                  peticiones == [], f"peticiones: {peticiones}")
    finally:
        interno.shutdown()

    # ---------------- C-12 · rate limiting ----------------
    print("\nC-12 · Rate limiting de los endpoints públicos del examen")
    codigos = [requests.get(f"{API}/educativo/examen/{token_p}/estado-resultados", timeout=30).status_code
               for _ in range(31)]
    comprobar("Uso normal de un alumno: las primeras 30 consultas pasan",
              codigos[:30].count(200) == 30, f"{codigos[:30].count(200)}/30")
    comprobar("La consulta 31 del MISMO enlace en un minuto: 429", codigos[30] == 429,
              f"status {codigos[30]}")
    r = requests.get(f"{API}/educativo/examen/{token_d}/estado-resultados", timeout=30)
    comprobar("Otro alumno de la misma IP (mismo aula) NO se ve afectado (200)",
              r.status_code == 200, f"status {r.status_code}")

    # Por IP: enumeración de tokens (cada intento usa un token distinto)
    enumeracion = [requests.get(f"{API}/educativo/examen/{uuid.uuid4()}/informe-pdf",
                                timeout=30).status_code for _ in range(125)]
    comprobar("Enumerar tokens desde una IP acaba bloqueado (429)",
              429 in enumeracion, f"404×{enumeracion.count(404)} y 429×{enumeracion.count(429)}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E FASE 3: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def montar_y_comenzar(headers, inst_id, prueba_id, sello, etiqueta, dni):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": dni}, headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    mat = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                               json=[persona["id"]], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    token = mat["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumna", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")
    return token


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF3%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF3%'"
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZF3%'"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM auditoria_arco WHERE institucion_id IN ({insts})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF3%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF3%'",
            f"DELETE FROM edu_campos_socio WHERE cliente_id IN ({insts})",
            f"DELETE FROM consentimientos_informados WHERE institucion_id IN ({insts})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            "DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE 'zzf3%')",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzf3%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZF3%'",
        ]:
            c.execute(text(q))
    print("Datos ZZF3 eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    a = ap.parse_args()
    if a.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(a.url))
