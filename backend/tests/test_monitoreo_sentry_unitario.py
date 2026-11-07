"""M4 de la revisión de seguridad (sesión 2026-11-07): Sentry no debe recibir
datos de alumnos ni credenciales — ver core/monitoreo.py.

Sin BD ni servidor y sin mandar nada a Sentry: la parte [4] inicia el SDK
real con un DSN de mentira y un transporte que GUARDA lo que se habría
enviado, provoca un error de verdad en main.app (ASGI directo) con un DNI,
un correo, el token del examen en la URL, una variable local con un
diagnóstico y un cuerpo JSON con datos, y revisa byte a byte el envío.

    python -m tests.test_monitoreo_sentry_unitario
"""
import asyncio
import json
import os
import sys

from core import monitoreo

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


TOKEN = "f3a9c1d2e4b5a6978877665544332211aabbccddeeff00112233445566778899"
DNI = "45678912"
CORREO = "alumna.prueba@colegio.pe"
DIAGNOSTICO = "Diagnostico confidencial ZZSENTRY"
RESPUESTA = "respuesta-secreta-ZZSENTRY"


def test_opciones():
    print("\n[1] Opciones de sentry_sdk.init()")
    os.environ.pop("SENTRY_TRACES_SAMPLE_RATE", None)
    o = monitoreo.opciones_sentry("api")
    comprobar("send_default_pii=False", o["send_default_pii"] is False)
    comprobar("include_local_variables=False (antes: True por defecto)", o["include_local_variables"] is False)
    comprobar("max_request_body_size='never'", o["max_request_body_size"] == "never")
    comprobar("trazas apagadas por defecto (antes: 1.0)", o["traces_sample_rate"] == 0.0)
    comprobar("before_send / before_send_transaction / before_breadcrumb conectados",
              o["before_send"] is monitoreo.limpiar_evento and o["before_send_transaction"] is monitoreo.limpiar_evento
              and o["before_breadcrumb"] is monitoreo.limpiar_miga)
    for valor, esperado in (("0.05", 0.05), ("abc", 0.0), ("7", 1.0), ("-1", 0.0)):
        os.environ["SENTRY_TRACES_SAMPLE_RATE"] = valor
        comprobar(f"SENTRY_TRACES_SAMPLE_RATE={valor!r} → {esperado}",
                  monitoreo.opciones_sentry("api")["traces_sample_rate"] == esperado)
    os.environ.pop("SENTRY_TRACES_SAMPLE_RATE", None)


def test_sin_dsn():
    print("\n[2] Sin SENTRY_DSN no se activa nada")
    previo = os.environ.pop("SENTRY_DSN", None)
    comprobar("iniciar_sentry() devuelve False", monitoreo.iniciar_sentry("api") is False)
    if previo is not None:
        os.environ["SENTRY_DSN"] = previo


def test_limpiar_evento():
    print("\n[3] limpiar_evento sobre un evento armado a mano")
    evento = {
        "request": {
            "method": "POST",
            "url": f"https://api.x.pe/api/examen/{TOKEN}/guardar?pregunta=3",
            "query_string": "pregunta=3",
            "cookies": {"aurora_sesion": "abc"},
            "data": {"respuesta": RESPUESTA},
            "env": {"REMOTE_ADDR": "190.1.2.3"},
            "headers": {"Authorization": "Bearer x", "Cookie": "a=b", "X-Forwarded-For": "190.1.2.3",
                        "User-Agent": "Chrome", "X-CSRF-Token": "zzz"},
        },
        "user": {"email": CORREO, "ip_address": "190.1.2.3"},
        "server_name": "PC-DE-ADMIN",
        "transaction": f"/api/auth/usuarios/7/firma/{TOKEN}",
        "contexts": {"celery-job": {"task_name": "x", "args": [CORREO]}, "runtime": {"name": "CPython"}},
        "exception": {"values": [{"type": "ValueError", "value": f"falló {DNI} {CORREO} {TOKEN}",
                                  "stacktrace": {"frames": [{"function": "f", "vars": {"d": DIAGNOSTICO}}]}}]},
        "logentry": {"message": f"Error no manejado en /api/examen/{TOKEN}/guardar", "params": [DNI]},
        "extra": {"persona": DIAGNOSTICO},
        "breadcrumbs": {"values": [
            {"category": "query", "message": f"SELECT * FROM personas WHERE dni = '{DNI}'"},
            {"category": "httplib", "data": {"url": f"https://x/api/examen/{TOKEN}/intake?a=1", "method": "GET",
                                              "body": RESPUESTA}},
            {"category": "log", "message": f"correo enviado a {CORREO}"},
        ]},
    }
    limpio = monitoreo.limpiar_evento(evento)
    req = limpio["request"]
    comprobar("URL sin token y sin query", req["url"] == "https://api.x.pe/api/examen/[tapado]/guardar", req["url"])
    comprobar("sin cookies, cuerpo, query ni env", not ({"cookies", "data", "query_string", "env"} & set(req)))
    comprobar("solo cabeceras inofensivas (User-Agent)", req["headers"] == {"User-Agent": "Chrome"}, req["headers"])
    comprobar("sin user ni server_name", "user" not in limpio and "server_name" not in limpio)
    comprobar("transacción de la firma con token tapado",
              limpio["transaction"] == "/api/auth/usuarios/7/firma/[tapado]", limpio["transaction"])
    comprobar("sin contexto celery-job (args de la tarea)", "celery-job" not in limpio["contexts"])
    comprobar("se conservan contextos técnicos (runtime)", "runtime" in limpio["contexts"])
    valor = limpio["exception"]["values"][0]["value"]
    comprobar("mensaje de la excepción sin DNI, correo ni token",
              DNI not in valor and CORREO not in valor and TOKEN not in valor, valor)
    comprobar("frames sin variables locales", "vars" not in limpio["exception"]["values"][0]["stacktrace"]["frames"][0])
    comprobar("mensaje de log sin token y sin params", TOKEN not in limpio["logentry"]["message"]
              and "params" not in limpio["logentry"])
    comprobar("sin extra", "extra" not in limpio)
    migas = limpio["breadcrumbs"]["values"]
    comprobar("breadcrumb de SQL descartado", all(m.get("category") != "query" for m in migas))
    comprobar("breadcrumb http: URL tapada y sin body",
              migas[0]["data"] == {"url": "https://x/api/examen/[tapado]/intake", "method": "GET"}, migas[0]["data"])
    comprobar("breadcrumb de log sin correo", CORREO not in migas[1]["message"])
    texto = json.dumps(limpio)
    for secreto in (TOKEN, DNI, CORREO, DIAGNOSTICO, RESPUESTA, "190.1.2.3", "PC-DE-ADMIN"):
        comprobar(f"'{secreto[:20]}' no aparece en ninguna parte", secreto not in texto)


