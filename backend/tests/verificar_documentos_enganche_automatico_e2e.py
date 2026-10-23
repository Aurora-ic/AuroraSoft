"""Verificación end-to-end del enganche automático motor de pruebas ->
motor de documentos (ver CLAUDE.md, "Enganche automático: motor de
pruebas → motor de documentos"): PlantillaDocumento.generar_
automaticamente_al_finalizar_examen + crud.generar_documentos_
automaticos_por_examen, disparado desde finalizar_examen_seguro vía
BackgroundTasks.

Contra el pipeline real (HTTP + Postgres + PDF real en storage, igual que
verificar_documentos_resultado_retenido_e2e.py), confirma cada salvaguarda
descrita para esta función, una por una:

  1   Plantilla elegible (activa, flag=True, exactamente 1 sección
      resultados_prueba) + examen limpio (sin alerta) -> se genera sola,
      v1, con el resultado REAL visible en el PDF.
  2   Misma plantilla, examen con alerta -> se genera igual, pero el PDF
      muestra "Pendiente de revisión profesional", nunca el nivel real
      (sinergia con el fix de _resolver_resultados_prueba de esta misma
      sesión -- este enganche es seguro por construcción gracias a él).
  3   Plantilla con CERO secciones resultados_prueba (flag=True) -> no se
      genera nada para ella.
  4   Plantilla con DOS secciones resultados_prueba (flag=True) -> tampoco
      se genera nada (ambigüedad real, nunca se adivina).
  5   Plantilla con flag=False (control) -> no se genera nada.
  6   Resolución de actor: si el creador de la campaña queda inactivo
      antes de finalizar, el documento se atribuye al primer admin activo
      de la institución -- nunca a 'colegio', aunque exista uno activo.
  7   Gate de consentimiento: una persona sin consentimiento vigente del
      apoderado nunca obtiene un documento automático de un TipoDocumento
      que lo exige (verificado llamando a la función real contra la BD
      real, no vía HTTP -- ver nota en el propio bloque: el consentimiento
      apoderado es también requisito para finalizar un examen, así que no
      hay forma de alcanzar esta rama a través del flujo HTTP normal; es
      una salvaguarda de defensa en profundidad, no una ruta alcanzable
      hoy en la práctica, y eso en sí mismo queda documentado como hallazgo).

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_enganche_automatico_e2e
    python -m tests.verificar_documentos_enganche_automatico_e2e --limpiar
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
from core.database import SessionLocal  # noqa: E402
from modulos.documentos import crud as docs_crud  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZDOCENG"
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
    """El documento automático se genera en un BackgroundTask tras
    finalizar -- polling breve a la BD hasta que aparezca CON su versión ya
    generada (no apenas creado: crear_documento_institucional/
    vincular_resultado_prueba/generar_version_documento hacen su propio
    commit() cada uno, así que hay una ventana real, aunque breve, donde la
    fila ya existe con version_actual todavía NULL) -- mismo criterio que
    esperar_informe() en verificar_informe_phq9_e2e.py."""
    limite = time.time() + timeout
    fila = None
    while time.time() < limite:
        fila = sql_uno(
            "SELECT id, version_actual, creado_por_usuario_id FROM documentos_institucionales "
            "WHERE plantilla_documento_id=:p AND id IN "
            "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:per) "
            "ORDER BY id DESC LIMIT 1",
            p=plantilla_id, per=persona_id,
        )
        if fila and fila.version_actual is not None:
            return fila
        time.sleep(0.5)
    return fila


def no_se_genero_nada(plantilla_id, espera=3):
    """Control negativo: espera un rato prudente y confirma que NINGÚN
    documento se creó para esta plantilla -- a diferencia de
    esperar_documento_de_plantilla(), que sale en cuanto aparece algo,
    aquí hay que dejar pasar el tiempo completo porque "nada apareció
    todavía" y "nunca va a aparecer" se ven igual a mitad del polling."""
    time.sleep(espera)
    fila = sql_uno(
        "SELECT id FROM documentos_institucionales WHERE plantilla_documento_id=:p", p=plantilla_id,
    )
    return fila is None


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_id = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}"}, headers=h_super, timeout=30), 201, "Institución")["id"]
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", f"{PREFIJO} Psicóloga", "psicologo", inst_id)
    registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com", f"{PREFIJO} Admin", "admin", inst_id)
    registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com", f"{PREFIJO} Colegio", "colegio", inst_id)
    psi_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com").id
    admin_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com").id

    phq9 = exigir(requests.get(f"{API}/educativo/pruebas/", headers=h_psi, timeout=30), 200, "catálogo pruebas")
    phq9_id = next(p["id"] for p in phq9 if p["nombre_tecnico"] == "PHQ-9")

    def _crear_tipo(nombre, requiere_consentimiento=False):
        return exigir(requests.post(f"{API}/documentos/tipos", json={
            "clave": f"{PREFIJO.lower()}_{nombre.lower()}_{sello}", "nombre": f"{PREFIJO} {nombre}",
            "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
            "requiere_consentimiento_individual": requiere_consentimiento,
        }, headers=h_super, timeout=30), 200, f"crear tipo {nombre}")

    # 🔒 Cada escenario usa su PROPIO TipoDocumento, a propósito: el índice
    # único parcial "como máximo una plantilla activa por institución+tipo"
    # (ver PlantillaDocumento) desactivaría silenciosamente la plantilla
    # anterior si varias compartieran el mismo tipo -- eso es justo el
    # comportamiento correcto del motor (una salvaguarda real, no un bug),
    # pero aquí se necesitan varias plantillas activas AL MISMO TIEMPO para
    # comparar escenarios, así que cada una necesita su propio tipo.
    tipo_feliz = _crear_tipo("Feliz")
    tipo_cero = _crear_tipo("CeroSecciones")
    tipo_dos = _crear_tipo("DosSecciones")
    tipo_apagada = _crear_tipo("Apagada")
    tipo_con_consentimiento = _crear_tipo("ExigeConsentimiento", requiere_consentimiento=True)

    def _crear_plantilla(nombre, tipo, automatica, n_secciones_resultado):
        plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
            "institucion_id": inst_id, "tipo_documento_id": tipo["id"], "nombre": f"{PREFIJO} {nombre} {sello}",
            "generar_automaticamente_al_finalizar_examen": automatica,
        }, headers=h_super, timeout=30), 200, f"crear plantilla {nombre}")
        exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
            "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
        }, headers=h_super, timeout=30), 200, f"sección encabezado {nombre}")
        for i in range(n_secciones_resultado):
            exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
                "orden": i + 1, "tipo_seccion": "resultados_prueba", "titulo": f"Resultados {i + 1}",
            }, headers=h_super, timeout=30), 200, f"sección resultados_prueba #{i + 1} {nombre}")
        return plantilla

    plantilla_feliz = _crear_plantilla("Feliz", tipo_feliz, True, 1)
    plantilla_cero_secciones = _crear_plantilla("CeroSecciones", tipo_cero, True, 0)
    plantilla_dos_secciones = _crear_plantilla("DosSecciones", tipo_dos, True, 2)
    plantilla_apagada = _crear_plantilla("Apagada", tipo_apagada, False, 1)

    comprobar("[montaje] La plantilla feliz quedó creada con el flag en True",
              sql_uno("SELECT generar_automaticamente_al_finalizar_examen FROM documentos_plantillas WHERE id=:i",
                      i=plantilla_feliz["id"])[0] is True)
    comprobar("[montaje] La plantilla apagada quedó con el flag en False",
              sql_uno("SELECT generar_automaticamente_al_finalizar_examen FROM documentos_plantillas WHERE id=:i",
                      i=plantilla_apagada["id"])[0] is False)

    def _aplicar_phq9(nombre_alumno, valor_respuesta, h_creador=h_psi):
        """Monta una aplicación PHQ-9 real completa (campaña->matrícula->
        examen->finalizar), devuelve (persona_id, inscripcion_id,
        evaluacion_id)."""
        persona = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_id, "nombres": PREFIJO, "apellidos": f"{nombre_alumno} {sello}",
            "tipo_perfil": "estudiante",
        }, headers=h_psi, timeout=30), 200, f"crear alumno {nombre_alumno}")
        exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
            "persona_id": persona["id"], "institucion_id": inst_id,
            "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado",
        }, headers=h_psi, timeout=30), 200, "consentimiento apoderado")

        campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
            "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña {nombre_alumno} {sello}", "institucion_id": inst_id,
        }, headers=h_creador, timeout=30), 200, "crear campaña")
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
        return persona["id"], inscripcion_id, campana["id"]

    print("\n1 · Plantilla elegible + examen LIMPIO -> se genera sola, con el resultado real visible")
    alumno1_id, insc1_id, _ = _aplicar_phq9("Limpio", 0)
    doc1 = esperar_documento_de_plantilla(plantilla_feliz["id"], alumno1_id)
    comprobar("[1] Se generó un DocumentoInstitucional solo, sin llamada manual", doc1 is not None)
    if doc1:
        comprobar("[1] Nació ya con version_actual=1 (no se quedó en borrador)", doc1.version_actual == 1)
        diag1 = sql_uno("SELECT nivel FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=insc1_id)
        texto1 = texto_pdf(leer_pdf_de_version(1, doc1.id)).upper()
        comprobar("[1] El PDF real trae el nivel diagnosticado real (no está retenido -> no hay alerta)",
                  diag1 is not None and diag1.nivel.upper() in texto1, diag1.nivel if diag1 else "")
        comprobar("[1] El PDF NO trae el placeholder de pendiente (no aplica, no está retenido)",
                  "PENDIENTE DE REVISIÓN PROFESIONAL" not in texto1 and "PENDIENTE DE REVISION PROFESIONAL" not in texto1)

    print("\n2 · Misma plantilla + examen con ALERTA -> se genera, pero retenido (sinergia con el fix de esta sesión)")
    alumno2_id, insc2_id, _ = _aplicar_phq9("ConAlerta", 3)
    liberado2, visible2 = sql_uno(
        "SELECT informe_liberado, resultado_visible_alumno FROM edu_inscripciones WHERE id=:i", i=insc2_id,
    )
    comprobar("[2] El examen de alerta quedó retenido al finalizar (precondición del caso)", liberado2 is False and visible2 is False)
    doc2 = esperar_documento_de_plantilla(plantilla_feliz["id"], alumno2_id)
    comprobar("[2] El documento automático SÍ se genera aunque el resultado esté retenido", doc2 is not None)
    if doc2:
        diag2 = sql_uno("SELECT nivel FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=insc2_id)
        texto2 = texto_pdf(leer_pdf_de_version(1, doc2.id)).upper()
        comprobar("[2] El PDF trae el placeholder de revisión pendiente",
                  "PENDIENTE DE REVISIÓN PROFESIONAL" in texto2 or "PENDIENTE DE REVISION PROFESIONAL" in texto2)
        comprobar("[2] El PDF NUNCA imprime el nivel real de alerta", diag2.nivel.upper() not in texto2, diag2.nivel)

    print("\n3 · Plantilla con CERO secciones resultados_prueba (flag=True) -> no genera nada")
    alumno3_id, _, _ = _aplicar_phq9("CeroSecciones", 0)
    comprobar("[3] Ninguna fila para la plantilla de 0 secciones", no_se_genero_nada(plantilla_cero_secciones["id"]))

    print("\n4 · Plantilla con DOS secciones resultados_prueba (flag=True) -> tampoco genera (ambigüedad real)")
    alumno4_id, _, _ = _aplicar_phq9("DosSecciones", 0)
    comprobar("[4] Ninguna fila para la plantilla de 2 secciones", no_se_genero_nada(plantilla_dos_secciones["id"]))

    print("\n5 · Plantilla con flag=False (control) -> no genera nada")
    alumno5_id, _, _ = _aplicar_phq9("Apagada", 0)
    comprobar("[5] Ninguna fila para la plantilla apagada", no_se_genero_nada(plantilla_apagada["id"]))

    print("\n6 · Resolución de actor: creador inactivo -> cae al primer admin activo, NUNCA a 'colegio'")
    alumno6_id, insc6_id, campana6_id = _aplicar_phq9("ActorFallback", 0)
    # El examen ya se finalizó con el psicólogo activo como creador; ahora
    # se lo desactiva y se fuerza un reproceso del DOCUMENTO (no del
    # examen) llamando de nuevo a la función real -- simula el caso donde
    # el creador deja de estar activo ANTES de que corra el background
    # task (una condición de carrera real, aunque rara). Primero se borra
    # el documento que ya generó el psicólogo activo en el paso 1 del
    # flujo normal, para poder observar limpio a quién se atribuye esta
    # segunda corrida.
    sql_ejecutar("DELETE FROM documentos_institucionales_resultados_prueba WHERE documento_institucional_id IN "
                 "(SELECT id FROM documentos_institucionales WHERE id IN "
                 "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:p))", p=alumno6_id)
    sql_ejecutar("DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN "
                 "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:p)", p=alumno6_id)
    sql_ejecutar("DELETE FROM expediente_entradas WHERE documento_institucional_id IN "
                 "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:p)", p=alumno6_id)
    sql_ejecutar("DELETE FROM documentos_institucionales_estudiantes WHERE persona_id=:p", p=alumno6_id)
    sql_ejecutar("DELETE FROM documentos_institucionales WHERE id NOT IN "
                 "(SELECT documento_institucional_id FROM documentos_institucionales_estudiantes) AND plantilla_documento_id=:pl",
                 pl=plantilla_feliz["id"])
    sql_ejecutar("UPDATE auth_usuarios SET activo=false WHERE id=:i", i=psi_id)
    db = SessionLocal()
    try:
        docs_crud.generar_documentos_automaticos_por_examen(db, inscripcion_id=insc6_id)
    finally:
        db.close()
    sql_ejecutar("UPDATE auth_usuarios SET activo=true WHERE id=:i", i=psi_id)  # deja la cuenta como estaba
    doc6 = sql_uno(
        "SELECT id, creado_por_usuario_id FROM documentos_institucionales WHERE plantilla_documento_id=:p "
        "AND id IN (SELECT documento_institucional_id FROM documentos_institucionales_estudiantes WHERE persona_id=:per) "
        "ORDER BY id DESC LIMIT 1", p=plantilla_feliz["id"], per=alumno6_id,
    )
    comprobar("[6] El documento se generó igual (el enganche no depende del creador activo)", doc6 is not None)
    if doc6:
        comprobar("[6] Se atribuyó al admin activo de la institución, NO al psicólogo (ahora inactivo)",
                  doc6.creado_por_usuario_id == admin_id, f"obtenido={doc6.creado_por_usuario_id} admin={admin_id} psi={psi_id}")
        comprobar("[6] NUNCA se atribuyó al psicólogo inactivo", doc6.creado_por_usuario_id != psi_id)

    print("\n7 · Gate de consentimiento (función real contra BD real, sin HTTP -- ver nota del archivo)")
    alumno7 = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": PREFIJO, "apellidos": f"SinConsentimiento {sello}",
        "tipo_perfil": "estudiante",
    }, headers=h_psi, timeout=30), 200, "crear alumno sin consentimiento")["id"]
    plantilla_consiente = _crear_plantilla("ExigeConsentimiento", tipo_con_consentimiento, True, 1)
    # Inscripción real para ESTE alumno (sin registrar consentimiento) -- se
    # reutiliza el patrón _aplicar_phq9 pero el consentimiento de apoderado
    # es tan obligatorio para FINALIZAR como para EMPEZAR el examen, así que
    # no hay forma real de llegar hasta aquí con una inscripción Finalizado
    # y sin consentimiento -- se arma la fila mínima de Inscripcion por SQL
    # directo, exactamente como ya hace _vincular_resultado en el E2E
    # hermano cuando el estado no es alcanzable por el flujo normal.
    campana7 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña SinConsentimiento {sello}", "institucion_id": inst_id,
    }, headers=h_psi, timeout=30), 200, "crear campaña 7")["id"]
    sql_ejecutar(
        "INSERT INTO edu_inscripciones (evaluacion_id, persona_id, token, estado, nombre_completo, "
        "edad, sexo, poblacion, acepto_asentimiento, is_deleted, is_anonymized, "
        "informe_liberado, resultado_visible_alumno) "
        "VALUES (:ev, :per, :tok, 'Finalizado', :nom, 14, 'Masculino', 'Secundaria', true, false, false, true, true)",
        ev=campana7, per=alumno7, tok=f"{PREFIJO.lower()}-sinconsentimiento-{sello}", nom=f"{PREFIJO} SinConsentimiento",
    )
    insc7_id = sql_uno("SELECT id FROM edu_inscripciones WHERE token=:t", t=f"{PREFIJO.lower()}-sinconsentimiento-{sello}").id
    comprobar("[7] Precondición: la persona NO tiene ningún consentimiento registrado",
              sql_uno("SELECT count(*) FROM consentimientos_informados WHERE persona_id=:p", p=alumno7)[0] == 0)
    db = SessionLocal()
    try:
        docs_crud.generar_documentos_automaticos_por_examen(db, inscripcion_id=insc7_id)
    finally:
        db.close()
    # 🔒 Se filtra por ESTE alumno (alumno7), no por "ningún documento en
    # absoluto para esta plantilla": una vez creada, plantilla_consiente
    # queda activa y elegible para CUALQUIER inscripción de la institución
    # que su propia tarea en segundo plano procese de ahí en adelante —
    # incluida la del Escenario 6 (ActorFallback, que SÍ tiene
    # consentimiento vigente), cuya tarea puede correr tarde y generarle su
    # propio documento legítimo contra esta misma plantilla. Filtrar solo
    # por plantilla_documento_id confundía ese documento ajeno y correcto
    # con una fuga real del gate de consentimiento.
    comprobar("[7] NINGÚN documento se generó para ESTE alumno en la plantilla que exige consentimiento",
              sql_uno(
                  "SELECT di.id FROM documentos_institucionales di "
                  "JOIN documentos_institucionales_estudiantes die ON die.documento_institucional_id = di.id "
                  "WHERE di.plantilla_documento_id = :p AND die.persona_id = :per",
                  p=plantilla_consiente["id"], per=alumno7,
              ) is None)

    print("\n8 · /reprocesar reemite el documento ya generado (cierra el hueco antes documentado como 'no enganchado')")
    # Reutiliza el documento v1 del escenario 1 (alumno1/insc1, resultado
    # limpio -> nivel "Mínimo", no retenido). Se corrige el baremo que
    # cubre puntaje=0 para que AHORA sea alerta (mismo mecanismo que
    # verificar_reproceso_informe_e2e.py: desactivar + crear el reemplazo,
    # nunca editar un tramo en uso) y se reprocesa -- debe aparecer v2 del
    # MISMO documento, con el placeholder de retención, sin que nadie haya
    # llamado a /documentos/{id}/reemitir a mano.
    # 🔒 Esto muta una fila REAL del catálogo PÚBLICO de PHQ-9 (compartido
    # por cualquier institución, no un dato con prefijo ZZDOCENG) -- a
    # diferencia de todo lo demás en este archivo, no alcanza con que
    # `limpiar()` borre filas con el prefijo al final: si algo falla a
    # mitad de este bloque, el baremo real de PHQ-9 quedaría corrompido
    # para cualquier otra institución de esta base de datos hasta que
    # alguien lo notara. El try/finally de abajo restaura el baremo
    # original SIEMPRE, incluso si una comprobación de arriba hace
    # sys.exit(1) a mitad de camino (exigir() lanza SystemExit, que un
    # finally sí intercepta).
    dim_phq9_id = sql_uno(
        "SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p ON p.id = d.prueba_id "
        "WHERE p.id = :pid LIMIT 1", pid=phq9_id,
    ).id
    baremo_cero = sql_uno(
        "SELECT id FROM edu_baremos WHERE dimension_id=:d AND puntaje_minimo <= 0 AND puntaje_maximo >= 0 "
        "AND activo = true AND criterio_normativo IS NULL", d=dim_phq9_id,
    )
    baremo_reemplazo_id = None
    try:
        exigir(requests.delete(f"{API}/educativo/baremos/{baremo_cero.id}", headers=h_super, timeout=30),
               200, "desactivar baremo PHQ-9 puntaje=0 (soft-delete, ya está en uso)")
        baremo_reemplazo_id = exigir(requests.post(f"{API}/educativo/baremos/", json={
            "dimension_id": dim_phq9_id, "puntaje_minimo": 0, "puntaje_maximo": 0,
            "nivel": f"{PREFIJO} corregido a alerta", "es_alerta": True,
        }, headers=h_super, timeout=30), 200, "crear baremo de reemplazo con es_alerta=True")["id"]

        r_reproceso = exigir(requests.post(f"{API}/educativo/inscripciones/{insc1_id}/reprocesar",
                                            json={"motivo": f"{PREFIJO} corrección de baremo puntaje=0"},
                                            headers=h_super, timeout=60), 200, "reprocesar insc1")
        comprobar("[8] El reproceso reporta el documento del escenario 1 entre los reemitidos",
                  doc1.id in r_reproceso["documentos_institucionales_reemitidos"],
                  r_reproceso["documentos_institucionales_reemitidos"])
        comprobar("[8] El reproceso retuvo el resultado (el baremo corregido ahora SÍ es alerta)",
                  r_reproceso["requiere_revision"] is True)

        doc1_v2 = sql_uno(
            "SELECT version_actual FROM documentos_institucionales WHERE id=:i", i=doc1.id,
        )
        comprobar("[8] El MISMO documento (no uno nuevo) subió a version_actual=2", doc1_v2.version_actual == 2)
        texto_doc1_v2 = texto_pdf(leer_pdf_de_version(2, doc1.id)).upper()
        comprobar("[8] La v2 reemitida por el reproceso YA trae el placeholder de retención "
                  "(el resultado corregido ahora requiere revisión profesional)",
                  "PENDIENTE DE REVISIÓN PROFESIONAL" in texto_doc1_v2 or "PENDIENTE DE REVISION PROFESIONAL" in texto_doc1_v2)
        texto_doc1_v1_relectura = texto_pdf(leer_pdf_de_version(1, doc1.id)).upper()
        comprobar("[8] La v1 original sigue intacta (releída de storage) -- sigue con el nivel de ANTES de la "
                  "corrección, nunca se reescribe", diag1.nivel.upper() in texto_doc1_v1_relectura, diag1.nivel)
    finally:
        # Restaura el catálogo público de PHQ-9 exactamente a como estaba
        # antes de este escenario -- reactiva el tramo original, desactiva
        # el de prueba. Nunca se hace por la API (no hay endpoint para
        # reactivar un Baremo ya desactivado), así que es el único UPDATE
        # directo por SQL de todo este archivo, y a propósito.
        sql_ejecutar("UPDATE edu_baremos SET activo = true WHERE id = :i", i=baremo_cero.id)
        if baremo_reemplazo_id is not None:
            sql_ejecutar("UPDATE edu_baremos SET activo = false WHERE id = :i", i=baremo_reemplazo_id)
        comprobar("[8] Catálogo público de PHQ-9 restaurado: el baremo original vuelve a estar activo",
                  sql_uno("SELECT activo FROM edu_baremos WHERE id = :i", i=baremo_cero.id)[0] is True)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E — ENGANCHE AUTOMÁTICO DOCUMENTOS: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))

    # 🔒 Red de seguridad para el Escenario 8: el try/finally de main() ya
    # restaura el catálogo público de PHQ-9 en una corrida normal (éxito o
    # fallo controlado) -- esto cubre el caso en que el proceso se
    # interrumpió a la mitad (Ctrl+C, corte de luz) y nadie llegó a
    # restaurar nada. Busca cualquier baremo de prueba dejado activo
    # (nivel con el prefijo) y reactiva lo que haya quedado desactivado en
    # su mismo rango de puntaje para la misma dimensión -- nunca asume
    # un id fijo, porque esta BD puede no ser la misma en la que se corrió
    # el escenario.
    with motor.begin() as c:
        huerfanos = c.execute(text(
            f"SELECT id, dimension_id, puntaje_minimo, puntaje_maximo FROM edu_baremos "
            f"WHERE nivel LIKE '{PREFIJO}%' AND activo = true"
        )).fetchall()
        for h in huerfanos:
            c.execute(text(
                "UPDATE edu_baremos SET activo = false WHERE id = :i"
            ), {"i": h.id})
            c.execute(text(
                "UPDATE edu_baremos SET activo = true WHERE dimension_id = :d "
                "AND puntaje_minimo <= :pmin AND puntaje_maximo >= :pmax AND activo = false "
                "AND nivel NOT LIKE '" + PREFIJO + "%'"
            ), {"d": h.dimension_id, "pmin": h.puntaje_minimo, "pmax": h.puntaje_maximo})
        if huerfanos:
            print(f"Restaurados {len(huerfanos)} baremo(s) de catálogo público que había(n) quedado sin limpiar.")

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
