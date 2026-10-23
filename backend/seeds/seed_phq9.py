"""
Carga el catálogo PÚBLICO (institucion_id=None) del PHQ-9 — prueba, dimensión,
9 ítems con sus 4 alternativas, y los baremos clínicos estándar por puntaje
total (Kroenke & Spitzer, 2001). También carga un 10º ítem estándar del
PHQ-9 ("Indicador de Disfuncionalidad") que NO puntúa, y reparte los 9 ítems
que sí puntúan en dos sub-dimensiones reales (Afectivo-Cognitiva / Somática-
Vegetativa) para que la sección "Resultados cualitativos" del informe PDF
tenga contenido propio por área clínica, no solo el párrafo único del
puntaje total — ver docs/informes-psicometricos.md.

Es idempotente: si "PHQ-9" ya existe como prueba pública, no toca nada salvo
lo que falte (regla del ítem 9, contenido del informe, ítem 10, sub-
dimensiones) — nunca pisa contenido que un psicólogo haya ajustado a mano
después de la carga inicial. Para forzar una recarga completa desde cero,
borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_phq9

⚠️ LIMITACIÓN CLÍNICA CONOCIDA, DEJADA A PROPÓSITO FUERA DE ESTA FASE:
El protocolo clínico del PHQ-9 exige revisar a CUALQUIER paciente cuyo ítem 9
("Pensamientos de que estaría mejor muerto...") tenga una respuesta > 0,
INDEPENDIENTEMENTE del puntaje total. Esto SÍ está cubierto (ver
ReglaInterpretacion más abajo, ámbito='item'). Lo que queda fuera de esta
fase es el criterio oficial completo "funcionamiento afectado (ítem 10 ≥ 2)
+ síntomas" propio de otras escalas tipo conteo — el PHQ-9 no lo necesita,
ver docs/motor-scoring.md → "Conteo de síntomas" para el caso que sí lo usa
(NICHQ Vanderbilt).

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `TECNICAS_ADICIONALES` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas — el PHQ-9 fue, de hecho, el molde
("• Entrevista • Observación • [nombre de la prueba]") que se generalizó a
todas. Ejecutarlo después de cualquier `python -m seeds.seed_phq9`.
"""
import sys

# La consola de Windows por defecto usa cp1252, que no sabe codificar los
# emoji de estos mensajes (mismo riesgo que ya existe en seed_superadmin.py,
# pero aquí se blinda para no depender de que la terminal ya esté en UTF-8).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de Prueba/ReglaInterpretacion)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de Prueba)
from modulos.educativo import models

PREGUNTAS = [
    "Poco interés o placer en hacer cosas",
    "Se ha sentido decaído(a), deprimido(a) o sin esperanzas",
    "Dificultad para quedarse o permanecer dormido(a), o ha dormido demasiado",
    "Se ha sentido cansado(a) o con poca energía",
    "Falta de apetito o ha comido en exceso",
    "Se ha sentido mal con usted mismo(a) — o que es un fracaso, o que ha "
    "quedado mal con usted mismo(a) o con su familia",
    "Dificultad para concentrarse en cosas, tales como leer o ver la televisión",
    "Se ha movido o hablado tan lento que otras personas podrían haberlo "
    "notado, o lo contrario: muy inquieto(a) o agitado(a), moviéndose mucho "
    "más de lo normal",
    "Pensamientos de que estaría mejor muerto(a) o de hacerse daño de alguna forma",
]

OPCIONES = [
    ("Nunca", 0),
    ("Varios días", 1),
    ("Más de la mitad de los días", 2),
    ("Casi todos los días", 3),
]

# 🆕 10º ítem estándar del PHQ-9 ("Indicador de Disfuncionalidad") — NO forma
# parte de las 9 preguntas que puntúan: se carga con dimension_id=None (ver
# Pregunta.incluir_en_informe en models.py), así que
# core/algoritmo.py:calcular_likert_generico lo ignora por completo al sumar.
# Su respuesta se imprime literal en la sección 5.2 del informe bajo la
# etiqueta configurada aquí.
TEXTO_ITEM_DISFUNCIONALIDAD = (
    "Si usted marcó cualquiera de estos problemas, ¿qué tan difícil le han "
    "hecho estos problemas realizar su trabajo, atender su casa, o "
    "relacionarse con otras personas?"
)
OPCIONES_DISFUNCIONALIDAD = [
    ("Nada difícil", 0),
    ("Un poco difícil", 1),
    ("Muy difícil", 2),
    ("Extremadamente difícil", 3),
]
ETIQUETA_ITEM_DISFUNCIONALIDAD = "Indicador de Disfuncionalidad"

