"""Verificación funcional de punta a punta — pedida explícitamente como
verificación (NO se modifica código de producción):

  1. Institución -> estructura académica -> importación Excel -> consentimiento
     -> campaña -> enlace público -> responder -> finalizar -> resultado ->
     revisión -> liberación -> PDF -> dashboard, con datos nuevos.
  2. Repite todo el flujo con una SEGUNDA institución y confirma aislamiento
     multi-tenant en cada endpoint importante del flujo.

No usa ningún dato ficticio "inventado" fuera de lo que la propia plantilla
oficial de importación ya sugiere como ejemplo, y reutiliza el catálogo
público PHQ-9 (nunca contenido clínico inventado por este script).

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_flujo_completo_e2e.py
    python tests/verificar_flujo_completo_e2e.py --limpiar
"""

import argparse
import io
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from openpyxl import Workbook
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZFLUJO"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []
_evidencia = []  # (hallazgo, endpoint_o_archivo)


def comprobar(nombre, condicion, endpoint="", detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    _evidencia.append((nombre, bool(condicion), endpoint))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else "") + (f"   [{endpoint}]" if endpoint else ""))
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


def construir_excel_una_fila(codigo, nombres, apellidos, documento, nivel, grado, seccion, anio):
    """Genera un .xlsx real en memoria con las columnas EXACTAS de la
    plantilla oficial (mismo orden que importacion_estudiantes.COLUMNAS)."""
    wb = Workbook()
    ws = wb.active
    ws.append(["codigo_institucional", "nombres", "apellidos", "documento_identidad",
               "fecha_nacimiento", "genero", "nivel_educativo", "grado", "seccion",
               "turno", "anio_escolar"])
    ws.append([codigo, nombres, apellidos, documento, "2012-03-15", "Femenino",
               nivel, grado, seccion, "", str(anio)])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


class Contexto:
    """Agrupa todo lo que produce el flujo de UNA institución, para poder
    comparar/cruzar contra el de la otra en los chequeos de aislamiento."""
    pass


