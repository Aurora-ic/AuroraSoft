"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 1:
catálogo (TipoDocumento, AnioOficial, globales y solo superadmin) y el
"constructor de plantillas" por institución (PlantillaDocumento/
PlantillaSeccion, abierto a STAFF_CLINICO de la institución dueña — ver
"Constructor de plantillas" en docs/motor-documentos.md) y Usuario.cargo.

  1   TipoDocumento: solo superadmin escribe (403 para otros roles);
      lectura abierta a cualquier autenticado; clave duplicada -> 409;
      alcance/visibilidad inválidos -> 422 (antes de tocar la BD)
  2   AnioOficial: solo superadmin escribe; re-declarar el mismo año
      actualiza el texto (upsert), no duplica la fila
  3   PlantillaDocumento: admin/psicólogo de la institución dueña pueden
      crear/editar la suya (el "constructor"); 'colegio' sigue sin poder;
      un institucion_id ajeno en el body se IGNORA y se fuerza a la propia
      (nunca 403, mismo criterio que la importación Excel); otra
      institución no puede leer/editar/listar (403); activar una segunda
      plantilla del mismo institución+tipo desactiva la anterior (índice
      único parcial respetado, sin IntegrityError crudo)
  4   PlantillaSeccion: mismas reglas de escritura/lectura que su
      plantilla (incluida la escritura ahora abierta a STAFF_CLINICO);
      tipo_seccion inválido -> 422; DELETE (nuevo) solo de la institución
      dueña
  5   Usuario.cargo: editable vía el PATCH de usuario ya existente

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_catalogo_e2e
    python -m tests.verificar_documentos_catalogo_e2e --limpiar
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

