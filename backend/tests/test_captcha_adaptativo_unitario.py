"""Unitario — captcha adaptativo del login (core/captcha.py, sesión 2026-11-01).

Sin BD ni servidor. Comprueba que el captcha solo se exige tras
FALLOS_PARA_CAPTCHA contraseñas fallidas recientes por IP o por correo, que un
login correcto reinicia los contadores, que la ventana de 15 minutos caduca,
y que LOGIN_CAPTCHA_OBLIGATORIO=false / LOGIN_CAPTCHA_SIEMPRE=true siguen
mandando sobre todo lo demás. Además, por inspección del router, que el login
registra el fallo DESPUÉS de mirar el captcha y limpia al acertar.

    python -m tests.test_captcha_adaptativo_unitario
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SECRET_KEY", "clave-de-prueba-unitaria")
os.environ.setdefault("DATABASE_URL", "postgresql://x:y@localhost/z")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core import captcha  # noqa: E402

_resultados = []


def comprobar(nombre, condicion):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}")


def reiniciar(obligatorio=True, siempre=False):
    captcha._fallos.clear()
    captcha.CAPTCHA_OBLIGATORIO = obligatorio
    captcha.CAPTCHA_SIEMPRE = siempre


def main():
    n = captcha.FALLOS_PARA_CAPTCHA
    print(f"\nCaptcha adaptativo (umbral = {n} fallos)")

    reiniciar()
    comprobar("Sin fallos: no se pide captcha", not captcha.captcha_requerido("1.1.1.1", "ana@x.com"))
    for _ in range(n - 1):
        captcha.registrar_fallo("1.1.1.1", "ana@x.com")
    comprobar(f"Con {n - 1} fallos todavía no", not captcha.captcha_requerido("1.1.1.1", "ana@x.com"))
    captcha.registrar_fallo("1.1.1.1", "ana@x.com")
    comprobar(f"Al fallo {n}: sí, para esa IP", captcha.captcha_requerido("1.1.1.1"))
    comprobar("…y para ese correo desde otra IP (ataque a una cuenta)", captcha.captcha_requerido("9.9.9.9", "ANA@x.com "))
    comprobar("Otra IP con otro correo: no", not captcha.captcha_requerido("9.9.9.9", "beto@x.com"))

    reiniciar()
    for i in range(n):
        captcha.registrar_fallo("2.2.2.2", f"usuario{i}@x.com")
    comprobar("Muchos correos distintos desde una IP: la IP exige captcha", captcha.captcha_requerido("2.2.2.2", "nuevo@x.com"))

    captcha.limpiar_fallos("2.2.2.2", "usuario0@x.com")
    comprobar("Login correcto reinicia el contador de la IP", not captcha.captcha_requerido("2.2.2.2"))

    reiniciar()
    for _ in range(n):
        captcha.registrar_fallo("3.3.3.3", "caro@x.com")
    vieja = captcha.time.monotonic() - captcha.VENTANA_FALLOS_SEGUNDOS - 1
    for clave in list(captcha._fallos):
        captcha._fallos[clave] = [vieja] * n
    comprobar("Fallos de hace más de 15 minutos ya no cuentan", not captcha.captcha_requerido("3.3.3.3", "caro@x.com"))

    reiniciar(obligatorio=False)
    for _ in range(n + 2):
        captcha.registrar_fallo("4.4.4.4", "dani@x.com")
    comprobar("LOGIN_CAPTCHA_OBLIGATORIO=false: nunca", not captcha.captcha_requerido("4.4.4.4", "dani@x.com"))

    reiniciar(siempre=True)
    comprobar("LOGIN_CAPTCHA_SIEMPRE=true: siempre, sin fallos", captcha.captcha_requerido("5.5.5.5", "eva@x.com"))

    reiniciar()
    for i in range(captcha.MAX_CLAVES_FALLOS + 50):
        captcha._fallos[f"ip:x{i}"] = [captcha.time.monotonic()]
    captcha.registrar_fallo("6.6.6.6", None)
    comprobar("El almacén de contadores tiene tope", len(captcha._fallos) <= captcha.MAX_CLAVES_FALLOS)

    print("\nRouter del login")
    from modulos.auth import router as auth_router
    fuente = inspect.getsource(auth_router.iniciar_sesion)
    comprobar("Mira el captcha ANTES de la contraseña", fuente.index("captcha_requerido") < fuente.index("verify_password"))
    comprobar("Registra el fallo de contraseña", "captcha.registrar_fallo(ip, form_data.username)" in fuente)
    comprobar("Limpia los contadores al acertar", "captcha.limpiar_fallos(ip, form_data.username)" in fuente)
    comprobar("GET /captcha usa la misma regla", "captcha_requerido" in inspect.getsource(auth_router.obtener_captcha))

    total, pasan = len(_resultados), sum(_resultados)
    print(f"\nRESULTADO: {pasan}/{total} comprobaciones superadas")
    return 0 if pasan == total else 1


if __name__ == "__main__":
    sys.exit(main())
