"""Verificación de la cadena de migraciones (Fase 3 · B-10 y punto 2).

Trabaja sobre bases PostgreSQL TEMPORALES creadas para la ocasión (prefijo
`zz_mig_`) y nunca toca la base de la aplicación salvo para leerla y para el
`alembic check` final. Comprueba:

  1. upgrade head sobre una base COMPLETAMENTE VACÍA
  2. alembic check sin deriva
  3. downgrade base  ->  upgrade head (la cadena entera, en ambos sentidos)
  4. upgrade sobre una base EXISTENTE con datos (clon de la real)
  5. instalación nueva == instalación existente (comparación estricta)
  6. columnas NOT NULL añadidas sobre tablas CON filas (punto 2)
  7. la guarda accionable de personas.institucion_id
  8. integridad de las claves foráneas nuevas (C-16) y su guarda de huérfanos

    python tests/verificar_fase3_migraciones.py
"""

import os
import subprocess
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
load_dotenv(os.path.join(RAIZ, ".env"))

from tests.comparar_esquemas import diferencias, huella  # noqa: E402

URL_APP = make_url(os.environ["DATABASE_URL"])
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def url_de(nombre):
    return URL_APP.set(database=nombre).render_as_string(hide_password=False)


def _admin():
    return create_engine(URL_APP.set(database="postgres"), isolation_level="AUTOCOMMIT")


def recrear(nombre, plantilla=None):
    with _admin().connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
        if plantilla:
            c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                           "WHERE datname = :d AND pid <> pg_backend_pid()"), {"d": plantilla})
            c.execute(text(f'CREATE DATABASE "{nombre}" TEMPLATE "{plantilla}"'))
        else:
            c.execute(text(f'CREATE DATABASE "{nombre}"'))


def borrar(nombre):
    with _admin().connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))


def alembic(bd, *args):
    """Ejecuta alembic contra una base concreta, en un proceso aparte."""
    entorno = {**os.environ, "DATABASE_URL": url_de(bd)}
    p = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=RAIZ,
                       env=entorno, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def sql(bd, consulta, **params):
    with create_engine(url_de(bd)).begin() as c:
        r = c.execute(text(consulta), params)
        return r.fetchall() if r.returns_rows else None


def cabeza_actual():
    _, salida = alembic("postgres", "heads")
    return salida.strip().split()[0]


