"""Pruebas unitarias de la Fase 4 — cierre de auditoría y limpieza.

    python tests/test_fase4_unitario.py

No necesitan la base de datos ni el servidor.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core.email_service import enviar_alerta_riesgo  # noqa: E402
from modulos.educativo import schemas  # noqa: E402

_resultados = []
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_escapado_html_alerta():
    print("\nGrupo D · Escapado HTML del nombre del alumno en el correo de alerta")

    capturados = {}

    def _enviar_falso(destinatario, asunto, cuerpo_html):
        capturados["cuerpo"] = cuerpo_html
        return True

    import core.email_service as es
    original = es.enviar_correo
    es.enviar_correo = _enviar_falso
    try:
        nombre_hostil = "<script>alert(1)</script>Ana"
        dimension_hostil = "Ansiedad<img src=x onerror=alert(2)>"
        enviar_alerta_riesgo(
            destinatarios="psicologo@colegio.edu.pe",
            nombre_alumno=nombre_hostil,
            dimensiones_en_riesgo=[dimension_hostil],
        )
    finally:
        es.enviar_correo = original

    cuerpo = capturados.get("cuerpo", "")
    comprobar(
        "El nombre del alumno llega escapado al HTML del correo",
        "<script>" not in cuerpo and "&lt;script&gt;" in cuerpo,
        cuerpo[:120],
    )
    comprobar(
        "El nombre de la dimensión también llega escapado",
        "<img" not in cuerpo and "&lt;img" in cuerpo,
    )
    comprobar(
        "El contenido legítimo (etiquetas propias del correo) sigue intacto",
        "<strong>" in cuerpo and "<ul>" in cuerpo,
    )


def test_baremo_rango_invertido():
    print("\nGrupo D · Validación psicométrica de baremos — rango invertido")
    try:
        schemas.BaremoCreate(dimension_id=1, puntaje_minimo=10, puntaje_maximo=5, nivel="x")
        ok = False
    except Exception as e:
        ok = "puntaje_minimo" in str(e)
    comprobar("puntaje_minimo > puntaje_maximo se rechaza en el esquema", ok)

    try:
        schemas.BaremoCreate(
            dimension_id=1, puntaje_minimo=0, puntaje_maximo=5, nivel="x",
            edad_min=15, edad_max=10,
        )
        ok = False
    except Exception as e:
        ok = "edad_min" in str(e)
    comprobar("edad_min > edad_max se rechaza en el esquema", ok)

    # Un rango válido sigue aceptándose sin problema.
    valido = schemas.BaremoCreate(dimension_id=1, puntaje_minimo=0, puntaje_maximo=5, nivel="x")
    comprobar("Un rango normal (min <= max) se sigue aceptando", valido.puntaje_maximo == 5)


def test_baremo_solapamiento():
    print("\nGrupo D · Validación psicométrica de baremos — solapamiento")
    from modulos.educativo import crud as edu_crud

    comprobar(
        "_rangos_se_solapan detecta el solape",
        edu_crud._rangos_se_solapan(0, 5, 3, 8) is True,
    )
    comprobar(
        "_rangos_se_solapan no marca solape en tramos contiguos (0-2 y 3-5)",
        edu_crud._rangos_se_solapan(0, 2, 3, 5) is False,
    )
    comprobar(
        "_rangos_se_solapan trata None como sin tope (edad 'todas')",
        edu_crud._rangos_se_solapan(None, None, 10, 20) is True,
    )

    class _Falsa:  # simula una fila models.Baremo existente
        id = 99
        sexo = None
        poblacion = None
        edad_min = None
        edad_max = None
        puntaje_minimo = 0
        puntaje_maximo = 10
        nivel = "Alto"

    class _DBFalsa:
        def query(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def all(self):
            return [_Falsa()]

    class _Nuevo:
        sexo = None
        poblacion = None
        edad_min = None
        edad_max = None
        puntaje_minimo = 5
        puntaje_maximo = 15

    try:
        edu_crud._validar_solapamiento_baremo(_DBFalsa(), _Nuevo(), dimension_id=1)
        ok = False
    except Exception as e:
        ok = getattr(e, "status_code", None) == 409
    comprobar("crear/actualizar un baremo que se solapa con uno existente devuelve 409", ok)


def test_casos_pendientes_usa_es_alerta():
    print("\nGrupo D · HALLAZGO CRÍTICO — casos pendientes de seguimiento filtraba por texto, no por es_alerta")
    import inspect
    from modulos.educativo import crud as edu_crud

    fuente = inspect.getsource(edu_crud.obtener_casos_pendientes_de_seguimiento)
    comprobar(
        "Ya no compara diag.nivel contra el set de texto NIVELES_DE_ALERTA",
        "not in models.NIVELES_DE_ALERTA" not in fuente,
    )
    comprobar(
        "Filtra por el indicador explícito diag.es_alerta",
        "diag.es_alerta" in fuente,
    )


def test_dashboard_una_sola_consulta():
    print("\nGrupo D · Rendimiento — el dashboard de campaña ya no hace 1 consulta por inscripción")
    import inspect
    from modulos.educativo import crud as edu_crud

    # 🔒 Corregido (auditoría de tests, sesión 2026-10-15): esta prueba leía
    # el código fuente de `obtener_dashboard_campana` buscando el patrón
    # batcheado — pero una sesión posterior extrajo el bucle/la consulta a su
    # propia función compartida, `_armar_alumnos_y_distribucion` (reusada
    # también por el dashboard académico), así que `obtener_dashboard_campana`
    # ya no contiene literalmente "for insc in inscripciones:" en su propio
    # código. El `partition()` de abajo encontraba la cadena vacía y la
    # comprobación "Se batchea con .in_(inscripcion_ids) antes del bucle"
    # fallaba — no porque el fix de rendimiento se hubiera perdido (seguía
    # intacto, solo que en otra función), sino porque la aserción apuntaba al
    # lugar equivocado. Se corrige apuntando a `_armar_alumnos_y_distribucion`
    # (donde vive hoy de verdad) más una comprobación nueva de que
    # `obtener_dashboard_campana` sigue delegando ahí, para que esa conexión
    # no se pierda en silencio si alguien la rompe más adelante.
    fuente = inspect.getsource(edu_crud._armar_alumnos_y_distribucion)
    # Antes había un db.query(...) DENTRO del for insc in inscripciones.
    # Ahora la consulta de resultados/diagnósticos debe estar FUERA del bucle,
    # una sola vez, agrupada después en memoria.
    antes_del_for, _, resto = fuente.partition("for insc in inscripciones:")
    comprobar(
        "La consulta de ResultadoDimension/Dimension/DiagnosticoAlumno ya no vive dentro del bucle",
        "db.query(models.ResultadoDimension" not in resto,
    )
    comprobar(
        "Se batchea con .in_(inscripcion_ids) antes del bucle",
        "inscripcion_ids.in_" in antes_del_for or ".in_(inscripcion_ids)" in antes_del_for,
    )

    fuente_dashboard_campana = inspect.getsource(edu_crud.obtener_dashboard_campana)
    comprobar(
        "obtener_dashboard_campana delega en _armar_alumnos_y_distribucion (no duplica el bucle)",
        "_armar_alumnos_y_distribucion(" in fuente_dashboard_campana,
    )

    fuente_proceso = inspect.getsource(edu_crud.obtener_dashboard_proceso)
    comprobar(
        "El dashboard consolidado por institución ya no re-consulta Inscripcion por alumno",
        "db.query(models.Inscripcion)" not in fuente_proceso,
    )


def _indice_de_primera_linea(lineas, fragmento):
    for i, linea in enumerate(lineas):
        if fragmento in linea:
            return i
    return None


def test_orden_de_carga_de_env():
    print("\nGrupo D · Orden de carga de variables de entorno (bug real: Sentry nunca leía .env)")
    for ruta in ("main.py", "migraciones/env.py"):
        with open(os.path.join(_BACKEND_DIR, ruta), encoding="utf-8") as f:
            lineas = f.readlines()
        idx_dotenv = _indice_de_primera_linea(lineas, "load_dotenv()")
        idx_sentry = _indice_de_primera_linea(lineas, 'os.getenv("SENTRY_DSN")')
        comprobar(
            f"{ruta}: load_dotenv() corre antes de leer SENTRY_DSN",
            idx_dotenv is not None and idx_sentry is not None and idx_dotenv < idx_sentry,
            f"dotenv en línea {idx_dotenv}, SENTRY_DSN en línea {idx_sentry}",
        )
        # Verificación sintáctica de que el archivo sigue siendo Python válido.
        ast.parse("".join(lineas), filename=ruta)


def test_archivo_huerfano_eliminado():
    print("\nGrupo D · Limpieza — parche obsoleto eliminado")
    ruta = os.path.join(_BACKEND_DIR, "modulos", "auth", "7_auth_router.py")
    comprobar(
        "modulos/auth/7_auth_router.py (nota de parche ya aplicada, no era código) ya no existe",
        not os.path.exists(ruta),
    )


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — FASE 4")
    print("=" * 72)
    test_escapado_html_alerta()
    test_baremo_rango_invertido()
    test_baremo_solapamiento()
    test_casos_pendientes_usa_es_alerta()
    test_dashboard_una_sola_consulta()
    test_orden_de_carga_de_env()
    test_archivo_huerfano_eliminado()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