PREFIJO = "ZZDOCCAT"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []
_ANIO_PRUEBA = 2099  # año lejano, no puede colisionar con un AnioOficial real ya cargado


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
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)
    h_col_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.cola.{sello}@ejemplo.com", f"{PREFIJO} ColA", "colegio", inst_a)

    clave_tipo = f"{PREFIJO.lower()}_informe_individual_{sello}"

    print("\n1 · TipoDocumento")
    r = requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": f"{PREFIJO} Informe individual",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": True,
    }, headers=h_psi_a, timeout=30)
    comprobar("[1] 'psicologo' NO puede crear un TipoDocumento (403)", r.status_code == 403, f"status {r.status_code}")

    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": f"{PREFIJO} Informe individual",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": True,
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento")
    tipo_id = tipo["id"]
    comprobar("[1] requiere_consentimiento_individual quedó en True", tipo["requiere_consentimiento_individual"] is True)

    r = requests.post(f"{API}/documentos/tipos", json={
        "clave": clave_tipo, "nombre": "Duplicado",
        "alcances_permitidos": "institucion", "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30)
    comprobar("[1] Clave duplicada -> 409", r.status_code == 409, f"status {r.status_code}")

    r = requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{clave_tipo}_bad", "nombre": "Malo",
        "alcances_permitidos": "un_alcance_inventado", "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30)
    comprobar("[1] alcances_permitidos inválido -> 422 antes de tocar la BD", r.status_code == 422, f"status {r.status_code}")

    listado = exigir(requests.get(f"{API}/documentos/tipos", headers=h_psi_b, timeout=30), 200, "listar tipos (psicólogo B)")
    comprobar("[1] Cualquier autenticado puede LISTAR tipos (no solo superadmin)",
               any(t["id"] == tipo_id for t in listado))

    tipo_actualizado = exigir(requests.patch(f"{API}/documentos/tipos/{tipo_id}", json={
        "nombre": f"{PREFIJO} Informe individual (editado)",
    }, headers=h_super, timeout=30), 200, "editar TipoDocumento")
    comprobar("[1] PATCH de superadmin se refleja", tipo_actualizado["nombre"].endswith("(editado)"))

    r = requests.patch(f"{API}/documentos/tipos/{tipo_id}", json={"nombre": "hackeado"}, headers=h_psi_a, timeout=30)
    comprobar("[1] 'psicologo' no puede editar un TipoDocumento (403)", r.status_code == 403, f"status {r.status_code}")

    print("\n2 · AnioOficial")
    r = requests.post(f"{API}/documentos/anios-oficiales", json={
        "anio": _ANIO_PRUEBA, "texto": f"{PREFIJO} Año de prueba original",
    }, headers=h_psi_a, timeout=30)
    comprobar("[2] 'psicologo' no puede crear un AnioOficial (403)", r.status_code == 403, f"status {r.status_code}")

    exigir(requests.post(f"{API}/documentos/anios-oficiales", json={
        "anio": _ANIO_PRUEBA, "texto": f"{PREFIJO} Año de prueba original",
    }, headers=h_super, timeout=30), 200, "crear AnioOficial")

    exigir(requests.post(f"{API}/documentos/anios-oficiales", json={
        "anio": _ANIO_PRUEBA, "texto": f"{PREFIJO} Año de prueba corregido",
    }, headers=h_super, timeout=30), 200, "re-declarar mismo AnioOficial (upsert)")

    anios = exigir(requests.get(f"{API}/documentos/anios-oficiales", headers=h_psi_a, timeout=30), 200, "listar AnioOficial")
    fila_anio = next(a for a in anios if a["anio"] == _ANIO_PRUEBA)
    comprobar("[2] Re-declarar el mismo año actualiza el texto (no duplica la fila)",
               fila_anio["texto"] == f"{PREFIJO} Año de prueba corregido")
    comprobar("[2] Solo existe UNA fila para ese año", sum(1 for a in anios if a["anio"] == _ANIO_PRUEBA) == 1)

    print("\n3 · PlantillaDocumento")
    plantilla_v1 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla v1",
    }, headers=h_psi_a, timeout=30), 200, "crear plantilla v1 (psicólogo de su propia institución)")
    plantilla_v1_id = plantilla_v1["id"]
    comprobar("[3] v1 nace activa=True", plantilla_v1["activa"] is True)
    comprobar("[3] Tipografía por defecto: Arial 11pt justificado",
               plantilla_v1["fuente"] == "Arial" and plantilla_v1["tamano_pt"] == 11 and plantilla_v1["justificado"] is True)

    r = requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_b, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Intento cruzado",
    }, headers=h_psi_a, timeout=30)
    plantilla_cruzada = exigir(r, 200, "psicólogo A manda institucion_id de B en el body")
    comprobar("[3] Un institucion_id ajeno en el body se IGNORA y se fuerza a la propia (nunca 403, "
              "mismo criterio que _institucion_para_importacion)", plantilla_cruzada["institucion_id"] == inst_a)

    r = requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Intento colegio",
    }, headers=h_col_a, timeout=30)
    comprobar("[3] 'colegio' sigue sin poder crear una PlantillaDocumento (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/plantillas/{plantilla_v1_id}", headers=h_psi_a, timeout=30)
    comprobar("[3] La propia institución SÍ puede leer su plantilla", r.status_code == 200, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/plantillas/{plantilla_v1_id}", headers=h_psi_b, timeout=30)
    comprobar("[3] Otra institución NO puede leer la plantilla (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/plantillas", params={"institucion_id": inst_b}, headers=h_psi_a, timeout=30)
    comprobar("[3] Listar plantillas de OTRA institución -> 403", r.status_code == 403, f"status {r.status_code}")

    plantilla_v2 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla v2",
    }, headers=h_super, timeout=30), 200, "crear plantilla v2 (activa por defecto)")
    plantilla_v2_id = plantilla_v2["id"]

    v1_relectura = exigir(requests.get(f"{API}/documentos/plantillas/{plantilla_v1_id}", headers=h_super, timeout=30), 200, "releer v1")
    comprobar("[3] Activar v2 desactivó automáticamente v1 (índice único parcial respetado)",
               v1_relectura["activa"] is False and plantilla_v2["activa"] is True)

    r = requests.patch(f"{API}/documentos/plantillas/{plantilla_v1_id}", json={"nombre": "hackeado"}, headers=h_psi_b, timeout=30)
    comprobar("[3] 'psicologo' de OTRA institución no puede editar esta plantilla (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Correlativo malo",
        "formato_correlativo": "INFORME-{numero_que_no_existe}",
    }, headers=h_super, timeout=30)
    comprobar("[3] formato_correlativo con placeholder inválido -> 422 al GUARDAR la plantilla", r.status_code == 422, f"status {r.status_code}")

    print("\n4 · PlantillaSeccion")
    seccion_encabezado = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
        "config": {"mostrar_correlativo": True, "destinatarios": [{"nombre": "Directora", "cargo": "Dirección académica"}]},
    }, headers=h_psi_a, timeout=30), 200, "crear sección encabezado (psicólogo de su propia institución)")

    r = requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 1, "tipo_seccion": "datos_filiacion",
    }, headers=h_psi_b, timeout=30)
    comprobar("[4] 'psicologo' de OTRA institución no puede agregar una sección a esta plantilla (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 1, "tipo_seccion": "datos_filiacion",
    }, headers=h_col_a, timeout=30)
    comprobar("[4] 'colegio' sigue sin poder crear una PlantillaSeccion (403)", r.status_code == 403, f"status {r.status_code}")

    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 1, "tipo_seccion": "datos_filiacion",
    }, headers=h_super, timeout=30), 200, "crear sección datos_filiacion")

    r = requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 2, "tipo_seccion": "un_tipo_que_no_existe",
    }, headers=h_super, timeout=30)
    comprobar("[4] tipo_seccion inválido -> 422", r.status_code == 422, f"status {r.status_code}")

    secciones = exigir(requests.get(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", headers=h_psi_a, timeout=30), 200, "listar secciones (institución propia)")
    comprobar("[4] Quedaron 2 secciones, en orden", [s["tipo_seccion"] for s in secciones] == ["encabezado", "datos_filiacion"])

    r = requests.get(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", headers=h_psi_b, timeout=30)
    comprobar("[4] Otra institución no lista las secciones (403)", r.status_code == 403, f"status {r.status_code}")

    seccion_editada = exigir(requests.patch(f"{API}/documentos/secciones/{seccion_encabezado['id']}", json={
        "titulo": "Encabezado institucional",
    }, headers=h_psi_a, timeout=30), 200, "editar sección (psicólogo de su propia institución)")
    comprobar("[4] Edición de título persistida", seccion_editada["titulo"] == "Encabezado institucional")
    comprobar("[4] config no se perdió al editar solo el título",
               seccion_editada["config"]["mostrar_correlativo"] is True)

    r = requests.patch(f"{API}/documentos/secciones/{seccion_editada['id']}", json={"titulo": "hackeado"}, headers=h_psi_b, timeout=30)
    comprobar("[4] 'psicologo' de OTRA institución no puede editar esta sección (403)", r.status_code == 403, f"status {r.status_code}")

    seccion_a_borrar = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", json={
        "orden": 2, "tipo_seccion": "firma",
    }, headers=h_psi_a, timeout=30), 200, "crear sección a borrar")

    r = requests.delete(f"{API}/documentos/secciones/{seccion_a_borrar['id']}", headers=h_psi_b, timeout=30)
    comprobar("[4] 'psicologo' de OTRA institución no puede borrar esta sección (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.delete(f"{API}/documentos/secciones/{seccion_a_borrar['id']}", headers=h_psi_a, timeout=30)
    comprobar("[4] (nuevo) 'psicologo' de su propia institución SÍ puede borrar una sección en borrador (204)", r.status_code == 204, f"status {r.status_code}")

    r = requests.get(f"{API}/documentos/plantillas/{plantilla_v2_id}/secciones", headers=h_super, timeout=30)
    comprobar("[4] La sección borrada ya no aparece en el listado", seccion_a_borrar["id"] not in [s["id"] for s in r.json()])

    print("\n5 · Usuario.cargo")
    psi_a_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com").id
    usuario_editado = exigir(requests.patch(f"{API}/auth/usuarios/{psi_a_id}", json={
        "cargo": "INTERNA del DPTO DE PSICOLOGÍA",
    }, headers=h_super, timeout=30), 200, "editar cargo")
    comprobar("[5] Usuario.cargo editable y devuelto en la respuesta",
               usuario_editado["cargo"] == "INTERNA del DPTO DE PSICOLOGÍA")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — CATÁLOGO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
    plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM documentos_anios_oficiales WHERE anio = {_ANIO_PRUEBA}",
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
