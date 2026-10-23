"""Verificación end-to-end de la Promoción Anual de Estudiantes contra el
servidor real: algoritmo de mapeo automático, endpoints
validar/previsualizar/confirmar, y activación explícita del año escolar.

  1  transición dentro del mismo nivel (3° -> 4° primaria)
  2  transición ENTRE niveles (5 años inicial -> 1° primaria) — mismo
     algoritmo, no un caso aparte
  3  último grado de la estructura -> propuesta de EGRESO, sin advertencia
  4  ambigüedad REAL de 'orden' (dos grados empatados por ser "el
     siguiente") -> mapeo manual, nunca adivina
  5  grado resuelto pero sin sección destino creada -> mapeo manual con
     advertencia específica (la sección nunca se crea sola)
  6  excepciones en lote: repitente / retirado / trasladado
  7  confirmar con filas manuales sin resolver se rechaza (409), no aplica
     nada
  8  tras confirmar: motivo_apertura/motivo_cierre/condicion_matricula
     correctos en BD, y la fila de ORIGEN nunca se reescribe (solo se
     cierra) — el mismo mecanismo que ya protege a Inscripcion de un
     cambio de sección corriente
  9  idempotencia: reintentar el mismo año origen/destino ya confirmado
     devuelve 409
 10  activar año escolar es una acción explícita — nunca se activa sola al
     confirmar una promoción
 11  aislamiento entre instituciones (iniciar/confirmar/activar año)

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python -m tests.verificar_promocion_e2e
    python -m tests.verificar_promocion_e2e --limpiar
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

PREFIJO = "ZZASC"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:600]}")
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


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    correo_a = f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro A", json={
        "email": correo_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} A",
        "rol": "admin", "institucion_id": inst_a}, headers=h_super), 200, "Registro A")
    h_a = {"Authorization": f"Bearer {exigir(login(correo_a, 'ClaveDePrueba123'), 200, 'login A')['access_token']}"}

    correo_b = f"{PREFIJO.lower()}.b.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro B", json={
        "email": correo_b, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} B",
        "rol": "admin", "institucion_id": inst_b}, headers=h_super), 200, "Registro B")
    h_b = {"Authorization": f"Bearer {exigir(login(correo_b, 'ClaveDePrueba123'), 200, 'login B')['access_token']}"}

    print("\n1 · Estructura académica de A: Inicial(0) / Primaria(1) / Secundaria(2)")

    def nivel(nombre, orden):
        return exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
            "institucion_id": inst_a, "nombre": nombre, "orden": orden}, headers=h_a, timeout=30), 200, f"nivel {nombre}")["id"]

    def grado(nivel_id, nombre, orden):
        return exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
            "nivel_educativo_id": nivel_id, "nombre": nombre, "orden": orden}, headers=h_a, timeout=30), 200, f"grado {nombre}")["id"]

    def seccion(grado_id, nombre, anio):
        return exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
            "grado_id": grado_id, "nombre": nombre, "anio_escolar": anio}, headers=h_a, timeout=30), 200, f"sección {nombre} {anio}")["id"]

    niv_inicial = nivel("Inicial", 0)
    niv_primaria = nivel("Primaria", 1)
    niv_secundaria = nivel("Secundaria", 2)

    grado_5anios = grado(niv_inicial, "5 años", 0)
    grado_1prim = grado(niv_primaria, "1°", 0)
    grado_3prim = grado(niv_primaria, "3°", 2)
    grado_4prim = grado(niv_primaria, "4°", 3)
    grado_5sec = grado(niv_secundaria, "5°", 4)  # último grado de toda la estructura
    # Grado justo ANTES de un empate real de 'orden' (Amb1/Amb2, ambos 9):
    # un estudiante aquí SÍ tiene una sucesión ambigua.
    grado_pre_ambiguo = grado(niv_primaria, "PreAmbiguo", 8)
    grado(niv_primaria, "Amb1", 9)
    grado(niv_primaria, "Amb2", 9)
    grado_sin_seccion = grado(niv_primaria, "SinSeccionDestino", 20)
    grado_siguiente_sin_seccion = grado(niv_primaria, "SiguienteSinSeccion", 21)

    sec_5anios_2026 = seccion(grado_5anios, "A", 2026)
    seccion(grado_1prim, "A", 2027)  # destino de la transición de nivel
    sec_3prim_2026 = seccion(grado_3prim, "A", 2026)
    seccion(grado_4prim, "A", 2027)  # destino normal
    sec_5sec_2026 = seccion(grado_5sec, "A", 2026)
    sec_pre_amb_2026 = seccion(grado_pre_ambiguo, "A", 2026)
    sec_sin_seccion_2026 = seccion(grado_sin_seccion, "A", 2026)
    # A propósito NO se crea sección 2027 para grado_siguiente_sin_seccion:
    # la sección destino nunca se crea sola (punto 8 del diseño aprobado).
    sec_retirar_2026 = seccion(grado_3prim, "B", 2026)
    sec_trasladar_2026 = seccion(grado_3prim, "C", 2026)
    sec_repetir_2026 = seccion(grado_3prim, "D", 2026)
    sec_repetir_2027 = seccion(grado_3prim, "D", 2027)  # repitente: mismo grado, año siguiente

    print("\n2 · Estudiantes matriculados en 2026")

    def estudiante(nombre, seccion_id):
        persona_id = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_a, "nombres": nombre, "apellidos": PREFIJO, "tipo_perfil": "estudiante"},
            headers=h_a, timeout=30), 200, f"crear {nombre}")["id"]
        exigir(requests.post(f"{API}/admin/personas/{persona_id}/matricula", json={"seccion_id": seccion_id},
               headers=h_a, timeout=30), 200, f"matricular {nombre}")
        return persona_id

    p_transicion_nivel = estudiante("TransicionNivel", sec_5anios_2026)
    p_normal = estudiante("Normal", sec_3prim_2026)
    p_egreso = estudiante("Egreso", sec_5sec_2026)
    p_ambiguo = estudiante("Ambiguo", sec_pre_amb_2026)
    p_seccion_faltante = estudiante("SeccionFaltante", sec_sin_seccion_2026)
    p_retirar = estudiante("Retirar", sec_retirar_2026)
    p_trasladar = estudiante("Trasladar", sec_trasladar_2026)
    p_repetir = estudiante("Repetir", sec_repetir_2026)

    print("\n3 · Aislamiento: B no puede iniciar la promoción de A")
    r = requests.post(f"{API}/admin/personas/promocion/procesos", json={
        "institucion_id": inst_a, "anio_origen": 2026, "anio_destino": 2027}, headers=h_b, timeout=30)
    comprobar("B->A iniciar proceso de A devuelve 403", r.status_code == 403, f"status {r.status_code}")

    print("\n4 · Iniciar el proceso de promoción de A (algoritmo de mapeo automático)")
    proceso = exigir(requests.post(f"{API}/admin/personas/promocion/procesos", json={
        "anio_origen": 2026, "anio_destino": 2027}, headers=h_a, timeout=30), 201, "iniciar proceso")
    proceso_id = proceso["proceso"]["id"]
    comprobar("El proceso queda en estado 'borrador'", proceso["proceso"]["estado"] == "borrador")

    detalle_por_persona = {d["persona_id"]: d for d in proceso["detalle"]}

    d = detalle_por_persona[p_transicion_nivel]
    comprobar(
        "Transición de NIVEL (5 años inicial -> 1° primaria) resuelta automáticamente",
        d["tipo_excepcion"] == "ninguna" and d["seccion_propuesta"] is not None
        and d["seccion_propuesta"]["grado"] == "1°" and d["seccion_propuesta"]["nivel_educativo"] == "Primaria",
        str(d["seccion_propuesta"]),
    )

    d = detalle_por_persona[p_normal]
    comprobar(
        "Promoción normal (3° -> 4° primaria, misma sección 'A') resuelta automáticamente",
        d["tipo_excepcion"] == "ninguna" and d["seccion_propuesta"] is not None
        and d["seccion_propuesta"]["grado"] == "4°" and d["seccion_propuesta"]["seccion"] == "A",
        str(d["seccion_propuesta"]),
    )

    d = detalle_por_persona[p_egreso]
    comprobar(
        "Último grado de la estructura -> propuesta de EGRESO (sin sección, sin advertencia)",
        d["tipo_excepcion"] == "egreso" and d["seccion_propuesta"] is None and d["advertencia_mapeo"] is None,
        str(d),
    )

    d = detalle_por_persona[p_ambiguo]
    comprobar(
        "Ambigüedad REAL de 'orden' -> mapeo manual con advertencia (nunca adivina)",
        d["tipo_excepcion"] == "cambio_manual" and d["seccion_propuesta"] is None and d["advertencia_mapeo"] is not None,
        str(d["advertencia_mapeo"]),
    )

    d = detalle_por_persona[p_seccion_faltante]
    comprobar(
        "Grado resuelto pero sin sección destino creada -> manual con advertencia específica",
        d["tipo_excepcion"] == "cambio_manual" and d["seccion_propuesta"] is None
        and "no existe una sección" in (d["advertencia_mapeo"] or ""),
        str(d["advertencia_mapeo"]),
    )

    print("\n5 · Marcar excepciones en lote: repitente / retirado / trasladado")
    edits = [
        {"detalle_id": detalle_por_persona[p_repetir]["detalle_id"], "tipo_excepcion": "repitente", "seccion_definitiva_id": sec_repetir_2027},
        {"detalle_id": detalle_por_persona[p_retirar]["detalle_id"], "tipo_excepcion": "retirado", "seccion_definitiva_id": None},
        {"detalle_id": detalle_por_persona[p_trasladar]["detalle_id"], "tipo_excepcion": "trasladado", "seccion_definitiva_id": None},
    ]
    r = requests.patch(f"{API}/admin/personas/promocion/procesos/{proceso_id}/detalle", json={"ediciones": edits}, headers=h_a, timeout=30)
    comprobar("La edición en lote de 3 filas devuelve 200", r.status_code == 200, r.text[:300])

    print("\n6 · Rechazo: confirmar con filas manuales sin resolver")
    r = requests.post(f"{API}/admin/personas/promocion/procesos/{proceso_id}/confirmar", headers=h_a, timeout=30)
    comprobar("Confirmar con filas manuales pendientes -> 409, no aplica nada", r.status_code == 409, r.text[:300])
    sin_aplicar = sql_uno(
        "SELECT COUNT(*) AS n FROM procesos_promocion_detalle WHERE proceso_id=:p AND aplicado=true", p=proceso_id,
    )
    comprobar("Ninguna fila quedó aplicada tras el rechazo", sin_aplicar.n == 0)

    print("\n7 · Resolver manualmente las 2 filas pendientes -> confirmar")
    edits2 = [
        {"detalle_id": detalle_por_persona[p_ambiguo]["detalle_id"], "tipo_excepcion": "cambio_manual", "seccion_definitiva_id": sql_uno(
            "SELECT id FROM secciones WHERE grado_id=:g AND anio_escolar=2027", g=grado_4prim).id},
        {"detalle_id": detalle_por_persona[p_seccion_faltante]["detalle_id"], "tipo_excepcion": "cambio_manual", "seccion_definitiva_id": sql_uno(
            "SELECT id FROM secciones WHERE grado_id=:g AND anio_escolar=2027", g=grado_4prim).id},
    ]
    exigir(requests.patch(f"{API}/admin/personas/promocion/procesos/{proceso_id}/detalle", json={"ediciones": edits2}, headers=h_a, timeout=30), 200, "resolver manuales")

    confirmado = exigir(requests.post(f"{API}/admin/personas/promocion/procesos/{proceso_id}/confirmar", headers=h_a, timeout=30), 200, "confirmar")
    comprobar("El proceso queda 'confirmado'", confirmado["proceso"]["estado"] == "confirmado")

    print("\n8 · Verificación en BD tras confirmar")
    m_origen_normal = sql_uno(
        "SELECT id, seccion_id, fecha_fin, motivo_cierre FROM matriculas_academicas WHERE persona_id=:p AND seccion_id=:s",
        p=p_normal, s=sec_3prim_2026,
    )
    comprobar(
        "La fila de ORIGEN de 'Normal' NUNCA se reescribe: sigue apuntando a su sección original, solo se cerró",
        m_origen_normal.seccion_id == sec_3prim_2026 and m_origen_normal.fecha_fin is not None and m_origen_normal.motivo_cierre == "promocion",
        str(m_origen_normal),
    )
    m_nueva_normal = sql_uno(
        "SELECT motivo_apertura, seccion_id FROM matriculas_academicas WHERE persona_id=:p AND fecha_fin IS NULL", p=p_normal,
    )
    comprobar("Nueva matrícula de 'Normal' abierta con motivo_apertura='promocion' en 4°A/2027",
              m_nueva_normal.motivo_apertura == "promocion", str(m_nueva_normal))

    m_repetir = sql_uno(
        "SELECT motivo_apertura, seccion_id FROM matriculas_academicas WHERE persona_id=:p AND fecha_fin IS NULL", p=p_repetir,
    )
    comprobar("Repitente: motivo_apertura='repitencia', misma sección de grado (3°D) en el año siguiente",
              m_repetir.motivo_apertura == "repitencia" and m_repetir.seccion_id == sec_repetir_2027, str(m_repetir))

    p_retirar_row = sql_uno("SELECT condicion_matricula FROM personas WHERE id=:p", p=p_retirar)
    m_retirar = sql_uno("SELECT motivo_cierre FROM matriculas_academicas WHERE persona_id=:p AND seccion_id=:s", p=p_retirar, s=sec_retirar_2026)
    sin_nueva_retirar = sql_uno("SELECT COUNT(*) AS n FROM matriculas_academicas WHERE persona_id=:p AND fecha_fin IS NULL", p=p_retirar)
    comprobar(
        "Retirado: condicion_matricula='retirado', motivo_cierre='retiro', SIN matrícula nueva",
        p_retirar_row.condicion_matricula == "retirado" and m_retirar.motivo_cierre == "retiro" and sin_nueva_retirar.n == 0,
        str((p_retirar_row, m_retirar, sin_nueva_retirar.n)),
    )

    p_trasladar_row = sql_uno("SELECT condicion_matricula FROM personas WHERE id=:p", p=p_trasladar)
    comprobar("Trasladado: condicion_matricula='trasladado'", p_trasladar_row.condicion_matricula == "trasladado")

    p_egreso_row = sql_uno("SELECT condicion_matricula FROM personas WHERE id=:p", p=p_egreso)
    comprobar("Egreso: condicion_matricula='egresado'", p_egreso_row.condicion_matricula == "egresado")

    print("\n9 · Idempotencia: reintentar el mismo origen/destino tras confirmar")
    r = requests.post(f"{API}/admin/personas/promocion/procesos", json={"anio_origen": 2026, "anio_destino": 2027}, headers=h_a, timeout=30)
    comprobar("Reintentar 2026->2027 tras confirmar devuelve 409 (ya confirmada)", r.status_code == 409, r.text[:200])

    print("\n10 · Activar año escolar — acción explícita, separada de confirmar")
    inst_antes = exigir(requests.get(f"{API}/instituciones/me", headers=h_a, timeout=30), 200, "ver institución A")
    comprobar("anio_escolar_activo sigue NULL tras confirmar la promoción (nunca se activa solo)",
              inst_antes.get("anio_escolar_activo") is None, str(inst_antes.get("anio_escolar_activo")))

    r = requests.patch(f"{API}/instituciones/{inst_a}/anio-escolar-activo", json={"anio_escolar": 2027}, headers=h_a, timeout=30)
    inst_despues = exigir(r, 200, "activar año escolar")
    comprobar("Tras la acción explícita, anio_escolar_activo=2027", inst_despues["anio_escolar_activo"] == 2027)

    print("\n11 · Aislamiento: B no puede activar el año escolar de A")
    r = requests.patch(f"{API}/instituciones/{inst_a}/anio-escolar-activo", json={"anio_escolar": 2027}, headers=h_b, timeout=30)
    comprobar("B no puede activar el año escolar de A (403)", r.status_code == 403, f"status {r.status_code}")

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E PROMOCIÓN ANUAL: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE nivel_educativo_id IN ({niveles})"
    secciones = f"SELECT id FROM secciones WHERE grado_id IN ({grados})"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    matriculas = f"SELECT id FROM matriculas_academicas WHERE persona_id IN ({personas})"
    procesos = f"SELECT id FROM procesos_promocion WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM procesos_promocion_detalle WHERE proceso_id IN ({procesos})",
            f"DELETE FROM procesos_promocion WHERE institucion_id IN ({insts})",
            f"DELETE FROM matriculas_academicas WHERE id IN ({matriculas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts})",
            f"DELETE FROM secciones WHERE id IN ({secciones})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
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
        sys.exit(0)
    sys.exit(main(args.url))
