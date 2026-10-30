from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, Numeric, JSON, CheckConstraint, Index, text

# 🔢 C-1 — Tipo común para toda la cadena de puntuación: valor de la opción ->
# puntaje obtenido -> puntaje directo -> límites del baremo. Antes todo era
# Integer: una prueba con ítems ponderados (0.5, 1.25...) perdía los decimales
# en silencio y el baremo interpretaba un número que no era el real.
# asdecimal=False devuelve float, que es lo que ya esperan los schemas, el PDF
# y el Excel: Decimal mezclado con float lanzaría TypeError en el algoritmo.
TIPO_PUNTAJE = Numeric(12, 4, asdecimal=False)
from sqlalchemy.sql import func
from core.database import Base
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey
# ==========================================
# 1. TABLAS DEL MOTOR DE EVALUACIONES (CATÁLOGO)
# ==========================================

# ⚠️ OBSOLETO para decidir si un resultado es de alerta.
#
# La detección de riesgo ya NO depende de que el psicólogo escriba el nivel
# exactamente como una de estas cadenas: se usa el indicador explícito
# `Baremo.es_alerta`, copiado a `DiagnosticoAlumno.es_alerta` en el momento de
# interpretar. La migración d3b8e1f05c94 tiene su PROPIA copia de este
# conjunto (NIVELES_DE_ALERTA_HISTORICOS) para el backfill único que hizo en
# su momento — no importa esta constante. Y hasta la Fase 4,
# `obtener_casos_pendientes_de_seguimiento` todavía comparaba contra esta
# lista de texto en vez del indicador explícito: un baremo es_alerta=True con
# un nivel fuera de este set retenía el informe y disparaba el correo, pero
# no aparecía en el worklist de seguimiento del psicólogo. Ya corregido — este
# conjunto queda solo como referencia/sugerencia al redactar baremos nuevos,
# sin ningún efecto en la lógica de negocio.
NIVELES_DE_ALERTA = {"alto", "crítico", "critico", "riesgo"}

# Estados posibles de la interpretación de una inscripción finalizada.
# Distinguen un resultado psicométrico real de un fallo de configuración.
INTERPRETACION_COMPLETA = "completa"      # todas las dimensiones tuvieron baremo
INTERPRETACION_INCOMPLETA = "incompleta"  # falta baremo en al menos una dimensión

# ==========================================
# REGLAS DE INTERPRETACIÓN ADICIONALES (genéricas, por prueba)
# ==========================================
# Capa de alerta que NO depende de baremos: un ítem, una dimensión o el
# puntaje total de la prueba puede, por sí solo, forzar revisión profesional
# aunque el tramo de baremo alcanzado no sea de alerta (ej. PHQ-9 ítem 9:
# ideación de autolesión). La regla vive en datos (esta tabla), nunca como
# `if prueba.nombre == "..."` en el motor — ver core/algoritmo.py, que sigue
# sin saber nada de ningún instrumento concreto.
AMBITO_ITEM = "item"
AMBITO_DIMENSION = "dimension"
AMBITO_PUNTAJE_TOTAL = "puntaje_total"
AMBITOS_REGLA_VALIDOS = {AMBITO_ITEM, AMBITO_DIMENSION, AMBITO_PUNTAJE_TOTAL}

OPERADORES_REGLA_VALIDOS = {">", ">=", "<", "<=", "==", "!="}

# Única acción soportada hoy: encender es_alerta (que ya dispara retención,
# notificación y worklist por sí solo — ver DiagnosticoAlumno.es_alerta más
# abajo). El campo queda como string, no bool, para poder añadir otra acción
# el día que haga falta sin una migración de esquema.
ACCION_ES_ALERTA = "es_alerta"
ACCIONES_REGLA_VALIDAS = {ACCION_ES_ALERTA}


