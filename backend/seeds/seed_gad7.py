"""
Carga el catálogo PÚBLICO (institucion_id=None) del GAD-7 — prueba, dimensión
única, 7 ítems con sus 4 alternativas, y los tramos de baremo por puntaje
total (Spitzer, Kroenke, Williams & Löwe, 2006; punto de corte clásico
replicado en la adaptación española de García-Campayo et al., 2010).

Es idempotente: si "GAD-7" ya existe como prueba pública, no toca nada (para
no pisar baremos que un psicólogo haya ajustado a mano después de la carga
inicial). Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_gad7

✅ CONTENIDO DE INFORME YA CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más abajo):
`Prueba.motivo_consulta_default`/`tecnicas_adicionales` y, por cada tramo
del criterio CLÁSICO, `Baremo.conclusion_sugerida`/`recomendacion_sugerida`
— contenido para el PDF profesional (fuente "B", ver CLAUDE.md "FUENTES DE
CONTENIDO DEL INFORME") — están completos, mismo patrón idempotente que
`seed_phq9.py._asegurar_contenido_informe` (`_asegurar_contenido_informe_
gad7`, aditivo, nunca pisa contenido que un psicólogo haya editado a mano).
El tramo "Severa" del criterio clásico está adaptado casi literalmente de un
informe GAD-7 real de referencia (caso de ansiedad severa) que una
psicóloga entregó como ejemplo; los otros tres tramos del clásico se
extrapolaron en el mismo tono. El criterio peruano (`BAREMOS_CRITERIO_PERU`
más abajo) sigue deliberadamente sin este contenido — decisión explícita,
no un olvido, ver `_asegurar_contenido_informe_gad7`.

⚠️ TEXTO DE LOS 7 ÍTEMS — PROVISIONAL, NO ES EL FORMULARIO OFICIAL:
la ficha técnica que sustenta esta carga advierte explícitamente que los
ítems originales del GAD-7 están protegidos por derechos de autor y no los
reproduce; solo entrega el CONTENIDO temático que evalúa cada uno (p. ej.
"Nerviosismo, ansiedad o tensión"). Ese es el texto que se carga aquí, tal
cual, marcado como no-literal. Antes de usar esta prueba con estudiantes
reales, reemplazar PREGUNTAS por el texto exacto del formulario licenciado
que usará la institución — es un cambio de datos (UPDATE sobre
edu_preguntas.texto_pregunta), nunca de estructura ni de código.

⚠️ DOS CRITERIOS DE CORTE EN LA EVIDENCIA — AHORA AMBOS CARGADOS, UNO SOLO
ACTIVO POR DEFECTO (ver `Baremo.criterio_normativo`/`Prueba.criterio_
normativo_activo` en models.py):
la ficha reporta un corte clásico/internacional (≥10, sensibilidad 86.8%/
especificidad 93.4% en la adaptación española) y un corte reportado en
evidencia peruana (≥8, sensibilidad 84.7%/especificidad 50.1%, y que el
propio estudio peruano de 2024 NO propuso como su punto de corte oficial).
Antes de que existiera `criterio_normativo`, el modelo `Baremo` no tenía
ningún eje para esto: dos tramos que compartan dimensión/sexo/población y se
solapen en el rango de puntaje (aquí, 8-9) eran rechazados por la validación
de solapamiento (409). Ahora cada criterio es un LENTE con su propia
etiqueta: el corte clásico queda, como siempre, con `criterio_normativo=NULL`
(es el que usa `Prueba.criterio_normativo_activo=NULL`, el comportamiento por
defecto — cero cambio respecto a antes de esta carga) y el corte peruano se
añade como un SEGUNDO conjunto de tramos con `criterio_normativo=
"corte_peru_2024"`, cargado por `_asegurar_criterio_peru()` (idempotente y
aditivo, mismo patrón que `seed_phq9.py._asegurar_contenido_informe`: corre
incluso si GAD-7 ya existía, y nunca pisa nada). El corte peruano es un
UMBRAL ÚNICO documentado por la ficha (≥8 = cribado positivo), no cuatro
niveles como el clásico — se carga tal cual lo reporta la evidencia (2
tramos), sin inventar niveles intermedios que la fuente no define (ver "NO
INVENTAR CONTENIDO").

Para que una institución use el corte peruano en vez del clásico:
`PATCH /educativo/pruebas/{id}` con `{"criterio_normativo_activo":
"corte_peru_2024"}`, y después `POST /educativo/inscripciones/{id}/reprocesar`
sobre las inscripciones que se quieran reinterpretar con el nuevo criterio
(no reprocesa nada por sí solo).

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT`/`TECNICAS_ADICIONALES` de
arriba quedan como documentación histórica de cómo se derivaron
originalmente — el VALOR REALMENTE CARGADO en la base para esos dos campos
(y el nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que los sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_gad7`.
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

# Contenido TEMÁTICO de cada ítem (no el texto literal protegido del
# formulario original) — ver advertencia arriba.
PREGUNTAS = [
    "Nerviosismo, ansiedad o tensión",
    "Incapacidad para dejar de preocuparse",
    "Preocupación excesiva por diferentes asuntos",
    "Dificultad para relajarse",
    "Inquietud o dificultad para permanecer quieto(a)",
    "Irritabilidad",
    "Sensación de que algo malo podría ocurrir",
]

OPCIONES = [
    ("En absoluto", 0),
    ("Varios días", 1),
    ("Más de la mitad de los días", 2),
    ("Casi todos los días", 3),
]

# (mínimo, máximo, nivel, es_alerta, interpretación)
# Corte clásico/internacional (Spitzer et al., 2006): ≥10 = cribado positivo,
# por eso "Moderada" y "Severa" quedan es_alerta=True. criterio_normativo=NULL
# — es el criterio ACTIVO por defecto (Prueba.criterio_normativo_activo=NULL).
# Ver BAREMOS_CRITERIO_PERU más abajo para el segundo criterio cargado.
# 🆕 Revisión crítica de contenido (ver docs/informes-psicometricos.md): el
# texto de interpretación original (citas/corte clínico) y el narrativo
# agregado después por `_asegurar_contenido_informe_gad7` vivían como dos
# fragmentos pegados uno detrás del otro — en 3 de los 4 tramos eso producía
# una redundancia real y visible en el PDF (ambas mitades describían la
# misma intensidad con palabras distintas). Reescrito aquí como UN solo
# párrafo cohesivo por tramo, que conserva las citas donde las había
# (ninguna se perdió) y el contenido del informe de referencia (tramo
# "Severa", adaptado de un caso real que una psicóloga entregó como
# ejemplo), sin repetirse.
BAREMOS = [
    (0, 4, "Mínima", False,
     "El puntaje se encuentra dentro del rango mínimo de síntomas de ansiedad evaluados por el "
     "GAD-7: no se observan indicadores relevantes de preocupación excesiva, inquietud o dificultad "
     "para relajarse, y el resultado es compatible con un funcionamiento emocional habitual en "
     "relación con la ansiedad. Esto no implica ausencia absoluta de ansiedad ni descarta la "
     "necesidad de observación habitual."),
    (5, 9, "Leve", False,
     "El puntaje corresponde a una presencia leve de síntomas de ansiedad: pueden observarse "
     "manifestaciones puntuales de preocupación o tensión que, por su intensidad, no alcanzan "
     "todavía un nivel clínicamente significativo. La interpretación debe considerar el contexto y "
     "el funcionamiento cotidiano del estudiante."),
    (10, 14, "Moderada", True,
     "Puntaje que supera el punto de corte clásico de cribado (≥10, Spitzer et al., 2006; "
     "replicado en la adaptación española con sensibilidad 86.8% y especificidad 93.4%), con "
     "indicadores compatibles con preocupación frecuente, dificultad para controlar las "
     "preocupaciones, inquietud y dificultades para relajarse, que podrían empezar a interferir en "
     "algunas actividades cotidianas del estudiante. Nota: evidencia peruana (Baños-Chaparro, 2024) "
     "reporta un corte alternativo de ≥8 (criterio_normativo='corte_peru_2024', cargado por separado "
     "— ver BAREMOS_CRITERIO_PERU) con especificidad mucho menor (50.1%); este es el criterio ACTIVO "
     "por defecto, por su mejor desempeño diagnóstico y mayor replicación."),
    (15, 21, "Severa", True,
     "El resultado evidencia una elevada frecuencia e intensidad de los síntomas evaluados por el "
     "GAD-7, con indicadores compatibles con preocupación frecuente, dificultad para controlar las "
     "preocupaciones, inquietud, nerviosismo y dificultades para relajarse, que podrían estar "
     "interfiriendo en actividades cotidianas del estudiante, especialmente en situaciones que "
     "demanden atención, adaptación a cambios o afrontamiento de situaciones percibidas como "
     "difíciles. Por tratarse de una herramienta de tamizaje, el resultado debe considerarse un "
     "indicador de posible sintomatología ansiosa y no un diagnóstico por sí mismo — se sugiere "
     "considerar una evaluación clínica integral."),
]

# 🆕 Segundo criterio normativo — corte peruano ≥8 (Baños-Chaparro, 2024).
# La evidencia reporta un UMBRAL ÚNICO de cribado, no cuatro niveles como el
# clásico: se carga tal cual (2 tramos), sin inventar niveles intermedios que
# la fuente no define (ver "NO INVENTAR CONTENIDO" en CLAUDE.md).
CRITERIO_PERU = "corte_peru_2024"
BAREMOS_CRITERIO_PERU = [
    (0, 7, "Por debajo del corte de cribado (criterio peruano)", False,
     "Puntaje por debajo del punto de corte de cribado reportado en evidencia peruana "
     "(≥8, Baños-Chaparro, 2024). No implica ausencia absoluta de ansiedad."),
    (8, 21, "Cribado positivo para ansiedad (criterio peruano)", True,
     "Puntaje que alcanza o supera el punto de corte de cribado reportado en evidencia "
     "peruana (≥8, Baños-Chaparro, 2024; sensibilidad 84.7%, especificidad 50.1% — nota: "
     "el propio estudio NO propuso este valor como su punto de corte oficial, y su "
     "especificidad es considerablemente menor que la del corte clásico ≥10). Sugiere "
     "evaluación clínica más detallada."),
]

# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES
# DE CONTENIDO DEL INFORME") — lo único que faltaba desde que se cargó el
# catálogo (ver advertencia de cabecera). motivo_consulta_default adapta la
# sección "Motivo de evaluación" de un informe real de referencia (GAD-7,
# caso de ansiedad severa) al mismo molde institucional ya usado por
# seed_phq9.py. tecnicas_adicionales usa la misma convención.
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para medir la presencia y el nivel de sintomatología ansiosa "
    "reportada por el estudiante durante las últimas dos semanas, en el marco de una campaña de "
    "evaluación psicométrica institucional."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

# Por tramo (mismo rango que BAREMOS arriba, criterio clásico — ver CLAUDE.md,
# el criterio peruano se deja deliberadamente sin este contenido por ahora):
# `conclusion_sugerida`/`recomendacion_sugerida`, que eran NULL. (El texto de
# `interpretacion` ya no vive aquí como fragmento aparte — tras la revisión
# crítica de contenido quedó integrado directamente en cada tupla de
# BAREMOS, como un solo párrafo cohesivo, para no repetir lo mismo dos
# veces dentro del mismo informe.) El tramo "Severa" está adaptado casi
# literalmente de un informe GAD-7 real de referencia (caso de ansiedad
# severa, puntaje 15) que una psicóloga entregó como ejemplo; los otros tres
# tramos se extrapolaron en el mismo tono y nivel de detalle para que las 4
# bandas se sientan parte de un mismo informe, no contenido de calidad
# dispareja.
CONTENIDO_INFORME_POR_TRAMO = {
    (0, 4): {
        "conclusion": (
            "El estudiante obtuvo un puntaje dentro del rango mínimo de sintomatología ansiosa "
            "evaluada por el GAD-7. No se identifican indicadores clínicamente significativos de "
            "ansiedad al momento de la evaluación."
        ),
        "recomendacion": (
            "Se recomienda continuar con el acompañamiento habitual del estudiante. No se requiere "
            "intervención especializada en este momento; se sugiere una nueva evaluación de tamizaje "
            "en el siguiente periodo académico o ante cambios observables en el estudiante."
        ),
    },
    (5, 9): {
        "conclusion": (
            "El puntaje obtenido corresponde a sintomatología ansiosa de grado leve. Se identifican "
            "algunos indicadores que ameritan seguimiento, sin alcanzar aún un nivel clínicamente "
            "significativo."
        ),
        "recomendacion": (
            "Se recomienda seguimiento por parte del área de psicología del colegio, con observación "
            "periódica de la evolución del estudiante. Puede ser útil una conversación exploratoria "
            "breve para descartar factores estresores puntuales."
        ),
    },
    (10, 14): {
        "conclusion": (
            "El puntaje obtenido corresponde a sintomatología ansiosa de grado moderado, lo que "
            "sugiere un impacto relevante en el bienestar del estudiante que amerita atención "
            "profesional."
        ),
        "recomendacion": (
            "Se recomienda derivación a evaluación psicológica individual y seguimiento cercano por "
            "parte del profesional responsable. Se sugiere informar y coordinar con la familia o "
            "apoderados, según el protocolo institucional vigente, y favorecer estrategias sencillas "
            "de regulación emocional y relajación acordes con la edad del estudiante."
        ),
    },
    (15, 21): {
        # Adaptado de "VI. Conclusiones" del informe de referencia.
        "conclusion": (
            "El puntaje obtenido corresponde a sintomatología ansiosa de grado severo, con "
            "indicadores relacionados con preocupación frecuente, nerviosismo, inquietud y dificultad "
            "para relajarse. Los resultados sugieren la presencia de manifestaciones ansiosas que "
            "requieren seguimiento y evaluación complementaria; el resultado obtenido mediante el "
            "GAD-7 no establece por sí mismo un diagnóstico psicológico o clínico, pero constituye un "
            "indicador de alto riesgo que exige atención profesional."
        ),
        # Adaptado de "VII. Recomendaciones" del informe de referencia (lista
        # de viñetas condensada a un párrafo, mismo formato que el resto del
        # contenido configurado de esta prueba y de PHQ-9).
        "recomendacion": (
            "Se recomienda derivación urgente a evaluación especializada (psicología y/o psiquiatría), "
            "activación del protocolo institucional de atención a casos de riesgo, y comunicación "
            "inmediata con la familia o apoderados. Se sugiere además favorecer estrategias sencillas "
            "de regulación emocional y relajación acordes con la edad del estudiante, promover "
            "espacios de comunicación donde pueda expresar sus preocupaciones, y mantener rutinas "
            "estables que favorezcan su sensación de seguridad."
        ),
    },
}

NOMBRE_TECNICO = "GAD-7"

# Evidencia peruana disponible (Villarreal-Zegarra et al., 2024; n=4,431):
# muestra de 12 a 65 años, con invariancia de medida confirmada entre sexos y
# entre adolescentes/adultos — de ahí el rango de edad del baremo y sexo=None.
EDAD_MIN = 12
EDAD_MAX = 65


def _asegurar_criterio_peru(db, prueba) -> None:
    """Añade el segundo criterio normativo (corte peruano ≥8) si todavía no
    existe para esta prueba — idempotente y puramente aditivo, mismo patrón
    que seed_phq9.py._asegurar_contenido_informe: corre incluso si GAD-7 ya
    existía, y nunca pisa un tramo que ya esté cargado."""
    dimension = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).first()
    if not dimension:
        print("⚠️  GAD-7 no tiene dimensión cargada todavía; no se puede añadir el criterio peruano.")
        return

    ya_existe = db.query(models.Baremo).filter(
        models.Baremo.dimension_id == dimension.id,
        models.Baremo.criterio_normativo == CRITERIO_PERU,
    ).first()
    if ya_existe:
        print(f"↪️  El criterio normativo '{CRITERIO_PERU}' ya estaba cargado; no se toca.")
        return

    for minimo, maximo, nivel, es_alerta, interpretacion in BAREMOS_CRITERIO_PERU:
        db.add(models.Baremo(
            dimension_id=dimension.id,
            edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
            interpretacion=interpretacion, es_alerta=es_alerta,
            criterio_normativo=CRITERIO_PERU,
        ))
    db.commit()
    print(f"✅ Criterio normativo '{CRITERIO_PERU}' añadido: {len(BAREMOS_CRITERIO_PERU)} tramo(s). "
          "Sigue inactivo por defecto — Prueba.criterio_normativo_activo es NULL (usa el corte "
          "clásico) hasta que se haga PATCH explícito.")


_INTERPRETACION_CLASICA_POR_RANGO = {
    (minimo, maximo): interpretacion for minimo, maximo, _nivel, _alerta, interpretacion in BAREMOS
}


def _asegurar_contenido_informe_gad7(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba, y
    conclusion_sugerida/recomendacion_sugerida en cada tramo del criterio
    CLÁSICO (criterio_normativo IS NULL) — idempotente y puramente aditivo
    para esos tres campos, mismo patrón que seed_phq9.py._asegurar_
    contenido_informe.

    `interpretacion` es la ÚNICA excepción: revisión crítica de contenido
    (ver docs/informes-psicometricos.md) — se REEMPLAZA por el párrafo
    cohesivo de BAREMOS cuando el tramo todavía tiene el texto viejo
    "fragmentado" (base + narrativo pegados aparte, detectable porque no
    contiene ya el párrafo nuevo). Igual que el enriquecimiento equivalente
    de seed_phq9.py, esto solo es seguro porque a la fecha no hay ninguna
    inscripción real de GAD-7 en la base."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")

    baremos_clasicos = db.query(models.Baremo).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(
        models.Dimension.prueba_id == prueba.id,
        models.Baremo.criterio_normativo.is_(None),
    ).all()

    baremos_actualizados = 0
    for baremo in baremos_clasicos:
        rango = (float(baremo.puntaje_minimo), float(baremo.puntaje_maximo))
        contenido = CONTENIDO_INFORME_POR_TRAMO.get(rango)
        if not contenido:
            continue
        cambio_tramo = False
        interpretacion_nueva = _INTERPRETACION_CLASICA_POR_RANGO.get(
            (int(rango[0]), int(rango[1]))
        )
        if interpretacion_nueva and interpretacion_nueva != baremo.interpretacion:
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
        print("↪️  El contenido del informe (motivo, técnicas, conclusiones, recomendaciones) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{baremos_actualizados} tramo(s) del criterio clásico con interpretación/conclusión/"
          "recomendación añadidas.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  GAD-7 ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_criterio_peru(db, existente)
            _asegurar_contenido_informe_gad7(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala de Ansiedad Generalizada (GAD-7)",
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
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoadministrada
            # Mismo período de referencia que la escala (últimas 2 semanas):
            # reaplicar antes de que termine esa ventana no aporta una
            # medición independiente.
            dias_minimos_entre_aplicaciones=14,
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
            tecnicas_adicionales=TECNICAS_ADICIONALES,
        )
        db.add(prueba)
        db.flush()

        dimension = models.Dimension(
            prueba_id=prueba.id,
            nombre="Ansiedad Generalizada",
            descripcion=(
                "Puntaje único del GAD-7 (suma de los 7 ítems, 0-21) — estructura unifactorial "
                "confirmada tanto en la validación original (Spitzer et al., 2006) como en "
                "muestras peruanas (Villarreal-Zegarra et al., 2024; Franco-Jiménez y "
                "Núñez-Magallanes, 2022). No debe programarse ni interpretarse como 7 "
                "dimensiones independientes."
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
                es_inverso=False,  # el GAD-7 no tiene ítems inversos
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in OPCIONES:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id,
                    texto_opcion=texto_opcion,
                    valor_puntuacion=valor,
                ))

        for minimo, maximo, nivel, es_alerta, interpretacion in BAREMOS:
            contenido = CONTENIDO_INFORME_POR_TRAMO.get((minimo, maximo), {})
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN,
                edad_max=EDAD_MAX,
                sexo=None,       # unisex — invariancia por sexo confirmada en evidencia peruana
                poblacion=None,  # el GAD-7 segmenta por edad, no por nivel educativo
                puntaje_minimo=minimo,
                puntaje_maximo=maximo,
                nivel=nivel,
                interpretacion=interpretacion,  # ya es el párrafo cohesivo completo, ver BAREMOS arriba
                conclusion_sugerida=contenido.get("conclusion"),
                recomendacion_sugerida=contenido.get("recomendacion"),
                es_alerta=es_alerta,
            ))

        for minimo, maximo, nivel, es_alerta, interpretacion in BAREMOS_CRITERIO_PERU:
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=EDAD_MIN, edad_max=EDAD_MAX, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=interpretacion, es_alerta=es_alerta,
                criterio_normativo=CRITERIO_PERU,
            ))

        db.commit()
        print(f"✅ GAD-7 cargado: prueba id={prueba.id}, dimensión id={dimension.id}, "
              f"{len(PREGUNTAS)} preguntas, {len(BAREMOS)} tramos de baremo criterio clásico "
              f"(activo por defecto, con contenido de informe completo) + {len(BAREMOS_CRITERIO_PERU)} "
              f"tramo(s) criterio '{CRITERIO_PERU}' (edad {EDAD_MIN}-{EDAD_MAX}, sin contenido de "
              "informe propio todavía — ver cabecera del archivo).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando GAD-7: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
