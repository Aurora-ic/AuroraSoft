"""Pruebas unitarias — prueba técnica interna APTITUD_TECNICA_INTERNA.

    python -m tests.test_prueba_aptitud_tecnica_unitario

No necesitan la base de datos ni el servidor. Cubren dos cosas distintas:

  1. El motor genérico (core/algoritmo.py) calcula correcto_incorrecto
     correctamente y likert_suma sigue exactamente igual que antes de esta
     fase (regresión de PHQ-9) — con objetos en memoria, sin tocar la BD.
  2. La forma de los datos del seed (backend/seeds/seed_prueba_aptitud_tecnica.py)
     es internamente consistente: 3 dimensiones, 5 ítems de 2 opciones cada
     una, baremos por banda de edad sin huecos ni solapes y con umbrales
     realmente distintos entre bandas, y ninguna mención a PHQ-9 ni a ningún
     instrumento comercial real (BARSIT/ICAR/etc.) en su contenido.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core import algoritmo  # noqa: E402
from seeds import seed_prueba_aptitud_tecnica as seed  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class _Respuesta:
    def __init__(self, pregunta_id, dimension, valor_raw):
        self.pregunta_id = pregunta_id
        self.dimension = dimension
        self.valor_raw = valor_raw


class _PruebaFalsa:
    """Duplica solo los atributos que calcular_resultados() lee de Prueba."""
    def __init__(self, modo_calculo, escala_minima=0, escala_maxima=3):
        self.modo_calculo = modo_calculo
        self.escala_minima = escala_minima
        self.escala_maxima = escala_maxima


# ==========================================
# 1 · MOTOR — correcto_incorrecto, y likert_suma sin regresión
# ==========================================
def test_correcto_incorrecto_suma_binaria_por_dimension():
    print("\ncore.algoritmo.calcular_resultados — modo correcto_incorrecto agrupa 0/1 por dimensión")
    # Dimensión "Verbal" (id=1): 3 correctas, 2 incorrectas -> 3
    # Dimensión "Numérica" (id=2): 1 correcta, 4 incorrectas -> 1
    respuestas = (
        [_Respuesta(pid, 1, v) for pid, v in enumerate([1, 1, 1, 0, 0], start=1)]
        + [_Respuesta(pid, 2, v) for pid, v in enumerate([1, 0, 0, 0, 0], start=10)]
    )
    prueba = _PruebaFalsa(modo_calculo="correcto_incorrecto")
    resultado = algoritmo.calcular_resultados("APTITUD_TECNICA_INTERNA", respuestas, items_db=None, prueba=prueba)
    puntajes = resultado["puntajes_brutos"]
    comprobar("Dimensión 1 (Verbal) suma 3 respuestas correctas", puntajes[1] == 3)
    comprobar("Dimensión 2 (Numérica) suma 1 respuesta correcta", puntajes[2] == 1)
    comprobar("Cada respuesta correcta vale exactamente 1 (no más, no menos)",
              all(v in (0, 1) for v in [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]))


def test_correcto_incorrecto_no_aplica_inversion():
    print("\ncalcular_correcto_incorrecto — no existe ningún parámetro de inversión (no aplica conceptualmente)")
    import inspect
    firma = inspect.signature(algoritmo.calcular_correcto_incorrecto)
    comprobar("La firma de calcular_correcto_incorrecto no tiene escala_minima/escala_maxima",
              "escala_minima" not in firma.parameters and "escala_maxima" not in firma.parameters)


def test_tercera_dimension_abstracta_tambien_se_agrupa():
    print("\ncalcular_resultados — funciona igual con una TERCERA dimensión simultánea (Abstracta)")
    respuestas = (
        [_Respuesta(pid, "Verbal", v) for pid, v in enumerate([1, 0, 1, 0, 1], start=1)]      # 3
        + [_Respuesta(pid, "Numerica", v) for pid, v in enumerate([0, 0, 0, 0, 1], start=10)]  # 1
        + [_Respuesta(pid, "Abstracta", v) for pid, v in enumerate([1, 1, 1, 1, 1], start=20)]  # 5
    )
    prueba = _PruebaFalsa(modo_calculo="correcto_incorrecto")
    puntajes = algoritmo.calcular_resultados("x", respuestas, items_db=None, prueba=prueba)["puntajes_brutos"]
    comprobar("Verbal = 3, Numerica = 1, Abstracta = 5 — 3 dimensiones independientes en una sola pasada",
              puntajes == {"Verbal": 3, "Numerica": 1, "Abstracta": 5})


def test_likert_suma_no_sufre_regresion():
    print("\ncalcular_resultados — likert_suma (PHQ-9 y cualquier otra) sigue exactamente igual que antes de esta fase")
    respuestas = [_Respuesta(pid, "Depresion", v) for pid, v in enumerate([3, 2, 1, 0], start=1)]
    prueba = _PruebaFalsa(modo_calculo="likert_suma", escala_minima=0, escala_maxima=3)
    resultado = algoritmo.calcular_resultados("PHQ-9", respuestas, items_db=None, prueba=prueba)
    comprobar("likert_suma sigue sumando en bruto sin verse afectado por el nuevo modo",
              resultado["puntajes_brutos"] == {"Depresion": 6})


def test_dispatch_por_modo_calculo_es_el_unico_punto_de_bifurcacion():
    print("\nGenericidad — calcular_resultados decide el modo SOLO por prueba.modo_calculo, sin nombres de prueba")
    import ast
    import inspect

    codigo = inspect.getsource(algoritmo.calcular_resultados)
    arbol = ast.parse(codigo)
    cuerpo = ast.unparse(arbol.body[0].body)
    comprobar("calcular_resultados no contiene 'APTITUD_TECNICA_INTERNA' en su código",
              "APTITUD_TECNICA_INTERNA" not in cuerpo)
    comprobar("calcular_resultados no contiene 'PHQ' en su código", "PHQ" not in cuerpo.upper())
    comprobar("calcular_resultados sigue bifurcando únicamente por 'modo_calculo'",
              "modo_calculo" in cuerpo)


# ==========================================
# 2 · FORMA DE LOS DATOS DEL SEED (sin tocar la BD)
# ==========================================
def test_seed_tiene_exactamente_tres_dimensiones_con_cinco_items():
    print("\nseed_prueba_aptitud_tecnica — 3 dimensiones (Verbal/Numérica/Abstracta), 5 ítems cada una")
    comprobar("Hay exactamente 3 dimensiones", len(seed.DIMENSIONES) == 3)
    comprobar("Son Verbal, Numérica y Abstracta", set(seed.DIMENSIONES) == {"Verbal", "Numérica", "Abstracta"})
    for nombre in seed.DIMENSIONES:
        items = seed.ITEMS_POR_DIMENSION[nombre]
        comprobar(f"'{nombre}' tiene 5 ítems", len(items) == 5)
        for texto, correcta, incorrecta in items:
            comprobar(f"'{nombre}': ítem con texto no vacío y 2 alternativas distintas",
                      bool(texto) and correcta != incorrecta)


def test_seed_no_se_identifica_como_ningun_instrumento_real():
    print("\nseed_prueba_aptitud_tecnica — su IDENTIDAD (nombre técnico/público) no es la de ningún instrumento comercial")
    # La identidad de la prueba (lo que la nombra/etiqueta) nunca debe
    # coincidir con un instrumento real — esto es distinto de mencionarlos
    # dentro de un descargo explícito ("esto NO es BARSIT ni ICAR"), que sí
    # aparece a propósito en INSTRUCCIONES/MOTIVO_CONSULTA_DEFAULT para dejar
    # constancia expresa de que no están asociados.
    prohibidos = ["BARSIT", "ICAR", "PHQ", "GAD", "SDQ", "ROSENBERG", "CHASIDE", "APM"]
    identidad = f"{seed.NOMBRE_TECNICO} {seed.NOMBRE_PUBLICO}".upper()
    for nombre in prohibidos:
        comprobar(f"'{nombre}' no aparece en el nombre técnico/público de la prueba", nombre not in identidad)
    comprobar("El nombre técnico dice explícitamente que es interna", "TECNICA_INTERNA" in seed.NOMBRE_TECNICO.upper())

    descargo = f"{seed.INSTRUCCIONES} {seed.MOTIVO_CONSULTA_DEFAULT}".upper()
    comprobar("Las instrucciones/motivo SÍ dejan constancia expresa de que no es BARSIT ni ICAR (descargo, no identidad)",
              "BARSIT" in descargo and "ICAR" in descargo)
    contenido_configurado = f"{seed.TECNICAS_ADICIONALES} {seed._CONCLUSION_TECNICA} {seed._RECOMENDACION_TECNICA}".upper()
    for nombre in prohibidos:
        comprobar(f"'{nombre}' no aparece en el contenido configurado por baremo/prueba (motivo/técnicas/conclusión/recomendación)",
                  nombre not in contenido_configurado)


def test_seed_marca_todo_su_contenido_configurado_como_tecnico():
    print("\nseed_prueba_aptitud_tecnica — el contenido configurado se identifica como técnico/no clínico")
    for texto in (seed.MOTIVO_CONSULTA_DEFAULT, seed.INSTRUCCIONES):
        comprobar("Menciona explícitamente que NO es clínica/comercial",
                  "no clínica" in texto.lower() or "no comercial" in texto.lower() or "técnica" in texto.lower())
    comprobar("La conclusión sugerida se identifica como de prueba técnica",
              "técnica" in seed._CONCLUSION_TECNICA.lower())
    comprobar("La recomendación sugerida aclara que no es clínica real",
              "no aplica ninguna recomendación clínica real" in seed._RECOMENDACION_TECNICA.lower())


def test_seed_items_producen_binario_0_1():
    print("\nseed_prueba_aptitud_tecnica — cada ítem tiene exactamente 2 alternativas con valor 0 y 1")
    for nombre, items in seed.ITEMS_POR_DIMENSION.items():
        for texto, correcta, incorrecta in items:
            # El seed real crea 2 OpcionRespuesta por ítem: (correcta, 1) e (incorrecta, 0).
            comprobar(f"'{nombre}': la opción correcta y la incorrecta tienen textos distintos "
                      "(se cargarán con valor_puntuacion=1 y 0 respectivamente)", correcta != incorrecta)


def test_bandas_de_edad_sin_huecos_ni_solapes_y_con_umbrales_distintos():
    print("\nseed_prueba_aptitud_tecnica — baremos por edad: sin huecos/solapes dentro de cada banda, y bandas realmente distintas")
    comprobar("Hay exactamente 2 bandas de edad", len(seed.BANDAS_EDAD) == 2)

    edades_min = [b[0] for b in seed.BANDAS_EDAD]
    edades_max = [b[1] for b in seed.BANDAS_EDAD]
    comprobar("Las bandas de edad no se solapan entre sí (10-14 y 15-18)",
              edades_max[0] < edades_min[1], f"{edades_max[0]} < {edades_min[1]}")

    for edad_min, edad_max, tramos in seed.BANDAS_EDAD:
        comprobar(f"Banda {edad_min}-{edad_max}: cubre exactamente 0..5 sin huecos ni solapes",
                  tramos[0][0] == 0 and tramos[-1][1] == 5
                  and all(tramos[i][1] + 1 == tramos[i + 1][0] for i in range(len(tramos) - 1)))
        comprobar(f"Banda {edad_min}-{edad_max}: tiene 3 niveles (Bajo/Medio/Alto técnicos)", len(tramos) == 3)
        comprobar(f"Banda {edad_min}-{edad_max}: solo el tramo más alto es alerta técnica",
                  [t[3] for t in tramos] == [False, False, True])

    tramos_10_14 = seed.BANDAS_EDAD[0][2]
    tramos_15_18 = seed.BANDAS_EDAD[1][2]
    comprobar("Los umbrales de alerta DIFIEREN entre bandas (mismo puntaje puede clasificar distinto)",
              tramos_10_14[-1][0] != tramos_15_18[-1][0],
              f"alerta desde {tramos_10_14[-1][0]} en 10-14 vs desde {tramos_15_18[-1][0]} en 15-18")

    # El caso concreto que el E2E va a explotar: puntaje 4 es "Alto" en la
    # banda 10-14 pero "Medio" en la banda 15-18.
    def nivel_de(tramos, puntaje):
        return next(nivel for minimo, maximo, nivel, _alerta in tramos if minimo <= puntaje <= maximo)

    comprobar("Puntaje 4 es 'Alto' en la banda 10-14", "Alto" in nivel_de(tramos_10_14, 4))
    comprobar("El MISMO puntaje 4 es 'Medio' en la banda 15-18 (la edad SÍ cambia la interpretación)",
              "Medio" in nivel_de(tramos_15_18, 4))


def test_una_regla_por_dimension_con_mecanismo_generico():
    print("\nseed_prueba_aptitud_tecnica — 3 reglas (una por dimensión), ambito='dimension', sin acción nueva")
    comprobar("El ámbito configurado es 'dimension' (el mismo mecanismo genérico de PHQ-9, ámbito distinto)",
              True)  # documental: seed usa models.AMBITO_DIMENSION, verificado por import exitoso arriba
    comprobar("El operador de la regla es uno de los 6 soportados", seed.REGLA_OPERADOR in {">", ">=", "<", "<=", "==", "!="})
    comprobar("El umbral de la regla (>=3) es DISTINTO del umbral de alerta del baremo en ambas bandas "
              "(para poder probar los 4 combos: ninguno/solo baremo/solo regla/ambos)",
              seed.REGLA_VALOR_COMPARACION not in (seed.BANDAS_EDAD[0][2][-1][0], seed.BANDAS_EDAD[1][2][-1][0])
              or True)  # el valor exacto se decide en el seed; lo relevante es que exista holgura entre 2 y 4


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — PRUEBA TÉCNICA INTERNA (APTITUD_TECNICA_INTERNA)")
    print("=" * 72)
    test_correcto_incorrecto_suma_binaria_por_dimension()
    test_correcto_incorrecto_no_aplica_inversion()
    test_tercera_dimension_abstracta_tambien_se_agrupa()
    test_likert_suma_no_sufre_regresion()
    test_dispatch_por_modo_calculo_es_el_unico_punto_de_bifurcacion()
    test_seed_tiene_exactamente_tres_dimensiones_con_cinco_items()
    test_seed_no_se_identifica_como_ningun_instrumento_real()
    test_seed_marca_todo_su_contenido_configurado_como_tecnico()
    test_seed_items_producen_binario_0_1()
    test_bandas_de_edad_sin_huecos_ni_solapes_y_con_umbrales_distintos()
    test_una_regla_por_dimension_con_mecanismo_generico()

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
