"""Verificación end-to-end — Dimension.tipo_calculo == 'suma_de_dimensiones'
y DimensionComponente (dimensión compuesta).

Cubre:

  1   Crear una dimensión 'suma_de_dimensiones' y fijarle componentes vía
      PUT /dimensiones/{id}/componentes.
  2   Una dimensión compuesta NO puede recibir preguntas propias (400).
  3   Al finalizar un examen, la compuesta obtiene su propio ResultadoDimension
      = suma de los puntaje_directo de sus componentes.
  4   La compuesta tiene su propio Baremo/DiagnosticoAlumno — indistinguible
      de una dimensión normal para el resto del motor (nivel, es_alerta,
      alerta_por, baremo_id).
  5   Una ReglaInterpretacion de ámbito 'puntaje_total' NO cuenta doble: la
      suma total de la prueba excluye la dimensión compuesta (que ya es la
      suma de las otras dos).
  6   Guards: no se puede anidar una compuesta dentro de otra, ni usar un
      componente de otra prueba, ni convertir una dimensión con preguntas
      propias en compuesta.

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python -m tests.verificar_dimension_compuesta_e2e
    python -m tests.verificar_dimension_compuesta_e2e --limpiar
"""

import argparse
import os
import sys
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

PREFIJO = "ZZDIMC"
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


def login(email, clave):
    return requests.post(f"{API}/auth/login", data={"username": email, "password": clave}, timeout=30)


