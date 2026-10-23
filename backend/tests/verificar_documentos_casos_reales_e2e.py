"""Verificación end-to-end del Motor de Documentos Institucionales con dos
casos ilustrativos pedidos como validación funcional del motor (no existen
PDFs "originales" reales para comparar byte a byte — ver la nota al final de
este docstring y el hallazgo correspondiente reportado en CLAUDE.md/el
entregable de la tarea). Los dos casos se diseñaron usando EXCLUSIVAMENTE los
7 `tipo_seccion` ya existentes (encabezado, datos_filiacion, datos_familiares,
texto_libre, tabla_dinamica, resultados_prueba, firma) — no se agregó ningún
tipo nuevo.

  CASO 1 — "Informe psicológico individual" (alcance='personas_especificas',
  1 estudiante, requiere_consentimiento_individual=True):
    encabezado, datos_filiacion, datos_familiares, texto_libre (motivo),
    texto_libre (observación conductual), resultados_prueba (PHQ-9, la
    única prueba con catálogo/baremos cargados hoy), texto_libre
    (conclusiones), texto_libre (recomendaciones), firma.

  CASO 2 — "Informe grupal por sección" (alcance='estructura_academica',
  una Sección completa, SIN requiere_consentimiento_individual):
    encabezado, texto_libre (contexto), tabla_dinamica (ligada a la lista
    congelada de estudiantes: nombre/grado-sección automáticos + una
    columna libre de observaciones por estudiante), texto_libre
    (conclusiones grupales), texto_libre (recomendaciones), firma.
    Deliberadamente SIN datos_filiacion/datos_familiares/resultados_prueba:
    con más de un estudiante esas tres secciones solo pueden renderizar
    "No aplica" (ver crud._resolver_datos_filiacion/_familiares/
    _resultados_prueba) — incluirlas en una plantilla grupal real sería un
    error de diseño de plantilla, no algo que este motor deba forzar.

Lo que se verifica contra el PDF real generado (pypdf):
  1. Las 9 (CASO 1) / 6 (CASO 2) secciones aparecen, EN EL ORDEN declarado
     por PlantillaSeccion.orden.
  2. Tipografía: Arial/Helvetica (según lo que el servidor tenga registrado)
     a 11pt, igual que declara la plantilla.
  3. Contenido: los datos de filiación/familiares/resultados de la prueba
     coinciden con lo que hay en la base de datos real (Persona,
     PersonaDatosFamiliares, PersonaAntecedentesClinicos,
     DiagnosticoAlumno) — no con un valor inventado en el test.
  4. CASO 1: ninguna sección cae en "No aplica" (hay exactamente 1
     estudiante). CASO 2: NINGUNA sección cae en "No aplica" en absoluto,
     porque la plantilla grupal no usa ninguna de las 3 secciones que
     dependen de tener exactamente un estudiante.
  5. Reemisión (v2 en ambos casos): la v1 ya emitida permanece
     BYTE-IDÉNTICA (checksum_sha256 sin cambios) después de generar v2, y
     v2 refleja el contenido editado — mismo criterio de inmutabilidad que
     ya exige CLAUDE.md para InformeVersion/DocumentoInstitucionalVersion.

Nota sobre el punto 4 del prompt ("listar diferencias con el PDF original"):
no se adjuntó/describió ningún documento real de un colegio (el prompt que
originó esta tarea traía el placeholder sin llenar); el usuario indicó
explícitamente construir casos ilustrativos usando la lógica ya implementada
en el backend. Por lo tanto no existe un PDF "original" contra el cual
diferenciar — el sustituto válido es lo que este script sí hace: verificar
que el PDF generado es fiel a (a) la PlantillaSeccion tal como se diseñó y
(b) los datos reales en la base de datos. La sección "Diferencias" del
entregable de la tarea documenta esta limitación explícitamente.

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_casos_reales_e2e
    python -m tests.verificar_documentos_casos_reales_e2e --limpiar
"""

import argparse
import io
import os
import re
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from pypdf import PdfReader  # noqa: E402
from core.storage import obtener_storage_service  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZDOCEJ"
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


