"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 5:
generar una versión — el paso de mayor riesgo del feature.

  1   v1 real: PDF válido, correlativo impreso, version_actual=1
  2   Gate de consentimiento: bloquea sin consentimiento vigente del
      apoderado, se desbloquea al registrarlo, y vuelve a bloquear una
      REEMISIÓN si el consentimiento se revoca entre versiones
  3   Tipo SIN gate: 1 sola persona manual, nunca se bloquea
  4   Reemisión exige motivo y NUNCA toca la lista congelada
  5   Entradas-puente del expediente: una por estudiante por versión, con
      autor_usuario_id correcto, sujetas a la regla YA EXISTENTE de acceso
      (nivel_visibilidad del documento no las afecta)
  6   Tipografía de la plantilla reflejada en el PDF real
  7   Concurrencia real: correlativo nunca se repite; dos reemisiones
      simultáneas del MISMO documento se serializan sin duplicar ni saltar
      número de versión

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_version_e2e
    python -m tests.verificar_documentos_version_e2e --limpiar
"""

import argparse
import io
import os
import re
import sys
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from pypdf import PdfReader  # noqa: E402
from core.storage import obtener_storage_service  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZDOCVER"
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


def crear_persona(h, institucion_id, nombres):
    return exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": institucion_id, "nombres": nombres, "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h, timeout=30), 200, f"crear persona {nombres}")["id"]


def otorgar_consentimiento_apoderado(h, persona_id, institucion_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": institucion_id,
        "otorgado_por_nombre": "Madre de Prueba", "tipo_otorgante": "apoderado",
    }, headers=h, timeout=30), 200, "otorgar consentimiento apoderado")


def revocar_consentimiento_apoderado(h, persona_id):
    return exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento/revocar", json={},
                                 headers=h, timeout=30), 200, "revocar consentimiento apoderado")


def leer_pdf_de_version(numero_version, documento_id):
    fila = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones "
        "WHERE documento_institucional_id=:d AND numero_version=:n",
        d=documento_id, n=numero_version,
    )
    return obtener_storage_service().leer(fila.storage_key)


def fuentes_usadas(contenido: bytes) -> set:
    lector = PdfReader(io.BytesIO(contenido))
    nombres = set()
    for pagina in lector.pages:
        fuentes = pagina.get("/Resources", {}).get("/Font", {})
        for clave in fuentes:
            base = str(fuentes[clave].get_object().get("/BaseFont", ""))
            nombres.add(base.split("+")[-1])
    return nombres


def tamano_fuente_presente(contenido: bytes, tamano: int) -> bool:
    lector = PdfReader(io.BytesIO(contenido))
    patron = re.compile(rf"/F\d+\+?0?\s+{tamano}\s+Tf")
    for pagina in lector.pages:
        ref = pagina.get("/Contents")
        if ref is None:
            continue
        datos = ref.get_object().get_data().decode("latin1", errors="replace")
        if patron.search(datos):
            return True
    return False


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
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)

    psi_a_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com").id
    exigir(requests.patch(f"{API}/auth/usuarios/{psi_a_id}", json={"cargo": "Psicóloga del DPTO"}, headers=h_super, timeout=30), 200, "poner cargo")

    # Tipo SIN gate, con correlativo, Helvetica explícito (evita depender de
    # si el servidor de pruebas tiene Arial instalada) a 12pt.
    tipo_libre = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_libre_{sello}", "nombre": f"{PREFIJO} Libre",
        "alcances_permitidos": "ninguno, personas_especificas", "visibilidades_permitidas": "confidencial_clinico, compartible_colegio",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo libre")
    plantilla_libre = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_libre["id"], "nombre": f"{PREFIJO} Plantilla libre",
        "fuente": "Helvetica", "tamano_pt": 12, "formato_correlativo": "DOC-{correlativo:04d}-{anio}",
    }, headers=h_super, timeout=30), 200, "crear plantilla libre")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_libre['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
    }, headers=h_super, timeout=30), 200, "sección encabezado (libre)")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_libre['id']}/secciones", json={
        "orden": 1, "tipo_seccion": "texto_libre", "titulo": "Cuerpo",
    }, headers=h_super, timeout=30), 200, "sección texto_libre (libre)")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_libre['id']}/secciones", json={
        "orden": 2, "tipo_seccion": "firma", "titulo": "Firma",
    }, headers=h_super, timeout=30), 200, "sección firma (libre)")

    # Tipo CON gate (individual), datos_filiacion + datos_familiares.
    tipo_gated = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_individual_{sello}", "nombre": f"{PREFIJO} Individual",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": True,
    }, headers=h_super, timeout=30), 200, "crear tipo gated")
    plantilla_gated = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_gated["id"], "nombre": f"{PREFIJO} Plantilla individual",
    }, headers=h_super, timeout=30), 200, "crear plantilla gated")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_gated['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "datos_filiacion", "titulo": "Filiación",
    }, headers=h_super, timeout=30), 200, "sección datos_filiacion")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_gated['id']}/secciones", json={
        "orden": 1, "tipo_seccion": "datos_familiares", "titulo": "Datos familiares",
    }, headers=h_super, timeout=30), 200, "sección datos_familiares")

    print("\n1 · v1 real (tipo sin gate, alcance='ninguno')")
    doc_ninguno = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_libre["id"], "plantilla_documento_id": plantilla_libre["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Plan de trabajo",
    }, headers=h_psi_a, timeout=30), 200, "crear doc ninguno")
    seccion_texto_id = _id_seccion(h_psi_a, plantilla_libre, "texto_libre")
    exigir(requests.put(f"{API}/documentos/{doc_ninguno['id']}/secciones/{seccion_texto_id}",
                         json={"contenido": {"texto": "Objetivo general de la intervención institucional."}},
                         headers=h_psi_a, timeout=30), 200, "escribir contenido")
    version1 = exigir(requests.post(f"{API}/documentos/{doc_ninguno['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "generar v1")
    comprobar("[1] numero_version=1", version1["numero_version"] == 1)
    comprobar("[1] motivo_version='Emisión inicial'", version1["motivo_version"] == "Emisión inicial")
    doc_relectura = exigir(requests.get(f"{API}/documentos/{doc_ninguno['id']}", headers=h_psi_a, timeout=30), 200, "releer doc")
    comprobar("[1] version_actual pasó a 1", doc_relectura["version_actual"] == 1)

    pdf_bytes = leer_pdf_de_version(1, doc_ninguno["id"])
    lector = PdfReader(io.BytesIO(pdf_bytes))
    texto = " ".join((p.extract_text() or "") for p in lector.pages)
    comprobar("[1] El PDF es legible y trae el correlativo impreso", "DOC-0001" in texto, texto[:200])

    print("\n2 · Gate de consentimiento")
    alumno_gated = crear_persona(h_psi_a, inst_a, f"{PREFIJO} Gated")
    doc_gated = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_gated["id"], "plantilla_documento_id": plantilla_gated["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Informe individual", "personas_ids": [alumno_gated],
    }, headers=h_psi_a, timeout=30), 200, "crear doc gated")

    r = requests.post(f"{API}/documentos/{doc_gated['id']}/generar-version", headers=h_psi_a, timeout=30)
    comprobar("[2] Sin consentimiento vigente -> 403", r.status_code == 403, f"status {r.status_code}")

    otorgar_consentimiento_apoderado(h_psi_a, alumno_gated, inst_a)
    v1_gated = exigir(requests.post(f"{API}/documentos/{doc_gated['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "generar v1 gated tras consentir")
    comprobar("[2] Con consentimiento vigente, v1 se genera", v1_gated["numero_version"] == 1)

    revocar_consentimiento_apoderado(h_psi_a, alumno_gated)
    r = requests.post(f"{API}/documentos/{doc_gated['id']}/reemitir", json={"motivo": "Corrección de forma"}, headers=h_psi_a, timeout=30)
    comprobar("[2] Consentimiento revocado ENTRE versiones -> reemisión también bloqueada (403)", r.status_code == 403, f"status {r.status_code}")

    otorgar_consentimiento_apoderado(h_psi_a, alumno_gated, inst_a)
    v2_gated = exigir(requests.post(f"{API}/documentos/{doc_gated['id']}/reemitir", json={"motivo": "Corrección de forma"}, headers=h_psi_a, timeout=30), 200, "reemitir tras renovar consentimiento")
    comprobar("[2] Renovado el consentimiento, la reemisión sí procede", v2_gated["numero_version"] == 2)

    print("\n3 · Tipo SIN gate con 1 persona manual — nunca se bloquea")
    alumno_libre = crear_persona(h_psi_a, inst_a, f"{PREFIJO} Libre1")
    doc_libre_manual = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_libre["id"], "plantilla_documento_id": plantilla_libre["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Sin gate", "personas_ids": [alumno_libre],
    }, headers=h_psi_a, timeout=30), 200, "crear doc libre manual")
    v_libre_manual = exigir(requests.post(f"{API}/documentos/{doc_libre_manual['id']}/generar-version", headers=h_psi_a, timeout=30),
                             200, "generar sin consentimiento (no debería exigirlo)")
    comprobar("[3] Se genera SIN pedir consentimiento (requiere_consentimiento_individual=False)", v_libre_manual["numero_version"] == 1)

    print("\n4 · Reemisión exige motivo y nunca toca la lista congelada")
    r = requests.post(f"{API}/documentos/{doc_ninguno['id']}/generar-version", headers=h_psi_a, timeout=30)
    comprobar("[4] Reintentar 'generar-version' cuando ya hay v1 -> 422 (exige usar reemitir)", r.status_code == 422, f"status {r.status_code}")
    r = requests.post(f"{API}/documentos/{doc_gated['id']}/reemitir", json={"motivo": "x"}, headers=h_psi_a, timeout=30)
    comprobar("[4] motivo demasiado corto -> 422", r.status_code == 422, f"status {r.status_code}")

    ids_antes = {e["persona_id"] for e in exigir(requests.get(f"{API}/documentos/{doc_gated['id']}", headers=h_psi_a, timeout=30), 200, "leer doc gated")["estudiantes"]}
    exigir(requests.post(f"{API}/documentos/{doc_gated['id']}/reemitir",
                          json={"motivo": "Intento de colar más estudiantes", "personas_ids": [alumno_libre], "estructura": [{"seccion_id": 1}]},
                          headers=h_psi_a, timeout=30), 200, "reemitir con payload manipulado")
    ids_despues = {e["persona_id"] for e in exigir(requests.get(f"{API}/documentos/{doc_gated['id']}", headers=h_psi_a, timeout=30), 200, "releer doc gated")["estudiantes"]}
    comprobar("[4] La lista congelada NO cambió aunque el payload trajera personas_ids/estructura", ids_antes == ids_despues == {alumno_gated})

    print("\n5 · Entradas-puente del expediente")
    entradas = sql_todos(
        "SELECT persona_id, autor_usuario_id, documento_institucional_id, version_actual FROM expediente_entradas "
        "WHERE tipo_entrada='documento_institucional' AND documento_institucional_id=:d",
        d=doc_gated["id"],
    )
    comprobar("[5] Una entrada-puente por estudiante incluido", len(entradas) == 1 and entradas[0].persona_id == alumno_gated)
    comprobar("[5] autor_usuario_id = creado_por_usuario_id del documento (no quien reemitió)", entradas[0].autor_usuario_id == psi_a_id)
    comprobar("[5] Sin version_actual propio (es puente)", entradas[0].version_actual is None)

    entrada_id = sql_uno(
        "SELECT id FROM expediente_entradas WHERE tipo_entrada='documento_institucional' AND documento_institucional_id=:d",
        d=doc_gated["id"],
    ).id
    r = requests.get(f"{API}/admin/personas/expediente/{entrada_id}", headers=h_colegio_a, timeout=30)
    comprobar("[5] 'colegio' SIN AutorizacionAccesoColegio no lee la entrada-puente (403), "
              "aunque el documento sea 'confidencial_clinico' (regla del expediente sin excepción nueva)",
              r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/admin/personas/expediente/{entrada_id}", headers=h_psi_a, timeout=30)
    comprobar("[5] El autor (creador del documento) SÍ lee la entrada-puente", r.status_code == 200, f"status {r.status_code}")

    print("\n6 · Tipografía de la plantilla reflejada en el PDF")
    pdf_libre = leer_pdf_de_version(1, doc_ninguno["id"])
    fuentes_pdf = fuentes_usadas(pdf_libre)
    comprobar("[6] La plantilla pidió Helvetica explícito y el PDF la usa",
              any("Helvetica" in f for f in fuentes_pdf), str(fuentes_pdf))
    comprobar("[6] El cuerpo del texto usa 12pt (tamano_pt de la plantilla)", tamano_fuente_presente(pdf_libre, 12))

    print("\n7 · Concurrencia real")
    doc_x = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_libre["id"], "plantilla_documento_id": plantilla_libre["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Correlativo X",
    }, headers=h_psi_a, timeout=30), 200, "crear doc X")
    doc_y = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_libre["id"], "plantilla_documento_id": plantilla_libre["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Correlativo Y",
    }, headers=h_psi_a, timeout=30), 200, "crear doc Y")

    resultados_correlativo = {}
    barrera = threading.Barrier(2)

    def generar_en_paralelo(doc_id, clave):
        barrera.wait()
        r = requests.post(f"{API}/documentos/{doc_id}/generar-version", headers=h_psi_a, timeout=60)
        resultados_correlativo[clave] = r

    hilos = [
        threading.Thread(target=generar_en_paralelo, args=(doc_x["id"], "x")),
        threading.Thread(target=generar_en_paralelo, args=(doc_y["id"], "y")),
    ]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    ok_x = resultados_correlativo["x"].status_code == 200
    ok_y = resultados_correlativo["y"].status_code == 200
    comprobar("[7a] Ambas emisiones simultáneas de documentos DISTINTOS tienen éxito", ok_x and ok_y,
              f"x={resultados_correlativo['x'].status_code} y={resultados_correlativo['y'].status_code}")
    snap_x = sql_uno("SELECT contenido_snapshot FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1", d=doc_x["id"])
    snap_y = sql_uno("SELECT contenido_snapshot FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1", d=doc_y["id"])
    import json as _json
    correlativo_x = _json.loads(snap_x.contenido_snapshot)["documento"]["correlativo"] if isinstance(snap_x.contenido_snapshot, str) else snap_x.contenido_snapshot["documento"]["correlativo"]
    correlativo_y = _json.loads(snap_y.contenido_snapshot)["documento"]["correlativo"] if isinstance(snap_y.contenido_snapshot, str) else snap_y.contenido_snapshot["documento"]["correlativo"]
    comprobar("[7a] El correlativo NUNCA se repite entre las dos emisiones simultáneas",
              correlativo_x != correlativo_y, f"x={correlativo_x} y={correlativo_y}")

    doc_z = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_libre["id"], "plantilla_documento_id": plantilla_libre["id"],
        "alcance": "ninguno", "titulo": f"{PREFIJO} Reemisiones concurrentes",
    }, headers=h_psi_a, timeout=30), 200, "crear doc Z")
    exigir(requests.post(f"{API}/documentos/{doc_z['id']}/generar-version", headers=h_psi_a, timeout=30), 200, "v1 de Z")

    resultados_reemision = []
    barrera2 = threading.Barrier(2)

    def reemitir_en_paralelo():
        barrera2.wait()
        r = requests.post(f"{API}/documentos/{doc_z['id']}/reemitir", json={"motivo": "Reemisión concurrente de prueba"}, headers=h_psi_a, timeout=60)
        resultados_reemision.append(r.status_code)

    hilos2 = [threading.Thread(target=reemitir_en_paralelo) for _ in range(2)]
    for h in hilos2:
        h.start()
    for h in hilos2:
        h.join()

    comprobar("[7b] Dos reemisiones simultáneas del MISMO documento: ambas resueltas sin 500 crudo",
              all(c in (200, 409) for c in resultados_reemision), f"códigos: {resultados_reemision}")
    numeros_z = [r.numero_version for r in sql_todos(
        "SELECT numero_version FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d ORDER BY numero_version",
        d=doc_z["id"],
    )]
    comprobar("[7b] Los números de versión resultantes son consecutivos, sin duplicar ni saltar (lock serializó correctamente)",
              numeros_z == list(range(1, len(numeros_z) + 1)), f"versiones: {numeros_z}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — VERSIÓN: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def _id_seccion(h, plantilla, tipo_seccion):
    r = requests.get(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", headers=h, timeout=30)
    for s in r.json():
        if s["tipo_seccion"] == tipo_seccion:
            return s["id"]
    raise RuntimeError(f"No se encontró sección {tipo_seccion}")


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
            f"DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_correlativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
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
