"""
⚠️ ESTO NO ES UN INSTRUMENTO PSICOMÉTRICO REAL. ⚠️

Carga el catálogo PÚBLICO (institucion_id=None) de "APTITUD_TECNICA_INTERNA":
una prueba TÉCNICA, INTERNA, de INGENIERÍA, creada exclusivamente para
demostrar que el motor genérico de AuroraSoft (core/algoritmo.py + Baremo +
ReglaInterpretacion + el informe profesional) funciona correctamente con un
segundo modo de cálculo (`correcto_incorrecto`) y con más de una dimensión
real, ANTES de cargar cualquier instrumento comercial (BARSIT, ICAR, SDQ,
GAD-7, etc.).

Esta prueba:
  - NO es clínica.
  - NO es comercial.
  - NO es psicométrica (sus "niveles" y "baremos" son clasificaciones
    técnicas inventadas para el test, no normas poblacionales reales).
  - NO está asociada a BARSIT, ICAR, ni a ningún instrumento real. Sus ítems
    son originales, redactados solo para tener contenido variado y
    verificable — no están copiados ni adaptados de ningún test existente.
  - NO debe usarse jamás para evaluar estudiantes reales ni para producir
    ningún informe que se entregue como si fuera un resultado psicológico.

Estructura (ver CLAUDE.md "NUEVA FASE — SELECCIÓN DE LA SEGUNDA PRUEBA" y el
encargo de esta fase):
  - modo_calculo = "correcto_incorrecto" (el motor genérico nunca lo había
    ejercitado con datos reales antes de esta fase).
  - 3 dimensiones (Verbal, Numérica, Abstracta), 5 ítems cada una, cada ítem
    con 2 alternativas (una correcta=1, una incorrecta=0). Sin ítems
    inversos: la inversión no aplica conceptualmente a corrección objetiva.
  - Baremos por TRAMO DE EDAD (dos bandas, 10-14 y 15-18) con umbrales
    DISTINTOS entre bandas para cada dimensión — así un mismo puntaje directo
    puede clasificar distinto según la edad, ejercitando de verdad el filtro
    `edad_min`/`edad_max` de `interpretar_resultados_alumno` (con PHQ-9 ese
    filtro nunca se activa: sus baremos son unisex y de cualquier edad).
  - 3 `ReglaInterpretacion` (una por dimensión, ambito="dimension"),
    cargadas exactamente con el mismo mecanismo genérico que ya usa la regla
    del ítem 9 de PHQ-9 — ninguna lógica nueva en el motor.

Es idempotente y aditivo, con el mismo patrón que seed_phq9.py: si la prueba
ya existe, no se sobrescribe nada que ya esté cargado; solo se completan
piezas que falten (útil si una corrida anterior fue parcial).

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_prueba_aptitud_tecnica
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de Prueba/ReglaInterpretacion)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de Prueba)
from modulos.educativo import models

NOMBRE_TECNICO = "APTITUD_TECNICA_INTERNA"

NOMBRE_PUBLICO = (
    "Prueba Técnica Interna de Validación del Motor — NO CLÍNICA, NO COMERCIAL"
)

INSTRUCCIONES = (
    "Esta es una prueba TÉCNICA INTERNA de AuroraSoft, usada exclusivamente "
    "para validar el funcionamiento del motor de cálculo, baremos, reglas de "
    "interpretación e informes con múltiples dimensiones. No mide ninguna "
    "aptitud real, no corresponde a ningún instrumento psicométrico "
    "comercial (no es BARSIT, ICAR, ni ningún otro test real) y sus "
    "resultados no tienen ningún valor clínico. Responda cada ítem eligiendo "
    "la alternativa que considere correcta."
)

MOTIVO_CONSULTA_DEFAULT = (
    "Aplicación de una prueba TÉCNICA INTERNA de AuroraSoft para validar el "
    "motor genérico de cálculo, baremos por edad, reglas de interpretación "
    "simultáneas e informe multidimensional, antes de cargar cualquier "
    "instrumento psicométrico comercial. Este contenido es de validación de "
    "ingeniería, no una evaluación clínica real."
)
TECNICAS_ADICIONALES = "Validación técnica interna del motor (sin valor clínico)"

# (texto_pregunta, texto_opcion_correcta, texto_opcion_incorrecta)
# Ítems originales, redactados para esta fase — no copiados ni adaptados de
# ningún instrumento real.
ITEMS_POR_DIMENSION = {
    "Verbal": [
        ("Selecciona la palabra que es sinónimo de 'RÁPIDO'.", "Veloz", "Lento"),
        ("Selecciona la palabra que es antónimo de 'ALTO'.", "Bajo", "Grande"),
        ("PERRO es a LADRAR como GATO es a ___.", "Maullar", "Nadar"),
        ("Selecciona la palabra que NO pertenece al grupo: manzana, plátano, silla, naranja.", "Silla", "Plátano"),
        ("Selecciona el sinónimo de 'CONTENTO'.", "Feliz", "Triste"),
    ],
    "Numérica": [
        ("¿Cuánto es 4 + 5?", "9", "8"),
        ("En la secuencia 2, 4, 6, 8, ¿qué número sigue?", "10", "12"),
        ("¿Cuánto es 9 - 3?", "6", "5"),
        ("¿Cuál es el doble de 7?", "14", "16"),
        ("En la secuencia 1, 3, 5, 7, ¿qué número sigue?", "9", "10"),
    ],
    "Abstracta": [
        ("Si todas las figuras del grupo A son de color gris y esta figura pertenece al grupo A, ¿de qué color es?", "Gris", "Blanco"),
        ("¿Qué figura sigue en la secuencia: círculo, cuadrado, círculo, cuadrado, ___?", "Círculo", "Triángulo"),
        ("Hay 6 triángulos y se agrupan de dos en dos. ¿Cuántos grupos se forman?", "3", "4"),
        ("¿Cuál figura no pertenece al grupo, si todas menos una tienen 4 lados: cuadrado, rectángulo, círculo, rombo?", "Círculo", "Rombo"),
        ("Si la regla de la secuencia es 'sumar 3' y empieza en 1 (1, 4, 7, ...), ¿cuál es el tercer número?", "7", "10"),
    ],
}
DIMENSIONES = list(ITEMS_POR_DIMENSION.keys())

# Dos bandas de edad con UMBRALES DISTINTOS a propósito, para comprobar que
# interpretar_resultados_alumno() realmente filtra por edad_min/edad_max
# (con 5 ítems por dimensión, el puntaje directo va de 0 a 5).
# (edad_min, edad_max, [(minimo, maximo, nivel, es_alerta), ...])
BANDAS_EDAD = [
    (10, 14, [
        (0, 1, "Bajo (clasificación técnica)", False),
        (2, 3, "Medio (clasificación técnica)", False),
        (4, 5, "Alto (clasificación técnica)", True),
    ]),
    (15, 18, [
        (0, 2, "Bajo (clasificación técnica)", False),
        (3, 4, "Medio (clasificación técnica)", False),
        (5, 5, "Alto (clasificación técnica)", True),
    ]),
]

# Umbral de la ReglaInterpretacion por dimensión — deliberadamente distinto
# del umbral de alerta del baremo en cada banda, para poder ejercitar los 4
# combos (ni baremo ni regla / solo baremo / solo regla / ambos) con el mismo
# mecanismo genérico que ya usa el ítem 9 de PHQ-9.
REGLA_OPERADOR = ">="
REGLA_VALOR_COMPARACION = 3


def _texto_interpretacion(dimension_nombre, edad_min, edad_max, nivel):
    return (
        f"Clasificación TÉCNICA INTERNA (no clínica, no psicométrica) del "
        f"desempeño en la dimensión '{dimension_nombre}' para el rango de "
        f"edad {edad_min}-{edad_max}: nivel '{nivel}'. Este texto no describe "
        f"ninguna aptitud real ni corresponde a ningún instrumento comercial."
    )


_CONCLUSION_TECNICA = (
    "Contenido de PRUEBA TÉCNICA INTERNA, sin valor clínico: se usa "
    "únicamente para validar que el informe profesional puede mostrar una "
    "conclusión configurada por tramo de baremo en una prueba con varias "
    "dimensiones."
)
_RECOMENDACION_TECNICA = (
    "No aplica ninguna recomendación clínica real. Este texto solo valida "
    "que el PDF reproduce el contenido configurado por baremo (fuente "
    "'configurada por la prueba') junto al resto del informe multidimensional."
)


def _asegurar_reglas(db, prueba, dimensiones_por_nombre) -> None:
    """Añade las 3 reglas (una por dimensión) si faltan — idempotente y
    aditivo, mismo criterio que _asegurar_regla_item_9 en seed_phq9.py."""
    creadas = 0
    for nombre_dim in DIMENSIONES:
        dimension = dimensiones_por_nombre[nombre_dim]
        ya_existe = db.query(models.ReglaInterpretacion).filter(
            models.ReglaInterpretacion.prueba_id == prueba.id,
            models.ReglaInterpretacion.ambito == models.AMBITO_DIMENSION,
            models.ReglaInterpretacion.dimension_id == dimension.id,
        ).first()
        if ya_existe:
            continue
        db.add(models.ReglaInterpretacion(
            prueba_id=prueba.id,
            ambito=models.AMBITO_DIMENSION,
            dimension_id=dimension.id,
            operador=REGLA_OPERADOR,
            valor_comparacion=REGLA_VALOR_COMPARACION,
            accion=models.ACCION_ES_ALERTA,
            descripcion=(
                f"[TÉCNICA INTERNA] Regla de validación sobre la dimensión "
                f"'{nombre_dim}': puntaje {REGLA_OPERADOR} {REGLA_VALOR_COMPARACION} "
                "fuerza revisión técnica para comprobar que varias reglas "
                "pueden activarse simultáneamente sobre distintas dimensiones "
                "de la misma prueba. No representa ningún criterio clínico real."
            ),
            activa=True,
        ))
        creadas += 1
    if creadas:
        db.commit()
        print(f"✅ {creadas} regla(s) de interpretación técnica añadida(s) (una por dimensión).")
    else:
        print("↪️  Las 3 reglas de interpretación técnica ya existían; no se modifican.")


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales y las
    conclusiones/recomendaciones de cada tramo SOLO si están vacíos —
    idempotente y aditivo, mismo criterio que en seed_phq9.py."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")

    baremos_existentes = db.query(models.Baremo, models.Dimension).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(models.Dimension.prueba_id == prueba.id).all()

    actualizados = 0
    for baremo, _dim in baremos_existentes:
        cambio_tramo = False
        if not baremo.conclusion_sugerida:
            baremo.conclusion_sugerida = _CONCLUSION_TECNICA
            cambio_tramo = True
        if not baremo.recomendacion_sugerida:
            baremo.recomendacion_sugerida = _RECOMENDACION_TECNICA
            cambio_tramo = True
        if cambio_tramo:
            actualizados += 1

    if not cambios and not actualizados:
        print("↪️  El contenido del informe (motivo, técnicas, conclusiones, recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{actualizados} tramo(s) de baremo con conclusión/recomendación añadidas.")


def _asegurar_no_visible_para_clientes(db, prueba) -> None:
    """Fuerza visible_para_clientes=False en esta fila concreta — idempotente:
    si un superadmin la reactivó a propósito más tarde, esta función NO la
    vuelve a apagar en una corrida futura del seed (mismo espíritu aditivo que
    el resto de este archivo: nunca pisar una decisión ya tomada a mano).
    Aquí se localiza la fila por nombre_tecnico porque este es un script de
    DATOS de un solo uso (igual que el resto de este seed) — la regla de "sin
    lógica por nombre de prueba" aplica al MOTOR (algoritmo.py, crud de
    cálculo/interpretación), nunca a un seed que ya identifica su propia fila
    por nombre para decidir su idempotencia."""
    if prueba.visible_para_clientes is False:
        print("↪️  Ya estaba marcada como no visible para clientes; no se modifica.")
        return
    prueba.visible_para_clientes = False
    db.commit()
    print("✅ Marcada como NO visible para clientes (no aparecerá en el catálogo de ningún colegio).")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  {NOMBRE_TECNICO} ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_no_visible_para_clientes(db, existente)
            dimensiones = db.query(models.Dimension).filter(models.Dimension.prueba_id == existente.id).all()
            dimensiones_por_nombre = {d.nombre: d for d in dimensiones}
            faltantes = set(DIMENSIONES) - set(dimensiones_por_nombre)
            if faltantes:
                print(f"⚠️  Faltan dimensiones {faltantes}; esta corrida no las crea para no arriesgar "
                      "duplicar ítems ya cargados a mano. Revisa manualmente si esto es inesperado.")
            else:
                _asegurar_reglas(db, existente, dimensiones_por_nombre)
                _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico=NOMBRE_PUBLICO,
            instrucciones=INSTRUCCIONES,
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft, igual que PHQ-9
            # 🆕 No es un producto ofrecido a colegios: no debe aparecer en su
            # catálogo ni admitir campañas nuevas de una institución.
            visible_para_clientes=False,
            escala_minima=0,
            escala_maxima=1,
            modo_calculo="correcto_incorrecto",
            dias_minimos_entre_aplicaciones=0,  # uso técnico/interno, sin restricción de reaplicación
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
            tecnicas_adicionales=TECNICAS_ADICIONALES,
        )
        db.add(prueba)
        db.flush()

        dimensiones_por_nombre = {}
        total_items = 0
        for nombre_dim in DIMENSIONES:
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Dimensión TÉCNICA INTERNA '{nombre_dim}' de validación del motor "
                    "(no clínica, no comercial): ítems originales de corrección "
                    "objetiva (correcto=1/incorrecto=0), sin relación con ningún "
                    "instrumento psicométrico real."
                ),
            )
            db.add(dimension)
            db.flush()
            dimensiones_por_nombre[nombre_dim] = dimension

            for orden, (texto, correcta, incorrecta) in enumerate(ITEMS_POR_DIMENSION[nombre_dim], start=1):
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=texto,
                    orden=orden,
                    es_inverso=False,  # no aplica en modo correcto_incorrecto
                )
                db.add(pregunta)
                db.flush()
                db.add(models.OpcionRespuesta(pregunta_id=pregunta.id, texto_opcion=correcta, valor_puntuacion=1))
                db.add(models.OpcionRespuesta(pregunta_id=pregunta.id, texto_opcion=incorrecta, valor_puntuacion=0))
                total_items += 1

        total_baremos = 0
        for edad_min, edad_max, tramos in BANDAS_EDAD:
            for nombre_dim in DIMENSIONES:
                dimension = dimensiones_por_nombre[nombre_dim]
                for minimo, maximo, nivel, es_alerta in tramos:
                    db.add(models.Baremo(
                        dimension_id=dimension.id,
                        edad_min=edad_min,
                        edad_max=edad_max,
                        sexo=None,       # unisex — esta fase solo ejercita el filtro de edad
                        poblacion=None,  # aplica a cualquier población
                        puntaje_minimo=minimo,
                        puntaje_maximo=maximo,
                        nivel=nivel,
                        interpretacion=_texto_interpretacion(nombre_dim, edad_min, edad_max, nivel),
                        conclusion_sugerida=_CONCLUSION_TECNICA,
                        recomendacion_sugerida=_RECOMENDACION_TECNICA,
                        es_alerta=es_alerta,
                    ))
                    total_baremos += 1

        for nombre_dim in DIMENSIONES:
            dimension = dimensiones_por_nombre[nombre_dim]
            db.add(models.ReglaInterpretacion(
                prueba_id=prueba.id,
                ambito=models.AMBITO_DIMENSION,
                dimension_id=dimension.id,
                operador=REGLA_OPERADOR,
                valor_comparacion=REGLA_VALOR_COMPARACION,
                accion=models.ACCION_ES_ALERTA,
                descripcion=(
                    f"[TÉCNICA INTERNA] Regla de validación sobre la dimensión "
                    f"'{nombre_dim}': puntaje {REGLA_OPERADOR} {REGLA_VALOR_COMPARACION} "
                    "fuerza revisión técnica para comprobar que varias reglas "
                    "pueden activarse simultáneamente sobre distintas dimensiones "
                    "de la misma prueba. No representa ningún criterio clínico real."
                ),
                activa=True,
            ))

        db.commit()
        print(f"✅ {NOMBRE_TECNICO} cargada: prueba id={prueba.id}, "
              f"{len(DIMENSIONES)} dimensiones ({', '.join(DIMENSIONES)}), "
              f"{total_items} ítems (5 por dimensión, correcto_incorrecto), "
              f"{total_baremos} tramos de baremo (2 bandas de edad x 3 dimensiones x 3 niveles), "
              f"{len(DIMENSIONES)} reglas de interpretación (una por dimensión).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando {NOMBRE_TECNICO}: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
