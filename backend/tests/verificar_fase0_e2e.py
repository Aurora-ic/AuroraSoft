"""Verificación end-to-end del flujo completo tras los arreglos de la Fase 0.

Recorre el camino real de negocio contra el servidor HTTP en marcha:

    crear prueba -> cargar preguntas/opciones -> crear campaña (con fecha_fin)
    -> matricular estudiante -> comenzar examen -> guardar respuestas
    -> finalizar -> calcular resultados -> consultar/generar informe

y comprueba además que los candados de expiración, que hasta ahora eran código
inalcanzable porque `fecha_fin` nunca se guardaba, rechazan de verdad.

Uso:
    uvicorn main:app --port 8010        (en otra terminal)
    python tests/verificar_fase0_e2e.py [--url http://127.0.0.1:8010]
    python tests/verificar_fase0_e2e.py --limpiar     (borra los datos ZZTEST)

Todo lo que crea lleva el prefijo ZZTEST para poder limpiarlo después.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

PREFIJO = "ZZTEST"
API = "http://127.0.0.1:8010/api"

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def cabecera(texto):
    print(f"\n{texto}")


def pedir_con_reintento(metodo, url, contexto, **kwargs):
    """Reintenta ante un 429: /auth/* está limitado a 5 peticiones por minuto
    por IP. El límite es correcto y no se toca; simplemente se espera."""
    for _ in range(6):
        respuesta = metodo(url, timeout=30, **kwargs)
        if respuesta.status_code != 429:
            return respuesta
        print(f"    (429 en {contexto}; esperando 13s a que se abra la ventana)")
        time.sleep(13)
    return respuesta


def exigir(respuesta, esperado, contexto):
    """Aborta con un mensaje legible si un paso intermedio del flujo falla."""
    if respuesta.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {respuesta.status_code}")
        print(f"   {respuesta.text[:500]}")
        sys.exit(1)
    return respuesta.json() if respuesta.text else None


# ======================================================================
def main(url_base):
    global API
    API = url_base.rstrip("/") + "/api"

    sello = datetime.utcnow().strftime("%H%M%S")

    # ------------------------------------------------------------------
    cabecera("0 · Preparación: superadmin, institución y psicólogo")

    pwd_super = os.getenv("SUPERADMIN_PASSWORD")
    email_super = os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com")
    if not pwd_super:
        print("!! Falta SUPERADMIN_PASSWORD en el .env")
        sys.exit(1)

    r = pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login superadmin",
        data={"username": email_super, "password": pwd_super},
    )
    tok_super = exigir(r, 200, "Login del superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    comprobar("Login del superadmin", True)

    inst = exigir(
        requests.post(
            f"{API}/instituciones/",
            json={"nombre": f"{PREFIJO} Colegio {sello}", "tipo": "Colegio"},
            headers=h_super, timeout=30,
        ), 201, "Crear institución",
    )
    inst_id = inst["id"]

    email_psi = f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com"
    exigir(
        pedir_con_reintento(
            requests.post, f"{API}/auth/registro", "registro psicólogo",
            json={
                "email": email_psi, "password": "ClaveDePrueba123",
                "nombre_completo": f"{PREFIJO} Psicologo", "rol": "psicologo",
                "institucion_id": inst_id,
            },
            headers=h_super,
        ), 200, "Registrar psicólogo",
    )

    r = pedir_con_reintento(
        requests.post, f"{API}/auth/login", "login psicólogo",
        data={"username": email_psi, "password": "ClaveDePrueba123"},
    )
    tok_psi = exigir(r, 200, "Login del psicólogo")["access_token"]
    h_psi = {"Authorization": f"Bearer {tok_psi}"}
    comprobar("Login del psicólogo", True, f"institución {inst_id}")

    # ------------------------------------------------------------------
    cabecera("1 · B-2 · El psicólogo crea una prueba (antes: 500)")

    r = requests.post(
        f"{API}/educativo/pruebas/",
        json={
            "nombre_tecnico": f"{PREFIJO}-ANSIEDAD-{sello}",
            "nombre_publico": "Escala de prueba Fase 0",
            "escala_minima": 0, "escala_maxima": 3, "modo_calculo": "likert_suma",
        },
        headers=h_psi, timeout=30,
    )
    comprobar("POST /educativo/pruebas/ como psicólogo devuelve 200", r.status_code == 200,
              f"status {r.status_code}" + ("" if r.status_code == 200 else f" · {r.text[:200]}"))
    prueba = exigir(r, 200, "Crear prueba")
    prueba_id = prueba["id"]

    # El aislamiento se comprueba en la BD porque PruebaResponse no expone
    # institucion_id (pendiente del grupo E de la auditoría, fuera de Fase 0).
    from sqlalchemy import create_engine, text  # noqa: E402
    motor = create_engine(os.getenv("DATABASE_URL"))
    with motor.connect() as cx:
        inst_de_prueba = cx.execute(
            text("select institucion_id from edu_pruebas where id = :i"), {"i": prueba_id}
        ).scalar()
    comprobar("La prueba queda ligada a la institución del psicólogo",
              inst_de_prueba == inst_id, f"institucion_id = {inst_de_prueba}")

    # Intento de colarse en otra institución: el router debe sobrescribirlo
    r = requests.post(
        f"{API}/educativo/pruebas/",
        json={
            "nombre_tecnico": f"{PREFIJO}-INTRUSA-{sello}",
            "nombre_publico": "Intento de fuga de tenencia",
            "institucion_id": 99999,
        },
        headers=h_psi, timeout=30,
    )
    intrusa_id = exigir(r, 200, "Crear prueba con institución ajena")["id"]
    with motor.connect() as cx:
        inst_intrusa = cx.execute(
            text("select institucion_id from edu_pruebas where id = :i"), {"i": intrusa_id}
        ).scalar()
    comprobar("Un institucion_id ajeno en el body se ignora (aislamiento)",
              inst_intrusa == inst_id, f"quedó en {inst_intrusa}, no en 99999")

    # ------------------------------------------------------------------
    cabecera("2 · Carga de dimensiones, preguntas y opciones")

    opciones = [
        {"texto_opcion": "Nunca", "valor_puntuacion": 0},
        {"texto_opcion": "Algunos días", "valor_puntuacion": 1},
        {"texto_opcion": "Más de la mitad", "valor_puntuacion": 2},
        {"texto_opcion": "Casi todos los días", "valor_puntuacion": 3},
    ]
    carga = exigir(
        requests.post(
            f"{API}/educativo/pruebas/carga-masiva/",
            json={
                "prueba_id": prueba_id,
                "dimensiones": [{"nombre": "Ansiedad", "descripcion": "Dimensión de prueba"}],
                "preguntas": [
                    {"texto_pregunta": "Me siento nervioso", "orden": 1,
                     "nombre_dimension": "Ansiedad", "es_inverso": False, "opciones": opciones},
                    {"texto_pregunta": "Me siento tranquilo", "orden": 2,
                     "nombre_dimension": "Ansiedad", "es_inverso": True, "opciones": opciones},
                ],
            },
            headers=h_psi, timeout=30,
        ), 200, "Carga masiva",
    )
    comprobar("Carga masiva de 2 ítems (uno inverso)", carga["total_preguntas"] == 2)

    completa = exigir(
        requests.get(f"{API}/educativo/pruebas/{prueba_id}/completa", headers=h_psi, timeout=30),
        200, "Ver prueba completa",
    )
    dimension = completa["dimensiones"][0]
    dimension_id = dimension["id"]
    preguntas = {p["orden"]: p for p in dimension["preguntas"]}

    # Baremos: 0-2 bajo · 3-5 medio · 6-8 alto.
    # Desde la Fase 1 la retención NO depende del texto del nivel sino del
    # indicador explícito `es_alerta`, así que el tramo alto se marca a
    # propósito. Un baremo llamado "alto" sin marcar se entrega con normalidad.
    for minimo, maximo, nivel, es_alerta in [
        (0, 2, "bajo", False), (3, 5, "medio", False), (6, 8, "alto", True)
    ]:
        exigir(
            requests.post(
                f"{API}/educativo/baremos/",
                json={
                    "dimension_id": dimension_id, "puntaje_minimo": minimo,
                    "puntaje_maximo": maximo, "nivel": nivel, "es_alerta": es_alerta,
                    "interpretacion": f"Nivel {nivel} de ansiedad.",
                },
                headers=h_psi, timeout=30,
            ), 200, f"Crear baremo {nivel}",
        )
    comprobar("3 baremos cargados en la dimensión", True)

    # ------------------------------------------------------------------
    cabecera("3 · B-1 y B-3 · Crear campaña con fecha_fin (antes: 500)")

    fecha_fin = (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)
    r = requests.post(
        f"{API}/educativo/campanas/",
        json={
            "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} 5to B",
            "institucion_id": inst_id, "fecha_fin": fecha_fin.isoformat(),
        },
        headers=h_psi, timeout=30,
    )
    comprobar("POST /educativo/campanas/ devuelve 200", r.status_code == 200,
              f"status {r.status_code}" + ("" if r.status_code == 200 else f" · {r.text[:300]}"))
    campana = exigir(r, 200, "Crear campaña")
    campana_id = campana["id"]

    comprobar("La respuesta devuelve fecha_fin", campana.get("fecha_fin") is not None,
              f"fecha_fin = {campana.get('fecha_fin')}")

    with motor.connect() as cx:
        fecha_guardada = cx.execute(
            text("select fecha_fin from edu_evaluaciones where id = :i"), {"i": campana_id}
        ).scalar()
    comprobar("fecha_fin queda persistida en PostgreSQL", fecha_guardada == fecha_fin,
              f"BD: {fecha_guardada}")

    # ------------------------------------------------------------------
    cabecera("4 · Padrón, consentimiento y matriculación")

    persona = exigir(
        requests.post(
            f"{API}/admin/personas/",
            json={
                "institucion_id": inst_id, "nombres": f"{PREFIJO} Ana",
                "apellidos": "Estudiante", "documento_identidad": f"{sello}001",
                "fecha_nacimiento": "2010-05-14", "genero": "Femenino",
                "grado_seccion": "5to B",
            },
            headers=h_psi, timeout=30,
        ), 200, "Registrar persona",
    )
    persona_id = persona["id"]

    exigir(
        requests.post(
            f"{API}/admin/personas/{persona_id}/consentimiento",
            json={
                "persona_id": persona_id, "institucion_id": inst_id,
                "otorgado_por_nombre": "Madre de familia",
                "tipo_otorgante": "apoderado",
                "referencia_documento": "Ficha de matrícula 2026",
            },
            headers=h_psi, timeout=30,
        ), 200, "Registrar consentimiento",
    )
    comprobar("Persona registrada con consentimiento vigente", True, f"persona {persona_id}")

    matricula = exigir(
        requests.post(
            f"{API}/educativo/campanas/{campana_id}/matricular-roster",
            json=[persona_id], headers=h_psi, timeout=30,
        ), 200, "Matricular roster",
    )
    comprobar("Matriculación genera 1 link mágico",
              len(matricula["generados"]) == 1 and not matricula["rechazados"],
              f"rechazados: {matricula['rechazados']}")
    token = matricula["generados"][0]["token"]

    # ------------------------------------------------------------------
    cabecera("5 · El alumno rinde el examen")

    exigir(
        requests.post(
            f"{API}/educativo/comenzar-test/{token}",
            json={
                "nombre_completo": "Ana Estudiante", "edad": 15,
                "sexo": "Femenino", "poblacion": "Secundaria", "acepta_terminos": True,
            }, timeout=30,
        ), 200, "Comenzar test",
    )
    comprobar("El alumno acepta el consentimiento y entra", True)

    examen = exigir(
        requests.get(f"{API}/educativo/examen/{token}/preguntas", timeout=30),
        200, "Cargar preguntas",
    )
    comprobar("El examen devuelve las 2 preguntas con sus opciones",
              len(examen) == 2 and all(len(p["opciones"]) == 4 for p in examen))

    # Q1 (directo) -> 3 · Q2 (inverso) -> 0, que al invertir vale (0+3)-0 = 3
    # Total esperado en la dimensión: 6 -> baremo "alto" -> informe retenido
    def opcion_con_valor(pregunta_orden, valor):
        preg = preguntas[pregunta_orden]
        return next(o["id"] for o in preg["opciones"] if o["valor_puntuacion"] == valor)

    guardado = exigir(
        requests.post(
            f"{API}/educativo/examen/{token}/guardar",
            json={"respuestas": [
                {"pregunta_id": preguntas[1]["id"], "opcion_id": opcion_con_valor(1, 3)},
                {"pregunta_id": preguntas[2]["id"], "opcion_id": opcion_con_valor(2, 0)},
            ]}, timeout=30,
        ), 200, "Guardar respuestas",
    )
    comprobar("Respuestas guardadas", "2" in guardado["mensaje"], guardado["mensaje"])

    # ------------------------------------------------------------------
    cabecera("6 · B-4 · Finalización y cálculo (antes: TypeError con escala NULL)")

    r = requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60)
    comprobar("POST /finalizar devuelve 200 (sin TypeError de escala)", r.status_code == 200,
              f"status {r.status_code}" + ("" if r.status_code == 200 else f" · {r.text[:300]}"))
    diagnosticos = exigir(r, 200, "Finalizar examen")

    with motor.connect() as cx:
        fila = cx.execute(text("""
            select i.id, i.estado, i.resultado_visible_alumno, i.informe_liberado
            from edu_inscripciones i where i.token = :t
        """), {"t": token}).one()
        insc_id = fila[0]
        puntaje = cx.execute(text(
            "select puntaje_directo from edu_resultados_dimensiones where inscripcion_id = :i"
        ), {"i": insc_id}).scalar()
        nivel = cx.execute(text(
            "select nivel from edu_diagnosticos_alumno where inscripcion_id = :i"
        ), {"i": insc_id}).scalar()

    comprobar("La inscripción queda Finalizada", fila[1] == "Finalizado", fila[1])
    comprobar("Puntaje directo = 6 (3 directo + 3 invertido con escala 0..3)",
              puntaje == 6, f"obtenido {puntaje}")
    comprobar("El baremo interpreta el puntaje como 'alto'", nivel == "alto", f"nivel '{nivel}'")
    comprobar("Al ser nivel de alerta, el informe queda retenido",
              fila[2] is False and fila[3] is False,
              f"visible={fila[2]} liberado={fila[3]}")
    comprobar("finalizar() no filtra diagnósticos de un caso en riesgo",
              diagnosticos == [], f"devolvió {len(diagnosticos)} elementos")

    # ------------------------------------------------------------------
    cabecera("7 · Informe: retención, liberación y PDF")

    estado = exigir(
        requests.get(f"{API}/educativo/examen/{token}/estado-resultados", timeout=30),
        200, "Estado de resultados",
    )
    comprobar("El alumno ve un estado 'en revisión' sin puntajes",
              estado["resultado_visible_alumno"] is False and "revis" in estado["mensaje"].lower())

    r = requests.get(f"{API}/educativo/examen/{token}/informe-pdf", timeout=60)
    comprobar("El PDF del alumno está bloqueado antes de la revisión (403)",
              r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/educativo/inscripciones/{insc_id}/informe-pdf",
                     headers=h_psi, timeout=60)
    comprobar("El psicólogo sí puede descargar el PDF",
              r.status_code == 200 and r.content[:4] == b"%PDF",
              f"status {r.status_code}, {len(r.content)} bytes")

    exigir(
        requests.patch(
            f"{API}/educativo/inscripciones/{insc_id}/liberar-informe",
            json={"interpretacion_clinica": "Revisado en sesión con la alumna."},
            headers=h_psi, timeout=30,
        ), 200, "Liberar informe",
    )
    r = requests.get(f"{API}/educativo/examen/{token}/informe-pdf", timeout=60)
    comprobar("Tras la liberación el alumno ya descarga su PDF",
              r.status_code == 200 and r.content[:4] == b"%PDF",
              f"status {r.status_code}, {len(r.content)} bytes")

    # ------------------------------------------------------------------
    cabecera("8 · B-3 · Los candados de expiración ya actúan de verdad")

    # 🆕 Desde 2026-10-29 la API rechaza crear una campaña con fecha_fin ya
    # pasada (crud.validar_fecha_fin_futura) — antes nacía vencida sin aviso.
    r = requests.post(
        f"{API}/educativo/campanas/",
        json={
            "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Nace vencida",
            "institucion_id": inst_id,
            "fecha_fin": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        }, headers=h_psi, timeout=30,
    )
    comprobar("Crear una campaña con fecha de cierre pasada se rechaza (400)",
              r.status_code == 400, f"status {r.status_code}: {r.text[:120]}")

    # Campaña vencida: la matriculación debe rechazarse. Como la API ya no
    # deja crearla vencida, se crea vigente y se vence por SQL (mismo
    # recurso que usa más abajo la campaña "Caduca").
    vencida = exigir(
        requests.post(
            f"{API}/educativo/campanas/",
            json={
                "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Vencida",
                "institucion_id": inst_id,
                "fecha_fin": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            }, headers=h_psi, timeout=30,
        ), 200, "Crear campaña (luego se vence por SQL)",
    )
    with motor.begin() as cx:
        cx.execute(text("update edu_evaluaciones set fecha_fin = :f where id = :i"),
                   {"f": datetime.utcnow() - timedelta(days=1), "i": vencida["id"]})
    res = exigir(
        requests.post(
            f"{API}/educativo/campanas/{vencida['id']}/matricular-roster",
            json=[persona_id], headers=h_psi, timeout=30,
        ), 200, "Matricular en campaña vencida",
    )
    comprobar("Matricular en una campaña vencida se rechaza",
              res.get("error") is not None and not res["generados"],
              res.get("error", "sin error"))

    # Campaña que caduca mientras el alumno la tiene abierta
    viva = exigir(
        requests.post(
            f"{API}/educativo/campanas/",
            json={
                "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Caduca",
                "institucion_id": inst_id,
                "fecha_fin": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            }, headers=h_psi, timeout=30,
        ), 200, "Crear campaña que caducará",
    )
    persona2 = exigir(
        requests.post(
            f"{API}/admin/personas/",
            json={
                "institucion_id": inst_id, "nombres": f"{PREFIJO} Luis",
                "apellidos": "Estudiante", "documento_identidad": f"{sello}002",
                "genero": "Masculino",
            }, headers=h_psi, timeout=30,
        ), 200, "Registrar segunda persona",
    )["id"]
    exigir(
        requests.post(
            f"{API}/admin/personas/{persona2}/consentimiento",
            json={"persona_id": persona2, "institucion_id": inst_id,
                  "otorgado_por_nombre": "Padre", "tipo_otorgante": "apoderado"},
            headers=h_psi, timeout=30,
        ), 200, "Consentimiento segunda persona",
    )
    mat2 = exigir(
        requests.post(
            f"{API}/educativo/campanas/{viva['id']}/matricular-roster",
            json=[persona2], headers=h_psi, timeout=30,
        ), 200, "Matricular en campaña viva",
    )
    token2 = mat2["generados"][0]["token"]

    # El alumno EMPIEZA con la campaña vigente y la campaña vence después.
    # (Desde C-5, Fase 3, comenzar-test rechaza con 410 una campaña ya vencida
    # y no registra el consentimiento; antes lo registraba igualmente.)
    exigir(requests.post(
        f"{API}/educativo/comenzar-test/{token2}",
        json={"nombre_completo": "Luis Estudiante", "edad": 14, "sexo": "Masculino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30,
    ), 200, "Comenzar con la campaña vigente")
    r = requests.get(f"{API}/educativo/examen/{token2}/preguntas", timeout=30)
    comprobar("Con la campaña vigente el examen carga", r.status_code == 200,
              f"status {r.status_code}")

    with motor.begin() as cx:
        cx.execute(text("update edu_evaluaciones set fecha_fin = :f where id = :i"),
                   {"f": datetime.utcnow() - timedelta(hours=1), "i": viva["id"]})

    r = requests.post(
        f"{API}/educativo/comenzar-test/{token2}",
        json={"nombre_completo": "Luis Estudiante", "edad": 14, "sexo": "Masculino",
              "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30,
    )
    comprobar("Al vencer la campaña, reanudar el examen devuelve 410 GONE",
              r.status_code == 410, f"status {r.status_code}")
    r = requests.get(f"{API}/educativo/examen/{token2}/preguntas", timeout=30)
    comprobar("Al vencer la campaña, cargar preguntas devuelve 410 GONE",
              r.status_code == 410, f"status {r.status_code}")

    r = requests.post(
        f"{API}/educativo/examen/{token2}/guardar",
        json={"respuestas": [{"pregunta_id": preguntas[1]["id"],
                              "opcion_id": opcion_con_valor(1, 1)}]}, timeout=30,
    )
    comprobar("Al vencer la campaña, guardar respuestas devuelve 410 GONE",
              r.status_code == 410, f"status {r.status_code}")

    r = requests.post(f"{API}/educativo/examen/{token2}/finalizar", timeout=30)
    comprobar("Al vencer la campaña, finalizar devuelve 410 GONE",
              r.status_code == 410, f"status {r.status_code}")

    # ------------------------------------------------------------------
    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    """Borra todo lo creado por esta verificación (prefijo ZZTEST)."""
    from sqlalchemy import create_engine, text

    motor = create_engine(os.getenv("DATABASE_URL"))
    with motor.begin() as cx:
        cx.execute(text("""
            DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN (
                SELECT i.id FROM edu_inscripciones i
                JOIN edu_evaluaciones e ON i.evaluacion_id = e.id
                WHERE e.nombre_grupo LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN (
                SELECT i.id FROM edu_inscripciones i
                JOIN edu_evaluaciones e ON i.evaluacion_id = e.id
                WHERE e.nombre_grupo LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN (
                SELECT i.id FROM edu_inscripciones i
                JOIN edu_evaluaciones e ON i.evaluacion_id = e.id
                WHERE e.nombre_grupo LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_inscripciones WHERE evaluacion_id IN (
                SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZTEST%')"""))
        cx.execute(text("DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE 'ZZTEST%'"))
        cx.execute(text("""
            DELETE FROM edu_baremos WHERE dimension_id IN (
                SELECT d.id FROM edu_dimensiones d
                JOIN edu_pruebas p ON d.prueba_id = p.id
                WHERE p.nombre_tecnico LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_opciones WHERE pregunta_id IN (
                SELECT pr.id FROM edu_preguntas pr
                JOIN edu_pruebas p ON pr.prueba_id = p.id
                WHERE p.nombre_tecnico LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_preguntas WHERE prueba_id IN (
                SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZTEST%')"""))
        cx.execute(text("""
            DELETE FROM edu_dimensiones WHERE prueba_id IN (
                SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZTEST%')"""))
        cx.execute(text("DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE 'ZZTEST%'"))
        cx.execute(text("""
            DELETE FROM consentimientos_informados WHERE persona_id IN (
                SELECT id FROM personas WHERE nombres LIKE 'ZZTEST%')"""))
        cx.execute(text("DELETE FROM personas WHERE nombres LIKE 'ZZTEST%'"))
        cx.execute(text("DELETE FROM auth_usuarios WHERE email LIKE 'zztest%'"))
        cx.execute(text("DELETE FROM instituciones WHERE nombre LIKE 'ZZTEST%'"))
    print("Datos ZZTEST eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    parser.add_argument("--limpiar", action="store_true")
    args = parser.parse_args()

    if args.limpiar:
        limpiar()
        sys.exit(0)
    sys.exit(main(args.url))
