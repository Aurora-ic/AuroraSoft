"""E2E — datos del examen sin "Sexo" ni "Universitario", con el colegio a la
vista (sesión 2026-11-02, decisiones del usuario).

Contra uvicorn real en :8010 (captcha no obligatorio), con PHQ-9 real:

  1  GET /examen/{token}/intake ya no devuelve el sexo (el alumno no lo ve)
     aunque la inscripción lo tenga del padrón, y sí trae el nombre y el logo
     del colegio
  2  comenzar-test funciona SIN mandar sexo; el sexo del padrón se conserva
  3  Nivel: "Universitario" → 422; "Inicial" es válido
  4  Un alumno matriculado en el nivel "Inicial" queda con población
     "Inicial" derivada al matricularlo (antes quedaba vacía)
  5  En un enlace sin sexo del padrón, el sexo queda vacío y el examen se
     corrige igual (los baremos cargados son unisex)

    uvicorn main:app --port 8010   (LOGIN_CAPTCHA_OBLIGATORIO=false)
    python -m tests.verificar_examen_intake_e2e
    python -m tests.verificar_examen_intake_e2e --limpiar
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

PREFIJO = "ZZINTAKE"
API = "http://127.0.0.1:8010/api"
LOGO = "https://ejemplo.com/logo-zzintake.png"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    return r.json() if r.text else None


def login(email, clave):
    for _ in range(8):
        r = requests.post(f"{API}/auth/login", data={"username": email, "password": clave}, timeout=60)
        if r.status_code != 429:
            return r
        print("    (429 en login; esperando 13s)")
        time.sleep(13)
    return r


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
        phq9 = c.execute(text("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")).scalar()
    if not phq9:
        print("!! Falta el catálogo PHQ-9 (python -m seeds.seed_phq9).")
        return 1
    h = {"Authorization": f"Bearer {exigir(login(correo_super, 'ClaveDePrueba123'), 200, 'login')['access_token']}"}

    nombre_inst = f"{PREFIJO} Colegio {sello}"
    inst = exigir(requests.post(f"{API}/instituciones/", json={"nombre": nombre_inst}, headers=h, timeout=30), 201, "institución")["id"]
    # El logo se guarda directo: PATCH lo valida contra SSRF descargándolo, y
    # aquí solo importa que /intake lo devuelva tal cual.
    with motor.begin() as c:
        c.execute(text("update instituciones set logo_url = :u where id = :i"), {"u": LOGO, "i": inst})

    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={"institucion_id": inst, "nombre": "Inicial"}, headers=h, timeout=30), 200, "nivel Inicial")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={"nivel_educativo_id": nivel["id"], "nombre": "5 años"}, headers=h, timeout=30), 200, "grado")
    seccion = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={"grado_id": grado["id"], "nombre": "A", "anio_escolar": datetime.now().year}, headers=h, timeout=30), 200, "sección")

    def persona(etiqueta, genero):
        datos = {"institucion_id": inst, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno", "documento_identidad": f"{sello}{etiqueta}"}
        if genero:
            datos["genero"] = genero
        pid = exigir(requests.post(f"{API}/admin/personas/", json=datos, headers=h, timeout=30), 200, f"persona {etiqueta}")["id"]
        exigir(requests.post(f"{API}/admin/personas/{pid}/consentimiento", json={
            "persona_id": pid, "institucion_id": inst, "otorgado_por_nombre": "Apoderado", "tipo_otorgante": "apoderado"},
            headers=h, timeout=30), 200, f"consentimiento {etiqueta}")
        return pid

    con_sexo = persona("ConSexo", "Femenino")
    sin_sexo = persona("SinSexo", None)
    exigir(requests.post(f"{API}/admin/personas/{con_sexo}/matricula", json={"seccion_id": seccion["id"]}, headers=h, timeout=30), 200, "matrícula académica")
    camp = exigir(requests.post(f"{API}/educativo/campanas/", json={"prueba_id": phq9, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst}, headers=h, timeout=30), 200, "campaña")

    def matricular(pid):
        return exigir(requests.post(f"{API}/educativo/campanas/{camp['id']}/matricular-roster", json=[pid], headers=h, timeout=30), 200, "matrícula")["generados"][0]["token"]

    tok_con, tok_sin = matricular(con_sexo), matricular(sin_sexo)

    def inscripcion(tok):
        with motor.connect() as c:
            return c.execute(text("select sexo, poblacion, estado from edu_inscripciones where token = :t"), {"t": tok}).one()

    print("\n1 · /intake: sin sexo, con el colegio")
    fila = inscripcion(tok_con)
    comprobar("(control) la inscripción tiene el sexo del padrón", fila.sexo == "Femenino", str(fila.sexo))
    intake = exigir(requests.get(f"{API}/educativo/examen/{tok_con}/intake", timeout=30), 200, "intake")
    comprobar("/intake NO devuelve el sexo", intake.get("sexo") is None, str(intake.get("sexo")))
    comprobar("/intake trae el nombre del colegio", intake.get("institucion_nombre") == nombre_inst, str(intake.get("institucion_nombre")))
    comprobar("/intake trae el logo del colegio", intake.get("institucion_logo_url") == LOGO, str(intake.get("institucion_logo_url")))

    print("\n4 · Nivel Inicial derivado del padrón")
    comprobar("Matriculado en 'Inicial' → población 'Inicial'", fila.poblacion == "Inicial", str(fila.poblacion))
    comprobar("/intake la muestra como ya conocida", intake.get("poblacion") == "Inicial", str(intake.get("poblacion")))

    print("\n3 · Valores del campo Nivel")
    base = {"nombre_completo": "Alumno", "edad": 5, "acepta_terminos": True}
    r = requests.post(f"{API}/educativo/comenzar-test/{tok_sin}", json={**base, "poblacion": "Universitario"}, timeout=30)
    comprobar("'Universitario' ya no es válido (422)", r.status_code == 422, f"{r.status_code} {r.text[:120]}")

    print("\n2 · comenzar-test sin sexo")
    r = requests.post(f"{API}/educativo/comenzar-test/{tok_con}", json={**base, "poblacion": "Inicial"}, timeout=30)
    comprobar("Sin sexo y con 'Inicial' → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    fila = inscripcion(tok_con)
    comprobar("El sexo del padrón se conserva", fila.sexo == "Femenino", str(fila.sexo))

    print("\n5 · Enlace sin sexo en el padrón")
    r = requests.post(f"{API}/educativo/comenzar-test/{tok_sin}", json={**base, "poblacion": "Primaria"}, timeout=30)
    comprobar("comenzar-test sin sexo → 200", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    preguntas = exigir(requests.get(f"{API}/educativo/examen/{tok_sin}/preguntas", timeout=30), 200, "preguntas")
    respuestas = [{"pregunta_id": p["id"], "opcion_id": p["opciones"][0]["id"]} for p in preguntas]
    exigir(requests.post(f"{API}/educativo/examen/{tok_sin}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "guardar")
    exigir(requests.post(f"{API}/educativo/examen/{tok_sin}/finalizar", timeout=60), 200, "finalizar")
    fila = inscripcion(tok_sin)
    comprobar("Queda sin sexo y se finaliza", fila.sexo is None and fila.estado == "Finalizado", str(tuple(fila)))
    with motor.connect() as c:
        sin_baremo = c.execute(text(
            "select count(*) from edu_diagnosticos_alumno d join edu_inscripciones i on i.id = d.inscripcion_id "
            "where i.token = :t and d.nivel is not null"), {"t": tok_sin}).scalar()
    comprobar("Igual encuentra baremo (unisex) e interpreta", sin_baremo > 0, f"diagnósticos con nivel: {sin_baremo}")

    print(f"\n{sum(_resultados)}/{len(_resultados)} comprobaciones pasan.")
    return 0 if all(_resultados) else 1


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    evals = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evals})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE nivel_educativo_id IN ({niveles})"
    with motor.begin() as c:
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
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM registro_cambios_persona WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE grado_id IN ({grados})",
            f"DELETE FROM grados WHERE nivel_educativo_id IN ({niveles})",
            f"DELETE FROM niveles_educativos WHERE institucion_id IN ({insts})",
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
