"""Verificación end-to-end de la Fase 4 contra el servidor real.

  D  validación psicométrica de baremos: rango invertido (422) y
     solapamiento del mismo público (409)
  D  rendimiento — dashboard por campaña con varios alumnos sigue agregando
     bien tras quitar el N+1, y el dashboard consolidado por institución
     agrupa por persona sin duplicar tras quitar su propio N+1

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_fase4_e2e.py
    python tests/verificar_fase4_e2e.py --limpiar
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

PREFIJO = "ZZF4"
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
    """Reintenta SOLO ante 429 de /auth (5/min por IP): el límite es correcto,
    pero puede toparse si esta suite corre justo después de otra que también
    usó /auth mucho desde la misma IP."""
    for _ in range(8):
        r = metodo(url, timeout=30, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login",
                 data={"username": email, "password": clave})


def crear_prueba_simple(headers, sello, sufijo):
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sufijo}-{sello}", "nombre_publico": f"Prueba {sufijo}"},
        headers=headers, timeout=30), 200, f"Prueba {sufijo}")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D", "opciones": opciones}
                      for i in (1, 2)]}, headers=headers, timeout=30), 200, f"Carga {sufijo}")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa",
                                  headers=headers, timeout=30), 200, f"Detalle {sufijo}")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    return prueba["id"], dim["id"], pregs


def montar_y_finalizar(headers, inst_id, prueba_id, pregs, sello, etiqueta, dni, valores):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": dni}, headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    mat = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                               json=[persona["id"]], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    token = mat["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    def opcion(orden, valor):
        return next(o["id"] for o in pregs[orden]["opciones"] if o["valor_puntuacion"] == valor)

    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": [
        {"pregunta_id": pregs[1]["id"], "opcion_id": opcion(1, valores[0])},
        {"pregunta_id": pregs[2]["id"], "opcion_id": opcion(2, valores[1])},
    ]}, timeout=30), 200, f"Guardar {etiqueta}")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, f"Finalizar {etiqueta}")
    return campana["id"], persona["id"]


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}"}, headers=h_super, timeout=30), 201, "Institución")
    inst_id = inst["id"]

    correo_psi = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro psicólogo", json={
        "email": correo_psi, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psi",
        "rol": "psicologo", "institucion_id": inst_id}, headers=h_super), 200, "Registro psicólogo")
    r = login(correo_psi, "ClaveDePrueba123")
    h_psi = {"Authorization": f"Bearer {exigir(r, 200, 'login psicólogo')['access_token']}"}

    # ------------------------------------------------------------
    print("\n1 · Validación psicométrica de baremos")
    prueba_id, dim_id, pregs = crear_prueba_simple(h_psi, sello, "BAR")

    r = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 10, "puntaje_maximo": 2, "nivel": "Invertido"},
        headers=h_psi, timeout=30)
    comprobar("Rango invertido (min > max) se rechaza con 422", r.status_code == 422, f"status {r.status_code}")

    b1 = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Bajo"},
        headers=h_psi, timeout=30), 200, "Baremo Bajo (0-1)")

    r = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 1, "puntaje_maximo": 2, "nivel": "Se solapa"},
        headers=h_psi, timeout=30)
    comprobar("Un tramo que toca el mismo público y se solapa (1-2 vs 0-1) se rechaza con 409",
              r.status_code == 409, f"status {r.status_code}: {r.text[:200]}")

    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 2, "puntaje_maximo": 2, "nivel": "Alto", "es_alerta": True},
        headers=h_psi, timeout=30), 200, "Baremo Alto (2-2), contiguo, no se solapa")

    r = requests.patch(f"{API}/educativo/baremos/{b1['id']}", json={"puntaje_maximo": 5},
                        headers=h_psi, timeout=30)
    comprobar("Editar un baremo para que invada el rango de otro (0-5 pisa 2-2) también se rechaza con 409",
              r.status_code == 409, f"status {r.status_code}")

    # ------------------------------------------------------------
    print("\n2 · Dashboard de campaña con varios alumnos (sin N+1)")
    campana_id, _ = montar_y_finalizar(h_psi, inst_id, prueba_id, pregs, sello, "M1", f"{sello}D1", (0, 0))
    campana2_id, persona_2 = montar_y_finalizar(h_psi, inst_id, prueba_id, pregs, sello, "M2", f"{sello}D2", (1, 1))
    # tercer alumno en la MISMA campaña que el primero
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} M3", "apellidos": "Alumno",
        "documento_identidad": f"{sello}D3"}, headers=h_psi, timeout=30), 200, "Persona M3")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
        headers=h_psi, timeout=30), 200, "Consentimiento M3")
    mat = exigir(requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                               json=[persona["id"]], headers=h_psi, timeout=30), 200, "Matrícula M3")
    token3 = mat["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token3}", json={
        "nombre_completo": "Alumno M3", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar M3")
    # M3 se queda "Pendiente" (no finaliza), para comprobar el conteo de pendientes

    dash = exigir(requests.get(f"{API}/educativo/campanas/{campana_id}/dashboard",
                               headers=h_psi, timeout=30), 200, "Dashboard campaña 1")
    comprobar("total_inscritos = 2 en la campaña 1", dash["total_inscritos"] == 2, str(dash["total_inscritos"]))
    comprobar("total_finalizados = 1, total_pendientes = 1",
              (dash["total_finalizados"], dash["total_pendientes"]) == (1, 1))
    comprobar("La distribución por dimensión trae el nivel 'Bajo' para el alumno que respondió 0+0",
              dash["distribucion_por_dimension"].get("D", {}).get("Bajo") == 1,
              str(dash["distribucion_por_dimension"]))
    finalizado = next(a for a in dash["alumnos"] if a["estado"] == "Finalizado")
    comprobar("El alumno finalizado trae su resultado con nivel 'Bajo'",
              finalizado["resultados"][0]["nivel"] == "Bajo", str(finalizado["resultados"]))

    # ------------------------------------------------------------
    print("\n3 · Dashboard consolidado por institución (sin N+1, agrupa por persona)")
    dashp = exigir(requests.get(f"{API}/educativo/procesos/dashboard?institucion_id={inst_id}",
                                headers=h_psi, timeout=30), 200, "Dashboard consolidado")
    comprobar("Trae 3 alumnos distintos consolidados (M1, M2, M3)",
              len(dashp["alumnos"]) == 3, str(len(dashp["alumnos"])))
    total_pruebas = sum(len(a["pruebas"]) for a in dashp["alumnos"])
    comprobar("Cada alumno trae exactamente 1 prueba en su historial (ninguno duplicado)",
              total_pruebas == 3, str(total_pruebas))

    # ------------------------------------------------------------
    print("\n4 · HALLAZGO CRÍTICO — casos pendientes de seguimiento con nivel 'inocuo'")
    # Mismo caso que probó C-13 en la Fase 1: un baremo con texto que NO está
    # en el set legacy NIVELES_DE_ALERTA pero SÍ marcado es_alerta=True. El
    # informe se retiene y se avisa por correo desde la Fase 1 — lo que
    # estaba roto era que este caso no aparecía en el worklist de casos
    # pendientes del psicólogo.
    prueba_r_id, dim_r_id, pregs_r = crear_prueba_simple(h_psi, sello, "SEG")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_r_id, "puntaje_minimo": 0, "puntaje_maximo": 0, "nivel": "Sin indicadores aparentes",
        "es_alerta": True}, headers=h_psi, timeout=30), 200, "Baremo con nivel inocuo pero es_alerta")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_r_id, "puntaje_minimo": 1, "puntaje_maximo": 2, "nivel": "Normal"},
        headers=h_psi, timeout=30), 200, "Baremo normal")
    _, persona_seg = montar_y_finalizar(
        h_psi, inst_id, prueba_r_id, pregs_r, sello, "SEG", f"{sello}SEG", (0, 0),
    )
    pendientes = exigir(requests.get(f"{API}/educativo/casos-pendientes?institucion_id={inst_id}",
                                     headers=h_psi, timeout=30), 200, "Casos pendientes")
    comprobar(
        "El caso con nivel inocuo pero es_alerta=True SÍ aparece en casos pendientes de seguimiento",
        any(p["persona_id"] == persona_seg for p in pendientes),
        str(pendientes),
    )

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E FASE 4: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF4%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF4%'"
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZF4%'"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM auditoria_arco WHERE institucion_id IN ({insts})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZF4%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZF4%'",
            f"DELETE FROM consentimientos_informados WHERE institucion_id IN ({insts})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            "DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE 'zzf4%')",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzf4%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZF4%'",
        ]:
            c.execute(text(q))
    print("Datos ZZF4 eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
