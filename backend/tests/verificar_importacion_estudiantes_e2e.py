"""Verificación end-to-end — Importación masiva de estudiantes (Excel).

Cubre los 25 casos obligatorios de la fase (número citado en cada
aserción) más la operación de rollback probada directamente sobre
`aplicar_importacion` (más abajo de la API HTTP, porque simula un choque
que la validación normal ya no deja pasar por la API).

    uvicorn main:app --port 8010         (SMTP deshabilitado)
    python tests/verificar_importacion_estudiantes_e2e.py
    python tests/verificar_importacion_estudiantes_e2e.py --limpiar
"""

import argparse
import io
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

PREFIJO = "ZZXLS"
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


ENCABEZADOS = ["codigo_institucional", "nombres", "apellidos", "documento_identidad",
               "fecha_nacimiento", "genero", "nivel_educativo", "grado", "seccion", "turno", "anio_escolar"]


def excel_de(filas, encabezados=None):
    wb = Workbook()
    ws = wb.active
    ws.append(encabezados or ENCABEZADOS)
    for fila in filas:
        ws.append(fila)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def subir(endpoint, headers, buffer, nombre="estudiantes.xlsx"):
    buffer.seek(0)
    return requests.post(
        endpoint, headers=headers,
        files={"archivo": (nombre, buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        timeout=30,
    )


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    r = login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"), os.getenv("SUPERADMIN_PASSWORD"))
    h_super = {"Authorization": f"Bearer {exigir(r, 200, 'login superadmin')['access_token']}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]

    correo_a = f"{PREFIJO.lower()}.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro A", json={
        "email": correo_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} A",
        "rol": "admin", "institucion_id": inst_a}, headers=h_super), 200, "Registro A")
    h_a = {"Authorization": f"Bearer {exigir(login(correo_a, 'ClaveDePrueba123'), 200, 'login A')['access_token']}"}

    correo_colegio_a = f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro colegio A", json={
        "email": correo_colegio_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Colegio-rol A",
        "rol": "colegio", "institucion_id": inst_a}, headers=h_super), 200, "Registro colegio A")
    h_colegio_a = {"Authorization": f"Bearer {exigir(login(correo_colegio_a, 'ClaveDePrueba123'), 200, 'login colegio A')['access_token']}"}

    correo_b = f"{PREFIJO.lower()}.b.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro B", json={
        "email": correo_b, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} B",
        "rol": "admin", "institucion_id": inst_b}, headers=h_super), 200, "Registro B")
    h_b = {"Authorization": f"Bearer {exigir(login(correo_b, 'ClaveDePrueba123'), 200, 'login B')['access_token']}"}

    # Estructura académica de A: Secundaria -> 3° -> A (2026) y B (2027)
    nivel_a = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": f"{PREFIJO}-Secundaria"}, headers=h_a, timeout=30), 200, "Nivel A")
    grado_a = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel_a["id"], "nombre": "3°"}, headers=h_a, timeout=30), 200, "Grado A")
    seccion_a_2026 = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_a["id"], "nombre": "A", "turno": "Mañana", "anio_escolar": 2026},
        headers=h_a, timeout=30), 200, "Sección A 2026")
    exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_a["id"], "nombre": "B", "turno": "Tarde", "anio_escolar": 2027},
        headers=h_a, timeout=30), 200, "Sección B 2027")
    # Un segundo nivel/grado, para probar "grado que no pertenece al nivel"
    nivel_a2 = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_a, "nombre": f"{PREFIJO}-Primaria"}, headers=h_a, timeout=30), 200, "Nivel A2")

    # ==================================================================
    print("\n[1] Plantilla válida")
    r = requests.get(f"{API}/admin/personas/importar/plantilla", headers=h_a, timeout=30)
    comprobar("[1] La plantilla se descarga con 200 y tipo xlsx",
              r.status_code == 200 and "spreadsheetml" in r.headers.get("content-type", ""))
    wb_plantilla = load_workbook(io.BytesIO(r.content))
    comprobar("[1] Trae las 3 hojas esperadas",
              set(wb_plantilla.sheetnames) == {"Estudiantes", "Instrucciones", "Estructura académica"})
    comprobar("[1] La hoja 'Estructura académica' de A lista lo que A ya creó",
              any(row[0] == f"{PREFIJO}-Secundaria" for row in wb_plantilla["Estructura académica"].iter_rows(values_only=True)))

    print("\n[2] Excel 'vacío' (solo encabezado, sin filas de datos)")
    r = subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([]))
    comprobar("[2] Se acepta sin error, con 0 filas — no es un archivo inválido, simplemente no hay nada que hacer",
              r.status_code == 200 and r.json()["total_filas"] == 0, f"status {r.status_code}: {r.text[:200]}")

    print("\n[3] Encabezados incorrectos")
    r = subir(f"{API}/admin/personas/importar/validar", h_a,
              excel_de([["E-1", "Ana", "Torres"]], encabezados=["codigo", "nombre", "apellido"]))
    comprobar("[3] Se rechaza con 422 e indica qué columnas faltan",
              r.status_code == 422 and "codigo_institucional" in r.json()["detail"], f"status {r.status_code}")

    print("\n[4] codigo_institucional faltante")
    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a,
                     excel_de([["", "Ana", "Torres"]])), 200, "Validar sin código")
    fila = r["filas"][0]
    comprobar("[4] La fila se marca como error, señalando el campo vacío",
              fila["accion"] == "error" and any(e["campo"] == "codigo_institucional" for e in fila["errores"]))

    print("\n[5] Código duplicado DENTRO del propio Excel")
    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        [f"{PREFIJO}-D1", "Ana", "Torres"],
        [f"{PREFIJO}-D1", "Ana", "Otra"],
    ])), 200, "Validar duplicado interno")
    comprobar("[5] La primera fila es 'nuevo' y la segunda 'duplicado'",
              r["filas"][0]["accion"] == "nuevo" and r["filas"][1]["accion"] == "duplicado")
    comprobar("[5] El resumen cuenta 1 duplicado", r["resumen"]["duplicados"] == 1)

    # ==================================================================
    print("\n[6][7][8] Creación, código ya existente -> actualización")
    codigo_1 = f"{PREFIJO}-{sello}-001"
    r = exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [codigo_1, "Ana", "Torres Quispe", f"{sello}1", "2012-03-15", "Femenino",
         f"{PREFIJO}-Secundaria", "3°", "A", "Mañana", "2026"],
    ])), 200, "Confirmar creación")
    comprobar("[7] Se crea un estudiante nuevo", r["resumen"]["nuevos"] == 1 and r["resumen"]["actualizados"] == 0)
    persona_1_id = r["detalle"][0]["persona_id"]
    fila_bd = sql_uno("select nombres, apellidos, tipo_perfil, institucion_id from personas where id=:i", i=persona_1_id)
    comprobar("[7] Los datos y tipo_perfil='estudiante' quedan correctos en BD",
              fila_bd == ("Ana", "Torres Quispe", "estudiante", inst_a))
    matricula = sql_uno("select seccion_id from matriculas_academicas where persona_id=:p and fecha_fin is null", p=persona_1_id)
    comprobar("[7] Queda matriculado en la sección resuelta", matricula[0] == seccion_a_2026["id"])

    r2 = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        [codigo_1, "Ana María", "Torres Quispe", f"{sello}1", "2012-03-15", "Femenino", "", "", "", "", ""],
    ])), 200, "Validar mismo código")
    comprobar("[6] Con el mismo codigo_institucional ya existente, se clasifica como 'actualizado', no 'nuevo'",
              r2["filas"][0]["accion"] == "actualizado" and r2["filas"][0]["persona_id_existente"] == persona_1_id)

    r3 = exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [codigo_1, "Ana María", "Torres Quispe", f"{sello}1", "2012-03-15", "Femenino", "", "", "", "", ""],
    ])), 200, "Confirmar actualización")
    comprobar("[8] Se actualiza (no se crea una segunda persona)",
              r3["resumen"]["actualizados"] == 1 and r3["resumen"]["nuevos"] == 0)
    total_con_ese_codigo = sql_uno(
        "select count(*) from personas where institucion_id=:i and codigo_institucional=:c",
        i=inst_a, c=codigo_1)[0]
    comprobar("[6][8] Sigue existiendo UNA sola Persona con ese código (no se duplicó)", total_con_ese_codigo == 1)
    nombre_actualizado = sql_uno("select nombres from personas where id=:i", i=persona_1_id)[0]
    comprobar("[8] El nombre se actualizó de verdad", nombre_actualizado == "Ana María")

    # ==================================================================
    print("\n[9][10] DNI duplicado dentro de una institución / mismo DNI en instituciones distintas")
    dni_compartido = f"{sello}DNIX"
    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        [f"{PREFIJO}-{sello}-DNI1", "Luis", "Ramírez", dni_compartido, "", "", "", "", "", "", ""],
    ])), 200, "Validar DNI 1")
    comprobar("[9] Primera fila con ese DNI, sin conflicto todavía", r["filas"][0]["accion"] == "nuevo")
    exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [f"{PREFIJO}-{sello}-DNI1", "Luis", "Ramírez", dni_compartido, "", "", "", "", "", "", ""],
    ])), 200, "Confirmar DNI 1")

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        [f"{PREFIJO}-{sello}-DNI2", "Otro", "Alumno", dni_compartido, "", "", "", "", "", "", ""],
    ])), 200, "Validar DNI repetido, mismo colegio")
    comprobar("[9] Un DNI ya usado por OTRO estudiante de la MISMA institución es un error",
              r["filas"][0]["accion"] == "error"
              and any(e["campo"] == "documento_identidad" for e in r["filas"][0]["errores"]))

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_b, excel_de([
        [f"{PREFIJO}-{sello}-DNI-B", "Persona", "De B", dni_compartido, "", "", "", "", "", "", ""],
    ])), 200, "Validar mismo DNI en institución B")
    comprobar("[10] El MISMO DNI en OTRA institución no es conflicto (unicidad es por institución, no global)",
              r["filas"][0]["accion"] == "nuevo")

    # ==================================================================
    print("\n[11]-[17] Estructura académica")
    def fila_estructura(nivel, grado, seccion, turno="", anio="2026", codigo_sufijo="X"):
        return [f"{PREFIJO}-{sello}-{codigo_sufijo}", "Test", "Estructura", "", "", "",
                nivel, grado, seccion, turno, anio]

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura("Nivel que no existe", "3°", "A", codigo_sufijo="N1"),
    ])), 200, "Nivel inexistente")
    comprobar("[11] Nivel educativo inexistente -> error", r["filas"][0]["accion"] == "error"
              and any(e["campo"] == "nivel_educativo" for e in r["filas"][0]["errores"]))

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura(f"{PREFIJO}-Secundaria", "9° (no existe)", "A", codigo_sufijo="N2"),
    ])), 200, "Grado inexistente")
    comprobar("[12] Grado inexistente -> error", r["filas"][0]["accion"] == "error"
              and any(e["campo"] == "grado" for e in r["filas"][0]["errores"]))

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura(f"{PREFIJO}-Primaria", "3°", "A", codigo_sufijo="N3"),
    ])), 200, "Grado de otro nivel")
    comprobar("[13] El grado '3°' existe, pero bajo Secundaria, no bajo Primaria -> error distinguido",
              r["filas"][0]["accion"] == "error"
              and any("otro nivel" in e["problema"] for e in r["filas"][0]["errores"]))

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura(f"{PREFIJO}-Secundaria", "3°", "Z (no existe)", codigo_sufijo="N4"),
    ])), 200, "Sección inexistente")
    comprobar("[14] Sección inexistente en ese grado -> error", r["filas"][0]["accion"] == "error"
              and any(e["campo"] == "seccion" for e in r["filas"][0]["errores"]))

    # [15] sección que no pertenece al grado: se crea un segundo grado y se
    # pide su sección "A" pero apuntando al OTRO grado (3°) -> no existe ahí.
    grado_a_otro = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel_a["id"], "nombre": "4°"}, headers=h_a, timeout=30), 200, "Grado 4°")
    exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_a_otro["id"], "nombre": "Z", "anio_escolar": 2026}, headers=h_a, timeout=30), 200, "Sección Z de 4°")
    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura(f"{PREFIJO}-Secundaria", "3°", "Z", codigo_sufijo="N5"),  # "Z" es de 4°, no de 3°
    ])), 200, "Sección de otro grado")
    comprobar("[15] La sección 'Z' existe, pero en otro grado -> error (no se asigna por error)",
              r["filas"][0]["accion"] == "error")

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_b, excel_de([
        fila_estructura(f"{PREFIJO}-Secundaria", "3°", "A", codigo_sufijo="N6"),
    ])), 200, "Sección de otra institución, validada por B")
    comprobar("[16] B no puede usar la estructura académica de A (ni siquiera existe para B) -> error",
              r["filas"][0]["accion"] == "error" and any(e["campo"] == "nivel_educativo" for e in r["filas"][0]["errores"]))

    r = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        fila_estructura(f"{PREFIJO}-Secundaria", "3°", "A", anio="2099", codigo_sufijo="N7"),
    ])), 200, "Año escolar incorrecto")
    comprobar("[17] La sección 'A' de 3° existe, pero no para el año 2099 -> error, NO se crea la sección",
              r["filas"][0]["accion"] == "error"
              and any("año escolar" in e["problema"] for e in r["filas"][0]["errores"]))
    existe_seccion_2099 = sql_uno(
        "select count(*) from secciones where grado_id=:g and anio_escolar=2099", g=grado_a["id"])[0]
    comprobar("[9 de la fase / punto 9] La sección de 2099 NO se creó automáticamente", existe_seccion_2099 == 0)

    # ==================================================================
    print("\n[18][25] Institución ajena / aislamiento completo")
    comprobar("[18] El Excel nunca tiene una columna institucion_id: no hay forma de que el archivo la declare",
              "institucion_id" not in ENCABEZADOS)

    # 🔒 Regla objetivo: superadmin pasa institucion_id explícito; admin/
    # psicologo SIEMPRE se fuerzan a la institución de su propio token — un
    # institucion_id ajeno en la request se ignora en silencio, igual que
    # GET /auth/usuarios/ (nunca un 403: no hay nada que proteger que esto no
    # proteja ya, porque el valor ajeno nunca se usa). La fila SÍ se importa,
    # pero queda en la institución de A, jamás en la de B.
    r_conf = requests.post(
        f"{API}/admin/personas/importar/confirmar", headers=h_a, params={"institucion_id": inst_b},
        files={"archivo": ("e.xlsx", excel_de([[f"{PREFIJO}-{sello}-ISO", "Ana", "Torres"]]), "application/octet-stream")},
        timeout=30,
    )
    comprobar("[18] Confirmar con institucion_id de OTRO colegio -> se ignora, NO da 403",
              r_conf.status_code == 200, f"status {r_conf.status_code}: {r_conf.text[:200]}")
    fila_iso = sql_uno(
        f"select institucion_id from personas where codigo_institucional = '{PREFIJO}-{sello}-ISO'")
    comprobar("[18] La persona SÍ se creó, pero en la institución de A (del token), nunca en la de B",
              fila_iso is not None and fila_iso[0] == inst_a, f"institucion_id={fila_iso}")

    # B crea su PROPIA estructura, con nombres distintos a los de A, para
    # que "A nunca ve la de B" sea una comprobación real y no vacía.
    nivel_b = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_b, "nombre": f"{PREFIJO}-SoloDeB"}, headers=h_b, timeout=30), 200, "Nivel B")
    grado_b = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel_b["id"], "nombre": "1°"}, headers=h_b, timeout=30), 200, "Grado B")
    exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado_b["id"], "nombre": "A", "anio_escolar": 2026}, headers=h_b, timeout=30), 200, "Sección B")

    r_plantilla_cruzada = requests.get(f"{API}/admin/personas/importar/plantilla", headers=h_a, params={"institucion_id": inst_b})
    wb_cruzada = load_workbook(io.BytesIO(r_plantilla_cruzada.content))
    nombres_en_plantilla_cruzada = {
        fila[0] for fila in wb_cruzada["Estructura académica"].iter_rows(values_only=True) if fila[0]
    }
    comprobar("[25] Pedir la plantilla con institucion_id de OTRO colegio -> se ignora, NO da 403 (200 con la propia de A)",
              r_plantilla_cruzada.status_code == 200, f"status {r_plantilla_cruzada.status_code}")
    comprobar(
        "[25] Esa plantilla trae la estructura de A, y NUNCA la de B ('SoloDeB')",
        f"{PREFIJO}-Secundaria" in nombres_en_plantilla_cruzada and f"{PREFIJO}-SoloDeB" not in nombres_en_plantilla_cruzada,
        str(nombres_en_plantilla_cruzada),
    )

    # 🔒 `colegio` no puede importar en absoluto — los tres endpoints exigen
    # requerir_rol("superadmin", "admin", "psicologo"), que nunca incluye
    # `colegio`. Sin esto, un usuario colegio autenticado en su propia
    # institución igual podría dar de alta/actualizar estudiantes por Excel.
    r_colegio_plantilla = requests.get(f"{API}/admin/personas/importar/plantilla", headers=h_colegio_a)
    comprobar("[colegio] GET /importar/plantilla -> 403", r_colegio_plantilla.status_code == 403,
              f"status {r_colegio_plantilla.status_code}")
    r_colegio_validar = requests.post(
        f"{API}/admin/personas/importar/validar", headers=h_colegio_a,
        files={"archivo": ("e.xlsx", excel_de([[f"{PREFIJO}-{sello}-COL", "Ana", "Torres"]]), "application/octet-stream")},
        timeout=30,
    )
    comprobar("[colegio] POST /importar/validar -> 403", r_colegio_validar.status_code == 403,
              f"status {r_colegio_validar.status_code}")
    r_colegio_confirmar = requests.post(
        f"{API}/admin/personas/importar/confirmar", headers=h_colegio_a,
        files={"archivo": ("e.xlsx", excel_de([[f"{PREFIJO}-{sello}-COL", "Ana", "Torres"]]), "application/octet-stream")},
        timeout=30,
    )
    comprobar("[colegio] POST /importar/confirmar -> 403", r_colegio_confirmar.status_code == 403,
              f"status {r_colegio_confirmar.status_code}")
    comprobar("[colegio] Ningún intento de colegio creó una persona",
              sql_uno(f"select count(*) from personas where codigo_institucional = '{PREFIJO}-{sello}-COL'")[0] == 0)

    # Sin institucion_id en el query (el caso normal de un no-superadmin), A
    # sigue viendo SOLO su propia estructura, nunca la de B.
    r = requests.get(f"{API}/admin/personas/importar/plantilla", headers=h_a)
    wb_propia = load_workbook(io.BytesIO(r.content))
    nombres_de_nivel_en_hoja = {
        fila[0] for fila in wb_propia["Estructura académica"].iter_rows(values_only=True) if fila[0]
    }
    comprobar(
        "[25] La plantilla que descarga A (sin institucion_id en el query) muestra la estructura de A, "
        "y NUNCA la de B ('SoloDeB')",
        f"{PREFIJO}-Secundaria" in nombres_de_nivel_en_hoja and f"{PREFIJO}-SoloDeB" not in nombres_de_nivel_en_hoja,
        str(nombres_de_nivel_en_hoja),
    )

    # ==================================================================
    print("\n[19] Rollback de importación (atomicidad)")
    from modulos.superadmin import importacion_estudiantes as importacion
    from core.database import SessionLocal
    db_directo = SessionLocal()
    try:
        resultado_falso = {
            "total_filas": 2,
            "resumen": {"nuevos": 2, "actualizados": 0, "duplicados": 0, "errores": 0},
            "filas": [
                {"fila": 2, "accion": "nuevo", "codigo_institucional": f"{PREFIJO}-{sello}-RB1",
                 "nombres": "Uno", "apellidos": "Rollback", "documento_identidad": f"{sello}RBDNI",
                 "fecha_nacimiento": None, "genero": None, "estructura_academica": None},
                {"fila": 3, "accion": "nuevo", "codigo_institucional": f"{PREFIJO}-{sello}-RB2",
                 "nombres": "Dos", "apellidos": "Rollback", "documento_identidad": f"{sello}RBDNI",  # mismo DNI -> choca en BD
                 "fecha_nacimiento": None, "genero": None, "estructura_academica": None},
            ],
        }
        exploto = False
        try:
            importacion.aplicar_importacion(db_directo, inst_a, resultado_falso, usuario_id=1)
        except Exception:
            exploto = True
        comprobar("[19] aplicar_importacion() propaga el error en vez de dejarlo pasar en silencio", exploto)
    finally:
        db_directo.close()
    quedaron = sql_uno(
        "select count(*) from personas where codigo_institucional in (:a,:b)",
        a=f"{PREFIJO}-{sello}-RB1", b=f"{PREFIJO}-{sello}-RB2")[0]
    comprobar("[19] NINGUNA de las dos filas quedó aplicada — ni siquiera la primera, que individualmente era válida",
              quedaron == 0, f"quedaron={quedaron}")

    # ==================================================================
    print("\n[20] Vista previa antes de guardar (no escribe nada)")
    antes = sql_uno("select count(*) from personas where institucion_id=:i", i=inst_a)[0]
    exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de([
        [f"{PREFIJO}-{sello}-VP1", "No", "Debe Crearse", "", "", "", "", "", "", "", ""],
    ])), 200, "Validar (vista previa)")
    despues = sql_uno("select count(*) from personas where institucion_id=:i", i=inst_a)[0]
    comprobar("[20] /validar no creó ninguna fila (el conteo de personas no cambió)", antes == despues, f"{antes} -> {despues}")

    # ==================================================================
    print("\n[21] Cambio de sección por Excel sin alterar el historial")
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-P-{sello}", "nombre_publico": "Prueba"}, headers=h_a, timeout=30), 200, "Prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}],
        "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "D", "opciones": opciones}]},
        headers=h_a, timeout=30), 200, "Carga masiva")
    detalle_prueba = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa",
                                         headers=h_a, timeout=30), 200, "Detalle prueba")
    pregs = {p["orden"]: p for p in detalle_prueba["dimensiones"][0]["preguntas"]}
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": detalle_prueba["dimensiones"][0]["id"], "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Normal"},
        headers=h_a, timeout=30), 200, "Baremo")
    exigir(requests.post(f"{API}/admin/personas/{persona_1_id}/consentimiento", json={
        "persona_id": persona_1_id, "institucion_id": inst_a,
        "otorgado_por_nombre": "Madre", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30), 200, "Consentimiento")
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba["id"], "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña")
    mat = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                               json=[persona_1_id], headers=h_a, timeout=30), 200, "Matrícula roster")
    token = mat["generados"][0]["token"]
    insc_id, seccion_snap_antes = sql_uno(
        "select id, seccion_id from edu_inscripciones where token=:t", t=token)
    comprobar("[21] La inscripción quedó con el snapshot de la sección ANTES del cambio (A-2026)",
              seccion_snap_antes == seccion_a_2026["id"])

    # El Excel mueve a persona_1 de 3°A-2026 a 3°B-2027
    exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [codigo_1, "Ana María", "Torres Quispe", f"{sello}1", "2012-03-15", "Femenino",
         f"{PREFIJO}-Secundaria", "3°", "B", "Tarde", "2027"],
    ])), 200, "Confirmar cambio de sección")
    seccion_actual = sql_uno(
        "select s.nombre, s.anio_escolar from matriculas_academicas m join secciones s on s.id=m.seccion_id "
        "where m.persona_id=:p and m.fecha_fin is null", p=persona_1_id)
    comprobar("[21] La matrícula ACTUAL ya refleja 3°B-2027", seccion_actual == ("B", 2027))
    seccion_snap_despues = sql_uno("select seccion_id from edu_inscripciones where id=:i", i=insc_id)[0]
    comprobar("[21] La inscripción histórica SIGUE apuntando a 3°A-2026 — el cambio de sección no la tocó",
              seccion_snap_despues == seccion_a_2026["id"] == seccion_snap_antes)

    # ==================================================================
    print("\n[22] Estudiante importado, luego encontrable y matriculable en una campaña")
    r = exigir(requests.get(f"{API}/admin/personas/por-codigo/{codigo_1}", headers=h_a, timeout=30),
               200, "Buscar por código")
    comprobar("[22] Se encuentra por código institucional", r["id"] == persona_1_id)
    mat_2 = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                 json=[persona_1_id], headers=h_a, timeout=30), 200, "Segunda matrícula (rechazada por duplicado en campaña)")
    comprobar("[22] El estudiante importado SÍ es un candidato válido para una campaña "
              "(el único motivo de rechazo aquí es que ya estaba en ESTA campaña, C-15 — no un problema del alumno)",
              not mat_2["generados"] and "ya está matriculado" in mat_2["rechazados"][0]["motivo"])

    # ==================================================================
    print("\n[23] Consentimiento existente no se duplica por re-importar/actualizar")
    consentimientos_antes = sql_uno(
        "select count(*) from consentimientos_informados where persona_id=:p", p=persona_1_id)[0]
    exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [codigo_1, "Ana María", "Torres Quispe (actualizada de nuevo)", f"{sello}1", "2012-03-15", "Femenino", "", "", "", "", ""],
    ])), 200, "Confirmar otra actualización")
    consentimientos_despues = sql_uno(
        "select count(*) from consentimientos_informados where persona_id=:p", p=persona_1_id)[0]
    comprobar("[23] Actualizar por Excel NO creó ningún consentimiento nuevo",
              consentimientos_despues == consentimientos_antes, f"{consentimientos_antes} -> {consentimientos_despues}")

    # ==================================================================
    print("\n[24] Estudiante recién creado, sin consentimiento, no autorizado para evaluar")
    r_nuevo = exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de([
        [f"{PREFIJO}-{sello}-SINCONS", "Sin", "Consentimiento", "", "", "", "", "", "", "", ""],
    ])), 200, "Crear estudiante sin consentimiento")
    persona_sin_consentimiento = r_nuevo["detalle"][0]["persona_id"]
    tiene_consentimiento = sql_uno(
        "select count(*) from consentimientos_informados where persona_id=:p", p=persona_sin_consentimiento)[0]
    comprobar("[24] La importación no le generó ningún consentimiento", tiene_consentimiento == 0)
    mat_sin_consentimiento = exigir(requests.post(
        f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
        json=[persona_sin_consentimiento], headers=h_a, timeout=30), 200, "Intentar matricular sin consentimiento")
    comprobar("[24] No puede matricularse en una campaña: 'estudiante importado' NO equivale a 'autorizado'",
              not mat_sin_consentimiento["generados"]
              and mat_sin_consentimiento["rechazados"][0]["motivo"] == "Sin consentimiento vigente.")

    # ==================================================================
    print("\n[PASO 2] sexo (catálogo abierto) y fecha_nacimiento — ambos opcionales, nunca bloquean")
    fila_sin_sexo = [f"{PREFIJO}-{sello}-P2SINSEXO", "Sin", "Sexo", "", "2012-05-01", "", "", "", "", "", ""]
    fila_sin_fecha = [f"{PREFIJO}-{sello}-P2SINFECHA", "Sin", "Fecha", "", "", "Femenino", "", "", "", "", ""]
    fila_sin_ninguno = [f"{PREFIJO}-{sello}-P2SINNINGUNO", "Sin", "Ninguno", "", "", "", "", "", "", "", ""]
    fila_con_ambos = [f"{PREFIJO}-{sello}-P2CONAMBOS", "Con", "Ambos", "", "2011-08-20", "Otro", "", "", "", "", ""]

    r_validar_p2 = exigir(subir(f"{API}/admin/personas/importar/validar", h_a, excel_de(
        [fila_sin_sexo, fila_sin_fecha, fila_sin_ninguno, fila_con_ambos])), 200, "Validar PASO 2")
    comprobar("[PASO2] Las 4 filas se clasifican como 'nuevo' (nada bloquea por sexo/fecha vacíos)",
              all(f["accion"] == "nuevo" for f in r_validar_p2["filas"]), str(r_validar_p2["filas"]))
    comprobar("[PASO2] 'Otro' (fuera del viejo catálogo cerrado Masculino/Femenino) se acepta sin error",
              next(f for f in r_validar_p2["filas"] if f["codigo_institucional"].endswith("P2CONAMBOS"))["genero"] == "Otro")
    por_codigo_v = {f["codigo_institucional"]: f for f in r_validar_p2["filas"]}
    comprobar("[PASO2] Fila sin sexo -> datos_incompletos=['genero']",
              por_codigo_v[f"{PREFIJO}-{sello}-P2SINSEXO"]["datos_incompletos"] == ["genero"])
    comprobar("[PASO2] Fila sin fecha_nacimiento -> datos_incompletos=['fecha_nacimiento']",
              por_codigo_v[f"{PREFIJO}-{sello}-P2SINFECHA"]["datos_incompletos"] == ["fecha_nacimiento"])
    comprobar("[PASO2] Fila sin ninguno de los dos -> datos_incompletos=['genero', 'fecha_nacimiento']",
              por_codigo_v[f"{PREFIJO}-{sello}-P2SINNINGUNO"]["datos_incompletos"] == ["genero", "fecha_nacimiento"])
    comprobar("[PASO2] Fila con ambos -> datos_incompletos=[] (nada que reportar)",
              por_codigo_v[f"{PREFIJO}-{sello}-P2CONAMBOS"]["datos_incompletos"] == [])
    comprobar("[PASO2] El total de filas con datos incompletos es 3 de 4 (todas menos 'con ambos')",
              r_validar_p2["filas_con_datos_incompletos"] == 3, str(r_validar_p2["filas_con_datos_incompletos"]))

    r_confirmar_p2 = exigir(subir(f"{API}/admin/personas/importar/confirmar", h_a, excel_de(
        [fila_sin_sexo, fila_sin_fecha, fila_sin_ninguno, fila_con_ambos])), 200, "Confirmar PASO 2")
    comprobar("[PASO2] /confirmar aplicó las 4 altas pese a los datos incompletos (nunca bloquea)",
              len(r_confirmar_p2["detalle"]) == 4)
    comprobar("[PASO2] /confirmar también reporta filas_con_datos_incompletos=3",
              r_confirmar_p2["filas_con_datos_incompletos"] == 3)

    fila_bd_sin_sexo = sql_uno(
        f"select genero, fecha_nacimiento is not null from personas where codigo_institucional='{PREFIJO}-{sello}-P2SINSEXO'")
    comprobar("[PASO2] En BD: la persona 'sin sexo' quedó con genero=NULL pero SÍ con fecha_nacimiento",
              fila_bd_sin_sexo[0] is None and fila_bd_sin_sexo[1] is True)
    fila_bd_sin_ninguno = sql_uno(
        f"select genero, fecha_nacimiento from personas where codigo_institucional='{PREFIJO}-{sello}-P2SINNINGUNO'")
    comprobar("[PASO2] En BD: la persona 'sin ninguno' se creó igual, con ambos campos NULL (nunca bloqueó el alta)",
              fila_bd_sin_ninguno[0] is None and fila_bd_sin_ninguno[1] is None)
    fila_bd_con_ambos = sql_uno(
        f"select genero, fecha_nacimiento from personas where codigo_institucional='{PREFIJO}-{sello}-P2CONAMBOS'")
    comprobar("[PASO2] En BD: la persona 'con ambos' guardó genero='Otro' TAL CUAL (catálogo abierto, no normalizado a nada)",
              fila_bd_con_ambos[0] == "Otro" and fila_bd_con_ambos[1] is not None)

    # No se deriva ninguna 'edad' en ningún momento de este flujo — solo se
    # guarda fecha_nacimiento; confirmamos que la tabla personas no tiene
    # ninguna columna 'edad' que la importación pudiera haber rellenado.
    columnas_personas = {c[0] for c in MOTOR.connect().execute(text(
        "select column_name from information_schema.columns where table_name='personas'"))}
    comprobar("[PASO2] La tabla personas no tiene columna 'edad' (se calcula al momento de necesitarse, no se guarda)",
              "edad" not in columnas_personas)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E IMPORTACIÓN DE ESTUDIANTES: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = "SELECT id FROM instituciones WHERE nombre LIKE 'ZZXLS%'"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    grados = f"SELECT id FROM grados WHERE nivel_educativo_id IN ({niveles})"
    secciones = f"SELECT id FROM secciones WHERE grado_id IN ({grados})"
    personas = (
        f"SELECT id FROM personas WHERE institucion_id IN ({insts}) "
        f"OR codigo_institucional LIKE 'ZZXLS%'"
    )
    campanas = "SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZXLS%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    pruebas = "SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZXLS%'"
    with motor.begin() as c:
        for q in [
            f"UPDATE edu_inscripciones SET consentimiento_apoderado_id=NULL WHERE evaluacion_id IN ({campanas})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            "DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZXLS%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            "DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZXLS%'",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE institucion_id IN ({insts}) OR codigo_institucional LIKE 'ZZXLS%'",
            f"DELETE FROM secciones WHERE id IN ({secciones})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
            "DELETE FROM auth_usuarios WHERE email LIKE 'zzxls%'",
            "DELETE FROM instituciones WHERE nombre LIKE 'ZZXLS%'",
        ]:
            c.execute(text(q))
    print("Datos ZZXLS eliminados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--limpiar", action="store_true")
    args = ap.parse_args()
    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
