"""Pruebas unitarias — Motor de documentos institucionales, Paso 6
(usuario_puede_ver_documento: tabla de verdad rol × nivel_visibilidad).

    python -m tests.test_documentos_acceso_unitario

No necesitan la base de datos ni el servidor: `usuario_puede_ver_documento`
se ejercita con objetos en memoria (mismo patrón que
test_expediente_unitario.py para usuario_puede_ver_contenido_completo).
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.documentos import crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def _usuario(rol, institucion_id=1):
    return SimpleNamespace(rol=rol, institucion_id=institucion_id)


def _documento(institucion_id=1, nivel_visibilidad="confidencial_clinico"):
    return SimpleNamespace(institucion_id=institucion_id, nivel_visibilidad=nivel_visibilidad)


def test_superadmin_siempre_ve_cualquier_documento():
    print("\nsuperadmin — siempre, sin importar institución ni visibilidad")
    doc = _documento(institucion_id=999, nivel_visibilidad="confidencial_clinico")
    comprobar("superadmin ve un documento confidencial de otra institución",
               crud.usuario_puede_ver_documento(_usuario("superadmin", institucion_id=1), doc) is True)


def test_admin_y_psicologo_ven_confidencial_de_su_institucion():
    print("\nadmin/psicologo de la MISMA institución — ven 'confidencial_clinico', sin ACL por documento")
    doc = _documento(institucion_id=1, nivel_visibilidad="confidencial_clinico")
    comprobar("admin de la misma institución ve el confidencial",
               crud.usuario_puede_ver_documento(_usuario("admin", institucion_id=1), doc) is True)
    comprobar("psicologo de la misma institución ve el confidencial (aunque no lo haya creado él)",
               crud.usuario_puede_ver_documento(_usuario("psicologo", institucion_id=1), doc) is True)


def test_admin_y_psicologo_de_otra_institucion_no_ven_nada():
    print("\nadmin/psicologo de OTRA institución — nunca, sin importar visibilidad")
    doc_confidencial = _documento(institucion_id=1, nivel_visibilidad="confidencial_clinico")
    doc_compartible = _documento(institucion_id=1, nivel_visibilidad="compartible_colegio")
    comprobar("admin de otra institución no ve el confidencial",
               crud.usuario_puede_ver_documento(_usuario("admin", institucion_id=2), doc_confidencial) is False)
    comprobar("psicologo de otra institución tampoco ve el compartible_colegio (no es SU institución)",
               crud.usuario_puede_ver_documento(_usuario("psicologo", institucion_id=2), doc_compartible) is False)


def test_colegio_no_ve_confidencial_clinico():
    print("\ncolegio — NO ve 'confidencial_clinico' aunque sea de su propia institución")
    doc = _documento(institucion_id=1, nivel_visibilidad="confidencial_clinico")
    comprobar("colegio de la misma institución NO ve el confidencial",
               crud.usuario_puede_ver_documento(_usuario("colegio", institucion_id=1), doc) is False)


def test_colegio_si_ve_compartible_colegio_de_su_institucion():
    print("\ncolegio — SÍ ve 'compartible_colegio' de su propia institución")
    doc = _documento(institucion_id=1, nivel_visibilidad="compartible_colegio")
    comprobar("colegio de la misma institución ve el compartible_colegio",
               crud.usuario_puede_ver_documento(_usuario("colegio", institucion_id=1), doc) is True)


def test_colegio_no_ve_compartible_colegio_de_otra_institucion():
    print("\ncolegio — nunca cruza tenant, ni siquiera para 'compartible_colegio'")
    doc = _documento(institucion_id=1, nivel_visibilidad="compartible_colegio")
    comprobar("colegio de OTRA institución no ve el compartible_colegio de la institución 1",
               crud.usuario_puede_ver_documento(_usuario("colegio", institucion_id=2), doc) is False)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (ACCESO)")
    print("=" * 72)
    test_superadmin_siempre_ve_cualquier_documento()
    test_admin_y_psicologo_ven_confidencial_de_su_institucion()
    test_admin_y_psicologo_de_otra_institucion_no_ven_nada()
    test_colegio_no_ve_confidencial_clinico()
    test_colegio_si_ve_compartible_colegio_de_su_institucion()
    test_colegio_no_ve_compartible_colegio_de_otra_institucion()

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
