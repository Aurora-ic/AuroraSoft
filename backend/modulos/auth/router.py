from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from core import permisos
from core.deps import obtener_usuario_actual
from core.url_segura import UrlNoPermitida, validar_url_logo
from core.subida_archivos import leer_archivo_con_limite
from core.branding import TAMANO_MAXIMO_IMAGEN_BYTES
from modulos.instituciones import models as instituciones_models
from core.database import get_db
from datetime import timedelta

from fastapi.responses import JSONResponse

from core import sesiones
from core.security import ACCESS_TOKEN_EXPIRE_MINUTES, verify_password, create_access_token
from core.limiter import limiter  # 👈 Evita importación circular
from core import captcha
from . import models, schemas, crud
from core.email_service import enviar_correo_recuperacion
from fastapi import Request
router = APIRouter(prefix="/auth", tags=["Autenticación y Seguridad"])


@router.post("/registro", response_model=schemas.UsuarioResponse)
@limiter.limit("5/minute")
def registrar_usuario(
    request: Request,  # 👈 Requerido por el limiter para leer la IP
    usuario: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO)
):
    # Un "admin" de colegio solo puede crear cuentas DE SU PROPIO colegio
    if usuario_actual.rol != "superadmin":
        if usuario.institucion_id != usuario_actual.institucion_id:
            raise HTTPException(status_code=403, detail="No puedes crear usuarios para otro colegio.")
        if usuario.rol in ("admin", "superadmin"):
            raise HTTPException(status_code=403, detail="No puedes asignar ese rol.")
            
    return crud.crear_usuario(db=db, usuario=usuario)


def _ip_de(request: Request) -> Optional[str]:
    # Misma fuente que la clave del rate limit (core/limiter.py).
    return request.client.host if request.client else None


@router.get("/captcha", response_model=schemas.CaptchaResponse)
@limiter.limit("30/minute")
def obtener_captcha(request: Request, email: Optional[str] = None):
    """🆕 Desafío de imagen para el login (ver core/captcha.py). Público a
    propósito: se pide ANTES de tener sesión. Con
    LOGIN_CAPTCHA_OBLIGATORIO=false responde `habilitado=false` y la pantalla
    de login oculta el campo.

    🆕 Adaptativo: `habilitado` solo es true si esta IP (o el `email`, si se
    manda) acumula contraseñas fallidas recientes — ver
    captcha.captcha_requerido. La pantalla lo vuelve a consultar tras cada
    intento fallido."""
    if not captcha.captcha_requerido(_ip_de(request), email):
        return {"habilitado": False, "captcha_id": None, "imagen": None}
    return {"habilitado": True, **captcha.generar_captcha()}


