"""🆕 (2026-11-15) Recuperar y cambiar la contraseña, contra un servidor real.

Prefijo ZZPASS. Necesita la BD real y `uvicorn main:app --port 8010` con el
SMTP deshabilitado (EMAIL_USUARIO vacío) y PROXIES_CONFIABLES=127.0.0.1: cada
petición sale con su propia X-Forwarded-For para no chocar con el rate limit
por IP del login y de la recuperación (aquí se prueba otra cosa).

Cubre:
  1. "¿Olvidaste tu contraseña?" para TODA cuenta activa (psicólogo, admin,
     colegio), no solo superadmin; nada para una desactivada ni para un
     correo inexistente, con la misma respuesta; tope de 3 enlaces por hora
     por cuenta; el enlace sirve una vez, cierra las sesiones abiertas y no
     sirve para una cuenta desactivada después de pedirlo.
  2. "Cambiar contraseña" desde la sesión (cookies, como el navegador):
     exige la actual (400, nunca 401), rechaza la misma, corta/larga (422) y
     sin la cabecera anti-CSRF (403); al cambiarla, ESTA sesión sigue viva,
     la de otro navegador queda revocada en el servidor, la clave vieja ya no
     entra y un enlace de recuperación pendiente deja de servir.

    python -m tests.verificar_password_e2e [--limpiar]
"""
import argparse
import hashlib
import itertools
import os
import random
import sys
import uuid

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
BASE = os.getenv("E2E_BASE_URL", "http://127.0.0.1:8010")
API = f"{BASE}/api"
PREFIJO = "ZZPASS"
CLAVE = "ClaveInicial123"
engine = create_engine(os.environ["DATABASE_URL"])

resultados = []
# Primer octeto al azar: cada corrida usa IPs nuevas y no hereda el rate
# limit de la anterior.
_ips = (f"10.{random.randint(1, 250)}.{a}.{b}" for a, b in itertools.product(range(1, 250), range(1, 250)))


