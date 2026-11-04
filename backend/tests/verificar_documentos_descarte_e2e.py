"""Verificación end-to-end de DESCARTAR un borrador de DocumentoInstitucional y de ELIMINAR una PlantillaDocumento
(DELETE /documentos/{id}, sesión 2026-11-01) y del resumen de estudiantes
del listado (`estudiantes_resumen`).

  1   El listado trae `estudiantes_resumen` con los nombres congelados de
      cada documento — dos borradores con el mismo título se distinguen
  2   Permisos: 'colegio' -> 403 (rol), psicólogo de OTRA institución -> 403
  3   Descartar un borrador -> 204; desde ahí 404 en detalle, secciones y
      generar-version, y desaparece del listado (total incluido) y del
      filtro por persona_id; un segundo DELETE -> 404
  4   Soft-delete real: la fila sigue en la BD con descartado_en y
      descartado_por_usuario_id, y su auditoría de lecturas se conserva
  5   Un documento con versión emitida -> 409, sigue visible e intacto
  6   El CHECK ck_documentos_institucionales_descartado_solo_borrador
      rechaza a nivel de BD marcar como descartado un documento emitido
  7   (misma sesión) Dos plantillas ACTIVAS del mismo tipo conviven y ambas
      sirven para crear documentos; cada sección trae
      `inscripciones_vinculadas`
  8   (misma sesión) Eliminar una plantilla: 403 para 'colegio'/otra
      institución; un duplicado sin documentos -> 204, desaparece del listado
      pero se puede leer por id, y toda escritura sobre ella -> 404; con un
      borrador en curso -> 409 (al descartarlo, 204); con solo documentos
      emitidos -> 204 y esos documentos se siguen abriendo y reemitiendo;
      una predeterminada del catálogo -> 409
  9   (misma sesión, escalabilidad) Filtros del listado en el servidor
      (plantilla, estado, q en título y alumno, varios persona_id sin
      duplicar ni inflar el total, 422 con estado inválido, sin filtros =
      igual que antes), `cantidad_secciones` en el listado de plantillas,
      `plantilla_origen_id` al clonar, búsqueda del padrón por nombre
      completo en ambos órdenes, y casos-pendientes con la misma forma y
      el mismo candado de rol

    uvicorn main:app --port 8010          (SMTP deshabilitado, LOGIN_CAPTCHA_OBLIGATORIO=false)
    python -m tests.verificar_documentos_descarte_e2e
    python -m tests.verificar_documentos_descarte_e2e --limpiar
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZDOCDESC"
API = "http://127.0.0.1:8010/api"
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


def crear_persona(h, institucion_id, nombres):
    return exigir(requests.post(f"{API}/admin/personas/", json={
        "institucion_id": institucion_id, "nombres": nombres, "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }, headers=h, timeout=30), 200, f"crear persona {nombres}")["id"]


def crear_documento(h, tipo_id, plantilla_id, titulo, personas_ids):
    return exigir(requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla_id, "alcance": "personas_especificas",
        "titulo": titulo, "personas_ids": personas_ids,
    }, headers=h, timeout=30), 200, f"crear documento {titulo}")


def listar(h, institucion_id, persona_id=None):
    url = f"{API}/documentos/?institucion_id={institucion_id}&limit=200"
    if persona_id:
        url += f"&persona_id={persona_id}"
    return exigir(requests.get(url, headers=h, timeout=30), 200, "listar documentos")


def main(url_base):
    global API
    API = url_base.rstrip("/") + "/api"
    motor = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.now(timezone.utc).strftime("%H%M%S")

    print("\n0 · Montaje")
    # Superadmin PROPIO del test (se borra en --limpiar): no depende de que
    # la contraseña real del superadmin siga siendo la del .env — la BD manda
    # si se cambió con "Olvidé mi contraseña" (ver seeds/seed_superadmin.py).
    from core.security import get_password_hash
    correo_super = f"{PREFIJO.lower()}.super.{sello}@ejemplo.com"
    with motor.begin() as c:
        c.execute(text(
            "INSERT INTO auth_usuarios (email, hashed_password, nombre_completo, rol, activo, token_version) "
            "VALUES (:e, :h, :n, 'superadmin', true, 0)"
        ), {"e": correo_super, "h": get_password_hash("ClaveDePrueba123"), "n": f"{PREFIJO} Super"})
    tok_super = exigir(login(correo_super, "ClaveDePrueba123"), 200, "login superadmin del test")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}

    inst_a = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} A {sello}"}, headers=h_super, timeout=30), 201, "Institución A")["id"]
    inst_b = exigir(requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} B {sello}"}, headers=h_super, timeout=30), 201, "Institución B")["id"]
    h_psi_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com", f"{PREFIJO} PsiA", "psicologo", inst_a)
    h_psi_b = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.psib.{sello}@ejemplo.com", f"{PREFIJO} PsiB", "psicologo", inst_b)
    h_colegio_a = registrar_y_loguear(h_super, f"{PREFIJO.lower()}.colegioa.{sello}@ejemplo.com", f"{PREFIJO} ColegioA", "colegio", inst_a)

    tipo_id = exigir(requests.post(f"{API}/documentos/tipos", json={
        "clave": f"{PREFIJO.lower()}_tipo_{sello}", "nombre": f"{PREFIJO} Ficha de derivación",
        "alcances_permitidos": "personas_especificas", "visibilidades_permitidas": "confidencial_clinico",
    }, headers=h_super, timeout=30), 200, "crear TipoDocumento")["id"]
    plantilla_id = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla",
    }, headers=h_psi_a, timeout=30), 200, "crear plantilla")["id"]
    exigir(requests.post(f"{API}/documentos/plantillas/{plantilla_id}/secciones", json={
        "orden": 0, "tipo_seccion": "texto_libre", "titulo": "Motivo de la derivación",
    }, headers=h_psi_a, timeout=30), 200, "crear sección")

    p1 = crear_persona(h_psi_a, inst_a, f"{PREFIJO} Ana")
    p2 = crear_persona(h_psi_a, inst_a, f"{PREFIJO} Beto")
    titulo = "Ficha Derivación Externa"
    doc1 = crear_documento(h_psi_a, tipo_id, plantilla_id, titulo, [p1])
    doc2 = crear_documento(h_psi_a, tipo_id, plantilla_id, titulo, [p2])
    doc_emitido = crear_documento(h_psi_a, tipo_id, plantilla_id, f"{titulo} emitida", [p1])
    exigir(requests.post(f"{API}/documentos/{doc_emitido['id']}/generar-version", headers=h_psi_a, timeout=60), 200, "generar v1")

    print("\n1 · estudiantes_resumen en el listado")
    lista = listar(h_psi_a, inst_a)
    por_id = {d["id"]: d for d in lista["items"]}
    comprobar("El listado trae 3 documentos", lista["total"] == 3, str(lista["total"]))
    comprobar("doc1 lista a Ana", por_id[doc1["id"]].get("estudiantes_resumen") == [f"{PREFIJO} Ana Prueba"], str(por_id[doc1["id"]].get("estudiantes_resumen")))
    comprobar("doc2 (mismo título) lista a Beto — se distinguen", por_id[doc2["id"]].get("estudiantes_resumen") == [f"{PREFIJO} Beto Prueba"])

    # Lectura auditada del borrador ANTES de descartarlo (.../secciones siempre audita).
    secciones_doc1 = exigir(requests.get(f"{API}/documentos/{doc1['id']}/secciones", headers=h_psi_a, timeout=30), 200, "leer secciones doc1")
    comprobar("[7] Cada sección trae inscripciones_vinculadas (vacío sin vínculo)",
              all(s.get("inscripciones_vinculadas") == [] for s in secciones_doc1), str(secciones_doc1)[:200])

    print("\n7 · Varias plantillas activas del mismo tipo")
    plantilla2 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla para padres", "activa": True,
    }, headers=h_psi_a, timeout=30), 200, "crear segunda plantilla activa")
    plantilla1 = exigir(requests.get(f"{API}/documentos/plantillas/{plantilla_id}", headers=h_psi_a, timeout=30), 200, "releer plantilla 1")
    comprobar("[7] Activar una segunda plantilla del mismo tipo NO apaga la primera", plantilla1["activa"] is True and plantilla2["activa"] is True)
    r = requests.post(f"{API}/documentos/", json={
        "tipo_documento_id": tipo_id, "plantilla_documento_id": plantilla2["id"], "alcance": "personas_especificas",
        "titulo": "Desde la segunda plantilla", "personas_ids": [p2],
    }, headers=h_psi_a, timeout=30)
    comprobar("[7] Se puede crear un documento con la segunda plantilla activa", r.status_code == 200, str(r.status_code))
    doc_segunda = r.json() if r.status_code == 200 else None

    print("\n2 · Permisos")
    r = requests.delete(f"{API}/documentos/{doc1['id']}", headers=h_colegio_a, timeout=30)
    comprobar("'colegio' no puede descartar (403)", r.status_code == 403, str(r.status_code))
    r = requests.delete(f"{API}/documentos/{doc1['id']}", headers=h_psi_b, timeout=30)
    comprobar("Psicólogo de otra institución no puede descartar (403)", r.status_code == 403, str(r.status_code))

    print("\n3 · Descartar un borrador")
    r = requests.delete(f"{API}/documentos/{doc1['id']}", headers=h_psi_a, timeout=30)
    comprobar("DELETE del borrador -> 204", r.status_code == 204, f"{r.status_code} {r.text[:200]}")
    for ruta, metodo in [(f"/documentos/{doc1['id']}", requests.get), (f"/documentos/{doc1['id']}/secciones", requests.get),
                         (f"/documentos/{doc1['id']}/generar-version", requests.post)]:
        r = metodo(f"{API}{ruta}", headers=h_psi_a, timeout=30)
        comprobar(f"{metodo.__name__.upper()} {ruta} -> 404 tras descartar", r.status_code == 404, str(r.status_code))
    lista = listar(h_psi_a, inst_a)
    esperado = 3 if doc_segunda else 2
    comprobar(f"Ya no aparece en el listado y total baja a {esperado}",
              lista["total"] == esperado and doc1["id"] not in {d["id"] for d in lista["items"]}, str(lista["total"]))
    lista_p1 = listar(h_psi_a, inst_a, persona_id=p1)
    comprobar("Tampoco aparece filtrando por la persona", {d["id"] for d in lista_p1["items"]} == {doc_emitido["id"]})
    r = requests.delete(f"{API}/documentos/{doc1['id']}", headers=h_psi_a, timeout=30)
    comprobar("Un segundo DELETE -> 404", r.status_code == 404, str(r.status_code))

    print("\n4 · Soft-delete real")
    with motor.connect() as c:
        fila = c.execute(text(
            "SELECT descartado_en, descartado_por_usuario_id FROM documentos_institucionales WHERE id = :id"
        ), {"id": doc1["id"]}).first()
        lecturas = c.execute(text(
            "SELECT count(*) FROM documentos_registro_lecturas WHERE documento_institucional_id = :id"
        ), {"id": doc1["id"]}).scalar()
        id_psi_a = c.execute(text("SELECT id FROM auth_usuarios WHERE email = :e"),
                             {"e": f"{PREFIJO.lower()}.psia.{sello}@ejemplo.com"}).scalar()
    comprobar("La fila sigue en la BD con descartado_en", fila is not None and fila[0] is not None)
    comprobar("descartado_por_usuario_id = quien descartó", fila is not None and fila[1] == id_psi_a, str(fila))
    comprobar("La auditoría de lecturas del borrador se conserva", lecturas >= 1, str(lecturas))

    print("\n5 · Documento emitido")
    r = requests.delete(f"{API}/documentos/{doc_emitido['id']}", headers=h_psi_a, timeout=30)
    comprobar("DELETE de un documento con versión -> 409", r.status_code == 409, str(r.status_code))
    det = exigir(requests.get(f"{API}/documentos/{doc_emitido['id']}", headers=h_psi_a, timeout=30), 200, "detalle emitido")
    comprobar("Sigue visible con su v1", det["version_actual"] == 1)

    print("\n6 · CHECK de la tabla")
    try:
        with motor.begin() as c:
            c.execute(text("UPDATE documentos_institucionales SET descartado_en = now() WHERE id = :id"), {"id": doc_emitido["id"]})
        comprobar("El CHECK rechaza descartar un emitido a nivel BD", False, "el UPDATE pasó")
    except IntegrityError:
        comprobar("El CHECK rechaza descartar un emitido a nivel BD", True)

    print("\n8 · Eliminar una plantilla (duplicado por accidente)")
    # Duplicado sin ningún documento: el caso típico de "clonar dos veces".
    duplicada = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla (copia)", "activa": True,
    }, headers=h_psi_a, timeout=30), 200, "crear plantilla duplicada")
    r = requests.delete(f"{API}/documentos/plantillas/{duplicada['id']}", headers=h_colegio_a, timeout=30)
    comprobar("[8] 'colegio' no puede eliminar una plantilla (403)", r.status_code == 403, str(r.status_code))
    r = requests.delete(f"{API}/documentos/plantillas/{duplicada['id']}", headers=h_psi_b, timeout=30)
    comprobar("[8] Psicólogo de otra institución no puede eliminarla (403)", r.status_code == 403, str(r.status_code))
    r = requests.delete(f"{API}/documentos/plantillas/{duplicada['id']}", headers=h_psi_a, timeout=30)
    comprobar("[8] Eliminar un duplicado sin documentos -> 204", r.status_code == 204, f"{r.status_code} {r.text[:150]}")
    ids_listado = {p["id"] for p in exigir(requests.get(f"{API}/documentos/plantillas", params={"institucion_id": inst_a},
                                                         headers=h_psi_a, timeout=30), 200, "listar plantillas")}
    comprobar("[8] La eliminada ya no aparece en Mis plantillas", duplicada["id"] not in ids_listado)
    r = requests.get(f"{API}/documentos/plantillas/{duplicada['id']}", headers=h_psi_a, timeout=30)
    comprobar("[8] Leerla por id sigue funcionando (la usan sus documentos emitidos)", r.status_code == 200 and r.json()["activa"] is False)
    for metodo, ruta, cuerpo in [
        (requests.patch, f"/documentos/plantillas/{duplicada['id']}", {"nombre": "revivida"}),
        (requests.post, f"/documentos/plantillas/{duplicada['id']}/secciones", {"orden": 0, "tipo_seccion": "texto_libre"}),
        (requests.post, f"/documentos/plantillas/{duplicada['id']}/clonar", {"institucion_destino_id": inst_a}),
        (requests.post, "/documentos/", {"tipo_documento_id": tipo_id, "plantilla_documento_id": duplicada["id"],
                                         "alcance": "personas_especificas", "titulo": "No debe crearse", "personas_ids": [p1]}),
        (requests.delete, f"/documentos/plantillas/{duplicada['id']}", None),
    ]:
        r = metodo(f"{API}{ruta}", json=cuerpo, headers=h_psi_a, timeout=30) if cuerpo is not None else metodo(f"{API}{ruta}", headers=h_psi_a, timeout=30)
        comprobar(f"[8] {metodo.__name__.upper()} {ruta} sobre la eliminada -> 404", r.status_code == 404, str(r.status_code))

    # Con un borrador en curso no se elimina; al descartarlo, sí.
    r = requests.delete(f"{API}/documentos/plantillas/{plantilla2['id']}", headers=h_psi_a, timeout=30)
    comprobar("[8] Plantilla con un borrador en curso -> 409", r.status_code == 409, f"{r.status_code} {r.text[:150]}")
    if doc_segunda:
        exigir(requests.delete(f"{API}/documentos/{doc_segunda['id']}", headers=h_psi_a, timeout=30), 204, "descartar borrador de la plantilla 2")
        r = requests.delete(f"{API}/documentos/plantillas/{plantilla2['id']}", headers=h_psi_a, timeout=30)
        comprobar("[8] Descartado el borrador, la plantilla ya se puede eliminar (204)", r.status_code == 204, str(r.status_code))

    # Con un documento EMITIDO sí se elimina, y ese documento sigue funcionando.
    exigir(requests.delete(f"{API}/documentos/{doc2['id']}", headers=h_psi_a, timeout=30), 204, "descartar doc2 (último borrador de la plantilla 1)")
    r = requests.delete(f"{API}/documentos/plantillas/{plantilla_id}", headers=h_psi_a, timeout=30)
    comprobar("[8] Plantilla con solo documentos emitidos -> 204", r.status_code == 204, f"{r.status_code} {r.text[:150]}")
    r = requests.get(f"{API}/documentos/{doc_emitido['id']}/secciones", headers=h_psi_a, timeout=30)
    comprobar("[8] El documento emitido se sigue abriendo con su plantilla eliminada", r.status_code == 200 and len(r.json()) == 1)
    r = requests.post(f"{API}/documentos/{doc_emitido['id']}/reemitir", json={"motivo": "Corrección tras eliminar la plantilla"},
                      headers=h_psi_a, timeout=60)
    comprobar("[8] ...y se puede reemitir (v2)", r.status_code == 200 and r.json().get("numero_version") == 2, f"{r.status_code} {r.text[:150]}")

    predeterminadas = exigir(requests.get(f"{API}/documentos/plantillas/predeterminadas", headers=h_psi_a, timeout=30), 200, "listar predeterminadas")
    if predeterminadas:
        # El 409 se decide ANTES de tocar nada: no hay riesgo de eliminar el catálogo real.
        r = requests.delete(f"{API}/documentos/plantillas/{predeterminadas[0]['id']}", headers=h_psi_a, timeout=30)
        comprobar("[8] Una predeterminada del catálogo no se elimina (409)", r.status_code == 409, str(r.status_code))

    print("\n9 · Escalabilidad: filtros en el servidor, conteos, origen y búsqueda")
    plantilla9 = exigir(requests.post(f"{API}/documentos/plantillas", json={
        "institucion_id": inst_a, "tipo_documento_id": tipo_id, "nombre": f"{PREFIJO} Plantilla filtros", "activa": True,
    }, headers=h_psi_a, timeout=30), 200, "crear plantilla de filtros")
    for orden in (0, 1):
        exigir(requests.post(f"{API}/documentos/plantillas/{plantilla9['id']}/secciones", json={
            "orden": orden, "tipo_seccion": "texto_libre", "titulo": f"Sección {orden}",
        }, headers=h_psi_a, timeout=30), 200, "crear sección de filtros")
    d_ana = crear_documento(h_psi_a, tipo_id, plantilla9["id"], "Informe trimestral", [p1])
    d_beto = crear_documento(h_psi_a, tipo_id, plantilla9["id"], "Informe trimestral", [p2])
    d_grupal = crear_documento(h_psi_a, tipo_id, plantilla9["id"], "Reunión grupal", [p1, p2])
    exigir(requests.post(f"{API}/documentos/{d_beto['id']}/generar-version", headers=h_psi_a, timeout=60), 200, "emitir doc de Beto")

    def ids_de(params):
        r = requests.get(f"{API}/documentos/", params={"institucion_id": inst_a, "limit": 200, **params}, headers=h_psi_a, timeout=30)
        cuerpo = r.json() if r.status_code == 200 else {}
        return r.status_code, {d["id"] for d in cuerpo.get("items", [])}, cuerpo.get("total")

    _, ids, total = ids_de({"plantilla_documento_id": plantilla9["id"]})
    comprobar("[9] plantilla_documento_id filtra solo sus 3 documentos", ids == {d_ana["id"], d_beto["id"], d_grupal["id"]} and total == 3, str(ids))
    _, ids, _ = ids_de({"plantilla_documento_id": plantilla9["id"], "estado": "borrador"})
    comprobar("[9] estado=borrador excluye el emitido", ids == {d_ana["id"], d_grupal["id"]}, str(ids))
    _, ids, _ = ids_de({"plantilla_documento_id": plantilla9["id"], "estado": "emitido"})
    comprobar("[9] estado=emitido trae solo el emitido", ids == {d_beto["id"]}, str(ids))
    _, ids, _ = ids_de({"plantilla_documento_id": plantilla9["id"], "q": "grupal"})
    comprobar("[9] q busca en el título", ids == {d_grupal["id"]}, str(ids))
    _, ids, _ = ids_de({"plantilla_documento_id": plantilla9["id"], "q": "beto"})
    comprobar("[9] q busca en el nombre congelado del alumno (sin distinguir mayúsculas)", ids == {d_beto["id"], d_grupal["id"]}, str(ids))
    r = requests.get(f"{API}/documentos/", params=[("institucion_id", inst_a), ("plantilla_documento_id", plantilla9["id"]),
                                                    ("persona_id", p1), ("persona_id", p2), ("limit", 200)], headers=h_psi_a, timeout=30)
    items = r.json()["items"] if r.status_code == 200 else []
    comprobar("[9] Varios persona_id: el documento grupal sale UNA vez y el total no se infla",
              r.status_code == 200 and len(items) == 3 and r.json()["total"] == 3 and len({d["id"] for d in items}) == 3, f"{r.status_code} {len(items)}")
    _, ids, _ = ids_de({"persona_id": p1, "plantilla_documento_id": plantilla9["id"]})
    comprobar("[9] Un solo persona_id sigue funcionando igual que antes", ids == {d_ana["id"], d_grupal["id"]}, str(ids))
    codigo, _, _ = ids_de({"estado": "cualquiera"})
    comprobar("[9] estado inválido -> 422", codigo == 422, str(codigo))
    _, ids_todos, total_todos = ids_de({})
    comprobar("[9] Sin filtros, el listado no cambia (incluye los 3 nuevos)", {d_ana["id"], d_beto["id"], d_grupal["id"]} <= ids_todos)

    plantillas9 = exigir(requests.get(f"{API}/documentos/plantillas", params={"institucion_id": inst_a}, headers=h_psi_a, timeout=30), 200, "listar plantillas")
    conteo = next((x.get("cantidad_secciones") for x in plantillas9 if x["id"] == plantilla9["id"]), None)
    comprobar("[9] cantidad_secciones viene en el listado (2)", conteo == 2, str(conteo))
    clon9 = exigir(requests.post(f"{API}/documentos/plantillas/{plantilla9['id']}/clonar", json={"institucion_destino_id": inst_a},
                                 headers=h_psi_a, timeout=30), 200, "clonar plantilla de filtros")
    comprobar("[9] Clonar registra plantilla_origen_id", clon9.get("plantilla_origen_id") == plantilla9["id"], str(clon9.get("plantilla_origen_id")))
    comprobar("[9] Una plantilla armada desde cero no tiene origen", plantilla9.get("plantilla_origen_id") is None)

    for texto, debe in [(f"{PREFIJO} Ana Prueba", p1), (f"Prueba {PREFIJO} Ana", p1), ("ana prueba", p1)]:
        r = requests.get(f"{API}/admin/personas/{inst_a}", params={"busqueda": texto, "limit": 20}, headers=h_psi_a, timeout=30)
        encontrados = {x["id"] for x in r.json().get("items", [])} if r.status_code == 200 else set()
        comprobar(f"[9] Buscar alumno por nombre completo «{texto}»", debe in encontrados, f"{r.status_code} {encontrados}")
    r = requests.get(f"{API}/admin/personas/{inst_a}", params={"limit": 200}, headers=h_psi_a, timeout=30)
    comprobar("[9] El padrón paginado sigue trayendo seccion_actual/con_diagnostico en cada fila",
              r.status_code == 200 and all("seccion_actual" in x and "con_diagnostico" in x for x in r.json()["items"]))
    # 🆕 (sesión 2026-11-02) /casos-pendientes se retiró; su reemplazo, la bandeja.
    r = requests.get(f"{API}/educativo/casos-riesgo", headers=h_psi_a, timeout=60)
    comprobar("[9] casos-riesgo responde la bandeja (casos en lista)", r.status_code == 200 and isinstance(r.json().get("casos"), list), str(r.status_code))
    r = requests.get(f"{API}/educativo/casos-riesgo", headers=h_colegio_a, timeout=30)
    comprobar("[9] casos-riesgo sigue cerrado a 'colegio' (403)", r.status_code == 403, str(r.status_code))

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E DOCUMENTOS — DESCARTE DE BORRADOR: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


def limpiar():
    motor = create_engine(os.getenv("DATABASE_URL"))
    insts = f"SELECT id FROM instituciones WHERE nombre LIKE '{PREFIJO}%'"
    tipos = f"SELECT id FROM documentos_tipos WHERE clave LIKE '{PREFIJO.lower()}%'"
    plantillas = f"SELECT id FROM documentos_plantillas WHERE institucion_id IN ({insts})"
    documentos = f"SELECT id FROM documentos_institucionales WHERE institucion_id IN ({insts})"
    entradas = f"SELECT id FROM expediente_entradas WHERE documento_institucional_id IN ({documentos})"
    with motor.begin() as c:
        for q in [
            f"DELETE FROM registro_lecturas_expediente WHERE entrada_expediente_id IN ({entradas})",
            f"DELETE FROM expediente_entradas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_registro_lecturas WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_versiones WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_seccion_contenido WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estudiantes WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales_estructura WHERE documento_institucional_id IN ({documentos})",
            f"DELETE FROM documentos_institucionales WHERE id IN ({documentos})",
            f"DELETE FROM documentos_correlativos WHERE institucion_id IN ({insts})",
            f"DELETE FROM documentos_plantilla_secciones WHERE plantilla_documento_id IN ({plantillas})",
            f"DELETE FROM documentos_plantillas WHERE id IN ({plantillas})",
            f"DELETE FROM documentos_tipos WHERE id IN ({tipos})",
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
