"""
Carga el catálogo PÚBLICO (institucion_id=None) de HAMILTON_AUTOINFORME — el
formulario real de 17 ítems proporcionado ("ESCALA DE HAMILTON"), cargado TAL
CUAL como autoinforme — decisión consultada y confirmada con el usuario antes
de escribir este script, no una simplificación silenciosa.

Es idempotente: si "HAMILTON_AUTOINFORME" ya existe como prueba pública, no
toca nada. Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_hamilton_autoinforme

⚠️ ESTO NO ES LA HDRS-17 CLÍNICA OFICIAL — ADVERTENCIA CENTRAL DE ESTA
CARGA, no un detalle menor: la ficha técnica es explícita en que la Hamilton
Depression Rating Scale (HDRS/HAM-D) es **heteroaplicada** — la completa un
clínico, puntuando lo que observa en una entrevista clínica estructurada,
nunca el propio paciente. El formulario real proporcionado, en cambio, está
redactado en primera persona como autoinforme ("marque la respuesta que más
esté de acuerdo con SU estado de ánimo"), exactamente igual que PHQ-9/GAD-7/
DASS-21. Esta plataforma hoy solo tiene un mecanismo de aplicación — el link
mágico que completa quien lo recibe — sin ningún modo de "el clínico
completa esto durante/después de una entrevista estructurada". Se decidió
(consultado y confirmado con el usuario) cargar el formulario real tal cual,
vía el flujo normal de examen, dejando constancia expresa en
`nombre_publico`/`instrucciones` de que esto NO es la HDRS-17 clínica
heteroaplicada oficial — es una adaptación de autoinforme de un formulario
que circula con ese nombre. `nombre_tecnico="HAMILTON_AUTOINFORME"`
(nunca "HDRS-17" ni "HAM-D") para que ningún reporte ni integración futura
pueda confundir esta carga con el instrumento clínico validado.

⚠️ LA ESTRUCTURA DE 17 ÍTEMS DEL FORMULARIO REAL NO COINCIDE CON LOS 17
DOMINIOS OFICIALES DE LA HDRS-17 — segundo hallazgo real, verificado
dominio por dominio contra la ficha técnica, no solo "distinta numeración"
como en casos anteriores (BARSIT/Vanderbilt): el formulario real OMITE
dominios oficiales como Ansiedad somática, Agitación psicomotora e Insight,
y en su lugar (a) añade un ítem de variación diurna (ítem 13, "¿Está peor
temprano por la mañana, pero mejora...?") que la propia ficha dice que **no
se usa en absoluto en la puntuación de gravedad de la versión de 17
ítems** (es uno de los 4 ítems extra de la versión de 21 que HDRS-17
explícitamente excluye), y (b) descompone el ítem oficial único "3.
Suicidio" (una escala 0-4 con anclajes acumulativos: ausente / siente que no
vale la pena vivir / desearía estar muerto / ideas o gestos suicidas /
intentos de suicidio) en CUATRO preguntas de sí/no independientes (ítems
14-17 de este formulario) que reflejan esos mismos cuatro niveles de
gravedad como preguntas separadas en vez de una sola escala ordinal. Se
cargó la estructura literal del formulario real tal cual — no se intentó
"corregir" la lista de dominios para que coincida con el oficial, porque eso
alteraría el instrumento que efectivamente se va a aplicar.

⚠️ ÍTEM 14 — HALLAZGO VERIFICADO POR INCONSISTENCIA LÓGICA INTERNA (mismo
criterio que los ítems inversos de EAR/SDQ-CAS): el formulario imprime "14.
¿Le encuentra sentido a la vida? NO=0 SÍ=1" — es decir, responder "Sí"
(encuentro sentido, la respuesta tranquilizadora) puntúa MÁS que responder
"No" (no encuentro sentido, la respuesta preocupante), al revés de la
dirección "mayor puntaje = más sintomatología" que siguen los otros 16
ítems y que el propio casillero "TOTAL PUNTAJE" del formulario asume
implícitamente al sumarlos todos juntos. Sin corregir esto, una persona
completamente sana que responde "Sí" a este ítem (y lo mínimo en todos los
demás) obtendría 1 punto en vez de 0 — una inflación de línea base
silenciosa. Se cargó `es_inverso=True` en este ítem (con el texto/valores
literales "No"=0/"Sí"=1 tal cual los ve el estudiante) para que el motor
genérico (`(escala_minima+escala_maxima)-valor`) lo recodifique a la
dirección correcta antes de sumarlo — NO se alteraron los textos ni valores
de las alternativas, solo se corrigió la dirección de cómputo. Por ser el
ÚNICO ítem invertido de esta prueba y tener su propia escala 0-1,
`Prueba.escala_minima`/`escala_maxima` se fijan en 0/1 — eso no afecta a
los otros 16 ítems (su contribución es su `valor_puntuacion` literal sin
pasar por la fórmula de inversión en absoluto, ver `es_inverso=False`),
solo garantiza que la inversión de este ítem específico sea matemáticamente
correcta.

⚠️ UNA SOLA DIMENSIÓN ("Depresión Total"), SIN SUBESCALAS: la ficha técnica
es explícita en que "las estructuras factoriales... pueden variar según la
versión de la escala" y "no deben incorporarse como subescalas universales
sin especificar la versión utilizada" — los factores de melancolía/
ansiedad/sueño que menciona no tienen ni siquiera sus ítems exactos
especificados en la fuente. Se carga tal como el propio formulario real lo
usa: una única casilla "TOTAL PUNTAJE".

⚠️ BAREMO — EL DEL FORMULARIO REAL, NO NINGUNO DE LOS TRES DE LA FICHA
TÉCNICA (decisión consultada y confirmada con el usuario): el formulario
imprime "0-7 Normal / 8-15 Depresión Menor / >16 Depresión Mayor" — un
CUARTO sistema de corte, de solo 3 niveles, que no coincide con el sistema
de Bech (5 niveles: 0-7/8-12/13-17/18-29/30-52), el "otro sistema" de la
ficha (3 niveles: 0-7/8-14/15-52) ni la "clasificación alternativa" (5
niveles: 0-7/8-13/14-18/19-22/≥23). Esos tres sistemas de la ficha técnica
NO se cargan. **Vacío detectado y resuelto por inferencia razonable, no
inventado**: el formulario deja el valor exacto "16" sin cubrir entre "8-15"
y "> 16" (mayor que 16, es decir ≥17) — se interpretó "> 16" como "≥16"
(Depresión Mayor empieza en 16), cerrando el hueco de un solo punto, mismo
tipo de ajuste de piso/techo ya hecho para BARSIT (0-4 en vez de 1-4). El
puntaje máximo real de este formulario (8 ítems×4 + 5 ítems×2 + 4 ítems×1 =
46) se usa como techo del tramo "Depresión Mayor".

⚠️ es_alerta: DECISIÓN CLÍNICA PROPIA DE ESTA PLATAFORMA — el formulario no
declara cuál de sus 3 niveles es "cribado positivo". Se marca "Depresión
Menor" y "Depresión Mayor" como `es_alerta=True` (retienen el informe) y
"Normal" como `es_alerta=False`, mismo criterio ya usado en GAD-7/DASS-21
cuando la fuente no da un único punto de corte explícito.

⚠️ TRES ReglaInterpretacion DE SEGURIDAD PROPIAS DE LA PLATAFORMA — NO
EXIGIDAS por el formulario, mismo mecanismo que el ítem 9 de PHQ-9/ítem 21
de DASS-21/ítem 37 de RCADS-47, pero sobre contenido MÁS explícito que
cualquiera de esos: los ítems 15 ("¿Ha pensado en ponerle fin a todo?"), 16
("¿Ha hecho planes para quitarse la vida?") y 17 ("¿Ha intentado o intenta
quitarse la vida?") son ideación/planificación/intento suicida directos —
cualquier respuesta "Sí" (valor=1) fuerza `es_alerta=True` sobre la
dimensión total, sin esperar al puntaje agregado. El ítem 14 (inverso, ver
arriba) NO lleva regla propia — su contenido (sentido de vida) es más
inespecífico y, por estar invertido, una regla de ámbito 'item' tendría que
comparar contra el valor CRUDO (`RespuestaAlumno.puntaje_obtenido`, antes de
la inversión), lo que complicaría la regla sin una ganancia clínica clara
frente a ya tener las tres reglas directas de 15-17.

🆕 visible_para_clientes=True (sesión 2026-10-17) — ACTIVADA POR DECISIÓN
EXPLÍCITA DEL EQUIPO DE AURORASOFT PARA EL PILOTO. Hasta esa sesión estuvo
en False, mismo nivel de cautela que BARSIT, por dos razones combinadas que
quedan documentadas porque el riesgo asumido no debe perderse: (1) licencia
sin resolver (la ficha es explícita: "NO ESPECIFICADO EN LA FUENTE
CONSULTADA" para reproducción/dominio público de la versión española) y (2)
la autenticidad/oficialidad de este formulario concreto es dudosa (ver
arriba: su estructura de dominios no coincide con la HDRS-17 oficial y su
sistema de corte no coincide con ninguno de los tres documentados). Sigue
sin ser la HDRS-17 heteroaplicada oficial — eso seguiría siendo una `Prueba`
separada si alguna vez se necesita; `nombre_tecnico`/`nombre_publico` ya
dejan constancia de que esto NO es el instrumento clínico oficial, y esa
salvedad es justamente lo que hace responsable activarla ahora (el usuario
que la aplique sabe, por el propio nombre, que es una adaptación, no el
HDRS-17 real).

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_INFORME_POR_TRAMO más abajo y
_asegurar_contenido_informe_hamilton, mismo patrón idempotente/aditivo que
seed_gad7.py/seed_dass21.py): `motivo_consulta_default`/`tecnicas_
adicionales` y, por cada uno de los 3 tramos ya cargados, `Baremo.
conclusion_sugerida`/`recomendacion_sugerida`.

⚠️ EL EJEMPLAR DE REFERENCIA (informe real de Hamilton entregado) **NO SE
USÓ LITERALMENTE** — se detectaron dos conflictos de datos reales contra lo
ya cargado, consultados y resueltos con el usuario (autorización expresa:
"si no te parece coherente realiza a tu manera"):
  (1) Sus 3 "dimensiones" (melancolía=ítems 1,2,7,8,10,13 / ansiedad=9,10,
      11,12,13,15,17 / sueño=4,5,6, con ítems repetidos entre dimensiones)
      usan una numeración que NO coincide con el contenido real de los
      ítems 4-6 de este formulario (lentitud/ansiedad/preocupación por
      enfermedad, no sueño — los ítems de sueño reales son 8-10). No
      resuelve el vacío de subescalas ya documentado arriba ("UNA SOLA
      DIMENSIÓN, SIN SUBESCALAS") — sigue sin cargarse ninguna subescala.
  (2) Reporta "17/52 puntos... depresión ligera": el techo 52 delata que usa
      uno de los sistemas de corte de la ficha técnica (probablemente Bech)
      que este módulo decidió explícitamente NO cargar — nuestro techo real
      es 46, con el sistema propio de 3 niveles del formulario (Normal 0-7 /
      Depresión Menor 8-15 / Depresión Mayor ≥16). Bajo ESE sistema, 17 cae
      en "Depresión Mayor", no "ligera".
Resolución: el tono/contenido del ejemplar (combinación leve de síntomas
depresivos y ansiosos, sin urgencia) se adaptó al tramo **"Depresión
Menor"** (8-15) — coincide mejor en severidad con su propia etiqueta
"ligera" que forzarlo dentro de "Depresión Mayor". El tramo "Depresión
Mayor" se redactó de cero, en tono más urgente, consistente con que
`es_alerta=True` y con las 3 ReglaInterpretacion de seguridad de los ítems
15-17 (sin determinar riesgo suicida por sí solo — ver advertencia de esas
reglas más abajo). El tramo "Normal" también se redactó de cero. Pendiente
de verificación cruzada final (acordado con el usuario), igual que el resto
del contenido de informe cargado en esta sesión.

⚠️ dias_minimos_entre_aplicaciones=7: NO ES UN VALOR DE LA FUENTE (el
formulario pregunta por "este momento", sin ventana de recall explícita de
varios días) — criterio conservador propio de esta plataforma, igual que
otros valores no-sourced ya usados (APGAR-FAMILIAR=90, Vanderbilt=180),
aquí alineado con el valor más corto ya usado para otros instrumentos de
depresión (PHQ-9/CES-DC=7) por prudencia ante la falta de un criterio
explícito.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `TECNICAS_ADICIONALES` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_hamilton_autoinforme`.
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

NOMBRE_TECNICO = "HAMILTON_AUTOINFORME"
# 🆕 Título corto para la UI (auditoría de UX, 2026-10-13) — ver Prueba.nombre_corto en models.py.
NOMBRE_CORTO = "Escala de Hamilton (autoinforme)"

OPCIONES_0_4 = [("Nada", 0), ("Un poco", 1), ("Moderado", 2), ("Mucho", 3), ("Sumamente", 4)]
OPCIONES_0_2 = [("No", 0), ("A veces", 1), ("Siempre", 2)]
OPCIONES_0_1 = [("No", 0), ("Sí", 1)]

# (orden, texto literal, opciones, es_inverso)
ITEMS = [
    (1, "¿Me siento decepcionado, triste e infeliz?", OPCIONES_0_4, False),
    (2, "¿Se siente culpable de las cosas que ha hecho o pensado?", OPCIONES_0_4, False),
    (3, "¿Ha perdido interés en su trabajo o pasatiempo?", OPCIONES_0_4, False),
    (4, "¿Le parece que es usted más lento que su velocidad normal o habitual?", OPCIONES_0_4, False),
    (5, "¿Estado ansioso o lento?", OPCIONES_0_4, False),
    (6, "¿Le preocupa que podría padecer una enfermedad grave como cáncer o venérea?", OPCIONES_0_4, False),
    (7, "¿Ha perdido peso recientemente (aparte de las dietas)?", OPCIONES_0_4, False),
    (8, "¿Le cuesta más tiempo dormirse?", OPCIONES_0_4, False),
    (9, "¿Duerme a ratos? ¿Se despierta a menudo?", OPCIONES_0_2, False),
    (10, "¿Se despierta antes de lo habitual y luego no puede conciliar otra vez el sueño?", OPCIONES_0_2, False),
    (11, "¿Sufre de algún síntoma físico?", OPCIONES_0_2, False),
    (12, "¿Ha perdido interés en el sexo?", OPCIONES_0_2, False),
    (13, "¿Está peor temprano por la mañana, pero mejora a medida que pasa el día?", OPCIONES_0_2, False),
    # ⚠️ Inverso — ver advertencia en el docstring (inconsistencia verificada).
    (14, "¿Le encuentra sentido a la vida?", OPCIONES_0_1, True),
    # ⚠️ Ítems 15-17: ReglaInterpretacion de seguridad — ver docstring.
    (15, "¿Ha pensado en ponerle fin a todo?", OPCIONES_0_1, False),
    (16, "¿Ha hecho planes para quitarse la vida?", OPCIONES_0_1, False),
    (17, "¿Ha intentado o intenta quitarse la vida?", OPCIONES_0_1, False),
]
ORDENES_CON_REGLA_SEGURIDAD = {15, 16, 17}

# (mínimo, máximo, nivel, es_alerta) — puntaje bruto, techo real = 46
# (8 ítems×4 + 5 ítems×2 + 4 ítems×1). Ver docstring sobre el hueco en "16".
BAREMO = [
    (0, 7, "Normal", False),
    (8, 15, "Depresión Menor", True),
    (16, 46, "Depresión Mayor", True),
]

# 🆕 Contenido del informe profesional (fuente "B", ver CLAUDE.md "FUENTES DE
# CONTENIDO DEL INFORME") — ver advertencia ✅ de cabecera sobre por qué el
# ejemplar de referencia no se usó literalmente.
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluación de tamizaje solicitada para medir la presencia y el nivel de sintomatología "
    "depresiva (y, de forma asociada, ansiosa) reportada por el estudiante, con la finalidad de "
    "identificar posibles indicadores de malestar psicológico y orientar las estrategias de "
    "acompañamiento o intervención correspondientes, en el marco de una campaña de evaluación "
    "psicométrica institucional."
)
TECNICAS_ADICIONALES = "Entrevista, Observación"

# (mínimo, máximo) del tramo -> {conclusion, recomendacion}. Ver advertencia
# ✅ de cabecera: "Depresión Menor" adapta el tono del ejemplar (combinación
# leve de síntomas depresivos/ansiosos); "Normal"/"Depresión Mayor" se
# redactaron de cero, en el mismo registro clínico.
CONTENIDO_INFORME_POR_TRAMO = {
    (0, 7): {
        "conclusion": (
            "El puntaje obtenido se encuentra dentro del rango normal, sin indicadores "
            "significativos de sintomatología depresiva según este formulario."
        ),
        "recomendacion": (
            "Se recomienda mantener el acompañamiento habitual del estudiante. No se identifica "
            "necesidad de intervención adicional por este motivo."
        ),
    },
    (8, 15): {
        # Adaptado del tono de "5. Resultados"/"6. Conclusiones" del ejemplar
        # (combinación leve de síntomas depresivos y ansiosos) — ver
        # advertencia ✅ de cabecera sobre por qué se mapeó a este tramo.
        "conclusion": (
            "El puntaje obtenido corresponde a un nivel de depresión menor (leve). Los resultados "
            "evidencian una combinación de síntomas depresivos y ansiosos en grado leve — "
            "manifestaciones relacionadas con el estado de ánimo decaído, sentimientos de culpa o "
            "preocupación excesiva — sin alcanzar un nivel de mayor severidad."
        ),
        "recomendacion": (
            "Se recomienda que el estudiante reciba acompañamiento psicológico para abordar los "
            "indicadores asociados al estado de ánimo depresivo y la ansiedad. Se sugiere "
            "fortalecer estrategias de afrontamiento y regulación emocional, promover hábitos "
            "saludables y realizar seguimiento periódico de su evolución; de persistir o "
            "incrementarse los indicadores, considerar una evaluación especializada "
            "complementaria."
        ),
    },
    (16, 46): {
        "conclusion": (
            "El puntaje obtenido corresponde a un nivel de depresión mayor, con una presencia más "
            "marcada de indicadores depresivos y, frecuentemente, ansiosos asociados. Este "
            "resultado, obtenido mediante un instrumento de autoinforme, constituye un indicador "
            "de alerta prioritario que amerita evaluación profesional oportuna; no sustituye una "
            "valoración clínica estructurada ni determina por sí solo un diagnóstico psiquiátrico."
        ),
        "recomendacion": (
            "Se recomienda derivación prioritaria a evaluación psicológica (y, de ser pertinente, "
            "psiquiátrica), fortalecer estrategias de afrontamiento y regulación emocional, y "
            "realizar seguimiento cercano de la evolución del estudiante. Se sugiere además "
            "coordinar con la familia o apoderados según el protocolo institucional vigente. "
            "Cualquier respuesta positiva a los ítems 15-17 (ideación, planificación o intento "
            "suicida) activa de forma independiente una señal de alerta que requiere revisión "
            "profesional inmediata (ver ReglaInterpretacion asociada)."
        ),
    },
}


def _verificar_estructura():
    """Falla ruidosamente ANTES de tocar la BD si la estructura no es
    exactamente la esperada — mismo criterio defensivo que seed_barsit.py/
    seed_vanderbilt_padres.py/seed_dass21.py."""
    if len(ITEMS) != 17:
        raise RuntimeError(f"Se esperaban 17 ítems, hay {len(ITEMS)}")
    ordenes = [i[0] for i in ITEMS]
    if ordenes != list(range(1, 18)):
        raise RuntimeError(f"Los órdenes no son 1..17 consecutivos: {ordenes}")
    inversos = {i[0] for i in ITEMS if i[3]}
    if inversos != {14}:
        raise RuntimeError(f"Se esperaba solo el ítem 14 invertido, hay: {sorted(inversos)}")
    if not ORDENES_CON_REGLA_SEGURIDAD <= set(ordenes):
        raise RuntimeError("Órdenes de reglas de seguridad fuera de rango")
    maximo_calculado = sum(max(v for _, v in opciones) for _, _, opciones, _ in ITEMS)
    if maximo_calculado != BAREMO[-1][1]:
        raise RuntimeError(
            f"El techo del baremo ({BAREMO[-1][1]}) no coincide con el máximo real calculado ({maximo_calculado})"
        )


def _asegurar_contenido_informe_hamilton(db, prueba) -> None:
    """Rellena motivo_consulta_default/tecnicas_adicionales de la prueba y
    conclusion_sugerida/recomendacion_sugerida de cada uno de los 3 tramos
    SOLO si están vacíos — idempotente y puramente aditivo, mismo patrón que
    seed_gad7.py._asegurar_contenido_informe_gad7/seed_dass21.py._asegurar_
    contenido_informe_dass21: nunca pisa contenido que un psicólogo ya haya
    editado a mano."""
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
    # 🆕 Activación explícita (sesión 2026-10-17): mismo criterio y misma
    # decisión de negocio que seed_barsit.py — ver advertencia en el
    # docstring de este archivo.
    if not prueba.visible_para_clientes:
        prueba.visible_para_clientes = True
        cambios.append("visible_para_clientes")

    dimension = db.query(models.Dimension).filter(models.Dimension.prueba_id == prueba.id).first()
    baremos_actualizados = 0
    if dimension:
        for minimo, maximo, _nivel, _alerta in BAREMO:
            contenido = CONTENIDO_INFORME_POR_TRAMO.get((minimo, maximo))
            if not contenido:
                continue
            baremo = db.query(models.Baremo).filter(
                models.Baremo.dimension_id == dimension.id,
                models.Baremo.puntaje_minimo == minimo,
                models.Baremo.puntaje_maximo == maximo,
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
          f"{baremos_actualizados} tramo(s) con conclusión/recomendación añadidas.")


def cargar():
    _verificar_estructura()
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  HAMILTON_AUTOINFORME ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_contenido_informe_hamilton(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico=(
                "Escala de Hamilton — versión de autoinforme "
                "(NO es la HDRS-17 clínica heteroaplicada oficial — ver notas del catálogo)"
            ),
            # 🆕 Ver Prueba.nombre_corto en models.py — NOMBRE_TECNICO
            # ("HAMILTON_AUTOINFORME") es un identificador interno, no un
            # título legible para un psicólogo.
            nombre_corto=NOMBRE_CORTO,
            instrucciones=(
                "Por favor, lea atentamente las siguientes preguntas y marque la respuesta que más esté "
                "de acuerdo con su estado de ánimo en este momento. Asegúrese de que solo haya una "
                "respuesta por pregunta."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=0,
            escala_maxima=1,  # ver advertencia en el docstring — solo afecta al ítem 14 (único invertido)
            modo_calculo="likert_suma",
            modo_interpretacion=models.MODO_INTERPRETACION_RANGO,
            visible_para_clientes=True,  # 🆕 activación explícita (sesión 2026-10-17) — ver docstring
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # ver advertencia central del docstring
            dias_minimos_entre_aplicaciones=7,  # no sourced — ver docstring
            motivo_consulta_default=MOTIVO_CONSULTA_DEFAULT,
            tecnicas_adicionales=TECNICAS_ADICIONALES,
        )
        db.add(prueba)
        db.flush()

        dimension = models.Dimension(
            prueba_id=prueba.id,
            nombre="Depresión Total",
            descripcion=(
                "Puntaje único de este formulario (suma de los 17 ítems tras invertir el ítem 14; "
                "rango 0-46). Sin subescalas — ver docstring de seed_hamilton_autoinforme.py sobre "
                "por qué los factores de melancolía/ansiedad/sueño no se cargan como dimensiones."
            ),
        )
        db.add(dimension)
        db.flush()

        preguntas_por_orden = {}
        for orden, texto, opciones, es_inverso in ITEMS:
            pregunta = models.Pregunta(
                prueba_id=prueba.id,
                dimension_id=dimension.id,
                texto_pregunta=texto,
                orden=orden,
                es_inverso=es_inverso,
            )
            db.add(pregunta)
            db.flush()
            for texto_opcion, valor in opciones:
                db.add(models.OpcionRespuesta(
                    pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                ))
            preguntas_por_orden[orden] = pregunta

        for minimo, maximo, nivel, es_alerta in BAREMO:
            contenido = CONTENIDO_INFORME_POR_TRAMO.get((minimo, maximo), {})
            db.add(models.Baremo(
                dimension_id=dimension.id,
                edad_min=None, edad_max=None, sexo=None, poblacion=None,
                puntaje_minimo=minimo, puntaje_maximo=maximo, nivel=nivel,
                interpretacion=(
                    f"Puntaje bruto {minimo}-{maximo}: nivel '{nivel}' según el sistema de corte impreso "
                    "en este formulario (no es ninguno de los sistemas de Bech ni de la clasificación "
                    "alternativa documentados para la HDRS-17 oficial). No constituye por sí solo un "
                    "diagnóstico psiquiátrico."
                ),
                conclusion_sugerida=contenido.get("conclusion"),
                recomendacion_sugerida=contenido.get("recomendacion"),
                es_alerta=es_alerta,
            ))

        for orden in sorted(ORDENES_CON_REGLA_SEGURIDAD):
            pregunta = preguntas_por_orden[orden]
            db.add(models.ReglaInterpretacion(
                prueba_id=prueba.id,
                ambito=models.AMBITO_ITEM,
                pregunta_id=pregunta.id,
                operador=">",
                valor_comparacion=0,
                accion=models.ACCION_ES_ALERTA,
                descripcion=(
                    f"Ítem {orden} positivo ('{pregunta.texto_pregunta}'): ideación/planificación/intento "
                    "suicida directo — requiere revisión profesional inmediata, sin esperar al puntaje "
                    "agregado."
                ),
                activa=True,
            ))

        db.commit()
        print(f"✅ HAMILTON_AUTOINFORME cargado: prueba id={prueba.id}, 1 dimensión, 17 preguntas "
              f"(1 invertida: ítem 14), {len(BAREMO)} tramos de baremo (sistema propio del formulario, "
              "con conclusión/recomendación por tramo), "
              f"{len(ORDENES_CON_REGLA_SEGURIDAD)} ReglaInterpretacion de seguridad (ítems 15-17). "
              "visible_para_clientes=True (🆕 activación explícita, sesión 2026-10-17). NO es la "
              "HDRS-17 clínica heteroaplicada oficial (ver "
              "docstring).")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando HAMILTON_AUTOINFORME: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