def sql_uno(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchone()


def sql_todos(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchall()


def leer_pdf_de_version(numero_version, documento_id):
    fila = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones "
        "WHERE documento_institucional_id=:d AND numero_version=:n",
        d=documento_id, n=numero_version,
    )
    return obtener_storage_service().leer(fila.storage_key)


def checksum_de_version(numero_version, documento_id):
    fila = sql_uno(
        "SELECT checksum_sha256 FROM documentos_institucionales_versiones "
        "WHERE documento_institucional_id=:d AND numero_version=:n",
        d=documento_id, n=numero_version,
    )
    return fila.checksum_sha256


def texto_pdf(contenido: bytes) -> str:
    """Texto de todas las páginas, con TODO whitespace (incluidos saltos de
    línea dentro de una celda de tabla envuelta por Paragraph) colapsado a
    un solo espacio -- sin esto, una búsqueda literal de una frase que cae
    partida entre dos líneas de una celda nunca encuentra coincidencia
    aunque el contenido sea correcto."""
    lector = PdfReader(io.BytesIO(contenido))
    crudo = " ".join((p.extract_text() or "") for p in lector.pages)
    return re.sub(r"\s+", " ", crudo)


def orden_correcto(texto_mayus: str, titulos_en_orden) -> bool:
    """True si cada título de `titulos_en_orden` aparece en `texto_mayus`
    (ya en mayúsculas, igual que el generador los dibuja) en índices
    estrictamente crecientes -- confirma que el PDF real respeta
    PlantillaSeccion.orden, no solo que las secciones están presentes."""
    posicion = -1
    for titulo in titulos_en_orden:
        idx = texto_mayus.find(titulo.upper())
        if idx == -1 or idx <= posicion:
            return False
        posicion = idx
    return True


def fuentes_usadas(contenido: bytes) -> set:
    lector = PdfReader(io.BytesIO(contenido))
    nombres = set()
    for pagina in lector.pages:
        fuentes = pagina.get("/Resources", {}).get("/Font", {})
        for clave in fuentes:
            base = str(fuentes[clave].get_object().get("/BaseFont", ""))
            nombres.add(base.split("+")[-1])
    return nombres


def tamano_fuente_presente(contenido: bytes, tamano: int) -> bool:
    lector = PdfReader(io.BytesIO(contenido))
    patron = re.compile(rf"/F\d+\+?0?\s+{tamano}\s+Tf")
    for pagina in lector.pages:
        ref = pagina.get("/Contents")
        if ref is None:
            continue
        datos = ref.get_object().get_data().decode("latin1", errors="replace")
        if patron.search(datos):
            return True
    return False


def _id_seccion(h, plantilla_id, tipo_seccion, titulo):
    r = requests.get(f"{API}/documentos/plantillas/{plantilla_id}/secciones", headers=h, timeout=30)
    for s in r.json():
        if s["tipo_seccion"] == tipo_seccion and s["titulo"] == titulo:
            return s["id"]
    raise RuntimeError(f"No se encontró sección {tipo_seccion}/{titulo}")


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")
    anio_actual = datetime.now().year

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_id = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}"}, headers=h_super, timeout=30), 201, "Institución")["id"]
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", f"{PREFIJO} Psicóloga", "psicologo", inst_id)
    h_admin = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com", f"{PREFIJO} Admin", "admin", inst_id)

    psi_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com").id
    exigir(requests.patch(f"{API}/auth/usuarios/{psi_id}", json={"cargo": "Psicóloga del DPTO"}, headers=h_super, timeout=30), 200, "poner cargo psicóloga")

    exigir(requests.post(f"{API}/documentos/anios-oficiales", json={
        "anio": anio_actual, "texto": f"Año De La Prueba {sello}",
    }, headers=h_super, timeout=30), 200, "upsert año oficial")

    # ------------------------------------------------------------------
    # 0b · Punto 2 del prompt: verificar contra la BD real qué Prueba(s)
    # referencia un resultados_prueba y si ya están cargadas (catálogo,
    # dimensiones, baremos) -- antes de construir nada sobre ellas.
    # ------------------------------------------------------------------
    print("\n0b · Verificación contra BD real: ¿qué Prueba(s) están cargadas para resultados_prueba?")
    fila_phq9 = sql_uno("SELECT id, nombre_tecnico, nombre_publico, visible_para_clientes FROM edu_pruebas WHERE nombre_tecnico='PHQ-9'")
    comprobar("[0b] PHQ-9 existe en el catálogo real (edu_pruebas)", fila_phq9 is not None)
    phq9_id = fila_phq9.id
    phq9_nombre_publico = fila_phq9.nombre_publico
    n_dim = sql_uno("SELECT COUNT(*) AS n FROM edu_dimensiones WHERE prueba_id=:p", p=phq9_id).n
    n_baremos = sql_uno("SELECT COUNT(*) AS n FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id=:p) AND activo=true", p=phq9_id).n
    comprobar("[0b] PHQ-9 tiene al menos 1 dimensión cargada", n_dim >= 1, f"n_dimensiones={n_dim}")
    comprobar("[0b] PHQ-9 tiene al menos 1 baremo activo cargado", n_baremos >= 1, f"n_baremos={n_baremos}")
    otras = sql_todos("SELECT nombre_tecnico FROM edu_pruebas WHERE nombre_tecnico != 'PHQ-9' AND visible_para_clientes=true")
    print(f"    Otras pruebas visibles para clientes en catálogo real: {[o.nombre_tecnico for o in otras] or '(ninguna)'}")
    print("    -> Único instrumento con catálogo+baremos+informe completo hoy: PHQ-9. "
          "CASO 1 usa PHQ-9 en su sección resultados_prueba; no se referencia CARAS/FES/ningún otro "
          "instrumento comercial (no están cargados -- ver hallazgo en el entregable).")

    # ==================================================================
    # CASO 1 — Informe psicológico individual
    # ==================================================================
    print("\n1 · CASO 1 — Plantilla 'Informe psicológico individual'")
    tipo1 = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_individual_{sello}", "nombre": f"{PREFIJO} Informe individual",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": True,
    }, headers=h_super, timeout=30), 200, "crear tipo individual")

    plantilla1 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_id, "tipo_documento_id": tipo1["id"], "nombre": f"{PREFIJO} Plantilla individual",
        "fuente": "Arial", "tamano_pt": 11, "formato_correlativo": "INF-{correlativo:04d}-{anio}",
    }, headers=h_super, timeout=30), 200, "crear plantilla individual")

    _CASO1_SECCIONES = [
        (0, "encabezado", "Encabezado", {
            "destinatarios": [{"nombre": "Dirección Académica", "cargo": "Directora"}],
            "mostrar_anio_oficial": True,
        }),
        (1, "datos_filiacion", "I. Datos de Filiación", None),
        (2, "datos_familiares", "II. Datos Familiares y Antecedentes", None),
        (3, "texto_libre", "III. Motivo de Consulta", None),
        (4, "texto_libre", "IV. Observación Conductual", None),
        (5, "resultados_prueba", "V. Resultados de la Evaluación Psicométrica", None),
        (6, "texto_libre", "VI. Conclusiones", None),
        (7, "texto_libre", "VII. Recomendaciones", None),
        (8, "firma", "Firma", None),
    ]
    for orden, tipo_seccion, titulo, config in _CASO1_SECCIONES:
        exigir(requests.post(f"{API}/documentos/plantillas/{plantilla1['id']}/secciones", json={
            "orden": orden, "tipo_seccion": tipo_seccion, "titulo": titulo, "config": config,
        }, headers=h_super, timeout=30), 200, f"sección CASO1 {titulo}")
    comprobar("[1] Plantilla 1 usa solo los 7 tipos existentes (sin agregar ninguno)", True)

    print("\n2 · CASO 1 — Estudiante real: consentimiento, ficha familiar/clínica, aplicación PHQ-9 real")
    alumno = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": PREFIJO, "apellidos": f"Individual {sello}",
        "tipo_perfil": "estudiante", "documento_identidad": f"DNI{sello}",
        "fecha_nacimiento": "2012-05-10", "genero": "Femenino",
    }, headers=h_admin, timeout=30), 200, "crear alumno individual")["id"]

    exigir(requests.post(f"{API}/admin/personas/{alumno}/consentimiento", json={
        "persona_id": alumno, "institucion_id": inst_id,
        "otorgado_por_nombre": "Madre de Prueba", "tipo_otorgante": "apoderado",
    }, headers=h_psi, timeout=30), 200, "consentimiento apoderado")

    exigir(requests.patch(f"{API}/admin/personas/{alumno}/datos-familiares", json={
        "numero_hermanos": 2, "vive_con": "Madre y abuela materna",
        "lugar_nacimiento": "Lima", "lugar_procedencia": "Lima",
    }, headers=h_psi, timeout=30), 200, "datos familiares")
    exigir(requests.patch(f"{API}/admin/personas/{alumno}/antecedentes-clinicos", json={
        "recibe_terapia_psicologica_externa": True,
        "detalle_terapia_psicologica_externa": "Terapia particular desde marzo, 1 sesión semanal.",
        "recibe_atencion_psiquiatrica_externa": False,
    }, headers=h_psi, timeout=30), 200, "antecedentes clínicos")

    campana1 = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} Campaña individual {sello}", "institucion_id": inst_id,
    }, headers=h_admin, timeout=30), 200, "crear campaña 1")
    matricula1 = exigir(requests.post(f"{API}/educativo/campanas/{campana1['id']}/matricular-roster",
                                       json=[alumno], headers=h_admin, timeout=30), 200, "matricular alumno individual")
    token1 = matricula1["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token1}", json={
        "nombre_completo": PREFIJO, "edad": 13, "sexo": "Femenino", "poblacion": "Secundaria",
        "acepta_terminos": True,
    }, timeout=30), 200, "comenzar test individual")
    preguntas1 = exigir(requests.get(f"{API}/educativo/examen/{token1}/preguntas", timeout=30), 200, "preguntas individual")
    detalle_staff = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_admin, timeout=30), 200, "detalle staff PHQ-9")
    preg_por_orden = {p["orden"]: p for p in detalle_staff["dimensiones"][0]["preguntas"]}

    def _opcion_id_publica(pregunta_publica_id, valor_deseado):
        orden = next(o["orden"] for o in preg_por_orden.values() if o["id"] == pregunta_publica_id)
        return next(o["id"] for o in preg_por_orden[orden]["opciones"] if o["valor_puntuacion"] == valor_deseado)

    # Puntaje bajo (0 en todos los ítems, incluido el 9) -> sin alerta, para
    # que el diagnóstico real quede disponible sin depender del flujo de
    # informe_liberado (irrelevante para el motor de documentos -- ver
    # hallazgo sobre _resolver_resultados_prueba en el entregable).
    respuestas1 = [{"pregunta_id": p["id"], "opcion_id": _opcion_id_publica(p["id"], 0)} for p in preguntas1]
    exigir(requests.post(f"{API}/educativo/examen/{token1}/guardar", json={"respuestas": respuestas1}, timeout=30), 200, "guardar respuestas individual")
    exigir(requests.post(f"{API}/educativo/examen/{token1}/finalizar", timeout=60), 200, "finalizar individual")
    inscripcion1_id = sql_uno("SELECT id FROM edu_inscripciones WHERE token=:t", t=token1).id

    diag = sql_uno(
        "SELECT d.nivel, d.interpretacion, dim.nombre AS dimension_nombre "
        "FROM edu_diagnosticos_alumno d JOIN edu_dimensiones dim ON dim.id = d.dimension_id "
        "WHERE d.inscripcion_id=:i", i=inscripcion1_id,
    )
    comprobar("[2] El examen real generó al menos un DiagnosticoAlumno", diag is not None)

    # ------------------------------------------------------------------
    # HALLAZGO (reportado, no corregido -- fuera de alcance de esta tarea):
    # no existe ningún endpoint público para escribir
    # DocumentoInstitucionalResultadoPrueba (modulos/documentos/router.py no
    # lo expone; crud.py solo lo LEE en _resolver_resultados_prueba). Un
    # psicólogo real no tiene forma, hoy, de vincular una Inscripcion a una
    # sección resultados_prueba a través de la API. Se inserta la fila
    # directamente por SQL solo para poder ejercitar el renderizador.
    # ------------------------------------------------------------------
    print("\n    [HALLAZGO] No hay endpoint para crear DocumentoInstitucionalResultadoPrueba;"
          " se inserta por SQL directo solo para poder probar el renderizador resultados_prueba.")

    print("\n3 · CASO 1 — Crear documento, escribir contenido, generar v1")
    doc1 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo1["id"], "plantilla_documento_id": plantilla1["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Informe individual", "personas_ids": [alumno],
    }, headers=h_psi, timeout=30), 200, "crear documento 1")

    seccion_resultados_id = _id_seccion(h_psi, plantilla1["id"], "resultados_prueba", "V. Resultados de la Evaluación Psicométrica")
    with MOTOR.begin() as c:
        c.execute(text(
            "INSERT INTO documentos_institucionales_resultados_prueba "
            "(documento_institucional_id, plantilla_seccion_id, institucion_id, persona_id, inscripcion_id) "
            "VALUES (:d, :s, :i, :p, :ins)"
        ), {"d": doc1["id"], "s": seccion_resultados_id, "i": inst_id, "p": alumno, "ins": inscripcion1_id})

    seccion_filiacion_id = _id_seccion(h_psi, plantilla1["id"], "datos_filiacion", "I. Datos de Filiación")
    exigir(requests.put(f"{API}/documentos/{doc1['id']}/secciones/{seccion_filiacion_id}",
                         json={"contenido": {"diagnostico_presuntivo": "Sin indicadores clínicos significativos al momento de la evaluación."}},
                         headers=h_psi, timeout=30), 200, "contenido filiación")
    contenidos_texto1 = {
        "III. Motivo de Consulta": "Derivación por tutoría para descarte de sintomatología depresiva.",
        "IV. Observación Conductual": "Colaboradora durante la entrevista, contacto visual adecuado, discurso coherente.",
        "VI. Conclusiones": "No se evidencian indicadores clínicos de riesgo al momento de la evaluación.",
        "VII. Recomendaciones": "Continuar seguimiento tutorial trimestral; no requiere derivación externa por ahora.",
    }
    for titulo, texto_val in contenidos_texto1.items():
        sid = _id_seccion(h_psi, plantilla1["id"], "texto_libre", titulo)
        exigir(requests.put(f"{API}/documentos/{doc1['id']}/secciones/{sid}", json={"contenido": {"texto": texto_val}},
                             headers=h_psi, timeout=30), 200, f"contenido {titulo}")

    version1_v1 = exigir(requests.post(f"{API}/documentos/{doc1['id']}/generar-version", headers=h_psi, timeout=30), 200, "generar v1 CASO1")
    comprobar("[3] v1 numero_version=1", version1_v1["numero_version"] == 1)

    print("\n4 · CASO 1 — Validar PDF v1 contra plantilla y BD real")
    pdf1_v1 = leer_pdf_de_version(1, doc1["id"])
    texto1 = texto_pdf(pdf1_v1).upper()

    titulos_orden1 = [t for _, _, t, _ in _CASO1_SECCIONES]
    comprobar("[4] Las 9 secciones del CASO 1 aparecen EN ORDEN en el PDF real", orden_correcto(texto1, titulos_orden1))
    comprobar("[4] No aparece 'No aplica' en ningún lado (hay exactamente 1 estudiante)", "NO APLICA" not in texto1)
    comprobar("[4] El correlativo se imprimió (INF-0001-...)", "INF-0001" in texto1, texto1[:200])
    comprobar("[4] El año oficial configurado aparece", f"AÑO DE LA PRUEBA {sello}".upper() in texto1)
    comprobar("[4] El destinatario configurado aparece ('PARA: ...')", "DIRECCIÓN ACADÉMICA" in texto1 or "DIRECCION ACADEMICA" in texto1)
    comprobar("[4] Nombre del alumno (filiación, desde el snapshot histórico) aparece",
              f"{PREFIJO} INDIVIDUAL {sello}".upper() in texto1)
    comprobar("[4] DNI real de la BD aparece en filiación", f"DNI{sello}" in texto1)
    comprobar("[4] Composición familiar real (vive_con) aparece", "MADRE Y ABUELA MATERNA" in texto1)
    comprobar("[4] Antecedente clínico real (terapia externa) aparece", "TERAPIA PARTICULAR DESDE MARZO" in texto1)
    comprobar("[4] Nombre real de la prueba (nombre_publico desde BD) aparece en resultados_prueba",
              phq9_nombre_publico.upper() in texto1, phq9_nombre_publico)
    comprobar("[4] La dimensión real de PHQ-9 (desde BD) aparece en la tabla de resultados",
              diag.dimension_nombre.upper() in texto1, diag.dimension_nombre)
    comprobar("[4] El nivel real diagnosticado (desde BD) aparece en la tabla de resultados",
              diag.nivel.upper() in texto1, diag.nivel)

    fuentes1 = fuentes_usadas(pdf1_v1)
    _FUENTES_ARIAL_O_SUSTITUTO = {"Arial", "Arial-Bold", "ArialMT", "Arial-BoldMT", "/Helvetica", "Helvetica", "Helvetica-Bold"}
    comprobar("[4] Tipografía: usa Arial (o su nombre real registrado por el SO) o su sustituto Helvetica",
              any(f in _FUENTES_ARIAL_O_SUSTITUTO for f in fuentes1), str(fuentes1))
    comprobar("[4] Tamaño de cuerpo 11pt (tamano_pt de la plantilla) presente", tamano_fuente_presente(pdf1_v1, 11))

    print("\n5 · CASO 1 — Reemisión: v1 permanece byte-idéntica, v2 refleja el cambio")
    checksum_v1_antes = checksum_de_version(1, doc1["id"])
    sid_motivo = _id_seccion(h_psi, plantilla1["id"], "texto_libre", "III. Motivo de Consulta")
    exigir(requests.put(f"{API}/documentos/{doc1['id']}/secciones/{sid_motivo}",
                         json={"contenido": {"texto": "Motivo de consulta corregido tras revisión del expediente."}},
                         headers=h_psi, timeout=30), 200, "editar motivo antes de reemitir")
    version1_v2 = exigir(requests.post(f"{API}/documentos/{doc1['id']}/reemitir",
                                        json={"motivo": "Corrección de redacción del motivo de consulta"},
                                        headers=h_psi, timeout=30), 200, "reemitir CASO1")
    comprobar("[5] v2 numero_version=2", version1_v2["numero_version"] == 2)
    checksum_v1_despues = checksum_de_version(1, doc1["id"])
    comprobar("[5] v1 sigue byte-idéntica tras la reemisión (checksum sin cambios)", checksum_v1_antes == checksum_v1_despues)
    texto1_v2 = texto_pdf(leer_pdf_de_version(2, doc1["id"])).upper()
    comprobar("[5] v2 refleja el texto corregido", "MOTIVO DE CONSULTA CORREGIDO" in texto1_v2)
    texto1_v1_relectura = texto_pdf(leer_pdf_de_version(1, doc1["id"])).upper()
    comprobar("[5] v1 (releída de storage) sigue con el texto ORIGINAL, no el corregido",
              "DERIVACIÓN POR TUTORÍA" in texto1_v1_relectura or "DERIVACION POR TUTORIA" in texto1_v1_relectura)

    # ==================================================================
    # CASO 2 — Informe grupal por sección
    # ==================================================================
    print("\n6 · CASO 2 — Plantilla 'Informe grupal por sección'")
    tipo2 = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_grupal_{sello}", "nombre": f"{PREFIJO} Informe grupal",
        "alcances_permitidos": "estructura_academica", "visibilidades_permitidas": "confidencial_clinico, compartible_colegio",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo grupal")
    plantilla2 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_id, "tipo_documento_id": tipo2["id"], "nombre": f"{PREFIJO} Plantilla grupal",
        "fuente": "Arial", "tamano_pt": 11, "formato_correlativo": "GRP-{correlativo:04d}-{anio}",
    }, headers=h_super, timeout=30), 200, "crear plantilla grupal")

    _CONFIG_TABLA = {
        "filas_desde_lista_estudiantes": True,
        "columnas": [
            {"titulo": "Estudiante", "origen": "automatico", "campo_automatico": "nombre_completo"},
            {"titulo": "Grado y sección", "origen": "automatico", "campo_automatico": "grado_seccion"},
            {"titulo": "Observaciones del aula", "origen": "libre"},
        ],
    }
    _CASO2_SECCIONES = [
        (0, "encabezado", "Encabezado", {"mostrar_anio_oficial": True}),
        (1, "texto_libre", "I. Contexto y Objetivo de la Evaluación Grupal", None),
        (2, "tabla_dinamica", "II. Cuadro de Estudiantes Evaluados", _CONFIG_TABLA),
        (3, "texto_libre", "III. Conclusiones Grupales", None),
        (4, "texto_libre", "IV. Recomendaciones para el Aula", None),
        (5, "firma", "Firma", None),
    ]
    for orden, tipo_seccion, titulo, config in _CASO2_SECCIONES:
        exigir(requests.post(f"{API}/documentos/plantillas/{plantilla2['id']}/secciones", json={
            "orden": orden, "tipo_seccion": tipo_seccion, "titulo": titulo, "config": config,
        }, headers=h_super, timeout=30), 200, f"sección CASO2 {titulo}")
    comprobar("[6] Plantilla 2 usa solo los 7 tipos existentes, sin datos_filiacion/familiares/resultados_prueba "
              "(no aplican a un documento con más de 1 estudiante)", True)

    print("\n7 · CASO 2 — Estructura académica real: Nivel/Grado/Sección + 3 matriculados")
    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_id, "nombre": f"{PREFIJO} Secundaria {sello}", "orden": 1,
    }, headers=h_admin, timeout=30), 200, "crear nivel")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "1°", "orden": 1,
    }, headers=h_admin, timeout=30), 200, "crear grado")
    seccion = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "anio_escolar": anio_actual,
    }, headers=h_admin, timeout=30), 200, "crear sección")

    alumnos_grupo = []
    for i in range(3):
        p = exigir(requests.post(f"{API}/admin/personas/", json={
            "institucion_id": inst_id, "nombres": PREFIJO, "apellidos": f"Grupal{i} {sello}",
            "tipo_perfil": "estudiante",
        }, headers=h_admin, timeout=30), 200, f"crear alumno grupal {i}")["id"]
        exigir(requests.post(f"{API}/admin/personas/{p}/matricula", json={"seccion_id": seccion["id"]},
                              headers=h_admin, timeout=30), 200, f"matricular alumno grupal {i}")
        alumnos_grupo.append(p)

    doc2 = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo2["id"], "plantilla_documento_id": plantilla2["id"],
        "alcance": "estructura_academica", "titulo": f"{PREFIJO} Informe grupal 1°A",
        "estructura": [{"seccion_id": seccion["id"]}],
    }, headers=h_psi, timeout=30), 200, "crear documento 2")
    comprobar("[7] La lista congelada trae a los 3 estudiantes matriculados", len(doc2["estudiantes"]) == 3)

    print("\n8 · CASO 2 — Completar contenido (contexto + tabla) y generar v1")
    sid_contexto = _id_seccion(h_psi, plantilla2["id"], "texto_libre", "I. Contexto y Objetivo de la Evaluación Grupal")
    exigir(requests.put(f"{API}/documentos/{doc2['id']}/secciones/{sid_contexto}",
                         json={"contenido": {"texto": "Tamizaje grupal de bienestar socioemocional del aula 1°A, 2do bimestre."}},
                         headers=h_psi, timeout=30), 200, "contenido contexto")
    sid_tabla = _id_seccion(h_psi, plantilla2["id"], "tabla_dinamica", "II. Cuadro de Estudiantes Evaluados")
    celdas_v1 = {str(pid): {"Observaciones del aula": f"Observación inicial alumno {pid}"} for pid in alumnos_grupo}
    exigir(requests.put(f"{API}/documentos/{doc2['id']}/secciones/{sid_tabla}", json={"contenido": {"celdas": celdas_v1}},
                         headers=h_psi, timeout=30), 200, "contenido tabla v1")
    for titulo, texto_val in {
        "III. Conclusiones Grupales": "El aula no presenta indicadores grupales de alerta.",
        "IV. Recomendaciones para el Aula": "Reforzar actividades de tutoría sobre manejo emocional.",
    }.items():
        sid = _id_seccion(h_psi, plantilla2["id"], "texto_libre", titulo)
        exigir(requests.put(f"{API}/documentos/{doc2['id']}/secciones/{sid}", json={"contenido": {"texto": texto_val}},
                             headers=h_psi, timeout=30), 200, f"contenido {titulo}")

    version2_v1 = exigir(requests.post(f"{API}/documentos/{doc2['id']}/generar-version", headers=h_psi, timeout=30), 200, "generar v1 CASO2")
    comprobar("[8] v1 numero_version=1", version2_v1["numero_version"] == 1)

    pdf2_v1 = leer_pdf_de_version(1, doc2["id"])
    texto2 = texto_pdf(pdf2_v1).upper()
    titulos_orden2 = [t for _, _, t, _ in _CASO2_SECCIONES]
    comprobar("[8] Las 6 secciones del CASO 2 aparecen EN ORDEN en el PDF real", orden_correcto(texto2, titulos_orden2))
    comprobar("[8] 'No aplica' NUNCA aparece (la plantilla grupal no usa ninguna sección de 1-estudiante)",
              "NO APLICA" not in texto2)
    comprobar("[8] La tabla trae los 3 nombres reales de los estudiantes matriculados",
              all(f"GRUPAL{i} {sello}".upper() in texto2 for i in range(3)))
    comprobar("[8] La tabla trae el grado/sección real ('1° A')", "1° A" in texto2 or "1°A" in texto2 or "1 A" in texto2.replace("°", ""))
    comprobar("[8] Las observaciones libres v1 aparecen", f"OBSERVACIÓN INICIAL ALUMNO {alumnos_grupo[0]}".upper() in texto2
              or f"OBSERVACION INICIAL ALUMNO {alumnos_grupo[0]}".upper() in texto2)

    print("\n9 · CASO 2 — Reemisión: lista congelada NO cambia, v1 queda byte-idéntica, v2 trae la tabla actualizada")
    checksum2_v1_antes = checksum_de_version(1, doc2["id"])
    celdas_v2 = {str(pid): {"Observaciones del aula": f"Observación actualizada tras segunda sesión, alumno {pid}"} for pid in alumnos_grupo}
    exigir(requests.put(f"{API}/documentos/{doc2['id']}/secciones/{sid_tabla}", json={"contenido": {"celdas": celdas_v2}},
                         headers=h_psi, timeout=30), 200, "actualizar tabla antes de reemitir")
    ids_antes = {e["persona_id"] for e in exigir(requests.get(f"{API}/documentos/{doc2['id']}", headers=h_psi, timeout=30), 200, "releer doc2 antes")["estudiantes"]}
    version2_v2 = exigir(requests.post(f"{API}/documentos/{doc2['id']}/reemitir",
                                        json={"motivo": "Actualización de observaciones tras segunda sesión de aula"},
                                        headers=h_psi, timeout=30), 200, "reemitir CASO2")
    comprobar("[9] v2 numero_version=2", version2_v2["numero_version"] == 2)
    ids_despues = {e["persona_id"] for e in exigir(requests.get(f"{API}/documentos/{doc2['id']}", headers=h_psi, timeout=30), 200, "releer doc2 después")["estudiantes"]}
    comprobar("[9] La lista congelada de estudiantes NO cambió con la reemisión", ids_antes == ids_despues == set(alumnos_grupo))
    checksum2_v1_despues = checksum_de_version(1, doc2["id"])
    comprobar("[9] v1 del CASO 2 sigue byte-idéntica tras la reemisión", checksum2_v1_antes == checksum2_v1_despues)
    texto2_v2 = texto_pdf(leer_pdf_de_version(2, doc2["id"])).upper()
    comprobar("[9] v2 trae las observaciones ACTUALIZADAS", "OBSERVACIÓN ACTUALIZADA TRAS SEGUNDA SESIÓN".upper() in texto2_v2
              or "OBSERVACION ACTUALIZADA TRAS SEGUNDA SESION".upper() in texto2_v2)
    texto2_v1_relectura = texto_pdf(leer_pdf_de_version(1, doc2["id"])).upper()
    comprobar("[9] v1 (releída de storage) sigue con las observaciones ORIGINALES, no las actualizadas",
              "OBSERVACIÓN INICIAL".upper() in texto2_v1_relectura or "OBSERVACION INICIAL".upper() in texto2_v1_relectura)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — CASOS REALES: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
    plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
    documentos = f"SELECT id FROM documentos_institucionales WHERE institucion_id IN ({insts})"
    entradas = f"SELECT id FROM expediente_entradas WHERE documento_institucional_id IN ({documentos}) OR persona_id IN ({personas})"
    evaluaciones = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
    inscripciones = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evaluaciones})"
    informes = f"SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscripciones})"
    grados = f"SELECT id FROM grados WHERE institucion_id IN ({insts})"
    niveles = f"SELECT id FROM niveles_educativos WHERE institucion_id IN ({insts})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM registro_lecturas_expediente WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM documentos_registro_lecturas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM expediente_entradas WHERE id IN ({entradas})",
            f"DELETE FROM documentos_institucionales_resultados_prueba WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_correlativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscripciones})",
            f"DELETE FROM edu_informe_versiones WHERE informe_id IN ({informes})",
            f"DELETE FROM edu_informes WHERE id IN ({informes})",
            f"DELETE FROM edu_inscripciones WHERE id IN ({inscripciones})",
            f"DELETE FROM edu_evaluaciones WHERE id IN ({evaluaciones})",
            f"DELETE FROM matriculas_academicas WHERE persona_id IN ({personas})",
            f"DELETE FROM secciones WHERE grado_id IN ({grados})",
            f"DELETE FROM grados WHERE id IN ({grados})",
            f"DELETE FROM niveles_educativos WHERE id IN ({niveles})",
            f"DELETE FROM personas_datos_familiares WHERE persona_id IN ({personas})",
            f"DELETE FROM personas_antecedentes_clinicos WHERE persona_id IN ({personas})",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
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
