"""Verificación end-to-end del Expediente/Seguimiento del Estudiante:
CRUD de EntradaExpediente/EntradaExpedienteVersion, la regla de acceso
final, la auditoría automática de lecturas, ContactoFamiliar (soft-delete)
y AutorizacionAccesoColegio (otorgar/revocar, índice único parcial).

  1   Contactos familiares: crear, listar, editar, desactivar (soft-delete)
  2   Entradas narrativas: observacion_conducta / contacto_apoderado (con
      contacto_familiar_id) / derivacion — cada una crea su v1
  3   Validación de campos según tipo (422) antes de tocar la BD
  4   Entradas puente: 'sesion' (enlaza SesionSeguimiento real) y
      'aplicacion_prueba' (enlaza un Informe real) — nunca duplican
      contenido, y rechazan un enlace de OTRA persona (404)
  5   Regla de acceso final: autor / superadmin -> 200; admin -> 403;
      otro psicólogo (no autor) -> 403; colegio sin autorización -> 403
  6   Auditoría automática: cada lectura de contenido completo queda en
      RegistroLecturasExpediente, con autorizacion_acceso_colegio_id
      poblado solo cuando corresponde
  7   AutorizacionAccesoColegio: solo psicologo/superadmin otorgan/revocan;
      motivo obligatorio; el índice único parcial impide una segunda
      vigente sin revocar antes; revocar habilita otorgar una NUEVA (no
      reactiva la vieja)
  8   Versionado: agregar versión exige motivo_version; solo autor/
      superadmin; una versión anterior sigue leíble e intacta
  9   Aislamiento entre instituciones en cada endpoint nuevo
  10  No se modifican históricos: SesionSeguimiento/Informe intactos tras
      enlazarlos

    uvicorn main:app --port 8010          (SMTP deshabilitado)
    python -m tests.verificar_expediente_e2e
    python -m tests.verificar_expediente_e2e --limpiar
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

PREFIJO = "ZZEXP"
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

    h_autor = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.autor.{sello}@ejemplo.com", f"{PREFIJO} Autor", "psicologo", inst_a)
    h_otro_psi = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.otropsi.{sello}@ejemplo.com", f"{PREFIJO} OtroPsi", "psicologo", inst_a)
    h_admin = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com", f"{PREFIJO} Admin", "admin", inst_a)
    h_colegio = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegio.{sello}@ejemplo.com", f"{PREFIJO} Colegio", "colegio", inst_a)
    h_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.b.{sello}@ejemplo.com", f"{PREFIJO} B", "psicologo", inst_b)

    autor_id = sql_uno("SELECT id FROM auth_usuarios WHERE email=:e", e=f"{PREFIJO.lower()}.autor.{sello}@ejemplo.com").id

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h_autor, timeout=30), 200, "crear persona")
    persona_id = persona["id"]

    persona_b = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_b, "nombres": f"{PREFIJO} Alumno B", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h_b, timeout=30), 200, "crear persona B")
    persona_b_id = persona_b["id"]

    print("\n1 · ContactoFamiliar — CRUD + soft-delete")
    contacto = exigir(requests.post(f"{API}/admin/personas/{persona_id}/contactos", json={
        "nombre": "Madre de Prueba", "telefono": "999888777", "relacion": "madre", "email": "madre@ejemplo.com",
    }, headers=h_autor, timeout=30), 201, "crear contacto")
    contacto_id = contacto["id"]
    comprobar("[1] Contacto creado con activo=True", contacto["activo"] is True)

    r = requests.post(f"{API}/admin/personas/{persona_id}/contactos", json={"nombre": "X"}, headers=h_colegio, timeout=30)
    comprobar("[1] 'colegio' no puede crear contactos (403)", r.status_code == 403, f"status {r.status_code}")

    lista = exigir(requests.get(f"{API}/admin/personas/{persona_id}/contactos", headers=h_colegio, timeout=30), 200, "listar contactos (colegio)")
    comprobar("[1] 'colegio' SÍ puede leer contactos", len(lista) == 1)

    exigir(requests.patch(f"{API}/admin/personas/contactos/{contacto_id}", json={"telefono": "111222333"}, headers=h_autor, timeout=30), 200, "editar contacto")
    contacto_editado = sql_uno("SELECT telefono FROM contactos_familiares WHERE id=:c", c=contacto_id)
    comprobar("[1] Edición aplicada", contacto_editado.telefono == "111222333")

    exigir(requests.delete(f"{API}/admin/personas/contactos/{contacto_id}", headers=h_autor, timeout=30), 200, "desactivar contacto")
    fila_contacto = sql_uno("SELECT activo FROM contactos_familiares WHERE id=:c", c=contacto_id)
    comprobar("[1] Soft-delete: activo=False, la fila SIGUE existiendo (no se borró físicamente)", fila_contacto is not None and fila_contacto.activo is False)
    lista_por_defecto = exigir(requests.get(f"{API}/admin/personas/{persona_id}/contactos", headers=h_autor, timeout=30), 200, "listar sin inactivos")
    comprobar("[1] El listado por defecto ya no lo muestra", len(lista_por_defecto) == 0)
    lista_con_inactivos = exigir(requests.get(f"{API}/admin/personas/{persona_id}/contactos?incluir_inactivos=true", headers=h_autor, timeout=30), 200, "listar con inactivos")
    comprobar("[1] ?incluir_inactivos=true SÍ lo muestra", len(lista_con_inactivos) == 1)

    print("\n2 · Entradas narrativas (crean su v1 automáticamente)")
    entrada_obs = exigir(requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "observacion_conducta", "motivo": "Reporte de tutoría", "contenido": "Observación inicial detallada.",
        "interpretacion": "Interpretación clínica inicial.", "diagnostico_presuntivo": "Ninguno por ahora.",
    }, headers=h_autor, timeout=30), 201, "crear observación")
    entrada_obs_id = entrada_obs["id"]
    comprobar("[2] version_actual=1 al crear", entrada_obs["version_actual"] == 1)
    comprobar("[2] autor_usuario_id es quien la creó", entrada_obs["autor_usuario_id"] == autor_id)

    entrada_contacto = exigir(requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "contacto_apoderado", "contenido": "Llamada telefónica de seguimiento.",
        "contacto_familiar_id": contacto_id,
    }, headers=h_autor, timeout=30), 201, "crear contacto_apoderado")
    comprobar("[2] 'contacto_apoderado' referencia el contacto (aunque ya esté desactivado)", entrada_contacto["contacto_familiar_id"] == contacto_id)

    exigir(requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "derivacion", "motivo": "Derivación externa", "contenido": "Se deriva a psiquiatría.",
    }, headers=h_autor, timeout=30), 201, "crear derivación")

    print("\n3 · Validación de campos según tipo (422 antes de tocar la BD)")
    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={"tipo_entrada": "sesion"}, headers=h_autor, timeout=30)
    comprobar("[3] 'sesion' sin sesion_seguimiento_id -> 422", r.status_code == 422, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "observacion_conducta", "contenido": "x", "informe_id": 99999,
    }, headers=h_autor, timeout=30)
    comprobar("[3] 'observacion_conducta' con informe_id -> 422 (no es entrada puente)", r.status_code == 422, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={"tipo_entrada": "algo_inventado"}, headers=h_autor, timeout=30)
    comprobar("[3] tipo_entrada inválido -> 422 (Pydantic)", r.status_code == 422, f"status {r.status_code}")

    print("\n4 · Entradas puente: 'sesion' y 'aplicacion_prueba'")
    sesion = exigir(requests.post(f"{API}/educativo/seguimiento/", json={
        "persona_id": persona_id, "observaciones": "Sesión de seguimiento real.",
    }, headers=h_autor, timeout=30), 200, "crear sesión real")
    sesion_id = sesion["id"]
    entrada_sesion = exigir(requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "sesion", "sesion_seguimiento_id": sesion_id,
    }, headers=h_autor, timeout=30), 201, "enlazar sesión")
    entrada_sesion_id = entrada_sesion["id"]
    comprobar("[4] Entrada 'sesion' no tiene version_actual (nada propio que versionar)", entrada_sesion["version_actual"] is None)

    sesion_b = exigir(requests.post(f"{API}/educativo/seguimiento/", json={
        "persona_id": persona_b_id, "observaciones": "Sesión de B.",
    }, headers=h_b, timeout=30), 200, "crear sesión B")
    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "sesion", "sesion_seguimiento_id": sesion_b["id"],
    }, headers=h_autor, timeout=30)
    comprobar("[4] Enlazar una sesión de OTRA persona -> 404", r.status_code == 404, f"status {r.status_code}")

    # Generar un Informe real: prueba mínima likert_suma con 1 dimensión/1 pregunta.
    prueba = exigir(requests.post(f"{API}/educativo/pruebas/", json={
        "nombre_tecnico": f"{PREFIJO}_PRUEBA_{sello}", "nombre_publico": f"{PREFIJO} Prueba {sello}",
        "modo_calculo": "likert_suma", "escala_minima": 0, "escala_maxima": 3, "institucion_id": inst_a,
        "requiere_consentimiento": True,
    }, headers=h_autor, timeout=30), 200, "crear prueba mínima")
    prueba_id = prueba["id"]
    exigir(requests.post(f"{API}/educativo/pruebas/carga-masiva/", json={
        "prueba_id": prueba_id,
        "dimensiones": [{"nombre": "D1"}],
        "preguntas": [{"texto_pregunta": "P1", "orden": 1, "nombre_dimension": "D1", "opciones": [
            {"texto_opcion": "Nunca", "valor_puntuacion": 0}, {"texto_opcion": "Siempre", "valor_puntuacion": 3},
        ]}],
    }, headers=h_autor, timeout=30), 200, "carga masiva")
    detalle_prueba = exigir(requests.get(f"{API}/educativo/pruebas/{prueba_id}/completa", headers=h_autor, timeout=30), 200, "detalle prueba")
    dimension_id = detalle_prueba["dimensiones"][0]["id"]
    pregunta = detalle_prueba["dimensiones"][0]["preguntas"][0]
    opcion_id = pregunta["opciones"][0]["id"]
    exigir(requests.post(f"{API}/educativo/baremos/", json={
        "dimension_id": dimension_id, "puntaje_minimo": 0, "puntaje_maximo": 3, "nivel": "Bajo", "es_alerta": False,
    }, headers=h_autor, timeout=30), 200, "crear baremo")

    exigir(requests.post(f"{API}/admin/personas/{persona_id}/consentimiento", json={
        "persona_id": persona_id, "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado",
    }, headers=h_autor, timeout=30), 200, "consentimiento apoderado")

    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": prueba_id, "nombre_grupo": f"{PREFIJO} Campaña {sello}", "institucion_id": inst_a,
    }, headers=h_autor, timeout=30), 200, "crear campaña")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona_id], headers=h_autor, timeout=30), 200, "matricular")
    examen_token = matricula["generados"][0]["token"]
    exigir(requests.post(f"{API}/educativo/comenzar-test/{examen_token}", json={
        "nombre_completo": "Alumno Prueba", "edad": 15, "sexo": "Femenino", "poblacion": "Secundaria", "acepta_terminos": True,
    }, timeout=30), 200, "comenzar test")
    exigir(requests.post(f"{API}/educativo/examen/{examen_token}/guardar", json={
        "respuestas": [{"pregunta_id": pregunta["id"], "opcion_id": opcion_id}],
    }, timeout=30), 200, "guardar respuesta")
    exigir(requests.post(f"{API}/educativo/examen/{examen_token}/finalizar", timeout=60), 200, "finalizar examen")

    inscripcion_id = sql_uno("SELECT id FROM edu_inscripciones WHERE token=:t", t=examen_token).id
    informe_id = None
    limite = time.time() + 20
    while time.time() < limite and informe_id is None:
        fila_informe = sql_uno("SELECT id FROM edu_informes WHERE inscripcion_id=:i", i=inscripcion_id)
        if fila_informe:
            informe_id = fila_informe.id
        else:
            time.sleep(0.5)
    comprobar("[4] El informe se generó en segundo plano", informe_id is not None)

    entrada_prueba = exigir(requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "aplicacion_prueba", "informe_id": informe_id,
    }, headers=h_autor, timeout=30), 201, "enlazar informe")
    comprobar("[4] Entrada 'aplicacion_prueba' tampoco tiene version_actual", entrada_prueba["version_actual"] is None)

    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={
        "tipo_entrada": "aplicacion_prueba", "informe_id": informe_id + 999999,
    }, headers=h_autor, timeout=30)
    comprobar("[4] Un informe_id inexistente -> 404", r.status_code == 404, f"status {r.status_code}")

    print("\n5-6 · Regla de acceso final + auditoría automática de lectura")
    r_autor = exigir(requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_autor, timeout=30), 200, "autor lee")
    comprobar("[5] Autor ve el contenido completo", r_autor["version"]["contenido"] == "Observación inicial detallada.")

    exigir(requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_super, timeout=30), 200, "superadmin lee")

    r = requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_admin, timeout=30)
    comprobar("[5] 'admin' NO puede leer el contenido, ni siquiera de su propia institución (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_otro_psi, timeout=30)
    comprobar("[5] Otro psicólogo (no autor) NO puede leer (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_colegio, timeout=30)
    comprobar("[5] 'colegio' sin autorización NO puede leer (403)", r.status_code == 403, f"status {r.status_code}")

    n_lecturas = sql_uno("SELECT COUNT(*) AS n FROM registro_lecturas_expediente WHERE entrada_expediente_id=:e", e=entrada_obs_id).n
    comprobar("[6] Se auditaron exactamente 2 lecturas exitosas (autor + superadmin), ninguna de los 403", n_lecturas == 2, f"n={n_lecturas}")
    sin_autorizacion = sql_uno(
        "SELECT COUNT(*) AS n FROM registro_lecturas_expediente WHERE entrada_expediente_id=:e AND autorizacion_acceso_colegio_id IS NOT NULL",
        e=entrada_obs_id,
    ).n
    comprobar("[6] Ninguna de esas 2 lecturas dependió de una autorización de colegio", sin_autorizacion == 0)

    print("\n7 · AutorizacionAccesoColegio")
    r = requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={"motivo": "x"}, headers=h_admin, timeout=30)
    comprobar("[7] 'admin' no puede otorgar (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={"motivo": "x"}, headers=h_colegio, timeout=30)
    comprobar("[7] 'colegio' no puede otorgarse acceso a sí mismo (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={"motivo": "   "}, headers=h_autor, timeout=30)
    comprobar("[7] motivo vacío/solo espacios -> 422", r.status_code == 422, f"status {r.status_code}")

    autorizacion = exigir(requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={
        "motivo": "Solicitud formal de la dirección para revisión de caso.",
    }, headers=h_autor, timeout=30), 201, "otorgar autorización")
    autorizacion_id = autorizacion["id"]
    comprobar("[7] Autorización creada vigente=True", autorizacion["vigente"] is True)

    r_colegio_autorizado = exigir(requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_colegio, timeout=30), 200, "colegio lee autorizado")
    comprobar("[7] Con autorización vigente, 'colegio' SÍ ve el contenido completo", r_colegio_autorizado["version"]["contenido"] == "Observación inicial detallada.")

    fila_lectura_colegio = sql_uno(
        "SELECT autorizacion_acceso_colegio_id FROM registro_lecturas_expediente "
        "WHERE entrada_expediente_id=:e AND rol_lector='colegio' ORDER BY id DESC LIMIT 1", e=entrada_obs_id,
    )
    comprobar("[6] Esa lectura de colegio SÍ quedó apuntada a la autorización usada", fila_lectura_colegio.autorizacion_acceso_colegio_id == autorizacion_id)

    r = requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={"motivo": "Otra razón"}, headers=h_autor, timeout=30)
    comprobar("[7] Otorgar una SEGUNDA vigente sin revocar la anterior -> 409", r.status_code == 409, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/autorizacion-colegio/{autorizacion_id}/revocar", headers=h_admin, timeout=30)
    comprobar("[7] 'admin' no puede revocar (403)", r.status_code == 403, f"status {r.status_code}")

    revocada = exigir(requests.post(f"{API}/admin/personas/autorizacion-colegio/{autorizacion_id}/revocar", headers=h_autor, timeout=30), 200, "revocar")
    comprobar("[7] Queda vigente=False con fecha/usuario de revocación", revocada["vigente"] is False and revocada["revocado_por_usuario_id"] == autor_id)

    r = requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_colegio, timeout=30)
    comprobar("[7] Tras revocar, 'colegio' vuelve a 403", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/autorizacion-colegio/{autorizacion_id}/revocar", headers=h_autor, timeout=30)
    comprobar("[7] Revocar de nuevo la misma (ya revocada) -> 409", r.status_code == 409, f"status {r.status_code}")

    nueva_autorizacion = exigir(requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={
        "motivo": "Renovación tras revisión.",
    }, headers=h_autor, timeout=30), 201, "otorgar nueva tras revocar")
    comprobar("[7] Tras revocar, SÍ se puede otorgar una NUEVA (fila distinta, no reactiva la vieja)",
              nueva_autorizacion["id"] != autorizacion_id and nueva_autorizacion["vigente"] is True)
    historial_autorizaciones = exigir(requests.get(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", headers=h_admin, timeout=30), 200, "historial (admin puede ver estado)")
    comprobar("[7] El historial trae AMBAS filas (la vieja revocada + la nueva vigente)", len(historial_autorizaciones) == 2)

    print("\n8 · Versionado del contenido narrativo")
    r = requests.post(f"{API}/admin/personas/expediente/{entrada_obs_id}/versiones", json={
        "contenido": "Contenido corregido.",
    }, headers=h_autor, timeout=30)
    comprobar("[8] Agregar versión SIN motivo_version -> 422", r.status_code == 422, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/expediente/{entrada_obs_id}/versiones", json={
        "contenido": "Intento de otro psicólogo.", "motivo_version": "x",
    }, headers=h_otro_psi, timeout=30)
    comprobar("[8] Otro psicólogo (no autor) no puede agregar versión (403)", r.status_code == 403, f"status {r.status_code}")

    r = requests.post(f"{API}/admin/personas/expediente/{entrada_obs_id}/versiones", json={
        "contenido": "Intento de admin.", "motivo_version": "x",
    }, headers=h_admin, timeout=30)
    comprobar("[8] 'admin' no puede agregar versión (403, ni pasa del role gate)", r.status_code == 403, f"status {r.status_code}")

    v2 = exigir(requests.post(f"{API}/admin/personas/expediente/{entrada_obs_id}/versiones", json={
        "contenido": "Contenido corregido por el autor.", "motivo_version": "Se corrige una imprecisión.",
    }, headers=h_autor, timeout=30), 201, "agregar v2")
    comprobar("[8] Nueva versión es la v2", v2["numero_version"] == 2)

    detalle_v2 = exigir(requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_autor, timeout=30), 200, "leer vigente")
    comprobar("[8] La versión vigente ahora es la v2 con el contenido corregido", detalle_v2["version_actual"] == 2 and detalle_v2["version"]["contenido"] == "Contenido corregido por el autor.")

    detalle_v1 = exigir(requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}?version=1", headers=h_autor, timeout=30), 200, "leer v1 explícita")
    comprobar("[8] La v1 sigue leíble e INTACTA (contenido original, no sobrescrito)", detalle_v1["version"]["contenido"] == "Observación inicial detallada.")

    r = requests.post(f"{API}/admin/personas/expediente/{entrada_sesion_id}/versiones", json={
        "contenido": "x", "motivo_version": "x",
    }, headers=h_autor, timeout=30)
    comprobar("[8] No se puede versionar una entrada puente ('sesion') -> 400", r.status_code == 400, f"status {r.status_code}")

    print("\n9 · Aislamiento entre instituciones")
    r = requests.post(f"{API}/admin/personas/{persona_id}/expediente", json={"tipo_entrada": "derivacion", "contenido": "x"}, headers=h_b, timeout=30)
    comprobar("[9] B no puede crear una entrada sobre un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/admin/personas/{persona_id}/expediente", headers=h_b, timeout=30)
    comprobar("[9] B no puede listar el expediente de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.get(f"{API}/admin/personas/expediente/{entrada_obs_id}", headers=h_b, timeout=30)
    comprobar("[9] B no puede ver el detalle de una entrada de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/contactos", json={"nombre": "X"}, headers=h_b, timeout=30)
    comprobar("[9] B no puede crear contactos de un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")
    r = requests.post(f"{API}/admin/personas/{persona_id}/autorizacion-colegio", json={"motivo": "x"}, headers=h_b, timeout=30)
    comprobar("[9] B no puede otorgar acceso sobre un alumno de A (403)", r.status_code == 403, f"status {r.status_code}")

    print("\n10 · No se modifican históricos")
    sesion_tras = sql_uno("SELECT observaciones FROM edu_sesiones_seguimiento WHERE id=:s", s=sesion_id)
    comprobar("[10] SesionSeguimiento intacta tras enlazarla desde el expediente", sesion_tras.observaciones == "Sesión de seguimiento real.")
    informe_tras = sql_uno("SELECT version_actual FROM edu_informes WHERE id=:i", i=informe_id)
    comprobar("[10] Informe intacto (version_actual sigue en 1) tras enlazarlo desde el expediente", informe_tras.version_actual == 1)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E EXPEDIENTE: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    personas = f"SELECT id FROM personas WHERE institucion_id IN ({insts})"
    entradas = f"SELECT id FROM expediente_entradas WHERE persona_id IN ({personas})"
    autorizaciones = f"SELECT id FROM autorizaciones_acceso_colegio WHERE persona_id IN ({personas})"
    sesiones = f"SELECT id FROM edu_sesiones_seguimiento WHERE persona_id IN ({personas})"
    campanas = f"SELECT id FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%'"
    inscs = f"SELECT id FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})"
    informes = f"SELECT id FROM edu_informes WHERE inscripcion_id IN ({inscs})"
    pruebas = f"SELECT id FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%'"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM registro_lecturas_expediente WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM expediente_entradas_version WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM expediente_entradas WHERE id IN ({entradas})",
            f"DELETE FROM autorizaciones_acceso_colegio WHERE id IN ({autorizaciones})",
            f"DELETE FROM contactos_familiares WHERE persona_id IN ({personas})",
            f"DELETE FROM edu_diagnosticos_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_resultados_dimensiones WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_respuestas_alumno WHERE inscripcion_id IN ({inscs})",
            f"DELETE FROM edu_informe_versiones WHERE informe_id IN ({informes})",
            f"DELETE FROM edu_informes WHERE id IN ({informes})",
            f"DELETE FROM edu_inscripciones WHERE evaluacion_id IN ({campanas})",
            f"DELETE FROM edu_evaluaciones WHERE nombre_grupo LIKE '{PREFIJO}%'",
            f"DELETE FROM edu_baremos WHERE dimension_id IN (SELECT id FROM edu_dimensiones WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_opciones WHERE pregunta_id IN (SELECT id FROM edu_preguntas WHERE prueba_id IN ({pruebas}))",
            f"DELETE FROM edu_preguntas WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_dimensiones WHERE prueba_id IN ({pruebas})",
            f"DELETE FROM edu_pruebas WHERE nombre_tecnico LIKE '{PREFIJO}%'",
            f"DELETE FROM edu_sesiones_seguimiento WHERE id IN ({sesiones})",
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
        sys.exit(0)
    sys.exit(main(args.url))
