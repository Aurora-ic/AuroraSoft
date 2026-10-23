"""Pruebas unitarias — DiagnosticoAlumno.baremo_id, Baremo.activo/actualizado_en
y el bloqueo de edición sobre baremos en uso (auditoría de arquitectura
genérica, PUNTO 1).

    python -m tests.test_baremo_trazabilidad_unitario

Sin BD ni servidor.
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, schemas, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columnas_existen():
    print("\nModelo — columnas nuevas existen con el tipo/nulabilidad esperados")
    baremo_cols = models.Baremo.__table__.columns
    comprobar("Baremo.activo existe, NOT NULL, default True", "activo" in baremo_cols and not baremo_cols["activo"].nullable)
    comprobar("Baremo.activo tiene server_default 'true'", baremo_cols["activo"].server_default.arg == "true")
    comprobar("Baremo.actualizado_en existe y es nullable (NULL = nunca editado)",
              "actualizado_en" in baremo_cols and baremo_cols["actualizado_en"].nullable)
    comprobar("Baremo.actualizado_en es DateTime CON zona horaria (timezone=True)",
              baremo_cols["actualizado_en"].type.timezone is True)

    diag_cols = models.DiagnosticoAlumno.__table__.columns
    comprobar("DiagnosticoAlumno.baremo_id existe y es nullable", "baremo_id" in diag_cols and diag_cols["baremo_id"].nullable)
    fk = next(iter(diag_cols["baremo_id"].foreign_keys))
    comprobar("El FK de baremo_id apunta a edu_baremos.id", str(fk.target_fullname) == "edu_baremos.id")
    comprobar("El FK usa ondelete='SET NULL' (un baremo sin uso SÍ puede borrarse físicamente)",
              fk.ondelete == "SET NULL")


def test_actualizado_en_usa_datetime_con_zona_horaria_no_utcnow():
    print("\nModelo — el onupdate de actualizado_en produce un datetime CON zona horaria")
    columna = models.Baremo.__table__.columns["actualizado_en"]
    valor = columna.onupdate.arg(None)  # ColumnDefault envuelve el callable
    comprobar("El valor producido tiene tzinfo (no es un datetime naive como utcnow())", valor.tzinfo is not None)
    comprobar("Es UTC", valor.utcoffset() == timezone.utc.utcoffset(datetime.now()))


def test_schemas_exponen_lo_nuevo():
    print("\nschemas — BaremoResponse/BaremoUpdate/DiagnosticoAlumnoBase exponen lo nuevo")
    comprobar("BaremoResponse trae 'activo'", "activo" in schemas.BaremoResponse.model_fields)
    comprobar("BaremoResponse trae 'actualizado_en'", "actualizado_en" in schemas.BaremoResponse.model_fields)
    comprobar("BaremoUpdate permite 'activo' (la única vía de escape sobre un baremo en uso)",
              "activo" in schemas.BaremoUpdate.model_fields)
    comprobar("DiagnosticoAlumnoBase trae 'baremo_id'", "baremo_id" in schemas.DiagnosticoAlumnoBase.model_fields)


def test_campos_bloqueados_son_exactamente_rango_nivel_alerta():
    print("\ncrud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO — exactamente rango + nivel + es_alerta, nada más")
    comprobar("Son exactamente {puntaje_minimo, puntaje_maximo, edad_min, edad_max, nivel, es_alerta}",
              crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO == {
                  "puntaje_minimo", "puntaje_maximo", "edad_min", "edad_max", "nivel", "es_alerta",
              })
    comprobar("'activo' NUNCA está bloqueado (siempre debe poder desactivarse)",
              "activo" not in crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO)
    comprobar("'sexo'/'poblacion' NO están bloqueados (no son el criterio de clasificación en sí)",
              "sexo" not in crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO
              and "poblacion" not in crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO)
    comprobar("El contenido informativo (interpretacion/conclusion_sugerida/recomendacion_sugerida) NO está bloqueado",
              not crud.CAMPOS_BAREMO_BLOQUEADOS_SI_EN_USO & {
                  "interpretacion", "conclusion_sugerida", "recomendacion_sugerida", "tipo_puntaje", "valor_convertido",
              })


def test_eliminar_baremo_es_condicional_no_incondicional():
    print("\nGenericidad/seguridad — eliminar_baremo ya no hace db.delete() incondicional")
    import inspect
    cuerpo = inspect.getsource(crud.eliminar_baremo)
    comprobar("Llama a _baremo_tiene_diagnosticos antes de decidir", "_baremo_tiene_diagnosticos" in cuerpo)
    comprobar("Tiene una rama que solo desactiva (activo = False)", "activo = False" in cuerpo)
    comprobar("Sigue pudiendo borrar físicamente en el caso sin uso", "db.delete(baremo)" in cuerpo)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Trazabilidad y soft-delete de Baremo")
    print("=" * 72)
    test_columnas_existen()
    test_actualizado_en_usa_datetime_con_zona_horaria_no_utcnow()
    test_schemas_exponen_lo_nuevo()
    test_campos_bloqueados_son_exactamente_rango_nivel_alerta()
    test_eliminar_baremo_es_condicional_no_incondicional()

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
