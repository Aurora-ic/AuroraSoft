"""Verificación end-to-end — Prueba TÉCNICA INTERNA de validación del motor
(APTITUD_TECNICA_INTERNA): NO clínica, NO comercial, NO psicométrica, NO
asociada a BARSIT/ICAR ni a ningún instrumento real. Su único propósito es
demostrar que el motor genérico soporta un segundo modo de cálculo
(correcto_incorrecto) y un informe con varias dimensiones reales, antes de
cargar cualquier instrumento comercial.

Cubre los puntos obligatorios de esta fase (ver encargo "FASE 8 — E2E y
regresión"):

  0   Idempotencia del seed: correrlo dos veces no duplica nada
  1   correcto_incorrecto: cada correcta suma 1, cada incorrecta suma 0
  2   Múltiples dimensiones reales (Verbal/Numérica/Abstracta) agrupadas
      correctamente y de forma independiente
  3   Baremos por edad: el MISMO puntaje directo clasifica distinto según
      la banda de edad (10-14 vs 15-18)
  4   Varias ReglaInterpretacion simultáneas sobre distintas dimensiones de
      la MISMA inscripción: ambas quedan registradas, no se pisan, y una
      regla activada en una dimensión NO alerta las demás automáticamente
  5   Informe profesional con N dimensiones reales (PDF real, vía pypdf)
  6   Storage + checksum + versionado/reemisión + historial
  7   Aislamiento multi-tenant
  8   Regresión ligera: likert_suma (PHQ-9) sigue funcionando exactamente igual

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_prueba_aptitud_tecnica_e2e.py
    python tests/verificar_prueba_aptitud_tecnica_e2e.py --limpiar
"""

import argparse
import hashlib
import io
import os
import subprocess
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from pypdf import PdfReader
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZAPT"
NOMBRE_TECNICO_PRUEBA = "APTITUD_TECNICA_INTERNA"
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


def texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    texto_crudo = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    return " ".join(texto_crudo.split())