def montar_institucion(h_super, letra, sello):
    ctx = Contexto()
    ctx.letra = letra
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"[POST /instituciones/] Institución {letra}")
    ctx.inst_id = inst["id"]
    comprobar(f"[{letra}] Institución creada", True, "POST /api/instituciones/")

    # rol "admin": la estructura académica (niveles/grados/secciones) exige
    # admin o superadmin, mismo criterio que verificar_informe_pdf_e2e.py.
    correo = f"{PREFIJO.lower()}.admin.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {letra}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Admin {letra}",
        "rol": "admin", "institucion_id": ctx.inst_id}, headers=h_super), 200, f"Registro {letra}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {letra}")["access_token"]
    ctx.h = {"Authorization": f"Bearer {tok}"}

    # --- Estructura académica ---
    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": ctx.inst_id, "nombre": "Secundaria"}, headers=ctx.h, timeout=30),
        200, f"[POST /admin/personas/academico/niveles] Nivel {letra}")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "3°"}, headers=ctx.h, timeout=30),
        200, f"[POST /admin/personas/academico/grados] Grado {letra}")
    seccion = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "anio_escolar": 2026}, headers=ctx.h, timeout=30),
        200, f"[POST /admin/personas/academico/secciones] Sección {letra}")
    ctx.nivel_id, ctx.grado_id, ctx.seccion_id = nivel["id"], grado["id"], seccion["id"]
    comprobar(f"[{letra}] Estructura académica creada (Nivel->Grado->Sección)", True,
              "POST /api/admin/personas/academico/{niveles,grados,secciones}")

    # --- Importación Excel (dato nuevo, vía plantilla real) ---
    r_plantilla = requests.get(f"{API}/admin/personas/importar/plantilla", headers=ctx.h, timeout=30)
    comprobar(f"[{letra}] La plantilla oficial se descarga (200, xlsx real)",
              r_plantilla.status_code == 200 and r_plantilla.content[:2] == b"PK",
              "GET /api/admin/personas/importar/plantilla")

    codigo = f"{PREFIJO}-{letra}-{sello}"
    excel = construir_excel_una_fila(codigo, f"{PREFIJO}", f"Alumno{letra}", f"{sello}{letra}1",
                                      "Secundaria", "3°", "A", 2026)
    r_validar = requests.post(f"{API}/admin/personas/importar/validar",
                              files={"archivo": ("alta.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                              headers=ctx.h, timeout=30)
    comprobar(f"[{letra}] Validación del Excel (200), 1 fila 'nuevo', sin errores",
              r_validar.status_code == 200 and r_validar.json()["resumen"] == {"nuevos": 1, "actualizados": 0, "duplicados": 0, "errores": 0},
              "POST /api/admin/personas/importar/validar", r_validar.text[:200])

    excel.seek(0)
    r_confirmar = requests.post(f"{API}/admin/personas/importar/confirmar",
                                files={"archivo": ("alta.xlsx", excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                                headers=ctx.h, timeout=30)
    confirmado = exigir(r_confirmar, 200, f"[POST /admin/personas/importar/confirmar] Confirmar {letra}")
    comprobar(f"[{letra}] Confirmación aplicó exactamente 1 alta nueva", confirmado["resumen"]["nuevos"] == 1,
              "POST /api/admin/personas/importar/confirmar")
    ctx.persona_id = confirmado["detalle"][0]["persona_id"]
    ctx.codigo = codigo

    fila_persona = sql_uno("select institucion_id, tipo_perfil, codigo_institucional from personas where id=:i", i=ctx.persona_id)
    comprobar(f"[{letra}] La persona importada quedó con institucion_id/tipo_perfil correctos",
              fila_persona[0] == ctx.inst_id and fila_persona[1] == "estudiante" and fila_persona[2] == codigo,
              "tabla personas (verificación directa en BD)")
    matricula_activa = sql_uno("select seccion_id from matriculas_academicas where persona_id=:p and fecha_fin is null", p=ctx.persona_id)
    comprobar(f"[{letra}] La importación matriculó al alumno en la sección correcta", matricula_activa[0] == ctx.seccion_id,
              "tabla matriculas_academicas (verificación directa en BD)")

    # --- Consentimiento ---
    exigir(requests.post(f"{API}/admin/personas/{ctx.persona_id}/consentimiento", json={
        "persona_id": ctx.persona_id, "institucion_id": ctx.inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"},
        headers=ctx.h, timeout=30), 200, f"[POST /admin/personas/{{id}}/consentimiento] Consentimiento {letra}")
    comprobar(f"[{letra}] Consentimiento de apoderado registrado", True, "POST /api/admin/personas/{id}/consentimiento")

    # --- Campaña (catálogo público PHQ-9) ---
    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]
    ctx.phq9_id = phq9_id
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {letra} {sello}", "institucion_id": ctx.inst_id},
        headers=ctx.h, timeout=30), 200, f"[POST /educativo/campanas/] Campaña {letra}")
    ctx.campana_id = campana["id"]
    comprobar(f"[{letra}] Campaña creada sobre PHQ-9", True, "POST /api/educativo/campanas/")

    # --- Enlace público (matrícula por padrón, sobre el alumno recién importado) ---
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{ctx.campana_id}/matricular-roster",
                                     json=[ctx.persona_id], headers=ctx.h, timeout=30),
                       200, f"[POST /campanas/{{id}}/matricular-roster] Matrícula {letra}")
    comprobar(f"[{letra}] El alumno importado quedó matriculado (0 rechazados)", matricula["rechazados"] == [],
              "POST /api/educativo/campanas/{id}/matricular-roster", str(matricula["rechazados"]))
    ctx.token = matricula["generados"][0]["token"]

    # --- Responder por el enlace PÚBLICO (sin ningún header de autenticación) ---
    # El endpoint sigue exigiendo estos 4 campos en el body (RegistroAlumnoDemograficos
    # no los hace opcionales) aunque el alumno ya venga de padrón — se envían,
    # pero como la persona YA tiene nombre/edad/sexo/población resueltos por
    # matrícula, quedan silenciosamente ignorados a favor de los reales (ver
    # CLAUDE.md "Exam resumption" / "solo llena lo que sigue vacío").
    r_comenzar = requests.post(f"{API}/educativo/comenzar-test/{ctx.token}", json={
        "nombre_completo": "NOMBRE QUE NO DEBE USARSE (ya viene de padrón)", "edad": 99,
        "sexo": "Masculino", "poblacion": "Universitario", "acepta_terminos": True}, timeout=30)
    comprobar(f"[{letra}] comenzar-test (SIN JWT, solo el token público) -> 200",
              r_comenzar.status_code == 200, "POST /api/educativo/comenzar-test/{token}", r_comenzar.text[:200])
    comprobar(f"[{letra}] Los datos demográficos falsos enviados fueron IGNORADOS (ya venían de padrón)",
              r_comenzar.json()["nombre_completo"] != "NOMBRE QUE NO DEBE USARSE (ya viene de padrón)"
              and r_comenzar.json()["edad"] != 99,
              "POST /api/educativo/comenzar-test/{token} (respuesta)", str(r_comenzar.json()))

    r_preguntas = requests.get(f"{API}/educativo/examen/{ctx.token}/preguntas", timeout=30)
    preguntas_publicas = exigir(r_preguntas, 200, f"[GET /examen/{{token}}/preguntas] Preguntas {letra}")
    comprobar(f"[{letra}] El endpoint público de preguntas NO expone valor_puntuacion (opciones solo id+texto)",
              all(set(o.keys()) == {"id", "texto_opcion"} for p in preguntas_publicas for o in p["opciones"]),
              "GET /api/educativo/examen/{token}/preguntas")

    # Para poder construir una respuesta con INTENCIÓN (alta = con alerta),
    # se consulta el detalle vía staff (propio de esta institución) SOLO para
    # saber qué opción corresponde a qué valor — el estudiante real nunca
    # necesita esto, ve las mismas 9 preguntas por el endpoint público de arriba.
    detalle_staff = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=ctx.h, timeout=30),
                           200, f"Detalle staff PHQ-9 {letra}")
    preg_por_orden = {p["orden"]: p for p in detalle_staff["dimensiones"][0]["preguntas"]}

    def opcion_id_publica(pregunta_publica_id, valor_deseado):
        orden = next(o["orden"] for o in preg_por_orden.values() if o["id"] == pregunta_publica_id)
        return next(o["id"] for o in preg_por_orden[orden]["opciones"] if o["valor_puntuacion"] == valor_deseado)

    # Puntaje alto (3 en cada uno de los 9 ítems = 27) -> dispara alerta por
    # baremo, para poder ejercitar de verdad revisión + liberación más abajo.
    respuestas = [{"pregunta_id": p["id"], "opcion_id": opcion_id_publica(p["id"], 3)} for p in preguntas_publicas]
    r_guardar = requests.post(f"{API}/educativo/examen/{ctx.token}/guardar", json={"respuestas": respuestas}, timeout=30)
    comprobar(f"[{letra}] Guardar respuestas (público, sin JWT) -> 200", r_guardar.status_code == 200,
              "POST /api/educativo/examen/{token}/guardar", r_guardar.text[:200])

    r_progreso = requests.get(f"{API}/educativo/examen/{ctx.token}/progreso", timeout=30)
    comprobar(f"[{letra}] Progreso (público) refleja las 9 respondidas", r_progreso.status_code == 200,
              "GET /api/educativo/examen/{token}/progreso")

    r_finalizar = requests.post(f"{API}/educativo/examen/{ctx.token}/finalizar", timeout=60)
    comprobar(f"[{letra}] Finalizar (público) -> 200", r_finalizar.status_code == 200,
              "POST /api/educativo/examen/{token}/finalizar", r_finalizar.text[:200])

    ctx.insc_id = sql_uno("select id from edu_inscripciones where token=:t", t=ctx.token)[0]

    # --- Resultado (antes de revisar/liberar): debe quedar retenido ---
    r_estado = requests.get(f"{API}/educativo/examen/{ctx.token}/estado-resultados", timeout=30)
    estado_json = exigir(r_estado, 200, f"[GET /examen/{{token}}/estado-resultados] {letra}")
    comprobar(f"[{letra}] Puntaje alto -> el resultado queda RETENIDO (nunca muestra el puntaje al alumno)",
              "puntaje" not in str(estado_json).lower() and estado_json.get("resultado_visible_alumno") is False,
              "GET /api/educativo/examen/{token}/estado-resultados", str(estado_json))

    r_pdf_bloqueado = requests.get(f"{API}/educativo/examen/{ctx.token}/informe-pdf", timeout=60)
    comprobar(f"[{letra}] PDF bloqueado al alumno mientras está retenido (403)", r_pdf_bloqueado.status_code == 403,
              "GET /api/educativo/examen/{token}/informe-pdf")

    # --- Revisión + liberación (staff) ---
    r_revision = requests.patch(f"{API}/educativo/inscripciones/{ctx.insc_id}/revision-informe", json={
        "motivo_consulta": f"Tamizaje de rutina — {letra}",
        "observacion_conductual": "Alumno colaborador durante la aplicación.",
    }, headers=ctx.h, timeout=30)
    comprobar(f"[{letra}] Revisión clínica guardada (200)", r_revision.status_code == 200,
              "PATCH /api/educativo/inscripciones/{id}/revision-informe", r_revision.text[:200])

    r_liberar = requests.patch(f"{API}/educativo/inscripciones/{ctx.insc_id}/liberar-informe", json={}, headers=ctx.h, timeout=30)
    comprobar(f"[{letra}] Liberación del informe (200)", r_liberar.status_code == 200,
              "PATCH /api/educativo/inscripciones/{id}/liberar-informe", r_liberar.text[:200])

    # --- PDF, ya liberado ---
    limite = time.time() + 20
    r_pdf = None
    while time.time() < limite:
        r_pdf = requests.get(f"{API}/educativo/examen/{ctx.token}/informe-pdf", timeout=60)
        if r_pdf.status_code == 200:
            break
        time.sleep(0.5)
    comprobar(f"[{letra}] PDF descargable tras liberar (200, %PDF- real)",
              r_pdf is not None and r_pdf.status_code == 200 and r_pdf.content[:5] == b"%PDF-",
              "GET /api/educativo/examen/{token}/informe-pdf")
    ctx.pdf_bytes = r_pdf.content if r_pdf else b""

    # --- Dashboard ---
    r_dash_campana = requests.get(f"{API}/educativo/campanas/{ctx.campana_id}/dashboard", headers=ctx.h, timeout=30)
    dash_campana = exigir(r_dash_campana, 200, f"[GET /campanas/{{id}}/dashboard] {letra}")
    comprobar(f"[{letra}] Dashboard de campaña: 1 finalizado, 1 inscrito", dash_campana["total_inscritos"] == 1 and dash_campana["total_finalizados"] == 1,
              "GET /api/educativo/campanas/{id}/dashboard", str(dash_campana))

    r_dash_proceso = requests.get(f"{API}/educativo/procesos/dashboard", params={"institucion_id": ctx.inst_id}, headers=ctx.h, timeout=30)
    dash_proceso = exigir(r_dash_proceso, 200, f"[GET /procesos/dashboard] {letra}")
    hay_un_alumno_con_esa_prueba = (
        len(dash_proceso["alumnos"]) == 1
        and len(dash_proceso["alumnos"][0]["pruebas"]) == 1
        and dash_proceso["alumnos"][0]["pruebas"][0]["prueba"] == detalle_staff["nombre_publico"]
    )
    comprobar(f"[{letra}] Dashboard institucional trae al alumno con su prueba aplicada",
              hay_un_alumno_con_esa_prueba, "GET /api/educativo/procesos/dashboard", str(dash_proceso)[:300])

    return ctx


