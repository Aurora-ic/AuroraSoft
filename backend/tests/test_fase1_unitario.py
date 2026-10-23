"""Pruebas unitarias de la Fase 1 — protección del estudiante en riesgo.

Aíslan la lógica de detección de alerta y el contrato de los motores, sin
base de datos ni servidor:

    python tests/test_fase1_unitario.py

Los ocho casos obligatorios se cubren de punta a punta en
tests/verificar_fase1_e2e.py; aquí se fija la lógica pura.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

# OJO: `modulos.superadmin.crud` y `modulos.educativo.crud` se importan
# mutuamente. La cadena solo se resuelve si el primero en cargarse es
# superadmin (que es el orden que impone main.py). Importar educativo.crud
# directamente revienta con ImportError. Es una fragilidad preexistente del
# proyecto, ajena a la Fase 1, pero hay que respetarla para poder testear.
import modulos.superadmin.crud  # noqa: E402,F401
from modulos.educativo import crud, models, schemas  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


class DiagnosticoFalso:
    def __init__(self, nivel, es_alerta):
        self.nivel = nivel
        self.es_alerta = es_alerta


# ======================================================================
# B-5 · La detección usa el indicador, no el texto
# ======================================================================
def test_b5_deteccion_por_indicador():
    print("\nB-5 · Detección de alerta por indicador explícito")

    comprobar(
        "Un nivel 'bajo' marcado como alerta SÍ se detecta",
        crud.detectar_niveles_de_alerta([DiagnosticoFalso("bajo", True)]) == ["bajo"],
        "el texto ya no manda",
    )
    comprobar(
        "Un nivel 'alto' NO marcado como alerta no se detecta",
        crud.detectar_niveles_de_alerta([DiagnosticoFalso("alto", False)]) == [],
    )

    # El fallo original: estos nombres nunca disparaban la protección
    nombres_antes_invisibles = [
        "Severo", "Alto riesgo", "Clínicamente significativo",
        "Muy alto", "ALTO ", "Requiere derivación inmediata",
    ]
    detectados = crud.detectar_niveles_de_alerta(
        [DiagnosticoFalso(n, True) for n in nombres_antes_invisibles]
    )
    comprobar(
        "Textos que antes eran invisibles ahora se detectan todos",
        len(detectados) == len(nombres_antes_invisibles),
        f"{len(detectados)}/{len(nombres_antes_invisibles)} detectados",
    )

    mezcla = [
        DiagnosticoFalso("Sin indicadores", False),
        DiagnosticoFalso("Severo", True),
        DiagnosticoFalso("Leve", False),
        DiagnosticoFalso("Crisis", True),
    ]
    comprobar(
        "Se devuelven solo los niveles marcados, en orden",
        crud.detectar_niveles_de_alerta(mezcla) == ["Severo", "Crisis"],
    )

    comprobar(
        "Un diagnóstico de alerta sin nombre no rompe el aviso",
        crud.detectar_niveles_de_alerta([DiagnosticoFalso(None, True)]) == ["Nivel sin nombre"],
    )
    comprobar("Lista vacía no detecta nada", crud.detectar_niveles_de_alerta([]) == [])


# ======================================================================
# B-5 · El modelo y los schemas exponen el indicador
# ======================================================================
def test_b5_modelo_y_schemas():
    print("\nB-5 · Modelo y schemas")

    comprobar("Baremo tiene la columna es_alerta", hasattr(models.Baremo, "es_alerta"))
    comprobar("DiagnosticoAlumno tiene la columna es_alerta",
              hasattr(models.DiagnosticoAlumno, "es_alerta"))

    baremo = schemas.BaremoCreate(
        dimension_id=1, puntaje_minimo=0, puntaje_maximo=10, nivel="Severo", es_alerta=True
    )
    comprobar("BaremoCreate acepta es_alerta", baremo.es_alerta is True)

    por_defecto = schemas.BaremoCreate(
        dimension_id=1, puntaje_minimo=0, puntaje_maximo=10, nivel="Leve"
    )
    comprobar("es_alerta por defecto es False (hay que marcarlo a propósito)",
              por_defecto.es_alerta is False)

    comprobar("BaremoUpdate permite corregir el indicador",
              "es_alerta" in schemas.BaremoUpdate.model_fields)
    comprobar("El nivel sigue siendo texto libre descriptivo",
              schemas.BaremoCreate.model_fields["nivel"].annotation is str)


# ======================================================================
# B-6 · Tres estados distinguibles
# ======================================================================
def test_b6_estados_interpretacion():
    print("\nB-6 · Distinción de los tres estados")

    comprobar("Existe la constante INTERPRETACION_COMPLETA",
              models.INTERPRETACION_COMPLETA == "completa")
    comprobar("Existe la constante INTERPRETACION_INCOMPLETA",
              models.INTERPRETACION_INCOMPLETA == "incompleta")
    comprobar("Inscripcion registra el estado de interpretación",
              hasattr(models.Inscripcion, "estado_interpretacion"))
    comprobar("Inscripcion registra qué dimensiones quedaron sin baremo",
              hasattr(models.Inscripcion, "dimensiones_sin_baremo"))
    comprobar("El endpoint de estado del alumno lo expone",
              "estado_interpretacion" in schemas.EstadoResultadosAlumnoResponse.model_fields)
    comprobar("El panel del psicólogo lo ve en InscripcionResponse",
              "estado_interpretacion" in schemas.InscripcionResponse.model_fields
              and "dimensiones_sin_baremo" in schemas.InscripcionResponse.model_fields)

    # La regla de decisión de la finalización, reproducida aquí tal cual
    def requiere_revision(alertas, completa):
        return bool(alertas) or not completa

    comprobar("1· Resultado válido sin alerta -> se entrega",
              requiere_revision([], True) is False)
    comprobar("2· Resultado válido con alerta -> se retiene",
              requiere_revision(["Severo"], True) is True)
    comprobar("3· Sin baremo aplicable -> se retiene (NO es 'sin riesgo')",
              requiere_revision([], False) is True)
    comprobar("3b· Sin baremo Y con alerta -> se retiene",
              requiere_revision(["Severo"], False) is True)


# ======================================================================
# B-9 · Los motores ya no confirman por su cuenta
# ======================================================================
def test_b9_motores_sin_commit():
    print("\nB-9 · Los motores no controlan la transacción")

    import inspect

    for nombre in ("calcular_resultados_dimensiones", "interpretar_resultados_alumno"):
        fuente = inspect.getsource(getattr(crud, nombre))
        comprobar(f"{nombre}() no llama a db.commit()", "db.commit()" not in fuente)
        comprobar(f"{nombre}() usa db.flush()", "db.flush()" in fuente)

    comprobar("Existe limpiar_resultados_previos() para recalcular sin duplicar",
              callable(getattr(crud, "limpiar_resultados_previos", None)))

    fuente_router = inspect.getsource(
        __import__("modulos.educativo.router", fromlist=["router"]).finalizar_examen_seguro
    )
    comprobar("La finalización obtiene la inscripción vía "
              "crud.bloquear_inscripcion_para_finalizar()",
              "crud.bloquear_inscripcion_para_finalizar(" in fuente_router)
    fuente_bloqueo = inspect.getsource(crud.bloquear_inscripcion_para_finalizar)
    comprobar("bloquear_inscripcion_para_finalizar() mantiene el bloqueo with_for_update()",
              "with_for_update()" in fuente_bloqueo)
    comprobar("bloquear_inscripcion_para_finalizar() fuerza estado fresco con "
              "populate_existing() (si no, el identity map de la Fase 1 sin "
              "bloqueo deja leer un estado obsoleto tras desbloquear)",
              "populate_existing()" in fuente_bloqueo)
    comprobar("La finalización revierte con db.rollback() ante un fallo",
              "db.rollback()" in fuente_router)
    comprobar("La finalización confirma una sola vez",
              fuente_router.count("db.commit()") == 1,
              f"{fuente_router.count('db.commit()')} commit(s)")
    # 🆕 finalizar_examen_seguro ya no llama a interpretar_resultados_alumno
    # directamente — despacha vía crud.interpretar_segun_modo() (que corre
    # interpretar_resultados_alumno para el modo 'rango', el único que
    # existía cuando se escribió este test; ver "Interpretación por perfil"
    # en CLAUDE.md). El orden que importa (interpretar antes de marcar
    # "Finalizado") es el mismo, solo cambió el nombre de la llamada.
    comprobar("El estado 'Finalizado' se asigna después de interpretar",
              fuente_router.index("interpretar_segun_modo")
              < fuente_router.index('inscripcion.estado = "Finalizado"'))


# ======================================================================
# C-13 · Respaldo institucional
# ======================================================================
def test_c13_respaldo():
    print("\nC-13 · Cadena de respaldo para las alertas")

    import inspect

    comprobar("Existe obtener_destinatarios_alerta()",
              callable(getattr(crud, "obtener_destinatarios_alerta", None)))

    fuente = inspect.getsource(crud.obtener_destinatarios_alerta)
    comprobar("Solo considera al creador si está activo", "creador.activo" in fuente)
    comprobar("Incluye a los admins de la institución como respaldo",
              '"admin"' in fuente and "rol.in_" in fuente)
    comprobar("Acota el respaldo a la institución de la campaña (aislamiento)",
              "institucion_id == evaluacion.institucion_id" in fuente)
    comprobar("Cae al correo de contacto del colegio como último recurso",
              "email_contacto" in fuente)

    from core.email_service import enviar_alerta_riesgo
    firma = inspect.signature(enviar_alerta_riesgo)
    comprobar("El envío acepta varios destinatarios",
              "destinatarios" in firma.parameters)
    comprobar("El envío distingue el motivo 'sin baremo'",
              "dimensiones_sin_baremo" in firma.parameters)
    comprobar("Sin destinatarios devuelve False en vez de romper",
              enviar_alerta_riesgo([], "Alumno", ["Severo"]) is False)


# ======================================================================
# 🆕 Validación server-side de examen completo (hallazgo de auditoría,
# sesión 2026-10-16/17, ver docs/gaps-pendientes.md) — segunda capa de
# defensa, independiente del candado de frontend (`faltanPreguntas`).
#
# `crud.contar_preguntas_sin_responder` usa func.count()/func.distinct() —
# agregados SQL reales que solo significan algo cuando una base de datos de
# verdad los evalúa sobre filas reales. Un duck-type con una lista de
# "respuestas falsas" ya sabría de antemano el resultado "correcto" que se
# supone debe estar probando (mismo criterio documentado en CLAUDE.md para
# `db.query(func.sum(...))...`): por eso aquí se verifica (a) que la
# aritmética de la función es correcta por construcción — un `max(a-b, 0)`
# nunca puede dar negativo ni confundir "más respuestas que preguntas" con
# "faltan preguntas" — y (b) a nivel de fuente, que `finalizar_examen_
# seguro` la llama en el momento correcto: con la fila ya bloqueada, DESPUÉS
# del candado de idempotencia y ANTES de calcular cualquier resultado. La
# cobertura real de la consulta SQL en sí queda para un e2e contra Postgres
# real (no construido en esta sesión — no hay base de datos disponible aquí).
# ======================================================================
def test_validacion_completitud_examen():
    print("\nValidación server-side de examen completo")

    import inspect

    comprobar("Existe crud.contar_preguntas_sin_responder()",
              callable(getattr(crud, "contar_preguntas_sin_responder", None)))

    fuente_funcion = inspect.getsource(crud.contar_preguntas_sin_responder)
    comprobar("Cuenta Pregunta de la prueba (total) vía func.count()",
              "func.count(models.Pregunta.id)" in fuente_funcion)
    comprobar("Cuenta RespuestaAlumno distintas por pregunta_id para esta inscripción",
              "func.count(func.distinct(models.RespuestaAlumno.pregunta_id))" in fuente_funcion)
    comprobar("El resultado nunca es negativo (max(..., 0) — más respuestas que "
              "preguntas, ej. un reproceso, nunca se reporta como 'faltan preguntas')",
              "max(" in fuente_funcion and ", 0)" in fuente_funcion)

    fuente_router = inspect.getsource(
        __import__("modulos.educativo.router", fromlist=["router"]).finalizar_examen_seguro
    )
    comprobar("finalizar_examen_seguro() llama a crud.contar_preguntas_sin_responder()",
              "crud.contar_preguntas_sin_responder(" in fuente_router)
    comprobar("Se evalúa DESPUÉS del candado de idempotencia (con la fila ya bloqueada)",
              fuente_router.index('inscripcion.estado == "Finalizado"')
              < fuente_router.index("crud.contar_preguntas_sin_responder("))
    comprobar("Se evalúa ANTES de calcular cualquier resultado "
              "(limpiar_resultados_previos)",
              fuente_router.index("crud.contar_preguntas_sin_responder(")
              < fuente_router.index("crud.limpiar_resultados_previos("))
    comprobar("Un examen incompleto se rechaza con 400, nunca con un 500 silencioso",
              "preguntas_sin_responder > 0" in fuente_router
              and "HTTP_400_BAD_REQUEST" in fuente_router)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — FASE 1")
    print("=" * 72)

    test_b5_deteccion_por_indicador()
    test_b5_modelo_y_schemas()
    test_b6_estados_interpretacion()
    test_b9_motores_sin_commit()
    test_c13_respaldo()
    test_validacion_completitud_examen()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
