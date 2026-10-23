"""Verificación end-to-end — Reproceso de informe tras corrección de baremo.

Contexto: `reemitir_informe` (ya existente) solo vuelve a renderizar el PDF
con lo que YA está en `DiagnosticoAlumno` — no recalcula nada, así que
corregir un baremo mal configurado nunca se reflejaba en una inscripción ya
finalizada (gap documentado en CLAUDE.md). `reprocesar_informe_de_inscripcion`
(`POST /inscripciones/{id}/reprocesar`) cierra ese hueco: recalcula desde las
respuestas crudas contra los baremos/reglas VIGENTES y emite una nueva
versión — respetando la misma forma transaccional que `finalizar_examen_seguro`
(bloqueo de fila + `populate_existing()`, commit único, misma fórmula de
alerta).

Cubre:

  PARTE A — mecanismo, determinista: dos sesiones ORM reales reproducen la
  misma carrera que `verificar_concurrencia_finalizar_e2e.py` ya prueba para
  `finalizar_examen_seguro`, pero contra `bloquear_inscripcion_para_reprocesar`.

  PARTE B — end-to-end, realista:
    1   Finalizar con un baremo "Bajo" (sin alerta) -> informe v1,
        origen='automatica', sin alerta, visible y liberado.
    2   psicólogo intenta /reprocesar -> 403 (rol restringido a admin/superadmin)
    3   admin de OTRA institución intenta /reprocesar -> 403
    4   Se corrige el baremo (desactivar + crear uno nuevo con es_alerta=True
        sobre el MISMO rango — el único camino real, porque un baremo en uso
        no admite editar su rango/nivel/es_alerta) y se reprocesa como admin
        -> 200, v2 con origen='reproceso' y motivo, DiagnosticoAlumno apunta
        al nuevo baremo, resultado_visible_alumno/informe_liberado pasan a
        False, estado sigue "Finalizado", fecha_resolucion no cambia, v1
        sigue intacta en storage (mismo checksum).
    5   Se corrige de nuevo hacia un baremo sin alerta y se reprocesa otra
        vez -> v3, vuelve a quedar visible/liberado sin que nadie tenga que
        liberar el informe a mano — misma fórmula que finalizar, simétrica
        en ambas direcciones.
    6   /reprocesar sobre una inscripción que NO está "Finalizado" -> 400.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_reproceso_informe_e2e.py
    python tests/verificar_reproceso_informe_e2e.py --limpiar
"""

import argparse
import inspect
import os
import sys
import threading
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

import modulos.superadmin.crud  # noqa: E402,F401  (ver nota de import circular en verificar_concurrencia_finalizar_e2e.py)
from core.database import SessionLocal  # noqa: E402
from modulos.educativo import crud as edu_crud, models as edu_models  # noqa: E402

PREFIJO = "ZZREPR"
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


def crear_colegio_completo(h_super, sello, etiqueta):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {etiqueta} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{etiqueta.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {etiqueta}")

    def registrar_y_loguear(rol, sufijo):
        correo = f"{PREFIJO.lower()}.{sufijo}.{etiqueta.lower()}.{sello}@ejemplo.com"
        exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {sufijo}", json={
            "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} {rol}",
            "rol": rol, "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro {sufijo}")
        tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {sufijo}")["access_token"]
        return {"Authorization": f"Bearer {tok}"}

    h_psi = registrar_y_loguear("psicologo", "psi")
    h_admin = registrar_y_loguear("admin", "admin")
    return inst["id"], h_psi, h_admin


