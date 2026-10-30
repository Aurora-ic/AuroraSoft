import io
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from core.database import get_db
from . import models, schemas, crud  # <-- ¡Aquí agregamos models!
from core.deps import (
    ip_del_cliente,
    obtener_usuario_actual,
    requerir_staff_clinico,
    verificar_acceso_institucion,
)
from core import permisos
from core.schemas_comunes import RespuestaPaginada
from modulos.auth import models as auth_models
from fastapi import status
from fastapi.responses import StreamingResponse
from core.pdf_generator import generar_pdf
from core.email_service import enviar_alerta_riesgo, enviar_alerta_regresion_informe_liberado
from core.limiter import ambito_ip, clave_por_token, limite_ip, limite_token, limiter
from modulos.superadmin import crud as superadmin_crud
from modulos.superadmin import models as superadmin_models
from modulos.instituciones import models as instituciones_models
logger = logging.getLogger("aurorasoft")

# Creamos el enrutador específico para Educación
router = APIRouter(prefix="/educativo", tags=["Educativo"])


def _encolar_sin_bloquear(tarea, *args) -> None:
    """Encola una tarea Celery (`tarea.delay(*args)`) sin dejar que un
    broker caído/inalcanzable (Redis) tumbe una respuesta HTTP que, hasta
    este punto, ya terminó bien (el examen finalizado / el reproceso
    aplicado).

    🔒 Con `BackgroundTasks` de FastAPI esto nunca podía pasar —
    `add_task` solo registra un callback, nunca toca la red de forma
    síncrona. `.delay()` de Celery sí publica al broker EN EL MISMO hilo
    que atiende la petición: si Redis está caído, confirmado probando
    contra un puerto que no escucha, el intento puede directamente
    QUEDARSE COLGADO (no solo lanzar una excepción rápida) sin el
    `broker_transport_options`/`broker_connection_timeout` que
    `core/cola_tareas.py` ya configura. Con ese timeout corto más este
    `try/except`, una caída de Redis se loguea y se sigue — nunca un 500
    (o un cuelgue) para alguien que no tiene nada que ver con la cola."""
    try:
        tarea.delay(*args)
    except Exception:
        logger.error(
            "No se pudo encolar %s (broker de Celery no disponible). Revisar Redis/el worker.",
            getattr(tarea, "name", tarea), exc_info=True,
        )

# ==========================================
# RUTAS PARA LA FICHA SOCIODEMOGRÁFICA
# ==========================================
@router.post("/campos-socio/", response_model=schemas.CampoSociodemograficoResponse)
def crear_campo_sociodemografico(
    campo: schemas.CampoSociodemograficoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    if usuario_actual.rol != "superadmin":
        campo.cliente_id = usuario_actual.institucion_id
    # 🔗 C-16 — con la nueva FK, un cliente_id inexistente (solo lo puede enviar
    # un superadmin) sería un IntegrityError -> 500. Se responde con un 404 claro.
    elif not db.query(instituciones_models.Institucion.id).filter(
        instituciones_models.Institucion.id == campo.cliente_id
    ).first():
        raise HTTPException(status_code=404, detail="Institución no encontrada.")
    return crud.crear_campo_socio(db=db, campo=campo)

# ==========================================
# RUTAS PARA EL MOTOR DE TESTS
# ==========================================
@router.post("/pruebas/", response_model=schemas.PruebaResponse)
def crear_prueba_psicologica(
    prueba: schemas.PruebaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """
    Crea un test nuevo. Si el usuario NO es superadmin, la prueba
    queda marcada como privada de SU colegio (no la ve nadie más).
    """
    if usuario_actual.rol != "superadmin":
        prueba.institucion_id = usuario_actual.institucion_id  # Forzado por seguridad desde la sesión

    return crud.crear_prueba(db=db, prueba=prueba, creado_por_usuario_id=usuario_actual.id)


@router.post("/pruebas/carga-masiva/")
def carga_masiva_de_test(
    datos: schemas.CargaMasivaTest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    crud.verificar_propiedad_de_prueba(db, datos.prueba_id, usuario_actual)  # 🔒 Bloquea IDOR
    return crud.cargar_test_masivo(db=db, datos=datos)


@router.post("/preguntas/", response_model=schemas.PreguntaResponse)
def agregar_pregunta_a_prueba(
    pregunta: schemas.PreguntaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)  # Pregunta ya tiene prueba_id directo
    return crud.crear_pregunta(db=db, pregunta=pregunta)


@router.post("/dimensiones/", response_model=schemas.DimensionResponse)
def agregar_dimension_a_prueba(
    dimension: schemas.DimensionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.crear_dimension(db=db, dimension=dimension)


@router.post("/opciones/", response_model=schemas.OpcionRespuestaResponse)
def agregar_opcion_a_pregunta(
    opcion: schemas.OpcionRespuestaCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    pregunta = db.query(models.Pregunta).filter(models.Pregunta.id == opcion.pregunta_id).first()
    if not pregunta:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada.")
    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)
    return crud.crear_opcion_respuesta(db=db, opcion=opcion)

# ==========================================
# RUTAS DE PROGRESO Y FINALIZACIÓN
# ==========================================
@router.post("/examen/{token}/guardar", response_model=dict)
@limiter.limit(limite_token("guardar"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("guardar"), scope=ambito_ip("guardar"))
def guardar_progreso_examen(request: Request, token: str, respuestas: schemas.ExamenSubmit, db: Session = Depends(get_db)):
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Link inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )
        
    # 🔒 CANDADO 1: Asentimiento del propio estudiante requerido
    if not inscripcion.acepto_asentimiento:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden guardar respuestas sin haber aceptado previamente el asentimiento informado."
        )

    # 🔒 CANDADO 1.5: Verificar si el consentimiento fue revocado globalmente
    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio."
        )

    # 🔒 CANDADO 2: Expiración por Fecha Límite de Evaluación/Campaña
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido."
        )

    if inscripcion.estado == "Finalizado":
        raise HTTPException(status_code=400, detail="El examen ya está finalizado. No se pueden modificar respuestas.")

    # 🟢 Se agrega la invocación al CRUD para guardar las respuestas en la base de datos
    resultado = crud.guardar_respuestas_examen(db=db, token=token, respuestas=respuestas.respuestas)
    return resultado

@router.post("/examen/{token}/finalizar", response_model=List[schemas.DiagnosticoAlumnoResponse])
@limiter.limit(limite_token("finalizar"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("finalizar"), scope=ambito_ip("finalizar"))
def finalizar_examen_seguro(
    request: Request,
    token: str, 
    background_tasks: BackgroundTasks,  # 🟢 Inyección de tareas en segundo plano
    db: Session = Depends(get_db)
):
    # --- FASE 1: Validaciones previas SIN bloqueo (para no saturar la BD si vamos a rechazar) ---
    inscripcion_val = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion_val:
        raise HTTPException(status_code=404, detail="Link inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion_val):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    if not inscripcion_val.acepto_asentimiento:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No se puede finalizar la evaluación sin haber aceptado el asentimiento informado.")

    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion_val):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio.")

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion_val.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido.")


    # --- FASE 2: Bloqueo de fila + cálculo + estado, TODO en una transacción ---
    #
    # Antes el estado pasaba a "Finalizado" y se confirmaba ANTES de calcular.
    # Si el cálculo fallaba, el alumno recibía un 500, la inscripción quedaba
    # marcada como finalizada sin resultados, y el reintento chocaba contra el
    # candado de idempotencia: quedaba bloqueado para siempre (B-9).
    #
    # Ahora el bloqueo de fila se mantiene hasta el ÚNICO commit del final, así
    # que se conserva intacta la protección contra doble envío concurrente —una
    # segunda petición simultánea espera en el FOR UPDATE y, al desbloquearse,
    # lee "Finalizado" y es rechazada— pero cualquier excepción revierte la
    # transacción entera y el alumno puede volver a intentarlo.
    try:
        # 🔒 Ver crud.bloquear_inscripcion_para_finalizar(): trae la fila con
        # FOR UPDATE y fuerza estado fresco (populate_existing()) pese a que
        # la Fase 1 ya cargó esta misma Inscripcion, sin bloqueo, en el
        # identity map de esta Session.
        inscripcion = crud.bloquear_inscripcion_para_finalizar(db=db, token=token)

        if not inscripcion:
            raise HTTPException(status_code=404, detail="Link inválido.")

        # 🔒 Candado de idempotencia (se evalúa ya con la fila bloqueada)
        if inscripcion.estado == "Finalizado":
            raise HTTPException(
                status_code=400,
                detail="Este examen ya fue finalizado. No se puede repetir.",
            )

        # 🔒 🆕 Segunda capa de defensa contra un examen incompleto (hallazgo
        # de auditoría, ver docs/gaps-pendientes.md y crud.contar_preguntas_
        # sin_responder) — hasta ahora la ÚNICA barrera era el candado de
        # frontend (`faltanPreguntas`), ya endurecido contra fallos de
        # autoguardado pero no una segunda capa real del lado del servidor.
        # Un dispositivo/navegador real del piloto (conexión inestable, un
        # bug de frontend no visto en Playwright, una llamada directa a la
        # API) podía finalizar con menos RespuestaAlumno que Pregunta sin que
        # el backend lo notara — calcular_resultados_dimensiones solo suma lo
        # que de verdad se guardó, así que el puntaje quedaba silenciosamente
        # más bajo, sin ningún error. Se evalúa ya con la fila bloqueada, en
        # el mismo lugar que el candado de idempotencia de arriba, y ANTES de
        # tocar cualquier resultado: un examen incompleto se rechaza aquí y
        # la inscripción queda exactamente como estaba, igual de
        # reintentable que antes de este candado.
        preguntas_sin_responder = crud.contar_preguntas_sin_responder(
            db=db, inscripcion_id=inscripcion.id, prueba_id=evaluacion.prueba_id,
        )
        if preguntas_sin_responder > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Todavía tienes preguntas sin responder. Vuelve atrás, "
                    "respóndelas y vuelve a intentar finalizar."
                ),
            )

        # 1. Recalcular desde cero: si una finalización anterior se revirtió a
        #    medias, el reintento no debe acumular puntajes ni diagnósticos.
        crud.limpiar_resultados_previos(db=db, inscripcion_id=inscripcion.id)

        # 2. Motores de cálculo e interpretación (ninguno confirma por su cuenta)
        crud.calcular_resultados_dimensiones(db=db, inscripcion_id=inscripcion.id)
        interpretacion = crud.interpretar_segun_modo(
            db=db, inscripcion_id=inscripcion.id, prueba_id=evaluacion.prueba_id,
        )
        diagnosticos = interpretacion["diagnosticos"]
        dimensiones_sin_baremo = interpretacion["dimensiones_sin_baremo"]

        # 2.5. Reglas de interpretación adicionales (genéricas, por prueba —
        #      ver modulos/educativo/models.py:ReglaInterpretacion). Pueden
        #      encender es_alerta sobre un diagnóstico que el baremo dejó sin
        #      alerta (o incluso sin baremo aplicable), pero NUNCA lo apagan.
        resultado_reglas = crud.evaluar_reglas_interpretacion(
            db=db, inscripcion_id=inscripcion.id, prueba_id=evaluacion.prueba_id,
        )
        diagnosticos = crud.aplicar_reglas_a_diagnosticos(
            db=db, inscripcion_id=inscripcion.id, diagnosticos=diagnosticos,
            resultado_reglas=resultado_reglas,
        )
        reglas_con_error = resultado_reglas["con_error"]

        # 3. ¿Requiere revisión profesional? Tres motivos distintos, misma
        #    consecuencia para el alumno: el informe se retiene.
        niveles_alerta = crud.detectar_niveles_de_alerta(diagnosticos)
        interpretacion_completa = interpretacion["interpretacion_completa"]
        requiere_revision = bool(niveles_alerta) or not interpretacion_completa or bool(reglas_con_error)

        # 4. Estado final y visibilidad
        inscripcion.estado = "Finalizado"
        inscripcion.fecha_resolucion = datetime.now(timezone.utc)
        inscripcion.resultado_visible_alumno = not requiere_revision
        inscripcion.informe_liberado = not requiere_revision
        inscripcion.estado_interpretacion = (
            models.INTERPRETACION_COMPLETA if interpretacion_completa
            else models.INTERPRETACION_INCOMPLETA
        )
        inscripcion.dimensiones_sin_baremo = (
            ", ".join(dimensiones_sin_baremo) if dimensiones_sin_baremo else None
        )
        inscripcion.reglas_con_error = ", ".join(reglas_con_error) if reglas_con_error else None

        # 5. Un único commit: o queda todo, o no queda nada.
        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.error(
            "Fallo al finalizar la evaluación del token %s. La transacción se "
            "revirtió: la inscripción NO queda marcada como finalizada y el "
            "alumno puede reintentar.", token, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "No se pudieron calcular tus resultados en este momento. "
                "Tus respuestas están guardadas: vuelve a intentarlo en unos "
                "minutos o avisa al equipo de orientación de tu colegio."
            ),
        )

    # --- FASE 3: Notificaciones e informe, ya fuera de la transacción ---
    #
    # 🆕 Informes — el PDF se genera y se guarda en storage SIEMPRE, tenga o
    # no alerta: la autorización de descarga la deciden informe_liberado/
    # resultado_visible_alumno en el momento de servirlo (ver router más
    # abajo), nunca si el archivo existe o no. Va en segundo plano para no
    # bloquear al alumno esperando a que reportlab/matplotlib terminen — ver
    # "GENERACIÓN BAJO DEMANDA VS ALMACENAMIENTO".
    #
    # 🆕 Fase 2 (Celery, docs/gaps-pendientes.md) — antes era
    # `background_tasks.add_task(...)` (BackgroundTasks de FastAPI, sin
    # reintento ni recuperación); ahora `.delay()` encola la tarea real en
    # Celery/Redis, con reintento automático. El parámetro `background_tasks`
    # de este endpoint queda sin uso (aditivo primero, deprecar después —
    # ver docs/gaps-pendientes.md, "Principios rectores"): no se borra
    # todavía, se confirma antes que ningún test dependa de él.
    _encolar_sin_bloquear(crud.tarea_generar_informe_en_segundo_plano, inscripcion.id)

    # 🆕 Enganche motor de pruebas -> motor de documentos (ver
    # modulos/documentos/crud.py:generar_documentos_automaticos_por_examen):
    # si la institución de esta inscripción activó
    # PlantillaDocumento.generar_automaticamente_al_finalizar_examen en
    # alguna de sus plantillas, esto genera además, en segundo plano, un
    # DocumentoInstitucional propio de ESA institución a partir de este
    # mismo resultado — sin reemplazar ni tocar el informe psicométrico
    # fijo de arriba, que sigue siendo igual para todos los colegios.
    # Importado adentro de la función (no al tope del archivo) a propósito:
    # modulos.documentos.crud ya importa modulos.educativo.models, así que
    # esto mantiene la dependencia entre módulos en un solo sentido real
    # (educativo dispara, nunca se importa desde el tope en el otro
    # sentido) — mismo criterio por el que tarea_generar_informe_en_
    # segundo_plano importa SessionLocal adentro de sí misma.
    from modulos.documentos import crud as documentos_crud
    _encolar_sin_bloquear(documentos_crud.tarea_generar_documentos_automaticos_en_segundo_plano, inscripcion.id)

    if requiere_revision:
        destinatarios, motivos = crud.obtener_destinatarios_alerta(db=db, evaluacion=evaluacion)
        if destinatarios:
            logger.info(
                "Alerta de la inscripción %s enviada a %s destinatario(s): %s",
                inscripcion.id, len(destinatarios), ", ".join(motivos),
            )
            # 🚀 Celery ejecuta el envío de forma asíncrona, con reintento real
            _encolar_sin_bloquear(
                enviar_alerta_riesgo,
                destinatarios,
                inscripcion.nombre_completo or "Evaluado",
                niveles_alerta,
                dimensiones_sin_baremo,
                reglas_con_error,
            )

    # Se conserva la forma de respuesta histórica (lista) para no romper al
    # frontend, pero nunca se devuelven diagnósticos si el profesional debe
    # revisarlos primero.
    return diagnosticos if inscripcion.resultado_visible_alumno else []


