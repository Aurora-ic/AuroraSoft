"""Verificación end-to-end — Reglas de interpretación genéricas (item/dimensión/puntaje total).

Cubre los 7 casos obligatorios de la fase:

  A · PHQ-9, puntaje bajo + ítem 9 SIN disparar -> resultado normal, sin alerta
  B · PHQ-9, puntaje bajo + ítem 9 positivo     -> requiere_revision por regla
  C · PHQ-9, puntaje alto + ítem 9 negativo     -> alerta por baremo (no por regla)
  D · PHQ-9, puntaje alto + ítem 9 positivo     -> una sola alerta, ambos orígenes trazados
  E · Otra prueba sin reglas                    -> funciona exactamente como antes
  F · Regla configurada incorrectamente         -> nunca se traduce en "sin riesgo"
  G · Aislamiento entre instituciones           -> las reglas de A no afectan a B

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_reglas_interpretacion_e2e.py
    python tests/verificar_reglas_interpretacion_e2e.py --limpiar
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

PREFIJO = "ZZREGLA"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []



def completar_restantes(token):
    """🔧 (sesión 2026-11-07, mismo ajuste que verificar_informe_phq9_e2e del
    2026-11-02) El backend exige responder TODAS las preguntas antes de
    finalizar; este test arma a mano solo las puntuables (ítems 1-9 del
    PHQ-9). Responde con la primera opción lo que falte — hoy, el ítem 10
    informativo, que no puntúa — para no alterar el puntaje verificado."""
    progreso = requests.get(f"{API}/educativo/examen/{token}/progreso", timeout=30).json()
    hechas = {r["pregunta_id"] for r in progreso.get("respuestas", [])}
    preguntas = requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30).json()
    faltan = [{"pregunta_id": p["id"], "opcion_id": p["opciones"][0]["id"]}
              for p in preguntas if p["id"] not in hechas and p.get("opciones")]
    if faltan:
        r = requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": faltan}, timeout=30)
        assert r.status_code == 200, f"Completar ítems restantes: {r.status_code} {r.text[:200]}"

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


def aplicar_phq9(headers, inst_id, sello, etiqueta, preg_phq9, phq9_id, valores):
    """Crea campaña + persona + consentimiento + matrícula + responde y finaliza el PHQ-9.
    `valores` son 9 enteros 0-3, uno por ítem en orden. Devuelve (token, inscripcion_id)."""
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona_id = crear_persona_con_consentimiento(headers, inst_id, sello, etiqueta)
    token = matricular(headers, campana["id"], persona_id)

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": 16, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, v)} for i, v in enumerate(valores)]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")

    completar_restantes(token)

    r = requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60)
    exigir(r, 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token)
    return token, insc[0]


def crear_prueba_simple(headers, sello, sufijo, n_items=1):
    """Prueba de N ítems, 1 dimensión, con un baremo que SÍ alerta en el tramo alto. Sin ninguna regla."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sufijo}-{sello}", "nombre_publico": f"Prueba {sufijo}",
        "escala_minima": 0, "escala_maxima": 1}, headers=headers, timeout=30), 200, f"Prueba {sufijo}")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    preguntas_carga = [
        {"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D", "opciones": opciones}
        for i in range(1, n_items + 1)
    ]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}], "preguntas": preguntas_carga},
        headers=headers, timeout=30), 200, f"Carga {sufijo}")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=headers, timeout=30), 200, f"Detalle {sufijo}")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 0, "nivel": "Normal", "es_alerta": False},
        headers=headers, timeout=30), 200, f"Baremo bajo {sufijo}")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 1, "puntaje_maximo": n_items, "nivel": "Alto", "es_alerta": True},
        headers=headers, timeout=30), 200, f"Baremo alto {sufijo}")
    return prueba["id"], dim["id"], pregs


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    # ==================================================================
    print("\n0 · Montaje: dos instituciones + localizar el PHQ-9 público y su regla de ítem 9")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "auroraintegratedconsulting@gmail.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a, h_a = crear_colegio(h_super, "A", sello)
    inst_b, h_b = crear_colegio(h_super, "B", sello)

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]
    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_a, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for d in detalle_phq9["dimensiones"] for p in d["preguntas"]}
    comprobar("[0] El PHQ-9 público trae al menos 1 regla de interpretación (ítem 9)", len(detalle_phq9["reglas"]) >= 1)
    regla_item9 = detalle_phq9["reglas"][0]
    comprobar("[0] La regla es de ámbito 'item', operador '>' 0", regla_item9["ambito"] == "item" and regla_item9["operador"] == ">" and regla_item9["valor_comparacion"] == 0)

    # ==================================================================
    print("\nCASO A · Puntaje bajo + ítem 9 SIN disparar -> resultado normal")
    tok_a, insc_a = aplicar_phq9(h_a, inst_a, sello, "CasoA", preg_phq9, phq9_id, [0, 0, 0, 0, 0, 0, 0, 0, 0])
    diag_a = sql_uno("select es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_a)
    estado_a = sql_uno("select resultado_visible_alumno, informe_liberado, reglas_con_error from edu_inscripciones where id=:i", i=insc_a)
    comprobar("[A] Sin alerta", diag_a[0] is False, f"alerta_por={diag_a[1]!r}")
    comprobar("[A] Resultado visible/liberado con normalidad", estado_a[0] is True and estado_a[1] is True)
    comprobar("[A] Sin reglas con error", estado_a[2] is None)

    # ==================================================================
    # 🔧 (sesión 2026-11-08) Desde el 2026-11-02 el PHQ-9 tiene 3 dimensiones
    # y un diagnóstico por cada una: Afectivo-Cognitiva (ítems 1,2,6,7,9),
    # Somática/Vegetativa (3,4,5,8) y el total "Depresión" (suma de ambas, la
    # única con tramos de alerta). La regla del ítem 9 se aplica a la dimensión
    # que contiene ese ítem (crud.evaluar_reglas_interpretacion); el baremo de
    # alerta, al total. Antes este test leía "el" diagnóstico (uno cualquiera).
    def diagnosticos_por_rol(insc_id):
        """{'item9': fila, 'total': fila, 'otra': fila} con (es_alerta, alerta_por, regla_activada_id)."""
        with MOTOR.connect() as c:
            filas = c.execute(text(
                "select d.es_alerta, d.alerta_por, d.regla_activada_id, d.dimension_id, dim.tipo_calculo "
                "from edu_diagnosticos_alumno d join edu_dimensiones dim on dim.id = d.dimension_id "
                "where d.inscripcion_id = :i"), {"i": insc_id}).fetchall()
            dim_item9 = c.execute(text(
                "select dimension_id from edu_preguntas where prueba_id = :p and orden = 9"), {"p": phq9_id}).scalar()
        roles = {}
        for es_alerta, alerta_por, regla_id, dim_id, tipo in filas:
            rol = "total" if tipo == "suma_de_dimensiones" else ("item9" if dim_id == dim_item9 else "otra")
            roles.setdefault(rol, []).append((es_alerta, alerta_por, regla_id))
        return len(filas), {k: v[0] for k, v in roles.items() if len(v) == 1}, roles

    print("\nCASO B · Puntaje bajo + ítem 9 positivo -> requiere_revision por regla")
    # Total = 1 (solo el ítem 9 en 1) -> tramo 0-4, SIN alerta por baremo.
    tok_b, insc_b = aplicar_phq9(h_a, inst_a, sello, "CasoB", preg_phq9, phq9_id, [0, 0, 0, 0, 0, 0, 0, 0, 1])
    n_b, d_b, _ = diagnosticos_por_rol(insc_b)
    estado_b = sql_uno("select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc_b)
    comprobar("[B] Un diagnóstico por dimensión (3)", n_b == 3 and set(d_b) == {"item9", "otra", "total"}, str(d_b))
    comprobar("[B] La dimensión del ítem 9 queda en alerta POR LA REGLA",
              d_b.get("item9", (None,))[0] is True and d_b["item9"][1] == "regla", str(d_b.get("item9")))
    comprobar("[B] regla_activada_id apunta a la regla del ítem 9", d_b.get("item9", (0, 0, None))[2] == regla_item9["id"])
    comprobar("[B] El total NO alerta por baremo (puntaje 1, tramo mínimo)",
              d_b.get("total", (None,))[0] is False and d_b["total"][1] is None, str(d_b.get("total")))
    comprobar("[B] La otra dimensión sigue sin alerta", d_b.get("otra", (None,))[0] is False, str(d_b.get("otra")))
    comprobar("[B] El informe queda retenido (requiere_revision)", estado_b[0] is False and estado_b[1] is False)

    # ==================================================================
    print("\nCASO C · Puntaje alto + ítem 9 negativo -> alerta por baremo, no por regla")
    # 8 ítems en 3 (=24) + ítem 9 en 0 -> total 24 -> tramo alto, CON alerta de baremo.
    tok_c, insc_c = aplicar_phq9(h_a, inst_a, sello, "CasoC", preg_phq9, phq9_id, [3, 3, 3, 3, 3, 3, 3, 3, 0])
    n_c, d_c, roles_c = diagnosticos_por_rol(insc_c)
    estado_c = sql_uno("select resultado_visible_alumno, informe_liberado from edu_inscripciones where id=:i", i=insc_c)
    comprobar("[C] El total alerta POR BAREMO", d_c.get("total", (None,))[0] is True and d_c["total"][1] == "baremo",
              str(d_c.get("total")))
    comprobar("[C] Ningún diagnóstico registra la regla (el ítem 9 NO disparó)",
              all("regla" not in (f[1] or "") and f[2] is None for filas in roles_c.values() for f in filas), str(roles_c))
    comprobar("[C] El informe queda retenido", estado_c[0] is False and estado_c[1] is False)

    # ==================================================================
    print("\nCASO D · Puntaje alto + ítem 9 positivo -> ambos orígenes trazados, sin filas duplicadas")
    tok_d, insc_d = aplicar_phq9(h_a, inst_a, sello, "CasoD", preg_phq9, phq9_id, [3, 3, 3, 3, 3, 3, 3, 3, 3])
    n_d, d_d, _ = diagnosticos_por_rol(insc_d)
    comprobar("[D] Exactamente UN diagnóstico por dimensión (3, sin duplicación)",
              n_d == 3 and set(d_d) == {"item9", "otra", "total"}, f"{n_d} filas: {d_d}")
    comprobar("[D] El total alerta por baremo", d_d.get("total", (None,))[0] is True and "baremo" in (d_d["total"][1] or ""),
              str(d_d.get("total")))
    comprobar("[D] La dimensión del ítem 9 alerta por la regla, con regla_activada_id",
              d_d.get("item9", (None,))[0] is True and "regla" in (d_d["item9"][1] or "")
              and d_d["item9"][2] == regla_item9["id"], str(d_d.get("item9")))

    # ==================================================================
    print("\nCASO E · Otra prueba SIN reglas -> funciona exactamente como antes")
    prueba_e, dim_e, preg_e = crear_prueba_simple(h_a, sello, "E")
    campana_e = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_e, "nombre_grupo": f"{PREFIJO} CasoE {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña E")
    persona_e = crear_persona_con_consentimiento(h_a, inst_a, sello, "CasoE")
    tok_e = matricular(h_a, campana_e["id"], persona_e)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_e}", json={
        "nombre_completo": "Alumno E", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar E")
    op_alerta = next(o["id"] for o in preg_e[1]["opciones"] if o["valor_puntuacion"] == 1)
    exigir(requests.post(f"{API}/educativo/examen/{tok_e}/guardar",
                         json={"respuestas": [{"pregunta_id": preg_e[1]["id"], "opcion_id": op_alerta}]}, timeout=30), 200, "Guardar E")
    completar_restantes(tok_e)
    exigir(requests.post(f"{API}/educativo/examen/{tok_e}/finalizar", timeout=60), 200, "Finalizar E")
    insc_e = sql_uno("select id from edu_inscripciones where token=:t", t=tok_e)[0]
    diag_e = sql_uno("select es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_e)
    comprobar("[E] El baremo sigue alertando exactamente igual que antes de esta fase", diag_e[0] is True and diag_e[1] == "baremo")
    reglas_e = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_e}/reglas", headers=h_a, timeout=30), 200, "Reglas de E")
    comprobar("[E] Esta prueba no tiene ninguna regla configurada", reglas_e == [])

    # ==================================================================
    print("\nCASO F · Regla configurada incorrectamente -> nunca se traduce en 'sin riesgo'")
    # Prueba de 2 ítems; la regla apunta al ítem 2, pero el alumno de este
    # caso NUNCA llega a responderlo (solo el 1) — una config perfectamente
    # válida en sí misma (el endpoint la acepta) que resulta inevaluable para
    # ESTA aplicación concreta, el mismo tipo de "hueco" que dimensiones_sin_baremo
    # cubre para los baremos.
    prueba_f, dim_f, preg_f = crear_prueba_simple(h_a, sello, "F", n_items=2)
    regla_f = exigir(requests.post(f"{API}/educativo/pruebas/{prueba_f}/reglas", json={
        "ambito": "item", "pregunta_id": preg_f[2]["id"], "operador": ">", "valor_comparacion": 0,
        "descripcion": "Regla sobre un ítem que este alumno no respondió"},
        headers=h_a, timeout=30), 200, "Crear regla F")

    campana_f = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_f, "nombre_grupo": f"{PREFIJO} CasoF {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña F")
    persona_f = crear_persona_con_consentimiento(h_a, inst_a, sello, "CasoF")
    tok_f = matricular(h_a, campana_f["id"], persona_f)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_f}", json={
        "nombre_completo": "Alumno F", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar F")
    op_bajo = next(o["id"] for o in preg_f[1]["opciones"] if o["valor_puntuacion"] == 0)
    # Solo se responde el ítem 1 — el ítem 2 (el que la regla necesita) queda sin respuesta.
    exigir(requests.post(f"{API}/educativo/examen/{tok_f}/guardar",
                         json={"respuestas": [{"pregunta_id": preg_f[1]["id"], "opcion_id": op_bajo}]}, timeout=30), 200, "Guardar F")
    # 🔧 (sesión 2026-11-08) Desde el 2026-11-02 el backend NO deja finalizar
    # con preguntas sin responder: el hueco "regla sobre un ítem no respondido"
    # ya no llega al motor. Lo que se comprueba aquí es ese candado; la regla
    # inevaluable que SÍ llega al motor (reglas_con_error, nunca 'sin riesgo')
    # la cubre el caso F2, justo debajo.
    r_fin_f = requests.post(f"{API}/educativo/examen/{tok_f}/finalizar", timeout=60)
    comprobar("[F] No se puede finalizar con el ítem de la regla sin responder (400)",
              r_fin_f.status_code == 400 and "sin responder" in r_fin_f.text, f"{r_fin_f.status_code} {r_fin_f.text[:150]}")
    insc_f = sql_uno("select id, estado from edu_inscripciones where token=:t", t=tok_f)
    comprobar("[F] La inscripción NO queda finalizada (no se convirtió en 'sin riesgo')", insc_f[1] != "Finalizado", str(insc_f[1]))
    n_diag_f = sql_uno("select count(*) from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_f[0])[0]
    comprobar("[F] Ningún diagnóstico emitido", n_diag_f == 0, str(n_diag_f))

    # F2 · Una regla que SÍ llega al motor y no se puede evaluar: regla de
    # ámbito 'dimension' sobre una dimensión SIN ítems (sin puntaje
    # calculado). El examen se finaliza completo; la regla falla y eso tiene
    # que traducirse en informe RETENIDO + reglas_con_error, nunca en "sin riesgo".
    prueba_f2 = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-F2-{sello}", "nombre_publico": "Prueba F2",
        "escala_minima": 0, "escala_maxima": 1}, headers=h_a, timeout=30), 200, "Prueba F2")["id"]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_f2, "dimensiones": [{"nombre": "D"}, {"nombre": "Sin items"}],
        "preguntas": [{"texto_pregunta": "Ítem 1", "orden": 1, "nombre_dimension": "D",
                       "opciones": [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]}]},
        headers=h_a, timeout=30), 200, "Carga F2")
    det_f2 = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_f2}/completa", headers=h_a, timeout=30), 200, "Detalle F2")
    dim_d = next(d for d in det_f2["dimensiones"] if d["nombre"] == "D")
    dim_vacia = next(d for d in det_f2["dimensiones"] if d["nombre"] == "Sin items")
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_d["id"], "puntaje_minimo": 0, "puntaje_maximo": 1, "nivel": "Normal", "es_alerta": False},
        headers=h_a, timeout=30), 200, "Baremo F2")
    regla_f2 = exigir(requests.post(f"{API}/educativo/pruebas/{prueba_f2}/reglas", json={
        "ambito": "dimension", "dimension_id": dim_vacia["id"], "operador": ">", "valor_comparacion": 0,
        "descripcion": "Regla sobre una dimensión sin ítems"}, headers=h_a, timeout=30), 200, "Regla F2")
    campana_f2 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_f2, "nombre_grupo": f"{PREFIJO} CasoF2 {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña F2")
    tok_f2 = matricular(h_a, campana_f2["id"], crear_persona_con_consentimiento(h_a, inst_a, sello, "CasoF2"))
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_f2}", json={
        "nombre_completo": "Alumno F2", "edad": 15, "poblacion": "Secundaria", "acepta_terminos": True},
        timeout=30), 200, "Comenzar F2")
    op_no = dim_d["preguntas"][0]["opciones"][0]["id"]
    exigir(requests.post(f"{API}/educativo/examen/{tok_f2}/guardar", json={"respuestas": [
        {"pregunta_id": dim_d["preguntas"][0]["id"], "opcion_id": op_no}]}, timeout=30), 200, "Guardar F2")
    exigir(requests.post(f"{API}/educativo/examen/{tok_f2}/finalizar", timeout=60), 200, "Finalizar F2")
    estado_f2 = sql_uno("select resultado_visible_alumno, informe_liberado, reglas_con_error, id "
                        "from edu_inscripciones where token=:t", t=tok_f2)
    alerta_f2 = sql_uno("select bool_or(es_alerta) from edu_diagnosticos_alumno where inscripcion_id=:i", i=estado_f2[3])[0]
    comprobar("[F2] El baremo por sí solo NO habría alertado", alerta_f2 is not True, str(alerta_f2))
    comprobar("[F2] Aun así, el informe queda RETENIDO por la regla inevaluable",
              estado_f2[0] is False and estado_f2[1] is False, str(estado_f2[:2]))
    comprobar("[F2] reglas_con_error queda registrado, mencionando la regla concreta",
              estado_f2[2] is not None and f"Regla #{regla_f2['id']}" in estado_f2[2], str(estado_f2[2]))

    # ==================================================================
    print("\nCASO G · Aislamiento entre instituciones")
    prueba_ga, dim_ga, preg_ga = crear_prueba_simple(h_a, sello, "GA")
    prueba_gb, dim_gb, preg_gb = crear_prueba_simple(h_b, sello, "GB")

    # A configura una regla propia en SU prueba (ámbito dimensión, puntaje>=0 -> siempre dispara)
    regla_a = exigir(requests.post(f"{API}/educativo/pruebas/{prueba_ga}/reglas", json={
        "ambito": "dimension", "dimension_id": dim_ga, "operador": ">=", "valor_comparacion": 0,
        "descripcion": "Regla de prueba del colegio A"}, headers=h_a, timeout=30), 200, "Crear regla A")
    comprobar("[G] A puede crear una regla en su propia prueba", regla_a["prueba_id"] == prueba_ga)

    r_cross_crear = requests.post(f"{API}/educativo/pruebas/{prueba_ga}/reglas", json={
        "ambito": "dimension", "dimension_id": dim_ga, "operador": ">=", "valor_comparacion": 0}, headers=h_b, timeout=30)
    comprobar("[G] B NO puede crear una regla en la prueba de A (403)", r_cross_crear.status_code == 403, f"status {r_cross_crear.status_code}")

    r_cross_ver = requests.get(f"{API}/educativo/pruebas/{prueba_ga}/reglas", headers=h_b, timeout=30)
    comprobar("[G] B NO puede LISTAR las reglas de la prueba de A (403)", r_cross_ver.status_code == 403, f"status {r_cross_ver.status_code}")

    # B aplica su PROPIA prueba (sin ninguna regla) y su alumno con puntaje bajo NO debe verse afectado por la regla de A
    campana_gb = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_gb, "nombre_grupo": f"{PREFIJO} CasoG {sello}", "institucion_id": inst_b},
        headers=h_b, timeout=30), 200, "Campaña GB")
    persona_gb = crear_persona_con_consentimiento(h_b, inst_b, sello, "CasoGB")
    tok_gb = matricular(h_b, campana_gb["id"], persona_gb)
    exigir(requests.post(f"{API}/educativo/comenzar-test/{tok_gb}", json={
        "nombre_completo": "Alumno GB", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar GB")
    op_bajo_gb = next(o["id"] for o in preg_gb[1]["opciones"] if o["valor_puntuacion"] == 0)
    exigir(requests.post(f"{API}/educativo/examen/{tok_gb}/guardar",
                         json={"respuestas": [{"pregunta_id": preg_gb[1]["id"], "opcion_id": op_bajo_gb}]}, timeout=30), 200, "Guardar GB")
    completar_restantes(tok_gb)
    exigir(requests.post(f"{API}/educativo/examen/{tok_gb}/finalizar", timeout=60), 200, "Finalizar GB")
    insc_gb = sql_uno("select id from edu_inscripciones where token=:t", t=tok_gb)[0]
    diag_gb = sql_uno("select es_alerta, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_gb)
    comprobar("[G] La regla del colegio A NO afectó al alumno de B (sin alerta, mismo baremo 'Normal')",
              diag_gb[0] is False and diag_gb[1] is None)

    # Regla en la PRUEBA PÚBLICA (PHQ-9) es compartida a propósito — eso NO es
    # una fuga de aislamiento: es del catálogo público, igual que sus baremos.
    r_publica_ver = requests.get(f"{API}/educativo/pruebas/{phq9_id}/reglas", headers=h_b, timeout=30)
    comprobar("[G] Cualquier institución puede LEER las reglas del catálogo público (no es privado)", r_publica_ver.status_code == 200)
    r_publica_crear = requests.post(f"{API}/educativo/pruebas/{phq9_id}/reglas", json={
        "ambito": "item", "pregunta_id": preg_phq9[1]["id"], "operador": ">", "valor_comparacion": 0}, headers=h_b, timeout=30)
    comprobar("[G] Pero SOLO superadmin puede escribir reglas en el catálogo público (403 para B)", r_publica_crear.status_code == 403)

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
            delete from edu_reglas_interpretacion where prueba_id in (
                select id from edu_pruebas where nombre_tecnico like '{PREFIJO}%')"""))
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
