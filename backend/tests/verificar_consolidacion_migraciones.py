"""Verificación de la consolidación de migraciones (sesión 2026-11-08, Tarea 1).

Las 81 migraciones viejas (hasta `4ffd2710409b`) se reemplazaron por una sola,
`b9d1ee03b2f8` (versions/..._esquema_consolidado.py); las viejas quedan en
migraciones/historico/. Este script comprueba, sobre bases TEMPORALES
`zz_mig_*` en un servidor PostgreSQL que NO es el de la aplicación:

  1. la cadena vieja (historico/) desde una base vacía -> zz_mig_cadena
  2. la migración consolidada desde una base vacía -> zz_mig_base,
     y `alembic check` sin deriva respecto de los modelos
  3. zz_mig_cadena == zz_mig_base: `pg_dump --schema-only` idéntico línea a
     línea y comparar_esquemas sin diferencias
  4. downgrade base deja la base vacía, y un upgrade head la reconstruye igual
  5. el camino para una base que YA existe (en `4ffd2710409b`): una COPIA
     desechable (pg_dump de solo lectura de la base de origen, restaurada en
     zz_mig_copia) -> `alembic stamp --purge b9d1ee03b2f8` -> queda en la
     revisión nueva, `upgrade head` no hace nada, `alembic check` sin deriva,
     el esquema es idéntico a zz_mig_base y los datos no cambian (filas por
     tabla iguales antes y después)

La base de origen solo se LEE (pg_dump). Nunca se le aplica nada.

Uso (servidor temporal y binarios de PostgreSQL 16 por variable de entorno):

    ZZ_MIG_SERVIDOR_URL=postgresql://postgres:***@localhost:5432/postgres \\
    PG_BIN="C:/Program Files/PostgreSQL/16/bin" \\
    python -m tests.verificar_consolidacion_migraciones [--copia-de URL] [--conservar]

`--copia-de` es la base a copiar para el paso 5 (por defecto DATABASE_URL del
.env). `--conservar` deja las bases zz_mig_* para inspeccionarlas.
"""
import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
load_dotenv(os.path.join(RAIZ, ".env"))

from tests.comparar_esquemas import diferencias, huella  # noqa: E402

REVISION_VIEJA = "4ffd2710409b"
REVISION_NUEVA = "b9d1ee03b2f8"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


# ----------------------------------------------------------------------------
# Servidor temporal y herramientas
# ----------------------------------------------------------------------------
def _servidor():
    crudo = os.getenv("ZZ_MIG_SERVIDOR_URL")
    if not crudo:
        sys.exit("Falta ZZ_MIG_SERVIDOR_URL (servidor PostgreSQL donde crear las bases zz_mig_*).")
    url = make_url(crudo)
    app = make_url(os.environ["DATABASE_URL"])
    if (url.host, url.port) == (app.host, app.port):
        sys.exit("ZZ_MIG_SERVIDOR_URL apunta al mismo servidor que la aplicación: usa otro (p. ej. un PostgreSQL local).")
    return url


SERVIDOR = None


def url_de(nombre):
    return SERVIDOR.set(database=nombre).render_as_string(hide_password=False)


