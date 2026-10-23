"""Verificación end-to-end del Hallazgo B (ver CLAUDE.md, "Motor de
documentos institucionales"): antes de este fix, `crud._resolver_resultados_prueba`
leía `DiagnosticoAlumno.nivel`/`.interpretacion` sin comprobar
`Inscripcion.informe_liberado`, así que un `DocumentoInstitucionalVersion`
podía exponer un resultado psicométrico que el flujo de revisión profesional
del informe (ver "Exam finalization is transactional" en CLAUDE.md) todavía
retenía para todo el mundo.

🆕 Decisión de alcance (sesión 2026-10-17, ver docs/gaps-pendientes.md y
"Hallazgo abierto... resuelto" en docs/motor-documentos.md): el candado
original exigía `informe_liberado=True` **Y** `resultado_visible_alumno=True`
(un OR sobre los dos campos retenía si cualquiera era False). Ese segundo
booleano responde "¿el ALUMNO, específicamente, puede ver esto en su propio
portal?" -- una pregunta ajena a la mayoría de los documentos institucionales
(un plan de intervención, una ficha de derivación externa NUNCA van
dirigidos al alumno), y bloqueaba sin razón real justo los casos de riesgo
que más necesitan esos documentos de trabajo interno MIENTRAS el resultado
sigue retenido para la familia. Este motor ya NO exige `resultado_visible_
alumno` -- solo `informe_liberado` (un profesional ya revisó y liberó el
resultado). El candado del PORTAL DEL ALUMNO (`GET /examen/{token}/estado-
resultados`, `.../informe-pdf`) no cambió: sigue exigiendo ambos campos, ver
docs/informes-psicometricos.md.

Reproduce el escenario EXACTO reportado -- resultado retenido + intento real
de vincularlo a una sección resultados_prueba -- contra el pipeline real
(HTTP + Postgres + PDF real en storage), y confirma:

  1   Montaje: una aplicación PHQ-9 real con puntaje alto (misma técnica que
      verificar_permisos_colegio_e2e.py) deja informe_liberado=False /
      resultado_visible_alumno=False al finalizar, sin intervención manual.
  2   v1 del documento: el PDF real NUNCA imprime el nivel/interpretación
      reales -- solo el placeholder "Pendiente de revisión profesional".
  3   `liberar-informe` (SOLO informe_liberado=True, sin tocar
      resultado_visible_alumno -- sigue False, siguen siendo campos
      independientes) ya basta para que una reemisión (v2) SÍ traiga el
      resultado real -- la decisión de 2026-10-17 en acción: este motor no
      espera a que el alumno también lo vea.
  4   v1 (releída de storage) sigue exactamente igual que antes -- byte a
      byte -- confirmando que liberar/reemitir nunca reescribe una versión
      ya emitida.
  5   Un segundo caso, armado directamente con informe_liberado=True Y
      resultado_visible_alumno=False (la combinación que el Hallazgo B
      original trataba como retenida): el documento YA NO queda retenido --
      confirma que la condición depende solo de informe_liberado ahora.

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_resultado_retenido_e2e
    python -m tests.verificar_documentos_resultado_retenido_e2e --limpiar
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

PREFIJO = "ZZDOCRET"
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


def checksum_de_version(numero_version, documento_id):
    fila = sql_uno(
        "SELECT checksum_sha256 FROM documentos_institucionales_versiones "
        "WHERE documento_institucional_id=:d AND numero_version=:n",
        d=documento_id, n=numero_version,
    )
    return fila.checksum_sha256


def texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    crudo = " ".join((p.extract_text() or "") for p in lector.pages)
    return re.sub(r"\s+", " ", crudo)


def _id_seccion(h, plantilla_id, tipo_seccion):
    r = requests.get(f"{API}/documentos/plantillas/{plantilla_id}/secciones", headers=h, timeout=30)
    for s in r.json():
        if s["tipo_seccion"] == tipo_seccion:
            return s["id"]
    raise RuntimeError(f"No se encontró sección {tipo_seccion}")


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

    phq9_id = exigir(requests.get(f"{API}/educativo/pruebas/", headers=h_psi, timeout=30), 200, "catálogo pruebas")
    phq9_id = next(p["id"] for p in phq9_id if p["nombre_tecnico"] == "PHQ-9")

    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_{sello}", "nombre": f"{PREFIJO} Informe con resultados",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo")
    plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_id, "tipo_documento_id": tipo["id"], "nombre": f"{PREFIJO} Plantilla",
    }, headers=h_super, timeout=30), 200, "crear plantilla")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
    }, headers=h_super, timeout=30), 200, "sección encabezado")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
        "orden": 1, "tipo_seccion": "resultados_prueba", "titulo": "Resultados",
    }, headers=h_super, timeout=30), 200, "sección resultados_prueba")

    def _aplicar_phq9(nombre_alumno, valor_respuesta):
        """Monta una aplicación PHQ-9 real completa (campaña->matrícula->
        examen->finalizar) -- mismo mecanismo que
        verificar_permisos_colegio_e2e.py -- y devuelve (persona_id,
        inscripcion_id)."""
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
        }, headers=h_psi, timeout=30), 200, "crear campaña")
        matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                          json=[persona["id"]], headers=h_psi, timeout=30), 200, "matricular")
        token = matricula["generados"][0]["token"]
        exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
            "nombre_completo": PREFIJO, "edad": 14, "sexo": "Masculino", "poblacion": "Secundaria",
            "acepta_terminos": True,
        }, timeout=30), 200, "comenzar test")
        preguntas = exigir(requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30), 200, "preguntas")
        # El endpoint público de preguntas deliberadamente NO expone
        # valor_puntuacion (sería filtrar el puntaje al alumno) -- y cruzar
        # contra el detalle de staff por dimensión (como hacía esta función
        # antes) rompe con PHQ-9 real, que ya tiene una 'Depresión'
        # compuesta (sin preguntas propias) y un ítem 10 sin dimension_id
        # (la pregunta de dificultad funcional del ítem-9): ninguno de los
        # dos aparece en dimensiones[*].preguntas. Se resuelve por SQL
        # directo contra edu_opciones, por pregunta_id -- robusto sin
        # importar a qué dimensión (o a ninguna) pertenezca cada ítem.
        opciones_por_pregunta = {}
        for fila in sql_todos(
            "SELECT o.pregunta_id, o.id, o.valor_puntuacion FROM edu_opciones o "
            "JOIN edu_preguntas q ON q.id = o.pregunta_id WHERE q.prueba_id=:p", p=phq9_id,
        ):
            opciones_por_pregunta.setdefault(fila.pregunta_id, []).append(fila)

        def _opcion_id(pregunta_id, valor_deseado):
            return next(o.id for o in opciones_por_pregunta[pregunta_id] if float(o.valor_puntuacion) == valor_deseado)

        respuestas = [{"pregunta_id": p["id"], "opcion_id": _opcion_id(p["id"], valor_respuesta)} for p in preguntas]
        exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar respuestas")
        exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "finalizar")
        inscripcion_id = sql_uno("SELECT id FROM edu_inscripciones WHERE token=:t", t=token).id
        return persona["id"], inscripcion_id

    def _vincular_resultado(documento_id, seccion_id, persona_id, inscripcion_id):
        # Hallazgo A (ya reportado, sin corregir aquí -- ver CLAUDE.md): no
        # hay endpoint público para esto; se inserta por SQL directo.
        sql_ejecutar(
            "INSERT INTO documentos_institucionales_resultados_prueba "
            "(documento_institucional_id, plantilla_seccion_id, institucion_id, persona_id, inscripcion_id) "
            "VALUES (:d, :s, :i, :p, :ins)",
            d=documento_id, s=seccion_id, i=inst_id, p=persona_id, ins=inscripcion_id,
        )

    print("\n1 · Montaje del caso: PHQ-9 real con puntaje alto -> retenido al finalizar (sin intervención manual)")
    alumno_id, inscripcion_id = _aplicar_phq9("Retenido", 3)
    liberado, visible = sql_uno(
        "SELECT informe_liberado, resultado_visible_alumno FROM edu_inscripciones WHERE id=:i", i=inscripcion_id,
    )
    comprobar("[1] informe_liberado=False justo al finalizar (puntaje alto -> alerta -> retenido)", liberado is False)
    comprobar("[1] resultado_visible_alumno=False también", visible is False)
    diag = sql_uno(
        "SELECT nivel, interpretacion FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=inscripcion_id,
    )
    comprobar("[1] Hay un DiagnosticoAlumno real (nivel de alerta) para intentar exponer", diag is not None, diag.nivel if diag else "")

    doc = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Documento", "personas_ids": [alumno_id],
    }, headers=h_psi, timeout=30), 200, "crear documento")
    seccion_id = _id_seccion(h_psi, plantilla["id"], "resultados_prueba")
    _vincular_resultado(doc["id"], seccion_id, alumno_id, inscripcion_id)

    print("\n2 · v1: el PDF real NUNCA expone el resultado retenido")
    v1 = exigir(requests.post(f"{API}/documentos/{doc['id']}/generar-version", headers=h_psi, timeout=30), 200, "generar v1")
    comprobar("[2] v1 numero_version=1", v1["numero_version"] == 1)
    texto_v1 = texto_pdf(leer_pdf_de_version(1, doc["id"])).upper()
    comprobar("[2] El PDF v1 SÍ trae el placeholder de revisión pendiente",
              "PENDIENTE DE REVISIÓN PROFESIONAL" in texto_v1 or "PENDIENTE DE REVISION PROFESIONAL" in texto_v1)
    comprobar("[2] El PDF v1 NO imprime el nivel real de alerta diagnosticado",
              diag.nivel.upper() not in texto_v1, diag.nivel)
    if diag.interpretacion:
        comprobar("[2] El PDF v1 NO imprime la interpretación real diagnosticada",
                  diag.interpretacion.upper() not in texto_v1)
    checksum_v1_antes = checksum_de_version(1, doc["id"])

    print("\n3 · Se libera SOLO el informe (resultado_visible_alumno sigue False) -> v2 YA trae el resultado real "
          "(decisión de alcance, sesión 2026-10-17)")
    # liberar-informe SOLO toca informe_liberado -- resultado_visible_alumno
    # se decide aparte (revision-informe), a propósito (ver
    # schemas.RevisionInformeRequest: "decide por separado la visibilidad
    # del resultado y PDF"). Antes del 2026-10-17 este motor exigía AMBOS
    # campos (ver docstring del módulo); ahora solo le importa
    # informe_liberado, así que esto YA basta.
    exigir(requests.patch(f"{API}/educativo/inscripciones/{inscripcion_id}/liberar-informe", json={},
                           headers=h_psi, timeout=30), 200, "liberar informe")
    liberado_solo, visible_solo = sql_uno(
        "SELECT informe_liberado, resultado_visible_alumno FROM edu_inscripciones WHERE id=:i", i=inscripcion_id,
    )
    comprobar("[3] informe_liberado=True tras liberar-informe", liberado_solo is True)
    comprobar("[3] resultado_visible_alumno SIGUE False (son campos independientes; el portal del alumno sigue "
              "sin mostrárselo aunque este motor ya pueda usarlo)", visible_solo is False)

    v2 = exigir(requests.post(f"{API}/documentos/{doc['id']}/reemitir",
                               json={"motivo": "Informe liberado (resultado_visible_alumno aún False)"},
                               headers=h_psi, timeout=30), 200, "reemitir con solo informe_liberado")
    comprobar("[3] v2 numero_version=2", v2["numero_version"] == 2)
    texto_v2 = texto_pdf(leer_pdf_de_version(2, doc["id"])).upper()
    comprobar("[3] El PDF v2 YA NO trae el placeholder de pendiente, con SOLO informe_liberado=True",
              "PENDIENTE DE REVISIÓN PROFESIONAL" not in texto_v2 and "PENDIENTE DE REVISION PROFESIONAL" not in texto_v2)
    comprobar("[3] El PDF v2 SÍ imprime el nivel real, aunque el alumno todavía no lo vería en su propio portal",
              diag.nivel.upper() in texto_v2, diag.nivel)

    print("\n4 · v1 (releída de storage) sigue exactamente igual -- nunca se reescribe una versión ya emitida")
    checksum_v1_despues = checksum_de_version(1, doc["id"])
    comprobar("[4] Checksum de v1 sin cambios tras liberar y reemitir", checksum_v1_antes == checksum_v1_despues)
    texto_v1_relectura = texto_pdf(leer_pdf_de_version(1, doc["id"])).upper()
    comprobar("[4] v1 releída SIGUE sin exponer el nivel real (inmutable)", diag.nivel.upper() not in texto_v1_relectura)

    print("\n5 · informe_liberado=True + resultado_visible_alumno=False -> YA NO retiene (decisión de alcance, 2026-10-17)")
    alumno2_id, inscripcion2_id = _aplicar_phq9("SoloNoVisible", 3)
    # Combinación que no ocurre sola en el flujo normal (ambos flags se
    # fijan juntos en finalizar_examen_seguro), así que se arma directamente
    # por SQL para probar la rama: liberado=True, pero el alumno todavía no
    # lo vería en su propio portal.
    sql_ejecutar(
        "UPDATE edu_inscripciones SET informe_liberado=true, resultado_visible_alumno=false WHERE id=:i",
        i=inscripcion2_id,
    )
    diag2 = sql_uno(
        "SELECT nivel, interpretacion FROM edu_diagnosticos_alumno WHERE inscripcion_id=:i LIMIT 1", i=inscripcion2_id,
    )
    doc2 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo["id"], "plantilla_documento_id": plantilla["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Documento 2", "personas_ids": [alumno2_id],
    }, headers=h_psi, timeout=30), 200, "crear documento 2")
    seccion2_id = _id_seccion(h_psi, plantilla["id"], "resultados_prueba")
    _vincular_resultado(doc2["id"], seccion2_id, alumno2_id, inscripcion2_id)
    exigir(requests.post(f"{API}/documentos/{doc2['id']}/generar-version", headers=h_psi, timeout=30), 200, "generar v1 doc2")
    texto_doc2 = texto_pdf(leer_pdf_de_version(1, doc2["id"])).upper()
    comprobar("[5] YA NO retiene con solo resultado_visible_alumno=False (informe_liberado=True basta)",
              "PENDIENTE DE REVISIÓN PROFESIONAL" not in texto_doc2 and "PENDIENTE DE REVISION PROFESIONAL" not in texto_doc2)
    comprobar("[5] El PDF SÍ imprime el nivel real de este segundo caso", diag2.nivel.upper() in texto_doc2, diag2.nivel)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — RESULTADO RETENIDO (Hallazgo B): {total - len(fallos)}/{total} comprobaciones superadas")
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