# 🆕 Reparto de los 9 ítems que SÍ puntúan en dos sub-dimensiones clínicas
# reales (ver Dimension.tipo_calculo='suma_de_dimensiones'/
# DimensionComponente en models.py) — "Depresión" sigue siendo la suma de
# los 9 ítems (0-27) exactamente como siempre, solo que ahora llega ahí como
# la suma de estas dos sub-dimensiones en vez de sumar sus propios ítems
# directamente. Agrupación clínica habitual del PHQ-9 (factor afectivo-
# cognitivo vs. somático-vegetativo); el ítem 9 (ideación autolítica) queda
# en el grupo afectivo-cognitivo, coherente con su propia
# ReglaInterpretacion de ítem (ver más abajo), que no depende de a qué
# dimensión pertenezca.
ORDENES_AFECTIVO_COGNITIVA = {1, 2, 6, 7, 9}
ORDENES_SOMATICA_VEGETATIVA = {3, 4, 5, 8}
NOMBRE_DIM_AFECTIVO = "Dimensión Afectivo-Cognitiva"
NOMBRE_DIM_SOMATICA = "Dimensión Somática/Vegetativa"
DESCRIPCION_DIM_AFECTIVO = (
    "Ánimo, interés/anhedonia, autopercepción, concentración e ideación "
    "autolítica (ítems 1, 2, 6, 7 y 9)."
)
DESCRIPCION_DIM_SOMATICA = (
    "Sueño, energía, apetito y actividad psicomotora (ítems 3, 4, 5 y 8)."
)

# (mínimo, máximo, nivel, es_alerta, conclusión sugerida, recomendación sugerida)
# — sin huecos entre tramos, 0..27. Umbral de alerta en 10 (moderado en
# adelante): criterio clínico habitual de referencia/derivación para este
# instrumento; un psicólogo puede ajustarlo después vía
# PATCH /educativo/baremos/{id} si su protocolo institucional difiere.
# Conclusión/recomendación son CONTENIDO CONFIGURADO (fuente "B" del
# informe, ver "FUENTES DE CONTENIDO DEL INFORME") — el profesional puede
# sustituirlas por su propio texto al revisar cada informe.
BAREMOS = [
    (0, 4, "Mínimo o ninguno", False,
     "El puntaje obtenido se encuentra dentro del rango mínimo o ausente de sintomatología depresiva. "
     "No se identifican indicadores clínicamente significativos de depresión al momento de la evaluación.",
     "Se recomienda continuar con el acompañamiento habitual del estudiante. No se requiere intervención "
     "especializada en este momento; se sugiere una nueva evaluación de tamizaje en el siguiente periodo "
     "académico o ante cambios observables en el estudiante."),
    (5, 9, "Leve", False,
     "El puntaje obtenido corresponde a sintomatología depresiva de grado leve. Se identifican algunos "
     "indicadores que ameritan seguimiento, sin alcanzar aún un nivel clínicamente significativo.",
     "Se recomienda seguimiento por parte del área de psicología del colegio, con observación periódica "
     "de la evolución del estudiante. Puede ser útil una conversación exploratoria breve para descartar "
     "factores estresores puntuales."),
    (10, 14, "Moderado", True,
     "El puntaje obtenido corresponde a sintomatología depresiva de grado moderado, lo que sugiere un "
     "impacto relevante en el bienestar del estudiante que amerita atención profesional.",
     "Se recomienda derivación a evaluación psicológica individual y seguimiento cercano por parte del "
     "profesional responsable. Se sugiere informar y coordinar con la familia o apoderados, según el "
     "protocolo institucional vigente."),
    (15, 19, "Moderadamente severo", True,
     "El puntaje obtenido corresponde a sintomatología depresiva de grado moderadamente severo. Los "
     "resultados indican un nivel de afectación considerable que requiere intervención oportuna.",
     "Se recomienda derivación prioritaria a evaluación psicológica o psiquiátrica especializada, y "
     "coordinación inmediata con la familia y las instancias institucionales correspondientes según el "
     "protocolo de la institución."),
    (20, 27, "Severo", True,
     "El puntaje obtenido corresponde a sintomatología depresiva de grado severo, lo que constituye un "
     "indicador de alto riesgo que exige atención profesional inmediata.",
     "Se recomienda derivación urgente a evaluación especializada (psicología y/o psiquiatría), activación "
     "del protocolo institucional de atención a casos de riesgo, y comunicación inmediata con la familia "
     "o apoderados."),
]

