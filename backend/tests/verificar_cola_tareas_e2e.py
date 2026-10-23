"""Verificación end-to-end — Cambio B del plan de arquitectura "paginación
real y cola de tareas asíncronas" (sesión 2026-10-17): la Fase 2 de
core/models_tareas.py, Celery+Redis reemplazando BackgroundTasks para los
5 sitios reales de modulos/educativo/router.py.

Cubre:
  1   Finalizar un examen real -> el informe PDF se genera igual que
      siempre (`esperar_informe`, mismo helper que verificar_informe_
      phq9_e2e.py), PERO ahora a través de un worker Celery real: se
      confirma consultando `registro_tareas_asincronas` directamente que
      la fila terminó 'exito' Y con un `job_id` real (NO None) — el único
      modo en que `job_id` se llena es `self.request.id` dentro de la
      ejecución real de la tarea por un worker (ver
      core/tareas_async.ejecutar_tarea_registrada), así que un job_id real
      es evidencia directa de que pasó por Celery, no de una llamada
      directa en el mismo proceso.
  2   El enganche automático de documentos (`generar_documento_automatico`)
      también deja su propia fila 'exito' con job_id real, aunque esta
      institución no tenga ninguna PlantillaDocumento con generación
      automática activada (el bitácora se escribe igual, la tarea
      simplemente no encuentra nada que generar).
  3   tareas/reconciliar_tareas_colgadas.py contra una fila REAL marcada a
      mano como 'en_progreso' desde hace 30 minutos: se confirma que la
      marca 'fallo' (con intentos=1) Y que re-encola de verdad -- aparece
      una fila NUEVA del mismo tipo_tarea/referencia_id con su propio
      job_id, y esa segunda ejecución reemite el informe (version_actual
      pasa a 2) -- prueba que el re-encolado no es solo un UPDATE de fila,
      sino una tarea Celery real ejecutándose de nuevo.

Deliberadamente FUERA de este e2e: forzar un reintento real de
`enviar_alerta_riesgo`/`enviar_alerta_regresion_informe_liberado`. Estos
dos no escriben en `registro_tareas_asincronas` (no tienen fila propia que
inspeccionar -- ver su docstring en core/email_service.py), y como el SMTP
va deshabilitado en todo e2e de este proyecto (EMAIL_USUARIO/EMAIL_PASSWORD
vacíos), forzar su camino de reintento real tardaría minutos (3 intentos ×
60s de backoff) solo para confirmar un mecanismo que ya se prueba acá con
la tarea del informe -- las 4 tareas comparten la misma app Celery
(core/cola_tareas.py), así que el mismo mecanismo de despacho/reintento
aplica a las 4 por igual.

Uso:
    uvicorn main:app --port 8010                      (EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    celery -A core.cola_tareas worker --loglevel=info  (Redis real corriendo en localhost:6379)
    python -m tests.verificar_cola_tareas_e2e
    python -m tests.verificar_cola_tareas_e2e --limpiar
"""

import argparse
import os
import subprocess
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

PREFIJO = "ZZCOLA"
API = "http://127.0.0.1:8010/api"
RAIZ_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def sql_ejecutar(consulta, **p):
    with MOTOR.begin() as c:
        c.execute(text(consulta), p)


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


def esperar_fila_registro_tarea(tipo_tarea, referencia_id, excluir_id=None, timeout=20):
    """Polling breve (la tarea corre en un worker Celery real, fuera de
    este proceso) a la fila MÁS RECIENTE de `registro_tareas_asincronas`
    para ese tipo_tarea/referencia_id, en estado terminal ('exito'/'fallo')
    -- opcionalmente excluyendo una fila ya conocida (para esperar la
    SIGUIENTE, tras un re-encolado)."""
    limite = time.time() + timeout
    clausula_excluir = "and id != :excluir_id" if excluir_id is not None else ""
    while time.time() < limite:
        fila = sql_uno(
            f"""select id, estado, job_id, intentos, error_detalle from registro_tareas_asincronas
                where tipo_tarea=:t and referencia_id=:r {clausula_excluir}
                and estado in ('exito', 'fallo') order by id desc limit 1""",
            t=tipo_tarea, r=referencia_id, excluir_id=excluir_id,
        )
        if fila:
            return fila
        time.sleep(0.5)
    return None


