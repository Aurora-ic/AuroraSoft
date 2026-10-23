"""Verificación end-to-end — Informes (modelo genérico) sobre el piloto PHQ-9.

Cubre el flujo vertical completo pedido en la fase de informes:

  0     Montaje: dos instituciones, y localizar el catálogo público PHQ-9
  1-8   Aplicación SIN alerta: examen -> finalizar -> informe generado y
        almacenado en background -> PDF descargable -> metadata -> historial
  9-15  Aplicación CON alerta (PHQ-9 severo): informe retenido, PDF bloqueado
        al alumno pero visible al staff, liberación, reemisión (versionado)
  16-18 Interpretación incompleta (prueba sin baremo): igual se genera informe
  19-23 Seguridad multi-tenant: el colegio B no puede ver nada del colegio A
  24-26 Storage: 404 de inscripción inexistente, informe aún no generado,
        checksum/tamaño coherentes con el PDF real descargado
  27    Regresión ligera: dimensiones_sin_baremo nunca se confunde con "sin riesgo"

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_informe_phq9_e2e.py
    python tests/verificar_informe_phq9_e2e.py --limpiar
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

PREFIJO = "ZZPHQ"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:400]}")
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


def crear_colegio(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}", "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
    correo = f"{PREFIJO.lower()}.psi.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {letra}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo {letra}",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro {letra}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {letra}")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}, correo


def crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta):
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    return persona["id"]


def matricular(headers, campana_id, persona_id):
    m = exigir(requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                             json=[persona_id], headers=headers, timeout=30), 200, "Matrícula")
    return m["generados"][0]["token"]


def responder_phq9(token, preguntas_por_orden, valores):
    """`valores` es una lista de 9 enteros 0-3, uno por ítem en orden."""
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno PHQ-9", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar test")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preguntas_por_orden[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [
        {"pregunta_id": preguntas_por_orden[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)}
        for i, v in enumerate(valores)
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar",
                         json={"respuestas": respuestas}, timeout=30), 200, "Guardar respuestas")


def esperar_informe(headers, inscripcion_id, timeout=20):
    """El PDF se genera en un BackgroundTask tras finalizar: hace polling breve
    a la metadata del informe hasta que aparece (o hasta agotar el timeout)."""
    limite = time.time() + timeout
    while time.time() < limite:
        r = requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30)
        if r.status_code == 200 and r.json().get("existe"):
            return r.json()
        time.sleep(0.5)
    return requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30).json()


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ==================================================================
    print("\n0 · Montaje: dos instituciones + localizar el catálogo público PHQ-9")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a, h_a, _ = crear_colegio(h_super, "A", sello)
    inst_b, h_b, _ = crear_colegio(h_super, "B", sello)

    fila_phq9 = sql_uno(
        "select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")
    comprobar("El catálogo público PHQ-9 existe (seed_phq9.py ya se ejecutó)", fila_phq9 is not None)
    if not fila_phq9:
        print("\n!! Ejecuta `python -m seeds.seed_phq9` antes de correr este E2E.")
        sys.exit(1)
    phq9_id = fila_phq9[0]

    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa",
                                       headers=h_a, timeout=30), 200, "Detalle PHQ-9")
    comprobar("PHQ-9 tiene exactamente 1 dimensión", len(detalle_phq9["dimensiones"]) == 1)
    dim_phq9 = detalle_phq9["dimensiones"][0]
    comprobar("PHQ-9 tiene 9 preguntas", len(dim_phq9["preguntas"]) == 9, str(len(dim_phq9["preguntas"])))
    preg_phq9 = {p["orden"]: p for p in dim_phq9["preguntas"]}
    comprobar("PHQ-9 tiene 5 tramos de baremo (sin huecos 0-27)", len(detalle_phq9["baremos"]) == 5)

    # ==================================================================
    print("\n1-8 · Aplicación SIN alerta (todo 'Nunca' -> puntaje 0)")
    campana_ok = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Sin alerta {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña sin alerta")
    persona_ok = crear_persona_con_consentimiento(h_a, inst_a, sello, "OK")
    tok_ok = matricular(h_a, campana_ok["id"], persona_ok)

    responder_phq9(tok_ok, preg_phq9, [0] * 9)
    r = requests.post(f"{API}/educativo/examen/{tok_ok}/finalizar", timeout=60)
    comprobar("[1] Finaliza correctamente (200)", r.status_code == 200, f"status {r.status_code}")
    diagnosticos = r.json()
    comprobar("[1] Se devuelve el diagnóstico al alumno (sin alerta)", len(diagnosticos) == 1)
    # No se asume un texto de nivel concreto (el catálogo público puede tener
    # su propia redacción): lo único que importa es el indicador es_alerta,
    # igual que el resto del sistema — ver "nunca infieras riesgo del nivel".
    comprobar("[1] Puntaje 0/27 cae en un tramo SIN alerta",
              diagnosticos[0]["es_alerta"] is False, f"nivel={diagnosticos[0]['nivel']!r}")

    insc_ok = sql_uno("select id, resultado_visible_alumno, informe_liberado from edu_inscripciones where token=:t", t=tok_ok)
    comprobar("[2] resultado_visible_alumno=True, informe_liberado=True", insc_ok[1] is True and insc_ok[2] is True)

    meta_ok = esperar_informe(h_a, insc_ok[0])
    comprobar("[3] El informe se generó en segundo plano tras finalizar (sin bloquear la respuesta)", meta_ok.get("existe") is True)
    comprobar("[3] version_actual == 1 en la primera emisión", meta_ok.get("version_actual") == 1)
    comprobar("[3] El historial trae exactamente 1 versión, motivo 'Emisión inicial', sin usuario (generado por el sistema)",
              len(meta_ok["versiones"]) == 1 and meta_ok["versiones"][0]["motivo_version"] == "Emisión inicial"
              and meta_ok["versiones"][0]["generado_por_usuario_id"] is None)

    fila_version = sql_uno(
        "select v.storage_key, v.tamano_bytes, v.checksum_sha256, v.resultados_snapshot "
        "from edu_informe_versiones v join edu_informes i on i.id = v.informe_id "
        "where i.inscripcion_id = :i and v.numero_version = 1", i=insc_ok[0])
    comprobar("[4] La storage_key está aislada por institución y por informe",
              fila_version[0].startswith(f"instituciones/{inst_a}/informes/"), fila_version[0])

    r_pdf_alumno = requests.get(f"{API}/educativo/examen/{tok_ok}/informe-pdf", timeout=60)
    comprobar("[5] El alumno descarga su PDF (200, liberado automáticamente sin alerta)",
              r_pdf_alumno.status_code == 200, f"status {r_pdf_alumno.status_code}")
    comprobar("[5] Es un PDF real", r_pdf_alumno.content[:4] == b"%PDF")
    comprobar("[6] tamano_bytes/checksum en BD coinciden con el PDF servido",
              len(r_pdf_alumno.content) == fila_version[1]
              and hashlib.sha256(r_pdf_alumno.content).hexdigest() == fila_version[2])

    r_pdf_staff = requests.get(f"{API}/educativo/inscripciones/{insc_ok[0]}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[7] El staff del propio colegio también puede descargarlo (200)", r_pdf_staff.status_code == 200)
    comprobar("[7] El PDF servido al staff es el MISMO archivo ya almacenado (no se regeneró)",
              r_pdf_staff.content == r_pdf_alumno.content)

    hist_persona = exigir(requests.get(f"{API}/educativo/personas/{persona_ok}/informes",
                                       headers=h_a, timeout=30), 200, "Historial de informes")
    comprobar("[8] El historial del estudiante incluye esta aplicación, con es_alerta=False",
              len(hist_persona) == 1 and hist_persona[0]["es_alerta"] is False)

    # ==================================================================
    print("\n9-15 · Aplicación CON alerta (todo 'Casi todos los días' -> 27, Severo) + versionado")
    campana_alerta = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Alerta {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña alerta")
    persona_alerta = crear_persona_con_consentimiento(h_a, inst_a, sello, "AL")
    tok_alerta = matricular(h_a, campana_alerta["id"], persona_alerta)

    responder_phq9(tok_alerta, preg_phq9, [3] * 9)
    r = requests.post(f"{API}/educativo/examen/{tok_alerta}/finalizar", timeout=60)
    comprobar("[9] Finaliza correctamente (200)", r.status_code == 200, f"status {r.status_code}")
    comprobar("[9] No se devuelve ningún diagnóstico al alumno (retenido)", r.json() == [])

    insc_alerta = sql_uno("select id, resultado_visible_alumno, informe_liberado from edu_inscripciones where token=:t", t=tok_alerta)
    comprobar("[10] resultado_visible_alumno=False, informe_liberado=False", insc_alerta[1] is False and insc_alerta[2] is False)
    nivel_alerta = sql_uno("select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_alerta[0])
    comprobar("[10] Puntaje 27/27 cae en un tramo CON alerta", nivel_alerta[1] is True, f"nivel={nivel_alerta[0]!r}")

    meta_alerta = esperar_informe(h_a, insc_alerta[0])
    comprobar("[11] El informe se generó IGUAL aunque el caso esté retenido (existencia != autorización)",
              meta_alerta.get("existe") is True)
    checksum_v1_antes = sql_uno(
        "select checksum_sha256 from edu_informe_versiones where informe_id=:inf and numero_version=1",
        inf=meta_alerta["informe_id"])[0]

    r_pdf_alumno_bloqueado = requests.get(f"{API}/educativo/examen/{tok_alerta}/informe-pdf", timeout=60)
    comprobar("[12] El alumno NO puede descargar su PDF (403, retenido por alerta)",
              r_pdf_alumno_bloqueado.status_code == 403, f"status {r_pdf_alumno_bloqueado.status_code}")

    r_pdf_staff_alerta = requests.get(f"{API}/educativo/inscripciones/{insc_alerta[0]}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[12] El staff SÍ puede verlo para revisarlo (200) aunque no esté liberado",
              r_pdf_staff_alerta.status_code == 200)

    exigir(requests.patch(f"{API}/educativo/inscripciones/{insc_alerta[0]}/liberar-informe",
                          json={}, headers=h_a, timeout=30), 200, "Liberar informe")
    r_pdf_tras_liberar = requests.get(f"{API}/educativo/examen/{tok_alerta}/informe-pdf", timeout=60)
    comprobar("[13] Tras liberar, el alumno SÍ puede descargar su PDF (200)",
              r_pdf_tras_liberar.status_code == 200, f"status {r_pdf_tras_liberar.status_code}")

    r_reemitir_sin_motivo = requests.post(f"{API}/educativo/inscripciones/{insc_alerta[0]}/informe/reemitir",
                                          json={"motivo": ""}, headers=h_a, timeout=30)
    comprobar("[14] Reemitir sin motivo válido se rechaza (422)", r_reemitir_sin_motivo.status_code == 422)

    reemision = exigir(requests.post(f"{API}/educativo/inscripciones/{insc_alerta[0]}/informe/reemitir",
                                     json={"motivo": "Corrección del logo institucional en el PDF"},
                                     headers=h_a, timeout=30), 200, "Reemitir informe")
    comprobar("[15] La reemisión crea la versión 2, no sobreescribe la 1", reemision["numero_version"] == 2)

    meta_tras_reemitir = requests.get(f"{API}/educativo/inscripciones/{insc_alerta[0]}/informe", headers=h_a, timeout=30).json()
    comprobar("[15] version_actual pasa a 2 y quedan 2 versiones en el historial",
              meta_tras_reemitir["version_actual"] == 2 and len(meta_tras_reemitir["versiones"]) == 2)
    v2 = next(v for v in meta_tras_reemitir["versiones"] if v["numero_version"] == 2)
    comprobar("[15] La v2 queda trazada: motivo + usuario que la pidió",
              v2["motivo_version"] == "Corrección del logo institucional en el PDF" and v2["generado_por_usuario_id"] is not None)

    fila_v1 = sql_uno(
        "select v.storage_key from edu_informe_versiones v join edu_informes i on i.id = v.informe_id "
        "where i.inscripcion_id=:i and v.numero_version=1", i=insc_alerta[0])
    from core.storage import obtener_storage_service
    comprobar("[15] La versión 1 SIGUE existiendo en storage tras reemitir (nunca se borra una versión histórica)",
              obtener_storage_service().existe(fila_v1[0]))

    # ==================================================================
    print("\n16-18 · Interpretación incompleta (prueba sin baremo cargado)")
    prueba_sb = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-SINBAREMO-{sello}", "nombre_publico": "Prueba sin baremo",
        "escala_minima": 0, "escala_maxima": 3}, headers=h_a, timeout=30), 200, "Prueba sin baremo")
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_sb["id"], "dimensiones": [{"nombre": "SinBaremo"}],
        "preguntas": [{"texto_pregunta": "Ítem único", "orden": 1, "nombre_dimension": "SinBaremo",
                       "opciones": [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]}]},
        headers=h_a, timeout=30), 200, "Carga sin baremo")
    detalle_sb = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_sb['id']}/completa", headers=h_a, timeout=30), 200, "Detalle sin baremo")
    preg_sb = {p["orden"]: p for p in detalle_sb["dimensiones"][0]["preguntas"]}

    campana_sb = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_sb["id"], "nombre_grupo": f"{PREFIJO} SinBaremo {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña sin baremo")
    persona_sb = crear_persona_con_consentimiento(h_a, inst_a, sello, "SB")
    tok_sb = matricular(h_a, campana_sb["id"], persona_sb)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_sb}", json={
        "nombre_completo": "Alumno SB", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar sin baremo")
    op_id = next(o["id"] for o in preg_sb[1]["opciones"] if o["valor_puntuacion"] == 1)
    exigir(requests.post(f"{API}/educativo/examen/{tok_sb}/guardar",
                         json={"respuestas": [{"pregunta_id": preg_sb[1]["id"], "opcion_id": op_id}]}, timeout=30), 200, "Guardar sin baremo")
    exigir(requests.post(f"{API}/educativo/examen/{tok_sb}/finalizar", timeout=60), 200, "Finalizar sin baremo")

    insc_sb = sql_uno("select id, estado_interpretacion, resultado_visible_alumno from edu_inscripciones where token=:t", t=tok_sb)
    comprobar("[16] estado_interpretacion='incompleta', NUNCA 'sin riesgo'",
              insc_sb[1] == "incompleta" and insc_sb[2] is False)

    meta_sb = esperar_informe(h_a, insc_sb[0])
    comprobar("[17] El informe se genera IGUAL cuando la interpretación está incompleta", meta_sb.get("existe") is True)
    r_pdf_sb = requests.get(f"{API}/educativo/examen/{tok_sb}/informe-pdf", timeout=60)
    comprobar("[18] El alumno no puede descargarlo (403, retenido por falta de baremo)", r_pdf_sb.status_code == 403)

    # ==================================================================
    print("\n19-23 · Seguridad multi-tenant: B no ve nada de A")
    r = requests.get(f"{API}/educativo/inscripciones/{insc_ok[0]}/informe-pdf", headers=h_b, timeout=30)
    comprobar("[19] B no puede descargar el PDF de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/educativo/inscripciones/{insc_ok[0]}/informe", headers=h_b, timeout=30)
    comprobar("[20] B no puede ver la metadata del informe de A (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/educativo/inscripciones/{insc_ok[0]}/informe/reemitir",
                      json={"motivo": "intento cruzado"}, headers=h_b, timeout=30)
    comprobar("[21] B no puede reemitir el informe de A (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/educativo/personas/{persona_ok}/informes", headers=h_b, timeout=30)
    comprobar("[22] B no puede ver el historial de informes de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/educativo/inscripciones/999999999/informe-pdf", headers=h_a, timeout=30)
    comprobar("[23] Inscripción inexistente -> 404, no 500 ni filtración", r.status_code == 404, f"status {r.status_code}")

    # ==================================================================
    print("\n24-26 · Storage y trazabilidad")
    comprobar("[24] El MIME type persistido es application/pdf", meta_ok["versiones"][0]["mime_type"] == "application/pdf")
    checksum_v1_despues = sql_uno(
        "select checksum_sha256 from edu_informe_versiones where informe_id=:inf and numero_version=1",
        inf=meta_alerta["informe_id"])[0]
    comprobar("[25] El checksum de la v1 NO cambió tras reemitir (una versión histórica es inmutable)",
              checksum_v1_despues == checksum_v1_antes)
    comprobar("[26] Cada aplicación tiene su PROPIO informe (informe_id de la sin-alerta != el de la con-alerta)",
              meta_ok["informe_id"] != meta_alerta["informe_id"])

    # ==================================================================
    print("\n27 · Regresión ligera: dimensiones_sin_baremo queda registrada, no se pierde")
    dims_sb = sql_uno("select dimensiones_sin_baremo from edu_inscripciones where id=:i", i=insc_sb[0])[0]
    comprobar("[27] dimensiones_sin_baremo trae el nombre de la dimensión sin baremo", dims_sb and "SinBaremo" in dims_sb)

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
            delete from edu_informe_versiones where informe_id in (
                select i.id from edu_informes i
                join edu_inscripciones ins on ins.id = i.inscripcion_id
                join edu_evaluaciones ev on ev.id = ins.evaluacion_id
                where ev.nombre_grupo like '{PREFIJO}%'
            )"""))
        c.execute(text(f"""
            delete from edu_informes where inscripcion_id in (
                select ins.id from edu_inscripciones ins
                join edu_evaluaciones ev on ev.id = ins.evaluacion_id
                where ev.nombre_grupo like '{PREFIJO}%'
            )"""))
        c.execute(text(f"delete from edu_diagnosticos_alumno where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_resultados_dimensiones where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_respuestas_alumno where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_inscripciones where evaluacion_id in "
                       f"(select id from edu_evaluaciones where nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_evaluaciones where nombre_grupo like '{PREFIJO}%'"))
        c.execute(text(f"delete from consentimientos_informados where persona_id in "
                       f"(select id from personas where nombres like '{PREFIJO}%')"))
        c.execute(text(f"delete from personas where nombres like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from edu_baremos where dimension_id in (
                select d.id from edu_dimensiones d join edu_pruebas p on p.id = d.prueba_id
                where p.nombre_tecnico like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_opciones where pregunta_id in (
                select q.id from edu_preguntas q join edu_pruebas p on p.id = q.prueba_id
                where p.nombre_tecnico like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_preguntas where prueba_id in (
                select id from edu_pruebas where nombre_tecnico like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_dimensiones where prueba_id in (
                select id from edu_pruebas where nombre_tecnico like '{PREFIJO}%')"""))
        c.execute(text(f"delete from edu_pruebas where nombre_tecnico like '{PREFIJO}%'"))
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
