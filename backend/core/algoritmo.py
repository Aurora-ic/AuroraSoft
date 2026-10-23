# ============================================================
# MOTOR DE CÁLCULO PSICOMÉTRICO - AuroraSoft
# Archivo: core/algoritmo.py
# ============================================================
import logging

logger = logging.getLogger("aurorasoft")

# Escala de respaldo para pruebas antiguas que quedaron con escala_minima o
# escala_maxima en NULL (la migración 371596cbc96e añadió esas columnas sin
# server_default). La migración a1f4c9d27e30 rellena esos NULL a partir de las
# opciones reales de cada prueba, así que en una base al día esto no debería
# usarse nunca — se mantiene solo para que un dato incompleto no tumbe la
# finalización del examen del alumno.
ESCALA_MINIMA_POR_DEFECTO = 0
ESCALA_MAXIMA_POR_DEFECTO = 3


def resolver_escala(prueba):
    """Devuelve (escala_minima, escala_maxima) siempre como enteros.

    Usa `getattr(..., None)` + comprobación `is None` en vez de `hasattr()`:
    en un modelo SQLAlchemy el atributo SIEMPRE existe aunque la columna valga
    NULL, así que `hasattr()` devolvía True y dejaba pasar un None que luego
    reventaba en `(escala_minima + escala_maxima)` con un TypeError.
    """
    escala_minima = getattr(prueba, "escala_minima", None) if prueba is not None else None
    escala_maxima = getattr(prueba, "escala_maxima", None) if prueba is not None else None

    if escala_minima is None:
        escala_minima = ESCALA_MINIMA_POR_DEFECTO
    if escala_maxima is None:
        escala_maxima = ESCALA_MAXIMA_POR_DEFECTO

    return int(escala_minima), int(escala_maxima)


def resolver_escala_item(pregunta, escala_minima_prueba, escala_maxima_prueba):
    """Devuelve (escala_minima, escala_maxima) de UNA pregunta: su propia
    escala (`Pregunta.escala_minima/escala_maxima`, ver migración
    f4d8a1c6b2e7_escala_por_pregunta) si está definida, o si no la escala
    de la `Prueba` completa (respaldo histórico — el comportamiento de
    siempre, antes de que existiera escala por ítem).

    Única función que debe resolver esto. Cualquier código que necesite
    invertir el valor de un ítem debe pasar por aquí (directamente o vía
    `invertir_valor_item`, más abajo) en vez de leer `Prueba.escala_minima/
    maxima` e inventar su propia fórmula — eso es justo lo que producía el
    bug que esta función cierra: dos caminos de código (el cálculo de
    dimensión y, antes de este fix, ningún otro) que podían llegar a
    recodificar un mismo ítem con escalas distintas."""
    escala_min = getattr(pregunta, "escala_minima", None) if pregunta is not None else None
    escala_max = getattr(pregunta, "escala_maxima", None) if pregunta is not None else None
    if escala_min is None:
        escala_min = escala_minima_prueba
    if escala_max is None:
        escala_max = escala_maxima_prueba
    return int(escala_min), int(escala_max)


def invertir_valor_item(pregunta, valor_raw, escala_minima_prueba, escala_maxima_prueba):
    """Devuelve el valor de una respuesta en su DIRECCIÓN CLÍNICA correcta:
    si `Pregunta.es_inverso`, aplica (escala_minima+escala_maxima)-valor_raw
    usando la escala que corresponde a ESE ítem (`resolver_escala_item`,
    nunca la de la Prueba a secas); si no es inversa, devuelve valor_raw
    tal cual. `valor_raw=None` (respuesta faltante) devuelve None sin
    tocarlo — el llamador decide qué hacer con un faltante, esta función
    nunca lo convierte en 0.

    Esta es la ÚNICA fórmula de inversión de todo el motor — tanto
    `calcular_likert_generico` (puntaje de dimensión) como
    `modulos.educativo.crud.evaluar_reglas_interpretacion`/
    `_resolver_items_monitoreados_riesgo` (ReglaInterpretacion ámbito
    'item') deben usarla, para que un ítem invertido se interprete
    siempre en la misma dirección sin importar qué parte del sistema lo
    esté leyendo — antes de este fix, las reglas de ámbito 'item'
    comparaban el valor CRUDO (pre-inversión), mientras que el puntaje de
    dimensión ya usaba el valor corregido: dos direcciones distintas para
    el mismo dato, sin que ningún instrumento cargado lo disparara todavía
    (ver auditoría de motor, sesión 2026-10-12)."""
    if valor_raw is None:
        return None
    if not getattr(pregunta, "es_inverso", False):
        return valor_raw
    escala_min, escala_max = resolver_escala_item(pregunta, escala_minima_prueba, escala_maxima_prueba)
    return (escala_min + escala_max) - valor_raw