def esperar_informe(headers, inscripcion_id, timeout=20):
    limite = time.time() + timeout
    while time.time() < limite:
        r = requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30)
        if r.status_code == 200 and r.json().get("existe"):
            return r.json()
        time.sleep(0.5)
    return requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30).json()


def responder_phq9(token, preguntas_por_orden, valores):
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno Cola", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar test")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preguntas_por_orden[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [
        {"pregunta_id": preguntas_por_orden[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)}
        for i, v in enumerate(valores)
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar",
                         json={"respuestas": respuestas}, timeout=30), 200, "Guardar respuestas")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    inst_id = inst["id"]
    correo = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo",
        "rol": "psicologo", "institucion_id": inst_id}, headers=h_super), 200, "Registro")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, "Login")["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    fila_phq9 = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")
    comprobar("[montaje] Existe la prueba pública PHQ-9 (seed_phq9 ya corrido)", fila_phq9 is not None)
    if not fila_phq9:
        print("\n!! Ejecuta `python -m seeds.seed_phq9` antes de correr este E2E.")
        sys.exit(1)
    phq9_id = fila_phq9[0]

    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa",
                                       headers=h, timeout=30), 200, "Detalle PHQ-9")
    # El PHQ-9 real de esta base puede estar dividido en más de una dimensión
    # (ej. "Afectivo-Cognitiva"/"Somática") — las preguntas se juntan de
    # TODAS las dimensiones, no solo la primera, para cubrir los 9 ítems.
    preg_phq9 = {
        p["orden"]: p
        for dim in detalle_phq9["dimensiones"]
        for p in dim["preguntas"]
    }
    comprobar("[montaje] El catálogo PHQ-9 trae 9 preguntas en total (sin importar cuántas dimensiones)",
              len(preg_phq9) == 9, str(sorted(preg_phq9.keys())))

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}COLA", "genero": "Femenino"},
        headers=h, timeout=30), 200, "Persona")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"},
        headers=h, timeout=30), 200, "Consentimiento")

    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_id},
        headers=h, timeout=30), 200, "Campaña")
    m = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                             json=[persona], headers=h, timeout=30), 200, "Matrícula")
    token_examen = m["generados"][0]["token"]

    # ==================================================================
    print("\n1 · Finalizar examen -> el informe PDF se genera vía un worker Celery real")
    responder_phq9(token_examen, preg_phq9, [0] * 9)
    r = requests.post(f"{API}/educativo/examen/{token_examen}/finalizar", timeout=60)
    comprobar("[1] Finaliza correctamente (200) -- _encolar_sin_bloquear no lo frena ni lo rompe",
              r.status_code == 200, f"status {r.status_code}")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token_examen)
    comprobar("[montaje] La inscripción real existe", insc is not None)
    inscripcion_id = insc[0]

    meta_informe = esperar_informe(h, inscripcion_id)
    comprobar("[1] El informe se generó igual que siempre (la vía Celery no cambia el resultado visible)",
              meta_informe.get("existe") is True)
    comprobar("[1] version_actual == 1 en la primera emisión", meta_informe.get("version_actual") == 1)

    fila_informe = esperar_fila_registro_tarea("generar_informe", inscripcion_id)
    comprobar("[1] Hay una fila registro_tareas_asincronas 'generar_informe' para esta inscripción",
              fila_informe is not None)
    if fila_informe:
        comprobar("[1] Terminó en 'exito'", fila_informe[1] == "exito", str(fila_informe))
        comprobar("[1] job_id quedó lleno con un id REAL de Celery (no None) -- prueba que corrió "
                  "en un worker real, no en el mismo proceso que atendió el request",
                  fila_informe[2] is not None, f"job_id={fila_informe[2]!r}")

    fila_documento = esperar_fila_registro_tarea("generar_documento_automatico", inscripcion_id)
    comprobar("[2] El enganche automático de documentos también deja su propia fila "
              "(aunque esta institución no tenga ninguna plantilla con generación automática)",
              fila_documento is not None)
    if fila_documento:
        comprobar("[2] Terminó en 'exito' (no encontrar plantillas no es un error)",
                  fila_documento[1] == "exito", str(fila_documento))
        comprobar("[2] job_id también quedó lleno con un id real de Celery",
                  fila_documento[2] is not None, f"job_id={fila_documento[2]!r}")

    # ==================================================================
    print("\n3 · Reconciliación — una fila colgada de verdad se marca 'fallo' y se re-encola")
    sql_ejecutar("""
        insert into registro_tareas_asincronas (tipo_tarea, referencia_id, estado, iniciado_en, intentos)
        values ('generar_informe', :r, 'en_progreso', now() - interval '30 minutes', 0)
    """, r=inscripcion_id)
    fila_colgada_id = sql_uno(
        "select id from registro_tareas_asincronas where tipo_tarea='generar_informe' and referencia_id=:r "
        "and estado='en_progreso' order by id desc limit 1", r=inscripcion_id,
    )[0]

    proceso = subprocess.run(
        [sys.executable, "-m", "tareas.reconciliar_tareas_colgadas", "--minutos", "15"],
        cwd=RAIZ_BACKEND, capture_output=True, text=True, timeout=60,
    )
    comprobar("[3] El script de reconciliación corre sin error", proceso.returncode == 0, proceso.stderr[:300])
    comprobar("[3] Reporta haber reconciliado al menos 1 tarea", "Reconciliadas" in proceso.stdout, proceso.stdout.strip())

    fila_marcada = sql_uno(
        "select estado, intentos, error_detalle from registro_tareas_asincronas where id=:id", id=fila_colgada_id,
    )
    comprobar("[3] La fila colgada quedó en 'fallo'", fila_marcada[0] == "fallo", str(fila_marcada))
    comprobar("[3] intentos pasó de 0 a 1", fila_marcada[1] == 1)
    comprobar("[3] error_detalle explica que fue la reconciliación", "Reconciliación" in (fila_marcada[2] or ""))

    fila_reencolada = esperar_fila_registro_tarea("generar_informe", inscripcion_id, excluir_id=fila_colgada_id, timeout=20)
    comprobar("[3] Se re-encoló de verdad: apareció una fila NUEVA (no la ya vista) que también terminó",
              fila_reencolada is not None)
    if fila_reencolada:
        comprobar("[3] Esa nueva ejecución real también terminó en 'exito'", fila_reencolada[1] == "exito")
        comprobar("[3] Y tiene su PROPIO job_id (una ejecución Celery distinta, no la misma fila reusada)",
                  fila_reencolada[2] is not None and fila_reencolada[2] != "")

    meta_tras_reconciliar = esperar_informe(h, inscripcion_id)
    comprobar("[3] El re-encolado de verdad regeneró el informe: ahora hay una v2",
              meta_tras_reconciliar.get("version_actual") == 2, str(meta_tras_reconciliar.get("version_actual")))

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
            delete from registro_tareas_asincronas where referencia_id in (
                select i.id from edu_inscripciones i
                join edu_evaluaciones e on e.id = i.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_informe_versiones where informe_id in (
                select i.id from edu_informes i
                join edu_inscripciones ins on ins.id = i.inscripcion_id
                join edu_evaluaciones e on e.id = ins.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_informes where inscripcion_id in (
                select i.id from edu_inscripciones i
                join edu_evaluaciones e on e.id = i.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_respuestas_alumno where inscripcion_id in (
                select i.id from edu_inscripciones i
                join edu_evaluaciones e on e.id = i.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_diagnosticos_alumno where inscripcion_id in (
                select i.id from edu_inscripciones i
                join edu_evaluaciones e on e.id = i.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_resultados_dimensiones where inscripcion_id in (
                select i.id from edu_inscripciones i
                join edu_evaluaciones e on e.id = i.evaluacion_id
                where e.nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"""
            delete from edu_inscripciones where evaluacion_id in (
                select id from edu_evaluaciones where nombre_grupo like '{PREFIJO}%')"""))
        c.execute(text(f"delete from edu_evaluaciones where nombre_grupo like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from consentimientos_informados where persona_id in (
                select id from personas where documento_identidad like '%{PREFIJO}%' or nombres like '{PREFIJO}%')"""))
        c.execute(text(f"delete from personas where nombres like '{PREFIJO}%'"))
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
