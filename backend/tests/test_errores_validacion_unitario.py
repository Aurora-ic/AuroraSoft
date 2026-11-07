"""El 422 no devuelve lo que mandó el cliente (sesión 2026-11-07, revisión de
seguridad previa al piloto) — ver core/errores_validacion.py.

Sin servidor: peticiones directas por ASGI a main.app. Ninguna llega a
consultar la base (la validación falla antes).

    python -m tests.test_errores_validacion_unitario
"""
import asyncio
import json
import sys

import main
from core.errores_validacion import limpiar_errores

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def llamar(metodo, path, cuerpo=b"", query=b"", content_type=b"application/json"):
    mensajes = []

    async def receive():
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def send(m):
        mensajes.append(m)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": metodo,
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": query,
             "headers": [(b"host", b"t"), (b"content-type", content_type),
                         (b"content-length", str(len(cuerpo)).encode())],
             "client": ("127.0.0.1", 1), "server": ("t", 80)}
    asyncio.run(main.app(scope, receive, send))
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    texto = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body").decode("utf-8")
    return inicio["status"], texto


def test_funcion():
    print("\n[1] limpiar_errores")
    errores = [{"type": "string_too_short", "loc": ("body", "nueva_password"), "msg": "muy corta",
                "input": "Clave7x", "ctx": {"min_length": 8}, "url": "https://errors.pydantic.dev/x"},
               {"type": "value_error", "loc": ("body", "x"), "msg": "Value error, malo", "input": {"dni": "45678912"},
                "ctx": {"error": ValueError("malo")}}]
    limpios = limpiar_errores(errores)
    comprobar("sin input", all("input" not in e for e in limpios))
    comprobar("sin url", all("url" not in e for e in limpios))
    comprobar("conserva type/loc/msg", limpios[0]["msg"] == "muy corta" and limpios[0]["loc"] == ("body", "nueva_password"))
    comprobar("conserva el límite del ctx (min_length)", limpios[0].get("ctx") == {"min_length": 8})
    comprobar("quita ctx.error y el ctx vacío", "ctx" not in limpios[1])


def test_reseteo():
    print("\n[2] POST /api/auth/resetear-password con una contraseña corta")
    cuerpo = json.dumps({"token": "tok-ZZ422", "nueva_password": "Clave7x"}).encode()
    status, texto = llamar("POST", "/api/auth/resetear-password", cuerpo)
    comprobar("422", status == 422, status)
    comprobar("la contraseña NO vuelve en la respuesta", "Clave7x" not in texto, texto[:300])
    comprobar("el token NO vuelve en la respuesta", "tok-ZZ422" not in texto)
    detalle = json.loads(texto)["detail"]
    comprobar("el mensaje para el usuario sigue (msg)", any("8 caracteres" in e.get("msg", "") for e in detalle), detalle)
    comprobar("sin 'input' ni 'url' en ningún error", all("input" not in e and "url" not in e for e in detalle))


def test_json_roto_y_query():
    print("\n[3] JSON roto y parámetro de query inválido")
    status, texto = llamar("POST", "/api/auth/resetear-password", b'{"token": "tok-ZZROTO", "nueva_password": ')
    comprobar("JSON roto → 422", status == 422, status)
    comprobar("JSON roto: el cuerpo recibido no vuelve", "tok-ZZROTO" not in texto, texto[:300])
    @main.app.get("/zz-prueba-422")
    def _zz_prueba(numero: int):
        return {"numero": numero}

    status, texto = llamar("GET", "/zz-prueba-422", query=b"numero=ZZTEXTO-45678912")
    comprobar("query inválida → 422", status == 422, status)
    comprobar("query inválida: el valor no vuelve", "45678912" not in texto, texto[:200])


if __name__ == "__main__":
    test_funcion()
    test_reseteo()
    test_json_roto_y_query()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO 422 SIN ECO DE DATOS: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