class ReglaInterpretacion(Base):
    """Una condición configurable, adicional al baremo, que puede forzar alerta.

    `ambito` decide qué valor se compara: la respuesta a UNA pregunta
    (`pregunta_id`), el puntaje directo de UNA dimensión (`dimension_id`), o
    el puntaje total de la prueba entera (ninguno de los dos — se suman todas
    las dimensiones). `operador` + `valor_comparacion` son la condición
    (ej. ">" 0); `accion` es lo que ocurre si se cumple.
    """
    __tablename__ = "edu_reglas_interpretacion"
    __table_args__ = (
        CheckConstraint(
            "ambito IN ('item', 'dimension', 'puntaje_total')",
            name="ck_reglas_interpretacion_ambito_valido",
        ),
        CheckConstraint(
            "operador IN ('>', '>=', '<', '<=', '==', '!=')",
            name="ck_reglas_interpretacion_operador_valido",
        ),
        CheckConstraint(
            "accion IN ('es_alerta')",
            name="ck_reglas_interpretacion_accion_valida",
        ),
        # Una regla de ámbito 'item' necesita saber DE QUÉ pregunta; una de
        # 'dimension' necesita saber DE QUÉ dimensión. 'puntaje_total' no
        # necesita ninguna de las dos (se calcula sobre toda la prueba).
        CheckConstraint(
            "(ambito != 'item' OR pregunta_id IS NOT NULL) AND "
            "(ambito != 'dimension' OR dimension_id IS NOT NULL)",
            name="ck_reglas_interpretacion_campos_segun_ambito",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    prueba_id = Column(Integer, ForeignKey("edu_pruebas.id"), nullable=False, index=True)
    ambito = Column(String, nullable=False)
    pregunta_id = Column(Integer, ForeignKey("edu_preguntas.id"), nullable=True)
    dimension_id = Column(Integer, ForeignKey("edu_dimensiones.id"), nullable=True)
    operador = Column(String, nullable=False)
    valor_comparacion = Column(TIPO_PUNTAJE, nullable=False)
    accion = Column(String, nullable=False, server_default=ACCION_ES_ALERTA, default=ACCION_ES_ALERTA)
    descripcion = Column(Text, nullable=True)
    activa = Column(Boolean, nullable=False, server_default="true", default=True)
    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    creado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# 🆕 Segundo algoritmo de interpretación, ahora implementado: "perfil"
# compara las dimensiones de UNA MISMA inscripción entre sí (quién quedó
# 1º, 2º...) en vez de leer cada una contra un rango absoluto de Baremo —
# ver crud.interpretar_perfil_alumno()/crud.interpretar_segun_modo() y la
# sección "Interpretación por perfil" en CLAUDE.md. El placeholder llevaba
# declarado desde antes sin algoritmo (deliberadamente, para que nadie lo
# usara y el motor lo tratara en silencio como "rango"); IPIP-RIASEC es la
# prueba real que lo necesitaba y la primera en usarlo.
MODO_INTERPRETACION_RANGO = "rango"
MODO_INTERPRETACION_PERFIL = "perfil"
MODOS_INTERPRETACION_VALIDOS = {MODO_INTERPRETACION_RANGO, MODO_INTERPRETACION_PERFIL}

# 🆕 Informante — quién responde el instrumento, DISTINTO de sobre quién es
# el resultado (Inscripcion.persona_id, que nunca cambia de significado).
# La mayoría de pruebas son autorreporte ("estudiante"), pero varias
# reales (NICHQ Vanderbilt, SDQ, RCADS, SCARED) tienen versiones pensadas
# para que las responda un padre/madre o un docente ACERCA del estudiante.
# Cada versión se carga como una Prueba propia (mismo criterio que ya usa
# el catálogo: una fila por variante, nunca una rama de código nueva), así
# que esto es puramente dato — el motor de cálculo/interpretación no
# necesita saber que existe.
INFORMANTE_ESTUDIANTE = "estudiante"
INFORMANTE_PADRE_MADRE = "padre_madre"
INFORMANTE_DOCENTE = "docente"
INFORMANTES_VALIDOS = {INFORMANTE_ESTUDIANTE, INFORMANTE_PADRE_MADRE, INFORMANTE_DOCENTE}


class Prueba(Base):
    __tablename__ = "edu_pruebas"
    __table_args__ = (
        CheckConstraint(
            "modo_interpretacion IN ('rango', 'perfil')",
            name="ck_pruebas_modo_interpretacion_valido",
        ),
        CheckConstraint(
            "informante_tipo IN ('estudiante', 'padre_madre', 'docente')",
            name="ck_pruebas_informante_tipo_valido",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    nombre_tecnico = Column(String, index=True)
    nombre_publico = Column(String)
    # 🆕 Nombre corto CURADO para UI (auditoría de UX, sesión 2026-10-13) —
    # NULL por defecto: la UI debe usar nombre_tecnico como título corto de
    # respaldo (ya es razonable para la mayoría: "PHQ-9", "GAD-7", "CES-DC"),
    # y recurrir a este campo solo cuando nombre_tecnico es un identificador
    # interno no legible para un psicólogo (ej. "HAMILTON_AUTOINFORME" ->
    # "Escala de Hamilton (autoinforme)", "VANDERBILT_PADRES" -> "NICHQ
    # Vanderbilt — Padres"). nombre_tecnico NUNCA se renombra para esto —
    # sigue siendo el identificador estable que usan los seeds/lookups; este
    # campo es puramente de presentación. nombre_publico (el nombre
    # completo) sigue existiendo sin cambios para la descripción expandida.
    nombre_corto = Column(String, nullable=True)
    instrucciones = Column(Text, nullable=True)
    requiere_consentimiento = Column(Boolean, default=True)
    activa = Column(Boolean, default=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)
    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)

    # 🆕 Estas dos columnas son las que reemplazan tener que escribir una función por prueba
    # NOT NULL + server_default (migración a1f4c9d27e30): un NULL aquí rompía
    # la recodificación de ítems inversos durante la finalización del examen.
    escala_minima = Column(Integer, nullable=False, server_default="0", default=0)   # ej: PHQ-9 usa 0-3, otras usan 1-4, etc.
    escala_maxima = Column(Integer, nullable=False, server_default="3", default=3)
    modo_calculo = Column(String, nullable=False, server_default="likert_suma", default="likert_suma")  # "likert_suma" o "correcto_incorrecto" (para ICAR)
    dias_minimos_entre_aplicaciones = Column(Integer, default=60)  # 🆕 ajustable por prueba, no genérico

    # 🆕 Espejo de modo_calculo para la INTERPRETACIÓN en vez del CÁLCULO.
    # "rango" (default, toda prueba existente) sigue usando interpretar_
    # resultados_alumno (cada dimensión contra su propio Baremo). "perfil"
    # usa interpretar_perfil_alumno (compara las dimensiones de la misma
    # inscripción entre sí, sin consultar Baremo) — ver
    # crud.interpretar_segun_modo(), el único punto que decide cuál correr.
    # Deliberadamente NO expuesto en PruebaUpdate/PATCH: cambiar el modo de
    # interpretación de una prueba ya cargada es una decisión estructural,
    # no un ajuste de configuración — se hace a mano (seed script), nunca
    # por accidente vía API.
    modo_interpretacion = Column(String, nullable=False, server_default=MODO_INTERPRETACION_RANGO, default=MODO_INTERPRETACION_RANGO)

    # 🆕 Catálogo genérico: distingue una prueba ofrecida a instituciones
    # (colegios clientes) de una prueba interna de AuroraSoft (p. ej. de
    # validación técnica del motor, nunca clínica ni comercial). NOT NULL +
    # server_default="true" — toda prueba existente (PHQ-9, cualquier prueba
    # privada de colegio) queda visible exactamente como antes; solo una
    # prueba que explícitamente se marque en False (vía script de datos, no
    # por código que compare nombre_tecnico) deja de aparecer en el catálogo
    # que ve un colegio y deja de admitir campañas nuevas para no-superadmin.
    visible_para_clientes = Column(Boolean, nullable=False, server_default="true", default=True)

    # 🆕 Informe profesional — contenido CONFIGURADO POR LA PRUEBA (fuente "B"
    # de las tres fuentes del informe: automático / configurado / profesional).
    # motivo_consulta_default se usa tal cual en el PDF salvo que el
    # profesional escriba el suyo en Inscripcion.motivo_consulta (ese SIEMPRE
    # prevalece). tecnicas_adicionales es una lista separada por comas (mismo
    # criterio que dimensiones_sin_baremo/reglas_con_error) de técnicas que se
    # suman al instrumento mismo (que ya se toma de nombre_publico) — ej.
    # "Entrevista, Observación". observacion_conductual_default (🆕) es el
    # mismo mecanismo de fallback para la sección 4 del PDF — se usa tal cual
    # salvo que el profesional escriba la suya en
    # Inscripcion.observacion_conductual (ese SIEMPRE prevalece, ver abajo).
    # Ninguno de los tres se inventa por prueba individual: por decisión
    # explícita del producto, AuroraSoft estandarizó el mismo texto
    # (procedimental, no clínico) para las tres en TODAS las pruebas
    # cargadas — ver seeds/_contenido_informe_comun.py. Si quedan NULL, el
    # informe simplemente no imprime esa línea (ver "NO INVENTAR CONTENIDO").
    motivo_consulta_default = Column(Text, nullable=True)
    tecnicas_adicionales = Column(Text, nullable=True)
    observacion_conductual_default = Column(Text, nullable=True)

    # 🆕 Recomendación GENÉRICA de la prueba — mismo rol que motivo_consulta_
    # default (fuente "B"), pero para la sección 7 en vez de la 2: texto fijo
    # que no depende de qué tramo alcanzó el estudiante (ej. CHASIDE: "Se
    # recomienda que el/la evaluado/a investigue el perfil profesional..."
    # idéntico en todo informe, nunca condicionado al resultado). Prioridad
    # exacta en obtener_datos_para_pdf(): profesional (recomendaciones_
    # override) > agregado de Baremo.recomendacion_sugerida por tramo
    # alcanzado (si hay alguno) > este campo > nada. NULL en toda prueba
    # existente: cero cambio de comportamiento, las que ya usan
    # recomendacion_sugerida por tramo (PHQ-9/GAD-7) nunca llegan a leer este
    # campo porque esa lista nunca queda vacía para ellas.
    recomendacion_generica_default = Column(Text, nullable=True)

    # 🆕 Ver INFORMANTES_VALIDOS arriba. NOT NULL + server_default="estudiante":
    # toda prueba existente sigue siendo autorreporte, sin cambio de comportamiento.
    informante_tipo = Column(String, nullable=False, server_default=INFORMANTE_ESTUDIANTE, default=INFORMANTE_ESTUDIANTE)

    # 🆕 Informe PDF — "Diseño A" para pruebas de PERFIL (ver IPIP-RIASEC):
    # cuando es True, obtener_datos_para_pdf() ordena las dimensiones del
    # informe por puntaje descendente (en vez del orden de creación, fijo
    # siempre) e imprime un "código de perfil" (las 3 dimensiones más altas)
    # bajo el gráfico de la sección 5.1 — pura presentación, no toca
    # Baremo/DiagnosticoAlumno ni el motor de interpretación. NOT NULL +
    # server_default="false": toda prueba existente conserva el orden de
    # dimensiones que ya tenía, cero cambio de comportamiento. No sustituye
    # al modo de interpretación "perfil" (comparar dimensiones entre sí para
    # decidir es_alerta/nivel) que `modo_interpretacion` sigue reservando sin
    # implementar — esto es solo cómo se MUESTRAN los resultados ya
    # calculados, no cómo se interpretan.
    ordenar_dimensiones_por_puntaje = Column(Boolean, nullable=False, server_default="false", default=False)

    # 🆕 Informe PDF — agrupamiento por ÁREA para pruebas vocacionales con
    # dimensiones PAREADAS (ver CHASIDE: 7 áreas × Intereses/Aptitudes, cada
    # una interpretada por rango contra su propio Baremo — a diferencia de
    # IPIP-RIASEC, que compara 6 dimensiones sueltas entre sí). Cuando es
    # True, obtener_datos_para_pdf() agrupa las dimensiones de la prueba por
    # la convención de nombre "Tipo — Código: Nombre del área" (Tipo ∈
    # {"Intereses","Aptitudes"}, ya usada por seed_chaside.py) y arma, en vez
    # del listado plano de siempre, tres bloques en la sección 5.2: áreas con
    # nivel "Alto" en Intereses, en Aptitudes, y su unión ("Áreas Vocacionales
    # Compatibles") — ver crud._agrupar_dimensiones_por_area(). Pura
    # presentación/síntesis de lo ya calculado: nunca cambia qué Baremo
    # aplica ni el nivel de cada dimensión. NOT NULL + server_default="false":
    # toda prueba existente sigue imprimiendo el listado plano de siempre,
    # cero cambio de comportamiento. No reemplaza a modo_interpretacion=
    # 'perfil' (que SÍ cambia la interpretación comparando dimensiones) ni a
    # ordenar_dimensiones_por_puntaje (pensado para dimensiones sueltas, no
    # pareadas) — son tres mecanismos independientes para tres formas
    # distintas de prueba, que pueden combinarse si algún instrumento futuro
    # lo necesitara.
    agrupar_dimensiones_por_area = Column(Boolean, nullable=False, server_default="false", default=False)

    # 🆕 Criterio normativo ACTIVO — ver Baremo.criterio_normativo arriba.
    # NULL (toda prueba existente) significa "interpretar contra los tramos
    # con criterio_normativo IS NULL", que es exactamente lo único que existe
    # hoy: cero cambio de comportamiento. Cuando una prueba tiene más de un
    # criterio cargado (ej. GAD-7: corte clásico y corte peruano), este campo
    # dice cuál de las etiquetas de Baremo.criterio_normativo aplica — un
    # PATCH normal sobre Prueba (PruebaUpdate), no un endpoint nuevo. Cambiar
    # este valor y después llamar POST /inscripciones/{id}/reprocesar sobre
    # las inscripciones afectadas es el mecanismo correcto para "decidimos
    # usar el corte peruano desde ahora", mismo patrón ya usado para corregir
    # un Baremo mal configurado, aplicado a un eje distinto.
    criterio_normativo_activo = Column(String, nullable=True, default=None)

# 🆕 Dimensión compuesta — ver DimensionComponente más abajo. 'items' (toda
# dimensión de las 6 pruebas ya cargadas) suma los puntajes de sus propias
# Pregunta, exactamente como siempre. 'suma_de_dimensiones' no tiene
# preguntas propias: su puntaje_directo es la suma de los puntaje_directo ya
# calculados de otras dimensiones (sus "componentes") — y a partir de ahí se
# comporta exactamente como cualquier otra dimensión (Baremo, DiagnosticoAlumno,
# ReglaInterpretacion no necesitan saber que existe este concepto). Resuelve
# el hueco documentado de SCARED (total 0-82) y RCADS-47 (Total Ansiedad,
# Total Ansiedad+Depresión), que no tenían forma de cargarse como Baremo
# porque Pregunta.dimension_id es una FK única.
TIPO_CALCULO_ITEMS = "items"
TIPO_CALCULO_SUMA_DE_DIMENSIONES = "suma_de_dimensiones"
# 🆕 Conteo de síntomas — una Dimension SÍ tiene preguntas propias (a
# diferencia de 'suma_de_dimensiones'), pero su puntaje_directo no es la suma
# de los valores crudos de sus ítems: es la CANTIDAD de ítems que alcanzan o
# superan `conteo_umbral_item`. Resuelve el hueco real que surgió al cargar
# NICHQ Vanderbilt (escala de evaluación para padres): su criterio clínico
# oficial no es "sumar y comparar contra un rango" sino "6 de 9 ítems con
# puntuación ≥2" — una suma puede dar el mismo total con una distribución de
# respuestas que no cumple ese conteo (nueve ítems en 2 = conteo 9/9, pero
# cinco ítems en 3 y cuatro en 0 = conteo 5/9 con una suma MAYOR), así que no
# hay forma honesta de expresar el criterio oficial como un Baremo de suma.
# Una vez calculado como conteo, el resultado es un número como cualquier
# otro: Baremo/DiagnosticoAlumno/ReglaInterpretacion lo interpretan exacta-
# mente igual que una suma, sin saber que es un conteo (ver
# core/algoritmo.py:calcular_likert_generico).
TIPO_CALCULO_CONTEO_SINTOMAS = "conteo_sintomas"
TIPOS_CALCULO_DIMENSION_VALIDOS = {TIPO_CALCULO_ITEMS, TIPO_CALCULO_SUMA_DE_DIMENSIONES, TIPO_CALCULO_CONTEO_SINTOMAS}

# 🆕 Pregunta.tipo_respuesta (sesión 2026-10-17) — cierra el límite #4 de
# "Cinco límites reales del motor" (ver docs/catalogo-pruebas.md): un ítem
# de respuesta CONSTRUIDA (el alumno escribe números, no elige una
# OpcionRespuesta) — primer caso real, BARSIT "Razonamiento numérico". Ver
# Pregunta más abajo para el detalle completo.
TIPO_RESPUESTA_OPCION_MULTIPLE = "opcion_multiple"
TIPO_RESPUESTA_NUMERICO = "numerico"
TIPOS_RESPUESTA_VALIDOS = {TIPO_RESPUESTA_OPCION_MULTIPLE, TIPO_RESPUESTA_NUMERICO}


class Dimension(Base):
    """Las escalas o áreas que mide el test (ej. "Depresión" para PHQ-9)."""
    __tablename__ = "edu_dimensiones"
    __table_args__ = (
        CheckConstraint(
            "tipo_calculo IN ('items', 'suma_de_dimensiones', 'conteo_sintomas')",
            name="ck_dimensiones_tipo_calculo_valido",
        ),
        # 🆕 Una dimensión 'conteo_sintomas' sin umbral nunca podría calcular
        # nada — mismo criterio que cualquier otro campo "obligatorio según
        # el valor de otro campo" ya impuesto a nivel de BD en este modelo.
        CheckConstraint(
            "tipo_calculo != 'conteo_sintomas' OR conteo_umbral_item IS NOT NULL",
            name="ck_dimensiones_conteo_umbral_requerido",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    prueba_id = Column(Integer, ForeignKey("edu_pruebas.id"))
    nombre = Column(String)
    descripcion = Column(Text, nullable=True)
    # NOT NULL + server_default='items': toda dimensión existente sigue
    # calculándose exactamente como antes (suma de sus propias Pregunta).
    tipo_calculo = Column(String, nullable=False, server_default=TIPO_CALCULO_ITEMS, default=TIPO_CALCULO_ITEMS)
    # 🆕 Solo tiene sentido cuando tipo_calculo='conteo_sintomas': el valor
    # (ya invertido, si aplica) que un ítem debe alcanzar o superar para
    # contar como "positivo" — ej. 2 en una escala de frecuencia 0-3 (NICHQ
    # Vanderbilt: "puntuación 2 o 3"), o 4 en una escala de funcionamiento
    # 1-5 ("problema de rendimiento"). NULL para cualquier otro tipo_calculo.
    conteo_umbral_item = Column(Integer, nullable=True, default=None)

    # 🆕 Contenido de informe para pruebas con Prueba.modo_interpretacion=
    # 'perfil' (ver crud.interpretar_perfil_alumno en este mismo archivo)
    # — ese modo NUNCA consulta Baremo (compara dimensiones entre sí, no
    # contra un rango absoluto), así que Baremo.interpretacion/conclusion_
    # sugerida/recomendacion_sugerida no tienen ningún tramo al que
    # anclarse para estas pruebas. Estos tres campos son el equivalente,
    # anclado a la Dimension en vez de a un Baremo: `obtener_datos_para_pdf`
    # elige predominante/secundaria según si esta dimensión quedó entre las
    # `top_n` de mayor puntaje de ESTA aplicación (ver _calcular_codigo_
    # perfil) y, si existe, SOBRESCRIBE el texto automático de rango/posición
    # que interpretar_perfil_alumno ya escribió (ej. "1º de 6") — nunca lo
    # hace si el campo está NULL (ninguna prueba existente usa esto todavía,
    # cero cambio de comportamiento). conclusion_sugerida_perfil solo se
    # agrega a la sección 6 cuando la dimensión es predominante, mismo
    # criterio que Baremo.conclusion_sugerida en modo 'rango'. No hay un
    # "recomendacion_sugerida_perfil" propio: la recomendación fija de una
    # prueba de perfil (si la necesita) usa Prueba.recomendacion_generica_
    # default, el mismo campo que ya usan APGAR-FAMILIAR/CHASIDE, para no
    # duplicar un mecanismo que ya existe.
    contenido_perfil_predominante = Column(Text, nullable=True)
    contenido_perfil_secundaria = Column(Text, nullable=True)
    conclusion_sugerida_perfil = Column(Text, nullable=True)


class DimensionComponente(Base):
    """Qué Dimension 'items' alimentan a una Dimension 'suma_de_dimensiones'.

    Deliberadamente sin anidar: `dimension_componente_id` nunca puede a su
    vez ser una dimensión compuesta (validado en crud, no solo documentado)
    — así el cálculo queda en dos pasadas simples (ver
    crud.calcular_resultados_dimensiones) y no hace falta detectar ciclos.
    """
    __tablename__ = "edu_dimensiones_componentes"
    __table_args__ = (
        UniqueConstraint(
            "dimension_compuesta_id", "dimension_componente_id",
            name="uq_edu_dim_componentes_par",
        ),
        CheckConstraint(
            "dimension_compuesta_id != dimension_componente_id",
            name="ck_edu_dim_componentes_no_autorreferencia",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    # CASCADE: si se borra la dimensión compuesta, sus filas de composición
    # no tienen ningún sentido por sí solas. La dimensión COMPONENTE, en
    # cambio, NO tiene ondelete aquí a propósito — eliminar_dimension la
    # bloquea explícitamente mientras esté en uso como componente (ver
    # crud.py), para no desarmar en silencio una dimensión compuesta ya
    # configurada.
    dimension_compuesta_id = Column(
        Integer, ForeignKey("edu_dimensiones.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    dimension_componente_id = Column(Integer, ForeignKey("edu_dimensiones.id"), nullable=False, index=True)
    orden = Column(Integer, nullable=False, server_default="0", default=0)

class Pregunta(Base):
    __tablename__ = "edu_preguntas"
    __table_args__ = (
        CheckConstraint(
            "tipo_respuesta IN ('opcion_multiple', 'numerico')",
            name="ck_preguntas_tipo_respuesta_valido",
        ),
        # 🆕 Un ítem 'numerico' sin clave de corrección nunca podría
        # puntuarse — mismo criterio que Dimension.conteo_umbral_item.
        CheckConstraint(
            "tipo_respuesta != 'numerico' OR respuesta_correcta_numerica IS NOT NULL",
            name="ck_preguntas_respuesta_correcta_numerica_requerida",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    prueba_id = Column(Integer, ForeignKey("edu_pruebas.id"))
    dimension_id = Column(Integer, ForeignKey("edu_dimensiones.id"), nullable=True)
    texto_pregunta = Column(Text)
    orden = Column(Integer)
    es_inverso = Column(Boolean, default=False)  # 🆕 el dato que reemplaza las listas hardcodeadas

    # 🆕 Tipo de respuesta (sesión 2026-10-17) — cierra el límite #4 de
    # "Cinco límites reales del motor" (ver docs/catalogo-pruebas.md):
    # 'opcion_multiple' (de siempre, NOT NULL + server_default, cero cambio
    # para las 14 pruebas ya cargadas) vs. 'numerico', un ítem de respuesta
    # CONSTRUIDA — el alumno escribe una lista de números en vez de elegir
    # una OpcionRespuesta (ej. BARSIT "Razonamiento numérico": completar los
    # dos números que faltan en una serie). Un ítem 'numerico' no tiene
    # ninguna fila en OpcionRespuesta; su clave de corrección vive en
    # `respuesta_correcta_numerica`, de abajo. Ver guardar_respuestas_examen
    # en crud.py — es la única función que debe calcular el puntaje de un
    # ítem numérico (1 si coincide exactamente con la clave, 0 si no); el
    # cliente nunca envía ni decide ese puntaje, misma garantía que ya
    # tenía 'opcion_multiple' con OpcionRespuesta.valor_puntuacion.
    tipo_respuesta = Column(
        String, nullable=False,
        server_default=TIPO_RESPUESTA_OPCION_MULTIPLE, default=TIPO_RESPUESTA_OPCION_MULTIPLE,
    )
    # 🆕 Clave de corrección de un ítem 'numerico' — lista de números
    # esperados, EN ORDEN (ej. [30, 45] para una serie con dos espacios en
    # blanco, el primero y el segundo). NULL para cualquier ítem
    # 'opcion_multiple'. Nunca se expone al frontend del examen — solo la
    # CANTIDAD de valores esperados (ver crud.obtener_preguntas_por_token),
    # para que el alumno sepa cuántos campos llenar sin ver la respuesta.
    respuesta_correcta_numerica = Column(JSON, nullable=True)

    # 🆕 Escala PROPIA de este ítem (auditoría de motor, sesión 2026-10-13) —
    # NULL por defecto: cuando está vacía, cualquier cálculo que necesite
    # invertir esta pregunta usa la escala de `Prueba.escala_minima/maxima`
    # como respaldo, exactamente el comportamiento de siempre (cero cambio
    # para las 14 pruebas ya cargadas, todas con escala uniforme por
    # instrumento). Existe para el caso que SÍ rompe ese supuesto: un
    # instrumento con ítems de escalas heterogéneas (ej. NICHQ Vanderbilt,
    # que mezcla 0-3 y 1-5, aunque hoy no tiene ningún ítem inverso) que en
    # el futuro SÍ necesite invertir un ítem de la escala minoritaria — sin
    # esto, la fórmula de inversión recodificaría con la escala de la
    # prueba completa, no la de ese ítem, y produciría un puntaje
    # silenciosamente incorrecto. Ver `core.algoritmo.resolver_escala_item`
    # (única función que debe leer estas columnas — todo lo demás, incluida
    # la evaluación de ReglaInterpretacion ámbito 'item', pasa por ella en
    # vez de reimplementar la fórmula de inversión).
    escala_minima = Column(Integer, nullable=True)
    escala_maxima = Column(Integer, nullable=True)

    # 🆕 Ítem informativo del informe — NO participa del cálculo de ningún
    # puntaje (algoritmo.calcular_likert_generico ya ignora cualquier
    # respuesta cuya Pregunta tenga dimension_id=NULL, típicamente el caso
    # aquí). Cuando es True, obtener_datos_para_pdf() imprime literalmente la
    # opción que el estudiante eligió bajo la etiqueta `etiqueta_informe` —
    # ej. el ítem 10 del PHQ-9 ("qué tan difícil le han resultado estos
    # problemas"), que el protocolo clínico pide reportar pero no puntúa.
    # NOT NULL + server_default='false': cero cambio para cualquier pregunta
    # ya cargada.
    incluir_en_informe = Column(Boolean, nullable=False, server_default="false", default=False)
    etiqueta_informe = Column(String, nullable=True)

class OpcionRespuesta(Base):
    """Alternativas de cada pregunta del test"""
    __tablename__ = "edu_opciones"
    id = Column(Integer, primary_key=True, index=True)
    pregunta_id = Column(Integer, ForeignKey("edu_preguntas.id"))
    texto_opcion = Column(String)
    valor_puntuacion = Column(TIPO_PUNTAJE)

class Baremo(Base):
    """Convierte el Puntaje Directo en un Diagnóstico filtrando por variables demográficas"""
    __tablename__ = "edu_baremos"
    id = Column(Integer, primary_key=True, index=True)
    dimension_id = Column(Integer, ForeignKey("edu_dimensiones.id"))
    edad_min = Column(Integer, nullable=True)
    edad_max = Column(Integer, nullable=True)
    sexo = Column(String, nullable=True)
    poblacion = Column(String, nullable=True)
    puntaje_minimo = Column(TIPO_PUNTAJE)
    puntaje_maximo = Column(TIPO_PUNTAJE)
    tipo_puntaje = Column(String, nullable=True)
    valor_convertido = Column(String, nullable=True)
    nivel = Column(String)   # texto descriptivo libre: "Alto", "Severo", "Clínicamente significativo"...
    interpretacion = Column(Text, nullable=True)

    # 🆕 Criterio normativo — eje INDEPENDIENTE de `activo` (que sigue
    # significando exclusivamente trazabilidad/corrección de un tramo mal
    # configurado, nunca esto). Apareció con GAD-7 (corte clásico ≥10 vs.
    # corte peruano ≥8) y de nuevo con APGAR-FAMILIAR (dos tablas de corte
    # peruanas contradictorias): más de un criterio de interpretación válido
    # y documentado para el mismo rango de puntaje, que antes no se podía
    # cargar simultáneamente porque _validar_solapamiento_baremo lo rechazaba
    # con 409. NULL (el valor de las 6 pruebas ya cargadas) significa "el
    # único criterio" — cero cambio de comportamiento. Un valor no-NULL es
    # una etiqueta libre (ej. "corte_peru_2024") que identifica UN lente
    # alternativo de interpretación: dos tramos con criterio_normativo
    # distinto pueden solaparse en rango de puntaje sin disparar el 409,
    # porque no son un duplicado real, son dos formas válidas de leer el
    # mismo puntaje. Ver Prueba.criterio_normativo_activo, que decide cuál
    # de los criterios cargados se usa para interpretar.
    criterio_normativo = Column(String, nullable=True, default=None)

    # 🆕 Informe profesional — contenido CONFIGURADO POR LA PRUEBA, a nivel de
    # TRAMO (igual que `interpretacion`, del que son hermanos): qué conclusión
    # y qué recomendación sugiere este nivel concreto. Se copian a
    # DiagnosticoAlumno al interpretar (mismo criterio de snapshot que
    # `interpretacion`/`nivel`/`es_alerta`), así que editar el baremo después
    # nunca reescribe retroactivamente un informe ya emitido. El profesional
    # puede sustituirlas por su propio texto en Inscripcion.conclusion_override/
    # recomendaciones_override, que SIEMPRE prevalece sobre esto.
    conclusion_sugerida = Column(Text, nullable=True)
    recomendacion_sugerida = Column(Text, nullable=True)

    # 🚨 Indicador EXPLÍCITO de que este tramo exige revisión profesional.
    # Es el único criterio que usa el sistema para retener un informe: el
    # texto de `nivel` queda libre para que el psicólogo lo redacte como
    # quiera sin afectar a la seguridad del alumno.
    es_alerta = Column(Boolean, nullable=False, server_default="false", default=False)

    # 🆕 Trazabilidad/auditoría (sin versionado completo — ver auditoría de
    # arquitectura genérica, punto 1): un baremo con diagnósticos asociados ya
    # no puede editar su rango/nivel/es_alerta (crud.actualizar_baremo lo
    # bloquea con 409) — la única forma de "cambiar de criterio" sobre un
    # tramo ya usado es desactivarlo y crear uno nuevo. `activo=False` lo
    # saca de interpretar_resultados_alumno Y de la validación de solapes,
    # así un tramo de reemplazo puede cubrir el mismo rango sin chocar con el
    # desactivado. Reemplaza al DELETE físico cuando el baremo tiene uso
    # (crud.eliminar_baremo) — uno sin uso todavía se puede borrar de verdad.
    activo = Column(Boolean, nullable=False, server_default="true", default=True)
    # NULL = nunca se editó desde que se creó. Con zona horaria a propósito:
    # esta es una columna NUEVA, sin ningún dato histórico naive que migrar
    # (a diferencia de las demás columnas DateTime de este archivo, que
    # siguen sin `timezone=True` — ver docs/gaps-pendientes.md: el valor
    # Python que las llena ya se generó con datetime.now(timezone.utc) donde
    # era seguro, pero la propia COLUMNA se deja naive a propósito, porque
    # migrarla es un cambio de esquema aparte, no parte de este cierre).
    actualizado_en = Column(DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc))

# ==========================================
# 2. CONTROL DE CAMPAÑAS Y ACCESO DE ALUMNOS
# ==========================================

# 🆕 Ciclo de vida explícito de una campaña. `activo` (abajo) queda como
# columna heredada sin ningún efecto en la lógica de negocio (nunca se lee en
# ningún filtro ni candado) — no se repurpone para no cambiar en silencio el
# significado de un campo que ya viaja en EvaluacionResponse; el ciclo de vida
# real vive por completo en `estado`, nuevo desde esta migración y con CHECK
# desde el día uno (mismo criterio que Prueba.modo_interpretacion,
# ReglaInterpretacion.ambito, etc.).
ESTADO_CAMPANA_ACTIVA = "activa"
ESTADO_CAMPANA_CERRADA = "cerrada"
ESTADO_CAMPANA_CANCELADA = "cancelada"
ESTADOS_CAMPANA_VALIDOS = {ESTADO_CAMPANA_ACTIVA, ESTADO_CAMPANA_CERRADA, ESTADO_CAMPANA_CANCELADA}


class Evaluacion(Base):
    """Representa una campaña de evaluación creada por un psicólogo para un grupo específico"""
    __tablename__ = "edu_evaluaciones"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('activa', 'cerrada', 'cancelada')",
            name="ck_evaluaciones_estado_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # 🆕 index=True (hallazgo de auditoría, sesión 2026-10-16): esta columna es
    # exactamente lo que filtra listar_campanas_de_institucion y cada consulta
    # multi-tenant sobre campañas — sin índice, cada colegio acumulando años de
    # campañas termina forzando un scan secuencial de edu_evaluaciones completa
    # (compartida entre TODOS los tenants), no solo de sus propias filas.
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True) # <-- ¡AQUÍ AGREGAS EL ENLACE AL COLEGIO!
    prueba_id = Column(Integer, ForeignKey("edu_pruebas.id"))
    # 🔗 C-16 — antes era un entero suelto: se podía guardar el id de un usuario
    # inexistente y la alerta de riesgo (C-13) buscaba a su destinatario ahí.
    creador_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    nombre_grupo = Column(String)
    fecha_creacion = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    activo = Column(Boolean, default=True)
    fecha_fin = Column(DateTime, nullable=True)  # 👈 Columna para expiración por fecha

    # 🆕 Editar/cerrar/cancelar campaña — ver crud.actualizar_campana/
    # cerrar_campana/cancelar_campana. `estado` es la única fuente de verdad
    # del ciclo de vida; cerrar y cancelar, además de moverlo, fuerzan
    # `fecha_fin` a "ahora" (si no estaba ya en el pasado) para reutilizar tal
    # cual el candado de expiración que YA existe en los 7 puntos del flujo de
    # examen (guardar/finalizar/comenzar-test/progreso/preguntas/campos-socio
    # x2) y en matricular_roster_en_campana — cero endpoints nuevos que
    # revisar por expiración, cero riesgo de que alguno se quede sin el
    # candado. `motivo_cierre` es obligatorio para cancelar (crud lo exige) y
    # opcional para un cierre normal.
    estado = Column(String, nullable=False, server_default=ESTADO_CAMPANA_ACTIVA, default=ESTADO_CAMPANA_ACTIVA)
    fecha_cierre = Column(DateTime, nullable=True)
    # Nombre explícito = el que Postgres generaría solo (mismo criterio que
    # seccion_id en Inscripcion, arriba), para que create_all() y la cadena de
    # migraciones produzcan el mismo esquema.
    cerrada_por_usuario_id = Column(
        Integer,
        ForeignKey("auth_usuarios.id", name="edu_evaluaciones_cerrada_por_usuario_id_fkey"),
        nullable=True,
    )
    motivo_cierre = Column(Text, nullable=True)

# 🆕 Texto versionado del asentimiento informado que el alumno ve al abrir
# su link de examen (sesión 2026-10-18, ver Inscripcion.asentimiento_texto_
# version_id más abajo) — hasta ahora era una constante fija en el frontend
# (`TEXTO_ASENTIMIENTO_INFORMADO`), sin fuente configurable por institución
# ni versión que un alumno hubiera "visto realmente" quedara registrada.
class AsentimientoInformadoTexto(Base):
    """Una versión del texto de asentimiento — global (institucion_id=NULL,
    mismo patrón que PlantillaDocumento 'predeterminada') o propia de una
    institución. Solo una fila por institución (o la global) tiene
    activo=True a la vez: crear una versión nueva desactiva la anterior en
    la misma transacción (ver crud.crear_version_asentimiento_texto) — nunca
    se EDITA una fila ya usada por alguna Inscripcion, para que el snapshot
    de lo que un alumno realmente aceptó quede fijo para siempre aunque el
    texto activo cambie después.

    Dos índices únicos PARCIALES (no un UniqueConstraint normal — Postgres
    nunca trata dos NULL como iguales en una constraint UNIQUE, así que uno
    solo no cerraría el caso global) imponen "un solo `version` por ámbito"
    a nivel de BD de verdad: el commit que pierde la carrera de crear dos
    versiones a la vez para el mismo ámbito choca contra el índice, y
    crud.crear_version_asentimiento_texto lo traduce a 409 con
    commit_o_conflicto (core/concurrencia.py) — hallazgo real de
    tests/test_patron_concurrencia_unitario.py, no una precaución de más.
    """
    __tablename__ = "edu_asentimiento_textos"
    # 🆕 Modelos de consentimiento Y asentimiento por colegio y por nivel
    # (sesión 2026-10-30) — la tabla (y la clase, por compatibilidad con
    # todo lo que ya la usa) conserva su nombre, pero ahora guarda DOS
    # tipos de texto (`tipo_texto`: el consentimiento que firma el
    # apoderado, o el asentimiento que acepta el alumno) y, opcionalmente,
    # uno distinto por `nivel_educativo_id` (un asentimiento para Inicial no
    # se redacta igual que para Secundaria). Un "ámbito" es ahora
    # (institución | global, tipo_texto, nivel | general) — cada uno con su
    # propia numeración de versiones y su propia versión activa. Resolución:
    # nivel del alumno → general del colegio → global (ver
    # crud.resolver_texto_consentimiento_activo).
    #
    # Tres índices únicos PARCIALES en vez de dos — mismo motivo que antes
    # (Postgres nunca trata dos NULL como iguales en un UNIQUE), ahora con
    # una dimensión NULLable más.
    __table_args__ = (
        Index(
            "uq_edu_textos_consent_inst_nivel_version",
            "institucion_id", "tipo_texto", "nivel_educativo_id", "version",
            unique=True,
            postgresql_where=text("institucion_id IS NOT NULL AND nivel_educativo_id IS NOT NULL"),
        ),
        Index(
            "uq_edu_textos_consent_inst_general_version",
            "institucion_id", "tipo_texto", "version",
            unique=True,
            postgresql_where=text("institucion_id IS NOT NULL AND nivel_educativo_id IS NULL"),
        ),
        Index(
            "uq_edu_textos_consent_global_version",
            "tipo_texto", "version",
            unique=True,
            postgresql_where=text("institucion_id IS NULL"),
        ),
        CheckConstraint(
            "tipo_texto IN ('apoderado', 'asentimiento')",
            name="ck_edu_asentimiento_textos_tipo_valido",
        ),
        # Un nivel educativo siempre es de UNA institución — un texto global
        # por nivel no tiene sentido.
        CheckConstraint(
            "nivel_educativo_id IS NULL OR institucion_id IS NOT NULL",
            name="ck_edu_asentimiento_textos_nivel_requiere_institucion",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)
    # Mismos valores que ConsentimientoInformado.tipo_consentimiento
    # (TIPO_CONSENTIMIENTO_APODERADO / _ASENTIMIENTO en superadmin/models.py).
    tipo_texto = Column(String, nullable=False, server_default="asentimiento", default="asentimiento")
    nivel_educativo_id = Column(
        Integer,
        ForeignKey("niveles_educativos.id", name="edu_asentimiento_textos_nivel_educativo_id_fkey"),
        nullable=True,
        index=True,
    )
    version = Column(Integer, nullable=False)
    contenido = Column(Text, nullable=False)
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    creado_en = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)


class Inscripcion(Base):
    """Representa un 'cupo' o 'link mágico' único asignado a un estudiante"""
    __tablename__ = "edu_inscripciones"

    # 🔒 C-15 — Un alumno del padrón no puede quedar matriculado dos veces en
    # la misma campaña: duplicaba su fila en los dashboards y contaba doble en
    # la distribución de niveles, falseando la estadística del salón.
    #
    # Los links anónimos (persona_id NULL) quedan fuera de la restricción
    # porque PostgreSQL trata cada NULL como distinto, que es justo lo que
    # queremos: varios cupos sin nombre en la misma campaña son legítimos.
    # La anonimización ARCO también pone persona_id a NULL, así que nunca
    # choca con esta regla.
    __table_args__ = (
        UniqueConstraint(
            "evaluacion_id", "persona_id",
            name="uq_edu_inscripciones_evaluacion_persona",
        ),
        CheckConstraint(
            "informante_tipo IN ('estudiante', 'padre_madre', 'docente')",
            name="ck_inscripciones_informante_tipo_valido",
        ),
        # 🆕 Cierre de gap (docs/gaps-pendientes.md) — estado y
        # estado_interpretacion eran String libre con un set fijo de valores
        # reales en la práctica, nunca validado por la base de datos. Los
        # tres valores de estado son los únicos que el código real escribe
        # (crud.py/router.py: "Pendiente" por defecto, "En Progreso" al
        # empezar el examen, "Finalizado" al terminarlo) — nunca se borra ni
        # se reescribe una inscripción ya Finalizada, así que no hay un
        # cuarto estado "cancelado"/"expirado" que agregar aquí.
        CheckConstraint(
            "estado IN ('Pendiente', 'En Progreso', 'Finalizado')",
            name="ck_inscripciones_estado_valido",
        ),
        CheckConstraint(
            "estado_interpretacion IN ('completa', 'incompleta')",
            name="ck_inscripciones_estado_interpretacion_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    evaluacion_id = Column(Integer, ForeignKey("edu_evaluaciones.id"))
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)
    token = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    nombre_completo = Column(String, nullable=True)
    edad = Column(Integer, nullable=True)
    sexo = Column(String, nullable=True)
    poblacion = Column(String, nullable=True)
    # 🆕 Ver INFORMANTES_VALIDOS arriba. informante_tipo es un SNAPSHOT de
    # Prueba.informante_tipo al momento de matricular (mismo criterio que
    # grado_seccion_historico: nunca se vuelve a leer de Prueba después).
    # informante_nombre/informante_relacion (ej. "Madre", "Docente de aula")
    # solo se llenan cuando informante_tipo != 'estudiante' — para el
    # autorreporte de siempre quedan NULL, igual que en cualquier inscripción
    # existente antes de esta migración.
    informante_tipo = Column(String, nullable=False, server_default=INFORMANTE_ESTUDIANTE, default=INFORMANTE_ESTUDIANTE)
    informante_nombre = Column(String, nullable=True)
    informante_relacion = Column(String, nullable=True)
    estado = Column(String, default="Pendiente") 
    fecha_resolucion = Column(DateTime, nullable=True)

    # 🟢 AUDITORÍA DEL ASENTIMIENTO INFORMADO (LEY 29733) — esto es lo que el
    # propio ESTUDIANTE marca al abrir su link, figura legal distinta del
    # consentimiento que da su apoderado (ver consentimiento_apoderado_id/
    # consentimiento_asentimiento_id más abajo, que sí son ese consentimiento
    # pre-registrado). Renombrado desde acepto_consentimiento/fecha_
    # consentimiento/ip_consentimiento — mismo criterio y mismo patrón de
    # migración (RENAME de columna, sin pérdida de datos) que ya se usó en
    # 2026_10_08_2123-d4c774e7c9cf_asentimiento_estudiante_rename.py para el
    # asentimiento pre-registrado; ese rename se había quedado incompleto
    # porque no tocó estas tres columnas.
    acepto_asentimiento = Column(Boolean, default=False, nullable=False)
    fecha_asentimiento = Column(DateTime, nullable=True)
    ip_asentimiento = Column(String, nullable=True)
    # 🆕 Snapshot de QUÉ versión de AsentimientoInformadoTexto vio y aceptó
    # el alumno — se escribe una sola vez, en el mismo momento que
    # acepto_asentimiento pasa a True (ver crud.validar_y_registrar_alumno),
    # nunca se vuelve a tocar después aunque el texto activo cambie. NULL
    # para cualquier inscripción anterior a esta migración (no hay forma de
    # reconstruir retroactivamente qué texto vio un alumno que ya aceptó).
    asentimiento_texto_version_id = Column(
        Integer,
        ForeignKey(
            "edu_asentimiento_textos.id",
            name="edu_inscripciones_asentimiento_texto_version_id_fkey",
        ),
        nullable=True,
    )

    # 🔒 PASO 3.5: DERECHOS ARCO - SOFT DELETE Y ANONIMIZACIÓN (LEY 29733)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    is_anonymized = Column(Boolean, default=False, nullable=False)
    anonymized_at = Column(DateTime, nullable=True)

    # Los resultados sin alerta se entregan automáticamente. Los que tienen
    # alerta clínica se retienen hasta que un profesional los revise.
    resultado_visible_alumno = Column(Boolean, default=True, nullable=False)
    informe_liberado = Column(Boolean, default=True, nullable=False)
    interpretacion_clinica = Column(Text, nullable=True)

    # 🆕 Informe profesional — contenido de fuente "C" (PROFESIONAL, ver
    # sección "FUENTES DE CONTENIDO DEL INFORME"). Todos nullable y editables
    # solo vía PATCH /inscripciones/{id}/revision-informe, nunca escritos por
    # el motor. Cuando están vacíos, el informe usa el valor configurado por
    # la prueba (motivo_consulta_default, Baremo.conclusion_sugerida/
    # recomendacion_sugerida) o, si tampoco existe, señala explícitamente que
    # no hay contenido — nunca inventa texto clínico (ver "NO INVENTAR
    # CONTENIDO"). 🆕 observacion_conductual SÍ tiene ahora un valor por
    # defecto (Prueba.observacion_conductual_default, mismo mecanismo que
    # motivo_consulta_default) — el profesional sigue pudiendo sobrescribirlo
    # aquí para esta aplicación puntual, y ese valor SIEMPRE prevalece.
    motivo_consulta = Column(Text, nullable=True)
    observacion_conductual = Column(Text, nullable=True)
    # 🆕 Técnicas adicionales de ESTA aplicación puntual (sección 3 del PDF),
    # mismo mecanismo de override que motivo_consulta/observacion_conductual:
    # reemplaza por completo Prueba.tecnicas_adicionales cuando está
    # presente (lista separada por comas, ej. "Entrevista, Observación,
    # Revisión de expediente"). El instrumento mismo (Prueba.nombre_publico)
    # NUNCA se reemplaza aquí — siempre se imprime, sea cual sea este campo.
    tecnicas_override = Column(Text, nullable=True)
    conclusion_override = Column(Text, nullable=True)
    recomendaciones_override = Column(Text, nullable=True)
    # 🆕 Cargo/especialidad que se imprime bajo el nombre en la FIRMA del PDF
    # (ej. "Psicóloga Clínica — COP 12345"). Sin esto, el PDF solo podía
    # mostrar la etiqueta genérica del rol (_CARGO_POR_ROL: "Psicólogo(a)"),
    # nunca el título o colegiatura real del profesional que firma. Mismo
    # patrón "override" que conclusion_override/recomendaciones_override:
    # vacío = se usa la etiqueta genérica de siempre, cero cambio.
    firma_cargo_override = Column(Text, nullable=True)
    # 🆕 Completa el bloque de firma (auditoría de UX, sesión 2026-10-13),
    # mismo patrón "override" exacto que firma_cargo_override:
    #   - firma_nombre_override: antes el NOMBRE de la firma era SIEMPRE
    #     derivado automáticamente de Inscripcion.revisado_por_usuario_id
    #     (o del creador de la campaña si nadie había revisado todavía),
    #     sin forma de corregirlo para un caso puntual (ej. un supervisor
    #     firma en lugar de quien hizo la revisión técnica). Vacío = se
    #     sigue derivando automáticamente, cero cambio de comportamiento.
    #   - firma_dni_override: antes la línea de DNI del profesional era
    #     siempre un literal fijo "DNI: ____________________" en blanco,
    #     para llenar a mano después de imprimir. Vacío = sigue imprimiendo
    #     ese mismo placeholder en blanco.
    firma_nombre_override = Column(Text, nullable=True)
    firma_dni_override = Column(String, nullable=True)

    revisado_por_usuario_id = Column(
        Integer,
        # Nombre explícito = el que crea la migración e72c49df46b1 (ver B-10).
        ForeignKey("auth_usuarios.id", name="fk_edu_inscripciones_revisado_por_usuario"),
        nullable=True,
    )
    fecha_revision_informe = Column(DateTime, nullable=True)

    # 🔍 Distingue un resultado psicométrico de un fallo de configuración.
    # "incompleta" significa que al menos una dimensión no encontró baremo
    # aplicable: NO es un alumno sin riesgo, es un resultado que nadie ha
    # podido interpretar todavía, y por eso también retiene el informe.
    estado_interpretacion = Column(
        String, nullable=False, server_default=INTERPRETACION_COMPLETA,
        default=INTERPRETACION_COMPLETA, index=True,
    )
    # Nombres de las dimensiones que quedaron sin interpretar, para que el
    # profesional sepa exactamente qué baremo le falta cargar.
    dimensiones_sin_baremo = Column(Text, nullable=True)

    # 🆕 Reglas de interpretación (ReglaInterpretacion) que existían para esta
    # prueba pero no se pudieron evaluar (ej. referencian una pregunta que el
    # alumno nunca respondió). Es una señal DISTINTA de dimensiones_sin_baremo
    # — un error de configuración de reglas, no una falta de baremo — pero
    # con la misma consecuencia: nunca se convierte en "sin riesgo", siempre
    # retiene el informe (ver evaluar_reglas_interpretacion en crud.py).
    reglas_con_error = Column(Text, nullable=True)

    # 🆕 Núcleo del estudiante — snapshot de la sección vigente del alumno en
    # el momento de matricularlo a ESTA campaña, con el mismo criterio que ya
    # usan nombre_completo/edad/sexo/poblacion: una evaluación ya aplicada no
    # debe cambiar de valor porque después el alumno se mueva de sección. El
    # FK es útil para consultas estructuradas mientras la sección exista tal
    # cual; el texto es la copia resistente incluso si esa sección se
    # renombra o se reorganiza más adelante. Ambos quedan NULL si el alumno
    # no tenía matrícula académica activa al momento de inscribirse (o si es
    # un cupo anónimo, sin persona_id).
    seccion_id = Column(
        Integer,
        # Nombre explícito = el que crea la migración 037502038612, para que
        # create_all y la cadena de migraciones produzcan el mismo esquema
        # (mismo criterio que revisado_por_usuario_id, más abajo).
        ForeignKey("secciones.id", name="edu_inscripciones_seccion_id_fkey"),
        nullable=True,
        index=True,
    )
    grado_seccion_historico = Column(String, nullable=True)

    # 🆕 Consentimientos del estudiante/apoderado — mismo principio de
    # snapshot que seccion_id, arriba: al matricular por padrón se guarda AQUÍ
    # qué fila concreta de ConsentimientoInformado estaba vigente en ese
    # instante, para cada uno de los dos consentimientos independientes. Un
    # consentimiento nunca se edita en el sitio (solo se revoca, lo que marca
    # esa MISMA fila, no la borra ni crea una nueva) — así que el FK por sí
    # solo ya es una prueba inmutable de "esto era lo vigente cuando se
    # aplicó", sin necesitar además una copia de texto: aunque ese
    # consentimiento se revoque después, esta fila sigue señalando al mismo
    # registro histórico, con su fecha_otorgamiento y (si corresponde)
    # fecha_revocacion intactas. NULL si no había consentimiento de ese tipo
    # vigente al matricular, o si es un cupo anónimo sin persona_id.
    consentimiento_apoderado_id = Column(
        Integer,
        ForeignKey(
            "consentimientos_informados.id",
            name="edu_inscripciones_consentimiento_apoderado_id_fkey",
        ),
        nullable=True,
        index=True,
    )
    # 🆕 Renombrada de consentimiento_estudiante_id (docs/gaps-pendientes.md)
    # — mismo FK, mismos datos, solo el nombre pasa a reflejar la figura
    # legal correcta (asentimiento del estudiante, no "su consentimiento").
    consentimiento_asentimiento_id = Column(
        Integer,
        ForeignKey(
            "consentimientos_informados.id",
            name="edu_inscripciones_consentimiento_asentimiento_id_fkey",
        ),
        nullable=True,
        index=True,
    )
# ==========================================
# 3. PREGUNTAS SOCIODEMOGRÁFICAS DINÁMICAS (OPCIONALES)
# ==========================================
class CampoSociodemografico(Base):
    __tablename__ = "edu_campos_socio"
    id = Column(Integer, primary_key=True, index=True)
    # 🔗 C-16 — `cliente_id` es la institución dueña del campo (el nombre es
    # heredado de la antigua tabla `clientes`); ahora con integridad referencial.
    cliente_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)
    pregunta = Column(String) 
    tipo_respuesta = Column(String) 
    opciones = Column(Text, nullable=True) 
    obligatorio = Column(Boolean, default=True)

class RespuestaSociodemografica(Base):
    __tablename__ = "edu_respuestas_socio"
    id = Column(Integer, primary_key=True, index=True)
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id")) 
    campo_id = Column(Integer, ForeignKey("edu_campos_socio.id")) 
    valor = Column(String) 

# ==========================================
# 4. RESOLUCIÓN DEL EXAMEN Y DIAGNÓSTICOS FINAL
# ==========================================
class RespuestaAlumno(Base):
    """Guarda exactamente qué alternativa marcó el alumno en cada ítem"""
    __tablename__ = "edu_respuestas_alumno"
    __table_args__ = (
        # 🆕 Exactamente uno de los dos — nunca ambos, nunca ninguno — según
        # Pregunta.tipo_respuesta ('opcion_multiple' siempre trae opcion_id,
        # 'numerico' siempre trae respuesta_numerica). Toda fila existente ya
        # cumple esto (opcion_id siempre presente, respuesta_numerica
        # siempre NULL hasta esta sesión), así que se agrega sin backfill.
        CheckConstraint(
            "(opcion_id IS NOT NULL) != (respuesta_numerica IS NOT NULL)",
            name="ck_respuestas_alumno_opcion_xor_numerica",
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id"))
    pregunta_id = Column(Integer, ForeignKey("edu_preguntas.id"))
    opcion_id = Column(Integer, ForeignKey("edu_opciones.id"))
    puntaje_obtenido = Column(TIPO_PUNTAJE)
    # 🆕 Lo que el alumno escribió para un ítem Pregunta.tipo_respuesta=
    # 'numerico' (ej. BARSIT "Razonamiento numérico") — análogo a lo que
    # `opcion_id` ya guarda para un ítem 'opcion_multiple'. NULL en ese
    # caso, y viceversa: `opcion_id` queda NULL en una fila 'numerico'.
    # `puntaje_obtenido` se calcula y se guarda en el servidor comparando
    # esto contra `Pregunta.respuesta_correcta_numerica` — nunca se confía
    # en un puntaje que mande el cliente, misma garantía que opcion_id ya
    # tenía. Ver crud.guardar_respuestas_examen.
    respuesta_numerica = Column(JSON, nullable=True)

class ResultadoDimension(Base):
    """Guarda la suma total de puntos (Puntaje Directo) de un alumno en cada área/dimensión"""
    __tablename__ = "edu_resultados_dimensiones"
    id = Column(Integer, primary_key=True, index=True)
    # 🆕 index=True en ambas FK (hallazgo de auditoría, sesión 2026-10-16):
    # esta tabla crece con cada (inscripción × dimensión) de TODOS los
    # tenants, para siempre — y es exactamente lo que
    # crud._armar_alumnos_y_distribucion filtra/joinea en cada dashboard. Sin
    # índice, esas consultas pasan de un lookup a un scan secuencial completo
    # de la tabla a medida que se acumulan años de campañas.
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id"), index=True)
    dimension_id = Column(Integer, ForeignKey("edu_dimensiones.id"), index=True)
    puntaje_directo = Column(TIPO_PUNTAJE)

class DiagnosticoAlumno(Base):
    """Almacena el resultado clínico interpretado para cada escala"""
    __tablename__ = "edu_diagnosticos_alumno"
    id = Column(Integer, primary_key=True, index=True)
    # 🆕 index=True en ambas FK — mismo motivo exacto que ResultadoDimension
    # arriba (hallazgo de auditoría, sesión 2026-10-16).
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id"), index=True)
    dimension_id = Column(Integer, ForeignKey("edu_dimensiones.id"), index=True)
    nivel = Column(String)
    tipo_puntaje_usado = Column(String, nullable=True)
    valor_convertido = Column(String, nullable=True)
    interpretacion = Column(Text, nullable=True)

    # 🆕 Snapshot de Baremo.conclusion_sugerida/recomendacion_sugerida al
    # momento de interpretar — mismo criterio que `interpretacion`/`nivel`,
    # sus hermanos en esta misma fila: un baremo editado después nunca
    # reescribe retroactivamente el contenido de un informe ya emitido.
    conclusion_sugerida = Column(Text, nullable=True)
    recomendacion_sugerida = Column(Text, nullable=True)

    # 🆕 Snapshot del rango de corte del tramo de Baremo aplicado (su
    # puntaje_minimo/maximo) — "Resultados cuantitativos" necesita poder
    # mostrar, por ejemplo, "Rango de corte: 10-14 puntos" tal como era
    # cuando se interpretó, sin depender de que ese Baremo siga existiendo
    # o no haya sido editado después.
    rango_minimo = Column(TIPO_PUNTAJE, nullable=True)
    rango_maximo = Column(TIPO_PUNTAJE, nullable=True)

    # Copia del `Baremo.es_alerta` vigente en el instante de interpretar.
    # Se guarda como instantánea y no por referencia: un diagnóstico ya
    # emitido es un registro histórico, y reeditar el baremo después no debe
    # reescribir retroactivamente si aquel alumno fue o no un caso de alerta.
    es_alerta = Column(Boolean, nullable=False, server_default="false", default=False)

    # 🆕 Trazabilidad de POR QUÉ es_alerta quedó en True: "baremo", "regla", o
    # "baremo,regla" cuando ambos coincidieron (nunca se duplica la alerta,
    # solo se registran los dos orígenes). NULL si es_alerta es False.
    # regla_activada_id apunta a la ReglaInterpretacion concreta que disparó
    # (si alguna lo hizo) — referencia histórica, no se borra si la regla se
    # desactiva después.
    alerta_por = Column(String, nullable=True)
    regla_activada_id = Column(Integer, ForeignKey("edu_reglas_interpretacion.id"), nullable=True)

    # 🆕 Puntero histórico a LA FILA de Baremo que produjo este diagnóstico —
    # antes solo se guardaba el CONTENIDO (nivel/interpretacion/rango arriba),
    # sin forma de preguntar "¿qué baremo exacto fue?". Mismo criterio que
    # regla_activada_id: referencia histórica, nunca se reescribe. A
    # diferencia de las reglas (que solo se desactivan, nunca se borran), un
    # Baremo sin uso SÍ puede borrarse físicamente (crud.eliminar_baremo) —
    # ondelete="SET NULL" evita que ese borrado rompa un diagnóstico ya
    # emitido; su contenido sigue intacto en las columnas de snapshot de
    # arriba con o sin este puntero.
    baremo_id = Column(Integer, ForeignKey("edu_baremos.id", ondelete="SET NULL"), nullable=True)

class SesionSeguimiento(Base):
    """
    Registra que un psicólogo dio seguimiento a un caso de alerta.
    """
    __tablename__ = "edu_sesiones_seguimiento"
    __table_args__ = (
        # 🆕 Cierre de gap (docs/gaps-pendientes.md) — mismos tres valores
        # que ya documentaba el comentario de la columna `estado` y el de
        # `SesionSeguimientoUpdate.estado` en schemas.py, ahora garantizados
        # por la base de datos.
        CheckConstraint(
            "estado IN ('Pendiente', 'En proceso', 'Atendido')",
            name="ck_sesiones_seguimiento_estado_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    psicologo_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    
    fecha = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    observaciones = Column(Text, nullable=True)
    accion_tomada = Column(String, nullable=True)  # ej: "derivado a psicología externa"
    acuerdos_compromisos = Column(Text, nullable=True)
    proxima_cita = Column(DateTime, nullable=True)
    estado = Column(String, default="Atendido")  # 'Pendiente', 'En proceso', 'Atendido'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# ==========================================
# 5. INFORMES (PDF versionado por aplicación)
# ==========================================
class Informe(Base):
    """Identidad del informe de UNA aplicación concreta (1 por Inscripcion).

    No pertenece al alumno sino a la inscripción/aplicación: un alumno con
    tres campañas resueltas tiene tres filas Informe independientes, cada una
    con su propio historial de versiones. institucion_id/prueba_id/persona_id
    están denormalizados aquí (mismo criterio ya usado en CitaProgramada,
    RegistroAuditoriaArco, NivelEducativo...) para poder filtrar/autorizar
    sin tener que atravesar Inscripcion -> Evaluacion en cada consulta.
    """
    __tablename__ = "edu_informes"
    __table_args__ = (
        UniqueConstraint("inscripcion_id", name="uq_edu_informes_inscripcion"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # ON DELETE CASCADE: un Informe no tiene vida propia fuera de su
    # Inscripcion — los scripts --limpiar de los E2E existentes (y el soft
    # delete/ARCO en producción) borran la inscripción sin saber nada de esta
    # tabla nueva; sin CASCADE, esa fila huérfana bloquearía el DELETE con un
    # IntegrityError en cada test que ya finalice un examen (ahora siempre
    # genera un informe en segundo plano).
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id", ondelete="CASCADE"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    prueba_id = Column(Integer, ForeignKey("edu_pruebas.id"), nullable=False)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)

    # La versión "actual" es la que sirven los endpoints de descarga. Nunca
    # baja: reemitir crea version_actual + 1, jamás reescribe una anterior.
    version_actual = Column(Integer, nullable=False, default=1)

    creado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    actualizado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class InformeVersion(Base):
    """Un PDF concreto, inmutable una vez creado — nunca se edita ni se sobreescribe.

    resultados_snapshot congela el resultado estructurado (puntajes, niveles,
    alerta, estado de interpretación...) usado para generar ESE PDF exacto,
    igual que Inscripcion ya congela nombre/edad/sexo/sección al momento de
    inscribirse: si el alumno cambia de sección o un baremo se corrige
    después, esta fila sigue describiendo fielmente lo que el informe decía
    cuando se emitió. El binario vive en storage (core/storage/); aquí solo
    la metadata necesaria para localizarlo y verificarlo.
    """
    __tablename__ = "edu_informe_versiones"
    __table_args__ = (
        UniqueConstraint("informe_id", "numero_version", name="uq_edu_informe_versiones_numero"),
        CheckConstraint(
            "origen IN ('automatica', 'reemision', 'reproceso')",
            name="ck_edu_informe_versiones_origen_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    informe_id = Column(Integer, ForeignKey("edu_informes.id", ondelete="CASCADE"), nullable=False, index=True)
    numero_version = Column(Integer, nullable=False)

    resultados_snapshot = Column(JSON, nullable=False)

    # 🆕 Reproceso de informe tras corrección de baremo — antes de esta
    # columna, "automática" (generado_por_usuario_id NULL) y "reemisión"
    # (generado_por_usuario_id con valor) eran las dos únicas formas de
    # aparecer una InformeVersion; un reproceso también trae usuario_id, así
    # que quedaría indistinguible de una simple reemisión salvo comparando a
    # mano el contenido de resultados_snapshot entre versiones. `origen` lo
    # deja explícito, mismo criterio de "nunca inferir" que ya usa el resto
    # del motor de informes (es_alerta, alerta_por...). Ver
    # crud.generar_y_almacenar_informe.
    origen = Column(String, nullable=False, server_default="automatica", default="automatica")

    storage_key = Column(String, nullable=False)
    nombre_archivo = Column(String, nullable=False)
    mime_type = Column(String, nullable=False, server_default="application/pdf", default="application/pdf")
    tamano_bytes = Column(Integer, nullable=False)
    checksum_sha256 = Column(String, nullable=False)

    generado_en = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # NULL = generado automáticamente por el sistema al finalizar el examen.
    # Con valor = una reemisión explícita pedida por ese usuario (ver motivo_version).
    generado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    # Obligatorio solo para reemisiones (v2+); v1 lleva "Emisión inicial".
    motivo_version = Column(Text, nullable=True)

    # 🆕 Riesgo operacional documentado en docs/gaps-pendientes.md ("un
    # reproceso que retiene un informe ya liberado no deja rastro de que esa
    # versión anterior circuló mientras estaba visible"). Esta columna NO
    # resuelve el riesgo de fondo — una vez que el alumno descargó el PDF, el
    # sistema no tiene forma de invalidarlo ni de retirarlo de donde sea que
    # haya terminado — pero sí deja explícito, en la propia versión nueva que
    # el reproceso genera, que la versión que reemplaza HABÍA estado liberada
    # y visible para el alumno (ver reprocesar_informe_de_inscripcion). Mismo
    # criterio de "nunca inferir" que origen/es_alerta: calculable a mano
    # comparando fechas contra el historial, pero eso es exactamente lo que
    # este motor ya decidió no pedirle a nadie.
    retracta_version_previa_liberada = Column(
        Boolean, nullable=False, server_default="false", default=False,
    )