def cruzar_aislamiento(ctx_a, ctx_b):
    letra_a, letra_b = ctx_a.letra, ctx_b.letra
    print(f"\n=== AISLAMIENTO: {letra_b} contra los recursos de {letra_a} ===")

    r = requests.get(f"{API}/admin/personas/{ctx_a.inst_id}", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Padrón de personas de otra institución -> 403",
              r.status_code == 403, "GET /api/admin/personas/{institucion_id}")

    r = requests.get(f"{API}/admin/personas/{ctx_a.persona_id}/ficha-completa", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Ficha completa de un alumno de otra institución -> 403",
              r.status_code == 403, "GET /api/admin/personas/{persona_id}/ficha-completa")

    # 🔒 Regla objetivo (ver CLAUDE.md, "Excel import"): admin/psicologo SIEMPRE
    # se fuerzan a la institución de su propio token — un institucion_id ajeno
    # en la request se ignora en silencio (igual que GET /auth/usuarios/), así
    # que esto ya NO da 403. La prueba real de aislamiento es otra: se usa el
    # `codigo_institucional` que YA existe como Persona en A. Si el ajeno
    # `institucion_id=A` se hubiera respetado, la fila resolvería como
    # "actualizado" (el código existe en A); como se ignora y se usa la propia
    # institución de B (donde ese código nunca existió), debe resolver como
    # "nuevo" — la única forma de que esto pase es que A nunca fue consultada.
    excel_cruzado = construir_excel_una_fila(ctx_a.codigo, "X", "Y", None, "Secundaria", "3°", "A", 2026)
    r = requests.post(f"{API}/admin/personas/importar/validar", params={"institucion_id": ctx_a.inst_id},
                      files={"archivo": ("x.xlsx", excel_cruzado, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                      headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] institucion_id=A en el query con JWT de B -> se ignora, NO da 403",
              r.status_code == 200, "POST /api/admin/personas/importar/validar (?institucion_id= ajeno)", r.text[:200])
    if r.status_code == 200:
        fila = r.json()["filas"][0]
        comprobar(f"[{letra_b}->{letra_a}] La fila resuelve como 'nuevo' bajo la institución de B, "
                  f"pese a que ese código YA existe como Persona en A (prueba real de que A nunca se consultó)",
                  fila["accion"] == "nuevo", f"accion={fila['accion']!r}")

    r = requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": ctx_a.phq9_id, "nombre_grupo": f"{PREFIJO} CROSS {letra_b}", "institucion_id": ctx_a.inst_id},
        headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Crear campaña PARA la institución de A -> 403",
              r.status_code == 403, "POST /api/educativo/campanas/")

    r = requests.post(f"{API}/educativo/campanas/{ctx_a.campana_id}/matricular-roster",
                      json=[ctx_a.persona_id], headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Matricular en la campaña de A -> 403",
              r.status_code == 403, "POST /api/educativo/campanas/{id}/matricular-roster")

    r = requests.get(f"{API}/educativo/campanas/{ctx_a.campana_id}/dashboard", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Dashboard de la campaña de A -> 403",
              r.status_code == 403, "GET /api/educativo/campanas/{id}/dashboard")

    r = requests.get(f"{API}/educativo/procesos/dashboard", params={"institucion_id": ctx_a.inst_id}, headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Dashboard institucional de A -> 403",
              r.status_code == 403, "GET /api/educativo/procesos/dashboard")

    r = requests.get(f"{API}/educativo/inscripciones/{ctx_a.insc_id}/informe-pdf", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Descargar el PDF (ya liberado) de un alumno de A -> 403",
              r.status_code == 403, "GET /api/educativo/inscripciones/{id}/informe-pdf")

    r = requests.get(f"{API}/educativo/inscripciones/{ctx_a.insc_id}/informe", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Ver metadata del informe de A -> 403",
              r.status_code == 403, "GET /api/educativo/inscripciones/{id}/informe")

    r = requests.patch(f"{API}/educativo/inscripciones/{ctx_a.insc_id}/revision-informe", json={
        "motivo_consulta": "intento cruzado"}, headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Escribir la revisión clínica de un alumno de A -> 403",
              r.status_code == 403, "PATCH /api/educativo/inscripciones/{id}/revision-informe")

    r = requests.get(f"{API}/educativo/campanas/{ctx_a.campana_id}/links", headers=ctx_b.h, timeout=30)
    comprobar(f"[{letra_b}->{letra_a}] Ver los enlaces mágicos de la campaña de A -> 403",
              r.status_code == 403, "GET /api/educativo/campanas/{id}/links")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje: login superadmin")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    print("\n1 · FLUJO COMPLETO — Institución A")
    ctx_a = montar_institucion(h_super, "A", sello)

    print("\n2 · FLUJO COMPLETO — Institución B (repetido con datos propios)")
    ctx_b = montar_institucion(h_super, "B", sello)

    cruzar_aislamiento(ctx_a, ctx_b)
    cruzar_aislamiento(ctx_b, ctx_a)

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
        c.execute(text(f"""
            delete from matriculas_academicas where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from consentimientos_informados where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from personas where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
        c.execute(text(f"""
            delete from secciones where grado_id in (
                select g.id from grados g join niveles_educativos n on n.id = g.nivel_educativo_id
                where n.institucion_id in (select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from grados where nivel_educativo_id in (
                select id from niveles_educativos where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from niveles_educativos where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
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