@router.get(
    "/examen/{token}/estado-resultados",
    response_model=schemas.EstadoResultadosAlumnoResponse,
)
@limiter.limit(limite_token("estado_resultados"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("estado_resultados"), scope=ambito_ip("estado_resultados"))
def obtener_estado_resultados_alumno(request: Request, token: str, db: Session = Depends(get_db)):
    """Estado seguro para que el portal del alumno informe la revisión clínica.

    Esta ruta no expone puntajes, diagnósticos ni interpretación clínica.
    """
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    if inscripcion.estado != "Finalizado":
        mensaje = "Tu evaluación aún no ha sido finalizada."
    elif not inscripcion.resultado_visible_alumno:
        # Mismo mensaje tanto si hay alerta como si faltó baremo: el alumno no
        # debe poder deducir por el texto que fue marcado como caso de riesgo.
        mensaje = "Tus resultados están siendo revisados por el equipo de orientación de tu institución."
    elif not inscripcion.informe_liberado:
        mensaje = "Tus resultados están disponibles; el informe completo sigue en revisión profesional."
    else:
        mensaje = "Tus resultados y tu informe están disponibles."

    return {
        "estado_examen": inscripcion.estado,
        "resultado_visible_alumno": inscripcion.resultado_visible_alumno,
        "informe_liberado": inscripcion.informe_liberado,
        "estado_interpretacion": inscripcion.estado_interpretacion,
        "mensaje": mensaje,
    }

# ==========================================
# INFORME PDF — DESCARGA PARA EL ALUMNO (con su link mágico)
# ==========================================
@router.get("/examen/{token}/informe-pdf")
@limiter.limit(limite_token("informe_pdf"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("informe_pdf"), scope=ambito_ip("informe_pdf"))
def descargar_informe_pdf_alumno(request: Request, token: str, db: Session = Depends(get_db)):
    """El alumno descarga su propio informe justo después de finalizar el examen."""
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    if inscripcion.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="El examen todavía no ha sido finalizado.")

    if not inscripcion.informe_liberado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu psicólogo del colegio revisará tus resultados contigo antes de entregarte el informe.",
        )

    # 🆕 Informes — si ya existe un PDF almacenado (el caso normal desde que
    # finalizar-examen los genera en segundo plano), se sirve tal cual desde
    # storage: nunca se regenera solo porque alguien vuelva a pedirlo. Si no
    # existe (inscripción finalizada ANTES de esta fase, o el trabajo en
    # segundo plano aún no terminó), se cae al generado al vuelo de siempre.
    informe = crud.obtener_informe_de_inscripcion(db, inscripcion.id)
    version = crud.obtener_version_actual_de_informe(db, informe) if informe else None

    if version:
        try:
            contenido = crud.leer_pdf_de_version(version)
        except FileNotFoundError:
            contenido = None
    else:
        contenido = None

    if contenido is not None:
        pdf_buffer = io.BytesIO(contenido)
        nombre_archivo = version.nombre_archivo
    else:
        datos = crud.obtener_datos_para_pdf(db=db, inscripcion_id=inscripcion.id)
        if not datos:
            raise HTTPException(status_code=404, detail="No se encontraron datos para generar el informe.")

        institucion_pdf = db.query(instituciones_models.Institucion).filter(
            instituciones_models.Institucion.id == datos["institucion_id"]
        ).first()
        pdf_buffer = generar_pdf(crud.construir_contenido_pdf(datos, institucion=institucion_pdf))
        nombre_archivo = f"informe_{(inscripcion.nombre_completo or 'evaluado').replace(' ', '_')}.pdf"

    # 🟢 PRIVACIDAD Y SEGURIDAD: Cabeceras anti-caché estrictas (Ley 29733)
    headers = {
        "Content-Disposition": f'attachment; filename="{nombre_archivo}"',
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers=headers
    )


# ==========================================
# INFORME PDF — DESCARGA PARA EL PSICÓLOGO/COLEGIO (panel, con login)
# ==========================================
@router.get("/inscripciones/{inscripcion_id}/informe-pdf")
def descargar_informe_pdf_staff(
    inscripcion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """El psicólogo/colegio descarga el informe de cualquier alumno de SU institución."""
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")

    datos = crud.obtener_datos_para_pdf(db=db, inscripcion_id=inscripcion_id)
    if not datos:
        raise HTTPException(status_code=404, detail="No se encontraron datos para generar el informe.")

    crud.verificar_puede_ver_informe(usuario_actual, datos["institucion_id"], inscripcion.informe_liberado)

    # 🆕 Informes — mismo criterio que la descarga del alumno: servir el PDF
    # ya almacenado en vez de regenerarlo, con fallback al vuelo si aún no
    # existe (inscripción pre-fase-informes, o el job en 2º plano no terminó).
    informe = crud.obtener_informe_de_inscripcion(db, inscripcion_id)
    version = crud.obtener_version_actual_de_informe(db, informe) if informe else None

    if version:
        try:
            contenido = crud.leer_pdf_de_version(version)
        except FileNotFoundError:
            contenido = None
    else:
        contenido = None

    if contenido is not None:
        pdf_buffer = io.BytesIO(contenido)
        nombre_archivo = version.nombre_archivo
    else:
        institucion_pdf = db.query(instituciones_models.Institucion).filter(
            instituciones_models.Institucion.id == datos["institucion_id"]
        ).first()
        pdf_buffer = generar_pdf(crud.construir_contenido_pdf(datos, institucion=institucion_pdf))
        nombre_archivo = f"informe_{inscripcion_id}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'}
    )


