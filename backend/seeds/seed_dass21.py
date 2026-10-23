"""
Carga el catálogo PÚBLICO (institucion_id=None) del DASS-21 — prueba, 3
dimensiones (Depresión/Ansiedad/Estrés, 7 ítems cada una), sus 4 alternativas
(escala 0-3), y los tramos de baremo por puntaje bruto de cada subescala.

Es idempotente: si "DASS-21" ya existe como prueba pública, no toca nada.
Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_dass21

⚠️ TEXTO LITERAL — tomado del documento completo (ClinikLab, Fundación
Universitaria Konrad Lorenz, Bogotá — cita la validación colombiana real:
Ruiz, García-Martín, Suárez-Falcón y Odriozola-González, 2017), que reproduce
los 21 ítems completos y la escala de respuesta íntegros, a diferencia de la
ficha técnica secundaria (que advierte "Texto literal completo de los 21
ítems: NO SE REPRODUCE COMPLETAMENTE... por restricciones de reproducción" y
solo da los dos primeros). Existen OTRAS traducciones españolas autorizadas
distintas (UNSW oficial, Bados López, García Valenzuela, IQVIA) con
pequeñas diferencias de redacción — la ficha técnica advierte explícitamente
"No confundir traducciones": reemplazar PREGUNTAS/OPCIONES por otra
traducción autorizada es un cambio de datos, no de estructura.

⚠️ LICENCIA — EL MÁS PERMISIVO DE LOS DOCE INSTRUMENTOS CARGADOS HASTA
AHORA: la página oficial de la UNSW/Psychology Foundation of Australia
declara el DASS en DOMINIO PÚBLICO, con los formularios "pueden descargarse
y copiarse sin restricciones" — la única condición real es que "las escalas
no pueden modificarse ni venderse con fines de lucro", que esta carga
respeta (se reproduce tal cual, sin alterar ítems ni escala, y AuroraSoft no
vende el instrumento en sí). `visible_para_clientes=True` sin reservas,
a diferencia de BARSIT (licencia restrictiva) o RCADS-47/IPIP-RIASEC
(licencia limitada).

⚠️ BAREMO POR SUBESCALA — VERIFICADO POR CÁLCULO, NO COPIADO DIRECTAMENTE DE
NINGUNA DE LAS DOS FUENTES (que se CONTRADICEN entre sí en Ansiedad): el
sistema oficial de corte del DASS se publica sobre el puntaje ×2 (para
hacerlo comparable con el DASS-42 original: Depresión 0-9/10-13/14-20/21-27/
28+; Ansiedad 0-7/8-9/10-14/15-19/20+; Estrés 0-14/15-18/19-25/26-33/34+ —
estos SÍ coinciden exactamente entre ambas fuentes). Para obtener los cortes
sobre el puntaje BRUTO (0-21, lo que esta plataforma almacena como
puntaje_directo) hay que aplicar esos cortes ×2 a cada entero bruto posible
(ej. bruto=5 -> 10 -> cae en "Moderada" del rango ×2 10-14), no dividir las
fronteras del rango ×2 entre 2 (eso produce fronteras fraccionarias sin
sentido, p. ej. 8/2=4 pero 9/2=4.5). Haciendo ese cálculo entero por entero:
  Depresión bruto: 0-4 Normal / 5-6 Leve / 7-10 Moderada / 11-13 Grave / 14-21 Extremadamente grave.
  Ansiedad  bruto: 0-3 Normal / 4-4 Leve / 5-7 Moderada / 8-9 Grave / 10-21 Extremadamente grave.
  Estrés    bruto: 0-7 Normal / 8-9 Leve / 10-12 Moderada / 13-16 Grave / 17-21 Extremadamente grave.
Depresión y Estrés coinciden exactamente con AMBAS fuentes (`dass-21-2.pdf` y
la ficha técnica secundaria). Ansiedad NO: `dass-21-2.pdf` da "4 leve, 5-7
moderada" (coincide con este cálculo), pero la ficha técnica secundaria da
"4-5 leve, 6-7 moderada" (su propia tabla de puntaje bruto, inconsistente con
su propia tabla ×2 de la que debería derivarse) — se cargó el valor
verificado por cálculo exacto (y confirmado por `dass-21-2.pdf`), no el de la
ficha técnica secundaria.

⚠️ es_alerta: DECISIÓN CLÍNICA EXPLÍCITA DE ESTA PLATAFORMA, NO UN VALOR
DADO POR LA FUENTE — a diferencia de PHQ-9/GAD-7 (que sí declaran un único
punto de corte de cribado), el DASS-21 no declara un umbral "positivo"
único: solo describe 5 niveles de severidad y dice "a mayor puntaje, mayor
sintomatología". Mismo criterio ya usado en esta plataforma (GAD-7: Moderada
y Severa retienen informe; Leve y Mínima no): aquí Moderada/Grave/
Extremadamente grave retienen el informe (`es_alerta=True`) y Normal/Leve
no, en las TRES subescalas. Ajustable después vía PATCH /educativo/baremos/{id}.

⚠️ ÍTEM 21 CON ReglaInterpretacion PROPIA DE ESTA PLATAFORMA — NO EXIGIDA POR
LA FUENTE, mismo mecanismo que el ítem 9 de PHQ-9/ítem 37 de RCADS-47, pero
MÁS CAUTELOSA en su redacción porque la propia ficha técnica es explícita:
"el DASS-21 no constituye por sí mismo una evaluación específica de riesgo
suicida" y "Criterio automático de riesgo suicida: NO ESPECIFICADO EN LA
FUENTE". El ítem 21 ("Sentí que la vida no tenía ningún sentido") aborda
desesperanza/falta de sentido — un correlato de riesgo reconocido en la
literatura clínica, aunque el instrumento no sea una herramienta de tamizaje
suicida — por lo que cualquier respuesta positiva fuerza `es_alerta=True`
sobre Depresión aunque el puntaje de esa subescala quede en un tramo sin
alerta. La descripción de la regla deja explícito que esto es una señal de
revisión profesional, nunca una determinación de riesgo suicida. Revisable/
desactivable vía PATCH /educativo/reglas/{id} si el equipo clínico no la
quiere.

⚠️ SIN DIMENSIÓN "TOTAL": la fuente es explícita — "No se debe convertir el
DASS-21 en una única escala diagnóstica... No existe una tabla oficial de
severidad para la suma de los 21 ítems" — por eso NO se carga ninguna
`Dimension(tipo_calculo='suma_de_dimensiones')` para un total global,
a diferencia de SDQ-CAS. Las tres subescalas se interpretan siempre por
separado.

⚠️ SIN SEGUNDO CRITERIO NORMATIVO: existe evidencia psicométrica peruana
reciente (2025, 1,163 universitarios de Lima, estructura trifactorial
confirmada, fiabilidad >.90), pero esa evidencia respalda usar los cortes
tradicionales en población peruana — no propone una tabla de corte
alternativa con valores propios. Por eso, a diferencia de GAD-7/APGAR-
FAMILIAR/EAR/SDQ-CAS, aquí no hay nada que cargar como segundo
`criterio_normativo` (cargar un segundo criterio inventado violaría "NO
INVENTAR CONTENIDO"). `edad_min`/`edad_max`/`sexo`/`poblacion` quedan
`NULL` — la fuente no establece un rango de edad universal verificable (una
ficha peruana secundaria da 18-80 años, pero advierte explícitamente que
"no debe tratarse como límite universal").

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más abajo y
_asegurar_contenido_informe_dass21, mismo patrón idempotente/aditivo que
seed_gad7.py._asegurar_contenido_informe_gad7): `motivo_consulta_default`
adapta la sección "Motivo de evaluación" de un informe DASS-21 real de
referencia (caso con Depresión leve / Ansiedad extremadamente grave /
Estrés moderado) al mismo molde institucional de los demás instrumentos.
`tecnicas_adicionales` queda NULL a propósito — ese ejemplar no reporta
ninguna técnica adicional a la aplicación del propio cuestionario (mismo
criterio que SDQ-CAS: no se inventa una lista de "Entrevista/Observación"
que la fuente no da).

Por tratarse de TRES subescalas independientes sin dimensión total (ver
advertencia de arriba), cada una de las 15 combinaciones dimensión×tramo
tiene su propio `conclusion_sugerida`/`recomendacion_sugerida`
AUTOCONTENIDO — no asume que las otras dos subescalas estén simultáneamente
elevadas, mismo criterio ya usado para las 3 sub-escalas de RCADS-47 ("cuyas
3 sub-escalas elevadas simultáneamente sí ameritaban cada una su propio
lineamiento"). El ejemplar de referencia da texto real para exactamente un
tramo por dimensión — Depresión "Leve" (5-6), Ansiedad "Extremadamente
grave" (10-21) y Estrés "Moderada" (10-12) — adaptado casi literalmente de
sus secciones "Interpretación de las áreas predominantes"/"VII.
Recomendaciones"; los otros 12 tramos (4 por dimensión) se extrapolaron en
el mismo tono y nivel de detalle, igual que hizo seed_gad7.py con sus 4
bandas a partir de un único tramo real ("Severa"). `Baremo.interpretacion`
(el párrafo base genérico ya existente) no se tocó — la narrativa clínica
vive en conclusion_sugerida/recomendacion_sugerida, igual que seed_phq9.py.

⚠️ PERIODO DE RECALL = LA SEMANA ANTERIOR (igual que PHQ-9/CES-DC, no 2
semanas como GAD-7): `dias_minimos_entre_aplicaciones=7`.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `tecnicas_adicionales` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_dass21`.
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

NOMBRE_TECNICO = "DASS-21"

OPCIONES = [
    ("No me ha ocurrido", 0),
    ("Me ha ocurrido un poco, o durante parte del tiempo", 1),
    ("Me ha ocurrido bastante, o durante una buena parte del tiempo", 2),
    ("Me ha ocurrido mucho, o la mayor parte del tiempo", 3),
]

# Texto literal de los 21 ítems (ClinikLab/Konrad Lorenz) — orden = numeración oficial.
ITEMS = [
    (1, "Me ha costado mucho descargar la tensión"),
    (2, "Me di cuenta que tenía la boca seca"),
    (3, "No podía sentir ningún sentimiento positivo"),
    (4, "Se me hizo difícil respirar"),
    (5, "Se me hizo difícil tomar la iniciativa para hacer cosas"),
    (6, "Reaccioné exageradamente en ciertas situaciones"),
    (7, "Sentí que mis manos temblaban"),
    (8, "He sentido que estaba gastando una gran cantidad de energía"),
    (9, "Estaba preocupado por situaciones en las cuales podía tener pánico o en las que podría hacer el ridículo"),
    (10, "He sentido que no había nada que me ilusionara"),
    (11, "Me he sentido inquieto"),
    (12, "Se me hizo difícil relajarme"),
    (13, "Me sentí triste y deprimido"),
    (14, "No toleré nada que no me permitiera continuar con lo que estaba haciendo"),
    (15, "Sentí que estaba al punto de pánico"),
    (16, "No me pude entusiasmar por nada"),
    (17, "Sentí que valía muy poco como persona"),
    (18, "He tendido a sentirme enfadado con facilidad"),
    (19, "Sentí los latidos de mi corazón a pesar de no haber hecho ningún esfuerzo físico"),
    (20, "Tuve miedo sin razón"),
    (21, "Sentí que la vida no tenía ningún sentido"),
]

ITEMS_DEPRESION = {3, 5, 10, 13, 16, 17, 21}
ITEMS_ANSIEDAD = {2, 4, 7, 9, 15, 19, 20}
ITEMS_ESTRES = {1, 6, 8, 11, 12, 14, 18}
ITEM_SEGURIDAD_DEPRESION = 21  # "Sentí que la vida no tenía ningún sentido" — ver docstring

# (mínimo, máximo, nivel, es_alerta) — puntaje BRUTO (0-21), derivado por
# cálculo entero de los cortes oficiales ×2 (ver docstring). es_alerta es
# decisión de esta plataforma (ver docstring), no dada por la fuente.
BAREMO_DEPRESION = [
    (0, 4, "Normal", False),
    (5, 6, "Leve", False),
    (7, 10, "Moderada", True),
    (11, 13, "Grave", True),
    (14, 21, "Extremadamente grave", True),
]
BAREMO_ANSIEDAD = [
    (0, 3, "Normal", False),
    (4, 4, "Leve", False),
    (5, 7, "Moderada", True),
    (8, 9, "Grave", True),
    (10, 21, "Extremadamente grave", True),
]
BAREMO_ESTRES = [
    (0, 7, "Normal", False),
    (8, 9, "Leve", False),
    (10, 12, "Moderada", True),
    (13, 16, "Grave", True),
    (17, 21, "Extremadamente grave", True),
]

DEFINICION_DIMENSIONES = [
    ("Depresión", ITEMS_DEPRESION, BAREMO_DEPRESION),
    ("Ansiedad", ITEMS_ANSIEDAD, BAREMO_ANSIEDAD),
    ("Estrés", ITEMS_ESTRES, BAREMO_ESTRES),
]

# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES DE
# CONTENIDO DEL INFORME") — ver advertencia ✅ de cabecera. motivo_consulta_
# default adapta "II. MOTIVO DE EVALUACIÓN" de un informe DASS-21 real de
# referencia al mismo molde institucional de PHQ-9/GAD-7.
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para medir la presencia y severidad de síntomas de "
    "depresión, ansiedad y estrés reportados por el estudiante, con la finalidad de identificar "
    "posibles indicadores de malestar psicológico y orientar las estrategias de intervención o "
    "soporte correspondientes, en el marco de una campaña de evaluación psicométrica "
    "institucional."
)

# (nombre_dimension, (mínimo, máximo)) -> {conclusion, recomendacion}. Cada
# entrada es AUTOCONTENIDA (no asume que otra subescala esté simultáneamente
# elevada — ver advertencia ✅ de cabecera). Los tramos marcados "adaptado del
# ejemplar" reproducen casi literalmente el párrafo real de referencia; los
# demás se extrapolaron en el mismo tono.
CONTENIDO_INFORME_POR_TRAMO = {
    ("Depresión", (0, 4)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Depresión se encuentra dentro del rango "
            "normal. No se identifican indicadores significativos de pérdida de interés, "
            "anhedonia o desánimo relacionados con un cuadro depresivo."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del estudiante. No se identifica "
            "necesidad de intervención adicional por este motivo; se sugiere una nueva evaluación "
            "de tamizaje en el siguiente periodo académico o ante cambios observables."
        ),
    },
    ("Depresión", (5, 6)): {
        # Adaptado casi literalmente de "Dimensión Depresión (D)" del ejemplar.
        "conclusion": (
            "El puntaje obtenido en la subescala de Depresión corresponde a un nivel leve. Se "
            "registran indicadores iniciales relacionados con la pérdida de iniciativa, "
            "dificultades para experimentar disfrute o entusiasmo (anhedonia leve) y una "
            "percepción ligeramente desanimada respecto a sus actividades habituales, aunque sin "
            "configurar un cuadro depresivo mayor por sí solo."
        ),
        "recomendacion": (
            "Se recomienda seguimiento por parte del área de psicología del colegio, con "
            "observación periódica de la evolución del estudiante y una conversación exploratoria "
            "breve que permita identificar posibles factores asociados al desánimo reportado."
        ),
    },
    ("Depresión", (7, 10)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Depresión corresponde a un nivel moderado. Se "
            "observan indicadores más consistentes de pérdida de interés, desánimo y dificultad "
            "para experimentar disfrute en actividades habituales, que podrían estar afectando el "
            "bienestar emocional y el desempeño cotidiano del estudiante."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica individual y seguimiento cercano "
            "por parte del profesional responsable, además de informar y coordinar con la familia "
            "o apoderados según el protocolo institucional vigente."
        ),
    },
    ("Depresión", (11, 13)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Depresión corresponde a un nivel grave. Se "
            "identifican indicadores marcados de desánimo, pérdida de iniciativa y dificultad "
            "significativa para experimentar disfrute o entusiasmo, con posible interferencia en "
            "el funcionamiento cotidiano del estudiante."
        ),
        "recomendacion": (
            "Se recomienda derivación prioritaria a evaluación psicológica, comunicación con la "
            "familia o apoderados según el protocolo institucional, y seguimiento cercano de la "
            "evolución del estudiante."
        ),
    },
    ("Depresión", (14, 21)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Depresión corresponde a un nivel "
            "extremadamente grave, con indicadores marcados de desánimo, pérdida de iniciativa y "
            "dificultad importante para experimentar disfrute o entusiasmo por las actividades "
            "habituales. El DASS-21 no constituye por sí mismo una evaluación específica de "
            "riesgo suicida; cualquier indicador de desesperanza reportado (ítem 21) debe "
            "revisarse con especial atención (ver regla de seguridad asociada)."
        ),
        "recomendacion": (
            "Se recomienda derivación urgente a evaluación psicológica especializada, activación "
            "del protocolo institucional de atención a casos de riesgo y comunicación inmediata "
            "con la familia o apoderados. Se sugiere además coordinar una valoración "
            "complementaria que permita descartar un cuadro depresivo de mayor severidad."
        ),
    },
    ("Ansiedad", (0, 3)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Ansiedad se encuentra dentro del rango "
            "normal. No se identifican indicadores significativos de respuestas fisiológicas de "
            "ansiedad ni preocupación excesiva."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del estudiante. No se identifica "
            "necesidad de intervención adicional por este motivo."
        ),
    },
    ("Ansiedad", (4, 4)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Ansiedad corresponde a un nivel leve. Pueden "
            "observarse manifestaciones puntuales de tensión o aprensión que, por su intensidad, "
            "no alcanzan todavía un nivel clínicamente significativo."
        ),
        "recomendacion": (
            "Se recomienda observación periódica por parte del área de psicología del colegio, y "
            "una conversación exploratoria breve para identificar posibles factores situacionales "
            "asociados."
        ),
    },
    ("Ansiedad", (5, 7)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Ansiedad corresponde a un nivel moderado. Se "
            "identifican indicadores más frecuentes de tensión, aprensión y respuestas "
            "fisiológicas (como sequedad de boca o dificultad para respirar en situaciones de "
            "tensión), que podrían comenzar a interferir en algunas actividades cotidianas del "
            "estudiante."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica individual y seguimiento cercano, "
            "además de entrenar al estudiante en técnicas sencillas de relajación acordes con su "
            "edad."
        ),
    },
    ("Ansiedad", (8, 9)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Ansiedad corresponde a un nivel grave. Se "
            "identifican indicadores marcados de respuestas fisiológicas ante el pánico, tensión "
            "corporal y preocupación frecuente por perder el control, con posible interferencia "
            "relevante en el funcionamiento cotidiano del estudiante."
        ),
        "recomendacion": (
            "Se recomienda derivación prioritaria a evaluación psicológica, coordinación con la "
            "familia o apoderados según el protocolo institucional, y entrenamiento en técnicas de "
            "relajación y manejo de la activación fisiológica."
        ),
    },
    ("Ansiedad", (10, 21)): {
        # Adaptado casi literalmente de "Dimensión Ansiedad (A)" y "VII.
        # Recomendaciones" del ejemplar.
        "conclusion": (
            "Constituye la sintomatología predominante y de mayor severidad dentro del perfil "
            "evaluado. El estudiante reporta de manera recurrente respuestas fisiológicas ante el "
            "pánico, temblores corporales, aprensión, sequedad de boca y dificultades para "
            "respirar en situaciones de tensión. Asimismo, se evidencia una constante "
            "preocupación por perder el control o experimentar episodios de miedo intenso sin una "
            "causa aparente. Este resultado no constituye un diagnóstico clínico definitivo por sí "
            "mismo, pero funciona como un indicador de alerta prioritario."
        ),
        "recomendacion": (
            "Se recomienda iniciar un proceso de psicoterapia individual (preferentemente con "
            "enfoque cognitivo-conductual) enfocado en el manejo de la ansiedad, reestructuración "
            "cognitiva y regulación emocional; entrenar al estudiante en técnicas de relajación "
            "como respiración diafragmática, relajación muscular progresiva y prácticas de "
            "mindfulness; coordinar una evaluación médica o psiquiátrica complementaria dada la "
            "severidad del resultado; y brindar orientación a los padres o apoderados sobre los "
            "resultados de la evaluación."
        ),
    },
    ("Estrés", (0, 7)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Estrés se encuentra dentro del rango normal. "
            "No se identifican indicadores significativos de dificultad para relajarse, "
            "irritabilidad o baja tolerancia a la frustración."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del estudiante. No se identifica "
            "necesidad de intervención adicional por este motivo."
        ),
    },
    ("Estrés", (8, 9)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Estrés corresponde a un nivel leve. Pueden "
            "observarse manifestaciones puntuales de impaciencia o tensión que, por su "
            "intensidad, no alcanzan todavía un nivel clínicamente significativo."
        ),
        "recomendacion": (
            "Se recomienda observación periódica por parte del área de psicología del colegio, "
            "favoreciendo pautas sencillas de autocuidado y manejo del tiempo."
        ),
    },
    ("Estrés", (10, 12)): {
        # Adaptado casi literalmente de "Dimensión Estrés (S)" del ejemplar.
        "conclusion": (
            "Presenta un nivel moderado. El estudiante experimenta dificultades para relajarse, "
            "niveles de impaciencia difusa, irritabilidad y una baja tolerancia a la frustración "
            "ante eventos cotidianos. Se observa una tendencia a reaccionar de manera "
            "desproporcionada ante situaciones estresantes, acompañadas de tensión muscular y "
            "agitación."
        ),
        "recomendacion": (
            "Se recomienda seguimiento por parte del área de psicología del colegio, establecer "
            "pautas de higiene del sueño y rutinas de autocuidado que incluyan actividad física "
            "regular, y entrenar al estudiante en técnicas básicas de relajación."
        ),
    },
    ("Estrés", (13, 16)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Estrés corresponde a un nivel grave. Se "
            "identifican indicadores marcados de irritabilidad, dificultad significativa para "
            "relajarse y una tendencia acentuada a reaccionar de forma desproporcionada ante "
            "situaciones cotidianas, con posible interferencia relevante en el bienestar del "
            "estudiante."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica individual y seguimiento cercano, "
            "coordinación con la familia o apoderados según el protocolo institucional, y "
            "entrenamiento en técnicas de relajación y manejo del estrés."
        ),
    },
    ("Estrés", (17, 21)): {
        "conclusion": (
            "El puntaje obtenido en la subescala de Estrés corresponde a un nivel extremadamente "
            "grave, con activación fisiológica sostenida, irritabilidad marcada y una tolerancia "
            "muy baja a la frustración ante eventos cotidianos. Este resultado sugiere una "
            "sobrecarga emocional relevante que requiere atención profesional oportuna."
        ),
        "recomendacion": (
            "Se recomienda derivación prioritaria a evaluación psicológica especializada, "
            "activación del protocolo institucional de seguimiento, establecer pautas de higiene "
            "del sueño y autocuidado, y comunicación con la familia o apoderados para generar un "
            "entorno de soporte."
        ),
    },
}


def _verificar_estructura():
    """Falla ruidosamente ANTES de tocar la BD si la estructura de ítems no
    es exactamente la esperada — mismo criterio defensivo que seed_barsit.py/
    seed_vanderbilt_padres.py."""
    if len(ITEMS) != 21:
        raise RuntimeError(f"Se esperaban 21 ítems, hay {len(ITEMS)}")
    todos = ITEMS_DEPRESION | ITEMS_ANSIEDAD | ITEMS_ESTRES
    if len(todos) != 21 or todos != set(range(1, 22)):
        raise RuntimeError("Las 3 subescalas no cubren exactamente los ítems 1-21 sin solape")
    if ITEMS_DEPRESION & ITEMS_ANSIEDAD or ITEMS_DEPRESION & ITEMS_ESTRES or ITEMS_ANSIEDAD & ITEMS_ESTRES:
        raise RuntimeError("Las 3 subescalas se solapan — un ítem no puede pertenecer a más de una")
    for nombre, items, baremo in DEFINICION_DIMENSIONES:
        if len(items) != 7:
            raise RuntimeError(f"'{nombre}' tiene {len(items)} ítems, se esperaban 7")
    if ITEM_SEGURIDAD_DEPRESION not in ITEMS_DEPRESION:
        raise RuntimeError("El ítem de seguridad debe pertenecer a Depresión")


def _asegurar_contenido_informe_dass21(db, prueba) -> None:
    """Rellena motivo_consulta_default de la prueba y conclusion_sugerida/
    recomendacion_sugerida de cada tramo de las 3 subescalas SOLO si están
    vacíos — idempotente y puramente aditivo, mismo patrón que
    seed_gad7.py._asegurar_contenido_informe_gad7/seed_phq9.py._asegurar_
    contenido_informe: nunca pisa contenido que un psicólogo ya haya editado
    a mano."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")

    dimensiones = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).all()
    dimensiones_por_nombre = {dim.nombre: dim for dim in dimensiones}

    baremos_actualizados = 0
    for (nombre_dim, rango), contenido in CONTENIDO_INFORME_POR_TRAMO.items():
        dimension = dimensiones_por_nombre.get(nombre_dim)
        if not dimension:
            continue
        baremo = db.query(models.Baremo).filter(
            models.Baremo.dimension_id == dimension.id,
            models.Baremo.puntaje_minimo == rango[0],
            models.Baremo.puntaje_maximo == rango[1],
        ).first()
        if not baremo:
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
        print("↪️  El contenido del informe (motivo, conclusiones, recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) (de las 3 subescalas) con conclusión/recomendación añadidas.")