# ======================================================================
def main():
    cabeza = cabeza_actual()
    print(f"Cabeza de la cadena: {cabeza}")

    # ------------------------------------------------------------------
    print("\n1-3 · Base completamente vacía")
    recrear("zz_mig_limpia")
    codigo, salida = alembic("zz_mig_limpia", "upgrade", "head")
    pasos = salida.count("Running upgrade")
    comprobar("upgrade head sobre una base VACÍA termina sin errores",
              codigo == 0, f"{pasos} revisiones aplicadas" if codigo == 0 else salida[-300:])
    tablas = {r[0] for r in sql("zz_mig_limpia",
              "select tablename from pg_tables where schemaname='public'")}
    esperadas = {"instituciones", "auth_usuarios", "auth_tokens_recuperacion", "personas",
                 "consentimientos_informados", "citas_programadas", "auditoria_arco",
                 "edu_pruebas", "edu_dimensiones", "edu_preguntas", "edu_opciones",
                 "edu_baremos", "edu_evaluaciones", "edu_inscripciones",
                 "edu_respuestas_alumno", "edu_resultados_dimensiones",
                 "edu_diagnosticos_alumno", "edu_sesiones_seguimiento",
                 "edu_campos_socio", "edu_respuestas_socio"}
    comprobar("Se crean todas las tablas de la aplicación",
              esperadas <= tablas, f"faltan: {sorted(esperadas - tablas)}" if esperadas - tablas else f"{len(esperadas)} tablas")
    comprobar("Las tablas heredadas (clientes/usuarios) no sobreviven",
              not ({"clientes", "usuarios", "sesiones_seguimiento"} & tablas))

    codigo, salida = alembic("zz_mig_limpia", "check")
    comprobar("alembic check: sin deriva frente a los modelos",
              codigo == 0 and "No new upgrade operations" in salida, salida.strip().splitlines()[-1])

    codigo, salida = alembic("zz_mig_limpia", "downgrade", "base")
    comprobar("downgrade base recorre la cadena entera hacia abajo",
              codigo == 0, f"{salida.count('Running downgrade')} revisiones" if codigo == 0 else salida[-300:])
    restantes = {r[0] for r in sql("zz_mig_limpia",
                 "select tablename from pg_tables where schemaname='public'")} - {"alembic_version"}
    comprobar("Tras downgrade base no queda ninguna tabla", not restantes, str(sorted(restantes)))
    codigo, salida = alembic("zz_mig_limpia", "upgrade", "head")
    comprobar("...y upgrade head vuelve a construirlo todo", codigo == 0, salida[-200:] if codigo else "")

    # ------------------------------------------------------------------
    print("\n4-5 · Base existente con datos")
    respaldo = "aurora_respaldo_pre_fase3"
    existe_respaldo = sql("postgres", "select 1 from pg_database where datname=:d", d=respaldo)
    plantilla = respaldo if existe_respaldo else URL_APP.database
    recrear("zz_mig_existente", plantilla=plantilla)
    antes = sql("zz_mig_existente", "select count(*), coalesce(sum(valor_puntuacion),0) from edu_opciones")[0]
    version_antes = sql("zz_mig_existente", "select version_num from alembic_version")[0][0]
    codigo, salida = alembic("zz_mig_existente", "upgrade", "head")
    comprobar(f"upgrade sobre una base existente ({version_antes} -> head)",
              codigo == 0, salida[-200:] if codigo else "")
    despues = sql("zz_mig_existente", "select count(*), coalesce(sum(valor_puntuacion),0) from edu_opciones")[0]
    comprobar("Los datos existentes se conservan intactos",
              antes[0] == despues[0] and float(antes[1]) == float(despues[1]),
              f"{antes[0]} opciones, suma {antes[1]} -> {despues[1]}")

    difs = diferencias(huella(url_de("zz_mig_limpia")), huella(url_de("zz_mig_existente")),
                       "nueva", "existente")
    comprobar("Instalación NUEVA y EXISTENTE son estructuralmente idénticas",
              not difs, "; ".join(difs[:3]))

    codigo, salida = alembic("zz_mig_existente", "downgrade", "-4")
    codigo2, salida2 = alembic("zz_mig_existente", "upgrade", "head")
    comprobar("Base con datos: downgrade -4 y upgrade head", codigo == 0 and codigo2 == 0,
              (salida + salida2)[-200:] if (codigo or codigo2) else "")
    tras_ciclo = sql("zz_mig_existente", "select count(*) from edu_opciones")[0][0]
    comprobar("El ciclo no pierde datos", tras_ciclo == antes[0], f"{tras_ciclo} opciones")

    # ------------------------------------------------------------------
    print("\n6 · Columnas NOT NULL añadidas sobre tablas con filas (punto 2)")
    recrear("zz_mig_notnull")
    alembic("zz_mig_notnull", "upgrade", "906f970db71e")   # justo antes de 0050390ab444
    sql("zz_mig_notnull", "insert into instituciones (id, nombre) values (1, 'Colegio previo')")
    sql("zz_mig_notnull", "insert into edu_pruebas (id, nombre_tecnico) values (1, 'T')")
    sql("zz_mig_notnull", "insert into edu_evaluaciones (id, institucion_id, prueba_id) values (1, 1, 1)")
    sql("zz_mig_notnull", "insert into edu_inscripciones (id, evaluacion_id, token) values (1, 1, 'tok-previo')")
    codigo, salida = alembic("zz_mig_notnull", "upgrade", "head")
    comprobar("La cadena avanza sobre inscripciones YA existentes",
              codigo == 0, salida[-250:] if codigo else "")
    if codigo == 0:
        fila = sql("zz_mig_notnull", "select acepto_asentimiento, is_deleted, is_anonymized, "
                   "estado_interpretacion, informe_liberado from edu_inscripciones where id=1")[0]
        comprobar("Las filas previas reciben valores coherentes",
                  tuple(fila) == (False, False, False, "completa", True), str(tuple(fila)))
        inst = sql("zz_mig_notnull", "select plan_activo, limite_pruebas_mensual_por_alumno "
                   "from instituciones where id=1")[0]
        comprobar("La institución previa queda con licencia coherente (activa, límite 5)",
                  tuple(inst) == (True, 5), str(tuple(inst)))

    # ------------------------------------------------------------------
    print("\n7 · Guarda accionable de personas.institucion_id")
    recrear("zz_mig_personas")
    alembic("zz_mig_personas", "upgrade", "0a1b2c3d4e5f")   # solo el esquema base
    sql("zz_mig_personas", "insert into clientes (id, nombre, tipo) values (1, 'Heredado', 'Colegio')")
    sql("zz_mig_personas", "insert into personas (tipo_perfil, nombres, apellidos, documento_identidad, cliente_id) "
                           "values ('estudiante', 'Ana', 'Previa', '123', 1)")
    codigo, salida = alembic("zz_mig_personas", "upgrade", "f3c03cf327b6")
    comprobar("Con personas sin institución, la migración se detiene...", codigo != 0)
    comprobar("...con un mensaje accionable, no un error opaco",
              "asigna personas.institucion_id a mano" in salida,
              [l for l in salida.splitlines() if "RuntimeError" in l][-1:] or salida[-150:])

    # ------------------------------------------------------------------
    print("\n8 · Claves foráneas nuevas (C-16)")
    for consulta, nombre in [
        ("insert into edu_evaluaciones (id, institucion_id, prueba_id, creador_id) values (2, 1, 1, 999999)",
         "edu_evaluaciones.creador_id -> auth_usuarios"),
        ("insert into edu_campos_socio (cliente_id, pregunta) values (999999, 'x')",
         "edu_campos_socio.cliente_id -> instituciones"),
    ]:
        try:
            sql("zz_mig_notnull", consulta)
            comprobar(f"FK {nombre} rechaza un id inexistente", False, "el INSERT pasó")
        except Exception as exc:
            comprobar(f"FK {nombre} rechaza un id inexistente",
                      "ForeignKeyViolation" in type(exc.orig).__name__ if hasattr(exc, "orig") else False,
                      type(getattr(exc, "orig", exc)).__name__)

    recrear("zz_mig_huerfanos")
    alembic("zz_mig_huerfanos", "upgrade", "f7a2c5e91d40")   # justo antes de las FK nuevas
    sql("zz_mig_huerfanos", "insert into instituciones (id, nombre) values (1, 'C')")
    sql("zz_mig_huerfanos", "insert into edu_pruebas (id, nombre_tecnico) values (1, 'T')")
    sql("zz_mig_huerfanos", "insert into edu_evaluaciones (institucion_id, prueba_id, creador_id) "
                            "values (1, 1, 424242)")
    codigo, salida = alembic("zz_mig_huerfanos", "upgrade", "head")
    comprobar("Con referencias huérfanas la migración se detiene y las lista",
              codigo != 0 and "creador_id no corresponde a ningún usuario" in salida)

    # ------------------------------------------------------------------
    print("\nBase de la aplicación")
    codigo, salida = alembic(URL_APP.database, "current")
    comprobar("La base de la aplicación está en la cabeza", cabeza in salida, salida.strip()[-60:])
    codigo, salida = alembic(URL_APP.database, "check")
    comprobar("alembic check sobre la base de la aplicación",
              codigo == 0 and "No new upgrade operations" in salida)
    difs = diferencias(huella(url_de(URL_APP.database)), huella(url_de("zz_mig_limpia")),
                       "aplicación", "nueva")
    comprobar("La base de la aplicación es idéntica a una instalación nueva",
              not difs, "; ".join(difs[:3]))

    for bd in ("zz_mig_limpia", "zz_mig_existente", "zz_mig_notnull",
               "zz_mig_personas", "zz_mig_huerfanos"):
        borrar(bd)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO MIGRACIONES: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
