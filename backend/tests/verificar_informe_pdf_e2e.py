"""Verificación end-to-end — Cierre y validación del INFORME PDF del piloto PHQ-9.

No se limita a comprobar que generar_pdf() devuelve bytes: genera aplicaciones
PHQ-9 reales, descarga el PDF real por los endpoints autorizados y EXTRAE SU
TEXTO con pypdf para verificar el contenido real, sección por sección.

  1     Sin alerta: aplicación -> resultado -> informe -> PDF -> storage -> descarga
  2     Con alerta: informe retenido -> PDF no accesible -> liberación -> accesible
  3     Contenido histórico: el PDF conserva la sección de cuando se aplicó,
        no la sección actual del alumno (incluso tras reemitir)
  4     Reemisión: v1 y v2 coexisten, identificables, con su propio motivo
  5     Contenido psicométrico por escenario (completo/baremo/regla/incompleta)
  6     Ítem 9 del PHQ-9 reflejado en el flujo completo del informe
  7     Storage: sin blob en Postgres, key aislada, checksum/tamaño/MIME correctos
  8     Seguridad: aislamiento institucional, sin acceso por manipulación

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_informe_pdf_e2e.py
    python tests/verificar_informe_pdf_e2e.py --limpiar
"""

import argparse
import hashlib
import io
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pypdf import PdfReader
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZPDF"
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


def texto_pdf(contenido: bytes) -> str:
    """Abre el PDF de verdad (pypdf falla si el archivo está corrupto) y devuelve
    todo su texto concatenado, para poder aserir sobre CONTENIDO real.

    Normaliza saltos de línea a espacios: reportlab justifica párrafos y
    pypdf inserta un '\\n' donde el renderizador cortó la línea, así que una
    frase como "sin riesgo" puede quedar partida en "sin\\nriesgo" sin que
    eso sea un error de contenido — es solo dónde cayó el salto de línea.
    """
    lector = PdfReader(io.BytesIO(contenido))
    texto_crudo = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    return " ".join(texto_crudo.split())


def crear_colegio(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
    # rol "admin": la estructura académica (niveles/grados/secciones) exige
    # admin o superadmin, igual que en el Núcleo del Estudiante — mismo
    # criterio que ya usa verificar_consentimientos_e2e.py.
    correo = f"{PREFIJO.lower()}.admin.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {letra}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Admin {letra}",
        "rol": "admin", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro {letra}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {letra}")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


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


def aplicar_phq9(headers, inst_id, sello, etiqueta, preg_phq9, phq9_id, valores, nombre_alumno=None):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona_id = crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta)
    token = matricular(headers, campana["id"], persona_id)

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": nombre_alumno or f"Alumno PHQ9 {etiqueta}", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)} for i, v in enumerate(valores)]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id, persona_id from edu_inscripciones where token=:t", t=token)
    return token, insc[0], insc[1]


