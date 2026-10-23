"""
Carga el catálogo PÚBLICO (institucion_id=None) del SCARED-41 — versión
SCARED-C (autoinforme del niño/a), prueba, 5 dimensiones (sub-escalas
clínicas), 41 ítems con sus 3 alternativas, y los tramos de baremo por
punto de corte de cada sub-escala (Birmaher et al., 1999).

Es idempotente: si "SCARED-C" ya existe como prueba pública, no toca nada.
Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_scared

⚠️ SOLO SCARED-C (autoinforme del niño), SCARED-P (versión para padres) NO
CARGADA TODAVÍA — esta es, justamente, la prueba real que motivó construir
`informante_tipo` (ver CLAUDE.md, "Informante: who answers is not always
who the result is about"): SCARED-C y SCARED-P son DOS instrumentos
("una fila por variante", mismo criterio que PHQ-9 vs. la prueba de
aptitud técnica interna), cada uno con su propio informante_tipo
("estudiante" vs. "padre_madre"). Solo se carga SCARED-C aquí porque es la
única con texto literal disponible (el formulario real, en español
argentino, traducido por la Lic. Elefante y la Dra. Graña del Htal.
Zubizarreta, para niños de 8-12 años). SCARED-P usa una redacción distinta
("mi hijo/a..." en vez de "yo...") que no se inventa aquí — queda como
trabajo pendiente explícito para cuando se disponga del formulario parental
real, siguiendo el mismo criterio de "no inventar contenido" ya aplicado a
GAD-7/CHASIDE/APGAR-FAMILIAR.

✅ EL PUNTO DE CORTE DEL PUNTAJE TOTAL YA SE CARGA (antes no — ver el
párrafo anterior a esta edición, que documentaba el límite como abierto):
el motor que resuelve esto (`Dimension.tipo_calculo='suma_de_dimensiones'`
+ `DimensionComponente`) ya existía desde que se cargó SDQ-CAS — "Puntaje
total" (ver `_asegurar_dimension_total` más abajo) es el segundo uso real
de ese mecanismo fuera de sus propios tests, exactamente el mismo patrón
que "Dificultades Totales" de seed_sdq.py: una Dimension nueva, sin
preguntas propias, cuyo puntaje_directo es la suma de las 5 sub-escalas ya
cargadas (`DimensionComponente` referencia las 5, rango resultante 0-82).
Se añadió recién en esta sesión, a partir de un informe real de referencia
que sí reporta un "Puntaje total" con su propio punto de corte — antes de
tener ese ejemplo concreto no había evidencia suficiente para fijar el
corte con confianza. **Corte único en 25** (`<25` No elevado / `≥25`
Elevado) — el valor que el propio informe de referencia declara
explícitamente ("por encima del punto de corte de 25 puntos"); la
literatura internacional también reporta un segundo corte más específico
(>30) pero, a falta de una segunda fuente que lo confirme para esta
versión de 41 ítems en particular, solo se carga el corte de 25 (mismo
criterio de "no inventar un segundo tramo sin evidencia" ya aplicado en
otras cargas de esta plataforma).

⚠️ RANGO ETARIO: 8-12 años, NO 8-18 — se usa el rango que el propio
formulario cargado declara en su encabezado ("Niños 8-12 años"), no el
rango más amplio (8-18) que reporta la literatura internacional general
para el instrumento en conjunto. Igual que con el resto de las pruebas
cargadas en esta sesión, se prefiere el rango específico de la evidencia
realmente en uso sobre uno más amplio no verificado contra este formulario
en particular.

⚠️ es_alerta: cada sub-escala tiene dos tramos (por debajo del punto de
corte / en el punto de corte o por encima), con es_alerta=True solo en el
tramo "Elevado" — siguiendo el mismo criterio ya usado en GAD-7/
APGAR-FAMILIAR para instrumentos de cribado con punto de corte clínico
explícito (a diferencia de CHASIDE, que no es clínico).

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_POR_SUBESCALA/CONTENIDO_
TOTAL más abajo y _asegurar_contenido_informe): `motivo_consulta_default`
de la prueba (adaptado casi literalmente de "II. MOTIVO DE EVALUACIÓN" del
informe de referencia — es un motivo genérico y reutilizable, no específico
de ningún caso) queda cargado; `tecnicas_adicionales` se deja NULL a
propósito — el informe de referencia no reporta ninguna técnica adicional
real a la aplicación del propio cuestionario (a diferencia de APGAR-
FAMILIAR, que sí listaba "Observación"), así que no se inventa una.

`Baremo.interpretacion` del tramo "Elevado" de cada una de las 5
sub-escalas se reescribe con el párrafo real de "Interpretación por
dimensiones" del informe de referencia (adaptado a "el/la evaluado/a"); el
tramo "No elevado" de cada sub-escala conserva su texto original — ya
tenía redacción clínica propia desde su carga inicial, a diferencia de los
tramos genéricos de CHASIDE. **`conclusion_sugerida`/`recomendacion_
sugerida` se cargan SOLO en el tramo del total "Puntaje total" (nunca en
las 5 sub-escalas)** — mismo criterio exacto que PHQ-9: "para que las
secciones 6/7 no repitan el mismo contenido [cinco] veces" (ver seed_phq9.py
y docs/informes-psicometricos.md, "PHQ-9 por sub-dimensiones"). La
sección "VI. CONCLUSIONES" del informe de referencia incluye un punto que
identifica "el área de mayor puntuación" — es un cómputo real (qué
sub-escala anotó más alto varía por estudiante), no texto fijo, y el motor
de conclusion_sugerida/recomendacion_sugerida solo sabe imprimir texto fijo
por tramo alcanzado; replicar ese punto exacto necesitaría el mismo tipo de
mecanismo de "código de perfil" que ya existe para IPIP-RIASEC
(`ordenar_dimensiones_por_puntaje`/`_calcular_codigo_perfil`), que NO se
activa aquí a propósito — asume que la primera letra del nombre de cada
dimensión es significativa (cierto para R-I-A-S-E-C, falso para los
nombres largos de SCARED) e imprimiría un "código de perfil" sin sentido
clínico en cada informe. Se omite ese punto específico del contenido
cargado; el resto de la síntesis de "VI. CONCLUSIONES"/"VII.
RECOMENDACIONES" sí se carga, generalizado sin esa afirmación computada.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `tecnicas_adicionales` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_scared`.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de Prueba)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de Prueba)
from modulos.educativo import models

NOMBRE_TECNICO = "SCARED-C"

# Texto LITERAL de los 41 ítems — formulario real en español (Htal.
# Zubizarreta, Buenos Aires; trad. Lic. Elefante, Dra. Graña), tal como lo
# usa la institución que lo aplica. Se retira únicamente la anotación
# marginal "(¿?)" del ítem 27 (una nota del propio traductor, no parte de
# la pregunta).
PREGUNTAS = {
    1: "Cuando me siento asustado, me es difícil respirar.",
    2: "Tengo dolor de cabeza cuando estoy en la escuela.",
    3: "No me gusta estar con gente a la que no conozco bien.",
    4: "Tengo miedo si duermo fuera de casa.",
    5: "Me preocupo si le caigo bien a otras personas.",
    6: "Cuando estoy asustado quisiera desaparecer.",
    7: "Soy nervioso.",
    8: "Sigo a mi madre o padre donde sea que vayan.",
    9: "La gente me dice que parece que estoy nervioso.",
    10: "Me siento nervioso con gente a la que no conozco mucho.",
    11: "Tengo dolor de estómago en la escuela.",
    12: "Cuando estoy asustado siento como si me estuviera volviendo loco.",
    13: "Me da miedo dormir solo.",
    14: "Me preocupa ser tan bueno como los otros niños.",
    15: "Cuando estoy asustado siento como si las cosas no fueran reales.",
    16: "Tengo pesadillas acerca de que algo malo pueda sucederle a mis padres.",
    17: "Me da miedo ir a la escuela.",
    18: "Cuando estoy asustado mi corazón late rápido.",
    19: "Me pongo a temblar.",
    20: "Tengo pesadillas con que algo malo pueda sucederme.",
    21: "Me preocupo que las cosas me salgan bien.",
    22: "Cuando estoy asustado transpiro mucho.",
    23: "Me preocupo demasiado.",
    24: "Me asusto demasiado sin ninguna razón.",
    25: "Me asusto cuando me quedo solo en casa.",
    26: "Es difícil para mí hablar con gente que no conozco bien.",
    27: "Cuando estoy asustado, siento como si cayera en shock.",
    28: "La gente me dice que me preocupo demasiado.",
    29: "No me gusta estar lejos de mi familia.",
    30: "Tengo miedo de ponerme ansioso o tener ataques de pánico.",
    31: "Me preocupa que algo malo podría sucederle a mis padres.",
    32: "Me pongo tímido con la gente a la que no conozco bien.",
    33: "Me preocupa pensar en lo que pudiera sucederme en el futuro.",
    34: "Cuando me asusto siento como si me estuviera cayendo.",
    35: "Me preocupa si hago bien las cosas.",
    36: "Tengo miedo de ir a la escuela.",
    37: "Me preocupo por cosas que ya pasaron.",
    38: "Cuando me asusto, me siento mareado.",
    39: "Me siento nervioso cuando estoy con otros niños o adultos, y tengo que hacer algo "
        "mientras ellos me observan (ej: leer en voz alta, hablar, jugar, practicar un deporte, etc).",
    40: "Me siento nervioso cuando voy a fiestas, bailes o algún lugar en donde habrá gente que no conozco.",
    41: "Soy tímido.",
}

# Matriz de sub-escalas — fuente: ficha técnica (guía de puntuación de la
# versión de 41 ítems, Birmaher et al., 1999). Verificada por código: cubre
# 1-41 exactamente una vez (ver verificación previa a este script).
SUBESCALAS = {
    "Pánico / síntomas somáticos": {
        "items": [1, 6, 9, 12, 15, 18, 19, 22, 24, 27, 30, 34, 38],
        "rango_max": 26, "corte": 7,
    },
    "Ansiedad generalizada": {
        "items": [5, 7, 14, 21, 23, 28, 33, 35, 37],
        "rango_max": 18, "corte": 9,
    },
    "Ansiedad de separación": {
        "items": [4, 8, 13, 16, 20, 25, 29, 31],
        "rango_max": 16, "corte": 5,
    },
    "Ansiedad / fobia social": {
        "items": [3, 10, 26, 32, 39, 40, 41],
        "rango_max": 14, "corte": 8,
    },
    "Evitación escolar": {
        "items": [2, 11, 17, 36],
        "rango_max": 8, "corte": 3,
    },
}

# Opciones tal como las usa este formulario específico (traducción
# argentina) — funcionalmente igual a la escala 0-2 genérica del
# instrumento, con su propia redacción.
OPCIONES = [
    ("Nunca o casi nunca ocurre", 0),
    ("Ocurre a veces o seguido", 1),
    ("Ocurre muy seguido o siempre", 2),
]

EDAD_MIN = 8
EDAD_MAX = 12

# Dimensiones componentes del "Puntaje total" — las 5 sub-escalas, en el
# mismo orden que SUBESCALAS. rango_max total = suma de los 5 rango_max
# (26+18+16+14+8 = 82, coincide con la literatura internacional del
# instrumento).
NOMBRE_DIMENSION_TOTAL = "Puntaje total"
CORTE_TOTAL = 25
RANGO_MAX_TOTAL = sum(d["rango_max"] for d in SUBESCALAS.values())

# ============================================================
# CONTENIDO DE INFORME — ver docstring del módulo. El párrafo de cada
# sub-escala es el real de "Interpretación por dimensiones" del informe de
# referencia (adaptado a "el/la evaluado/a"); conclusion/recomendacion
# viven SOLO en CONTENIDO_TOTAL (ver advertencia del módulo).
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluar la presencia de síntomas relacionados con la ansiedad infantil, identificando las "
    "principales áreas de manifestación ansiosa mediante la aplicación del cuestionario SCARED."
)

CONTENIDO_POR_SUBESCALA = {
    "Pánico / síntomas somáticos": (
        "El resultado obtenido evidencia presencia elevada de manifestaciones relacionadas con "
        "ansiedad y síntomas físicos. El/la evaluado/a podría experimentar preocupación "
        "acompañada de sensaciones corporales desagradables, temor ante determinadas situaciones "
        "y malestar físico asociado a estados de tensión."
    ),
    "Ansiedad generalizada": (
        "Se observa un nivel elevado de síntomas relacionados con preocupación frecuente. El/la "
        "evaluado/a podría presentar tendencia a anticipar situaciones negativas, preocuparse "
        "excesivamente por diferentes acontecimientos y experimentar dificultad para dejar de "
        "pensar en aquello que le genera inquietud."
    ),
    "Ansiedad de separación": (
        "El puntaje obtenido indica presencia elevada de indicadores relacionados con temor a "
        "separarse de figuras significativas. Podrían presentarse preocupaciones ante la "
        "posibilidad de que los padres o cuidadores se alejen, así como necesidad de permanecer "
        "cerca de ellos en determinadas situaciones."
    ),
    "Ansiedad / fobia social": (
        "Se evidencia un nivel elevado de indicadores relacionados con situaciones sociales. "
        "El/la evaluado/a podría mostrar inseguridad al interactuar con otras personas, temor a "
        "equivocarse o ser evaluado/a negativamente y cierta tendencia a evitar situaciones que "
        "impliquen exposición frente a compañeros u otras personas."
    ),
    "Evitación escolar": (
        "El resultado se encuentra elevado, sugiriendo posibles dificultades emocionales "
        "asociadas al contexto escolar. Podrían presentarse preocupación, resistencia o malestar "
        "ante la asistencia al colegio, especialmente cuando existen situaciones que el niño o la "
        "niña percibe como amenazantes o difíciles."
    ),
}

# (mínimo, máximo) del tramo del TOTAL -> {interpretacion, conclusion, recomendacion}.
CONTENIDO_TOTAL = {
    (0, CORTE_TOTAL - 1): {
        "interpretacion": (
            f"Puntaje total por debajo del punto de corte orientativo ({CORTE_TOTAL}). No indica "
            "ausencia de síntomas ansiosos, pero el conjunto de las 5 sub-escalas no alcanza, en "
            "suma, el nivel que la literatura asocia con mayor probabilidad de un trastorno de "
            "ansiedad. Debe revisarse igualmente si alguna sub-escala individual sí alcanzó su "
            "propio punto de corte (ver sección 5.2)."
        ),
        "conclusion": (
            "El puntaje total obtenido en el SCARED se encuentra por debajo del punto de corte "
            "orientativo, por lo que el resultado global no sugiere, por sí solo, la presencia "
            "significativa de sintomatología ansiosa. Los resultados obtenidos no permiten "
            "establecer por sí solos la ausencia de un trastorno de ansiedad."
        ),
        "recomendacion": (
            "- Revisar si alguna sub-escala individual alcanzó su propio punto de corte clínico, "
            "aun con un total no elevado.\n"
            "- Mantener una observación general del bienestar emocional del/de la evaluado/a.\n"
            "- De surgir nuevas señales de malestar, considerar una reevaluación."
        ),
    },
    (CORTE_TOTAL, RANGO_MAX_TOTAL): {
        "interpretacion": (
            f"Puntaje total en el punto de corte o por encima (≥{CORTE_TOTAL}), lo que sugiere la "
            "necesidad de realizar una evaluación complementaria. Los resultados obtenidos en el "
            "SCARED evidencian un nivel elevado de sintomatología ansiosa. Estos resultados deben "
            "interpretarse como indicadores de tamizaje y no como un diagnóstico por sí mismos: la "
            "puntuación elevada justifica complementar la información mediante entrevista "
            "psicológica, observación y otros procedimientos de evaluación."
        ),
        "conclusion": (
            "El/la evaluado/a obtuvo un puntaje total en el SCARED que se encuentra en el punto de "
            "corte orientativo o por encima. Se identifican indicadores elevados de ansiedad en "
            "una o más de las dimensiones evaluadas (pánico/síntomas somáticos, ansiedad "
            "generalizada, ansiedad de separación, ansiedad/fobia social y evitación escolar — ver "
            "sección 5.2 para el detalle por dimensión). Los resultados evidencian un perfil de "
            "sintomatología ansiosa elevada, por lo que se recomienda realizar una evaluación "
            "psicológica complementaria. Los resultados obtenidos no permiten establecer por sí "
            "solos un diagnóstico de trastorno de ansiedad."
        ),
        "recomendacion": (
            "- Realizar una entrevista psicológica complementaria para conocer las situaciones que "
            "generan mayor ansiedad en el/la evaluado/a.\n"
            "- Explorar la presencia de preocupaciones frecuentes, temores, síntomas físicos y "
            "dificultades relacionadas con la separación.\n"
            "- Favorecer espacios de comunicación donde pueda expresar sus preocupaciones y "
            "emociones.\n"
            "- Enseñar estrategias sencillas de respiración y relajación adecuadas para su edad.\n"
            "- Mantener rutinas familiares y escolares estables que favorezcan la sensación de "
            "seguridad.\n"
            "- Coordinar con los padres y docentes para identificar situaciones escolares que "
            "puedan estar relacionadas con el malestar emocional.\n"
            "- Reforzar progresivamente la participación en situaciones sociales y escolares, "
            "evitando respuestas que incrementen la evitación.\n"
            "- Realizar seguimiento psicológico y, de persistir o intensificarse los síntomas, "
            "considerar una evaluación especializada."
        ),
    },
}


def _asegurar_dimension_total(db, prueba) -> "models.Dimension | None":
    """Crea la dimensión COMPUESTA "Puntaje total" (`tipo_calculo=
    'suma_de_dimensiones'`, suma de las 5 sub-escalas ya cargadas) si
    todavía no existe — idempotente y puramente aditivo, mismo patrón que
    seed_sdq.py con "Dificultades Totales", aplicado DESPUÉS de que las 5
    sub-escalas ya existen (a diferencia de SDQ-CAS, que las crea en la
    misma corrida). Nunca toca las 5 Dimension 'items' existentes ni sus
    Pregunta — solo agrega una Dimension nueva sin preguntas propias y sus
    DimensionComponente. Devuelve la Dimension total (nueva o ya existente)."""
    dim_total = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre == NOMBRE_DIMENSION_TOTAL,
    ).first()
    if dim_total:
        print(f"↪️  '{NOMBRE_DIMENSION_TOTAL}' ya estaba cargada (id={dim_total.id}); no se toca.")
        return dim_total

    dimensiones_por_nombre = {
        d.nombre: d for d in db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).all()
    }
    faltantes = [n for n in SUBESCALAS if n not in dimensiones_por_nombre]
    if faltantes:
        print(f"⚠️  No se encontraron todas las sub-escalas ({faltantes}); no se puede crear '{NOMBRE_DIMENSION_TOTAL}'.")
        return None

    dim_total = models.Dimension(
        prueba_id=prueba.id,
        nombre=NOMBRE_DIMENSION_TOTAL,
        descripcion=(
            f"Suma de las 5 sub-escalas del SCARED-C (rango 0-{RANGO_MAX_TOTAL}), punto de corte "
            f"orientativo ≥{CORTE_TOTAL} (declarado por el informe de referencia usado para cargar "
            "este contenido; ver advertencia del módulo)."
        ),
        tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
    )
    db.add(dim_total)
    db.flush()

    for orden, nombre_dim in enumerate(SUBESCALAS, start=1):
        db.add(models.DimensionComponente(
            dimension_compuesta_id=dim_total.id,
            dimension_componente_id=dimensiones_por_nombre[nombre_dim].id,
            orden=orden,
        ))

    for (minimo, maximo), contenido in CONTENIDO_TOTAL.items():
        db.add(models.Baremo(
            dimension_id=dim_total.id,
            edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo,
            nivel="Elevado" if minimo == CORTE_TOTAL else "No elevado",
            interpretacion=contenido["interpretacion"],
            conclusion_sugerida=contenido["conclusion"],
            recomendacion_sugerida=contenido["recomendacion"],
            es_alerta=(minimo == CORTE_TOTAL),
        ))

    db.commit()
    print(f"✅ '{NOMBRE_DIMENSION_TOTAL}' creada (dimensión compuesta, id={dim_total.id}): "
          f"5 componentes, rango 0-{RANGO_MAX_TOTAL}, corte {CORTE_TOTAL}, con contenido de "
          "informe completo (interpretación/conclusión/recomendación en sus 2 tramos).")
    return dim_total


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default de la prueba y reescribe
    `interpretacion` del tramo "Elevado" de cada sub-escala con el párrafo
    real de "Interpretación por dimensiones" del informe de referencia —
    idempotente (interpretacion SIEMPRE se reemplaza si difiere del texto
    nuevo, mismo criterio ya usado en seed_gad7.py/seed_apgar_familiar.py;
    seguro solo porque no hay ninguna inscripción real de SCARED-C en la
    base a la fecha de esta carga). NO toca conclusion_sugerida/
    recomendacion_sugerida de ninguna sub-escala a propósito — ver
    advertencia del módulo."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")

    dimensiones = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre.in_(list(SUBESCALAS.keys())),
    ).all()
    baremos_actualizados = 0
    for dim in dimensiones:
        texto_nuevo = CONTENIDO_POR_SUBESCALA.get(dim.nombre)
        if not texto_nuevo:
            continue
        baremo_elevado = db.query(models.Baremo).filter(
            models.Baremo.dimension_id == dim.id, models.Baremo.nivel == "Elevado",
        ).first()
        if baremo_elevado and baremo_elevado.interpretacion != texto_nuevo:
            baremo_elevado.interpretacion = texto_nuevo
            baremos_actualizados += 1

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe (motivo, interpretación por sub-escala) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) 'Elevado' con interpretación real de sub-escala.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  SCARED-C ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_dimension_total(db, existente)
            _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala SCARED — Autoinforme del niño/a (SCARED-C)",
            instrucciones=(
                "A continuación hay una lista de oraciones que describen cómo se sienten las "
                "personas. Lee cada oración y marca con qué frecuencia te ocurre: nunca o casi "
                "nunca, a veces o seguido, o muy seguido o siempre."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=2,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # SCARED-C = autoinforme
            # Período de referencia del instrumento: últimos 3 meses.
            dias_minimos_entre_aplicaciones=90,
        )
        db.add(prueba)
        db.flush()

        total_preguntas = 0
        total_baremos = 0
        for nombre_dim, datos in SUBESCALAS.items():
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Sub-escala '{nombre_dim}' del SCARED-C — suma de {len(datos['items'])} "
                    f"ítems, rango 0-{datos['rango_max']}, punto de corte clínico ≥{datos['corte']} "
                    "(Birmaher et al., 1999)."
                ),
            )
            db.add(dimension)
            db.flush()

            for numero_item in datos["items"]:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=PREGUNTAS[numero_item],
                    orden=numero_item,  # número real del ítem en el protocolo (1-41)
                    es_inverso=False,
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                total_preguntas += 1

            corte = datos["corte"]
            rango_max = datos["rango_max"]
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=0, puntaje_maximo=corte - 1, nivel="No elevado",
                interpretacion=(
                    f"Puntaje por debajo del punto de corte clínico (<{corte}) en '{nombre_dim}'. "
                    "No indica ausencia de síntomas, pero no alcanza el nivel que la literatura "
                    "asocia con mayor probabilidad de trastorno de ansiedad en esta área."
                ),
                es_alerta=False,
            ))
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=corte, puntaje_maximo=rango_max, nivel="Elevado",
                interpretacion=(
                    f"Puntaje en el punto de corte clínico o por encima (≥{corte}) en '{nombre_dim}'. "
                    "Sugiere una elevación de síntomas en esta área que amerita evaluación clínica "
                    "más amplia; no constituye por sí solo un diagnóstico de trastorno de ansiedad."
                ),
                es_alerta=True,
            ))
            total_baremos += 2

        db.commit()
        print(f"✅ SCARED-C cargado: prueba id={prueba.id}, {len(SUBESCALAS)} dimensiones, "
              f"{total_preguntas} preguntas, {total_baremos} tramos de baremo "
              f"(edad {EDAD_MIN}-{EDAD_MAX}). "
              "SCARED-P (versión para padres) no cargada — pendiente del formulario literal.")
        _asegurar_dimension_total(db, prueba)
        _asegurar_contenido_informe(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando SCARED-C: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
