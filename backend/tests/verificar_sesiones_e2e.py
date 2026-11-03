"""E2E — sesiones de servidor: token corto con renovación, cookies httpOnly,
cerrar sesión y bloqueo por inactividad del lado del servidor (sesión
2026-11-02, core/sesiones.py + modulos/auth/router.py).

Contra uvicorn real en :8010 (captcha no obligatorio). Crea su propio
usuario psicólogo directamente en la BD (prefijo ZZSES) y lo borra con
--limpiar.

  1  Login: dos cookies httpOnly (acceso path /api, renovación path
     /api/auth), SameSite; el cuerpo trae `sesion` y sigue trayendo el token
  2  Por cookie: GET sin cabecera anti-CSRF pasa; POST sin ella → 403, con
     ella → llega a validar el cuerpo (422)
  3  Bearer sigue funcionando y no exige la cabecera (no la adjunta ningún
     navegador)
  4  Renovar: acceso nuevo, actualiza ultimo_uso, sin token en el cuerpo;
     sin cabecera anti-CSRF → 403
  5  Bloquear: la sesión deja de valer EN EL SERVIDOR (cookie y Bearer → 401),
     renovar → 401 y borra las cookies
  6  Desbloquear = login nuevo: la sesión vieja queda revocada como
     'reemplazada' y la nueva funciona
  7  Cerrar sesión: revoca; un acceso copiado antes ya no sirve (cookie ni
     Bearer); repetirlo no falla
  8  Cambio de contraseña (token_version) → acceso y renovación inválidos
  9  Inactividad del servidor: sin renovarse por más de
     SESION_INACTIVIDAD_MINUTOS → renovar 401; vida máxima vencida → 401
 10  Token sin `sid` (anterior a esta sesión) se sigue aceptando

    uvicorn main:app --port 8010   (LOGIN_CAPTCHA_OBLIGATORIO=false)
    python -m tests.verificar_sesiones_e2e
    python -m tests.verificar_sesiones_e2e --limpiar
"""
import argparse
import os
import sys
import time
from datetime import timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from core import sesiones  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from core.security import create_access_token, get_password_hash  # noqa: E402
from modulos.auth import models  # noqa: E402
from modulos.instituciones import models as inst_models  # noqa: E402

API = "http://127.0.0.1:8010/api"
EMAIL = "zzses.psicologo@aurorasoft.test"
CLAVE = "ZzSes-Clave-2026!"
CSRF = {"X-Aurora-Cliente": "web"}
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def limpiar():
    db = SessionLocal()
    try:
        u = db.query(models.Usuario).filter(models.Usuario.email == EMAIL).first()
        if u:
            db.query(models.SesionUsuario).filter(models.SesionUsuario.usuario_id == u.id).delete()
            db.delete(u)
        db.commit()
        print("Datos ZZSES borrados.")
    finally:
        db.close()


def preparar_usuario():
    db = SessionLocal()
    try:
        u = db.query(models.Usuario).filter(models.Usuario.email == EMAIL).first()
        inst = db.query(inst_models.Institucion).filter(inst_models.Institucion.plan_activo == True).first()  # noqa: E712
        if u is None:
            u = models.Usuario(email=EMAIL, nombre_completo="ZZSES Psicólogo", rol="psicologo", activo=True)
            db.add(u)
        u.hashed_password = get_password_hash(CLAVE)
        u.institucion_id = inst.id
        u.activo = True
        u.token_version = 0
        db.commit()
        return u.id
    finally:
        db.close()


def login(cliente: requests.Session):
    for _ in range(3):
        r = cliente.post(f"{API}/auth/login", data={"username": EMAIL, "password": CLAVE})
        if r.status_code != 429:
            return r
        print("     (rate limit del login: espero 60 s)")
        time.sleep(61)
    return r


def sesion_bd(sid):
    db = SessionLocal()
    try:
        return db.query(models.SesionUsuario).filter(models.SesionUsuario.id == sid).first()
    finally:
        db.close()


def tocar_bd(sid=None, usuario_id=None, **campos):
    db = SessionLocal()
    try:
        if sid:
            db.query(models.SesionUsuario).filter(models.SesionUsuario.id == sid).update(campos)
        else:
            db.query(models.Usuario).filter(models.Usuario.id == usuario_id).update(campos)
        db.commit()
    finally:
        db.close()


def sid_de(token):
    from jose import jwt

    return jwt.get_unverified_claims(token).get("sid")


def cookie(cliente, nombre):
    return next((c for c in cliente.cookies if c.name == nombre), None)


