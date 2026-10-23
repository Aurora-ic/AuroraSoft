"""
Carga el catálogo PÚBLICO (institucion_id=None) del IPIP-RIASEC — prueba, 6
dimensiones (Realista/Investigativo/Artístico/Social/Emprendedor/
Convencional), 48 ítems (8 por dimensión) con escala Likert 1-5, interpretada
por PERFIL (modo_interpretacion='perfil' — ver crud.interpretar_perfil_alumno
en modulos/educativo/crud.py), no por rango de Baremo.

Es idempotente: si "IPIP-RIASEC" ya existe como prueba pública, no toca
nada. Para forzar una recarga, borra antes la fila de edu_pruebas.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_riasec

⚠️ DOS DOCUMENTOS FUENTE DISTINTOS — SOLO UNO SE USÓ COMO BASE ESTRUCTURAL:
se evaluaron dos PDFs para esta carga. Uno ("What is your RIASEC?",
ilide.info) describe un cuestionario de 60 ítems (10 por dimensión, formato
de casillas Sí/No, sin ficha técnica propia ni respaldo psicométrico
declarado) — es un instrumento DISTINTO, no cargado aquí. El otro es la
ficha técnica real del **IPIP-RIASEC / AFPD RIASEC Markers** (Armstrong,
Allison & Rounds, 2008; validación española de Cupani et al., 2019): 48
ítems (8 por dimensión), escala Likert 1-5, sin ítems inversos. Esta carga
usa EXCLUSIVAMENTE la estructura de la ficha técnica (dimensiones, escala,
fórmula de puntuación, ausencia de puntos de corte clínicos) — mezclar las
dos fuentes habría producido un instrumento que no es ninguno de los dos
realmente validados.

⚠️ TEXTO DE LOS 48 ÍTEMS — TEMÁTICO/PARÁFRASIS, NO LITERAL (mismo criterio
que seed_gad7.py, no el de seed_chaside.py): la propia ficha técnica del
IPIP-RIASEC NO reproduce el texto de los 48 ítems oficiales — remite a la
página oficial de RIASEC Markers, cuyo contenido está protegido por los
autores (ver advertencia de licencia más abajo). El texto cargado aquí es
una redacción propia en español, en primera persona, fiel a las
descripciones de constructo que sí trae la ficha técnica para cada
dimensión (sección "6. DIMENSIONES/ESCALAS") — nunca una traducción del
cuestionario de 60 ítems del otro PDF (que es un instrumento distinto) ni
una reconstrucción del cuestionario oficial de 48 ítems protegido. Antes de
usar esta prueba con estudiantes reales, reemplazar `PREGUNTAS` por el
formulario oficial licenciado que use cada institución — es un cambio de
datos, nunca de estructura ni de código (mismo criterio ya documentado en
seed_gad7.py).

⚠️ LICENCIA — NO ES DE DOMINIO PÚBLICO COMPLETO (mismo criterio que
seed_rcads47.py): el AFPD RIASEC Markers se diseñó como alternativa de
dominio público a inventarios comerciales, pero la página oficial vigente
indica que los marcadores están protegidos por los autores y que el
permiso gratuito se concede solo para **uso no comercial**, con atribución
a Armstrong, Allison y Rounds. Para uso comercial real (esta plataforma es
una SaaS comercial) NO debe asumirse autorización automática — antes de
ofrecer esta prueba a un colegio cliente real hay que confirmar las
condiciones vigentes directamente con los autores. `visible_para_clientes`
se deja en `True` de todas formas (mismo criterio que RCADS-47: la carga de
datos no es el punto de decisión legal, pero queda documentado aquí sin
ambigüedad para que no se redescubra).

⚠️ NO EXISTEN PUNTOS DE CORTE CLÍNICOS — ESTRUCTURA GENUINAMENTE DISTINTA
A PHQ-9/GAD-7 (mismo criterio que seed_chaside.py): la propia ficha técnica
es explícita: "El IPIP-RIASEC no posee puntos de corte clínicos... El
instrumento mide intereses vocacionales, no psicopatología." Por eso:
  - `interpretar_perfil_alumno` nunca marca `es_alerta=True` por diseño —
    ver "Interpretación por perfil" en CLAUDE.md.
  - No hay `ReglaInterpretacion` — no existe ningún ítem crítico declarado.
  - `modo_calculo` sigue siendo "likert_suma": sumar 8 ítems por dimensión
    (escala 1-5, sin inversos) es exactamente la misma operación que ya
    hace el motor para cualquier otra prueba Likert.

⚠️ INTERPRETACIÓN: MODO 'PERFIL', NO 'RANGO' — SIN BAREMO EN ABSOLUTO.
La ficha técnica confirma explícitamente que "no se encontró un baremo
peruano oficial" y que la interpretación correcta NO es contra un punto de
corte absoluto sino **comparativa**: ordenar las 6 dimensiones de la propia
persona de mayor a menor puntaje y tomar las 3 más altas como "código
Holland" (ver sección 8-9 de la ficha técnica). Esto es EXACTAMENTE el
"tercer límite real del motor" que esta misma prueba surgió para documentar
en CLAUDE.md ("Catálogo de pruebas cargadas") — y que ya quedó resuelto:
`Prueba.modo_interpretacion` se fija aquí en `'perfil'`
(`models.MODO_INTERPRETACION_PERFIL`), así que `crud.interpretar_perfil_alumno`
hace la comparación real entre dimensiones en vez de inventar un baremo de
rango "falso" (algo que una versión anterior de este script sí hacía, como
una banda descriptiva de 4 tramos sin corte normativo — superada por el
algoritmo real; ver la migración `3a1f4fcd127d` y "Interpretación por
perfil" en CLAUDE.md). Por eso este script **no carga ningún `Baremo`**:
en modo `'perfil'` nunca se consulta ninguno.

`Prueba.ordenar_dimensiones_por_puntaje=True` (ver "Diseño A — Informe PDF"
en CLAUDE.md) sigue activo además del modo perfil — son dos mejoras
independientes y complementarias: el modo perfil decide QUÉ dice cada
`DiagnosticoAlumno.nivel` (el puesto), y `ordenar_dimensiones_por_puntaje`
decide en qué ORDEN se muestran en el PDF y calcula la línea "Código de
perfil" — ninguna de las dos necesita a la otra para funcionar, pero juntas
son lo que hace que el informe de IPIP-RIASEC sea legible como perfil de
verdad.

✅ CONTENIDO DE INFORME CARGADO (ver CONTENIDO_POR_AREA/RECOMENDACION_
GENERICA_DEFAULT más abajo y _asegurar_contenido_informe): a diferencia de
la carga original de este script, `motivo_consulta_default`/`tecnicas_
adicionales` quedan completos, y cada una de las 6 dimensiones recibe
contenido propio vía `Dimension.contenido_perfil_predominante`/
`contenido_perfil_secundaria`/`conclusion_sugerida_perfil` (ver esos
campos en `modulos/educativo/models.py`) — el equivalente de `Baremo.
interpretacion`/`conclusion_sugerida` para modo 'perfil', que nunca
consulta Baremo (ver advertencia de arriba). `obtener_datos_para_pdf`
elige el texto "predominante" o "secundaria" de cada dimensión según si
quedó entre las 3 de mayor puntaje de ESA aplicación — nunca un umbral
fijo, siempre comparativo, exactamente como ya decide
`interpretar_perfil_alumno`. El texto de las 3 áreas predominantes del
ejemplar de referencia (Social/Investigativo/Artístico) está adaptado casi
literalmente de un informe IPIP-RIASEC real; las 3 secundarias
(Emprendedor/Realista/Convencional) también, y además se escribió la
versión "predominante" de las 6 (necesaria porque cualquiera de las 6
puede terminar siendo top-3 según la aplicación real, no solo las que el
ejemplar mostró destacadas). La síntesis "código SIA, área de mayor
predominancia..." (sección V/VI del ejemplar) se genera en código
(`crud._resumen_codigo_perfil`), nunca como texto fijo — depende de qué
3 dimensiones resulten top-3 en cada aplicación real, información que
`codigo_perfil`/`ordenar_dimensiones_por_puntaje` ya calculan.
`Prueba.recomendacion_generica_default` carga las recomendaciones FIJAS
del ejemplar (orientación vocacional, complementar con aptitudes/
personalidad/valores, revisar planes de estudio, considerar capacidades) —
a propósito no dependen de qué área resultó predominante, igual que el
mismo campo ya usa APGAR-FAMILIAR/CHASIDE.

🆕 ACTUALIZACIÓN POSTERIOR (estandarización de contenido procedimental,
sesión 2026-10-12): `MOTIVO_CONSULTA_DEFAULT` de arriba queda como
documentación histórica de cómo se derivó originalmente — el VALOR
REALMENTE CARGADO en la base para ese campo y `tecnicas_adicionales` (y el
nuevo `observacion_conductual_default`) lo fija
`seeds/normalizar_contenido_comun.py`, que lo sobrescribe al mismo texto
estándar en TODAS las pruebas públicas. Ejecutarlo después de cualquier
`python -m seeds.seed_riasec`.
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

NOMBRE_TECNICO = "IPIP-RIASEC"

OPCIONES = [
    ("Me desagrada mucho", 1),
    ("Me desagrada", 2),
    ("Neutral", 3),
    ("Me gusta", 4),
    ("Me gusta mucho", 5),
]

# Texto TEMÁTICO/PARÁFRASIS en español — ver advertencia del módulo. 8
# ítems por dimensión, sin ítems inversos (confirmado por la ficha técnica).
PREGUNTAS = {
    "Realista": [
        "Reparar o armar aparatos y objetos con mis propias manos.",
        "Usar herramientas y maquinaria para construir algo.",
        "Trabajar al aire libre en tareas físicas.",
        "Desarmar un equipo para entender cómo funciona.",
        "Realizar trabajos de carpintería, electricidad o mecánica.",
        "Cultivar una huerta o cuidar plantas y animales.",
        "Hacer reparaciones en casa (pintura, gasfitería, electricidad).",
        "Operar maquinaria o vehículos.",
    ],
    "Investigativo": [
        "Investigar por qué ocurre un fenómeno natural.",
        "Resolver problemas matemáticos complejos.",
        "Leer artículos científicos o de divulgación.",
        "Realizar experimentos de laboratorio.",
        "Analizar datos para encontrar patrones.",
        "Observar y clasificar seres vivos u objetos.",
        "Aprender sobre descubrimientos científicos recientes.",
        "Buscar explicaciones lógicas a problemas complejos.",
    ],
    "Artístico": [
        "Dibujar, pintar o crear obras visuales.",
        "Tocar un instrumento musical o componer música.",
        "Escribir cuentos, poemas u otros textos creativos.",
        "Diseñar ropa, objetos o espacios.",
        "Actuar en una obra de teatro o participar en producciones audiovisuales.",
        "Fotografiar escenas o personas de forma creativa.",
        "Idear soluciones originales y poco convencionales.",
        "Asistir a exposiciones de arte, conciertos u obras de teatro.",
    ],
    "Social": [
        "Enseñar o explicar un tema a otra persona.",
        "Ayudar a alguien a resolver un problema personal.",
        "Orientar a otros sobre decisiones importantes.",
        "Trabajar en equipo apoyando a mis compañeros.",
        "Participar en actividades de voluntariado o servicio comunitario.",
        "Escuchar atentamente los problemas de otras personas.",
        "Organizar actividades para integrar a un grupo.",
        "Cuidar o acompañar a personas que lo necesitan.",
    ],
    "Emprendedor": [
        "Liderar un grupo de trabajo hacia una meta.",
        "Convencer a otros de aceptar una idea o propuesta.",
        "Vender un producto o servicio.",
        "Negociar un acuerdo entre dos partes.",
        "Iniciar y dirigir mi propio proyecto o negocio.",
        "Tomar decisiones importantes bajo presión.",
        "Organizar y dirigir un equipo de personas.",
        "Competir para alcanzar una meta u objetivo.",
    ],
    "Convencional": [
        "Organizar archivos, documentos o registros.",
        "Llevar el control detallado de gastos o ingresos.",
        "Seguir procedimientos establecidos paso a paso.",
        "Trabajar con tablas, listas o bases de datos.",
        "Revisar cuidadosamente un documento en busca de errores.",
        "Clasificar y ordenar información de manera sistemática.",
        "Usar programas de cálculo u hojas electrónicas.",
        "Completar tareas administrativas con precisión.",
    ],
}

# Orden de carga = mismo orden que la ficha técnica (R-I-A-S-E-C).
DIMENSIONES_ORDEN = ["Realista", "Investigativo", "Artístico", "Social", "Emprendedor", "Convencional"]

# ============================================================
# CONTENIDO DE INFORME — por área (ver docstring del módulo). El texto de
# Social/Investigativo/Artístico (predominante) y Emprendedor/Realista/
# Convencional (secundaria) está adaptado de un informe IPIP-RIASEC real de
# referencia; la versión "del otro lado" de las 6 (necesaria porque
# cualquier área puede terminar siendo predominante o secundaria según la
# aplicación real) se redactó en el mismo tono.
# ============================================================
MOTIVO_CONSULTA_DEFAULT = (
    "Evaluar las preferencias e intereses vocacionales del/de la estudiante mediante la "
    "aplicación del IPIP-RIASEC, con la finalidad de identificar las áreas de interés "
    "predominantes y orientar la exploración de posibles alternativas académicas y profesionales."
)

RECOMENDACION_GENERICA_DEFAULT = (
    "Se recomienda que el/la evaluado/a:\n"
    "•  Participe en actividades de orientación vocacional que le permitan conocer de manera "
    "directa las características de las carreras de interés.\n"
    "•  Complemente la evaluación de intereses con instrumentos que permitan identificar "
    "aptitudes, personalidad y valores profesionales.\n"
    "•  Revise los planes de estudio y campos laborales de las carreras que resulten de mayor "
    "interés.\n"
    "•  Considere tanto los intereses identificados como sus capacidades académicas y "
    "expectativas personales antes de tomar una decisión profesional."
)

CONTENIDO_POR_AREA = {
    "Realista": {
        "predominante": (
            "Constituye una de las áreas de mayor interés vocacional. El/la evaluado/a muestra "
            "preferencia por actividades prácticas, mecánicas y técnicas, relacionadas con el uso "
            "de herramientas, maquinaria u objetos, así como por el trabajo manual y al aire libre."
        ),
        "secundaria": (
            "No constituye una de las áreas de mayor interés. Se evidencia menor preferencia por "
            "actividades predominantemente prácticas, mecánicas, técnicas o relacionadas con el "
            "uso constante de herramientas y objetos."
        ),
        "carreras": [
            "Ingeniería Mecánica", "Ingeniería Civil", "Arquitectura", "Agronomía",
            "Tecnología Industrial", "Educación Física",
        ],
    },
    "Investigativo": {
        "predominante": (
            "Constituye una de las áreas de mayor interés vocacional. Presenta un nivel alto de "
            "interés por actividades relacionadas con el análisis, la observación, la búsqueda de "
            "información, la resolución de problemas y la comprensión de diferentes fenómenos. "
            "Puede mostrar motivación hacia actividades que impliquen investigar, analizar "
            "información y encontrar explicaciones a determinadas situaciones."
        ),
        "secundaria": (
            "No constituye una de las áreas de mayor interés. Se evidencia menor motivación hacia "
            "actividades de investigación, análisis de datos o búsqueda de explicaciones a "
            "fenómenos complejos."
        ),
        "carreras": [
            "Medicina", "Biología", "Física", "Química", "Ingeniería", "Investigación Científica",
        ],
    },
    "Artístico": {
        "predominante": (
            "Constituye una de las áreas de mayor interés vocacional. El/la evaluado/a presenta "
            "inclinación hacia actividades que permitan expresar ideas, creatividad y "
            "originalidad. Puede sentirse motivado/a por tareas relacionadas con la escritura, el "
            "diseño, la expresión artística, la comunicación creativa o la elaboración de "
            "propuestas novedosas."
        ),
        "secundaria": (
            "No constituye una de las áreas de mayor interés. Se evidencia menor inclinación hacia "
            "actividades de expresión creativa, artística o de generación de ideas originales."
        ),
        "carreras": [
            "Diseño Gráfico", "Artes Plásticas", "Música", "Arquitectura",
            "Comunicación Audiovisual", "Publicidad",
        ],
    },
    "Social": {
        "predominante": (
            "Constituye el interés predominante. El/la evaluado/a muestra preferencia por "
            "actividades que implican interacción con otras personas, apoyo, orientación, "
            "enseñanza, comunicación y colaboración. Se evidencia interés por comprender las "
            "necesidades de los demás y participar en actividades donde pueda brindar ayuda o "
            "generar un impacto positivo en otras personas."
        ),
        "secundaria": (
            "No constituye una de las áreas de mayor interés. Se evidencia menor preferencia por "
            "actividades de enseñanza, orientación, apoyo o interacción directa con otras "
            "personas."
        ),
        "carreras": [
            "Psicología", "Educación", "Trabajo Social", "Comunicación", "Periodismo", "Enfermería",
        ],
    },
    "Emprendedor": {
        "predominante": (
            "Constituye una de las áreas de mayor interés vocacional. El/la evaluado/a muestra "
            "disposición hacia actividades que impliquen iniciativa, liderazgo, organización y "
            "persuasión, como dirigir equipos, negociar o emprender proyectos propios."
        ),
        "secundaria": (
            "Presenta un nivel de interés menor, indicando cierta disposición hacia actividades "
            "que impliquen iniciativa, liderazgo, organización y persuasión, aunque estas "
            "características no constituyen sus principales intereses vocacionales."
        ),
        "carreras": [
            "Administración de Empresas", "Marketing", "Negocios Internacionales",
            "Derecho Comercial", "Gestión Pública",
        ],
    },
    "Convencional": {
        "predominante": (
            "Constituye una de las áreas de mayor interés vocacional. El/la evaluado/a muestra "
            "preferencia por actividades de organización sistemática de información, seguimiento "
            "de procedimientos establecidos y tareas administrativas que requieren orden y "
            "precisión."
        ),
        "secundaria": (
            "Presenta el nivel más bajo de preferencia relativa, sugiriendo menor interés por "
            "actividades caracterizadas principalmente por la organización rutinaria de "
            "información, el seguimiento estricto de procedimientos y las tareas administrativas "
            "repetitivas."
        ),
        "carreras": [
            "Contabilidad", "Administración", "Economía", "Secretariado Ejecutivo",
            "Gestión Documental",
        ],
    },
}


def _asegurar_contenido_informe(db, prueba) -> None:
    """Rellena motivo_consulta_default/recomendacion_generica_default de la
    prueba, y Dimension.contenido_perfil_predominante/contenido_perfil_
    secundaria/conclusion_sugerida_perfil de cada una de las 6 dimensiones
    — idempotente y puramente aditivo, mismo patrón que seed_gad7.py._
    asegurar_contenido_informe_gad7 (interpretacion/conclusion solo se
    completan si están vacíos; a diferencia de la "revisión crítica de
    contenido" de PHQ-9/GAD-7, aquí no hace falta pisar nada porque este
    contenido nunca se cargó)."""
    cambios = []
    if not prueba.motivo_consulta_default:
        prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT
        cambios.append("motivo_consulta_default")
    if not prueba.recomendacion_generica_default:
        prueba.recomendacion_generica_default = RECOMENDACION_GENERICA_DEFAULT
        cambios.append("recomendacion_generica_default")

    dimensiones = db.query(models.Dimension).filter(
        models.Dimension.prueba_id == prueba.id, models.Dimension.nombre.in_(DIMENSIONES_ORDEN),
    ).all()
    dimensiones_actualizadas = 0
    for dim in dimensiones:
        contenido = CONTENIDO_POR_AREA.get(dim.nombre)
        if not contenido:
            continue
        cambio_dim = False
        if not dim.contenido_perfil_predominante:
            dim.contenido_perfil_predominante = contenido["predominante"]
            cambio_dim = True
        if not dim.contenido_perfil_secundaria:
            dim.contenido_perfil_secundaria = contenido["secundaria"]
            cambio_dim = True
        if not dim.conclusion_sugerida_perfil:
            dim.conclusion_sugerida_perfil = (
                f"{dim.nombre}: entre las opciones profesionales acordes con esta área se "
                f"identifican carreras como {', '.join(contenido['carreras'][:-1])} y "
                f"{contenido['carreras'][-1]}, entre otras pertenecientes a esta área vocacional."
            )
            cambio_dim = True
        if cambio_dim:
            dimensiones_actualizadas += 1

    if not cambios and not dimensiones_actualizadas:
        print("↪️  El contenido del informe (motivo, recomendación, por área) ya estaba completo.")
        return

    db.commit()
    print(f"✅ Contenido del informe completado: {', '.join(cambios) or 'sin cambios en Prueba'}; "
          f"{dimensiones_actualizadas} dimensión(es) con contenido predominante/secundaria/"
          "carreras añadido.")


def _asegurar_orden_por_puntaje(db, prueba) -> None:
    """Idempotente y aditivo (mismo patrón que _asegurar_* en los demás
    seed_*.py): activa `ordenar_dimensiones_por_puntaje` si todavía no
    estaba activado — RIASEC es exactamente el caso de perfil que justificó
    añadir ese campo (ver "Diseño A" en CLAUDE.md)."""
    if prueba.ordenar_dimensiones_por_puntaje:
        print("↪️  ordenar_dimensiones_por_puntaje ya estaba activado; no se toca.")
        return
    prueba.ordenar_dimensiones_por_puntaje = True
    db.commit()
    print("✅ ordenar_dimensiones_por_puntaje activado — el informe ahora ordena las "
          "dimensiones por puntaje e imprime el código de perfil (top-3).")


def _asegurar_modo_perfil(db, prueba) -> None:
    """Idempotente y aditivo — cambia `modo_interpretacion` a 'perfil' si
    todavía estaba en 'rango' (versión previa de este script, antes de que
    el algoritmo de perfil existiera). Si quedan tramos de la banda
    descriptiva anterior SIN ningún DiagnosticoAlumno apuntándolos (nunca se
    interpretó ninguna aplicación real con ellos todavía), se eliminan — ya
    no tienen ningún efecto en modo 'perfil' y dejarlos sería confuso. Si
    alguno SÍ tiene diagnósticos históricos, se deja intacto (igual que
    crud.eliminar_baremo nunca borra un tramo en uso) y solo se avisa."""
    if prueba.modo_interpretacion == models.MODO_INTERPRETACION_PERFIL:
        print("↪️  modo_interpretacion ya era 'perfil'; no se toca.")
        return

    prueba.modo_interpretacion = models.MODO_INTERPRETACION_PERFIL

    baremos_antiguos = db.query(models.Baremo).join(
        models.Dimension, models.Baremo.dimension_id == models.Dimension.id
    ).filter(models.Dimension.prueba_id == prueba.id).all()
    eliminados, conservados = 0, 0
    for baremo in baremos_antiguos:
        en_uso = db.query(models.DiagnosticoAlumno.id).filter(
            models.DiagnosticoAlumno.baremo_id == baremo.id
        ).first() is not None
        if en_uso:
            conservados += 1
            continue
        db.delete(baremo)
        eliminados += 1

    db.commit()
    print(f"✅ modo_interpretacion activado en 'perfil'. Banda descriptiva anterior: "
          f"{eliminados} tramo(s) sin uso eliminados, {conservados} con diagnósticos "
          "históricos conservados intactos.")


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.Prueba).filter(
            models.Prueba.nombre_tecnico == NOMBRE_TECNICO,
            models.Prueba.institucion_id.is_(None),
        ).first()
        if existente:
            print(f"↪️  IPIP-RIASEC ya existe (prueba id={existente.id}); no se toca su catálogo.")
            _asegurar_orden_por_puntaje(db, existente)
            _asegurar_modo_perfil(db, existente)
            _asegurar_contenido_informe(db, existente)
            return

        prueba = models.Prueba(
            nombre_tecnico=NOMBRE_TECNICO,
            nombre_publico="Inventario de Intereses Vocacionales RIASEC (IPIP-AFPD, 48 ítems)",
            instrucciones=(
                "Indique, para cada actividad, cuánto le agrada o interesa realizarla, "
                "usando una escala de 1 (me desagrada mucho) a 5 (me gusta mucho)."
            ),
            requiere_consentimiento=True,
            activa=True,
            institucion_id=None,  # catálogo público de AuroraSoft
            escala_minima=1,
            escala_maxima=5,
            modo_calculo="likert_suma",
            # 🆕 'perfil', no 'rango' — ver advertencia del módulo y
            # "Interpretación por perfil" en CLAUDE.md. interpretar_perfil_
            # alumno compara las 6 dimensiones entre sí; no se carga ningún
            # Baremo porque en este modo nunca se consulta ninguno.
            modo_interpretacion=models.MODO_INTERPRETACION_PERFIL,
            visible_para_clientes=True,
            informante_tipo=models.INFORMANTE_ESTUDIANTE,  # autoadministrada
            # No es un instrumento de tamizaje repetido: los intereses
            # vocacionales son razonablemente estables — se aplica una vez
            # por proceso de orientación, no cada 2 semanas (mismo criterio
            # que seed_chaside.py, otro instrumento vocacional).
            dias_minimos_entre_aplicaciones=180,
            # 🆕 "Diseño A" — el informe PDF ordena las 6 dimensiones por
            # puntaje e imprime el código de perfil (top-3). Independiente
            # del modo_interpretacion de arriba (ver advertencia del módulo).
            ordenar_dimensiones_por_puntaje=True,
        )
        db.add(prueba)
        db.flush()

        total_preguntas = 0
        for nombre_dim in DIMENSIONES_ORDEN:
            dimension = models.Dimension(
                prueba_id=prueba.id,
                nombre=nombre_dim,
                descripcion=(
                    f"Sub-escala {nombre_dim} del IPIP-RIASEC — suma de 8 ítems Likert "
                    "1-5 (sin ítems inversos), rango 8-40."
                ),
            )
            db.add(dimension)
            db.flush()

            for orden, texto in enumerate(PREGUNTAS[nombre_dim], start=1):
                pregunta = models.Pregunta(
                    prueba_id=prueba.id,
                    dimension_id=dimension.id,
                    texto_pregunta=texto,
                    orden=orden,
                    es_inverso=False,  # el IPIP-RIASEC no tiene ítems inversos
                )
                db.add(pregunta)
                db.flush()
                for texto_opcion, valor in OPCIONES:
                    db.add(models.OpcionRespuesta(
                        pregunta_id=pregunta.id, texto_opcion=texto_opcion, valor_puntuacion=valor,
                    ))
                total_preguntas += 1

        db.commit()
        print(f"✅ IPIP-RIASEC cargado: prueba id={prueba.id}, {len(DIMENSIONES_ORDEN)} dimensiones "
              f"(R-I-A-S-E-C), {total_preguntas} preguntas. modo_interpretacion='perfil' — sin "
              "ningún Baremo (no se consulta ninguno en este modo).")
        _asegurar_contenido_informe(db, prueba)
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando IPIP-RIASEC: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
