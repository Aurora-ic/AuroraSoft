"""Pruebas unitarias — Reglas de interpretación genéricas (item/dimensión/puntaje total).

    python -m tests.test_reglas_interpretacion_unitario

No necesitan la base de datos ni el servidor: ejercitan la lógica de fusión
(aplicar_reglas_a_diagnosticos) con objetos ORM en memoria y un `db` falso
que solo implementa add()/flush() como no-ops.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class DBFalso:
    """Duplica solo lo que aplicar_reglas_a_diagnosticos() necesita de una Session."""
    def add(self, obj):
        pass

    def flush(self):
        pass


# ==========================================
# MODELO
# ==========================================
def test_modelo_regla_interpretacion():
    print("\nModelos — ReglaInterpretacion: ámbitos y operadores controlados por CHECK, no texto libre")
    comprobar("AMBITOS_REGLA_VALIDOS trae item/dimension/puntaje_total",
              models.AMBITOS_REGLA_VALIDOS == {"item", "dimension", "puntaje_total"})
    comprobar("OPERADORES_REGLA_VALIDOS trae los 6 comparadores",
              models.OPERADORES_REGLA_VALIDOS == {">", ">=", "<", "<=", "==", "!="})
    nombres = [c.name for c in models.ReglaInterpretacion.__table__.constraints]
    for esperado in (
        "ck_reglas_interpretacion_ambito_valido",
        "ck_reglas_interpretacion_operador_valido",
        "ck_reglas_interpretacion_accion_valida",
        "ck_reglas_interpretacion_campos_segun_ambito",
    ):
        comprobar(f"CHECK constraint {esperado} existe", esperado in nombres, str(nombres))


def test_diagnostico_trae_trazabilidad():
    print("\nModelos — DiagnosticoAlumno guarda de dónde vino la alerta")
    for columna in ("alerta_por", "regla_activada_id"):
        comprobar(f"DiagnosticoAlumno.{columna} existe", columna in models.DiagnosticoAlumno.__table__.columns)
    comprobar("regla_activada_id es nullable (no toda alerta viene de una regla)",
              models.DiagnosticoAlumno.__table__.columns["regla_activada_id"].nullable)


def test_inscripcion_trae_reglas_con_error():
    print("\nModelos — Inscripcion.reglas_con_error es una señal DISTINTA de dimensiones_sin_baremo")
    comprobar("Inscripcion.reglas_con_error existe", "reglas_con_error" in models.Inscripcion.__table__.columns)
    comprobar("Inscripcion.dimensiones_sin_baremo sigue existiendo sin tocarse",
              "dimensiones_sin_baremo" in models.Inscripcion.__table__.columns)


# ==========================================
# OPERADORES
# ==========================================
def test_operadores_sin_eval():
    print("\ncrud._OPERADORES_REGLA — comparadores seguros, sin eval() de por medio")
    casos = [(">", 1, 0, True), (">", 0, 0, False), (">=", 0, 0, True),
             ("<", -1, 0, True), ("<=", 0, 0, True), ("==", 3, 3, True), ("!=", 3, 3, False)]
    for op, a, b, esperado in casos:
        comprobar(f"{a} {op} {b} == {esperado}", crud._OPERADORES_REGLA[op](a, b) == esperado)
    comprobar("Los 6 operadores del modelo están cubiertos",
              set(crud._OPERADORES_REGLA.keys()) == models.OPERADORES_REGLA_VALIDOS)


# ==========================================
# PRIORIDAD: la regla enciende, nunca apaga
# ==========================================
def test_regla_no_apaga_alerta_de_baremo():
    print("\naplicar_reglas_a_diagnosticos — un baremo que YA alertó nunca se apaga por una regla")
    diag = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=10, nivel="Alto", es_alerta=True, alerta_por="baremo")
    resultado_reglas = {"disparadas": [], "con_error": []}
    salida = crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=1, diagnosticos=[diag], resultado_reglas=resultado_reglas)
    comprobar("Sin reglas disparadas, el diagnóstico no cambia", salida[0].es_alerta is True and salida[0].alerta_por == "baremo")


def test_regla_enciende_alerta_apagada_por_baremo():
    print("\naplicar_reglas_a_diagnosticos — Caso B: baremo sin alerta + regla disparada -> se enciende")
    diag = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=10, nivel="Bajo", es_alerta=False, alerta_por=None)
    resultado_reglas = {"disparadas": [{"dimension_id": 10, "regla_id": 99, "descripcion": "ítem 9"}], "con_error": []}
    crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=1, diagnosticos=[diag], resultado_reglas=resultado_reglas)
    comprobar("es_alerta pasa a True", diag.es_alerta is True)
    comprobar("alerta_por queda en 'regla' (el baremo no había alertado)", diag.alerta_por == "regla")
    comprobar("regla_activada_id apunta a la regla que disparó", diag.regla_activada_id == 99)


def test_regla_y_baremo_coinciden_sin_duplicar():
    print("\naplicar_reglas_a_diagnosticos — Caso D: baremo Y regla alertan -> una sola alerta, ambos orígenes trazados")
    diag = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=10, nivel="Severo", es_alerta=True, alerta_por="baremo")
    resultado_reglas = {"disparadas": [{"dimension_id": 10, "regla_id": 7, "descripcion": "ítem 9"}], "con_error": []}
    salida = crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=1, diagnosticos=[diag], resultado_reglas=resultado_reglas)
    comprobar("Sigue habiendo un solo diagnóstico (no se duplicó la fila)", len(salida) == 1)
    comprobar("es_alerta sigue True (no se apaga ni se re-dispara dos veces)", salida[0].es_alerta is True)
    comprobar("alerta_por registra AMBOS orígenes", salida[0].alerta_por == "baremo,regla")


def test_regla_puntaje_total_aplica_a_todas_las_dimensiones():
    print("\naplicar_reglas_a_diagnosticos — una regla de ámbito 'puntaje_total' (dimension_id=None) alerta TODAS las dimensiones de la prueba")
    d1 = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=1, nivel="Bajo", es_alerta=False, alerta_por=None)
    d2 = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=2, nivel="Bajo", es_alerta=False, alerta_por=None)
    resultado_reglas = {"disparadas": [{"dimension_id": None, "regla_id": 5, "descripcion": "total alto"}], "con_error": []}
    crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=1, diagnosticos=[d1, d2], resultado_reglas=resultado_reglas)
    comprobar("Ambas dimensiones quedan alertadas", d1.es_alerta is True and d2.es_alerta is True)


def test_regla_crea_diagnostico_si_no_habia_por_falta_de_baremo():
    print("\naplicar_reglas_a_diagnosticos — una regla puede alertar una dimensión que quedó SIN diagnóstico por falta de baremo")
    resultado_reglas = {"disparadas": [{"dimension_id": 77, "regla_id": 3, "descripcion": "regla huérfana"}], "con_error": []}
    salida = crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=55, diagnosticos=[], resultado_reglas=resultado_reglas)
    comprobar("Se crea un DiagnosticoAlumno nuevo para esa dimensión", len(salida) == 1 and salida[0].dimension_id == 77)
    comprobar("Queda marcado como alerta por regla, trazado", salida[0].es_alerta is True and salida[0].alerta_por == "regla" and salida[0].regla_activada_id == 3)


def test_sin_reglas_disparadas_no_toca_nada():
    print("\naplicar_reglas_a_diagnosticos — Caso E: sin reglas activas, el comportamiento es exactamente el de antes")
    diag = models.DiagnosticoAlumno(inscripcion_id=1, dimension_id=1, nivel="Bajo", es_alerta=False, alerta_por=None)
    resultado_reglas = {"disparadas": [], "con_error": []}
    salida = crud.aplicar_reglas_a_diagnosticos(DBFalso(), inscripcion_id=1, diagnosticos=[diag], resultado_reglas=resultado_reglas)
    comprobar("Devuelve la MISMA lista de diagnósticos, sin alteraciones", salida == [diag] and diag.es_alerta is False and diag.alerta_por is None)


# ==========================================
# 🆕 ÁMBITO 'item' — INVERSIÓN (auditoría de motor, sesión 2026-10-13)
# ==========================================
class _DBFalsaPorModelo:
    """A diferencia de DBFalso (solo add/flush, sin query) y de
    _FakeQuerySecuencia (otros archivos — una cola única sin importar el
    modelo), este fake resuelve .query(Modelo) SEGÚN el modelo pedido: hace
    falta aquí porque evaluar_reglas_interpretacion consulta 4 modelos
    DISTINTOS (ReglaInterpretacion/Pregunta/RespuestaAlumno/Prueba) dentro
    del mismo ciclo, no una secuencia fija de llamadas al mismo modelo."""
    def __init__(self, respuestas_por_modelo):
        self._respuestas = respuestas_por_modelo  # {Modelo: valor_o_lista}
        self._modelo_actual = None

    def query(self, modelo, *a, **k):
        self._modelo_actual = modelo
        return self

    def filter(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def all(self):
        return self._respuestas.get(self._modelo_actual, [])

    def first(self):
        return self._respuestas.get(self._modelo_actual)


def test_regla_item_invertido_usa_valor_corregido_no_crudo():
    print("\ncrud.evaluar_reglas_interpretacion — ámbito 'item' sobre un ítem INVERTIDO compara el valor CORREGIDO, no el crudo")
    # Ítem estilo Hamilton #14 ("¿Le encuentra sentido a la vida?"): escala
    # propia 0-1, es_inverso=True. "No"=raw 0 es la respuesta PREOCUPANTE
    # (debería poder disparar una regla de seguridad); "Sí"=raw 1 es la sana.
    pregunta = models.Pregunta(id=14, prueba_id=1, dimension_id=1, es_inverso=True,
                                escala_minima=0, escala_maxima=1)
    prueba = models.Prueba(id=1, escala_minima=0, escala_maxima=3)
    respuesta = models.RespuestaAlumno(inscripcion_id=1, pregunta_id=14, puntaje_obtenido=0)  # "No"
    regla = models.ReglaInterpretacion(
        id=1, prueba_id=1, ambito=models.AMBITO_ITEM, pregunta_id=14,
        operador=">", valor_comparacion=0, accion=models.ACCION_ES_ALERTA, activa=True,
    )
    db = _DBFalsaPorModelo({
        models.ReglaInterpretacion: [regla],
        models.Pregunta: pregunta,
        models.RespuestaAlumno: respuesta,
        models.Prueba: prueba,
    })

    resultado = crud.evaluar_reglas_interpretacion(db, inscripcion_id=1, prueba_id=1)
    comprobar(
        "Antes del fix: raw=0 > 0 es False -> NO disparaba (la respuesta preocupante no alertaba). "
        "Con el fix: invertido=(0+1)-0=1 > 0 es True -> SÍ dispara",
        len(resultado["disparadas"]) == 1 and resultado["disparadas"][0]["regla_id"] == 1,
        detalle=str(resultado),
    )
    comprobar("No queda ninguna regla con_error", resultado["con_error"] == [], detalle=str(resultado["con_error"]))


def test_regla_item_invertido_usa_escala_de_la_pregunta_no_de_la_prueba():
    print("\ncrud.evaluar_reglas_interpretacion — la inversión usa la escala PROPIA del ítem, no la de la Prueba completa")
    # Mismo ítem (escala propia 0-1), pero ahora con raw=1 ("Sí", sana) y
    # valor_comparacion=1 con '>' — un caso donde invertir con la escala
    # CORRECTA (0-1 -> invertido=0) y con la escala INCORRECTA de la prueba
    # (0-4 -> invertido=3) producen resultados DISTINTOS, para que el test
    # realmente discrimine cuál escala se usó (no solo que SE invirtió).
    pregunta = models.Pregunta(id=14, prueba_id=1, dimension_id=1, es_inverso=True,
                                escala_minima=0, escala_maxima=1)
    prueba = models.Prueba(id=1, escala_minima=0, escala_maxima=4)  # deliberadamente distinta
    respuesta = models.RespuestaAlumno(inscripcion_id=1, pregunta_id=14, puntaje_obtenido=1)  # "Sí"
    regla = models.ReglaInterpretacion(
        id=2, prueba_id=1, ambito=models.AMBITO_ITEM, pregunta_id=14,
        operador=">", valor_comparacion=1, accion=models.ACCION_ES_ALERTA, activa=True,
    )
    db = _DBFalsaPorModelo({
        models.ReglaInterpretacion: [regla],
        models.Pregunta: pregunta,
        models.RespuestaAlumno: respuesta,
        models.Prueba: prueba,
    })

    resultado = crud.evaluar_reglas_interpretacion(db, inscripcion_id=1, prueba_id=1)
    comprobar(
        "Con la escala de la PREGUNTA (0-1): invertido=(0+1)-1=0, 0>1 es False -> no dispara. "
        "Si usara la escala de la PRUEBA (0-4) por error: invertido=(0+4)-1=3, 3>1 sería True -> SÍ dispararía (bug)",
        len(resultado["disparadas"]) == 0,
        detalle=str(resultado),
    )


# ==========================================
# GENERICIDAD: el motor no conoce nombres de pruebas
# ==========================================
def test_motor_no_menciona_phq9():
    print("\nGenericidad — el CÓDIGO (sin docstrings/comentarios) de las funciones no menciona 'PHQ' ni compara nombres de prueba")
    import ast
    import inspect

    def cuerpo_sin_docstring(func):
        codigo = inspect.getsource(func)
        arbol = ast.parse(codigo)
        funcdef = arbol.body[0]
        cuerpo = funcdef.body
        # ast.get_docstring detecta y permite saltar el primer nodo si es la docstring
        if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant):
            cuerpo = cuerpo[1:]
        return "\n".join(ast.unparse(nodo) for nodo in cuerpo)

    cuerpo_evaluar = cuerpo_sin_docstring(crud.evaluar_reglas_interpretacion)
    cuerpo_aplicar = cuerpo_sin_docstring(crud.aplicar_reglas_a_diagnosticos)
    comprobar("evaluar_reglas_interpretacion (sin docstring) no contiene 'PHQ'", "PHQ" not in cuerpo_evaluar.upper())
    comprobar("aplicar_reglas_a_diagnosticos (sin docstring) no contiene 'PHQ'", "PHQ" not in cuerpo_aplicar.upper())
    comprobar("evaluar_reglas_interpretacion no compara prueba.nombre_tecnico",
              "nombre_tecnico" not in cuerpo_evaluar)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — REGLAS DE INTERPRETACIÓN GENÉRICAS")
    print("=" * 72)
    test_modelo_regla_interpretacion()
    test_diagnostico_trae_trazabilidad()
    test_inscripcion_trae_reglas_con_error()
    test_operadores_sin_eval()
    test_regla_no_apaga_alerta_de_baremo()
    test_regla_enciende_alerta_apagada_por_baremo()
    test_regla_y_baremo_coinciden_sin_duplicar()
    test_regla_puntaje_total_aplica_a_todas_las_dimensiones()
    test_regla_crea_diagnostico_si_no_habia_por_falta_de_baremo()
    test_sin_reglas_disparadas_no_toca_nada()
    test_regla_item_invertido_usa_valor_corregido_no_crudo()
    test_regla_item_invertido_usa_escala_de_la_pregunta_no_de_la_prueba()
    test_motor_no_menciona_phq9()

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
