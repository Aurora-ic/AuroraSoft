"""E2E — aplicación individual desde el perfil, elegibilidad antes de
matricular y regla de reaplicación corregida (sesión 2026-11-01).

  1  POST /personas/{id}/aplicacion-individual crea una campaña `individual`
     de un solo inscrito con su enlace; GET /campanas?tipo= la separa
  2  Repetirla con la prueba pendiente -> 409 (antes: dos enlaces)
  3  Terminada, repetirla -> 409 con la fecha desde la que vuelve a estar disponible
  4  Sin consentimiento -> 409 y NO queda ninguna campaña vacía
  5  GET /pruebas/{id}/elegibilidad: motivos (sin consentimiento, pendiente,
     reciente) para el padrón entero y para un solo estudiante
  6  Una campaña grupal ya NO matricula a quien tiene la misma prueba
     pendiente en otra (bug cerrado)
  7  Estadísticas por salón (dashboard académico) e Inicio ignoran las individuales
  8  Candados: colegio 403, estudiante de otro colegio 404, fecha de cierre pasada rechazada

    uvicorn main:app --port 8010   (SMTP apagado, captcha no obligatorio)
    python -m tests.verificar_aplicacion_individual_e2e
    python -m tests.verificar_aplicacion_individual_e2e --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZINDIV"
API = "http://127.0.0.1:8010/api"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    return r.json() if r.text else None


def pedir(metodo, url, contexto="", **kw):
    for _ in range(8):
        r = metodo(url, timeout=60, **kw)
        if r.status_code != 429:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


def main(url_base):
    global API
    API = url_base.rstrip("/") + "/api"
    motor = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.now(timezone.utc).strftime("%H%M%S")

    print("\n0 · Montaje")
    from core.security import get_password_hash
    correo_super = f"{PREFIJO.lower()}.super.{sello}@ejemplo.com"
    with motor.begin() as c:
        c.execute(text(
            "INSERT INTO auth_usuarios (email, hashed_password, nombre_completo, rol, activo, token_version) "
            "VALUES (:e, :h, :n, 'superadmin', true, 0)"
        ), {"e": correo_super, "h": get_password_hash("ClaveDePrueba123"), "n": f"{PREFIJO} Super"})
        ids = dict(c.execute(text(
            "select nombre_tecnico, id from edu_pruebas where institucion_id is null "
            "and nombre_tecnico in ('PHQ-9', 'GAD-7', 'APTITUD_TECNICA_INTERNA')")).all())
    if not {"PHQ-9", "GAD-7"} <= set(ids):
        print("!! Faltan PHQ-9/GAD-7 en el catálogo.")
        return 1
    phq9, gad7, interna = ids["PHQ-9"], ids["GAD-7"], ids.get("APTITUD_TECNICA_INTERNA")
    h_super = {"Authorization": f"Bearer {exigir(login(correo_super, 'ClaveDePrueba123'), 200, 'login super')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    def usuario(etiqueta, rol, inst):
        correo = f"{PREFIJO.lower()}.{etiqueta}.{sello}@ejemplo.com"
        exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {etiqueta}", json={
            "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} {etiqueta}",
            "rol": rol, "institucion_id": inst}, headers=h_super), 200, f"Registro {etiqueta}")
        return {"Authorization": f"Bearer {exigir(login(correo, 'ClaveDePrueba123'), 200, f'Login {etiqueta}')['access_token']}"}

    h_psi = usuario("psi", "psicologo", inst_a)
    h_col = usuario("colegio", "colegio", inst_a)
    h_psib = usuario("psib", "psicologo", inst_b)

    base = f"{API}/admin/personas"
    nivel = exigir(requests.post(f"{base}/academico/niveles", json={"institucion_id": inst_a, "nombre": "Secundaria"}, headers=h_super, timeout=30), 200, "nivel")["id"]
    grado = exigir(requests.post(f"{base}/academico/grados", json={"nivel_educativo_id": nivel, "nombre": "3°"}, headers=h_super, timeout=30), 200, "grado")["id"]
    seccion = exigir(requests.post(f"{base}/academico/secciones", json={"grado_id": grado, "nombre": "A", "anio_escolar": 2026}, headers=h_super, timeout=30), 200, "sección")["id"]

    def persona(etiqueta, consentimiento=True, inst=inst_a, h=h_psi):
        pid = exigir(requests.post(f"{base}/", json={
            "institucion_id": inst, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
            "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=h, timeout=30), 200, f"persona {etiqueta}")["id"]
        if inst == inst_a:
            exigir(requests.post(f"{base}/{pid}/matricula", json={"seccion_id": seccion}, headers=h, timeout=30), 200, f"matrícula {etiqueta}")
        if consentimiento:
            exigir(requests.post(f"{base}/{pid}/consentimiento", json={
                "persona_id": pid, "institucion_id": inst, "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
                headers=h, timeout=30), 200, f"consentimiento {etiqueta}")
        return pid

    def individual(pid, prueba_id, h=h_psi, **extra):
        return requests.post(f"{API}/educativo/personas/{pid}/aplicacion-individual",
                             json={"prueba_id": prueba_id, **extra}, headers=h, timeout=60)

    def rendir(token):
        exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
            "nombre_completo": "Alumno", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
            "acepta_terminos": True}, timeout=30), 200, "comenzar")
        preguntas = exigir(requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30), 200, "preguntas")
        respuestas = [{"pregunta_id": p["id"], "opcion_id": p["opciones"][0]["id"]} for p in preguntas]
        exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar")
        exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "finalizar")

    def campanas_de_a():
        with motor.connect() as c:
            return c.execute(text("select count(*) from edu_evaluaciones where institucion_id=:i"), {"i": inst_a}).scalar()

    ana, beto, caro, dani = persona("Ana"), persona("Beto", consentimiento=False), persona("Caro"), persona("Dani")

    # ------------------------------------------------------------------
    print("\n1 · Aplicación individual")
    r = individual(ana, phq9, alumno_ve_informe=True)
    cuerpo = r.json() if r.status_code == 200 else {}
    comprobar("POST aplicacion-individual -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    ev = cuerpo.get("evaluacion", {})
    comprobar("La campaña es 'individual', con el interruptor pedido", ev.get("tipo") == "individual" and ev.get("alumno_ve_informe") is True, str(ev))
    comprobar("Trae el enlace (token) del estudiante", bool(cuerpo.get("token")))
    tok_ana = cuerpo.get("token")
    with motor.connect() as c:
        n = c.execute(text("select count(*) from edu_inscripciones where evaluacion_id=:e"), {"e": ev.get("id")}).scalar()
    comprobar("Un solo inscrito", n == 1, str(n))
    ind = exigir(requests.get(f"{API}/educativo/campanas/", params={"tipo": "individual"}, headers=h_psi, timeout=30), 200, "lista individual")
    gru = exigir(requests.get(f"{API}/educativo/campanas/", params={"tipo": "grupal"}, headers=h_psi, timeout=30), 200, "lista grupal")
    todas = exigir(requests.get(f"{API}/educativo/campanas/", headers=h_psi, timeout=30), 200, "lista")
    comprobar("?tipo=individual la incluye", any(i["id"] == ev.get("id") for i in ind["items"]))
    comprobar("?tipo=grupal no la incluye", all(i["id"] != ev.get("id") for i in gru["items"]))
    comprobar("Sin tipo, aparece como siempre", any(i["id"] == ev.get("id") for i in todas["items"]))
    comprobar("tipo inválido -> 422", requests.get(f"{API}/educativo/campanas/", params={"tipo": "x"}, headers=h_psi, timeout=30).status_code == 422)

    # ------------------------------------------------------------------
    print("\n2 · Misma prueba pendiente")
    r = individual(ana, phq9)
    comprobar("Repetir con la prueba pendiente -> 409 'pendiente'", r.status_code == 409 and "pendiente" in r.text.lower(), f"{r.status_code} {r.text[:200]}")

    # ------------------------------------------------------------------
    print("\n3 · Reaplicación")
    rendir(tok_ana)
    r = individual(ana, phq9)
    comprobar("Terminada hace nada -> 409 con 'se reaplica cada'", r.status_code == 409 and "se reaplica cada" in r.text, f"{r.status_code} {r.text[:200]}")

    # ------------------------------------------------------------------
    print("\n4 · Sin consentimiento")
    antes = campanas_de_a()
    r = individual(beto, phq9)
    comprobar("Sin consentimiento -> 409", r.status_code == 409 and "consentimiento" in r.text.lower(), f"{r.status_code} {r.text[:200]}")
    comprobar("No queda ninguna campaña vacía", campanas_de_a() == antes)

    # ------------------------------------------------------------------
    print("\n5 · Elegibilidad")
    e = exigir(requests.get(f"{API}/educativo/pruebas/{phq9}/elegibilidad", headers=h_psi, timeout=30), 200, "elegibilidad")
    motivos = {x["persona_id"]: x for x in e["no_elegibles"]}
    comprobar("Ana -> reciente, con fecha de disponibilidad", motivos.get(ana, {}).get("motivo") == "reciente" and motivos[ana]["disponible_desde"], str(motivos.get(ana)))
    comprobar("Beto -> sin_consentimiento", motivos.get(beto, {}).get("motivo") == "sin_consentimiento")
    comprobar("Caro y Dani son elegibles", caro not in motivos and dani not in motivos)
    comprobar("Informa los días de reaplicación de la prueba", isinstance(e.get("dias_minimos_entre_aplicaciones"), int))
    e1 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9}/elegibilidad", params={"persona_id": caro}, headers=h_psi, timeout=30), 200, "elegibilidad 1")
    comprobar("Con persona_id: solo ese estudiante (elegible -> lista vacía)", e1["no_elegibles"] == [])

    # ------------------------------------------------------------------
    print("\n6 · Pendiente en otra campaña (bug cerrado)")
    r = individual(caro, gad7)
    comprobar("Caro: GAD-7 individual pendiente", r.status_code == 200, r.text[:200])
    camp = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": gad7, "nombre_grupo": f"{PREFIJO} GAD7 {sello}", "institucion_id": inst_a}, headers=h_psi, timeout=30), 200, "campaña grupal")
    m = exigir(requests.post(f"{API}/educativo/campanas/{camp['id']}/matricular-roster", json=[caro, dani], headers=h_psi, timeout=30), 200, "matrícula")
    rech = {x["persona_id"]: x["motivo"] for x in m["rechazados"]}
    comprobar("Caro rechazada por tenerla pendiente", caro in rech and "pendiente" in rech[caro].lower(), str(m["rechazados"]))
    comprobar("Dani sí se matricula", len(m["generados"]) == 1)
    e2 = exigir(requests.get(f"{API}/educativo/pruebas/{gad7}/elegibilidad", headers=h_psi, timeout=30), 200, "elegibilidad gad7")
    comprobar("Elegibilidad GAD-7: Caro y Dani 'pendiente'", {x["persona_id"]: x["motivo"] for x in e2["no_elegibles"]}.get(caro) == "pendiente"
              and {x["persona_id"]: x["motivo"] for x in e2["no_elegibles"]}.get(dani) == "pendiente")

    # ------------------------------------------------------------------
    print("\n7 · Estadísticas por salón e Inicio")
    camp_phq = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9, "nombre_grupo": f"{PREFIJO} PHQ9 3A {sello}", "institucion_id": inst_a}, headers=h_psi, timeout=30), 200, "campaña PHQ-9")
    m = exigir(requests.post(f"{API}/educativo/campanas/{camp_phq['id']}/matricular-roster", json=[dani], headers=h_psi, timeout=30), 200, "matrícula Dani")
    rendir(m["generados"][0]["token"])
    d = exigir(requests.get(f"{API}/educativo/dashboard/academico", params={"prueba_id": phq9, "seccion_id": seccion}, headers=h_psi, timeout=60), 200, "dashboard académico")
    nombres = " ".join(a.get("nombre_completo") or "" for a in d.get("alumnos", []))
    comprobar("El salón cuenta la campaña grupal (Dani)", "Dani" in nombres, nombres[:200])
    comprobar("…y NO la aplicación individual (Ana)", "Ana" not in nombres, nombres[:200])
    resumen = exigir(requests.get(f"{API}/educativo/inicio/resumen", headers=h_psi, timeout=30), 200, "inicio")
    comprobar("Inicio: campañas activas = solo las 2 grupales", resumen["campanas_activas"] == 2, str(resumen))

    # ------------------------------------------------------------------
    print("\n8 · Candados")
    comprobar("colegio -> 403", individual(dani, gad7, h=h_col).status_code == 403)
    comprobar("colegio no ve elegibilidad -> 403", requests.get(f"{API}/educativo/pruebas/{phq9}/elegibilidad", headers=h_col, timeout=30).status_code == 403)
    comprobar("Psicólogo de otro colegio -> 404", individual(dani, gad7, h=h_psib).status_code == 404)
    pasada = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    r = individual(dani, phq9 if False else gad7, fecha_fin=pasada)
    comprobar("Fecha de cierre pasada -> rechazada (4xx)", 400 <= r.status_code < 500 and r.status_code != 404, str(r.status_code))
    if interna:
        comprobar("Prueba interna (no visible para clientes) -> 404", individual(dani, interna).status_code == 404)

    total, pasan = len(_resultados), sum(_resultados)
    print(f"\n{pasan}/{total} comprobaciones pasan.")
    return 0 if pasan == total else 1


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    evals = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evals})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    usuarios = f"SELECT id FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%'"
    with motor.begin() as c:
        c.execute(text(f"DELETE FROM edu_casos_riesgo WHERE institucion_id IN ({insts})"))
        hijos = c.execute(text("""
            select tc.table_name, kcu.column_name from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu on kcu.constraint_name = tc.constraint_name
            join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name
            where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'edu_inscripciones'
              and tc.table_name <> 'edu_inscripciones'""")).all()
        c.execute(text(f"DELETE FROM edu_informe_versiones WHERE informe_id IN (SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscs}))"))
        for tabla, col in hijos:
            c.execute(text(f"DELETE FROM {tabla} WHERE {col} IN ({inscs})"))
        for q in [
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({evals})",
            f"DELETE FROM edu_evaluaciones WHERE institucion_id IN ({insts})",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM registro_cambios_persona WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE institucion_id IN ({insts})",
            f"DELETE FROM grados WHERE institucion_id IN ({insts})",
            f"DELETE FROM niveles_educativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN ({usuarios})",
            f"DELETE FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%'",
            f"DELETE FROM instituciones WHERE nombre LIKE '{PREFIJO}%'",
        ]:
            c.execute(text(q))
    print(f"Datos {PREFIJO} eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
    else:
        sys.exit(main(args.url))
