"""🆕 (2026-11-16) Composición familiar del estudiante (registro único por
familiar en `ContactoFamiliar`), contra un servidor real. Prefijo ZZFAMI.
Necesita la BD y `uvicorn main:app --port 8010` con PROXIES_CONFIABLES=127.0.0.1
(cada petición sale con su propia X-Forwarded-For para no chocar con el
rate limit del login).

Cubre:
  1. Un contacto creado con la forma ANTERIOR (nombre/teléfono/relación)
     sigue funcionando y queda como contacto, no apoderado.
  2. Familiares con los campos nuevos (madre apoderada, hermano que no es
     contacto); PATCH parcial; un booleano obligatorio en null no rompe.
  3. El rol `colegio` ve nombre, parentesco, apoderado y teléfono, pero NO
     ocupación, instrucción, estado civil, dirección, distrito, vive con ni
     fecha de nacimiento; tampoco puede crear ni editar (403).
  4. Otra institución no ve ni edita (403).
  5. La exportación ARCO trae los campos nuevos.

    python -m tests.verificar_familia_estudiante_e2e [--limpiar]
"""
import argparse
import itertools
import os
import random
import sys
import uuid

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8010")
API = f"{BASE}/api"
PREFIJO = "ZZFAMI"
CLAVE = "ClaveDePrueba123"
engine = create_engine(os.environ["DATABASE_URL"])
resultados = []
_ips = (f"10.{random.randint(1, 250)}.{a}.{b}" for a, b in itertools.product(range(1, 250), range(1, 250)))
SOLO_STAFF = ("vive_con_estudiante", "ocupacion", "grado_instruccion", "estado_civil", "direccion", "distrito", "fecha_nacimiento")


