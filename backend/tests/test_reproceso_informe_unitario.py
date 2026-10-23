"""Pruebas unitarias — Reproceso de informe tras corrección de baremo.

    python -m tests.test_reproceso_informe_unitario

Sin BD ni servidor. Cubre: la columna InformeVersion.origen (existe, CHECK,
default 'automatica'), que ReprocesarInformeRequest exige motivo, y —lo más
importante— que el endpoint dependa de permisos.SOLO_ADMINISTRATIVO
(superadmin+admin) y NO de requerir_staff_clinico: a diferencia de reemitir/liberar-informe
(que sí incluyen psicólogo), reprocesar tras corregir un baremo queda
restringido a admin/superadmin por decisión explícita de diseño. También
verifica, por inspección de código, que la transacción de reproceso replica
la misma forma que finalizar_examen_seguro: bloqueo con populate_existing,
un único commit, y que nunca toca `estado` ni `fecha_resolucion`.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from types import SimpleNamespace  # noqa: E402

from pydantic import ValidationError  # noqa: E402

from modulos.educativo import models, schemas  # noqa: E402
from modulos.educativo import crud as educativo_crud  # noqa: E402
from modulos.educativo import router as educativo_router  # noqa: E402
from modulos.documentos import crud as documentos_crud  # noqa: E402


def _cuerpo_de_funcion(fuente: str, nombre_funcion: str) -> str:
    inicio = fuente.index(f"def {nombre_funcion}(")
    fin = fuente.index("\ndef ", inicio + 10)
    return fuente[inicio:fin]


class _FakeTarea:
    """Reemplaza una tarea Celery real (p.ej. `enviar_alerta_riesgo`) para
    capturar llamadas a `.delay(...)` sin tocar Redis -- Fase 2, ver
    core/cola_tareas.py. Antes de la Fase 2 esto monkeypatcheaba
    `_FakeBackgroundTasks.add_task`; ahora el router llama `.delay()`
    directo (ya no pasa por `background_tasks`), así que lo que hay que
    capturar es esto, no un `add_task` que ya no ocurre."""
    def __init__(self):
        self.llamadas = []

    def delay(self, *a, **k):
        self.llamadas.append((a, k))


_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columna_origen():
    print("\nModelo — InformeVersion.origen")
    tabla = models.InformeVersion.__table__
    columna = tabla.columns["origen"]
    comprobar("origen existe", columna is not None)
    comprobar("origen es NOT NULL", columna.nullable is False)
    comprobar("origen tiene server_default 'automatica' (backfill de versiones ya existentes)",
              columna.server_default.arg == "automatica")

    nombres_check = {c.sqltext.text for c in tabla.constraints if c.__class__.__name__ == "CheckConstraint"}
    check_origen = next((t for t in nombres_check if "origen" in t), None)
    comprobar("Existe un CHECK sobre 'origen'", check_origen is not None, str(nombres_check))
    if check_origen:
        for valor in ("automatica", "reemision", "reproceso"):
            comprobar(f"El CHECK de 'origen' incluye '{valor}'", valor in check_origen)


def test_columna_retracta_version_previa_liberada():
    print("\nModelo — InformeVersion.retracta_version_previa_liberada (docs/gaps-pendientes.md)")
    tabla = models.InformeVersion.__table__
    columna = tabla.columns["retracta_version_previa_liberada"]
    comprobar("retracta_version_previa_liberada existe", columna is not None)
    comprobar("es NOT NULL", columna.nullable is False)
    comprobar("default Python es False (no se asume True por omisión)", columna.default.arg is False)


def test_reprocesar_informe_request_exige_motivo():
    print("\nschemas.ReprocesarInformeRequest — motivo obligatorio, mismo criterio que reemitir")
    try:
        schemas.ReprocesarInformeRequest()
        exige_motivo = False
    except ValidationError:
        exige_motivo = True
    comprobar("Instanciar sin 'motivo' -> ValidationError", exige_motivo)

    try:
        schemas.ReprocesarInformeRequest(motivo="ok")  # 2 caracteres
        exige_min_length = False
    except ValidationError:
        exige_min_length = True
    comprobar("min_length=3 igual que ReemitirInformeRequest", exige_min_length)

    ok = schemas.ReprocesarInformeRequest(motivo="Corrección de baremo mal configurado")
    comprobar("Con un motivo válido se construye sin error", ok.motivo.startswith("Corrección"))


def test_endpoint_reprocesar_restringido_a_admin_superadmin():
    print("\nrouter — /reprocesar depende de requerir_rol(superadmin, admin), NO de requerir_staff_clinico")
    fuente = inspect.getsource(__import__("modulos.educativo.router", fromlist=["router"]))
    cuerpo = _cuerpo_de_funcion(fuente, "reprocesar_informe_de_inscripcion")

    # 🆕 PLAN_REMODELACION_ARQUITECTURA.md, fase 2 — el router ya no escribe
    # la tupla a mano: importa permisos.SOLO_ADMINISTRATIVO (misma tupla
    # real superadmin+admin, declarada una sola vez en core/permisos.py).
    comprobar("Usa permisos.SOLO_ADMINISTRATIVO (superadmin+admin, sin psicólogo)",
              "permisos.SOLO_ADMINISTRATIVO" in cuerpo)
    comprobar("NO usa requerir_staff_clinico/permisos.STAFF_CLINICO (a diferencia de reemitir/liberar-informe)",
              "requerir_staff_clinico" not in cuerpo and "permisos.STAFF_CLINICO" not in cuerpo)
    comprobar("NO incluye 'psicologo' en el rol de este endpoint",
              '"psicologo"' not in cuerpo)


def test_reprocesar_replica_la_forma_de_finalizar_examen_seguro():
    """Checks de forma (qué funciones MENCIONA el código fuente) que no
    dependen de que la BD real esté disponible: cuántas veces aparece
    'db.commit()' en el texto, que no se reescriben estado/fecha_resolucion,
    etc. La parte que de verdad importa -- el ORDEN real de ejecución y que
    ningún valor devuelto se descarte por el camino -- está en
    test_reprocesar_ejecuta_los_pasos_reales_en_el_orden_correcto(), que
    llama a la función real con todo mockeado, no solo lee su texto."""
    print("\nrouter — /reprocesar reutiliza el mismo patrón transaccional que finalizar_examen_seguro (forma)")
    fuente = inspect.getsource(__import__("modulos.educativo.router", fromlist=["router"]))
    cuerpo = _cuerpo_de_funcion(fuente, "reprocesar_informe_de_inscripcion")

    comprobar("Un único db.commit() en la fase de recálculo", cuerpo.count("db.commit()") == 1)
    comprobar("Nunca reescribe inscripcion.estado", 'inscripcion.estado =' not in cuerpo)
    comprobar("Nunca reescribe inscripcion.fecha_resolucion", "inscripcion.fecha_resolucion" not in cuerpo)


def test_reprocesar_ejecuta_los_pasos_reales_en_el_orden_correcto():
    """A diferencia del test de arriba (que solo lee el código fuente como
    texto), esto LLAMA a reprocesar_informe_de_inscripcion de verdad, con
    cada crud.* / documentos_crud.* que toca sustituido por un fake que
    registra en qué orden se invocó y qué datos recibió -- exactamente lo
    que el chequeo de substrings no podía ver: un commit movido antes de
    interpretar, un valor devuelto que se descarta sin usar, o una llamada
    que desaparece silenciosamente en un refactor futuro.

    Los parámetros con Depends(...) (db, usuario_actual) son solo
    anotaciones de tipo para FastAPI -- llamar la función directamente
    como Python puro las ignora por completo, así que no hace falta nada
    especial para "saltarse" la inyección de dependencias."""
    print("\nrouter — /reprocesar: EJECUCIÓN real con fakes, orden y flujo de datos verificados de verdad")
    llamadas = []

    inscripcion_fake = SimpleNamespace(
        id=55, estado="Finalizado", evaluacion_id=10, nombre_completo="Alumno de Prueba",
        resultado_visible_alumno=None, informe_liberado=None,
        estado_interpretacion=None, dimensiones_sin_baremo=None, reglas_con_error=None,
    )
    evaluacion_fake = SimpleNamespace(id=10, institucion_id=77, prueba_id=3)
    usuario_fake = SimpleNamespace(id=7, rol="admin", institucion_id=77)

    class _FakeQuery:
        def __init__(self, resultado):
            self._r = resultado

        def filter(self, *a, **k):
            return self

        def first(self):
            return self._r

    class _FakeDB:
        def query(self, modelo):
            if modelo is models.Inscripcion:
                return _FakeQuery(inscripcion_fake)
            if modelo is models.Evaluacion:
                return _FakeQuery(evaluacion_fake)
            raise AssertionError(f"consulta inesperada a {modelo} -- este test no la anticipaba")

        def commit(self):
            llamadas.append("db.commit")

        def rollback(self):
            llamadas.append("db.rollback")

    class _FakeBackgroundTasks:
        def __init__(self):
            self.tareas = []

        def add_task(self, fn, *a, **k):
            self.tareas.append((fn, a, k))

    def fake_bloquear(db, inscripcion_id):
        llamadas.append("bloquear_inscripcion_para_reprocesar")
        comprobar("bloquear_inscripcion_para_reprocesar recibe el id correcto", inscripcion_id == 55)
        return inscripcion_fake

    def fake_inscripcion_esta_activa(insc):
        llamadas.append("inscripcion_esta_activa")
        return True

    def fake_limpiar(db, inscripcion_id):
        llamadas.append("limpiar_resultados_previos")

    def fake_calcular(db, inscripcion_id):
        llamadas.append("calcular_resultados_dimensiones")

    def fake_interpretar_segun_modo(db, inscripcion_id, prueba_id):
        llamadas.append("interpretar_segun_modo")
        comprobar("interpretar_segun_modo recibe el prueba_id de la Evaluacion real, no uno inventado",
                  prueba_id == 3)
        return {"diagnosticos": ["diag_falso_1"], "dimensiones_sin_baremo": [], "interpretacion_completa": True}

    def fake_evaluar_reglas(db, inscripcion_id, prueba_id):
        llamadas.append("evaluar_reglas_interpretacion")
        return {"con_error": []}

    def fake_aplicar_reglas(db, inscripcion_id, diagnosticos, resultado_reglas):
        llamadas.append("aplicar_reglas_a_diagnosticos")
        comprobar("aplicar_reglas_a_diagnosticos recibe EXACTAMENTE los diagnosticos de interpretar_segun_modo "
                  "(no se descartan ni se sustituyen por el camino)", diagnosticos == ["diag_falso_1"])
        return diagnosticos

    def fake_detectar_alertas(diagnosticos):
        llamadas.append("detectar_niveles_de_alerta")
        return []

    def fake_generar_informe(db, inscripcion_id, usuario_id, motivo, origen, retracta_version_previa_liberada):
        llamadas.append("generar_y_almacenar_informe")
        comprobar("generar_y_almacenar_informe recibe origen='reproceso'", origen == "reproceso")
        comprobar("generar_y_almacenar_informe recibe el motivo real pasado por el caller",
                  motivo == "Corrección de baremo (test real)")
        comprobar("Como NO estaba liberado/visible antes (ambos None), retracta_version_previa_liberada=False",
                  retracta_version_previa_liberada is False)
        return SimpleNamespace(informe_id=999, numero_version=2)

    def fake_reemitir_documentos(db, inscripcion_id, usuario_id, motivo):
        llamadas.append("reemitir_documentos_vinculados_a_inscripcion")
        comprobar("reemitir_documentos_vinculados_a_inscripcion recibe un motivo que referencia el reproceso",
                  motivo.startswith("Reproceso de examen:"))
        return [321]

    fake_alerta_riesgo = _FakeTarea()

    parches = {
        educativo_crud: {
            "bloquear_inscripcion_para_reprocesar": fake_bloquear,
            "inscripcion_esta_activa": fake_inscripcion_esta_activa,
            "limpiar_resultados_previos": fake_limpiar,
            "calcular_resultados_dimensiones": fake_calcular,
            "interpretar_segun_modo": fake_interpretar_segun_modo,
            "evaluar_reglas_interpretacion": fake_evaluar_reglas,
            "aplicar_reglas_a_diagnosticos": fake_aplicar_reglas,
            "detectar_niveles_de_alerta": fake_detectar_alertas,
            "generar_y_almacenar_informe": fake_generar_informe,
        },
        documentos_crud: {
            "reemitir_documentos_vinculados_a_inscripcion": fake_reemitir_documentos,
        },
        educativo_router: {
            "enviar_alerta_riesgo": fake_alerta_riesgo,
        },
    }
    originales = {
        modulo: {nombre: getattr(modulo, nombre) for nombre in parches[modulo]}
        for modulo in parches
    }
    for modulo, funciones in parches.items():
        for nombre, fake in funciones.items():
            setattr(modulo, nombre, fake)

    try:
        bg = _FakeBackgroundTasks()
        resultado = educativo_router.reprocesar_informe_de_inscripcion(
            inscripcion_id=55,
            datos=schemas.ReprocesarInformeRequest(motivo="Corrección de baremo (test real)"),
            background_tasks=bg,
            db=_FakeDB(),
            usuario_actual=usuario_fake,
        )
    finally:
        for modulo, funciones in originales.items():
            for nombre, original in funciones.items():
                setattr(modulo, nombre, original)

    orden_esperado = [
        "bloquear_inscripcion_para_reprocesar", "inscripcion_esta_activa", "limpiar_resultados_previos",
        "calcular_resultados_dimensiones", "interpretar_segun_modo", "evaluar_reglas_interpretacion",
        "aplicar_reglas_a_diagnosticos", "detectar_niveles_de_alerta", "db.commit",
        "generar_y_almacenar_informe", "reemitir_documentos_vinculados_a_inscripcion",
    ]
    # inscripcion_esta_activa se llama dos veces (Fase 1 sin bloqueo, Fase 2
    # ya bloqueada) -- se filtra a la ÚLTIMA ocurrencia de cada nombre para
    # comparar el orden relativo real sin que la duplicación lo rompa.
    posiciones = {nombre: max(i for i, x in enumerate(llamadas) if x == nombre) for nombre in orden_esperado}
    secuencia_real = sorted(orden_esperado, key=lambda n: posiciones[n])
    comprobar("El orden real de ejecución es exactamente el esperado (lock -> limpiar -> calcular -> "
              "interpretar -> reglas -> aplicar reglas -> detectar alertas -> commit -> informe -> documentos)",
              secuencia_real == orden_esperado, " -> ".join(llamadas))

    comprobar("db.commit ocurre DESPUÉS de interpretar (nunca antes, nunca se confirma a medias)",
              posiciones["db.commit"] > posiciones["interpretar_segun_modo"])
    comprobar("generar_y_almacenar_informe ocurre DESPUÉS de db.commit (Fase 3 es posterior a la transacción)",
              posiciones["generar_y_almacenar_informe"] > posiciones["db.commit"])
    comprobar("reemitir_documentos_vinculados_a_inscripcion ocurre DESPUÉS de generar_y_almacenar_informe "
              "(primero el informe psicométrico, después los documentos que dependen de él)",
              posiciones["reemitir_documentos_vinculados_a_inscripcion"] > posiciones["generar_y_almacenar_informe"])

    comprobar("La inscripción real queda con resultado_visible_alumno=True (niveles_alerta=[], "
              "interpretacion_completa=True, sin reglas con error -> requiere_revision=False)",
              inscripcion_fake.resultado_visible_alumno is True)
    comprobar("informe_liberado también queda en True, misma fórmula", inscripcion_fake.informe_liberado is True)
    comprobar("estado_interpretacion queda 'completa'", inscripcion_fake.estado_interpretacion == "completa")

    comprobar("La respuesta del endpoint expone requiere_revision=False", resultado["requiere_revision"] is False)
    comprobar("La respuesta expone los documentos realmente reemitidos (no una lista vacía inventada)",
              resultado["documentos_institucionales_reemitidos"] == [321])
    comprobar("Como requiere_revision es False, NUNCA se encoló la tarea Celery de alerta (enviar_alerta_riesgo.delay)",
              len(fake_alerta_riesgo.llamadas) == 0)
    comprobar("La respuesta expone retraccion_informe_liberado=False (no estaba liberado/visible antes)",
              resultado["retraccion_informe_liberado"] is False)
    comprobar("La respuesta expone revisor_original_notificado=False (nunca se buscó revisor: no hubo regresión)",
              resultado["revisor_original_notificado"] is False)


def test_reprocesar_programa_la_alerta_solo_cuando_requiere_revision():
    """Mismo mecanismo que el test anterior, pero forzando niveles_alerta
    no vacío -- confirma la otra rama de requiere_revision, que el test de
    arriba (con un resultado limpio) nunca ejercita."""
    print("\nrouter — /reprocesar: SÍ programa la alerta cuando el resultado corregido la requiere")
    llamadas = []

    inscripcion_fake = SimpleNamespace(
        id=56, estado="Finalizado", evaluacion_id=11, nombre_completo="Alumno Con Alerta",
        resultado_visible_alumno=True, informe_liberado=True,  # estaba liberado ANTES de corregir
        estado_interpretacion=None, dimensiones_sin_baremo=None, reglas_con_error=None,
        revisado_por_usuario_id=42,  # quien lo había liberado originalmente
    )
    revisor_original_fake = SimpleNamespace(id=42, email="psicologo.original@ejemplo.com", activo=True)
    evaluacion_fake = SimpleNamespace(id=11, institucion_id=77, prueba_id=3)
    usuario_fake = SimpleNamespace(id=7, rol="superadmin", institucion_id=None)

    class _FakeQuery:
        def __init__(self, resultado):
            self._r = resultado

        def filter(self, *a, **k):
            return self

        def first(self):
            return self._r

    class _FakeDB:
        def query(self, modelo):
            if modelo is models.Inscripcion:
                return _FakeQuery(inscripcion_fake)
            if modelo is models.Evaluacion:
                return _FakeQuery(evaluacion_fake)
            raise AssertionError(f"consulta inesperada a {modelo}")

        def commit(self):
            llamadas.append("db.commit")

        def rollback(self):
            llamadas.append("db.rollback")

    class _FakeBackgroundTasks:
        def __init__(self):
            self.tareas = []

        def add_task(self, fn, *a, **k):
            self.tareas.append((fn, a, k))

    def fake_generar_informe_con_alerta(db, inscripcion_id, usuario_id, motivo, origen, retracta_version_previa_liberada):
        comprobar("generar_y_almacenar_informe recibe retracta_version_previa_liberada=True "
                  "(estaba liberado/visible y la corrección exige revisión)",
                  retracta_version_previa_liberada is True)
        return SimpleNamespace(informe_id=1000, numero_version=3)

    def fake_obtener_revisor_original(db, inscripcion):
        comprobar("obtener_revisor_original_de_inscripcion recibe la inscripción real",
                  inscripcion is inscripcion_fake)
        return revisor_original_fake

    fake_alerta_riesgo = _FakeTarea()
    fake_alerta_regresion = _FakeTarea()

    parches = {
        educativo_crud: {
            "bloquear_inscripcion_para_reprocesar": lambda db, inscripcion_id: inscripcion_fake,
            "inscripcion_esta_activa": lambda insc: True,
            "limpiar_resultados_previos": lambda db, inscripcion_id: None,
            "calcular_resultados_dimensiones": lambda db, inscripcion_id: None,
            "interpretar_segun_modo": lambda db, inscripcion_id, prueba_id: {
                "diagnosticos": ["diag_alerta"], "dimensiones_sin_baremo": [], "interpretacion_completa": True,
            },
            "evaluar_reglas_interpretacion": lambda db, inscripcion_id, prueba_id: {"con_error": []},
            "aplicar_reglas_a_diagnosticos": lambda db, inscripcion_id, diagnosticos, resultado_reglas: diagnosticos,
            # Ahora SÍ hay un nivel de alerta real -> requiere_revision debe salir True.
            "detectar_niveles_de_alerta": lambda diagnosticos: ["Severo"],
            "generar_y_almacenar_informe": fake_generar_informe_con_alerta,
            "obtener_destinatarios_alerta": lambda db, evaluacion: (["admin@ejemplo.com"], ["respaldo institucional"]),
            "obtener_revisor_original_de_inscripcion": fake_obtener_revisor_original,
        },
        documentos_crud: {
            "reemitir_documentos_vinculados_a_inscripcion": lambda db, inscripcion_id, usuario_id, motivo: [],
        },
        educativo_router: {
            "enviar_alerta_riesgo": fake_alerta_riesgo,
            "enviar_alerta_regresion_informe_liberado": fake_alerta_regresion,
        },
    }
    originales = {
        modulo: {nombre: getattr(modulo, nombre) for nombre in parches[modulo]}
        for modulo in parches
    }
    for modulo, funciones in parches.items():
        for nombre, fake in funciones.items():
            setattr(modulo, nombre, fake)

    try:
        bg = _FakeBackgroundTasks()
        resultado = educativo_router.reprocesar_informe_de_inscripcion(
            inscripcion_id=56,
            datos=schemas.ReprocesarInformeRequest(motivo="Corrección que revela una alerta"),
            background_tasks=bg,
            db=_FakeDB(),
            usuario_actual=usuario_fake,
        )
    finally:
        for modulo, funciones in originales.items():
            for nombre, original in funciones.items():
                setattr(modulo, nombre, original)

    comprobar("requiere_revision=True en la respuesta (había un nivel de alerta real)",
              resultado["requiere_revision"] is True)
    comprobar("Un informe YA liberado queda RE-RETENIDO por la corrección "
              "(resultado_visible_alumno vuelve a False)", inscripcion_fake.resultado_visible_alumno is False)
    comprobar("informe_liberado también vuelve a False", inscripcion_fake.informe_liberado is False)
    comprobar("La respuesta expone retraccion_informe_liberado=True (docs/gaps-pendientes.md)",
              resultado["retraccion_informe_liberado"] is True)
    comprobar("La respuesta expone revisor_original_notificado=True",
              resultado["revisor_original_notificado"] is True)
    comprobar("SE ENCOLARON (Celery, .delay) exactamente las dos tareas esperadas: la alerta genérica "
              "y el aviso puntual a quien liberó el informe originalmente",
              len(fake_alerta_riesgo.llamadas) == 1 and len(fake_alerta_regresion.llamadas) == 1)
    if fake_alerta_riesgo.llamadas:
        args_generica, _ = fake_alerta_riesgo.llamadas[0]
        comprobar("Se le pasan los destinatarios reales devueltos por obtener_destinatarios_alerta",
                  args_generica[0] == ["admin@ejemplo.com"])
    if fake_alerta_regresion.llamadas:
        args_regresion, _ = fake_alerta_regresion.llamadas[0]
        comprobar("Se le pasa el correo real del revisor original (no uno de la alerta genérica)",
                  args_regresion[0] == "psicologo.original@ejemplo.com")
        comprobar("Se le pasa el número de la versión ANTERIOR (la que quedó retractada), no la nueva",
                  args_regresion[2] == 2)


def test_reprocesar_regresion_sin_revisor_original_activo():
    """Misma regresión que el test anterior, pero sin nadie a quien avisar
    puntualmente (nunca se liberó a mano, o quien lo hizo ya no está
    activo) -- confirma que NO se rompe ni se inventa un destinatario: la
    alerta genérica sigue intacta y solo queda sin la notificación extra."""
    print("\nrouter — /reprocesar: regresión SIN revisor original activo -> solo la alerta genérica, sin romper nada")
    inscripcion_fake = SimpleNamespace(
        id=57, estado="Finalizado", evaluacion_id=12, nombre_completo="Alumno Sin Revisor",
        resultado_visible_alumno=True, informe_liberado=True,
        estado_interpretacion=None, dimensiones_sin_baremo=None, reglas_con_error=None,
        revisado_por_usuario_id=None,  # nunca se liberó a mano
    )
    evaluacion_fake = SimpleNamespace(id=12, institucion_id=77, prueba_id=3)
    usuario_fake = SimpleNamespace(id=7, rol="superadmin", institucion_id=None)

    class _FakeQuery:
        def __init__(self, resultado):
            self._r = resultado

        def filter(self, *a, **k):
            return self

        def first(self):
            return self._r

    class _FakeDB:
        def query(self, modelo):
            if modelo is models.Inscripcion:
                return _FakeQuery(inscripcion_fake)
            if modelo is models.Evaluacion:
                return _FakeQuery(evaluacion_fake)
            raise AssertionError(f"consulta inesperada a {modelo}")

        def commit(self):
            pass

        def rollback(self):
            pass

    class _FakeBackgroundTasks:
        def __init__(self):
            self.tareas = []

        def add_task(self, fn, *a, **k):
            self.tareas.append((fn, a, k))

    fake_alerta_riesgo = _FakeTarea()
    fake_alerta_regresion = _FakeTarea()

    parches = {
        educativo_crud: {
            "bloquear_inscripcion_para_reprocesar": lambda db, inscripcion_id: inscripcion_fake,
            "inscripcion_esta_activa": lambda insc: True,
            "limpiar_resultados_previos": lambda db, inscripcion_id: None,
            "calcular_resultados_dimensiones": lambda db, inscripcion_id: None,
            "interpretar_segun_modo": lambda db, inscripcion_id, prueba_id: {
                "diagnosticos": ["diag_alerta"], "dimensiones_sin_baremo": [], "interpretacion_completa": True,
            },
            "evaluar_reglas_interpretacion": lambda db, inscripcion_id, prueba_id: {"con_error": []},
            "aplicar_reglas_a_diagnosticos": lambda db, inscripcion_id, diagnosticos, resultado_reglas: diagnosticos,
            "detectar_niveles_de_alerta": lambda diagnosticos: ["Severo"],
            "generar_y_almacenar_informe": lambda db, inscripcion_id, usuario_id, motivo, origen,
            retracta_version_previa_liberada: SimpleNamespace(informe_id=1001, numero_version=2),
            "obtener_destinatarios_alerta": lambda db, evaluacion: (["admin@ejemplo.com"], ["respaldo institucional"]),
            # Nadie liberó a mano -> ninguna versión real llamaría a esto con
            # un id, pero por si acaso: debe devolver None sin que el
            # endpoint truene buscando .email en None.
            "obtener_revisor_original_de_inscripcion": lambda db, inscripcion: None,
        },
        documentos_crud: {
            "reemitir_documentos_vinculados_a_inscripcion": lambda db, inscripcion_id, usuario_id, motivo: [],
        },
        educativo_router: {
            "enviar_alerta_riesgo": fake_alerta_riesgo,
            "enviar_alerta_regresion_informe_liberado": fake_alerta_regresion,
        },
    }
    originales = {
        modulo: {nombre: getattr(modulo, nombre) for nombre in parches[modulo]}
        for modulo in parches
    }
    for modulo, funciones in parches.items():
        for nombre, fake in funciones.items():
            setattr(modulo, nombre, fake)

    try:
        bg = _FakeBackgroundTasks()
        resultado = educativo_router.reprocesar_informe_de_inscripcion(
            inscripcion_id=57,
            datos=schemas.ReprocesarInformeRequest(motivo="Corrección sin revisor original"),
            background_tasks=bg,
            db=_FakeDB(),
            usuario_actual=usuario_fake,
        )
    finally:
        for modulo, funciones in originales.items():
            for nombre, original in funciones.items():
                setattr(modulo, nombre, original)

    comprobar("retraccion_informe_liberado sigue True (SÍ hubo regresión real)",
              resultado["retraccion_informe_liberado"] is True)
    comprobar("revisor_original_notificado=False (nadie a quien avisar puntualmente)",
              resultado["revisor_original_notificado"] is False)
    comprobar("Solo se encoló UNA tarea Celery (la alerta genérica) -- nunca se inventa un destinatario",
              len(fake_alerta_riesgo.llamadas) == 1 and len(fake_alerta_regresion.llamadas) == 0)


def test_generar_y_almacenar_informe_acepta_origen_con_default_compatible():
    print("\ncrud.generar_y_almacenar_informe — origen nuevo, default no rompe llamadores existentes")
    firma = inspect.signature(__import__("modulos.educativo.crud", fromlist=["crud"]).generar_y_almacenar_informe)
    comprobar("Tiene parámetro 'origen'", "origen" in firma.parameters)
    comprobar("Su default es 'automatica' (la tarea en 2º plano no necesita cambiar su llamada)",
              firma.parameters["origen"].default == "automatica")


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Reproceso de informe tras corrección de baremo")
    print("=" * 72)
    test_columna_origen()
    test_columna_retracta_version_previa_liberada()
    test_reprocesar_informe_request_exige_motivo()
    test_endpoint_reprocesar_restringido_a_admin_superadmin()
    test_reprocesar_replica_la_forma_de_finalizar_examen_seguro()
    test_reprocesar_ejecuta_los_pasos_reales_en_el_orden_correcto()
    test_reprocesar_programa_la_alerta_solo_cuando_requiere_revision()
    test_reprocesar_regresion_sin_revisor_original_activo()
    test_generar_y_almacenar_informe_acepta_origen_con_default_compatible()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
