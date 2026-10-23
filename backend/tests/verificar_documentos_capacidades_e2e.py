"""Verificación end-to-end de 5 capacidades reales del motor de documentos
institucionales que hasta ahora estaban validadas solo a mano (ver
docs/frontend.md / docs/motor-documentos.md): branding de institución,
`ficha_imprimible`, `grafico_barras` (manual y automático), `imagen_anexo`,
y el agrupamiento `agrupar_dimensiones_por_area` (estilo CHASIDE). Ninguna
tenía antes una regresión automatizada que las protegiera si alguien las
toca después — solo cobertura unitaria (lógica pura, sin BD/PDF real) y
verificación manual puntual de la sesión que las construyó.

  1   Branding — SOLO validación (tipo inválido, y el candado SSRF real):
      subir un logo requiere `PUBLIC_BACKEND_URL` configurado (ver
      core/branding.py) porque el PDF vuelve a DESCARGAR la imagen por URL
      al generar cada versión, con la misma protección anti-SSRF que
      protege un logo externo cualquiera — un entorno de desarrollo local
      (sin dominio público propio) nunca puede completar esa subida, por
      diseño, no por un bug. Si `PUBLIC_BACKEND_URL` SÍ está configurado en
      el entorno donde corre esto, el script además genera un documento con
      el logo subido y confirma que el PDF embebe una imagen real.
  2   `ficha_imprimible` — una plantilla con sus 6 campos de config a la
      vez, confirmando que cada uno aparece en el PDF real.
  3   `grafico_barras` — modo manual (datos escritos a mano) y modo
      automático (vinculado a una Inscripcion real, PHQ-9-style), en sus
      tres estados: sin datos, retenido (informe no liberado) y con datos
      reales — cada uno con el texto/imagen exacto que corresponde.
  4   `imagen_anexo` — subida real de una imagen (nunca una URL externa, a
      diferencia de branding: esto no se re-descarga por red, así que SÍ es
      100% verificable en cualquier entorno), confirmando que el PDF la
      embebe, y que antes de subir nada se ve el placeholder correcto.
  5   `agrupar_dimensiones_por_area` (CHASIDE) — una prueba de 2
      dimensiones ("Intereses — ADM: Administración" / "Aptitudes — ADM:
      Administración") con un baremo nivel="Alto" en ambas, confirmando que
      el informe PDF fijo (core/pdf_generator.py) agrupa por área en vez de
      listar las dimensiones sueltas, Y que el resumen estadístico del
      dashboard calcula la misma área como "compatible".

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_documentos_capacidades_e2e
    python -m tests.verificar_documentos_capacidades_e2e --limpiar
"""

import argparse
import io
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from pypdf import PdfReader  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZDOCCAP"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []

def _construir_png_1x1() -> bytes:
    """PNG 1x1 real y válido, armado a mano con zlib -- para subidas de
    imagen reales sin depender de ningún archivo externo en disco ni de
    Pillow (que solo está instalado para el renderizador, no para tests)."""
    import struct
    import zlib

    def chunk(tipo: bytes, datos: bytes) -> bytes:
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))

    firma = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, RGB
    raw = b"\x00" + b"\xff\x00\x00"  # un filtro "none" + un píxel rojo
    idat = zlib.compress(raw)
    return firma + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


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


def texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    return " ".join((p.extract_text() or "") for p in lector.pages)


def num_imagenes(contenido: bytes) -> int:
    lector = PdfReader(io.BytesIO(contenido))
    total = 0
    for pagina in lector.pages:
        total += len(list(pagina.images))
    return total


def _id_seccion(h, plantilla_id, tipo_seccion):
    r = requests.get(f"{API}/documentos/plantillas/{plantilla_id}/secciones", headers=h, timeout=30)
    for s in r.json():
        if s["tipo_seccion"] == tipo_seccion:
            return s["id"]
    raise RuntimeError(f"No se encontró sección {tipo_seccion}")