# ==========================================
# INFORME — METADATA, HISTORIAL DE VERSIONES Y REEMISIÓN (staff)
# ==========================================
@router.get("/inscripciones/{inscripcion_id}/informe")
def obtener_metadata_informe(
    inscripcion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Metadata del informe de una aplicación: versión actual, historial de
    versiones (sin el binario) y estado de revisión/liberación vigente."""
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    crud.verificar_puede_ver_informe(usuario_actual, evaluacion.institucion_id, inscripcion.informe_liberado)

    informe = crud.obtener_informe_de_inscripcion(db, inscripcion_id)
    if not informe:
        return {
            "existe": False,
            "resultado_visible_alumno": inscripcion.resultado_visible_alumno,
            "informe_liberado": inscripcion.informe_liberado,
            "estado_interpretacion": inscripcion.estado_interpretacion,
        }

    versiones = crud.listar_versiones_de_informe(db, informe.id)
    return {
        "existe": True,
        "informe_id": informe.id,
        "version_actual": informe.version_actual,
        "resultado_visible_alumno": inscripcion.resultado_visible_alumno,
        "informe_liberado": inscripcion.informe_liberado,
        "estado_interpretacion": inscripcion.estado_interpretacion,
        # 🆕 Contenido profesional crudo (fuente "C" — ver construir_contenido_pdf
        # en crud.py), para que un panel de revisión pueda precargar lo que
        # YA se guardó (o None si nunca se tocó) antes de dejar editar. A
        # diferencia de obtener_datos_para_pdf, esto nunca mezcla con el
        # contenido configurado por la prueba/baremo: son los 5 campos tal
        # cual están en Inscripcion, sin resolver.
        "motivo_consulta": inscripcion.motivo_consulta,
        "observacion_conductual": inscripcion.observacion_conductual,
        "tecnicas_override": inscripcion.tecnicas_override,
        "conclusion_override": inscripcion.conclusion_override,
        "recomendaciones_override": inscripcion.recomendaciones_override,
        "firma_cargo_override": inscripcion.firma_cargo_override,
        "firma_nombre_override": inscripcion.firma_nombre_override,
        "firma_dni_override": inscripcion.firma_dni_override,
        "interpretacion_clinica": inscripcion.interpretacion_clinica,
        "versiones": [
            {
                "numero_version": v.numero_version,
                "generado_en": v.generado_en,
                "generado_por_usuario_id": v.generado_por_usuario_id,
                "motivo_version": v.motivo_version,
                "origen": v.origen,
                "tamano_bytes": v.tamano_bytes,
                "checksum_sha256": v.checksum_sha256,
                "mime_type": v.mime_type,
                # 🆕 docs/gaps-pendientes.md — esta versión reemplaza a una
                # anterior (numero_version - 1) que ya estaba liberada y
                # visible para el alumno antes de esta corrección.
                "retracta_version_previa_liberada": v.retracta_version_previa_liberada,
            }
            for v in versiones
        ],
    }


@router.post("/inscripciones/{inscripcion_id}/informe/reemitir")
def reemitir_informe(
    inscripcion_id: int,
    datos: schemas.ReemitirInformeRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Crea una NUEVA versión del informe (nunca sobreescribe la anterior).

    Pensado para cuando se corrige un error de representación o se re-emite
    el informe tras revisar la interpretación — no para uso rutinario: cada
    llamada queda trazada con quién y por qué (`motivo`, obligatorio).
    """
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if inscripcion.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden reemitir informes de evaluaciones finalizadas.")

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes reemitir informes de otro colegio.")

    try:
        version = crud.generar_y_almacenar_informe(
            db, inscripcion_id=inscripcion_id, usuario_id=usuario_actual.id, motivo=datos.motivo,
            origen="reemision",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "mensaje": "Informe reemitido.",
        "informe_id": version.informe_id,
        "numero_version": version.numero_version,
    }


@router.post("/inscripciones/{inscripcion_id}/reprocesar")
def reprocesar_informe_de_inscripcion(
    inscripcion_id: int,
    datos: schemas.ReprocesarInformeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    # 🔒 A diferencia de reemitir/liberar-informe (que incluyen psicólogo),
    # esta acción queda restringida a admin/superadmin: corregir un baremo y
    # reprocesar lo que ya se interpretó con él es una acción administrativa
    # sobre la CONFIGURACIÓN del motor, no un juicio clínico caso por caso.
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Recalcula una inscripción YA finalizada contra los baremos/reglas
    VIGENTES (p. ej. tras corregir un Baremo mal configurado) y emite una
    nueva versión del informe — a diferencia de `reemitir`, que solo vuelve a
    renderizar el PDF con lo que ya estaba guardado en DiagnosticoAlumno.

    Respeta las mismas garantías que `finalizar_examen_seguro`: bloqueo de
    fila con `populate_existing()`, una única transacción para recalcular +
    reinterpretar + reevaluar reglas, y la misma fórmula para decidir si el
    resultado requiere revisión profesional. Nunca toca `estado` (sigue
    "Finalizado") ni `fecha_resolucion` (hecho histórico); nunca sobreescribe
    una InformeVersion anterior.
    """
    # --- Fase 1: validaciones sin bloqueo ---
    inscripcion_val = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion_val:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if not crud.inscripcion_esta_activa(inscripcion_val):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Esta inscripción fue eliminada o anonimizada; no se puede reprocesar.",
        )
    if inscripcion_val.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden reprocesar evaluaciones finalizadas.")

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion_val.evaluacion_id).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes reprocesar informes de otro colegio.")

    # --- Fase 2: bloqueo de fila + recálculo + reinterpretación, en una sola transacción ---
    try:
        inscripcion = crud.bloquear_inscripcion_para_reprocesar(db=db, inscripcion_id=inscripcion_id)
        if not inscripcion:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
        if not crud.inscripcion_esta_activa(inscripcion):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Esta inscripción fue eliminada o anonimizada; no se puede reprocesar.",
            )
        if inscripcion.estado != "Finalizado":
            raise HTTPException(status_code=400, detail="Solo se pueden reprocesar evaluaciones finalizadas.")

        crud.limpiar_resultados_previos(db=db, inscripcion_id=inscripcion.id)
        crud.calcular_resultados_dimensiones(db=db, inscripcion_id=inscripcion.id)
        interpretacion = crud.interpretar_segun_modo(
            db=db, inscripcion_id=inscripcion.id, prueba_id=evaluacion.prueba_id,
        )
        diagnosticos = interpretacion["diagnosticos"]
        dimensiones_sin_baremo = interpretacion["dimensiones_sin_baremo"]

        resultado_reglas = crud.evaluar_reglas_interpretacion(
            db=db, inscripcion_id=inscripcion.id, prueba_id=evaluacion.prueba_id,
        )
        diagnosticos = crud.aplicar_reglas_a_diagnosticos(
            db=db, inscripcion_id=inscripcion.id, diagnosticos=diagnosticos,
            resultado_reglas=resultado_reglas,
        )
        reglas_con_error = resultado_reglas["con_error"]

        niveles_alerta = crud.detectar_niveles_de_alerta(diagnosticos)
        interpretacion_completa = interpretacion["interpretacion_completa"]
        requiere_revision = bool(niveles_alerta) or not interpretacion_completa or bool(reglas_con_error)

        # 🆕 Riesgo operacional (docs/gaps-pendientes.md): se captura ANTES de
        # sobreescribir los dos campos de abajo, porque es exactamente la
        # pregunta "¿esta corrección retiene de nuevo algo que el alumno ya
        # pudo haber visto/descargado?" — nunca "¿quedó retenido ahora?",
        # que ya responde requiere_revision por sí solo.
        es_regresion_de_informe_liberado = (
            bool(inscripcion.informe_liberado) and bool(inscripcion.resultado_visible_alumno) and requiere_revision
        )

        # A diferencia de finalizar_examen_seguro: `estado`/`fecha_resolucion`
        # NUNCA se tocan (el examen ya se rindió, esto es una reinterpretación
        # de ese mismo resultado histórico). `revisado_por_usuario_id`/
        # `interpretacion_clinica` tampoco se tocan — son notas del
        # profesional, independientes del tramo de baremo alcanzado.
        inscripcion.resultado_visible_alumno = not requiere_revision
        inscripcion.informe_liberado = not requiere_revision
        inscripcion.estado_interpretacion = (
            models.INTERPRETACION_COMPLETA if interpretacion_completa
            else models.INTERPRETACION_INCOMPLETA
        )
        inscripcion.dimensiones_sin_baremo = (
            ", ".join(dimensiones_sin_baremo) if dimensiones_sin_baremo else None
        )
        inscripcion.reglas_con_error = ", ".join(reglas_con_error) if reglas_con_error else None

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.error(
            "Fallo al reprocesar la inscripción %s. La transacción se revirtió: "
            "el informe anterior sigue intacto y sin cambios.", inscripcion_id, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo reprocesar esta inscripción en este momento. Intenta de nuevo más tarde.",
        )

    # --- Fase 3: nueva versión del informe y, si corresponde, alerta — fuera de la transacción ---
    try:
        version = crud.generar_y_almacenar_informe(
            db, inscripcion_id=inscripcion.id, usuario_id=usuario_actual.id, motivo=datos.motivo,
            origen="reproceso", retracta_version_previa_liberada=es_regresion_de_informe_liberado,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # 🆕 Cierra el hueco documentado en CLAUDE.md ("no enganchado a
    # reprocesar, decisión deliberada de alcance"): cualquier
    # DocumentoInstitucional (automático o vinculado a mano) cuya sección
    # resultados_prueba apunte a esta inscripción queda con contenido
    # desactualizado tras la corrección — se reemite aquí mismo, síncrono,
    # igual que el informe psicométrico de arriba. Importado adentro de la
    # función por el mismo motivo que en finalizar_examen_seguro: mantiene
    # la dependencia entre educativo y documentos en un solo sentido real.
    from modulos.documentos import crud as documentos_crud
    documentos_reemitidos = documentos_crud.reemitir_documentos_vinculados_a_inscripcion(
        db, inscripcion_id=inscripcion.id, usuario_id=usuario_actual.id,
        motivo=f"Reproceso de examen: {datos.motivo}",
    )
    if documentos_reemitidos:
        logger.info(
            "Reproceso de la inscripción %s reemitió %s documento(s) institucional(es) vinculado(s): %s",
            inscripcion.id, len(documentos_reemitidos), documentos_reemitidos,
        )

    if requiere_revision:
        destinatarios, motivos = crud.obtener_destinatarios_alerta(db=db, evaluacion=evaluacion)
        if destinatarios:
            logger.info(
                "Alerta de la inscripción %s (reprocesada) enviada a %s destinatario(s): %s",
                inscripcion.id, len(destinatarios), ", ".join(motivos),
            )
            _encolar_sin_bloquear(
                enviar_alerta_riesgo,
                destinatarios,
                inscripcion.nombre_completo or "Evaluado",
                niveles_alerta,
                dimensiones_sin_baremo,
                reglas_con_error,
            )

    # 🆕 Riesgo operacional (docs/gaps-pendientes.md): además de la alerta
    # genérica de arriba (que va a la cadena de respaldo institucional, no
    # necesariamente a quien liberó el informe), si ESTA corrección retiene
    # de nuevo algo que ya estaba liberado y visible, se avisa puntualmente
    # a quien tomó esa decisión original — es quien tiene contexto real
    # para saber si el alumno/apoderado ya lo tienen en sus manos. No
    # reemplaza ni duplica la alerta genérica: puede coincidir con alguno de
    # sus destinatarios, o puede ser alguien que ya no está en esa lista
    # (ej. un psicólogo que liberó el informe pero no es el creador de la
    # campaña ni admin).
    revisor_original_notificado = False
    if es_regresion_de_informe_liberado:
        revisor_original = crud.obtener_revisor_original_de_inscripcion(db=db, inscripcion=inscripcion)
        if revisor_original and revisor_original.email:
            logger.info(
                "Reproceso de la inscripción %s retiene de nuevo un informe que ya estaba liberado "
                "(v%s -> v%s); se notifica a quien lo liberó originalmente (usuario %s).",
                inscripcion.id, version.numero_version - 1, version.numero_version, revisor_original.id,
            )
            _encolar_sin_bloquear(
                enviar_alerta_regresion_informe_liberado,
                revisor_original.email,
                inscripcion.nombre_completo or "Evaluado",
                version.numero_version - 1,
            )
            revisor_original_notificado = True
        else:
            logger.warning(
                "Reproceso de la inscripción %s retiene de nuevo un informe que ya estaba liberado, pero no "
                "hay un revisor original activo al que avisar; queda solo la alerta genérica de arriba.",
                inscripcion.id,
            )

    return {
        "mensaje": "Inscripción reprocesada.",
        "informe_id": version.informe_id,
        "numero_version": version.numero_version,
        "requiere_revision": requiere_revision,
        "resultado_visible_alumno": inscripcion.resultado_visible_alumno,
        "informe_liberado": inscripcion.informe_liberado,
        "documentos_institucionales_reemitidos": documentos_reemitidos,
        "retraccion_informe_liberado": es_regresion_de_informe_liberado,
        "revisor_original_notificado": revisor_original_notificado,
    }


@router.get("/personas/{persona_id}/informes")
def historial_informes_de_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Historial de informes de un estudiante, uno por aplicación (nunca se
    sobreescriben entre sí). superadmin puede pasar institucion_id por query;
    el resto queda forzado a la suya propia — mismo convenio que
    GET /admin/personas/{id}/historial-academico."""
    persona = db.query(superadmin_models.Persona).filter(superadmin_models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")

    institucion_objetivo = (
        persona.institucion_id if usuario_actual.rol == "superadmin" else usuario_actual.institucion_id
    )
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver informes de otro colegio.")

    historial = crud.listar_historial_informes_de_persona(db, persona_id=persona_id, institucion_id=institucion_objetivo)
    # 🔒 Remediación de permisos, paso 3 — es una LISTA (una persona puede
    # tener varias aplicaciones con distinto informe_liberado cada una), así
    # que el candado no puede ser un solo booleano como en el PDF/metadata de
    # una aplicación puntual: se filtra fila por fila, misma condición.
    if usuario_actual.rol == "colegio":
        historial = [fila for fila in historial if fila["informe_liberado"]]
    return historial


@router.patch("/inscripciones/{inscripcion_id}/liberar-informe")
def liberar_informe(
    inscripcion_id: int,
    datos: schemas.LiberarInformeRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Registra la revisión clínica y habilita el informe para el alumno."""
    inscripcion_val = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion_val:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if inscripcion_val.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden liberar informes de evaluaciones finalizadas.")

    evaluacion = db.query(models.Evaluacion).filter(
        models.Evaluacion.id == inscripcion_val.evaluacion_id
    ).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes liberar informes de otro colegio.")

    # 🔒 Ver bloquear_inscripcion_para_reprocesar: serializa contra un
    # reprocesar concurrente sobre la MISMA inscripción, que escribe estos
    # mismos dos campos (informe_liberado/resultado_visible_alumno) — sin
    # esto, esta acción podía quedar esperando el candado de reprocesar sin
    # saberlo y, al desbloquearse, escribir sobre un objeto cargado ANTES de
    # esa corrección, en vez de validar el estado fresco primero.
    inscripcion = crud.bloquear_inscripcion_para_reprocesar(db=db, inscripcion_id=inscripcion_id)
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if inscripcion.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden liberar informes de evaluaciones finalizadas.")

    if datos.interpretacion_clinica is not None:
        inscripcion.interpretacion_clinica = datos.interpretacion_clinica.strip() or None
    inscripcion.informe_liberado = True
    inscripcion.revisado_por_usuario_id = usuario_actual.id
    inscripcion.fecha_revision_informe = datetime.now(timezone.utc)
    db.commit()

    return {"mensaje": "Informe liberado.", "informe_liberado": True}


@router.patch("/inscripciones/{inscripcion_id}/revision-informe")
def actualizar_revision_informe(
    inscripcion_id: int,
    datos: schemas.RevisionInformeRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.STAFF_CLINICO),
):
    """Guarda la interpretación y decide por separado la visibilidad del resultado y PDF."""
    inscripcion_val = db.query(models.Inscripcion).filter(models.Inscripcion.id == inscripcion_id).first()
    if not inscripcion_val:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if inscripcion_val.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden revisar evaluaciones finalizadas.")

    evaluacion = db.query(models.Evaluacion).filter(
        models.Evaluacion.id == inscripcion_val.evaluacion_id
    ).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes revisar informes de otro colegio.")

    # 🔒 Ver el mismo candado en liberar_informe/bloquear_inscripcion_para_reprocesar:
    # este endpoint también escribe informe_liberado/resultado_visible_alumno,
    # los mismos campos que reprocesar — serializarlo evita que una revisión
    # manual escriba sobre un estado que un reprocesar concurrente ya corrigió.
    inscripcion = crud.bloquear_inscripcion_para_reprocesar(db=db, inscripcion_id=inscripcion_id)
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada.")
    if inscripcion.estado != "Finalizado":
        raise HTTPException(status_code=400, detail="Solo se pueden revisar evaluaciones finalizadas.")

    if datos.interpretacion_clinica is not None:
        inscripcion.interpretacion_clinica = datos.interpretacion_clinica.strip() or None
    if datos.resultado_visible_alumno is not None:
        inscripcion.resultado_visible_alumno = datos.resultado_visible_alumno
    if datos.informe_liberado is not None:
        inscripcion.informe_liberado = datos.informe_liberado
    # 🆕 Contenido profesional del informe (fuente "C" — ver
    # construir_contenido_informe en crud.py). Guardarlo aquí NO reescribe
    # ningún PDF ya emitido: solo queda disponible para la PRÓXIMA reemisión.
    if datos.motivo_consulta is not None:
        inscripcion.motivo_consulta = datos.motivo_consulta.strip() or None
    if datos.observacion_conductual is not None:
        inscripcion.observacion_conductual = datos.observacion_conductual.strip() or None
    if datos.tecnicas_override is not None:
        inscripcion.tecnicas_override = datos.tecnicas_override.strip() or None
    if datos.conclusion_override is not None:
        inscripcion.conclusion_override = datos.conclusion_override.strip() or None
    if datos.recomendaciones_override is not None:
        inscripcion.recomendaciones_override = datos.recomendaciones_override.strip() or None
    if datos.firma_cargo_override is not None:
        inscripcion.firma_cargo_override = datos.firma_cargo_override.strip() or None
    if datos.firma_nombre_override is not None:
        inscripcion.firma_nombre_override = datos.firma_nombre_override.strip() or None
    if datos.firma_dni_override is not None:
        inscripcion.firma_dni_override = datos.firma_dni_override.strip() or None

    inscripcion.revisado_por_usuario_id = usuario_actual.id
    inscripcion.fecha_revision_informe = datetime.now(timezone.utc)
    db.commit()

    return {
        "mensaje": "Revisión del informe actualizada.",
        "resultado_visible_alumno": inscripcion.resultado_visible_alumno,
        "informe_liberado": inscripcion.informe_liberado,
        "motivo_consulta": inscripcion.motivo_consulta,
        "observacion_conductual": inscripcion.observacion_conductual,
        "tecnicas_override": inscripcion.tecnicas_override,
        "conclusion_override": inscripcion.conclusion_override,
        "recomendaciones_override": inscripcion.recomendaciones_override,
        "firma_cargo_override": inscripcion.firma_cargo_override,
        "firma_nombre_override": inscripcion.firma_nombre_override,
        "firma_dni_override": inscripcion.firma_dni_override,
    }
# ==========================================
# RUTAS PARA BAREMOS
# ==========================================
# ==========================================
# RUTAS PARA BAREMOS
# ==========================================
@router.post("/baremos/", response_model=schemas.BaremoResponse)
def agregar_baremo_a_dimension(
    baremo: schemas.BaremoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    dimension = db.query(models.Dimension).filter(models.Dimension.id == baremo.dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.crear_baremo(db=db, baremo=baremo)

# ==========================================
# RUTAS PARA REGLAS DE INTERPRETACIÓN (genéricas, por prueba)
# ==========================================
@router.post("/pruebas/{prueba_id}/reglas", response_model=schemas.ReglaInterpretacionResponse)
def crear_regla_de_interpretacion(
    prueba_id: int,
    regla: schemas.ReglaInterpretacionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Declara una condición adicional de alerta para esta prueba (ej. ítem 9
    del PHQ-9). Mismo candado de propiedad que preguntas/dimensiones/baremos:
    solo quien es dueño de la prueba (o superadmin, para el catálogo público)
    puede configurarle reglas — así una institución nunca puede alterar cómo
    se interpreta la prueba de otra."""
    crud.verificar_propiedad_de_prueba(db, prueba_id, usuario_actual)
    if regla.pregunta_id is not None:
        pregunta_valida = db.query(models.Pregunta.id).filter(
            models.Pregunta.id == regla.pregunta_id, models.Pregunta.prueba_id == prueba_id,
        ).first()
        if not pregunta_valida:
            raise HTTPException(status_code=400, detail="La pregunta indicada no pertenece a esta prueba.")
    if regla.dimension_id is not None:
        dimension_valida = db.query(models.Dimension.id).filter(
            models.Dimension.id == regla.dimension_id, models.Dimension.prueba_id == prueba_id,
        ).first()
        if not dimension_valida:
            raise HTTPException(status_code=400, detail="La dimensión indicada no pertenece a esta prueba.")
    return crud.crear_regla_interpretacion(db=db, prueba_id=prueba_id, datos=regla)


@router.get("/pruebas/{prueba_id}/reglas", response_model=List[schemas.ReglaInterpretacionResponse])
def listar_reglas_de_interpretacion(
    prueba_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    # 🔒 Lectura con el MISMO criterio que /pruebas/{id}/completa (pública,
    # propia, o superadmin) — deliberadamente más laxo que la escritura, que
    # sigue exigiendo verificar_propiedad_de_prueba: cualquier colegio que use
    # el PHQ-9 público debe poder VER sus reglas, pero no crear/editarlas.
    prueba = db.query(models.Prueba).filter(models.Prueba.id == prueba_id).first()
    if not prueba:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
    es_publica = prueba.institucion_id is None
    es_propia = prueba.institucion_id == usuario_actual.institucion_id
    if usuario_actual.rol != "superadmin" and not es_publica and not es_propia:
        raise HTTPException(status_code=403, detail="No puedes ver las reglas de una prueba de otro colegio.")
    return crud.listar_reglas_de_prueba(db=db, prueba_id=prueba_id)


@router.patch("/reglas/{regla_id}", response_model=schemas.ReglaInterpretacionResponse)
def actualizar_regla_de_interpretacion(
    regla_id: int,
    datos: schemas.ReglaInterpretacionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    regla = crud.obtener_regla_interpretacion(db, regla_id)
    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada.")
    crud.verificar_propiedad_de_prueba(db, regla.prueba_id, usuario_actual)
    return crud.actualizar_regla_interpretacion(db=db, regla=regla, datos=datos)

# ==========================================
# RUTAS DE CAMPAÑA Y REGISTRO SEGURO DE ALUMNOS
# ==========================================
@router.post("/campanas/", response_model=schemas.EvaluacionResponse)
def crear_campana_de_test(
    evaluacion: schemas.EvaluacionCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Crea la campaña/salón. Para agregar alumnos, usa /campanas/{id}/matricular-roster."""
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes crear campañas para un colegio que no es el tuyo."
        )

    # 🔒 Fase 3 (aislamiento) — Antes solo se validaba la institución, NO la
    # prueba: un psicólogo podía lanzar una campaña con la prueba PRIVADA de
    # otro colegio y, a través del examen, leer sus preguntas. La prueba debe
    # existir, estar activa y ser pública o de la institución de la campaña.
    prueba = db.query(models.Prueba).filter(models.Prueba.id == evaluacion.prueba_id).first()
    if not prueba or (
        prueba.institucion_id is not None and prueba.institucion_id != evaluacion.institucion_id
    ):
        # Mismo 404 exista o no: no se confirma la existencia de pruebas ajenas.
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
    if not prueba.activa:
        raise HTTPException(status_code=409, detail="La prueba está desactivada; no admite campañas nuevas.")
    # 🆕 Catálogo genérico — una prueba interna (visible_para_clientes=False)
    # tampoco admite campañas nuevas de un colegio, aunque sea pública y esté
    # activa: mismo 404 que la prueba privada de otro colegio de arriba, por
    # el mismo motivo (no confirmar su existencia a quien no debería verla).
    if usuario_actual.rol != "superadmin" and not prueba.visible_para_clientes:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
    if not db.query(instituciones_models.Institucion.id).filter(
        instituciones_models.Institucion.id == evaluacion.institucion_id
    ).first():
        raise HTTPException(status_code=404, detail="Institución no encontrada.")

    return crud.crear_campana_evaluacion(db=db, evaluacion=evaluacion, creador_id=usuario_actual.id)


def _obtener_campana_de_mi_institucion(db: Session, evaluacion_id: int, usuario_actual: auth_models.Usuario) -> models.Evaluacion:
    """Trae la campaña y revalida el tenant contra la fila de BD — nunca
    contra nada que venga del cliente. Compartida por editar/cerrar/cancelar."""
    campana = db.query(models.Evaluacion).filter(models.Evaluacion.id == evaluacion_id).first()
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and campana.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes administrar campañas de un colegio que no es el tuyo.",
        )
    return campana


@router.patch("/campanas/{evaluacion_id}", response_model=schemas.EvaluacionResponse)
def editar_campana(
    evaluacion_id: int,
    datos: schemas.EvaluacionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Edita nombre/fecha de cierre/prueba de una campaña activa.

    `prueba_id` solo es editable si la campaña todavía no tiene ninguna
    inscripción; `nombre_grupo`/`fecha_fin` son siempre editables mientras
    esté "activa" — ver crud.actualizar_campana para las reglas exactas.
    """
    campana = _obtener_campana_de_mi_institucion(db, evaluacion_id, usuario_actual)

    if datos.prueba_id is not None and datos.prueba_id != campana.prueba_id:
        prueba = db.query(models.Prueba).filter(models.Prueba.id == datos.prueba_id).first()
        if not prueba or (
            prueba.institucion_id is not None and prueba.institucion_id != campana.institucion_id
        ):
            raise HTTPException(status_code=404, detail="Prueba no encontrada.")
        if not prueba.activa:
            raise HTTPException(status_code=409, detail="La prueba está desactivada; no admite campañas.")
        if usuario_actual.rol != "superadmin" and not prueba.visible_para_clientes:
            raise HTTPException(status_code=404, detail="Prueba no encontrada.")

    return crud.actualizar_campana(db=db, evaluacion=campana, datos=datos)


@router.post("/campanas/{evaluacion_id}/cerrar", response_model=schemas.EvaluacionResponse)
def cerrar_campana(
    evaluacion_id: int,
    datos: schemas.CerrarCampanaRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Cierre normal: deja de aceptar actividad nueva (reutiliza el candado
    de expiración por fecha_fin) sin tocar ningún resultado ya emitido."""
    campana = _obtener_campana_de_mi_institucion(db, evaluacion_id, usuario_actual)
    return crud.cerrar_campana(db=db, evaluacion=campana, usuario_id=usuario_actual.id, motivo=datos.motivo)


@router.post("/campanas/{evaluacion_id}/cancelar", response_model=schemas.EvaluacionResponse)
def cancelar_campana(
    evaluacion_id: int,
    datos: schemas.CancelarCampanaRequest,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Anula una campaña que nunca produjo resultados reales. Rechazada con
    409 si ya tiene alguna inscripción Finalizada (para eso está cerrar)."""
    campana = _obtener_campana_de_mi_institucion(db, evaluacion_id, usuario_actual)
    return crud.cancelar_campana(db=db, evaluacion=campana, usuario_id=usuario_actual.id, motivo=datos.motivo)


# ==========================================
# NUEVA RUTA: VER LOS LINKS DE LA CAMPAÑA
# ==========================================
@router.get("/campanas/{evaluacion_id}/links", response_model=List[schemas.InscripcionResponse])
def listar_links_de_campana(
    evaluacion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """
    El psicólogo usa esta ruta para ver, copiar y repartir
    los links mágicos generados para su campaña.

    🔒 Los tokens que devuelve son credenciales de acceso al examen de cada
    alumno (quien los tenga puede entrar/ver progreso en su nombre), no datos
    de solo lectura — `colegio` nunca debe poder listarlos.
    """
    # 🔒 CANDADO: buscamos primero de qué colegio es esta campaña
    campana = db.query(models.Evaluacion).filter(models.Evaluacion.id == evaluacion_id).first()
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")

    if usuario_actual.rol != "superadmin" and campana.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes ver los links de una campaña que no es de tu colegio."
        )

    return crud.obtener_links_por_campana(db=db, evaluacion_id=evaluacion_id)

@router.get("/examen/{token}/intake", response_model=schemas.IntakeExamenResponse)
@limiter.limit(limite_token("intake"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("intake"), scope=ambito_ip("intake"))
def obtener_intake_examen(request: Request, token: str, db: Session = Depends(get_db)):
    """Lo que ya se sabe de esta inscripción ANTES de pedirle nada al
    estudiante — para que la pantalla "Antes de comenzar" del frontend
    muestre de solo lectura lo que el colegio ya cargó al matricular por
    padrón (nombre/edad/sexo/nivel), en vez de volver a pedirlo como si
    nada se supiera. Deliberadamente SIN el candado de asentimiento (es
    justamente la pantalla que se ve ANTES de aceptarlo) — sí reutiliza los
    mismos candados de validez del enlace que el resto del flujo público.
    """
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido o no existe.")
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido.",
        )
    if inscripcion.estado == "Finalizado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta evaluación ya fue finalizada.",
        )
    return crud.obtener_intake_previo_por_token(db=db, token=token)


@router.get("/examen/{token}/asentimiento-texto", response_model=schemas.AsentimientoInformadoTextoPublico)
@limiter.limit(limite_token("asentimiento_texto"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("asentimiento_texto"), scope=ambito_ip("asentimiento_texto"))
def obtener_asentimiento_texto_examen(request: Request, token: str, db: Session = Depends(get_db)):
    """El texto de asentimiento informado que le corresponde a ESTA
    inscripción (propio de su institución, o el global si no tiene uno
    configurado) — reemplaza la constante fija que antes vivía hardcodeada
    en el frontend (ver docs/gaps-pendientes.md). Deliberadamente SIN el
    candado de asentimiento (es la pantalla que se ve ANTES de aceptarlo),
    mismo criterio que /intake."""
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido o no existe.")
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido.",
        )
    # 🆕 El modelo del NIVEL del alumno, si su colegio definió uno (si no,
    # el general del colegio, y si no, el global).
    texto = crud.resolver_asentimiento_texto_activo(
        db, evaluacion.institucion_id, crud.nivel_educativo_de_inscripcion(db, inscripcion),
    )
    if not texto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un texto de asentimiento informado configurado todavía. Avisa a tu colegio.",
        )
    return texto


@router.get("/asentimiento-textos", response_model=List[schemas.AsentimientoInformadoTextoResponse])
def listar_asentimiento_textos(
    institucion_id: Optional[int] = None,
    tipo_texto: Optional[str] = Query(default=None, pattern="^(apoderado|asentimiento)$"),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Historial completo (activas e inactivas) del texto de asentimiento
    informado de una institución -- o de la versión GLOBAL si se omite
    institucion_id (solo superadmin puede pedirla explícitamente, mismo
    candado que el POST de abajo)."""
    if institucion_id is None:
        if usuario_actual.rol != "superadmin":
            raise HTTPException(status_code=403, detail="Solo superadmin puede ver el historial de la versión global.")
    elif usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el historial de otro colegio.")
    return crud.listar_versiones_asentimiento_texto(db, institucion_id, tipo_texto)


@router.post("/asentimiento-textos", response_model=schemas.AsentimientoInformadoTextoResponse)
def crear_asentimiento_texto(
    datos: schemas.AsentimientoInformadoTextoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """Crea una nueva versión del texto de asentimiento informado y
    desactiva la anterior del mismo ámbito -- propia de una institución
    (su propio admin, o superadmin) o GLOBAL (institucion_id=None en el
    body, solo superadmin: afecta a cualquier institución que no tenga su
    propia versión activa). Nunca edita una versión ya existente -- ver
    AsentimientoInformadoTexto en models.py."""
    if datos.institucion_id is None:
        if usuario_actual.rol != "superadmin":
            raise HTTPException(status_code=403, detail="Solo superadmin puede editar el texto global.")
    elif usuario_actual.rol != "superadmin" and datos.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes configurar el texto de otro colegio.")
    # 🆕 Un modelo por nivel: el nivel tiene que ser de ESA institución (y
    # nunca hay un texto global por nivel — mismo CHECK en la base).
    if datos.nivel_educativo_id is not None:
        if datos.institucion_id is None:
            raise HTTPException(status_code=400, detail="Un modelo por nivel educativo necesita una institución.")
        nivel = db.query(superadmin_models.NivelEducativo).filter(
            superadmin_models.NivelEducativo.id == datos.nivel_educativo_id,
        ).first()
        if not nivel or nivel.institucion_id != datos.institucion_id:
            raise HTTPException(status_code=404, detail="Nivel educativo no encontrado en esta institución.")
    return crud.crear_version_asentimiento_texto(
        db, datos.institucion_id, datos.contenido, usuario_actual.id,
        tipo_texto=datos.tipo_texto, nivel_educativo_id=datos.nivel_educativo_id,
    )


def _persona_del_mismo_colegio(db: Session, persona_id: int, usuario_actual):
    persona = db.query(superadmin_models.Persona).filter(superadmin_models.Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver datos de un estudiante de otro colegio.")
    return persona


@router.get("/modelos-consentimiento/vigente", response_model=schemas.TextoConsentimientoVigente)
def ver_modelo_consentimiento_vigente(
    persona_id: int,
    tipo_texto: str = Query(pattern="^(apoderado|asentimiento)$"),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🆕 El modelo de consentimiento/asentimiento que le corresponde HOY a
    un alumno (su nivel → general del colegio → global), para mostrarlo al
    registrar su consentimiento en la ficha. A diferencia del historial
    (/asentimiento-textos, solo administrativo), esto lo necesita quien
    registra — el staff clínico. 404 si el colegio no configuró ninguno."""
    persona = _persona_del_mismo_colegio(db, persona_id, usuario_actual)
    nivel_id = crud.nivel_educativo_actual_de_persona(db, persona.id)
    texto, origen = crud.resolver_texto_consentimiento_activo(db, persona.institucion_id, tipo_texto, nivel_id)
    if not texto:
        raise HTTPException(status_code=404, detail="Tu colegio todavía no configuró este modelo.")
    return {
        "id": texto.id,
        "tipo_texto": texto.tipo_texto,
        "version": texto.version,
        "contenido": texto.contenido,
        "nivel_educativo_id": texto.nivel_educativo_id,
        "origen": origen,
    }


@router.get("/modelos-consentimiento/pdf")
def descargar_modelo_consentimiento_pdf(
    persona_id: int,
    tipo_texto: str = Query(pattern="^(apoderado|asentimiento)$"),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🆕 El modelo vigente del alumno como PDF para imprimir y firmar, con
    sus datos ya completados (ver core/pdf_consentimiento.py). No registra
    nada: el consentimiento se registra aparte, y el escaneado firmado se
    sube como su evidencia."""
    from core.pdf_consentimiento import fecha_larga, generar_pdf_modelo_consentimiento

    persona = _persona_del_mismo_colegio(db, persona_id, usuario_actual)
    nivel_id, ubicacion = crud.ubicacion_academica_actual(db, persona.id)
    texto, _ = crud.resolver_texto_consentimiento_activo(db, persona.institucion_id, tipo_texto, nivel_id)
    if not texto:
        raise HTTPException(status_code=404, detail="Tu colegio todavía no configuró este modelo.")
    institucion = db.query(instituciones_models.Institucion).filter(
        instituciones_models.Institucion.id == persona.institucion_id,
    ).first()
    nombre_nivel = ubicacion.split(" · ")[0] if ubicacion else None
    pdf = generar_pdf_modelo_consentimiento({
        "tipo_texto": texto.tipo_texto,
        "version": texto.version,
        "contenido": texto.contenido,
        "institucion_nombre": institucion.nombre if institucion else "",
        "alumno_nombre": f"{persona.nombres} {persona.apellidos}",
        "alumno_documento": persona.documento_identidad,
        "nivel": nombre_nivel,
        "grado_seccion": ubicacion,
        "fecha_texto": fecha_larga(datetime.now(timezone.utc).date()),
    })
    prefijo = "consentimiento" if tipo_texto == "apoderado" else "asentimiento"
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{prefijo}_{persona.id}.pdf"'},
    )


@router.post("/comenzar-test/{token}", response_model=schemas.InscripcionResponse)
@limiter.limit(limite_token("comenzar"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("comenzar"), scope=ambito_ip("comenzar"))
def validar_y_comenzar_evaluacion(
    token: str,
    datos: schemas.RegistroAlumnoDemograficos,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    El alumno abre su Link Mágico, escribe sus datos sociodemográficos y,
    si el token es válido, se le autoriza y se bloquea el acceso para otros.

    🏛️ B-11 — Es el momento en el que el alumno acepta el consentimiento, así
    que aquí se capturan la fecha y la IP: son los únicos datos de auditoría
    que el contexto HTTP puede aportar, y hasta ahora las columnas existían
    pero nadie las escribía.
    """
    # 🔁 C-5 — Antes esta ruta solo aceptaba inscripciones en "Pendiente": si el
    # alumno recargaba la página o se le cortaba la conexión, el enlace ya
    # estaba "En Progreso" y recibía un 400 ("este link ya caducó"). Quedaba
    # fuera del examen para siempre. Ahora cada estado recibe su respuesta:
    #
    #   Pendiente     -> se registra y comienza            (200)
    #   En Progreso   -> se REANUDA sin perder nada        (200)
    #   Finalizado    -> protegido contra reenvíos         (409)
    #   Campaña vencida                                    (410)
    #   Inscripción eliminada/anonimizada                  (410)
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido o no existe.")

    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido.",
        )

    if inscripcion.estado == "Finalizado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta evaluación ya fue finalizada. No se puede volver a rendir.",
        )

    # Mismo candado que el resto de rutas del examen: sin consentimiento vigente
    # de ESTA institución no se abre el examen, tampoco al reanudar.
    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio.",
        )

    if not datos.acepta_terminos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes aceptar el consentimiento informado para comenzar la evaluación.",
        )

    # 🆕 Informante — algunas pruebas reales (NICHQ Vanderbilt, SDQ, RCADS,
    # SCARED) las responde un padre/madre o un docente ACERCA del estudiante,
    # no el propio estudiante. `inscripcion.informante_tipo` es el snapshot
    # tomado al matricular (ver matricular_roster_en_campana); cuando no es
    # autorreporte, se exige saber quién efectivamente está respondiendo —
    # para el caso de siempre (informante_tipo='estudiante') esto nunca se
    # evalúa y el comportamiento es idéntico al de antes de este campo.
    if inscripcion.informante_tipo != models.INFORMANTE_ESTUDIANTE and not (datos.informante_nombre or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Esta evaluación debe completarla un(a) "
                f"{'padre/madre o apoderado' if inscripcion.informante_tipo == models.INFORMANTE_PADRE_MADRE else 'docente'} "
                "del estudiante: indica el nombre de quien responde en 'informante_nombre'."
            ),
        )

    inscripcion = crud.validar_y_registrar_alumno(
        db=db, token=token, datos=datos, ip_asentimiento=ip_del_cliente(request),
        institucion_id=evaluacion.institucion_id,
    )
    if not inscripcion:
        raise HTTPException(status_code=400, detail="No se pudo iniciar la evaluación con este enlace.")
    return inscripcion


@router.get("/examen/{token}/progreso", response_model=schemas.ProgresoExamenResponse)
@limiter.limit(limite_token("progreso"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("progreso"), scope=ambito_ip("progreso"))
def obtener_progreso_examen(request: Request, token: str, db: Session = Depends(get_db)):
    """🔁 C-5 — Respuestas ya guardadas, para que el portal pueda reanudar.

    Sin esto, "reanudar" solo significaba poder seguir enviando: el alumno
    no veía qué había contestado. Devuelve pares (pregunta, opción) — o,
    para un ítem Pregunta.tipo_respuesta='numerico', los números que el
    propio alumno escribió — y NUNCA puntajes ni la clave de corrección,
    así que no revela nada que el alumno no haya elegido/escrito él mismo.
    """
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido o no existe.")
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido.",
        )
    if inscripcion.estado == "Finalizado":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Esta evaluación ya fue finalizada.",
        )
    if not inscripcion.acepto_asentimiento:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes aceptar el asentimiento informado antes de acceder a la evaluación.",
        )
    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio.",
        )

    respuestas = db.query(
        models.RespuestaAlumno.pregunta_id,
        models.RespuestaAlumno.opcion_id,
        models.RespuestaAlumno.respuesta_numerica,
    ).filter(
        models.RespuestaAlumno.inscripcion_id == inscripcion.id
    ).order_by(models.RespuestaAlumno.pregunta_id).all()

    return {
        "estado": inscripcion.estado,
        "respuestas": [
            {"pregunta_id": p, "opcion_id": o, "respuesta_numerica": rn}
            for p, o, rn in respuestas
        ],
    }