# 🆕 Tramos de las sub-dimensiones — SOLO descriptivos (es_alerta=False
# siempre: la alerta sigue decidiéndose exclusivamente por el baremo del
# total "Depresión" y por la ReglaInterpretacion del ítem 9, nunca por
# estos). Sin conclusion_sugerida/recomendacion_sugerida a propósito: esas
# siguen viniendo solo del tramo del total, para que la sección 6/7 del
# informe no repita el mismo contenido tres veces (una por dimensión).
# (mínimo, máximo, nivel, interpretación)
BAREMOS_AFECTIVO_COGNITIVA = [
    (0, 2, "Mínimo o ninguno",
     "No se identifican indicadores relevantes en el área afectivo-cognitiva (ánimo, interés por "
     "actividades, autopercepción, concentración, pensamientos de autolesión)."),
    (3, 5, "Leve",
     "Se identifican indicadores leves en el área afectivo-cognitiva: cierta disminución del ánimo o "
     "del interés en actividades habituales, sin que esto represente, por sí solo, una afectación "
     "clínicamente significativa."),
    (6, 8, "Moderado",
     "Se identifica una presencia moderada de indicadores afectivo-cognitivos: ánimo decaído y/o "
     "disminución del interés por actividades placenteras (anhedonia), que pueden acompañarse de "
     "sentimientos de culpa o minusvalía y cierta dificultad para concentrarse."),
    (9, 11, "Moderadamente severo",
     "Se identifica una presencia considerable de indicadores afectivo-cognitivos: ánimo deprimido y/o "
     "anhedonia marcados, sentimientos de culpa o minusvalía relevantes, y dificultad para concentrarse "
     "en tareas cotidianas."),
    (12, 15, "Severo",
     "Se identifica una presencia crítica de indicadores afectivo-cognitivos: ánimo deprimido/tristeza "
     "persistente, anhedonia marcada, sentimientos significativos de culpa o minusvalía, dificultad "
     "relevante para concentrarse y posible presencia de pensamientos de autolesión — este último punto "
     "se detalla en el Análisis de riesgo."),
]
BAREMOS_SOMATICA_VEGETATIVA = [
    (0, 2, "Mínimo o ninguno",
     "No se identifican alteraciones relevantes en el área somática/vegetativa (sueño, energía, "
     "apetito, actividad psicomotora)."),
    (3, 4, "Leve",
     "Se identifican alteraciones leves en el área somática/vegetativa, sin que esto represente, por sí "
     "solo, una afectación clínicamente significativa."),
    (5, 7, "Moderado",
     "Se identifican alteraciones moderadas en el área somática/vegetativa: cambios en el ciclo del "
     "sueño (insomnio o hipersomnia) y/o fatiga o baja energía, con posible disminución o aumento del "
     "apetito."),
    (8, 9, "Moderadamente severo",
     "Se identifican alteraciones considerables en el área somática/vegetativa: afectación relevante "
     "del sueño, fatiga marcada y/o cambios notorios en el apetito, que pueden acompañarse de "
     "enlentecimiento o agitación psicomotora."),
    (10, 12, "Severo",
     "Se identifican alteraciones severas en el área somática/vegetativa: afectación marcada del sueño, "
     "fatiga intensa, cambios significativos en el apetito y/o alteraciones notorias en la actividad "
     "psicomotora (enlentecimiento o agitación)."),
]

MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para medir la presencia y severidad de sintomatología depresiva "
    "reportada por el estudiante durante las últimas dos semanas, en el marco de una campaña de "
    "evaluación psicométrica institucional."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

NOMBRE_TECNICO = "PHQ-9"


def _asegurar_regla_item_9(db, prueba) -> None:
    """Añade la regla del ítem 9 si el PHQ-9 ya existía sin ella (idempotente
    y puramente aditivo: nunca toca preguntas, opciones ni baremos ya
    cargados por otra vía)."""
    pregunta_item_9 = db.query(models.Pregunta).filter(
        models.Pregunta.prueba_id == prueba.id, models.Pregunta.orden == 9,
    ).first()
    if not pregunta_item_9:
        print("⚠️  No se encontró el ítem 9 en este PHQ-9; no se pudo asegurar la regla de alerta.")
        return

    ya_existe = db.query(models.ReglaInterpretacion).filter(
        models.ReglaInterpretacion.prueba_id == prueba.id,
        models.ReglaInterpretacion.ambito == models.AMBITO_ITEM,
        models.ReglaInterpretacion.pregunta_id == pregunta_item_9.id,
    ).first()
    if ya_existe:
        print(f"↪️  La regla del ítem 9 ya existe (id={ya_existe.id}); no se modifica.")
        return

    regla = models.ReglaInterpretacion(
        prueba_id=prueba.id,
        ambito=models.AMBITO_ITEM,
        pregunta_id=pregunta_item_9.id,
        operador=">",
        valor_comparacion=0,
        accion=models.ACCION_ES_ALERTA,
        descripcion=(
            "Ítem 9 positivo (pensamientos de autolesión o de estar mejor "
            "muerto/a): requiere revisión profesional aunque el puntaje "
            "total no alcance un tramo de alerta."
        ),
        activa=True,
    )
    db.add(regla)
    db.commit()
    print(f"✅ Regla del ítem 9 añadida al PHQ-9 existente (regla id={regla.id}).")


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba y
    conclusion_sugerida/recomendacion_sugerida de cada tramo de baremo SOLO
    si están vacíos — idempotente y puramente aditivo, igual que
    _asegurar_regla_item_9: nunca pisa contenido que un psicólogo ya haya
    editado a mano."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")

    baremos_existentes = db.query(models.Baremo).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(models.Dimension.prueba_id == prueba.id).all()

    baremos_actualizados = 0
    for baremo in baremos_existentes:
        for minimo, maximo, _nivel, _alerta, conclusion, recomendacion in BAREMOS:
            if float(baremo.puntaje_minimo) == minimo and float(baremo.puntaje_maximo) == maximo:
                cambio_tramo = False
                if not baremo.conclusion_sugerida:
                    baremo.conclusion_sugerida = conclusion
                    cambio_tramo = True
                if not baremo.recomendacion_sugerida:
                    baremo.recomendacion_sugerida = recomendacion
                    cambio_tramo = True
                if cambio_tramo:
                    baremos_actualizados += 1
                break

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe (motivo, técnicas, conclusiones, recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) de baremo con conclusión/recomendación añadidas.")


def _asegurar_item_disfuncionalidad(db, prueba) -> None:
    """Añade el ítem 10 (Indicador de Disfuncionalidad, sin puntuar) si el
    PHQ-9 ya existía sin él — idempotente y aditivo, mismo criterio que
    _asegurar_regla_item_9."""
    ya_existe = db.query(models.Pregunta).filter(
        models.Pregunta.prueba_id == prueba.id, models.Pregunta.orden == 10,
    ).first()
    if ya_existe:
        print(f"↪️  El ítem 10 (disfuncionalidad) ya existe (id={ya_existe.id}); no se modifica.")
        return

    pregunta = models.Pregunta(
        prueba_id=prueba.id,
        dimension_id=None,
        texto_pregunta=TEXTO_ITEM_DISFUNCIONALIDAD,
        orden=10,
        es_inverso=False,
        incluir_en_informe=True,
        etiqueta_informe=ETIQUETA_ITEM_DISFUNCIONALIDAD,
    )
    db.add(pregunta)
    db.flush()
    for texto_opcion, valor in OPCIONES_DISFUNCIONALIDAD:
        db.add(models.OpcionRespuesta(pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor))
    db.commit()
    print(f"✅ Ítem 10 (disfuncionalidad) añadido al PHQ-9 existente (pregunta id={pregunta.id}).")


