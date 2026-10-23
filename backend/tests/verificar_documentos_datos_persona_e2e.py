"""Verificación end-to-end del Motor de Documentos Institucionales, Paso 2:
PersonaDatosFamiliares (composición del hogar) y PersonaAntecedentesClinicos
(terapia psicológica / atención psiquiátrica externa, diagnóstico
reportado), ambos 1:1 con Persona, en la ficha del estudiante.

  1   Datos familiares: ficha vacía por defecto (no 404) -> editar -> se
      refleja; lugar_nacimiento y lugar_procedencia son campos distintos
  2   Antecedentes clínicos: ficha vacía por defecto -> editar -> se
      refleja; terapia y psiquiatría se guardan independientes;
      diagnóstico reportado es su propio campo
  3   'colegio' puede LEER ambos bloques pero no editarlos (403)
  4   Aislamiento entre instituciones en lectura y escritura

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_datos_persona_e2e
    python -m tests.verificar_documentos_datos_persona_e2e --limpiar
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

PREFIJO = "ZZPERD"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
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
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    h_psi_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com", f"{PREFIJO} PsiA", "psicologo", inst_a)
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h_psi_a, timeout=30), 200, "crear persona")
    persona_id = persona["id"]

    print("\n1 · PersonaDatosFamiliares")
    vacio = exigir(requests.get(f"{API}/admin/personas/{persona_id}/datos-familiares", headers=h_psi_a, timeout=30), 200, "leer ficha vacía")
    comprobar("[1] Ficha vacía no es 404 — se devuelve la forma vacía", vacio["persona_id"] == persona_id)
    comprobar("[1] numero_hermanos vacío es None", vacio["numero_hermanos"] is None)

    editado = exigir(requests.patch(f"{API}/admin/personas/{persona_id}/datos-familiares", json={
        "numero_hermanos": 2, "vive_con": "Padres y hermano",
        "lugar_nacimiento": "Huancayo, Junín", "lugar_procedencia": "Huancayo",
    }, headers=h_psi_a, timeout=30), 200, "editar datos familiares")
    comprobar("[1] numero_hermanos persistido", editado["numero_hermanos"] == 2)
    comprobar("[1] lugar_nacimiento y lugar_procedencia son campos DISTINTOS",
               editado["lugar_nacimiento"] == "Huancayo, Junín" and editado["lugar_procedencia"] == "Huancayo")

    relectura = exigir(requests.get(f"{API}/admin/personas/{persona_id}/datos-familiares", headers=h_psi_a, timeout=30), 200, "releer datos familiares")
    comprobar("[1] La relectura trae lo mismo que se guardó (upsert, no duplicó fila)",
               relectura["vive_con"] == "Padres y hermano")

    print("\n2 · PersonaAntecedentesClinicos")
    vacio2 = exigir(requests.get(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", headers=h_psi_a, timeout=30), 200, "leer antecedentes vacíos")
    comprobar("[2] Ficha vacía no es 404", vacio2["persona_id"] == persona_id)
    comprobar("[2] recibe_terapia_psicologica_externa vacío es None (no False)",
               vacio2["recibe_terapia_psicologica_externa"] is None)

    editado2 = exigir(requests.patch(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", json={
        "recibe_terapia_psicologica_externa": True,
        "detalle_terapia_psicologica_externa": "Psicóloga particular, sesiones semanales",
        "recibe_atencion_psiquiatrica_externa": False,
        "diagnostico_reportado": "TDAH (diagnóstico externo, 2024)",
    }, headers=h_psi_a, timeout=30), 200, "editar antecedentes clínicos")
    comprobar("[2] Terapia SÍ, psiquiatría NO — quedan independientes",
               editado2["recibe_terapia_psicologica_externa"] is True
               and editado2["recibe_atencion_psiquiatrica_externa"] is False)
    comprobar("[2] detalle_atencion_psiquiatrica_externa vacío al no aplicar", editado2["detalle_atencion_psiquiatrica_externa"] is None)
    comprobar("[2] diagnostico_reportado persistido", editado2["diagnostico_reportado"] == "TDAH (diagnóstico externo, 2024)")

    editado3 = exigir(requests.patch(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", json={
        "detalle_terapia_psicologica_externa": "Cambió de profesional, ahora quincenal",
    }, headers=h_psi_a, timeout=30), 200, "editar solo un campo")
    comprobar("[2] Editar un solo campo no borra diagnostico_reportado (actualización parcial real)",
               editado3["diagnostico_reportado"] == "TDAH (diagnóstico externo, 2024)")
    comprobar("[2] El campo editado sí cambió", editado3["detalle_terapia_psicologica_externa"] == "Cambió de profesional, ahora quincenal")

    print("\n3 · 'colegio' lee pero no edita")
    r = requests.get(f"{API}/admin/personas/{persona_id}/datos-familiares", headers=h_colegio_a, timeout=30)
    comprobar("[3] 'colegio' SÍ puede leer datos familiares", r.status_code == 200, f"status {r.status_code}")
    r = requests.patch(f"{API}/admin/personas/{persona_id}/datos-familiares", json={"numero_hermanos": 5}, headers=h_colegio_a, timeout=30)
    comprobar("[3] 'colegio' NO puede editar datos familiares (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", headers=h_colegio_a, timeout=30)
    comprobar("[3] 'colegio' SÍ puede leer antecedentes clínicos", r.status_code == 200, f"status {r.status_code}")
    r = requests.patch(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", json={"diagnostico_reportado": "hackeado"}, headers=h_colegio_a, timeout=30)
    comprobar("[3] 'colegio' NO puede editar antecedentes clínicos (403)", r.status_code == 403, f"status {r.status_code}")

    print("\n4 · Aislamiento entre instituciones")
    r = requests.get(f"{API}/admin/personas/{persona_id}/datos-familiares", headers=h_psi_b, timeout=30)
    comprobar("[4] B no puede leer datos familiares de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.patch(f"{API}/admin/personas/{persona_id}/datos-familiares", json={"numero_hermanos": 9}, headers=h_psi_b, timeout=30)
    comprobar("[4] B no puede editar datos familiares de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", headers=h_psi_b, timeout=30)
    comprobar("[4] B no puede leer antecedentes clínicos de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.patch(f"{API}/admin/personas/{persona_id}/antecedentes-clinicos", json={"diagnostico_reportado": "hackeado"}, headers=h_psi_b, timeout=30)
    comprobar("[4] B no puede editar antecedentes clínicos de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — DATOS DE PERSONA: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM personas_antecedentes_clinicos WHERE persona_id IN ({personas})",
            f"DELETE FROM personas_datos_familiares WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
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