# ==========================================
# RUTA PARA RENDERIZAR EL EXAMEN EN VIVO
# ==========================================
@router.get("/examen/{token}/preguntas", response_model=List[schemas.PreguntaExamen])
@limiter.limit(limite_token("preguntas"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("preguntas"), scope=ambito_ip("preguntas"))
def cargar_examen_en_vivo(request: Request, token: str, db: Session = Depends(get_db)):
    """
    El frontend web usa esta ruta para pintar la interfaz del alumno. 
    Solo requiere el Link Mágico y le devuelve el examen completo.
    """
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="El link de evaluación es inválido o no existe.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    # 🔒 CANDADO 1: Verificar Asentimiento Informado del propio estudiante (Ley 29733)
    if not inscripcion.acepto_asentimiento:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes aceptar el asentimiento informado antes de acceder a la evaluación."
        )

    # 🔒 CANDADO 1.5: Verificar si el consentimiento fue revocado globalmente
    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio."
        )

    # 🔒 CANDADO 2: Expiración por Fecha Límite de Evaluación/Campaña
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido."
        )

    preguntas = crud.obtener_preguntas_por_token(db=db, token=token)
    if preguntas is None:
        raise HTTPException(status_code=404, detail="No se pudieron recuperar las preguntas para esta evaluación.")
        
    return preguntas

