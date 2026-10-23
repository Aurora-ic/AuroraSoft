"""Pruebas unitarias — Enganche automático motor de pruebas -> motor de
documentos (PlantillaDocumento.generar_automaticamente_al_finalizar_examen,
crud.generar_documentos_automaticos_por_examen). No necesitan la base de
datos ni el servidor.

    python -m tests.test_documentos_enganche_automatico_unitario

Qué SÍ se ejecuta de verdad (duck-typed, sin BD real):
  - _resolver_actor_automatico_para_institucion — su cadena de respaldo
    (creador de campaña -> admin -> psicólogo -> None) es una secuencia
    corta y determinista de consultas, perfectamente fakeable.
  - Las columnas/esquemas nuevos (PlantillaDocumento.generar_
    automaticamente_al_finalizar_examen, su default, su presencia en
    PlantillaDocumentoUpdate).

Qué se verifica por inspección de código (mismo criterio ya usado en
test_reproceso_informe_unitario.py para funciones de orquestación que
encadenan varias llamadas a otras funciones crud con sus propias consultas
reales — duck-typearlas por completo exigiría reimplementar media base de
datos falsa): generar_documentos_automaticos_por_examen,
_generar_documento_automatico_de_plantilla, reemitir_documentos_vinculados_
a_inscripcion, y los dos wrappers (BackgroundTasks del enganche automático,
y el llamado síncrono desde /reprocesar).

El comportamiento real end-to-end (creación + vínculo + versión + que el
documento retiene correctamente un resultado no liberado gracias al fix de
_resolver_resultados_prueba + que /reprocesar reemite el documento ya
generado con el contenido corregido) está verificado de verdad contra una
base de datos Postgres real y un servidor uvicorn real, no solo simulado:
ver tests/verificar_documentos_enganche_automatico_e2e.py (prefijo
ZZDOCENG, 23/23 comprobaciones).
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from types import SimpleNamespace  # noqa: E402

from modulos.documentos import schemas, models as docs_models, crud as docs_crud  # noqa: E402
from modulos.auth import models as auth_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


# ==========================================
# Columna nueva: default seguro, cero cambio de comportamiento
# ==========================================
def test_columna_existe_con_default_false():
    print("\nPlantillaDocumento.generar_automaticamente_al_finalizar_examen — columna nueva")
    columna = docs_models.PlantillaDocumento.__table__.columns["generar_automaticamente_al_finalizar_examen"]
    comprobar("NOT NULL", columna.nullable is False)
    comprobar("server_default es 'false' (texto literal del DDL)", str(columna.server_default.arg) == "false")


def test_schemas_exponen_el_campo_con_default_false():
    print("\nschemas — el campo nuevo expone default False y es opcional en el PATCH")
    base = schemas.PlantillaDocumentoCreate(
        institucion_id=1, tipo_documento_id=1, nombre="Informe individual",
    )
    comprobar("PlantillaDocumentoCreate: default False sin pasar el campo", base.generar_automaticamente_al_finalizar_examen is False)

    update_vacio = schemas.PlantillaDocumentoUpdate()
    comprobar("PlantillaDocumentoUpdate: ausente por defecto (None, no False) — PATCH parcial real",
              update_vacio.generar_automaticamente_al_finalizar_examen is None)

    update_activa = schemas.PlantillaDocumentoUpdate(generar_automaticamente_al_finalizar_examen=True)
    comprobar("PlantillaDocumentoUpdate: acepta activarlo explícitamente",
              update_activa.generar_automaticamente_al_finalizar_examen is True)


def test_clonar_plantilla_no_copia_el_enganche():
    print("\ncrud.clonar_plantilla_documento — el enganche automático NUNCA se copia a la institución destino")
    fuente = inspect.getsource(docs_crud.clonar_plantilla_documento)
    comprobar(
        "El constructor de la plantilla clonada no asigna generar_automaticamente_al_finalizar_examen "
        "(queda en el default False de la columna, igual que 'activa' por defecto)",
        "generar_automaticamente_al_finalizar_examen=" not in fuente,
    )


# ==========================================
# _resolver_actor_automatico_para_institucion — ejecutado de verdad
# ==========================================
class _FakeQuerySecuencial:
    """A diferencia del _FakeQuery de otros tests (que ignora filter() y
    responde siempre lo mismo), esta función hace VARIAS consultas al mismo
    modelo (Usuario) con filtros distintos en un orden fijo y conocido —
    así que el fake necesita devolver una respuesta DISTINTA por cada
    llamada, en la secuencia real: 1) creador por id, 2) primer admin
    activo, 3) primer psicólogo activo."""
    def __init__(self, respuestas_en_orden):
        self._respuestas = list(respuestas_en_orden)

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        if not self._respuestas:
            return None
        return self._respuestas.pop(0)


class _FakeDBSecuencial:
    def __init__(self, respuestas_en_orden):
        self._query = _FakeQuerySecuencial(respuestas_en_orden)

    def query(self, *modelos):
        assert modelos[0] is auth_models.Usuario
        return self._query


def _usuario(id_, activo=True):
    return SimpleNamespace(id=id_, activo=activo)


def test_actor_automatico_usa_el_creador_de_la_campana_si_esta_activo():
    print("\n_resolver_actor_automatico_para_institucion — creador de la campaña activo, se usa directo")
    evaluacion = SimpleNamespace(creador_id=42)
    db = _FakeDBSecuencial([_usuario(42)])  # la consulta del creador ya filtra activo=True
    actor = docs_crud._resolver_actor_automatico_para_institucion(db, institucion_id=1, evaluacion=evaluacion)
    comprobar("Devuelve el id del creador", actor == 42)


def test_actor_automatico_cae_a_admin_si_el_creador_esta_inactivo_o_no_existe():
    print("\n_resolver_actor_automatico_para_institucion — sin creador activo, cae al primer admin activo")
    evaluacion = SimpleNamespace(creador_id=42)
    # 1ª consulta (creador, ya filtrada por activo=True): None. 2ª (admin): id 7.
    db = _FakeDBSecuencial([None, _usuario(7)])
    actor = docs_crud._resolver_actor_automatico_para_institucion(db, institucion_id=1, evaluacion=evaluacion)
    comprobar("Devuelve el id del admin de respaldo", actor == 7)


def test_actor_automatico_cae_a_psicologo_si_tampoco_hay_admin():
    print("\n_resolver_actor_automatico_para_institucion — sin creador ni admin, cae al primer psicólogo activo")
    evaluacion = SimpleNamespace(creador_id=None)
    # Sin creador_id no se consulta el creador en absoluto -> 1ª respuesta es admin (None), 2ª psicólogo (id 9).
    db = _FakeDBSecuencial([None, _usuario(9)])
    actor = docs_crud._resolver_actor_automatico_para_institucion(db, institucion_id=1, evaluacion=evaluacion)
    comprobar("Devuelve el id del psicólogo de respaldo", actor == 9)


def test_actor_automatico_none_si_la_institucion_no_tiene_a_nadie():
    print("\n_resolver_actor_automatico_para_institucion — institución sin ningún usuario activo elegible -> None")
    evaluacion = SimpleNamespace(creador_id=None)
    db = _FakeDBSecuencial([None, None])
    actor = docs_crud._resolver_actor_automatico_para_institucion(db, institucion_id=1, evaluacion=evaluacion)
    comprobar("Devuelve None (el llamador debe omitir, nunca crear con FK inventada)", actor is None)


def _cuerpo_sin_docstring(funcion):
    """Fuente de una función SIN su docstring — para que un comentario
    explicativo (que puede legítimamente nombrar algo de contraste, como
    'colegio') no genere un falso negativo al buscar qué hace el CÓDIGO."""
    import ast
    fuente = inspect.getsource(funcion)
    arbol = ast.parse(fuente)
    funcdef = arbol.body[0]
    cuerpo = funcdef.body
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(getattr(cuerpo[0], "value", None), ast.Constant):
        cuerpo = cuerpo[1:]
    return "\n".join(ast.unparse(nodo) for nodo in cuerpo)


def test_actor_automatico_nunca_considera_el_rol_colegio():
    print("\n_resolver_actor_automatico_para_institucion — 'colegio' NUNCA es una opción de respaldo")
    cuerpo = _cuerpo_sin_docstring(docs_crud._resolver_actor_automatico_para_institucion)
    comprobar(
        "El CÓDIGO (sin docstring) no menciona el rol 'colegio' (a diferencia de obtener_destinatarios_alerta, "
        "que sí lo incluye como destinatario de notificación — aquí se necesita permiso real de ESCRIBIR documentos)",
        "colegio" not in cuerpo,
    )
    comprobar(
        "Solo considera admin y psicologo como respaldo",
        "for rol in" in cuerpo and "admin" in cuerpo and "psicologo" in cuerpo,
    )


# ==========================================
# generar_documentos_automaticos_por_examen / _generar_documento_automatico_
# de_plantilla — orquestación con varias llamadas a otras funciones crud
# reales; verificado por inspección de código (ver docstring del archivo).
# ==========================================
def test_omite_inscripciones_anonimas():
    print("\ngenerar_documentos_automaticos_por_examen — sin persona_id, se omite sin tocar nada más")
    fuente = inspect.getsource(docs_crud.generar_documentos_automaticos_por_examen)
    comprobar("Revisa inscripcion.persona_id antes de seguir", "not inscripcion.persona_id" in fuente)


def test_filtra_plantillas_activas_y_marcadas():
    print("\ngenerar_documentos_automaticos_por_examen — solo plantillas activa=True y generar_automaticamente...=True")
    fuente = inspect.getsource(docs_crud.generar_documentos_automaticos_por_examen)
    comprobar("Filtra por PlantillaDocumento.activa == True", "models.PlantillaDocumento.activa == True" in fuente)
    comprobar(
        "Filtra por PlantillaDocumento.generar_automaticamente_al_finalizar_examen == True",
        "models.PlantillaDocumento.generar_automaticamente_al_finalizar_examen == True" in fuente,
    )


def test_una_plantilla_fallida_no_detiene_a_las_demas():
    print("\ngenerar_documentos_automaticos_por_examen — cada plantilla corre en su propio try/except con rollback")
    fuente = inspect.getsource(docs_crud.generar_documentos_automaticos_por_examen)
    comprobar("Itera las plantillas en un for", "for plantilla in plantillas:" in fuente)
    comprobar("Atrapa cualquier excepción por plantilla (no deja que una tumbe a las demás)", "except Exception:" in fuente)
    comprobar("Hace rollback antes de seguir con la siguiente plantilla", "db.rollback()" in fuente)


def test_exige_exactamente_una_seccion_resultados_prueba():
    print("\n_generar_documento_automatico_de_plantilla — 0 ó 2+ secciones 'resultados_prueba' se omite")
    fuente = inspect.getsource(docs_crud._generar_documento_automatico_de_plantilla)
    comprobar("Filtra PlantillaSeccion por tipo_seccion == 'resultados_prueba'",
              'models.PlantillaSeccion.tipo_seccion == "resultados_prueba"' in fuente)
    comprobar("Exige longitud exactamente 1 (nunca adivina entre varias)", "len(secciones_resultado) != 1" in fuente)


def test_revalida_consentimiento_antes_de_crear_el_borrador():
    print("\n_generar_documento_automatico_de_plantilla — gate de consentimiento revalidado ANTES de crear nada")
    fuente = inspect.getsource(docs_crud._generar_documento_automatico_de_plantilla)
    comprobar("Lee TipoDocumento.requiere_consentimiento_individual", "tipo.requiere_consentimiento_individual" in fuente)
    comprobar("Llama a superadmin_crud.tiene_consentimiento_vigente", "superadmin_crud.tiene_consentimiento_vigente" in fuente)
    # El chequeo debe estar ANTES de la llamada a crear_documento_institucional en el texto fuente.
    pos_gate = fuente.find("tiene_consentimiento_vigente")
    pos_crear = fuente.find("crear_documento_institucional(")
    comprobar("El gate de consentimiento aparece ANTES de crear el documento (nunca deja un borrador huérfano)",
              -1 < pos_gate < pos_crear)


def test_encadena_crear_vincular_generar_en_ese_orden():
    print("\n_generar_documento_automatico_de_plantilla — crea, vincula el resultado y genera la versión, en ese orden")
    fuente = inspect.getsource(docs_crud._generar_documento_automatico_de_plantilla)
    pos_crear = fuente.find("crear_documento_institucional(")
    pos_vincular = fuente.find("vincular_resultado_prueba(")
    pos_generar = fuente.find("generar_version_documento(")
    comprobar("Las tres llamadas existen", -1 not in (pos_crear, pos_vincular, pos_generar))
    comprobar("Orden: crear -> vincular -> generar_version", pos_crear < pos_vincular < pos_generar)
    comprobar("alcance='personas_especificas' (nunca estructura_academica/institucion para un solo examen)",
              'alcance="personas_especificas"' in fuente)


def test_wrapper_de_background_tasks_abre_su_propia_sesion_y_nunca_revienta():
    print("\ntarea_generar_documentos_automaticos_en_segundo_plano — mismo patrón que el del informe psicométrico")
    fuente = inspect.getsource(docs_crud.tarea_generar_documentos_automaticos_en_segundo_plano)
    comprobar("Abre su propia SessionLocal()", "SessionLocal()" in fuente)
    comprobar("Atrapa cualquier excepción (nunca debe tumbar el worker de Celery)", "except Exception as exc:" in fuente)
    comprobar("Cierra la sesión en finally", "finally:" in fuente and "db.close()" in fuente)
    comprobar("Es una tarea Celery real, bind=True (para poder reintentar con self.retry)",
              "@celery_app.task(bind=True" in fuente and "self.retry(exc=exc)" in fuente)


def test_router_educativo_dispara_el_enganche_junto_al_informe_automatico():
    print("\nmodulos/educativo/router.py — finalizar_examen_seguro programa el enganche en Celery")
    import modulos.educativo.router as educativo_router
    fuente = inspect.getsource(educativo_router.finalizar_examen_seguro)
    comprobar(
        "Programa tarea_generar_documentos_automaticos_en_segundo_plano vía _encolar_sin_bloquear "
        "(Celery .delay(), Fase 2, sin dejar que un broker caído tumbe la respuesta)",
        "_encolar_sin_bloquear(documentos_crud.tarea_generar_documentos_automaticos_en_segundo_plano" in fuente,
    )
    comprobar(
        "Sigue programando también el informe psicométrico automático (no lo reemplaza)",
        "_encolar_sin_bloquear(crud.tarea_generar_informe_en_segundo_plano" in fuente,
    )


def test_encolar_sin_bloquear_nunca_propaga_un_broker_caido():
    """Confirmado probando contra Redis real: `.delay()` contra un broker
    inalcanzable puede lanzar o incluso colgarse (sin el timeout corto que
    core/cola_tareas.py ya configura). `_encolar_sin_bloquear` es la única
    barrera entre eso y una respuesta HTTP 500 para un alumno/psicólogo que
    no tiene nada que ver con la infraestructura de la cola -- esto LLAMA
    a la función real con una tarea falsa que revienta, para confirmar que
    de verdad nunca deja escapar la excepción."""
    print("\n_encolar_sin_bloquear — una tarea que revienta al encolar nunca rompe al caller")
    import modulos.educativo.router as educativo_router

    class _TareaQueRevienta:
        name = "tarea_de_prueba_que_revienta"

        def delay(self, *a, **k):
            raise ConnectionError("Redis inalcanzable (simulado)")

    try:
        educativo_router._encolar_sin_bloquear(_TareaQueRevienta(), 123)
        comprobar("No propaga la excepción del broker caído", True)
    except Exception as exc:
        comprobar("No propaga la excepción del broker caído", False, f"se propagó: {exc!r}")


def test_reemitir_vinculados_solo_toca_documentos_con_version_ya_generada():
    print("\nreemitir_documentos_vinculados_a_inscripcion — salta los que siguen en borrador (version_actual NULL)")
    fuente = inspect.getsource(docs_crud.reemitir_documentos_vinculados_a_inscripcion)
    comprobar("Consulta DocumentoInstitucionalResultadoPrueba filtrando por inscripcion_id",
              "models.DocumentoInstitucionalResultadoPrueba.inscripcion_id == inscripcion_id" in fuente)
    comprobar("Usa distinct() (un documento puede tener varias secciones resultados_prueba de la misma inscripción)",
              ".distinct()" in fuente)
    comprobar("Salta un documento sin version_actual (sigue en borrador, nunca se tocó)",
              "documento.version_actual is None" in fuente)
    comprobar("Reutiliza generar_version_documento (el mismo mecanismo que una reemisión manual)",
              "generar_version_documento(db, documento_id=documento_id" in fuente)


def test_reemitir_vinculados_nunca_revienta_un_documento_a_la_vez():
    print("\nreemitir_documentos_vinculados_a_inscripcion — un documento que falla no detiene a los demás ni revierte el reproceso")
    fuente = inspect.getsource(docs_crud.reemitir_documentos_vinculados_a_inscripcion)
    comprobar("Itera los documentos en un for", "for documento_id in documento_ids:" in fuente)
    comprobar("Atrapa cualquier excepción por documento", "except Exception:" in fuente)
    comprobar("Hace rollback antes de seguir con el siguiente", "db.rollback()" in fuente)


def test_router_educativo_reprocesar_llama_al_reemitidor_de_documentos():
    print("\nmodulos/educativo/router.py — reprocesar_informe_de_inscripcion reemite los documentos vinculados (cierra el hueco)")
    import modulos.educativo.router as educativo_router
    fuente = inspect.getsource(educativo_router.reprocesar_informe_de_inscripcion)
    comprobar(
        "Llama a documentos_crud.reemitir_documentos_vinculados_a_inscripcion",
        "documentos_crud.reemitir_documentos_vinculados_a_inscripcion" in fuente,
    )
    comprobar(
        "Lo hace de forma SÍNCRONA (no via background_tasks.add_task) -- misma sesión que ya regenera "
        "el informe psicométrico en este mismo endpoint",
        "background_tasks.add_task(documentos_crud" not in fuente,
    )
    comprobar(
        "El motivo que le pasa deja claro que viene de un reproceso (distinguible de un /reemitir manual "
        "del documento en su propio historial de versiones)",
        "Reproceso de examen:" in fuente,
    )
    comprobar(
        "La llamada ocurre DESPUÉS de generar_y_almacenar_informe (mismo orden: primero el informe "
        "psicométrico, después los documentos institucionales que dependen de él)",
        fuente.find("generar_y_almacenar_informe") < fuente.find("reemitir_documentos_vinculados_a_inscripcion"),
    )
    comprobar(
        "La respuesta del endpoint expone qué documentos se reemitieron",
        '"documentos_institucionales_reemitidos": documentos_reemitidos' in fuente,
    )


def main():
    test_columna_existe_con_default_false()
    test_schemas_exponen_el_campo_con_default_false()
    test_clonar_plantilla_no_copia_el_enganche()
    test_actor_automatico_usa_el_creador_de_la_campana_si_esta_activo()
    test_actor_automatico_cae_a_admin_si_el_creador_esta_inactivo_o_no_existe()
    test_actor_automatico_cae_a_psicologo_si_tampoco_hay_admin()
    test_actor_automatico_none_si_la_institucion_no_tiene_a_nadie()
    test_actor_automatico_nunca_considera_el_rol_colegio()
    test_omite_inscripciones_anonimas()
    test_filtra_plantillas_activas_y_marcadas()
    test_una_plantilla_fallida_no_detiene_a_las_demas()
    test_exige_exactamente_una_seccion_resultados_prueba()
    test_revalida_consentimiento_antes_de_crear_el_borrador()
    test_encadena_crear_vincular_generar_en_ese_orden()
    test_wrapper_de_background_tasks_abre_su_propia_sesion_y_nunca_revienta()
    test_router_educativo_dispara_el_enganche_junto_al_informe_automatico()
    test_encolar_sin_bloquear_nunca_propaga_un_broker_caido()
    test_reemitir_vinculados_solo_toca_documentos_con_version_ya_generada()
    test_reemitir_vinculados_nunca_revienta_un_documento_a_la_vez()
    test_router_educativo_reprocesar_llama_al_reemitidor_de_documentos()

    total = len(_resultados)
    pasaron = sum(1 for _, ok, _ in _resultados if ok)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {pasaron}/{total} comprobaciones superadas")
    print("=" * 72)
    if pasaron != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
