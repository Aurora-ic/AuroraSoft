"""
Carga el catálogo PÚBLICO (institucion_id=None) del APGAR Familiar — prueba,
dimensión única, 5 ítems con sus 5 alternativas (escala 0-4), y los tramos de
baremo de la adaptación peruana (Castilla, Caycho, Shimabukuro y Valdivia,
2014).

Es idempotente: si "APGAR-FAMILIAR" ya existe como prueba pública, no toca
nada. Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_apgar_familiar

⚠️ NO CONFUNDIR CON EL APGAR NEONATAL — son instrumentos completamente
distintos (uno evalúa funcionamiento familiar percibido, el otro la
condición de un recién nacido). El nombre técnico se elige
deliberadamente como "APGAR-FAMILIAR", nunca solo "APGAR", para que no haya
ambigüedad en ningún listado ni en la lógica de negocio (que además, como
en toda esta plataforma, nunca decide nada comparando nombres — ver
"NO INVENTAR CONTENIDO"/"no logic by name" en CLAUDE.md).

⚠️ SE ELIGIÓ UNA SOLA VERSIÓN ENTRE VARIAS INCOMPATIBLES — igual que
seed_gad7.py con sus dos puntos de corte, aquí hay que decidir entre tres
variantes reales del instrumento que NO deben mezclarse:
  1. Versión original de Smilkstein (1978): 3 alternativas por ítem (0-2),
     total 0-10. Es la más citada internacionally pero nunca fue validada
     en Perú.
  2. Versión infantil (Austin & Huberty, 1989, ~8 años): 3 alternativas,
     misma escala 0-10 que la original (una fuente reproduce el
     encabezado como "(1)(2)(3)" pero el propio texto aclara que puntúa
     0-2 por ítem, y su baremo de corte coincide exactamente con el de la
     versión original de Smilkstein) — pensada para niños pequeños, sin
     ninguna validación peruana.
  3. Adaptación peruana de Castilla et al. (2014): 5 alternativas por
     ítem (0-4), total 0-20 — validada en adolescentes de Lima (11-18
     años, α=.788) y confirmada por un estudio psicométrico posterior de
     2024 en escolares de Lima Norte (11-16 años, α=.872).
Se carga la OPCIÓN 3: es la única con evidencia psicométrica peruana real,
y esta plataforma aplica exámenes a población escolar peruana (Primaria/
Secundaria/Universitario) — la versión infantil de 8 años no encaja con
ese rango, y la versión original de Smilkstein carece de validación local.

⚠️ DE LAS DOS TABLAS DE CORTE PERUANAS REPORTADAS PARA LA VERSIÓN 0-20,
AMBAS QUEDAN CARGADAS — UNA SOLA ACTIVA POR DEFECTO (ver `Baremo.criterio_
normativo`/`Prueba.criterio_normativo_activo` en models.py). La ficha
técnica documenta explícitamente una contradicción real entre dos fuentes:
  Sistema A: 0-9 severa / 10-12 moderada / 13-16 leve / 17-20 adecuada.
  Sistema B: 0-9 severa / 10-13 moderada / 14-17 leve / 18-20 adecuada.
Una fuente adicional e independiente (no ligada a la adaptación peruana
0-20, sino una ficha clínica genérica del instrumento) reporta exactamente
los mismos cortes que el Sistema A (17-20 Normal, 16-13 leve, 12-10
moderada, ≤9 severa) — esa coincidencia independiente es lo que inclinó la
elección del Sistema A como criterio ACTIVO por defecto
(`criterio_normativo=NULL`, `Prueba.criterio_normativo_activo=NULL` — cero
cambio respecto a antes de esta carga). El Sistema B se añade como SEGUNDO
criterio (`criterio_normativo="sistema_b"`) por `_asegurar_criterio_
sistema_b()` (idempotente y aditivo, mismo patrón que
`seed_phq9.py._asegurar_contenido_informe`), para que quede cargado y
trazable si el equipo clínico prefiere usarlo — antes de que existiera
`criterio_normativo` esto no se podía cargar sin que la validación de
solapamiento lo rechazara con 409 (10-12 vs. 10-13 se solapan).

Para que una institución use el Sistema B en vez del Sistema A:
`PATCH /educativo/pruebas/{id}` con `{"criterio_normativo_activo":
"sistema_b"}`, y después `POST /educativo/inscripciones/{id}/reprocesar`
sobre las inscripciones que se quieran reinterpretar con el nuevo criterio.

⚠️ es_alerta: DECISIÓN CLÍNICA EXPLÍCITA, NO UN VALOR POR DEFECTO.
Los tramos "Disfunción severa" y "Disfunción moderada" quedan con
es_alerta=True (retienen el informe hasta revisión profesional, igual que
un tramo alto de PHQ-9/GAD-7); "Disfunción leve" y "Funcionalidad familiar
adecuada" quedan es_alerta=False. Esto sigue el mismo criterio ya usado en
esta plataforma para otros instrumentos: una puntuación que la propia
ficha técnica describe como "indicador de posible alteración... debe
interpretarse junto con entrevista" amerita retención para revisión, no
entrega automática. Es ajustable después vía PATCH /educativo/baremos/{id}
si el protocolo institucional de un colegio difiere.

⚠️ TEXTO DE LOS 5 ÍTEMS — SÍ ES LITERAL: se tomó de un cuestionario público
que reproduce exactamente la estructura de 5 alternativas (0-4) de la
adaptación peruana, no un resumen temático.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_INFORME_POR_TRAMO/
_INTERPRETACION_POR_RANGO más abajo y _asegurar_contenido_informe_apgar):
a diferencia de la carga original de este script (que, mismo criterio que
seed_gad7.py en su momento, dejaba el informe sin contenido), motivo_
consulta_default/tecnicas_adicionales de la prueba y conclusion_sugerida/
recomendacion_sugerida de cada tramo del Sistema A (criterio_normativo
IS NULL, el activo por defecto) quedan cargados — el Sistema B se deja
deliberadamente SIN este contenido, mismo criterio exacto que seed_gad7.py
con su criterio peruano. El tramo "Disfunción moderada" está adaptado
casi literalmente de un informe APGAR Familiar real (caso de un/a
evaluado/a de 12 años, puntaje total 5-6 sobre la versión infantil de 3
alternativas/0-10 — un instrumento DISTINTO al que carga este script, ver
advertencia de arriba sobre las tres versiones) que una psicóloga entregó
como ejemplo de referencia; los otros tres tramos del Sistema A (0-20, el
que esta plataforma sí carga) se extrapolaron en el mismo tono y nivel de
detalle, mismo criterio que seed_gad7.py con sus 4 tramos. `Baremo.
interpretacion` también se reescribe, mismo patrón que la "Revisión
crítica de contenido" de PHQ-9/GAD-7 (ver docs/informes-psicometricos.md)
— único caso documentado donde SÍ se pisa contenido ya cargado, seguro
solo porque no hay ninguna inscripción real de APGAR-FAMILIAR en la base
a la fecha de esta carga.

⚠️ UNIDIMENSIONAL A PROPÓSITO: aunque el instrumento tiene 5 componentes
conceptuales (Adaptación, Participación, Crecimiento, Afectividad,
Capacidad resolutiva), la propia adaptación peruana encontró un único
factor psicométrico — la ficha técnica es explícita: "no debe programarse
automáticamente como cinco subescalas independientes". Se carga como UNA
sola Dimension con los 5 ítems sumados, no cinco.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `motivo_consulta_default`/`tecnicas_adicionales` de
ARRIBA quedan como documentación histórica de cómo se derivaron
originalmente — el VALOR REALMENTE CARGADO en la base para estos dos campos
(y el nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas (decisión de producto, no una
recarga de este archivo). Ejecutarlo después de cualquier `python -m
seeds.seed_apgar_familiar`.
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

NOMBRE_TECNICO = "APGAR-FAMILIAR"

# Texto literal — adaptación peruana de 5 alternativas (0-4). Orden = mismo
# orden de los 5 componentes conceptuales del instrumento (Adaptación,
# Participación, Crecimiento, Afectividad, Capacidad resolutiva).
PREGUNTAS = [
    "Me satisface la ayuda que recibo de mi familia cuando tengo algún problema y/o necesidad.",
    "Me satisface la participación que mi familia brinda y permite.",
    "Me satisface cómo mi familia acepta y apoya mis deseos de emprender nuevas actividades.",
    "Me satisface cómo mi familia expresa afectos y responde a mis emociones como rabia, tristeza y amor.",
    "Me satisface cómo compartimos en familia: el tiempo para estar juntos, los espacios en la casa y el dinero.",
]

OPCIONES = [
    ("Nunca", 0),
    ("Casi nunca", 1),
    ("Algunas veces", 2),
    ("Casi siempre", 3),
    ("Siempre", 4),
]

# (mínimo, máximo, nivel, es_alerta) — Sistema A, criterio_normativo=NULL,
# ACTIVO por defecto. Ver advertencia arriba y BAREMOS_SISTEMA_B más abajo.
BAREMOS = [
    (0, 9, "Disfunción severa", True),
    (10, 12, "Disfunción moderada", True),
    (13, 16, "Disfunción leve", False),
    (17, 20, "Funcionalidad familiar adecuada", False),
]

# 🆕 Segundo criterio normativo — Sistema B (ver advertencia arriba). Mismos
# niveles y mismo criterio de es_alerta que el Sistema A (severa/moderada
# retienen, leve/adecuada no), solo cambian los puntos de corte.
CRITERIO_SISTEMA_B = "sistema_b"
BAREMOS_SISTEMA_B = [
    (0, 9, "Disfunción severa", True),
    (10, 13, "Disfunción moderada", True),
    (14, 17, "Disfunción leve", False),
    (18, 20, "Funcionalidad familiar adecuada", False),
]


# ============================================================
# CONTENIDO DE INFORME — solo Sistema A (criterio_normativo IS NULL, el
# activo por defecto). Ver docstring del módulo: el tramo "Disfunción
# moderada" está adaptado casi literalmente de un informe real de
# referencia; los otros tres se extrapolaron en el mismo tono.
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación del funcionamiento familiar percibido por el/la estudiante, como parte del "
    "proceso de acompañamiento psicológico institucional."
)
TECNICAS_ADICIONALES = "Observación"

# 🆕 Red de seguridad para el Sistema B — ver nota en _asegurar_contenido_informe_apgar.
RECOMENDACION_GENERICA_DEFAULT = (
    "Se recomienda mantener el acompañamiento habitual del/de la estudiante y continuar con la "
    "observación periódica propia del seguimiento escolar. De presentarse cambios relevantes en "
    "la dinámica familiar percibida, se sugiere una nueva evaluación o consulta con el área de "
    "psicología."
)

# (mínimo, máximo) -> párrafo de interpretación reescrito (reemplaza el
# genérico "Puntaje total X-Y: percepción del funcionamiento familiar de
# nivel 'Z'..." — mismo mecanismo que _INTERPRETACION_CLASICA_POR_RANGO de
# seed_gad7.py).
_INTERPRETACION_POR_RANGO = {
    (0, 9): (
        "Puntaje total 0-9: el funcionamiento familiar percibido por el/la evaluado/a se ubica "
        "en el nivel de disfunción severa. La familia no estaría atendiendo de manera suficiente "
        "las necesidades físicas, emocionales y de desarrollo del evaluado/a, con un compromiso "
        "muy limitado para dedicarle tiempo, espacio y apoyo."
    ),
    (10, 12): (
        "Puntaje total 10-12: el funcionamiento familiar percibido por el/la evaluado/a se ubica "
        "en el nivel de disfunción moderada. La familia no estaría atendiendo del todo las "
        "necesidades físicas y emocionales del evaluado/a; no existe un compromiso total para "
        "dedicarle tiempo o espacio."
    ),
    (13, 16): (
        "Puntaje total 13-16: el funcionamiento familiar percibido por el/la evaluado/a se ubica "
        "en el nivel de disfunción leve. La familia atiende en general las necesidades físicas y "
        "emocionales del evaluado/a, aunque se perciben algunas áreas puntuales de mejora en la "
        "comunicación, el tiempo compartido o el apoyo ante nuevas iniciativas."
    ),
    (17, 20): (
        "Puntaje total 17-20: el/la evaluado/a percibe un funcionamiento familiar adecuado. La "
        "familia atiende de manera satisfactoria sus necesidades físicas y emocionales, con un "
        "compromiso real para compartir tiempo, espacio y apoyo."
    ),
}

CONTENIDO_INFORME_POR_TRAMO = {
    (0, 9): {
        "conclusion": (
            "El/la evaluado/a muestra una disfuncionalidad familiar severa, lo que indica que la "
            "familia no estaría atendiendo las necesidades físicas y emocionales del evaluado/a. "
            "No se evidencia un compromiso real para dedicar tiempo, espacio o apoyo dentro del "
            "núcleo familiar."
        ),
        "recomendacion": (
            "- Derivar a un profesional de salud mental y/o terapia familiar de forma prioritaria.\n"
            "- Coordinar con los padres/apoderados una entrevista para profundizar en la dinámica familiar.\n"
            "- Dar seguimiento cercano al caso dentro de la institución educativa.\n"
            "- Evaluar la necesidad de articular con otros servicios de protección si corresponde."
        ),
    },
    (10, 12): {
        "conclusion": (
            "El/la evaluado/a muestra una disfuncionalidad moderada dentro de su grupo familiar, "
            "lo que indica que la familia no atiende del todo a las necesidades físicas y "
            "emocionales del evaluado/a. No existe un compromiso total a dedicar tiempo o espacio."
        ),
        "recomendacion": (
            "- Realizar más actividades familiares.\n"
            "- Fortalecer la comunicación y comprensión en el seno familiar.\n"
            "- Ahondar más en las relaciones familiares.\n"
            "- Buscar un profesional que les ayude a mejorar su relación familiar."
        ),
    },
    (13, 16): {
        "conclusion": (
            "El/la evaluado/a percibe un funcionamiento familiar con disfuncionalidad leve: en "
            "términos generales la familia responde a sus necesidades, aunque se identifican "
            "aspectos puntuales que podrían fortalecerse."
        ),
        "recomendacion": (
            "- Promover espacios regulares de diálogo en familia.\n"
            "- Reconocer y reforzar las fortalezas familiares ya identificadas.\n"
            "- Realizar seguimiento no prioritario del caso."
        ),
    },
    (17, 20): {
        "conclusion": (
            "El/la evaluado/a percibe un funcionamiento familiar adecuado, con una familia que "
            "atiende de manera satisfactoria sus necesidades físicas y emocionales."
        ),
        "recomendacion": (
            "- Mantener y reforzar las dinámicas familiares positivas identificadas.\n"
            "- No se identifica necesidad de intervención adicional por este motivo."
        ),
    },
}


def _asegurar_contenido_informe_apgar(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba, y
    conclusion_sugerida/recomendacion_sugerida en cada tramo del Sistema A
    (criterio_normativo IS NULL) — idempotente y puramente aditivo para
    esos tres campos, mismo patrón exacto que seed_gad7.py._asegurar_
    contenido_informe_gad7.

    `interpretacion` es la ÚNICA excepción: se REEMPLAZA siempre por el
    párrafo de _INTERPRETACION_POR_RANGO, igual que la revisión crítica de
    contenido de PHQ-9/GAD-7 (ver docs/informes-psicometricos.md) — solo es
    seguro porque a la fecha no hay ninguna inscripción real de APGAR-
    FAMILIAR en la base."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.tecnicas_adicionales:
        prueba.tecnicas_adicionales = TECNICAS_ADICIONALES
        cambios.append("tecnicas_adicionales")
    # 🆕 Red de seguridad (auditoría de contenido, sesión 2026-10-12): el
    # Sistema B (segundo criterio normativo, ver _asegurar_criterio_sistema_b
    # más abajo) nunca recibe conclusion_sugerida/recomendacion_sugerida en
    # ninguno de sus 4 tramos — decisión deliberada (mismo criterio que el
    # corte peruano de GAD-7/percentil_n1228 de EAR), pero sin esta red de
    # seguridad una institución que active Sistema B vía `PATCH .../pruebas/
    # {id}` se quedaría con las secciones 6/7 vacías incluso en un tramo de
    # alerta ("Disfunción severa"/"moderada"). Mismo patrón que CHASIDE/
    # IPIP-RIASEC/RCADS-47.
    if not prueba.recomendacion_generica_default:
        prueba.recomendacion_generica_default = RECOMENDACION_GENERICA_DEFAULT
        cambios.append("recomendacion_generica_default")

    baremos_sistema_a = db.query(models.Baremo).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(
        models.Dimension.prueba_id == prueba.id,
        models.Baremo.criterio_normativo.is_(None),
    ).all()

    baremos_actualizados = 0
    for baremo in baremos_sistema_a:
        rango = (int(baremo.puntaje_minimo), int(baremo.puntaje_maximo))
        contenido = CONTENIDO_INFORME_POR_TRAMO.get(rango)
        if not contenido:
            continue
        cambio_tramo = False
        interpretacion_nueva = _INTERPRETACION_POR_RANGO.get(rango)
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
          f"{baremos_actualizados} tramo(s) del Sistema A con interpretación/conclusión/recomendación añadidas.")


def _asegurar_criterio_sistema_b(db, prueba) -> None:
    """Añade el Sistema B (segundo criterio normativo) si todavía no existe
    para esta prueba — idempotente y puramente aditivo, mismo patrón que
    seed_gad7.py._asegurar_criterio_peru / seed_phq9.py._asegurar_contenido_
    informe: corre incluso si APGAR-FAMILIAR ya existía."""
    dimension = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).first()
    if not dimension:
        print("⚠️  APGAR-FAMILIAR no tiene dimensión cargada todavía; no se puede añadir el Sistema B.")
        return

    ya_existe = db.query(models.Baremo).filter(
        models.Baremo.dimension_id == dimension.id,
        models.Baremo.criterio_normativo == CRITERIO_SISTEMA_B,
    ).first()
    if ya_existe:
        print(f"↪️  El criterio normativo '{CRITERIO_SISTEMA_B}' ya estaba cargado; no se toca.")
        return

    for minimo, maximo, nivel, es_alerta in BAREMOS_SISTEMA_B:
        db.add(models.Baremo(
            dimension_id=dimension.id,
            edad_min=None, edad_max=None, sexo=None, poblacion=None,
            puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
            interpretacion=(
                f"Puntaje total {minimo}-{maximo} (Sistema B): percepción del funcionamiento "
                f"familiar de nivel '{nivel.lower()}'. No constituye por sí solo un diagnóstico "
                "familiar, psicológico o psiquiátrico."
            ),
            es_alerta=es_alerta,
            criterio_normativo=CRITERIO_SISTEMA_B,
        ))
    db.commit()
    print(f"✅ Criterio normativo '{CRITERIO_SISTEMA_B}' añadido: {len(BAREMOS_SISTEMA_B)} tramo(s). "
          "Sigue inactivo por defecto — Prueba.criterio_normativo_activo es NULL (usa el Sistema A) "
          "hasta que se haga PATCH explícito.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  APGAR-FAMILIAR ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_criterio_sistema_b(db, existente)
            _asegurar_contenido_informe_apgar(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Escala APGAR Familiar (adaptación peruana)",
            instrucciones=(
                "Responda de acuerdo a su apreciación personal las siguientes preguntas, "
                "pensando en su propia familia."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=4,
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoevaluación sobre la propia familia
            # No es un tamizaje de recall corto (no hay "últimas 2 semanas");
            # la percepción de funcionamiento familiar no amerita reaplicación
            # tan frecuente como PHQ-9/GAD-7.
            dias_minimos_entre_aplicaciones=90,
        )
        db.add(prueba)
        db.flush()

        dimension = models.Dimension(
            prueba_id=prueba.id,
            nombre="Funcionamiento Familiar Percibido",
            descripcion=(
                "Puntaje único del APGAR Familiar (suma de los 5 ítems, 0-20) — la adaptación "
                "peruana (Castilla et al., 2014) encontró estructura unifactorial; no debe "
                "interpretarse como 5 subescalas independientes (Adaptación/Participación/"
                "Crecimiento/Afectividad/Capacidad resolutiva son componentes conceptuales, "
                "no factores psicométricos separados)."
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
                es_inverso=False,  # todos los ítems están formulados positivamente
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in OPCIONES:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                ))

        for minimo, maximo, nivel, es_alerta in BAREMOS:
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=(
                    f"Puntaje total {minimo}-{maximo}: percepción del funcionamiento familiar "
                    f"de nivel '{nivel.lower()}'. No constituye por sí solo un diagnóstico "
                    "familiar, psicológico o psiquiátrico."
                ),
                es_alerta=es_alerta,
            ))

        for minimo, maximo, nivel, es_alerta in BAREMOS_SISTEMA_B:
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=(
                    f"Puntaje total {minimo}-{maximo} (Sistema B): percepción del funcionamiento "
                    f"familiar de nivel '{nivel.lower()}'. No constituye por sí solo un diagnóstico "
                    "familiar, psicológico o psiquiátrico."
                ),
                es_alerta=es_alerta,
                criterio_normativo=CRITERIO_SISTEMA_B,
            ))

        db.commit()
        print(f"✅ APGAR-FAMILIAR cargado: prueba id={prueba.id}, dimensión id={dimension.id}, "
              f"{len(PREGUNTAS)} preguntas, {len(BAREMOS)} tramos Sistema A (activo por defecto) + "
              f"{len(BAREMOS_SISTEMA_B)} tramos Sistema B (adaptación peruana 0-20).")
        _asegurar_contenido_informe_apgar(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando APGAR-FAMILIAR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
