"""Almacén compartido de seguridad en Redis (core/almacen_seguridad.py,
sesión 2026-11-02).

Necesita un Redis real (el mismo de Celery; usa la base 15 para no tocar
nada) pero NI la BD ni el servidor. Comprueba que, con ALMACEN_SEGURIDAD_URL:

  · un captcha emitido por un "worker" lo acepta OTRO (el almacén ya no es
    de un solo proceso) y es de uso único también entre procesos;
  · los fallos de contraseña registrados en un proceso disparan el captcha
    en otro, y un login correcto los limpia para todos;
  · el rate limit de slowapi cuenta en Redis (dos limitadores distintos
    comparten el cupo);
  · si Redis se cae, el login sigue funcionando con la memoria del proceso.

Cada "proceso" se simula recargando los módulos en un subproceso de Python
real — así no comparten NADA en memoria, solo Redis.

    python -m tests.test_almacen_seguridad_redis
"""

import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.getenv("ALMACEN_SEGURIDAD_URL_TEST", "redis://localhost:6379/15")

_resultados = []


def comprobar(nombre, condicion):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}")


def en_otro_proceso(codigo: str, url: str = URL) -> dict:
    """Corre `codigo` en un intérprete nuevo y devuelve el JSON que imprime."""
    entorno = dict(os.environ)
    entorno.update(
        SECRET_KEY="clave-de-prueba-redis",
        DATABASE_URL="postgresql://x:y@localhost/z",
        ALMACEN_SEGURIDAD_URL=url,
        LOGIN_CAPTCHA_OBLIGATORIO="true",
        LOGIN_CAPTCHA_SIEMPRE="false",
    )
    preambulo = "import json, sys\nsys.path.insert(0, %r)\nfrom core import captcha\n" % RAIZ
    salida = subprocess.run(
        [sys.executable, "-c", preambulo + codigo],
        capture_output=True, text=True, env=entorno, cwd=RAIZ, timeout=60,
    )
    if salida.returncode != 0:
        raise RuntimeError(salida.stderr)
    return json.loads(salida.stdout.strip().splitlines()[-1])


def main():
    import redis

    r = redis.Redis.from_url(URL)
    try:
        r.ping()
    except Exception as exc:  # noqa: BLE001
        print(f"Redis no disponible en {URL} ({exc}) — no se puede correr este test.")
        sys.exit(1)
    r.flushdb()

    print("\nCaptcha compartido entre procesos")
    # Proceso A emite el captcha y, solo para el test, saca el código leyendo
    # la huella que guardó (el código real nunca sale de generar_captcha).
    emitido = en_otro_proceso(
        "import unittest.mock as m\n"
        "codigos=[]\n"
        "orig=captcha._dibujar\n"
        "def espia(c):\n    codigos.append(c); return orig(c)\n"
        "with m.patch.object(captcha, '_dibujar', espia):\n"
        "    d=captcha.generar_captcha()\n"
        "print(json.dumps({'id': d['captcha_id'], 'codigo': codigos[0], 'en_memoria': len(captcha._almacen)}))"
    )
    comprobar("El proceso A no lo guarda en su memoria", emitido["en_memoria"] == 0)
    comprobar("Queda en Redis con TTL", 0 < r.ttl("aurora:seg:captcha:" + emitido["id"]) <= 300)

    verificar = (
        "try:\n    captcha.verificar_captcha(%r, %r); print(json.dumps({'ok': True}))\n"
        "except captcha.CaptchaInvalido as e:\n    print(json.dumps({'ok': False, 'msg': str(e)}))"
    )
    b = en_otro_proceso(verificar % (emitido["id"], emitido["codigo"].lower()))
    comprobar("El proceso B acepta el captcha emitido por A", b["ok"])
    c = en_otro_proceso(verificar % (emitido["id"], emitido["codigo"]))
    comprobar("Uso único entre procesos: C ya no puede reutilizarlo", not c["ok"])

    emitido2 = en_otro_proceso("d=captcha.generar_captcha(); print(json.dumps({'id': d['captcha_id']}))")
    malo = en_otro_proceso(verificar % (emitido2["id"], "ZZZZZ"))
    comprobar("Un código equivocado se rechaza", not malo["ok"])
    comprobar("…y el captcha queda consumido igual", r.exists("aurora:seg:captcha:" + emitido2["id"]) == 0)

    print("\nCaptcha adaptativo compartido entre procesos")
    n = en_otro_proceso("print(json.dumps({'n': captcha.FALLOS_PARA_CAPTCHA}))")["n"]
    for _ in range(n - 1):
        en_otro_proceso("captcha.registrar_fallo('7.7.7.7', 'ana@x.com'); print('{}')")
    req = "print(json.dumps({'r': captcha.captcha_requerido(%r, %r)}))"
    comprobar(f"Con {n - 1} fallos (en procesos distintos) todavía no", not en_otro_proceso(req % ("7.7.7.7", "ana@x.com"))["r"])
    en_otro_proceso("captcha.registrar_fallo('7.7.7.7', 'ana@x.com'); print('{}')")
    comprobar(f"Al fallo {n}, OTRO proceso ya exige captcha por IP", en_otro_proceso(req % ("7.7.7.7", None))["r"])
    comprobar("…y por correo desde otra IP", en_otro_proceso(req % ("8.8.8.8", "ANA@x.com "))["r"])
    comprobar("Las claves caducan solas (TTL ≤ 15 min)", 0 < r.ttl("aurora:seg:fallos:ip:7.7.7.7") <= 900)
    en_otro_proceso("captcha.limpiar_fallos('7.7.7.7', 'ana@x.com'); print('{}')")
    comprobar("Login correcto en un proceso limpia para todos", not en_otro_proceso(req % ("7.7.7.7", "ana@x.com"))["r"])

    print("\nRate limit compartido (slowapi sobre Redis)")
    limite = en_otro_proceso(
        "from core.limiter import limiter\n"
        "from limits import parse\n"
        "ok=[limiter.limiter.hit(parse('3/minute'), 'prueba', '1.2.3.4') for _ in range(2)]\n"
        "print(json.dumps({'ok': ok, 'almacen': type(limiter._storage).__name__}))"
    )
    comprobar("El limitador usa almacenamiento Redis", "Redis" in limite["almacen"])
    otro = en_otro_proceso(
        "from core.limiter import limiter\n"
        "from limits import parse\n"
        "ok=[limiter.limiter.hit(parse('3/minute'), 'prueba', '1.2.3.4') for _ in range(2)]\n"
        "print(json.dumps({'ok': ok}))"
    )
    comprobar("Otro proceso hereda el conteo: el 3.º pasa, el 4.º no", limite["ok"] == [True, True] and otro["ok"] == [True, False])

    print("\nRedis caído: el login no se cae")
    caido = en_otro_proceso(
        "for _ in range(captcha.FALLOS_PARA_CAPTCHA):\n    captcha.registrar_fallo('6.6.6.6', None)\n"
        "d=captcha.generar_captcha()\n"
        "print(json.dumps({'r': captcha.captcha_requerido('6.6.6.6'), 'id': bool(d['captcha_id']), 'mem': len(captcha._almacen)}))",
        url="redis://localhost:1/0",  # puerto que no escucha
    )
    comprobar("Sin Redis cuenta en memoria y sigue exigiendo captcha", caido["r"])
    comprobar("Sin Redis el captcha se emite en memoria", caido["id"] and caido["mem"] == 1)

    r.flushdb()
    print(f"\n{sum(_resultados)}/{len(_resultados)} comprobaciones pasaron")
    sys.exit(0 if all(_resultados) else 1)


if __name__ == "__main__":
    main()