def calcular_likert_generico(respuestas, items_db, escala_minima, escala_maxima, dimensiones_conteo=None):
    """
    Sirve para CUALQUIER prueba de suma por dimensión con o sin ítems invertidos
    -- PHQ-9 es la única cargada hoy (ver seed_phq9.py); cualquier otro
    instrumento de este modo_calculo es solo un dato nuevo, nunca código nuevo.

    La inversión ya no está hardcodeada en el código — se lee de Pregunta.es_inverso.
    Aplica la fórmula matemática general: (escala_minima + escala_maxima) - valor.

    🆕 dimensiones_conteo: dict opcional {dimension_id: umbral_item} para
    dimensiones con Dimension.tipo_calculo='conteo_sintomas' (ver NICHQ
    Vanderbilt — seed_vanderbilt_padres.py). En vez de SUMAR los valores de
    sus ítems, CUENTA cuántos (ya invertidos, si aplica) alcanzan o superan su
    propio umbral — ej. "6 de 9 ítems con puntuación ≥2". El resultado sigue
    siendo un número de dimensión como cualquier otro: a partir de aquí
    Baremo/DiagnosticoAlumno/ReglaInterpretacion lo tratan exactamente igual
    que una suma, sin saber que es un conteo.
    """
    # 🔒 Blindaje: aunque el llamador normal pasa por resolver_escala(), esta
    # función es pública y se invoca también desde tests. Un None aquí produce
    # un TypeError en plena finalización del examen, que por el commit previo
    # del estado "Finalizado" deja al alumno sin resultados y sin reintento.
    if escala_minima is None:
        escala_minima = ESCALA_MINIMA_POR_DEFECTO
    if escala_maxima is None:
        escala_maxima = ESCALA_MAXIMA_POR_DEFECTO
    dimensiones_conteo = dimensiones_conteo or {}

    # 🆕 Guarda la Pregunta completa (no solo su es_inverso) — invertir_valor_item
    # necesita leer también su escala propia, si la tiene (ver resolver_escala_item).
    mapa_preguntas = {item.id: item for item in items_db} if items_db else {}
    puntajes = {}

    for r in respuestas:
        if r.valor_raw is None or r.dimension is None:
            continue

        # 🔒 Inversión genérica basada en la BD para escalas min..max (ej: 1..5, 0..3)
        # — misma fórmula de siempre, pero ahora resuelta por invertir_valor_item
        # para que coincida exactamente con lo que usa evaluar_reglas_interpretacion
        # (ámbito 'item') al leer el mismo dato. Si la pregunta no está en
        # items_db (no debería pasar en operación normal), no se invierte —
        # mismo comportamiento de respaldo que el mapa anterior (.get(..., False)).
        pregunta = mapa_preguntas.get(r.pregunta_id)
        valor = invertir_valor_item(pregunta, r.valor_raw, escala_minima, escala_maxima)

        umbral_item = dimensiones_conteo.get(r.dimension)
        if umbral_item is not None:
            incremento = 1 if valor >= umbral_item else 0
        else:
            incremento = valor

        puntajes[r.dimension] = puntajes.get(r.dimension, 0) + incremento

    return {
        "puntajes_brutos": puntajes,
        "puntajes_norma": puntajes,
        "niveles": {} # El nivel/baremo se asignará dinámicamente consultando la BD
    }


def calcular_correcto_incorrecto(respuestas, items_db=None, dimensiones_conteo=None):
    """
    Para pruebas de habilidad/conocimiento (modo_calculo='correcto_incorrecto'):
    no hay inversión, cada ítem vale 1 si acertó (según
    OpcionRespuesta.valor_puntuacion) y 0 si no, sumado por dimensión/dominio.

    🆕 dimensiones_conteo: mismo mecanismo que calcular_likert_generico (ver
    su docstring) — nada impedía a nivel de BD que una Dimension con
    tipo_calculo='conteo_sintomas' viviera en una Prueba modo_calculo=
    'correcto_incorrecto' (el CHECK de la columna liga conteo_umbral_item
    a tipo_calculo, nunca a modo_calculo de la prueba), pero este camino de
    código ignoraba el parámetro por completo: antes de este fix, esa
    combinación SUMABA en vez de CONTAR, silenciosamente. No hay inversión
    en este modo, así que el valor comparado contra el umbral es siempre
    el crudo.
    """
    dimensiones_conteo = dimensiones_conteo or {}
    puntajes = {}
    for r in respuestas:
        if r.valor_raw is None or r.dimension is None:
            continue

        # valor_raw ya viene del frontend o backend como 1 o 0
        umbral_item = dimensiones_conteo.get(r.dimension)
        if umbral_item is not None:
            incremento = 1 if r.valor_raw >= umbral_item else 0
        else:
            incremento = r.valor_raw
        puntajes[r.dimension] = puntajes.get(r.dimension, 0) + incremento

    return {
        "puntajes_brutos": puntajes,
        "puntajes_norma": puntajes,
        "niveles": {}
    }


def calcular_resultados(codigo_prueba, respuestas, items_db=None, prueba=None, dimensiones_conteo=None):
    if prueba is not None and getattr(prueba, "modo_calculo", None) == "correcto_incorrecto":
        return calcular_correcto_incorrecto(respuestas, items_db, dimensiones_conteo=dimensiones_conteo)

    # 🔒 Resolución de escala tolerante a NULL (ver resolver_escala)
    escala_min, escala_max = resolver_escala(prueba)

    # Si la prueba no tenía escala definida Y además usa ítems inversos, el
    # respaldo puede recodificar con la escala equivocada y falsear puntajes.
    # No abortamos (dejaría al alumno bloqueado), pero lo dejamos en el log
    # para que sea detectable en vez de silencioso.
    escala_indefinida = prueba is None or (
        getattr(prueba, "escala_minima", None) is None
        or getattr(prueba, "escala_maxima", None) is None
    )
    if escala_indefinida and items_db and any(getattr(i, "es_inverso", False) for i in items_db):
        logger.warning(
            "Prueba '%s' tiene ítems inversos pero escala_minima/escala_maxima sin definir. "
            "Se recodifica con la escala por defecto %s..%s; revisa la configuración de la prueba.",
            codigo_prueba, escala_min, escala_max,
        )

    # 🟢 Pasamos los parámetros requeridos por calcular_likert_generico
    return calcular_likert_generico(respuestas, items_db, escala_min, escala_max, dimensiones_conteo=dimensiones_conteo)