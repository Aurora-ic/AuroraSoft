"""Pruebas unitarias — PASO 1 (aislamiento de institucion_id en importación).

    python -m tests.test_aislamiento_importacion_unitario

Sin BD ni servidor: ejercita `_institucion_para_importacion` directamente con
objetos de usuario en memoria (SimpleNamespace), sin pasar por HTTP, y además
extrae el `Depends(requerir_rol(...))` real de cada endpoint de importación
para confirmar que `colegio` nunca puede invocarlos.
"""

import inspect
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from fastapi import HTTPException  # noqa: E402

from modulos.superadmin import router as superadmin_router  # noqa: E402
from modulos.superadmin.router import _institucion_para_importacion  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _usuario(rol, institucion_id):
    return SimpleNamespace(rol=rol, institucion_id=institucion_id)


# ---------------------------------------------------------------------------
# _institucion_para_importacion — regla objetivo: superadmin explícito;
# admin/psicologo SIEMPRE forzados a su propia institución, ignorando en
# silencio cualquier institucion_id ajeno en la request (misma convención que
# GET /auth/usuarios/).
# ---------------------------------------------------------------------------

def test_no_superadmin_con_institucion_ajena_se_ignora_en_silencio():
    print("\nNo-superadmin (admin) + institucion_id de OTRO colegio -> se IGNORA, devuelve la propia (sin 403)")
    usuario = _usuario("admin", institucion_id=10)
    resultado = _institucion_para_importacion(usuario, institucion_id=99)
    comprobar(
        "Devuelve la institución del token, nunca la ajena pedida",
        resultado == 10,
        f"resultado={resultado}",
    )


def test_no_superadmin_psicologo_con_institucion_ajena_se_ignora_en_silencio():
    print("\nNo-superadmin (psicologo) + institucion_id de OTRO colegio -> se IGNORA, devuelve la propia (sin 403)")
    usuario = _usuario("psicologo", institucion_id=10)
    resultado = _institucion_para_importacion(usuario, institucion_id=99)
    comprobar(
        "Devuelve la institución del token, nunca la ajena pedida",
        resultado == 10,
        f"resultado={resultado}",
    )


def test_no_superadmin_sin_institucion_sigue_igual():
    print("\nNo-superadmin sin institucion_id en el query -> su propia institución, sin cambios")
    usuario = _usuario("psicologo", institucion_id=10)
    resultado = _institucion_para_importacion(usuario, institucion_id=None)
    comprobar("Devuelve la institución del usuario", resultado == 10)


def test_no_superadmin_con_su_propia_institucion_sigue_igual():
    print("\nNo-superadmin enviando SU PROPIA institucion_id -> se acepta, sin cambios")
    usuario = _usuario("psicologo", institucion_id=10)
    resultado = _institucion_para_importacion(usuario, institucion_id=10)
    comprobar("Devuelve su propia institución", resultado == 10)


def test_superadmin_sigue_igual():
    print("\nSuperadmin — comportamiento sin cambios (400 si falta, o el valor pedido)")
    usuario = _usuario("superadmin", institucion_id=None)
    try:
        _institucion_para_importacion(usuario, institucion_id=None)
        comprobar("Superadmin sin institucion_id -> lanza HTTPException", False)
    except HTTPException as exc:
        comprobar("Superadmin sin institucion_id -> 400 (no cambia)", exc.status_code == 400)
    comprobar("Superadmin CON institucion_id -> devuelve exactamente ese valor, cualquiera que sea",
              _institucion_para_importacion(usuario, institucion_id=77) == 77)


# ---------------------------------------------------------------------------
# Rol permitido en los tres endpoints reales — colegio nunca debe pasar.
# Se extrae el verificador real de `Depends(requerir_rol(...))` de cada
# función del router (no una copia/asunción del rol permitido) y se llama
# directamente, sin pasar por FastAPI ni por HTTP.
# ---------------------------------------------------------------------------

_ENDPOINTS_IMPORTACION = {
    "GET /importar/plantilla": superadmin_router.descargar_plantilla_importacion,
    "POST /importar/validar": superadmin_router.validar_importacion_estudiantes,
    "POST /importar/confirmar": superadmin_router.confirmar_importacion_estudiantes,
}


def _extraer_verificador_de_rol(endpoint_fn):
    firma = inspect.signature(endpoint_fn)
    default = firma.parameters["usuario_actual"].default
    dependencia = getattr(default, "dependency", None)
    assert dependencia is not None, (
        f"{endpoint_fn.__name__} no usa Depends(...) para 'usuario_actual'"
    )
    return dependencia


def test_endpoints_importacion_bloquean_colegio():
    for nombre, endpoint_fn in _ENDPOINTS_IMPORTACION.items():
        verificador = _extraer_verificador_de_rol(endpoint_fn)
        try:
            verificador(usuario_actual=_usuario("colegio", institucion_id=10))
            comprobar(f"{nombre}: colegio -> 403", False)
        except HTTPException as exc:
            comprobar(f"{nombre}: colegio -> 403", exc.status_code == 403, f"status={exc.status_code}")


def test_endpoints_importacion_permiten_admin_psicologo_superadmin():
    for nombre, endpoint_fn in _ENDPOINTS_IMPORTACION.items():
        verificador = _extraer_verificador_de_rol(endpoint_fn)
        for rol in ("superadmin", "admin", "psicologo"):
            usuario = _usuario(rol, institucion_id=10)
            resultado = verificador(usuario_actual=usuario)
            comprobar(f"{nombre}: {rol} -> permitido", resultado is usuario)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — PASO 1: aislamiento de institucion_id en importación")
    print("=" * 72)
    test_no_superadmin_con_institucion_ajena_se_ignora_en_silencio()
    test_no_superadmin_psicologo_con_institucion_ajena_se_ignora_en_silencio()
    test_no_superadmin_sin_institucion_sigue_igual()
    test_no_superadmin_con_su_propia_institucion_sigue_igual()
    test_superadmin_sigue_igual()
    test_endpoints_importacion_bloquean_colegio()
    test_endpoints_importacion_permiten_admin_psicologo_superadmin()

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
