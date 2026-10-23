"""Verificación end-to-end del Núcleo del Estudiante contra el servidor real.

  1  crear estudiante (con código institucional) / consultar ficha
  2  no duplicar personas (documento y código, únicos por institución)
  3  crear nivel -> grado -> sección; matricular; consultar historial
  4  cambiar de sección conserva el historial y NO reescribe evaluaciones
     ya aplicadas (snapshot inmutable en Inscripcion)
  5  buscar por identificador institucional
  6  aislamiento entre instituciones (estructura académica y matrícula)
  7  el roster ya no pide re-ingresar datos personales (se derivan de la
     ficha) y la población se deriva del nivel educativo cuando coincide

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_nucleo_estudiante_e2e.py
    python tests/verificar_nucleo_estudiante_e2e.py --limpiar
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

PREFIJO = "ZZNUC"
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


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    # rol "admin": crear/editar estructura académica (niveles/grados/secciones)
    # exige admin o superadmin, igual que otras acciones administrativas
    # sensibles ya existentes (p. ej. anonimizar-arco).
    correo_a = f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro A", json={
        "email": correo_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} A",
        "rol": "admin", "institucion_id": inst_a}, headers=h_super), 200, "Registro A")
    h_a = {"Authorization": f"Bearer {exigir(login(correo_a, 'ClaveDePrueba123'), 200, 'login A')['access_token']}"}

    correo_b = f"{PREFIJO.lower()}.b.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro B", json={
        "email": correo_b, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} B",
        "rol": "admin", "institucion_id": inst_b}, headers=h_super), 200, "Registro B")
    h_b = {"Authorization": f"Bearer {exigir(login(correo_b, 'ClaveDePrueba123'), 200, 'login B')['access_token']}"}

    # ------------------------------------------------------------
    print("\n1 · Estructura académica: Institución -> Nivel -> Grado -> Sección")
    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": "Secundaria", "orden": 1},
        headers=h_a, timeout=30), 200, "Crear nivel")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "3°", "orden": 3},
        headers=h_a, timeout=30), 200, "Crear grado")
    seccion_2025 = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "turno": "Mañana", "anio_escolar": 2025},
        headers=h_a, timeout=30), 200, "Crear sección 2025-A")
    seccion_2026 = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "B", "turno": "Tarde", "anio_escolar": 2026},
        headers=h_a, timeout=30), 200, "Crear sección 2026-B")

    r = requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "turno": "Mañana", "anio_escolar": 2025},
        headers=h_a, timeout=30)
    comprobar("Repetir sección/grado/año se rechaza con 409", r.status_code == 409, f"status {r.status_code}")

    # 🔒 Aislamiento — B no puede leer ni escribir la estructura de A
    r = requests.get(f"{API}/admin/personas/academico/grados/{nivel['id']}", headers=h_b, timeout=30)
    comprobar("B no puede listar los grados del nivel de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "Z", "anio_escolar": 2025}, headers=h_b, timeout=30)
    comprobar("B no puede crear una sección en un grado de A (403)", r.status_code == 403, f"status {r.status_code}")

    # ------------------------------------------------------------
    print("\n2 · Crear estudiante — código institucional, sin duplicados")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Ana", "apellidos": "Torres",
        "documento_identidad": f"{sello}DNI1", "codigo_institucional": f"{PREFIJO}-{sello}-001",
        "fecha_nacimiento": "2011-03-05"}, headers=h_a, timeout=30), 200, "Crear persona")

    r = requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": "Otra", "apellidos": "Persona",
        "codigo_institucional": f"{PREFIJO}-{sello}-001"}, headers=h_a, timeout=30)
    comprobar("Repetir el código institucional en la MISMA institución se rechaza (409)",
              r.status_code == 409, f"status {r.status_code}")

    # El mismo código en OTRA institución sí es válido: unicidad por institución, no global.
    persona_b = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_b, "nombres": f"{PREFIJO} Bruno", "apellidos": "Lopez",
        "codigo_institucional": f"{PREFIJO}-{sello}-001"}, headers=h_b, timeout=30),
        200, "Mismo código en institución B (permitido)")
    comprobar("El mismo código institucional es válido en OTRA institución",
              persona_b["codigo_institucional"] == f"{PREFIJO}-{sello}-001")

    # ------------------------------------------------------------
    print("\n3 · Matricular al estudiante en una sección y consultar su ficha")
    mat1 = exigir(requests.post(f"{API}/admin/personas/{persona['id']}/matricula",
                                json={"seccion_id": seccion_2025["id"]}, headers=h_a, timeout=30),
                  200, "Matricular en 2025-A")
    comprobar("La matrícula queda vigente (fecha_fin None)", mat1["fecha_fin"] is None)

    ficha = exigir(requests.get(f"{API}/admin/personas/{persona['id']}/ficha-completa",
                                headers=h_a, timeout=30), 200, "Ficha completa")
    comprobar("La ficha trae la información académica actual (grado 3°, sección A, año 2025)",
              (ficha["informacion_academica_actual"]["grado"],
               ficha["informacion_academica_actual"]["seccion"],
               ficha["informacion_academica_actual"]["anio_escolar"]) == ("3°", "A", 2025),
              str(ficha["informacion_academica_actual"]))
    comprobar("El historial académico tiene 1 tramo (recién matriculado)",
              len(ficha["historial_academico"]) == 1)
    comprobar("La ficha expone el código institucional", ficha["datos_personales"]["codigo_institucional"] ==
              f"{PREFIJO}-{sello}-001")

    # 🔒 Regresión — GET /admin/personas/{institucion_id} (el padrón) resuelve
    # seccion_actual en una consulta batch (_secciones_vigentes_de_institucion),
    # un camino de código DISTINTO al de ficha-completa/historial-academico
    # (_describir_matricula, ya cubierto arriba con "3°"/"Mañana"). Un
    # diagnóstico previo sospechó que ese camino batch devolvía tildes/ñ/°
    # con doble codificación UTF-8; se descartó como falso positivo de una
    # herramienta de verificación local (python -m json.tool leyendo un pipe
    # sin PYTHONIOENCODING=utf-8 en Windows, no el servidor), pero esta
    # comprobación queda para que un futuro cambio real en ese camino no
    # pueda pasar inadvertido.
    padron = exigir(requests.get(f"{API}/admin/personas/{inst_a}", headers=h_a, timeout=30),
                    200, "Padrón institución A")
    fila = next((p for p in padron if p["id"] == persona["id"]), None)
    comprobar("El alumno matriculado aparece en el padrón con seccion_actual resuelta",
              fila is not None and fila.get("seccion_actual") is not None,
              str(fila.get("seccion_actual")) if fila else "no encontrado")
    if fila and fila.get("seccion_actual"):
        sa = fila["seccion_actual"]
        comprobar("seccion_actual.grado conserva el '°' sin doble-codificar (grado creado como '3°')",
                  sa["grado"] == "3°", f"grado={sa['grado']!r}")
        comprobar("seccion_actual.turno conserva la 'ñ' sin doble-codificar (turno creado como 'Mañana')",
                  sa["turno"] == "Mañana", f"turno={sa['turno']!r}")
        comprobar("seccion_actual apunta a la sección vigente correcta (A, año 2025)",
                  sa["seccion"] == "A" and sa["anio_escolar"] == 2025, str(sa))

    # 🔒 Aislamiento — B no puede matricular a un alumno de A, ni siquiera en su propia sección
    r = requests.post(f"{API}/admin/personas/{persona['id']}/matricula",
                       json={"seccion_id": seccion_2025["id"]}, headers=h_b, timeout=30)
    comprobar("B no puede matricular a un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")

    # ------------------------------------------------------------
    print("\n4 · El roster hereda sección/población; el snapshot de la evaluación es inmutable")
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-P-{sello}", "nombre_publico": "Prueba núcleo"},
        headers=h_a, timeout=30), 200, "Crear prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "D", "opciones": opciones}]},
        headers=h_a, timeout=30), 200, "Carga masiva")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa",
                                  headers=h_a, timeout=30), 200, "Detalle prueba")
    pregs = {p["orden"]: p for p in detalle["dimensiones"][0]["preguntas"]}
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": detalle["dimensiones"][0]["id"], "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Normal"},
        headers=h_a, timeout=30), 200, "Baremo")

    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=h_a, timeout=30), 200, "Consentimiento")

    mat_roster = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                      json=[persona["id"]], headers=h_a, timeout=30), 200, "Matrícula roster")
    token = mat_roster["generados"][0]["token"]

    insc_id, edad_snap, sexo_snap, poblacion_snap, seccion_id_snap, grado_seccion_snap = sql_uno(
        "select id, edad, sexo, poblacion, seccion_id, grado_seccion_historico "
        "from edu_inscripciones where token=:t", t=token,
    )
    comprobar("El roster heredó edad/sexo de la Persona sin pedirlos de nuevo",
              edad_snap is not None, f"edad={edad_snap}")
    comprobar("La población se derivó del nivel educativo ('Secundaria') sin que nadie la tipeara",
              poblacion_snap == "Secundaria", f"poblacion={poblacion_snap}")
    comprobar("La inscripción guardó un snapshot de la sección vigente (2025-A)",
              seccion_id_snap == seccion_2025["id"] and grado_seccion_snap == "3° A",
              f"seccion_id={seccion_id_snap} texto={grado_seccion_snap}")

    # El examen NO debería exigir que el alumno reescriba su nombre/edad/sexo
    # (ya vienen de la ficha); sigue pidiendo aceptar términos, que es el
    # único dato de este paso que la Persona no puede responder por él.
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "valor ignorado — ya viene de la ficha", "edad": 1, "sexo": "Femenino",
        "poblacion": "Universitario", "acepta_terminos": True}, timeout=30), 200, "Comenzar examen")
    edad_tras_comenzar, poblacion_tras_comenzar = sql_uno(
        "select edad, poblacion from edu_inscripciones where token=:t", t=token,
    )
    comprobar("El formulario NO pudo sobrescribir la edad ya conocida (sigue siendo la real, no 1)",
              edad_tras_comenzar == edad_snap, f"edad={edad_tras_comenzar}")
    comprobar("El formulario NO pudo sobrescribir la población ya derivada (sigue 'Secundaria', no 'Universitario')",
              poblacion_tras_comenzar == "Secundaria", f"poblacion={poblacion_tras_comenzar}")

    def opcion_de(valor):
        return next(o["id"] for o in pregs[1]["opciones"] if o["valor_puntuacion"] == valor)

    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": [
        {"pregunta_id": pregs[1]["id"], "opcion_id": opcion_de(1)}]}, timeout=30), 200, "Guardar respuesta")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")

    # ------------------------------------------------------------
    print("\n5 · Mover de sección: el historial crece, la evaluación pasada NO cambia")
    mat2 = exigir(requests.post(f"{API}/admin/personas/{persona['id']}/matricula",
                                json={"seccion_id": seccion_2026["id"]}, headers=h_a, timeout=30),
                  200, "Mover a 2026-B")
    comprobar("La nueva matrícula queda vigente", mat2["fecha_fin"] is None)
    comprobar("La matrícula anterior (2025-A) ya no es la misma fila", mat2["id"] != mat1["id"])

    historial = exigir(requests.get(f"{API}/admin/personas/{persona['id']}/historial-academico",
                                    headers=h_a, timeout=30), 200, "Historial académico")
    comprobar("El historial ahora tiene 2 tramos (2025-A y 2026-B)", len(historial) == 2, str(len(historial)))
    comprobar("El primer tramo (2025-A) quedó CERRADO (fecha_fin no nula)",
              historial[0]["fecha_fin"] is not None)
    comprobar("El segundo tramo (2026-B) está vigente (fecha_fin nula)",
              historial[1]["fecha_fin"] is None and historial[1]["seccion"] == "B")

    seccion_id_snap_2, grado_seccion_snap_2 = sql_uno(
        "select seccion_id, grado_seccion_historico from edu_inscripciones where token=:t", t=token,
    )
    comprobar(
        "La evaluación YA APLICADA sigue apuntando a la sección histórica (2025-A), "
        "no a la nueva (2026-B), pese a que el alumno ya se movió",
        seccion_id_snap_2 == seccion_2025["id"] and grado_seccion_snap_2 == "3° A",
        f"seccion_id={seccion_id_snap_2} texto={grado_seccion_snap_2}",
    )

    ficha2 = exigir(requests.get(f"{API}/admin/personas/{persona['id']}/ficha-completa",
                                 headers=h_a, timeout=30), 200, "Ficha tras mover de sección")
    comprobar("La ficha ahora muestra la sección ACTUAL (2026-B)",
              (ficha2["informacion_academica_actual"]["seccion"],
               ficha2["informacion_academica_actual"]["anio_escolar"]) == ("B", 2026))
    comprobar("El historial de evaluaciones de la ficha sigue teniendo 1 aplicación, sin duplicarse",
              len(ficha2["historial_evaluaciones"]) == 1)

    # ------------------------------------------------------------
    print("\n6 · Búsqueda por identificador institucional")
    encontrado = exigir(requests.get(
        f"{API}/admin/personas/por-codigo/{PREFIJO}-{sello}-001", headers=h_a, timeout=30,
    ), 200, "Buscar por código")
    comprobar("Encuentra al alumno correcto por su código institucional", encontrado["id"] == persona["id"])

    r = requests.get(f"{API}/admin/personas/por-codigo/{PREFIJO}-{sello}-001", headers=h_b, timeout=30)
    comprobar("B busca ese mismo código pero en SU institución y encuentra a SU propio alumno (no al de A)",
              r.status_code == 200 and r.json()["id"] == persona_b["id"], f"status {r.status_code}")

    r = requests.get(f"{API}/admin/personas/por-codigo/CODIGO-QUE-NO-EXISTE", headers=h_a, timeout=30)
    comprobar("Un código inexistente devuelve 404", r.status_code == 404, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E NÚCLEO DEL ESTUDIANTE: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZNUC%'"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE nivel_educativo_id IN ({niveles})"
    secciones = f"SELECT id FROM secciones WHERE grado_id IN ({grados})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZNUC%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZNUC%'"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZNUC%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZNUC%'",
            f"DELETE FROM consentimientos_informados WHERE institucion_id IN ({insts})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE id IN ({secciones})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
            "DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE 'zznuc%')",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zznuc%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZNUC%'",
        ]:
            c.execute(text(q))
    print("Datos ZZNUC eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