def main():
    usuario_id = preparar_usuario()

    print("\n1 · Login con cookies httpOnly")
    c = requests.Session()
    r = login(c)
    comprobar("Login 200", r.status_code == 200, r.text[:200])
    cuerpo = r.json()
    comprobar("El cuerpo trae `sesion` con rol", cuerpo.get("sesion", {}).get("rol") == "psicologo")
    comprobar("…y sigue trayendo access_token (Swagger/e2e)", bool(cuerpo.get("access_token")))
    cabeceras = r.headers.get("set-cookie", "").lower()
    acceso, renov = cookie(c, sesiones.COOKIE_ACCESO), cookie(c, sesiones.COOKIE_RENOVACION)
    comprobar("Cookie de acceso, path /api", acceso is not None and acceso.path == "/api")
    comprobar("Cookie de renovación, path /api/auth", renov is not None and renov.path == "/api/auth")
    comprobar("Ambas httpOnly", cabeceras.count("httponly") >= 2)
    comprobar("Ambas con SameSite", cabeceras.count("samesite=") >= 2)
    sid = sid_de(cuerpo["access_token"])
    fila = sesion_bd(sid)
    comprobar("Sesión guardada en la BD con hash (no el token)", fila is not None and len(fila.hash_renovacion) == 64 and fila.hash_renovacion != renov.value)
    comprobar("Vida máxima ≈ SESION_HORAS", fila is not None and abs((fila.expira_en - fila.creada_en) - timedelta(hours=sesiones.SESION_HORAS)) < timedelta(minutes=1))

    print("\n2 · Autenticación por cookie y CSRF")
    r = c.get(f"{API}/auth/me")
    comprobar("GET /auth/me solo con la cookie → 200", r.status_code == 200 and r.json().get("email") == EMAIL, r.text[:150])
    r = c.post(f"{API}/educativo/seguimiento/", json={})
    comprobar("POST por cookie SIN cabecera anti-CSRF → 403", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
    r = c.post(f"{API}/educativo/seguimiento/", json={}, headers=CSRF)
    comprobar("…CON la cabecera pasa la autenticación (llega a validar: 422)", r.status_code == 422, f"{r.status_code} {r.text[:120]}")

    print("\n3 · Bearer sigue funcionando")
    b = {"Authorization": f"Bearer {cuerpo['access_token']}"}
    comprobar("GET con Bearer → 200", requests.get(f"{API}/auth/me", headers=b).status_code == 200)
    comprobar("POST con Bearer no exige la cabecera (422)", requests.post(f"{API}/educativo/seguimiento/", json={}, headers=b).status_code == 422)

    print("\n4 · Renovar")
    tocar_bd(sid=sid, ultimo_uso=sesiones.ahora_utc() - timedelta(minutes=5))
    acceso_antes = cookie(c, sesiones.COOKIE_ACCESO).value
    r = c.post(f"{API}/auth/renovar")
    comprobar("Sin cabecera anti-CSRF → 403", r.status_code == 403)
    time.sleep(1.1)  # para que el `exp` del JWT nuevo cambie
    r = c.post(f"{API}/auth/renovar", headers=CSRF)
    comprobar("Con cabecera → 200", r.status_code == 200, r.text[:150])
    comprobar("Sin token en el cuerpo", "access_token" not in r.json() and r.json().get("sesion", {}).get("email") == EMAIL)
    comprobar("Cookie de acceso nueva", cookie(c, sesiones.COOKIE_ACCESO).value != acceso_antes)
    fila = sesion_bd(sid)
    comprobar("ultimo_uso actualizado", sesiones.ahora_utc() - fila.ultimo_uso < timedelta(minutes=1))
    comprobar("El acceso renovado funciona", c.get(f"{API}/auth/me").status_code == 200)

    print("\n5 · Bloquear por inactividad (servidor)")
    r = c.post(f"{API}/auth/bloquear", headers=CSRF)
    comprobar("POST /auth/bloquear → 204", r.status_code == 204)
    comprobar("bloqueada_en guardado", sesion_bd(sid).bloqueada_en is not None)
    comprobar("La cookie de acceso ya no sirve → 401", c.get(f"{API}/auth/me").status_code == 401)
    comprobar("Bearer de la misma sesión → 401", requests.get(f"{API}/auth/me", headers=b).status_code == 401)
    r = c.post(f"{API}/auth/renovar", headers=CSRF)
    comprobar("Renovar una sesión bloqueada → 401", r.status_code == 401)
    comprobar("…y borra las cookies", cookie(c, sesiones.COOKIE_RENOVACION) is None and cookie(c, sesiones.COOKIE_ACCESO) is None)
    comprobar("Bloquear otra vez no falla (idempotente)", c.post(f"{API}/auth/bloquear", headers=CSRF).status_code == 204)

    print("\n6 · Desbloquear = login nuevo que reemplaza la sesión")
    c2 = requests.Session()
    login(c2)
    sid_viejo = sid_de(cookie(c2, sesiones.COOKIE_ACCESO).value)
    c2.post(f"{API}/auth/bloquear", headers=CSRF)
    r = login(c2)  # trae la cookie de renovación de la sesión bloqueada
    sid_nuevo = sid_de(r.json()["access_token"])
    viejo = sesion_bd(sid_viejo)
    comprobar("La sesión bloqueada queda revocada como 'reemplazada'", viejo.revocada_en is not None and viejo.motivo_revocacion == "reemplazada")
    comprobar("La sesión nueva funciona", sid_nuevo != sid_viejo and c2.get(f"{API}/auth/me").status_code == 200)

    print("\n7 · Cerrar sesión")
    acceso_copiado = cookie(c2, sesiones.COOKIE_ACCESO).value
    r = c2.post(f"{API}/auth/cerrar-sesion", headers=CSRF)
    comprobar("POST /auth/cerrar-sesion → 204", r.status_code == 204)
    fila = sesion_bd(sid_nuevo)
    comprobar("Revocada como 'cierre_sesion'", fila.revocada_en is not None and fila.motivo_revocacion == "cierre_sesion")
    comprobar("Cookies borradas", cookie(c2, sesiones.COOKIE_ACCESO) is None and cookie(c2, sesiones.COOKIE_RENOVACION) is None)
    otro = requests.Session()
    otro.cookies.set(sesiones.COOKIE_ACCESO, acceso_copiado, path="/api")
    comprobar("Un acceso copiado ANTES de cerrar ya no sirve (cookie)", otro.get(f"{API}/auth/me").status_code == 401)
    comprobar("…ni como Bearer", requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {acceso_copiado}"}).status_code == 401)
    comprobar("Cerrar sesión otra vez no falla", c2.post(f"{API}/auth/cerrar-sesion", headers=CSRF).status_code == 204)
    comprobar("Cerrar sesión sin cabecera anti-CSRF → 403", requests.post(f"{API}/auth/cerrar-sesion").status_code == 403)

    print("\n8 · Cambio de contraseña")
    c3 = requests.Session()
    login(c3)
    tocar_bd(usuario_id=usuario_id, token_version=1)
    comprobar("El acceso deja de valer", c3.get(f"{API}/auth/me").status_code == 401)
    comprobar("Y la renovación también", c3.post(f"{API}/auth/renovar", headers=CSRF).status_code == 401)
    tocar_bd(usuario_id=usuario_id, token_version=0)

    print("\n9 · Inactividad y vida máxima en el servidor")
    c4 = requests.Session()
    login(c4)
    sid4 = sid_de(cookie(c4, sesiones.COOKIE_ACCESO).value)
    tocar_bd(sid=sid4, ultimo_uso=sesiones.ahora_utc() - timedelta(minutes=sesiones.SESION_INACTIVIDAD_MINUTOS + 1))
    comprobar(
        f"Sin renovarse por más de {sesiones.SESION_INACTIVIDAD_MINUTOS:g} min → renovar 401",
        c4.post(f"{API}/auth/renovar", headers=CSRF).status_code == 401,
    )
    c5 = requests.Session()
    login(c5)
    sid5 = sid_de(cookie(c5, sesiones.COOKIE_ACCESO).value)
    comprobar("(control) sesión nueva válida", c5.get(f"{API}/auth/me").status_code == 200)
    tocar_bd(sid=sid5, expira_en=sesiones.ahora_utc() - timedelta(seconds=1))
    comprobar("Vida máxima vencida → el acceso ya no vale", c5.get(f"{API}/auth/me").status_code == 401)

    print("\n10 · Compatibilidad: token sin `sid`")
    viejo = create_access_token({"sub": EMAIL, "rol": "psicologo", "tv": 0})
    comprobar("Se sigue aceptando hasta que venza", requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {viejo}"}).status_code == 200)

    print(f"\n{sum(_resultados)}/{len(_resultados)} comprobaciones pasan.")
    sys.exit(0 if all(_resultados) else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    if parser.parse_args().limpiar:
        limpiar()
    else:
        main()
