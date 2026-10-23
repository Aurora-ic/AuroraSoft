"""Verificación end-to-end — cierre de los 3 gaps de backend documentados en
docs/gaps-pendientes.md:

  1. GET /admin/personas/{id}/historico-campanas — comparación histórica
     entre campañas (dos campañas PHQ-9 reales, mismo alumno, puntajes
     distintos).
  2. GET /admin/personas/{id}/exportar-datos-arco?consentimiento_id=N —
     ARCO acotado a un consentimiento puntual (cada campaña matriculada
     bajo un consentimiento DISTINTO del apoderado).
  3. POST/GET /admin/personas/consentimiento/{id}/evidencia — subir y
     descargar el documento firmado/escaneado real de un consentimiento.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python -m tests.verificar_gaps_arco_evidencia_e2e
    python -m tests.verificar_gaps_arco_evidencia_e2e --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZGAPS"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:500]}")
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


def crear_colegio(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
    return inst["id"]


def registrar_y_loguear(h_super, correo, rol, institucion_id, nombre):
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {nombre}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": nombre,
        "rol": rol, "institucion_id": institucion_id}, headers=h_super), 200, f"Registro {nombre}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {nombre}")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def crear_persona(headers, inst_id, sello, etiqueta):
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    return persona["id"]


def registrar_consentimiento(headers, persona_id, inst_id, nombre_madre):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": inst_id,
        "otorgado_por_nombre": nombre_madre, "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento ({nombre_madre})")


def matricular(headers, campana_id, persona_id):
    m = exigir(requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                             json=[persona_id], headers=headers, timeout=30), 200, "Matrícula")
    return m["generados"][0]["token"]


def responder_y_finalizar_phq9(token, preg_phq9, valores):
    """`valores` es una lista de 9 enteros 0-3, uno por ítem en orden."""
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno PHQ-9", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar test")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [
        {"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)}
        for i, v in enumerate(valores)
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar",
                         json={"respuestas": respuestas}, timeout=30), 200, "Guardar respuestas")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    fila_phq9 = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")
    if not fila_phq9:
        print("\n!! Ejecuta `python -m seeds.seed_phq9` antes de correr este E2E.")
        sys.exit(1)
    phq9_id = fila_phq9[0]

    print("\n0 · Montaje: institución, admin, psicólogo, colegio, alumno")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst = crear_colegio(h_super, "A", sello)
    h_admin = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com", "admin", inst, f"{PREFIJO} Admin")
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", "psicologo", inst, f"{PREFIJO} Psi")
    h_colegio = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com", "colegio", inst, f"{PREFIJO} Colegio-user")

    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa",
                                       headers=h_admin, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}

    persona_id = crear_persona(h_admin, inst, sello, "Principal")

    # ------------------------------------------------------------------
    # 1 · Consentimiento 1 -> campaña A (puntaje 0, sin alerta) -> se revoca
    #     -> Consentimiento 2 -> campaña B (puntaje 27, alerta). La
    #     matrícula captura el consentimiento VIGENTE en ese momento.
    # ------------------------------------------------------------------
    print("\n1 · Consentimiento 1 -> campaña A -> revocar -> consentimiento 2 -> campaña B")
    cons_1_id = registrar_consentimiento(h_admin, persona_id, inst, "Madre Uno")["id"]

    campana_a = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña A {sello}", "institucion_id": inst},
        headers=h_psi, timeout=30), 200, "Campaña A")
    tok_a = matricular(h_admin, campana_a["id"], persona_id)
    insc_a = sql_uno("select id, consentimiento_apoderado_id from edu_inscripciones where token=:t", t=tok_a)
    insc_1_id, cons_de_insc_1 = insc_a[0], insc_a[1]
    comprobar("La matrícula de la campaña A capturó el consentimiento 1", cons_de_insc_1 == cons_1_id)
    responder_y_finalizar_phq9(tok_a, preg_phq9, [0] * 9)

    # 🆕 puede_aplicar_prueba() bloquea reaplicar la MISMA prueba antes de
    # `dias_minimos_entre_aplicaciones` (60 días si la prueba no fija uno
    # propio) — se adelanta fecha_resolucion de la campaña A para poder
    # matricular la campaña B del mismo PHQ-9 en el mismo test, sin que esto
    # sea en sí mismo lo que se está verificando.
    with MOTOR.begin() as c:
        c.execute(text("update edu_inscripciones set fecha_resolucion = :f where id = :i"),
                  {"f": datetime.utcnow() - timedelta(days=61), "i": insc_1_id})

    exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento/revocar",
                          headers=h_admin, timeout=30), 200, "Revocar consentimiento 1")
    cons_2_id = registrar_consentimiento(h_admin, persona_id, inst, "Madre Dos")["id"]

    campana_b = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña B {sello}", "institucion_id": inst},
        headers=h_psi, timeout=30), 200, "Campaña B")
    tok_b = matricular(h_admin, campana_b["id"], persona_id)
    insc_b = sql_uno("select id, consentimiento_apoderado_id from edu_inscripciones where token=:t", t=tok_b)
    insc_2_id, cons_de_insc_2 = insc_b[0], insc_b[1]
    comprobar("La matrícula de la campaña B capturó el consentimiento 2 (distinto del 1)",
              cons_de_insc_2 == cons_2_id and cons_de_insc_2 != cons_1_id)
    responder_y_finalizar_phq9(tok_b, preg_phq9, [3] * 9)

    # ------------------------------------------------------------------
    # 2 · Histórico entre campañas
    # ------------------------------------------------------------------
    print("\n2 · GET historico-campanas")
    r = requests.get(f"{API}/admin/personas/{persona_id}/historico-campanas", headers=h_psi, timeout=30)
    comprobar("psicólogo: 200", r.status_code == 200, f"status={r.status_code}")
    datos = r.json() if r.status_code == 200 else {}
    ids_evaluaciones = [e["inscripcion_id"] for e in datos.get("evaluaciones", [])]
    comprobar("Incluye las dos inscripciones", insc_1_id in ids_evaluaciones and insc_2_id in ids_evaluaciones,
              f"ids_evaluaciones={ids_evaluaciones}")
    if insc_1_id in ids_evaluaciones and insc_2_id in ids_evaluaciones:
        comprobar("Orden ASCENDENTE por fecha (la campaña A antes que la B)",
                  ids_evaluaciones.index(insc_1_id) < ids_evaluaciones.index(insc_2_id))
    comparacion = datos.get("comparacion_por_dimension", {})
    comprobar("comparacion_por_dimension no está vacía", len(comparacion) > 0)
    for serie in comparacion.values():
        niveles = [p["es_alerta"] for p in serie if p["inscripcion_id"] in (insc_1_id, insc_2_id)]
        if len(niveles) == 2:
            comprobar("La serie de la dimensión refleja la evolución real (sin alerta -> con alerta)",
                      niveles[0] is False and niveles[1] is True, f"serie={serie}")

    r_colegio = requests.get(f"{API}/admin/personas/{persona_id}/historico-campanas", headers=h_colegio, timeout=30)
    comprobar("'colegio': 403 (nunca ve el histórico clínico)", r_colegio.status_code == 403,
              f"status={r_colegio.status_code}")

    # ------------------------------------------------------------------
    # 3 · ARCO acotado a un consentimiento puntual
    # ------------------------------------------------------------------
    print("\n3 · GET exportar-datos-arco?consentimiento_id=")
    r_full = exigir(requests.get(f"{API}/admin/personas/{persona_id}/exportar-datos-arco",
                                  headers=h_admin, timeout=30), 200, "Export completo")
    ids_full = {i["inscripcion_id"] for i in r_full["inscripciones"]}
    comprobar("Sin acotar: trae ambas inscripciones", insc_1_id in ids_full and insc_2_id in ids_full)

    r_acotado = exigir(requests.get(
        f"{API}/admin/personas/{persona_id}/exportar-datos-arco?consentimiento_id={cons_2_id}",
        headers=h_admin, timeout=30), 200, "Export acotado a cons_2")
    ids_acotado = {i["inscripcion_id"] for i in r_acotado["inscripciones"]}
    comprobar("Acotado a cons_2: SOLO la inscripción ligada a ese consentimiento",
              ids_acotado == {insc_2_id}, f"ids_acotado={ids_acotado}")
    comprobar("Acotado: 'consentimientos' es solo ese registro, no la vista combinada",
              "acotado_a_un_consentimiento" in r_acotado["consentimientos"])
    comprobar("Acotado: no trae expediente_clinico/citas_programadas/sesiones_seguimiento",
              "expediente_clinico" not in r_acotado and "citas_programadas" not in r_acotado
              and "sesiones_seguimiento" not in r_acotado)
    comprobar("Acotado: SÍ trae datos_personales (identidad, no recortada por consentimiento)",
              r_acotado["datos_personales"]["id"] == persona_id)

    r_acotado_1 = exigir(requests.get(
        f"{API}/admin/personas/{persona_id}/exportar-datos-arco?consentimiento_id={cons_1_id}",
        headers=h_admin, timeout=30), 200, "Export acotado a cons_1")
    ids_acotado_1 = {i["inscripcion_id"] for i in r_acotado_1["inscripciones"]}
    comprobar("Acotado a cons_1: SOLO la inscripción ligada a ese otro consentimiento",
              ids_acotado_1 == {insc_1_id}, f"ids_acotado_1={ids_acotado_1}")

    otra_persona_id = crear_persona(h_admin, inst, sello, "Otra")
    r_mismatch = requests.get(
        f"{API}/admin/personas/{otra_persona_id}/exportar-datos-arco?consentimiento_id={cons_2_id}",
        headers=h_admin, timeout=30)
    comprobar("Un consentimiento de OTRA persona -> 404 (nunca se usa como filtro ajeno)",
              r_mismatch.status_code == 404, f"status={r_mismatch.status_code}")

    r_arco_colegio = requests.get(f"{API}/admin/personas/{persona_id}/exportar-datos-arco",
                                   headers=h_colegio, timeout=30)
    comprobar("'colegio': 403 en exportar-datos-arco (sin cambios por esta fase)",
              r_arco_colegio.status_code == 403, f"status={r_arco_colegio.status_code}")

    # ------------------------------------------------------------------
    # 4 · Evidencia del consentimiento
    # ------------------------------------------------------------------
    print("\n4 · POST/GET consentimiento/{id}/evidencia")
    contenido_pdf = b"%PDF-1.4 contenido de prueba " + sello.encode()
    r_subida = requests.post(
        f"{API}/admin/personas/consentimiento/{cons_2_id}/evidencia",
        files={"archivo": ("consentimiento_firmado.pdf", contenido_pdf, "application/pdf")},
        headers=h_admin, timeout=30,
    )
    comprobar("Subida: 200", r_subida.status_code == 200, f"status={r_subida.status_code} body={r_subida.text[:300]}")
    cuerpo_subida = r_subida.json() if r_subida.status_code == 200 else {}
    comprobar("evidencia_ruta queda apuntando a una key real de storage (no el texto crudo)",
              bool(cuerpo_subida.get("evidencia_ruta")) and "/consentimientos/" in cuerpo_subida.get("evidencia_ruta", ""))
    comprobar("evidencia_tamano_bytes coincide con el archivo subido",
              cuerpo_subida.get("evidencia_tamano_bytes") == len(contenido_pdf))

    r_descarga = requests.get(f"{API}/admin/personas/consentimiento/{cons_2_id}/evidencia",
                               headers=h_psi, timeout=30)
    comprobar("Descarga (otro rol de la misma institución): 200", r_descarga.status_code == 200)
    comprobar("El contenido descargado es BYTE A BYTE el mismo que se subió",
              r_descarga.content == contenido_pdf)

    r_extension_invalida = requests.post(
        f"{API}/admin/personas/consentimiento/{cons_2_id}/evidencia",
        files={"archivo": ("malicioso.exe", b"MZ...", "application/octet-stream")},
        headers=h_admin, timeout=30,
    )
    comprobar("Extensión no permitida -> 400 (nunca se guarda)", r_extension_invalida.status_code == 400,
              f"status={r_extension_invalida.status_code}")

    inst_b = crear_colegio(h_super, "B", sello)
    h_admin_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.adminb.{sello}@ejemplo.com", "admin", inst_b, f"{PREFIJO} Admin B")
    r_otra_institucion = requests.get(f"{API}/admin/personas/consentimiento/{cons_2_id}/evidencia",
                                       headers=h_admin_b, timeout=30)
    comprobar("Un admin de OTRA institución -> 403", r_otra_institucion.status_code == 403,
              f"status={r_otra_institucion.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    if fallos:
        sys.exit(1)


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    with motor.begin() as c:
        c.execute(text("""
            delete from edu_diagnosticos_alumno where inscripcion_id in (
                select i.id from edu_inscripciones i join personas p on p.id = i.persona_id
                where p.nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from edu_resultados_dimensiones where inscripcion_id in (
                select i.id from edu_inscripciones i join personas p on p.id = i.persona_id
                where p.nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from edu_respuestas_alumno where inscripcion_id in (
                select i.id from edu_inscripciones i join personas p on p.id = i.persona_id
                where p.nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from edu_informe_versiones where informe_id in (
                select inf.id from edu_informes inf join personas p on p.id = inf.persona_id
                where p.nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from edu_informes where persona_id in (select id from personas where nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from edu_inscripciones where persona_id in (
                select id from personas where nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("delete from edu_evaluaciones where nombre_grupo like :pref"), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from consentimientos_informados where persona_id in (
                select id from personas where nombres like :pref)
        """), {"pref": f"{PREFIJO}%"})
        c.execute(text("""
            delete from auditoria_arco where ejecutado_por_usuario_id in (
                select id from auth_usuarios where email like :pref)
        """), {"pref": f"{PREFIJO.lower()}%"})
        c.execute(text("delete from personas where nombres like :pref"), {"pref": f"{PREFIJO}%"})
        c.execute(text("delete from auth_usuarios where email like :pref"), {"pref": f"{PREFIJO.lower()}%"})
        c.execute(text("delete from instituciones where nombre like :pref"), {"pref": f"{PREFIJO}%"})
    print(f"Limpieza de datos {PREFIJO}* completada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    if args.limpiar:
        limpiar()
    else:
        main(args.url)
