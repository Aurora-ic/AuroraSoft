from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from core.database import get_db
from core.security import SECRET_KEY, ALGORITHM
from modulos.auth import models

# Esquema Bearer Token para Swagger UI
seguridad = HTTPBearer()


def ip_del_cliente(request: Request) -> Optional[str]:
    """IP real del cliente, para los registros de auditoría (Ley 29733).

    Detrás de un proxy inverso `request.client` es la IP del proxy, así que se
    prefiere el primer salto de X-Forwarded-For cuando viene. Si no hay
    contexto HTTP utilizable devuelve None: se guarda NULL antes que inventar
    un dato en una tabla de auditoría.
    """
    reenviada = request.headers.get("x-forwarded-for")
    if reenviada:
        return reenviada.split(",")[0].strip() or None
    return request.client.host if request.client else None


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(seguridad), 
    db: Session = Depends(get_db)
):
    """El Guardia: Verifica el token JWT y devuelve los datos del usuario logueado"""
    token = credenciales.credentials  # Extrae el token enviado en el header Authorization

    excepcion_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No tienes permiso para acceder. Token inválido o expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise excepcion_credenciales
    except JWTError:
        raise excepcion_credenciales

    usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if usuario is None or not usuario.activo:
        raise excepcion_credenciales

    # 🔑 C-4 — Token versionado. Cada JWT lleva la versión vigente al emitirse
    # (claim "tv") y se invalida en cuanto el usuario cambia su contraseña.
    # Los tokens emitidos antes de introducir este claim no lo traen y se
    # tratan como versión 0: siguen valiendo hasta el primer cambio de
    # contraseña, así que el despliegue no expulsa a nadie.
    if payload.get("tv", 0) != (usuario.token_version or 0):
        raise excepcion_credenciales

    # Validación de la licencia de la institución
    if usuario.rol != "superadmin" and usuario.institucion:
        inst = usuario.institucion
        if not inst.plan_activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="La licencia de tu institución no está activa. Contacta a AuroraSoft."
            )
        # 🆕 Cierre de gap (docs/gaps-pendientes.md) — deliberadamente NO se
        # cambia a datetime.now(timezone.utc): Institucion.fecha_vencimiento_
        # licencia es una columna DateTime SIN zona horaria, así que siempre
        # vuelve de la base de datos naive sin importar cómo se escribió.
        # Compararla contra un datetime aware lanzaría TypeError en cada
        # request autenticado de cualquier institución con licencia con
        # vencimiento. Mismo motivo en crud.campana_esta_expirada() y
        # puede_aplicar_prueba() — ver sus propios comentarios.
        if inst.fecha_vencimiento_licencia and inst.fecha_vencimiento_licencia < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="La licencia de tu institución venció."
            )

    return usuario


def verificar_acceso_institucion(
    institucion_id: int, 
    usuario_actual: models.Usuario = Depends(obtener_usuario_actual)
):
    """
    🔒 EL CANDADO MULTI-TENANT.
    Úsalo en cualquier endpoint que reciba un institucion_id (por body, query o path).
    - superadmin: pasa siempre (ve todos los colegios).
    - cualquier otro rol: solo pasa si institucion_id coincide con el suyo.
    """
    if usuario_actual.rol == "superadmin":
        return usuario_actual

    if usuario_actual.institucion_id != institucion_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a los datos de esta institución."
        )
    return usuario_actual


def requerir_rol(*roles_permitidos: str):
    """
    🔒 Fábrica de dependencias por rol.
    Uso: Depends(requerir_rol("superadmin", "admin"))
    """
    def verificador(usuario_actual: models.Usuario = Depends(obtener_usuario_actual)):
        if usuario_actual.rol not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Esta acción requiere uno de estos roles: {roles_permitidos}"
            )
        return usuario_actual
    return verificador


# 🔒 Auditoría de permisos (matriz endpoint × rol) — alias con nombre de
# negocio para el tier "personal clínico/administrativo de la institución,
# nunca colegio". Antes cada endpoint sensible repetía a mano
# `requerir_rol("superadmin", "admin", "psicologo")` (19 veces al momento de
# escribir esto) y varios simplemente se olvidaron de agregarlo, dejando
# entrar a `colegio` por omisión en vez de por decisión — ver CLAUDE.md,
# "Permission surface: what the matrix test can't see". Todo endpoint nuevo
# que deba excluir a `colegio` debe usar `Depends(requerir_staff_clinico)`,
# nunca repetir la tupla de roles a mano: así el test de matriz
# (`tests/test_matriz_permisos_unitario.py`) solo necesita reconocer un
# nombre, y un cambio de política (agregar/quitar un rol de este tier) se
# hace en un solo lugar.
requerir_staff_clinico = requerir_rol("superadmin", "admin", "psicologo")