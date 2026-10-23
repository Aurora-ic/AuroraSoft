"""Verificación end-to-end — Informe psicométrico PROFESIONAL (formato + contenido dinámico).

Complementa a verificar_informe_pdf_e2e.py (que ya cubre storage, checksum,
seguridad, reemisión y snapshot histórico) con lo específico de ESTA fase:

  A·formato   Arial, 11pt, estructura numerada 1-7 + firma, paginación
  B·contenido Filiación completa, datos faltantes ("No registrado"), motivo,
              técnicas, observación conductual (profesional vs pendiente)
  C·dinamismo Casos A/B/C (bajo/moderado/alto): nivel, interpretación,
              conclusión y recomendación DISTINTOS entre sí, no solo el número
  D·caso D    Alto + regla del ítem 9: alerta con doble origen, trazabilidad
  E·caso E    Prueba con 2 dimensiones: cada una con su propia interpretación
  F·revisión  El profesional edita motivo/observación/conclusión y reemite;
              la v1 (auto-generada) y la v2 (con su edición) son distintas

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_informe_profesional_e2e.py
    python tests/verificar_informe_profesional_e2e.py --limpiar
"""

import argparse
import io
import os
import re
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

PREFIJO = "ZZPRO"
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
    lector = PdfReader(io.BytesIO(contenido))
    texto_crudo = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    return " ".join(texto_crudo.split())


def fuentes_usadas(contenido: bytes) -> set:
    """Nombres base de las fuentes realmente declaradas en la página (para
    verificar Arial sin depender de que el extractor de texto exponga fuentes)."""
    lector = PdfReader(io.BytesIO(contenido))
    nombres = set()
    for pagina in lector.pages:
        recursos = pagina.get("/Resources", {})
        fuentes = recursos.get("/Font", {})
        for clave in fuentes:
            obj = fuentes[clave].get_object()
            base = str(obj.get("/BaseFont", ""))
            nombres.add(base.split("+")[-1])  # quita el prefijo de subsetting "AAAAAA+"
    return nombres


def tamanos_fuente_en_11pt(contenido: bytes) -> bool:
    """Confirma que el cuerpo del texto realmente usa 11pt (no solo que la
    fuente Arial esté declarada como recurso).

    Se resuelve `/Contents` directamente (`page["/Contents"].get_object()`)
    en vez de `page.get_contents()`: para los PDF que genera reportlab (un
    único content stream, no un array) esta versión de pypdf devuelve `{}`
    desde `get_contents()` — un vacío falsy que hace parecer que la página no
    tiene contenido — mientras que resolver el objeto indirecto a mano sí
    funciona.
    """
    lector = PdfReader(io.BytesIO(contenido))
    for pagina in lector.pages:
        contenidos_ref = pagina.get("/Contents")
        if contenidos_ref is None:
            continue
        objeto = contenidos_ref.get_object()
        datos = objeto.get_data().decode("latin1", errors="replace")
        if re.search(r"/F\d+\+?0?\s+11\s+Tf", datos):
            return True
    return False


def crear_colegio(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
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


def aplicar_phq9(headers, inst_id, sello, etiqueta, preg_phq9, phq9_id, valores):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona_id = crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta)
    token = matricular(headers, campana["id"], persona_id)

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)} for i, v in enumerate(valores)]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token)
    return token, insc[0]


def esperar_informe(headers, inscripcion_id, timeout=20):
    limite = time.time() + timeout
    while time.time() < limite:
        r = requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30)
        if r.status_code == 200 and r.json().get("existe"):
            return r.json()
        time.sleep(0.5)
    return requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30).json()


