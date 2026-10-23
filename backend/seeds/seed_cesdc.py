"""
Carga el catálogo PÚBLICO (institucion_id=None) del CES-DC — prueba, dimensión
única ("CES-DC Total"), 20 ítems con sus 4 alternativas (escala 0-3), y el
único tramo de baremo con evidencia verificable: el punto de corte
tradicional/internacional ≥15 (Weissman, Orvaschel & Padian, 1980; Faulstich
et al., 1986; replicado como punto de corte óptimo en población escolar
española por Visier-Alfonso et al., 2024).

Es idempotente: si "CES-DC" ya existe como prueba pública, no toca nada. Para
forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_cesdc

⚠️ TEXTO DE LOS 20 ÍTEMS — LITERAL, TOMADO DEL PROTOCOLO DE APLICACIÓN REAL
proporcionado (encabezado "Inventario de evaluación del Centro de Estudios
de Epidemiologia — escala de Depresión para niños y adolescentes CES-DC"),
no de la paráfrasis temática en inglés de la ficha técnica secundaria —
mismo criterio ya usado para CHASIDE (protocolo UCASAL)/SCARED-C (formulario
Htal. Zubizarreta)/RCADS-47 (formulario oficial childfirst.ucla.edu): cuando
existe un formulario real en uso clínico, ese es el texto que se carga, no
un resumen de una ficha secundaria.

⚠️ DISCREPANCIA DETECTADA ENTRE EL PROTOCOLO REAL Y LA FICHA TÉCNICA
SECUNDARIA (ítem 17) — NO RESUELTA AUTOMÁTICAMENTE, por lo que queda
documentada en vez de "corregida" por código: el protocolo real dice
"Sentía gusto de gritar" (sensación de gritar), mientras que la ficha
técnica describe el contenido temático del ítem 17 como "Sensación de
querer llorar" (sensación de llanto) — el ítem 17 original en inglés de la
CES-D/CES-DC es, en la literatura, "I felt like crying". Se cargó el texto
LITERAL del protocolo real (es el formulario que de hecho se aplica), no la
paráfrasis de la ficha. Esto NO afecta el sentido de puntuación (el ítem 17
no es uno de los 4 ítems invertidos) — es una discrepancia de contenido/
traducción, no de dirección de puntaje. Si el equipo clínico determina que
es un error de transcripción del protocolo, corregir
`edu_preguntas.texto_pregunta` es un cambio de datos, no de estructura.

⚠️ UNA SOLA DIMENSIÓN A PROPÓSITO ("CES-DC Total", NO tres subescalas):
la propia ficha técnica es explícita en su sección "Para software": "La
dimensión principal debe ser: CES-DC Total (20 ítems). Las tres dimensiones
factoriales deben mantenerse como información secundaria, porque no existe
una única estructura factorial universal que deba utilizarse como sistema
obligatorio de puntuación" — ni el estudio original (Faulstich et al.) ni la
validación española reciente (671 escolares, 9-11 años) coinciden en una
estructura factorial fija y universalmente aceptada para implementar como
subescalas independientes. Mismo criterio ya aplicado a APGAR-FAMILIAR
(unidimensional pese a tener 5 componentes conceptuales) y a EAR/Rosenberg
(unidimensional pese a la discusión de estructura positiva/negativa en la
literatura) — no se cargan "Afecto depresivo"/"Somático"/"Felicidad" como
Dimension independientes.

⚠️ SOLO UN CRITERIO NORMATIVO CARGADO (a diferencia de GAD-7/APGAR-FAMILIAR/
EAR/SDQ-CAS, que sí tienen dos): la ficha técnica reporta que el punto de
corte óptimo "puede variar aproximadamente entre 12 y 24 dependiendo de la
muestra", pero NO entrega una segunda tabla de corte concreta y verificable
— solo un rango aproximado sin un valor único alternativo documentado, a
diferencia de GAD-7 (corte peruano ≥8 concreto) o APGAR-FAMILIAR (Sistema B
concreto). Cargar un "segundo criterio" con un valor inventado dentro de ese
rango violaría "NO INVENTAR CONTENIDO" (CLAUDE.md). La ficha también es
explícita (sección 7.3) en que NO existe un baremo peruano nacional
verificado de la CES-DC-20 — por eso el único tramo cargado se registra como
"Punto de corte de referencia internacional/tradicional", nunca como
"baremo peruano".

⚠️ SOLO DOS NIVELES, NO CUATRO (mínima/leve/moderada/severa): la ficha
técnica (sección 12.E, "Interpretación por niveles") es explícita: "no
existe evidencia suficiente para establecer universalmente categorías como
mínima/leve/moderada/severa... por tanto, no recomiendo programar esas
cuatro categorías salvo que se adopte explícitamente un manual/estudio que
las defina". Se cargan únicamente los dos niveles que la fuente sí define
con un punto de corte verificable: por debajo del corte (0-14) y
alcanza/supera el corte (15-60).

⚠️ edad_min/edad_max DELIBERADAMENTE NULL (sin filtro de edad en el baremo):
la ficha técnica reporta rangos de edad incompatibles entre sí según la
fuente (algunas fuentes sitúan su uso entre 6 y 17 años, otras revisiones de
tamizaje usan específicamente 12-18 años) y concluye explícitamente: "la
edad debe registrarse según la versión/protocolo que se adopte" — no hay un
rango único verificable para fijar edad_min/edad_max sin inventar un
recorte que la fuente no define. sexo=None (ninguna fuente reporta un
baremo diferenciado por sexo) y poblacion=None (sin segmentación por nivel
educativo documentada).

⚠️ SIN ReglaInterpretacion — la ficha técnica es explícita (sección 8): "No
existen ítems críticos". A diferencia de PHQ-9 (ítem 9, ideación suicida) o
RCADS-47 (ítem 37, pensamientos sobre la muerte), la CES-DC no tiene ningún
ítem individual que la fuente consultada identifique como gatillo de alerta
independiente del puntaje total.

✅ CONTENIDO DE INFORME YA CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más
abajo): `Baremo.conclusion_sugerida`/`recomendacion_sugerida` en los dos
tramos del único criterio cargado — contenido para el PDF profesional
(fuente "B", ver CLAUDE.md "FUENTES DE CONTENIDO DEL INFORME"), mismo
patrón idempotente que `seed_gad7.py._asegurar_contenido_informe_gad7`
(aditivo, nunca pisa contenido que un psicólogo haya editado a mano). El
tramo "Alcanza/supera el punto de corte" está adaptado del informe CES-DC
real de referencia que una psicóloga entregó como ejemplo (caso de 18
puntos, clasificado por el propio ejemplar como "leve a moderada" — CES-DC
solo carga dos niveles, ver advertencia arriba, así que ese ejemplar cae
íntegro dentro de este único tramo de alerta); el tramo "Por debajo del
punto de corte" se extrapoló en el mismo tono, mismo criterio que los
tramos no cubiertos por el ejemplar de GAD-7. El ejemplar describe además
hallazgos "por componente" (afecto disfórico, somático, afecto positivo
invertido, relaciones interpersonales) que corresponden a la estructura de
tres sub-escalas factoriales que la propia ficha técnica indica NO cargar
como `Dimension` independientes (ver advertencia "UNA SOLA DIMENSIÓN A
PROPÓSITO" arriba) — ese desglose por componente no se trasladó al
contenido cargado aquí porque no hay ningún puntaje por componente que la
plataforma calcule o pueda citar de forma verificable por aplicación; el
texto cargado se mantiene a nivel del puntaje total, igual que el resto del
informe de este instrumento.
`motivo_consulta_default`/`tecnicas_adicionales` siguen NULL en este
archivo a propósito — los fija `seeds/normalizar_contenido_comun.py` al
mismo texto estándar de las 14 pruebas, ver su propio docstring.

⚠️ PERIODO DE RECALL = LA SEMANA ANTERIOR (no 2 semanas como PHQ-9/GAD-7):
dias_minimos_entre_aplicaciones=7, siguiendo el mismo razonamiento que fijó
PHQ-9/GAD-7 en 14 (reaplicar antes de que termine la ventana de recall no
produce una medición independiente). La ficha advierte explícitamente
(sección 11.5) no cambiar este periodo a "últimas dos semanas".

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): los tres campos procedimentales —
`motivo_consulta_default`, `tecnicas_adicionales` y el nuevo
`observacion_conductual_default` — quedan cargados vía
`seeds/normalizar_contenido_comun.py`, que los fija al mismo texto estándar
en TODAS las pruebas públicas. Ejecutarlo después de cualquier `python -m
seeds.seed_cesdc`.

🆕 ACTUALIZACIÓN POSTERIOR #2 (ejemplar real recibido): el contenido
clínico por tramo (`conclusion_sugerida`/`recomendacion_sugerida`) que este
docstring documentaba como pendiente arriba ya está cargado — ver
"✅ CONTENIDO DE INFORME YA CARGADO" más arriba. CES-DC ya no es el único
instrumento sin contenido de informe (ver docs/catalogo-pruebas.md).
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

NOMBRE_TECNICO = "CES-DC"

# Texto literal del protocolo de aplicación real (ver advertencia sobre el
# ítem 17 en el docstring del módulo).
PREGUNTAS = [
    "Me sentía incomodo por las cosas que usualmente no me son molestas",
    "No tenía ganas de comer. No tenía hambre",
    "No era capaz de sentirme feliz, incluso aunque mi familia y mis amigos me ayudaran a sentirme mejor",
    "Sentía que era apenas tan bueno como los demás compañeros",
    "Sentía que no podía poner atencion a lo que hacia",
    "Me sentía decaído e infeliz",
    "Sentía como que estaba demasiado cansado",
    "Sentía como que algo bueno iba a suceder",
    "Sentía que las cosas que antes hice, ahora no las resolvía bien.",
    "Me sentía asustado",
    "No dormía tan bien como generalmente duermo.",
    "Estaba feliz",
    "Era más reservado que por lo general",
    "Me sentía solo, como si no tuviera ningún amigo.",
    "Sentía que las personas que conozco no quería ser mis amigos o que no querían estar conmigo",
    "Pasaba buenos ratos",
    "Sentía gusto de gritar",
    "Me sentía triste",
    "Sentía que no le gustaba a la gente",
    "Me costaba trabajo comenzar a hacer las cosas",
]

OPCIONES = [
    ("No del todo", 0),
    ("Un poco", 1),
    ("Algo", 2),
    ("Mucho", 3),
]

# Ítems invertidos (1-indexados, orden = PREGUNTAS) — ficha técnica sección 3
# ("Distribución de ítems positivos y negativos") y sección 4 ("Ítems
# invertidos"), ambas coinciden sin contradicción: 4, 8, 12 y 16.
ITEMS_INVERSOS = {4, 8, 12, 16}


def _verificar_inversos():
    """Falla ruidosamente ANTES de tocar la BD si ITEMS_INVERSOS no es
    exactamente el conjunto documentado (4,8,12,16) — mismo criterio
    defensivo que seed_rosenberg.py/_verificar_inversos() y
    seed_chaside.py/_verificar_matriz()."""
    if ITEMS_INVERSOS != {4, 8, 12, 16}:
        raise RuntimeError(f"ITEMS_INVERSOS inesperado: {sorted(ITEMS_INVERSOS)}")
    if not (1 <= min(ITEMS_INVERSOS) and max(ITEMS_INVERSOS) <= len(PREGUNTAS)):
        raise RuntimeError("ITEMS_INVERSOS fuera de rango de PREGUNTAS")


# (mínimo, máximo, nivel, es_alerta, interpretación) — único criterio
# cargado, criterio_normativo=NULL (activo por defecto). Solo dos niveles,
# ver advertencia en el docstring sobre por qué no se cargan cuatro.
BAREMOS = [
    (0, 14, "Por debajo del punto de corte", False,
     "Puntaje por debajo del punto de corte de referencia internacional/tradicional (15, "
     "Weissman et al., 1980; Faulstich et al., 1986). Según este criterio de tamizaje, no se "
     "evidencia una elevación significativa de sintomatología depresiva. No equivale a ausencia "
     "absoluta de síntomas depresivos, y los resultados deben integrarse con la entrevista, "
     "observación y demás instrumentos administrados."),
    (15, 60, "Alcanza/supera el punto de corte de tamizaje", True,
     "Puntaje que alcanza o supera el punto de corte de referencia internacional/tradicional "
     "(≥15, Weissman et al., 1980; Bright Futures/American Academy of Pediatrics; replicado como "
     "corte óptimo en una validación española reciente con 671 escolares de 9-11 años, "
     "Visier-Alfonso et al., 2024). Evidencia una elevación de sintomatología depresiva en el "
     "instrumento y justifica una evaluación complementaria; no permite por sí sola un diagnóstico "
     "de trastorno depresivo."),
]

# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES DE
# CONTENIDO DEL INFORME") — lo único que faltaba desde que se cargó el
# catálogo (ver advertencia de cabecera). El tramo "Alcanza/supera" está
# adaptado del informe CES-DC real de referencia (caso de 18 puntos) que una
# psicóloga entregó como ejemplo; el tramo "Por debajo del corte" se
# extrapoló en el mismo tono, mismo criterio ya usado para completar los
# tramos sin ejemplar directo de GAD-7/PHQ-9. El desglose "por componente"
# del ejemplar (afecto disfórico/somático/afecto positivo/interpersonal) no
# se traslada aquí — ver advertencia en la cabecera del archivo sobre por
# qué CES-DC no carga esas sub-escalas como Dimension independientes.
CONTENIDO_INFORME_POR_TRAMO = {
    (0, 14): {
        "conclusion": (
            "El puntaje obtenido se ubica por debajo del punto de corte de tamizaje del CES-DC, sin "
            "evidenciarse una elevación significativa de sintomatología depresiva durante la última "
            "semana. No se identifican, a partir de este instrumento, indicadores relevantes de afecto "
            "disfórico (tristeza, desánimo) ni alteraciones somáticas o cognitivas (energía, "
            "concentración) que ameriten atención inmediata."
        ),
        "recomendacion": (
            "Se recomienda continuar con el acompañamiento habitual del estudiante. No se requiere "
            "intervención especializada a partir de este resultado; se sugiere una nueva evaluación de "
            "tamizaje en el siguiente periodo académico o ante cambios observables en su estado de "
            "ánimo o comportamiento."
        ),
    },
    (15, 60): {
        # Adaptado de "6. CONCLUSIONES" del informe de referencia (caso de 18 puntos).
        "conclusion": (
            "El puntaje obtenido alcanza o supera el punto de corte de tamizaje del CES-DC, lo que "
            "sugiere la presencia de sintomatología depresiva clínicamente relevante durante la última "
            "semana. El malestar reportado suele concentrarse en manifestaciones de afecto disfórico "
            "(tristeza, desánimo, mayor esfuerzo percibido para realizar actividades cotidianas) y en "
            "alteraciones somáticas/cognitivas asociadas (energía, concentración). Por tratarse de un "
            "instrumento de tamizaje, el resultado no constituye por sí mismo un diagnóstico de "
            "trastorno depresivo y debe integrarse con la entrevista, la observación conductual y los "
            "demás antecedentes recabados."
        ),
        # Adaptado de "7. RECOMENDACIONES" del informe de referencia (lista de
        # viñetas condensada a un párrafo, mismo formato ya usado en GAD-7/PHQ-9).
        "recomendacion": (
            "Se recomienda realizar una entrevista clínica estructurada que profundice en los "
            "desencadenantes de los síntomas reportados y permita descartar comorbilidades. Se sugiere "
            "además brindar acompañamiento psicológico preventivo orientado a la regulación emocional, "
            "la reestructuración cognitiva y el manejo del desánimo, así como fomentar canales de "
            "comunicación asertiva dentro del hogar y psicoeducar a la familia o apoderados sobre el "
            "soporte afectivo durante la adolescencia, según el protocolo institucional vigente."
        ),
    },
}


def _asegurar_contenido_informe_cesdc(db, prueba) -> None:
    """Rellena conclusion_sugerida/recomendacion_sugerida en los dos tramos
    del único criterio cargado — idempotente y puramente aditivo, mismo
    patrón que seed_gad7.py._asegurar_contenido_informe_gad7: corre incluso
    si CES-DC ya existía, y nunca pisa contenido que ya esté cargado."""
    dimension = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).first()
    if not dimension:
        print("⚠️  CES-DC no tiene dimensión cargada todavía; no se puede añadir el contenido del informe.")
        return

    baremos = db.query(models.Baremo).filter(models.Baremo.dimension_id == dimension.id).all()

    baremos_actualizados = 0
    for baremo in baremos:
        rango = (float(baremo.puntaje_minimo), float(baremo.puntaje_maximo))
        contenido = CONTENIDO_INFORME_POR_TRAMO.get(rango)
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

    if not baremos_actualizados:
        print("↪️  El contenido del informe (conclusiones/recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {baremos_actualizados} tramo(s) con "
          "conclusión/recomendación añadidas.")


def cargar():
    _verificar_inversos()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  CES-DC ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_cesdc(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala de Depresión del Centro de Estudios Epidemiológicos para Niños y Adolescentes (CES-DC)",
            instrucciones=(
                "La siguiente es una lista de cómo tú te has estado sintiendo o actuando. Revisa "
                "cuánto te has sentido de esta manera durante la semana pasada."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=3,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoadministrada/autoinforme
            # Periodo de recall = la semana anterior (no 2 semanas) — ver docstring.
            dias_minimos_entre_aplicaciones=7,
        )
        db.add(prueba)
        db.flush()

        dimension = models.Dimension(
            prueba_id=prueba.id,
            nombre="CES-DC Total",
            descripcion=(
                "Puntaje único del CES-DC (suma de los 20 ítems tras invertir 4, 8, 12 y 16; "
                "rango 0-60) — la propia ficha técnica indica que esta debe ser la dimensión "
                "principal, ya que no existe una estructura factorial universal (ni el estudio "
                "original de Faulstich et al. ni una validación española reciente coinciden en "
                "una agrupación fija) que deba cargarse como subescalas independientes."
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

        for minimo, maximo, nivel, es_alerta, interpretacion in BAREMOS:
            contenido = CONTENIDO_INFORME_POR_TRAMO.get((minimo, maximo), {})
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None,   # sin rango de edad único verificable — ver docstring
                edad_max=None,
                sexo=None,       # sin baremo diferenciado por sexo reportado
                poblacion=None,  # sin segmentación por nivel educativo documentada
                puntaje_minimo=minimo,
                puntaje_maximo=maximo,
                nivel=nivel,
                interpretacion=interpretacion,
                conclusion_sugerida=contenido.get("conclusion"),
                recomendacion_sugerida=contenido.get("recomendacion"),
                es_alerta=es_alerta,
            ))

        db.commit()
        print(f"✅ CES-DC cargado: prueba id={prueba.id}, dimensión id={dimension.id}, "
              f"{len(PREGUNTAS)} preguntas ({len(ITEMS_INVERSOS)} inversas: "
              f"{sorted(ITEMS_INVERSOS)}), {len(BAREMOS)} tramos de baremo con conclusión/"
              "recomendación (criterio de referencia internacional/tradicional, punto de corte 15 — "
              "único criterio cargado, sin rango de edad). motivo_consulta_default/tecnicas_"
              "adicionales quedan NULL aquí a propósito (los fija seeds/normalizar_contenido_comun.py "
              "al texto estándar común). Sin ReglaInterpretacion (la ficha técnica no reporta ítems "
              "críticos).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando CES-DC: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
