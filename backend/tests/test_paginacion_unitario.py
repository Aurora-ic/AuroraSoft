"""Pruebas unitarias — paginación real de los 3 listados que antes
devolvían todo sin tope (ver docs/gaps-pendientes.md, hallazgo "Sin
paginación real"): `GET /admin/personas/{institucion_id}`,
`GET /educativo/campanas/`, `GET /documentos/`.

No requiere base de datos: inspecciona los objetos `Query(...)` que FastAPI
ya adjunta como default de cada parámetro (no el texto del código) para
confirmar `skip`/`limit` por default, el tope de `limit` en 200, y que
`skip` negativo queda rechazado por la propia metadata de Pydantic — sin
fallback a "sin límite" si se omiten.

La corrección del `COUNT` contra la base real (que se cuente ANTES de
aplicar `offset/limit`, y que el filtro de `nivel_visibilidad` se aplique
ANTES del `COUNT` en el caso de documentos) solo tiene sentido verificada
contra Postgres real — eso lo cubre tests/verificar_paginacion_e2e.py
(prefijo ZZPAGIN), no este archivo.

    python -m tests.test_paginacion_unitario
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from annotated_types import Ge, Le  # noqa: E402

from modulos.superadmin.router import listar_personas_de_institucion  # noqa: E402
from modulos.educativo.router import listar_campanas  # noqa: E402
from modulos.documentos.router import listar_documentos_institucionales  # noqa: E402
from modulos.superadmin import crud as sa_crud  # noqa: E402
from modulos.educativo import crud as edu_crud  # noqa: E402
from modulos.documentos import crud as doc_crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _parametro(funcion, nombre):
    return inspect.signature(funcion).parameters[nombre].default


def _verificar_query_de_paginacion(nombre_endpoint, funcion):
    print(f"\n{nombre_endpoint}")
    skip = _parametro(funcion, "skip")
    limit = _parametro(funcion, "limit")

    comprobar(f"[{nombre_endpoint}] `skip` tiene default concreto 0 (sin fallback a \"sin límite\")",
              skip.default == 0, f"default={skip.default!r}")
    comprobar(f"[{nombre_endpoint}] `skip` rechaza negativos (ge=0 en la metadata real de Query)",
              any(isinstance(m, Ge) and m.ge == 0 for m in skip.metadata),
              f"metadata={skip.metadata!r}")

    comprobar(f"[{nombre_endpoint}] `limit` tiene default 50",
              limit.default == 50, f"default={limit.default!r}")
    comprobar(f"[{nombre_endpoint}] `limit` exige al menos 1 (ge=1)",
              any(isinstance(m, Ge) and m.ge == 1 for m in limit.metadata),
              f"metadata={limit.metadata!r}")
    comprobar(f"[{nombre_endpoint}] `limit` tiene tope real de 200 (le=200) — evita limit=999999",
              any(isinstance(m, Le) and m.le == 200 for m in limit.metadata),
              f"metadata={limit.metadata!r}")


def test_personas():
    _verificar_query_de_paginacion("GET /admin/personas/{institucion_id}", listar_personas_de_institucion)


def test_campanas():
    _verificar_query_de_paginacion("GET /educativo/campanas/", listar_campanas)


def test_documentos():
    _verificar_query_de_paginacion("GET /documentos/", listar_documentos_institucionales)


def test_crud_devuelve_total_y_items():
    print("\nLas 3 funciones crud devuelven (total, items) — nunca una lista plana")
    for nombre, funcion in (
        ("obtener_personas_por_institucion", sa_crud.obtener_personas_por_institucion),
        ("listar_campanas_de_institucion", edu_crud.listar_campanas_de_institucion),
        ("listar_documentos_visibles_para_usuario", doc_crud.listar_documentos_visibles_para_usuario),
    ):
        parametros = inspect.signature(funcion).parameters
        comprobar(f"[{nombre}] acepta `skip`/`limit` con default 0/50",
                  parametros["skip"].default == 0 and parametros["limit"].default == 50,
                  f"skip={parametros['skip'].default!r} limit={parametros['limit'].default!r}")


def test_documentos_count_despues_del_filtro_nivel_visibilidad():
    # 🔒 El COUNT/LIMIT debe aplicarse DESPUÉS de filtrar por nivel_visibilidad
    # (rol 'colegio'), no antes, o `total` quedaría mal para ese rol. Esto
    # solo se puede probar de verdad contra Postgres (ver ZZPAGIN en
    # verificar_paginacion_e2e.py); acá solo confirmamos, por inspección del
    # código fuente real (no una copia a mano), que `.count()` aparece
    # DESPUÉS del bloque `if usuario_actual.rol == "colegio"` en el texto de
    # la función — una regresión que invirtiera el orden rompería esto.
    print("\nOrden fuente: filtro nivel_visibilidad ANTES del count() en listar_documentos_visibles_para_usuario")
    fuente = inspect.getsource(doc_crud.listar_documentos_visibles_para_usuario)
    pos_filtro = fuente.index('usuario_actual.rol == "colegio"')
    pos_count = fuente.index(".count()")
    comprobar("El filtro de nivel_visibilidad aparece antes del .count() en el código fuente",
              pos_filtro < pos_count)


if __name__ == "__main__":
    test_personas()
    test_campanas()
    test_documentos()
    test_crud_devuelve_total_y_items()
    test_documentos_count_despues_del_filtro_nivel_visibilidad()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    sys.exit(0 if not fallos else 1)
