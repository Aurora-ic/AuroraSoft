"""Pruebas unitarias — Motor de documentos institucionales, Paso 4
(DocumentoInstitucionalSeccionContenido, borrador editable).

    python -m tests.test_documentos_contenido_unitario

No necesitan la base de datos ni el servidor.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pydantic import ValidationError  # noqa: E402

from modulos.documentos import schemas  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def test_contenido_acepta_objeto_json():
    print("\nDocumentoInstitucionalSeccionContenidoUpdate — objeto JSON válido")
    datos = schemas.DocumentoInstitucionalSeccionContenidoUpdate(contenido={"texto": "Motivo de la derivación..."})
    comprobar("Acepta un dict cualquiera", datos.contenido == {"texto": "Motivo de la derivación..."})


def test_contenido_acepta_none():
    print("\nDocumentoInstitucionalSeccionContenidoUpdate — None (limpiar la sección)")
    datos = schemas.DocumentoInstitucionalSeccionContenidoUpdate(contenido=None)
    comprobar("Acepta None explícito (vaciar la sección)", datos.contenido is None)


def test_contenido_por_defecto_es_none():
    print("\nDocumentoInstitucionalSeccionContenidoUpdate — sin campo, por defecto None")
    datos = schemas.DocumentoInstitucionalSeccionContenidoUpdate()
    comprobar("contenido por defecto None", datos.contenido is None)


def test_contenido_rechaza_un_array_suelto():
    print("\nDocumentoInstitucionalSeccionContenidoUpdate — un array suelto no es un objeto JSON")
    try:
        schemas.DocumentoInstitucionalSeccionContenidoUpdate(contenido=["no", "es", "un", "objeto"])
        comprobar("Rechaza una lista en vez de un objeto", False)
    except ValidationError:
        comprobar("Rechaza una lista en vez de un objeto", True)


def test_contenido_rechaza_un_string_suelto():
    print("\nDocumentoInstitucionalSeccionContenidoUpdate — un string suelto no es un objeto JSON")
    try:
        schemas.DocumentoInstitucionalSeccionContenidoUpdate(contenido="texto plano")
        comprobar("Rechaza un string en vez de un objeto", False)
    except ValidationError:
        comprobar("Rechaza un string en vez de un objeto", True)


def test_response_admite_seccion_nunca_tocada():
    print("\nDocumentoInstitucionalSeccionContenidoResponse — placeholder de sección sin editar")
    respuesta = schemas.DocumentoInstitucionalSeccionContenidoResponse(
        plantilla_seccion_id=1, tipo_seccion="texto_libre", titulo="Motivo", orden=0,
        contenido=None, editado_por_usuario_id=None, actualizado_en=None,
    )
    comprobar("contenido/editado_por_usuario_id/actualizado_en pueden ser None a la vez (nunca se tocó)",
               respuesta.contenido is None and respuesta.editado_por_usuario_id is None
               and respuesta.actualizado_en is None)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (CONTENIDO)")
    print("=" * 72)
    test_contenido_acepta_objeto_json()
    test_contenido_acepta_none()
    test_contenido_por_defecto_es_none()
    test_contenido_rechaza_un_array_suelto()
    test_contenido_rechaza_un_string_suelto()
    test_response_admite_seccion_nunca_tocada()

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
