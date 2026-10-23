"""Pruebas unitarias — Motor de documentos institucionales, Paso 3
(creación de DocumentoInstitucional: validación de alcance/estructura).

    python -m tests.test_documentos_creacion_unitario

No necesitan la base de datos ni el servidor: solo ejercitan los
validadores de `modulos/documentos/schemas.py` en memoria.
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


def _base(**overrides):
    datos = dict(tipo_documento_id=1, plantilla_documento_id=1, titulo="Documento de prueba")
    datos.update(overrides)
    return datos


# ==========================================
# NodoEstructuraSeleccion — exactamente uno
# ==========================================
def test_nodo_estructura_acepta_exactamente_uno():
    print("\nNodoEstructuraSeleccion — un solo campo por nodo")
    nodo = schemas.NodoEstructuraSeleccion(seccion_id=5)
    comprobar("seccion_id solo, aceptado", nodo.seccion_id == 5)


def test_nodo_estructura_rechaza_ninguno():
    print("\nNodoEstructuraSeleccion — sin ningún campo")
    try:
        schemas.NodoEstructuraSeleccion()
        comprobar("Rechaza un nodo vacío", False)
    except ValidationError:
        comprobar("Rechaza un nodo vacío", True)


def test_nodo_estructura_rechaza_dos_a_la_vez():
    print("\nNodoEstructuraSeleccion — dos campos a la vez")
    try:
        schemas.NodoEstructuraSeleccion(grado_id=1, seccion_id=2)
        comprobar("Rechaza grado_id + seccion_id juntos", False)
    except ValidationError:
        comprobar("Rechaza grado_id + seccion_id juntos", True)


# ==========================================
# DocumentoInstitucionalCreate — alcance/visibilidad válidos
# ==========================================
def test_alcance_invalido_rechazado():
    print("\nDocumentoInstitucionalCreate — alcance inventado")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(alcance="un_alcance_que_no_existe"))
        comprobar("Rechaza alcance inválido", False)
    except ValidationError:
        comprobar("Rechaza alcance inválido", True)


def test_visibilidad_invalida_rechazada():
    print("\nDocumentoInstitucionalCreate — nivel_visibilidad inventado")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(alcance="ninguno", nivel_visibilidad="publico"))
        comprobar("Rechaza nivel_visibilidad inválido", False)
    except ValidationError:
        comprobar("Rechaza nivel_visibilidad inválido", True)


# ==========================================
# Coherencia alcance <-> estructura/personas_ids
# ==========================================
def test_institucion_no_admite_estudiantes():
    print("\nalcance='institucion' — no admite estructura ni personas_ids")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(alcance="institucion", personas_ids=[1]))
        comprobar("Rechaza personas_ids con alcance='institucion'", False)
    except ValidationError:
        comprobar("Rechaza personas_ids con alcance='institucion'", True)
    ok = schemas.DocumentoInstitucionalCreate(**_base(alcance="institucion"))
    comprobar("Sin estudiantes, 'institucion' es válido", ok.alcance == "institucion")


def test_ninguno_no_admite_estudiantes():
    print("\nalcance='ninguno' (plan de trabajo) — no admite estructura ni personas_ids")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(
            alcance="ninguno", estructura=[{"seccion_id": 1}],
        ))
        comprobar("Rechaza estructura con alcance='ninguno'", False)
    except ValidationError:
        comprobar("Rechaza estructura con alcance='ninguno'", True)


def test_estructura_academica_exige_al_menos_un_nodo():
    print("\nalcance='estructura_academica' — exige al menos un nodo")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(alcance="estructura_academica"))
        comprobar("Rechaza estructura_academica sin ningún nodo", False)
    except ValidationError:
        comprobar("Rechaza estructura_academica sin ningún nodo", True)


def test_estructura_academica_admite_combinar_con_personas_ids():
    print("\nalcance='estructura_academica' — SÍ admite combinar con personas_ids sueltas")
    datos = schemas.DocumentoInstitucionalCreate(**_base(
        alcance="estructura_academica", anio_escolar=2026,
        estructura=[{"seccion_id": 10}], personas_ids=[99, 100],
    ))
    comprobar("Atajo por sección + nombres sueltos en el mismo documento",
               len(datos.estructura) == 1 and datos.personas_ids == [99, 100])


def test_personas_especificas_es_manual_puro():
    print("\nalcance='personas_especificas' — rechaza 'estructura' (selección manual pura)")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(
            alcance="personas_especificas", estructura=[{"seccion_id": 1}], personas_ids=[1],
        ))
        comprobar("Rechaza combinar 'estructura' con alcance='personas_especificas'", False)
    except ValidationError as exc:
        comprobar("Rechaza combinar 'estructura' con alcance='personas_especificas'", True, str(exc)[:100])


def test_personas_especificas_exige_al_menos_una_persona():
    print("\nalcance='personas_especificas' — exige al menos una persona")
    try:
        schemas.DocumentoInstitucionalCreate(**_base(alcance="personas_especificas"))
        comprobar("Rechaza personas_especificas sin ninguna persona", False)
    except ValidationError:
        comprobar("Rechaza personas_especificas sin ninguna persona", True)


def test_personas_especificas_combinando_varias_secciones_29_estudiantes():
    print("\nalcance='personas_especificas' — caso real: 29 estudiantes de varios grados")
    ids = list(range(1000, 1029))
    datos = schemas.DocumentoInstitucionalCreate(**_base(alcance="personas_especificas", personas_ids=ids))
    comprobar("29 personas_ids aceptadas, sin estructura", len(datos.personas_ids) == 29 and not datos.estructura)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (CREACIÓN)")
    print("=" * 72)
    test_nodo_estructura_acepta_exactamente_uno()
    test_nodo_estructura_rechaza_ninguno()
    test_nodo_estructura_rechaza_dos_a_la_vez()
    test_alcance_invalido_rechazado()
    test_visibilidad_invalida_rechazada()
    test_institucion_no_admite_estudiantes()
    test_ninguno_no_admite_estudiantes()
    test_estructura_academica_exige_al_menos_un_nodo()
    test_estructura_academica_admite_combinar_con_personas_ids()
    test_personas_especificas_es_manual_puro()
    test_personas_especificas_exige_al_menos_una_persona()
    test_personas_especificas_combinando_varias_secciones_29_estudiantes()

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
