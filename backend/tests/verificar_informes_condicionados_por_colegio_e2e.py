"""Verificación end-to-end de la pregunta central de esta ronda de sesiones:
¿puede la MISMA prueba (PHQ-9) producir, de verdad, un documento con
estructura y formato distintos según el colegio, en vez de un único informe
impuesto por la plataforma?

Monta DOS instituciones reales, cada una con su propia PlantillaDocumento
(secciones distintas, tipografía distinta) y el enganche automático activado
(PlantillaDocumento.generar_automaticamente_al_finalizar_examen), aplica el
MISMO PHQ-9 con la MISMA respuesta en cada una, y confirma contra los dos PDF
reales generados:

  1   Colegio A ("Informe Breve"): 3 secciones (encabezado, resultados_prueba,
      firma), Arial 11pt. Su PDF NO trae "DATOS DE FILIACIÓN" ni ningún texto
      libre institucional -- esas secciones no existen en su plantilla.
  2   Colegio B ("Informe Extendido"): 5 secciones (encabezado,
      datos_filiacion, resultados_prueba, texto_libre, firma), Times-Roman
      12pt. Su PDF SÍ trae "DATOS DE FILIACIÓN" y el texto libre propio que
      ese colegio configuró.
  3   Ambos PDF, pese a tener estructuras distintas, muestran el mismo
      resultado real (mismo nivel PHQ-9) en su sección resultados_prueba --
      la diferencia es de diseño/estructura, nunca del dato subyacente.
  4   El informe psicométrico fijo (core/pdf_generator.py, el de
      finalizar_examen_seguro) es, en cambio, IDÉNTICO en estructura para
      los dos colegios -- confirma que lo que varía es el motor de
      documentos configurable, nunca el informe psicométrico de la Sección 5.
  5   Las dos PlantillaDocumento quedan con tipografía realmente distinta en
      la base de datos (no solo "distinta a simple vista").

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_informes_condicionados_por_colegio_e2e
    python -m tests.verificar_informes_condicionados_por_colegio_e2e --limpiar
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
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from pypdf import PdfReader  # noqa: E402
from core.storage import obtener_storage_service  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZCONDIC"
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


def sql_ejecutar(consulta, **p):
    with MOTOR.begin() as c:
        c.execute(text(consulta), p)


def leer_pdf_de_version(numero_version, documento_id):
    fila = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones "
        "WHERE documento_institucional_id=:d AND numero_version=:n",
        d=documento_id, n=numero_version,
    )
    return obtener_storage_service().leer(fila.storage_key)


def texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    crudo = " ".join((p.extract_text() or "") for p in lector.pages)
    return re.sub(r"\s+", " ", crudo)


def esperar_documento_de_plantilla(plantilla_id, persona_id, timeout=20):
    limite = time.time() + timeout
    fila = None
    while time.time() < limite:
        fila = sql_uno(
            "SELECT id, version_actual FROM documentos_institucionales "
            "WHERE plantilla_documento_id=:p AND id IN "
            "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:per) "
            "ORDER BY id DESC LIMIT 1",
            p=plantilla_id, per=persona_id,
        )
        if fila and fila.version_actual is not None:
            return fila
        time.sleep(0.5)
    return fila


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje: dos colegios, cada uno con su propia PlantillaDocumento")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    phq9 = exigir(requests.get(f"{API}/educativo/pruebas/", headers=h_super, timeout=30), 200, "catálogo pruebas")
    phq9_id = next(p["id"] for p in phq9 if p["nombre_tecnico"] == "PHQ-9")

    def _crear_colegio(nombre):
        inst_id = exigir(requests.post(f"{API}/instituciones/", json={
            "nombre": f"{PREFIJO} {nombre} {sello}"}, headers=h_super, timeout=30), 201, f"Institución {nombre}")["id"]
        h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.{nombre.lower()}.psi.{sello}@ejemplo.com",
                                     f"{PREFIJO} {nombre} Psicóloga", "psicologo", inst_id)
        return inst_id, h_psi

    inst_a, h_psi_a = _crear_colegio("A")
    inst_b, h_psi_b = _crear_colegio("B")

    tipo_a = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_a_{sello}", "nombre": f"{PREFIJO} Informe Breve",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo A")
    tipo_b = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_b_{sello}", "nombre": f"{PREFIJO} Informe Extendido",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo B")

    # Colegio A: plantilla MÍNIMA -- Arial 11pt, 3 secciones, sin filiación ni texto libre.
    plantilla_a = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_a["id"], "nombre": f"{PREFIJO} Breve {sello}",
        "fuente": "Arial", "tamano_pt": 11, "generar_automaticamente_al_finalizar_examen": True,
    }, headers=h_super, timeout=30), 200, "crear plantilla A")["id"]
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_a}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
    }, headers=h_super, timeout=30), 200, "sección A: encabezado")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_a}/secciones", json={
        "orden": 1, "tipo_seccion": "resultados_prueba", "titulo": "Resultado",
    }, headers=h_super, timeout=30), 200, "sección A: resultados_prueba")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_a}/secciones", json={
        "orden": 2, "tipo_seccion": "firma", "titulo": "Firma",
    }, headers=h_super, timeout=30), 200, "sección A: firma")

    # Colegio B: plantilla EXTENDIDA -- Times-Roman 12pt, 5 secciones, con
    # filiación y una conclusión institucional en texto libre propia.
    plantilla_b = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_b, "tipo_documento_id": tipo_b["id"], "nombre": f"{PREFIJO} Extendida {sello}",
        "fuente": "Times-Roman", "tamano_pt": 12, "generar_automaticamente_al_finalizar_examen": True,
    }, headers=h_super, timeout=30), 200, "crear plantilla B")["id"]
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_b}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
    }, headers=h_super, timeout=30), 200, "sección B: encabezado")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_b}/secciones", json={
        "orden": 1, "tipo_seccion": "datos_filiacion", "titulo": "Datos de Filiación",
    }, headers=h_super, timeout=30), 200, "sección B: datos_filiacion")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_b}/secciones", json={
        "orden": 2, "tipo_seccion": "resultados_prueba", "titulo": "Resultado",
    }, headers=h_super, timeout=30), 200, "sección B: resultados_prueba")
    seccion_texto_b = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_b}/secciones", json={
        "orden": 3, "tipo_seccion": "texto_libre", "titulo": "Conclusión Institucional",
    }, headers=h_super, timeout=30), 200, "sección B: texto_libre")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_b}/secciones", json={
        "orden": 4, "tipo_seccion": "firma", "titulo": "Firma",
    }, headers=h_super, timeout=30), 200, "sección B: firma")

    comprobar("[montaje] Plantilla A y B quedan con tipografía REALMENTE distinta en la BD",
              sql_uno("SELECT fuente, tamano_pt FROM documentos_plantillas WHERE id=:i", i=plantilla_a) !=
              sql_uno("SELECT fuente, tamano_pt FROM documentos_plantillas WHERE id=:i", i=plantilla_b))

    def _aplicar_phq9(institucion_id, h_psi, nombre_alumno, valor_respuesta):
        persona = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": institucion_id, "nombres": PREFIJO, "apellidos": f"{nombre_alumno} {sello}",
            "tipo_perfil": "estudiante",
        }, headers=h_psi, timeout=30), 200, f"crear alumno {nombre_alumno}")
        exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
            "persona_id": persona["id"], "institucion_id": institucion_id,
            "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado",
        }, headers=h_psi, timeout=30), 200, "consentimiento apoderado")
        campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
            "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña {nombre_alumno} {sello}",
            "institucion_id": institucion_id,
        }, headers=h_psi, timeout=30), 200, "crear campaña")
        matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                          json=[persona["id"]], headers=h_psi, timeout=30), 200, "matricular")
        token = matricula["generados"][0]["token"]
        exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
            "nombre_completo": PREFIJO, "edad": 14, "sexo": "Masculino", "poblacion": "Secundaria",
            "acepta_terminos": True,
        }, timeout=30), 200, "comenzar test")
        preguntas = exigir(requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30), 200, "preguntas")
        detalle_staff = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_psi, timeout=30), 200, "detalle staff PHQ-9")
        preg_por_orden = {p["orden"]: p for p in detalle_staff["dimensiones"][0]["preguntas"]}

        def _opcion_id(pregunta_publica_id, valor_deseado):
            orden = next(o["orden"] for o in preg_por_orden.values() if o["id"] == pregunta_publica_id)
            return next(o["id"] for o in preg_por_orden[orden]["opciones"] if o["valor_puntuacion"] == valor_deseado)

        respuestas = [{"pregunta_id": p["id"], "opcion_id": _opcion_id(p["id"], valor_respuesta)} for p in preguntas]
        exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar respuestas")
        exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "finalizar")
        inscripcion_id = sql_uno("SELECT id FROM edu_inscripciones WHERE token=:t", t=token).id
        return persona["id"], inscripcion_id

    print("\n1 · Mismo PHQ-9, misma respuesta, en los dos colegios")
    alumno_a_id, insc_a_id = _aplicar_phq9(inst_a, h_psi_a, "AlumnoA", 0)
    alumno_b_id, insc_b_id = _aplicar_phq9(inst_b, h_psi_b, "AlumnoB", 0)

    doc_a = esperar_documento_de_plantilla(plantilla_a, alumno_a_id)
    doc_b = esperar_documento_de_plantilla(plantilla_b, alumno_b_id)
    comprobar("[1] El Colegio A obtuvo su documento automático", doc_a is not None)
    comprobar("[1] El Colegio B obtuvo su documento automático", doc_b is not None)

    diag_a = sql_uno("SELECT nivel FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=insc_a_id)
    diag_b = sql_uno("SELECT nivel FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=insc_b_id)
    comprobar("[1] Mismo resultado real en ambos (misma respuesta al mismo instrumento)", diag_a.nivel == diag_b.nivel, f"A={diag_a.nivel!r} B={diag_b.nivel!r}")

    print("\n2 · El PDF del Colegio A (Breve) NO trae filiación ni texto libre -- esas secciones no existen en su diseño")
    texto_a = texto_pdf(leer_pdf_de_version(1, doc_a.id)).upper()
    comprobar("[2] Colegio A: el PDF trae el resultado real", diag_a.nivel.upper() in texto_a)
    comprobar("[2] Colegio A: el PDF NO trae 'DATOS DE FILIACIÓN' (no está en su plantilla)",
              "DATOS DE FILIACIÓN" not in texto_a and "DATOS DE FILIACION" not in texto_a)
    comprobar("[2] Colegio A: el PDF NO trae 'CONCLUSIÓN INSTITUCIONAL' (no está en su plantilla)",
              "CONCLUSIÓN INSTITUCIONAL" not in texto_a and "CONCLUSION INSTITUCIONAL" not in texto_a)

    print("\n3 · El PDF del Colegio B (Extendido) SÍ trae filiación y SU propio texto libre")
    # Antes de generar la versión de B, se redacta el contenido de su sección
    # texto_libre -- exactamente lo que un psicólogo de ESE colegio haría a
    # mano; el enganche automático generó v1 con esta sección vacía porque
    # nadie la había redactado todavía, así que se reemite.
    doc_b_obj = exigir(requests.get(f"{API}/documentos/{doc_b.id}", headers=h_psi_b, timeout=30), 200, "obtener documento B")
    exigir(requests.put(f"{API}/documentos/{doc_b.id}/secciones/{seccion_texto_b['id']}", json={
        "contenido": {"texto": f"{PREFIJO} Conclusión Institucional: el Colegio B redacta su propio cierre, "
                                "distinto de cualquier otro colegio en esta plataforma."},
    }, headers=h_psi_b, timeout=30), 200, "redactar texto libre B")
    v2_b = exigir(requests.post(f"{API}/documentos/{doc_b.id}/reemitir", json={
        "motivo": f"{PREFIJO} agregar conclusión institucional redactada",
    }, headers=h_psi_b, timeout=30), 200, "reemitir B con el texto ya redactado")
    comprobar("[3] Colegio B: se generó una v2 tras redactar su sección propia", v2_b["numero_version"] == 2)

    texto_b = texto_pdf(leer_pdf_de_version(2, doc_b.id)).upper()
    comprobar("[3] Colegio B: el PDF trae el mismo resultado real", diag_b.nivel.upper() in texto_b)
    comprobar("[3] Colegio B: el PDF SÍ trae 'DATOS DE FILIACIÓN' (sección que el Colegio A no tiene)",
              "DATOS DE FILIACIÓN" in texto_b or "DATOS DE FILIACION" in texto_b)
    comprobar("[3] Colegio B: el PDF SÍ trae SU conclusión institucional redactada",
              "COLEGIO B REDACTA SU PROPIO CIERRE" in texto_b)

    print("\n4 · El informe psicométrico FIJO (Sección 5, core/pdf_generator.py) es IDÉNTICO en estructura para ambos colegios")
    informe_a_pdf = requests.get(
        f"{API}/educativo/inscripciones/{insc_a_id}/informe-pdf", headers=h_psi_a, timeout=30)
    informe_b_pdf = requests.get(
        f"{API}/educativo/inscripciones/{insc_b_id}/informe-pdf", headers=h_psi_b, timeout=30)
    comprobar("[4] El informe psicométrico de A descarga 200", informe_a_pdf.status_code == 200)
    comprobar("[4] El informe psicométrico de B descarga 200", informe_b_pdf.status_code == 200)
    texto_informe_a = texto_pdf(informe_a_pdf.content).upper()
    texto_informe_b = texto_pdf(informe_b_pdf.content).upper()
    for titulo in ("DATOS DE FILIACIÓN", "MOTIVO DE CONSULTA", "TÉCNICAS E INSTRUMENTO",
                   "OBSERVACIÓN CONDUCTUAL", "CONCLUSIONES", "RECOMENDACIONES"):
        titulo_norm = titulo.replace("Ó", "O").replace("É", "E")
        en_a = titulo in texto_informe_a or titulo_norm in texto_informe_a
        en_b = titulo in texto_informe_b or titulo_norm in texto_informe_b
        comprobar(f"[4] La sección fija '{titulo}' aparece en AMBOS informes psicométricos (nunca varía por colegio)",
                  en_a and en_b)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E — INFORMES CONDICIONADOS POR COLEGIO: {total - len(fallos)}/{total} comprobaciones superadas")
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
    entradas = f"SELECT id FROM expediente_entradas WHERE documento_institucional_id IN ({documentos}) OR persona_id IN ({personas})"
    evaluaciones = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
    inscripciones = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evaluaciones})"
    informes = f"SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscripciones})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM registro_lecturas_expediente WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM documentos_registro_lecturas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM expediente_entradas WHERE id IN ({entradas})",
            f"DELETE FROM documentos_institucionales_resultados_prueba WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_correlativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_informe_versiones WHERE informe_id IN ({informes})",
            f"DELETE FROM edu_informes WHERE id IN ({informes})",
            f"DELETE FROM edu_inscripciones WHERE id IN ({inscripciones})",
            f"DELETE FROM edu_evaluaciones WHERE id IN ({evaluaciones})",
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