@router.post("/login", response_model=schemas.Token)
@limiter.limit("5/minute")
def iniciar_sesion(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(), 
    captcha_id: Optional[str] = Form(None),
    captcha_respuesta: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Ruta de Login con Rate Limiting (máximo 5 intentos por minuto).
    Nota: FastAPI usa un estándar donde el email se envía en un campo
    llamado 'username'.

    🆕 Captcha: se valida ANTES de mirar la contraseña — si fuera después,
    un script podría seguir probando claves y solo "fallar el captcha" sin
    que eso le costara nada. Cada captcha es de un solo uso.
    """
    ip = _ip_de(request)
    if captcha.captcha_requerido(ip, form_data.username):
        try:
            captcha.verificar_captcha(captcha_id, captcha_respuesta)
        except captcha.CaptchaInvalido as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    usuario = crud.obtener_usuario_por_email(db, email=form_data.username)

    if not usuario or not verify_password(form_data.password, usuario.hashed_password):
        captcha.registrar_fallo(ip, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Esta cuenta está desactivada.",
        )

    # 🆕 (sesión 2026-11-02) Sesión de servidor + cookies httpOnly (ver
    # core/sesiones.py). Si el navegador ya traía una sesión (p. ej. se
    # desbloquea la pantalla por inactividad), esa se revoca: la nueva la
    # reemplaza.
    _revocar_sesion_de_cookie(db, request, "reemplazada")
    token_renovacion = sesiones.nuevo_token_renovacion()
    ahora = sesiones.ahora_utc()
    sesion = models.SesionUsuario(
        id=sesiones.nuevo_id_sesion(),
        usuario_id=usuario.id,
        hash_renovacion=sesiones.hash_renovacion(token_renovacion),
        token_version=usuario.token_version or 0,
        creada_en=ahora,
        ultimo_uso=ahora,
        expira_en=ahora + timedelta(hours=sesiones.SESION_HORAS),
        ip=ip,
        agente=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(sesion)
    db.commit()

    access_token = _emitir_acceso(usuario, sesion.id)
    sesiones.fijar_cookies(response, access_token, token_renovacion, ACCESS_TOKEN_EXPIRE_MINUTES)
    captcha.limpiar_fallos(ip, form_data.username)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "sesion": _sesion_publica(usuario),
        "expira_en": int(ACCESS_TOKEN_EXPIRE_MINUTES * 60),
    }


def _sesion_publica(usuario: models.Usuario) -> dict:
    return {"email": usuario.email, "rol": usuario.rol, "institucion_id": usuario.institucion_id}


def _emitir_acceso(usuario: models.Usuario, sid: str) -> str:
    return create_access_token(data={
        "sub": usuario.email,
        "rol": usuario.rol,
        "institucion_id": usuario.institucion_id,  # None para superadmin
        # 🔑 C-4 — versión de credenciales: cambia al resetear la contraseña y
        # deja sin efecto todos los tokens emitidos antes.
        "tv": usuario.token_version or 0,
        # 🆕 (sesión 2026-11-02) sesión de servidor (models.SesionUsuario).
        "sid": sid,
    })


def _sesion_de_cookie(db: Session, request: Request, bloquear_fila: bool = False):
    token = request.cookies.get(sesiones.COOKIE_RENOVACION)
    if not token:
        return None
    q = db.query(models.SesionUsuario).filter(
        models.SesionUsuario.hash_renovacion == sesiones.hash_renovacion(token)
    )
    if bloquear_fila:
        q = q.with_for_update().populate_existing()
    return q.first()


def _revocar_sesion_de_cookie(db: Session, request: Request, motivo: str) -> bool:
    sesion = _sesion_de_cookie(db, request, bloquear_fila=True)
    if sesion is None or sesion.revocada_en is not None:
        db.rollback()
        return False
    sesion.revocada_en = sesiones.ahora_utc()
    sesion.motivo_revocacion = motivo
    db.commit()
    return True


def _exigir_csrf(request: Request) -> None:
    # Estos tres endpoints se autentican SOLO por cookie: el navegador la
    # adjunta sola, así que sin esta cabecera un sitio ajeno podría
    # dispararlos (core/sesiones.py).
    if not sesiones.peticion_csrf_valida(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Falta la cabecera de seguridad de la aplicación.")


def _respuesta_401_sin_cookies(detalle: str) -> JSONResponse:
    # Una HTTPException perdería las cabeceras Set-Cookie de `response`:
    # se arma la respuesta a mano para que el navegador borre las cookies.
    respuesta = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detalle})
    sesiones.borrar_cookies(respuesta)
    return respuesta


@router.post("/renovar", response_model=schemas.RenovacionResponse)
@limiter.limit("60/minute")
def renovar_sesion(request: Request, response: Response, db: Session = Depends(get_db)):
    """🆕 (sesión 2026-11-02) Emite un token de acceso nuevo con la cookie de
    renovación. Falla (401, y borra las cookies) si la sesión se cerró, se
    bloqueó por inactividad, venció, lleva SESION_INACTIVIDAD_MINUTOS sin
    renovarse, o la contraseña cambió. Público por `Depends` a propósito:
    el acceso pudo haber vencido — lo que autentica es la cookie."""
    _exigir_csrf(request)
    sesion = _sesion_de_cookie(db, request, bloquear_fila=True)
    usuario = db.query(models.Usuario).filter(models.Usuario.id == sesion.usuario_id).first() if sesion else None
    if sesiones.motivo_renovacion_invalida(sesion, usuario) is not None:
        db.rollback()
        return _respuesta_401_sin_cookies("Tu sesión terminó. Vuelve a iniciar sesión.")
    sesion.ultimo_uso = sesiones.ahora_utc()
    db.commit()
    sesiones.fijar_cookies(response, _emitir_acceso(usuario, sesion.id), None, ACCESS_TOKEN_EXPIRE_MINUTES)
    return {"sesion": _sesion_publica(usuario), "expira_en": int(ACCESS_TOKEN_EXPIRE_MINUTES * 60)}


@router.post("/bloquear", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def bloquear_sesion(request: Request, db: Session = Depends(get_db)):
    """🆕 (sesión 2026-11-02) La pantalla se bloqueó por inactividad: la
    sesión queda bloqueada EN EL SERVIDOR. Ningún acceso de esta sesión vale
    hasta desbloquear con la contraseña (un login nuevo, que la reemplaza).
    Antes el bloqueo era solo una capa en el navegador. Idempotente."""
    _exigir_csrf(request)
    sesion = _sesion_de_cookie(db, request, bloquear_fila=True)
    if sesion is not None and sesion.bloqueada_en is None and sesion.revocada_en is None:
        sesion.bloqueada_en = sesiones.ahora_utc()
        db.commit()
    else:
        db.rollback()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cerrar-sesion", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
def cerrar_sesion(request: Request, db: Session = Depends(get_db)):
    """🆕 (sesión 2026-11-02) Revoca la sesión en el servidor y borra las
    cookies. Antes cerrar sesión solo borraba el token del navegador, que
    seguía valiendo 7 días. Idempotente: sin sesión, igual borra las cookies."""
    _exigir_csrf(request)
    _revocar_sesion_de_cookie(db, request, "cierre_sesion")
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    sesiones.borrar_cookies(respuesta)
    return respuesta


@router.get("/me", response_model=schemas.UsuarioResponse)
def obtener_sesion_actual(usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
    """
    🆕 Cierra el gap documentado en docs/gaps-pendientes.md: hasta ahora el
    frontend decodificaba el JWT localmente (ver contexts/AuthContext.tsx)
    sin ningún round-trip al backend para confirmar quién es el usuario.
    `obtener_usuario_actual` ya hace exactamente ese trabajo (decodifica,
    valida token_version, valida licencia de la institución) para proteger
    cualquier otro endpoint — este solo expone su resultado tal cual, sin
    lógica propia. Sirve también para que el frontend detecte una cuenta
    desactivada/un cambio de contraseña en el acto, en vez de solo cuando
    la próxima petición a otro endpoint falle.
    """
    return usuario_actual


@router.post("/solicitar-recuperacion")
@limiter.limit("3/minute")  # 🔒 PASO 3.3: Límite de 3 peticiones por minuto por IP
def solicitar_recuperacion(
    request: Request,  # 🟢 OBLIGATORIO para slowapi: extrae la IP del cliente
    datos: schemas.SolicitudRecuperacion,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    🔒 FIX: 'email' ahora viaja en el body (schemas.SolicitudRecuperacion),
    no como query param. Protegido con Rate Limiting (3 req/min).

    🆕 Solo cuentas SUPERADMIN activas reciben el enlace (decisión del
    equipo: el superadmin es la cuenta de AuroraSoft con correo real; a
    admin/psicólogo/colegio les cambia la clave un administrador). Para el
    resto la respuesta es idéntica y no se envía nada — no se delata qué
    correos existen ni qué rol tienen. /resetear-password no repite el filtro
    a propósito: esta es la única vía que emite tokens.
    """
    usuario = crud.obtener_usuario_por_email(db, datos.email)
    if usuario and usuario.rol == "superadmin" and usuario.activo:
        token_obj = crud.crear_token_recuperacion(db, usuario.id)
        # ✉️ C-14 — El SMTP ya no bloquea al worker: antes una conversación
        # SMTP lenta (varios segundos) retenía el hilo durante toda la
        # petición. Además la respuesta tarda lo mismo exista o no la cuenta,
        # así que el tiempo de respuesta tampoco delata qué correos están
        # registrados.
        background_tasks.add_task(enviar_correo_recuperacion, usuario.email, token_obj.token)

    # Mismo mensaje exista o no el correo — no confirmamos si un email está registrado
    return {
        "mensaje": "Si el correo existe en nuestro sistema, recibirás instrucciones para recuperar tu contraseña."
    }


@router.post("/resetear-password")
def resetear_password_endpoint(
    datos: schemas.ResetearPasswordRequest, db: Session = Depends(get_db)
):
    """
    🔒 FIX: 'token' y 'nueva_password' ahora viajan en el body
    (schemas.ResetearPasswordRequest), no como query params — antes
    quedaban expuestos en logs del servidor y en el historial del navegador.
    """
    registro = crud.validar_token_recuperacion(db, datos.token)
    if not registro:
        raise HTTPException(
            status_code=400, detail="El link de recuperación es inválido o ya expiró."
        )
    crud.resetear_password(db, registro, datos.nueva_password)
    return {"mensaje": "Contraseña actualizada correctamente."}

@router.get("/usuarios/", response_model=list[schemas.UsuarioResponse])
def listar_mis_psicologos(
    institucion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO)
):
    """Lista los usuarios de una institución.

    👥 C-6 — Antes el superadmin recibía un 400 que lo remitía a "el listado de
    instituciones para filtrar por institucion_id", un endpoint que no existe:
    no tenía ninguna forma de ver los usuarios de un colegio.

    - superadmin: debe indicar ?institucion_id= (mismo patrón que /campanas/
      y /casos-pendientes).
    - admin: ve SIEMPRE su propia institución; el parámetro se ignora, así
      que no puede usarlo para asomarse a otro colegio.
    """
    if usuario_actual.rol == "superadmin":
        if institucion_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Como superadmin, especifica ?institucion_id=",
            )
        existe = db.query(instituciones_models.Institucion.id).filter(
            instituciones_models.Institucion.id == institucion_id
        ).first()
        if not existe:
            raise HTTPException(status_code=404, detail="Institución no encontrada.")
    else:
        institucion_id = usuario_actual.institucion_id

    return crud.listar_usuarios_de_institucion(db=db, institucion_id=institucion_id)


