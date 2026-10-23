"""Pruebas unitarias — Cierre de gaps conocidos del backend (docs/gaps-pendientes.md).

    python -m tests.test_gaps_backend_unitario

Sin BD ni servidor. Cubre dos cierres independientes:

  1. `GET /auth/me` — existe, depende de `obtener_usuario_actual` (no de un
     rol específico, cualquier cuenta autenticada puede usarlo), y responde
     con `schemas.UsuarioResponse`.
  2. Los cinco CHECK constraints nuevos sobre columnas de "estado" que antes
     eran String libre sin ninguna validación a nivel de base de datos:
     `edu_inscripciones.estado`, `edu_inscripciones.estado_interpretacion`,
     `edu_sesiones_seguimiento.estado`, `citas_programadas.estado`,
     `auth_usuarios.rol`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

import main  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from modulos.auth import models as auth_models, schemas as auth_schemas  # noqa: E402
from modulos.educativo import models as educativo_models  # noqa: E402
from modulos.superadmin import models as superadmin_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _ruta(metodo, path):
    for route in main.app.routes:
        if isinstance(route, APIRoute) and route.path == path and metodo in route.methods:
            return route
    return None


def test_auth_me_existe_y_no_exige_rol_especifico():
    print("\nGET /auth/me — existe, cualquier rol autenticado, responde UsuarioResponse")
    route = _ruta("GET", "/api/auth/me")
    comprobar("La ruta existe", route is not None)
    if route is None:
        return

    nombres_dependencias = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
    comprobar(
        "Depende de obtener_usuario_actual (cualquier rol autenticado, sin requerir_rol propio)",
        "obtener_usuario_actual" in nombres_dependencias,
        f"dependencias={nombres_dependencias}",
    )
    comprobar(
        "NO tiene un requerir_rol propio (ningún rol queda excluido)",
        not any(getattr(d.call, "__qualname__", "") == "requerir_rol.<locals>.verificador" for d in route.dependant.dependencies),
    )
    comprobar("response_model es UsuarioResponse", route.response_model is auth_schemas.UsuarioResponse)

    import inspect
    fuente = inspect.getsource(route.endpoint)
    comprobar(
        "El endpoint no tiene lógica propia — devuelve usuario_actual tal cual "
        "(todo el trabajo real ya lo hizo obtener_usuario_actual)",
        "return usuario_actual" in fuente,
    )


def _tiene_check(tabla, nombre_constraint):
    nombres = [c.name for c in tabla.constraints]
    return nombre_constraint in nombres


def test_check_constraints_estados_libres():
    print("\nCHECK constraints nuevos sobre columnas de estado antes sin validar")

    comprobar(
        "edu_inscripciones: ck_inscripciones_estado_valido existe",
        _tiene_check(educativo_models.Inscripcion.__table__, "ck_inscripciones_estado_valido"),
    )
    comprobar(
        "edu_inscripciones: ck_inscripciones_estado_interpretacion_valido existe",
        _tiene_check(educativo_models.Inscripcion.__table__, "ck_inscripciones_estado_interpretacion_valido"),
    )
    comprobar(
        "edu_sesiones_seguimiento: ck_sesiones_seguimiento_estado_valido existe",
        _tiene_check(educativo_models.SesionSeguimiento.__table__, "ck_sesiones_seguimiento_estado_valido"),
    )
    comprobar(
        "citas_programadas: ck_citas_programadas_estado_valido existe",
        _tiene_check(superadmin_models.CitaProgramada.__table__, "ck_citas_programadas_estado_valido"),
    )
    comprobar(
        "auth_usuarios: ck_usuarios_rol_valido existe",
        _tiene_check(auth_models.Usuario.__table__, "ck_usuarios_rol_valido"),
    )

    # Las columnas siguen siendo String libre a nivel de Python (el CHECK
    # vive en la base de datos, no en el tipo) — esto confirma que no se
    # cambió el tipo de columna de paso, solo se le agregó la validación.
    comprobar(
        "Inscripcion.estado sigue siendo String (el CHECK no cambia el tipo)",
        str(educativo_models.Inscripcion.__table__.columns["estado"].type) == "VARCHAR"
        or "String" in str(type(educativo_models.Inscripcion.__table__.columns["estado"].type)),
    )


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Cierre de gaps conocidos del backend")
    print("=" * 72)
    test_auth_me_existe_y_no_exige_rol_especifico()
    test_check_constraints_estados_libres()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