@router.get("/campanas/{evaluacion_id}/dashboard", response_model=schemas.DashboardCampanaResponse)
def ver_dashboard_de_campana(
    evaluacion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Devuelve el resumen agregado de resultados de todo un salón/campaña."""
    dashboard = crud.obtener_dashboard_campana(db=db, evaluacion_id=evaluacion_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")

    # 🔒 CANDADO: mismo patrón de siempre
    if usuario_actual.rol != "superadmin" and dashboard["institucion_id"] != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes ver el dashboard de una campaña que no es de tu colegio."
        )

    # 🔒 Remediación de permisos, paso 5 — colegio ve participación/avance,
    # nunca el diagnóstico puntual por alumno (mismo criterio que ficha-completa).
    if usuario_actual.rol == "colegio":
        dashboard = crud.redactar_resultados_dashboard_campana(dashboard)
    return dashboard


@router.get("/dashboard/academico", response_model=schemas.DashboardAcademicoResponse)
def ver_dashboard_academico(
    prueba_id: int,
    seccion_id: Optional[int] = None,
    grado_id: Optional[int] = None,
    # 🆕 Ámbito "todo el colegio" (sesión 2026-10-25, docs/gaps-pendientes.md)
    # — opcional incluso para un no-superadmin: si no lo manda, se asume su
    # propia institución (mismo criterio que GET /casos-pendientes). Un
    # superadmin SÍ debe mandarlo explícito, porque no tiene una
    # institución propia de la que asumir.
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Resumen de UNA prueba para un salón, un grado o la institución
    completa — cruza todas las campañas en las que se aplicó, a diferencia
    del dashboard de campaña (una sola). Como mucho uno de `seccion_id`/
    `grado_id`/`institucion_id`; si no se manda ninguno, se asume la
    institución propia del caller (nunca la de un superadmin). Ver
    crud.obtener_dashboard_academico."""
    especificados = sum(x is not None for x in (seccion_id, grado_id, institucion_id))
    if especificados > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pasa como máximo uno de seccion_id, grado_id o institucion_id, nunca varios juntos.",
        )
    if especificados == 0:
        if usuario_actual.rol == "superadmin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Como superadmin, especifica institucion_id, seccion_id o grado_id.",
            )
        institucion_id = usuario_actual.institucion_id

    dashboard = crud.obtener_dashboard_academico(
        db=db, prueba_id=prueba_id, seccion_id=seccion_id, grado_id=grado_id, institucion_id=institucion_id,
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="Prueba, salón, grado o institución no encontrados.")

    # 🔒 Mismo candado multi-tenant que el resto de los dashboards.
    if usuario_actual.rol != "superadmin" and dashboard["institucion_id"] != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes ver el dashboard académico de otro colegio.",
        )

    # 🔒 Mismo criterio de redacción que el dashboard de campaña — colegio ve
    # participación/avance, nunca el diagnóstico puntual por alumno. La
    # misma función sirve aquí sin cambios: ambas formas comparten
    # `alumnos[].resultados`.
    if usuario_actual.rol == "colegio":
        dashboard = crud.redactar_resultados_dashboard_campana(dashboard)
    return dashboard