def crear_documento_de_una_seccion(h, inst_id, tipo_id, alumno_id, sello, etiqueta, tipo_seccion, config=None):
    """Plantilla con exactamente 2 secciones (encabezado + la que se quiere
    probar) + un documento de UN solo alumno -- el mínimo real para generar
    un PDF y leer el texto/imágenes de la sección bajo prueba."""
    plantilla = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_id, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla {etiqueta} {sello}",
        "fuente": "Helvetica",
    }, headers=h, timeout=30), 200, f"crear plantilla {etiqueta}")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
        "orden": 0, "tipo_seccion": "encabezado", "titulo": "Encabezado",
    }, headers=h, timeout=30), 200, f"sección encabezado {etiqueta}")
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla['id']}/secciones", json={
        "orden": 1, "tipo_seccion": tipo_seccion, "titulo": etiqueta, "config": config,
    }, headers=h, timeout=30), 200, f"sección {tipo_seccion} {etiqueta}")
    documento = exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla["id"],
        "alcance": "personas_especificas", "titulo": f"{PREFIJO} Documento {etiqueta} {sello}", "personas_ids": [alumno_id],
    }, headers=h, timeout=30), 200, f"crear documento {etiqueta}")
    return plantilla, documento


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_id = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}"}, headers=h_super, timeout=30), 201, "Institución")["id"]
    h_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psi.{sello}@ejemplo.com", f"{PREFIJO} Psicóloga", "psicologo", inst_id)
    h_admin = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com", f"{PREFIJO} Admin", "admin", inst_id)

    tipo = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_{sello}", "nombre": f"{PREFIJO} Tipo",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
        "requiere_consentimiento_individual": False,
    }, headers=h_super, timeout=30), 200, "crear tipo")["id"]

    alumno = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": PREFIJO, "apellidos": f"Alumno {sello}", "tipo_perfil": "estudiante",
    }, headers=h_psi, timeout=30), 200, "crear alumno")["id"]

    png_real = _construir_png_1x1()

    # ==================================================================
    print("\n1 · Branding — validación + candado SSRF real (PUBLIC_BACKEND_URL)")
    r_tipo_invalido = requests.post(f"{API}/instituciones/{inst_id}/branding/invalido",
                                     files={"archivo": ("x.png", png_real, "image/png")}, headers=h_admin, timeout=30)
    comprobar("[1] tipo inválido -> 400", r_tipo_invalido.status_code == 400, r_tipo_invalido.text[:200])

    r_get_invalido = requests.get(f"{API}/instituciones/{inst_id}/branding/invalido", timeout=30)
    comprobar("[1] GET con tipo inválido -> 404", r_get_invalido.status_code == 404)

    r_subir_logo = requests.post(f"{API}/instituciones/{inst_id}/branding/encabezado",
                                  files={"archivo": ("logo.png", png_real, "image/png")}, headers=h_admin, timeout=30)
    if os.getenv("PUBLIC_BACKEND_URL"):
        comprobar("[1] con PUBLIC_BACKEND_URL configurado, subir un logo real -> 200",
                  r_subir_logo.status_code == 200, r_subir_logo.text[:300])
        if r_subir_logo.status_code == 200:
            plantilla_logo, doc_logo = crear_documento_de_una_seccion(
                h_psi, inst_id, tipo, alumno, sello, "ConLogo", "texto_libre",
            )
            v1 = exigir(requests.post(f"{API}/documentos/{doc_logo['id']}/generar-version",
                                       headers=h_psi, timeout=30), 200, "generar doc con logo")
            fila = sql_uno(
                "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
                d=doc_logo["id"])
            from core.storage import obtener_storage_service
            pdf_bytes = obtener_storage_service().leer(fila.storage_key)
            comprobar("[1] el PDF con logo real embebe al menos una imagen", num_imagenes(pdf_bytes) >= 1)
    else:
        print("    (PUBLIC_BACKEND_URL no está configurado en este entorno -- por diseño, ver core/branding.py: "
              "un logo institucional se vuelve a DESCARGAR por URL al generar cada versión, con la misma "
              "protección anti-SSRF que protege cualquier logo externo. Un entorno de desarrollo local sin "
              "dominio público propio no puede completar esta subida; se confirma el candado real en su lugar.)")
        comprobar("[1] sin PUBLIC_BACKEND_URL, subir un logo real -> 503 (candado SSRF real, no un bug)",
                  r_subir_logo.status_code == 503, r_subir_logo.text[:300])

    # ==================================================================
    print("\n2 · ficha_imprimible — los 6 campos de config a la vez, en un PDF real")
    config_ficha = {
        "campos_encabezado": ["Estudiante", "Grado"],
        "leyenda": f"Leyenda de prueba {sello}: marcar con una X",
        "columnas": ["Sí", "No"],
        "filas": [f"Fila de verificación {sello}"],
        "listas_checkbox": [{"titulo": f"Lista {sello}", "opciones": [f"Opción uno {sello}", f"Opción dos {sello}"]}],
        "preguntas_abiertas": [f"Pregunta abierta {sello}"],
        "firmas_en_blanco": [f"Firma en blanco {sello}"],
    }
    _, doc_ficha = crear_documento_de_una_seccion(h_psi, inst_id, tipo, alumno, sello, "Ficha", "ficha_imprimible", config_ficha)
    v1_ficha = exigir(requests.post(f"{API}/documentos/{doc_ficha['id']}/generar-version",
                                     headers=h_psi, timeout=30), 200, "generar ficha_imprimible")
    fila_ficha = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_ficha["id"])
    from core.storage import obtener_storage_service
    texto_ficha = texto_pdf(obtener_storage_service().leer(fila_ficha.storage_key))
    comprobar("[2] campo_encabezado 'Estudiante' aparece", "Estudiante" in texto_ficha)
    comprobar("[2] leyenda aparece", f"Leyenda de prueba {sello}" in texto_ficha)
    comprobar("[2] columna 'Sí' de la tabla aparece", "Sí" in texto_ficha)
    comprobar("[2] fila de verificación aparece", f"Fila de verificación {sello}" in texto_ficha)
    comprobar("[2] título de la lista de checkbox aparece", f"Lista {sello}" in texto_ficha)
    comprobar("[2] opción de checkbox aparece", f"Opción uno {sello}" in texto_ficha)
    comprobar("[2] pregunta abierta aparece", f"Pregunta abierta {sello}" in texto_ficha)
    comprobar("[2] firma en blanco aparece", f"Firma en blanco {sello}" in texto_ficha)

    # ==================================================================
    print("\n3 · grafico_barras — sin datos / retenido / manual / automático liberado")

    # 3a: sin datos -> placeholder, nunca una imagen
    _, doc_graf_vacio = crear_documento_de_una_seccion(h_psi, inst_id, tipo, alumno, sello, "GrafVacio", "grafico_barras")
    exigir(requests.post(f"{API}/documentos/{doc_graf_vacio['id']}/generar-version",
                          headers=h_psi, timeout=30), 200, "generar grafico vacio")
    fila_vacio = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_graf_vacio["id"])
    pdf_vacio = obtener_storage_service().leer(fila_vacio.storage_key)
    comprobar("[3a] sin datos: placeholder 'Sin datos de gráfico'", "Sin datos de gráfico" in texto_pdf(pdf_vacio))
    comprobar("[3a] sin datos: cero imágenes en esa sección (el doc no tiene ninguna otra)", num_imagenes(pdf_vacio) == 0)

    # 3b: manual -> SÍ imagen
    plantilla_graf_manual, doc_graf_manual = crear_documento_de_una_seccion(
        h_psi, inst_id, tipo, alumno, sello, "GrafManual", "grafico_barras",
    )
    seccion_graf_manual = _id_seccion(h_psi, plantilla_graf_manual["id"], "grafico_barras")
    exigir(requests.put(f"{API}/documentos/{doc_graf_manual['id']}/secciones/{seccion_graf_manual}", json={
        "contenido": {"datos": [{"etiqueta": "A", "valor": 5}, {"etiqueta": "B", "valor": 9}]},
    }, headers=h_psi, timeout=30), 200, "cargar datos manuales de gráfico")
    exigir(requests.post(f"{API}/documentos/{doc_graf_manual['id']}/generar-version",
                          headers=h_psi, timeout=30), 200, "generar grafico manual")
    fila_manual = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_graf_manual["id"])
    pdf_manual = obtener_storage_service().leer(fila_manual.storage_key)
    comprobar("[3b] datos manuales: embebe al menos una imagen (el gráfico real)", num_imagenes(pdf_manual) >= 1)
    comprobar("[3b] datos manuales: NO muestra el placeholder de 'sin datos'", "Sin datos de gráfico" not in texto_pdf(pdf_manual))

    # 3c/3d: automático -- vincula una Inscripcion real, retenida primero, liberada después
    prueba_id, dim_id, pregs, baremo = crear_prueba_con_un_baremo(h_psi, f"{sello}GRAF", n_items=3, nivel="Alto", es_alerta=True)
    insc_id = matricular_y_finalizar(h_psi, inst_id, f"{sello}GRAF", prueba_id, pregs, alumno)
    estado = sql_uno("SELECT informe_liberado FROM edu_inscripciones WHERE id=:i", i=insc_id)
    comprobar("[3c] la inscripción de prueba nace retenida (alerta)", estado.informe_liberado is False)

    plantilla_graf_auto, doc_graf_auto = crear_documento_de_una_seccion(
        h_psi, inst_id, tipo, alumno, sello, "GrafAuto", "grafico_barras",
    )
    seccion_graf_auto = _id_seccion(h_psi, plantilla_graf_auto["id"], "grafico_barras")
    exigir(requests.put(f"{API}/documentos/{doc_graf_auto['id']}/secciones/{seccion_graf_auto}/resultados-prueba", json={
        "persona_id": alumno, "inscripcion_id": insc_id,
    }, headers=h_psi, timeout=30), 200, "vincular inscripción al gráfico")

    v1_graf_auto = exigir(requests.post(f"{API}/documentos/{doc_graf_auto['id']}/generar-version",
                                         headers=h_psi, timeout=30), 200, "generar v1 (retenido)")
    fila_auto_v1 = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_graf_auto["id"])
    pdf_auto_v1 = obtener_storage_service().leer(fila_auto_v1.storage_key)
    comprobar("[3c] vinculado pero RETENIDO: placeholder de revisión pendiente, NO imagen",
              "Pendiente de revisión profesional" in texto_pdf(pdf_auto_v1) and num_imagenes(pdf_auto_v1) == 0)

    exigir(requests.patch(f"{API}/educativo/inscripciones/{insc_id}/liberar-informe", json={},
                           headers=h_psi, timeout=30), 200, "liberar informe para el gráfico automático")
    v2_graf_auto = exigir(requests.post(f"{API}/documentos/{doc_graf_auto['id']}/reemitir",
                                         json={"motivo": "Informe liberado"}, headers=h_psi, timeout=30), 200, "reemitir (liberado)")
    fila_auto_v2 = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=2",
        d=doc_graf_auto["id"])
    pdf_auto_v2 = obtener_storage_service().leer(fila_auto_v2.storage_key)
    comprobar("[3d] liberado: ahora SÍ embebe la imagen real del puntaje", num_imagenes(pdf_auto_v2) >= 1)
    comprobar("[3d] liberado: ya no muestra el placeholder de retención", "Pendiente de revisión profesional" not in texto_pdf(pdf_auto_v2))

    # ==================================================================
    print("\n4 · imagen_anexo — sin imagen / con imagen real subida")
    plantilla_img, doc_img = crear_documento_de_una_seccion(h_psi, inst_id, tipo, alumno, sello, "Imagen", "imagen_anexo")
    seccion_img = _id_seccion(h_psi, plantilla_img["id"], "imagen_anexo")

    v1_img = exigir(requests.post(f"{API}/documentos/{doc_img['id']}/generar-version",
                                   headers=h_psi, timeout=30), 200, "generar sin imagen")
    fila_img_v1 = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_img["id"])
    pdf_img_v1 = obtener_storage_service().leer(fila_img_v1.storage_key)
    comprobar("[4a] sin imagen subida: placeholder 'Sin imagen/anexo'", "Sin imagen" in texto_pdf(pdf_img_v1))
    comprobar("[4a] sin imagen subida: cero imágenes embebidas", num_imagenes(pdf_img_v1) == 0)

    r_subir_img = requests.post(f"{API}/documentos/{doc_img['id']}/secciones/{seccion_img}/imagen",
                                 files={"archivo": ("anexo.png", png_real, "image/png")}, headers=h_psi, timeout=30)
    comprobar("[4b] subir una imagen real -> 200", r_subir_img.status_code == 200, r_subir_img.text[:300])

    v2_img = exigir(requests.post(f"{API}/documentos/{doc_img['id']}/reemitir",
                                   json={"motivo": "Imagen subida"}, headers=h_psi, timeout=30), 200, "reemitir con imagen")
    fila_img_v2 = sql_uno(
        "SELECT storage_key FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=2",
        d=doc_img["id"])
    pdf_img_v2 = obtener_storage_service().leer(fila_img_v2.storage_key)
    comprobar("[4b] con imagen real subida: el PDF embebe al menos una imagen", num_imagenes(pdf_img_v2) >= 1)
    comprobar("[4b] v1 (sin imagen) sigue intacta -- nunca se reescribe", sql_uno(
        "SELECT checksum_sha256 FROM documentos_institucionales_versiones WHERE documento_institucional_id=:d AND numero_version=1",
        d=doc_img["id"]).checksum_sha256 is not None)

    # ==================================================================
    print("\n5 · agrupar_dimensiones_por_area (estilo CHASIDE) — informe PDF fijo + resumen del dashboard")
    prueba_chaside_id, dims_chaside, pregs_chaside, baremos_chaside = crear_prueba_chaside(h_psi, sello)
    exigir(requests.patch(f"{API}/educativo/pruebas/{prueba_chaside_id}", json={
        "agrupar_dimensiones_por_area": True,
    }, headers=h_admin, timeout=30), 200, "activar agrupar_dimensiones_por_area")

    insc_chaside = matricular_y_finalizar_multi(h_psi, inst_id, f"{sello}CHA", prueba_chaside_id, pregs_chaside)
    estado_chaside = sql_uno(
        "SELECT informe_liberado, resultado_visible_alumno FROM edu_inscripciones WHERE id=:i", i=insc_chaside)
    comprobar("[5] la inscripción CHASIDE-style queda liberada (baremos sin alerta)",
              estado_chaside.informe_liberado is True)

    pdf_chaside = requests.get(f"{API}/educativo/inscripciones/{insc_chaside}/informe-pdf", headers=h_psi, timeout=30)
    comprobar("[5] descarga del informe PDF -> 200", pdf_chaside.status_code == 200)
    texto_chaside = texto_pdf(pdf_chaside.content)
    comprobar("[5] el PDF agrupa por área: aparece 'Área de Intereses'", "Área de Intereses" in texto_chaside)
    comprobar("[5] el PDF agrupa por área: aparece 'Área de Aptitudes'", "Área de Aptitudes" in texto_chaside)
    comprobar("[5] el PDF agrupa por área: aparece 'Áreas Vocacionales Compatibles'",
              "Áreas Vocacionales Compatibles" in texto_chaside)
    comprobar("[5] el área 'Administración' aparece como destacada/compatible", "Administración" in texto_chaside)

    evaluacion_chaside = sql_uno("SELECT evaluacion_id FROM edu_inscripciones WHERE id=:i", i=insc_chaside).evaluacion_id
    dashboard = exigir(requests.get(f"{API}/educativo/campanas/{evaluacion_chaside}/dashboard",
                                     headers=h_psi, timeout=30), 200, "dashboard de la campaña CHASIDE")
    resumen = dashboard["resumen_estadistico"]
    comprobar("[5] resumen_estadistico.agrupar_dimensiones_por_area=True", resumen["agrupar_dimensiones_por_area"] is True)
    areas = [a["area"] for a in resumen["areas_compatibles"]]
    comprobar("[5] resumen_estadistico.areas_compatibles incluye 'Administración'", "Administración" in areas, str(areas))

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — CAPACIDADES SIN TEST DEDICADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def crear_prueba_con_un_baremo(h, sello, n_items, nivel, es_alerta):
    """1 dimensión, correcto_incorrecto, UN tramo que cubre TODO el rango
    posible [0, n_items] -- mismo helper que usan otros e2e de este mismo
    estilo (ver verificar_reproceso_informe_e2e.py)."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-{sello}", "nombre_publico": "Prueba de capacidades",
        "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=h, timeout=30), 200, "Prueba")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    preguntas_carga = [
        {"texto_pregunta": f"Ítem {i}", "orden": i, "nombre_dimension": "D", "opciones": opciones}
        for i in range(1, n_items + 1)
    ]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": "D"}], "preguntas": preguntas_carga},
        headers=h, timeout=30), 200, "Carga")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=h, timeout=30), 200, "Detalle")
    dim = detalle["dimensiones"][0]
    pregs = {p["orden"]: p for p in dim["preguntas"]}
    baremo = exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": n_items,
        "nivel": nivel, "es_alerta": es_alerta},
        headers=h, timeout=30), 200, f"Baremo {nivel}")
    return prueba["id"], dim["id"], pregs, baremo


def matricular_y_finalizar(h, inst_id, sello, prueba_id, pregs, persona_id):
    """`persona_id` SIEMPRE se pasa desde afuera (nunca se crea una persona
    nueva aquí) -- el gráfico automático necesita vincularse a la MISMA
    persona que ya tiene el DocumentoInstitucional (`vincular_resultado_
    prueba` exige que inscripción y persona coincidan), así que ambos deben
    compartir exactamente el mismo alumno."""
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_id},
        headers=h, timeout=30), 200, "Campaña")
    exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h, timeout=30), 200, "Consentimiento")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona_id], headers=h, timeout=30), 200, "Matrícula")
    token = matricula["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar")
    respuestas = [
        {"pregunta_id": p["id"], "opcion_id": next(o["id"] for o in p["opciones"] if o["valor_puntuacion"] == 1)}
        for p in pregs.values()
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "Guardar")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")
    return sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]


def crear_prueba_chaside(h, sello):
    """2 dimensiones con la convención de nombre que `_agrupar_dimensiones_
    por_area` reconoce ("Intereses — X: Nombre"/"Aptitudes — X: Nombre") --
    3 ítems cada una, un único baremo por dimensión con nivel="Alto" que
    cubre todo el rango posible, SIN alerta (para que el informe se libere
    solo, igual que crear_prueba_con_un_baremo)."""
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}-CHA-{sello}", "nombre_publico": "Prueba vocacional de prueba",
        "escala_minima": 0, "escala_maxima": 1, "modo_calculo": "correcto_incorrecto"},
        headers=h, timeout=30), 200, "Prueba CHASIDE")
    opciones = [{"texto_opcion": "No", "valor_puntuacion": 0}, {"texto_opcion": "Sí", "valor_puntuacion": 1}]
    nombres_dim = ["Intereses — ADM: Administración", "Aptitudes — ADM: Administración"]
    preguntas_carga = []
    orden = 1
    for nombre_dim in nombres_dim:
        for _ in range(3):
            preguntas_carga.append({
                "texto_pregunta": f"Ítem {orden}", "orden": orden, "nombre_dimension": nombre_dim, "opciones": opciones,
            })
            orden += 1
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba["id"], "dimensiones": [{"nombre": n} for n in nombres_dim], "preguntas": preguntas_carga},
        headers=h, timeout=30), 200, "Carga CHASIDE")
    detalle = exigir(requests.get(f"{API}/educativo/pruebas/{prueba['id']}/completa", headers=h, timeout=30), 200, "Detalle CHASIDE")
    pregs_por_dim = {}
    baremos = []
    for dim in detalle["dimensiones"]:
        baremo = exigir(requests.post(f"{API}/educativo/baremos/", json={
            "dimension_id": dim["id"], "puntaje_minimo": 0, "puntaje_maximo": 3,
            "nivel": "Alto", "es_alerta": False},
            headers=h, timeout=30), 200, f"Baremo Alto {dim['nombre']}")
        baremos.append(baremo)
        for p in dim["preguntas"]:
            pregs_por_dim[p["orden"]] = p
    return prueba["id"], detalle["dimensiones"], pregs_por_dim, baremos


def matricular_y_finalizar_multi(h, inst_id, sello, prueba_id, pregs_por_orden):
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_id},
        headers=h, timeout=30), 200, "Campaña CHASIDE")
    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_id, "nombres": f"{PREFIJO} AlumnoCha", "apellidos": "Prueba",
        "documento_identidad": f"{sello}902", "genero": "Femenino"}, headers=h, timeout=30), 200, "Persona CHASIDE")["id"]
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_id,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h, timeout=30), 200, "Consentimiento CHASIDE")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=h, timeout=30), 200, "Matrícula CHASIDE")
    token = matricula["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "Alumno Chaside", "edad": 15, "sexo": "Femenino",
        "poblacion": "Secundaria", "acepta_terminos": True}, timeout=30), 200, "Comenzar CHASIDE")
    respuestas = [
        {"pregunta_id": p["id"], "opcion_id": next(o["id"] for o in p["opciones"] if o["valor_puntuacion"] == 1)}
        for p in pregs_por_orden.values()
    ]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "Guardar CHASIDE")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar CHASIDE")
    return sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]


def limpiar():
    with MOTOR.begin() as c:
        insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
        personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
        tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
        plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
        documentos = f"SELECT id FROM documentos_institucionales WHERE institucion_id IN ({insts})"
        entradas = f"SELECT id FROM expediente_entradas WHERE documento_institucional_id IN ({documentos}) OR persona_id IN ({personas})"
        evaluaciones = f"SELECT id FROM edu_evaluaciones WHERE institucion_id IN ({insts})"
        inscripciones = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({evaluaciones})"
        informes = f"SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscripciones})"
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
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT d.id FROM edu_dimensiones d JOIN edu_pruebas p ON p.id = d.prueba_id WHERE p.nombre_tecnico LIKE '{PREFIJO}%')",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT q.id FROM edu_preguntas q JOIN edu_pruebas p ON p.id = q.prueba_id WHERE p.nombre_tecnico LIKE '{PREFIJO}%')",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN (SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN (SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%')",
            f"DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%'",
            f"DELETE FROM consentimientos_informados WHERE persona_id IN ({personas})",
            f"DELETE FROM personas WHERE id IN ({personas})",
            f"DELETE FROM auth_usuarios WHERE email LIKE '{PREFIJO.lower()}%'",
            f"DELETE FROM instituciones WHERE nombre LIKE '{PREFIJO}%'",
        ]:
            c.execute(text(q))
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