def comprobar(nombre, condicion, detalle=""):
    resultados.append(bool(condicion))
    print(f"  {'[PASA]' if condicion else '[FALLA]'} {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def cab(extra=None):
    return {"X-Forwarded-For": next(_ips), **(extra or {})}


def sql(consulta, **p):
    with engine.begin() as c:
        return c.execute(text(consulta), p)


def login_bearer(email, clave):
    return requests.post(f"{API}/auth/login", data={"username": email, "password": clave}, headers=cab(), timeout=30)


def navegador(email, clave):
    """Una sesión con cookies, como el frontend."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", data={"username": email, "password": clave}, headers=cab(), timeout=30)
    return s, r.status_code


def me(s):
    return s.get(f"{API}/auth/me", headers=cab(), timeout=30).status_code


def cambiar(s, actual, nueva, csrf=True):
    h = cab({"x-aurora-cliente": "1"} if csrf else None)
    return s.post(f"{API}/auth/cambiar-password", json={"password_actual": actual, "nueva_password": nueva},
                  headers=h, timeout=30)


def solicitar(email):
    return requests.post(f"{API}/auth/solicitar-recuperacion", json={"email": email}, headers=cab(), timeout=30)


def tokens_vivos(email):
    return sql("select count(*) from auth_tokens_recuperacion t join auth_usuarios u on u.id=t.usuario_id "
               "where lower(u.email)=lower(:e) and t.usado=false", e=email).scalar()


def token_directo(email):
    """El correo no sale en el e2e (SMTP apagado): se inserta un enlace con el
    mismo formato (la BD guarda solo el SHA-256) y se usa el token en claro."""
    plano = uuid.uuid4().hex + uuid.uuid4().hex
    sql("insert into auth_tokens_recuperacion (usuario_id, token, fecha_expiracion, usado) "
        "select id, :t, now() + interval '1 hour', false from auth_usuarios where lower(email)=lower(:e)",
        t=hashlib.sha256(plano.encode()).hexdigest(), e=email)
    return plano


def resetear(token, nueva):
    return requests.post(f"{API}/auth/resetear-password", json={"token": token, "nueva_password": nueva},
                         headers=cab(), timeout=30)


def limpiar():
    ids = [f[0] for f in sql("select id from instituciones where nombre like :p", p=f"{PREFIJO}%").all()]
    usuarios = "select id from auth_usuarios where email like :p"
    p = f"{PREFIJO.lower()}.%"
    sql(f"delete from auth_tokens_recuperacion where usuario_id in ({usuarios})", p=p)
    sql(f"delete from auth_sesiones where usuario_id in ({usuarios})", p=p)
    sql("delete from auth_usuarios where email like :p", p=p)
    for i in ids:
        sql("delete from instituciones where id=:i", i=i)
    print(f"Limpieza {PREFIJO}: {len(ids)} institución(es) y sus usuarios.")


def main():
    sello = uuid.uuid4().hex[:8]
    correo = lambda rol: f"{PREFIJO.lower()}.{rol}.{sello}@ejemplo.com"  # noqa: E731

    r = login_bearer(os.environ["SUPERADMIN_EMAIL"], os.environ["SUPERADMIN_PASSWORD"])
    if r.status_code != 200:
        sys.exit(f"No pude iniciar sesión como superadmin ({r.status_code}).")
    h_super = cab({"Authorization": f"Bearer {r.json()['access_token']}"})
    inst = requests.post(f"{API}/instituciones/", json={"nombre": f"{PREFIJO} Colegio {sello}", "tipo": "Colegio"},
                         headers=h_super, timeout=30)
    inst.raise_for_status()
    iid = inst.json()["id"]
    for rol in ("psicologo", "admin", "colegio", "inactivo"):
        r = requests.post(f"{API}/auth/registro", headers=h_super, timeout=30, json={
            "email": correo(rol), "password": CLAVE, "nombre_completo": f"{PREFIJO} {rol}",
            "rol": "psicologo" if rol == "inactivo" else rol, "institucion_id": iid})
        r.raise_for_status()
        if rol == "inactivo":
            requests.patch(f"{API}/auth/usuarios/{r.json()['id']}", json={"activo": False},
                           headers=h_super, timeout=30).raise_for_status()

    print("\n1 · ¿Olvidaste tu contraseña? — para toda cuenta activa")
    respuestas = {}
    for rol in ("psicologo", "admin", "colegio", "inactivo"):
        r = solicitar(correo(rol))
        respuestas[rol] = (r.status_code, r.json().get("mensaje"))
        esperado = 0 if rol == "inactivo" else 1
        comprobar(f"{rol}: {esperado} enlace emitido", tokens_vivos(correo(rol)) == esperado,
                  f"{tokens_vivos(correo(rol))} enlace(s)")
    r = solicitar(f"{PREFIJO.lower()}.noexiste.{sello}@ejemplo.com")
    respuestas["inexistente"] = (r.status_code, r.json().get("mensaje"))
    comprobar("Misma respuesta exista o no la cuenta, activa o no", len(set(respuestas.values())) == 1,
              str(respuestas))
    comprobar("Lo guardado es el hash, nunca un token corto en claro",
              sql("select min(length(t.token)) from auth_tokens_recuperacion t join auth_usuarios u "
                  "on u.id=t.usuario_id where u.email=:e", e=correo("psicologo")).scalar() == 64)

    for _ in range(2):
        solicitar(correo("admin"))
    comprobar("admin: 3 enlaces tras 3 pedidos", tokens_vivos(correo("admin")) == 3)
    solicitar(correo("admin"))
    comprobar("Tope por cuenta: el 4.º pedido en la hora no emite otro", tokens_vivos(correo("admin")) == 3)

    print("\n  Usar el enlace")
    s_abierta, st = navegador(correo("psicologo"), CLAVE)
    comprobar("Sesión abierta antes de restablecer", st == 200 and me(s_abierta) == 200)
    tok = token_directo(correo("psicologo"))
    comprobar("Clave corta: 422", resetear(tok, "corta").status_code == 422)
    comprobar("Clave de más de 72 bytes: 422", resetear(tok, "ñ" * 40).status_code == 422)
    comprobar("Restablecer con el enlace: 200", resetear(tok, "NuevaPorCorreo456").status_code == 200)
    comprobar("El enlace no sirve dos veces", resetear(tok, "OtraMas789xyz").status_code == 400)
    comprobar("El otro enlace pendiente de esa cuenta también quedó anulado", tokens_vivos(correo("psicologo")) == 0)
    comprobar("La sesión que estaba abierta quedó cerrada (401)", me(s_abierta) == 401)
    comprobar("...y revocada en el servidor",
              sql("select count(*) from auth_sesiones s join auth_usuarios u on u.id=s.usuario_id "
                  "where u.email=:e and s.revocada_en is null", e=correo("psicologo")).scalar() == 0)
    comprobar("La clave vieja ya no entra", login_bearer(correo("psicologo"), CLAVE).status_code == 401)
    comprobar("La nueva sí", login_bearer(correo("psicologo"), "NuevaPorCorreo456").status_code == 200)

    tok = token_directo(correo("colegio"))
    sql("update auth_usuarios set activo=false where email=:e", e=correo("colegio"))
    comprobar("Cuenta desactivada después de pedir el enlace: 400", resetear(tok, "NoDebeCambiar123").status_code == 400)
    sql("update auth_usuarios set activo=true where email=:e", e=correo("colegio"))
    comprobar("...y su contraseña no cambió", login_bearer(correo("colegio"), CLAVE).status_code == 200)

    print("\n2 · Cambiar contraseña desde la sesión")
    s1, st1 = navegador(correo("colegio"), CLAVE)
    s2, st2 = navegador(correo("colegio"), CLAVE)
    comprobar("Dos navegadores con sesión", st1 == st2 == 200)
    r = cambiar(s1, "NoEsLaActual1", "OtraClave12345")
    comprobar("Actual equivocada: 400 (no 401, la sesión sigue)", r.status_code == 400 and me(s1) == 200,
              f"{r.status_code}")
    comprobar("Misma contraseña: 400", cambiar(s1, CLAVE, CLAVE).status_code == 400)
    comprobar("Nueva corta: 422", cambiar(s1, CLAVE, "abc").status_code == 422)
    comprobar("Sin cabecera anti-CSRF: 403", cambiar(s1, CLAVE, "OtraClave12345", csrf=False).status_code == 403)
    pendiente = token_directo(correo("colegio"))
    r = cambiar(s1, CLAVE, "OtraClave12345")
    comprobar("Cambio correcto: 200", r.status_code == 200, r.text[:200])
    comprobar("ESTE navegador sigue con sesión", me(s1) == 200)
    comprobar("...y puede renovar el acceso",
              s1.post(f"{API}/auth/renovar", headers=cab({"x-aurora-cliente": "1"}), timeout=30).status_code == 200)
    comprobar("El OTRO navegador quedó fuera (401)", me(s2) == 401)
    comprobar("...ni siquiera puede renovar",
              s2.post(f"{API}/auth/renovar", headers=cab({"x-aurora-cliente": "1"}), timeout=30).status_code == 401)
    comprobar("La clave vieja ya no entra", login_bearer(correo("colegio"), CLAVE).status_code == 401)
    comprobar("La nueva sí", login_bearer(correo("colegio"), "OtraClave12345").status_code == 200)
    comprobar("Un enlace de recuperación pedido antes ya no sirve", resetear(pendiente, "PisarlaAhora123").status_code == 400)

    # Por Bearer (scripts) también funciona: el token viejo deja de valer.
    tok_admin = login_bearer(correo("admin"), CLAVE).json()["access_token"]
    h = cab({"Authorization": f"Bearer {tok_admin}"})
    r = requests.post(f"{API}/auth/cambiar-password", json={"password_actual": CLAVE, "nueva_password": "AdminNueva2026"},
                      headers=h, timeout=30)
    comprobar("Por Bearer: 200", r.status_code == 200)
    comprobar("...y ese Bearer ya no vale (sesión conservada solo con cookies)",
              requests.get(f"{API}/auth/me", headers=cab({"Authorization": f"Bearer {tok_admin}"}), timeout=30).status_code == 401)

    print("\n3 · Corregir el correo de una cuenta")
    uid = lambda e: sql("select id from auth_usuarios where email=:e", e=e).scalar()  # noqa: E731
    s_psi, _ = navegador(correo("psicologo"), "NuevaPorCorreo456")
    nuevo = f"{PREFIJO.lower()}.psicologo.real.{sello}@ejemplo.com"
    tok_adm = login_bearer(correo("admin"), "AdminNueva2026").json()["access_token"]
    h_adm = cab({"Authorization": f"Bearer {tok_adm}"})
    r = requests.patch(f"{API}/auth/usuarios/{uid(correo('admin'))}", json={"email": nuevo}, headers=h_adm, timeout=30)
    comprobar("Un admin NO cambia el correo de un admin (403)", r.status_code == 403, str(r.status_code))
    r = requests.patch(f"{API}/auth/usuarios/{uid(correo('psicologo'))}", json={"email": correo("colegio")}, headers=h_adm, timeout=30)
    comprobar("Correo ya usado por otra cuenta: 409", r.status_code == 409, str(r.status_code))
    r = requests.patch(f"{API}/auth/usuarios/{uid(correo('psicologo'))}", json={"email": nuevo}, headers=h_adm, timeout=30)
    comprobar("El admin corrige el correo de una psicóloga de su colegio: 200", r.status_code == 200 and r.json()["email"] == nuevo, r.text[:200])
    comprobar("Sus sesiones abiertas se cerraron (401)", me(s_psi) == 401)
    comprobar("Con el correo viejo ya no entra", login_bearer(correo("psicologo"), "NuevaPorCorreo456").status_code == 401)
    comprobar("Con el nuevo y la misma clave, sí", login_bearer(nuevo, "NuevaPorCorreo456").status_code == 200)
    sql("update auth_usuarios set email=:v where email=:n", v=correo("psicologo"), n=nuevo)

    total, ok = len(resultados), sum(resultados)
    print(f"\nRESULTADO: {ok}/{total} comprobaciones superadas")
    return ok == total


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--limpiar", action="store_true")
    if a.parse_args().limpiar:
        limpiar()
        sys.exit(0)
    exito = main()
    limpiar()
    sys.exit(0 if exito else 1)
