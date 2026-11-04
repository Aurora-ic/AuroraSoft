"""E2E — bandeja "Casos en riesgo" con urgencia, estado y responsable
(`GET/PATCH /educativo/casos-riesgo`, sesión 2026-11-01).

Decisiones del usuario: urgencia automática en 3 niveles (ítem crítico →
urgente, baremo → alerta, antecedentes → seguimiento); estados nuevo →
en_atencion → derivado → en_seguimiento → cerrado; un caso solo sale de la
bandeja al cerrarlo (con motivo); responsable = creador de la campaña,
reasignable. Contra uvicorn real en :8010, con PHQ-9 real:

  1  Urgencias y orden: PHQ-9 ítem 9 positivo = urgente; total "Severo" con
     ítem 9 en cero = alerta; antecedentes "Sí" = seguimiento; sin alerta =
     no aparece. Responsables y lista de profesionales.
  2  Idempotencia: consultar dos veces no duplica casos
  3  Una sesión de seguimiento pasa 'nuevo' → 'en_atencion' sin sacarlo
  4  Cambiar estado y responsable; responsables inválidos → 422
  5  Cerrar exige motivo; cerrado sale de la bandeja y no se recrea
  6  Antecedentes: cerrado no se reabre solo; editados después, nuevo caso;
     reabrir el viejo con otro abierto → 409
  7  Reabrir un caso cerrado limpia el cierre
  8  Candados: colegio 403, otro colegio 404/vacío, superadmin exige institución
  9  Historial con usuario / sistema
 10  GET /casos-pendientes de siempre sigue respondiendo

    uvicorn main:app --port 8010   (SMTP apagado, captcha no obligatorio)
    python -m tests.verificar_casos_riesgo_e2e
    python -m tests.verificar_casos_riesgo_e2e --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZCASOS"
API = "http://127.0.0.1:8010/api"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    return r.json() if r.text else None


def pedir(metodo, url, contexto="", **kw):
    for _ in range(8):
        r = metodo(url, timeout=60, **kw)
        if r.status_code != 429:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


def main(url_base):
    global API
    API = url_base.rstrip("/") + "/api"
    motor = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.now(timezone.utc).strftime("%H%M%S")

    print("\n0 · Montaje")
    from core.security import get_password_hash
    correo_super = f"{PREFIJO.lower()}.super.{sello}@ejemplo.com"
    with motor.begin() as c:
        c.execute(text(
            "INSERT INTO auth_usuarios (email, hashed_password, nombre_completo, rol, activo, token_version) "
            "VALUES (:e, :h, :n, 'superadmin', true, 0)"
        ), {"e": correo_super, "h": get_password_hash("ClaveDePrueba123"), "n": f"{PREFIJO} Super"})
        phq9 = c.execute(text(
            "select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")).scalar()
    if not phq9:
        print("!! Falta el catálogo PHQ-9 (python -m seeds.seed_phq9).")
        return 1
    h_super = {"Authorization": f"Bearer {exigir(login(correo_super, 'ClaveDePrueba123'), 200, 'login super')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    def usuario(etiqueta, rol, inst):
        correo = f"{PREFIJO.lower()}.{etiqueta}.{sello}@ejemplo.com"
        exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {etiqueta}", json={
            "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} {etiqueta}",
            "rol": rol, "institucion_id": inst}, headers=h_super), 200, f"Registro {etiqueta}")
        tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {etiqueta}")["access_token"]
        with motor.connect() as c:
            uid = c.execute(text("select id from auth_usuarios where email=:e"), {"e": correo}).scalar()
        return uid, {"Authorization": f"Bearer {tok}"}

    p1_id, h_p1 = usuario("psi1", "psicologo", inst_a)
    p2_id, h_p2 = usuario("psi2", "psicologo", inst_a)
    col_id, h_col = usuario("colegio", "colegio", inst_a)
    pb_id, h_pb = usuario("psib", "psicologo", inst_b)

    def persona(etiqueta):
        pid = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_a, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
            "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=h_p1, timeout=30), 200, f"persona {etiqueta}")["id"]
        exigir(requests.post(f"{API}/admin/personas/{pid}/consentimiento", json={
            "persona_id": pid, "institucion_id": inst_a, "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
            headers=h_p1, timeout=30), 200, f"consentimiento {etiqueta}")
        return pid

    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9, "nombre_grupo": f"{PREFIJO} PHQ9 {sello}", "institucion_id": inst_a},
        headers=h_p1, timeout=30), 200, "campaña")

    def rendir(persona_id, maximo_items_1_8, item9_positivo):
        m = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                 json=[persona_id], headers=h_p1, timeout=30), 200, "matrícula")
        token = m["generados"][0]["token"]
        exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
            "nombre_completo": "Alumno", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
            "acepta_terminos": True}, timeout=30), 200, "comenzar")
        preguntas = exigir(requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30), 200, "preguntas")
        respuestas = []
        for p in preguntas:
            texto = p["texto_pregunta"].lower()
            if "mejor muerto" in texto:
                idx = 1 if item9_positivo else 0
            elif "si usted marcó" in texto:
                idx = 0
            else:
                idx = -1 if maximo_items_1_8 else 0
            respuestas.append({"pregunta_id": p["id"], "opcion_id": p["opciones"][idx]["id"]})
        exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar")
        exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "finalizar")
        with motor.connect() as c:
            return c.execute(text("select id from edu_inscripciones where token=:t"), {"t": token}).scalar()

    ana, beto, caro, dani = persona("Ana"), persona("Beto"), persona("Caro"), persona("Dani")
    insc_ana = rendir(ana, maximo_items_1_8=False, item9_positivo=True)    # urgente (regla ítem 9)
    insc_beto = rendir(beto, maximo_items_1_8=True, item9_positivo=False)  # alerta (baremo "Severo")
    rendir(dani, maximo_items_1_8=False, item9_positivo=False)             # sin alerta
    exigir(requests.patch(f"{API}/admin/personas/{caro}/antecedentes-clinicos",
                          json={"recibe_terapia_psicologica_externa": True}, headers=h_p1, timeout=30), 200, "antecedentes Caro")

    url = f"{API}/educativo/casos-riesgo"

    def bandeja(h=h_p1, **params):
        return exigir(requests.get(url, params=params, headers=h, timeout=60), 200, "bandeja")

    def por_persona(casos):
        return {c["persona_id"]: c for c in casos}

    # ------------------------------------------------------------------
    print("\n1 · Urgencias, orden y responsables")
    b = bandeja()
    casos = por_persona(b["casos"])
    comprobar("Aparecen exactamente Ana, Beto y Caro (Dani sin alerta no)", set(casos) == {ana, beto, caro}, str(list(casos)))
    comprobar("Ana (ítem 9 positivo) -> urgente", casos.get(ana, {}).get("urgencia") == "urgente", str(casos.get(ana))[:300])
    comprobar("Beto (baremo Severo, ítem 9 en cero) -> alerta", casos.get(beto, {}).get("urgencia") == "alerta", str(casos.get(beto))[:300])
    comprobar("Caro (antecedentes) -> seguimiento", casos.get(caro, {}).get("urgencia") == "seguimiento")
    comprobar("Orden: urgente, alerta, seguimiento", [c["urgencia"] for c in b["casos"]] == ["urgente", "alerta", "seguimiento"],
              str([c["urgencia"] for c in b["casos"]]))
    comprobar("Todos empiezan en 'nuevo'", all(c["estado"] == "nuevo" for c in b["casos"]))
    comprobar("La alerta de Ana viene marcada como ítem crítico con su motivo",
              any(a["item_critico"] and a["motivo"] for a in casos[ana]["alertas"]), str(casos[ana]["alertas"])[:300])
    comprobar("Responsable de los casos de prueba = creador de la campaña (psi1)",
              casos[ana]["responsable"]["id"] == p1_id and casos[beto]["responsable"]["id"] == p1_id)
    comprobar("Caso por antecedentes sin responsable", casos[caro]["responsable"] is None)
    ids_prof = {p["id"] for p in b["profesionales"]}
    comprobar("Profesionales: psi1 y psi2, nunca el rol colegio", {p1_id, p2_id} <= ids_prof and col_id not in ids_prof, str(ids_prof))

    # ------------------------------------------------------------------
    print("\n2 · Idempotencia")
    bandeja()
    with motor.connect() as c:
        n = c.execute(text("select count(*) from edu_casos_riesgo where institucion_id=:i"), {"i": inst_a}).scalar()
    comprobar("Consultar de nuevo no duplica (3 filas)", n == 3, str(n))

    # ------------------------------------------------------------------
    print("\n3 · Sesión de seguimiento")
    exigir(requests.post(f"{API}/educativo/seguimiento/", json={"persona_id": beto, "observaciones": "Entrevista"},
                         headers=h_p1, timeout=30), 200, "sesión Beto")
    beto_caso = por_persona(bandeja()["casos"]).get(beto)
    comprobar("Beto pasa a 'en_atencion' y sigue en la bandeja", beto_caso is not None and beto_caso["estado"] == "en_atencion",
              str(beto_caso)[:200])

    # ------------------------------------------------------------------
    print("\n3b · Avisos de casos urgentes (campana de la app, sesión 2026-11-02)")
    def avisos(h):
        return requests.get(f"{url}/avisos", headers=h, timeout=60)
    av = avisos(h_p1)
    ids_av = [c["persona_id"] for c in av.json().get("casos", [])] if av.status_code == 200 else []
    comprobar("psi1 (responsable) recibe el aviso de Ana (urgente, nueva)", av.status_code == 200 and ana in ids_av, av.text[:200])
    comprobar("…y no el de Beto (alerta de baremo, no urgente)", beto not in ids_av, str(ids_av))
    comprobar("El aviso de Ana viene marcado como asignado a mí",
              any(c["persona_id"] == ana and c["asignado_a_mi"] for c in av.json().get("casos", [])), av.text[:200])
    av2 = avisos(h_p2)
    comprobar("psi2 no recibe el de Ana (es de otro responsable)",
              av2.status_code == 200 and ana not in [c["persona_id"] for c in av2.json()["casos"]], av2.text[:200])
    comprobar("colegio -> 403", avisos(h_col).status_code == 403)
    av_b = avisos(h_pb)
    comprobar("Otro colegio no ve los avisos de A", av_b.status_code == 200 and av_b.json()["total"] == 0, av_b.text[:200])

    print("\n4 · Estado y responsable")
    id_ana, id_beto, id_caro = casos[ana]["id"], casos[beto]["id"], casos[caro]["id"]
    r = requests.patch(f"{url}/{id_ana}", json={"estado": "derivado", "nota": "Derivada a psiquiatría"}, headers=h_p1, timeout=30)
    comprobar("Ana -> derivado (200)", r.status_code == 200 and r.json()["estado"] == "derivado", r.text[:200])
    comprobar("Atender el caso (sale de 'nuevo') apaga su aviso", ana not in [c["persona_id"] for c in avisos(h_p1).json()["casos"]])
    r = requests.patch(f"{url}/{id_ana}", json={"responsable_usuario_id": p2_id}, headers=h_p1, timeout=30)
    comprobar("Reasignar a psi2 (200)", r.status_code == 200 and r.json()["responsable"]["id"] == p2_id, r.text[:200])
    r = requests.patch(f"{url}/{id_ana}", json={"responsable_usuario_id": col_id}, headers=h_p1, timeout=30)
    comprobar("Responsable con rol colegio -> 422", r.status_code == 422, str(r.status_code))
    r = requests.patch(f"{url}/{id_ana}", json={"responsable_usuario_id": pb_id}, headers=h_p1, timeout=30)
    comprobar("Responsable de otro colegio -> 422", r.status_code == 422, str(r.status_code))
    r = requests.patch(f"{url}/{id_ana}", json={"estado": "inventado"}, headers=h_p1, timeout=30)
    comprobar("Estado inexistente -> 422", r.status_code == 422, str(r.status_code))
    r = requests.patch(f"{url}/{id_caro}", json={"responsable_usuario_id": p1_id}, headers=h_p2, timeout=30)
    comprobar("Asignar el caso de antecedentes a psi1 (200)", r.status_code == 200 and r.json()["responsable"]["id"] == p1_id)

    # ------------------------------------------------------------------
    print("\n5 · Cerrar")
    r = requests.patch(f"{url}/{id_beto}", json={"estado": "cerrado"}, headers=h_p1, timeout=30)
    comprobar("Cerrar sin motivo -> 422", r.status_code == 422, str(r.status_code))
    r = requests.patch(f"{url}/{id_beto}", json={"estado": "cerrado", "motivo_cierre": "Síntomas remitidos"}, headers=h_p1, timeout=30)
    comprobar("Cerrar con motivo (200)", r.status_code == 200 and r.json()["estado"] == "cerrado"
              and r.json()["motivo_cierre"] == "Síntomas remitidos" and r.json()["cerrado_en"], r.text[:200])
    comprobar("Cerrado sale de la bandeja", beto not in por_persona(bandeja()["casos"]))
    con_cerrados = por_persona(bandeja(incluir_cerrados="true")["casos"])
    comprobar("…y aparece con incluir_cerrados", con_cerrados.get(beto, {}).get("estado") == "cerrado")
    with motor.connect() as c:
        n = c.execute(text("select count(*) from edu_casos_riesgo where inscripcion_id=:i"), {"i": insc_beto}).scalar()
    comprobar("No se recrea otro caso para esa evaluación", n == 1, str(n))

    # ------------------------------------------------------------------
    print("\n6 · Antecedentes")
    exigir(requests.patch(f"{url}/{id_caro}", json={"estado": "cerrado", "motivo_cierre": "Alta en terapia externa"},
                          headers=h_p1, timeout=30), 200, "cerrar Caro")
    comprobar("Cerrado por antecedentes: no se reabre solo", caro not in por_persona(bandeja()["casos"]))
    time.sleep(1.1)
    exigir(requests.patch(f"{API}/admin/personas/{caro}/antecedentes-clinicos",
                          json={"detalle_terapia_psicologica_externa": "Retomó terapia"}, headers=h_p1, timeout=30), 200, "editar antecedentes")
    nuevo_caro = por_persona(bandeja()["casos"]).get(caro)
    comprobar("Antecedentes editados después del cierre -> caso nuevo", nuevo_caro is not None and nuevo_caro["id"] != id_caro
              and nuevo_caro["estado"] == "nuevo", str(nuevo_caro)[:200])
    r = requests.patch(f"{url}/{id_caro}", json={"estado": "en_atencion"}, headers=h_p1, timeout=30)
    comprobar("Reabrir el viejo con otro abierto -> 409", r.status_code == 409, f"{r.status_code} {r.text[:200]}")

    # ------------------------------------------------------------------
    print("\n7 · Reabrir")
    r = requests.patch(f"{url}/{id_beto}", json={"estado": "en_seguimiento"}, headers=h_p1, timeout=30)
    cuerpo = r.json() if r.status_code == 200 else {}
    comprobar("Reabrir Beto (200) limpia el cierre", r.status_code == 200 and cuerpo.get("estado") == "en_seguimiento"
              and cuerpo.get("motivo_cierre") is None and cuerpo.get("cerrado_en") is None, r.text[:200])
    comprobar("…y vuelve a la bandeja", beto in por_persona(bandeja()["casos"]))

    # ------------------------------------------------------------------
    print("\n8 · Candados")
    comprobar("colegio GET -> 403", requests.get(url, headers=h_col, timeout=30).status_code == 403)
    comprobar("colegio PATCH -> 403", requests.patch(f"{url}/{id_ana}", json={"estado": "nuevo"}, headers=h_col, timeout=30).status_code == 403)
    comprobar("colegio historial -> 403", requests.get(f"{url}/{id_ana}/historial", headers=h_col, timeout=30).status_code == 403)
    comprobar("Otro colegio PATCH -> 404", requests.patch(f"{url}/{id_ana}", json={"estado": "nuevo"}, headers=h_pb, timeout=30).status_code == 404)
    comprobar("Otro colegio historial -> 404", requests.get(f"{url}/{id_ana}/historial", headers=h_pb, timeout=30).status_code == 404)
    comprobar("Otro colegio ve SU bandeja (vacía)", bandeja(h=h_pb)["casos"] == [])
    comprobar("Otro colegio no puede pedir la de A (se ignora institucion_id)", bandeja(h=h_pb, institucion_id=inst_a)["casos"] == [])
    comprobar("Superadmin sin institucion_id -> 400", requests.get(url, headers=h_super, timeout=30).status_code == 400)
    comprobar("Superadmin con institucion_id -> ve los mismos casos que psi1",
              {c["id"] for c in bandeja(h=h_super, institucion_id=inst_a)["casos"]} == {c["id"] for c in bandeja()["casos"]})
    comprobar("Sin sesión -> 401", requests.get(url, timeout=30).status_code == 401)

    # ------------------------------------------------------------------
    print("\n9 · Historial")
    hist = exigir(requests.get(f"{url}/{id_ana}/historial", headers=h_p1, timeout=30), 200, "historial Ana")
    tipos = [e["tipo"] for e in hist]
    comprobar("Ana: creado (sistema), estado y responsable, en orden", tipos[:3] == ["creado", "estado", "responsable"], str(tipos))
    comprobar("El alta automática no tiene usuario; los cambios sí", hist[0]["usuario"] is None and hist[1]["usuario"] and hist[2]["usuario"])
    comprobar("El cambio de responsable muestra nombres", hist[2]["responsable_anterior"] and hist[2]["responsable_nuevo"])
    comprobar("La nota de la derivación quedó registrada", hist[1]["nota"] == "Derivada a psiquiatría")
    hist_beto = exigir(requests.get(f"{url}/{id_beto}/historial", headers=h_p1, timeout=30), 200, "historial Beto")
    comprobar("Beto: el paso por sesión lo registró el sistema",
              any(e["estado_nuevo"] == "en_atencion" and e["usuario"] is None for e in hist_beto))

    # ------------------------------------------------------------------
    print("\n10 · Compatibilidad")
    r = requests.get(f"{API}/educativo/casos-pendientes", headers=h_p1, timeout=30)
    comprobar("GET /casos-pendientes sigue respondiendo (200, lista)", r.status_code == 200 and isinstance(r.json(), list))

    total, pasan = len(_resultados), sum(_resultados)
    print(f"\n{pasan}/{total} comprobaciones pasan.")
    return 0 if pasan == total else 1


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    evals = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evals})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    usuarios = f"SELECT id FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%'"
    with motor.begin() as c:
        c.execute(text(f"DELETE FROM edu_casos_riesgo WHERE institucion_id IN ({insts})"))
        hijos = c.execute(text("""
            select tc.table_name, kcu.column_name from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu on kcu.constraint_name = tc.constraint_name
            join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name
            where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'edu_inscripciones'
              and tc.table_name <> 'edu_inscripciones'""")).all()
        c.execute(text(f"DELETE FROM edu_informe_versiones WHERE informe_id IN (SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscs}))"))
        for tabla, col in hijos:
            c.execute(text(f"DELETE FROM {tabla} WHERE {col} IN ({inscs})"))
        for q in [
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({evals})",
            f"DELETE FROM edu_evaluaciones WHERE institucion_id IN ({insts})",
            f"DELETE FROM edu_sesiones_seguimiento WHERE institucion_id IN ({insts})",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas_antecedentes_clinicos WHERE persona_id IN ({personas})",
            f"DELETE FROM registro_cambios_persona WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN ({usuarios})",
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
