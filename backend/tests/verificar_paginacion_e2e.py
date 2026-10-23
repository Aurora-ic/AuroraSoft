"""Verificación end-to-end — paginación real de los 3 listados que antes
devolvían todo sin tope (ver docs/gaps-pendientes.md, "Sin paginación
real"): padrón de personas, campañas y documentos institucionales.

  1   GET /admin/personas/{institucion_id}: 150 personas reales -> total=150,
      3 páginas de 50 sin solape ni huecos entre ellas, default sin
      skip/limit también pagina (no "sin límite").
  2   GET /educativo/campanas/: mismo contrato con un conjunto más chico
      (5 campañas reales, prueba PHQ-9 pública).
  3   GET /documentos/: mismo contrato, y además confirma que el
      COUNT/LIMIT se aplica DESPUÉS del filtro de `nivel_visibilidad` — el
      rol 'colegio' ve un total menor al real porque algunos documentos son
      'confidencial_clinico'.
  4   Los 3 endpoints: skip negativo y limit>200 -> 422 (la cota real evita
      recrear el problema original con limit=999999).

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_paginacion_e2e
    python -m tests.verificar_paginacion_e2e --limpiar
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

PREFIJO = "ZZPAGIN"
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


def pedir(metodo, url, contexto="", **kw):
    for _ in range(8):
        r = metodo(url, timeout=60, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


def registrar_y_loguear(h_super, correo, nombre, rol, institucion_id):
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {correo}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": nombre,
        "rol": rol, "institucion_id": institucion_id}, headers=h_super), 200, f"Registro {correo}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {correo}")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def sql_uno(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchone()


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    inst_id = inst["id"]
    h_admin = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com",
                                   f"{PREFIJO} Admin", "admin", inst_id)
    h_colegio = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com",
                                     f"{PREFIJO} Colegio", "colegio", inst_id)

    # ==================================================================
    print("\n1 · PERSONAS — 150 reales, paginadas de a 50")
    ids_creados = []
    for i in range(150):
        p = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_id, "tipo_perfil": "estudiante",
            "nombres": f"{PREFIJO}{sello}", "apellidos": f"P{i:04d}",
        }, headers=h_admin, timeout=30), 200, f"crear persona {i}")
        ids_creados.append(p["id"])

    r1 = exigir(requests.get(f"{API}/admin/personas/{inst_id}?limit=50&skip=0",
                headers=h_admin, timeout=30), 200, "página 1 personas")
    r2 = exigir(requests.get(f"{API}/admin/personas/{inst_id}?limit=50&skip=50",
                headers=h_admin, timeout=30), 200, "página 2 personas")
    r3 = exigir(requests.get(f"{API}/admin/personas/{inst_id}?limit=50&skip=100",
                headers=h_admin, timeout=30), 200, "página 3 personas")

    comprobar("[1] Las 3 páginas reportan el mismo total=150",
              r1["total"] == 150 and r2["total"] == 150 and r3["total"] == 150,
              f"{r1['total']}/{r2['total']}/{r3['total']}")
    comprobar("[1] Cada página trae exactamente 50 items",
              len(r1["items"]) == 50 and len(r2["items"]) == 50 and len(r3["items"]) == 50,
              f"{len(r1['items'])}/{len(r2['items'])}/{len(r3['items'])}")

    ids_pag1 = {it["id"] for it in r1["items"]}
    ids_pag2 = {it["id"] for it in r2["items"]}
    ids_pag3 = {it["id"] for it in r3["items"]}
    comprobar("[1] Las 3 páginas no se solapan entre sí",
              not (ids_pag1 & ids_pag2) and not (ids_pag1 & ids_pag3) and not (ids_pag2 & ids_pag3))
    comprobar("[1] Las 3 páginas juntas cubren EXACTAMENTE las 150 personas creadas (sin huecos ni duplicados)",
              (ids_pag1 | ids_pag2 | ids_pag3) >= set(ids_creados[:150]) and
              len(ids_pag1 | ids_pag2 | ids_pag3) == 150)

    r_default = exigir(requests.get(f"{API}/admin/personas/{inst_id}",
                        headers=h_admin, timeout=30), 200, "personas sin skip/limit")
    comprobar("[1] Sin pasar skip/limit, el default sigue limitando a 50 (no 'sin límite')",
              r_default["total"] == 150 and len(r_default["items"]) == 50,
              f"total={r_default['total']} items={len(r_default['items'])}")

    r_tope = exigir(requests.get(f"{API}/admin/personas/{inst_id}?limit=200",
                     headers=h_admin, timeout=30), 200, "personas limit=200")
    comprobar("[1] limit=200 (el tope máximo) devuelve las 150 personas completas",
              len(r_tope["items"]) == 150, f"{len(r_tope['items'])}")

    r_skip_neg = requests.get(f"{API}/admin/personas/{inst_id}?skip=-1", headers=h_admin, timeout=30)
    comprobar("[1] skip=-1 -> 422", r_skip_neg.status_code == 422, str(r_skip_neg.status_code))
    r_limit_alto = requests.get(f"{API}/admin/personas/{inst_id}?limit=201", headers=h_admin, timeout=30)
    comprobar("[1] limit=201 (por encima del tope de 200) -> 422", r_limit_alto.status_code == 422, str(r_limit_alto.status_code))
    r_limit_cero = requests.get(f"{API}/admin/personas/{inst_id}?limit=0", headers=h_admin, timeout=30)
    comprobar("[1] limit=0 -> 422", r_limit_cero.status_code == 422, str(r_limit_cero.status_code))

    # ==================================================================
    print("\n2 · CAMPAÑAS — 5 reales, paginadas de a 2")
    fila_phq9 = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")
    comprobar("[montaje] Existe la prueba pública PHQ-9 (seed_phq9 ya corrido)", fila_phq9 is not None)
    prueba_id = fila_phq9[0]

    for i in range(5):
        exigir(requests.post(f"{API}/educativo/campanas/", json={
            "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}-{i}",
            "institucion_id": inst_id,
        }, headers=h_admin, timeout=30), 200, f"crear campaña {i}")

    rc1 = exigir(requests.get(f"{API}/educativo/campanas/?institucion_id={inst_id}&limit=2&skip=0",
                 headers=h_admin, timeout=30), 200, "página 1 campañas")
    rc3 = exigir(requests.get(f"{API}/educativo/campanas/?institucion_id={inst_id}&limit=2&skip=4",
                 headers=h_admin, timeout=30), 200, "página 3 campañas")
    comprobar("[2] total=5 y la página 1 trae 2 items", rc1["total"] == 5 and len(rc1["items"]) == 2,
              f"total={rc1['total']} items={len(rc1['items'])}")
    comprobar("[2] La última página parcial (skip=4) trae exactamente 1 item (5 - 4)",
              len(rc3["items"]) == 1, f"{len(rc3['items'])}")

    rc_skip_neg = requests.get(f"{API}/educativo/campanas/?institucion_id={inst_id}&skip=-1", headers=h_admin, timeout=30)
    comprobar("[2] skip=-1 -> 422", rc_skip_neg.status_code == 422, str(rc_skip_neg.status_code))
    rc_limit_alto = requests.get(f"{API}/educativo/campanas/?institucion_id={inst_id}&limit=201", headers=h_admin, timeout=30)
    comprobar("[2] limit=201 -> 422", rc_limit_alto.status_code == 422, str(rc_limit_alto.status_code))

    # ==================================================================
    print("\n3 · DOCUMENTOS — 5 'confidencial_clinico' + 1 'compartible_colegio', paginados de a 2")
    clave_tipo = f"{PREFIJO.lower()}_tipo_{sello}"
    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": f"{PREFIJO} Tipo",
        "alcances_permitidos": "institucion",
        "visibilidades_permitidas": "confidencial_clinico, compartible_colegio",
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento")
    tipo_id = tipo["id"]
    plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_id, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla",
    }, headers=h_super, timeout=30), 200, "crear plantilla")
    plantilla_id = plantilla["id"]

    for i in range(5):
        exigir(requests.post(f"{API}/documentos/", json={
            "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_id,
            "alcance": "institucion", "nivel_visibilidad": "confidencial_clinico",
            "titulo": f"{PREFIJO} Doc confidencial {sello}-{i}",
        }, headers=h_admin, timeout=30), 200, f"crear documento confidencial {i}")
    exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_id,
        "alcance": "institucion", "nivel_visibilidad": "compartible_colegio",
        "titulo": f"{PREFIJO} Doc compartible {sello}",
    }, headers=h_admin, timeout=30), 200, "crear documento compartible")

    rd_admin = exigir(requests.get(f"{API}/documentos/?institucion_id={inst_id}&limit=2&skip=0",
                       headers=h_admin, timeout=30), 200, "página 1 documentos (admin)")
    comprobar("[3] Para 'admin' (ve todo), total=6 (5 confidenciales + 1 compartible)",
              rd_admin["total"] == 6, f"total={rd_admin['total']}")
    comprobar("[3] La página 1 (limit=2) trae 2 items", len(rd_admin["items"]) == 2, f"{len(rd_admin['items'])}")

    rd_colegio = exigir(requests.get(f"{API}/documentos/?institucion_id={inst_id}&limit=2&skip=0",
                         headers=h_colegio, timeout=30), 200, "página 1 documentos (colegio)")
    comprobar("[3] Para 'colegio', total=1 (el COUNT se aplica DESPUÉS del filtro nivel_visibilidad, no antes)",
              rd_colegio["total"] == 1, f"total={rd_colegio['total']}")
    comprobar("[3] Y ese único documento visible es el 'compartible_colegio', nunca uno confidencial",
              len(rd_colegio["items"]) == 1 and rd_colegio["items"][0]["nivel_visibilidad"] == "compartible_colegio",
              str(rd_colegio["items"]))

    rd_skip_neg = requests.get(f"{API}/documentos/?institucion_id={inst_id}&skip=-1", headers=h_admin, timeout=30)
    comprobar("[3] skip=-1 -> 422", rd_skip_neg.status_code == 422, str(rd_skip_neg.status_code))
    rd_limit_alto = requests.get(f"{API}/documentos/?institucion_id={inst_id}&limit=201", headers=h_admin, timeout=30)
    comprobar("[3] limit=201 -> 422", rd_limit_alto.status_code == 422, str(rd_limit_alto.status_code))

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
            delete from documentos_institucionales_estudiantes where documento_institucional_id in (
                select id from documentos_institucionales where titulo like '{PREFIJO}%')"""))
        c.execute(text(f"delete from documentos_institucionales where titulo like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from documentos_plantilla_secciones where plantilla_documento_id in (
                select id from documentos_plantillas where nombre like '{PREFIJO}%')"""))
        c.execute(text(f"delete from documentos_plantillas where nombre like '{PREFIJO}%'"))
        c.execute(text(f"delete from documentos_tipos where clave like '{PREFIJO.lower()}%'"))
        c.execute(text(f"""
            delete from edu_inscripciones where evaluacion_id in (
                select id from edu_evaluaciones where nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"delete from edu_evaluaciones where nombre_grupo like '{PREFIJO}%'"))
        c.execute(text(f"delete from personas where apellidos like 'P0%' and nombres like '{PREFIJO}%'"))
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
