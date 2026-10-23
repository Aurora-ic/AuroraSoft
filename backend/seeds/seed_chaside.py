"""
Carga el catálogo PÚBLICO (institucion_id=None) del CHASIDE — prueba, 14
dimensiones (7 áreas vocacionales × Intereses/Aptitudes), 98 ítems dicotómicos
con sus 2 alternativas, y los tramos de baremo por sub-escala.

Es idempotente: si "CHASIDE" ya existe como prueba pública, no toca nada.
Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_chaside

⚠️ ESTRUCTURA GENUINAMENTE DISTINTA A PHQ-9/GAD-7 — NO ES UN DESCUIDO:
el CHASIDE no es una prueba clínica (la propia ficha técnica lo dice: "El
CHASIDE no es una prueba clínica de psicopatología... Puntos de corte
clínicos: NO APLICA"). Por eso:
  - Las 14 dimensiones (una por cada combinación área×tipo) NUNCA tienen
    es_alerta=True en ningún tramo — "Alto" en un área es un interés/aptitud
    marcado, no un indicador de riesgo. Una aplicación de CHASIDE nunca
    retiene el informe ni dispara el correo de alerta de riesgo.
  - No hay ReglaInterpretacion — la ficha técnica confirma que no existen
    ítems críticos.
  - modo_calculo sigue siendo "likert_suma" aunque los ítems sean
    dicotómicos (Sí=1/No=0): sumar valores de opción es exactamente la
    misma operación que sumar una escala Likert, el motor no necesita saber
    la diferencia. escala_minima=0/escala_maxima=1 por ítem.

⚠️ TEXTO DE LOS 98 ÍTEMS — SÍ ES LITERAL, a diferencia de seed_gad7.py:
la fuente aquí es el protocolo real de UCASAL (Universidad Católica de
Salta), que sí reproduce el cuadernillo completo — no un resumen temático.
Se usa tal cual. La ficha técnica complementaria (que si advertía sobre
derechos de autor) señalaba explícitamente que, de tenerse el cuadernillo
propio, correspondía extraer los ítems literalmente de ahí — eso es lo que
se hizo.

⚠️ MATRIZ DE CORRECCIÓN: SE USÓ LA DEL PROPIO PROTOCOLO UCASAL, NO LA DE
LA FICHA TÉCNICA SECUNDARIA — decisión de diseño explícita, no un
descuido. La ficha técnica complementaria advierte textualmente: "las
fuentes reproducidas en internet presentan inconsistencias en algunas
transcripciones de la matriz... conviene tomar como fuente maestra una
única matriz/protocolo y no mezclar versiones". Verificando ambas fuentes
se encontró exactamente esa inconsistencia: la ficha secundaria ubica el
ítem 30 en Aptitudes-C (Administrativas) y el ítem 89 en Aptitudes-H
(marcado con un asterisco de incertidumbre por la propia ficha), mientras
que la grilla original de UCASAL ubica el ítem 30 en Aptitudes-H y NO
incluye el ítem 89 en Aptitudes en absoluto (89 es un ítem de Intereses-H
en la matriz de UCASAL, y el resto de las 13 sub-escalas coincide
perfectamente entre ambas fuentes). Como el texto literal de los ítems
también viene de UCASAL, usar la matriz de UCASAL para todo mantiene una
única fuente consistente — mezclar la matriz de la otra ficha aquí habría
sido exactamente el error que la propia advertencia pedía evitar. Verificado
por código (no solo a mano) antes de cargar: la matriz de UCASAL cubre los
ítems 1-98 exactamente una vez, sin huecos ni duplicados.

⚠️ BAREMO: ES UN PUNTO DE CORTE INSTITUCIONAL, NO UNA NORMA PERUANA NI
INTERNACIONAL — cargado así a falta de algo mejor, documentado sin
ambigüedad. La ficha técnica reporta dos fuentes normativas y ninguna es
utilizable tal cual con el motor genérico de esta plataforma:
  1. Los puntos de corte de una institución educativa (Manizales, Colombia)
     — <5/5-7/>7 para Intereses (0-10) y <3/3/4 para Aptitudes (0-4) — la
     propia ficha aclara que "no deben presentarse automáticamente como
     baremo normativo internacional del CHASIDE". Es lo único que SÍ encaja
     con Baremo.puntaje_minimo/maximo (rango de puntaje directo), así que es
     lo que se carga aquí.
  2. Un baremo normativo 2026 de Honduras (715 estudiantes, San Pedro Sula)
     con percentiles y puntuaciones Z obtenidos por regresión lineal
     múltiple (ajustando por edad/sexo/centro educativo) — la propia ficha
     advierte "no debe confundirse con la puntuación convencional de 0-10
     para intereses y 0-4 para aptitudes" ni usarse como norma peruana. Este
     NO se carga: el modelo Baremo de hoy solo interpreta por rango de
     puntaje directo (`modo_interpretacion='rango'`); una norma por
     percentil/Z ajustada por regresión necesitaría un modo de
     interpretación nuevo que el motor no tiene todavía (ver
     Prueba.modo_interpretacion en modulos/educativo/models.py) — no es
     algo que deba improvisarse dentro de un script de carga.
No se encontró, y la ficha técnica lo confirma explícitamente, ningún
baremo peruano oficial vigente para el CHASIDE.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_AREAS/RECOMENDACION_
GENERICA_DEFAULT más abajo y _asegurar_contenido_informe_chaside):
a diferencia de la carga original de este script (que dejaba el informe
sin contenido, mismo criterio que seed_gad7.py en su momento), CHASIDE
ahora arma un informe condicionado al perfil real del evaluado, en vez de
un listado plano de 14 dimensiones — ver Prueba.agrupar_dimensiones_por_
area en modulos/educativo/models.py y crud._agrupar_dimensiones_por_area:

  - `Prueba.agrupar_dimensiones_por_area=True`: la sección 5.2 del PDF
    agrupa las 14 dimensiones por área a partir de la convención de nombre
    "Intereses — X: Nombre"/"Aptitudes — X: Nombre" (ya usada por este
    script desde su carga original) en tres bloques — Área de Intereses,
    Área de Aptitudes, Áreas Vocacionales Compatibles — mostrando solo las
    áreas con nivel "Alto", exactamente el criterio que se verificó contra
    un informe CHASIDE real de referencia (3 áreas con interés "Alto" + 4
    con aptitud "Alta" → la unión de ambos conjuntos, 4 áreas, es
    precisamente la lista de "Áreas Vocacionales Compatibles" que ese
    informe reporta).
  - `Baremo.interpretacion` del tramo "Alto" de cada una de las 14
    dimensiones se reescribe con un párrafo descriptivo propio del área
    (estilo/nivel de detalle calcado del informe de referencia) — los
    tramos "Bajo"/"Moderado" conservan el texto genérico original, porque
    el informe condicionado solo narra las áreas destacadas.
  - `Baremo.conclusion_sugerida` del tramo "Alto" (en Intereses Y en
    Aptitudes de la misma área, con el MISMO texto — crud._sin_duplicados
    colapsa la repetición cuando un área es "Alta" en ambos lados) agrega
    la lista de carreras sugeridas de esa área a la sección 6.
  - `Prueba.recomendacion_generica_default` carga las seis recomendaciones
    FIJAS del informe de referencia (investigar el perfil profesional,
    analizar objetivos y campos de acción, etc.) — a propósito NO dependen
    de qué área resultó destacada, igual que en el ejemplar: toda
    aplicación de CHASIDE las imprime en la sección 7, salvo que un
    profesional las sobrescriba vía `recomendaciones_override`.

Idempotente y aditivo, mismo criterio que seed_gad7.py: `interpretacion`
del tramo "Alto" SÍ se reemplaza si todavía tiene el texto genérico
original (detectable: no contiene ya el párrafo nuevo), seguro solo porque
a la fecha de esta carga no hay ninguna inscripción real de CHASIDE en la
base; `conclusion_sugerida`/`recomendacion_generica_default`/
`agrupar_dimensiones_por_area` solo se completan si todavía están
vacíos/en False, nunca se pisan si ya se habían configurado a mano.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): este archivo nunca definió `motivo_consulta_default`/
`tecnicas_adicionales` (quedaban NULL a propósito) — ahora SÍ quedan
cargados en la base, junto con el nuevo `observacion_conductual_default`,
porque `seeds/normalizar_contenido_comun.py` los fija al mismo texto
procedimental estándar en TODAS las pruebas públicas, sin necesidad de
tocar este script. Ejecutarlo después de cualquier
`python -m seeds.seed_chaside`.
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de Prueba)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de Prueba)
from modulos.educativo import models

NOMBRE_TECNICO = "CHASIDE"

# Texto LITERAL de los 98 ítems — protocolo UCASAL (Universidad Católica de
# Salta), tal como se entregó el cuadernillo completo. Ver advertencia arriba.
ITEMS = {
    1: "¿Aceptaría trabajar escribiendo artículos en la sección económica de un diario?",
    2: "¿Se ofrecería para organizar la despedida de soltero/a de uno/a de sus amigos/amigas?",
    3: "¿Le gustaría dirigir un proyecto de urbanización en su ciudad?",
    4: "¿A una frustración siempre opone un pensamiento positivo?",
    5: "¿Se dedicaría a socorrer personas accidentadas o atacadas por asaltantes?",
    6: "¿Cuando era niño/a, le interesaba saber cómo estaban construidos los juguetes?",
    7: "¿Le interesan más los misterios de la Naturaleza que los secretos de la tecnología?",
    8: "¿Escucha atentamente los problemas planteados por sus amigos/as?",
    9: "¿Se ofrecería para explicar algo a alguien?",
    10: "¿Es exigente y crítico con su trabajo?",
    11: "¿Le atrae armar puzzles o rompecabezas?",
    12: "¿Puede establecer la diferencia conceptual entre microeconomía y macroeconomía?",
    13: "¿Usar un uniforme lo/a haría sentirse distinto/a e importante?",
    14: "¿Participaría, como profesional, en un espectáculo de acrobacia aérea?",
    15: "¿Organiza su dinero de manera que siempre alcance hasta volver a cobrar?",
    16: "¿Convence fácilmente a otras personas sobre la validez de sus argumentos?",
    17: "¿Se encuentra informado/a sobre los nuevos descubrimientos sobre la Teoría del Big-Bang?",
    18: "¿Ante una situación de emergencia, actúa rápidamente?",
    19: "¿Cuando tiene que resolver un problema matemático, es perseverante hasta encontrar la solución?",
    20: "¿Si fuera convocado/a para planificar, organizar y/o dirigir un campo de deportes, aceptaría?",
    21: "¿Es Ud. él/la que pone un toque de alegría en las fiestas familiares?",
    22: "¿Cree que los detalles son tan importantes como el todo?",
    23: "¿Se sentiría a gusto trabajando en un Hospital?",
    24: "¿Le gustaría participar en el mantenimiento del orden ante grandes conflictos sociales o catástrofes?",
    25: "¿Pasaría varias horas leyendo un libro de su interés?",
    26: "¿Planifica cuidadosamente sus trabajos antes de iniciarlos?",
    27: "¿Mantiene una relación casi personal con su computadora?",
    28: "¿Disfruta modelando en arcilla?",
    29: "¿Ayuda habitualmente a los no videntes a cruzar la calle?",
    30: "¿Considera importante que, desde la escuela primaria, se fomente la actitud crítica y la participación activa?",
    31: "¿Acepta que las mujeres formen parte de las Fuerzas Armadas, bajo las mismas normas que los hombres?",
    32: "¿Le gustaría crear nuevas técnicas para descubrir las patologías de algunas enfermedades, usando un microscopio?",
    33: "¿Participaría en una campaña de prevención de la enfermedad de Chagas?",
    34: "¿Le interesa los temas relacionados con el pasado y con la evolución del hombre?",
    35: "¿Se incluiría en un proyecto de investigación de los movimientos sísmicos y sus consecuencias?",
    36: "¿Dedica algunas horas de la semana a la realización de actividad física?",
    37: "¿Le interesan las actividades de mucha acción y de reacción rápida en situaciones imprevistas o de peligro?",
    38: "¿Se ofrecería para colaborar como voluntario/a en los gabinetes especiales de la NASA?",
    39: "¿Le gusta más el trabajo manual que el intelectual?",
    40: "¿Estaría dispuesto/a a renunciar a un momento placentero para prestar su servicio como profesional?",
    41: "¿Participaría de un trabajo de investigación sobre la violencia social?",
    42: "¿Le gustaría trabajar en un laboratorio, mientras estudia?",
    43: "¿Arriesgaría su vida para salvar la de un desconocido?",
    44: "¿Le agradaría hacer un curso de primeros auxilios?",
    45: "¿Toleraría empezar tantas veces como fuera necesario hasta obtener un logro deseado?",
    46: "¿Distribuye los horarios adecuadamente para poder cumplir con lo planeado?",
    47: "¿Haría un curso para aprender a fabricar las piezas de máquinas o aparatos?",
    48: "¿Elegiría una profesión que lo/a obligara a estar alejado de su familia por algún tiempo?",
    49: "¿Se radicaría en una zona agrícola-ganadera?",
    50: "¿Cuando está trabajando en grupo, le entusiasma aportar ideas?",
    51: "¿Le resulta fácil coordinar un grupo de trabajo?",
    52: "¿Le resultan interesantes las Ciencias Biológicas?",
    53: "¿Si una empresa importante solicita un profesional para Gerente de Comercialización, le gustaría desempeñar esta función?",
    54: "¿Se incluiría en un proyecto nacional de desarrollo de la principal fuente de recursos de su provincia?",
    55: "¿Siente interés por descubrir cuáles son las causas que determinan ciertos fenómenos, aunque no altere su vida?",
    56: "¿Descubrió algún filósofo o escritor que haya expresado las mismas ideas de Ud. con anticipación?",
    57: "¿Desearía que le regalen algún instrumento musical?",
    58: "¿Aceptaría colaborar con el cumplimiento de las normas sociales en lugares públicos?",
    59: "¿Cree que sus ideas son importantes y hace lo posible para ponerlas en práctica?",
    60: "¿Cuando, en la casa, se descompone un artefacto, Ud. se dispone prontamente a repararlo?",
    61: "¿Formaría parte de un equipo de trabajo orientado a la preservación de la flora y de la fauna?",
    62: "¿Tiene por costumbre leer revistas relacionadas con los últimos avances científicos y tecnológicos en el área de la salud?",
    63: "¿Le parece importante y necesario preservar las raíces culturales de nuestro país?",
    64: "¿Le gustaría realizar una investigación que contribuyera a hacer más justa la distribución de la riqueza?",
    65: "¿Le gustaría realizar tareas de mantenimiento y conservación de un barco como, por ejemplo, pintura y conservación del casco, mantenimiento de los motores, etc.?",
    66: "¿Cree que el país debe poseer la más alta tecnología armamentista a cualquier precio?",
    67: "¿La libertad y la justicia son valores fundamentales en la vida?",
    68: "¿Aceptaría hacer práctica rentada en una industria de productos alimenticios en el sector de control de calidad?",
    69: "¿Considera que la salud pública debe ser prioritaria, gratuita y eficiente para todos?",
    70: "¿Le interesaría investigar sobre una nueva vacuna?",
    71: "¿Le gusta ocupar el rol de coordinador/a en un equipo de trabajo?",
    72: "¿En una discusión entre amigos(as), se ofrece como mediador/a?",
    73: "¿Está de acuerdo con la formación de un cuerpo de soldados profesionales?",
    74: "¿Lucharía por una causa justa hasta las últimas consecuencias?",
    75: "¿Le gustaría investigar científicamente sobre cultivos agrícolas?",
    76: "¿Haría un nuevo diseño de una prenda pasada de moda, ante una reunión imprevista?",
    77: "¿Visitaría un observatorio astronómico para conocerlo en acción?",
    78: "¿Le gustaría dirigir el área de importación/exportación de una empresa?",
    79: "¿Se siente inhibido/a al entrar en un lugar desconocido con gente que no conoce?",
    80: "¿Le gratificaría trabajar con niños?",
    81: "¿Haría un logotipo para un afiche de una campaña de prevención del SIDA?",
    82: "¿Dirigiría un grupo de teatro?",
    83: "¿Enviaría su Currículum a una empresa automotriz que solicita un gerente para el área de producción?",
    84: "¿Participaría de un grupo internacional de defensa de algo justo y benéfico para la humanidad?",
    85: "¿Se costearía sus estudios trabajando?",
    86: "¿Suele defender las llamadas «causas perdidas»?",
    87: "¿Ante una emergencia, participaría brindando su ayuda?",
    88: "¿Sabe el significado de las siglas ADN y ARN?",
    89: "¿Elegiría una carrera universitaria cuyo instrumento de trabajo fuera la utilización de un idioma extranjero?",
    90: "¿Trabajar con objetos le resulta más gratificante que trabajar con personas?",
    91: "¿Le gustaría ser el asesor contable de una empresa?",
    92: "¿Ante un llamado solidario, se ofrecería para cuidar a un enfermo?",
    93: "¿Se siente atraído/a por la investigación de los misterios del universo como, por ejemplo, la capa de ozono?",
    94: "¿El trabajo individual le resulta más rápido y efectivo que el trabajo grupal?",
    95: "¿Dedicaría parte de su tiempo a ayudar a los habitantes de zonas carenciadas?",
    96: "¿Cuando decora un ambiente, tiene en cuenta la combinación de los colores, el estilo preferido, etc.?",
    97: "¿Le gustaría trabajar como profesional dirigiendo la construcción de una empresa hidroeléctrica?",
    98: "¿Sabe el significado de la sigla PBI?",
}

AREAS = [
    ("C", "Administrativas y Contables"),
    ("H", "Humanísticas, Ciencias Jurídicas y Ciencias Sociales"),
    ("A", "Artísticas"),
    ("S", "Ciencias de la Salud"),
    ("I", "Ingenierías, Carreras Técnicas y Computación"),
    ("D", "Defensa y Seguridad"),
    ("E", "Ciencias Agrarias, de la Naturaleza y Exactas"),
]
AREAS_POR_CODIGO = dict(AREAS)

# Matriz de corrección — fuente: grilla propia del protocolo UCASAL (ver
# advertencia del módulo sobre la inconsistencia encontrada con la ficha
# secundaria). Verificada por código: cubre 1-98 exactamente una vez.
MATRIZ_INTERESES = {
    "C": [98, 12, 64, 53, 85, 1, 78, 20, 71, 91],
    "H": [9, 34, 80, 25, 95, 67, 41, 74, 56, 89],
    "A": [21, 45, 96, 57, 28, 11, 50, 3, 81, 36],
    "S": [33, 92, 70, 8, 87, 62, 23, 44, 16, 52],
    "I": [75, 6, 19, 38, 60, 27, 83, 54, 47, 97],
    "D": [84, 31, 48, 73, 5, 65, 14, 37, 58, 24],
    "E": [77, 42, 88, 17, 93, 32, 68, 49, 35, 61],
}
MATRIZ_APTITUDES = {
    "C": [15, 51, 2, 46],
    "H": [63, 30, 72, 86],
    "A": [22, 39, 76, 82],
    "S": [69, 40, 29, 4],
    "I": [26, 59, 90, 10],
    "D": [13, 66, 18, 43],
    "E": [94, 7, 79, 55],
}

OPCIONES = [("Sí", 1), ("No", 0)]

# (mínimo, máximo, nivel) — punto de corte institucional (Manizales,
# Colombia), NO normativo. es_alerta siempre False: el CHASIDE no es una
# prueba clínica. Ver advertencia del módulo.
BAREMO_INTERESES = [
    (0, 4, "Bajo"),
    (5, 7, "Moderado"),
    (8, 10, "Alto"),
]
BAREMO_APTITUDES = [
    (0, 2, "Bajo"),
    (3, 3, "Moderado"),
    (4, 4, "Alto"),
]

# ============================================================
# CONTENIDO DE INFORME — por área (ver docstring del módulo). Redactado por
# AuroraSoft en el mismo tono/nivel de detalle que el informe CHASIDE real
# usado como referencia para validar el diseño (no copiado de ningún
# estudiante concreto): un párrafo de intereses y uno de aptitudes por cada
# una de las 7 áreas del protocolo UCASAL, más sus carreras sugeridas. Solo
# se imprimen cuando esa área alcanza el tramo "Alto" — ver
# _asegurar_contenido_informe_chaside.
# ============================================================
CONTENIDO_AREAS = {
    "C": {
        "texto_interes": (
            "Se caracteriza por mostrar interés hacia actividades relacionadas con la gestión, la "
            "organización de recursos, el análisis numérico y la administración de proyectos u "
            "organizaciones. Presenta inclinación por el orden, la planificación financiera, la "
            "negociación comercial y la toma de decisiones orientadas a resultados."
        ),
        "texto_aptitud": (
            "Cuenta con aptitudes para el manejo de información cuantitativa, la organización "
            "metódica del trabajo, el razonamiento lógico-numérico, la capacidad de liderazgo y la "
            "gestión eficiente de recursos materiales y humanos."
        ),
        "carreras": [
            "Administración de Empresas", "Contabilidad", "Economía", "Marketing",
            "Negocios Internacionales", "Gestión Pública",
        ],
    },
    "H": {
        "texto_interes": (
            "Se caracteriza por mostrar interés hacia actividades relacionadas con la comunicación, "
            "la organización, las relaciones humanas y el análisis de información. Presenta "
            "inclinación por la precisión verbal, la justicia, el estudio de la conducta humana y la "
            "defensa de causas sociales."
        ),
        "texto_aptitud": (
            "Presenta aptitudes relacionadas con la precisión verbal, la organización, la relación "
            "de hechos, el orden, la justicia, la responsabilidad, el juicio crítico, la "
            "conciliación y la persuasión."
        ),
        "carreras": [
            "Derecho", "Comunicación Social", "Psicología", "Sociología", "Educación",
            "Ciencias Políticas", "Trabajo Social",
        ],
    },
    "A": {
        "texto_interes": (
            "Manifiesta interés por actividades relacionadas con la creatividad, la expresión y la "
            "innovación, evidenciando sensibilidad estética, imaginación, intuición, espontaneidad "
            "y capacidad para el trabajo detallista."
        ),
        "texto_aptitud": (
            "Cuenta con aptitudes para el trabajo estético, armónico, creativo y manual. Asimismo, "
            "evidencia habilidades visuales y auditivas, sensibilidad, imaginación, innovación e "
            "intuición."
        ),
        "carreras": [
            "Diseño Gráfico", "Artes Plásticas", "Música", "Arquitectura", "Actuación",
            "Diseño de Modas",
        ],
    },
    "S": {
        "texto_interes": (
            "Se evidencia una marcada inclinación hacia actividades de asistencia y servicio, "
            "destacando el interés por investigar, la precisión, la capacidad analítica, la "
            "percepción, la ayuda a otras personas, la rehabilitación y el cuidado de la salud."
        ),
        "texto_aptitud": (
            "Se observan capacidades relacionadas con la investigación, la asistencia, la "
            "precisión, la percepción, el análisis, la ayuda a los demás, el altruismo, la "
            "paciencia, la comprensión y la persuasión."
        ),
        "carreras": [
            "Medicina", "Enfermería", "Odontología", "Psicología Clínica", "Tecnología Médica",
            "Obstetricia",
        ],
    },
    "I": {
        "texto_interes": (
            "Se caracteriza por mostrar interés hacia el funcionamiento de aparatos, sistemas y "
            "tecnología, evidenciando curiosidad por el diseño, la construcción y la resolución de "
            "problemas técnicos."
        ),
        "texto_aptitud": (
            "Presenta aptitudes relacionadas con el razonamiento lógico-matemático, el manejo de "
            "herramientas y equipos, el pensamiento analítico-técnico, la perseverancia ante "
            "problemas complejos y la precisión en la ejecución de tareas."
        ),
        "carreras": [
            "Ingeniería de Sistemas", "Ingeniería Industrial", "Ingeniería Mecánica",
            "Ingeniería Civil", "Ciencias de la Computación", "Ingeniería Electrónica",
        ],
    },
    "D": {
        "texto_interes": (
            "Manifiesta interés por actividades de mucha acción, orden y disciplina, relacionadas "
            "con la protección de las personas, el mantenimiento del orden público y la actuación "
            "rápida ante situaciones de emergencia o conflicto."
        ),
        "texto_aptitud": (
            "Cuenta con aptitudes para actuar con rapidez y firmeza ante situaciones de emergencia, "
            "disciplina, capacidad de mando, resistencia física y disposición para asumir riesgos "
            "en beneficio de otros."
        ),
        "carreras": [
            "Ciencias Militares", "Ciencias Policiales", "Seguridad Ciudadana",
            "Gestión de Riesgos y Desastres", "Criminalística",
        ],
    },
    "E": {
        "texto_interes": (
            "Se evidencia interés por descubrir las causas de los fenómenos naturales, la "
            "investigación científica, el cuidado del medio ambiente, la agricultura y la "
            "exploración de los recursos naturales."
        ),
        "texto_aptitud": (
            "Presenta aptitudes para la investigación, la organización, el análisis y la síntesis, "
            "el razonamiento numérico, la clasificación metódica, la observación y la paciencia en "
            "la ejecución de tareas."
        ),
        "carreras": [
            "Ingeniería Agronómica", "Biología", "Química", "Ingeniería Ambiental",
            "Medicina Veterinaria", "Zootecnia",
        ],
    },
}

RECOMENDACION_GENERICA_DEFAULT = (
    "Se recomienda que el/la evaluado/a:\n"
    "•  Investigue el perfil profesional de las carreras de mayor interés.\n"
    "•  Analice los objetivos y campos de acción de cada profesión.\n"
    "•  Revise las principales actividades laborales que desempeñan los profesionales de dichas carreras.\n"
    "•  Consulte el plan de estudios y las asignaturas principales de cada programa académico.\n"
    "•  Participe en actividades de orientación vocacional y ferias universitarias que le permitan "
    "conocer de manera más cercana las opciones profesionales.\n"
    "•  Considere sus intereses personales, habilidades, valores y expectativas futuras antes de "
    "tomar una decisión definitiva respecto a su elección profesional."
)


def _asegurar_contenido_informe_chaside(db, prueba) -> None:
    """Completa el contenido del informe condicionado por área — idempotente
    y aditivo, mismo patrón que seed_gad7.py._asegurar_contenido_informe_
    gad7: `interpretacion` del tramo "Alto" se reemplaza SOLO si todavía
    tiene el texto genérico original (seguro porque no hay inscripciones
    reales de CHASIDE a la fecha de esta carga); conclusion_sugerida/
    recomendacion_generica_default/agrupar_dimensiones_por_area solo se
    completan si están vacíos, nunca se pisan si ya se habían configurado
    a mano."""
    cambios = []
    if not prueba.agrupar_dimensiones_por_area:
        prueba.agrupar_dimensiones_por_area = True
        cambios.append("agrupar_dimensiones_por_area")
    if not prueba.recomendacion_generica_default:
        prueba.recomendacion_generica_default = RECOMENDACION_GENERICA_DEFAULT
        cambios.append("recomendacion_generica_default")

    dimensiones = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).all()
    baremos_actualizados = 0
    for dim in dimensiones:
        m = re.match(r"^(Intereses|Aptitudes)\s+—\s+(.+?):\s*(.+)$", dim.nombre or "")
        if not m:
            continue
        tipo, codigo = m.group(1), m.group(2).strip()
        contenido_area = CONTENIDO_AREAS.get(codigo)
        if not contenido_area:
            continue
        nombre_area = AREAS_POR_CODIGO[codigo]

        baremo_alto = db.query(models.Baremo).filter(
            models.Baremo.dimension_id == dim.id, models.Baremo.nivel == "Alto",
        ).first()
        if not baremo_alto:
            continue

        cambio_tramo = False
        texto_narrativo = (
            contenido_area["texto_interes"] if tipo == "Intereses" else contenido_area["texto_aptitud"]
        )
        # ⚠️ puntaje_minimo/maximo vuelven de la BD como float (8.0, no 8) —
        # el texto genérico original se construyó con los enteros LITERALES
        # de BAREMO_INTERESES/BAREMO_APTITUDES (f"{8}" -> "8"), así que hay
        # que reproducir ese mismo formato aquí (int(...) -> "8", no "8.0")
        # o la comparación de abajo nunca coincide y esta función se queda
        # pisando solo conclusion_sugerida para siempre, en silencio.
        minimo_fmt = int(baremo_alto.puntaje_minimo)
        maximo_fmt = int(baremo_alto.puntaje_maximo)
        interpretacion_generica_original = (
            f"Puntaje {minimo_fmt}-{maximo_fmt} en "
            f"{'Intereses' if tipo == 'Intereses' else 'Aptitudes'} de {nombre_area}: nivel de "
            f"{'interés' if tipo == 'Intereses' else 'aptitud'} 'alto' en esta área. No es un "
            "indicador clínico."
        )
        if baremo_alto.interpretacion == interpretacion_generica_original:
            baremo_alto.interpretacion = texto_narrativo
            cambio_tramo = True
        if not baremo_alto.conclusion_sugerida:
            baremo_alto.conclusion_sugerida = (
                f"{nombre_area}: entre las opciones profesionales acordes con este perfil se "
                f"identifican carreras como {', '.join(contenido_area['carreras'][:-1])} y "
                f"{contenido_area['carreras'][-1]}, entre otras pertenecientes a esta área vocacional."
            )
            cambio_tramo = True
        if cambio_tramo:
            baremos_actualizados += 1

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe condicionado por área ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe condicionado por área completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) 'Alto' con interpretación/carreras sugeridas añadidas.")


def _verificar_matriz():
    """Falla ruidosamente ANTES de tocar la BD si la matriz tiene un hueco,
    un duplicado, o un ítem fuera de 1-98 — más vale un error acá que una
    dimensión con ítems mal asignados en producción."""
    todos = []
    for matriz in (MATRIZ_INTERESES, MATRIZ_APTITUDES):
        for lista in matriz.values():
            todos.extend(lista)
    faltantes = sorted(set(range(1, 99)) - set(todos))
    repetidos = sorted({x for x in todos if todos.count(x) > 1})
    if faltantes or repetidos or len(todos) != 98:
        raise RuntimeError(
            f"Matriz CHASIDE inconsistente — faltantes={faltantes} repetidos={repetidos} total={len(todos)}"
        )


def cargar():
    _verificar_matriz()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  CHASIDE ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_chaside(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Test de Orientación Vocacional CHASIDE",
            instrucciones=(
                "Lea atentamente cada pregunta y conteste SÍ o NO. Conteste a todas las "
                "preguntas sin omitir ninguna."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=1,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoevaluación
            # No es un instrumento de tamizaje repetido: se aplica una vez
            # por proceso de orientación vocacional, no cada 2 semanas.
            dias_minimos_entre_aplicaciones=180,
        )
        db.add(prueba)
        db.flush()

        total_preguntas = 0
        total_baremos = 0
        for codigo, nombre_area in AREAS:
            dim_intereses = models.Dimension(
                prueba_id=prueba.id,
                nombre=f"Intereses — {codigo}: {nombre_area}",
                descripcion=(
                    f"Sub-escala de Intereses del área {codigo} ({nombre_area}) — suma de "
                    "10 ítems dicotómicos (Sí=1/No=0), rango 0-10."
                ),
            )
            dim_aptitudes = models.Dimension(
                prueba_id=prueba.id,
                nombre=f"Aptitudes — {codigo}: {nombre_area}",
                descripcion=(
                    f"Sub-escala de Aptitudes del área {codigo} ({nombre_area}) — suma de "
                    "4 ítems dicotómicos (Sí=1/No=0), rango 0-4."
                ),
            )
            db.add(dim_intereses)
            db.add(dim_aptitudes)
            db.flush()

            for numero_item in MATRIZ_INTERESES[codigo]:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dim_intereses.id,
                    texto_pregunta=ITEMS[numero_item],
                    orden=numero_item,  # número real del ítem en el protocolo (1-98), no 1-10
                    es_inverso=False,
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                total_preguntas += 1

            for numero_item in MATRIZ_APTITUDES[codigo]:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dim_aptitudes.id,
                    texto_pregunta=ITEMS[numero_item],
                    orden=numero_item,
                    es_inverso=False,
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                total_preguntas += 1

            for minimo, maximo, nivel in BAREMO_INTERESES:
                db.add(models.Baremo(
                    dimension_id=dim_intereses.id,
                    edad_min=None, edad_max=None, sexo=None, poblacion=None,
                    puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                    interpretacion=(
                        f"Puntaje {minimo}-{maximo} en Intereses de {nombre_area}: nivel de "
                        f"interés '{nivel.lower()}' en esta área. No es un indicador clínico."
                    ),
                    es_alerta=False,
                ))
                total_baremos += 1
            for minimo, maximo, nivel in BAREMO_APTITUDES:
                db.add(models.Baremo(
                    dimension_id=dim_aptitudes.id,
                    edad_min=None, edad_max=None, sexo=None, poblacion=None,
                    puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                    interpretacion=(
                        f"Puntaje {minimo}-{maximo} en Aptitudes de {nombre_area}: nivel de "
                        f"aptitud '{nivel.lower()}' en esta área. No es un indicador clínico."
                    ),
                    es_alerta=False,
                ))
                total_baremos += 1

        db.commit()
        print(f"✅ CHASIDE cargado: prueba id={prueba.id}, {len(AREAS) * 2} dimensiones "
              f"(7 áreas × Intereses/Aptitudes), {total_preguntas} preguntas, "
              f"{total_baremos} tramos de baremo. Baremo institucional (no normativo) — "
              "ver advertencia en el docstring de este script.")
        _asegurar_contenido_informe_chaside(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando CHASIDE: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