def crear_colegio(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
    correo = f"{PREFIJO.lower()}.psi.{letra.lower()}.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {letra}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo {letra}",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro {letra}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {letra}")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


def crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta):
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"},
        headers=headers, timeout=30), 200, f"Persona {etiqueta}")
    exigir(requests.post(f"{API}/admin/personas/{persona['id']}/consentimiento", json={
        "persona_id": persona["id"], "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"},
        headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    return persona["id"]


def matricular(headers, campana_id, persona_id):
    m = exigir(requests.post(f"{API}/educativo/campanas/{campana_id}/matricular-roster",
                             json=[persona_id], headers=headers, timeout=30), 200, "Matrícula")
    return m["generados"][0]["token"]


def aplicar_aptitud(headers, inst_id, sello, etiqueta, prueba_id, preg_por_dim, edad, aciertos_por_dim, headers_campana=None):
    """Crea campaña + persona + consentimiento + matrícula + responde y finaliza
    la prueba técnica. `aciertos_por_dim` es {"Verbal": [True,True,False,False,False], ...}
    — un booleano (acertó/no) por cada uno de los 5 ítems, en orden. Devuelve
    (token, inscripcion_id, persona_id).

    `headers_campana` (por defecto = `headers`): desde que la prueba técnica es
    `visible_para_clientes=False`, SOLO superadmin puede crear una campaña con
    ella (ver PUNTO 3) — el resto del flujo (persona, matrícula, examen) sigue
    corriendo con las credenciales normales de la institución `headers`.
    """
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers_campana or headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona_id = crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta)
    token = matricular(headers, campana["id"], persona_id)

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": edad, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    respuestas = []
    for nombre_dim, aciertos in aciertos_por_dim.items():
        preguntas = preg_por_dim[nombre_dim]
        for orden, acerto in enumerate(aciertos, start=1):
            pregunta = preguntas[orden]
            valor_deseado = 1 if acerto else 0
            opcion_id = next(o["id"] for o in pregunta["opciones"] if o["valor_puntuacion"] == valor_deseado)
            respuestas.append({"pregunta_id": pregunta["id"], "opcion_id": opcion_id})

    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")
    r = requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60)
    exigir(r, 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id, persona_id from edu_inscripciones where token=:t", t=token)
    return token, insc[0], insc[1]


def esperar_informe(headers, inscripcion_id, timeout=20):
    limite = time.time() + timeout
    while time.time() < limite:
        r = requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30)
        if r.status_code == 200 and r.json().get("existe"):
            return r.json()
        time.sleep(0.5)
    return requests.get(f"{API}/educativo/inscripciones/{inscripcion_id}/informe", headers=headers, timeout=30).json()


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ==================================================================
    print("\n0 · IDEMPOTENCIA — correr el seed dos veces no duplica nada")
    raiz_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def contar(consulta):
        return sql_uno(consulta)[0]

    def conteos():
        return (
            contar(f"select count(*) from edu_pruebas where nombre_tecnico = '{NOMBRE_TECNICO_PRUEBA}' and institucion_id is null"),
            contar(f"select count(*) from edu_preguntas q join edu_pruebas p on p.id = q.prueba_id "
                   f"where p.nombre_tecnico = '{NOMBRE_TECNICO_PRUEBA}'"),
            contar(f"select count(*) from edu_baremos b join edu_dimensiones d on d.id = b.dimension_id "
                   f"join edu_pruebas p on p.id = d.prueba_id where p.nombre_tecnico = '{NOMBRE_TECNICO_PRUEBA}'"),
            contar(f"select count(*) from edu_reglas_interpretacion r join edu_pruebas p on p.id = r.prueba_id "
                   f"where p.nombre_tecnico = '{NOMBRE_TECNICO_PRUEBA}'"),
        )

    seed_modulo = ["-m", "seeds.seed_prueba_aptitud_tecnica"]
    r1 = subprocess.run([sys.executable, *seed_modulo], cwd=raiz_backend, capture_output=True, text=True)
    comprobar("[0] Primera corrida del seed termina sin error", r1.returncode == 0, r1.stderr[-300:] if r1.returncode else "")
    conteos_1 = conteos()
    r2 = subprocess.run([sys.executable, *seed_modulo], cwd=raiz_backend, capture_output=True, text=True)
    comprobar("[0] Segunda corrida del seed termina sin error", r2.returncode == 0, r2.stderr[-300:] if r2.returncode else "")
    conteos_2 = conteos()
    comprobar("[0] La prueba pública sigue siendo UNA sola tras la segunda corrida", conteos_2[0] == 1, str(conteos_2))
    comprobar("[0] El número de preguntas NO cambió (15) tras repetir el seed", conteos_1[1] == conteos_2[1] == 15, str(conteos_2))
    comprobar("[0] El número de tramos de baremo NO cambió (18) tras repetir el seed", conteos_1[2] == conteos_2[2] == 18, str(conteos_2))
    comprobar("[0] El número de reglas NO cambió (3) tras repetir el seed", conteos_1[3] == conteos_2[3] == 3, str(conteos_2))

    # ==================================================================
    print("\n0b · Montaje: dos instituciones + localizar la prueba técnica pública")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a, h_a = crear_colegio(h_super, "A", sello)
    inst_b, h_b = crear_colegio(h_super, "B", sello)

    prueba_id = sql_uno(f"select id from edu_pruebas where nombre_tecnico = '{NOMBRE_TECNICO_PRUEBA}' and institucion_id is null")[0]
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_id}/completa", headers=h_a, timeout=30), 200, "Detalle prueba técnica")

    comprobar("[2] La prueba trae exactamente 3 dimensiones", len(detalle["dimensiones"]) == 3)
    comprobar("[2] Las dimensiones son Verbal, Numérica y Abstracta",
              {d["nombre"] for d in detalle["dimensiones"]} == {"Verbal", "Numérica", "Abstracta"})
    comprobar("[1] modo_calculo es 'correcto_incorrecto'", detalle["modo_calculo"] == "correcto_incorrecto")
    comprobar("[3] Trae 18 tramos de baremo (2 bandas x 3 dimensiones x 3 niveles)", len(detalle["baremos"]) == 18)
    comprobar("[4] Trae 3 reglas de interpretación (una por dimensión)", len(detalle["reglas"]) == 3)
    comprobar("[4] Las 3 reglas son de ámbito 'dimension'", all(r["ambito"] == "dimension" for r in detalle["reglas"]))
    nombre_no_clinico = (detalle["nombre_publico"] + " " + (detalle["instrucciones"] or "")).upper()
    comprobar("[seguridad de contenido] El PDF/detalle no se identifica como BARSIT ni ICAR",
              "BARSIT" not in detalle["nombre_publico"].upper() and "ICAR" not in detalle["nombre_publico"].upper())

    preg_por_dim = {d["nombre"]: {p["orden"]: p for p in d["preguntas"]} for d in detalle["dimensiones"]}
    for nombre_dim, preguntas in preg_por_dim.items():
        comprobar(f"[2] Dimensión '{nombre_dim}' tiene 5 ítems", len(preguntas) == 5)
        for p in preguntas.values():
            comprobar(f"[1] Ítem de '{nombre_dim}' tiene exactamente 2 alternativas (0 y 1)",
                      sorted(o["valor_puntuacion"] for o in p["opciones"]) == [0, 1])

    dim_id_por_nombre = {d["nombre"]: d["id"] for d in detalle["dimensiones"]}
    regla_id_por_dimension_id = {r["dimension_id"]: r["id"] for r in detalle["reglas"]}

    # ==================================================================
    print("\n1 · CASO A — sin alerta en ninguna dimensión (correcto_incorrecto: 1 acierto de 5 en cada una)")
    # edad=12 -> banda 10-14: 0-1 Bajo (sin alerta), 2-3 Medio, 4-5 Alto (alerta).
    # 1 acierto = puntaje 1 = Bajo en las 3 dimensiones; la regla (>=3) no dispara.
    aciertos_a = {
        "Verbal": [True, False, False, False, False],
        "Numérica": [True, False, False, False, False],
        "Abstracta": [True, False, False, False, False],
    }
    tok_a, insc_a, _ = aplicar_aptitud(h_a, inst_a, sello, "CasoA", prueba_id, preg_por_dim, edad=12, aciertos_por_dim=aciertos_a, headers_campana=h_super)

    resultados_a = {row[0]: row[1] for row in MOTOR.connect().execute(text(
        "select dimension_id, puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i"), {"i": insc_a}).fetchall()}
    comprobar("[1] Puntaje directo de Verbal = 1 (1 correcta suma 1, 4 incorrectas suman 0)",
              float(resultados_a[dim_id_por_nombre["Verbal"]]) == 1.0)
    comprobar("[1] Puntaje directo de Numérica = 1", float(resultados_a[dim_id_por_nombre["Numérica"]]) == 1.0)
    comprobar("[1][2] Puntaje directo de Abstracta = 1 (3 dimensiones calculadas de forma independiente)",
              float(resultados_a[dim_id_por_nombre["Abstracta"]]) == 1.0)

    diag_a = MOTOR.connect().execute(text(
        "select dimension_id, nivel, es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i"), {"i": insc_a}).fetchall()
    comprobar("[2] Se generaron exactamente 3 diagnósticos (uno por dimensión)", len(diag_a) == 3)
    comprobar("[3][4] Las 3 dimensiones quedan en 'Bajo (clasificación técnica)', sin alerta",
              all("Bajo" in d[1] and d[2] is False and d[3] is None for d in diag_a), str(diag_a))

    estado_a = sql_uno("select resultado_visible_alumno, informe_liberado, estado_interpretacion from edu_inscripciones where id=:i", i=insc_a)
    comprobar("[2] Interpretación completa (las 3 dimensiones encontraron baremo)", estado_a[2] == "completa")
    comprobar("[caso A] Sin ninguna alerta, el resultado queda visible de inmediato", estado_a[0] is True and estado_a[1] is True)

    # ==================================================================
    print("\n2 · CASO MULTI — varias reglas simultáneas sobre distintas dimensiones de la MISMA inscripción")
    # edad=12 (banda 10-14):
    #   Verbal   = 3 aciertos -> Medio, SIN alerta de baremo; regla (>=3) SÍ dispara -> alerta_por='regla'
    #   Numérica = 4 aciertos -> Alto, CON alerta de baremo;  regla (>=3) también dispara -> alerta_por='baremo,regla'
    #   Abstracta= 1 acierto  -> Bajo, sin alerta de baremo NI de regla (1 < 3) -> sin alerta
    aciertos_multi = {
        "Verbal": [True, True, True, False, False],
        "Numérica": [True, True, True, True, False],
        "Abstracta": [True, False, False, False, False],
    }
    tok_multi, insc_multi, _ = aplicar_aptitud(h_a, inst_a, sello, "CasoMulti", prueba_id, preg_por_dim, edad=12, aciertos_por_dim=aciertos_multi, headers_campana=h_super)

    diag_multi = {row[0]: row for row in MOTOR.connect().execute(text(
        "select dimension_id, nivel, es_alerta, alerta_por, regla_activada_id from edu_diagnosticos_alumno where inscripcion_id=:i"),
        {"i": insc_multi}).fetchall()}
    comprobar("[4] Se generaron 3 diagnósticos (uno por dimensión), ninguno se pisó", len(diag_multi) == 3)

    d_verbal = diag_multi[dim_id_por_nombre["Verbal"]]
    d_numerica = diag_multi[dim_id_por_nombre["Numérica"]]
    d_abstracta = diag_multi[dim_id_por_nombre["Abstracta"]]

    comprobar("[3] Verbal queda en 'Medio (clasificación técnica)'", "Medio" in d_verbal[1])
    comprobar("[4] Verbal: alerta SOLO por regla (el baremo por sí solo no habría alertado)",
              d_verbal[2] is True and d_verbal[3] == "regla")
    comprobar("[4] Verbal: regla_activada_id apunta a LA REGLA PROPIA de Verbal",
              d_verbal[4] == regla_id_por_dimension_id[dim_id_por_nombre["Verbal"]])

    comprobar("[3] Numérica queda en 'Alto (clasificación técnica)'", "Alto" in d_numerica[1])
    comprobar("[4] Numérica: alerta por AMBOS orígenes (baremo Y regla, sin duplicar la fila)",
              d_numerica[2] is True and d_numerica[3] == "baremo,regla")
    comprobar("[4] Numérica: regla_activada_id apunta a LA REGLA PROPIA de Numérica (distinta de la de Verbal)",
              d_numerica[4] == regla_id_por_dimension_id[dim_id_por_nombre["Numérica"]]
              and d_numerica[4] != d_verbal[4])

    comprobar("[3] Abstracta queda en 'Bajo (clasificación técnica)'", "Bajo" in d_abstracta[1])
    comprobar("[4] Abstracta NO se ve afectada por las alertas de Verbal/Numérica (sin alerta, sin regla, sin cruce)",
              d_abstracta[2] is False and d_abstracta[3] is None and d_abstracta[4] is None)

    estado_multi = sql_uno("select resultado_visible_alumno, informe_liberado, estado_interpretacion from edu_inscripciones where id=:i", i=insc_multi)
    comprobar("[caso multi] Con al menos una dimensión en alerta, el informe queda retenido", estado_multi[0] is False and estado_multi[1] is False)
    comprobar("[caso multi] La interpretación sigue completa (todas las dimensiones tuvieron baremo aplicable)", estado_multi[2] == "completa")

    # ==================================================================
    print("\n3 · CASO EDAD — el MISMO puntaje directo (4) clasifica distinto según la banda de edad")
    # edad=16 (banda 15-18): 4 aciertos en Numérica -> tramo 3-4 = Medio, SIN alerta de
    # baremo (el umbral de alerta en esta banda es 5, no 4 como en la banda 10-14).
    # La regla (>=3) sigue disparando igual (no depende de la edad) -> alerta_por='regla' (no 'baremo,regla').
    aciertos_edad = {
        "Verbal": [True, False, False, False, False],
        "Numérica": [True, True, True, True, False],
        "Abstracta": [True, False, False, False, False],
    }
    tok_edad, insc_edad, _ = aplicar_aptitud(h_a, inst_a, sello, "CasoEdad", prueba_id, preg_por_dim, edad=16, aciertos_por_dim=aciertos_edad, headers_campana=h_super)
    d_numerica_16 = sql_uno(
        "select nivel, es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i and dimension_id=:d",
        i=insc_edad, d=dim_id_por_nombre["Numérica"])
    comprobar("[3] Puntaje 4 en Numérica a los 16 años clasifica como 'Medio' (a los 12 años el MISMO puntaje era 'Alto')",
              "Medio" in d_numerica_16[0], d_numerica_16)
    comprobar("[3] A los 16 años ese mismo puntaje NO alerta por baremo (el umbral en esta banda es 5, no 4)",
              d_numerica_16[2] == "regla", d_numerica_16)

    # ==================================================================
    print("\n4 · INFORME PROFESIONAL con 3 dimensiones reales — PDF real, verificado con pypdf")
    esperar_informe(h_a, insc_multi)
    r_pdf = requests.get(f"{API}/educativo/inscripciones/{insc_multi}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[5] El informe (staff) se descarga (200) aunque esté retenido al alumno", r_pdf.status_code == 200)
    contenido = r_pdf.content
    comprobar("[5] Es un PDF real (%PDF-)", contenido[:5] == b"%PDF-")

    r_pdf_alumno = requests.get(f"{API}/educativo/examen/{tok_multi}/informe-pdf", timeout=60)
    comprobar("[5] El alumno NO puede descargarlo mientras está retenido (403)", r_pdf_alumno.status_code == 403)

    texto = texto_pdf(contenido)
    comprobar("[5] pypdf abre el PDF y extrae texto real (no está corrupto)", len(texto) > 200)
    comprobar("[5] Estructura fija de siempre: encabezado + confidencialidad", "INFORME PSICOMÉTRICO" in texto and "DOCUMENTO CONFIDENCIAL" in texto)
    comprobar("[5] Muestra el banner de alerta (al menos una dimensión en riesgo técnico)",
              "REQUIERE REVISIÓN PROFESIONAL" in texto)
    comprobar("[5] NO menciona BARSIT en ningún lugar del PDF", "BARSIT" not in texto.upper())
    comprobar("[5] NO menciona ICAR en ningún lugar del PDF", "ICAR" not in texto.upper())
    comprobar("[5] Las 3 dimensiones aparecen por nombre en el PDF",
              "Verbal" in texto and "Numérica" in texto and "Abstracta" in texto)
    comprobar("[5] Los 3 niveles técnicos distintos aparecen (Bajo/Medio/Alto)",
              "Bajo (clasificación técnica)" in texto and "Medio (clasificación técnica)" in texto
              and "Alto (clasificación técnica)" in texto)
    comprobar("[5] El origen 'Baremo + Regla de interpretación' aparece para Numérica",
              "Baremo + Regla de interpretación" in texto)
    comprobar("[5] Aparecen EXACTAMENTE 2 líneas de 'regla activada' (Verbal y Numérica; Abstracta NO)",
              texto.count("regla activada:") == 2, f"apareció {texto.count('regla activada:')} veces")
    comprobar("[5] El texto propio de la regla técnica se refleja en el informe",
              "fuerza revisión técnica" in texto)
    comprobar("[5] La conclusión configurada por baremo (fuente 'B') se refleja, marcada como no clínica",
              "sin valor clínico" in texto.lower())
    comprobar("[5] El informe no atribuye ningún contenido a un instrumento comercial (auto-declarado técnico interno)",
              "técnica interna" in texto.lower() or "TÉCNICA INTERNA" in texto)

    # ==================================================================
    print("\n5 · STORAGE + VERSIONADO/REEMISIÓN + HISTORIAL")
    fila_v1 = sql_uno(
        "select v.storage_key, v.tamano_bytes, v.checksum_sha256, v.mime_type, v.motivo_version, i.id as informe_id "
        "from edu_informe_versiones v join edu_informes i on i.id = v.informe_id "
        "where i.inscripcion_id=:i and v.numero_version=1", i=insc_multi)
    comprobar("[6] Tamaño almacenado == tamaño real descargado", fila_v1[1] == len(contenido))
    comprobar("[6] Checksum SHA-256 almacenado == checksum real", fila_v1[2] == hashlib.sha256(contenido).hexdigest())
    comprobar("[6] mime_type es application/pdf", fila_v1[3] == "application/pdf")
    comprobar("[6] storage_key aislada por institución e informe", fila_v1[0].startswith(f"instituciones/{inst_a}/informes/"), fila_v1[0])
    comprobar("[6] v1 se registró como 'Emisión inicial'", fila_v1[4] == "Emisión inicial")

    reemision = exigir(requests.post(f"{API}/educativo/inscripciones/{insc_multi}/informe/reemitir",
                                     json={"motivo": "Verificación técnica de versionado (prueba interna)"},
                                     headers=h_a, timeout=30), 200, "Reemitir")
    meta = requests.get(f"{API}/educativo/inscripciones/{insc_multi}/informe", headers=h_a, timeout=30).json()
    comprobar("[6] Tras reemitir quedan exactamente 2 versiones", len(meta["versiones"]) == 2)
    comprobar("[6] version_actual pasó a 2", meta["version_actual"] == 2)
    v1_meta = next(v for v in meta["versiones"] if v["numero_version"] == 1)
    v2_meta = next(v for v in meta["versiones"] if v["numero_version"] == 2)
    comprobar("[6] Cada versión tiene su propio checksum", v1_meta["checksum_sha256"] != v2_meta["checksum_sha256"])
    comprobar("[6] v2 conserva el motivo de la reemisión", v2_meta["motivo_version"] == "Verificación técnica de versionado (prueba interna)")

    from core.storage import obtener_storage_service
    comprobar("[6] La v1 sigue existiendo físicamente en storage tras reemitir (no se sobreescribió)",
              obtener_storage_service().existe(fila_v1[0]))
    comprobar("[6] reemitir() no cambió informe_id", reemision["informe_id"] == fila_v1[5])

    # ==================================================================
    print("\n6 · AISLAMIENTO MULTI-TENANT")
    aciertos_b = {
        "Verbal": [True, True, True, False, False],
        "Numérica": [True, False, False, False, False],
        "Abstracta": [True, False, False, False, False],
    }
    tok_b, insc_b, _ = aplicar_aptitud(h_b, inst_b, sello, "CasoB", prueba_id, preg_por_dim, edad=12, aciertos_por_dim=aciertos_b, headers_campana=h_super)
    esperar_informe(h_b, insc_b)

    r_cruce_pdf = requests.get(f"{API}/educativo/inscripciones/{insc_multi}/informe-pdf", headers=h_b, timeout=30)
    comprobar("[7] B NO puede descargar el informe de A (403)", r_cruce_pdf.status_code == 403)
    r_cruce_meta = requests.get(f"{API}/educativo/inscripciones/{insc_multi}/informe", headers=h_b, timeout=30)
    comprobar("[7] B NO puede ver la metadata del informe de A (403)", r_cruce_meta.status_code == 403)
    r_cruce_inverso = requests.get(f"{API}/educativo/inscripciones/{insc_b}/informe-pdf", headers=h_a, timeout=30)
    comprobar("[7] A tampoco puede descargar el informe de B (403)", r_cruce_inverso.status_code == 403)

    r_publica_ver_b = requests.get(f"{API}/educativo/pruebas/{prueba_id}/reglas", headers=h_b, timeout=30)
    comprobar("[7] Cualquier institución puede LEER las reglas del catálogo público", r_publica_ver_b.status_code == 200)
    r_publica_crear_b = requests.post(f"{API}/educativo/pruebas/{prueba_id}/reglas", json={
        "ambito": "dimension", "dimension_id": dim_id_por_nombre["Verbal"], "operador": ">", "valor_comparacion": 0},
        headers=h_b, timeout=30)
    comprobar("[7] Pero SOLO superadmin puede escribir en el catálogo público (403 para B)", r_publica_crear_b.status_code == 403)
    r_publica_baremo_b = requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_id_por_nombre["Verbal"], "puntaje_minimo": 0, "puntaje_maximo": 5, "nivel": "x"},
        headers=h_b, timeout=30)
    comprobar("[7] B tampoco puede crear baremos en el catálogo público (403)", r_publica_baremo_b.status_code == 403)

    # ==================================================================
    print("\n6b · VISIBILIDAD PARA CLIENTES (PUNTO 3) — la prueba técnica queda oculta")
    catalogo_a = exigir(requests.get(f"{API}/educativo/pruebas/", headers=h_a, timeout=30), 200, "Catálogo de A")
    comprobar("[3] La institución A NO ve la prueba técnica en su catálogo (GET /pruebas/)",
              prueba_id not in {p["id"] for p in catalogo_a})
    catalogo_super = exigir(requests.get(f"{API}/educativo/pruebas/", headers=h_super, timeout=30), 200, "Catálogo de superadmin")
    comprobar("[3] Superadmin SÍ la ve en el catálogo", prueba_id in {p["id"] for p in catalogo_super})

    r_campana_bloqueada = requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} NoDebeCrearse {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30)
    comprobar("[3] Una institución (no superadmin) NO puede crear una campaña con la prueba técnica (404)",
              r_campana_bloqueada.status_code == 404, f"status {r_campana_bloqueada.status_code}: {r_campana_bloqueada.text[:200]}")
    comprobar("[3] No se creó ninguna campaña con ese nombre",
              sql_uno(f"select count(*) from edu_evaluaciones where nombre_grupo = '{PREFIJO} NoDebeCrearse {sello}'")[0] == 0)

    r_campana_super_ok = requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} SuperadminSiPuede {sello}", "institucion_id": inst_a},
        headers=h_super, timeout=30)
    comprobar("[3] Superadmin SÍ puede crear una campaña con la prueba técnica (200)", r_campana_super_ok.status_code == 200)

    # ==================================================================
    print("\n7 · REGRESIÓN LIGERA — likert_suma (PHQ-9) sigue funcionando exactamente igual")
    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")
    if phq9_id:
        detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id[0]}/completa", headers=h_a, timeout=30), 200, "Detalle PHQ-9")
        preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}
        campana_phq9 = exigir(requests.post(f"{API}/educativo/campanas/", json={
            "prueba_id": phq9_id[0], "nombre_grupo": f"{PREFIJO} RegresionPHQ9 {sello}", "institucion_id": inst_a},
            headers=h_a, timeout=30), 200, "Campaña PHQ-9 regresión")
        persona_phq9 = crear_persona_con_consentimiento(h_a, inst_a, sello, "RegresionPHQ9")
        tok_phq9 = matricular(h_a, campana_phq9["id"], persona_phq9)
        exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_phq9}", json={
            "nombre_completo": "Alumno RegresionPHQ9", "edad": 16, "sexo": "Femenino",
            "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar PHQ-9 regresión")

        def opcion_id(orden, valor):
            return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

        valores_phq9 = [2, 1, 0, 1, 0, 0, 1, 0, 0]  # total = 5, tramo "Leve", sin alerta
        respuestas_phq9 = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)} for i, v in enumerate(valores_phq9)]
        exigir(requests.post(f"{API}/educativo/examen/{tok_phq9}/guardar", json={"respuestas": respuestas_phq9}, timeout=30), 200, "Guardar PHQ-9 regresión")
        exigir(requests.post(f"{API}/educativo/examen/{tok_phq9}/finalizar", timeout=60), 200, "Finalizar PHQ-9 regresión")
        insc_phq9 = sql_uno("select id from edu_inscripciones where token=:t", t=tok_phq9)[0]
        puntaje_phq9 = sql_uno("select puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i", i=insc_phq9)
        comprobar("[8] PHQ-9 (likert_suma) sigue sumando exactamente igual que antes de esta fase: total = 5",
                  float(puntaje_phq9[0]) == 5.0, str(puntaje_phq9))
        # No asumimos qué texto/tramo tiene el catálogo PHQ-9 en vivo (puede
        # ser distinto del que carga seed_phq9.py si ya existía una fila
        # anterior — el seed es idempotente y nunca la sobrescribe). Lo único
        # que esta regresión debe probar es que el motor sigue interpretando
        # el puntaje contra EL BAREMO REAL exactamente igual que antes de
        # introducir correcto_incorrecto, no un valor de nivel hardcodeado.
        baremo_esperado_phq9 = sql_uno(
            "select nivel, es_alerta from edu_baremos where dimension_id = "
            "(select dimension_id from edu_resultados_dimensiones where inscripcion_id=:i) "
            "and puntaje_minimo <= 5 and puntaje_maximo >= 5", i=insc_phq9)
        diag_phq9 = sql_uno("select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_phq9)
        comprobar("[8] PHQ-9 interpreta el puntaje 5 contra el baremo REAL en vigor, sin verse afectado "
                  "por el nuevo modo correcto_incorrecto (el likert_suma de siempre)",
                  diag_phq9[0] == baremo_esperado_phq9[0] and diag_phq9[1] == bool(baremo_esperado_phq9[1]),
                  f"diag={diag_phq9} baremo_real={baremo_esperado_phq9}")
    else:
        comprobar("[8] PHQ-9 público no encontrado — se omite la regresión ligera en este entorno (correr seed_phq9.py)", False)

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
        c.execute(text(f"delete from consentimientos_informados where persona_id in "
                       f"(select id from personas where nombres like '{PREFIJO}%')"))
        c.execute(text(f"delete from personas where nombres like '{PREFIJO}%'"))
        c.execute(text(f"delete from auth_usuarios where email like '{PREFIJO.lower()}%'"))
        c.execute(text(f"delete from instituciones where nombre like '{PREFIJO}%'"))
    print(f"🧹 Datos de prueba {PREFIJO} eliminados. (La prueba técnica pública '{NOMBRE_TECNICO_PRUEBA}' "
          "NO se borra: es catálogo público reutilizable, igual que PHQ-9.)")


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
