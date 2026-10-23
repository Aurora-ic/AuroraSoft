from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime, timezone


def _a_utc_naive(valor: Optional[datetime]) -> Optional[datetime]:
    """La columna es DateTime sin zona y `obtener_usuario_actual` compara la
    licencia contra `datetime.utcnow()` (naive). Una fecha con offset guardada
    tal cual caducaría a la hora equivocada o lanzaría TypeError al comparar."""
    if valor is not None and valor.tzinfo is not None:
        return valor.astimezone(timezone.utc).replace(tzinfo=None)
    return valor


# Lo que nos manda el usuario para registrar un Colegio/Cliente
class InstitucionCreate(BaseModel):
    nombre: str
    tipo: Optional[str] = "Colegio"
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email_contacto: Optional[EmailStr] = None

    # 🏷️ C-17 — Antes estos tres campos no existían aquí y `crear_institucion`
    # los ignoraba: toda institución nacía con licencia perpetua y con el
    # límite que decidiera la BD. Los valores por defecto son los que el
    # sistema ya aplicaba (modelo y CRUD); no hay lógica comercial nueva.
    plan_activo: bool = True
    fecha_vencimiento_licencia: Optional[datetime] = None   # None = sin caducidad
    limite_pruebas_mensual_por_alumno: int = Field(
        default=5, ge=1,
        description="Pruebas máximas por alumno cada 30 días. 0 bloquearía toda evaluación.",
    )

    @field_validator("fecha_vencimiento_licencia")
    @classmethod
    def _normalizar_vencimiento(cls, v):
        return _a_utc_naive(v)


# Lo que el servidor le responde al frontend
class InstitucionResponse(BaseModel):
    id: int
    nombre: str
    tipo: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    # Sin validar como EmailStr en la RESPUESTA: un dato heredado mal formado
    # no debe convertir un GET en un 500.
    email_contacto: Optional[str] = None
    fecha_registro: datetime
    plan_activo: bool
    logo_url: Optional[str] = None
    # 🆕 Membrete del motor de documentos institucionales — franja de pie de
    # página, independiente de logo_url (encabezado). Ver modulos/documentos/
    # pdf_generador.py.
    logo_pie_pagina_url: Optional[str] = None
    # 🆕 Fondo de página completa del motor de documentos institucionales —
    # opt-in por plantilla (PlantillaDocumento.mostrar_fondo_institucion),
    # ver modulos/documentos/pdf_generador.py.
    fondo_documento_url: Optional[str] = None
    fecha_vencimiento_licencia: Optional[datetime] = None

    # 🏷️ C-17 — Antes: Optional[int] = 100, que contradecía al modelo (5) y
    # mostraba un límite que no era el aplicado. Ahora la columna es NOT NULL
    # y la respuesta refleja siempre el valor real.
    limite_pruebas_mensual_por_alumno: int

    # 🆕 Promoción anual — NULL hasta que se active explícitamente (ver
    # ActivarAnioEscolarRequest); nunca se fija automáticamente al confirmar
    # un ProcesoPromocion.
    anio_escolar_activo: Optional[int] = None

    # 🆕 Política institucional de consentimientos — ver el modelo. False
    # para toda institución existente hasta que su admin/superadmin la active.
    exigir_asentimiento_estudiante: bool = False

    class Config:
        from_attributes = True


class ActivarAnioEscolarRequest(BaseModel):
    """Cuerpo del endpoint explícito que fija `anio_escolar_activo` — una
    acción separada e intencional, nunca un efecto secundario de confirmar
    una promoción."""
    anio_escolar: int = Field(ge=2000, le=2100)


class PoliticaConsentimientosRequest(BaseModel):
    """Cuerpo del endpoint explícito que fija la política de consentimientos
    de la institución — mismo criterio que ActivarAnioEscolarRequest: una
    acción separada e intencional, no un campo más del PATCH general (que
    sigue siendo exclusivo de superadmin para licencia/plan)."""
    exigir_asentimiento_estudiante: bool


class InstitucionUpdate(BaseModel):
    logo_url: Optional[str] = None
    logo_pie_pagina_url: Optional[str] = None
    fondo_documento_url: Optional[str] = None
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email_contacto: Optional[EmailStr] = None
    plan_activo: Optional[bool] = None
    fecha_vencimiento_licencia: Optional[datetime] = None
    limite_pruebas_mensual_por_alumno: Optional[int] = Field(default=None, ge=1)

    @field_validator("fecha_vencimiento_licencia")
    @classmethod
    def _normalizar_vencimiento(cls, v):
        return _a_utc_naive(v)

    class Config:
        from_attributes = True