@router.patch("/usuarios/{usuario_id}", response_model=schemas.UsuarioResponse)
def actualizar_psicologo(
    usuario_id: int,
    datos: schemas.UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(permisos.SOLO_ADMINISTRATIVO)
):
    objetivo = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not objetivo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario_actual.rol != "superadmin" and objetivo.institucion_id != usuario_actual.institucion_id:
        raise HTTPException(status_code=403, detail="No puedes editar usuarios de otra institución.")

    # 🛡️ Mismo candado temprano que el logo institucional (C-11): una URL
    # de firma que apunte a la red interna ni siquiera llega a guardarse.
    if datos.firma_imagen_url:
        try:
            validar_url_logo(datos.firma_imagen_url)
        except UrlNoPermitida as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"URL de firma no permitida: {exc}",
            )
    elif datos.firma_imagen_url == "":
        datos.firma_imagen_url = None

    return crud.actualizar_usuario(db=db, usuario_id=usuario_id, datos=datos)


# ==========================================
# 🆕 Firma personal autoalojada — ver Usuario.firma_imagen_url en models.py
# y crud.subir_firma_usuario()/leer_firma_usuario(). Alternativa a pegar una
# URL externa vía el PATCH de arriba: el propio usuario sube el archivo y
# AuroraSoft lo sirve desde su propio dominio.
# ==========================================
@router.post("/usuarios/{usuario_id}/firma", response_model=schemas.UsuarioResponse)
async def subir_firma_usuario_endpoint(
    usuario_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual),
):
    """Sube la firma de un usuario — él mismo (la firma es personal), o un
    admin/superadmin de su misma institución en su nombre."""
    objetivo = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not objetivo:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    es_propia = usuario_actual.id == usuario_id
    es_admin_de_su_institucion = (
        usuario_actual.rol in ("superadmin", "admin")
        and (usuario_actual.rol == "superadmin" or objetivo.institucion_id == usuario_actual.institucion_id)
    )
    if not es_propia and not es_admin_de_su_institucion:
        raise HTTPException(status_code=403, detail="No puedes subir la firma de otro usuario.")
    contenido = leer_archivo_con_limite(archivo, TAMANO_MAXIMO_IMAGEN_BYTES, "archivo de firma")
    return crud.subir_firma_usuario(db, usuario_id, contenido, archivo.filename or "", archivo.content_type or "")


@router.get("/usuarios/{usuario_id}/firma")
def servir_firma_usuario_endpoint(usuario_id: int, db: Session = Depends(get_db)):
    """PÚBLICO a propósito, sin autenticación: es exactamente la URL que
    `core/url_segura.descargar_logo_seguro()` pide sin credenciales al
    generar un PDF."""
    contenido, content_type = crud.leer_firma_usuario(db, usuario_id)
    return Response(content=contenido, media_type=content_type)