def _interpretacion_total(minimo, maximo, nivel) -> str:
    """Texto de `Baremo.interpretacion` del tramo del TOTAL "Depresión" —
    antes de la revisión crítica de contenido (ver docs/informes-
    psicometricos.md) era solo "Puntaje total X-Y: síntomas depresivos de
    nivel 'Z'.", visiblemente más pobre que el de sus propias sub-
    dimensiones (que sí tienen prosa clínica) y que el de GAD-7 (que no
    tiene sub-dimensiones y concentra toda la narrativa en su único
    total) — una inconsistencia real entre informes de distintas pruebas.
    Se mantiene corto a propósito (las dos sub-dimensiones ya cargan el
    detalle narrativo), pero ahora sintetiza en vez de solo repetir el
    número."""
    return (
        f"Puntaje total {minimo}-{maximo}: síntomas depresivos de nivel '{nivel.lower()}'. "
        "Considerando en conjunto las áreas afectivo-cognitiva y somática/vegetativa (ver el "
        "detalle de cada una a continuación), este es el perfil general del estudiante en esta "
        "aplicación."
    )


def _asegurar_interpretacion_total_enriquecida(db, prueba) -> None:
    """Revisión crítica de contenido — actualiza `interpretacion` de los
    tramos del TOTAL "Depresión" al texto enriquecido de `_interpretacion_
    total()` cuando todavía tienen el texto terso original. A diferencia
    del resto de los `_asegurar_*` de este archivo, SÍ sobrescribe
    contenido ya cargado — justificado solo porque, a la fecha de este
    cambio, no hay ninguna inscripción real de PHQ-9 en la base (ver
    docs/informes-psicometricos.md), así que no hay ningún informe ya
    emitido cuyo significado pueda alterarse retroactivamente. Detecta "ya
    actualizado" por substring, no por campo vacío (interpretacion nunca
    estuvo vacía), para poder correr de nuevo sin duplicar el texto."""
    dimension_total = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id,
        models.Dimension.tipo_calculo == models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
    ).first()
    if not dimension_total:
        return

    baremos = db.query(models.Baremo).filter(
        models.Baremo.dimension_id == dimension_total.id,
    ).all()
    actualizados = 0
    for baremo in baremos:
        texto_nuevo = _interpretacion_total(
            baremo.puntaje_minimo if isinstance(baremo.puntaje_minimo, int) else int(baremo.puntaje_minimo),
            baremo.puntaje_maximo if isinstance(baremo.puntaje_maximo, int) else int(baremo.puntaje_maximo),
            baremo.nivel,
        )
        if "Considerando en conjunto" in (baremo.interpretacion or ""):
            continue
        baremo.interpretacion = texto_nuevo
        actualizados += 1

    if not actualizados:
        print("↪️  La interpretación del total 'Depresión' ya estaba enriquecida; no se modifica.")
        return
    db.commit()
    print(f"✅ Interpretación del total 'Depresión' enriquecida en {actualizados} tramo(s) "
          "(revisión crítica de contenido).")


def _asegurar_nombre_dimension_total(db, prueba) -> None:
    """Pura cosmética — algunas cargas tempranas de este PHQ-9 guardaron el
    nombre de la dimensión total como 'depresion' (sin tilde, minúscula) en
    vez de 'Depresión'; eso se imprime tal cual en la sección 5.1/5.2 del
    informe. No afecta ninguna lógica (desde este cambio, nada busca esta
    dimensión por nombre, ver _asegurar_subdimensiones), así que es seguro
    corregirlo con un simple rename. Idempotente: no hace nada si ya dice
    'Depresión' o si el psicólogo le puso otro nombre a propósito que no sea
    ninguna de las dos variantes conocidas."""
    dimension = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id,
        models.Dimension.tipo_calculo == models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
    ).first()
    if not dimension or dimension.nombre == "Depresión":
        return
    if dimension.nombre.strip().lower() not in ("depresion", "depresión"):
        return  # un nombre distinto a propósito: no se toca
    nombre_anterior = dimension.nombre
    dimension.nombre = "Depresión"
    db.add(dimension)
    db.commit()
    print(f"✅ Nombre de la dimensión total corregido: {nombre_anterior!r} -> 'Depresión'.")