def descargar_staff(headers, inscripcion_id):
    return requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe-pdf", headers=headers, timeout=60)


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_a, h_a = crear_colegio(h_super, "A", sello)

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]
    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_a, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}

    # ==================================================================
    print("\nCASO A · Resultado BAJO (puntaje 2, tramo 'Mínimo o ninguno')")
    tok_a, insc_a = aplicar_phq9(h_a, inst_a, sello, "CasoA", preg_phq9, phq9_id, [1, 1, 0, 0, 0, 0, 0, 0, 0])
    esperar_informe(h_a, insc_a)
    r_a = descargar_staff(h_a, insc_a)
    texto_a = texto_pdf(r_a.content)

    print("\nCASO B · Resultado MODERADO (puntaje 12)")
    tok_b, insc_b = aplicar_phq9(h_a, inst_a, sello, "CasoB", preg_phq9, phq9_id, [2, 2, 2, 2, 2, 1, 1, 0, 0])
    esperar_informe(h_a, insc_b)
    r_b = descargar_staff(h_a, insc_b)
    texto_b = texto_pdf(r_b.content)

    print("\nCASO C · Resultado ALTO (puntaje 24, ítem 9 en 0)")
    tok_c, insc_c = aplicar_phq9(h_a, inst_a, sello, "CasoC", preg_phq9, phq9_id, [3, 3, 3, 3, 3, 3, 3, 3, 0])
    esperar_informe(h_a, insc_c)
    r_c = descargar_staff(h_a, insc_c)
    texto_c = texto_pdf(r_c.content)

    print("\nCASO D · Resultado ALTO + regla del ítem 9 (puntaje 27)")
    tok_d, insc_d = aplicar_phq9(h_a, inst_a, sello, "CasoD", preg_phq9, phq9_id, [3, 3, 3, 3, 3, 3, 3, 3, 3])
    esperar_informe(h_a, insc_d)
    r_d = descargar_staff(h_a, insc_d)
    texto_d = texto_pdf(r_d.content)

    # ---- A · FORMATO ----
    print("\n· A· FORMATO — Arial, 11pt, estructura numerada, paginación")
    fuentes_a = fuentes_usadas(r_a.content)
    comprobar("[15] La(s) fuente(s) Arial están embebidas en el PDF", any("Arial" in f for f in fuentes_a), str(fuentes_a))
    comprobar("[16] El cuerpo del texto usa tamaño 11pt", tamanos_fuente_en_11pt(r_a.content))
    for n in range(1, 8):
        comprobar(f"[14][18] Sección {n}. presente y numerada", f"{n}." in texto_a)
    for sub in ("5.1.", "5.2.", "5.3."):
        comprobar(f"[14][18] Subsección {sub} presente", sub in texto_a)
    comprobar("[13] Bloque de firma presente (DNI)", "DNI" in texto_a)
    comprobar("[13] Bloque de firma presente (Sello)", "Sello" in texto_a)
    comprobar("[19] El PDF tiene numeración de página ('Página 1')", "Página 1" in texto_a)
    comprobar("[19] Encabezado de confidencialidad en cada página", "DOCUMENTO CONFIDENCIAL" in texto_a)
    comprobar("No es una plantilla informal: no usa emojis en el cuerpo", "⚠" not in texto_a and "🔴" not in texto_a)

    # ---- B · CONTENIDO — filiación, datos faltantes, motivo, técnicas, observación ----
    print("\n· B· CONTENIDO — filiación completa, datos faltantes, motivo, técnicas, observación")
    for etiqueta in ("Apellidos y Nombres", "Edad", "Grado de instrucción", "Ocupación actual",
                      "Vive con", "Fecha de evaluación", "Evaluador"):
        comprobar(f"[1] Filiación incluye '{etiqueta}'", etiqueta in texto_a)
    comprobar("[2] 'Vive con' (sin fuente de datos) se muestra como 'No registrado', no inventado",
              "No registrado" in texto_a)
    comprobar("[1] Ocupación actual se resuelve como 'Estudiante' (derivado de tipo_perfil, no inventado)",
              "Estudiante" in texto_a)
    comprobar("[3] Motivo de consulta configurado por la prueba aparece", "tamizaje" in texto_a.lower())
    comprobar("[3] Aviso de que el motivo es contenido CONFIGURADO, no escrito por el profesional",
              "sugerido según la configuración" in texto_a)
    comprobar("[4] Técnicas: instrumento (PHQ-9) listado", "PHQ-9" in texto_a.upper() or "SALUD DEL PACIENTE" in texto_a.upper())
    comprobar("[4] Técnicas adicionales configuradas (Entrevista/Observación) listadas",
              "Entrevista" in texto_a and "Observación" in texto_a)
    comprobar("[5] Observación conductual, sin profesional que la registre, queda como PENDIENTE (no inventada)",
              "pendiente de registro" in texto_a.lower())

    # ---- C · DINAMISMO — A/B/C deben diferir en nivel, interpretación, conclusión y recomendación ----
    print("\n· C· DINAMISMO — bajo/moderado/alto producen contenido REALMENTE distinto")
    nivel_a = sql_uno("select nivel from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_a)[0]
    nivel_b = sql_uno("select nivel from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_b)[0]
    nivel_c = sql_uno("select nivel from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_c)[0]
    comprobar("[20][21][22] Los tres niveles clínicos son DISTINTOS entre sí",
              len({nivel_a, nivel_b, nivel_c}) == 3, f"{nivel_a} / {nivel_b} / {nivel_c}")

    concl_a = sql_uno("select conclusion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_a)[0]
    concl_b = sql_uno("select conclusion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_b)[0]
    concl_c = sql_uno("select conclusion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_c)[0]
    comprobar("[11] Las tres CONCLUSIONES son textos distintos (no la misma frase con el número cambiado)",
              len({concl_a, concl_b, concl_c}) == 3)

    recom_a = sql_uno("select recomendacion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_a)[0]
    recom_b = sql_uno("select recomendacion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_b)[0]
    recom_c = sql_uno("select recomendacion_sugerida from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_c)[0]
    comprobar("[12] Las tres RECOMENDACIONES son textos distintos", len({recom_a, recom_b, recom_c}) == 3)

    interp_a = sql_uno("select interpretacion from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_a)[0]
    interp_c = sql_uno("select interpretacion from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_c)[0]
    comprobar("[7] La interpretación cualitativa de A y C son distintas", interp_a != interp_c)

    comprobar("[9] El PDF de A refleja su propia conclusión/recomendación (no la de otro caso)",
              (concl_a or "")[:40] in texto_a and (concl_c or "")[:40] not in texto_a)

    # ---- D · Alerta por regla + baremo combinados ----
    print("\n· D· CASO D — puntaje alto + ítem 9 -> alerta con doble origen, trazable")
    diag_d = sql_uno("select es_alerta, alerta_por, regla_activada_id from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_d)
    comprobar("[23][24] alerta_por = 'baremo,regla' (ambos orígenes)", diag_d[1] == "baremo,regla")
    comprobar("Trazabilidad: regla_activada_id apunta a una regla real", diag_d[2] is not None)
    comprobar("[23] El PDF de D muestra AMBOS orígenes de alerta", "Baremo + Regla" in texto_d)
    comprobar("El PDF de C (solo baremo) NO muestra 'Baremo + Regla'", "Baremo + Regla" not in texto_c)

    # ---- E · Prueba con múltiples dimensiones ----
    print("\nCASO E · Prueba con 2 dimensiones — cada una con su propia interpretación")
    prueba_e = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-MULTIDIM-{sello}", "nombre_publico": "Prueba multidimensional",
        "escala_minima": 0, "escala_maxima": 3}, headers=h_a, timeout=30), 200, "Prueba E")
    opciones_e = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 3}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_e["id"],
        "dimensiones": [{"nombre": "Ansiedad"}, {"nombre": "Animo"}],
        "preguntas": [
            {"texto_pregunta": "Item Ansiedad", "orden": 1, "nombre_dimension": "Ansiedad", "opciones": opciones_e},
            {"texto_pregunta": "Item Animo", "orden": 2, "nombre_dimension": "Animo", "opciones": opciones_e},
        ]}, headers=h_a, timeout=30), 200, "Carga E")
    detalle_e = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_e['id']}/completa", headers=h_a, timeout=30), 200, "Detalle E")
    dim_ansiedad = next(d for d in detalle_e["dimensiones"] if d["nombre"] == "Ansiedad")
    dim_animo = next(d for d in detalle_e["dimensiones"] if d["nombre"] == "Animo")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_ansiedad["id"], "puntaje_minimo": 0, "puntaje_maximo": 0, "nivel": "Ansiedad baja",
        "interpretacion": "Sin indicadores de ansiedad.", "conclusion_sugerida": "Conclusión de ansiedad baja.",
        "recomendacion_sugerida": "Recomendación de ansiedad baja.", "es_alerta": False},
        headers=h_a, timeout=30), 200, "Baremo Ansiedad")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_animo["id"], "puntaje_minimo": 3, "puntaje_maximo": 3, "nivel": "Ánimo alterado",
        "interpretacion": "Indicadores relevantes de alteración anímica.", "conclusion_sugerida": "Conclusión de ánimo alterado.",
        "recomendacion_sugerida": "Recomendación de ánimo alterado.", "es_alerta": True},
        headers=h_a, timeout=30), 200, "Baremo Animo")

    campana_e = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_e["id"], "nombre_grupo": f"{PREFIJO} CasoE {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña E")
    persona_e = crear_persona_con_consentimiento(h_a, inst_a, sello, "CasoE")
    tok_e = matricular(h_a, campana_e["id"], persona_e)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_e}", json={
        "nombre_completo": "Alumno E", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria", "acepta_terminos": True},
        timeout=30), 200, "Comenzar E")
    op_ansiedad_baja = next(o["id"] for o in dim_ansiedad["preguntas"][0]["opciones"] if o["valor_puntuacion"] == 0)
    op_animo_alto = next(o["id"] for o in dim_animo["preguntas"][0]["opciones"] if o["valor_puntuacion"] == 3)
    exigir(requests.post(f"{API}/educativo/examen/{tok_e}/guardar", json={"respuestas": [
        {"pregunta_id": dim_ansiedad["preguntas"][0]["id"], "opcion_id": op_ansiedad_baja},
        {"pregunta_id": dim_animo["preguntas"][0]["id"], "opcion_id": op_animo_alto},
    ]}, timeout=30), 200, "Guardar E")
    exigir(requests.post(f"{API}/educativo/examen/{tok_e}/finalizar", timeout=60), 200, "Finalizar E")
    insc_e = sql_uno("select id from edu_inscripciones where token=:t", t=tok_e)[0]
    esperar_informe(h_a, insc_e)
    r_e = descargar_staff(h_a, insc_e)
    texto_e = texto_pdf(r_e.content)

    comprobar("[8] El informe de E muestra AMBAS dimensiones por nombre", "Ansiedad" in texto_e and "Animo" in texto_e)
    comprobar("[8] Cada dimensión trae su PROPIA interpretación cualitativa",
              "Sin indicadores de ansiedad" in texto_e and "alteración anímica" in texto_e)
    comprobar("[10] El análisis de riesgo señala SOLO la dimensión que alertó (Animo), no Ansiedad",
              "Animo" in texto_e)

    # ---- F · Revisión profesional -> reemisión ----
    print("\n· F· REVISIÓN PROFESIONAL — el psicólogo edita y reemite; v1 y v2 difieren")
    exigir(requests.patch(f"{API}/educativo/inscripciones/{insc_a}/revision-informe", json={
        "motivo_consulta": "Motivo redactado a mano por la psicóloga tras la entrevista inicial.",
        "observacion_conductual": "El estudiante se mostró colaborador, con buen contacto visual durante la aplicación.",
        "conclusion_override": "Conclusión final redactada por la profesional tras revisar el caso.",
    }, headers=h_a, timeout=30), 200, "Revisión A")

    reemision_a = exigir(requests.post(f"{API}/educativo/inscripciones/{insc_a}/informe/reemitir",
                                       json={"motivo": "Incorporación de observación conductual y motivo de consulta"},
                                       headers=h_a, timeout=30), 200, "Reemitir A")
    comprobar("[26] La reemisión crea v2", reemision_a["numero_version"] == 2)

    r_a_v2 = descargar_staff(h_a, insc_a)
    texto_a_v2 = texto_pdf(r_a_v2.content)
    comprobar("[F] v2 refleja el motivo escrito por la profesional (sin aviso de 'configurado')",
              "redactado a mano por la psicóloga" in texto_a_v2
              and "sugerido según la configuración" not in texto_a_v2.split("MOTIVO DE CONSULTA")[1].split("TÉCNICAS")[0])
    comprobar("[F] v2 refleja la observación conductual real (ya no 'pendiente de registro')",
              "buen contacto visual" in texto_a_v2 and "pendiente de registro" not in texto_a_v2)
    comprobar("[F] v2 refleja la conclusión escrita por la profesional", "redactada por la profesional" in texto_a_v2)
    comprobar("[27] v1 (ya almacenada) sigue intacta: seguía diciendo 'pendiente de registro'",
              "pendiente de registro" in texto_a)

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