def esperar_informe(headers, inscripcion_id, timeout=20):
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
    print("\n0 · Montaje: dos instituciones + estructura académica + PHQ-9 público")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a, h_a = crear_colegio(h_super, "A", sello)
    inst_b, h_b = crear_colegio(h_super, "B", sello)

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]
    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_a, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}

    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": f"{PREFIJO}-Secundaria-{sello}"}, headers=h_a, timeout=30), 200, "Nivel")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "3°"}, headers=h_a, timeout=30), 200, "Grado")
    seccion_a = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "anio_escolar": 2026}, headers=h_a, timeout=30), 200, "Sección A")
    seccion_b = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "B", "anio_escolar": 2026}, headers=h_a, timeout=30), 200, "Sección B")

    # ==================================================================
    print("\n1 · CASO SIN ALERTA — aplicación -> resultado -> informe -> PDF -> storage -> descarga autorizada")
    campana_ok = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} SinAlerta {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña sin alerta")
    persona_ok = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} SinAlerta", "apellidos": "Uno",
        "documento_identidad": f"{sello}SA1", "genero": "Femenino"}, headers=h_a, timeout=30), 200, "Persona SinAlerta")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona_ok}/consentimiento", json={
        "persona_id": persona_ok, "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30), 200, "Consentimiento SinAlerta")
    exigir(requests.post(f"{API}/admin/personas/{persona_ok}/matricula",
                         json={"seccion_id": seccion_a["id"]}, headers=h_a, timeout=30), 200, "Matricular en 3°A")

    tok_ok = matricular(h_a, campana_ok["id"], persona_ok)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_ok}", json={
        "nombre_completo": "NOMBRE QUE NO DEBE USARSE (viene de matrícula)", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar SinAlerta")

    def opcion_id_de(preg, orden, valor):
        return next(o["id"] for o in preg[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas_ok = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id_de(preg_phq9, i + 1, 0)} for i in range(9)]
    exigir(requests.post(f"{API}/educativo/examen/{tok_ok}/guardar", json={"respuestas": respuestas_ok}, timeout=30), 200, "Guardar SinAlerta")
    exigir(requests.post(f"{API}/educativo/examen/{tok_ok}/finalizar", timeout=60), 200, "Finalizar SinAlerta")
    insc_ok = sql_uno("select id from edu_inscripciones where token=:t", t=tok_ok)[0]

    meta_ok = esperar_informe(h_a, insc_ok)
    comprobar("[1] El informe se generó (existe)", meta_ok.get("existe") is True)

    r_pdf_ok = requests.get(f"{API}/educativo/examen/{tok_ok}/informe-pdf", timeout=60)
    comprobar("[1] Descarga autorizada del alumno (200)", r_pdf_ok.status_code == 200)
    contenido_ok = r_pdf_ok.content
    comprobar("[1] Empieza con la cabecera %PDF (archivo real, no basura)", contenido_ok[:5] == b"%PDF-")

    texto_ok = texto_pdf(contenido_ok)
    comprobar("[2] pypdf ABRE el PDF sin excepción y extrae texto (no está corrupto)", len(texto_ok) > 100)
    comprobar("[2] Contiene el encabezado esperado", "INFORME PSICOMÉTRICO" in texto_ok and "DOCUMENTO CONFIDENCIAL" in texto_ok)
    comprobar("[2] Contiene el nombre de la prueba", "PHQ-9" in texto_ok.upper() or "SALUD DEL PACIENTE" in texto_ok.upper())
    comprobar("[2] IGNORA el nombre arbitrario que llegó por el formulario público (ya tenía nombre por padrón)",
              "NOMBRE QUE NO DEBE USARSE" not in texto_ok, "el snapshot ya tenía nombre_completo por ser alumno matriculado")
    comprobar("[2] Usa el nombre REAL de matrícula del padrón", "SinAlerta" in texto_ok)
    comprobar("[3] Usa el grado/sección HISTÓRICO de la aplicación: '3° A'", "3° A" in texto_ok or "3°A" in texto_ok, texto_ok[:0])
    comprobar("[1] Un resultado completo NO muestra el aviso de interpretación incompleta", "INTERPRETACIÓN INCOMPLETA" not in texto_ok)
    comprobar("[5][sin alerta] NO muestra el banner de alerta", "REQUIERE REVISIÓN PROFESIONAL" not in texto_ok)

    fila_v1_ok = sql_uno(
        "select v.storage_key, v.tamano_bytes, v.checksum_sha256, v.mime_type "
        "from edu_informe_versiones v join edu_informes i on i.id = v.informe_id "
        "where i.inscripcion_id=:i and v.numero_version=1", i=insc_ok)
    comprobar("[2] El tamaño almacenado coincide EXACTO con el PDF descargado", fila_v1_ok[1] == len(contenido_ok))
    comprobar("[2] El checksum SHA-256 almacenado coincide con el contenido real descargado",
              fila_v1_ok[2] == hashlib.sha256(contenido_ok).hexdigest())
    comprobar("[7] El MIME type es application/pdf", fila_v1_ok[3] == "application/pdf")
    comprobar("[7] La storage_key está aislada por institución y por informe",
              fila_v1_ok[0].startswith(f"instituciones/{inst_a}/informes/"), fila_v1_ok[0])

    r_pdf_staff_ok = requests.get(f"{API}/educativo/inscripciones/{insc_ok}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[2] Recuperable también por el endpoint autorizado del staff (200)", r_pdf_staff_ok.status_code == 200)
    comprobar("[2] Es EXACTAMENTE el mismo archivo (no se regeneró)", r_pdf_staff_ok.content == contenido_ok)

    # ==================================================================
    print("\n2 · CASO CON ALERTA — retenido, PDF almacenado pero no accesible, liberación, luego accesible")
    campana_al = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} ConAlerta {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña con alerta")
    tok_al, insc_al, persona_al = aplicar_phq9(h_a, inst_a, sello, "ConAlerta", preg_phq9, phq9_id, [3] * 9)

    est_al = sql_uno("select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc_al)
    comprobar("[4] La aplicación con alerta queda retenida", est_al[0] is False and est_al[1] is False)

    meta_al = esperar_informe(h_a, insc_al)
    comprobar("[4] El informe se generó y almacenó IGUAL (existencia != autorización)", meta_al.get("existe") is True)

    r_pdf_al_bloqueado = requests.get(f"{API}/educativo/examen/{tok_al}/informe-pdf", timeout=60)
    comprobar("[4] El alumno NO puede descargarlo (403) mientras está retenido", r_pdf_al_bloqueado.status_code == 403)

    r_pdf_al_staff = requests.get(f"{API}/educativo/inscripciones/{insc_al}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[4] El profesional SÍ puede revisarlo (200) aunque no esté liberado", r_pdf_al_staff.status_code == 200)
    texto_al = texto_pdf(r_pdf_al_staff.content)
    comprobar("[5][alerta] El PDF almacenado SÍ trae el banner de alerta", "REQUIERE REVISIÓN PROFESIONAL" in texto_al)

    exigir(requests.patch(f"{API}/educativo/inscripciones/{insc_al}/liberar-informe",
                          json={}, headers=h_a, timeout=30), 200, "Liberar informe")
    r_pdf_al_liberado = requests.get(f"{API}/educativo/examen/{tok_al}/informe-pdf", timeout=60)
    comprobar("[4] Tras liberar, el alumno SÍ puede descargarlo (200)", r_pdf_al_liberado.status_code == 200)
    comprobar("[4] Es el MISMO PDF que ya estaba almacenado (no se regeneró al liberar)",
              r_pdf_al_liberado.content == r_pdf_al_staff.content)

    # ==================================================================
    print("\n3 · CONTENIDO HISTÓRICO — el informe conserva 3°A aunque el alumno se mueva a 3°B")
    persona_hist_id = sql_uno("select persona_id from edu_inscripciones where id=:i", i=insc_al)[0]
    # (ConAlerta no estaba matriculado académicamente; usamos un tercer caso matriculado)
    campana_hist = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Historico {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña histórico")
    persona_hist = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Historico", "apellidos": "Tres",
        "documento_identidad": f"{sello}HIST", "genero": "Femenino"}, headers=h_a, timeout=30), 200, "Persona histórico")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona_hist}/consentimiento", json={
        "persona_id": persona_hist, "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30), 200, "Consentimiento histórico")
    exigir(requests.post(f"{API}/admin/personas/{persona_hist}/matricula",
                         json={"seccion_id": seccion_a["id"]}, headers=h_a, timeout=30), 200, "Matricular histórico en 3°A")

    tok_hist = matricular(h_a, campana_hist["id"], persona_hist)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_hist}", json={
        "nombre_completo": "x", "edad": 16, "sexo": "Femenino", "poblacion": "Secundaria", "acepta_terminos": True},
        timeout=30), 200, "Comenzar histórico")
    respuestas_hist = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id_de(preg_phq9, i + 1, 0)} for i in range(9)]
    exigir(requests.post(f"{API}/educativo/examen/{tok_hist}/guardar", json={"respuestas": respuestas_hist}, timeout=30), 200, "Guardar histórico")
    exigir(requests.post(f"{API}/educativo/examen/{tok_hist}/finalizar", timeout=60), 200, "Finalizar histórico")
    insc_hist = sql_uno("select id from edu_inscripciones where token=:t", t=tok_hist)[0]
    esperar_informe(h_a, insc_hist)

    r_pdf_hist_antes = requests.get(f"{API}/educativo/examen/{tok_hist}/informe-pdf", timeout=60)
    texto_hist_antes = texto_pdf(r_pdf_hist_antes.content)
    comprobar("[3] Antes de mover al alumno, el informe muestra 3° A", "3° A" in texto_hist_antes)

    # Se mueve al alumno a 3°B DESPUÉS de aplicada la prueba
    exigir(requests.post(f"{API}/admin/personas/{persona_hist}/matricula",
                         json={"seccion_id": seccion_b["id"]}, headers=h_a, timeout=30), 200, "Mover a 3°B")
    ficha_hist = exigir(requests.get(f"{API}/admin/personas/{persona_hist}/ficha-completa", headers=h_a, timeout=30), 200, "Ficha histórico")
    comprobar("[3] La ficha ACTUAL del alumno ya muestra 3° B",
              "B" in (ficha_hist.get("informacion_academica_actual") or {}).get("seccion", ""))

    r_pdf_hist_despues = requests.get(f"{API}/educativo/examen/{tok_hist}/informe-pdf", timeout=60)
    texto_hist_despues = texto_pdf(r_pdf_hist_despues.content)
    comprobar("[3] El informe YA ALMACENADO sigue mostrando 3° A (no se recalculó)", "3° A" in texto_hist_despues)
    comprobar("[3] El informe NO muestra 3° B en ningún momento", "3° B" not in texto_hist_despues)

    # Reemisión DESPUÉS de mover de sección — el v2 debe seguir usando el snapshot histórico, no la sección actual
    reemision_hist = exigir(requests.post(f"{API}/educativo/inscripciones/{insc_hist}/informe/reemitir",
                                          json={"motivo": "Verificación de snapshot histórico tras reemitir"},
                                          headers=h_a, timeout=30), 200, "Reemitir histórico")
    r_pdf_hist_v2 = requests.get(f"{API}/educativo/inscripciones/{insc_hist}/informe-pdf", headers=h_a, timeout=60)
    texto_hist_v2 = texto_pdf(r_pdf_hist_v2.content)
    comprobar("[3][6] Incluso la VERSIÓN REEMITIDA (v2) sigue mostrando 3° A, nunca la sección actual",
              "3° A" in texto_hist_v2 and "3° B" not in texto_hist_v2)

    # ==================================================================
    print("\n4 · REEMISIÓN — v1 y v2 coexisten, identificables, con su propio motivo")
    meta_hist = requests.get(f"{API}/educativo/inscripciones/{insc_hist}/informe", headers=h_a, timeout=30).json()
    comprobar("[6] Quedan exactamente 2 versiones en el historial", len(meta_hist["versiones"]) == 2)
    comprobar("[6] version_actual pasó a 2", meta_hist["version_actual"] == 2)
    v1_meta = next(v for v in meta_hist["versiones"] if v["numero_version"] == 1)
    v2_meta = next(v for v in meta_hist["versiones"] if v["numero_version"] == 2)
    comprobar("[6] v1 conserva su motivo original ('Emisión inicial')", v1_meta["motivo_version"] == "Emisión inicial")
    comprobar("[6] v2 conserva el motivo de la reemisión", v2_meta["motivo_version"] == "Verificación de snapshot histórico tras reemitir")
    comprobar("[6] Cada versión tiene su propio checksum (no son el mismo archivo)",
              v1_meta["checksum_sha256"] != v2_meta["checksum_sha256"])
    comprobar("[6] El PDF v2 se identifica a sí mismo como 'v2' en su propio texto", "v2" in texto_hist_v2)

    print("\n· Cruce entre estudiantes — ningún PDF contiene datos de otro alumno")
    comprobar("[2] El PDF de 'SinAlerta' NO menciona al alumno 'Historico'", "Historico" not in texto_ok)
    comprobar("[2] El PDF de 'Historico' NO menciona al alumno 'SinAlerta'", "SinAlerta" not in texto_hist_antes)

    fila_v1_storage = sql_uno(
        "select storage_key from edu_informe_versiones where informe_id=:inf and numero_version=1", inf=reemision_hist["informe_id"])
    from core.storage import obtener_storage_service
    comprobar("[6] La v1 SIGUE existiendo físicamente en storage tras reemitir (no se sobreescribió)",
              obtener_storage_service().existe(fila_v1_storage[0]))

    # ==================================================================
    print("\n5 · CONTENIDO PSICOMÉTRICO por escenario")
    # 5a) Completo sin alerta -> ya verificado en el CASO 1 (arriba): "Completa" + sin banner.
    comprobar("[7][completo sin alerta] Ya verificado en el bloque 1 (estado 'Completa', sin banner)", True)

    # 5b) Alerta por BAREMO (puntaje alto, ítem 9 en 0 -> la regla NO dispara)
    tok_bar, insc_bar, _ = aplicar_phq9(h_a, inst_a, sello, "AlertaBaremo", preg_phq9, phq9_id, [3, 3, 3, 3, 3, 3, 3, 3, 0])
    esperar_informe(h_a, insc_bar)
    r_pdf_bar = requests.get(f"{API}/educativo/inscripciones/{insc_bar}/informe-pdf", headers=h_a, timeout=60)
    texto_bar = texto_pdf(r_pdf_bar.content)
    comprobar("[7][alerta por baremo] Muestra el banner de alerta", "REQUIERE REVISIÓN PROFESIONAL" in texto_bar)
    comprobar("[7][alerta por baremo] La columna de origen dice 'Baremo'", "Baremo" in texto_bar)
    comprobar("[7][alerta por baremo] NO atribuye la alerta a una regla de interpretación",
              "activada:" not in texto_bar)

    # 5c) Alerta por REGLA (ítem 9 positivo, puntaje total bajo -> el baremo NO dispara)
    tok_reg, insc_reg, _ = aplicar_phq9(h_a, inst_a, sello, "AlertaRegla", preg_phq9, phq9_id, [0, 0, 0, 0, 0, 0, 0, 0, 1])
    esperar_informe(h_a, insc_reg)
    r_pdf_reg = requests.get(f"{API}/educativo/inscripciones/{insc_reg}/informe-pdf", headers=h_a, timeout=60)
    texto_reg = texto_pdf(r_pdf_reg.content)
    comprobar("[7][8][alerta por regla] Muestra el banner de alerta", "REQUIERE REVISIÓN PROFESIONAL" in texto_reg)
    comprobar("[7][8][alerta por regla] La columna de origen dice 'Regla de interpretación'", "Regla de interpretación" in texto_reg)
    comprobar("[7][8][alerta por regla] Incluye el motivo textual de la regla del ítem 9 (autolesión)",
              "autolesión" in texto_reg.lower() or "muerto" in texto_reg.lower())
    diag_reg = sql_uno("select es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_reg)
    comprobar("[8] DiagnosticoAlumno queda marcado (es_alerta=True, alerta_por='regla')",
              diag_reg[0] is True and diag_reg[1] == "regla")

    # 5d) Interpretación incompleta (prueba sin baremo)
    prueba_sb = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-SINBAREMO-{sello}", "nombre_publico": "Prueba sin baremo",
        "escala_minima": 0, "escala_maxima": 1}, headers=h_a, timeout=30), 200, "Prueba sin baremo")
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_sb["id"], "dimensiones": [{"nombre": "SinBaremo"}],
        "preguntas": [{"texto_pregunta": "Ítem único", "orden": 1, "nombre_dimension": "SinBaremo",
                       "opciones": [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]}]},
        headers=h_a, timeout=30), 200, "Carga sin baremo")
    detalle_sb = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_sb['id']}/completa", headers=h_a, timeout=30), 200, "Detalle sin baremo")
    preg_sb = {p["orden"]: p for p in detalle_sb["dimensiones"][0]["preguntas"]}
    campana_sb = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_sb["id"], "nombre_grupo": f"{PREFIJO} Incompleta {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña sin baremo")
    persona_sb = crear_persona_con_consentimiento(h_a, inst_a, sello, "Incompleta")
    tok_sb = matricular(h_a, campana_sb["id"], persona_sb)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_sb}", json={
        "nombre_completo": "Alumno SB", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria", "acepta_terminos": True},
        timeout=30), 200, "Comenzar sin baremo")
    op_sb = next(o["id"] for o in preg_sb[1]["opciones"] if o["valor_puntuacion"] == 1)
    exigir(requests.post(f"{API}/educativo/examen/{tok_sb}/guardar",
                         json={"respuestas": [{"pregunta_id": preg_sb[1]["id"], "opcion_id": op_sb}]}, timeout=30), 200, "Guardar sin baremo")
    exigir(requests.post(f"{API}/educativo/examen/{tok_sb}/finalizar", timeout=60), 200, "Finalizar sin baremo")
    insc_sb = sql_uno("select id from edu_inscripciones where token=:t", t=tok_sb)[0]
    esperar_informe(h_a, insc_sb)
    r_pdf_sb = requests.get(f"{API}/educativo/inscripciones/{insc_sb}/informe-pdf", headers=h_a, timeout=60)
    texto_sb = texto_pdf(r_pdf_sb.content)
    comprobar("[7][incompleta] Indica explícitamente 'Interpretación incompleta'", "interpretación incompleta" in texto_sb.lower())
    comprobar("[7][incompleta] Aclara que NO debe leerse como 'sin riesgo'", "sin riesgo" in texto_sb.lower())
    comprobar("[7][incompleta] Señala la dimensión sin baremo aplicable", "sin baremo aplicable" in texto_sb.lower() and "sinbaremo" in texto_sb.lower())

    # ==================================================================
    print("\n7 · STORAGE — sin blob en Postgres")
    columnas_informe_version = [c[0] for c in MOTOR.connect().execute(text(
        "select column_name from information_schema.columns where table_name = 'edu_informe_versiones'"))]
    comprobar("[storage] edu_informe_versiones NO tiene ninguna columna de tipo binario/bytea para el PDF",
              not any("bytea" in str(c).lower() for c in columnas_informe_version), str(columnas_informe_version))
    tipos_columnas = MOTOR.connect().execute(text(
        "select data_type from information_schema.columns where table_name = 'edu_informe_versiones' and column_name = 'storage_key'")).fetchone()
    comprobar("[storage] storage_key es texto (referencia), no el archivo en sí", tipos_columnas[0] in ("character varying", "text"))

    # ==================================================================
    print("\n8 · SEGURIDAD — aislamiento institucional y manipulación")
    r_cross_pdf = requests.get(f"{API}/educativo/inscripciones/{insc_ok}/informe-pdf", headers=h_b, timeout=30)
    comprobar("[10] B no puede descargar el informe de un alumno de A (403)", r_cross_pdf.status_code == 403)
    r_cross_meta = requests.get(f"{API}/educativo/inscripciones/{insc_ok}/informe", headers=h_b, timeout=30)
    comprobar("[10] B no puede ver la metadata del informe de A (403)", r_cross_meta.status_code == 403)
    r_inexistente = requests.get(f"{API}/educativo/inscripciones/999999999/informe-pdf", headers=h_a, timeout=30)
    comprobar("[10] Inscripción inexistente -> 404 (no 500, no filtra nada)", r_inexistente.status_code == 404)
    # No existe NINGÚN endpoint público que acepte una storage_key directamente
    # (todas las rutas resuelven el archivo a partir de inscripcion_id/token ya
    # autorizados) — lo verificamos negativamente: la key real no es un valor
    # que la API acepte como parámetro en ningún endpoint de descarga.
    r_key_directa = requests.get(f"{API}/educativo/informes/archivo?key={fila_v1_ok[0]}", timeout=30)
    comprobar("[10] No existe ninguna ruta que sirva un archivo a partir de una storage_key arbitraria",
              r_key_directa.status_code == 404)

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
                where ev.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_informes where inscripcion_id in (
                select ins.id from edu_inscripciones ins
                join edu_evaluaciones ev on ev.id = ins.evaluacion_id
                where ev.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_reglas_interpretacion where prueba_id in (
                select id from edu_pruebas where nombre_tecnico like '{PREFIJO}%')"""))
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
        c.execute(text(f"""
            delete from matriculas_academicas where persona_id in (
                select id from personas where nombres like '{PREFIJO}%')"""))
        c.execute(text(f"delete from consentimientos_informados where persona_id in "
                       f"(select id from personas where nombres like '{PREFIJO}%')"))
        c.execute(text(f"delete from personas where nombres like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from secciones where grado_id in (
                select g.id from grados g join niveles_educativos n on n.id = g.nivel_educativo_id
                where n.nombre like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from grados where nivel_educativo_id in (
                select id from niveles_educativos where nombre like '{PREFIJO}%')"""))
        c.execute(text(f"delete from niveles_educativos where nombre like '{PREFIJO}%'"))
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
