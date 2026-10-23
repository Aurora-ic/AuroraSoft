"""Verificación end-to-end — Trazabilidad y soft-delete de Baremo (PUNTO 1
de la auditoría de arquitectura genérica).

Cubre:

  1   DiagnosticoAlumno.baremo_id apunta al Baremo real que interpretó
  2   Un baremo CON diagnósticos no permite editar rango/nivel/es_alerta (409)
  3   Ese mismo baremo SÍ permite editar contenido informativo (interpretacion)
  4   Ese mismo baremo SIEMPRE permite desactivarse (activo=false), aunque
      esté en uso — es la única vía para "cambiar de criterio"
  5   actualizado_en pasa de NULL a un timestamp CON zona horaria tras un PATCH
  6   Un baremo desactivado deja de aplicarse a nuevas interpretaciones
      (el alumno siguiente cae en "sin baremo aplicable", NO "sin riesgo")
  7   Un tramo de reemplazo puede cubrir el MISMO rango que el desactivado
      (ya no cuenta para el chequeo de solapamiento)
  8   DELETE físico sigue funcionando sobre un baremo SIN uso
  9   DELETE sobre un baremo CON uso desactiva en vez de borrar (idempotente)
  10  Regresión ligera: PHQ-9 y la prueba técnica interna sin cambios

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_baremo_trazabilidad_e2e.py
    python tests/verificar_baremo_trazabilidad_e2e.py --limpiar
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZBAR"
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


def crear_colegio(h_super, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    correo = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, "Registro")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, "Login")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


def crear_prueba_con_dos_tramos(headers, sello, n_items=5):
    """1 dimensión, correcto_incorrecto, tramo 'Bajo' (0-1, sin alerta) y
    tramo 'Alto' (2-{n_items}, con alerta) — sin huecos entre 0 y n_items."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba de trazabilidad",
        "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=headers, timeout=30), 200, "Prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    preguntas_carga = [
        {"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D", "opciones": opciones}
        for i in range(1, n_items + 1)
    ]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}], "preguntas": preguntas_carga},
        headers=headers, timeout=30), 200, "Carga")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=headers, timeout=30), 200, "Detalle")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    baremo_bajo = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Bajo", "es_alerta": False},
        headers=headers, timeout=30), 200, "Baremo bajo")
    baremo_alto = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 2, "puntaje_maximo": n_items, "nivel": "Alto", "es_alerta": True},
        headers=headers, timeout=30), 200, "Baremo alto")
    return prueba["id"], dim["id"], pregs, baremo_bajo, baremo_alto


