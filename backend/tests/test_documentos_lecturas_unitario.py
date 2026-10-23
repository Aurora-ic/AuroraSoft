"""Pruebas unitarias — Motor de documentos institucionales, Paso 7
(auditoría de lectura: crud.registrar_lectura_documento).

    python -m tests.test_documentos_lecturas_unitario

No necesitan la base de datos ni el servidor: `registrar_lectura_documento`
se ejercita con un `db` falso (solo registra sus llamadas) y objetos en
memoria — mismo patrón que test_documentos_acceso_unitario.py para
usuario_puede_ver_documento.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.documentos import crud, models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


class _DBFalsa:
    """Sustituto mínimo de Session: solo registra qué se agregó/comiteó,
    nunca toca una base de datos real."""

    def __init__(self):
        self.agregados = []
        self.commits = 0

    def add(self, objeto):
        self.agregados.append(objeto)

    def commit(self):
        self.commits += 1


def _usuario(rol, usuario_id=42):
    return SimpleNamespace(rol=rol, id=usuario_id)


def _documento(documento_id=7, institucion_id=1):
    return SimpleNamespace(id=documento_id, institucion_id=institucion_id)


def test_lectura_de_contenido_por_psicologo_no_marca_via_colegio():
    print("\nLectura de secciones (contenido) por psicologo — vía colegio en False, sin número de versión")
    db = _DBFalsa()
    documento = _documento(documento_id=7, institucion_id=3)
    registro = crud.registrar_lectura_documento(
        db, documento, _usuario("psicologo", usuario_id=10), "contenido", ip_lectura="10.0.0.5",
    )
    comprobar("se agregó exactamente una fila", len(db.agregados) == 1)
    comprobar("se hizo commit", db.commits == 1)
    comprobar("documento_institucional_id correcto", registro.documento_institucional_id == 7)
    comprobar("institucion_id copiado del documento (no del usuario)", registro.institucion_id == 3)
    comprobar("leido_por_usuario_id correcto", registro.leido_por_usuario_id == 10)
    comprobar("rol_lector snapshoteado", registro.rol_lector == "psicologo")
    comprobar("ip_lectura guardada", registro.ip_lectura == "10.0.0.5")
    comprobar("tipo_acceso='contenido'", registro.tipo_acceso == "contenido")
    comprobar("numero_version_leida es None (el borrador no está versionado)", registro.numero_version_leida is None)
    comprobar("acceso_via_visibilidad_colegio es False", registro.acceso_via_visibilidad_colegio is False)


def test_descarga_pdf_por_admin_guarda_numero_de_version():
    print("\nDescarga de PDF por admin — guarda numero_version_leida, vía colegio en False")
    db = _DBFalsa()
    documento = _documento()
    registro = crud.registrar_lectura_documento(
        db, documento, _usuario("admin"), "descarga_pdf", ip_lectura=None, numero_version_leida=2,
    )
    comprobar("tipo_acceso='descarga_pdf'", registro.tipo_acceso == "descarga_pdf")
    comprobar("numero_version_leida=2", registro.numero_version_leida == 2)
    comprobar("acceso_via_visibilidad_colegio es False", registro.acceso_via_visibilidad_colegio is False)
    comprobar("ip_lectura None se guarda tal cual (no se inventa un dato)", registro.ip_lectura is None)


def test_lectura_por_colegio_marca_via_visibilidad_colegio():
    print("\nCualquier lectura por 'colegio' marca acceso_via_visibilidad_colegio=True")
    db = _DBFalsa()
    documento = _documento()
    registro_contenido = crud.registrar_lectura_documento(
        db, documento, _usuario("colegio"), "contenido",
    )
    registro_descarga = crud.registrar_lectura_documento(
        db, documento, _usuario("colegio"), "descarga_pdf", numero_version_leida=1,
    )
    comprobar("contenido por colegio marca vía colegio", registro_contenido.acceso_via_visibilidad_colegio is True)
    comprobar("descarga por colegio marca vía colegio", registro_descarga.acceso_via_visibilidad_colegio is True)
    comprobar("rol_lector='colegio' en ambas", registro_contenido.rol_lector == "colegio" and registro_descarga.rol_lector == "colegio")


def test_lectura_por_superadmin_no_marca_via_colegio():
    print("\nLectura por superadmin — nunca marca vía colegio")
    db = _DBFalsa()
    documento = _documento()
    registro = crud.registrar_lectura_documento(db, documento, _usuario("superadmin"), "contenido")
    comprobar("acceso_via_visibilidad_colegio es False para superadmin", registro.acceso_via_visibilidad_colegio is False)


def test_registro_es_instancia_del_modelo_correcto():
    print("\nEl objeto agregado a la sesión es un RegistroLecturaDocumento")
    db = _DBFalsa()
    documento = _documento()
    crud.registrar_lectura_documento(db, documento, _usuario("admin"), "contenido")
    comprobar("el objeto agregado es RegistroLecturaDocumento", isinstance(db.agregados[0], models.RegistroLecturaDocumento))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (AUDITORÍA DE LECTURA)")
    print("=" * 72)
    test_lectura_de_contenido_por_psicologo_no_marca_via_colegio()
    test_descarga_pdf_por_admin_guarda_numero_de_version()
    test_lectura_por_colegio_marca_via_visibilidad_colegio()
    test_lectura_por_superadmin_no_marca_via_colegio()
    test_registro_es_instancia_del_modelo_correcto()

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