@router.get("/dashboard/academico/tendencia", response_model=schemas.TendenciaSeccionResponse)
def ver_tendencia_seccion(
    prueba_id: int,
    seccion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Evolución de UN salón a través de todas las campañas en que se
    aplicó `prueba_id`, ordenadas por fecha — a diferencia de
    `/dashboard/academico` (que funde todo en un agregado único), esto
    responde "¿mejoró o empeoró entre marzo y agosto?". Ver
    crud.obtener_tendencia_seccion. Deliberadamente sin `grado_id` (ver
    docstring de esa función)."""
    tendencia = crud.obtener_tendencia_seccion(db=db, prueba_id=prueba_id, seccion_id=seccion_id)
    if not tendencia:
        raise HTTPException(status_code=404, detail="Prueba o salón no encontrado.")

    if usuario_actual.rol != "superadmin" and tendencia["institucion_id"] != usuario_actual.institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes ver la tendencia de otro colegio.",
        )

    # 🔒 Mismo criterio que el resto de dashboards: 'colegio' ve participación/
    # agregados, nunca el diagnóstico puntual por alumno. Esta vista nunca
    # expone `alumnos[]` en absoluto (solo resumen_estadistico por punto), así
    # que no hay nada que redactar — a diferencia de los otros dos dashboards.
    return tendencia


@router.get("/dashboard/academico/exportar-excel")
def exportar_dashboard_academico_excel(
    prueba_id: int,
    seccion_id: Optional[int] = None,
    grado_id: Optional[int] = None,
    institucion_id: Optional[int] = None,  # 🆕 ver ver_dashboard_academico — mismo criterio
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual),
):
    """Mismo Excel que `/campanas/{id}/exportar-excel` (incluida la hoja
    "Resumen estadístico" — ver generar_excel_dashboard), pero para el
    dashboard por salón/grado/institución, que hasta ahora no tenía ninguna
    forma de exportarse. Mismas reglas que `ver_dashboard_academico` de
    arriba: como mucho uno de seccion_id/grado_id/institucion_id, mismo
    candado multi-tenant, misma redacción para 'colegio'."""
    especificados = sum(x is not None for x in (seccion_id, grado_id, institucion_id))
    if especificados > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pasa como máximo uno de seccion_id, grado_id o institucion_id, nunca varios juntos.",
        )
    if especificados == 0:
        if usuario_actual.rol == "superadmin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Como superadmin, especifica institucion_id, seccion_id o grado_id.",
            )
        institucion_id = usuario_actual.institucion_id

    dashboard = crud.obtener_dashboard_academico(
        db=db, prueba_id=prueba_id, seccion_id=seccion_id, grado_id=grado_id, institucion_id=institucion_id,
    )
    if not dashboard:
        raise HTTPException(status_code=404, detail="Prueba, salón, grado o institución no encontrados.")
    if usuario_actual.rol != "superadmin" and dashboard["institucion_id"] != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes exportar el dashboard académico de otro colegio.")

    if usuario_actual.rol == "colegio":
        dashboard = crud.redactar_resultados_dashboard_campana(dashboard)
    buffer = crud.generar_excel_dashboard(dashboard)
    nombre_ambito = re.sub(r"[^A-Za-z0-9]+", "_", dashboard["ambito"]["nombre"]).strip("_")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="resultados_{prueba_id}_{nombre_ambito}.xlsx"'}
    )


@router.post("/campanas/{evaluacion_id}/matricular-roster", response_model=schemas.MatriculaRosterResponse)
def matricular_roster(
    evaluacion_id: int,
    persona_ids: List[int],
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Genera links nombrados para una lista de estudiantes ya registrados en el padrón."""
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == evaluacion_id).first()
    if not evaluacion:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")

    # 🔒 CANDADO: mismo patrón de siempre
    if usuario_actual.rol != "superadmin" and evaluacion.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes matricular alumnos en una campaña que no es de tu colegio.")

    return crud.matricular_roster_en_campana(db=db, evaluacion_id=evaluacion_id, persona_ids=persona_ids)

