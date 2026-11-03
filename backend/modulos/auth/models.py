from sqlalchemy import CheckConstraint, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base


class Usuario(Base):
    """Tabla maestra de usuarios (Psicólogos, Administradores, Colegios).
    ÚNICA tabla de usuarios de todo el sistema."""
    __tablename__ = "auth_usuarios"
    __table_args__ = (
        # 🆕 Cierre de gap (docs/gaps-pendientes.md) — `rol` ya se validaba a
        # nivel de Pydantic en UsuarioCreate (ROLES_VALIDOS, en schemas.py) y
        # nunca es editable después de crear la cuenta, pero no había ninguna
        # garantía a nivel de base de datos. Mismos cuatro valores.
        CheckConstraint(
            "rol IN ('superadmin', 'admin', 'psicologo', 'colegio')",
            name="ck_usuarios_rol_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)  # Jamás guardamos la contraseña real
    nombre_completo = Column(String)

    # "superadmin" (equipo AuroraSoft), "admin" (dueño del colegio),
    # "psicologo" (staff del colegio), "colegio" (cuenta genérica del colegio)
    rol = Column(String, default="psicologo")

    # 🔒 CANDADO MULTI-TENANT: a qué colegio pertenece este usuario.
    # Solo puede ser NULL si rol == "superadmin" (equipo de AuroraSoft,
    # que necesita ver todos los colegios).
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)

    activo = Column(Boolean, default=True)

    # 🆕 Motor de documentos institucionales — el "Emisor (DE)" de un
    # documento (nombre + cargo/departamento, ej. "INTERNA del DPTO DE
    # PSICOLOGÍA") se resuelve automáticamente desde `nombre_completo` +
    # este campo, para que la psicóloga no lo retipee documento por
    # documento. Nullable y sin efecto en ningún otro flujo existente
    # (login, JWT, roles) — puramente informativo.
    cargo = Column(String, nullable=True)

    # 🆕 Firma personal autoalojada — imagen (ej. firma escaneada/digital)
    # que `modulos/documentos/pdf_generador.py` dibuja encima del nombre en
    # los tipo_seccion 'firma'/'firma_doble' (lado izquierdo), en vez de la
    # línea de subrayado genérica. Mismo patrón que `Institucion.logo_url`:
    # URL https pública, validada contra SSRF (core/url_segura.py) al
    # guardarse Y al descargarse; NULL = sin firma propia, se sigue
    # mostrando la línea de subrayado de siempre, cero cambio de
    # comportamiento. Se sube vía POST /auth/usuarios/{id}/firma
    # (core/branding.py, el mismo storage autoalojado del logo
    # institucional), nunca se escribe por PATCH directo.
    firma_imagen_url = Column(String, nullable=True)

    # 🔑 C-4 — Se incrusta en cada JWT (claim "tv") y se compara en cada
    # petición. Al cambiar la contraseña se incrementa, y todos los tokens
    # emitidos antes dejan de valer al instante en vez de seguir activos
    # hasta su expiración (7 días).
    token_version = Column(Integer, nullable=False, server_default="0", default=0)

    fecha_registro = Column(DateTime(timezone=True), server_default=func.now())

    institucion = relationship("Institucion", backref="usuarios")

class TokenRecuperacion(Base):
    __tablename__ = "auth_tokens_recuperacion"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    token = Column(String, unique=True, index=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_expiracion = Column(DateTime(timezone=True), nullable=False)
    usado = Column(Boolean, default=False)

class SesionUsuario(Base):
    """🆕 (sesión 2026-11-02) Una fila por inicio de sesión. Antes el JWT
    duraba 7 días, vivía en localStorage y "cerrar sesión" solo lo borraba
    del navegador: el token seguía valiendo en el servidor.

    Ahora el login emite DOS tokens, ambos en cookies httpOnly (ver
    core/sesiones.py):
      · acceso (JWT, ~15 min) con el claim `sid` = `id` de esta fila; cada
        petición comprueba en la MISMA consulta que ya trae al usuario que
        la sesión no esté revocada, bloqueada ni vencida;
      · renovación (aleatorio, solo se guarda su SHA-256 en
        `hash_renovacion`), enviado únicamente a /api/auth, que emite
        accesos nuevos mientras la sesión siga viva.

    Sin rotación del token de renovación a propósito: con varias pestañas
    abiertas, dos renovaciones simultáneas con rotación se invalidarían
    entre sí (y la detección de reutilización cerraría la sesión de todas).
    La cookie es httpOnly y solo viaja a /api/auth, así que el riesgo que
    cubre la rotación (robo del token) ya está acotado; revocar la fila lo
    corta en el acto."""
    __tablename__ = "auth_sesiones"

    id = Column(String(43), primary_key=True)  # secrets.token_urlsafe(32)
    usuario_id = Column(Integer, ForeignKey("auth_usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    hash_renovacion = Column(String(64), nullable=False, unique=True)
    # Copia de Usuario.token_version al crearla: un cambio de contraseña la
    # invalida igual que a los JWT (C-4).
    token_version = Column(Integer, nullable=False, default=0)
    creada_en = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Vida máxima absoluta (SESION_HORAS) — no se extiende al renovar.
    expira_en = Column(DateTime(timezone=True), nullable=False)
    # Última renovación: una sesión sin renovarse más de
    # SESION_INACTIVIDAD_MINUTOS ya no se puede renovar.
    ultimo_uso = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Bloqueo por inactividad del lado del servidor: el navegador lo marca al
    # bloquear la pantalla; desbloquear exige la contraseña (= sesión nueva).
    bloqueada_en = Column(DateTime(timezone=True), nullable=True)
    revocada_en = Column(DateTime(timezone=True), nullable=True)
    # 'cierre_sesion', 'reemplazada' (login desde la pantalla de bloqueo), ...
    motivo_revocacion = Column(String(40), nullable=True)
    ip = Column(String(64), nullable=True)
    agente = Column(String(300), nullable=True)
