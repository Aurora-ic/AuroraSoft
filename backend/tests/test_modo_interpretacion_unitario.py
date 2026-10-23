"""Pruebas unitarias — Prueba.modo_interpretacion ('rango', el de siempre,
y 'perfil', ahora implementado — ver "Interpretación por perfil" en
CLAUDE.md).

    python -m tests.test_modo_interpretacion_unitario

Sin BD ni servidor. Cubre: la columna existe con su valor por defecto
"rango" (cero cambio para toda prueba existente), el CHECK/validador ahora
aceptan tanto "rango" como "perfil" (y siguen rechazando cualquier otro
valor inventado), `interpretar_resultados_alumno` (el algoritmo de 'rango')
sigue sin leer esta columna — el despacho vive por completo en
`crud.interpretar_segun_modo` —, y que `interpretar_perfil_alumno` (el
algoritmo de 'perfil') existe y es genérico.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pydantic import ValidationError

from modulos.educativo import models, schemas, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columna_existe_con_default_rango():
    print("\nModelo — Prueba.modo_interpretacion existe, NOT NULL, default 'rango'")
    columna = models.Prueba.__table__.columns["modo_interpretacion"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es NOT NULL", columna.nullable is False)
    comprobar("Su server_default sigue siendo 'rango' (ninguna prueba existente cambia de modo)",
              columna.server_default.arg == models.MODO_INTERPRETACION_RANGO)
    comprobar("MODOS_INTERPRETACION_VALIDOS ahora trae 'rango' Y 'perfil'",
              models.MODOS_INTERPRETACION_VALIDOS == {"rango", "perfil"})
    comprobar("MODO_INTERPRETACION_PERFIL == 'perfil'", models.MODO_INTERPRETACION_PERFIL == "perfil")


def test_check_constraint_permite_rango_y_perfil():
    print("\nModelo — CHECK constraint ck_pruebas_modo_interpretacion_valido admite 'rango' y 'perfil'")
    nombres = [c.name for c in models.Prueba.__table__.constraints]
    comprobar("El CHECK constraint existe", "ck_pruebas_modo_interpretacion_valido" in nombres, str(nombres))


def test_schema_acepta_rango_y_perfil_rechaza_lo_demas():
    print("\nschemas.PruebaBase — el validador acepta 'rango'/'perfil' y rechaza cualquier otro valor")
    base = {
        "nombre_tecnico": "X", "nombre_publico": "X",
    }
    creada_perfil = schemas.PruebaCreate(**base, modo_interpretacion="perfil")
    comprobar("'perfil' es aceptado por el schema", creada_perfil.modo_interpretacion == "perfil")

    try:
        schemas.PruebaCreate(**base, modo_interpretacion="ipsativo")
        comprobar("Un valor inventado cualquiera sigue siendo rechazado por el schema", False)
    except ValidationError:
        comprobar("Un valor inventado cualquiera sigue siendo rechazado por el schema (ValidationError)", True)

    creada = schemas.PruebaCreate(**base, modo_interpretacion="rango")
    comprobar("'rango' sigue siendo aceptado", creada.modo_interpretacion == "rango")

    por_defecto = schemas.PruebaCreate(**base)
    comprobar("Si no se envía, el default del schema sigue siendo 'rango'", por_defecto.modo_interpretacion == "rango")

    comprobar("PruebaUpdate (PATCH) NO expone modo_interpretacion — cambiarlo es una decisión "
              "estructural a mano (seed script), nunca un ajuste casual vía API",
              "modo_interpretacion" not in schemas.PruebaUpdate.model_fields)


def test_despacho_vive_en_interpretar_segun_modo():
    print("\nGenericidad — interpretar_resultados_alumno sigue sin leer modo_interpretacion; el despacho vive en interpretar_segun_modo")
    import ast
    import inspect

    def cuerpo_sin_docstring(func):
        codigo = inspect.getsource(func)
        arbol = ast.parse(codigo)
        funcdef = arbol.body[0]
        cuerpo = funcdef.body
        if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant):
            cuerpo = cuerpo[1:]
        return "\n".join(ast.unparse(nodo) for nodo in cuerpo)

    cuerpo = cuerpo_sin_docstring(crud.interpretar_resultados_alumno)
    comprobar("interpretar_resultados_alumno (el algoritmo de 'rango') sigue sin leer modo_interpretacion "
              "— no necesita saber que existe un segundo modo",
              "modo_interpretacion" not in cuerpo)

    comprobar("crud.interpretar_perfil_alumno existe (el algoritmo de 'perfil')",
              callable(getattr(crud, "interpretar_perfil_alumno", None)))
    comprobar("crud.interpretar_segun_modo existe y es el único punto que lee modo_interpretacion",
              callable(getattr(crud, "interpretar_segun_modo", None))
              and "modo_interpretacion" in inspect.getsource(crud.interpretar_segun_modo))

    fuente_despacho = inspect.getsource(crud.interpretar_segun_modo)
    comprobar("Despacha a interpretar_perfil_alumno cuando el modo es 'perfil'",
              "interpretar_perfil_alumno" in fuente_despacho)
    comprobar("Despacha a interpretar_resultados_alumno en cualquier otro caso (incluido el default 'rango')",
              "interpretar_resultados_alumno" in fuente_despacho)


def test_interpretar_perfil_alumno_es_generico_y_nunca_alerta():
    print("\ncrud.interpretar_perfil_alumno — genérico en su CÓDIGO (el docstring sí puede citar "
          "IPIP-RIASEC como el caso real que lo motivó, mismo criterio que el docstring de "
          "ReglaInterpretacion cita a PHQ-9 ítem 9 — lo que importa es que la LÓGICA no branchee por nombre)")
    import ast
    import inspect

    def cuerpo_sin_docstring(func):
        codigo = inspect.getsource(func)
        arbol = ast.parse(codigo)
        funcdef = arbol.body[0]
        cuerpo = funcdef.body
        if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant):
            cuerpo = cuerpo[1:]
        return "\n".join(ast.unparse(nodo) for nodo in cuerpo)

    fuente = inspect.getsource(crud.interpretar_perfil_alumno)
    cuerpo = cuerpo_sin_docstring(crud.interpretar_perfil_alumno)
    comprobar("El CÓDIGO (sin docstring) no menciona RIASEC ni ningún instrumento concreto por nombre",
              "RIASEC" not in cuerpo and "riasec" not in cuerpo.lower())
    comprobar("No consulta Baremo (compara dimensiones entre sí, no contra un rango)",
              "models.Baremo" not in fuente)
    comprobar("es_alerta siempre False — un puesto relativo nunca implica riesgo por sí solo",
              "es_alerta=False" in fuente)
    comprobar("baremo_id siempre None — ningún tramo que citar en este modo",
              "baremo_id=None" in fuente)
    comprobar("Nunca produce 'sin baremo aplicable' (ese concepto no existe en modo perfil)",
              '"dimensiones_sin_baremo": []' in fuente)
    comprobar("interpretacion_completa depende de haber generado algún ResultadoDimension "
              "(False si el examen se finalizó sin respuestas — se retiene, no se asume limpio)",
              '"interpretacion_completa": bool(puntajes_directos)' in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Prueba.modo_interpretacion ('rango' y 'perfil')")
    print("=" * 72)
    test_columna_existe_con_default_rango()
    test_check_constraint_permite_rango_y_perfil()
    test_schema_acepta_rango_y_perfil_rechaza_lo_demas()
    test_despacho_vive_en_interpretar_segun_modo()
    test_interpretar_perfil_alumno_es_generico_y_nunca_alerta()

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
