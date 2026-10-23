"""Pruebas unitarias del Núcleo del Estudiante (estructura académica).

    python tests/test_nucleo_estudiante_unitario.py

No necesitan la base de datos ni el servidor.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import models, schemas  # noqa: E402
from modulos.superadmin import router as superadmin_router  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_modelos_existen_y_tienen_las_columnas_esperadas():
    print("\nModelos — tablas nuevas del núcleo del estudiante")
    comprobar("NivelEducativo existe", hasattr(models, "NivelEducativo"))
    comprobar("Grado existe", hasattr(models, "Grado"))
    comprobar("Seccion existe", hasattr(models, "Seccion"))
    comprobar("MatriculaAcademica existe", hasattr(models, "MatriculaAcademica"))
    comprobar("Persona.codigo_institucional existe", hasattr(models.Persona, "codigo_institucional"))

    from modulos.educativo import models as edu_models
    comprobar("Inscripcion.seccion_id existe", hasattr(edu_models.Inscripcion, "seccion_id"))
    comprobar(
        "Inscripcion.grado_seccion_historico existe",
        hasattr(edu_models.Inscripcion, "grado_seccion_historico"),
    )


def test_matricula_tiene_indice_unico_parcial():
    print("\nModelos — a lo sumo una matrícula vigente por persona")
    indices = [ix for ix in models.MatriculaAcademica.__table__.indexes if ix.unique]
    comprobar("Existe un índice único sobre persona_id", any("persona_id" in [c.name for c in ix.columns] for ix in indices))
    con_where = [ix for ix in indices if ix.dialect_options.get("postgresql", {}).get("where") is not None]
    comprobar("Ese índice único es PARCIAL (solo fecha_fin IS NULL, no bloquea el historial)", len(con_where) >= 1)


def test_unicidad_por_institucion_no_global():
    print("\nModelos — unicidad de documento y código institucional POR institución")
    nombres_constraints = [uc.name for uc in models.Persona.__table__.constraints]
    comprobar("uq_personas_institucion_documento sigue existiendo", "uq_personas_institucion_documento" in nombres_constraints)
    comprobar("uq_personas_institucion_codigo existe", "uq_personas_institucion_codigo" in nombres_constraints)


def test_esquemas_no_piden_institucion_id_donde_se_puede_derivar():
    print("\nEsquemas — no confiar en institucion_id del frontend cuando se puede derivar del padre")
    comprobar(
        "GradoCreate NO pide institucion_id (se deriva de nivel_educativo_id)",
        "institucion_id" not in schemas.GradoCreate.model_fields,
    )
    comprobar(
        "SeccionCreate NO pide institucion_id (se deriva de grado_id)",
        "institucion_id" not in schemas.SeccionCreate.model_fields,
    )
    comprobar(
        "MatriculaCreate NO pide persona_id ni institucion_id (vienen de la ruta/la persona)",
        "persona_id" not in schemas.MatriculaCreate.model_fields
        and "institucion_id" not in schemas.MatriculaCreate.model_fields,
    )
    comprobar(
        "NivelEducativoCreate SÍ pide institucion_id (no hay padre del que derivarlo)",
        "institucion_id" in schemas.NivelEducativoCreate.model_fields,
    )


def test_rutas_nuevas_no_colisionan_con_el_segmento_unico_existente():
    print("\nRuteo — las rutas nuevas no quedan atrapadas por GET/{institucion_id} o PATCH/{persona_id}")
    rutas = [(r.path, sorted(r.methods)) for r in superadmin_router.router.routes]
    nuevas = [
        "/personas/academico/niveles", "/personas/academico/niveles/{institucion_id}",
        "/personas/academico/grados", "/personas/academico/grados/{nivel_educativo_id}",
        "/personas/academico/secciones", "/personas/academico/secciones/{grado_id}",
        "/personas/{persona_id}/matricula", "/personas/{persona_id}/historial-academico",
        "/personas/por-codigo/{codigo_institucional}",
    ]
    faltantes = [r for r in nuevas if r not in [p for p, _ in rutas]]
    comprobar("Todas las rutas nuevas quedaron registradas", not faltantes, str(faltantes))
    # Ninguna ruta nueva tiene UN SOLO segmento — eso es lo que colisionaría
    # con GET /{institucion_id} o PATCH /{persona_id}, que capturan cualquier
    # string de un segmento antes de que FastAPI intente la ruta siguiente.
    de_un_segmento = [r for r in nuevas if r.strip("/").count("/") == 0]
    comprobar("Ninguna ruta nueva es de un solo segmento", not de_un_segmento, str(de_un_segmento))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — NÚCLEO DEL ESTUDIANTE")
    print("=" * 72)
    test_modelos_existen_y_tienen_las_columnas_esperadas()
    test_matricula_tiene_indice_unico_parcial()
    test_unicidad_por_institucion_no_global()
    test_esquemas_no_piden_institucion_id_donde_se_puede_derivar()
    test_rutas_nuevas_no_colisionan_con_el_segmento_unico_existente()

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