def _asegurar_subdimensiones(db, prueba) -> None:
    """Reestructura la dimensión del puntaje total en dos sub-dimensiones
    reales (Afectivo-Cognitiva / Somática-Vegetativa) para la sección
    "Resultados cualitativos" del informe — ver docs/informes-psicometricos.md.

    Encuentra la dimensión total MIRANDO A QUÉ DIMENSIÓN apuntan hoy los 9
    ítems que puntúan (orden 1-9) en vez de buscarla por nombre — el nombre
    ("Depresión", "depresion"...) puede haber sido editado a mano después de
    la carga inicial, y da igual cuál sea: si los 9 siguen apuntando todos a
    la MISMA dimensión, esa es la que hay que reestructurar; si ya apuntan a
    más de una, se asume que la migración ya se hizo antes (idempotente).

    SOLO actúa si esa dimensión todavía no tiene ResultadoDimension: igual
    que crud.actualizar_dimension bloquea con 409 cambiar tipo_calculo de
    una dimensión que ya produjo resultados reales, este script nunca
    reestructura una dimensión en uso — eso cambiaría retroactivamente a qué
    dimensión pertenece cada respuesta ya registrada. En ese caso deja todo
    tal cual e imprime una advertencia en vez de arriesgar datos de
    estudiantes reales."""
    preguntas = {p.orden: p for p in db.query(models.Pregunta).filter(
        models.Pregunta.prueba_id == prueba.id, models.Pregunta.orden.in_(range(1, 10)),
    ).all()}
    if len(preguntas) != 9:
        print(f"⚠️  Se esperaban 9 ítems (orden 1-9) y se encontraron {len(preguntas)}; no se pudo verificar/crear las sub-dimensiones.")
        return

    dimension_ids_actuales = {p.dimension_id for p in preguntas.values()}
    if len(dimension_ids_actuales) > 1:
        print("↪️  Los 9 ítems que puntúan ya están repartidos en más de una dimensión; se asume que las "
              "sub-dimensiones ya existen y no se modifica nada.")
        return

    dimension_total = db.query(models.Dimension).filter(
        models.Dimension.id == next(iter(dimension_ids_actuales)),
    ).first()
    if not dimension_total or dimension_total.tipo_calculo != models.TIPO_CALCULO_ITEMS:
        print("↪️  La dimensión del puntaje total ya no es de tipo 'items' (o no se encontró); se asume "
              "que la migración ya se hizo y no se modifica nada.")
        return

    tiene_resultados = db.query(models.ResultadoDimension.id).filter(
        models.ResultadoDimension.dimension_id == dimension_total.id
    ).first() is not None
    if tiene_resultados:
        print(
            f"⚠️  La dimensión '{dimension_total.nombre}' ya tiene resultados calculados (hay "
            "inscripciones que ya la usaron) — no se reestructura en sub-dimensiones para no alterar "
            "retroactivamente un resultado ya emitido. Si esta base de datos es solo de prueba/QA y "
            "quieres la nueva estructura, borra la fila de edu_pruebas de PHQ-9 y vuelve a correr este "
            "script desde cero."
        )
        return

    dim_afectivo = models.Dimension(
        prueba_id=prueba.id, nombre=NOMBRE_DIM_AFECTIVO, descripcion=DESCRIPCION_DIM_AFECTIVO,
    )
    dim_somatica = models.Dimension(
        prueba_id=prueba.id, nombre=NOMBRE_DIM_SOMATICA, descripcion=DESCRIPCION_DIM_SOMATICA,
    )
    db.add_all([dim_afectivo, dim_somatica])
    db.flush()

    for orden, pregunta in preguntas.items():
        pregunta.dimension_id = dim_afectivo.id if orden in ORDENES_AFECTIVO_COGNITIVA else dim_somatica.id
        db.add(pregunta)

    dimension_total.tipo_calculo = models.TIPO_CALCULO_SUMA_DE_DIMENSIONES
    db.add(dimension_total)
    db.add_all([
        models.DimensionComponente(dimension_compuesta_id=dimension_total.id, dimension_componente_id=dim_afectivo.id, orden=1),
        models.DimensionComponente(dimension_compuesta_id=dimension_total.id, dimension_componente_id=dim_somatica.id, orden=2),
    ])

    for minimo, maximo, nivel, interpretacion in BAREMOS_AFECTIVO_COGNITIVA:
        db.add(models.Baremo(
            dimension_id=dim_afectivo.id, edad_min=None, edad_max=None, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel, interpretacion=interpretacion,
            es_alerta=False,
        ))
    for minimo, maximo, nivel, interpretacion in BAREMOS_SOMATICA_VEGETATIVA:
        db.add(models.Baremo(
            dimension_id=dim_somatica.id, edad_min=None, edad_max=None, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel, interpretacion=interpretacion,
            es_alerta=False,
        ))

    db.commit()
    print(f"✅ Sub-dimensiones creadas: Afectivo-Cognitiva (id={dim_afectivo.id}), "
          f"Somática/Vegetativa (id={dim_somatica.id}); 'Depresión' (id={dimension_total.id}) "
          f"ahora es 'suma_de_dimensiones' de ambas.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  PHQ-9 ya existe (prueba id={existente.id}); no se toca su catálogo base.")
            _asegurar_regla_item_9(db, existente)
            _asegurar_contenido_informe(db, existente)
            _asegurar_item_disfuncionalidad(db, existente)
            _asegurar_subdimensiones(db, existente)
            _asegurar_nombre_dimension_total(db, existente)
            _asegurar_interpretacion_total_enriquecida(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Cuestionario sobre la Salud del Paciente (PHQ-9)",
            instrucciones=(
                "Durante las últimas 2 semanas, ¿con qué frecuencia le han "
                "molestado los siguientes problemas?"
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=3,
            modo_calculo="likert_suma",
            dias_minimos_entre_aplicaciones=14,
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
            tecnicas_adicionales=TECNICAS_ADICIONALES,
        )
        db.add(prueba)
        db.flush()

        # 🆕 Dos sub-dimensiones reales (ver cabecera del archivo) — "Depresión"
        # más abajo las suma vía el mecanismo genérico de dimensión compuesta,
        # así que el puntaje total (0-27) y su alerta siguen siendo
        # exactamente los de siempre.
        dim_afectivo = models.Dimension(
            prueba_id=prueba.id, nombre=NOMBRE_DIM_AFECTIVO, descripcion=DESCRIPCION_DIM_AFECTIVO,
        )
        dim_somatica = models.Dimension(
            prueba_id=prueba.id, nombre=NOMBRE_DIM_SOMATICA, descripcion=DESCRIPCION_DIM_SOMATICA,
        )
        db.add_all([dim_afectivo, dim_somatica])
        db.flush()

        dimension_total = models.Dimension(
            prueba_id=prueba.id,
            nombre="Depresión",
            descripcion="Puntaje único del PHQ-9 (suma de los 9 ítems, 0-27) — suma de las dos "
                        "sub-dimensiones de abajo.",
            tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
        )
        db.add(dimension_total)
        db.flush()

        db.add_all([
            models.DimensionComponente(dimension_compuesta_id=dimension_total.id, dimension_componente_id=dim_afectivo.id, orden=1),
            models.DimensionComponente(dimension_compuesta_id=dimension_total.id, dimension_componente_id=dim_somatica.id, orden=2),
        ])

        pregunta_item_9 = None
        for orden, texto in enumerate(PREGUNTAS, start=1):
            dimension_item = dim_afectivo if orden in ORDENES_AFECTIVO_COGNITIVA else dim_somatica
            pregunta = models.Pregunta(
                prueba_id=prueba.id,
                dimension_id=dimension_item.id,
                texto_pregunta=texto,
                orden=orden,
                es_inverso=False,  # el PHQ-9 estándar no tiene ítems inversos
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in OPCIONES:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id,
                    texto_opcion=texto_opcion,
                    valor_puntuacion=valor,
                ))
            if orden == 9:
                pregunta_item_9 = pregunta

        # 🆕 Ítem 10 — "Indicador de Disfuncionalidad", no puntúa (ver
        # cabecera del archivo y Pregunta.incluir_en_informe en models.py).
        pregunta_disfuncionalidad = models.Pregunta(
            prueba_id=prueba.id,
            dimension_id=None,
            texto_pregunta=TEXTO_ITEM_DISFUNCIONALIDAD,
            orden=10,
            es_inverso=False,
            incluir_en_informe=True,
            etiqueta_informe=ETIQUETA_ITEM_DISFUNCIONALIDAD,
        )
        db.add(pregunta_disfuncionalidad)
        db.flush()
        for texto_opcion, valor in OPCIONES_DISFUNCIONALIDAD:
            db.add(models.OpcionRespuesta(
                pregunta_id=pregunta_disfuncionalidad.id,
                texto_opcion=texto_opcion,
                valor_puntuacion=valor,
            ))

        for minimo, maximo, nivel, es_alerta, conclusion, recomendacion in BAREMOS:
            db.add(models.Baremo(
                dimension_id=dimension_total.id,
                edad_min=None,
                edad_max=None,
                sexo=None,       # unisex
                poblacion=None,  # aplica a cualquier población (Primaria/Secundaria/Universitario)
                puntaje_minimo=minimo,
                puntaje_maximo=maximo,
                nivel=nivel,
                interpretacion=_interpretacion_total(minimo, maximo, nivel),
                conclusion_sugerida=conclusion,
                recomendacion_sugerida=recomendacion,
                es_alerta=es_alerta,
            ))

        # 🆕 Tramos descriptivos de cada sub-dimensión (ver BAREMOS_AFECTIVO_
        # COGNITIVA/BAREMOS_SOMATICA_VEGETATIVA más arriba) — es_alerta=False
        # siempre, nunca una segunda vía de alerta independiente del total.
        for minimo, maximo, nivel, interpretacion in BAREMOS_AFECTIVO_COGNITIVA:
            db.add(models.Baremo(
                dimension_id=dim_afectivo.id, edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel, interpretacion=interpretacion,
                es_alerta=False,
            ))
        for minimo, maximo, nivel, interpretacion in BAREMOS_SOMATICA_VEGETATIVA:
            db.add(models.Baremo(
                dimension_id=dim_somatica.id, edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel, interpretacion=interpretacion,
                es_alerta=False,
            ))

        # 🆕 Regla de interpretación específica del PHQ-9 — configurada por
        # DATOS (ReglaInterpretacion), no por código: el motor genérico
        # (crud.evaluar_reglas_interpretacion) no sabe que esto es "PHQ-9" ni
        # que el ítem 9 significa ideación de autolesión/suicidio, solo
        # evalúa ámbito='item' + pregunta_id + operador '>' + valor 0. Cubre
        # exactamente la limitación clínica documentada arriba: cualquier
        # respuesta positiva en el ítem 9 exige revisión aunque el puntaje
        # total quede en un tramo sin alerta.
        db.add(models.ReglaInterpretacion(
            prueba_id=prueba.id,
            ambito=models.AMBITO_ITEM,
            pregunta_id=pregunta_item_9.id,
            operador=">",
            valor_comparacion=0,
            accion=models.ACCION_ES_ALERTA,
            descripcion=(
                "Ítem 9 positivo (pensamientos de autolesión o de estar mejor "
                "muerto/a): requiere revisión profesional aunque el puntaje "
                "total no alcance un tramo de alerta."
            ),
            activa=True,
        ))

        db.commit()
        print(f"✅ PHQ-9 cargado: prueba id={prueba.id}; 3 dimensiones (Depresión total + "
              f"2 sub-dimensiones), {len(PREGUNTAS)} ítems que puntúan + 1 ítem informativo "
              f"(disfuncionalidad), {len(BAREMOS) + len(BAREMOS_AFECTIVO_COGNITIVA) + len(BAREMOS_SOMATICA_VEGETATIVA)} "
              f"tramos de baremo, 1 regla de interpretación (ítem 9).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando PHQ-9: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