def test_envio_real():
    print("\n[4] SDK real + error real en main.app: qué se habría enviado")
    import sentry_sdk
    from sentry_sdk.transport import Transport

    enviados = []

    class TransporteQueGuarda(Transport):
        def capture_envelope(self, envelope):
            enviados.append(envelope.serialize().decode("utf-8", "replace"))

    import main  # sin SENTRY_DSN en el .env de desarrollo: main no lo inicia

    @main.app.post("/api/examen/{token}/zz-prueba-sentry")
    async def _zz_prueba(token: str):
        diagnostico_del_alumno = DIAGNOSTICO  # noqa: F841 — variable local que NO debe viajar
        raise ValueError(f"fallo al puntuar al alumno {DNI} ({CORREO})")

    opciones = monitoreo.opciones_sentry("api")
    opciones.update(dsn="https://clave@o0.ingest.sentry.io/0", transport=TransporteQueGuarda)
    sentry_sdk.init(**opciones)

    cuerpo = json.dumps({"respuesta": RESPUESTA, "dni": DNI}).encode()
    path = f"/api/examen/{TOKEN}/zz-prueba-sentry"
    mensajes = []

    async def receive():
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def send(m):
        mensajes.append(m)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "",
        "query_string": f"t={TOKEN}".encode(),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                    (b"cookie", b"aurora_sesion=zzsesion"), (b"authorization", b"Bearer zzjwt"),
                    (b"content-length", str(len(cuerpo)).encode())],
        "client": ("190.1.2.3", 5000), "server": ("testserver", 80),
    }
    try:
        asyncio.run(main.app(scope, receive, send))
    except Exception:
        pass  # ServerErrorMiddleware re-lanza después de responder el 500
    sentry_sdk.flush(5)

    inicio = next((m for m in mensajes if m["type"] == "http.response.start"), None)
    comprobar("la app respondió 500", inicio is not None and inicio["status"] == 500)
    total = "\n".join(enviados)
    comprobar("se envió al menos un evento con el ValueError", "ValueError" in total, len(enviados))
    comprobar("el evento conserva el método y la ruta (tapada)", "/api/examen/[tapado]/zz-prueba-sentry" in total)
    for nombre, secreto in (("token del examen", TOKEN), ("DNI", DNI), ("correo", CORREO),
                            ("variable local (diagnóstico)", DIAGNOSTICO), ("cuerpo (respuesta)", RESPUESTA),
                            ("cookie de sesión", "zzsesion"), ("JWT", "zzjwt"), ("IP del alumno", "190.1.2.3")):
        comprobar(f"no viaja: {nombre}", secreto not in total)
    sentry_sdk.init(dsn=None)  # apagar


def test_fuentes():
    print("\n[5] Nadie más llama a sentry_sdk.init() por su cuenta")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    culpables = []
    for carpeta, _, archivos in os.walk(raiz):
        if any(p in carpeta for p in ("venv", "__pycache__", os.sep + "tests")):
            continue
        for nombre in archivos:
            if nombre.endswith(".py") and nombre != "monitoreo.py":
                ruta = os.path.join(carpeta, nombre)
                with open(ruta, encoding="utf-8") as f:
                    if "sentry_sdk.init(" in f.read():
                        culpables.append(os.path.relpath(ruta, raiz))
    comprobar("sentry_sdk.init solo en core/monitoreo.py", not culpables, culpables)
    with open(os.path.join(raiz, "core", "cola_tareas.py"), encoding="utf-8") as f:
        fuente = f.read()
    comprobar("el worker y el beat inician Sentry (worker_init / beat_init)",
              "@worker_init.connect" in fuente and "@beat_init.connect" in fuente)


if __name__ == "__main__":
    test_opciones()
    test_sin_dsn()
    test_limpiar_evento()
    test_envio_real()
    test_fuentes()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO SENTRY SIN DATOS PERSONALES: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
