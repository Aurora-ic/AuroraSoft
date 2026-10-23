"""Pruebas unitarias de los arreglos de la Fase 0 (B-1, B-2, B-3, B-4).

No necesitan base de datos ni servidor. Se ejecutan con el intérprete a secas
porque el proyecto todavía no tiene pytest instalado:

    python tests/test_fase0_unitario.py

Cada prueba reproduce el fallo concreto descrito en la auditoría y comprueba
que ya no ocurre.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

# Permite ejecutar el archivo directamente desde backend/ o desde backend/tests/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core.algoritmo import (  # noqa: E402
    ESCALA_MAXIMA_POR_DEFECTO,
    ESCALA_MINIMA_POR_DEFECTO,
    calcular_likert_generico,
    calcular_resultados,
    resolver_escala,
)
from modulos.educativo import models, schemas  # noqa: E402


# ----------------------------------------------------------------------
# Dobles de prueba mínimos
# ----------------------------------------------------------------------
class PruebaFalsa:
    """Imita un registro `Prueba` de SQLAlchemy: el atributo siempre existe
    aunque la columna esté en NULL. Ese era exactamente el motivo por el que
    `hasattr()` no servía como comprobación."""

    def __init__(self, escala_minima, escala_maxima, modo_calculo="likert_suma"):
        self.escala_minima = escala_minima
        self.escala_maxima = escala_maxima
        self.modo_calculo = modo_calculo
        self.nombre_tecnico = "PRUEBA-FALSA"


class ItemFalso:
    def __init__(self, id, es_inverso, escala_minima=None, escala_maxima=None):
        self.id = id
        self.es_inverso = es_inverso
        # 🆕 Escala PROPIA del ítem (auditoría de motor, 2026-10-13) — None
        # por defecto, igual que en el modelo real: calcular_likert_generico
        # debe usar la de la Prueba como respaldo en ese caso (ver los casos
        # existentes de este archivo, que no la fijan y siguen pasando).
        self.escala_minima = escala_minima
        self.escala_maxima = escala_maxima


class RespuestaFalsa:
    def __init__(self, pregunta_id, dimension, valor_raw):
        self.pregunta_id = pregunta_id
        self.dimension = dimension
        self.valor_raw = valor_raw


# ----------------------------------------------------------------------
# Infraestructura de aserciones
# ----------------------------------------------------------------------
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    estado = "PASA" if condicion else "FALLA"
    print(f"  [{estado}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ======================================================================
# B-1 — Crear campaña ya no pasa un kwarg inexistente al modelo
# ======================================================================
def test_b1_evaluacion_se_construye():
    print("\nB-1 · Creación de campañas")

    comprobar(
        "El modelo Evaluacion no declara 'mostrar_resultado_a_alumno'",
        not hasattr(models.Evaluacion, "mostrar_resultado_a_alumno"),
        "columna inexistente: nadie debe pasarla al constructor",
    )

    try:
        ev = models.Evaluacion(
            institucion_id=1,
            prueba_id=1,
            nombre_grupo="5to B",
            creador_id=1,
            fecha_fin=None,
        )
        comprobar("Evaluacion se instancia con los campos reales", ev.nombre_grupo == "5to B")
    except TypeError as exc:
        comprobar("Evaluacion se instancia con los campos reales", False, f"TypeError: {exc}")

    # El fallo original, para dejar constancia de que la causa está entendida
    try:
        models.Evaluacion(institucion_id=1, mostrar_resultado_a_alumno=False)
        comprobar("El kwarg fantasma sigue siendo inválido", False, "no lanzó TypeError")
    except TypeError:
        comprobar("El kwarg fantasma sigue siendo inválido", True, "TypeError esperado")


# ======================================================================
# B-2 — PruebaCreate admite institucion_id
# ======================================================================
def test_b2_prueba_create_acepta_institucion():
    print("\nB-2 · Creación de pruebas por psicólogo/admin")

    prueba = schemas.PruebaCreate(nombre_tecnico="PHQ-9", nombre_publico="Cuestionario")

    comprobar(
        "institucion_id está declarado y por defecto es None (prueba pública)",
        "institucion_id" in schemas.PruebaCreate.model_fields and prueba.institucion_id is None,
    )

    # Esto es literalmente lo que hace el router para un usuario no superadmin
    try:
        prueba.institucion_id = 7
        comprobar(
            "El router puede forzar la institución de la sesión",
            prueba.institucion_id == 7,
        )
    except ValueError as exc:
        comprobar("El router puede forzar la institución de la sesión", False, str(exc))

    comprobar(
        "institucion_id llega al modelo en model_dump()",
        prueba.model_dump().get("institucion_id") == 7,
    )


# ======================================================================
# B-3 — fecha_fin se conserva y se normaliza a UTC naive
# ======================================================================
def test_b3_fecha_fin():
    print("\nB-3 · Persistencia de fecha_fin")

    comprobar(
        "EvaluacionCreate declara fecha_fin",
        "fecha_fin" in schemas.EvaluacionCreate.model_fields,
    )

    sin_fecha = schemas.EvaluacionCreate(prueba_id=1, nombre_grupo="A", institucion_id=1)
    comprobar("fecha_fin es opcional (campaña sin caducidad)", sin_fecha.fecha_fin is None)

    naive = datetime(2026, 12, 1, 10, 30)
    con_fecha = schemas.EvaluacionCreate(
        prueba_id=1, nombre_grupo="A", institucion_id=1, fecha_fin=naive
    )
    comprobar("Una fecha naive se conserva intacta", con_fecha.fecha_fin == naive)

    # Peru es UTC-5: las 00:00 locales son las 05:00 UTC
    con_offset = schemas.EvaluacionCreate(
        prueba_id=1,
        nombre_grupo="A",
        institucion_id=1,
        fecha_fin="2026-12-01T00:00:00-05:00",
    )
    comprobar(
        "Una fecha con offset se convierte a UTC sin tzinfo",
        con_offset.fecha_fin == datetime(2026, 12, 1, 5, 0)
        and con_offset.fecha_fin.tzinfo is None,
        f"resultado: {con_offset.fecha_fin!r}",
    )

    # La comparación que hacen los candados debe funcionar sin TypeError
    try:
        caducada = con_offset.fecha_fin < datetime.utcnow()
        comprobar("El candado compara sin mezclar naive/aware", isinstance(caducada, bool))
    except TypeError as exc:
        comprobar("El candado compara sin mezclar naive/aware", False, str(exc))

    pasado = datetime.now(timezone.utc) - timedelta(days=1)
    vencida = schemas.EvaluacionCreate(
        prueba_id=1, nombre_grupo="A", institucion_id=1, fecha_fin=pasado
    )
    comprobar(
        "Una campaña con fecha pasada se evalúa como caducada",
        vencida.fecha_fin < datetime.utcnow(),
    )


# ======================================================================
# B-4 — Escalas NULL ya no revientan el cálculo
# ======================================================================
def test_b4_escalas_nulas():
    print("\nB-4 · Escala NULL en el motor de cálculo")

    comprobar(
        "resolver_escala() repone NULL con el respaldo documentado",
        resolver_escala(PruebaFalsa(None, None))
        == (ESCALA_MINIMA_POR_DEFECTO, ESCALA_MAXIMA_POR_DEFECTO),
    )
    comprobar(
        "resolver_escala() respeta una escala definida (1..5)",
        resolver_escala(PruebaFalsa(1, 5)) == (1, 5),
    )
    comprobar(
        "resolver_escala() repone solo el extremo que falta",
        resolver_escala(PruebaFalsa(None, 5)) == (ESCALA_MINIMA_POR_DEFECTO, 5),
    )
    comprobar("resolver_escala() tolera prueba=None", resolver_escala(None) == (0, 3))

    # El fallo original: escala NULL + ítem inverso -> TypeError
    items = [ItemFalso(1, False), ItemFalso(2, True)]
    respuestas = [RespuestaFalsa(1, 10, 3), RespuestaFalsa(2, 10, 0)]

    try:
        res = calcular_resultados("PRUEBA", respuestas, items, PruebaFalsa(None, None))
        comprobar(
            "Escala NULL + ítem inverso ya no lanza TypeError",
            res["puntajes_brutos"][10] == 6,
            f"puntaje {res['puntajes_brutos'][10]} (3 directo + 3 invertido)",
        )
    except TypeError as exc:
        comprobar("Escala NULL + ítem inverso ya no lanza TypeError", False, f"TypeError: {exc}")

    # Matemática de la inversión con escala real 1..5: (1+5)-2 = 4
    res_1a5 = calcular_resultados(
        "PRUEBA",
        [RespuestaFalsa(2, 20, 2)],
        [ItemFalso(2, True)],
        PruebaFalsa(1, 5),
    )
    comprobar(
        "Inversión correcta en escala 1..5: (1+5)-2 = 4",
        res_1a5["puntajes_brutos"][20] == 4,
        f"obtenido {res_1a5['puntajes_brutos'][20]}",
    )

    # Escala 0..3: (0+3)-1 = 2
    res_0a3 = calcular_resultados(
        "PRUEBA",
        [RespuestaFalsa(2, 30, 1)],
        [ItemFalso(2, True)],
        PruebaFalsa(0, 3),
    )
    comprobar(
        "Inversión correcta en escala 0..3: (0+3)-1 = 2",
        res_0a3["puntajes_brutos"][30] == 2,
        f"obtenido {res_0a3['puntajes_brutos'][30]}",
    )

    # 🆕 Auditoría de motor (sesión 2026-10-13): un ítem con escala PROPIA
    # distinta de la Prueba (ej. NICHQ Vanderbilt, que mezcla 0-3 y 1-5) debe
    # invertirse con SU escala, no la de la prueba completa. Item con
    # escala_minima/maxima=0/1 (como Hamilton #14) dentro de una Prueba con
    # escala 0-3: si se invirtiera con la escala de la prueba, (0+3)-1=2
    # (resultado erróneo); con la escala propia del ítem, (0+1)-1=0 (correcto).
    res_escala_propia = calcular_resultados(
        "PRUEBA",
        [RespuestaFalsa(2, 40, 1)],
        [ItemFalso(2, True, escala_minima=0, escala_maxima=1)],
        PruebaFalsa(0, 3),
    )
    comprobar(
        "Ítem con escala propia 0-1 se invierte con ESA escala, no con la 0-3 de la prueba: (0+1)-1 = 0",
        res_escala_propia["puntajes_brutos"][40] == 0,
        f"obtenido {res_escala_propia['puntajes_brutos'][40]} (0 = correcto, 2 = bug: usó la escala de la prueba)",
    )

    # Mismo caso pero SIN escala propia (None/None, el comportamiento de
    # siempre) — debe seguir cayendo en la escala de la Prueba, sin cambios.
    res_sin_escala_propia = calcular_resultados(
        "PRUEBA",
        [RespuestaFalsa(2, 41, 1)],
        [ItemFalso(2, True)],  # escala_minima/maxima=None -> respaldo de la Prueba
        PruebaFalsa(0, 3),
    )
    comprobar(
        "Ítem SIN escala propia sigue usando la escala de la Prueba (0+3)-1 = 2 — compatibilidad hacia atrás",
        res_sin_escala_propia["puntajes_brutos"][41] == 2,
        f"obtenido {res_sin_escala_propia['puntajes_brutos'][41]}",
    )

    # Blindaje de la función pública
    try:
        directo = calcular_likert_generico(
            [RespuestaFalsa(2, 40, 1)], [ItemFalso(2, True)], None, None
        )
        comprobar(
            "calcular_likert_generico() tolera None directo",
            directo["puntajes_brutos"][40] == 2,
        )
    except TypeError as exc:
        comprobar("calcular_likert_generico() tolera None directo", False, f"TypeError: {exc}")

    # modo_calculo NULL no debe desviar el flujo ni romperlo
    try:
        res_modo = calcular_resultados(
            "PRUEBA", [RespuestaFalsa(1, 50, 2)], [ItemFalso(1, False)],
            PruebaFalsa(0, 3, modo_calculo=None),
        )
        comprobar("modo_calculo NULL cae en likert_suma", res_modo["puntajes_brutos"][50] == 2)
    except Exception as exc:  # noqa: BLE001
        comprobar("modo_calculo NULL cae en likert_suma", False, f"{type(exc).__name__}: {exc}")

    # No se rompe el modo correcto/incorrecto que ya funcionaba
    res_ci = calcular_resultados(
        "ICAR", [RespuestaFalsa(1, 60, 1), RespuestaFalsa(2, 60, 0)],
        [ItemFalso(1, False), ItemFalso(2, False)],
        PruebaFalsa(0, 1, modo_calculo="correcto_incorrecto"),
    )
    comprobar("modo correcto_incorrecto sigue sumando aciertos", res_ci["puntajes_brutos"][60] == 1)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — FASE 0")
    print("=" * 72)

    test_b1_evaluacion_se_construye()
    test_b2_prueba_create_acepta_institucion()
    test_b3_fecha_fin()
    test_b4_escalas_nulas()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]

    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
