"""Verificación end-to-end — Ciclo de vida de campaña: editar / cerrar / cancelar.

Cubre:

  1   Una campaña nace con estado='activa' (EvaluacionResponse la expone)
  2   PATCH edita nombre_grupo/fecha_fin/prueba_id mientras no hay inscripciones
  3   'colegio' recibe 403 en editar/cerrar/cancelar (nunca ese rol)
  4   En cuanto existe una Inscripcion, prueba_id queda bloqueado (409) pero
      nombre_grupo/fecha_fin siguen editables
  5   Cerrar fuerza fecha_fin a "ahora": comenzar-test/preguntas/progreso/
      guardar/finalizar quedan en 410 de inmediato, y matricular-roster
      rechaza con su propio mensaje de error (sin excepción)
  6   Una campaña cerrada/cancelada no admite más ediciones (409) ni un
      segundo cierre/cancelación (409)
  7   Cancelar una campaña SIN resultados finalizados -> 200
  8   Cancelar una campaña CON al menos una Inscripcion Finalizado -> 409
      (la vía correcta ahí es cerrar, que sí funciona)

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_campanas_ciclo_vida_e2e.py
    python tests/verificar_campanas_ciclo_vida_e2e.py --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZCAMP"
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


def crear_colegio_con_psicologo_y_colegio(h_super, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")

    correo_psi = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro psicologo", json={
        "email": correo_psi, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, "Registro psicólogo")
    tok_psi = exigir(login(correo_psi, "ClaveDePrueba123"), 200, "Login psicólogo")["access_token"]

    correo_col = f"{PREFIJO.lower()}.col.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro colegio", json={
        "email": correo_col, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Colegio",
        "rol": "colegio", "institucion_id": inst["id"]}, headers=h_super), 200, "Registro colegio")
    tok_col = exigir(login(correo_col, "ClaveDePrueba123"), 200, "Login colegio")["access_token"]

    return (
        inst["id"],
        {"Authorization": f"Bearer {tok_psi}"},
        {"Authorization": f"Bearer {tok_col}"},
    )


def crear_prueba_minima(h, sello, etiqueta):
    return exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}-{etiqueta}", "nombre_publico": f"Prueba {etiqueta}"},
        headers=h, timeout=30), 200, f"Prueba {etiqueta}")["id"]


def crear_persona_con_consentimiento(h, inst_id, sello, etiqueta):
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=h, timeout=30), 200, f"Persona {etiqueta}")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h, timeout=30), 200, f"Consentimiento {etiqueta}")
    return persona


def matricular(h, campana_id, persona_id):
    r = requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                       json=[persona_id], headers=h, timeout=30)
    return exigir(r, 200, "Matrícula")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_id, h_psi, h_col = crear_colegio_con_psicologo_y_colegio(h_super, sello)
    prueba_a = crear_prueba_minima(h_psi, sello, "A")
    prueba_b = crear_prueba_minima(h_psi, sello, "B")

    # ==================================================================
    print("\n1 · Una campaña nace 'activa'")
    c1 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_a, "nombre_grupo": f"{PREFIJO} C1 {sello}", "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Crear C1")
    comprobar("[1] estado == 'activa'", c1["estado"] == "activa", str(c1))
    comprobar("[1] activo sigue en True (columna legacy, sin efecto)", c1["activo"] is True)

    # ==================================================================
    print("\n2 · Editar sin inscripciones: nombre_grupo, fecha_fin y prueba_id, todos permitidos")
    fecha_futura = (datetime.utcnow() + timedelta(days=30)).isoformat()
    r_edit1 = requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={
        "nombre_grupo": f"{PREFIJO} C1 renombrada {sello}", "fecha_fin": fecha_futura},
        headers=h_psi, timeout=30)
    comprobar("[2] PATCH nombre_grupo+fecha_fin -> 200", r_edit1.status_code == 200, r_edit1.text[:200])
    comprobar("[2] nombre_grupo quedó actualizado", r_edit1.json()["nombre_grupo"] == f"{PREFIJO} C1 renombrada {sello}")

    r_edit_prueba = requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={"prueba_id": prueba_b},
                                    headers=h_psi, timeout=30)
    comprobar("[2] PATCH prueba_id sin inscripciones -> 200", r_edit_prueba.status_code == 200, r_edit_prueba.text[:200])
    comprobar("[2] prueba_id quedó actualizado", r_edit_prueba.json()["prueba_id"] == prueba_b)

    # ==================================================================
    print("\n3 · 'colegio' recibe 403 en editar/cerrar/cancelar")
    comprobar("[3] PATCH como colegio -> 403",
              requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={"nombre_grupo": "x"},
                              headers=h_col, timeout=30).status_code == 403)
    comprobar("[3] cerrar como colegio -> 403",
              requests.post(f"{API}/educativo/campanas/{c1['id']}/cerrar", json={},
                            headers=h_col, timeout=30).status_code == 403)
    comprobar("[3] cancelar como colegio -> 403",
              requests.post(f"{API}/educativo/campanas/{c1['id']}/cancelar", json={"motivo": "x"*5},
                            headers=h_col, timeout=30).status_code == 403)

    # ==================================================================
    print("\n4 · En cuanto hay una Inscripcion, prueba_id queda bloqueado")
    persona1 = crear_persona_con_consentimiento(h_psi, inst_id, sello, "P1")
    mat1 = matricular(h_psi, c1["id"], persona1)
    token1 = mat1["generados"][0]["token"]

    r_prueba_bloqueada = requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={"prueba_id": prueba_a},
                                        headers=h_psi, timeout=30)
    comprobar("[4] PATCH prueba_id CON inscripciones -> 409", r_prueba_bloqueada.status_code == 409, r_prueba_bloqueada.text[:200])
    comprobar("[4] prueba_id NO cambió en la base",
              sql_uno("select prueba_id from edu_evaluaciones where id=:i", i=c1["id"])[0] == prueba_b)

    r_nombre_sigue_editable = requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={"nombre_grupo": f"{PREFIJO} C1 v2 {sello}"},
                                             headers=h_psi, timeout=30)
    comprobar("[4] nombre_grupo sigue editable CON inscripciones -> 200", r_nombre_sigue_editable.status_code == 200)

    # ==================================================================
    print("\n5 · Cerrar fuerza fecha_fin a 'ahora': el flujo de examen queda en 410 de inmediato")
    persona2 = crear_persona_con_consentimiento(h_psi, inst_id, sello, "P2")
    mat2 = matricular(h_psi, c1["id"], persona2)
    token2_no_iniciado = mat2["generados"][0]["token"]

    r_comenzar1 = requests.post(f"{API}/educativo/comenzar-test/{token1}", json={
        "nombre_completo": "Alumno P1", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30)
    comprobar("[5-setup] comenzar-test ANTES de cerrar -> 200", r_comenzar1.status_code == 200, r_comenzar1.text[:200])

    r_cerrar = requests.post(f"{API}/educativo/campanas/{c1['id']}/cerrar", json={}, headers=h_psi, timeout=30)
    comprobar("[5] cerrar (motivo omitido) -> 200", r_cerrar.status_code == 200, r_cerrar.text[:200])
    cerrada = r_cerrar.json()
    comprobar("[5] estado == 'cerrada'", cerrada["estado"] == "cerrada")

    fila_cierre = sql_uno("select fecha_cierre, cerrada_por_usuario_id, fecha_fin from edu_evaluaciones where id=:i", i=c1["id"])
    comprobar("[5] fecha_cierre quedó registrada", fila_cierre[0] is not None)
    comprobar("[5] cerrada_por_usuario_id quedó registrado", fila_cierre[1] is not None)
    comprobar("[5] fecha_fin fue forzada a 'ahora' (ya no queda en 30 días)", fila_cierre[2] < datetime.utcnow() + timedelta(minutes=2))

    comprobar("[5] comenzar-test de un token NUNCA iniciado -> 410 tras cerrar",
              requests.post(f"{API}/educativo/comenzar-test/{token2_no_iniciado}", json={
                  "nombre_completo": "Alumno P2", "edad": 15, "sexo": "Femenino",
                  "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30).status_code == 410)
    comprobar("[5] progreso de un token YA iniciado -> 410 tras cerrar",
              requests.get(f"{API}/educativo/examen/{token1}/progreso", timeout=30).status_code == 410)
    comprobar("[5] preguntas -> 410 tras cerrar",
              requests.get(f"{API}/educativo/examen/{token1}/preguntas", timeout=30).status_code == 410)
    comprobar("[5] guardar -> 410 tras cerrar",
              requests.post(f"{API}/educativo/examen/{token1}/guardar", json={"respuestas": []}, timeout=30).status_code == 410)
    comprobar("[5] finalizar -> 410 tras cerrar",
              requests.post(f"{API}/educativo/examen/{token1}/finalizar", timeout=30).status_code == 410)

    persona3 = crear_persona_con_consentimiento(h_psi, inst_id, sello, "P3")
    r_matricular_tras_cerrar = matricular(h_psi, c1["id"], persona3)
    comprobar("[5] matricular-roster tras cerrar rechaza con su propio mensaje (sin excepción)",
              r_matricular_tras_cerrar.get("generados") == [] and "cierre" in (r_matricular_tras_cerrar.get("error") or "").lower(),
              str(r_matricular_tras_cerrar))

    # ==================================================================
    print("\n6 · Una campaña cerrada no admite más ediciones ni un segundo cierre/cancelación")
    comprobar("[6] PATCH sobre campaña cerrada -> 409",
              requests.patch(f"{API}/educativo/campanas/{c1['id']}", json={"nombre_grupo": "x"},
                              headers=h_psi, timeout=30).status_code == 409)
    comprobar("[6] cerrar de nuevo -> 409",
              requests.post(f"{API}/educativo/campanas/{c1['id']}/cerrar", json={}, headers=h_psi, timeout=30).status_code == 409)
    comprobar("[6] cancelar una campaña ya cerrada -> 409",
              requests.post(f"{API}/educativo/campanas/{c1['id']}/cancelar", json={"motivo": "x"*5},
                            headers=h_psi, timeout=30).status_code == 409)

    # ==================================================================
    print("\n7 · Cancelar una campaña SIN resultados finalizados")
    c2 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_a, "nombre_grupo": f"{PREFIJO} C2 {sello}", "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Crear C2")
    r_cancelar_c2 = requests.post(f"{API}/educativo/campanas/{c2['id']}/cancelar", json={"motivo": "Se decidió no aplicarla"},
                                  headers=h_psi, timeout=30)
    comprobar("[7] cancelar C2 (sin inscripciones) -> 200", r_cancelar_c2.status_code == 200, r_cancelar_c2.text[:200])
    comprobar("[7] estado == 'cancelada'", r_cancelar_c2.json()["estado"] == "cancelada")

    r_cancelar_sin_motivo = requests.post(f"{API}/educativo/campanas/{c1['id']}/cancelar", json={},
                                          headers=h_psi, timeout=30)
    comprobar("[7] cancelar sin 'motivo' -> 422 (motivo obligatorio)", r_cancelar_sin_motivo.status_code == 422)

    # ==================================================================
    print("\n8 · Cancelar una campaña CON una Inscripcion Finalizado -> 409 (cerrar sí funciona)")
    c3 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_a, "nombre_grupo": f"{PREFIJO} C3 {sello}", "institucion_id": inst_id},
        headers=h_psi, timeout=30), 200, "Crear C3")
    persona4 = crear_persona_con_consentimiento(h_psi, inst_id, sello, "P4")
    mat4 = matricular(h_psi, c3["id"], persona4)
    token4 = mat4["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token4}", json={
        "nombre_completo": "Alumno P4", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar P4")
    exigir(requests.post(f"{API}/educativo/examen/{token4}/finalizar", timeout=60), 200, "Finalizar P4 (sin preguntas)")

    r_cancelar_c3 = requests.post(f"{API}/educativo/campanas/{c3['id']}/cancelar", json={"motivo": "Intento indebido"},
                                  headers=h_psi, timeout=30)
    comprobar("[8] cancelar C3 (con 1 Finalizado) -> 409", r_cancelar_c3.status_code == 409, r_cancelar_c3.text[:200])

    r_cerrar_c3 = requests.post(f"{API}/educativo/campanas/{c3['id']}/cerrar", json={"motivo": "Cierre normal"},
                                headers=h_psi, timeout=30)
    comprobar("[8] cerrar C3 (con 1 Finalizado) -> 200 (cerrar SÍ está permitido)", r_cerrar_c3.status_code == 200, r_cerrar_c3.text[:200])

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
        c.execute(text(f"delete from edu_informe_versiones where informe_id in "
                       f"(select inf.id from edu_informes inf join edu_inscripciones ins on ins.id = inf.inscripcion_id "
                       f"join edu_evaluaciones ev on ev.id = ins.evaluacion_id where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_informes where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_inscripciones where evaluacion_id in "
                       f"(select id from edu_evaluaciones where nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_evaluaciones where nombre_grupo like '{PREFIJO}%'"))
        c.execute(text(f"delete from consentimientos_informados where persona_id in "
                       f"(select id from personas where nombres like '{PREFIJO}%')"))
        c.execute(text(f"delete from personas where nombres like '{PREFIJO}%'"))
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
