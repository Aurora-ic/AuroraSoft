"""
Carga el catálogo PÚBLICO (institucion_id=None) del SDQ-CAS — Cuestionario
de Capacidades y Dificultades, versión AUTOINFORME 11-17 años (Robert
Goodman, 1997/2005) — prueba, 5 dimensiones "items" (25 ítems, 5 por
dimensión, escala 0-2) más 1 dimensión COMPUESTA "Dificultades Totales"
(`Dimension.tipo_calculo='suma_de_dimensiones'` — ver "Dimensión compuesta"
en CLAUDE.md, primer uso real de ese mecanismo fuera de sus propios tests),
con dos criterios normativos cargados simultáneamente sobre esa compuesta
(`Baremo.criterio_normativo` — ver "Criterio normativo de Baremo").

Es idempotente: si "SDQ-CAS" ya existe como prueba pública, no toca nada
salvo asegurar el segundo criterio normativo. Para forzar una recarga,
borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_sdq

⚠️ HALLAZGO IMPORTANTE — LOS ÍTEMS PROSOCIALES NO DEBEN INVERTIRSE, AUNQUE
LA FICHA TÉCNICA LOS LISTE COMO INVERTIDOS (el error más significativo
encontrado en esta carga; verificado por una contradicción INTERNA
comprobable, no solo por conocimiento externo del SDQ oficial):

La ficha técnica (secciones "5. CLAVE Y PUNTUACIÓN" Y "CONFIGURACIÓN
RECOMENDADA PARA SOFTWARE", ambas internamente consistentes entre sí) listan
como invertidos los ítems "1, 4, 7, 9, 11, 14, 17, 20, 21 y 25" — es decir,
LOS CINCO ítems de Conducta Prosocial (1, 4, 9, 17, 20) MÁS los cinco ítems
positivamente redactados dentro de las cuatro escalas de dificultad (7, 11,
14, 21, 25). Aplicar la inversión a los cinco ítems prosociales es
INCORRECTO, y se puede demostrar con los datos de la propia ficha, sin
necesitar ninguna fuente externa: la sección "7. BAREMOS" (tabla A,
autoinforme) dice "Conducta prosocial: Normal 6–10 / Límite 5 / Anormal
0–4" — es decir, un puntaje ALTO en prosocial es "Normal" (bueno) y uno
BAJO es "Anormal" (dificultad). Si se invirtieran los 5 ítems prosociales
como pide la sección 5, alguien que responde "Absolutamente cierto" (el
valor más alto, 2 puntos) a los cinco ítems — "Intento ser agradable...",
"Normalmente comparto...", "Ofrezco ayuda...", "Trato bien a los niños
pequeños...", "A menudo me ofrezco para ayudar..." — obtendría, tras la
inversión, un puntaje prosocial de 0/10: el mínimo posible, clasificado
como "Anormal" por la tabla de la sección 7, para la persona que MÁS
fuertemente respalda CADA afirmación prosocial. Eso invierte el sentido
completo de la escala. Los cinco ítems de las escalas de dificultad que sí
están en la lista (7, 11, 14, 21, 25), en cambio, SÍ necesitan inversión —
y la misma prueba de contradicción lo confirma en sentido contrario: el
ítem 7 ("Por lo general soy obediente") pertenece a Problemas de Conducta
(alto=más problemas); si NO se invirtiera, alguien muy obediente ("Absolutamente
cierto") sumaría 2 puntos a su puntaje de problemas de conducta, el máximo,
exactamente lo opuesto de lo que ese ítem debería indicar.

Por lo tanto, el conjunto de ítems invertidos que SÍ se carga aquí es
**{7, 11, 14, 21, 25}** (cinco ítems, uno o dos por cada una de las cuatro
escalas de dificultad, ninguno en Prosocial) — NO los diez que lista la
ficha técnica secundaria. Esto coincide, además, con la guía de puntuación
pública oficial del SDQ (sdqinfo.org), que puntúa los ítems prosociales de
forma directa precisamente porque Prosocial es la única escala donde
"más" ya significa "mejor" sin necesitar inversión. **Se recomienda
verificar este punto contra la guía oficial antes de cualquier uso clínico
real** — queda documentado aquí con el razonamiento completo para que
pueda auditarse, no solo para que se redescubra.

⚠️ SOLO LA VERSIÓN AUTOINFORME 11-17 — PADRES/MAESTROS NO SE CARGAN (mismo
criterio que SCARED-P/RCADS-47 Caregiver, documentados como pendientes): la
ficha confirma que SDQ-Padres (P4-16) y SDQ-Maestros (T4-16) son
`Prueba.informante_tipo` distintos con ítems "adaptados gramaticalmente"
("Tiene en cuenta..." en vez de "Intento ser agradable...") y CON SUS
PROPIOS puntos de corte (tabla B y C de la sección 7, ambas distintas de
la tabla A) — pero la ficha técnica solo da dos ejemplos de la adaptación
gramatical, no el cuestionario completo de 25 ítems para esos dos
informantes. Cargarlos sin el texto literal completo sería inventar
contenido. Si se consiguen esos cuestionarios completos, cada uno es una
`Prueba` nueva con su propio `informante_tipo` ('padre_madre'/'docente') —
mismo patrón arquitectónico ya documentado en CLAUDE.md bajo "Informante:
who answers is not always who the result is about" — nunca una rama de
código nueva. Esto convertiría al SDQ en el primer caso real de ese
mecanismo con los tres informantes completos; sigue sin estarlo hoy.

⚠️ EDAD 11-17 EXPLÍCITA — mismo criterio que SCARED-C (8-12): la ficha
advierte repetidamente "no mezclar grupos de edad" (2-4 / 4-16/17 / 11-16/17
son versiones distintas, no la misma prueba con diferente filtro). Los
`Baremo` de esta carga llevan `edad_min=11, edad_max=17` explícitamente.

⚠️ SOLO LOS 25 ÍTEMS PRINCIPALES — EL SUPLEMENTO DE IMPACTO NO SE CARGA
(decisión explícita, no un olvido): la ficha aclara que el SDQ tiene un
"suplemento de impacto" (duración, malestar, interferencia) que "no debe
confundirse con los 25 ítems principales" — es un instrumento cualitativo
aparte, fuera del alcance de esta carga (y del motor genérico de
preguntas Likert de esta plataforma).

⚠️ "DIFICULTADES TOTALES" ES UNA DIMENSIÓN COMPUESTA REAL — primer uso de
`Dimension.tipo_calculo='suma_de_dimensiones'` fuera de sus propios tests
(ver "Dimensión compuesta" en CLAUDE.md): suma las 4 escalas de
dificultad (Síntomas Emocionales + Problemas de Conducta + Hiperactividad +
Problemas con Compañeros) y EXCLUYE deliberadamente Conducta Prosocial —
la propia ficha es explícita: "La escala de conducta prosocial no se
incluye en el total de dificultades." `DimensionComponente` referencia
exactamente esas 4, nunca las 5.

⚠️ CRITERIO NORMATIVO: DOS SISTEMAS DE BANDAS PARA EL MISMO TOTAL — tercer
caso real de `Baremo.criterio_normativo` (después de GAD-7/APGAR-FAMILIAR/
EAR), y la propia ficha técnica lo advierte explícitamente: "Este sistema
más reciente no debe mezclarse con el sistema tradicional de tres
categorías." El sistema tradicional de 3 bandas (Normal/Límite/Anormal,
sección 7A) se carga como criterio ACTIVO por defecto
(`criterio_normativo=NULL`); el sistema de 4 bandas (Cercano al promedio/
Ligeramente elevado/Alto/Muy alto, sección 8) se carga como segundo
criterio (`criterio_normativo="cuatro_bandas"`) — SOLO sobre "Dificultades
Totales", porque la ficha únicamente da la tabla de 4 bandas para el total,
no para las sub-escalas.

⚠️ SÍ ES UN INSTRUMENTO DE CRIBADO — `es_alerta=True` EN LOS TRAMOS
"ANORMAL"/"MUY ALTO" (a diferencia de CHASIDE/IPIP-RIASEC/EAR): la propia
ficha técnica se autodescribe como "instrumento de cribado para identificar
posibles dificultades emocionales, conductuales, atencionales y sociales"
— un uso y lenguaje mucho más cercano al de PHQ-9/GAD-7/APGAR-FAMILIAR que
al de los instrumentos no clínicos ya cargados. Los tramos "Anormal" de
las 4 escalas de dificultad y de "Dificultades Totales" (ambos criterios),
y el tramo "Anormal" (0-4, el BAJO) de Conducta Prosocial, quedan
`es_alerta=True`; "Normal"/"Límite" quedan en False. Ajustable después vía
`PATCH /educativo/baremos/{id}` si el protocolo clínico de un colegio
difiere.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_POR_DIMENSION/CONTENIDO_
TOTAL más abajo y _asegurar_contenido_informe): `motivo_consulta_default`
de la prueba (adaptado de un informe SDQ-CAS real de referencia) queda
cargado; `tecnicas_adicionales` se deja NULL a propósito — el ejemplar no
reporta ninguna técnica adicional real a la aplicación del propio
cuestionario (a diferencia de APGAR-FAMILIAR/RCADS-47, que sí listaban
Entrevista/Observación), así que no se inventa una.

`Baremo.interpretacion` se reescribe SOLO en el tramo clínicamente
relevante de cada dimensión "items" (el tramo "Anormal" de las 4 escalas
de dificultad; el tramo "Normal" de Conducta Prosocial — el favorable, por
ser la única escala donde la dirección está invertida, ver advertencia de
arriba) con el párrafo real de "Interpretación por dimensiones" del
ejemplar — los demás tramos conservan su texto genérico original (ya
tenían redacción clínica propia desde la carga inicial, a diferencia de
los tramos genéricos de CHASIDE). **`conclusion_sugerida`/
`recomendacion_sugerida` viven SOLO en los 3 tramos de "Dificultades
Totales" del criterio ACTIVO (criterio_normativo IS NULL), nunca en las 5
dimensiones "items"** — mismo criterio exacto que PHQ-9/SCARED-C: el
ejemplar da una única narrativa de conclusión/recomendación para el perfil
completo (no una por sub-escala, a diferencia de RCADS-47, cuyas 3
sub-escalas elevadas simultáneamente sí ameritaban cada una su propio
lineamiento) — el tramo "Anormal" está adaptado casi literalmente del
ejemplar (incluye sus 4 conclusiones y 7 recomendaciones); "Normal"/
"Límite" se extrapolaron en el mismo tono. El criterio `cuatro_bandas`
se deja deliberadamente sin este contenido, mismo criterio que el corte
peruano de GAD-7/el Sistema B de APGAR-FAMILIAR.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `tecnicas_adicionales` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_sdq`.
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

NOMBRE_TECNICO = "SDQ-CAS"
EDAD_MIN = 11
EDAD_MAX = 17

OPCIONES = [
    ("No es cierto", 0),
    ("Un tanto cierto", 1),
    ("Absolutamente cierto", 2),
]

# Texto LITERAL — sección 3 de la ficha técnica (versión española
# consultada, A11-17 autoinforme). Orden = numeración oficial 1-25.
PREGUNTAS = {
    1: "Intento ser agradable con los demás. Tengo en cuenta los sentimientos de las otras personas.",
    2: "Soy inquieto/a, hiperactivo/a, no puedo permanecer quieto/a por mucho tiempo.",
    3: "Suelo tener muchos dolores de cabeza, estómago o náuseas.",
    4: "Normalmente comparto con otros mis juguetes, chucherías, lápices, etc.",
    5: "Cuando me enfado, me enfado mucho y pierdo el control.",
    6: "Prefiero estar solo/a que con gente de mi edad.",
    7: "Por lo general soy obediente.",
    8: "A menudo estoy preocupado/a.",
    9: "Ofrezco ayuda cuando alguien resulta herido, disgustado o enfermo.",
    10: "Estoy todo el tiempo moviéndome, me muevo demasiado.",
    11: "Tengo un/a buen/a amigo/a por lo menos.",
    12: "Peleo mucho. Puedo hacer que los demás hagan lo que yo quiero.",
    13: "Me siento a menudo triste, desanimado o con ganas de llorar.",
    14: "Por lo general caigo bien a la otra gente de mi edad.",
    15: "Me distraigo con facilidad, me cuesta concentrarme.",
    16: "Me pongo nervioso/a con las situaciones nuevas, fácilmente pierdo la confianza en mí mismo/a.",
    17: "Trato bien a los niños/as más pequeños/as.",
    18: "A menudo me acusan de mentir o de hacer trampa.",
    19: "Otros chicos de mi edad se meten conmigo o se burlan de mí.",
    20: "A menudo me ofrezco para ayudar a padres, maestros, otros niños/as.",
    21: "Pienso las cosas antes de hacerlas.",
    22: "Tomo cosas que no son mías de casa, la escuela o de otros sitios.",
    23: "Me llevo mejor con adultos que con otros de mi edad.",
    24: "Tengo muchos miedos, me asusto fácilmente.",
    25: "Termino lo que empiezo, tengo buena concentración.",
}

# Las 5 dimensiones "items" — ver sección 6 de la ficha técnica.
DIMENSIONES_ITEMS = {
    "Síntomas Emocionales": [3, 8, 13, 16, 24],
    "Problemas de Conducta": [5, 7, 12, 18, 22],
    "Hiperactividad": [2, 10, 15, 21, 25],
    "Problemas con Compañeros": [6, 11, 14, 19, 23],
    "Conducta Prosocial": [1, 4, 9, 17, 20],
}

# Dimensiones que suman "Dificultades Totales" — EXCLUYE Prosocial a
# propósito (ver advertencia del módulo).
DIMENSIONES_DIFICULTADES = ["Síntomas Emocionales", "Problemas de Conducta", "Hiperactividad", "Problemas con Compañeros"]

# ⚠️ Ver el hallazgo documentado arriba: {7, 11, 14, 21, 25} — NO los 10 que
# lista (incorrectamente, para los 5 prosociales) la ficha técnica.
ITEMS_INVERSOS = {7, 11, 14, 21, 25}


def _verificar_matriz():
    """Falla ruidosamente ANTES de tocar la BD si DIMENSIONES_ITEMS no
    particiona exactamente 1-25, o si ITEMS_INVERSOS no es el conjunto
    verificado — mismo criterio defensivo que seed_chaside.py."""
    todos = [item for items in DIMENSIONES_ITEMS.values() for item in items]
    faltantes = sorted(set(range(1, 26)) - set(todos))
    repetidos = sorted({x for x in todos if todos.count(x) > 1})
    if faltantes or repetidos or len(todos) != 25:
        raise RuntimeError(f"Matriz SDQ-CAS inconsistente — faltantes={faltantes} repetidos={repetidos} total={len(todos)}")
    if ITEMS_INVERSOS != {7, 11, 14, 21, 25}:
        raise RuntimeError(f"ITEMS_INVERSOS inesperado: {sorted(ITEMS_INVERSOS)}")
    if not ITEMS_INVERSOS.isdisjoint(DIMENSIONES_ITEMS["Conducta Prosocial"]):
        raise RuntimeError("ITEMS_INVERSOS no debe incluir ningún ítem de Conducta Prosocial — ver hallazgo del módulo")
    if set(DIMENSIONES_DIFICULTADES) | {"Conducta Prosocial"} != set(DIMENSIONES_ITEMS.keys()):
        raise RuntimeError("DIMENSIONES_DIFICULTADES debe ser exactamente las 4 escalas de dificultad")


# (mínimo, máximo, nivel) por dimensión — sección 7A de la ficha técnica
# (autoinforme 11-16/17). es_alerta=True solo en "Anormal" — ver advertencia
# del módulo sobre por qué este SÍ es un instrumento de cribado.
BAREMOS_POR_DIMENSION = {
    "Síntomas Emocionales": [(0, 5, "Normal", False), (6, 6, "Límite", False), (7, 10, "Anormal", True)],
    "Problemas de Conducta": [(0, 3, "Normal", False), (4, 4, "Límite", False), (5, 10, "Anormal", True)],
    "Hiperactividad": [(0, 5, "Normal", False), (6, 6, "Límite", False), (7, 10, "Anormal", True)],
    "Problemas con Compañeros": [(0, 3, "Normal", False), (4, 5, "Límite", False), (6, 10, "Anormal", True)],
    # Dirección invertida: puntaje BAJO = mayor dificultad (ver advertencia del módulo).
    "Conducta Prosocial": [(0, 4, "Anormal", True), (5, 5, "Límite", False), (6, 10, "Normal", False)],
}

# "Dificultades Totales" — criterio tradicional de 3 bandas (sección 7A),
# ACTIVO por defecto (criterio_normativo=NULL).
BAREMOS_DIFICULTADES_TOTALES = [
    (0, 15, "Normal", False),
    (16, 19, "Límite", False),
    (20, 40, "Anormal", True),
]
# Segundo criterio — sistema de 4 bandas (sección 8), SOLO sobre el total.
CRITERIO_CUATRO_BANDAS = "cuatro_bandas"
BAREMOS_CUATRO_BANDAS = [
    (0, 14, "Cercano al promedio", False),
    (15, 17, "Ligeramente elevado", False),
    (18, 19, "Alto", False),
    (20, 40, "Muy alto", True),
]

_DESCRIPCION_DIMENSION = {
    "Síntomas Emocionales": "preocupación, tristeza, miedos, nerviosismo y quejas somáticas.",
    "Problemas de Conducta": "rabietas, pérdida de control, peleas, desobediencia, mentiras y apropiación de objetos.",
    "Hiperactividad": "inquietud, exceso de movimiento, distractibilidad y dificultades atencionales.",
    "Problemas con Compañeros": "dificultades en las relaciones con pares, aislamiento o rechazo.",
    "Conducta Prosocial": "comportamientos de ayuda, compartir y consideración hacia otras personas — AQUÍ una puntuación BAJA representa mayor dificultad.",
}


def _interpretacion_dimension(nombre_dim, minimo, maximo, nivel):
    return (
        f"Puntaje {minimo}-{maximo} en {nombre_dim}: nivel '{nivel.lower()}', relacionado con "
        f"{_DESCRIPCION_DIMENSION[nombre_dim]} El SDQ-CAS es un instrumento de cribado, no "
        "diagnóstico: este resultado no establece por sí mismo un diagnóstico clínico."
    )


def _interpretacion_total(minimo, maximo, nivel, etiqueta_criterio):
    return (
        f"Dificultades Totales {minimo}-{maximo}: nivel '{nivel.lower()}' según {etiqueta_criterio}. "
        "Suma de Síntomas Emocionales, Problemas de Conducta, Hiperactividad y Problemas con "
        "Compañeros (la Conducta Prosocial no se incluye en este total). Es un indicador de "
        "cribado, no una puntuación diagnóstica de un trastorno específico."
    )


# ============================================================
# CONTENIDO DE INFORME — ver docstring del módulo. El texto de las 4
# escalas de dificultad (tramo "Anormal") y de Conducta Prosocial (tramo
# "Normal") está adaptado de un informe SDQ-CAS real de referencia; el
# contenido del total (los 3 tramos del criterio tradicional) también.
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluar la presencia de posibles dificultades emocionales y conductuales, así como "
    "identificar recursos y capacidades presentes en el/la estudiante, mediante la aplicación "
    "del SDQ-CAS."
)

# (nombre_dimension, nivel_relevante) -> interpretacion. El nivel relevante
# es el clínicamente significativo de cada dimensión — "Anormal" para las
# 4 escalas de dificultad, "Normal" (el favorable) para Prosocial.
CONTENIDO_POR_DIMENSION = {
    ("Síntomas Emocionales", "Anormal"): (
        "El puntaje obtenido evidencia indicadores de riesgo en el área emocional. El/la "
        "evaluado/a podría presentar preocupación frecuente, tendencia a sentirse triste o "
        "inseguro/a y dificultades para manejar adecuadamente algunas situaciones que generan "
        "malestar emocional."
    ),
    ("Problemas de Conducta", "Anormal"): (
        "Se observa un nivel de riesgo que podría relacionarse con dificultades para seguir "
        "normas, controlar impulsos o regular determinadas respuestas conductuales. En "
        "situaciones de frustración podría presentar conductas oposicionistas o respuestas poco "
        "adecuadas para su contexto."
    ),
    ("Hiperactividad", "Anormal"): (
        "El resultado se encuentra en un rango de riesgo, sugiriendo posibles dificultades para "
        "mantener la atención, permanecer concentrado/a durante períodos prolongados y controlar "
        "el nivel de actividad. Estas características podrían interferir ocasionalmente con su "
        "desempeño académico y seguimiento de indicaciones."
    ),
    ("Problemas con Compañeros", "Anormal"): (
        "El puntaje obtenido indica riesgo en las relaciones con sus pares. Podrían presentarse "
        "dificultades para establecer o mantener interacciones adecuadas, así como tendencia a "
        "experimentar conflictos o sentirse poco integrado/a dentro del grupo."
    ),
    ("Conducta Prosocial", "Normal"): (
        "La puntuación obtenida se encuentra dentro de un rango adecuado, evidenciando la "
        "presencia de recursos positivos relacionados con la disposición para ayudar, compartir "
        "y considerar las necesidades de otras personas."
    ),
}

# (mínimo, máximo) del tramo del total (criterio tradicional, 3 bandas) ->
# {conclusion, recomendacion}.
CONTENIDO_TOTAL = {
    (0, 15): {
        "conclusion": (
            "El puntaje total de dificultades obtenido se encuentra dentro del rango normal. No "
            "se identifican, en conjunto, indicadores de riesgo emocional o conductual "
            "significativos; la conducta prosocial debe revisarse de forma independiente (ver "
            "sección 5.2), ya que es una escala con dirección invertida."
        ),
        "recomendacion": (
            "- Mantener las dinámicas de cuidado y acompañamiento actuales.\n"
            "- No se identifica necesidad de intervención adicional por este motivo."
        ),
    },
    (16, 19): {
        "conclusion": (
            "El puntaje total de dificultades obtenido se encuentra en un rango límite, cercano "
            "al punto de corte de riesgo."
        ),
        "recomendacion": (
            "- Dar seguimiento a la evolución de las dificultades identificadas en las "
            "sub-escalas.\n"
            "- Reforzar estrategias de regulación emocional y conductual de forma preventiva."
        ),
    },
    (20, 40): {
        "conclusion": (
            "El evaluado presenta un perfil general de riesgo en dificultades emocionales y "
            "conductuales. Se identifican indicadores de riesgo en las áreas evaluadas por "
            "encima del punto de corte; la conducta prosocial, cuando se mantiene en un rango "
            "adecuado, constituye un recurso positivo para el desarrollo de estrategias de "
            "adaptación y regulación emocional. El SDQ-CAS es un instrumento de tamizaje: estos "
            "resultados no constituyen por sí mismos un diagnóstico psicológico o clínico."
        ),
        "recomendacion": (
            "- Realizar seguimiento de las dificultades emocionales y conductuales "
            "identificadas.\n"
            "- Favorecer estrategias de regulación emocional y control de impulsos mediante "
            "actividades acordes con su edad.\n"
            "- Establecer rutinas claras y normas consistentes tanto en el hogar como en el "
            "contexto escolar.\n"
            "- Reforzar positivamente las conductas adecuadas y los avances observados.\n"
            "- Promover actividades que favorezcan las habilidades sociales y la interacción "
            "positiva con sus compañeros.\n"
            "- Coordinar con los padres y docentes para realizar un seguimiento de su "
            "comportamiento y adaptación escolar.\n"
            "- En caso de persistir o incrementarse las dificultades identificadas, considerar "
            "una evaluación psicológica complementaria."
        ),
    },
}


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default de la prueba; reescribe interpretacion
    del tramo clínicamente relevante de cada dimensión "items" (idempotente:
    SIEMPRE se reemplaza si difiere, mismo criterio que seed_gad7.py/
    seed_scared.py/seed_rcads47.py; seguro solo porque no hay ninguna
    inscripción real de SDQ-CAS en la base a la fecha de esta carga); y
    completa conclusion_sugerida/recomendacion_sugerida en los 3 tramos de
    "Dificultades Totales" del criterio ACTIVO (solo si están vacíos)."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")

    dimensiones = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre.in_(list(DIMENSIONES_ITEMS.keys())),
    ).all()
    baremos_actualizados = 0
    for dim in dimensiones:
        for (nombre_dim, nivel_relevante), texto_nuevo in CONTENIDO_POR_DIMENSION.items():
            if dim.nombre != nombre_dim:
                continue
            baremo = db.query(models.Baremo).filter(
                models.Baremo.dimension_id == dim.id, models.Baremo.nivel == nivel_relevante,
            ).first()
            if baremo and baremo.interpretacion != texto_nuevo:
                baremo.interpretacion = texto_nuevo
                baremos_actualizados += 1

    dim_total = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre == "Dificultades Totales",
    ).first()
    if dim_total:
        baremos_totales = db.query(models.Baremo).filter(
            models.Baremo.dimension_id == dim_total.id, models.Baremo.criterio_normativo.is_(None),
        ).all()
        for baremo in baremos_totales:
            rango = (int(baremo.puntaje_minimo), int(baremo.puntaje_maximo))
            contenido = CONTENIDO_TOTAL.get(rango)
            if not contenido:
                continue
            cambio_tramo = False
            if not baremo.conclusion_sugerida:
                baremo.conclusion_sugerida = contenido["conclusion"]
                cambio_tramo = True
            if not baremo.recomendacion_sugerida:
                baremo.recomendacion_sugerida = contenido["recomendacion"]
                cambio_tramo = True
            if cambio_tramo:
                baremos_actualizados += 1

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe (motivo, interpretación, conclusión/recomendación del total) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) con interpretación/conclusión/recomendación añadidas.")


def _asegurar_criterio_cuatro_bandas(db, prueba) -> None:
    """Idempotente y aditivo, mismo patrón que _asegurar_criterio_peru en
    seed_gad7.py."""
    dim_total = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre == "Dificultades Totales",
    ).first()
    if not dim_total:
        print("⚠️  SDQ-CAS no tiene 'Dificultades Totales' cargada todavía; no se puede añadir el segundo criterio.")
        return
    ya_existe = db.query(models.Baremo).filter(
        models.Baremo.dimension_id == dim_total.id,
        models.Baremo.criterio_normativo == CRITERIO_CUATRO_BANDAS,
    ).first()
    if ya_existe:
        print(f"↪️  El criterio normativo '{CRITERIO_CUATRO_BANDAS}' ya estaba cargado; no se toca.")
        return
    for minimo, maximo, nivel, es_alerta in BAREMOS_CUATRO_BANDAS:
        db.add(models.Baremo(
            dimension_id=dim_total.id,
            edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
            interpretacion=_interpretacion_total(minimo, maximo, nivel, "el sistema actualizado de 4 bandas"),
            es_alerta=es_alerta,
            criterio_normativo=CRITERIO_CUATRO_BANDAS,
        ))
    db.commit()
    print(f"✅ Criterio normativo '{CRITERIO_CUATRO_BANDAS}' añadido: {len(BAREMOS_CUATRO_BANDAS)} tramo(s). "
          "Sigue inactivo por defecto — Prueba.criterio_normativo_activo es NULL (usa el sistema "
          "tradicional de 3 bandas) hasta que se haga PATCH explícito.")


def cargar():
    _verificar_matriz()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  SDQ-CAS ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_criterio_cuatro_bandas(db, existente)
            _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Cuestionario de Capacidades y Dificultades (SDQ) — Autoinforme 11-17 años",
            instrucciones=(
                "Coloca una cruz en la opción que creas que mejor responde a cada una de las "
                "preguntas. Es importante que respondas a todas las preguntas lo mejor que "
                "puedas, pensando en cómo te sentiste o comportaste en los últimos seis meses."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=2,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoinforme adolescente
            # Mismo período de referencia que la escala (últimos 6 meses):
            # reaplicar antes de que termine esa ventana no aporta una
            # medición independiente (mismo criterio que GAD-7/PHQ-9 con
            # su propia ventana de 2 semanas).
            dias_minimos_entre_aplicaciones=180,
        )
        db.add(prueba)
        db.flush()

        dimensiones_creadas = {}
        for nombre_dim, items in DIMENSIONES_ITEMS.items():
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Sub-escala {nombre_dim} del SDQ-CAS — suma de 5 ítems (escala 0-2), rango 0-10."
                ),
            )
            db.add(dimension)
            db.flush()
            dimensiones_creadas[nombre_dim] = dimension

            for numero_item in items:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=PREGUNTAS[numero_item],
                    orden=numero_item,  # número real del ítem (1-25), no 1-5
                    es_inverso=numero_item in ITEMS_INVERSOS,
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))

            for minimo, maximo, nivel, es_alerta in BAREMOS_POR_DIMENSION[nombre_dim]:
                db.add(models.Baremo(
                    dimension_id=dimension.id,
                    edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                    puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                    interpretacion=_interpretacion_dimension(nombre_dim, minimo, maximo, nivel),
                    es_alerta=es_alerta,
                    criterio_normativo=None,
                ))

        # "Dificultades Totales" — dimensión COMPUESTA (ver advertencia del
        # módulo y "Dimensión compuesta" en CLAUDE.md). Se crea DESPUÉS de
        # sus componentes, para poder referenciar sus ids reales.
        dim_total = models.Dimension(
            prueba_id=prueba.id,
            nombre="Dificultades Totales",
            descripcion=(
                "Suma de Síntomas Emocionales + Problemas de Conducta + Hiperactividad + "
                "Problemas con Compañeros (rango 0-40). Conducta Prosocial NO se incluye."
            ),
            tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
        )
        db.add(dim_total)
        db.flush()

        for orden, nombre_dim in enumerate(DIMENSIONES_DIFICULTADES, start=1):
            db.add(models.DimensionComponente(
                dimension_compuesta_id=dim_total.id,
                dimension_componente_id=dimensiones_creadas[nombre_dim].id,
                orden=orden,
            ))

        for minimo, maximo, nivel, es_alerta in BAREMOS_DIFICULTADES_TOTALES:
            db.add(models.Baremo(
                dimension_id=dim_total.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=_interpretacion_total(minimo, maximo, nivel, "el sistema tradicional de 3 bandas"),
                es_alerta=es_alerta,
                criterio_normativo=None,
            ))

        db.commit()
        print(f"✅ SDQ-CAS cargado: prueba id={prueba.id}, 5 dimensiones 'items' + 1 compuesta "
              f"('Dificultades Totales'), 25 preguntas ({len(ITEMS_INVERSOS)} inversas: "
              f"{sorted(ITEMS_INVERSOS)} — NO los 10 que lista incorrectamente la ficha técnica "
              f"secundaria para Prosocial, ver advertencia del módulo), edad {EDAD_MIN}-{EDAD_MAX}.")

        _asegurar_criterio_cuatro_bandas(db, prueba)
        _asegurar_contenido_informe(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando SDQ-CAS: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
