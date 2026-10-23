"""
Carga el catálogo PÚBLICO (institucion_id=None) de VANDERBILT_PADRES — el
formulario para padres/tutores de la NICHQ Vanderbilt Assessment Scale,
3.ª edición (AAP, "Caring for Children With ADHD: A Practical Resource
Toolkit for Clinicians", traducción oficial al español, © 2020 American
Academy of Pediatrics). Primer instrumento con `informante_tipo="padre_madre"`
cargado en esta plataforma — ver "Informante" en CLAUDE.md, la fundación de
datos ya existía desde antes de que cualquier instrumento real la usara.

Es idempotente: si "VANDERBILT_PADRES" ya existe como prueba pública, no toca
nada. Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_vanderbilt_padres

⚠️ PRIMER USO REAL DE `Dimension.tipo_calculo='conteo_sintomas'` — EXTENSIÓN
DEL MOTOR CONSULTADA Y CONFIRMADA CON EL USUARIO ANTES DE CONSTRUIRLA, no una
decisión unilateral: el criterio clínico oficial del Vanderbilt no es "sumar
los puntajes y comparar contra un rango" (lo único que el motor sabía hacer
antes de esta sesión) sino un CONTEO de síntomas — "6 de 9 ítems de
Inatención con puntuación 2 o 3" — que una suma no puede expresar
honestamente (nueve ítems en 2 = conteo 9/9 pero suma 18; cinco ítems en 3 y
cuatro en 0 = conteo 5/9 pero suma 15, MAYOR que la anterior pese a NO
cumplir el criterio). Ver `Dimension.tipo_calculo`/`conteo_umbral_item` en
`modulos/educativo/models.py` y `core/algoritmo.py:calcular_likert_generico`
para el mecanismo genérico (no conoce Vanderbilt por nombre): cada dimensión
'conteo_sintomas' cuenta cuántos de sus propios ítems alcanzan
`conteo_umbral_item`, y ese conteo pasa a ser su `puntaje_directo` de
siempre — Baremo/DiagnosticoAlumno/ReglaInterpretacion no necesitan saber que
es un conteo. Migración: `2026_10_04_1000-e4ab309bbab8_conteo_sintomas.py`.

⚠️ NUMERACIÓN: SE USÓ LA DEL FORMULARIO REAL (`test.pdf`, 56 ítems, 3.ª
edición AAP 2020), NO LA DEL DOCUMENTO DE PUNTUACIÓN (55 ítems) — decisión
consultada y confirmada con el usuario. Los dos documentos de referencia que
sustentan esta carga NO coinciden en la numeración de ítems a partir de
Conducta, un hallazgo real de discrepancia de EDICIÓN (ver "No debe
mezclarse información de diferentes ediciones" en la ficha técnica), no un
error de transcripción:
  - El formulario real (`test.pdf`) tiene su propia casilla de conteo oficial
    impresa al pie de cada bloque, confirmada además por el resumen final de
    la página 4: Inatención=1-9 (9), Hiperactividad=10-18 (9), TND=19-26 (8),
    Conducta=27-41 (15, casilla "/15"), Ansiedad/depresión=42-48 (7, casilla
    "/7"), Funcionamiento=49-56 (8). Total 56 ítems.
  - El documento de puntuación que acompaña esta carga usa una numeración de
    55 ítems (de una edición anterior): Conducta=27-40 (14 ítems, no 15),
    Ansiedad/depresión=41-47, Funcionamiento=48-55.
Se cargó la numeración de 56 ítems de `test.pdf`, porque es el formulario que
se va a aplicar de verdad. El criterio "3 de 14" del documento de puntuación
se adaptó a "3 de 15" para esta carga (ver BAREMO_CONDUCTA más abajo) — es la
interpretación más razonable del mismo criterio clínico ("una minoría de
síntomas de conducta, ya con deterioro, amerita revisión") aplicada al
recuento real de ítems de la edición cargada, no un valor inventado sin
relación con la fuente.

⚠️ EL "GATE" DE DETERIORO FUNCIONAL Y "TDAH COMBINADO" NO SE AUTOMATIZAN —
DECISIÓN DE ALCANCE EXPLÍCITA, NO UN DESCUIDO: el criterio clínico completo
de cada área sintomática es "N de M síntomas, MÁS al menos un ítem de
Funcionamiento con puntuación 4 o 5" — una condición que cruza DOS
dimensiones independientes con un AND. El motor extendido en esta sesión
resuelve el conteo POR dimensión (ya es la parte más difícil y la que de
verdad bloqueaba cargar este instrumento), pero no incluye un mecanismo para
exigir que el resultado de una dimensión dependa del resultado de otra —
`ReglaInterpretacion` (ambito='dimension') solo compara el puntaje de SU
PROPIA dimensión contra un umbral fijo, nunca el de otra. Construir ese
cruce es una extensión de alcance mayor, deliberadamente fuera de esta
sesión. Por eso: (1) cada dimensión sintomática (Inatención/Hiperactividad/
TND/Conducta/Ansiedad-depresión) queda con `es_alerta=True` en su propio
tramo "criterio cumplido" SIN exigir el deterioro funcional — es decir, el
motor es más sensible que el criterio clínico completo, nunca menos (nunca
deja pasar un caso que el criterio real marcaría), y (2) la dimensión
Funcionamiento tiene su PROPIO tramo de alerta ("al menos un área con
deterioro") que un profesional revisa junto a las demás. "TDAH combinado"
(inatención Y simultáneamente hiperactividad) tampoco se computa
automáticamente, por la misma razón — ambas dimensiones ya aparecen
individualmente marcadas si corresponde, y combinarlas es lectura directa
del propio informe. Ver `Baremo.interpretacion` de cada dimensión para el
texto exacto que explica esto al profesional que revisa el caso.

⚠️ CINCO ÍTEMS DE CONDUCTA CON `ReglaInterpretacion` PROPIA DE ESTA
PLATAFORMA — NO EXIGIDA POR LAS INSTRUCCIONES OFICIALES (que no declaran
ningún "ítem crítico"), mismo mecanismo y mismo criterio ya usado para el
ítem 9 de PHQ-9 y el ítem 37 de RCADS-47: los ítems 29 ("Ha usado un arma que
puede causar daño grave"), 30 ("Ha sido físicamente cruel con las
personas"), 31 ("Ha sido físicamente cruel con animales"), 33 ("Ha forzado a
alguien a mantener una actividad sexual") y 34 ("Ha prendido fuego
deliberadamente para causar daño") describen riesgo de daño grave e
inmediato — a diferencia del resto de ítems de Conducta (mentir, faltar a
clases, robar...), una sola respuesta positiva (incluso "De vez en cuando")
en cualquiera de estos cinco amerita revisión profesional sin esperar a que
se cumpla el umbral agregado de "3 de 15". Declarado como datos
(`ReglaInterpretacion`, ambito='item', operador='>', valor_comparacion=0),
nunca escondido en ningún cálculo — el equipo clínico puede revisar o
desactivar cada una vía `PATCH /educativo/reglas/{id}` si no las quiere.

⚠️ SIN BAREMO PERCENTILAR (NORMAS ESTADOUNIDENSES 2022): la ficha técnica
(usada aquí solo como panorama, no como fuente de implementación, según lo
indicado) menciona que existen percentiles nacionales de EE. UU. (estudio
2022, n=1,570) para TDAH total/Inatención/Hiperactividad/TND/Conducta/
Ansiedad-depresión, pero no reproduce las tablas numéricas reales —
cargarlas sin los valores concretos violaría "NO INVENTAR CONTENIDO". El
único criterio cargado es el de conteo de síntomas de las fuentes que sí se
pidió implementar (`test.pdf` + el documento de puntuación). Tampoco existe
baremo peruano (ninguna fuente lo reporta).

⚠️ SOLO EL FORMULARIO PARA PADRES — el formulario para maestros (43 ítems,
distribución distinta: TND=19-28, Ansiedad/depresión=29-35, Funcionamiento
escolar=36-43) es una `Prueba` DISTINTA, con su propio `informante_tipo`,
pendiente de carga futura — mismo criterio de "una fila por variante" ya
usado en todo este catálogo (PHQ-9 vs. aptitud técnica interna, etc.). "No
deben mezclarse" los criterios de un formulario con el otro, advertencia
explícita de la propia ficha.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más abajo y
_asegurar_contenido_informe_vanderbilt, mismo patrón idempotente/aditivo que
seed_gad7.py/seed_dass21.py/seed_hamilton_autoinforme.py/seed_barsit.py):
`motivo_consulta_default`/`tecnicas_adicionales` y, por cada uno de los 12
tramos (6 dimensiones × 2 niveles), `Baremo.conclusion_sugerida`/
`recomendacion_sugerida`.

⚠️ EL EJEMPLAR DE REFERENCIA CUBRE 5 DE LAS 6 DIMENSIONES, NO "CONDUCTA":
un informe real de Vanderbilt (Padres + Tutor) entregado como ejemplo da
conteos reales para Inatención (7-8/9, cumple), Hiperactividad/Impulsividad
(2-3/9, no cumple), TND (1-2/8 o /10 según informante, no cumple),
Ansiedad/Depresión (3-4/7, cumple) y Funcionamiento (deterioro en 2 áreas,
cumple) — todos coinciden exactamente con los umbrales ya cargados aquí.
Nunca menciona "Conducta" (ni en la tabla cuantitativa ni en el texto
cualitativo), así que esa dimensión (ambos tramos) se redactó de cero, en
el mismo registro clínico.

Cada tramo es AUTOCONTENIDO: no asume que otras dimensiones estén
simultáneamente elevadas (mismo criterio que RCADS-47/DASS-21/Vanderbilt no
automatiza el cruce entre dimensiones — ver advertencia de arriba), aunque
el tramo "cumplido" de Ansiedad/Depresión sí incluye, adaptada del propio
ejemplar, la advertencia de no asumir automáticamente un trastorno
disocial cuando la sintomatología ansiosa coincide con otras áreas
elevadas — es una nota de cautela interpretativa, no una referencia a un
caso específico. El contenido de "Inatención" (tramo cumplido),
"Hiperactividad/Impulsividad" (no cumplido), "TND" (no cumplido),
"Ansiedad/Depresión" (cumplido) y "Funcionamiento" (cumplido) adapta casi
literalmente el ejemplar; los 7 tramos restantes se extrapolaron en el
mismo tono. Pendiente de verificación cruzada final, igual que el resto
del contenido de informe cargado en esta sesión.

`tecnicas_adicionales` = "Entrevista, Observación" — el ejemplar sí las
lista explícitamente (sección 3), igual que PHQ-9/GAD-7/Hamilton.

⚠️ `Prueba.escala_minima`/`escala_maxima`=0/3 ES SOLO COSMÉTICO/FALLBACK DE
INVERSIÓN, NO AFECTA EL PUNTAJE: Vanderbilt no tiene ítems inversos (ningún
`es_inverso=True`), así que estos dos campos nunca participan en ningún
cálculo real — se dejan en el rango de la mayoría de los ítems (48 de 56,
escala de frecuencia 0-3) por convención, aunque la dimensión Funcionamiento
usa su propia escala 1-5 (reflejada correctamente en sus propias
`OpcionRespuesta.valor_puntuacion`, que es lo único que el motor realmente
usa para contar).

⚠️ PERIODO DE RECALL = LOS ÚLTIMOS 6 MESES (instrucciones del formulario):
`dias_minimos_entre_aplicaciones=180`, mismo razonamiento ya aplicado a
PHQ-9/GAD-7/APGAR-FAMILIAR/CES-DC (reaplicar antes de que termine la ventana
de recall no da una medición independiente).

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `TECNICAS_ADICIONALES` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_vanderbilt_padres`.
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

NOMBRE_TECNICO = "VANDERBILT_PADRES"
# 🆕 Título corto para la UI (auditoría de UX, 2026-10-13) — ver Prueba.nombre_corto en models.py.
NOMBRE_CORTO = "NICHQ Vanderbilt — Padres"

OPCIONES_FRECUENCIA = [
    ("Nunca", 0),
    ("De vez en cuando", 1),
    ("A menudo", 2),
    ("Muy a menudo", 3),
]
UMBRAL_SINTOMA = 2  # "puntuación 2 o 3" cuenta como síntoma positivo

OPCIONES_FUNCIONAMIENTO = [
    ("Excelente", 1),
    ("Por encima del promedio", 2),
    ("Promedio", 3),
    ("Algo problemático", 4),
    ("Problemático", 5),
]
UMBRAL_FUNCIONAMIENTO = 4  # "puntuación 4 o 5" = deterioro

# Texto literal de los 56 ítems (test.pdf, formulario AAP 3.ª edición,
# traducción oficial al español) — numeración real, ver advertencia arriba.
ITEMS_INATENCION = [
    "No presta atención a detalles o comete errores que parecen descuidos, por ejemplo, con las tareas domiciliarias.",
    "Tiene dificultad para prestar atención a las tareas o actividades que se deben realizar.",
    "Cuando se le habla directamente parece no escuchar.",
    "No sigue las instrucciones o no termina las actividades (no porque se niegue ni porque no entienda).",
    "Tiene dificultad para organizar las tareas y las actividades.",
    "Evita, no le gustan o no quiere comenzar las tareas que requieren esfuerzo mental continuo.",
    "Pierde cosas que necesita para las tareas o actividades (p. ej. juguetes, deberes, lápices, libros).",
    "Se distrae con facilidad con ruidos u otros estímulos.",
    "Se muestra olvidadizo en las actividades diarias.",
]  # 1-9

ITEMS_HIPERACTIVIDAD = [
    "Juguetea con o golpea las manos o los pies o se retuerce en el asiento.",
    "Se levanta de su asiento cuando se espera que permanezca sentado.",
    "Corre o trepa en exceso cuando se espera que permanezca sentado.",
    "Tiene dificultad para jugar o comenzar a desarrollar juegos tranquilos.",
    'Está siempre activo o con frecuencia actúa como si "tuviera un motor".',
    "Habla demasiado.",
    "Responde a las preguntas sin esperar que terminen de hacerlas.",
    "Tiene dificultad para esperar su turno.",
    "Interrumpe o se entromete en las conversaciones o actividades de los demás, o ambas cosas.",
]  # 10-18

ITEMS_TND = [
    "Pierde los estribos.",
    "Es quisquilloso o se molesta fácilmente.",
    "Se enoja o muestra resentimiento.",
    "Discute con figuras de autoridad o con adultos.",
    "Desafía activamente o se niega a cumplir solicitudes o reglas.",
    "Molesta a otras personas deliberadamente.",
    "Culpa a los demás por sus errores o mal comportamiento.",
    "Es rencoroso y vengativo.",
]  # 19-26

# ⚠️ Posiciones 1-indexadas 3, 4, 5, 7 y 8 de esta lista (ítems 29, 30, 31,
# 33 y 34 del formulario) llevan ReglaInterpretacion propia — ver docstring.
ITEMS_CONDUCTA = [
    "Hostiga, amenaza o intimida a otros.",
    "Comienza las peleas físicas.",
    "Ha usado un arma que puede causar daño grave (p. ej., bate, cuchillo, ladrillo, pistola).",
    "Ha sido físicamente cruel con las personas.",
    "Ha sido físicamente cruel con animales.",
    "Ha robado confrontando a una persona.",
    "Ha forzado a alguien a mantener una actividad sexual.",
    "Ha prendido fuego deliberadamente para causar daño.",
    "Destruye deliberadamente las cosas de otras personas.",
    "Ha ingresado con violencia en otra casa, tienda o auto.",
    "Miente para salir de un problema, obtener cosas o favores o evitar obligaciones (p.ej., embauca a los demás).",
    "Ha robado objetos de valor.",
    "Ha pasado la noche fuera de su casa sin permiso desde antes de los 13 años de edad.",
    "Se ha escapado de casas dos veces o una vez por un período prolongado.",
    "Suele faltar a la escuela.",
]  # 27-41 (15 ítems)
INDICES_CONDUCTA_CON_REGLA_SEGURIDAD = {3, 4, 5, 7, 8}  # 1-indexado dentro de ITEMS_CONDUCTA

ITEMS_ANSIEDAD_DEPRESION = [
    "Es temeroso, ansioso o se preocupa.",
    "Teme hacer cosas nuevas por miedo a cometer errores.",
    "Se siente despreciable o inferior.",
    "Se culpa por problemas o se siente culpable.",
    "Se siente solo, no querido o no amado; a menudo dice que nadie lo quiere.",
    "No es feliz; está triste o deprimido.",
    "Es acomplejado, tímido o se avergüenza con facilidad.",
]  # 42-48

ITEMS_FUNCIONAMIENTO = [
    "Rendimiento escolar en general.",
    "Lectura.",
    "Escritura.",
    "Matemática.",
    "Relación con los padres.",
    "Relación con los hermanos.",
    "Relación con los compañeros.",
    "Participación en actividades organizadas (p. ej. equipos).",
]  # 49-56

# (nombre, items, umbral_item, opciones, umbral_minimo_positivo)
DEFINICION_DIMENSIONES = [
    ("Inatención", ITEMS_INATENCION, UMBRAL_SINTOMA, OPCIONES_FRECUENCIA, 6),
    ("Hiperactividad/Impulsividad", ITEMS_HIPERACTIVIDAD, UMBRAL_SINTOMA, OPCIONES_FRECUENCIA, 6),
    ("Trastorno Negativista Desafiante", ITEMS_TND, UMBRAL_SINTOMA, OPCIONES_FRECUENCIA, 4),
    ("Conducta", ITEMS_CONDUCTA, UMBRAL_SINTOMA, OPCIONES_FRECUENCIA, 3),
    ("Ansiedad/Depresión", ITEMS_ANSIEDAD_DEPRESION, UMBRAL_SINTOMA, OPCIONES_FRECUENCIA, 3),
    ("Funcionamiento", ITEMS_FUNCIONAMIENTO, UMBRAL_FUNCIONAMIENTO, OPCIONES_FUNCIONAMIENTO, 1),
]


# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES DE
# CONTENIDO DEL INFORME") — ver advertencia ✅ de cabecera.
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para identificar síntomas compatibles con Trastorno por "
    "Déficit de Atención e Hiperactividad (TDAH) y conductas asociadas (oposicionismo, conducta "
    "disruptiva, ansiedad/depresión), así como el posible deterioro funcional asociado, mediante "
    "el reporte de un padre/madre o tutor, en el marco de una campaña de evaluación psicométrica "
    "institucional."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

# (nombre_dimension, (mínimo, máximo)) -> {conclusion, recomendacion}. Las 12
# combinaciones (6 dimensiones × 2 niveles) son AUTOCONTENIDAS — ver
# advertencia ✅ de cabecera sobre cuáles adaptan el ejemplar y cuáles se
# extrapolaron.
CONTENIDO_INFORME_POR_TRAMO = {
    ("Inatención", (0, 5)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Inatención por debajo del criterio "
            "clínico de cribado (menos de 6 de 9 ítems con puntuación 'A menudo' o 'Muy a "
            "menudo'). No se evidencian, por este reporte, dificultades significativas para "
            "mantener la atención en tareas, organizarse o seguir instrucciones."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Inatención."
        ),
    },
    ("Inatención", (6, 9)): {
        # Adaptado del ejemplar (perfil con 7-8/9 síntomas de Inatención).
        "conclusion": (
            "El informante reporta un número de síntomas de Inatención que alcanza o supera el "
            "criterio clínico de cribado (6 o más de 9 ítems con puntuación 'A menudo' o 'Muy a "
            "menudo'). Esto se traduce en dificultad para mantener la atención en tareas "
            "prolongadas, comisión de errores por descuido, dificultades para seguir "
            "instrucciones complejas y falta de organización. El criterio clínico completo "
            "requiere además revisar la dimensión 'Funcionamiento' (al menos un área con "
            "deterioro) antes de considerar el cribado positivo; este resultado no equivale por "
            "sí solo a un diagnóstico de TDAH."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación especializada (psicología y/o neurología/"
            "psiquiatría) para la correlación clínica formal del perfil atencional, revisando en "
            "conjunto la dimensión de Funcionamiento y el resto de subescalas. Se sugiere además "
            "implementar estrategias de apoyo a la organización y el seguimiento de instrucciones "
            "(agendas, rutinas, instrucciones breves y claras) en el entorno escolar y familiar."
        ),
    },
    ("Hiperactividad/Impulsividad", (0, 5)): {
        # Adaptado del ejemplar ("por debajo del corte clínico, lo que
        # descarta componentes motores... de importancia").
        "conclusion": (
            "El informante reporta un número de síntomas de Hiperactividad/Impulsividad por "
            "debajo del criterio clínico de cribado (menos de 6 de 9 ítems con puntuación 'A "
            "menudo' o 'Muy a menudo'), lo que no evidencia componentes motores o impulsivos de "
            "importancia."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Hiperactividad/Impulsividad."
        ),
    },
    ("Hiperactividad/Impulsividad", (6, 9)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Hiperactividad/Impulsividad que "
            "alcanza o supera el criterio clínico de cribado (6 o más de 9 ítems con puntuación "
            "'A menudo' o 'Muy a menudo'), compatible con dificultad para permanecer quieto/a, "
            "esperar su turno o inhibir respuestas impulsivas. El criterio clínico completo "
            "requiere además revisar la dimensión 'Funcionamiento' (al menos un área con "
            "deterioro) antes de considerar el cribado positivo; este resultado no equivale por "
            "sí solo a un diagnóstico de TDAH."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación especializada para la correlación clínica "
            "formal del perfil hiperactivo/impulsivo, revisando en conjunto la dimensión de "
            "Funcionamiento. Se sugiere implementar estrategias de regulación conductual (pausas "
            "activas, rutinas estructuradas, refuerzo positivo) en el entorno escolar y familiar."
        ),
    },
    ("Trastorno Negativista Desafiante", (0, 3)): {
        # Adaptado del ejemplar ("por debajo del corte clínico, lo que
        # descarta... desafiantes externos de importancia").
        "conclusion": (
            "El informante reporta un número de síntomas de Oposición y Desafío por debajo del "
            "criterio clínico de cribado (menos de 4 de 8 ítems con puntuación 'A menudo' o 'Muy "
            "a menudo'), lo que no evidencia un patrón desafiante u oposicionista de importancia."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Oposición y Desafío."
        ),
    },
    ("Trastorno Negativista Desafiante", (4, 8)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Oposición y Desafío que alcanza o "
            "supera el criterio clínico de cribado (4 o más de 8 ítems con puntuación 'A menudo' "
            "o 'Muy a menudo'), compatible con un patrón persistente de irritabilidad, discusión "
            "con figuras de autoridad o desafío a reglas. El criterio clínico completo requiere "
            "además revisar la dimensión 'Funcionamiento' (al menos un área con deterioro) antes "
            "de considerar el cribado positivo; este resultado no equivale por sí solo a un "
            "diagnóstico."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica especializada, revisando en "
            "conjunto la dimensión de Funcionamiento y el resto de subescalas. Se sugiere "
            "trabajar con la familia y la escuela estrategias de manejo conductual consistentes "
            "(límites claros, refuerzo positivo, reducción de confrontaciones)."
        ),
    },
    ("Conducta", (0, 2)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Conducta por debajo del criterio "
            "clínico de cribado (menos de 3 de 15 ítems con puntuación 'A menudo' o 'Muy a "
            "menudo'), lo que no evidencia un patrón de conducta disocial de importancia."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Conducta."
        ),
    },
    ("Conducta", (3, 15)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Conducta que alcanza o supera el "
            "criterio clínico de cribado (3 o más de 15 ítems con puntuación 'A menudo' o 'Muy a "
            "menudo'), compatible con un patrón de comportamiento que vulnera normas o derechos "
            "de otros. El criterio clínico completo requiere además revisar la dimensión "
            "'Funcionamiento' (al menos un área con deterioro) antes de considerar el cribado "
            "positivo; este resultado no equivale por sí solo a un diagnóstico. Cualquier "
            "respuesta positiva a los ítems de mayor riesgo de esta dimensión (uso de armas, "
            "crueldad física, actividad sexual forzada o incendio deliberado) activa de forma "
            "independiente una señal de alerta que requiere revisión profesional inmediata, sin "
            "esperar a este umbral agregado (ver ReglaInterpretacion asociada)."
        ),
        "recomendacion": (
            "Se recomienda derivación prioritaria a evaluación psicológica especializada, "
            "revisando en conjunto la dimensión de Funcionamiento y el resto de subescalas, y "
            "comunicación con la familia o apoderados según el protocolo institucional vigente."
        ),
    },
    ("Ansiedad/Depresión", (0, 2)): {
        "conclusion": (
            "El informante reporta un número de síntomas de Ansiedad/Depresión por debajo del "
            "criterio clínico de cribado (menos de 3 de 7 ítems con puntuación 'A menudo' o 'Muy "
            "a menudo'), lo que no evidencia indicadores significativos en esta área."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Ansiedad/Depresión."
        ),
    },
    ("Ansiedad/Depresión", (3, 7)): {
        # Adaptado del ejemplar (síntomas de rumiación, tensión, baja
        # tolerancia a la frustración; nota de cautela sobre no confundir con
        # un trastorno disocial cuando coincide con otras áreas elevadas).
        "conclusion": (
            "El informante reporta un número de síntomas de Ansiedad/Depresión que alcanza o "
            "supera el criterio clínico de cribado (3 o más de 7 ítems con puntuación 'A menudo' "
            "o 'Muy a menudo'), con indicadores asociados a preocupación, tensión, baja "
            "tolerancia a la frustración, sentimientos de culpa o tristeza. El criterio clínico "
            "completo requiere además revisar la dimensión 'Funcionamiento' (al menos un área con "
            "deterioro) antes de considerar el cribado positivo; este resultado no equivale por "
            "sí solo a un diagnóstico. Cuando esta dimensión se eleva junto con otras áreas "
            "sintomáticas (p. ej. Inatención), conviene considerar si la sintomatología "
            "ansiosa/depresiva podría relacionarse con la frustración o el aislamiento secundario "
            "a esas otras dificultades, en vez de evaluarla de forma aislada."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica especializada para profundizar en "
            "la sintomatología ansiosa/depresiva reportada, revisando en conjunto la dimensión de "
            "Funcionamiento y el resto de subescalas. Se sugiere favorecer espacios de expresión "
            "emocional y acompañamiento psicoeducativo a la familia."
        ),
    },
    ("Funcionamiento", (0, 0)): {
        "conclusion": (
            "El informante no reporta áreas con deterioro funcional significativo (ninguna "
            "calificación de 'Problemas' o 'Problemas graves' en las áreas evaluadas: rendimiento "
            "escolar, relaciones familiares, con compañeros o participación en actividades)."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual. No se identifica necesidad de "
            "intervención adicional por este motivo en el área de Funcionamiento."
        ),
    },
    ("Funcionamiento", (1, 8)): {
        # Adaptado del ejemplar ("deterioro funcional es evidente y grave,
        # afectando su desempeño... y la armonía en la convivencia").
        "conclusion": (
            "El informante reporta al menos un área con deterioro funcional significativo "
            "(calificación de 'Problemas' o 'Problemas graves' en rendimiento escolar/laboral, "
            "relaciones familiares, con compañeros o participación en actividades). Este hallazgo "
            "es el que completa, junto con el umbral agregado de cualquiera de las dimensiones "
            "sintomáticas, el criterio clínico COMPLETO de cribado del NICHQ Vanderbilt — revisar "
            "en conjunto con las dimensiones de Inatención, Hiperactividad/Impulsividad, "
            "Oposición y Desafío, Conducta y Ansiedad/Depresión."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación especializada para profundizar en el impacto "
            "funcional reportado, y coordinar con la familia y la institución educativa "
            "estrategias de apoyo específicas para la(s) área(s) afectada(s) (académica, "
            "familiar, social, según corresponda)."
        ),
    },
}


def _verificar_estructura():
    """Falla ruidosamente ANTES de tocar la BD si la estructura no es
    exactamente la esperada (56 ítems, 6 dimensiones, conteos oficiales) —
    mismo criterio defensivo que seed_barsit.py/_verificar_estructura()."""
    conteos_esperados = {
        "Inatención": 9, "Hiperactividad/Impulsividad": 9,
        "Trastorno Negativista Desafiante": 8, "Conducta": 15,
        "Ansiedad/Depresión": 7, "Funcionamiento": 8,
    }
    total = 0
    for nombre, items, umbral, opciones, minimo in DEFINICION_DIMENSIONES:
        if len(items) != conteos_esperados[nombre]:
            raise RuntimeError(f"'{nombre}' tiene {len(items)} ítems, se esperaban {conteos_esperados[nombre]}")
        if minimo > len(items):
            raise RuntimeError(f"'{nombre}': umbral mínimo {minimo} > cantidad de ítems {len(items)}")
        total += len(items)
    if total != 56:
        raise RuntimeError(f"Se esperaban 56 ítems en total, hay {total}")
    if not INDICES_CONDUCTA_CON_REGLA_SEGURIDAD <= set(range(1, len(ITEMS_CONDUCTA) + 1)):
        raise RuntimeError("Índices de reglas de seguridad fuera de rango de ITEMS_CONDUCTA")


def _asegurar_contenido_informe_vanderbilt(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba y
    conclusion_sugerida/recomendacion_sugerida de cada uno de los 12 tramos
    (6 dimensiones × 2 niveles) SOLO si están vacíos — idempotente y
    puramente aditivo, mismo patrón que seed_gad7.py/seed_dass21.py/
    seed_hamilton_autoinforme.py/seed_barsit.py: nunca pisa contenido que un
    psicólogo ya haya editado a mano."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")
    if not prueba.nombre_corto:
        prueba.nombre_corto = NOMBRE_CORTO
        cambios.append("nombre_corto")

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
        print("↪️  El contenido del informe (motivo, técnicas, conclusiones, recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) (de las 6 dimensiones) con conclusión/recomendación añadidas.")


def cargar():
    _verificar_estructura()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  VANDERBILT_PADRES ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_vanderbilt(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="NICHQ Vanderbilt — Escala de Evaluación para Padres (3.ª edición, AAP)",
            # 🆕 Ver Prueba.nombre_corto en models.py — NOMBRE_TECNICO
            # ("VANDERBILT_PADRES") es un identificador interno, no un
            # título legible para un psicólogo.
            nombre_corto=NOMBRE_CORTO,
            instrucciones=(
                "Cada calificación debe ser considerada en el contexto de lo que es adecuado para la edad "
                "de su hijo/a. Al completar este formulario, piense sobre el comportamiento de su hijo/a "
                "en los últimos 6 meses."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=3,  # ver advertencia en el docstring — cosmético, Funcionamiento usa su propia escala 1-5
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_PADRE_MADRE,  # 🆕 primer uso real
            dias_minimos_entre_aplicaciones=180,  # recall de 6 meses — ver docstring
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
            tecnicas_adicionales=TECNICAS_ADICIONALES,
        )
        db.add(prueba)
        db.flush()

        dimensiones_por_nombre = {}
        preguntas_conducta = []

        for nombre_dim, items, umbral_item, opciones, umbral_minimo in DEFINICION_DIMENSIONES:
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Dimensión '{nombre_dim}' del NICHQ Vanderbilt — Padres ({len(items)} ítems). "
                    f"puntaje_directo = cantidad de ítems con puntuación ≥{umbral_item} "
                    "(Dimension.tipo_calculo='conteo_sintomas'), no una suma."
                ),
                tipo_calculo=models.TIPO_CALCULO_CONTEO_SINTOMAS,
                conteo_umbral_item=umbral_item,
            )
            db.add(dimension)
            db.flush()
            dimensiones_por_nombre[nombre_dim] = dimension

            for orden, texto in enumerate(items, start=1):
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=texto,
                    orden=orden,
                    es_inverso=False,  # Vanderbilt no tiene ítems inversos
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in opciones:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                if nombre_dim == "Conducta":
                    preguntas_conducta.append(pregunta)

            # Baremo: 2 tramos (no cumple / cumple criterio), ver docstring
            # sobre por qué es_alerta no exige también el gate de Funcionamiento.
            n = len(items)
            contenido_no_cumplido = CONTENIDO_INFORME_POR_TRAMO.get((nombre_dim, (0, umbral_minimo - 1)), {})
            contenido_cumplido = CONTENIDO_INFORME_POR_TRAMO.get((nombre_dim, (umbral_minimo, n)), {})
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=0, puntaje_maximo=umbral_minimo - 1,
                nivel="Criterio no cumplido",
                interpretacion=(
                    f"{umbral_minimo - 1} o menos de {n} ítems de '{nombre_dim}' alcanzan el umbral de "
                    "positividad. No cumple, por sí solo, el criterio de cribado de esta área. Revisar "
                    "junto con el resto de dimensiones y con la dimensión Funcionamiento."
                ),
                conclusion_sugerida=contenido_no_cumplido.get("conclusion"),
                recomendacion_sugerida=contenido_no_cumplido.get("recomendacion"),
                es_alerta=False,
            ))
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=umbral_minimo, puntaje_maximo=n,
                nivel=f"Criterio cumplido ({umbral_minimo} de {n})",
                interpretacion=(
                    f"Alcanza o supera {umbral_minimo} de {n} ítems de '{nombre_dim}' con puntuación "
                    f"≥{umbral_item}. El criterio clínico COMPLETO de cribado requiere, además, que al "
                    "menos un ítem de la dimensión 'Funcionamiento' tenga puntuación 4 o 5 (deterioro) — "
                    "verificar esa dimensión antes de considerar el cribado de esta área como positivo. "
                    "No equivale por sí solo a un diagnóstico."
                ),
                conclusion_sugerida=contenido_cumplido.get("conclusion"),
                recomendacion_sugerida=contenido_cumplido.get("recomendacion"),
                es_alerta=True,
            ))

        # ⚠️ Cinco ReglaInterpretacion de seguridad — ver docstring. Ambito
        # 'item', cualquier respuesta >0 (incluso "De vez en cuando") dispara.
        for idx in sorted(INDICES_CONDUCTA_CON_REGLA_SEGURIDAD):
            pregunta = preguntas_conducta[idx - 1]
            db.add(models.ReglaInterpretacion(
                prueba_id=prueba.id,
                ambito=models.AMBITO_ITEM,
                pregunta_id=pregunta.id,
                operador=">",
                valor_comparacion=0,
                accion=models.ACCION_ES_ALERTA,
                descripcion=(
                    f"Ítem de Conducta #{idx} ('{pregunta.texto_pregunta}') positivo: describe riesgo de "
                    "daño grave e inmediato — requiere revisión profesional sin esperar al umbral agregado "
                    "de Conducta (3 de 15)."
                ),
                activa=True,
            ))

        db.commit()
        print(f"✅ VANDERBILT_PADRES cargado: prueba id={prueba.id}, "
              f"{len(DEFINICION_DIMENSIONES)} dimensiones ('conteo_sintomas'), 56 preguntas, "
              f"{len(DEFINICION_DIMENSIONES) * 2} tramos de baremo (con conclusión/recomendación "
              "por tramo), "
              f"{len(INDICES_CONDUCTA_CON_REGLA_SEGURIDAD)} ReglaInterpretacion de seguridad "
              "(ítems de Conducta de alto riesgo). Deterioro funcional cruzado y 'TDAH combinado' "
              "quedan como síntesis profesional, no automatizados (ver docstring).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando VANDERBILT_PADRES: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
