from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from datetime import datetime
from core.database import Base

class Institucion(Base):
    __tablename__ = "instituciones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True, nullable=False) # Ej: Colegio San Agustín
    tipo = Column(String, default="Colegio") # Puede ser "Colegio", "Universidad", "Empresa"
    direccion = Column(String, nullable=True)
    telefono = Column(String, nullable=True)
    email_contacto = Column(String, nullable=True)
    
    # Nuevos campos agregados
    # 🏷️ C-17 — NOT NULL: `obtener_usuario_actual` hace `if not inst.plan_activo`,
    # así que un NULL (lo que dejó la migración f3c03cf327b6 en filas previas)
    # bloqueaba el acceso de todo el colegio como si la licencia estuviera
    # desactivada.
    plan_activo = Column(Boolean, nullable=False, server_default="true", default=True)
    fecha_vencimiento_licencia = Column(DateTime, nullable=True)
    
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    # 🏷️ C-17 — NOT NULL: con NULL, `puede_aplicar_prueba` comparaba
    # `aplicadas >= None` y lanzaba TypeError al matricular. 5 es el valor que
    # el código ya aplicaba al crear (default del ORM y respaldo del CRUD).
    limite_pruebas_mensual_por_alumno = Column(Integer, nullable=False, server_default="5", default=5)

    logo_url = Column(String, nullable=True)

    # 🆕 Membrete del motor de documentos institucionales (modulos/documentos) —
    # imagen de PIE DE PÁGINA, independiente de `logo_url` (que sigue siendo
    # el logo pequeño del informe psicométrico, core/pdf_generator.py, y
    # también el que se dibuja en el encabezado de los documentos
    # institucionales). Una institución puede no tener franja de pie de
    # página propia (NULL = el PDF simplemente no dibuja nada ahí, igual que
    # logo_url ausente). Misma descarga SSRF-safe que logo_url
    # (core/url_segura.descargar_logo_seguro) — nunca un mecanismo propio.
    logo_pie_pagina_url = Column(String, nullable=True)

    # 🆕 Fondo de página del motor de documentos institucionales — imagen
    # de página COMPLETA (no una franja como logo_url/logo_pie_pagina_url),
    # dibujada detrás del membrete en `pdf_generador._dibujar_marco_pagina`.
    # Opcional y, a diferencia de las dos anteriores, NUNCA se dibuja por
    # sola presencia de la URL: cada `PlantillaDocumento` decide si la usa
    # (`mostrar_fondo_institucion`) — un fondo de página afecta la
    # legibilidad del texto mucho más que una franja de encabezado/pie, así
    # que queda opt-in por plantilla, no automático por institución. Misma
    # descarga SSRF-safe que logo_url (core/url_segura.descargar_logo_seguro).
    fondo_documento_url = Column(String, nullable=True)

    # 🆕 Promoción anual — única fuente de verdad de "en qué año estamos"
    # para esta institución. Se activa SOLO con una acción explícita (un
    # futuro "Iniciar año X"), nunca automáticamente al confirmar un
    # ProcesoPromocion — decisión expresa de la psicóloga: una institución
    # puede promover secciones con anticipación sin que el resto de la app
    # cambie de vista todavía. NULL antes de que exista esa acción (o para
    # una institución que nunca la usó).
    anio_escolar_activo = Column(Integer, nullable=True)

    # 🆕 Política institucional de consentimientos — hasta ahora solo el
    # consentimiento del APODERADO bloqueaba matrícula/examen, hardcodeado
    # igual para toda institución. Este flag es la primera política
    # configurable por colegio: cuando está en True, `matricular_roster_en_campana`
    # y `consentimiento_vigente_para_inscripcion` (modulos/educativo/crud.py)
    # exigen ADEMÁS un asentimiento vigente del propio estudiante (tipo
    # "asentimiento" en ConsentimientoInformado), no solo el consentimiento
    # del apoderado.
    # Default False (server_default incluido) para que ninguna institución
    # existente cambie de comportamiento con esta migración — mismo criterio
    # C-17 que ya usan `plan_activo`/`limite_pruebas_mensual_por_alumno`.
    #
    # 🆕 Renombrada de exigir_consentimiento_estudiante (docs/gaps-
    # pendientes.md) — mismo flag, mismo comportamiento, solo el nombre pasa
    # a reflejar la figura legal correcta.
    exigir_asentimiento_estudiante = Column(
        Boolean, nullable=False, server_default="false", default=False,
    )