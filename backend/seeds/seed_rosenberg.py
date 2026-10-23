"""
Carga el catálogo PÚBLICO (institucion_id=None) de la Escala de Autoestima de
Rosenberg (EAR/RSES) — prueba, 1 dimensión (Autoestima Global, unifactorial),
10 ítems literales con escala Likert 1-4, y dos criterios normativos
cargados simultáneamente (`Baremo.criterio_normativo` — ver "Criterio
normativo de Baremo" en CLAUDE.md).

Es idempotente: si "EAR" ya existe como prueba pública, no toca nada salvo
asegurar el segundo criterio (ver `_asegurar_criterio_percentil_n1228`).
Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_rosenberg

⚠️ HALLAZGO — LA FICHA TÉCNICA SECUNDARIA SE CONTRADICE A SÍ MISMA SOBRE
CUÁLES SON LOS ÍTEMS INVERTIDOS (mismo tipo de inconsistencia ya documentado
para CHASIDE, verificado por código antes de cargar, no solo a mano):
la sección "3. ÍTEMS" de la ficha marca con asterisco (*) los ítems 2, 5, 8,
9 y 10 como "redactados en sentido negativo y sujetos a inversión de
puntuación" — y el propio cuestionario original (RSE.pdf, Atienza, Balaguer
& Moreno, 2000) lo confirma de forma independiente y explícita: "Modelo
unifactorial – Autoestima global: ítems invertidos 2, 5, 8, 9, 10." Sin
embargo, la MISMA ficha técnica, en la sección "5.B Rango de puntuación" Y
de nuevo en "CONFIGURACIÓN RECOMENDADA PARA SOFTWARE", escribe "2, 5, 6, 8
y 9" — sustituyendo el 10 por un 6 que, además, aparece simultáneamente en
la lista de ítems DIRECTOS de esa misma sección ("directos: 1, 3, 4, 6, 7"),
una contradicción interna irreconciliable (el ítem 6 no puede ser directo
e inverso a la vez). El contenido del propio ítem 6 ("Tengo una actitud
positiva hacia mí mismo") es inequívocamente positivo, y el del ítem 10
("A veces pienso que no sirvo para nada") inequívocamente negativo — ambas
fuentes primarias (el cuestionario real y la sección con asteriscos de la
misma ficha) coinciden entre sí y con el contenido semántico de los ítems.
Se cargan aquí como inversos los ítems **2, 5, 8, 9 y 10** — la sección
"5.B"/"CONFIGURACIÓN RECOMENDADA" de la ficha secundaria queda descartada
por ser la fuente en minoría y autocontradictoria, verificado por código
(`_verificar_inversos`) antes de tocar la base de datos.

⚠️ TEXTO DE LOS 10 ÍTEMS — SÍ ES LITERAL: tomado de RSE.pdf, la traducción
española de Atienza, Balaguer y Moreno (2000), ampliamente citada en
estudios peruanos (p. ej. Ventura-León et al., 2018). **No** es la misma
cosa que "la versión peruana publicada" mencionada más abajo — esa es una
variante distinta de 9 ítems (ver advertencia siguiente), no una traducción
diferente de los 10.

⚠️ SOLO LA VERSIÓN ORIGINAL DE 10 ÍTEMS — LA VARIANTE PERUANA DE 9 NO SE
CARGA (decisión de diseño explícita, mismo criterio que seed_apgar_familiar.py
eligiendo una versión entre varias): Sánchez-Villena, de la Fuente-Figuerola
y Ventura-León (2021) estudiaron una variante que OMITE el ítem 8 ("Me
gustaría tener más respeto por mí mismo" — el único ítem redactado como
aspiración/deseo en vez de afirmación directa, señalado por más de un
estudio peruano con "comportamiento psicométrico" problemático), con rango
9-36 en vez de 10-40. Cargar ambas como la misma `Prueba` es imposible (son
estructuras de ítems distintas, no un criterio de corte alternativo sobre
el mismo puntaje — ver `Baremo.criterio_normativo`, que solo sirve para
"mismos ítems, distinto punto de corte"); cargarlas como dos `Prueba`
separadas es una opción real, pero no se hace aquí por no tener todavía un
caso de uso real que lo pida — mismo criterio que SCARED-P/RCADS-47
Caregiver, documentados como pendientes en vez de cargados sin necesidad.
Si se necesita en el futuro, es un `seed_rosenberg_9items.py` nuevo, nunca
una rama de código en el motor.

⚠️ UNA SOLA DIMENSIÓN, A PESAR DE LA ESTRUCTURA POSITIVA/NEGATIVA DISCUTIDA
EN LA LITERATURA (mismo criterio que seed_apgar_familiar.py): la ficha
técnica es explícita en que la separación ítems-positivos/ítems-negativos
"no debe confundirse automáticamente con dos dimensiones oficiales de la
RSES. Puede representar un efecto de método derivado de la redacción
positiva/negativa de los ítems" — y que, usando la concepción original de
Rosenberg, "la interpretación principal debe realizarse sobre el puntaje
global". Se carga como UNA sola `Dimension` (Autoestima Global, 10 ítems),
nunca como dos sub-escalas.

⚠️ CRITERIO NORMATIVO: DOS TABLAS DE CORTE QUE SE SOLAPAN Y NO COINCIDEN —
mismo hueco que ya resolvió `Baremo.criterio_normativo` para GAD-7/
APGAR-FAMILIAR (ver "Criterio normativo de Baremo" en CLAUDE.md), y la
propia ficha técnica de Rosenberg lo documenta con el mismo nivel de
explicitud que esas dos: la sección "8. PUNTOS DE CORTE" reporta un rango
"frecuentemente utilizado... incluso en trabajos peruanos" (10-25 Baja /
26-29 Media / 30-40 Elevada) y la sección "7. BAREMOS" reporta, de una
fuente académica secundaria distinta (n=1,228 estudiantes, percentiles
Pc25/Pc50/Pc75), un corte DIFERENTE para las mismas tres bandas conceptuales
(10-27 Baja / 28-35 Promedio / 36-40 Alta) — ambos NO pueden ser el mismo
tramo de Baremo porque se solapan en rango (26-27 es ambiguo entre ambos
criterios). Se carga el de la sección 8 (`criterio_normativo=NULL`, activo
por defecto) por ser el descrito como más ampliamente usado; el de la
sección 7 se carga como segundo criterio (`criterio_normativo=
"percentil_n1228"`). Ninguno de los dos es, ni se presenta como, un baremo
nacional peruano oficial — la propia ficha técnica confirma explícitamente
que no existe uno ("No se encontró un baremo nacional peruano único y
representativo para todas las edades").

⚠️ NO ES UNA PRUEBA DIAGNÓSTICA — `es_alerta=False` EN TODOS LOS TRAMOS,
EN AMBOS CRITERIOS (decisión explícita, no un descuido): a diferencia de
PHQ-9/GAD-7/APGAR-FAMILIAR (que sí tienen tramos `es_alerta=True`
documentados como "indicador de posible alteración... amerita revisión"),
la ficha técnica de Rosenberg es inusualmente insistente en lo contrario a
lo largo de TODO el documento: "No existe un punto de corte diagnóstico
universal... La escala mide autoestima; no diagnostica depresión,
ansiedad... ni otros trastornos psicológicos" (sección 8), "No significa
por sí misma la presencia de un trastorno psicológico" (sección 9), "Una
puntuación baja no permite diagnosticar depresión, ansiedad ni ningún otro
trastorno" (sección 11), y la propia sección "CONFIGURACIÓN RECOMENDADA
PARA SOFTWARE" fija explícitamente `diagnostico_automatico: NO`. La
sección 8 incluso advierte contra escribir "La persona tiene autoestima
baja" en un informe, prefiriendo "El puntaje obtenido se encuentra en el
rango interpretativo utilizado para esta población..." — exactamente el
tipo de afirmación categórica que `es_alerta=True` + retención de informe
terminaría comunicando. Mismo criterio que CHASIDE/IPIP-RIASEC: ninguna
aplicación de esta prueba retiene el informe ni dispara el correo de
alerta de riesgo. Ajustable después vía `PATCH /educativo/baremos/{id}` si
el protocolo clínico de un colegio difiere (mismo criterio ya documentado
para APGAR-FAMILIAR).

⚠️ REDACCIÓN DE `Baremo.interpretacion` — TOMADA CASI LITERAL DE LA
"REDACCIÓN SUGERIDA" DE LA PROPIA FICHA TÉCNICA (secciones 8 y 10), no
inventada: la ficha da explícitamente el patrón de frase recomendado
("El puntaje obtenido se encuentra en el rango interpretativo utilizado
para esta población...") precisamente para evitar la formulación
categórica que advierte en contra. Se usa ese patrón tal cual en los 6
tramos (3 por criterio).

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_POR_TRAMO más abajo y
_asegurar_contenido_informe): `motivo_consulta_default`/`tecnicas_
adicionales="Entrevista, Observación"` de la prueba, y `Baremo.
interpretacion`/`conclusion_sugerida`/`recomendacion_sugerida` de los 3
tramos del criterio ACTIVO (sección 8, `criterio_normativo IS NULL`)
quedan completos — el segundo criterio (`percentil_n1228`) se deja
deliberadamente SIN este contenido, mismo criterio exacto que seed_gad7.py
con su criterio peruano. `interpretacion` conserva el patrón de redacción
no-categórica ya documentado arriba (tomado de la propia ficha técnica) y
le AÑADE la descripción cualitativa de un informe EAR real de referencia
(adaptada a "el/la evaluado/a", generalizada para los 3 tramos — el
ejemplar solo mostraba el tramo "Baja").

⚠️ EL EJEMPLAR DE REFERENCIA SE CONTRADICE A SÍ MISMO — NO SE REPLICÓ LA
CONTRADICCIÓN: su propia sección "Cualitativo" calcula correctamente
puntaje total 20 → tramo "Baja" (coincide exactamente con el criterio
activo de este script: 10-25 = Baja), pero su sección "6. CONCLUSIONES"
dice "autoestima MODERADA... está bien" — un error de redacción del
documento fuente (quizás una plantilla reusada sin actualizar), no un
dato a preservar. El contenido cargado aquí es consistente con el tramo
realmente alcanzado (Baja), nunca con la conclusión contradictoria.
Tampoco se reutilizó el texto de "7. RECOMENDACIONES" del ejemplar (habla
de la situación familiar específica de ESE paciente — padres separados,
"resistencia a vivir con otras personas" — contenido de caso, no
reutilizable como default de la prueba, mismo criterio ya aplicado en
RCADS-47/SCARED-C con las autoverbalizaciones del paciente).

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT`/`TECNICAS_ADICIONALES` de
arriba quedan como documentación histórica de cómo se derivaron
originalmente — el VALOR REALMENTE CARGADO en la base para esos dos campos
(y el nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que los sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_rosenberg`.
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

NOMBRE_TECNICO = "EAR"

# Texto LITERAL — traducción española de Atienza, Balaguer y Moreno (2000),
# ver advertencia del módulo.
PREGUNTAS = [
    "Me siento una persona tan valiosa como las otras",
    "Generalmente me inclino a pensar que soy un fracaso",
    "Creo que tengo algunas cualidades buenas",
    "Soy capaz de hacer las cosas tan bien como los demás",
    "Creo que no tengo mucho de lo que estar orgulloso",
    "Tengo una actitud positiva hacia mí mismo",
    "En general me siento satisfecho conmigo mismo",
    "Me gustaría tener más respeto por mí mismo",
    "Realmente me siento inútil en algunas ocasiones",
    "A veces pienso que no sirvo para nada",
]

OPCIONES = [
    ("Muy en desacuerdo", 1),
    ("En desacuerdo", 2),
    ("De acuerdo", 3),
    ("Muy de acuerdo", 4),
]

# Ítems invertidos (1-indexados, orden = PREGUNTAS) — ver el hallazgo
# documentado en el docstring del módulo sobre la inconsistencia interna de
# la ficha técnica secundaria.
ITEMS_INVERSOS = {2, 5, 8, 9, 10}


def _verificar_inversos():
    """Falla ruidosamente ANTES de tocar la BD si ITEMS_INVERSOS no es
    exactamente el conjunto documentado y verificado (2,5,8,9,10) — mismo
    criterio defensivo que _verificar_matriz() en seed_chaside.py."""
    if ITEMS_INVERSOS != {2, 5, 8, 9, 10}:
        raise RuntimeError(f"ITEMS_INVERSOS inesperado: {sorted(ITEMS_INVERSOS)}")
    if not (1 <= min(ITEMS_INVERSOS) and max(ITEMS_INVERSOS) <= len(PREGUNTAS)):
        raise RuntimeError("ITEMS_INVERSOS fuera de rango de PREGUNTAS")


# (mínimo, máximo, nivel) — sección 8 de la ficha técnica ("rangos
# orientativos frecuentemente utilizados"), criterio ACTIVO por defecto
# (criterio_normativo=NULL). Ver advertencia del módulo.
CRITERIO_PERCENTIL_N1228 = "percentil_n1228"
BAREMOS = [
    (10, 25, "Baja"),
    (26, 29, "Media"),
    (30, 40, "Elevada"),
]
# Segundo criterio — sección 7 (fuente secundaria, n=1,228, Pc25/50/75).
BAREMOS_PERCENTIL_N1228 = [
    (10, 27, "Baja"),
    (28, 35, "Promedio"),
    (36, 40, "Alta"),
]


def _interpretacion(minimo, maximo, nivel, etiqueta_criterio):
    # Patrón de redacción tomado de la propia ficha técnica (secciones 8/10)
    # — ver advertencia del módulo.
    return (
        f"El puntaje obtenido ({minimo}-{maximo}) se encuentra en el rango interpretativo "
        f"'{nivel.lower()}' de autoestima global, según {etiqueta_criterio}. Este resultado "
        "no constituye un diagnóstico: la Escala de Autoestima de Rosenberg mide autoestima, "
        "no psicopatología, y no existe un punto de corte diagnóstico oficial. Debe "
        "integrarse con la entrevista, observación y demás instrumentos de la evaluación."
    )


# ============================================================
# CONTENIDO DE INFORME — solo criterio activo (sección 8, criterio_
# normativo IS NULL). Ver advertencia del módulo: el tramo "Baja" está
# adaptado de un informe EAR real de referencia; "Media"/"Elevada" se
# extrapolaron en el mismo tono.
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluar el nivel de autoestima global del/de la estudiante mediante la aplicación de la "
    "Escala de Autoestima de Rosenberg (EAR), como parte del proceso de acompañamiento "
    "psicológico institucional."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

# 🆕 Red de seguridad para el criterio percentil_n1228 — ver nota en _asegurar_contenido_informe.
RECOMENDACION_GENERICA_DEFAULT = (
    "Se recomienda mantener el acompañamiento habitual del/de la estudiante y continuar con la "
    "observación periódica propia del seguimiento escolar. De presentarse cambios relevantes en "
    "su autopercepción, se sugiere una nueva evaluación o consulta con el área de psicología."
)

CONTENIDO_POR_TRAMO = {
    "Baja": {
        "color_cualitativo": (
            " Este resultado puede asociarse con una valoración desfavorable de sí mismo/a, "
            "dificultades para reconocer las propias cualidades y capacidades, y una percepción "
            "limitada del propio valor personal; también pueden presentarse pensamientos "
            "autocríticos y sentimientos de inseguridad."
        ),
        "conclusion": (
            "El resultado obtenido en la Escala de Autoestima de Rosenberg se ubica en el rango "
            "interpretativo 'baja' de autoestima global. Este hallazgo debe interpretarse "
            "conjuntamente con la entrevista psicológica, la observación conductual y los demás "
            "instrumentos aplicados, evitando considerarlo de manera aislada como un diagnóstico "
            "clínico."
        ),
        "recomendacion": (
            "- Fortalecer el reconocimiento de logros y cualidades personales en el espacio "
            "terapéutico.\n"
            "- Favorecer espacios de expresión emocional que permitan explorar la percepción que "
            "el/la evaluado/a tiene de sí mismo/a.\n"
            "- Dar seguimiento psicológico y, de identificarse sintomatología adicional (ansiedad, "
            "estado de ánimo), considerar una evaluación complementaria.\n"
            "- Involucrar al entorno familiar, de ser pertinente, para favorecer un ambiente de "
            "apoyo y validación."
        ),
    },
    "Media": {
        "color_cualitativo": (
            " Este resultado se sitúa en un nivel intermedio: ni una valoración marcadamente "
            "desfavorable ni una autoestima consistentemente elevada. Puede reflejar una "
            "percepción de sí mismo/a variable según el contexto o el momento, con fortalezas y "
            "aspectos a fortalecer reconocidos de forma simultánea."
        ),
        "conclusion": (
            "El resultado obtenido en la Escala de Autoestima de Rosenberg se ubica en un rango "
            "interpretativo intermedio de autoestima global."
        ),
        "recomendacion": (
            "- Reforzar el reconocimiento de logros y virtudes personales.\n"
            "- Dar seguimiento psicológico a la evolución de la autopercepción del/de la "
            "evaluado/a."
        ),
    },
    "Elevada": {
        "color_cualitativo": (
            " Este resultado puede asociarse con una valoración favorable de sí mismo/a, "
            "reconocimiento de las propias cualidades y capacidades, y una percepción adecuada "
            "del propio valor personal."
        ),
        "conclusion": (
            "El resultado obtenido en la Escala de Autoestima de Rosenberg se ubica en el rango "
            "interpretativo 'elevada' de autoestima global."
        ),
        "recomendacion": (
            "- Mantener y reforzar las dinámicas que sostienen esta valoración positiva de sí "
            "mismo/a.\n"
            "- No se identifica necesidad de intervención adicional por este motivo."
        ),
    },
}


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba, y
    reescribe interpretacion (le añade el color cualitativo de
    CONTENIDO_POR_TRAMO al patrón de redacción ya existente, tomado de la
    ficha técnica — nunca lo reemplaza del todo) más conclusion_sugerida/
    recomendacion_sugerida de los 3 tramos del criterio ACTIVO —
    idempotente: interpretacion SIEMPRE se reemplaza si difiere (mismo
    criterio que seed_gad7.py/seed_apgar_familiar.py/seed_scared.py;
    seguro solo porque no hay ninguna inscripción real de EAR en la base a
    la fecha de esta carga); conclusion_sugerida/recomendacion_sugerida
    solo se completan si están vacíos."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")
    # 🆕 Red de seguridad (auditoría de contenido, sesión 2026-10-12): el
    # criterio `percentil_n1228` (ver _asegurar_criterio_percentil_n1228 más
    # abajo) nunca recibe conclusion_sugerida/recomendacion_sugerida en
    # ninguno de sus 3 tramos — decisión deliberada (mismo criterio que el
    # corte peruano de GAD-7), pero sin esta red de seguridad una
    # institución que active ese criterio se quedaría con las secciones 6/7
    # vacías. Mismo patrón que CHASIDE/IPIP-RIASEC/RCADS-47/APGAR-FAMILIAR.
    if not prueba.recomendacion_generica_default:
        prueba.recomendacion_generica_default = RECOMENDACION_GENERICA_DEFAULT
        cambios.append("recomendacion_generica_default")

    baremos_activos = db.query(models.Baremo).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(
        models.Dimension.prueba_id == prueba.id,
        models.Baremo.criterio_normativo.is_(None),
    ).all()

    baremos_actualizados = 0
    for baremo in baremos_activos:
        contenido = CONTENIDO_POR_TRAMO.get(baremo.nivel)
        if not contenido:
            continue
        cambio_tramo = False
        interpretacion_nueva = _interpretacion(
            int(baremo.puntaje_minimo), int(baremo.puntaje_maximo), baremo.nivel,
            "los rangos orientativos frecuentemente utilizados en aplicaciones académicas y clínicas",
        ) + contenido["color_cualitativo"]
        if baremo.interpretacion != interpretacion_nueva:
            baremo.interpretacion = interpretacion_nueva
            cambio_tramo = True
        if not baremo.conclusion_sugerida:
            baremo.conclusion_sugerida = contenido["conclusion"]
            cambio_tramo = True
        if not baremo.recomendacion_sugerida:
            baremo.recomendacion_sugerida = contenido["recomendacion"]
            cambio_tramo = True
        if cambio_tramo:
            baremos_actualizados += 1

    if not cambios and not baremos_actualizados:
        print("↪️  El contenido del informe (motivo, técnicas, interpretación/conclusión/recomendación) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) del criterio activo con interpretación/conclusión/recomendación.")


def _asegurar_criterio_percentil_n1228(db, prueba) -> None:
    """Idempotente y aditivo (mismo patrón que _asegurar_criterio_peru en
    seed_gad7.py): añade el segundo criterio normativo si todavía no existe
    para esta prueba."""
    dimension = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).first()
    if not dimension:
        print("⚠️  EAR no tiene dimensión cargada todavía; no se puede añadir el segundo criterio.")
        return

    ya_existe = db.query(models.Baremo).filter(
        models.Baremo.dimension_id == dimension.id,
        models.Baremo.criterio_normativo == CRITERIO_PERCENTIL_N1228,
    ).first()
    if ya_existe:
        print(f"↪️  El criterio normativo '{CRITERIO_PERCENTIL_N1228}' ya estaba cargado; no se toca.")
        return

    for minimo, maximo, nivel in BAREMOS_PERCENTIL_N1228:
        db.add(models.Baremo(
            dimension_id=dimension.id,
            edad_min=None, edad_max=None, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
            interpretacion=_interpretacion(
                minimo, maximo, nivel,
                "la tabla de percentiles de una muestra de 1,228 estudiantes (Pc25/Pc50/Pc75)",
            ),
            es_alerta=False,
            criterio_normativo=CRITERIO_PERCENTIL_N1228,
        ))
    db.commit()
    print(f"✅ Criterio normativo '{CRITERIO_PERCENTIL_N1228}' añadido: {len(BAREMOS_PERCENTIL_N1228)} "
          "tramo(s). Sigue inactivo por defecto — Prueba.criterio_normativo_activo es NULL "
          "(usa los rangos orientativos de la sección 8) hasta que se haga PATCH explícito.")


def cargar():
    _verificar_inversos()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  EAR ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_criterio_percentil_n1228(db, existente)
            _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala de Autoestima de Rosenberg (EAR)",
            instrucciones=(
                "Lee las frases que figuran a continuación y señala tu nivel de acuerdo o "
                "desacuerdo con cada una de ellas."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=1,
            escala_maxima=4,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoadministrada
            # No es un instrumento de tamizaje de recall corto (no hay
            # "últimas 2 semanas" como PHQ-9/GAD-7); la autoestima es un
            # rasgo relativamente estable — mismo criterio de intervalo que
            # seed_apgar_familiar.py, otro constructo no agudo.
            dias_minimos_entre_aplicaciones=90,
        )
        db.add(prueba)
        db.flush()

        dimension = models.Dimension(
            prueba_id=prueba.id,
            nombre="Autoestima Global",
            descripcion=(
                "Puntaje único de la EAR (suma de los 10 ítems, 10-40) — concepción "
                "unidimensional original de Rosenberg (1965). La estructura positiva/negativa "
                "discutida en la literatura NO debe programarse como dos dimensiones "
                "independientes (ver docstring de seed_rosenberg.py)."
            ),
        )
        db.add(dimension)
        db.flush()

        for orden, texto in enumerate(PREGUNTAS, start=1):
            pregunta = models.Pregunta(
                prueba_id=prueba.id,
                dimension_id=dimension.id,
                texto_pregunta=texto,
                orden=orden,
                es_inverso=orden in ITEMS_INVERSOS,
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in OPCIONES:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                ))

        for minimo, maximo, nivel in BAREMOS:
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=_interpretacion(
                    minimo, maximo, nivel,
                    "los rangos orientativos frecuentemente utilizados en aplicaciones académicas y clínicas",
                ),
                es_alerta=False,
                criterio_normativo=None,  # activo por defecto
            ))

        db.commit()
        print(f"✅ EAR cargado: prueba id={prueba.id}, dimensión id={dimension.id}, "
              f"{len(PREGUNTAS)} preguntas ({len(ITEMS_INVERSOS)} inversas: "
              f"{sorted(ITEMS_INVERSOS)}), {len(BAREMOS)} tramos de baremo (criterio activo "
              "por defecto).")

        _asegurar_criterio_percentil_n1228(db, prueba)
        _asegurar_contenido_informe(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando EAR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
