"""E2E — interruptor por campaña "los estudiantes ven su informe"
(`Evaluacion.alumno_ve_informe`, sesión 2026-11-01).

Regla (decisión del usuario): el alumno ve su resultado — resumen por
dimensión en pantalla y el PDF — SOLO si la campaña tiene el interruptor
encendido, y entonces lo ve aunque haya alerta clínica, sin revisión previa.
El psicólogo recibe siempre todos los resultados. Contra uvicorn real en :8010:

  1  Campaña nueva sin el campo -> apagado
  2  Apagado + sin alerta: /finalizar devuelve [], /estado-resultados sin
     resultados y con el mensaje de revisión, PDF del alumno 403; el
     psicólogo descarga el PDF igual
  3  Encendido + CON alerta (retenido para el staff): /finalizar devuelve
     los diagnósticos, /estado-resultados trae dimensión+nivel, PDF 200
  4  Encender/apagar con PATCH tiene efecto inmediato sobre quien ya terminó
  5  Con la campaña CERRADA el interruptor se puede cambiar; el nombre no
  6  Candados: `colegio` y otro colegio no pueden cambiarlo; un null
     explícito no rompe nada

    uvicorn main:app --port 8010   (SMTP apagado, captcha no obligatorio)
    python -m tests.verificar_visibilidad_alumno_e2e
    python -m tests.verificar_visibilidad_alumno_e2e --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZVISAL"
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


def registrar_y_loguear(h_super, correo, rol, institucion_id):
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {correo}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} {rol}",
        "rol": rol, "institucion_id": institucion_id}, headers=h_super), 200, f"Registro {correo}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {correo}")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


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
        phq9 = c.execute(text(
            "select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")).scalar()
    if not phq9:
        print("!! Falta el catálogo PHQ-9 (python -m seeds.seed_phq9).")
        return 1
    h_super = {"Authorization": f"Bearer {exigir(login(correo_super, 'ClaveDePrueba123'), 200, 'login super')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", "psicologo", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", "psicologo", inst_b)
    h_colegio = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com", "colegio", inst_a)

    def persona(etiqueta):
        pid = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_a, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
            "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=h_psi, timeout=30), 200, f"persona {etiqueta}")["id"]
        exigir(requests.post(f"{API}/admin/personas/{pid}/consentimiento", json={
            "persona_id": pid, "institucion_id": inst_a, "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
            headers=h_psi, timeout=30), 200, f"consentimiento {etiqueta}")
        return pid

    def campana(nombre, **extra):
        return exigir(requests.post(f"{API}/educativo/campanas/", json={
            "prueba_id": phq9, "nombre_grupo": f"{PREFIJO} {nombre} {sello}", "institucion_id": inst_a, **extra},
            headers=h_psi, timeout=30), 200, f"campaña {nombre}")

    def matricular(campana_id, persona_id):
        m = exigir(requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                                 json=[persona_id], headers=h_psi, timeout=30), 200, "matrícula")
        return m["generados"][0]["token"]

    def rendir(token, ultima_opcion):
        """Responde todo con la primera opción (puntaje mínimo) o la última (máximo)."""
        exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
            "nombre_completo": "Alumno", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
            "acepta_terminos": True}, timeout=30), 200, "comenzar")
        preguntas = exigir(requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30), 200, "preguntas")
        respuestas = [{"pregunta_id": p["id"], "opcion_id": p["opciones"][-1 if ultima_opcion else 0]["id"]} for p in preguntas]
        exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar")
        return exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "finalizar")

    def estado(token):
        return exigir(requests.get(f"{API}/educativo/examen/{token}/estado-resultados", timeout=30), 200, "estado")

    def pdf_alumno(token):
        return requests.get(f"{API}/educativo/examen/{token}/informe-pdf", timeout=60)

    def inscripcion(token):
        with motor.connect() as c:
            return c.execute(text("select id, resultado_visible_alumno, informe_liberado from edu_inscripciones where token=:t"),
                             {"t": token}).fetchone()

    # ------------------------------------------------------------------
    print("\n1 · Campaña nueva: apagado por defecto")
    c_apagada = campana("Apagada")
    comprobar("POST sin el campo -> alumno_ve_informe False", c_apagada.get("alumno_ve_informe") is False, str(c_apagada))

    # ------------------------------------------------------------------
    print("\n2 · Apagado + sin alerta")
    tok_1 = matricular(c_apagada["id"], persona("SinAlerta"))
    devueltos = rendir(tok_1, ultima_opcion=False)
    fila_1 = inscripcion(tok_1)
    comprobar("El caso no tiene alerta (resultado_visible_alumno True)", fila_1[1] is True, str(fila_1))
    comprobar("/finalizar no devuelve diagnósticos al alumno", devueltos == [], str(devueltos)[:200])
    e = estado(tok_1)
    comprobar("/estado-resultados: alumno_puede_ver_informe False y sin resultados",
              e["alumno_puede_ver_informe"] is False and e["resultados"] == [], str(e))
    comprobar("Mensaje de revisión (no revela nada)", "revisad" in e["mensaje"].lower(), e["mensaje"])
    comprobar("PDF del alumno -> 403", pdf_alumno(tok_1).status_code == 403)
    r_staff = requests.get(f"{API}/educativo/inscripciones/{fila_1[0]}/informe-pdf", headers=h_psi, timeout=60)
    comprobar("El psicólogo descarga el PDF igual (200, %PDF)", r_staff.status_code == 200 and r_staff.content[:4] == b"%PDF",
              f"status {r_staff.status_code}")

    # ------------------------------------------------------------------
    print("\n3 · Encendido + CON alerta")
    c_encendida = campana("Encendida", alumno_ve_informe=True)
    comprobar("POST con alumno_ve_informe True -> queda encendido", c_encendida.get("alumno_ve_informe") is True)
    tok_2 = matricular(c_encendida["id"], persona("ConAlerta"))
    devueltos = rendir(tok_2, ultima_opcion=True)
    fila_2 = inscripcion(tok_2)
    comprobar("El caso SÍ tiene alerta (retenido para el staff)", fila_2[1] is False and fila_2[2] is False, str(fila_2))
    comprobar("/finalizar devuelve los diagnósticos al alumno", len(devueltos) > 0)
    e = estado(tok_2)
    comprobar("/estado-resultados: alumno_puede_ver_informe True", e["alumno_puede_ver_informe"] is True, str(e)[:300])
    comprobar("resultados = solo dimensión y nivel, uno por diagnóstico",
              len(e["resultados"]) == len(devueltos) and all(set(x) == {"dimension", "nivel"} for x in e["resultados"]),
              str(e["resultados"])[:300])
    r = pdf_alumno(tok_2)
    comprobar("PDF del alumno -> 200 aunque haya alerta", r.status_code == 200 and r.content[:4] == b"%PDF", f"status {r.status_code}")

    # ------------------------------------------------------------------
    print("\n4 · Encender/apagar con efecto inmediato")
    url_a = f"{API}/educativo/campanas/{c_apagada['id']}"
    exigir(requests.patch(url_a, json={"alumno_ve_informe": True}, headers=h_psi, timeout=30), 200, "encender")
    comprobar("Tras encender: el alumno que ya terminó descarga su PDF", pdf_alumno(tok_1).status_code == 200)
    comprobar("Tras encender: ve su resumen", len(estado(tok_1)["resultados"]) > 0)
    exigir(requests.patch(url_a, json={"alumno_ve_informe": False}, headers=h_psi, timeout=30), 200, "apagar")
    comprobar("Tras apagar: PDF -> 403 otra vez", pdf_alumno(tok_1).status_code == 403)

    # ------------------------------------------------------------------
    print("\n5 · Campaña cerrada")
    url_e = f"{API}/educativo/campanas/{c_encendida['id']}"
    exigir(requests.post(f"{url_e}/cerrar", json={}, headers=h_psi, timeout=30), 200, "cerrar")
    r = requests.patch(url_e, json={"alumno_ve_informe": False}, headers=h_psi, timeout=30)
    comprobar("Cerrada: el interruptor sí se puede cambiar (200)", r.status_code == 200 and r.json()["alumno_ve_informe"] is False,
              f"{r.status_code} {r.text[:200]}")
    comprobar("Cerrada y apagada: PDF -> 403", pdf_alumno(tok_2).status_code == 403)
    r = requests.patch(url_e, json={"nombre_grupo": f"{PREFIJO} renombrada"}, headers=h_psi, timeout=30)
    comprobar("Cerrada: el nombre sigue sin poder editarse (409)", r.status_code == 409, str(r.status_code))
    r = requests.patch(url_e, json={"nombre_grupo": f"{PREFIJO} x", "alumno_ve_informe": True}, headers=h_psi, timeout=30)
    comprobar("Cerrada: nombre + interruptor juntos -> 409 y no cambia nada",
              r.status_code == 409 and pdf_alumno(tok_2).status_code == 403, str(r.status_code))

    # ------------------------------------------------------------------
    print("\n6 · Candados")
    r = requests.patch(url_a, json={"alumno_ve_informe": True}, headers=h_colegio, timeout=30)
    comprobar("`colegio` no puede cambiarlo (403)", r.status_code == 403, str(r.status_code))
    r = requests.patch(url_a, json={"alumno_ve_informe": True}, headers=h_psi_b, timeout=30)
    comprobar("Otro colegio no puede cambiarlo (403/404)", r.status_code in (403, 404), str(r.status_code))
    comprobar("…y sigue apagado", pdf_alumno(tok_1).status_code == 403)
    r = requests.patch(url_a, json={"nombre_grupo": f"{PREFIJO} Apagada2 {sello}", "alumno_ve_informe": None}, headers=h_psi, timeout=30)
    comprobar("null explícito junto a otro campo: 200 y el interruptor no cambia",
              r.status_code == 200 and r.json()["alumno_ve_informe"] is False, f"{r.status_code} {r.text[:200]}")
    r = requests.patch(url_a, json={"alumno_ve_informe": None}, headers=h_psi, timeout=30)
    comprobar("null explícito solo: 200 sin cambios", r.status_code == 200 and r.json()["alumno_ve_informe"] is False,
              f"{r.status_code} {r.text[:200]}")

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
        # Todo lo que cuelga de las inscripciones, descubierto por FK.
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
            f"DELETE FROM registro_cambios_persona WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
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
