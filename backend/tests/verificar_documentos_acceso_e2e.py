"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 6:
lectura/descarga gobernada por nivel_visibilidad.

  1   Aislamiento entre instituciones en detalle/secciones/versiones/descarga
  2   'colegio' denegado en 'confidencial_clinico', permitido en
      'compartible_colegio' — en listado, detalle y descarga
  3   Los bytes descargados coinciden con el checksum almacenado
  4   Independencia respecto a la entrada-puente del expediente: 'colegio'
      con acceso al documento (compartible_colegio) SIGUE sin poder leer
      la entrada-puente del estudiante sin una AutorizacionAccesoColegio
      aparte — nivel_visibilidad del documento nunca contagia al expediente

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_acceso_e2e
    python -m tests.verificar_documentos_acceso_e2e --limpiar
"""

import argparse
import hashlib
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

PREFIJO = "ZZDOCACC"
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
        r = metodo(url, timeout=30, **kw)
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
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]
    h_psi_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com", f"{PREFIJO} PsiA", "psicologo", inst_a)
    h_admin_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admina.{sello}@ejemplo.com", f"{PREFIJO} AdminA", "admin", inst_a)
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)

    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_tipo_{sello}", "nombre": f"{PREFIJO} Tipo",
        "alcances_permitidos": "ninguno, personas_especificas", "visibilidades_permitidas": "confidencial_clinico, compartible_colegio",
    }, headers=h_super, timeout=30), 200, "crear tipo")

    plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo["id"], "nombre": f"{PREFIJO} Plantilla",
    }, headers=h_super, timeout=30), 200, "crear plantilla")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "texto_libre", "titulo": "Cuerpo",
    }, headers=h_super, timeout=30), 200, "crear sección")

    doc_confidencial = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Confidencial", "nivel_visibilidad": "confidencial_clinico",
    }, headers=h_psi_a, timeout=30), 200, "crear doc confidencial")
    exigir(requests.post(f"{API}/documentos/{doc_confidencial['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "v1 confidencial")

    doc_compartible = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Compartible", "nivel_visibilidad": "compartible_colegio",
    }, headers=h_psi_a, timeout=30), 200, "crear doc compartible")
    exigir(requests.post(f"{API}/documentos/{doc_compartible['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "v1 compartible")

    print("\n1 · Aislamiento entre instituciones")
    for etiqueta, url in [
        ("detalle", f"{API}/documentos/{doc_confidencial['id']}"),
        ("secciones", f"{API}/documentos/{doc_confidencial['id']}/secciones"),
        ("versiones", f"{API}/documentos/{doc_confidencial['id']}/versiones"),
        ("descarga", f"{API}/documentos/{doc_confidencial['id']}/versiones/1/descargar"),
    ]:
        r = requests.get(url, headers=h_psi_b, timeout=30)
        comprobar(f"[1] B no accede a {etiqueta} de un documento de A (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/", params={"institucion_id": inst_a}, headers=h_psi_b, timeout=30)
    comprobar("[1] B no puede listar documentos de A (403)", r.status_code == 403, f"status {r.status_code}")

    print("\n2 · 'colegio' — confidencial_clinico denegado, compartible_colegio permitido")
    r = requests.get(f"{API}/documentos/{doc_confidencial['id']}", headers=h_colegio_a, timeout=30)
    comprobar("[2] 'colegio' NO ve el detalle de un documento confidencial (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/documentos/{doc_confidencial['id']}/versiones/1/descargar", headers=h_colegio_a, timeout=30)
    comprobar("[2] 'colegio' NO puede descargar un documento confidencial (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/{doc_compartible['id']}", headers=h_colegio_a, timeout=30)
    comprobar("[2] 'colegio' SÍ ve el detalle de un documento compartible_colegio", r.status_code == 200, f"status {r.status_code}")
    r = requests.get(f"{API}/documentos/{doc_compartible['id']}/versiones/1/descargar", headers=h_colegio_a, timeout=30)
    comprobar("[2] 'colegio' SÍ puede descargar el documento compartible_colegio", r.status_code == 200, f"status {r.status_code}")

    listado_colegio = exigir(requests.get(f"{API}/documentos/", params={"institucion_id": inst_a}, headers=h_colegio_a, timeout=30), 200, "listar como colegio")
    ids_listado_colegio = {d["id"] for d in listado_colegio}
    comprobar("[2] El listado de 'colegio' incluye el compartible_colegio", doc_compartible["id"] in ids_listado_colegio)
    comprobar("[2] El listado de 'colegio' NO incluye el confidencial_clinico (filtrado, no bloqueado entero)",
               doc_confidencial["id"] not in ids_listado_colegio)

    listado_admin = exigir(requests.get(f"{API}/documentos/", params={"institucion_id": inst_a}, headers=h_admin_a, timeout=30), 200, "listar como admin")
    ids_listado_admin = {d["id"] for d in listado_admin}
    comprobar("[2] admin de la misma institución ve AMBOS documentos (sin ACL por documento)",
               {doc_confidencial["id"], doc_compartible["id"]} <= ids_listado_admin)

    print("\n3 · Bytes descargados == checksum almacenado")
    r = requests.get(f"{API}/documentos/{doc_confidencial['id']}/versiones/1/descargar", headers=h_psi_a, timeout=30)
    if r.status_code != 200:
        print(f"\n!! descargar confidencial: esperaba 200, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    checksum_real = hashlib.sha256(r.content).hexdigest()
    checksum_bd = sql_uno(
        "SELECT checksum_sha256 FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_confidencial["id"],
    ).checksum_sha256
    comprobar("[3] El checksum del PDF descargado coincide con el almacenado", checksum_real == checksum_bd)
    comprobar("[3] Content-Disposition trae el nombre de archivo", "attachment" in r.headers.get("content-disposition", ""))

    print("\n4 · Independencia respecto a la entrada-puente del expediente")
    alumno = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h_psi_a, timeout=30), 200, "crear persona")["id"]
    doc_compartible_con_alumno = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Compartible con alumno",
        "nivel_visibilidad": "compartible_colegio", "personas_ids": [alumno],
    }, headers=h_psi_a, timeout=30), 200, "crear doc compartible con alumno")
    exigir(requests.post(f"{API}/documentos/{doc_compartible_con_alumno['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "v1 compartible con alumno")

    r = requests.get(f"{API}/documentos/{doc_compartible_con_alumno['id']}", headers=h_colegio_a, timeout=30)
    comprobar("[4] 'colegio' SÍ accede al documento (es compartible_colegio)", r.status_code == 200, f"status {r.status_code}")

    entrada_id = sql_uno(
        "SELECT id FROM expediente_entradas WHERE tipo_entrada='documento_institucional' AND documento_institucional_id=:d",
        d=doc_compartible_con_alumno["id"],
    ).id
    r = requests.get(f"{API}/admin/personas/expediente/{entrada_id}", headers=h_colegio_a, timeout=30)
    comprobar("[4] Pero 'colegio' SIGUE sin poder leer la entrada-puente del expediente sin AutorizacionAccesoColegio "
              "(nivel_visibilidad del documento nunca contagia la regla del expediente)",
              r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — ACCESO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
    plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
    documentos = f"SELECT id FROM documentos_institucionales WHERE institucion_id IN ({insts})"
    entradas = f"SELECT id FROM expediente_entradas WHERE documento_institucional_id IN ({documentos})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM registro_lecturas_expediente WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM expediente_entradas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_registro_lecturas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_correlativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%')",
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