def aplicar(headers, inst_id, sello, etiqueta, prueba_id, pregs, n_correctas):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=headers, timeout=30), 200, f"Persona {etiqueta}")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    token = matricula["generados"][0]["token"]

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    n_items = len(pregs)
    respuestas = []
    for orden, pregunta in pregs.items():
        acerto = orden <= n_correctas
        valor = 1 if acerto else 0
        opcion_id = next(o["id"] for o in pregunta["opciones"] if o["valor_puntuacion"] == valor)
        respuestas.append({"pregunta_id": pregunta["id"], "opcion_id": opcion_id})
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]
    return insc


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_id, h = crear_colegio(h_super, sello)
    prueba_id, dim_id, pregs, baremo_bajo, baremo_alto = crear_prueba_con_dos_tramos(h, sello)

    baremos_iniciales = sql_uno(
        "select actualizado_en, activo from edu_baremos where id=:i", i=baremo_alto["id"])
    comprobar("[5] Un baremo recién creado tiene actualizado_en = NULL (nunca editado)", baremos_iniciales[0] is None)
    comprobar("[modelo] Un baremo recién creado nace activo=True", baremos_iniciales[1] is True)

    # ==================================================================
    print("\n1 · DiagnosticoAlumno.baremo_id apunta al Baremo real")
    insc_alto = aplicar(h, inst_id, sello, "Alto1", prueba_id, pregs, n_correctas=4)  # 4/5 -> tramo Alto (2-5)
    diag = sql_uno("select baremo_id, nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_alto)
    comprobar("[1] baremo_id apunta EXACTAMENTE al baremo 'Alto' usado", diag[0] == baremo_alto["id"], str(diag))
    comprobar("[1] El nivel/alerta coinciden con ese baremo", diag[1] == "Alto" and diag[2] is True)

    # ==================================================================
    print("\n2-3 · Bloqueo de edición sobre un baremo EN USO")
    r_bloqueado_nivel = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}",
                                       json={"nivel": "Otro nombre"}, headers=h, timeout=30)
    comprobar("[2] Editar 'nivel' de un baremo en uso -> 409", r_bloqueado_nivel.status_code == 409, r_bloqueado_nivel.text[:200])
    r_bloqueado_rango = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}",
                                       json={"puntaje_minimo": 3}, headers=h, timeout=30)
    comprobar("[2] Editar 'puntaje_minimo' de un baremo en uso -> 409", r_bloqueado_rango.status_code == 409)
    r_bloqueado_alerta = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}",
                                        json={"es_alerta": False}, headers=h, timeout=30)
    comprobar("[2] Editar 'es_alerta' de un baremo en uso -> 409", r_bloqueado_alerta.status_code == 409)

    baremo_sin_tocar = sql_uno("select nivel, puntaje_minimo, es_alerta from edu_baremos where id=:i", i=baremo_alto["id"])
    comprobar("[2] Ninguno de los 3 intentos bloqueados cambió realmente el baremo",
              baremo_sin_tocar == ("Alto", 2, True), str(baremo_sin_tocar))

    r_contenido_ok = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}",
                                    json={"interpretacion": "Texto informativo nuevo, no es criterio de clasificación."},
                                    headers=h, timeout=30)
    comprobar("[3] Editar 'interpretacion' (contenido, no criterio) SÍ se permite aunque esté en uso",
              r_contenido_ok.status_code == 200, r_contenido_ok.text[:200])

    fila_tras_contenido = sql_uno("select actualizado_en from edu_baremos where id=:i", i=baremo_alto["id"])
    comprobar("[5] actualizado_en pasó de NULL a un valor tras el PATCH", fila_tras_contenido[0] is not None)
    comprobar("[5] actualizado_en quedó con zona horaria (tzinfo)", fila_tras_contenido[0].tzinfo is not None)

    # ==================================================================
    print("\n4 · Desactivar SIEMPRE se permite, incluso en uso")
    r_desactivar = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}",
                                  json={"activo": False}, headers=h, timeout=30)
    comprobar("[4] PATCH activo=false sobre un baremo en uso -> 200 (nunca bloqueado)", r_desactivar.status_code == 200)
    comprobar("[4] Queda activo=False en la base", r_desactivar.json()["activo"] is False)

    # ==================================================================
    print("\n6 · Un baremo desactivado deja de aplicarse a interpretaciones nuevas")
    insc_huerfano = aplicar(h, inst_id, sello, "Huerfano", prueba_id, pregs, n_correctas=4)  # mismo 4/5 de antes
    estado_huerfano = sql_uno(
        "select estado_interpretacion, dimensiones_sin_baremo, resultado_visible_alumno from edu_inscripciones where id=:i",
        i=insc_huerfano)
    comprobar("[6] Con el tramo Alto desactivado y sin reemplazo, esta dimensión queda SIN baremo aplicable",
              estado_huerfano[0] == "incompleta" and estado_huerfano[1] is not None, str(estado_huerfano))
    comprobar("[6] El informe queda retenido (NUNCA se confunde con 'sin riesgo')", estado_huerfano[2] is False)
    diag_huerfano = sql_uno("select id from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_huerfano)
    comprobar("[6] No se generó ningún DiagnosticoAlumno para esta dimensión", diag_huerfano is None)

    # ==================================================================
    print("\n7 · Un tramo de reemplazo SÍ puede cubrir el mismo rango que el desactivado")
    r_reemplazo = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 2, "puntaje_maximo": 5, "nivel": "Alto (revisado)", "es_alerta": True},
        headers=h, timeout=30)
    comprobar("[7] Crear un baremo nuevo sobre el MISMO rango que el desactivado -> 200 (no 409)",
              r_reemplazo.status_code == 200, r_reemplazo.text[:200])
    baremo_reemplazo = r_reemplazo.json()

    insc_reemplazo = aplicar(h, inst_id, sello, "Reemplazo", prueba_id, pregs, n_correctas=4)
    diag_reemplazo = sql_uno("select baremo_id, nivel from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_reemplazo)
    comprobar("[7] El alumno nuevo queda interpretado por el baremo DE REEMPLAZO, no el desactivado",
              diag_reemplazo[0] == baremo_reemplazo["id"] and diag_reemplazo[1] == "Alto (revisado)", str(diag_reemplazo))
    comprobar("[7] Su baremo_id es DISTINTO del baremo desactivado", diag_reemplazo[0] != baremo_alto["id"])

    # ==================================================================
    print("\n8-9 · DELETE físico vs. desactivación según uso")
    r_delete_sin_uso = requests.delete(f"{API}/educativo/baremos/{baremo_bajo['id']}", headers=h, timeout=30)
    comprobar("[8] DELETE sobre un baremo SIN uso -> 200, mensaje 'eliminado'",
              r_delete_sin_uso.status_code == 200 and "eliminado" in r_delete_sin_uso.json()["mensaje"].lower())
    existe_bajo = sql_uno("select count(*) from edu_baremos where id=:i", i=baremo_bajo["id"])[0]
    comprobar("[8] Efectivamente ya no existe la fila", existe_bajo == 0)

    r_delete_con_uso = requests.delete(f"{API}/educativo/baremos/{baremo_alto['id']}", headers=h, timeout=30)
    comprobar("[9] DELETE sobre un baremo CON uso -> 200, mensaje distinto ('desactivó', no 'eliminó')",
              r_delete_con_uso.status_code == 200 and "desactiv" in r_delete_con_uso.json()["mensaje"].lower())
    fila_alto_tras_delete = sql_uno("select activo from edu_baremos where id=:i", i=baremo_alto["id"])
    comprobar("[9] La fila SIGUE existiendo (no fue un DELETE físico)", fila_alto_tras_delete is not None)
    comprobar("[9] Sigue activo=False", fila_alto_tras_delete[0] is False)
    diag_intacto = sql_uno("select baremo_id from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_alto)
    comprobar("[9] El diagnóstico histórico que lo usaba SIGUE apuntando a él (no se rompió nada)",
              diag_intacto[0] == baremo_alto["id"])

    # ==================================================================
    print("\n10 · REGRESIÓN LIGERA — PHQ-9 y la prueba técnica interna sin cambios")
    conteo_phq9 = sql_uno(
        "select count(*) from edu_baremos b join edu_dimensiones d on d.id=b.dimension_id "
        "join edu_pruebas p on p.id=d.prueba_id where p.nombre_tecnico='PHQ-9'")[0]
    comprobar("[10] PHQ-9 sigue teniendo sus 5 tramos de baremo, ninguno tocado", conteo_phq9 == 5, str(conteo_phq9))
    conteo_activos_phq9 = sql_uno(
        "select count(*) from edu_baremos b join edu_dimensiones d on d.id=b.dimension_id "
        "join edu_pruebas p on p.id=d.prueba_id where p.nombre_tecnico='PHQ-9' and b.activo=true")[0]
    comprobar("[10] Los 5 siguen activos (el default True no desactivó nada existente)", conteo_activos_phq9 == 5)

    conteo_apt = sql_uno(
        "select count(*) from edu_baremos b join edu_dimensiones d on d.id=b.dimension_id "
        "join edu_pruebas p on p.id=d.prueba_id where p.nombre_tecnico='APTITUD_TECNICA_INTERNA' and b.activo=true")[0]
    comprobar("[10] Los 18 tramos de la prueba técnica interna siguen activos", conteo_apt == 18, str(conteo_apt))

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
