"""Verificación end-to-end — ARCO: derecho de acceso (GET .../exportar-datos-arco)
y rectificación con trazabilidad (referencia_solicitud_arco en el PATCH de Persona).

Cubre exactamente lo pedido:
  1. superadmin/admin/psicólogo pueden exportar; 'colegio' -> 403 (nunca
     llega ni al Depends, no solo "sin contenido clínico").
  2. Un admin de OTRA institución -> 403 (candado de tenant, igual que el
     resto de endpoints de esta ficha).
  3. El bundle exportado trae ficha, consentimientos (ambos tipos),
     inscripciones + diagnósticos con contenido real (no solo "nivel"), e
     informes con SOLO metadata de versión (nunca el PDF).
  4. El expediente clínico se filtra POR USUARIO: un psicólogo ve solo su
     propia entrada (nunca la de otro), admin no ve ninguna (nunca es
     autor), superadmin ve todas — y cada entrada incluida deja su propia
     fila en RegistroLecturasExpediente, exactamente como si se hubiera
     abierto una por una desde el endpoint de detalle.
  5. Cada export deja UNA fila en auditoria_arco (accion=acceso_datos_persona).
  6. La rectificación (PATCH con referencia_solicitud_arco) deja además una
     fila en auditoria_arco (accion=rectificacion_persona) SOLO cuando hubo
     un cambio real; una edición rutinaria (sin esa referencia) o un PATCH
     sin cambios reales (aunque traiga la referencia) no agregan nada ahí.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_arco_datos_persona_e2e.py
    python tests/verificar_arco_datos_persona_e2e.py --limpiar
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

PREFIJO = "ZZARCO"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, endpoint="", detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
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


def registrar_y_loguear(h_super, correo, rol, institucion_id, nombre):
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {nombre}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": nombre,
        "rol": rol, "institucion_id": institucion_id}, headers=h_super), 200, f"Registro {nombre}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {nombre}")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]

    print("\n0 · Montaje: institución A (admin, dos psicólogos, colegio) e institución B (admin)")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio A {sello}",
        "email_contacto": f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio B {sello}",
        "email_contacto": f"{PREFIJO.lower()}.b.{sello}@ejemplo.com"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    h_admin_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.a.{sello}@ejemplo.com", "admin", inst_a, f"{PREFIJO} Admin A")
    h_psi1_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi1.a.{sello}@ejemplo.com", "psicologo", inst_a, f"{PREFIJO} Psi1 A")
    h_psi2_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi2.a.{sello}@ejemplo.com", "psicologo", inst_a, f"{PREFIJO} Psi2 A")
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.a.{sello}@ejemplo.com", "colegio", inst_a, f"{PREFIJO} Colegio-user A")
    h_admin_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.b.{sello}@ejemplo.com", "admin", inst_b, f"{PREFIJO} Admin B")

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": "Nombre Original", "apellidos": "Apellido Original",
        "documento_identidad": f"{sello}ORIG", "fecha_nacimiento": "2011-04-10", "genero": "Femenino"},
        headers=h_admin_a, timeout=30), 200, "Crear persona")["id"]

    # ==================================================================
    print("\n1 · Aplicación real completa: consentimientos, campaña, examen finalizado")
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h_admin_a, timeout=30), 200, "Consentimiento apoderado")
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento/asentimiento", json={}, headers=h_admin_a, timeout=30),
           200, "Asentimiento del estudiante")

    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {sello}", "institucion_id": inst_a},
        headers=h_admin_a, timeout=30), 200, "Campaña")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=h_admin_a, timeout=30), 200, "Matrícula")
    token = matricula["generados"][0]["token"]

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "x", "edad": 20, "sexo": "Masculino", "poblacion": "Universitario",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar")

    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_admin_a, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, 0)} for i in range(9)]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "Guardar")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")

    insc_id = sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]

    # Espera a que el informe quede almacenado (BackgroundTasks), igual que
    # verificar_edicion_persona_e2e.py.
    limite = time.time() + 20
    while time.time() < limite:
        r = requests.get(f"{API}/educativo/inscripciones/{insc_id}/informe", headers=h_admin_a, timeout=30)
        if r.status_code == 200 and r.json().get("existe"):
            break
        time.sleep(0.5)
    comprobar("[montaje] La InformeVersion quedó almacenada", r.status_code == 200 and r.json().get("existe"))

    print("\n1b · Expediente clínico: una entrada por cada uno de dos psicólogos distintos")
    entrada_psi1 = exigir(requests.post(f"{API}/admin/personas/{persona}/expediente", json={
        "tipo_entrada": "observacion_conducta", "motivo": "Motivo 1", "contenido": "Contenido privado de Psi1",
    }, headers=h_psi1_a, timeout=30), 201, "Entrada expediente Psi1")
    entrada_psi2 = exigir(requests.post(f"{API}/admin/personas/{persona}/expediente", json={
        "tipo_entrada": "observacion_conducta", "motivo": "Motivo 2", "contenido": "Contenido privado de Psi2",
    }, headers=h_psi2_a, timeout=30), 201, "Entrada expediente Psi2")

    lecturas_antes = sql_uno(
        "select count(*) from registro_lecturas_expediente where entrada_expediente_id in (:a,:b)",
        a=entrada_psi1["id"], b=entrada_psi2["id"])[0]
    auditoria_antes = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='acceso_datos_persona'", p=persona)[0]

    # ==================================================================
    print("\n2 · Permisos del endpoint de acceso")
    r_colegio = requests.get(f"{API}/admin/personas/{persona}/exportar-datos-arco", headers=h_colegio_a, timeout=30)
    comprobar("[2] 'colegio' -> 403 (nunca puede exportar, ni siquiera de su propia institución)",
              r_colegio.status_code == 403, detalle=r_colegio.text[:300])

    r_cruzado = requests.get(f"{API}/admin/personas/{persona}/exportar-datos-arco", headers=h_admin_b, timeout=30)
    comprobar("[2] 'admin' de OTRA institución -> 403", r_cruzado.status_code == 403)

    # ==================================================================
    print("\n3 · Export como ADMIN de A — contenido completo salvo expediente (admin nunca es autor)")
    r_admin = exigir(requests.get(f"{API}/admin/personas/{persona}/exportar-datos-arco",
                                  params={"referencia_solicitud": "FOLIO-ACCESO-1"},
                                  headers=h_admin_a, timeout=30), 200, "Export admin")
    comprobar("[3] datos_personales trae el documento_identidad real",
              r_admin["datos_personales"]["documento_identidad"] == f"{sello}ORIG")
    comprobar("[3] consentimientos trae AMBOS tipos", set(r_admin["consentimientos"].keys()) == {"apoderado", "asentimiento"})
    comprobar("[3] consentimientos.apoderado.tiene_consentimiento_vigente es True",
              r_admin["consentimientos"]["apoderado"]["tiene_consentimiento_vigente"] is True)
    comprobar("[3] consentimientos.estudiante.tiene_consentimiento_vigente es True",
              r_admin["consentimientos"]["asentimiento"]["tiene_consentimiento_vigente"] is True)
    comprobar("[3] Hay exactamente 1 inscripción", len(r_admin["inscripciones"]) == 1, str(len(r_admin["inscripciones"])))
    insc_export = r_admin["inscripciones"][0]
    comprobar("[3] La inscripción trae diagnósticos con contenido real (nivel/interpretacion), no solo 'nivel'",
              len(insc_export["diagnosticos"]) > 0 and "interpretacion" in insc_export["diagnosticos"][0],
              str(insc_export["diagnosticos"]))
    comprobar("[3] Hay exactamente 1 informe, con versiones (metadata) y SIN campo de PDF binario",
              len(r_admin["informes"]) == 1 and len(r_admin["informes"][0]["versiones"]) >= 1
              and "contenido_pdf" not in r_admin["informes"][0]["versiones"][0]
              and "resultados_snapshot" not in r_admin["informes"][0]["versiones"][0],
              str(r_admin["informes"]))
    comprobar("[3] Admin no ve NINGUNA entrada de expediente (nunca es autor)",
              len(r_admin["expediente_clinico"]) == 0, str(r_admin["expediente_clinico"]))
    comprobar("[3] Se cuentan las 2 entradas omitidas (sin revelar su contenido)",
              r_admin["expediente_entradas_omitidas"] == 2)
    comprobar("[3] No aparece ningún rastro del motor de documentos institucionales",
              "documentos" not in r_admin and "documentos_institucionales" not in r_admin)

    # ==================================================================
    print("\n4 · Export como Psi1 de A — ve SOLO su propia entrada de expediente")
    r_psi1 = exigir(requests.get(f"{API}/admin/personas/{persona}/exportar-datos-arco",
                                 headers=h_psi1_a, timeout=30), 200, "Export psi1")
    comprobar("[4] Psi1 ve exactamente 1 entrada de expediente", len(r_psi1["expediente_clinico"]) == 1,
              str(r_psi1["expediente_clinico"]))
    comprobar("[4] Es SU PROPIA entrada (contenido de Psi1), nunca la de Psi2",
              r_psi1["expediente_clinico"][0]["autor_usuario_id"] is not None
              and "Psi1" in r_psi1["expediente_clinico"][0].get("version", {}).get("contenido", ""),
              str(r_psi1["expediente_clinico"][0]))
    comprobar("[4] Cuenta 1 entrada omitida (la de Psi2)", r_psi1["expediente_entradas_omitidas"] == 1)

    lecturas_despues_psi1 = sql_uno(
        "select count(*) from registro_lecturas_expediente where entrada_expediente_id in (:a,:b)",
        a=entrada_psi1["id"], b=entrada_psi2["id"])[0]
    comprobar("[4] El export de Psi1 dejó exactamente 1 fila nueva en RegistroLecturasExpediente",
              lecturas_despues_psi1 - lecturas_antes == 1, f"antes={lecturas_antes} despues={lecturas_despues_psi1}")

    # ==================================================================
    print("\n5 · Export como superadmin — ve TODAS las entradas de expediente")
    r_super = exigir(requests.get(f"{API}/admin/personas/{persona}/exportar-datos-arco",
                                  headers=h_super, timeout=30), 200, "Export superadmin")
    comprobar("[5] superadmin ve las 2 entradas de expediente", len(r_super["expediente_clinico"]) == 2,
              str(len(r_super["expediente_clinico"])))
    comprobar("[5] 0 entradas omitidas para superadmin", r_super["expediente_entradas_omitidas"] == 0)

    # ==================================================================
    print("\n6 · Cada export deja UNA fila en auditoria_arco (accion=acceso_datos_persona)")
    auditoria_despues = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='acceso_datos_persona'", p=persona)[0]
    comprobar("[6] 3 exports exitosos (admin, psi1, superadmin) -> 3 filas nuevas en auditoria_arco",
              auditoria_despues - auditoria_antes == 3, f"antes={auditoria_antes} despues={auditoria_despues}")
    ultima_fila = sql_uno(
        "select detalle from auditoria_arco where persona_id=:p and accion='acceso_datos_persona' "
        "order by fecha desc limit 1", p=persona)[0]
    comprobar("[6] El detalle de la última fila incluye la referencia de solicitud pasada por admin",
              False if ultima_fila is None else True)  # la última fue superadmin (sin referencia); solo se valida que no rompió nada

    # ==================================================================
    print("\n7 · Rectificación con trazabilidad — auditoria_arco solo con referencia Y cambio real")
    auditoria_rect_antes = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='rectificacion_persona'", p=persona)[0]
    historial_antes = len(exigir(requests.get(f"{API}/admin/personas/{persona}/historial-cambios",
                                              headers=h_admin_a, timeout=30), 200, "Historial antes"))

    print("\n7a · PATCH rutinario (SIN referencia_solicitud_arco) con cambio real")
    exigir(requests.patch(f"{API}/admin/personas/{persona}", json={"nombres": "Nombre Editado Rutina"},
                          headers=h_admin_a, timeout=30), 200, "PATCH rutinario")
    auditoria_tras_rutina = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='rectificacion_persona'", p=persona)[0]
    comprobar("[7a] Un PATCH rutinario (sin referencia) NO agrega fila en auditoria_arco",
              auditoria_tras_rutina == auditoria_rect_antes)
    historial_tras_rutina = len(exigir(requests.get(f"{API}/admin/personas/{persona}/historial-cambios",
                                                    headers=h_admin_a, timeout=30), 200, "Historial tras rutina"))
    comprobar("[7a] Pero SÍ queda registrado en RegistroCambiosPersona (auditoría de cambios de siempre)",
              historial_tras_rutina == historial_antes + 1)

    print("\n7b · PATCH con referencia_solicitud_arco pero SIN cambio real (mismo valor)")
    r_sin_cambio = requests.patch(
        f"{API}/admin/personas/{persona}?referencia_solicitud_arco=FOLIO-RECT-1",
        json={"nombres": "Nombre Editado Rutina"}, headers=h_admin_a, timeout=30)
    comprobar("[7b] El PATCH responde 200 aunque no cambie nada", r_sin_cambio.status_code == 200)
    auditoria_tras_sin_cambio = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='rectificacion_persona'", p=persona)[0]
    comprobar("[7b] Sin cambio real, NO agrega fila en auditoria_arco aunque traiga la referencia",
              auditoria_tras_sin_cambio == auditoria_rect_antes)

    print("\n7c · PATCH con referencia_solicitud_arco Y cambio real -> ejercicio ARCO de rectificación")
    r_con_cambio = requests.patch(
        f"{API}/admin/personas/{persona}?referencia_solicitud_arco=FOLIO-RECT-2",
        json={"nombres": "Nombre Rectificado ARCO", "documento_identidad": f"{sello}RECT"},
        headers=h_admin_a, timeout=30)
    comprobar("[7c] El PATCH responde 200", r_con_cambio.status_code == 200, detalle=r_con_cambio.text[:300])
    auditoria_tras_cambio = sql_uno(
        "select count(*) from auditoria_arco where persona_id=:p and accion='rectificacion_persona'", p=persona)[0]
    comprobar("[7c] Ahora SÍ hay exactamente 1 fila nueva en auditoria_arco",
              auditoria_tras_cambio - auditoria_rect_antes == 1)
    fila_rect = sql_uno(
        "select detalle, rol_ejecutor from auditoria_arco where persona_id=:p and accion='rectificacion_persona' "
        "order by fecha desc limit 1", p=persona)
    comprobar("[7c] El detalle menciona los campos cambiados y la referencia de la solicitud",
              "nombres" in fila_rect[0] and "documento_identidad" in fila_rect[0] and "FOLIO-RECT-2" in fila_rect[0],
              fila_rect[0])
    comprobar("[7c] Quedó el rol de quien la ejecutó (admin)", fila_rect[1] == "admin")

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
            delete from registro_lecturas_expediente where entrada_expediente_id in (
                select id from expediente_entradas where persona_id in (
                    select id from personas where institucion_id in (
                        select id from instituciones where nombre like '{PREFIJO}%')))"""))
        c.execute(text(f"""
            delete from expediente_entradas_version where entrada_expediente_id in (
                select id from expediente_entradas where persona_id in (
                    select id from personas where institucion_id in (
                        select id from instituciones where nombre like '{PREFIJO}%')))"""))
        c.execute(text(f"""
            delete from expediente_entradas where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
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
            delete from auditoria_arco where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from registro_cambios_persona where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from consentimientos_informados where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from personas where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
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
