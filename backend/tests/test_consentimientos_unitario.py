"""Pruebas unitarias — Consentimientos del estudiante y del apoderado.

    python tests/test_consentimientos_unitario.py

No necesitan la base de datos ni el servidor.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import models, schemas, crud  # noqa: E402
from modulos.educativo import models as edu_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_constantes_extensibles():
    print("\nModelos — tipo/estado controlados por constantes, no texto libre disperso")
    comprobar("TIPO_CONSENTIMIENTO_APODERADO == 'apoderado'", models.TIPO_CONSENTIMIENTO_APODERADO == "apoderado")
    comprobar("TIPO_CONSENTIMIENTO_ASENTIMIENTO == 'asentimiento'", models.TIPO_CONSENTIMIENTO_ASENTIMIENTO == "asentimiento")
    comprobar("TIPOS_CONSENTIMIENTO_VALIDOS trae ambos", set(models.TIPOS_CONSENTIMIENTO_VALIDOS) == {"apoderado", "asentimiento"})
    comprobar("ESTADO_CONSENTIMIENTO_VIGENTE == 'vigente'", models.ESTADO_CONSENTIMIENTO_VIGENTE == "vigente")
    comprobar("ESTADO_CONSENTIMIENTO_REVOCADO == 'revocado'", models.ESTADO_CONSENTIMIENTO_REVOCADO == "revocado")


def test_check_constraints_en_bd():
    print("\nModelos — CHECK constraints a nivel de base de datos")
    nombres = [c.name for c in models.ConsentimientoInformado.__table__.constraints]
    comprobar("ck_consentimientos_tipo_valido existe", "ck_consentimientos_tipo_valido" in nombres)
    comprobar("ck_consentimientos_estado_valido existe", "ck_consentimientos_estado_valido" in nombres)


def test_indice_unico_parcial_por_tipo():
    print("\nModelos — a lo sumo un consentimiento vigente POR TIPO, no combinado")
    indices = [ix for ix in models.ConsentimientoInformado.__table__.indexes if ix.unique]
    objetivo = [ix for ix in indices if ix.name == "uq_consentimiento_vigente_por_persona_y_tipo"]
    comprobar("Existe el índice único parcial", len(objetivo) == 1)
    if objetivo:
        columnas = [c.name for c in objetivo[0].columns]
        comprobar(
            "Cubre persona_id + institucion_id + tipo_consentimiento (no combina apoderado y estudiante)",
            set(columnas) == {"persona_id", "institucion_id", "tipo_consentimiento"},
            str(columnas),
        )
        comprobar(
            "Es PARCIAL (solo estado='vigente', no bloquea el historial revocado)",
            objetivo[0].dialect_options.get("postgresql", {}).get("where") is not None,
        )


def test_columnas_apoderado_son_nullable():
    print("\nModelos — las columnas exclusivas de 'apoderado' son NULLABLE (para poder alojar 'estudiante')")
    for columna in ("otorgado_por_nombre", "tipo_otorgante", "otorgante_apellidos", "otorgante_documento", "otorgante_relacion"):
        col = models.ConsentimientoInformado.__table__.columns[columna]
        comprobar(f"{columna} es nullable", col.nullable, f"nullable={col.nullable}")


def test_snapshot_en_inscripcion():
    print("\nModelos — Inscripcion guarda snapshot de qué consentimiento estaba vigente")
    for columna in ("consentimiento_apoderado_id", "consentimiento_asentimiento_id"):
        comprobar(f"Inscripcion.{columna} existe", hasattr(edu_models.Inscripcion, columna))
    col = edu_models.Inscripcion.__table__.columns["consentimiento_apoderado_id"]
    comprobar("consentimiento_apoderado_id es nullable (cupos anónimos, sin persona)", col.nullable)


def test_esquemas_no_confian_en_ids_derivables():
    print("\nEsquemas — ConsentimientoAsentimientoCreate no pide persona_id/institucion_id")
    comprobar(
        "persona_id NO está en ConsentimientoAsentimientoCreate",
        "persona_id" not in schemas.ConsentimientoAsentimientoCreate.model_fields,
    )
    comprobar(
        "institucion_id NO está en ConsentimientoAsentimientoCreate",
        "institucion_id" not in schemas.ConsentimientoAsentimientoCreate.model_fields,
    )


def test_funciones_crud_aceptan_tipo_consentimiento():
    print("\nCRUD — las funciones de vigencia/revocación/historial aceptan tipo_consentimiento")
    import inspect
    for nombre_fn in ("tiene_consentimiento_vigente", "obtener_consentimiento_vigente",
                      "registrar_consentimiento", "revocar_consentimiento_de_persona",
                      "historial_consentimientos"):
        fn = getattr(crud, nombre_fn)
        firma = inspect.signature(fn)
        comprobar(f"{nombre_fn} acepta tipo_consentimiento", "tipo_consentimiento" in firma.parameters)

    # El valor por defecto sigue siendo "apoderado" — todo el código de las
    # fases anteriores que llama a estas funciones SIN pasar tipo_consentimiento
    # (el candado de matrícula del roster, el candado del examen en vivo)
    # debe seguir comportándose EXACTAMENTE igual que antes.
    default_vigente = inspect.signature(crud.tiene_consentimiento_vigente).parameters["tipo_consentimiento"].default
    comprobar(
        "El valor por defecto de tipo_consentimiento sigue siendo 'apoderado' (compatibilidad retroactiva)",
        default_vigente == models.TIPO_CONSENTIMIENTO_APODERADO,
    )


def test_tipo_perfil_bloquea_matricula():
    print("\nCRUD — matricular_persona_en_seccion rechaza tipo_perfil != 'estudiante'")
    import inspect
    fuente = inspect.getsource(crud.matricular_persona_en_seccion)
    comprobar(
        "La función comprueba tipo_perfil antes de matricular",
        "persona.tipo_perfil != \"estudiante\"" in fuente or "persona.tipo_perfil != 'estudiante'" in fuente,
    )


def test_matricular_roster_guarda_snapshot_de_consentimiento():
    print("\nCRUD — matricular_roster_en_campana guarda el snapshot de consentimiento")
    import inspect
    from modulos.educativo import crud as edu_crud
    fuente = inspect.getsource(edu_crud.matricular_roster_en_campana)
    comprobar(
        "Usa obtener_consentimiento_vigente (la fila, no solo el booleano)",
        "obtener_consentimiento_vigente" in fuente,
    )
    comprobar(
        "Guarda consentimiento_apoderado_id en la nueva inscripción",
        "consentimiento_apoderado_id=consentimiento_apoderado.id" in fuente,
    )
    comprobar(
        "Guarda consentimiento_asentimiento_id en la nueva inscripción (si existe)",
        "consentimiento_asentimiento_id=" in fuente,
    )


def test_revocar_no_hace_borrado_fisico():
    print("\nCRUD — revocar_consentimiento actualiza la fila, nunca la borra")
    import inspect
    fuente = inspect.getsource(crud.revocar_consentimiento)
    comprobar("No hay ningún db.delete(...) en la revocación", "db.delete" not in fuente)
    comprobar("Marca estado=revocado y revocado=True en la MISMA fila", "estado = models.ESTADO_CONSENTIMIENTO_REVOCADO" in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — CONSENTIMIENTOS DEL ESTUDIANTE Y DEL APODERADO")
    print("=" * 72)
    test_constantes_extensibles()
    test_check_constraints_en_bd()
    test_indice_unico_parcial_por_tipo()
    test_columnas_apoderado_son_nullable()
    test_snapshot_en_inscripcion()
    test_esquemas_no_confian_en_ids_derivables()
    test_funciones_crud_aceptan_tipo_consentimiento()
    test_tipo_perfil_bloquea_matricula()
    test_matricular_roster_guarda_snapshot_de_consentimiento()
    test_revocar_no_hace_borrado_fisico()

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
