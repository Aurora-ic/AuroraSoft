"""Reglas del Dockerfile y docker-compose.yml (sesión 2026-11-07, revisión de
seguridad previa al piloto). Prueba estática: no necesita Docker instalado,
lee los archivos y falla si alguien vuelve a correr como root, mete el .env
en la imagen o publica Redis.

    python -m tests.test_docker_unitario
"""
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def leer(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as f:
        return f.read()


def instrucciones(dockerfile):
    """Líneas de instrucción (sin comentarios ni continuaciones)."""
    lineas, actual = [], ""
    for linea in dockerfile.splitlines():
        if linea.strip().startswith("#") or not linea.strip():
            continue
        actual += linea.rstrip("\\").strip() + " "
        if not linea.rstrip().endswith("\\"):
            lineas.append(actual.strip())
            actual = ""
    return lineas


def bloque_servicio(compose, nombre):
    m = re.search(rf"^  {nombre}:\n((?:    .*\n|\s*\n)*)", compose + "\n", re.M)
    if not m:
        return ""
    return "".join(l for l in m.group(1).splitlines(True) if not l.strip().startswith("#"))


def test_dockerfile():
    print("\n[1] Dockerfile")
    ins = instrucciones(leer("Dockerfile"))
    users = [i for i in ins if i.upper().startswith("USER ")]
    comprobar("hay una instrucción USER", bool(users))
    comprobar("el último USER no es root", users and users[-1].split()[1] not in ("root", "0"), users)
    idx_user = max(i for i, x in enumerate(ins) if x.upper().startswith("USER ")) if users else -1
    idx_cmd = max(i for i, x in enumerate(ins) if x.upper().startswith("CMD ")) if any(
        x.upper().startswith("CMD ") for x in ins) else -1
    comprobar("USER va antes del CMD", 0 <= idx_user < idx_cmd, (idx_user, idx_cmd))
    comprobar("ningún RUN después de USER (correría sin root, o sería un intento de volver a root)",
              not any(x.upper().startswith("RUN ") for x in ins[idx_user + 1:]))
    comprobar("el usuario se crea sin shell de login", any("useradd" in x and "nologin" in x for x in ins))
    comprobar("Python 3.12 (el de los tests)", any(re.match(r"FROM python:3\.12", x) for x in ins), ins[0])
    comprobar("uvicorn sin cabecera server", any(x.startswith("CMD") and "--no-server-header" in x for x in ins))
    comprobar("el código no se entrega al usuario de la app (sin COPY --chown)",
              not any(x.startswith("COPY") and "--chown" in x for x in ins))


def test_dockerignore():
    print("\n[2] .dockerignore")
    reglas = {l.strip() for l in leer(".dockerignore").splitlines() if l.strip() and not l.startswith("#")}
    for regla in (".env", ".env.*", "venv/", ".git/", "*.log", "storage_local/"):
        comprobar(f"excluye {regla}", regla in reglas)


def test_compose():
    print("\n[3] docker-compose.yml")
    compose = leer("docker-compose.yml")
    redis = bloque_servicio(compose, "redis")
    web = bloque_servicio(compose, "web")
    beat = bloque_servicio(compose, "beat")
    comprobar("redis existe", bool(redis))
    comprobar("redis NO publica puertos (no tiene contraseña)", "ports:" not in redis, redis)
    puertos_web = re.findall(r'-\s*"([^"]+)"', web.split("ports:", 1)[1]) if "ports:" in web else []
    comprobar("web publica solo en 127.0.0.1 (entra por Caddy)",
              bool(puertos_web) and all(p.startswith("127.0.0.1:") for p in puertos_web), puertos_web)
    comprobar("hay un servicio beat", bool(beat))
    comprobar("beat guarda su calendario en /tmp (el código es de solo lectura)", "--schedule /tmp/" in beat)
    comprobar("un solo beat", len(re.findall(r"celery -A core.cola_tareas beat", compose)) == 1)
    comprobar("ningún servicio pasa a root (user: root/0)", not re.search(r"^\s*user:\s*[\"']?(root|0)", compose, re.M))
    comprobar("los secretos llegan por env_file, no escritos en el compose",
              not re.search(r"(SECRET_KEY|PASSWORD|ACCESS_KEY|DATABASE_URL)\s*:", compose))


if __name__ == "__main__":
    test_dockerfile()
    test_dockerignore()
    test_compose()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO DOCKER SIN ROOT: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
