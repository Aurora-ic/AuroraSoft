"""
Carga el catálogo PÚBLICO (institucion_id=None) del RCADS-47 Youth — prueba,
6 dimensiones (sub-escalas clínicas), 47 ítems con sus 4 alternativas (texto
oficial en español, © 1998 Chorpita y Spence), y los tramos de baremo por
punto de corte de cada sub-escala (Chorpita et al., análisis ROC).

Es idempotente: si "RCADS-47" ya existe como prueba pública, no toca nada.
Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_rcads47

⚠️ CONTENIDO CON DERECHOS DE AUTOR — LICENCIA LIMITADA, NO DOMINIO PÚBLICO:
el RCADS está protegido por Bruce F. Chorpita y Susan H. Spence. La ficha
técnica que sustenta esta carga es explícita: "No está permitida la
distribución comercial... No se permite publicar el instrumento o sus
derivados en sitios web públicos... Se permite la distribución privada
dentro de una organización bajo las condiciones establecidas." Este script
carga el texto oficial (childfirst.ucla.edu, versión española 2018) para
uso INTERNO de esta plataforma — antes de cualquier uso comercial real con
estudiantes de un colegio cliente, alguien con autoridad para ello debe
confirmar que la licencia vigente con los autores cubre ese uso. No es una
decisión que este script, ni ningún código, pueda tomar por sí solo.

⚠️ SOLO RCADS-47 YOUTH (autoinforme) — RCADS-47 Caregiver, RCADS-25 Youth
y RCADS-25 Caregiver son, según la propia ficha técnica, "versiones
independientes" que no deben compartir la clave de corrección de esta.
Youth es la que se carga porque es la única con texto literal oficial
disponible en este momento. RCADS-47 Caregiver es el tercer caso real (tras
NICHQ Vanderbilt y SCARED-P) de instrumento pensado para
`informante_tipo="padre_madre"` — ver CLAUDE.md, sección "Informante" — que
queda pendiente hasta tener su formulario literal.

⚠️ SOLO SE CARGAN LOS 6 PUNTOS DE CORTE POR SUB-ESCALA (puntaje directo),
NO LAS PUNTUACIONES T NI LOS TOTALES AGREGADOS (Total Ansiedad/
Internalización) — dos límites reales y distintos del motor actual, no un
descuido:
  1. Las puntuaciones T oficiales dependen de grado escolar (EE.UU.) +
     sexo, vía tablas de conversión completas (puntaje bruto -> T) para
     cada combinación — esto no es un simple rango de puntaje por
     edad/sexo como ya soporta `Baremo` (edad_min/edad_max/sexo), es una
     función de conversión tabular distinta por grupo. El motor de hoy
     (`modo_interpretacion='rango'`) no tiene ningún mecanismo para esto;
     haría falta un modo de interpretación nuevo. Se usan en su lugar los
     puntos de corte directos de Chorpita et al. (análisis ROC en muestra
     clínica), que si encajan en el modelo de rango actual.
  2. ✅ "Total Ansiedad" (41 ítems, suma de TAS+FS+TAG+TP+TOC) y "Total
     Ansiedad+Depresión" (47 ítems, suma de las 6) YA SE CARGAN — ver
     `_asegurar_dimensiones_totales` más abajo, mismo mecanismo
     (`Dimension.tipo_calculo='suma_de_dimensiones'` + `DimensionComponente`)
     que cerró esta misma limitación en seed_scared.py ("Puntaje total").
     Rango resultante: 0-111 y 0-141 respectivamente (141 coincide con el
     máximo teórico del RCADS-47 completo reportado en la literatura —
     confirma que la suma de los 6 rango_max por sub-escala es correcta).
     **A diferencia de SCARED, estos dos totales NO llevan un tramo "Elevado"
     con punto de corte propio** — no existe, en ninguna fuente disponible
     para esta carga, un punto de corte DIRECTO (puntaje bruto) verificado
     para el total agregado: las únicas puntuaciones totales que el RCADS
     publica oficialmente son Puntuaciones T, que dependen de tablas de
     conversión por grado escolar y sexo (ver punto 1 de arriba, el mismo
     límite que ya impide cargar T-scores por sub-escala). Inventar un corte
     para el total sumando los 5/6 cortes individuales de ROC sería una
     aproximación no verificada — se prefiere cargar el total como dato
     informativo (aparece en 5.1/5.2 con un único tramo "Sin punto de corte
     verificado", es_alerta=False siempre) antes que fingir precisión
     clínica que no existe, mismo criterio de "no inventar contenido" que
     ya impidió cargar el baremo total completo de BARSIT. La interpretación
     clínica real sigue viniendo de los 6 puntos de corte YA VERIFICADOS por
     sub-escala (sin cambios).

⚠️ ÍTEM 37 ("Pienso acerca de la muerte") — REGLA DE ALERTA AÑADIDA POR
CRITERIO CLÍNICO PROPIO, NO ORDENADA POR LA FICHA TÉCNICA: la ficha solo
menciona el ítem 37 por un motivo psicométrico (cargó distinto en el
factor TAG en la validación española). Pero el contenido del ítem —
pensamientos sobre la muerte, en un niño o adolescente— es exactamente el
mismo tipo de señal que ya justificó la regla del ítem 9 del PHQ-9 en esta
plataforma (ideación de autolesión/muerte). Siguiendo ese mismo criterio ya
establecido (ver CLAUDE.md, "Interpretation rules: ReglaInterpretacion"),
se añade aquí una regla idéntica en mecanismo: cualquier respuesta
>0 en el ítem 37 fuerza es_alerta=True, independientemente del puntaje de
la sub-escala TAG. Esta es una decisión de seguridad clínica que el equipo
debe poder revisar y, si corresponde, desactivar explícitamente (la regla
quedaría con `activa=False` vía PATCH) — no se escondió dentro del cálculo
del tramo para que sea visible y editable.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_POR_SUBESCALA más abajo y
_asegurar_contenido_informe): `motivo_consulta_default` (genérico y
reutilizable, nunca el motivo específico de un caso) y `tecnicas_
adicionales="Entrevista, Observación"` (adaptados de un informe RCADS-47
real de referencia) quedan cargados. `Baremo.interpretacion`,
`conclusion_sugerida` y `recomendacion_sugerida` del tramo "Elevado" de
cada una de las 6 sub-escalas se cargan con contenido propio por área —
**a diferencia de PHQ-9/SCARED (conclusión/recomendación solo en el
total)**, aquí viven en cada sub-escala individual porque el RCADS-47
puede elevar varias sub-escalas clínicas independientes a la vez (el
informe de referencia, de hecho, eleva 3 de las 6 simultáneamente) y cada
una amerita su propio lineamiento de intervención (TCC con exposición para
Fobia Social, activación conductual para Depresión Mayor, etc.) — cuando
varias sub-escalas elevan a la vez, la sección 6/7 del informe concatena
el bloque de cada una (vía `crud._sin_duplicados`, que no colapsa textos
distintos). El texto de Fobia Social/Depresión Mayor/Ansiedad Generalizada
está adaptado del informe de referencia (despojado de contenido específico
de ESE paciente — autoverbalizaciones como "antisocial"/"manipuladora",
que pertenecen a `Inscripcion.motivo_consulta`/`observacion_conductual`
profesionales, nunca a contenido fijo de la prueba); los otros tres
(Ansiedad de Separación/Pánico/TOC) se extrapolaron en el mismo tono.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT`/`TECNICAS_ADICIONALES` de
arriba quedan como documentación histórica de cómo se derivaron
originalmente — el VALOR REALMENTE CARGADO en la base para esos dos campos
(y el nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que los sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_rcads47`.

🆕 CORRECCIÓN DE UN BUG REAL (auditoría crítica de contenido, sesión
2026-10-12): el tramo "No elevado" de las 6 sub-escalas (y, por extensión,
`Prueba.recomendacion_generica_default`) nunca habían tenido `conclusion_
sugerida`/`recomendacion_sugerida` — SOLO el tramo "Elevado" los tenía. Esto
dejaba las secciones 6/7 del PDF con el placeholder "no configurado" en el
caso MÁS FRECUENTE de una aplicación real (cribado negativo en las 6
sub-escalas simultáneamente), exactamente lo opuesto de lo que un informe
clínico debería priorizar. Corregido con `CONTENIDO_NO_ELEVADO_POR_
SUBESCALA` (contenido genérico, no específico de un caso — describe
ausencia de elevación, no inventa un hallazgo) y `RECOMENDACION_GENERICA_
DEFAULT` como red de seguridad adicional (mismo criterio ya usado en
CHASIDE/IPIP-RIASEC), ambos cargados por `_asegurar_contenido_informe`.
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

NOMBRE_TECNICO = "RCADS-47"

# Texto LITERAL — formulario oficial en español, © 1998 Chorpita y Spence
# (childfirst.ucla.edu, versión 2018), tal como lo entregó la institución.
PREGUNTAS = {
    1: "Me preocupo sobre las cosas",
    2: "Me siento triste o vacío/a",
    3: "Cuando tengo un problema, siento un malestar en el estómago",
    4: "Me preocupo cuando pienso que no hice algo bien",
    5: "Me da miedo tener que estar solo/a en casa",
    6: "Ya nada me divierte mucho",
    7: "Me da miedo cuando tengo un examen",
    8: "Me preocupo cuando pienso que alguien está enojado/a conmigo",
    9: "Me preocupa el estar alejado/a de mis padres",
    10: "Me molestan pensamientos malos o ridículos o imágenes en mi mente",
    11: "Tengo dificultades para dormir bien",
    12: "Me preocupa que vaya a salir mal en mi trabajo de la escuela",
    13: "Me preocupa que algo terrible le vaya a pasar a alguien de mi familia",
    14: "De repente siento como si no pudiera respirar aun sin haber alguna razón para sentirme así",
    15: "Tengo problemas con mi apetito",
    16: "Tengo que verificar constantemente que haya hecho las cosas bien (como el apagar la "
        "luz, o que la puerta esté cerrada con llave)",
    17: "Me da miedo el dormir solo/a",
    18: "Me cuesta trabajo ir a la escuela por las mañanas porque me siento nervioso/a o con miedo",
    19: "No tengo energía para hacer las cosas",
    20: "Me preocupa hacer el ridículo",
    21: "Estoy cansado/a con mucha frecuencia",
    22: "Me preocupa que me vayan a ocurrir cosas malas",
    23: "No parece que pueda quitarme los pensamientos malos o ridículos de la mente",
    24: "Cuando tengo algún problema, mi corazón late muy rápido",
    25: "No puedo pensar con claridad",
    26: "Comienzo a temblar o a estremecerme aun cuando no hay razón alguna para sentirme así",
    27: "Me preocupa de que algo malo me vaya a suceder",
    28: "Cuando tengo algún problema, me siento tembloroso/a",
    29: "Me siento que no valgo nada",
    30: "Me preocupa cometer errores",
    31: "Tengo que pensar en pensamientos especiales (como números o palabras) para evitar que "
        "sucedan cosas malas",
    32: "Me preocupa lo que los demás piensen de mí",
    33: "Me da miedo estar en lugares concurridos (con mucha gente como en los centros "
        "comerciales, las películas, los autobuses, sitios de recreo llenos)",
    34: "Me siento de repente con mucho miedo sin haber alguna razón",
    35: "Me preocupa de lo que vaya a pasar",
    36: "Me siento de repente mareado/a o débil aun cuando no haya razón para sentirme así",
    37: "Pienso acerca de la muerte",
    38: "Me siento con miedo si tengo que hablar en frente de la clase",
    39: "Me late el corazón muy rápido aun cuando no hay razón para sentirme así",
    40: "Me siento como que no quiero moverme",
    41: "Me preocupo de que de repente vaya a sentir miedo aun cuando no hay razón para sentirme así",
    42: "Tengo que hacer ciertas cosas una y otra vez (como lavarme las manos, limpiar, o poner "
        "las cosas en cierto orden)",
    43: "Me da miedo que vaya a hacer el ridículo en frente de las personas",
    44: "Tengo que hacer algunas cosas exactamente de la manera correcta para evitar que cosas "
        "malas sucedan",
    45: "Me preocupo cuando estoy en la cama en la noche",
    46: "Me daría miedo si tuviera que pasar la noche fuera de casa",
    47: "Me siento inquieto/a",
}

# Matriz de sub-escalas — fuente: ficha técnica (estructura original de 6
# factores, Chorpita et al., 2000). Verificada por código: cubre 1-47
# exactamente una vez (ver verificación previa a este script).
SUBESCALAS = {
    "Ansiedad de separación (TAS)": {
        "items": [5, 9, 17, 18, 33, 45, 46], "rango_max": 21, "corte": 5,
    },
    "Fobia social (FS)": {
        "items": [4, 7, 8, 12, 20, 30, 32, 38, 43], "rango_max": 27, "corte": 10,
    },
    "Ansiedad generalizada (TAG)": {
        "items": [1, 13, 22, 27, 35, 37], "rango_max": 18, "corte": 7,
    },
    "Pánico (TP)": {
        "items": [3, 14, 24, 26, 28, 34, 36, 39, 41], "rango_max": 27, "corte": 12,
    },
    "Obsesivo-compulsivo (TOC)": {
        "items": [10, 16, 23, 31, 42, 44], "rango_max": 18, "corte": 5,
    },
    "Depresión mayor (TDM)": {
        "items": [2, 6, 11, 15, 19, 21, 25, 29, 40, 47], "rango_max": 30, "corte": 11,
    },
}

OPCIONES = [
    ("Nunca", 0),
    ("Algunas Veces", 1),
    ("Con Frecuencia", 2),
    ("Siempre", 3),
]

EDAD_MIN = 8
EDAD_MAX = 18

ITEM_CRITICO_MUERTE = 37

# ============================================================
# DIMENSIONES COMPUESTAS — "Escala Total de Ansiedad" (5 sub-escalas,
# excluye Depresión Mayor) y "Escala Total (Ansiedad + Depresión)" (las 6).
# Ver advertencia del módulo: sin tramo "Elevado" propio, solo informativas.
# ============================================================
NOMBRE_DIMENSION_TOTAL_ANSIEDAD = "Escala Total de Ansiedad"
NOMBRE_DIMENSION_TOTAL_GENERAL = "Escala Total (Ansiedad + Depresión)"
DIMENSIONES_TOTAL_ANSIEDAD = [
    "Ansiedad de separación (TAS)", "Fobia social (FS)", "Ansiedad generalizada (TAG)",
    "Pánico (TP)", "Obsesivo-compulsivo (TOC)",
]
DIMENSIONES_TOTAL_GENERAL = DIMENSIONES_TOTAL_ANSIEDAD + ["Depresión mayor (TDM)"]

# ============================================================
# CONTENIDO DE INFORME — ver docstring del módulo. Fobia social/Depresión
# mayor/Ansiedad generalizada adaptados de un informe RCADS-47 real de
# referencia (despojado de contenido específico de ese paciente); los
# otros tres se extrapolaron en el mismo tono.
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluar la presencia de síntomas de ansiedad y depresión en el/la estudiante, identificando "
    "las principales áreas de manifestación mediante la aplicación del cuestionario RCADS-47."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

CONTENIDO_POR_SUBESCALA = {
    "Ansiedad de separación (TAS)": {
        "interpretacion": (
            "El resultado evidencia temor elevado a separarse de figuras significativas. "
            "Podrían presentarse preocupación ante la posibilidad de alejarse de sus padres o "
            "cuidadores, así como malestar significativo ante situaciones que impliquen separación."
        ),
        "conclusion": (
            "El/la evaluado/a presenta un nivel clínicamente elevado de Ansiedad de Separación, con "
            "temor significativo a separarse de figuras significativas."
        ),
        "recomendacion": (
            "- Trabajar de forma gradual la tolerancia a la separación en un marco terapéutico seguro.\n"
            "- Coordinar con la familia pautas consistentes que no refuercen la evitación.\n"
            "- Realizar seguimiento psicológico del caso."
        ),
    },
    "Fobia social (FS)": {
        "interpretacion": (
            "El resultado obtenido evidencia un temor marcado y persistente hacia situaciones de "
            "escrutinio social, miedo a la evaluación negativa y una tendencia a la evitación de "
            "interacciones interpersonales. El/la evaluado/a podría experimentar ansiedad social "
            "significativa que interfiere en su capacidad de generar y sostener vínculos "
            "interpersonales seguros."
        ),
        "conclusion": (
            "El/la evaluado/a presenta un nivel clínicamente elevado de Fobia Social, caracterizado "
            "por temor marcado y persistente a situaciones de escrutinio social y una tendencia a "
            "evitar interacciones interpersonales."
        ),
        "recomendacion": (
            "- Psicoterapia individual de enfoque cognitivo-conductual (TCC), priorizando la "
            "exposición gradual a situaciones sociales temidas.\n"
            "- Trabajar la reestructuración de pensamientos de evaluación negativa y "
            "autodesvalorización.\n"
            "- Favorecer espacios progresivos de participación social supervisada."
        ),
    },
    "Ansiedad generalizada (TAG)": {
        "interpretacion": (
            "Se observa un nivel de riesgo en la sintomatología de ansiedad generalizada. El/la "
            "evaluado/a podría experimentar preocupación excesiva y tensión persistente, lo que "
            "puede perpetuar la rigidez cognitiva y conductual y desgastar su dinámica de "
            "convivencia cotidiana."
        ),
        "conclusion": (
            "Se evidencia sintomatología de Ansiedad Generalizada en un rango de riesgo, que puede "
            "contribuir a la rigidez cognitiva y conductual del/de la evaluado/a."
        ),
        "recomendacion": (
            "- Enseñar estrategias de manejo de la preocupación excesiva y técnicas de relajación.\n"
            "- Favorecer rutinas estables que reduzcan la incertidumbre percibida.\n"
            "- Dar seguimiento psicológico a la evolución de los síntomas."
        ),
    },
    "Pánico (TP)": {
        "interpretacion": (
            "El resultado evidencia presencia elevada de síntomas de pánico. El/la evaluado/a "
            "podría experimentar episodios súbitos de miedo intenso acompañados de síntomas "
            "físicos (taquicardia, dificultad para respirar, mareo), incluso sin un desencadenante "
            "claro."
        ),
        "conclusion": (
            "El/la evaluado/a presenta un nivel clínicamente elevado de síntomas de Pánico, con "
            "episodios de miedo intenso acompañados de manifestaciones físicas."
        ),
        "recomendacion": (
            "- Psicoterapia individual orientada al manejo de episodios de pánico y sus síntomas "
            "físicos.\n"
            "- Enseñar técnicas de respiración y manejo de la activación fisiológica.\n"
            "- Evaluación por psiquiatría si los episodios son frecuentes o intensos."
        ),
    },
    "Obsesivo-compulsivo (TOC)": {
        "interpretacion": (
            "El resultado evidencia presencia elevada de síntomas obsesivo-compulsivos. Podrían "
            "presentarse pensamientos intrusivos recurrentes y/o conductas repetitivas "
            "(verificación, orden, limpieza) orientadas a reducir el malestar que generan dichos "
            "pensamientos."
        ),
        "conclusion": (
            "El/la evaluado/a presenta un nivel clínicamente elevado de síntomas Obsesivo-"
            "Compulsivos, con posibles pensamientos intrusivos y/o conductas repetitivas."
        ),
        "recomendacion": (
            "- Psicoterapia individual de enfoque cognitivo-conductual especializada en TOC "
            "(exposición con prevención de respuesta).\n"
            "- Evaluación por psiquiatría para valorar un abordaje complementario.\n"
            "- Dar seguimiento al impacto de estos síntomas en el funcionamiento diario."
        ),
    },
    "Depresión mayor (TDM)": {
        "interpretacion": (
            "El resultado se ubica en un rango clínicamente significativo. Podrían presentarse "
            "afecto plano, sentimientos de indefensión, anhedonia y pensamientos autocríticos "
            "severos, así como distorsiones cognitivas de autodesvalorización y un intento "
            "disfuncional de controlar el entorno cercano ante el temor al rechazo o al abandono."
        ),
        "conclusion": (
            "El/la evaluado/a presenta un nivel clínicamente significativo de síntomas depresivos, "
            "con posible afecto plano, anhedonia y pensamientos autocríticos."
        ),
        "recomendacion": (
            "- Psicoterapia individual de enfoque cognitivo-conductual (TCC), con activación "
            "conductual para la sintomatología depresiva.\n"
            "- Evaluación por psiquiatría para valorar un posible abordaje farmacológico "
            "complementario.\n"
            "- Seguimiento cercano del estado de ánimo y, de persistir o intensificarse los "
            "síntomas, priorizar la atención."
        ),
    },
}

# 🆕 CORRECCIÓN (auditoría de contenido, sesión 2026-10-12): el tramo "No
# elevado" (por debajo del punto de corte) de cada sub-escala NUNCA tenía
# conclusion_sugerida/recomendacion_sugerida — solo el tramo "Elevado" de
# arriba las tenía. Esto es justo el caso MÁS FRECUENTE en una aplicación
# real (cribado negativo en las 6 sub-escalas): si ninguna sub-escala
# alcanza "Elevado", el informe quedaba con las secciones 6/7 mostrando el
# placeholder "no configurado", precisamente en el caso sin riesgo — lo
# opuesto de lo que un informe debería priorizar. Contenido genérico
# (describe ausencia de elevación, no un hallazgo clínico específico que
# haya que adaptar de un ejemplar real — no viola "NO INVENTAR CONTENIDO").
CONTENIDO_NO_ELEVADO_POR_SUBESCALA = {
    "Ansiedad de separación (TAS)": {
        "conclusion": (
            "El puntaje obtenido en Ansiedad de Separación se encuentra por debajo del punto de "
            "corte clínico. No se evidencian indicadores significativos de temor excesivo a "
            "separarse de figuras significativas."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
    "Fobia social (FS)": {
        "conclusion": (
            "El puntaje obtenido en Fobia Social se encuentra por debajo del punto de corte "
            "clínico. No se evidencian indicadores significativos de temor a situaciones de "
            "escrutinio social o evitación de interacciones interpersonales."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
    "Ansiedad generalizada (TAG)": {
        "conclusion": (
            "El puntaje obtenido en Ansiedad Generalizada se encuentra por debajo del punto de "
            "corte clínico. No se evidencian indicadores significativos de preocupación excesiva "
            "o tensión persistente."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
    "Pánico (TP)": {
        "conclusion": (
            "El puntaje obtenido en Pánico se encuentra por debajo del punto de corte clínico. No "
            "se evidencian indicadores significativos de episodios de miedo intenso con "
            "manifestaciones físicas."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
    "Obsesivo-compulsivo (TOC)": {
        "conclusion": (
            "El puntaje obtenido en síntomas Obsesivo-Compulsivos se encuentra por debajo del "
            "punto de corte clínico. No se evidencian indicadores significativos de pensamientos "
            "intrusivos recurrentes ni conductas repetitivas."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
    "Depresión mayor (TDM)": {
        "conclusion": (
            "El puntaje obtenido en Depresión Mayor se encuentra por debajo del punto de corte "
            "clínico. No se evidencian indicadores significativos de afecto depresivo, anhedonia "
            "o pensamientos autocríticos."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del/de la estudiante. No se "
            "identifica necesidad de intervención adicional por este motivo."
        ),
    },
}

# 🆕 Red de seguridad (auditoría de contenido, sesión 2026-10-12): mismo
# criterio que ya usan CHASIDE/IPIP-RIASEC — una recomendación genérica de
# la prueba que SOLO se usa si, por algún motivo, ninguna de las 6
# sub-escalas aportó recomendacion_sugerida (ni "Elevado" ni "No elevado").
# Con el fix de arriba esto no debería dispararse en operación normal, pero
# cierra el hueco para cualquier caso no previsto (p. ej. un tramo
# reconfigurado a mano por una institución sin recomendación propia).
RECOMENDACION_GENERICA_DEFAULT = (
    "Se recomienda mantener el acompañamiento habitual del/de la estudiante y continuar con la "
    "observación periódica propia del seguimiento escolar. De presentarse cambios relevantes en "
    "su comportamiento o estado emocional, se sugiere una nueva evaluación o consulta con el área "
    "de psicología."
)


def _asegurar_dimensiones_totales(db, prueba) -> None:
    """Crea las dos dimensiones COMPUESTAS ("Escala Total de Ansiedad" y
    "Escala Total (Ansiedad + Depresión)") si todavía no existen —
    idempotente y puramente aditivo, mismo patrón que seed_scared.py._
    asegurar_dimension_total / seed_sdq.py con "Dificultades Totales".
    Nunca toca las 6 Dimension 'items' existentes ni sus Pregunta — solo
    agrega 2 Dimension nuevas sin preguntas propias y sus
    DimensionComponente. Cada una lleva un ÚNICO tramo de Baremo que cubre
    todo su rango (sin punto de corte propio — ver advertencia del
    módulo), así que nunca clasifica "Elevado"/"No elevado" a este nivel."""
    dimensiones_por_nombre = {
        d.nombre: d for d in db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).all()
    }
    creadas = []
    for nombre_total, componentes in (
        (NOMBRE_DIMENSION_TOTAL_ANSIEDAD, DIMENSIONES_TOTAL_ANSIEDAD),
        (NOMBRE_DIMENSION_TOTAL_GENERAL, DIMENSIONES_TOTAL_GENERAL),
    ):
        if nombre_total in dimensiones_por_nombre:
            print(f"↪️  '{nombre_total}' ya estaba cargada; no se toca.")
            continue
        faltantes = [n for n in componentes if n not in dimensiones_por_nombre]
        if faltantes:
            print(f"⚠️  No se encontraron todas las sub-escalas de '{nombre_total}' ({faltantes}); no se crea.")
            continue

        rango_max = sum(SUBESCALAS[n]["rango_max"] for n in componentes)
        dim_total = models.Dimension(
            prueba_id=prueba.id,
            nombre=nombre_total,
            descripcion=(
                f"Suma de {len(componentes)} sub-escalas del RCADS-47 Youth (rango 0-{rango_max}). "
                "Sin punto de corte directo propio verificado — ver advertencia en el docstring de "
                "este script; la clasificación clínica real sigue viniendo de las sub-escalas "
                "individuales."
            ),
            tipo_calculo=models.TIPO_CALCULO_SUMA_DE_DIMENSIONES,
        )
        db.add(dim_total)
        db.flush()

        for orden, nombre_dim in enumerate(componentes, start=1):
            db.add(models.DimensionComponente(
                dimension_compuesta_id=dim_total.id,
                dimension_componente_id=dimensiones_por_nombre[nombre_dim].id,
                orden=orden,
            ))

        db.add(models.Baremo(
            dimension_id=dim_total.id,
            edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
            puntaje_minimo=0, puntaje_maximo=rango_max, nivel="Sin punto de corte verificado",
            interpretacion=(
                f"Puntaje total = {rango_max} puntos posibles, suma de las sub-escalas que lo "
                "componen. Este puntaje agregado no tiene, a la fecha, un punto de corte directo "
                "verificado para esta plataforma (las puntuaciones T oficiales del RCADS dependen "
                "de tablas de conversión por grado escolar y sexo que no están cargadas). La "
                "interpretación clínica debe apoyarse en los puntos de corte YA VERIFICADOS de "
                "cada sub-escala individual (sección 5.2), no en este total."
            ),
            es_alerta=False,
        ))
        creadas.append(nombre_total)

    if creadas:
        db.commit()
        print(f"✅ Dimensión(es) compuesta(s) creada(s): {', '.join(creadas)}.")


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba, y
    reescribe interpretacion/conclusion_sugerida/recomendacion_sugerida del
    tramo "Elevado" de cada una de las 6 sub-escalas — idempotente:
    interpretacion SIEMPRE se reemplaza si difiere del texto nuevo (mismo
    criterio que seed_gad7.py/seed_apgar_familiar.py/seed_scared.py; seguro
    solo porque no hay ninguna inscripción real de RCADS-47 en la base a la
    fecha de esta carga); conclusion_sugerida/recomendacion_sugerida solo
    se completan si están vacíos."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")
    if not prueba.recomendacion_generica_default:
        prueba.recomendacion_generica_default = RECOMENDACION_GENERICA_DEFAULT
        cambios.append("recomendacion_generica_default")

    dimensiones = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre.in_(list(SUBESCALAS.keys())),
    ).all()
    baremos_actualizados = 0
    for dim in dimensiones:
        contenido = CONTENIDO_POR_SUBESCALA.get(dim.nombre)
        if contenido:
            baremo_elevado = db.query(models.Baremo).filter(
                models.Baremo.dimension_id == dim.id, models.Baremo.nivel == "Elevado",
            ).first()
            if baremo_elevado:
                cambio_tramo = False
                if baremo_elevado.interpretacion != contenido["interpretacion"]:
                    baremo_elevado.interpretacion = contenido["interpretacion"]
                    cambio_tramo = True
                if not baremo_elevado.conclusion_sugerida:
                    baremo_elevado.conclusion_sugerida = contenido["conclusion"]
                    cambio_tramo = True
                if not baremo_elevado.recomendacion_sugerida:
                    baremo_elevado.recomendacion_sugerida = contenido["recomendacion"]
                    cambio_tramo = True
                if cambio_tramo:
                    baremos_actualizados += 1

        # 🆕 Tramo "No elevado" — ver CONTENIDO_NO_ELEVADO_POR_SUBESCALA arriba.
        contenido_no_elevado = CONTENIDO_NO_ELEVADO_POR_SUBESCALA.get(dim.nombre)
        if contenido_no_elevado:
            baremo_no_elevado = db.query(models.Baremo).filter(
                models.Baremo.dimension_id == dim.id, models.Baremo.nivel == "No elevado",
            ).first()
            if baremo_no_elevado:
                cambio_tramo = False
                if not baremo_no_elevado.conclusion_sugerida:
                    baremo_no_elevado.conclusion_sugerida = contenido_no_elevado["conclusion"]
                    cambio_tramo = True
                if not baremo_no_elevado.recomendacion_sugerida:
                    baremo_no_elevado.recomendacion_sugerida = contenido_no_elevado["recomendacion"]
                    cambio_tramo = True
                if cambio_tramo:
                    baremos_actualizados += 1

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe (motivo, técnicas, interpretación/conclusión/recomendación) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) ('Elevado'/'No elevado') con interpretación/conclusión/"
          "recomendación.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  RCADS-47 ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_dimensiones_totales(db, existente)
            _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala Revisada de Ansiedad y Depresión Infantil (RCADS-47 Youth)",
            instrucciones=(
                "Encierra con un círculo la palabra que demuestre cuánto te sucede cada una de "
                "las siguientes cosas. No hay respuestas correctas o incorrectas."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=3,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # RCADS-47 Youth = autoinforme
            dias_minimos_entre_aplicaciones=90,
        )
        db.add(prueba)
        db.flush()

        pregunta_item_37 = None
        total_preguntas = 0
        total_baremos = 0
        for nombre_dim, datos in SUBESCALAS.items():
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Sub-escala '{nombre_dim}' del RCADS-47 Youth — suma de {len(datos['items'])} "
                    f"ítems, rango 0-{datos['rango_max']}, punto de corte clínico ≥{datos['corte']} "
                    "(Chorpita et al., análisis ROC en muestra clínica)."
                ),
            )
            db.add(dimension)
            db.flush()

            for numero_item in datos["items"]:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=PREGUNTAS[numero_item],
                    orden=numero_item,  # número real del ítem en el formulario oficial (1-47)
                    es_inverso=False,
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                total_preguntas += 1
                if numero_item == ITEM_CRITICO_MUERTE:
                    pregunta_item_37 = pregunta

            corte = datos["corte"]
            rango_max = datos["rango_max"]
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=0, puntaje_maximo=corte - 1, nivel="No elevado",
                interpretacion=(
                    f"Puntaje por debajo del punto de corte clínico (<{corte}) en '{nombre_dim}'."
                ),
                es_alerta=False,
            ))
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=corte, puntaje_maximo=rango_max, nivel="Elevado",
                interpretacion=(
                    f"Puntaje en el punto de corte clínico o por encima (≥{corte}) en '{nombre_dim}'. "
                    "Sugiere elevación de síntomas que amerita evaluación clínica más amplia; no "
                    "constituye por sí solo un diagnóstico."
                ),
                es_alerta=True,
            ))
            total_baremos += 2

        # 🆕 Regla de alerta del ítem 37 — ver advertencia del módulo arriba.
        # Mismo mecanismo exacto que el ítem 9 del PHQ-9: el motor genérico
        # (crud.evaluar_reglas_interpretacion) no sabe que esto es RCADS ni
        # que el ítem 37 habla de pensamientos sobre la muerte, solo evalúa
        # ámbito='item' + pregunta_id + operador '>' + valor 0.
        db.add(models.ReglaInterpretacion(
            prueba_id=prueba.id,
            ambito=models.AMBITO_ITEM,
            pregunta_id=pregunta_item_37.id,
            operador=">",
            valor_comparacion=0,
            accion=models.ACCION_ES_ALERTA,
            descripcion=(
                "Ítem 37 positivo (\"Pienso acerca de la muerte\"): requiere revisión "
                "profesional aunque la sub-escala de ansiedad generalizada no alcance su "
                "propio punto de corte. Regla añadida por criterio clínico de la plataforma, "
                "no exigida por la ficha técnica del instrumento — ver docstring de "
                "seed_rcads47.py."
            ),
            activa=True,
        ))

        db.commit()
        print(f"✅ RCADS-47 cargado: prueba id={prueba.id}, {len(SUBESCALAS)} dimensiones, "
              f"{total_preguntas} preguntas, {total_baremos} tramos de baremo "
              f"(edad {EDAD_MIN}-{EDAD_MAX}), 1 regla de interpretación (ítem 37). "
              "RCADS-47 Caregiver/RCADS-25 no cargadas — versiones independientes pendientes.")
        _asegurar_dimensiones_totales(db, prueba)
        _asegurar_contenido_informe(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando RCADS-47: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