def comprobar(nombre, condicion, detalle=""):
    resultados.append((nombre, bool(condicion)))
    print(f"  {'[PASA]' if condicion else '[FALLA]'} {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def cab(extra=None):
    return {"X-Forwarded-For": next(_ips), **(extra or {})}


def sql(consulta, **p):
    with engine.begin() as c:
        return c.execute(text(consulta), p)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        sys.exit(f"!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:400]}")
    return r.json() if r.text else None


def token(email, clave):
    r = requests.post(f"{API}/auth/login", data={"username": email, "password": clave}, headers=cab(), timeout=30)
    exigir(r, 200, f"login {email}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def pedir(metodo, ruta, h, **kw):
    return requests.request(metodo, f"{API}{ruta}", headers=cab(h), timeout=30, **kw)


def limpiar():
    insts = "select id from instituciones where nombre like :p"
    personas = f"select id from personas where institucion_id in ({insts})"
    usuarios = "select id from auth_usuarios where email like :u"
    p, u = f"{PREFIJO}%", f"{PREFIJO.lower()}.%"
    sql(f"delete from auditoria_arco where persona_id in ({personas})", p=p)
    sql(f"delete from contactos_familiares where persona_id in ({personas})", p=p)
    sql(f"delete from personas where institucion_id in ({insts})", p=p)
    sql(f"delete from auth_tokens_recuperacion where usuario_id in ({usuarios})", u=u)
    sql(f"delete from auth_sesiones where usuario_id in ({usuarios})", u=u)
    sql("delete from auth_usuarios where email like :u", u=u)
    n = sql("delete from instituciones where nombre like :p", p=p).rowcount
    print(f"Limpieza {PREFIJO}: {n} institución(es) y sus datos.")


def main():
    sello = uuid.uuid4().hex[:8]
    h_super = token(os.environ["SUPERADMIN_EMAIL"], os.environ["SUPERADMIN_PASSWORD"])

    def institucion(letra):
        return exigir(pedir("POST", "/instituciones/", h_super, json={"nombre": f"{PREFIJO} {letra} {sello}"}), 201, "institución")["id"]

    def cuenta(rol, inst):
        correo = f"{PREFIJO.lower()}.{rol}.{inst}.{sello}@ejemplo.com"
        exigir(pedir("POST", "/auth/registro", h_super, json={
            "email": correo, "password": CLAVE, "nombre_completo": f"{PREFIJO} {rol}", "rol": rol, "institucion_id": inst,
        }), 200, f"registro {rol}")
        return token(correo, CLAVE)

    inst_a, inst_b = institucion("A"), institucion("B")
    h_psi, h_col, h_psi_b = cuenta("psicologo", inst_a), cuenta("colegio", inst_a), cuenta("psicologo", inst_b)
    persona = exigir(pedir("POST", "/admin/personas/", h_psi, json={
        "institucion_id": inst_a, "nombres": f"{PREFIJO} Alumno", "apellidos": "Prueba", "tipo_perfil": "estudiante",
    }), 200, "crear persona")["id"]
    ruta = f"/admin/personas/{persona}/contactos"

    print("\n1 · La forma anterior sigue igual")
    viejo = exigir(pedir("POST", ruta, h_psi, json={"nombre": "Contacto Antiguo", "telefono": "900000001", "relacion": "tío"}), 201, "contacto antiguo")
    comprobar("Se crea con solo nombre/teléfono/relación", viejo["nombre"] == "Contacto Antiguo")
    comprobar("Queda como contacto (es_contacto=true)", viejo["es_contacto"] is True)
    comprobar("No queda como apoderado", viejo["es_apoderado"] is False)
    comprobar("Campos nuevos en null", all(viejo[c] is None for c in SOLO_STAFF + ("apellidos",)))

    print("\n2 · Familiares con los campos nuevos")
    madre = exigir(pedir("POST", ruta, h_psi, json={
        "nombre": "Rosa", "apellidos": "Quispe Mamani", "relacion": "Madre", "telefono": "988777666",
        "es_apoderado": True, "es_contacto": True, "vive_con_estudiante": True, "ocupacion": "Docente",
        "grado_instruccion": "Superior universitario completo", "estado_civil": "Casado(a)",
        "direccion": "Av. Los Pinos 123", "distrito": "San Juan de Lurigancho",
    }), 201, "madre")
    comprobar("Madre: apoderada y contacto", madre["es_apoderado"] and madre["es_contacto"])
    comprobar("Madre: ocupación, estado civil y distrito guardados",
              (madre["ocupacion"], madre["estado_civil"], madre["distrito"]) == ("Docente", "Casado(a)", "San Juan de Lurigancho"))
    hermano = exigir(pedir("POST", ruta, h_psi, json={
        "nombre": "Luis", "apellidos": "Quispe", "relacion": "Hermano", "es_contacto": False,
        "vive_con_estudiante": True, "fecha_nacimiento": "2014-06-15",
    }), 201, "hermano")
    comprobar("Hermano: no es contacto", hermano["es_contacto"] is False)
    comprobar("Hermano: fecha de nacimiento", hermano["fecha_nacimiento"] == "2014-06-15")
    r = pedir("POST", ruta, h_psi, json={"nombre": "Nulo", "es_apoderado": None, "es_contacto": None})
    comprobar("Booleanos en null al crear: toman su default", r.status_code == 201 and r.json()["es_contacto"] is True
              and r.json()["es_apoderado"] is False, f"{r.status_code} {r.text[:200]}")
    editado = exigir(pedir("PATCH", f"/admin/personas/contactos/{madre['id']}", h_psi,
                           json={"ocupacion": "Directora", "es_apoderado": None}), 200, "patch madre")
    comprobar("PATCH parcial: ocupación cambia", editado["ocupacion"] == "Directora")
    comprobar("PATCH parcial: el resto no se toca", editado["estado_civil"] == "Casado(a)" and editado["telefono"] == "988777666")
    comprobar("PATCH con es_apoderado=null no lo apaga", editado["es_apoderado"] is True)
    borrado = exigir(pedir("PATCH", f"/admin/personas/contactos/{madre['id']}", h_psi, json={"distrito": None}), 200, "borrar distrito")
    comprobar("PATCH con null borra un campo de texto", borrado["distrito"] is None)
    r = pedir("POST", ruta, h_psi, json={"nombre": ""})
    comprobar("Nombre vacío: 422", r.status_code == 422)

    print("\n3 · Rol colegio")
    lista_col = exigir(pedir("GET", ruta, h_col), 200, "colegio lista")
    madre_col = next(c for c in lista_col if c["id"] == madre["id"])
    comprobar("Colegio ve nombre, apellidos, parentesco y teléfono",
              (madre_col["nombre"], madre_col["apellidos"], madre_col["relacion"], madre_col["telefono"])
              == ("Rosa", "Quispe Mamani", "Madre", "988777666"))
    comprobar("Colegio ve que es apoderada", madre_col["es_apoderado"] is True)
    ocultos = [c for c in SOLO_STAFF if any(f[c] is not None for f in lista_col)]
    comprobar("Colegio NO ve el entorno familiar de nadie", not ocultos, f"visibles: {ocultos}")
    lista_psi = exigir(pedir("GET", ruta, h_psi), 200, "psicólogo lista")
    comprobar("El psicólogo sí lo ve", next(c for c in lista_psi if c["id"] == madre["id"])["ocupacion"] == "Directora")
    comprobar("Colegio no puede crear familiares (403)", pedir("POST", ruta, h_col, json={"nombre": "X"}).status_code == 403)
    comprobar("Colegio no puede editar familiares (403)",
              pedir("PATCH", f"/admin/personas/contactos/{madre['id']}", h_col, json={"ocupacion": "X"}).status_code == 403)

    print("\n4 · Otra institución")
    comprobar("B no ve los familiares (403)", pedir("GET", ruta, h_psi_b).status_code == 403)
    comprobar("B no edita (403)",
              pedir("PATCH", f"/admin/personas/contactos/{madre['id']}", h_psi_b, json={"ocupacion": "X"}).status_code == 403)

    print("\n5 · Exportación ARCO")
    arco = exigir(pedir("GET", f"/admin/personas/{persona}/exportar-datos-arco", h_psi), 200, "ARCO")
    def vacios(valor, ruta="arco"):
        """Rutas del export que salieron como {} (fila ORM expirada)."""
        if valor == {}:
            return [ruta]
        if isinstance(valor, dict):
            return [r for k, v in valor.items() for r in vacios(v, f"{ruta}.{k}")]
        if isinstance(valor, list):
            return [r for i, v in enumerate(valor) for r in vacios(v, f"{ruta}[{i}]")]
        return []

    huecos = vacios(arco)
    comprobar("Ninguna sección del export ARCO sale vacía ({})", not huecos, ", ".join(huecos[:5]))
    fam = {c.get("id"): c for c in arco.get("contactos_familiares", [])}
    comprobar("ARCO trae a los 4 familiares", len(fam) == 4, str(len(fam)))
    comprobar("ARCO trae los campos nuevos", fam.get(madre["id"], {}).get("ocupacion") == "Directora"
              and fam.get(hermano["id"], {}).get("fecha_nacimiento") == "2014-06-15")

    total, ok = len(resultados), sum(1 for _, b in resultados if b)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {ok}/{total} comprobaciones superadas")
    for n, b in resultados:
        if not b:
            print(f"  - {n}")
    print("=" * 72)
    return 0 if ok == total else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpiar", action="store_true")
    if ap.parse_args().limpiar:
        limpiar()
    else:
        sys.exit(main())
