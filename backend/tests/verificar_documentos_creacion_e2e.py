"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 3:
creación de DocumentoInstitucional (identidad + lista congelada de
estudiantes), por los dos caminos de selección y su combinación.

  1   Atajo por sección completa: incluye a TODOS los matriculados vigentes
      de esa sección, incluido_via='seccion'
  2   Atajo por grado (varias secciones a la vez, resuelto por año escolar)
  3   Selección manual pura ('personas_especificas'): incluido_via='manual',
      admite personas sin matrícula activa
  4   Combinación en un mismo documento: sección completa + nombres sueltos
      (alcance='estructura_academica'), sin duplicar a quien ya estaba
  5   alcance='institucion'/'ninguno': cero estudiantes ligados
  6   Revalidación multi-tenant desde la BD: sección/grado/persona/plantilla
      de OTRA institución -> 404/403, nunca se cuela
  7   Plantilla de otro tipo -> 422; plantilla inactiva -> 409
  8   Listado por institución + aislamiento

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_creacion_e2e
    python -m tests.verificar_documentos_creacion_e2e --limpiar
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

PREFIJO = "ZZDOCCRE"
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


def crear_persona(h, institucion_id, nombres):
    return exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": institucion_id, "nombres": nombres, "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h, timeout=30), 200, f"crear persona {nombres}")["id"]


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
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)

    # Catálogo: un TipoDocumento que admite los 4 alcances.
    clave_tipo = f"{PREFIJO.lower()}_tipo_{sello}"
    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": f"{PREFIJO} Tipo",
        "alcances_permitidos": "institucion, estructura_academica, personas_especificas, ninguno",
        "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento")
    tipo_id = tipo["id"]

    clave_tipo_otro = f"{PREFIJO.lower()}_tipo_otro_{sello}"
    tipo_otro = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo_otro, "nombre": f"{PREFIJO} Tipo Otro",
        "alcances_permitidos": "ninguno", "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento otro")
    tipo_otro_id = tipo_otro["id"]

    plantilla_a = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla A",
    }, headers=h_super, timeout=30), 200, "crear plantilla A")
    plantilla_a_id = plantilla_a["id"]

    plantilla_b = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_b, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla B",
    }, headers=h_super, timeout=30), 200, "crear plantilla B")
    plantilla_b_id = plantilla_b["id"]

    # Estructura académica de A: Nivel -> Grado "3°" -> Secciones "A" y "B" (2026).
    nivel_a = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": f"{PREFIJO} Primaria",
    }, headers=h_super, timeout=30), 200, "crear nivel A")
    grado_a = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel_a["id"], "nombre": "3°",
    }, headers=h_super, timeout=30), 200, "crear grado A")
    seccion_a1 = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_a["id"], "nombre": "A", "anio_escolar": 2026,
    }, headers=h_super, timeout=30), 200, "crear sección A1")
    seccion_a2 = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_a["id"], "nombre": "B", "anio_escolar": 2026,
    }, headers=h_super, timeout=30), 200, "crear sección A2")

    alumnos_seccion1 = [crear_persona(h_psi_a, inst_a, f"{PREFIJO} Sec1-{i}") for i in range(3)]
    alumnos_seccion2 = [crear_persona(h_psi_a, inst_a, f"{PREFIJO} Sec2-{i}") for i in range(2)]
    for pid in alumnos_seccion1:
        exigir(requests.post(f"{API}/admin/personas/{pid}/matricula", json={"seccion_id": seccion_a1["id"]}, headers=h_psi_a, timeout=30), 200, "matricular sec1")
    for pid in alumnos_seccion2:
        exigir(requests.post(f"{API}/admin/personas/{pid}/matricula", json={"seccion_id": seccion_a2["id"]}, headers=h_psi_a, timeout=30), 200, "matricular sec2")

    sueltos = [crear_persona(h_psi_a, inst_a, f"{PREFIJO} Suelto-{i}") for i in range(2)]  # sin matrícula

    # Estructura mínima de B (para el test de cross-tenant).
    nivel_b = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_b, "nombre": f"{PREFIJO} Primaria B",
    }, headers=h_super, timeout=30), 200, "crear nivel B")
    grado_b = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel_b["id"], "nombre": "1°",
    }, headers=h_super, timeout=30), 200, "crear grado B")
    seccion_b = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_b["id"], "nombre": "A", "anio_escolar": 2026,
    }, headers=h_super, timeout=30), 200, "crear sección B")
    persona_b = crear_persona(h_psi_b, inst_b, f"{PREFIJO} AlumnoB")

    print("\n1 · Atajo por sección completa")
    doc1 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "estructura_academica", "titulo": f"{PREFIJO} Doc sección completa",
        "estructura": [{"seccion_id": seccion_a1["id"]}],
    }, headers=h_psi_a, timeout=30), 200, "crear doc por sección")
    ids_doc1 = {e["persona_id"] for e in doc1["estudiantes"]}
    comprobar("[1] Incluye exactamente a los 3 matriculados de la sección", ids_doc1 == set(alumnos_seccion1))
    comprobar("[1] Todos con incluido_via='seccion'", all(e["incluido_via"] == "seccion" for e in doc1["estudiantes"]))
    comprobar("[1] grado_seccion_historico quedó poblado", all(e["grado_seccion_historico"] for e in doc1["estudiantes"]))
    comprobar("[1] version_actual sigue NULL (todavía borrador, sin versión emitida)", doc1["version_actual"] is None)

    print("\n2 · Atajo por grado (varias secciones combinadas por año escolar)")
    doc2 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "estructura_academica", "titulo": f"{PREFIJO} Doc por grado",
        "anio_escolar": 2026, "estructura": [{"grado_id": grado_a["id"]}],
    }, headers=h_psi_a, timeout=30), 200, "crear doc por grado")
    ids_doc2 = {e["persona_id"] for e in doc2["estudiantes"]}
    comprobar("[2] El grado completo trae las DOS secciones juntas",
               ids_doc2 == set(alumnos_seccion1) | set(alumnos_seccion2))

    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "estructura_academica", "titulo": "Sin año",
        "estructura": [{"grado_id": grado_a["id"]}],
    }, headers=h_psi_a, timeout=30)
    comprobar("[2] Nodo de grado SIN anio_escolar -> 422", r.status_code == 422, f"status {r.status_code}")

    print("\n3 · Selección manual pura")
    doc3 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Doc manual",
        "personas_ids": sueltos,
    }, headers=h_psi_a, timeout=30), 200, "crear doc manual")
    ids_doc3 = {e["persona_id"] for e in doc3["estudiantes"]}
    comprobar("[3] Incluye exactamente a los 2 sueltos (sin matrícula)", ids_doc3 == set(sueltos))
    comprobar("[3] incluido_via='manual'", all(e["incluido_via"] == "manual" for e in doc3["estudiantes"]))
    comprobar("[3] Sin matrícula activa, seccion_id_historico queda None",
               all(e["seccion_id_historico"] is None for e in doc3["estudiantes"]))

    print("\n4 · Combinación: sección completa + nombres sueltos")
    doc4 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "estructura_academica", "titulo": f"{PREFIJO} Doc combinado",
        "estructura": [{"seccion_id": seccion_a1["id"]}], "personas_ids": [sueltos[0], alumnos_seccion1[0]],
    }, headers=h_psi_a, timeout=30), 200, "crear doc combinado")
    por_id = {e["persona_id"]: e for e in doc4["estudiantes"]}
    comprobar("[4] Trae los 3 de la sección + el suelto extra (4 en total, sin duplicar)",
               set(por_id) == set(alumnos_seccion1) | {sueltos[0]} and len(doc4["estudiantes"]) == 4)
    comprobar("[4] El alumno que YA estaba en la sección conserva incluido_via='seccion' (no se pisa con 'manual')",
               por_id[alumnos_seccion1[0]]["incluido_via"] == "seccion")
    comprobar("[4] El suelto extra queda 'manual'", por_id[sueltos[0]]["incluido_via"] == "manual")

    print("\n5 · alcance='institucion'/'ninguno' — cero estudiantes")
    doc5 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "institucion", "titulo": f"{PREFIJO} Doc institución",
    }, headers=h_psi_a, timeout=30), 200, "crear doc institución")
    comprobar("[5] alcance='institucion' -> 0 estudiantes ligados", doc5["estudiantes"] == [])

    doc6 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "ninguno", "titulo": f"{PREFIJO} Plan de trabajo",
    }, headers=h_psi_a, timeout=30), 200, "crear plan de trabajo")
    comprobar("[5] alcance='ninguno' -> 0 estudiantes ligados", doc6["estudiantes"] == [])

    print("\n6 · Revalidación multi-tenant desde la BD")
    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "estructura_academica", "titulo": "Sección ajena",
        "estructura": [{"seccion_id": seccion_b["id"]}],
    }, headers=h_psi_a, timeout=30)
    comprobar("[6] Sección de OTRA institución -> 404 (nunca se cuela)", r.status_code == 404, f"status {r.status_code}")

    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "personas_especificas", "titulo": "Persona ajena",
        "personas_ids": [persona_b],
    }, headers=h_psi_a, timeout=30)
    comprobar("[6] Persona de OTRA institución -> 404", r.status_code == 404, f"status {r.status_code}")

    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_b_id,
        "alcance": "ninguno", "titulo": "Plantilla ajena",
    }, headers=h_psi_a, timeout=30)
    comprobar("[6] Plantilla de OTRA institución -> 403", r.status_code == 403, f"status {r.status_code}")

    print("\n7 · Plantilla de otro tipo -> 422; plantilla inactiva -> 409")
    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_otro_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "ninguno", "titulo": "Tipo no coincide",
    }, headers=h_psi_a, timeout=30)
    comprobar("[7] plantilla.tipo_documento_id distinto del tipo pedido -> 422", r.status_code == 422, f"status {r.status_code}")

    # Crear una plantilla_a2 (activa por defecto) desactiva automáticamente plantilla_a.
    exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla A2",
    }, headers=h_super, timeout=30), 200, "crear plantilla A2 (desactiva A)")
    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_a_id,
        "alcance": "ninguno", "titulo": "Plantilla ya inactiva",
    }, headers=h_psi_a, timeout=30)
    comprobar("[7] Plantilla ya no activa -> 409", r.status_code == 409, f"status {r.status_code}")

    print("\n8 · Listado por institución + aislamiento")
    listado = exigir(requests.get(f"{API}/documentos/", params={"institucion_id": inst_a}, headers=h_psi_a, timeout=30), 200, "listar documentos de A")
    comprobar("[8] El listado trae los documentos creados (al menos 6)", len(listado) >= 6)
    comprobar("[8] El listado NO trae la lista de estudiantes (solo metadata)", "estudiantes" not in listado[0])

    r = requests.get(f"{API}/documentos/", params={"institucion_id": inst_b}, headers=h_psi_a, timeout=30)
    comprobar("[8] Listar documentos de OTRA institución -> 403", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/{doc1['id']}", headers=h_psi_b, timeout=30)
    comprobar("[8] Leer el detalle de un documento de OTRA institución -> 403", r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — CREACIÓN: {total - len(fallos)}/{total} comprobaciones superadas")
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
    secciones = f"SELECT id FROM secciones WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE institucion_id IN ({insts})"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM secciones WHERE id IN ({secciones})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
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
