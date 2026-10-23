"""
Carga el catálogo PÚBLICO (institucion_id=None) de BARSIT — pero DELIBERADA
Y EXPLÍCITAMENTE INCOMPLETO: 4 de las 5 áreas (48 de 60 reactivos), SIN la
dimensión "Razonamiento numérico" y SIN el puntaje/baremo "BARSIT total"
(0-60). Esta decisión de alcance fue consultada y confirmada con el usuario
antes de escribir este script — no es una simplificación silenciosa.

Es idempotente: si "BARSIT" ya existe como prueba pública, no toca nada. Para
forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_barsit

🆕 POR QUÉ FALTA UNA DE LAS 5 ÁREAS — ERA UN LÍMITE REAL DEL MOTOR, YA
CERRADO (sesión 2026-10-17); lo que falta ahora es puramente DATO, no
código: de los 60 reactivos, 48 son de opción múltiple (5 alternativas, el
evaluado elige una) y encajan sin cambios en el modelo genérico existente
(Pregunta → OpcionRespuesta, modo_calculo="correcto_incorrecto", el mismo
camino que ya ejercita seed_prueba_aptitud_tecnica.py). Los 12 reactivos de
"Razonamiento numérico" (series como "10 15 20 25 ___ 35 40 ___ 50") piden
ESCRIBIR los dos números que faltan — una respuesta de texto libre, no una
selección entre alternativas predefinidas; hasta esa sesión,
`guardar_respuestas_examen` solo sabía validar un par (pregunta_id,
opcion_id) ya existente en la BD, sin forma de representar "escribe estos
dos números" sin inventar 5 alternativas de opción múltiple que ninguna
fuente da (violaría "NO INVENTAR CONTENIDO" de CLAUDE.md). Ahora el motor sí
soporta esto: `Pregunta.tipo_respuesta='numerico'` +
`respuesta_correcta_numerica` (migración `01f0b91b3907`), con
`guardar_respuestas_examen`/`obtener_preguntas_por_token`/el examen público
del frontend ya extendidos — ver "Pregunta.tipo_respuesta" en models.py.
Sigue sin crearse la dimensión "Razonamiento numérico" en ESTE script
porque no tengo (en esta sesión) el texto literal de los 12 reactivos ni su
clave de corrección — cargar eso sin la fuente real violaría "NO INVENTAR
CONTENIDO" exactamente igual que antes. Es trabajo de DATOS pendiente, no
una limitación de motor: una vez con el cuestionario fuente completo
(mismo documento UJED ya usado para los 48 ítems, o su clave de
corrección), añadir estos 12 reactivos es un seed aditivo normal, sin
tocar código.

🆕 POR QUÉ TAMPOCO SE CARGA "BARSIT TOTAL" (0-60) NI SUS BAREMOS POR
GRADO/EDAD — mismo motivo, ya no es un límite de motor: el mecanismo para
expresar un puntaje agregado por encima de varias dimensiones
(`Dimension.tipo_calculo='suma_de_dimensiones'`/`DimensionComponente`) ya
existe desde que se cerró para SCARED-C/RCADS-47 (ver "Cinco límites reales
del motor", límite #1, en docs/catalogo-pruebas.md) — conectarlo para
BARSIT (una quinta `DimensionComponente` + la propia dimensión compuesta)
sería trabajo de datos, no de motor, en cuanto exista la dimensión
"Razonamiento numérico" de arriba. Lo que SÍ sigue faltando es el valor
real de los baremos documentados del puntaje total (Baremo 1 "cualitativo
por escolaridad", Baremo 2 "CI/percentiles", Baremo 3 "PB→CI"), calibrados
sobre los 60 reactivos completos — no los tengo transcritos en esta sesión,
y cargar un corte inventado clasificaría mal a cualquier alumno sin ningún
aviso (ver "NO INVENTAR CONTENIDO"). Solo se cargan los baremos POR
DIMENSIÓN (ver más abajo), que sí son válidos de forma independiente
porque cada área se punteó sobre sus propios 12 ítems, sin depender de las
demás.

⚠️ BAREMO POR DIMENSIÓN — ÚNICO BAREMO CARGADO, IDÉNTICO PARA LAS 4 ÁREAS:
la ficha técnica (sección 8, "Por dimensión") da una sola tabla, sin
distinción de edad/sexo/grado/población, para cualquiera de las 5 áreas (12
reactivos cada una): 1-4 Deficiente, 5-7 Inferior, 8-10 Promedio, 11-12
Superior. La fuente no cubre el caso de 0 aciertos (el tramo documentado
empieza en 1); se extiende aquí a 0-4 porque 0 aciertos es, por construcción,
al menos tan "deficiente" como 1-4 — no es una categoría clínica inventada,
solo cerrar el piso natural de una escala continua de conteo de aciertos
(0-12). edad_min/edad_max/sexo/poblacion quedan NULL (aplica a cualquiera),
igual que GAD-7/APGAR-FAMILIAR antes de que tuvieran su propio rango.

⚠️ NO ES CLÍNICA — es_alerta=False EN LOS 16 TRAMOS (4 niveles × 4
dimensiones): el BARSIT mide aptitud/habilidad intelectual, no
psicopatología; la propia ficha es explícita en que "no debe confundirse
esto con un diagnóstico clínico" y que no hay ítems críticos. Mismo
criterio que CHASIDE/IPIP-RIASEC/EAR (instrumentos no clínicos cargados
antes, también con es_alerta=False en todos sus tramos).

🆕 visible_para_clientes=True (sesión 2026-10-17) — ACTIVADA POR DECISIÓN
EXPLÍCITA DEL EQUIPO DE AURORASOFT PARA EL PILOTO, asumiendo el riesgo de
licencia documentado abajo; hasta esa sesión estuvo en False por dos
razones combinadas, cada una ya suficiente por sí sola (quedan documentadas
tal cual para que el riesgo asumido no se pierda, no porque sigan
bloqueando nada):
  1. Licencia más restrictiva que cualquier otro instrumento cargado: la
     ficha técnica documenta Copyright 1957 (The Psychological Corporation)
     y una edición de 1980 (Editorial El Manual Moderno) "con derechos
     reservados", sin ningún permiso de reproducción, uso comercial o
     licencia abierta especificado en ninguna fuente consultada — more
     explícito que la advertencia ya conocida de RCADS-47/IPIP-RIASEC
     ("licencia limitada, confirmar con los autores"), que sí se cargaron
     visibles porque su advertencia dejaba espacio a un uso de buena fe.
     Aquí la ficha dice textualmente que NO debe tratarse como material de
     dominio público solo porque existan copias digitalizadas en Internet.
  2. Esta carga es deliberadamente PARCIAL (ver arriba): una institución que
     seleccionara "BARSIT" del catálogo esperaría razonablemente una
     aplicación completa con un CI/percentil global, y en cambio nunca
     podría obtener ese resultado porque no se cargó esa dimensión/baremo.
La carga sigue siendo PARCIAL (4 de 5 áreas, sin CI/percentil global) —
activarla no resuelve ese límite por sí sola: el motor YA soporta ítems de
respuesta numérica construida (ver advertencia "Razonamiento numérico" más
arriba), pero falta el DATO — los 12 ítems reales + el baremo total por
grado/edad, pendientes del cuestionario fuente completo — así que, hasta
que ese dato se cargue, un psicólogo que aplique BARSIT en el piloto debe
saber que todavía no va a obtener un puntaje global, solo las 4 sub-áreas
cargadas.

⚠️ TEXTO LITERAL DE LOS 48 ÍTEMS: tomado de un cuestionario institucional
real y completo (Universidad Juárez del Estado de Durango, Coordinación
General de Orientación Educativa — "Test Rápido Barranquilla BARSIT"), que
incluye los 60 reactivos y su clave de corrección completa. No es un resumen
ni una paráfrasis — mismo criterio que CHASIDE/SCARED-C/RCADS-47 (formulario
real en uso institucional, con el mismo tipo de advertencia de licencia que
ya se documentó para RCADS-47/IPIP-RIASEC).

⚠️ DISCREPANCIA DETECTADA Y NO RESUELTA SILENCIOSAMENTE (ítem 29, área
Razonamiento Lógico) — mismo criterio que las contradicciones del ítem 30 y
el ítem 40 que la propia ficha técnica del BARSIT ya documenta: la lista de
alternativas del cuestionario fuente dice literalmente "Vestidor" en la
opción 5, pero DOS fuentes independientes de clave de corrección (la propia
clave del cuestionario, y la tabla de la ficha técnica secundaria) coinciden
en que la respuesta correcta es "Vestidos". Se cargó el texto LITERAL de la
lista de alternativas ("Vestidor", es lo que el alumno vería), marcado como
la opción correcta por POSICIÓN (la 5ª), ya que dos fuentes independientes
coinciden en que esa posición es la correcta — no se corrigió el texto para
que coincida con la clave, para no inventar una redacción que el
cuestionario fuente no tiene.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más abajo y
_asegurar_contenido_informe_barsit, mismo patrón idempotente/aditivo que
seed_gad7.py/seed_dass21.py/seed_hamilton_autoinforme.py): `motivo_
consulta_default` y, por cada uno de los 16 tramos (4 dimensiones × 4
niveles), `Baremo.conclusion_sugerida`/`recomendacion_sugerida`.
`tecnicas_adicionales` queda NULL a propósito — el ejemplar de referencia
no lista ninguna técnica aplicada aparte del propio test (solo las
recomienda como complementarias en su recomendación #4), así que no se
inventa una lista.

⚠️ EL EJEMPLAR DE REFERENCIA (informe real de BARSIT entregado) **NO SE
PUDO USAR LITERALMENTE POR TRAMO** — conflicto estructural más profundo que
el de otros instrumentos: todos sus resultados ("Puntaje Directo 32,
Percentil 75, Rango II, Diagnóstico: Intelectualmente igual al término
medio") describen el sistema GLOBAL de percentil/Rango/CI que este módulo
decidió explícitamente NO cargar (ver advertencia de arriba sobre por qué
falta "BARSIT total"); el ejemplar nunca desglosa resultados por las 4
áreas que sí están cargadas (Información/Comprensión Verbal/Razonamiento
Verbal/Razonamiento Lógico). No hay ningún tramo de los 16 ya cargados al
que ese puntaje/Rango se pueda mapear directamente.
Resolución: se reutilizó únicamente el TONO/REGISTRO del ejemplar (la
descripción de "adecuado desarrollo... comprensión verbal, juicio,
razonamiento lógico, resolución de problemas" para el nivel "Promedio",
que es el que corresponde a su "término medio") y se redactaron de cero,
en ese mismo registro no clínico (el BARSIT mide aptitud, no
psicopatología — es_alerta=False en los 16 tramos), los niveles
"Deficiente"/"Inferior"/"Superior" de las 4 dimensiones. Pendiente de
verificación cruzada final, igual que el resto del contenido de informe
cargado en esta sesión.

Sin ReglaInterpretacion — la ficha es explícita: "No encontré una categoría
formal de 'ítems críticos'".

⚠️ ADAPTACIÓN/BAREMO PERUANO: la ficha es explícita en que "Adaptación
peruana oficial: NO ACREDITADA EN LAS FUENTES CONSULTADAS" y que no existen
baremos peruanos oficiales actuales — un estudio psicométrico de 2017 en
2750 adultos de Lima existe, pero la propia ficha advierte que "no equivale
automáticamente a una adaptación oficial peruana" y que ese estudio señaló
problemas psicométricos reales (baja discriminación de ítems, estructura
factorial no satisfactoria). Por eso edad_min/edad_max/sexo/poblacion quedan
NULL y en ningún lugar se etiqueta nada de esto como "baremo peruano".

⚠️ AÑO DE REFERENCIA CONTRADICTORIO ENTRE FUENTES (1958 / 1980 / 1940-1945)
— no se resuelve aquí; no afecta ningún dato cargado (la prueba no almacena
un año de publicación en ningún campo del modelo).

⚠️ dias_minimos_entre_aplicaciones=180: NO es un valor de la ficha técnica
(que no especifica intervalo de reaplicación) — es un criterio conservador
propio de esta plataforma, análogo al ya usado para APGAR-FAMILIAR (90 días,
tampoco sourced), por el efecto de práctica bien documentado en la
literatura general de pruebas de aptitud intelectual cronometradas: volver a
aplicar el mismo cuestionario en una ventana corta infla el puntaje por
familiaridad con los reactivos, no por un cambio real de aptitud.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `tecnicas_adicionales` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_barsit`.
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

NOMBRE_TECNICO = "BARSIT"
NOMBRE_PUBLICO = (
    "BARSIT — Medición Rápida de Habilidad Intelectual "
    "(versión parcial: 4 de 5 áreas, sin puntaje total ni CI — ver notas del catálogo)"
)

INSTRUCCIONES = (
    "Mediante esta prueba se persigue que pienses rápido y eficazmente. Cada "
    "reactivo está seguido de cinco respuestas, de las cuales debes escoger "
    "la mejor."
)

# Cada entrada: (número de reactivo original en el BARSIT de 60 ítems,
# texto literal, [5 alternativas literales en orden 1-5], posición 1-indexada
# de la alternativa correcta). El número original se conserva solo como
# referencia/trazabilidad — no se almacena en ningún campo del modelo.
ITEMS_POR_DIMENSION = {
    "Información": [
        (1, "El queso se fabrica de:",
         ["Las flores", "La harina", "La leche", "Las uvas", "El azúcar"], 3),
        (6, "Para medir la temperatura se emplea...",
         ["Litro", "Gramo", "Termómetro", "Metro", "Kilowatio"], 3),
        (11, "El triángulo es una figura formada por",
         ["4 lados", "6 lados", "65 lados", "3 lados", "9 lados"], 4),
        (16, "El gato es un:",
         ["Mamífero", "Insecto", "Ave", "Pez", "Reptil"], 1),
        (21, "Treinta es el triple de:",
         ["Quince", "Tres", "Diez", "Doce", "Cinco"], 3),
        (26, "La cordillera de los Andes está en:",
         ["Europa", "Asia", "América", "Austria", "África"], 3),
        (31, "Roma es la Capital de:",
         ["Nicaragua", "España", "Grecia", "Italia", "Paraguay"], 4),
        (36, "El idioma oficial de Haití es el:",
         ["Inglés", "Francés", "Español", "Holandés", "Portugués"], 2),
        (41, "Fernando Magallanes fue un famoso:",
         ["Militar", "Aviador", "Navegante", "Sabio", "Sacerdote"], 3),
        (46, "Cristóbal Colón descubrió América en el:",
         ["Siglo XIII", "Siglo XVII", "Siglo IV", "Siglo XV", "Siglo XIV"], 4),
        (51, "Los primeros ferrocarriles empezaron a funcionar hacia:",
         ["1900", "1800", "1825", "1750", "1710"], 3),
        (56, "La bitácora es de uso indispensable en:",
         ["Música", "Biología", "Navegación", "Teatro", "Química"], 3),
    ],
    "Comprensión Verbal": [
        (2, "Lo contrario de abierto es:",
         ["Liso", "Cerrado", "Delante", "Claro", "Despejado"], 2),
        (7, "Lo contrario de dormido es",
         ["Noche", "Luz", "Amanecer", "Despierto", "Día"], 4),
        (12, "Lo contrario de negro es:",
         ["Oscuro", "Sombra", "Opaco", "Sucio", "Blanco"], 5),
        (17, "Lo contrario de triste es:",
         ["Alegre", "Preocupado", "Dolorido", "Desgraciado", "Enfermo"], 1),
        (22, "Lo contrario de calor es:",
         ["Sudor", "Fatiga", "Blanco", "Frío", "Luz"], 4),
        (27, "Lo contrario de arriba es:",
         ["Dentro", "Abajo", "Cerca", "Completo", "Lejos"], 2),
        (32, "Lo contrario de si es:",
         ["Antes", "Afirmar", "Duda", "Luego", "No"], 5),
        (37, "Lo contrario de despacio es:",
         ["De prisa", "Lento", "Pausado", "Débil", "Grueso"], 1),
        (42, "Lo contrario de blando es:",
         ["Suave", "Duro", "Liso", "Grueso", "Débil"], 2),
        (47, "Lo contrario de fuera es:",
         ["Libre", "Lejos", "Distinto", "Malo", "Dentro"], 5),
        (52, "Lo contrario de empezar es:",
         ["Iniciar", "Adelantar", "Obstruir", "Terminar", "Buscar"], 4),
        (57, "Lo contrario de homogéneo es:",
         ["Compacto", "Heterogéneo", "Abstracto", "Sútil", "Neutro"], 2),
    ],
    "Razonamiento Verbal": [
        (3, "De las siguientes palabras una pertenece a una clase diferente ¿cuál es?",
         ["Rojo", "Amarillo", "Morado", "Bandera", "Verde"], 4),
        (8, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Agua", "Platino", "Café", "Té", "Cerveza"], 2),
        (13, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Enrique", "Pedro", "Ana", "José", "Carlos"], 3),
        (18, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Bogotá", "Lima", "Alpes", "Caracas", "Quito"], 3),
        (23, "De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
         ["Cuchara", "Plato", "Tenedor", "Cuchillo", "Cucharita"], 2),
        (28, "De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
         ["General", "Teniente", "Capitán", "Presidente", "Coronel"], 4),
        (33, "De estas cinco palabras, una pertenece a una clase diferente ¿Cuál es?",
         ["Vaso", "Copa", "Agua", "Jarra", "Taza"], 3),
        (38, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Carpintero", "Herrero", "Médico", "Albañil", "Zapatero"], 3),
        (43, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Ver", "Oir", "Oler", "Andar", "Gustar"], 4),
        (48, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Venus", "Júpiter", "Satélite", "Urano", "Neptuno"], 3),
        (53, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Feliz", "Triste", "Satisfecho", "Alegre", "Contento"], 2),
        (58, "De estas cinco palabras una pertenece a una clase diferente ¿Cuál es?",
         ["Stravinski", "Bach", "Mozart", "Newton", "Chopin"], 4),
    ],
    "Razonamiento Lógico": [
        (4, "El pájaro canta y el perro...",
         ["Habla", "Rebuzna", "Cacarea", "Maúlla", "Ladra"], 5),
        (9, "El zapato protege al pie, y el sombrero protege a:",
         ["La cabeza", "La mano", "El dedo", "El brazo", "La rodilla"], 1),
        (14, "El naranjo es un árbol, y el perro es:",
         ["Un objeto", "Un animal", "Una cosa", "Un mineral", "Un vegetal"], 2),
        (19, "La piel cubre al hombre, y las plumas cubren a:",
         ["La vaca", "El perro", "El gato", "La gallina", "El caballo"], 4),
        (24, "Para coser se emplea la aguja, y para dibujar se emplea el:",
         ["Lápiz", "Bastón", "Tintero", "Pie", "Ojo"], 1),
        # ⚠️ Opción 5 literal "Vestidor" — la clave de corrección (dos fuentes
        # independientes) dice "Vestidos". Ver advertencia en el docstring.
        (29, "Con el cuero se fabrica el calzado, y con la tela:",
         ["Piel", "Lana", "Algodón", "Seda", "Vestidor"], 5),
        (34, "La Nariz sirve para oler, y los ojos sirven para:",
         ["Oir", "Ver", "Gustar", "Tocar", "Andar"], 2),
        (39, "Al lunes sigue el martes, y a enero sigue:",
         ["Junio", "Viernes", "Mes", "Febrero", "Año"], 4),
        (44, "El codo articula el brazo, y la rodilla articula:",
         ["El corazón", "Los dedos", "Los pulmones", "El cerebro", "La pierna"], 5),
        (49, "Octubre es anterior a Noviembre y Jueves es anterior a:",
         ["Diciembre", "Viernes", "Septiembre", "Miércoles", "Día"], 2),
        (54, "La paz viene después de la guerra y la calma viene después de:",
         ["La tormenta", "El crepúsculo", "El bienestar", "La felicidad", "El ocaso"], 1),
        (59, "La biblioteca es para guardar libros y la pinacoteca para guardar:",
         ["Periódico", "Discos", "Películas", "Monedas", "Cuadros"], 5),
    ],
}

# (mínimo, máximo, nivel) — única tabla, idéntica para las 4 dimensiones (ver
# advertencia sobre la extensión de 1-4 a 0-4 en el docstring). No clínica:
# es_alerta=False siempre.
BAREMO_POR_DIMENSION = [
    (0, 4, "Deficiente"),
    (5, 7, "Inferior"),
    (8, 10, "Promedio"),
    (11, 12, "Superior"),
]

# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES DE
# CONTENIDO DEL INFORME") — ver advertencia ✅ de cabecera sobre por qué el
# ejemplar de referencia no se pudo usar literalmente por tramo (describe un
# sistema de percentil/Rango/CI global que no está cargado).
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para conocer el nivel de capacidad intelectual general "
    "del estudiante mediante la aplicación del BARSIT, identificando el desarrollo de "
    "habilidades relacionadas con el razonamiento verbal, la comprensión, el juicio y la "
    "resolución de problemas, en el marco de una campaña de evaluación psicométrica "
    "institucional."
)

# (nombre_dimension, (mínimo, máximo)) -> {conclusion, recomendacion}. Las 16
# combinaciones (4 dimensiones × 4 niveles) son AUTOCONTENIDAS, sin mención a
# un puntaje/CI global (no cargado). El nivel "Promedio" de cada dimensión
# reutiliza el tono del ejemplar ("adecuado desarrollo... acorde con lo
# esperado para su edad"); "Deficiente"/"Inferior"/"Superior" se extrapolaron
# en el mismo registro no clínico — ver advertencia ✅ de cabecera.
CONTENIDO_INFORME_POR_TRAMO = {
    ("Información", (0, 4)): {
        "conclusion": (
            "El puntaje obtenido en el área de Información se ubica en el rango 'Deficiente', lo "
            "que sugiere un nivel de conocimientos generales (cultura general y vocabulario de "
            "hechos cotidianos) por debajo de lo esperado para su edad y nivel educativo. El "
            "BARSIT es un instrumento de aptitud intelectual, no un diagnóstico clínico; este "
            "resultado debe interpretarse junto con el nivel educativo del estudiante y otras "
            "fuentes de información disponibles."
        ),
        "recomendacion": (
            "Se recomienda favorecer actividades que amplíen el bagaje de conocimientos generales "
            "del estudiante (lectura, exposición a distintos temas, conversación guiada), y "
            "complementar este resultado con información de la entrevista, la observación "
            "conductual y el desempeño académico antes de extraer conclusiones definitivas."
        ),
    },
    ("Información", (5, 7)): {
        "conclusion": (
            "El puntaje obtenido en el área de Información se ubica en el rango 'Inferior', por "
            "debajo del promedio esperado en conocimientos generales para su edad y nivel "
            "educativo."
        ),
        "recomendacion": (
            "Se recomienda reforzar la exposición del estudiante a información general mediante "
            "lectura, actividades educativas y conversación guiada, y dar seguimiento a su "
            "evolución en este tipo de tareas."
        ),
    },
    ("Información", (8, 10)): {
        "conclusion": (
            "El puntaje obtenido en el área de Información se ubica dentro del promedio esperado, "
            "evidenciando un nivel de conocimientos generales acorde con lo esperado para su edad "
            "y nivel educativo."
        ),
        "recomendacion": (
            "Se recomienda continuar fortaleciendo este desarrollo mediante actividades escolares "
            "y recreativas que promuevan la curiosidad y el acceso a información general."
        ),
    },
    ("Información", (11, 12)): {
        "conclusion": (
            "El puntaje obtenido en el área de Información se ubica en el rango 'Superior', "
            "evidenciando un nivel de conocimientos generales por encima de lo esperado para su "
            "edad y nivel educativo."
        ),
        "recomendacion": (
            "Se recomienda favorecer espacios que permitan al estudiante seguir ampliando su "
            "bagaje de conocimientos, aprovechando este recurso como fortaleza dentro de su "
            "perfil cognitivo."
        ),
    },
    ("Comprensión Verbal", (0, 4)): {
        "conclusion": (
            "El puntaje obtenido en el área de Comprensión Verbal se ubica en el rango "
            "'Deficiente', lo que sugiere dificultad para comprender el significado de las "
            "palabras y establecer relaciones de oposición entre conceptos, por debajo de lo "
            "esperado para su edad."
        ),
        "recomendacion": (
            "Se recomienda reforzar actividades de vocabulario y comprensión verbal (lectura "
            "guiada, juegos de palabras, asociación de conceptos), acordes con su edad y nivel "
            "educativo."
        ),
    },
    ("Comprensión Verbal", (5, 7)): {
        "conclusion": (
            "El puntaje obtenido en el área de Comprensión Verbal se ubica en el rango 'Inferior', "
            "por debajo del promedio esperado en la comprensión del significado de las palabras."
        ),
        "recomendacion": (
            "Se recomienda reforzar el vocabulario y la comprensión verbal mediante actividades de "
            "lectura y conversación, dando seguimiento a su evolución."
        ),
    },
    ("Comprensión Verbal", (8, 10)): {
        "conclusion": (
            "El puntaje obtenido en el área de Comprensión Verbal se ubica dentro del promedio "
            "esperado, con una adecuada comprensión del significado de las palabras y de las "
            "relaciones de oposición entre conceptos."
        ),
        "recomendacion": (
            "Se recomienda continuar estimulando la comprensión verbal mediante actividades de "
            "lectura y comprensión lectora acordes con su nivel educativo."
        ),
    },
    ("Comprensión Verbal", (11, 12)): {
        "conclusion": (
            "El puntaje obtenido en el área de Comprensión Verbal se ubica en el rango 'Superior', "
            "con una comprensión del significado de las palabras por encima de lo esperado para su "
            "edad."
        ),
        "recomendacion": (
            "Se recomienda favorecer actividades que sigan desarrollando este recurso, como "
            "lectura de mayor complejidad y espacios de debate o análisis verbal."
        ),
    },
    ("Razonamiento Verbal", (0, 4)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Verbal se ubica en el rango "
            "'Deficiente', lo que sugiere dificultad para clasificar conceptos y reconocer "
            "relaciones de pertenencia o exclusión entre ellos, por debajo de lo esperado para su "
            "edad."
        ),
        "recomendacion": (
            "Se recomienda reforzar actividades de clasificación y categorización de conceptos "
            "(agrupar por categorías, comparar semejanzas y diferencias), acordes con su edad y "
            "nivel educativo."
        ),
    },
    ("Razonamiento Verbal", (5, 7)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Verbal se ubica en el rango "
            "'Inferior', por debajo del promedio esperado en la capacidad para clasificar "
            "conceptos y reconocer relaciones entre ellos."
        ),
        "recomendacion": (
            "Se recomienda reforzar actividades de clasificación y comparación de conceptos, "
            "dando seguimiento a su evolución."
        ),
    },
    ("Razonamiento Verbal", (8, 10)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Verbal se ubica dentro del promedio "
            "esperado, con una adecuada capacidad para clasificar conceptos y reconocer "
            "relaciones de pertenencia o exclusión entre ellos."
        ),
        "recomendacion": (
            "Se recomienda continuar estimulando el razonamiento verbal mediante actividades "
            "escolares que impliquen clasificación, comparación y análisis de conceptos."
        ),
    },
    ("Razonamiento Verbal", (11, 12)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Verbal se ubica en el rango "
            "'Superior', con una capacidad para clasificar conceptos y reconocer relaciones entre "
            "ellos por encima de lo esperado para su edad."
        ),
        "recomendacion": (
            "Se recomienda favorecer actividades de mayor complejidad que sigan desarrollando "
            "este recurso, como análisis y debate de conceptos abstractos."
        ),
    },
    ("Razonamiento Lógico", (0, 4)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Lógico se ubica en el rango "
            "'Deficiente', lo que sugiere dificultad para establecer analogías y relaciones "
            "lógicas entre conceptos, por debajo de lo esperado para su edad."
        ),
        "recomendacion": (
            "Se recomienda reforzar actividades que estimulen el razonamiento lógico (analogías, "
            "acertijos sencillos, secuencias), acordes con su edad y nivel educativo."
        ),
    },
    ("Razonamiento Lógico", (5, 7)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Lógico se ubica en el rango "
            "'Inferior', por debajo del promedio esperado en la capacidad para establecer "
            "analogías y relaciones lógicas entre conceptos."
        ),
        "recomendacion": (
            "Se recomienda reforzar actividades de razonamiento lógico y resolución de problemas "
            "sencillos, dando seguimiento a su evolución."
        ),
    },
    ("Razonamiento Lógico", (8, 10)): {
        # Adaptado del tono de "V. Resultados"/"VI. Interpretación de
        # Resultados" del ejemplar ("realizar razonamientos lógicos y
        # resolver situaciones problemáticas de complejidad acorde con su
        # edad").
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Lógico se ubica dentro del promedio "
            "esperado, evidenciando una adecuada capacidad para establecer analogías, realizar "
            "razonamientos lógicos y resolver situaciones problemáticas de complejidad acorde con "
            "su edad."
        ),
        "recomendacion": (
            "Se recomienda continuar fortaleciendo el razonamiento lógico mediante actividades "
            "escolares y recreativas que impliquen análisis, resolución de problemas y "
            "pensamiento crítico."
        ),
    },
    ("Razonamiento Lógico", (11, 12)): {
        "conclusion": (
            "El puntaje obtenido en el área de Razonamiento Lógico se ubica en el rango "
            "'Superior', con una capacidad para establecer analogías y resolver situaciones "
            "problemáticas por encima de lo esperado para su edad."
        ),
        "recomendacion": (
            "Se recomienda favorecer actividades de mayor complejidad (resolución de problemas, "
            "pensamiento crítico avanzado) que sigan desarrollando este recurso dentro de su "
            "perfil cognitivo."
        ),
    },
}


def _verificar_estructura():
    """Falla ruidosamente ANTES de tocar la BD si la estructura de ítems no
    es exactamente la esperada (4 dimensiones × 12 ítems, 5 alternativas
    cada uno, índice correcto en rango) — mismo criterio defensivo que
    seed_rosenberg.py/_verificar_inversos() y seed_chaside.py/_verificar_matriz()."""
    if set(ITEMS_POR_DIMENSION.keys()) != {
        "Información", "Comprensión Verbal", "Razonamiento Verbal", "Razonamiento Lógico"
    }:
        raise RuntimeError(f"Dimensiones inesperadas: {sorted(ITEMS_POR_DIMENSION.keys())}")
    numeros_vistos = set()
    for nombre_dim, items in ITEMS_POR_DIMENSION.items():
        if len(items) != 12:
            raise RuntimeError(f"'{nombre_dim}' tiene {len(items)} ítems, se esperaban 12")
        for numero, texto, opciones, correcta in items:
            if numero in numeros_vistos:
                raise RuntimeError(f"Número de reactivo {numero} duplicado")
            numeros_vistos.add(numero)
            if len(opciones) != 5:
                raise RuntimeError(f"Reactivo {numero} no tiene 5 alternativas: {opciones}")
            if not (1 <= correcta <= 5):
                raise RuntimeError(f"Reactivo {numero}: índice correcto fuera de rango: {correcta}")
    if len(numeros_vistos) != 48:
        raise RuntimeError(f"Se esperaban 48 reactivos únicos, hay {len(numeros_vistos)}")
    # Los 12 reactivos de "Razonamiento numérico" (5,10,15,20,25,30,35,40,45,
    # 50,55,60) nunca deben aparecer aquí — ver docstring sobre por qué esa
    # dimensión no se carga.
    numeros_numericos = {5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60}
    if numeros_vistos & numeros_numericos:
        raise RuntimeError(
            f"Reactivos de Razonamiento numérico colados por error: {sorted(numeros_vistos & numeros_numericos)}"
        )


def _asegurar_contenido_informe_barsit(db, prueba) -> None:
    """Rellena motivo_consulta_default de la prueba y conclusion_sugerida/
    recomendacion_sugerida de cada uno de los 16 tramos (4 dimensiones × 4
    niveles) SOLO si están vacíos — idempotente y puramente aditivo, mismo
    patrón que seed_gad7.py/seed_dass21.py/seed_hamilton_autoinforme.py:
    nunca pisa contenido que un psicólogo ya haya editado a mano."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    # 🆕 Activación explícita (sesión 2026-10-17): decisión de negocio tomada
    # por el equipo de AuroraSoft de habilitar las 14 pruebas del catálogo
    # para el piloto, asumiendo el riesgo de licencia documentado arriba —
    # ya no es "pendiente de confirmar licencia", es una decisión tomada.
    # Única excepción deliberada al criterio "nunca pisar lo ya cargado": un
    # booleano de visibilidad no es contenido clínico, y la propia advertencia
    # del docstring decía que activarla requería esta decisión explícita.
    if not prueba.visible_para_clientes:
        prueba.visible_para_clientes = True
        cambios.append("visible_para_clientes")

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
          f"{baremos_actualizados} tramo(s) (de las 4 dimensiones) con conclusión/recomendación añadidas.")