def cargar():
    _verificar_estructura()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  DASS-21 ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_dass21(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala de Depresión, Ansiedad y Estrés — DASS-21",
            instrucciones=(
                "Por favor lea las siguientes afirmaciones e indique en qué grado le ha ocurrido a usted "
                "esta afirmación durante la semana pasada."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=3,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoinforme
            dias_minimos_entre_aplicaciones=7,  # recall de 1 semana — ver docstring
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
        )
        db.add(prueba)
        db.flush()

        dimensiones_por_nombre = {}
        for nombre_dim, items_set, baremo in DEFINICION_DIMENSIONES:
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Subescala '{nombre_dim}' del DASS-21 (7 de los 21 ítems, suma 0-21). Se interpreta "
                    "siempre por separado de las otras dos subescalas — no existe un puntaje total "
                    "diagnóstico para el DASS-21 (ver docstring de seed_dass21.py)."
                ),
            )
            db.add(dimension)
            db.flush()
            dimensiones_por_nombre[nombre_dim] = dimension

        preguntas_por_numero = {}
        for numero, texto in ITEMS:
            nombre_dim = next(nd for nd, items_set, _ in DEFINICION_DIMENSIONES if numero in items_set)
            dimension = dimensiones_por_nombre[nombre_dim]
            pregunta = models.Pregunta(
                prueba_id=prueba.id,
                dimension_id=dimension.id,
                texto_pregunta=texto,
                orden=numero,
                es_inverso=False,  # el DASS-21 no tiene ítems inversos
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in OPCIONES:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                ))
            preguntas_por_numero[numero] = pregunta

        for nombre_dim, items_set, baremo in DEFINICION_DIMENSIONES:
            dimension = dimensiones_por_nombre[nombre_dim]
            for minimo, maximo, nivel, es_alerta in baremo:
                contenido = CONTENIDO_INFORME_POR_TRAMO.get((nombre_dim, (minimo, maximo)), {})
                db.add(models.Baremo(
                    dimension_id=dimension.id,
                    edad_min=None, edad_max=None, sexo=None, poblacion=None,
                    puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                    interpretacion=(
                        f"Puntaje bruto {minimo}-{maximo} en '{nombre_dim}': nivel '{nivel}'. Las tres "
                        "subescalas del DASS-21 deben interpretarse por separado; no constituye por sí "
                        "solo un diagnóstico psiquiátrico."
                    ),
                    conclusion_sugerida=contenido.get("conclusion"),
                    recomendacion_sugerida=contenido.get("recomendacion"),
                    es_alerta=es_alerta,
                ))

        # ⚠️ Regla de seguridad del ítem 21 — ver docstring.
        pregunta_21 = preguntas_por_numero[ITEM_SEGURIDAD_DEPRESION]
        db.add(models.ReglaInterpretacion(
            prueba_id=prueba.id,
            ambito=models.AMBITO_ITEM,
            pregunta_id=pregunta_21.id,
            operador=">",
            valor_comparacion=0,
            accion=models.ACCION_ES_ALERTA,
            descripcion=(
                "Ítem 21 positivo ('Sentí que la vida no tenía ningún sentido'): señal de desesperanza "
                "que amerita revisión profesional, aunque el puntaje de Depresión no alcance un tramo de "
                "alerta. El DASS-21 no es una herramienta de evaluación de riesgo suicida — esta regla "
                "es una señal de revisión, no una determinación de riesgo."
            ),
            activa=True,
        ))

        db.commit()
        print(f"✅ DASS-21 cargado: prueba id={prueba.id}, 3 dimensiones "
              f"(Depresión/Ansiedad/Estrés, 7 ítems c/u), 21 preguntas, "
              f"{sum(len(b) for _, _, b in DEFINICION_DIMENSIONES)} tramos de baremo (puntaje bruto, "
              "sin segundo criterio normativo, con conclusión/recomendación por tramo), "
              "1 ReglaInterpretacion de seguridad (ítem 21). Sin dimensión total (las 3 subescalas "
              "se interpretan siempre por separado — ver docstring).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando DASS-21: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