def recrear(nombre):
    assert nombre.startswith("zz_mig_")
    motor = create_engine(SERVIDOR.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with motor.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{nombre}"'))
    motor.dispose()


def borrar(nombre):
    assert nombre.startswith("zz_mig_")
    motor = create_engine(SERVIDOR.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with motor.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
    motor.dispose()


def binario(nombre):
    carpeta = os.getenv("PG_BIN")
    ruta = shutil.which(nombre, path=carpeta) if carpeta else shutil.which(nombre)
    if not ruta:
        sys.exit(f"No encuentro {nombre}: define PG_BIN con la carpeta bin de PostgreSQL 16.")
    return ruta


def _ini_temporal(version_locations):
    """alembic.ini con version_locations explícito (historico/ o versions/)."""
    with open(os.path.join(RAIZ, "alembic.ini"), encoding="utf-8") as f:
        contenido = f.read()
    migraciones = os.path.join(RAIZ, "migraciones").replace("\\", "/")
    contenido = contenido.replace("%(here)s/migraciones", migraciones)
    contenido = contenido.replace(
        "[alembic]", f"[alembic]\nversion_locations = {migraciones}/{version_locations}", 1)
    fd, ruta = tempfile.mkstemp(suffix=".ini")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    return ruta


INI = {}


def alembic(nombre, *args, cadena="versions"):
    env = {**os.environ, "DATABASE_URL": url_de(nombre), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    env.pop("SENTRY_DSN", None)
    r = subprocess.run([sys.executable, "-m", "alembic", "-c", INI[cadena], *args], cwd=RAIZ, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout + r.stderr


def revision_actual(nombre):
    with create_engine(url_de(nombre)).connect() as c:
        return [r[0] for r in c.execute(text("select version_num from alembic_version"))]


def volcado_esquema(nombre):
    url = SERVIDOR.set(database=nombre)
    r = subprocess.run(
        [binario("pg_dump"), "--schema-only", "--no-owner", "--no-privileges", "--exclude-table=alembic_version",
         "-h", url.host, "-p", str(url.port or 5432), "-U", url.username, nombre],
        env={**os.environ, "PGPASSWORD": url.password or ""},
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    # Sin comentarios, líneas vacías ni el \restrict aleatorio de pg_dump 16.13+.
    return [l for l in r.stdout.splitlines()
            if l.strip() and not l.startswith("--") and not l.startswith(("\\restrict", "\\unrestrict"))]


def iguales(a, b):
    va, vb = volcado_esquema(a), volcado_esquema(b)
    diff = [l for l in difflib.unified_diff(va, vb, a, b, lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    difs = diferencias(huella(url_de(a)), huella(url_de(b)), a, b)
    comprobar(f"pg_dump --schema-only idéntico ({len(va)} líneas)", not diff, "; ".join(diff[:3])[:400])
    comprobar("comparar_esquemas sin diferencias", not difs, "; ".join(difs[:3])[:400])


def filas_por_tabla(nombre):
    motor = create_engine(url_de(nombre))
    tablas = [t for t in inspect(motor).get_table_names() if t != "alembic_version"]
    with motor.connect() as c:
        return {t: c.execute(text(f'select count(*) from "{t}"')).scalar() for t in tablas}


def copiar(origen_url, destino):
    """pg_dump (solo lectura) de la base de origen -> zz_mig_copia."""
    origen = make_url(origen_url)
    volcado = os.path.join(tempfile.mkdtemp(), "copia.dump")
    env_origen = {**os.environ, "PGPASSWORD": origen.password or ""}
    if origen.query.get("sslmode"):
        env_origen["PGSSLMODE"] = origen.query["sslmode"]
    if origen.query.get("channel_binding"):
        env_origen["PGCHANNELBINDING"] = origen.query["channel_binding"]
    r = subprocess.run([binario("pg_dump"), "--format=custom", "--no-owner", "--no-privileges",
                        "-h", origen.host, "-p", str(origen.port or 5432), "-U", origen.username,
                        "-f", volcado, origen.database],
                       env=env_origen, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"pg_dump de la base de origen falló: {r.stderr[-500:]}")
    recrear(destino)
    url = SERVIDOR.set(database=destino)
    r = subprocess.run([binario("pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error",
                        "-h", url.host, "-p", str(url.port or 5432), "-U", url.username, "-d", destino, volcado],
                       env={**os.environ, "PGPASSWORD": url.password or ""},
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    os.remove(volcado)
    if r.returncode != 0:
        sys.exit(f"pg_restore en {destino} falló: {r.stderr[-500:]}")


# ----------------------------------------------------------------------------
def main():
    global SERVIDOR
    parser = argparse.ArgumentParser()
    parser.add_argument("--copia-de", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--conservar", action="store_true")
    args = parser.parse_args()
    SERVIDOR = _servidor()
    INI["versions"] = _ini_temporal("versions")
    INI["historico"] = _ini_temporal("historico")

    print("\n1 · Cadena vieja (migraciones/historico/) desde una base vacía")
    recrear("zz_mig_cadena")
    rc, out = alembic("zz_mig_cadena", "upgrade", "head", cadena="historico")
    comprobar("upgrade head con las 81 migraciones viejas", rc == 0, out[-300:] if rc else "")
    comprobar(f"queda en {REVISION_VIEJA}", revision_actual("zz_mig_cadena") == [REVISION_VIEJA])

    print("\n2 · Migración consolidada desde una base vacía")
    recrear("zz_mig_base")
    rc, out = alembic("zz_mig_base", "upgrade", "head")
    comprobar("upgrade head con la migración consolidada", rc == 0, out[-300:] if rc else "")
    comprobar(f"queda en {REVISION_NUEVA}", revision_actual("zz_mig_base") == [REVISION_NUEVA])
    rc, out = alembic("zz_mig_base", "check")
    comprobar("alembic check: sin deriva respecto de los modelos", rc == 0, out.strip().splitlines()[-1][:300])

    print("\n3 · Cadena vieja == migración consolidada")
    iguales("zz_mig_cadena", "zz_mig_base")

    print("\n4 · downgrade base -> upgrade head")
    rc, out = alembic("zz_mig_base", "downgrade", "base")
    comprobar("downgrade base", rc == 0, out[-300:] if rc else "")
    restantes = [t for t in inspect(create_engine(url_de("zz_mig_base"))).get_table_names() if t != "alembic_version"]
    comprobar("no queda ninguna tabla", not restantes, str(restantes[:5]))
    rc, out = alembic("zz_mig_base", "upgrade", "head")
    comprobar("upgrade head de nuevo", rc == 0, out[-300:] if rc else "")
    iguales("zz_mig_cadena", "zz_mig_base")

    print("\n5 · Base que ya existe: copia desechable + alembic stamp --purge")
    origen = make_url(args.copia_de)
    print(f"  (copia de solo lectura de la base '{origen.database}' en {origen.host[:12]}…)")
    copiar(args.copia_de, "zz_mig_copia")
    # pg_dump escribe los CHECK "col IN (...)" ya expandidos a ANY (ARRAY[...]),
    # y al restaurarlos PostgreSQL los guarda con otra forma (equivalente). Por
    # eso la copia se compara con una referencia que pasó por el MISMO
    # pg_dump/pg_restore, no con la base construida por migraciones.
    copiar(url_de("zz_mig_base"), "zz_mig_referencia")
    comprobar(f"la copia está en {REVISION_VIEJA} (el esquema completo de la cadena vieja)",
              revision_actual("zz_mig_copia") == [REVISION_VIEJA], str(revision_actual("zz_mig_copia")))
    iguales("zz_mig_referencia", "zz_mig_copia")
    antes = filas_por_tabla("zz_mig_copia")
    rc, out = alembic("zz_mig_copia", "stamp", "--purge", REVISION_NUEVA)
    comprobar(f"alembic stamp --purge {REVISION_NUEVA}", rc == 0, out[-300:] if rc else "")
    comprobar(f"queda en {REVISION_NUEVA}", revision_actual("zz_mig_copia") == [REVISION_NUEVA])
    rc, out = alembic("zz_mig_copia", "upgrade", "head")
    comprobar("upgrade head no hace nada", rc == 0 and "Running upgrade" not in out, out[-200:])
    rc, out = alembic("zz_mig_copia", "check")
    comprobar("alembic check sin deriva", rc == 0, out.strip().splitlines()[-1][:300])
    iguales("zz_mig_referencia", "zz_mig_copia")
    despues = filas_por_tabla("zz_mig_copia")
    comprobar(f"los datos no cambian ({sum(antes.values())} filas en {len(antes)} tablas)", antes == despues)

    if not args.conservar:
        for nombre in ("zz_mig_cadena", "zz_mig_base", "zz_mig_copia", "zz_mig_referencia"):
            borrar(nombre)
    for ruta in INI.values():
        os.remove(ruta)

    total, pasan = len(_resultados), sum(_resultados)
    print("\n" + "=" * 72)
    print(f"RESULTADO CONSOLIDACIÓN DE MIGRACIONES: {pasan}/{total} comprobaciones superadas")
    print("=" * 72)
    return 0 if pasan == total else 1


if __name__ == "__main__":
    sys.exit(main())