def cargar():
    _verificar_estructura()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  BARSIT ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_barsit(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico=NOMBRE_PUBLICO,
            instrucciones=INSTRUCCIONES,
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=1,
            modo_calculo="correcto_incorrecto",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,  # 🆕 activación explícita (sesión 2026-10-17) — ver docstring
            informante_tipo=models.INFORMANTE_ESTUDIANTE,
            dias_minimos_entre_aplicaciones=180,  # ver advertencia en el docstring (no sourced)
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
        )
        db.add(prueba)
        db.flush()

        total_preguntas = 0
        for nombre_dim, items in ITEMS_POR_DIMENSION.items():
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Área '{nombre_dim}' del BARSIT (12 de los 60 reactivos originales). "
                    "Puntaje directo = número de aciertos (0-12). No clínica: no debe "
                    "asociarse a alerta de riesgo ni a diagnóstico alguno."
                ),
            )
            db.add(dimension)
            db.flush()

            for numero, texto, opciones, correcta in items:
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=texto,
                    orden=numero,  # conserva el número de reactivo original (1-60) como orden
                    es_inverso=False,  # no aplica a corrección objetiva (correcto_incorrecto)
                )
                db.add(pregunta)
                db.flush()
                for posicion, texto_opcion in enumerate(opciones, start=1):
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id,
                        texto_opcion=texto_opcion,
                        valor_puntuacion=1 if posicion == correcta else 0,
                    ))

            for minimo, maximo, nivel in BAREMO_POR_DIMENSION:
                contenido = CONTENIDO_INFORME_POR_TRAMO.get((nombre_dim, (minimo, maximo)), {})
                db.add(models.Baremo(
                    dimension_id=dimension.id,
                    edad_min=None, edad_max=None, sexo=None, poblacion=None,
                    puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                    interpretacion=(
                        f"{minimo}-{maximo} aciertos (de 12) en '{nombre_dim}': nivel '{nivel}'. "
                        "Mide aptitud/habilidad intelectual, no psicopatología; no equivale a un "
                        "diagnóstico clínico y debe interpretarse junto con el nivel educativo del "
                        "estudiante y demás fuentes de información disponibles."
                    ),
                    conclusion_sugerida=contenido.get("conclusion"),
                    recomendacion_sugerida=contenido.get("recomendacion"),
                    es_alerta=False,
                ))

            total_preguntas += len(items)

        db.commit()
        print(f"✅ BARSIT (versión parcial) cargado: prueba id={prueba.id}, "
              f"{len(ITEMS_POR_DIMENSION)} dimensiones, {total_preguntas} preguntas, "
              f"{len(ITEMS_POR_DIMENSION) * len(BAREMO_POR_DIMENSION)} tramos de baremo "
              "(por dimensión, sin 'BARSIT total', con conclusión/recomendación por tramo). "
              "visible_para_clientes=True (🆕 activación explícita, sesión 2026-10-17). Sin "
              "ReglaInterpretacion. Dimensión 'Razonamiento numérico' NO cargada (ver docstring) — "
              "sigue sin CI/percentil global pese a estar activa.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando BARSIT: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
