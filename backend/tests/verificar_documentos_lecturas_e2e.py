"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 7:
auditoría de lectura (documentos_registro_lecturas).

  1   Las vistas de solo listado/metadata (listar, detalle, listar versiones)
      NUNCA generan una fila de auditoría
  2   GET .../secciones (contenido real del borrador) SÍ genera una fila,
      con tipo_acceso='contenido', sin numero_version_leida, rol/ip correctos
  3   GET .../versiones/{n}/descargar (PDF) SÍ genera una fila, con
      tipo_acceso='descarga_pdf' y numero_version_leida correcto
  4   Una lectura de 'colegio' sobre un documento compartible_colegio marca
      acceso_via_visibilidad_colegio=True; la misma lectura por admin/
      psicologo la deja en False
  5   nivel_visibilidad SIGUE sin afectar la confidencialidad de la
      entrada-puente del expediente: 'colegio' pudo leer el contenido del
      documento (auditado aquí) pero sigue sin poder leer la entrada-puente
      del estudiante sin una AutorizacionAccesoColegio aparte

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_lecturas_e2e
    python -m tests.verificar_documentos_lecturas_e2e --limpiar
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

PREFIJO = "ZZDOCLEC"
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


def sql_todos(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchall()


def contar_lecturas(documento_id):
    return sql_uno(
        "SELECT COUNT(*) AS n FROM documentos_registro_lecturas WHERE documento_institucional_id=:d",
        d=documento_id,
    ).n


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
    h_psi_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com", f"{PREFIJO} PsiA", "psicologo", inst_a)
    h_admin_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admina.{sello}@ejemplo.com", f"{PREFIJO} AdminA", "admin", inst_a)
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)

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

    print("\n1 · Las vistas de solo listado/metadata NUNCA auditan")
    antes = contar_lecturas(doc_confidencial["id"])
    exigir(requests.get(f"{API}/documentos/", params={"institucion_id": inst_a}, headers=h_psi_a, timeout=30), 200, "listar documentos")
    exigir(requests.get(f"{API}/documentos/{doc_confidencial['id']}", headers=h_psi_a, timeout=30), 200, "detalle documento")
    exigir(requests.get(f"{API}/documentos/{doc_confidencial['id']}/versiones", headers=h_psi_a, timeout=30), 200, "listar versiones")
    despues = contar_lecturas(doc_confidencial["id"])
    comprobar("[1] listar/detalle/listar-versiones no agregan ninguna fila de auditoría", despues == antes,
              f"antes={antes} despues={despues}")

    print("\n2 · GET .../secciones (contenido) SÍ audita")
    antes = contar_lecturas(doc_confidencial["id"])
    exigir(requests.get(f"{API}/documentos/{doc_confidencial['id']}/secciones", headers=h_psi_a, timeout=30), 200, "leer secciones")
    despues = contar_lecturas(doc_confidencial["id"])
    comprobar("[2] leer secciones agrega exactamente una fila", despues == antes + 1, f"antes={antes} despues={despues}")

    fila = sql_uno(
        "SELECT * FROM documentos_registro_lecturas WHERE documento_institucional_id=:d AND tipo_acceso='contenido' "
        "ORDER BY id DESC LIMIT 1",
        d=doc_confidencial["id"],
    )
    comprobar("[2] tipo_acceso='contenido'", fila.tipo_acceso == "contenido")
    comprobar("[2] numero_version_leida es NULL (el borrador no está versionado)", fila.numero_version_leida is None)
    comprobar("[2] rol_lector='psicologo'", fila.rol_lector == "psicologo")
    comprobar("[2] acceso_via_visibilidad_colegio es False", fila.acceso_via_visibilidad_colegio is False)
    comprobar("[2] ip_lectura quedó registrada (no NULL en un request HTTP real)", fila.ip_lectura is not None)
    comprobar("[2] institucion_id es el del documento", fila.institucion_id == inst_a)

    print("\n3 · GET .../versiones/{n}/descargar (PDF) SÍ audita")
    antes = contar_lecturas(doc_confidencial["id"])
    r = requests.get(f"{API}/documentos/{doc_confidencial['id']}/versiones/1/descargar", headers=h_admin_a, timeout=30)
    if r.status_code != 200:
        print(f"\n!! descargar pdf: esperaba 200, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    despues = contar_lecturas(doc_confidencial["id"])
    comprobar("[3] descargar el PDF agrega exactamente una fila", despues == antes + 1, f"antes={antes} despues={despues}")

    fila = sql_uno(
        "SELECT * FROM documentos_registro_lecturas WHERE documento_institucional_id=:d AND tipo_acceso='descarga_pdf' "
        "ORDER BY id DESC LIMIT 1",
        d=doc_confidencial["id"],
    )
    comprobar("[3] tipo_acceso='descarga_pdf'", fila.tipo_acceso == "descarga_pdf")
    comprobar("[3] numero_version_leida=1", fila.numero_version_leida == 1)
    comprobar("[3] rol_lector='admin'", fila.rol_lector == "admin")
    comprobar("[3] acceso_via_visibilidad_colegio es False", fila.acceso_via_visibilidad_colegio is False)

    print("\n4 · 'colegio' leyendo un documento compartible_colegio marca acceso_via_visibilidad_colegio")
    antes = contar_lecturas(doc_compartible["id"])
    exigir(requests.get(f"{API}/documentos/{doc_compartible['id']}/secciones", headers=h_colegio_a, timeout=30), 200, "colegio lee secciones")
    r = requests.get(f"{API}/documentos/{doc_compartible['id']}/versiones/1/descargar", headers=h_colegio_a, timeout=30)
    if r.status_code != 200:
        print(f"\n!! colegio descarga pdf: esperaba 200, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    despues = contar_lecturas(doc_compartible["id"])
    comprobar("[4] ambas lecturas de colegio quedaron auditadas (2 filas nuevas)", despues == antes + 2, f"antes={antes} despues={despues}")

    filas_colegio = sql_todos(
        "SELECT * FROM documentos_registro_lecturas WHERE documento_institucional_id=:d AND rol_lector='colegio' "
        "ORDER BY id DESC LIMIT 2",
        d=doc_compartible["id"],
    )
    comprobar("[4] ambas lecturas de 'colegio' marcan acceso_via_visibilidad_colegio=True",
              all(f.acceso_via_visibilidad_colegio is True for f in filas_colegio))

    print("\n5 · nivel_visibilidad sigue sin afectar la confidencialidad del puente en el expediente")
    alumno = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h_psi_a, timeout=30), 200, "crear persona")["id"]
    doc_compartible_con_alumno = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Compartible con alumno",
        "nivel_visibilidad": "compartible_colegio", "personas_ids": [alumno],
    }, headers=h_psi_a, timeout=30), 200, "crear doc compartible con alumno")
    exigir(requests.post(f"{API}/documentos/{doc_compartible_con_alumno['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "v1 compartible con alumno")

    # 'colegio' SÍ puede leer el contenido del documento (y esa lectura queda
    # auditada aquí, en documentos_registro_lecturas) — pero eso no debe
    # abrirle la entrada-puente del expediente del alumno incluido.
    r = requests.get(f"{API}/documentos/{doc_compartible_con_alumno['id']}/secciones", headers=h_colegio_a, timeout=30)
    comprobar("[5] 'colegio' SÍ lee el contenido del documento compartible_colegio", r.status_code == 200, f"status {r.status_code}")

    fila_puente = sql_uno(
        "SELECT * FROM documentos_registro_lecturas WHERE documento_institucional_id=:d AND rol_lector='colegio'",
        d=doc_compartible_con_alumno["id"],
    )
    comprobar("[5] esa lectura quedó auditada con acceso_via_visibilidad_colegio=True",
              fila_puente is not None and fila_puente.acceso_via_visibilidad_colegio is True)

    entrada_id = sql_uno(
        "SELECT id FROM expediente_entradas WHERE tipo_entrada='documento_institucional' AND documento_institucional_id=:d",
        d=doc_compartible_con_alumno["id"],
    ).id
    r = requests.get(f"{API}/admin/personas/expediente/{entrada_id}", headers=h_colegio_a, timeout=30)
    comprobar("[5] 'colegio' SIGUE sin poder leer la entrada-puente del expediente sin AutorizacionAccesoColegio "
              "(nivel_visibilidad del documento nunca contagia la regla del expediente)",
              r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — LECTURAS: {total - len(fallos)}/{total} comprobaciones superadas")
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
