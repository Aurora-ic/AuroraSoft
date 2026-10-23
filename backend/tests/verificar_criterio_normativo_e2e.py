"""Verificación end-to-end — Baremo.criterio_normativo / Prueba.criterio_normativo_activo.

Cubre:

  1   Dos tramos que se solapan en rango de puntaje pero con criterio_normativo
      DISTINTO -> se crean los dos sin 409 (no son un duplicado real).
  2   Dos tramos que se solapan en rango de puntaje con el MISMO criterio
      (ambos NULL, el caso de siempre) -> sigue dando 409, sin cambio.
  3   Con Prueba.criterio_normativo_activo = NULL (default), una inscripción
      se interpreta contra los tramos del criterio clásico (NULL).
  4   PATCH /educativo/pruebas/{id} con criterio_normativo_activo="alt" + un
      POST .../reprocesar sobre esa misma inscripción cambia la interpretación
      al criterio alternativo — sin re-tomar el examen, sin tocar las
      respuestas crudas — y el informe cambia de retenido a liberado (o
      viceversa) acorde al nuevo criterio.
  5   Toda InformeVersion anterior sigue intacta (bytes idénticos) tras el
      reproceso.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python -m tests.verificar_criterio_normativo_e2e
    python -m tests.verificar_criterio_normativo_e2e --limpiar
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

PREFIJO = "ZZCRIT"
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


def esperar_informe_version(inscripcion_id, numero_version=1, timeout=20):
    """El PDF se genera en un BackgroundTask tras finalizar/reprocesar: hace
    polling breve a la BD hasta que la versión aparece (mismo patrón que
    esperar_informe() en verificar_informe_phq9_e2e.py)."""
    limite = time.time() + timeout
    fila = None
    while time.time() < limite:
        fila = sql_uno(
            "select v.numero_version, v.checksum_sha256 from edu_informe_versiones v "
            "join edu_informes i on i.id = v.informe_id "
            "where i.inscripcion_id=:ins and v.numero_version=:n",
            ins=inscripcion_id, n=numero_version)
        if fila:
            return fila
        time.sleep(0.5)
    return fila


def login(email, clave):
    return requests.post(f"{API}/auth/login", data={"username": email, "password": clave}, timeout=30)


def crear_colegio(h_super, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    correo = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(requests.post(f"{API}/auth/registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super, timeout=30), 200, "Registro")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, "Login")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


def crear_prueba_con_dos_criterios(headers, sello, n_items=10):
    """1 dimensión 'D', correcto_incorrecto, 10 ítems (puntaje 0-10).

    Criterio clásico (criterio_normativo=NULL, activo por defecto):
      0-4 'Bajo' (sin alerta), 5-10 'Alto' (alerta).
    Criterio alternativo ("alt"), que SE SOLAPA en rango de puntaje con el
    clásico (0-10 completo) pero no debe chocar con él:
      0-10 'UnicoAlt' (sin alerta) — un solo tramo, deliberadamente sin
      alerta para que el cambio de criterio sea observable sin ambigüedad.
    """
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba de criterio normativo",
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
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 4, "nivel": "Bajo", "es_alerta": False},
        headers=headers, timeout=30), 200, "Baremo Bajo (clásico)")
    baremo_alto = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 5, "puntaje_maximo": n_items, "nivel": "Alto", "es_alerta": True},
        headers=headers, timeout=30), 200, "Baremo Alto (clásico)")

    # [1] Se solapa en rango (0-10 cubre 0-4 y 5-10) pero criterio DISTINTO -> 200, no 409.
    r_alt = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": n_items, "nivel": "UnicoAlt",
        "es_alerta": False, "criterio_normativo": "alt"},
        headers=headers, timeout=30)
    comprobar("[1] Tramo del criterio 'alt' que se solapa en rango con el clásico -> 200 (no 409)",
              r_alt.status_code == 200, r_alt.text[:300])
    baremo_alt = r_alt.json() if r_alt.status_code == 200 else None

    # [2] Otro tramo del MISMO criterio clásico (NULL) que se solapa con 'Bajo' -> 409, sin cambio.
    r_duplicado = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 2, "puntaje_maximo": 6, "nivel": "Duplicado", "es_alerta": False},
        headers=headers, timeout=30)
    comprobar("[2] Tramo del MISMO criterio (NULL) que se solapa con uno existente -> sigue dando 409",
              r_duplicado.status_code == 409, r_duplicado.text[:300])

    return prueba["id"], dim["id"], pregs, baremo_bajo, baremo_alto, baremo_alt


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

    print("\n1-2 · Solapamiento: criterios distintos no chocan, el mismo criterio sigue chocando")
    prueba_id, dim_id, pregs, baremo_bajo, baremo_alto, baremo_alt = crear_prueba_con_dos_criterios(h, sello)
    comprobar("El tramo 'alt' se creó con criterio_normativo='alt'", baremo_alt is not None and baremo_alt.get("criterio_normativo") == "alt")

    # ==================================================================
    print("\n3 · Con criterio_normativo_activo=NULL, interpreta contra el criterio clásico")
    insc = aplicar(h, inst_id, sello, "Alumno1", prueba_id, pregs, n_correctas=7)  # 7/10 -> tramo Alto (5-10)
    diag_clasico = sql_uno(
        "select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc)
    comprobar("[3] Con el criterio clásico activo, 7/10 interpreta como 'Alto' (alerta)",
              diag_clasico == ("Alto", True), str(diag_clasico))
    estado_clasico = sql_uno(
        "select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc)
    comprobar("[3] El informe queda retenido (es_alerta=True bajo el criterio clásico)",
              estado_clasico[0] is False and estado_clasico[1] is False, str(estado_clasico))

    version_v1 = esperar_informe_version(insc, numero_version=1)
    comprobar("[3] Se generó la InformeVersion v1 automática", version_v1 is not None and version_v1[0] == 1)

    # ==================================================================
    print("\n4 · Cambiar criterio_normativo_activo + reprocesar cambia la interpretación")
    r_patch = requests.patch(f"{API}/educativo/pruebas/{prueba_id}", json={"criterio_normativo_activo": "alt"},
                             headers=h_super, timeout=30)
    comprobar("[4] PATCH /pruebas/{id} con criterio_normativo_activo='alt' -> 200", r_patch.status_code == 200, r_patch.text[:300])
    comprobar("[4] La prueba queda con criterio_normativo_activo='alt'", r_patch.json().get("criterio_normativo_activo") == "alt")

    r_reproceso = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar",
                                json={"motivo": f"{PREFIJO} cambio de criterio normativo"},
                                headers=h_super, timeout=60)
    comprobar("[4] POST .../reprocesar con el nuevo criterio activo -> 200", r_reproceso.status_code == 200, r_reproceso.text[:300])

    diag_alt = sql_uno("select nivel, es_alerta, baremo_id from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc)
    comprobar("[4] Tras reprocesar, el mismo puntaje (7/10) ahora interpreta bajo el criterio 'alt' ('UnicoAlt', sin alerta)",
              diag_alt[0] == "UnicoAlt" and diag_alt[1] is False, str(diag_alt))
    comprobar("[4] El baremo_id apunta al tramo 'alt', no al 'Alto' clásico",
              diag_alt[2] == baremo_alt["id"] and diag_alt[2] != baremo_alto["id"])

    estado_alt = sql_uno(
        "select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc)
    comprobar("[4] El informe se LIBERA automáticamente al reprocesar bajo un criterio sin alerta",
              estado_alt[0] is True and estado_alt[1] is True, str(estado_alt))

    # ==================================================================
    print("\n5 · La versión anterior del informe sigue intacta")
    version_v2 = sql_uno(
        "select v.numero_version, v.checksum_sha256, v.origen from edu_informe_versiones v "
        "join edu_informes i on i.id = v.informe_id where i.inscripcion_id=:ins order by v.numero_version desc limit 1",
        ins=insc)
    comprobar("[5] Se generó una v2 con origen='reproceso'", version_v2[0] == 2 and version_v2[2] == "reproceso", str(version_v2))
    version_v1_tras = sql_uno(
        "select checksum_sha256 from edu_informe_versiones v join edu_informes i on i.id = v.informe_id "
        "where i.inscripcion_id=:ins and v.numero_version=1", ins=insc)
    comprobar("[5] La v1 sigue teniendo EXACTAMENTE el mismo checksum (bytes idénticos, nunca se reescribió)",
              version_v1_tras[0] == version_v1[1], str((version_v1_tras[0], version_v1[1])))

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
        c.execute(text(f"delete from edu_informe_versiones where informe_id in "
                       f"(select inf.id from edu_informes inf join edu_inscripciones ins on ins.id = inf.inscripcion_id "
                       f"join edu_evaluaciones ev on ev.id = ins.evaluacion_id where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_informes where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
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