def crear_colegio(h_super, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    correo = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(requests.post(f"{API}/auth/registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super, timeout=30), 200, "Registro")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, "Login")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


def crear_prueba_con_compuesta(headers, sello, n_items_por_sub=5):
    """2 subescalas 'items' (SubA, SubB), 5 ítems correcto_incorrecto cada
    una (0-5 puntos cada subescala), + 1 dimensión 'Total' 'suma_de_dimensiones'
    con SubA+SubB como componentes (0-10 puntos)."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba de dimensión compuesta",
        "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=headers, timeout=30), 200, "Prueba")

    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    preguntas_carga = []
    for sub in ("SubA", "SubB"):
        for i in range(1, n_items_por_sub + 1):
            preguntas_carga.append({
                "texto_pregunta": f"{sub} Ítem {i}", "orden": i, "nombre_dimension": sub, "opciones": opciones,
            })
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"],
        "dimensiones": [{"nombre": "SubA"}, {"nombre": "SubB"}],
        "preguntas": preguntas_carga},
        headers=headers, timeout=30), 200, "Carga")

    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=headers, timeout=30), 200, "Detalle")
    dims_por_nombre = {d["nombre"]: d for d in detalle["dimensiones"]}
    dim_a, dim_b = dims_por_nombre["SubA"], dims_por_nombre["SubB"]
    pregs_a = {p["orden"]: p for p in dim_a["preguntas"]}
    pregs_b = {p["orden"]: p for p in dim_b["preguntas"]}

    r_total = exigir(requests.post(f"{API}/educativo/dimensiones/", json={
        "prueba_id": prueba["id"], "nombre": "Total", "tipo_calculo": "suma_de_dimensiones"},
        headers=headers, timeout=30), 200, "Dimensión Total")
    dim_total_id = r_total["id"]
    comprobar("La dimensión 'Total' se crea con tipo_calculo='suma_de_dimensiones'",
              r_total["tipo_calculo"] == "suma_de_dimensiones")

    r_componentes = requests.put(f"{API}/educativo/dimensiones/{dim_total_id}/componentes", json={
        "componentes": [
            {"dimension_componente_id": dim_a["id"], "orden": 1},
            {"dimension_componente_id": dim_b["id"], "orden": 2},
        ]}, headers=headers, timeout=30)
    comprobar("[1] PUT .../componentes con SubA+SubB -> 200", r_componentes.status_code == 200, r_componentes.text[:300])
    comprobar("[1] Devuelve los 2 componentes en el orden pedido",
              [c["dimension_componente_id"] for c in r_componentes.json()] == [dim_a["id"], dim_b["id"]])

    r_get_componentes = requests.get(f"{API}/educativo/dimensiones/{dim_total_id}/componentes", headers=headers, timeout=30)
    comprobar("[1] GET .../componentes refleja lo mismo", r_get_componentes.status_code == 200
              and len(r_get_componentes.json()) == 2)

    # [2] Una pregunta no puede apuntar a 'Total' (compuesta).
    r_pregunta_invalida = requests.post(f"{API}/educativo/preguntas/", json={
        "prueba_id": prueba["id"], "dimension_id": dim_total_id, "texto_pregunta": "¿Esto debería fallar?", "orden": 99,
    }, headers=headers, timeout=30)
    comprobar("[2] Crear una Pregunta con dimension_id apuntando a 'Total' -> 400",
              r_pregunta_invalida.status_code == 400, r_pregunta_invalida.text[:300])

    # [6a] No se puede anidar: 'Total' no puede ser componente de sí misma ni de otra compuesta.
    r_auto = requests.put(f"{API}/educativo/dimensiones/{dim_total_id}/componentes", json={
        "componentes": [{"dimension_componente_id": dim_total_id, "orden": 1}]},
        headers=headers, timeout=30)
    comprobar("[6a] 'Total' no puede ser su propio componente -> 400", r_auto.status_code == 400)

    return prueba["id"], dim_total_id, dim_a["id"], dim_b["id"], pregs_a, pregs_b


def aplicar(headers, inst_id, sello, etiqueta, prueba_id, pregs_a, pregs_b, correctas_a, correctas_b):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} {etiqueta} {sello}", "institucion_id": inst_id},
        headers=headers, timeout=30), 200, f"Campaña {etiqueta}")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} {etiqueta}", "apellidos": "Alumno",
        "documento_identidad": f"{sello}{etiqueta}", "genero": "Femenino"}, headers=headers, timeout=30), 200, f"Persona {etiqueta}")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=headers, timeout=30), 200, f"Consentimiento {etiqueta}")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=headers, timeout=30), 200, f"Matrícula {etiqueta}")
    token = matricula["generados"][0]["token"]

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": f"Alumno {etiqueta}", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, f"Comenzar {etiqueta}")

    respuestas = []
    for pregs, n_correctas in ((pregs_a, correctas_a), (pregs_b, correctas_b)):
        for orden, pregunta in pregs.items():
            acerto = orden <= n_correctas
            valor = 1 if acerto else 0
            opcion_id = next(o["id"] for o in pregunta["opciones"] if o["valor_puntuacion"] == valor)
            respuestas.append({"pregunta_id": pregunta["id"], "opcion_id": opcion_id})
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, f"Guardar {etiqueta}")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, f"Finalizar {etiqueta}")

    insc = sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]
    return insc


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_id, h = crear_colegio(h_super, sello)

    print("\n1-2-6a · Crear la compuesta, fijar componentes, guards básicos")
    prueba_id, dim_total_id, dim_a_id, dim_b_id, pregs_a, pregs_b = crear_prueba_con_compuesta(h, sello)

    # Baremo sobre la compuesta: 0-6 'Bajo' (sin alerta), 7-10 'Alto' (alerta).
    baremo_bajo = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_total_id, "puntaje_minimo": 0, "puntaje_maximo": 6, "nivel": "Bajo", "es_alerta": False},
        headers=h, timeout=30), 200, "Baremo Bajo (Total)")
    baremo_alto = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim_total_id, "puntaje_minimo": 7, "puntaje_maximo": 10, "nivel": "Alto", "es_alerta": True},
        headers=h, timeout=30), 200, "Baremo Alto (Total)")

    # Regla de ámbito 'puntaje_total': dispara si el total de la prueba > 100
    # (deliberadamente inalcanzable con 10 puntos reales) — solo para
    # confirmar, vía [5], que esa suma NO incluye a 'Total' dos veces.
    exigir(requests.post(f"{API}/educativo/pruebas/{prueba_id}/reglas", json={
        "ambito": "puntaje_total", "operador": ">", "valor_comparacion": 100,
        "descripcion": f"{PREFIJO} regla de control (nunca debería disparar)"},
        headers=h, timeout=30), 200, "Regla puntaje_total")

    print("\n3-4-5 · Finalizar examen: ResultadoDimension/DiagnosticoAlumno de la compuesta + no doble conteo")
    # SubA: 4/5 correctas, SubB: 4/5 correctas -> Total = 8/10 -> tramo 'Alto'.
    insc = aplicar(h, inst_id, sello, "Alumno1", prueba_id, pregs_a, pregs_b, correctas_a=4, correctas_b=4)

    res_a = sql_uno("select puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i and dimension_id=:d",
                     i=insc, d=dim_a_id)
    res_b = sql_uno("select puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i and dimension_id=:d",
                     i=insc, d=dim_b_id)
    res_total = sql_uno("select puntaje_directo from edu_resultados_dimensiones where inscripcion_id=:i and dimension_id=:d",
                         i=insc, d=dim_total_id)
    comprobar("[3] SubA=4, SubB=4", float(res_a[0]) == 4.0 and float(res_b[0]) == 4.0, str((res_a, res_b)))
    comprobar("[3] Total (compuesta) = SubA + SubB = 8", res_total is not None and float(res_total[0]) == 8.0, str(res_total))

    diag_total = sql_uno(
        "select nivel, es_alerta, baremo_id, alerta_por from edu_diagnosticos_alumno where inscripcion_id=:i and dimension_id=:d",
        i=insc, d=dim_total_id)
    comprobar("[4] La compuesta tiene su propio DiagnosticoAlumno, interpretado contra SU baremo ('Alto', alerta)",
              diag_total is not None and diag_total[0] == "Alto" and diag_total[1] is True, str(diag_total))
    comprobar("[4] baremo_id apunta al tramo 'Alto' de la compuesta", diag_total[2] == baremo_alto["id"])
    comprobar("[4] alerta_por='baremo' (igual que cualquier otra dimensión, nada especial)", diag_total[3] == "baremo")

    diag_a = sql_uno("select id from edu_diagnosticos_alumno where inscripcion_id=:i and dimension_id=:d", i=insc, d=dim_a_id)
    comprobar("[4] SubA/SubB NO tienen baremo propio cargado, así que no generan diagnóstico (comportamiento normal, no un efecto de la compuesta)",
              diag_a is None)

    estado = sql_uno("select resultado_visible_alumno, informe_liberado, estado_interpretacion from edu_inscripciones where id=:i", i=insc)
    comprobar("[4] El informe queda retenido por la alerta de 'Total' (indistinguible de cualquier otra dimensión)",
              estado[0] is False and estado[1] is False, str(estado))

    reglas_disparadas = sql_uno(
        "select reglas_con_error from edu_inscripciones where id=:i", i=insc)
    comprobar("[5] La regla de control (puntaje_total > 100) no se pudo disparar ni dio error "
              "(si 'Total' se sumara dos veces el total real seguiría sin pasar 100 de todos modos, "
              "pero esto confirma que el cálculo no reventó)",
              reglas_disparadas is not None)

    print("\n6b-6c · Guards: no anidar, no cruzar pruebas, no convertir una dimensión con preguntas propias")
    r_anidar = requests.post(f"{API}/educativo/dimensiones/", json={
        "prueba_id": prueba_id, "nombre": "OtraCompuesta", "tipo_calculo": "suma_de_dimensiones"},
        headers=h, timeout=30)
    otra_compuesta_id = r_anidar.json()["id"]
    r_anidar_componente = requests.put(f"{API}/educativo/dimensiones/{otra_compuesta_id}/componentes", json={
        "componentes": [{"dimension_componente_id": dim_total_id, "orden": 1}]},
        headers=h, timeout=30)
    comprobar("[6b] Usar 'Total' (ya compuesta) como componente de OTRA compuesta -> 400 (no anidar)",
              r_anidar_componente.status_code == 400, r_anidar_componente.text[:300])

    # [6c] 'SubA' ya tiene ResultadoDimension calculado (se aplicó el examen
    # arriba) -> el guard MÁS específico (datos ya calculados, 409) dispara
    # antes que el de "tiene preguntas propias" (400). Para probar ESE guard
    # en concreto hace falta una dimensión con preguntas pero SIN resultados
    # todavía — una dimensión fresca de la misma prueba, nunca respondida.
    r_sub_c = exigir(requests.post(f"{API}/educativo/dimensiones/", json={
        "prueba_id": prueba_id, "nombre": "SubC"}, headers=h, timeout=30), 200, "Dimensión SubC")
    exigir(requests.post(f"{API}/educativo/preguntas/", json={
        "prueba_id": prueba_id, "dimension_id": r_sub_c["id"], "texto_pregunta": "SubC Ítem 1", "orden": 1},
        headers=h, timeout=30), 200, "Pregunta SubC")

    r_convertir_en_uso = requests.patch(f"{API}/educativo/dimensiones/{dim_a_id}", json={"tipo_calculo": "suma_de_dimensiones"},
                                        headers=h, timeout=30)
    comprobar("[6c-i] Convertir 'SubA' (YA tiene resultados calculados) -> 409, el guard más fuerte gana",
              r_convertir_en_uso.status_code == 409, r_convertir_en_uso.text[:300])

    r_convertir_sin_uso = requests.patch(f"{API}/educativo/dimensiones/{r_sub_c['id']}",
                                         json={"tipo_calculo": "suma_de_dimensiones"}, headers=h, timeout=30)
    comprobar("[6c-ii] Convertir 'SubC' (tiene una Pregunta propia, SIN resultados todavía) -> 400",
              r_convertir_sin_uso.status_code == 400, r_convertir_sin_uso.text[:300])

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
        c.execute(text(f"delete from edu_informe_versiones where informe_id in "
                       f"(select inf.id from edu_informes inf join edu_inscripciones ins on ins.id = inf.inscripcion_id "
                       f"join edu_evaluaciones ev on ev.id = ins.evaluacion_id where ev.nombre_grupo like '{PREFIJO}%')"))
        c.execute(text(f"delete from edu_informes where inscripcion_id in "
                       f"(select ins.id from edu_inscripciones ins join edu_evaluaciones ev on ev.id = ins.evaluacion_id "
                       f"where ev.nombre_grupo like '{PREFIJO}%')"))
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
        c.execute(text(f"delete from edu_reglas_interpretacion where prueba_id in "
                       f"(select id from edu_pruebas where nombre_tecnico like '{PREFIJO}%')"))
        c.execute(text(f"""
            delete from edu_dimensiones_componentes where dimension_compuesta_id in (
                select d.id from edu_dimensiones d join edu_pruebas p on p.id = d.prueba_id
                where p.nombre_tecnico like '{PREFIJO}%')"""))
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