def crear_prueba_con_un_baremo(h, sello, n_items, nivel, es_alerta):
    """1 dimensión, correcto_incorrecto, UN tramo que cubre TODO el rango
    posible [0, n_items] — así cualquier cantidad de respuestas correctas cae
    siempre en ese mismo tramo, sin depender de cuántas se marquen."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba de reproceso",
        "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=h, timeout=30), 200, "Prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    preguntas_carga = [
        {"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D", "opciones": opciones}
        for i in range(1, n_items + 1)
    ]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}], "preguntas": preguntas_carga},
        headers=h, timeout=30), 200, "Carga")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=h, timeout=30), 200, "Detalle")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    baremo = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": n_items,
        "nivel": nivel, "es_alerta": es_alerta},
        headers=h, timeout=30), 200, f"Baremo {nivel}")
    return prueba["id"], dim["id"], pregs, baremo


def matricular_y_finalizar(h, inst_id, sello, prueba_id, pregs):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_id},
        headers=h, timeout=30), 200, "Campaña")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba",
        "documento_identidad": f"{sello}901", "genero": "Femenino"}, headers=h, timeout=30), 200, "Persona")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h, timeout=30), 200, "Consentimiento")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=h, timeout=30), 200, "Matrícula")
    token = matricula["generados"][0]["token"]

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar")

    respuestas = [
        {"pregunta_id": p["id"], "opcion_id": next(o["id"] for o in p["opciones"] if o["valor_puntuacion"] == 1)}
        for p in pregs.values()
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "Guardar")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]
    return insc


def esperar_version(inscripcion_id, numero_esperado, limite_seg=20):
    limite = time.time() + limite_seg
    while time.time() < limite:
        fila = sql_uno(
            "select v.id, v.origen, v.checksum_sha256 from edu_informe_versiones v "
            "join edu_informes i on i.id = v.informe_id "
            "where i.inscripcion_id=:i and v.numero_version=:n", i=inscripcion_id, n=numero_esperado)
        if fila:
            return fila
        time.sleep(0.5)
    return None


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_id, h_psi, h_admin = crear_colegio_completo(h_super, sello, "A")
    inst_id_b, _, h_admin_b = crear_colegio_completo(h_super, sello, "B")

    prueba_id, dim_id, pregs, baremo_bajo = crear_prueba_con_un_baremo(h_psi, sello, n_items=3, nivel="Bajo", es_alerta=False)

    # ==================================================================
    print("\nPARTE A · Mecanismo, determinista (dos sesiones ORM reales, sin HTTP)")
    insc_para_carrera = matricular_y_finalizar(h_psi, inst_id, sello + "R", prueba_id, pregs)
    # Vuelve a "Finalizado" tras montarla; se usa solo como fila de prueba
    # para el candado, igual que verificar_concurrencia_finalizar_e2e.py.

    resultado_perdedor = {}
    barrera = threading.Barrier(2)
    trazas = []
    traza_lock = threading.Lock()
    t_inicio = time.perf_counter()

    def trazar(msg):
        with traza_lock:
            trazas.append(f"+{time.perf_counter()-t_inicio:.4f} {msg}")

    def hilo_ganador():
        db = SessionLocal()
        try:
            f1 = db.query(edu_models.Inscripcion).filter(edu_models.Inscripcion.id == insc_para_carrera).first()
            trazar(f"[GANADOR] Fase1 estado={f1.estado}")
            barrera.wait()
            fila = edu_crud.bloquear_inscripcion_para_reprocesar(db=db, inscripcion_id=insc_para_carrera)
            trazar(f"[GANADOR] Fase2 devolvió estado={fila.estado} mismo_obj={fila is f1}")
            time.sleep(0.3)
            # 🆕 Cierre de gap (docs/gaps-pendientes.md) — ya no puede ser un
            # string inventado como "ZZREPR_GANADOR": ck_inscripciones_
            # estado_valido ahora lo rechazaría. La fila llega aquí en
            # "Finalizado" (ver matricular_y_finalizar arriba), así que
            # "En Progreso" sigue siendo un valor real y distinto, igual de
            # útil para distinguir "vio lo confirmado por el ganador" de
            # "vio su propia Fase 1".
            fila.estado = "En Progreso"
            db.commit()
            trazar("[GANADOR] COMMIT hecho")
        finally:
            db.close()

    def hilo_perdedor():
        db = SessionLocal()
        try:
            f1 = db.query(edu_models.Inscripcion).filter(edu_models.Inscripcion.id == insc_para_carrera).first()
            trazar(f"[PERDEDOR] Fase1 estado={f1.estado}")
            barrera.wait()
            time.sleep(0.6)
            fila = edu_crud.bloquear_inscripcion_para_reprocesar(db=db, inscripcion_id=insc_para_carrera)
            trazar(f"[PERDEDOR] Fase2 devolvió estado={fila.estado} mismo_obj={fila is f1}")
            resultado_perdedor["estado"] = fila.estado
        finally:
            db.rollback()
            db.close()

    th_g = threading.Thread(target=hilo_ganador)
    th_p = threading.Thread(target=hilo_perdedor)
    th_g.start()
    th_p.start()
    th_g.join()
    th_p.join()
    for linea in trazas:
        print("    " + linea)

    comprobar(
        "bloquear_inscripcion_para_reprocesar del perdedor ve el estado YA "
        "confirmado por el ganador, no el valor obsoleto de su propia Fase 1",
        resultado_perdedor.get("estado") == "En Progreso",
        f"vio estado={resultado_perdedor.get('estado')!r}",
    )

    db_restaurar = SessionLocal()
    try:
        fila = db_restaurar.query(edu_models.Inscripcion).filter(edu_models.Inscripcion.id == insc_para_carrera).first()
        fila.estado = "Finalizado"
        db_restaurar.commit()
    finally:
        db_restaurar.close()

    # ==================================================================
    print("\n1 · Finalizar con baremo 'Bajo' (sin alerta) -> v1 automática")
    insc = matricular_y_finalizar(h_psi, inst_id, sello, prueba_id, pregs)
    fecha_resolucion_v1 = sql_uno("select fecha_resolucion from edu_inscripciones where id=:i", i=insc)[0]

    v1 = esperar_version(insc, 1)
    comprobar("[1] v1 se generó", v1 is not None, str(v1))
    if v1:
        comprobar("[1] v1.origen == 'automatica'", v1[1] == "automatica")

    estado_v1 = sql_uno(
        "select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc)
    comprobar("[1] Sin alerta: visible y liberado", estado_v1 == (True, True), str(estado_v1))

    diag_v1 = sql_uno("select baremo_id, nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc)
    comprobar("[1] DiagnosticoAlumno apunta al baremo 'Bajo'", diag_v1[0] == baremo_bajo["id"], str(diag_v1))

    # 🆕 docs/gaps-pendientes.md — una revisión manual (sin cambiar
    # visibilidad) deja un revisor_original real en revisado_por_usuario_id,
    # para que el paso 4 (regresión) tenga a quién avisar puntualmente.
    r_revision_manual = exigir(requests.patch(
        f"{API}/educativo/inscripciones/{insc}/revision-informe",
        json={"interpretacion_clinica": "Revisión manual de control, sin cambios de visibilidad"},
        headers=h_psi, timeout=30), 200, "Revisión manual")
    comprobar("[1b] La revisión manual no cambia la visibilidad ya vigente",
              r_revision_manual["resultado_visible_alumno"] is True and r_revision_manual["informe_liberado"] is True)
    revisor_original_id = sql_uno("select revisado_por_usuario_id from edu_inscripciones where id=:i", i=insc)[0]
    comprobar("[1b] revisado_por_usuario_id quedó registrado", revisor_original_id is not None)

    # ==================================================================
    print("\n2-3 · Rol restringido: psicólogo y admin de OTRA institución -> 403")
    r_psi = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar",
                          json={"motivo": "Intento de psicólogo"}, headers=h_psi, timeout=30)
    comprobar("[2] psicólogo -> 403", r_psi.status_code == 403, r_psi.text[:200])

    r_otro_colegio = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar",
                                   json={"motivo": "Intento cruzado"}, headers=h_admin_b, timeout=30)
    comprobar("[3] admin de otra institución -> 403", r_otro_colegio.status_code == 403, r_otro_colegio.text[:200])

    r_sin_motivo = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar", json={}, headers=h_admin, timeout=30)
    comprobar("[2-3] admin sin 'motivo' -> 422 (motivo obligatorio)", r_sin_motivo.status_code == 422)

    # ==================================================================
    print("\n4 · Corregir el baremo (desactivar + reemplazo con alerta) y reprocesar como admin")
    r_desactivar = requests.patch(f"{API}/educativo/baremos/{baremo_bajo['id']}", json={"activo": False},
                                  headers=h_psi, timeout=30)
    comprobar("[4] Desactivar el baremo 'Bajo' en uso -> 200 (siempre permitido)", r_desactivar.status_code == 200)

    baremo_alto = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 0, "puntaje_maximo": 3, "nivel": "Alto (corregido)", "es_alerta": True},
        headers=h_psi, timeout=30), 200, "Baremo corregido")

    r_reproceso = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar",
                                json={"motivo": "Se corrigió el baremo: el tramo 0-3 debía ser de alerta"},
                                headers=h_admin, timeout=30)
    comprobar("[4] admin reprocesa -> 200", r_reproceso.status_code == 200, r_reproceso.text[:300])
    cuerpo_reproceso = r_reproceso.json()
    comprobar("[4] La respuesta indica requiere_revision=True", cuerpo_reproceso.get("requiere_revision") is True)
    comprobar("[4] numero_version == 2", cuerpo_reproceso.get("numero_version") == 2, str(cuerpo_reproceso))
    # 🆕 docs/gaps-pendientes.md — esta corrección SÍ retiene de nuevo un
    # informe que ya estaba liberado/visible (ver paso 1), y SÍ hay un
    # revisor original real (ver paso 1b) al que avisar puntualmente.
    comprobar("[4] La respuesta indica retraccion_informe_liberado=True",
              cuerpo_reproceso.get("retraccion_informe_liberado") is True, str(cuerpo_reproceso))
    comprobar("[4] La respuesta indica revisor_original_notificado=True",
              cuerpo_reproceso.get("revisor_original_notificado") is True, str(cuerpo_reproceso))

    v2 = esperar_version(insc, 2)
    comprobar("[4] v2 se generó", v2 is not None)
    if v2:
        comprobar("[4] v2.origen == 'reproceso'", v2[1] == "reproceso")
    comprobar("[4] v1 sigue intacta en storage (mismo checksum de antes)",
              v1 is not None and v2 is not None and sql_uno(
                  "select checksum_sha256 from edu_informe_versiones where id=:i", i=v1[0])[0] == v1[2])

    retracta_v2 = sql_uno("select retracta_version_previa_liberada from edu_informe_versiones where id=:i", i=v2[0])[0]
    comprobar("[4] v2.retracta_version_previa_liberada == True (reemplaza una v1 que ya era visible)",
              retracta_v2 is True)

    diag_v2 = sql_uno("select baremo_id, nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc)
    comprobar("[4] DiagnosticoAlumno ahora apunta al baremo corregido", diag_v2[0] == baremo_alto["id"], str(diag_v2))
    comprobar("[4] es_alerta ahora True", diag_v2[2] is True)

    estado_v2 = sql_uno(
        "select estado, resultado_visible_alumno, informe_liberado, fecha_resolucion from edu_inscripciones where id=:i",
        i=insc)
    comprobar("[4] estado sigue 'Finalizado'", estado_v2[0] == "Finalizado")
    comprobar("[4] resultado_visible_alumno pasó a False (informe retenido de nuevo)", estado_v2[1] is False)
    comprobar("[4] informe_liberado pasó a False", estado_v2[2] is False)
    comprobar("[4] fecha_resolucion NO cambió (hecho histórico)", estado_v2[3] == fecha_resolucion_v1)

    r_reprocesar_no_finalizado_check = sql_uno(
        "select generado_por_usuario_id, motivo_version from edu_informe_versiones where id=:i", i=v2[0])
    comprobar("[4] v2 quedó con generado_por_usuario_id y motivo trazados",
              r_reprocesar_no_finalizado_check[0] is not None and "corrigió" in r_reprocesar_no_finalizado_check[1])

    # ==================================================================
    print("\n5 · Corregir de nuevo hacia 'sin alerta' -> vuelve a quedar visible/liberado, sin liberar a mano")
    r_desactivar2 = requests.patch(f"{API}/educativo/baremos/{baremo_alto['id']}", json={"activo": False},
                                   headers=h_psi, timeout=30)
    comprobar("[5] Desactivar el baremo 'Alto (corregido)' -> 200", r_desactivar2.status_code == 200)
    baremo_final = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id, "puntaje_minimo": 0, "puntaje_maximo": 3, "nivel": "Bajo (definitivo)", "es_alerta": False},
        headers=h_psi, timeout=30), 200, "Baremo final")

    r_reproceso2 = requests.post(f"{API}/educativo/inscripciones/{insc}/reprocesar",
                                 json={"motivo": "Segunda corrección: el tramo no era de alerta"},
                                 headers=h_admin, timeout=30)
    comprobar("[5] Segundo reproceso -> 200", r_reproceso2.status_code == 200, r_reproceso2.text[:300])
    cuerpo_reproceso2 = r_reproceso2.json()
    comprobar("[5] requiere_revision == False", cuerpo_reproceso2.get("requiere_revision") is False)
    # 🆕 docs/gaps-pendientes.md — esta corrección libera de nuevo el
    # informe, no lo retiene: no hay regresión que anunciar (la inscripción
    # YA estaba retenida desde el paso 4, así que esto no "retracta" nada
    # que estuviera circulando).
    comprobar("[5] retraccion_informe_liberado == False (esto LIBERA, no retiene)",
              cuerpo_reproceso2.get("retraccion_informe_liberado") is False, str(cuerpo_reproceso2))
    comprobar("[5] revisor_original_notificado == False (no hubo regresión que avisar)",
              cuerpo_reproceso2.get("revisor_original_notificado") is False)

    v3 = esperar_version(insc, 3)
    comprobar("[5] v3 se generó con origen='reproceso'", v3 is not None and v3[1] == "reproceso")

    retracta_v3 = sql_uno("select retracta_version_previa_liberada from edu_informe_versiones where id=:i", i=v3[0])[0]
    comprobar("[5] v3.retracta_version_previa_liberada == False", retracta_v3 is False)

    estado_v3 = sql_uno(
        "select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc)
    comprobar("[5] resultado_visible_alumno vuelve a True SIN llamar a liberar-informe",
              estado_v3[0] is True, str(estado_v3))
    comprobar("[5] informe_liberado vuelve a True", estado_v3[1] is True)

    # ==================================================================
    print("\n6 · /reprocesar sobre una inscripción que NO está 'Finalizado' -> 400")
    campana_pendiente = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Pendiente {sello}", "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Campaña pendiente")
    persona_pendiente = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} Pendiente", "apellidos": "Prueba",
        "documento_identidad": f"{sello}902", "genero": "Femenino"}, headers=h_psi, timeout=30), 200, "Persona pendiente")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona_pendiente}/consentimiento", json={
        "persona_id": persona_pendiente, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h_psi, timeout=30), 200, "Consentimiento pendiente")
    mat_pendiente = exigir(requests.post(f"{API}/educativo/campanas/{campana_pendiente['id']}/matricular-roster",
                                         json=[persona_pendiente], headers=h_psi, timeout=30), 200, "Matrícula pendiente")
    insc_pendiente = sql_uno("select id from edu_inscripciones where token=:t", t=mat_pendiente["generados"][0]["token"])[0]

    r_pendiente = requests.post(f"{API}/educativo/inscripciones/{insc_pendiente}/reprocesar",
                                json={"motivo": "No debería aplicar"}, headers=h_admin, timeout=30)
    comprobar("[6] Reprocesar una inscripción 'Pendiente' -> 400", r_pendiente.status_code == 400, r_pendiente.text[:200])

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
        # edu_informes/edu_informe_versiones caen solas por ON DELETE CASCADE.
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
