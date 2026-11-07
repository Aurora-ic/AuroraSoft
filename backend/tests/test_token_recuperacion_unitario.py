"""El token de recuperación de contraseña se guarda solo como SHA-256
(sesión 2026-11-07, revisión de seguridad previa al piloto) — ver
modulos/auth/crud.hash_token_recuperacion.

Sin servidor ni base de desarrollo: la tabla real `auth_tokens_recuperacion`
se crea en un SQLite en memoria, así la búsqueda por hash corre como SQL de
verdad. El flujo HTTP completo (solicitar → resetear → no reutilizable) lo
cubre el bloque C-4 de verificar_fase3_e2e.py.

    python -m tests.test_token_recuperacion_unitario
"""
import hashlib
import inspect
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modulos.auth import crud, models
from modulos.auth import router as auth_router

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def sesion():
    motor = create_engine("sqlite://")
    models.TokenRecuperacion.__table__.create(motor)
    return sessionmaker(bind=motor)()


def test_guardado():
    print("\n[1] Lo que se guarda y lo que se devuelve")
    db = sesion()
    token = crud.crear_token_recuperacion(db, usuario_id=7)
    fila = db.query(models.TokenRecuperacion).one()
    comprobar("devuelve el token en claro (para el correo)", isinstance(token, str) and len(token) >= 40, token)
    comprobar("la fila NO contiene el token en claro", fila.token != token)
    comprobar("la fila contiene su SHA-256", fila.token == hashlib.sha256(token.encode()).hexdigest(), fila.token)
    comprobar("el hash mide 64 caracteres hex", len(fila.token) == 64 and all(c in "0123456789abcdef" for c in fila.token))
    otro = crud.crear_token_recuperacion(db, usuario_id=7)
    comprobar("dos solicitudes → dos tokens distintos", otro != token)


def test_validacion():
    print("\n[2] Validar: solo el token en claro abre el enlace")
    db = sesion()
    token = crud.crear_token_recuperacion(db, usuario_id=7)
    registro = crud.validar_token_recuperacion(db, token)
    comprobar("el token en claro → encuentra la fila", registro is not None and registro.usuario_id == 7)
    guardado = db.query(models.TokenRecuperacion).one().token
    comprobar("lo que está en la BD (el hash) NO sirve como token",
              crud.validar_token_recuperacion(db, guardado) is None)
    comprobar("un token inventado → None", crud.validar_token_recuperacion(db, "x" * 43) is None)
    comprobar("vacío → None (sin consultar)", crud.validar_token_recuperacion(db, "") is None)
    comprobar("None → None", crud.validar_token_recuperacion(db, None) is None)

    registro.usado = True
    db.commit()
    comprobar("usado → None", crud.validar_token_recuperacion(db, token) is None)

    vencido = crud.crear_token_recuperacion(db, usuario_id=8)
    fila = db.query(models.TokenRecuperacion).filter(models.TokenRecuperacion.usuario_id == 8).one()
    fila.fecha_expiracion = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    comprobar("vencido → None", crud.validar_token_recuperacion(db, vencido) is None)


def test_fuentes():
    print("\n[3] El router manda por correo el token en claro y nunca lo guarda")
    fuente = inspect.getsource(auth_router.solicitar_recuperacion)
    comprobar("el correo recibe lo que devuelve crear_token_recuperacion",
              "token_plano = crud.crear_token_recuperacion" in fuente
              and "enviar_correo_recuperacion, usuario.email, token_plano" in fuente)
    comprobar("ya no lee `.token` de la fila (sería el hash)", "token_obj.token" not in fuente)


if __name__ == "__main__":
    test_guardado()
    test_validacion()
    test_fuentes()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO TOKEN DE RECUPERACIÓN CON HASH: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
