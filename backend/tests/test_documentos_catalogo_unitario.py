"""Pruebas unitarias — Motor de documentos institucionales, Paso 1
(catálogo: TipoDocumento/AnioOficial/PlantillaDocumento/PlantillaSeccion).

    python -m tests.test_documentos_catalogo_unitario

No necesitan la base de datos ni el servidor: solo ejercitan los
validadores de `modulos/documentos/schemas.py` en memoria — mismo patrón
que `test_expediente_unitario.py`.
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


def _tipo_documento_base(**overrides):
    datos = dict(
        clave="informe_individual",
        nombre="Informe individual",
        alcances_permitidos="personas_especificas",
        visibilidades_permitidas="confidencial_clinico",
        requiere_consentimiento_individual=True,
    )
    datos.update(overrides)
    return datos


# ==========================================
# TipoDocumento — alcances_permitidos / visibilidades_permitidas
# ==========================================
def test_alcances_permitidos_acepta_valores_validos():
    print("\nTipoDocumento — alcances_permitidos válido")
    tipo = schemas.TipoDocumentoCreate(**_tipo_documento_base(
        alcances_permitidos="estructura_academica, personas_especificas",
    ))
    comprobar("Se normaliza a 'estructura_academica, personas_especificas'",
               tipo.alcances_permitidos == "estructura_academica, personas_especificas")


def test_alcances_permitidos_rechaza_valor_desconocido():
    print("\nTipoDocumento — alcances_permitidos con valor inventado")
    try:
        schemas.TipoDocumentoCreate(**_tipo_documento_base(alcances_permitidos="institucion, inventado"))
        comprobar("Rechaza 'inventado'", False)
    except ValidationError as exc:
        comprobar("Rechaza 'inventado' con 422/ValidationError", True, str(exc)[:120])


def test_alcances_permitidos_rechaza_vacio():
    print("\nTipoDocumento — alcances_permitidos vacío")
    try:
        schemas.TipoDocumentoCreate(**_tipo_documento_base(alcances_permitidos="   "))
        comprobar("Rechaza cadena vacía/solo espacios", False)
    except ValidationError:
        comprobar("Rechaza cadena vacía/solo espacios", True)


def test_visibilidades_permitidas_rechaza_valor_desconocido():
    print("\nTipoDocumento — visibilidades_permitidas con valor inventado")
    try:
        schemas.TipoDocumentoCreate(**_tipo_documento_base(visibilidades_permitidas="publico"))
        comprobar("Rechaza 'publico' (no es un nivel_visibilidad real)", False)
    except ValidationError:
        comprobar("Rechaza 'publico' (no es un nivel_visibilidad real)", True)


def test_visibilidades_permitidas_acepta_las_dos_reales():
    print("\nTipoDocumento — visibilidades_permitidas con los dos valores reales")
    tipo = schemas.TipoDocumentoCreate(**_tipo_documento_base(
        visibilidades_permitidas="confidencial_clinico,compartible_colegio",
    ))
    comprobar("Ambos valores aceptados y normalizados",
               tipo.visibilidades_permitidas == "confidencial_clinico, compartible_colegio")


def test_requiere_consentimiento_individual_es_el_unico_campo_de_gate():
    print("\nTipoDocumento — requiere_consentimiento_individual por defecto en false")
    tipo = schemas.TipoDocumentoCreate(**{**_tipo_documento_base(), "requiere_consentimiento_individual": False})
    comprobar("Un tipo grupal puede declararse sin exigir consentimiento", tipo.requiere_consentimiento_individual is False)


def test_tipo_documento_update_no_valida_campos_ausentes():
    print("\nTipoDocumentoUpdate — campos ausentes no disparan validación")
    actualizacion = schemas.TipoDocumentoUpdate(nombre="Nuevo nombre")
    comprobar("alcances_permitidos ausente no rompe nada", actualizacion.alcances_permitidos is None)


def test_tipo_documento_update_valida_si_se_manda():
    print("\nTipoDocumentoUpdate — si se manda un campo, sí se valida")
    try:
        schemas.TipoDocumentoUpdate(alcances_permitidos="no_existe")
        comprobar("Rechaza valor inválido incluso en Update parcial", False)
    except ValidationError:
        comprobar("Rechaza valor inválido incluso en Update parcial", True)


# ==========================================
# PlantillaDocumento — formato_correlativo (dry-run al guardar)
# ==========================================
def test_formato_correlativo_none_es_valido():
    print("\nPlantillaDocumento — formato_correlativo=None (sin numeración automática)")
    plantilla = schemas.PlantillaDocumentoCreate(
        institucion_id=1, tipo_documento_id=1, nombre="Plantilla X", formato_correlativo=None,
    )
    comprobar("None pasa sin intentar formatear nada", plantilla.formato_correlativo is None)


def test_formato_correlativo_valido():
    print("\nPlantillaDocumento — formato_correlativo con placeholders correctos")
    plantilla = schemas.PlantillaDocumentoCreate(
        institucion_id=1, tipo_documento_id=1, nombre="Plantilla X",
        formato_correlativo="INFORME-{correlativo:04d}-{anio}",
    )
    comprobar("Se acepta tal cual", plantilla.formato_correlativo == "INFORME-{correlativo:04d}-{anio}")


def test_formato_correlativo_con_placeholder_invalido():
    print("\nPlantillaDocumento — formato_correlativo con placeholder inexistente")
    try:
        schemas.PlantillaDocumentoCreate(
            institucion_id=1, tipo_documento_id=1, nombre="Plantilla X",
            formato_correlativo="INFORME-{numero}-{anio}",
        )
        comprobar("Rechaza {numero} (no es un placeholder real) al GUARDAR la plantilla", False)
    except ValidationError as exc:
        comprobar("Rechaza {numero} (no es un placeholder real) al GUARDAR la plantilla", True, str(exc)[:120])


def test_formato_correlativo_con_sintaxis_rota():
    print("\nPlantillaDocumento — formato_correlativo con llave sin cerrar")
    try:
        schemas.PlantillaDocumentoCreate(
            institucion_id=1, tipo_documento_id=1, nombre="Plantilla X",
            formato_correlativo="INFORME-{correlativo",
        )
        comprobar("Rechaza sintaxis de formato rota", False)
    except ValidationError:
        comprobar("Rechaza sintaxis de formato rota", True)


def test_valores_por_defecto_de_tipografia_coinciden_con_el_informe_psicometrico():
    print("\nPlantillaDocumento — valores por defecto de tipografía")
    plantilla = schemas.PlantillaDocumentoCreate(institucion_id=1, tipo_documento_id=1, nombre="Plantilla X")
    comprobar("Fuente por defecto Arial (mismo punto de partida que core/pdf_generator.py)",
               plantilla.fuente == "Arial")
    comprobar("Tamaño por defecto 11pt", plantilla.tamano_pt == 11)
    comprobar("Justificado por defecto True", plantilla.justificado is True)


# ==========================================
# PlantillaSeccion — tipo_seccion (conjunto cerrado)
# ==========================================
def test_tipo_seccion_acepta_los_siete_valores_reales():
    print("\nPlantillaSeccion — los 7 tipos de sección reales")
    for tipo in ("encabezado", "datos_filiacion", "datos_familiares",
                 "texto_libre", "tabla_dinamica", "resultados_prueba", "firma"):
        seccion = schemas.PlantillaSeccionCreate(orden=0, tipo_seccion=tipo)
        comprobar(f"'{tipo}' aceptado", seccion.tipo_seccion == tipo)


def test_tipo_seccion_rechaza_un_octavo_tipo_inventado():
    print("\nPlantillaSeccion — un tipo de sección que no existe en el catálogo cerrado")
    try:
        schemas.PlantillaSeccionCreate(orden=0, tipo_seccion="ficha_campos")
        comprobar("Rechaza 'ficha_campos' (deliberadamente diferido, no construido aún)", False)
    except ValidationError:
        comprobar("Rechaza 'ficha_campos' (deliberadamente diferido, no construido aún)", True)


def test_plantilla_seccion_update_no_permite_cambiar_tipo_seccion():
    print("\nPlantillaSeccionUpdate — tipo_seccion no es un campo editable")
    campos = schemas.PlantillaSeccionUpdate.model_fields.keys()
    comprobar("'tipo_seccion' no aparece en los campos editables de Update", "tipo_seccion" not in campos)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (CATÁLOGO)")
    print("=" * 72)
    test_alcances_permitidos_acepta_valores_validos()
    test_alcances_permitidos_rechaza_valor_desconocido()
    test_alcances_permitidos_rechaza_vacio()
    test_visibilidades_permitidas_rechaza_valor_desconocido()
    test_visibilidades_permitidas_acepta_las_dos_reales()
    test_requiere_consentimiento_individual_es_el_unico_campo_de_gate()
    test_tipo_documento_update_no_valida_campos_ausentes()
    test_tipo_documento_update_valida_si_se_manda()
    test_formato_correlativo_none_es_valido()
    test_formato_correlativo_valido()
    test_formato_correlativo_con_placeholder_invalido()
    test_formato_correlativo_con_sintaxis_rota()
    test_valores_por_defecto_de_tipografia_coinciden_con_el_informe_psicometrico()
    test_tipo_seccion_acepta_los_siete_valores_reales()
    test_tipo_seccion_rechaza_un_octavo_tipo_inventado()
    test_plantilla_seccion_update_no_permite_cambiar_tipo_seccion()

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
