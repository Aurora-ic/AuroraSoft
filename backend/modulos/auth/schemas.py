from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime
from typing import Optional

ROLES_VALIDOS = {"superadmin", "admin", "psicologo", "colegio"}


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str
    nombre_completo: str
    rol: Optional[str] = "psicologo"
    institucion_id: Optional[int] = None  # Obligatorio salvo rol="superadmin"

    @field_validator("rol")
    @classmethod
    def rol_valido(cls, v):
        if v not in ROLES_VALIDOS:
            raise ValueError(f"Rol inválido. Debe ser uno de: {ROLES_VALIDOS}")
        return v

    @field_validator("password")
    @classmethod
    def password_segura(cls, v):
        # 🔒 FIX: antes no había ninguna validación de fortaleza de contraseña
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v


class UsuarioResponse(BaseModel):
    id: int
    email: str
    nombre_completo: str
    rol: str
    institucion_id: Optional[int] = None
    activo: bool
    fecha_registro: datetime
    # 🆕 Motor de documentos institucionales — ver Usuario.cargo en models.py.
    cargo: Optional[str] = None
    # 🆕 Ver Usuario.firma_imagen_url en models.py.
    firma_imagen_url: Optional[str] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# ==========================================
# 🔒 FIX: esquemas para recuperación de contraseña.
# Antes "email" y "nueva_password" se recibían como parámetros sueltos
# de función (query params), lo que los expone en logs, historial del
# navegador y proxies. Ahora viajan en el body de la petición.
# ==========================================
class SolicitudRecuperacion(BaseModel):
    email: EmailStr


class ResetearPasswordRequest(BaseModel):
    token: str
    nueva_password: str

    @field_validator("nueva_password")
    @classmethod
    def password_segura(cls, v):
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v

class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    activo: Optional[bool] = None
    # 🆕 Motor de documentos institucionales — para resolver el "Emisor" de
    # un documento automáticamente (nombre + cargo), sin efecto en login/rol.
    cargo: Optional[str] = None
    # 🆕 Firma personal — alternativa a POST /auth/usuarios/{id}/firma
    # (subida + autoalojada) para quien ya tiene la imagen en un hosting
    # propio: pega la URL externa directamente aquí. Se valida igual
    # (core.url_segura.validar_url_logo) en el router.
    firma_imagen_url: Optional[str] = None