"""Verificación end-to-end — Política institucional de consentimientos:
Institucion.exigir_asentimiento_estudiante.

Cubre exactamente lo pedido:
  0. El nuevo PATCH /instituciones/{id}/politica-consentimientos está gateado
     a superadmin/admin (nunca psicologo), y admin solo para SU institución.
  1. Flag OFF (default de toda institución) — regresión exacta: matricular
     por roster con SOLO consentimiento de apoderado sigue funcionando,
     exactamente como antes de esta fase.
  2. Flag ON — matricular por roster sin consentimiento del propio
     estudiante queda RECHAZADO con el nuevo motivo; una vez registrado ese
     consentimiento, la matrícula sí procede.
  3. Flag ON — revocar el consentimiento del estudiante a mitad de examen
     (con el del apoderado todavía vigente) bloquea la reanudación
     (comenzar-test) con 403; renovarlo desbloquea la MISMA inscripción
     Pendiente (no crea una nueva).
  4. El flag se lee POR INSTITUCIÓN: la institución B, sin tocar su flag
     (queda en False), matricula exactamente igual que antes.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_politica_consentimiento_estudiante_e2e.py
    python tests/verificar_politica_consentimiento_estudiante_e2e.py --limpiar
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZPOLC"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, endpoint="", detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else "") + (f"   [{endpoint}]" if endpoint else ""))
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


def crear_colegio_con_admin_y_psicologo(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")

    correo_admin = f"{PREFIJO.lower()}.admin.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro admin {letra}", json={
        "email": correo_admin, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Admin {letra}",
        "rol": "admin", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro admin {letra}")
    tok_admin = exigir(login(correo_admin, "ClaveDePrueba123"), 200, f"Login admin {letra}")["access_token"]

    correo_psi = f"{PREFIJO.lower()}.psi.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro psi {letra}", json={
        "email": correo_psi, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo {letra}",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro psi {letra}")
    tok_psi = exigir(login(correo_psi, "ClaveDePrueba123"), 200, f"Login psi {letra}")["access_token"]

    return inst["id"], {"Authorization": f"Bearer {tok_admin}"}, {"Authorization": f"Bearer {tok_psi}"}


def crear_persona(h, institucion_id, sello, tag):
    return exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": institucion_id, "nombres": f"{PREFIJO} {tag}", "apellidos": "Prueba",
        "documento_identidad": f"{sello}{tag}", "fecha_nacimiento": "2011-04-10", "genero": "Femenino"},
        headers=h, timeout=30), 200, f"Crear persona {tag}")["id"]


def otorgar_consentimiento_apoderado(h, persona_id, institucion_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": institucion_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"},
        headers=h, timeout=30), 200, "Consentimiento apoderado")


def otorgar_consentimiento_estudiante(h, persona_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento/asentimiento", json={},
        headers=h, timeout=30), 200, "Consentimiento estudiante")


def revocar_consentimiento_estudiante(h, persona_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento/asentimiento/revocar",
        headers=h, timeout=30), 200, "Revocar consentimiento estudiante")


def crear_campana(h, institucion_id, prueba_id, sello, tag):
    return exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {tag} {sello}", "institucion_id": institucion_id},
        headers=h, timeout=30), 200, f"Campaña {tag}")


def comenzar_test(token):
    return requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "x", "edad": 1, "sexo": "Masculino", "poblacion": "Universitario",
        "acepta_terminos": True}, timeout=30)


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]

    print("\n0 · Montaje: dos instituciones (A y B), cada una con admin y psicólogo")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_a, h_admin_a, h_psi_a = crear_colegio_con_admin_y_psicologo(h_super, "A", sello)
    inst_b, h_admin_b, h_psi_b = crear_colegio_con_admin_y_psicologo(h_super, "B", sello)

    # ==================================================================
    print("\n1 · Permisos del nuevo PATCH /instituciones/{id}/politica-consentimientos")
    r_psi = requests.patch(f"{API}/instituciones/{inst_a}/politica-consentimientos",
                           json={"exigir_asentimiento_estudiante": True}, headers=h_psi_a, timeout=30)
    comprobar("[1] 'psicologo' de A -> 403 (no puede cambiar la política)", r_psi.status_code == 403)

    r_cruzado = requests.patch(f"{API}/instituciones/{inst_a}/politica-consentimientos",
                               json={"exigir_asentimiento_estudiante": True}, headers=h_admin_b, timeout=30)
    comprobar("[1] 'admin' de B -> 403 (no puede cambiar la política de A)", r_cruzado.status_code == 403)

    r_activar_a = requests.patch(f"{API}/instituciones/{inst_a}/politica-consentimientos",
                                 json={"exigir_asentimiento_estudiante": True}, headers=h_admin_a, timeout=30)
    comprobar("[1] 'admin' de A -> 200 (activa el flag de SU institución)", r_activar_a.status_code == 200,
              detalle=r_activar_a.text[:300])
    comprobar("[1] La respuesta refleja exigir_asentimiento_estudiante=True",
              r_activar_a.json().get("exigir_asentimiento_estudiante") is True)

    flag_b = sql_uno("select exigir_asentimiento_estudiante from instituciones where id=:i", i=inst_b)[0]
    comprobar("[1] B sigue en False — activar A nunca tocó B", flag_b is False)

    # ==================================================================
    print("\n2 · Flag ON en A — matricular sin consentimiento del estudiante queda RECHAZADO")
    persona_a = crear_persona(h_admin_a, inst_a, sello, "P1")
    otorgar_consentimiento_apoderado(h_admin_a, persona_a, inst_a)

    campana_a = crear_campana(h_admin_a, inst_a, phq9_id, sello, "A")
    r_matricula_1 = exigir(requests.post(f"{API}/educativo/campanas/{campana_a['id']}/matricular-roster",
                                         json=[persona_a], headers=h_admin_a, timeout=30), 200,
                           "Matrícula sin consentimiento estudiante")
    comprobar("[2] La matrícula fue RECHAZADA (0 generados, 1 rechazado)",
              len(r_matricula_1["generados"]) == 0 and len(r_matricula_1["rechazados"]) == 1,
              detalle=str(r_matricula_1))
    comprobar("[2] El motivo es el nuevo mensaje de consentimiento del estudiante",
              r_matricula_1["rechazados"][0]["motivo"] == "Sin asentimiento del propio estudiante vigente.",
              detalle=str(r_matricula_1["rechazados"]))

    print("\n2b · Tras registrar el consentimiento del estudiante, la matrícula sí procede")
    otorgar_consentimiento_estudiante(h_admin_a, persona_a)
    r_matricula_2 = exigir(requests.post(f"{API}/educativo/campanas/{campana_a['id']}/matricular-roster",
                                         json=[persona_a], headers=h_admin_a, timeout=30), 200,
                           "Matrícula con ambos consentimientos")
    comprobar("[2b] Ahora la matrícula procede (1 generado, 0 rechazados)",
              len(r_matricula_2["generados"]) == 1 and len(r_matricula_2["rechazados"]) == 0,
              detalle=str(r_matricula_2))
    token_a = r_matricula_2["generados"][0]["token"]

    # ==================================================================
    print("\n3 · Flag ON en A — revocar el consentimiento del estudiante bloquea la reanudación")
    r_comenzar_1 = comenzar_test(token_a)
    comprobar("[3] comenzar-test funciona con ambos consentimientos vigentes (200)",
              r_comenzar_1.status_code == 200, detalle=r_comenzar_1.text[:300])

    revocar_consentimiento_estudiante(h_admin_a, persona_a)
    r_comenzar_2 = comenzar_test(token_a)
    comprobar("[3] Reanudar (comenzar-test) tras revocar SOLO el consentimiento del estudiante -> 403",
              r_comenzar_2.status_code == 403, detalle=r_comenzar_2.text[:300])

    apoderado_vigente = sql_uno(
        "select estado from consentimientos_informados where persona_id=:p and tipo_consentimiento='apoderado' "
        "order by fecha_otorgamiento desc limit 1", p=persona_a)[0]
    comprobar("[3] El consentimiento del APODERADO sigue vigente (no se tocó)", apoderado_vigente == "vigente")

    print("\n3b · Renovar el consentimiento del estudiante desbloquea la MISMA inscripción Pendiente")
    otorgar_consentimiento_estudiante(h_admin_a, persona_a)
    r_comenzar_3 = comenzar_test(token_a)
    comprobar("[3b] Tras renovar, comenzar-test vuelve a funcionar (200)",
              r_comenzar_3.status_code == 200, detalle=r_comenzar_3.text[:300])

    filas_inscripcion = sql_uno("select count(*) from edu_inscripciones where token=:t", t=token_a)[0]
    comprobar("[3b] Sigue existiendo UNA sola Inscripcion para este token (nunca se creó una nueva)",
              filas_inscripcion == 1)

    # ==================================================================
    print("\n4 · Institución B (flag OFF, sin tocar) — regresión exacta: sin consentimiento de estudiante, igual matricula")
    persona_b = crear_persona(h_admin_b, inst_b, sello, "P2")
    otorgar_consentimiento_apoderado(h_admin_b, persona_b, inst_b)
    campana_b = crear_campana(h_admin_b, inst_b, phq9_id, sello, "B")
    r_matricula_b = exigir(requests.post(f"{API}/educativo/campanas/{campana_b['id']}/matricular-roster",
                                         json=[persona_b], headers=h_admin_b, timeout=30), 200,
                           "Matrícula en B (flag OFF)")
    comprobar("[4] En B (flag OFF), SOLO el consentimiento del apoderado ya basta (1 generado, 0 rechazados)",
              len(r_matricula_b["generados"]) == 1 and len(r_matricula_b["rechazados"]) == 0,
              detalle=str(r_matricula_b))

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 0 if not fallos else 1


def limpiar():
    with MOTOR.begin() as c:
        c.execute(text(f"""
            delete from edu_inscripciones where evaluacion_id in (
                select id from edu_evaluaciones where nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"delete from edu_evaluaciones where nombre_grupo like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from consentimientos_informados where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from personas where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
        c.execute(text(f"delete from auth_usuarios where email like '{PREFIJO.lower()}%'"))
        c.execute(text(f"delete from instituciones where nombre like '{PREFIJO}%'"))
    print(f"🧹 Datos de prueba {PREFIJO} eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    args = parser.parse_args()

    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    if args.limpiar:
        limpiar()
        sys.exit(0)

    sys.exit(main(args.url))
