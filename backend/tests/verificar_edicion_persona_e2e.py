"""Verificación end-to-end — PASO 3 (auditoría de arquitectura genérica):
PersonaUpdate ahora admite nombres/apellidos/fecha_nacimiento/documento_identidad.

Cubre exactamente lo pedido:
  1. Un psicólogo (no admin, no superadmin) puede editar estos 4 campos de un
     estudiante de SU institución — sin ningún cambio de permisos: el mismo
     candado de institución que ya regía para genero/email.
  2. Un psicólogo de OTRA institución sigue sin poder tocarlo (403).
  3. Editar estos 4 campos DESPUÉS de que el estudiante ya rindió y tiene un
     informe emitido NO altera ningún snapshot histórico: ni
     Inscripcion.nombre_completo/edad/sexo, ni DiagnosticoAlumno, ni el PDF
     ya generado (InformeVersion.resultados_snapshot / storage).

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_edicion_persona_e2e.py
    python tests/verificar_edicion_persona_e2e.py --limpiar
"""

import argparse
import io
import os
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

PREFIJO = "ZZEDITP"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, endpoint="", detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else "") + (f"   [{endpoint}]" if endpoint else ""))
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


def texto_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    texto_crudo = "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    return " ".join(texto_crudo.split())


def crear_colegio_con_psicologo(h_super, letra, sello):
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {letra} {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{letra.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, f"Institución {letra}")
    correo = f"{PREFIJO.lower()}.psi.{letra.lower()}.{sello}@ejemplo.com"
    # rol "psicologo" A PROPÓSITO: lo que este test verifica es que ESTE rol
    # (no admin, no superadmin) ya puede editar estos 4 campos.
    exigir(pedir(requests.post, f"{API}/auth/registro", f"registro {letra}", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Psicólogo {letra}",
        "rol": "psicologo", "institucion_id": inst["id"]}, headers=h_super), 200, f"Registro {letra}")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, f"Login {letra}")["access_token"]
    return inst["id"], {"Authorization": f"Bearer {tok}"}


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    print("\n0 · Montaje: dos instituciones, cada una con un usuario 'psicologo' (no admin)")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst_a, h_a = crear_colegio_con_psicologo(h_super, "A", sello)
    inst_b, h_b = crear_colegio_con_psicologo(h_super, "B", sello)

    persona = exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": inst_a, "nombres": "Nombre Original", "apellidos": "Apellido Original",
        "documento_identidad": f"{sello}ORIG", "fecha_nacimiento": "2011-04-10", "genero": "Femenino"},
        headers=h_a, timeout=30), 200, "Crear persona")["id"]

    # ==================================================================
    print("\n1 · Aplicación real completa (para poder probar snapshots después)")
    exigir(requests.post(f"{API}/admin/personas/{persona}/consentimiento", json={
        "persona_id": persona, "institucion_id": inst_a,
        "otorgado_por_nombre": "Apoderado de prueba", "tipo_otorgante": "apoderado"}, headers=h_a, timeout=30), 200, "Consentimiento")

    phq9_id = sql_uno("select id from edu_pruebas where nombre_tecnico = 'PHQ-9' and institucion_id is null")[0]
    campana = exigir(requests.post(f"{API}/educativo/campanas/", json={
        "prueba_id": phq9_id, "nombre_grupo": f"{PREFIJO} {sello}", "institucion_id": inst_a},
        headers=h_a, timeout=30), 200, "Campaña")
    matricula = exigir(requests.post(f"{API}/educativo/campanas/{campana['id']}/matricular-roster",
                                     json=[persona], headers=h_a, timeout=30), 200, "Matrícula")
    token = matricula["generados"][0]["token"]

    exigir(requests.post(f"{API}/educativo/comenzar-test/{token}", json={
        "nombre_completo": "x", "edad": 1, "sexo": "Masculino", "poblacion": "Universitario",
        "acepta_terminos": True}, timeout=30), 200, "Comenzar")

    detalle_phq9 = exigir(requests.get(f"{API}/educativo/pruebas/{phq9_id}/completa", headers=h_a, timeout=30), 200, "Detalle PHQ-9")
    preg_phq9 = {p["orden"]: p for p in detalle_phq9["dimensiones"][0]["preguntas"]}

    def opcion_id(orden, valor):
        return next(o["id"] for o in preg_phq9[orden]["opciones"] if o["valor_puntuacion"] == valor)

    respuestas = [{"pregunta_id": preg_phq9[i + 1]["id"], "opcion_id": opcion_id(i + 1, 0)} for i in range(9)]
    exigir(requests.post(f"{API}/educativo/examen/{token}/guardar", json={"respuestas": respuestas}, timeout=30), 200, "Guardar")
    exigir(requests.post(f"{API}/educativo/examen/{token}/finalizar", timeout=60), 200, "Finalizar")

    insc_id = sql_uno("select id from edu_inscripciones where token=:t", t=token)[0]

    # Se espera a que la METADATA confirme que ya existe una InformeVersion
    # ALMACENADA (no basta con que el PDF sea descargable: justo después de
    # finalizar, informe-pdf puede caer todavía en el fallback "generado al
    # vuelo" — ver router.py:385-399 — que produce un PDF con el mismo
    # contenido pero distinto en bytes al que luego queda en storage. Sin
    # esta espera, comparar checksums más abajo compararía dos renders
    # distintos por una carrera de tiempo, no por un problema real).
    limite = time.time() + 20
    informe_meta = None
    while time.time() < limite:
        informe_meta = requests.get(f"{API}/educativo/inscripciones/{insc_id}/informe", headers=h_a, timeout=30)
        if informe_meta.status_code == 200 and informe_meta.json().get("existe"):
            break
        time.sleep(0.5)
    comprobar("[montaje] La InformeVersion queda almacenada (no solo generada al vuelo)",
              informe_meta is not None and informe_meta.status_code == 200 and informe_meta.json().get("existe"))

    r_pdf_original = requests.get(f"{API}/educativo/examen/{token}/informe-pdf", timeout=60)
    comprobar("[montaje] El informe (sin alerta, PHQ-9 en 0) se generó y es descargable", r_pdf_original.status_code == 200)
    texto_original = texto_pdf(r_pdf_original.content)
    comprobar("[montaje] El PDF original contiene el nombre ORIGINAL", "Nombre Original" in texto_original)

    snapshot_antes = sql_uno(
        "select nombre_completo, edad, sexo from edu_inscripciones where id=:i", i=insc_id)
    diag_antes = sql_uno(
        "select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_id)

    # ==================================================================
    print("\n2 · Un psicólogo (NO admin) edita los 4 campos — sin ningún cambio de permisos")
    r_editar = requests.patch(f"{API}/admin/personas/{persona}", json={
        "nombres": "Nombre Corregido", "apellidos": "Apellido Corregido",
        "fecha_nacimiento": "2011-05-20", "documento_identidad": f"{sello}CORREGIDO",
    }, headers=h_a, timeout=30)
    comprobar("[1] Un usuario con rol 'psicologo' puede editar los 4 campos nuevos (200)",
              r_editar.status_code == 200, "PATCH /api/admin/personas/{id}", r_editar.text[:300])
    persona_editada = r_editar.json()
    comprobar("[1] La respuesta refleja los 4 valores nuevos",
              persona_editada["nombres"] == "Nombre Corregido" and persona_editada["apellidos"] == "Apellido Corregido"
              and persona_editada["documento_identidad"] == f"{sello}CORREGIDO", str(persona_editada))

    fila_bd = sql_uno("select nombres, apellidos, documento_identidad, fecha_nacimiento from personas where id=:i", i=persona)
    comprobar("[1] La fila real en BD quedó con los 4 valores nuevos",
              fila_bd[0] == "Nombre Corregido" and fila_bd[1] == "Apellido Corregido" and fila_bd[2] == f"{sello}CORREGIDO")

    # ==================================================================
    print("\n2b · Un psicólogo de OTRA institución sigue sin poder tocarlo")
    r_cruzado = requests.patch(f"{API}/admin/personas/{persona}", json={
        "nombres": "Intento Cruzado"}, headers=h_b, timeout=30)
    comprobar("[2] B no puede editar un estudiante de A (403) — mismo candado de siempre, sin cambios",
              r_cruzado.status_code == 403, "PATCH /api/admin/personas/{id}")

    # ==================================================================
    print("\n3 · Ningún snapshot histórico se vio afectado")
    snapshot_despues = sql_uno(
        "select nombre_completo, edad, sexo from edu_inscripciones where id=:i", i=insc_id)
    comprobar("[3] Inscripcion.nombre_completo/edad/sexo NO cambiaron tras editar la Persona",
              snapshot_antes == snapshot_despues, f"antes={snapshot_antes} despues={snapshot_despues}")

    diag_despues = sql_uno(
        "select nivel, es_alerta from edu_diagnosticos_alumno where inscripcion_id=:i", i=insc_id)
    comprobar("[3] DiagnosticoAlumno no cambió (nunca referenció a Persona)", diag_antes == diag_despues)

    r_pdf_staff = requests.get(f"{API}/educativo/inscripciones/{insc_id}/informe-pdf", headers=h_a, timeout=60)
    comprobar("[3] El PDF ya generado sigue siendo descargable", r_pdf_staff.status_code == 200)
    comprobar("[3] Es EXACTAMENTE el mismo archivo (checksum idéntico, no se regeneró)",
              r_pdf_staff.content == r_pdf_original.content)
    texto_tras_editar = texto_pdf(r_pdf_staff.content)
    comprobar("[3] El PDF ya emitido SIGUE mostrando el nombre ORIGINAL", "Nombre Original" in texto_tras_editar)
    comprobar("[3] El PDF ya emitido NUNCA muestra el nombre corregido", "Nombre Corregido" not in texto_tras_editar)

    snapshot_json = sql_uno(
        "select resultados_snapshot::text from edu_informe_versiones v join edu_informes i on i.id=v.informe_id "
        "where i.inscripcion_id=:i and v.numero_version=1", i=insc_id)[0]
    comprobar("[3] El snapshot JSON almacenado (resultados_snapshot) también conserva el nombre ORIGINAL",
              "Nombre Original" in snapshot_json and "Nombre Corregido" not in snapshot_json)

    # La FICHA actual sí debe reflejar el cambio (es una vista en vivo, no un histórico).
    ficha = exigir(requests.get(f"{API}/admin/personas/{persona}/ficha-completa", headers=h_a, timeout=30), 200, "Ficha")
    comprobar("[contraste] La ficha ACTUAL del alumno sí muestra el nombre corregido (es vista en vivo, no snapshot)",
              ficha["datos_personales"]["nombres"] == "Nombre Corregido", str(ficha["datos_personales"]))

    # ==================================================================
    print("\n4 · Auditoría — se registra cada campo realmente cambiado, nunca los que no cambiaron")
    historial = exigir(requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_a, timeout=30),
                       200, "Historial tras el PATCH de los 4 campos")
    comprobar("[4] Se registraron exactamente 4 filas (una por cada campo realmente cambiado)",
              len(historial) == 4, str(historial))
    por_campo = {r["campo"]: r for r in historial}
    comprobar("[4] Las 4 filas son nombres/apellidos/fecha_nacimiento/documento_identidad",
              set(por_campo) == {"nombres", "apellidos", "fecha_nacimiento", "documento_identidad"})
    comprobar("[4] 'nombres': valor_anterior/valor_nuevo correctos",
              por_campo["nombres"]["valor_anterior"] == "Nombre Original" and por_campo["nombres"]["valor_nuevo"] == "Nombre Corregido")
    comprobar("[4] 'apellidos': valor_anterior/valor_nuevo correctos",
              por_campo["apellidos"]["valor_anterior"] == "Apellido Original" and por_campo["apellidos"]["valor_nuevo"] == "Apellido Corregido")
    comprobar("[4] 'documento_identidad': valor_anterior/valor_nuevo correctos",
              por_campo["documento_identidad"]["valor_anterior"] == f"{sello}ORIG"
              and por_campo["documento_identidad"]["valor_nuevo"] == f"{sello}CORREGIDO")
    comprobar("[4] 'fecha_nacimiento': valor_anterior/valor_nuevo correctos (2011-04-10 -> 2011-05-20)",
              por_campo["fecha_nacimiento"]["valor_anterior"].startswith("2011-04-10")
              and por_campo["fecha_nacimiento"]["valor_nuevo"] == "2011-05-20")
    comprobar("[4] Las 4 filas quedaron atribuidas al rol 'psicologo' (quien hizo el PATCH)",
              all(r["rol_modificador"] == "psicologo" for r in historial))

    print("\n4b · Re-enviar los MISMOS valores no genera filas nuevas")
    r_repatch_igual = requests.patch(f"{API}/admin/personas/{persona}", json={
        "nombres": "Nombre Corregido", "apellidos": "Apellido Corregido",
        "fecha_nacimiento": "2011-05-20", "documento_identidad": f"{sello}CORREGIDO",
    }, headers=h_a, timeout=30)
    comprobar("[4b] El PATCH con los mismos valores sigue devolviendo 200", r_repatch_igual.status_code == 200)
    historial_tras_repetir = exigir(requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_a, timeout=30),
                                    200, "Historial tras re-enviar los mismos valores")
    comprobar("[4b] SIGUEN siendo exactamente 4 filas (ningún valor cambió realmente)",
              len(historial_tras_repetir) == 4, f"{len(historial_tras_repetir)} filas")

    print("\n4c · Cambiar SOLO un campo agrega SOLO una fila nueva")
    exigir(requests.patch(f"{API}/admin/personas/{persona}", json={"nombres": "Nombre Tres"},
                          headers=h_a, timeout=30), 200, "Tercer cambio de nombres")
    historial_final = exigir(requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_a, timeout=30),
                             200, "Historial tras el tercer cambio")
    comprobar("[4c] Ahora hay 5 filas en total (4 + 1 nueva de 'nombres')", len(historial_final) == 5, f"{len(historial_final)} filas")
    filas_nombres = [r for r in historial_final if r["campo"] == "nombres"]
    comprobar("[4c] Hay 2 filas de 'nombres' (la corrección original + esta nueva), ambas conservadas",
              len(filas_nombres) == 2)

    # ==================================================================
    print("\n5 · El endpoint de lectura respeta rol e institución")
    r_hist_cruzado = requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_b, timeout=30)
    comprobar("[5] Un psicólogo de OTRA institución -> 403", r_hist_cruzado.status_code == 403)

    correo_admin_a = f"{PREFIJO.lower()}.admin.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro admin A", json={
        "email": correo_admin_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Admin A",
        "rol": "admin", "institucion_id": inst_a}, headers=h_super), 200, "Registro admin A")
    h_admin_a = {"Authorization": f"Bearer {exigir(login(correo_admin_a, 'ClaveDePrueba123'), 200, 'Login admin A')['access_token']}"}
    r_hist_admin = requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_admin_a, timeout=30)
    comprobar("[5] Un 'admin' de la MISMA institución -> 200 (puede ver el historial)", r_hist_admin.status_code == 200)

    correo_colegio_a = f"{PREFIJO.lower()}.colegio.a.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro colegio A", json={
        "email": correo_colegio_a, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Colegio A",
        "rol": "colegio", "institucion_id": inst_a}, headers=h_super), 200, "Registro colegio A")
    h_colegio_a = {"Authorization": f"Bearer {exigir(login(correo_colegio_a, 'ClaveDePrueba123'), 200, 'Login colegio A')['access_token']}"}
    r_hist_colegio = requests.get(f"{API}/admin/personas/{persona}/historial-cambios", headers=h_colegio_a, timeout=30)
    comprobar("[5] El rol 'colegio', AUNQUE sea de la MISMA institución -> 403 (excluido explícitamente)",
              r_hist_colegio.status_code == 403, f"status {r_hist_colegio.status_code}")

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
        c.execute(text(f"""
            delete from consentimientos_informados where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from registro_cambios_persona where persona_id in (
                select id from personas where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from personas where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
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