@router.get("/pruebas/", response_model=List[schemas.PruebaResponse])
def listar_pruebas_disponibles(
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """Catálogo público + las pruebas privadas creadas por el propio colegio (solo activas)."""
    # 1. Filtro base: siempre deben estar en activa == True
    query = db.query(models.Prueba).filter(models.Prueba.activa == True)
    
    # 2. Filtro según el rol del usuario
    if usuario_actual.rol != "superadmin":
        query = query.filter(
            (models.Prueba.institucion_id == None) | (models.Prueba.institucion_id == usuario_actual.institucion_id)
        )
        # 🆕 Catálogo genérico: una prueba interna (visible_para_clientes=False,
        # p. ej. de validación técnica) nunca aparece en el catálogo de un
        # colegio. Superadmin sigue viendo todo, igual que con el filtro de
        # institución de arriba.
        query = query.filter(models.Prueba.visible_para_clientes == True)

    return query.all()

@router.get("/campanas/{evaluacion_id}/exportar-excel")
def exportar_dashboard_excel(
    evaluacion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    dashboard = crud.obtener_dashboard_campana(db=db, evaluacion_id=evaluacion_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="Campaña no encontrada.")
    if usuario_actual.rol != "superadmin" and dashboard["institucion_id"] != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No autorizado.")

    # 🔒 Remediación de permisos, paso 5 — mismo dashboard que el JSON de
    # arriba, así que la misma redacción aplica antes de volcarlo a Excel.
    if usuario_actual.rol == "colegio":
        dashboard = crud.redactar_resultados_dashboard_campana(dashboard)
    buffer = crud.generar_excel_dashboard(dashboard)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="resultados_{evaluacion_id}.xlsx"'}
    )

# ==========================================
# DASHBOARD CONSOLIDADO POR INSTITUCIÓN
# ==========================================
# 📝 Fase 4 — esta sección se llamaba "ENDPOINTS DESACTIVADOS TEMPORALMENTE
# (se reactivarán cuando definamos ProcesoEvaluativo y SesionSeguimiento)".
# Ambos endpoints llevan tiempo activos y en uso (ver obtener_dashboard_proceso
# y obtener_casos_pendientes_de_seguimiento en crud.py); el comentario había
# quedado desactualizado y podía llevar a alguien a creer que no funcionaban.

@router.get("/procesos/dashboard")
def ver_dashboard_proceso(
    institucion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    if usuario_actual.rol != "superadmin" and institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No autorizado.")
        
    dashboard = crud.obtener_dashboard_proceso(db=db, institucion_id=institucion_id)
    if not dashboard:
        raise HTTPException(status_code=404, detail="No hay evaluaciones para esta institución.")
    # 🔒 Remediación de permisos, paso 5 — mismo criterio que el dashboard de campaña.
    if usuario_actual.rol == "colegio":
        dashboard = crud.redactar_resultados_dashboard_institucional(dashboard)
    return dashboard

@router.get("/casos-pendientes")
def ver_casos_pendientes(
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """
    Retorna la lista de alertas/casos que requieren seguimiento.

    🔒 Es el worklist clínico del psicólogo (alumnos en riesgo pendientes de
    revisión) — mismo nivel de sensibilidad que `es_alerta`/`informe_liberado`
    en el resto del sistema, `colegio` no debe verlo.
    """
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Como superadmin, debes especificar ?institucion_id="
            )
    else:
        institucion_id = usuario_actual.institucion_id

    return crud.obtener_casos_pendientes_de_seguimiento(db=db, institucion_id=institucion_id)


@router.get("/inicio/resumen")
def ver_resumen_inicio(
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🆕 Resumen operativo del mes para el dashboard de aterrizaje
    (sesión 2026-10-25, rediseño de `/inicio` a pedido del usuario) — total
    de alumnos del padrón, pruebas finalizadas y alumnos con al menos una
    sesión de seguimiento este mes calendario, y campañas activas ahora
    mismo. Mismo criterio de `institucion_id` que `/casos-pendientes`
    (obligatorio para superadmin, implícito para el resto).

    🔒 `requerir_staff_clinico`: `estudiantes_con_seguimiento_mes` cuenta
    sesiones de seguimiento clínico (mismo nivel de sensibilidad que
    `casos-pendientes`, aunque acá solo viaje un número, nunca nombres) —
    'colegio' no debe verlo, igual que el resto de este worklist.
    """
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Como superadmin, debes especificar ?institucion_id=",
            )
    else:
        institucion_id = usuario_actual.institucion_id

    return crud.obtener_resumen_inicio(db=db, institucion_id=institucion_id)


@router.get("/inicio/series")
def ver_series_inicio(
    institucion_id: Optional[int] = None,
    meses: int = Query(default=6, ge=3, le=12),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """🆕 Series mensuales (evaluaciones con/sin alerta, sesiones de
    seguimiento, citas) y avance de campañas activas para los gráficos de
    `/inicio` (sesión 2026-10-30) — ver crud.obtener_series_inicio. Mismo
    candado y mismo criterio de `institucion_id` que `/inicio/resumen`:
    solo números agregados, pero de actividad clínica (alertas, sesiones)."""
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Como superadmin, debes especificar ?institucion_id=",
            )
    else:
        institucion_id = usuario_actual.institucion_id

    return crud.obtener_series_inicio(
        db=db, institucion_id=institucion_id, usuario_id=usuario_actual.id, meses=meses,
    )

# ==========================================
# RUTAS PARA DERECHOS ARCO (LEY 29733 - PASO 3.5)
# ==========================================
@router.delete("/alumnos/{inscripcion_id}/soft-delete", status_code=status.HTTP_200_OK)
def eliminar_alumno_soft(
    inscripcion_id: int,
    request: Request,
    referencia_solicitud: Optional[str] = None,
    db: Session = Depends(get_db),
    # 🔒 B-12: la cuenta genérica "colegio" no debe dar de baja registros
    # clínicos; el psicólogo sí, porque gestiona su propio padrón.
    usuario_actual: auth_models.Usuario = Depends(
        permisos.STAFF_CLINICO
    ),
):
    """
    🔒 Realiza un Soft Delete de la inscripción/registro de un alumno.
    Mantiene las métricas pero oculta el registro activo en la institución.
    Queda anotado en la bitácora ARCO.
    """
    exito = crud.soft_delete_alumno(
        db=db,
        inscripcion_id=inscripcion_id,
        institucion_id=usuario_actual.institucion_id,
        es_superadmin=(usuario_actual.rol == "superadmin"),
        ejecutado_por=usuario_actual,                     # 🏛️ B-12
        ip_solicitante=ip_del_cliente(request),
        referencia_solicitud=referencia_solicitud,
    )
    if not exito:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada o no pertenece a tu institución."
        )
    return {"mensaje": "Registro de alumno desactivado correctamente."}


@router.post("/alumnos/{inscripcion_id}/anonimizar-arco", status_code=status.HTTP_200_OK)
def anonimizar_alumno_derecho_arco(
    inscripcion_id: int,
    request: Request,
    referencia_solicitud: Optional[str] = None,
    db: Session = Depends(get_db),
    # 🔒 B-12: acción IRREVERSIBLE, reservada a quien responde por el colegio.
    usuario_actual: auth_models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO),
):
    """
    🏛️ Ley 29733 - Ejercicio de Derecho ARCO (Cancelación / Oposición).
    Elimina permanentemente nombres y datos identificables del estudiante,
    manteniendo las respuestas anonimizadas para validez psicométrica.

    No es un borrado físico y queda anotado en la bitácora `auditoria_arco`.
    """
    exito = crud.anonimizar_datos_alumno_arco(
        db=db,
        inscripcion_id=inscripcion_id,
        institucion_id=usuario_actual.institucion_id,
        es_superadmin=(usuario_actual.rol == "superadmin"),
        ejecutado_por=usuario_actual,                     # 🏛️ B-12
        ip_solicitante=ip_del_cliente(request),
        referencia_solicitud=referencia_solicitud,
    )
    if not exito:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada o no pertenece a tu institución."
        )
    return {"mensaje": "Los datos identificables del alumno han sido irreversiblemente anonimizados."}

@router.post("/seguimiento/", response_model=schemas.SesionSeguimientoResponse)
def registrar_seguimiento(
    datos: schemas.SesionSeguimientoCreate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    persona = db.query(superadmin_models.Persona).filter(
        superadmin_models.Persona.id == datos.persona_id
    ).first()
    
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
        
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No autorizado.")
        
    return crud.crear_sesion_seguimiento(db, datos, usuario_actual.id, persona.institucion_id)

@router.get("/seguimiento/{persona_id}", response_model=List[schemas.SesionSeguimientoResponse])
def listar_seguimiento_de_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Historial completo de sesiones de seguimiento de un alumno."""
    persona = db.query(superadmin_models.Persona).filter(
        superadmin_models.Persona.id == persona_id
    ).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
    if usuario_actual.rol != "superadmin" and persona.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes ver el seguimiento de un alumno de otro colegio.")
    return crud.obtener_historial_de_persona(db=db, persona_id=persona_id)


@router.patch("/seguimiento/{sesion_id}", response_model=schemas.SesionSeguimientoResponse)
def editar_seguimiento(
    sesion_id: int,
    datos: schemas.SesionSeguimientoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Corrige una nota de sesión ya guardada."""
    sesion = db.query(models.SesionSeguimiento).filter(models.SesionSeguimiento.id == sesion_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión de seguimiento no encontrada.")
    if usuario_actual.rol != "superadmin" and sesion.psicologo_id != usuario_actual.id:
        raise HTTPException(status_code=403, detail="No puedes editar una sesión registrada por otro psicólogo.")
    return crud.actualizar_sesion_seguimiento(db=db, sesion_id=sesion_id, datos=datos)


@router.delete("/seguimiento/{sesion_id}", status_code=status.HTTP_200_OK)
def eliminar_seguimiento(
    sesion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico),
):
    """Borra una nota de sesión creada por error."""
    sesion = db.query(models.SesionSeguimiento).filter(models.SesionSeguimiento.id == sesion_id).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión de seguimiento no encontrada.")
    if usuario_actual.rol != "superadmin" and sesion.psicologo_id != usuario_actual.id:
        raise HTTPException(status_code=403, detail="No puedes eliminar una sesión registrada por otro psicólogo.")
    crud.eliminar_sesion_seguimiento(db=db, sesion_id=sesion_id)
    return {"mensaje": "Sesión de seguimiento eliminada."}
# ==========================================
# ENDPOINTS DE GESTIÓN Y MATRICULACIÓN
# ==========================================

@router.patch("/pruebas/{prueba_id}", response_model=schemas.PruebaResponse)
def editar_prueba(
    prueba_id: int,
    datos: schemas.PruebaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    """
    Permite actualizar parcialmente datos de una prueba (nombre, instrucciones, estado activo, etc.).
    """
    crud.verificar_propiedad_de_prueba(db, prueba_id, usuario_actual)
    prueba_actualizada = crud.actualizar_prueba(db=db, prueba_id=prueba_id, datos=datos)
    if not prueba_actualizada:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
    return prueba_actualizada


@router.get("/baremos/{dimension_id}", response_model=List[schemas.BaremoResponse])
def listar_baremos_de_dimension(
    dimension_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """
    Obtiene la lista de baremos asociados a una dimensión psicométrica específica.
    """
    dimension = db.query(models.Dimension).filter(models.Dimension.id == dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.obtener_baremos_por_dimension(db=db, dimension_id=dimension_id)

@router.get("/examen/{token}/campos-socio", response_model=List[schemas.CampoSociodemograficoResponse])
@limiter.limit(limite_token("campos_socio"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("campos_socio"), scope=ambito_ip("campos_socio"))
def obtener_campos_socio_examen(request: Request, token: str, db: Session = Depends(get_db)):
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Link inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    #   🔒 CANDADO 1: Asentimiento del propio estudiante
    if not inscripcion.acepto_asentimiento:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes aceptar el asentimiento informado antes de acceder a este formulario."
        )

    #   🔒 CANDADO 1.5: Revocación global del consentimiento
    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio."
        )

    #   🔒 CANDADO 2: Expiración por fecha de cierre de campaña
    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido."
        )

    campos = crud.obtener_campos_socio_por_token(db=db, token=token)
    if campos is None:
        raise HTTPException(status_code=404, detail="Link inválido.")
    return campos


@router.post("/examen/{token}/campos-socio", response_model=dict)
@limiter.limit(limite_token("campos_socio"), key_func=clave_por_token)
@limiter.shared_limit(limite_ip("campos_socio"), scope=ambito_ip("campos_socio"))
def guardar_campos_socio_examen(request: Request, token: str, datos: schemas.CamposSocioSubmit, db: Session = Depends(get_db)):
    inscripcion = db.query(models.Inscripcion).filter(models.Inscripcion.token == token).first()
    if not inscripcion:
        raise HTTPException(status_code=404, detail="Link inválido.")

    # 🔒 C-8: un link de una inscripción eliminada o anonimizada deja de servir
    if not crud.inscripcion_esta_activa(inscripcion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ya no está disponible. Contacta a tu colegio.",
        )

    if not inscripcion.acepto_asentimiento:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pueden guardar respuestas sin haber aceptado previamente el asentimiento informado."
        )

    if not crud.consentimiento_vigente_para_inscripcion(db, inscripcion):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El consentimiento informado para este alumno fue revocado. Contacta al colegio."
        )

    evaluacion = db.query(models.Evaluacion).filter(models.Evaluacion.id == inscripcion.evaluacion_id).first()
    if crud.campana_esta_expirada(evaluacion):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Este enlace de evaluación ha expirado debido a que la fecha límite ha concluido."
        )

    resultado = crud.guardar_respuestas_socio(db=db, token=token, respuestas=datos.respuestas)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Link inválido.")
    return resultado

@router.get("/campanas/", response_model=RespuestaPaginada[schemas.EvaluacionResponse])
def listar_campanas(
    institucion_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    """🆕 Paginación real (docs/gaps-pendientes.md) — antes devolvía toda
    campaña creada, sin tope, para siempre."""
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(status_code=400, detail="Como superadmin, especifica ?institucion_id=")
    else:
        # Si no es superadmin, forzamos a que solo vea las campañas de su propia institución
        institucion_id = usuario_actual.institucion_id

    total, items = crud.listar_campanas_de_institucion(
        db=db, institucion_id=institucion_id, skip=skip, limit=limit,
    )
    return {"total": total, "items": items}

@router.get("/pruebas/{prueba_id}/completa", response_model=schemas.PruebaDetalleResponse)
def ver_prueba_completa(
    prueba_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(obtener_usuario_actual)
):
    prueba = db.query(models.Prueba).filter(models.Prueba.id == prueba_id).first()
    if not prueba:
        raise HTTPException(status_code=404, detail="Prueba no encontrada.")
        
    # 🔒 Lectura permitida si es pública, si es del propio colegio, o si eres superadmin
    es_publica = prueba.institucion_id is None
    es_propia = prueba.institucion_id == usuario_actual.institucion_id
    
    if usuario_actual.rol != "superadmin" and not es_publica and not es_propia:
        raise HTTPException(status_code=403, detail="No puedes ver una prueba de otro colegio.")
        
    return crud.obtener_prueba_completa(db=db, prueba_id=prueba_id)

# --- PREGUNTAS ---

@router.patch("/preguntas/{pregunta_id}", response_model=schemas.PreguntaResponse)
def editar_pregunta(
    pregunta_id: int,
    datos: schemas.PreguntaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    pregunta = db.query(models.Pregunta).filter(models.Pregunta.id == pregunta_id).first()
    if not pregunta:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada.")
    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)
    return crud.actualizar_pregunta(db=db, pregunta_id=pregunta_id, datos=datos)

@router.delete("/preguntas/{pregunta_id}", status_code=status.HTTP_200_OK)
def borrar_pregunta(
    pregunta_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    pregunta = db.query(models.Pregunta).filter(models.Pregunta.id == pregunta_id).first()
    if not pregunta:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada.")
    
    # 🔒 Validación de integridad: No borrar si ya hay respuestas de alumnos
    respuestas_existentes = db.query(models.RespuestaAlumno).filter(models.RespuestaAlumno.pregunta_id == pregunta_id).first()
    if respuestas_existentes:
        raise HTTPException(
            status_code=400, 
            detail="No se puede eliminar la pregunta porque ya tiene respuestas guardadas. Desactiva la prueba en su lugar."
        )

    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)
    crud.eliminar_pregunta(db=db, pregunta_id=pregunta_id)
    return {"mensaje": "Pregunta eliminada."}

# --- DIMENSIONES ---

@router.patch("/dimensiones/{dimension_id}", response_model=schemas.DimensionResponse)
def editar_dimension(
    dimension_id: int,
    datos: schemas.DimensionUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    dimension = db.query(models.Dimension).filter(models.Dimension.id == dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.actualizar_dimension(db=db, dimension_id=dimension_id, datos=datos)

@router.delete("/dimensiones/{dimension_id}", status_code=status.HTTP_200_OK)
def borrar_dimension(
    dimension_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    dimension = db.query(models.Dimension).filter(models.Dimension.id == dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    crud.eliminar_dimension(db=db, dimension_id=dimension_id)  # Lanza el 400 internamente si aplica
    return {"mensaje": "Dimensión eliminada."}

# --- DIMENSIONES COMPUESTAS (Dimension.tipo_calculo == 'suma_de_dimensiones') ---

@router.put("/dimensiones/{dimension_id}/componentes", response_model=List[schemas.DimensionComponenteResponse])
def reemplazar_componentes_de_dimension_compuesta(
    dimension_id: int,
    datos: schemas.DimensionComponentesReplace,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    """Reemplazo COMPLETO de qué dimensiones alimentan a esta dimensión
    'suma_de_dimensiones' — ver crud.reemplazar_componentes_de_dimension.
    Cada componente se revalida contra la BD (misma prueba, no es a su vez
    compuesta); nada de lo que mande el cliente se confía ciegamente."""
    dimension = db.query(models.Dimension).filter(models.Dimension.id == dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.reemplazar_componentes_de_dimension(db, dimension_id, datos.componentes)


@router.get("/dimensiones/{dimension_id}/componentes", response_model=List[schemas.DimensionComponenteResponse])
def listar_componentes_de_dimension_compuesta(
    dimension_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    dimension = db.query(models.Dimension).filter(models.Dimension.id == dimension_id).first()
    if not dimension:
        raise HTTPException(status_code=404, detail="Dimensión no encontrada.")
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.listar_componentes_de_dimension(db, dimension_id)

# --- OPCIONES DE RESPUESTA ---

@router.patch("/opciones/{opcion_id}", response_model=schemas.OpcionRespuestaResponse)
def editar_opcion(
    opcion_id: int,
    datos: schemas.OpcionRespuestaUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    opcion = db.query(models.OpcionRespuesta).filter(models.OpcionRespuesta.id == opcion_id).first()
    if not opcion:
        raise HTTPException(status_code=404, detail="Opción no encontrada.")
    pregunta = db.query(models.Pregunta).filter(models.Pregunta.id == opcion.pregunta_id).first()
    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)
    return crud.actualizar_opcion(db=db, opcion_id=opcion_id, datos=datos)

@router.delete("/opciones/{opcion_id}", status_code=status.HTTP_200_OK)
def borrar_opcion(
    opcion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    opcion = db.query(models.OpcionRespuesta).filter(models.OpcionRespuesta.id == opcion_id).first()
    if not opcion:
        raise HTTPException(status_code=404, detail="Opción no encontrada.")
    pregunta = db.query(models.Pregunta).filter(models.Pregunta.id == opcion.pregunta_id).first()
    crud.verificar_propiedad_de_prueba(db, pregunta.prueba_id, usuario_actual)
    crud.eliminar_opcion(db=db, opcion_id=opcion_id)  # Lanza el 400 internamente si aplica
    return {"mensaje": "Opción eliminada."}

# --- BAREMOS ---

@router.patch("/baremos/{baremo_id}", response_model=schemas.BaremoResponse)
def editar_baremo(
    baremo_id: int,
    datos: schemas.BaremoUpdate,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    baremo = db.query(models.Baremo).filter(models.Baremo.id == baremo_id).first()
    if not baremo:
        raise HTTPException(status_code=404, detail="Baremo no encontrado.")
    dimension = db.query(models.Dimension).filter(models.Dimension.id == baremo.dimension_id).first()
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    return crud.actualizar_baremo(db=db, baremo_id=baremo_id, datos=datos)

@router.delete("/baremos/{baremo_id}", status_code=status.HTTP_200_OK)
def borrar_baremo(
    baremo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: auth_models.Usuario = Depends(requerir_staff_clinico)
):
    baremo = db.query(models.Baremo).filter(models.Baremo.id == baremo_id).first()
    if not baremo:
        raise HTTPException(status_code=404, detail="Baremo no encontrado.")
    dimension = db.query(models.Dimension).filter(models.Dimension.id == baremo.dimension_id).first()
    crud.verificar_propiedad_de_prueba(db, dimension.prueba_id, usuario_actual)
    resultado = crud.eliminar_baremo(db=db, baremo_id=baremo_id)
    if resultado == "desactivado":
        return {"mensaje": "Este baremo ya tenía diagnósticos asociados: se desactivó en vez de borrarse."}
    return {"mensaje": "Baremo eliminado."}
