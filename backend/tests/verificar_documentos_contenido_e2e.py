"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 4:
edición del borrador (DocumentoInstitucionalSeccionContenido).

  1   Leer secciones de un documento nuevo: placeholders vacíos, nunca 404
  2   Guardar contenido de una sección -> se refleja; PUT es reemplazo
      TOTAL (no merge parcial)
  3   plantilla_seccion_id de OTRA plantilla -> 404 (no pertenece a este
      documento)
  4   'colegio' lee pero no edita (403)
  5   Aislamiento entre instituciones en lectura y escritura

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_contenido_e2e
    python -m tests.verificar_documentos_contenido_e2e --limpiar
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

PREFIJO = "ZZDOCCONT"
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
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)

    clave_tipo = f"{PREFIJO.lower()}_tipo_{sello}"
    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": f"{PREFIJO} Tipo",
        "alcances_permitidos": "ninguno", "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento")
    tipo_id = tipo["id"]

    plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla A",
    }, headers=h_super, timeout=30), 200, "crear plantilla A")
    plantilla_id = plantilla["id"]

    seccion_motivo = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_id}/secciones", json={
        "orden": 0, "tipo_seccion": "texto_libre", "titulo": "Motivo de la derivación",
    }, headers=h_super, timeout=30), 200, "crear sección motivo")
    seccion_tabla = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_id}/secciones", json={
        "orden": 1, "tipo_seccion": "tabla_dinamica", "titulo": "Cuadro comparativo",
    }, headers=h_super, timeout=30), 200, "crear sección tabla")

    # Una plantilla AJENA (mismo tipo, misma institución) para el test de
    # plantilla_seccion_id que no pertenece a la plantilla de este documento.
    # activa=False a propósito: activarla desactivaría automáticamente la
    # plantilla principal (índice único parcial, ver Paso 1) y rompería el
    # resto del montaje.
    plantilla_ajena = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla ajena",
        "activa": False,
    }, headers=h_super, timeout=30), 200, "crear plantilla ajena")
    seccion_ajena = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_ajena['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "texto_libre", "titulo": "De otra plantilla",
    }, headers=h_super, timeout=30), 200, "crear sección ajena")

    documento = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_id,
        "alcance": "ninguno", "titulo": f"{PREFIJO} Documento de prueba",
    }, headers=h_psi_a, timeout=30), 200, "crear documento")
    documento_id = documento["id"]

    print("\n1 · Leer secciones de un documento nuevo")
    secciones = exigir(requests.get(f"{API}/documentos/{documento_id}/secciones", headers=h_psi_a, timeout=30), 200, "leer secciones")
    comprobar("[1] Trae las 2 secciones de la plantilla, en orden",
               [s["tipo_seccion"] for s in secciones] == ["texto_libre", "tabla_dinamica"])
    comprobar("[1] contenido vacío es None (no 404, no {})", all(s["contenido"] is None for s in secciones))
    comprobar("[1] actualizado_en vacío es None (nunca se tocó)", all(s["actualizado_en"] is None for s in secciones))

    print("\n2 · Guardar contenido — reemplazo total, no merge")
    guardado1 = exigir(requests.put(f"{API}/documentos/{documento_id}/secciones/{seccion_motivo['id']}", json={
        "contenido": {"texto": "Motivo inicial", "formato": "html"},
    }, headers=h_psi_a, timeout=30), 200, "guardar contenido v1")
    comprobar("[2] Contenido persistido", guardado1["contenido"] == {"texto": "Motivo inicial", "formato": "html"})
    comprobar("[2] actualizado_en ya no es None", guardado1["actualizado_en"] is not None)

    guardado2 = exigir(requests.put(f"{API}/documentos/{documento_id}/secciones/{seccion_motivo['id']}", json={
        "contenido": {"texto": "Motivo corregido"},
    }, headers=h_psi_a, timeout=30), 200, "guardar contenido v2")
    comprobar("[2] El segundo PUT reemplaza TODO — 'formato' ya no está (no fue un merge)",
               guardado2["contenido"] == {"texto": "Motivo corregido"})

    relectura = exigir(requests.get(f"{API}/documentos/{documento_id}/secciones", headers=h_psi_a, timeout=30), 200, "releer secciones")
    por_seccion = {s["plantilla_seccion_id"]: s for s in relectura}
    comprobar("[2] La relectura de la lista trae el contenido actualizado",
               por_seccion[seccion_motivo["id"]]["contenido"] == {"texto": "Motivo corregido"})
    comprobar("[2] La sección de tabla sigue vacía (no se tocó)", por_seccion[seccion_tabla["id"]]["contenido"] is None)

    print("\n3 · plantilla_seccion_id de otra plantilla -> 404")
    r = requests.put(f"{API}/documentos/{documento_id}/secciones/{seccion_ajena['id']}", json={
        "contenido": {"texto": "no debería guardarse"},
    }, headers=h_psi_a, timeout=30)
    comprobar("[3] Sección de una plantilla distinta a la del documento -> 404", r.status_code == 404, f"status {r.status_code}")

    print("\n4 · 'colegio' — regla de nivel_visibilidad (Paso 6): este documento es "
          "'confidencial_clinico' (el default), así que 'colegio' NO lo lee ni lo edita")
    r = requests.get(f"{API}/documentos/{documento_id}/secciones", headers=h_colegio_a, timeout=30)
    comprobar("[4] 'colegio' NO lee las secciones de un documento confidencial_clinico (403)",
               r.status_code == 403, f"status {r.status_code}")
    r = requests.put(f"{API}/documentos/{documento_id}/secciones/{seccion_motivo['id']}", json={
        "contenido": {"texto": "hackeado"},
    }, headers=h_colegio_a, timeout=30)
    comprobar("[4] 'colegio' NO puede editar el contenido (403)", r.status_code == 403, f"status {r.status_code}")

    print("\n5 · Aislamiento entre instituciones")
    r = requests.get(f"{API}/documentos/{documento_id}/secciones", headers=h_psi_b, timeout=30)
    comprobar("[5] B no puede leer las secciones de un documento de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.put(f"{API}/documentos/{documento_id}/secciones/{seccion_motivo['id']}", json={
        "contenido": {"texto": "hackeado"},
    }, headers=h_psi_b, timeout=30)
    comprobar("[5] B no puede editar el contenido de un documento de A (403)", r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — CONTENIDO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
    plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
    documentos = f"SELECT id FROM documentos_institucionales WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM documentos_registro_lecturas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
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
