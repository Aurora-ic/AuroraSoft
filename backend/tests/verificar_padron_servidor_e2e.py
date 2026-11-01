"""E2E — filtros del padrón en el SERVIDOR, `/ids` y `/resumen-padron`
(sesión 2026-11-01, escalabilidad de Padrón / Nueva campaña / Agenda).

La equivalencia fina contra la lógica que antes corría en el navegador vive
en `tests/verificar_padron_servidor_equivalencia.py` (sin servidor, sobre
los datos reales + escenarios en una transacción revertida). Esto prueba lo
que solo se ve por HTTP, contra uvicorn real en :8010:

  1  Listado sin filtros = respuesta de siempre (solo activos, misma forma)
  2  Filtros nuevos: estado, seccion_id, grado_id, sin_matricula,
     datos_incompletos, consentimiento_apoderado, búsqueda — combinables
  3  422 con valores inválidos de estado / consentimiento_apoderado
  4  /ids devuelve exactamente los ids del listado filtrado
  5  /resumen-padron: KPIs y secciones, con y sin incluir_ids
  6  Candados: otro colegio -> 403 en los tres; 'colegio' de la misma
     institución sí lee (igual que el listado de siempre); sin token -> 401

    uvicorn main:app --port 8010   (SMTP apagado, captcha no obligatorio)
    python -m tests.verificar_padron_servidor_e2e
    python -m tests.verificar_padron_servidor_e2e --limpiar
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

PREFIJO = "ZZPADRON"
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
        r = metodo(url, timeout=30, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


def registrar_y_loguear(h_super, correo, nombre, rol, institucion_id):
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {correo}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": nombre,
        "rol": rol, "institucion_id": institucion_id}, headers=h_super), 200, f"Registro {correo}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {correo}")["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def main(url_base):
    global API
    API = url_base.rstrip("/") + "/api"
    motor = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.now(timezone.utc).strftime("%H%M%S")

    print("\n0 · Montaje")
    # Superadmin PROPIO del test (se borra en --limpiar), mismo criterio que
    # verificar_documentos_descarte_e2e.py.
    from core.security import get_password_hash
    correo_super = f"{PREFIJO.lower()}.super.{sello}@ejemplo.com"
    with motor.begin() as c:
        c.execute(text(
            "INSERT INTO auth_usuarios (email, hashed_password, nombre_completo, rol, activo, token_version) "
            "VALUES (:e, :h, :n, 'superadmin', true, 0)"
        ), {"e": correo_super, "h": get_password_hash("ClaveDePrueba123"), "n": f"{PREFIJO} Super"})
    h_super = {"Authorization": f"Bearer {exigir(login(correo_super, 'ClaveDePrueba123'), 200, 'login superadmin')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", f"{PREFIJO} Psi", "psicologo", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)
    h_colegio = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com", f"{PREFIJO} Colegio", "colegio", inst_a)

    base = f"{API}/admin/personas"
    nivel = exigir(requests.post(f"{base}/academico/niveles", json={"institucion_id": inst_a, "nombre": "Secundaria"}, headers=h_super, timeout=30), 200, "nivel")["id"]
    grado = exigir(requests.post(f"{base}/academico/grados", json={"nivel_educativo_id": nivel, "nombre": "3°"}, headers=h_super, timeout=30), 200, "grado")["id"]
    sec_a = exigir(requests.post(f"{base}/academico/secciones", json={"grado_id": grado, "nombre": "A", "anio_escolar": 2026}, headers=h_super, timeout=30), 200, "sección A")["id"]
    sec_b = exigir(requests.post(f"{base}/academico/secciones", json={"grado_id": grado, "nombre": "B", "anio_escolar": 2026}, headers=h_super, timeout=30), 200, "sección B")["id"]

    def persona(nombres, apellidos, **extra):
        return exigir(requests.post(f"{base}/", json={
            "institucion_id": inst_a, "nombres": nombres, "apellidos": apellidos, "tipo_perfil": "estudiante", **extra,
        }, headers=h_psi, timeout=30), 200, f"persona {nombres}")["id"]

    completos = {"genero": "F", "fecha_nacimiento": "2012-04-01T00:00:00Z"}
    ana = persona("Ana", f"{PREFIJO} Alva", **completos)          # sección A, con Dx, consentimiento
    beto = persona("Beto", f"{PREFIJO} Bravo", **completos)       # sección B
    caro = persona("Carolina", f"{PREFIJO} Cruz")                  # sin matrícula, datos incompletos
    dani = persona("Daniel", f"{PREFIJO} Diaz", **completos)      # inactivo, sección A
    for pid, sec in ((ana, sec_a), (beto, sec_b), (dani, sec_a)):
        exigir(requests.post(f"{base}/{pid}/matricula", json={"seccion_id": sec}, headers=h_psi, timeout=30), 200, "matrícula")
    exigir(requests.patch(f"{base}/{ana}/antecedentes-clinicos", json={"recibe_terapia_psicologica_externa": True}, headers=h_psi, timeout=30), 200, "antecedentes Ana")
    exigir(requests.post(f"{base}/{ana}/consentimiento", json={
        "persona_id": ana, "institucion_id": inst_a, "otorgado_por_nombre": "Madre de Ana", "tipo_otorgante": "apoderado",
    }, headers=h_psi, timeout=30), 200, "consentimiento Ana")
    exigir(requests.patch(f"{base}/{dani}", json={"activo": False}, headers=h_super, timeout=30), 200, "desactivar Daniel")
    todos = {ana, beto, caro, dani}

    def listado(params, h=h_psi, inst=inst_a):
        r = requests.get(f"{base}/{inst}", params={"limit": 200, **params}, headers=h, timeout=30)
        return r, (r.json() if r.status_code == 200 else {})

    def ids_listado(params):
        _, cuerpo = listado(params)
        return {p["id"] for p in cuerpo.get("items", [])} & todos

    def ids_endpoint(params, h=h_psi, inst=inst_a):
        r = requests.get(f"{base}/{inst}/ids", params=params, headers=h, timeout=30)
        return r, (set(r.json()["ids"]) if r.status_code == 200 else set())

    print("\n1 · Sin filtros nuevos: la respuesta de siempre")
    r, cuerpo = listado({})
    comprobar("200 y forma {total, items}", r.status_code == 200 and set(cuerpo) == {"total", "items"})
    comprobar("Solo activos por defecto (Daniel inactivo no aparece)", ids_listado({}) == {ana, beto, caro})
    comprobar("incluir_inactivas=true sigue trayendo a Daniel", ids_listado({"incluir_inactivas": "true"}) == todos)
    fila_ana = next(p for p in cuerpo["items"] if p["id"] == ana)
    comprobar("Cada fila sigue trayendo seccion_actual y con_diagnostico",
              fila_ana["seccion_actual"]["seccion_id"] == sec_a and fila_ana["con_diagnostico"] is True)

    print("\n2 · Filtros en el servidor")
    casos = [
        ({"estado": "activos"}, {ana, beto, caro}),
        ({"estado": "inactivos"}, {dani}),
        ({"estado": "todos"}, todos),
        ({"estado": "con_dx"}, {ana}),
        ({"seccion_id": sec_a}, {ana}),
        ({"seccion_id": sec_a, "estado": "todos"}, {ana, dani}),
        ({"grado_id": grado}, {ana, beto}),
        ({"sin_matricula": "true"}, {caro}),
        ({"datos_incompletos": "true"}, {caro}),
        ({"consentimiento_apoderado": "vigente"}, {ana}),
        ({"consentimiento_apoderado": "sin"}, {beto, caro}),
        ({"busqueda": f"Beto {PREFIJO} Bravo"}, {beto}),
        ({"busqueda": f"{PREFIJO} Cruz Carolina"}, {caro}),
        ({"grado_id": grado, "consentimiento_apoderado": "sin"}, {beto}),
    ]
    for params, esperado in casos:
        comprobar(f"Listado {params} -> {sorted(esperado)}", ids_listado(params) == esperado, str(ids_listado(params)))
    _, cuerpo = listado({"estado": "todos", "busqueda": PREFIJO})
    comprobar("total = cantidad filtrada (no el tamaño de página)", cuerpo["total"] == 4, str(cuerpo.get("total")))
    _, pag = listado({"estado": "todos", "busqueda": PREFIJO, "limit": 2})
    _, pag2 = listado({"estado": "todos", "busqueda": PREFIJO, "limit": 2, "skip": 2})
    ids_pag = [p["id"] for p in pag["items"] + pag2["items"]]
    comprobar("Dos páginas de 2 cubren los 4 sin repetir, ordenadas por apellido",
              ids_pag == [ana, beto, caro, dani], str(ids_pag))

    print("\n3 · Validación")
    comprobar("estado inválido -> 422", listado({"estado": "riesgo"})[0].status_code == 422)
    comprobar("consentimiento_apoderado inválido -> 422", listado({"consentimiento_apoderado": "talvez"})[0].status_code == 422)

    print("\n4 · /ids = ids del listado")
    for params, esperado in casos:
        r, ids = ids_endpoint(params)
        if not comprobar(f"/ids {params}", r.status_code == 200 and ids & todos == esperado, f"{r.status_code} {ids}"):
            break
    r, _ = ids_endpoint({})
    comprobar("/ids trae {total, ids} con total = len(ids)", set(r.json()) == {"total", "ids"} and r.json()["total"] == len(r.json()["ids"]))

    print("\n5 · /resumen-padron")
    r = requests.get(f"{base}/{inst_a}/resumen-padron", headers=h_psi, timeout=30)
    res = r.json() if r.status_code == 200 else {}
    comprobar("KPIs: 3 activos, 1 inactivo, 1 incompleto, 1 sin matrícula, 1 con Dx",
              r.status_code == 200 and (res["activos"], res["inactivos"], res["datos_incompletos"], res["sin_matricula"], res["con_diagnostico"]) == (3, 1, 1, 1, 1),
              str({k: res.get(k) for k in ("activos", "inactivos", "datos_incompletos", "sin_matricula", "con_diagnostico")}))
    secciones = {s["seccion_id"]: s for s in res.get("secciones", [])}
    comprobar("Secciones A y B, cantidad = solo activos (A=1 aunque Daniel esté matriculado)",
              set(secciones) == {sec_a, sec_b} and secciones[sec_a]["cantidad"] == 1 and secciones[sec_b]["cantidad"] == 1)
    comprobar("Sin incluir_ids no viajan ids", all(s.get("persona_ids") is None for s in secciones.values()) and res.get("ids_sin_matricula") is None)
    r = requests.get(f"{base}/{inst_a}/resumen-padron", params={"incluir_ids": "true"}, headers=h_psi, timeout=30)
    res_i = r.json()
    sec_i = {s["seccion_id"]: s for s in res_i["secciones"]}
    comprobar("incluir_ids: ids activos por sección y sin matrícula",
              sec_i[sec_a]["persona_ids"] == [ana] and sec_i[sec_b]["persona_ids"] == [beto] and res_i["ids_sin_matricula"] == [caro])

    print("\n6 · Candados")
    for ruta in ("", "/ids", "/resumen-padron"):
        r = requests.get(f"{base}/{inst_a}{ruta}", headers=h_psi_b, timeout=30)
        comprobar(f"Psicólogo de OTRO colegio -> 403 en /{{inst}}{ruta}", r.status_code == 403, str(r.status_code))
        r = requests.get(f"{base}/{inst_a}{ruta}", headers=h_colegio, timeout=30)
        comprobar(f"'colegio' de la misma institución lee /{{inst}}{ruta} (como el listado de siempre)", r.status_code == 200, str(r.status_code))
        r = requests.get(f"{base}/{inst_a}{ruta}", timeout=30)
        comprobar(f"Sin token -> 401 en /{{inst}}{ruta}", r.status_code == 401, str(r.status_code))

    total = len(_resultados)
    ok = sum(_resultados)
    print(f"\nRESULTADO: {ok}/{total} comprobaciones superadas")
    return 0 if ok == total else 1


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas_antecedentes_clinicos WHERE persona_id IN ({personas})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM registro_cambios_persona WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE institucion_id IN ({insts})",
            f"DELETE FROM grados WHERE institucion_id IN ({insts})",
            f"DELETE FROM niveles_educativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM auth_tokens_recuperacion WHERE usuario_id IN (SELECT id FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%')",
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
