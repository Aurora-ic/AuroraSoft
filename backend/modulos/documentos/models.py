from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON,
    Numeric, UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.sql import func, text
from core.database import Base


# ==========================================
# Catálogo global (mantenido por superadmin) — mismo principio ya aplicado
# a Prueba: agregar un tipo de documento es un dato nuevo, nunca una rama de
# código nueva.
# ==========================================

class TipoDocumento(Base):
    """Catálogo global de tipos de documento (informe individual, informe
    grupal/institucional, plan de trabajo/matriz...). `alcances_permitidos`
    y `visibilidades_permitidas` son listas separadas por coma (mismo
    criterio que `Prueba.tecnicas_adicionales`): no son la fuente de verdad
    de qué valores EXISTEN (eso lo fijan los CHECK de
    `DocumentoInstitucional`), solo de cuáles puede ofrecer una instancia de
    ESTE tipo en particular — ej. "Informe individual" solo admite
    alcance='personas_especificas' y visibilidad='confidencial_clinico'.

    `requiere_consentimiento_individual` es la ÚNICA señal que consulta el
    gate de generación de la Sección 5 de este diseño — nunca la `clave`:
    un documento de tipo "Informe grupal" reducido a una sola Persona por
    selección manual nunca se bloquea, porque su fila de catálogo trae este
    campo en `false`, sin importar cuántas personas terminó incluyendo.
    """
    __tablename__ = "documentos_tipos"
    __table_args__ = (
        UniqueConstraint("clave", name="uq_documentos_tipos_clave"),
    )

    id = Column(Integer, primary_key=True, index=True)
    clave = Column(String, nullable=False, index=True)
    nombre = Column(String, nullable=False)

    alcances_permitidos = Column(String, nullable=False)
    visibilidades_permitidas = Column(String, nullable=False)
    requiere_consentimiento_individual = Column(Boolean, nullable=False, server_default="false", default=False)

    activo = Column(Boolean, nullable=False, server_default="true", default=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnioOficial(Base):
    """Catálogo global chico, mantenido por superadmin: el nombre oficial
    que el gobierno peruano declara cada año (ej. "Año De La Esperanza Y El
    Fortalecimiento De La Democracia"), reutilizado en el encabezado de
    cualquier documento cuya plantilla lo active — un flag de configuración
    dentro de `PlantillaSeccion.config` para el tipo `encabezado`, nunca
    obligatorio. Si el año pedido no tiene fila, el encabezado simplemente
    omite la línea — no es un dato que deba bloquear la generación.
    """
    __tablename__ = "documentos_anios_oficiales"

    anio = Column(Integer, primary_key=True)
    texto = Column(String, nullable=False)


# ==========================================
# Plantilla por institución — configurada únicamente por superadmin (el
# dueño de la plataforma la arma a partir de documentos reales que el
# colegio proporciona); la psicóloga nunca la ajusta documento por
# documento. Mutable: se edita directamente, igual que Prueba/Baremo,
# porque cada documento generado congela su propio formato resuelto en su
# snapshot — mismo criterio "instantánea, no referencia" que ya usa todo
# el proyecto — así que no necesita su propia tabla de versiones.
# ==========================================

class PlantillaDocumento(Base):
    """Plantilla de un `TipoDocumento`: formato tipográfico fijo
    (fuente/tamaño/interlineado/justificado) y la configuración de
    numeración (correlativo). El índice único parcial garantiza como máximo
    una plantilla ACTIVA por institución+tipo —mismo mecanismo que
    `ConsentimientoInformado`/`MatriculaAcademica`—, así que reemplazar la
    plantilla de un colegio es desactivar la vieja y activar una nueva,
    nunca dos activas compitiendo.

    `institucion_id` puede ser NULL: esa fila es una plantilla
    PREDETERMINADA global, mantenida por AuroraSoft (solo superadmin la crea
    o edita — ver permisos.STAFF_CLINICO vs SOLO_SUPERADMIN en router.py),
    pensada para que cualquier colegio la clone (POST .../clonar, ya
    disponible a STAFF_CLINICO) y edite su propia copia libremente. Las
    predeterminadas nunca se modifican por el uso de un colegio — cada
    clon es una fila propia, independiente desde el momento en que se crea.
    La PLANTILLA en sí (secciones, orden, tipografía) de una fila con
    institucion_id propio la arma y edita el admin/psicólogo de ESA
    institución (STAFF_CLINICO), nunca la de otro colegio — ver el candado
    de tenant en cada endpoint de router.py.

    🔧 El índice único parcial de abajo nunca necesitó un segundo índice
    para el catálogo global: Postgres no considera que dos NULL "choquen"
    en un índice único, así que varias filas institucion_id IS NULL
    (predeterminadas) del mismo tipo_documento_id y activa=true ya conviven
    sin problema — el candado real solo aplica entre instituciones reales.
    Una sesión anterior agregó, por error, un índice EXTRA que sí forzaba
    "a lo sumo una predeterminada activa por tipo" — quitado en la
    siguiente sesión (migración
    2026_10_15_0900-f28b6a3c0e91_quitar_unicidad_predeterminada_por_tipo.py)
    al necesitar un segundo documento predeterminado bajo el MISMO
    TipoDocumento (ej. "informe escolar" + "informe para padres", ambos
    "Informe individual") — el catálogo global es un MENÚ, no "la plantilla
    vigente de este tipo", así que varias predeterminadas activas del mismo
    tipo coexistiendo es el comportamiento correcto, no un error a prevenir.
    `crud.crear_plantilla_documento`/`actualizar_plantilla_documento` saltan
    `_desactivar_plantillas_activas` por completo cuando institucion_id es
    None, por la misma razón — nunca desactivan una predeterminada global
    al crear/activar otra.
    """
    __tablename__ = "documentos_plantillas"
    __table_args__ = (
        # Postgres nunca considera que dos NULL "choquen" en un índice único,
        # así que este índice YA deja coexistir varias filas institucion_id
        # IS NULL (predeterminadas globales) con el mismo tipo_documento_id
        # y activa=true sin ningún ajuste — solo bloquea dos instituciones
        # reales compitiendo, que es lo único que necesita bloquear.
        Index(
            "uq_documentos_plantilla_activa_por_institucion_y_tipo",
            "institucion_id", "tipo_documento_id",
            unique=True,
            postgresql_where=text("activa = true"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=True, index=True)
    tipo_documento_id = Column(Integer, ForeignKey("documentos_tipos.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)
    activa = Column(Boolean, nullable=False, server_default="true", default=True)

    # Punto de partida: Arial 11pt justificado, mismo criterio que ya usa
    # core/pdf_generator.py para el informe psicométrico.
    fuente = Column(String, nullable=False, server_default="Arial", default="Arial")
    tamano_pt = Column(Integer, nullable=False, server_default="11", default=11)
    interlineado = Column(Numeric(4, 2), nullable=False, server_default="1.15", default=1.15)
    justificado = Column(Boolean, nullable=False, server_default="true", default=True)

    # Plantilla de texto para el correlativo (ej. "INFORME-{correlativo:04d}-{anio}").
    # NULL = este tipo de documento no lleva numeración automática.
    formato_correlativo = Column(String, nullable=True)
    # Decisión institucional (no técnica): si el contador vuelve a 1 cada
    # año o corre indefinidamente — ver CorrelativoDocumento.anio, abajo.
    # Enganche motor de pruebas -> motor de documentos. `False` en toda fila
    # cargada antes de esta columna: cero cambio de comportamiento hasta que
    # un superadmin lo activa a propósito. Cuando está en `True`,
    # crud.generar_documentos_automaticos_por_examen (ver modulos/documentos/
    # crud.py) crea y emite automáticamente, tras CADA examen finalizado de
    # esta institución, un DocumentoInstitucional de alcance
    # 'personas_especificas' a partir de ESTA plantilla para el estudiante
    # que acaba de rendir — el mecanismo que hace que "cada prueba" ya no
    # produzca un único informe fijo igual para todo colegio (ese sigue
    # siendo core/pdf_generator.py, sin tocar), sino el diseño propio que
    # cada institución configuró aquí. Solo aplica cuando la plantilla tiene
    # EXACTAMENTE UNA PlantillaSeccion de tipo_seccion='resultados_prueba'
    # (con 0 no hay dónde enlazar el resultado; con 2+ el sistema no puede
    # adivinar a cuál corresponde este examen en particular) — una plantilla
    # que no cumple esto simplemente se omite del enganche automático, sin
    # error, y sigue disponible para armarse a mano como cualquier otra.
    generar_automaticamente_al_finalizar_examen = Column(
        Boolean, nullable=False, server_default="false", default=False,
    )
    correlativo_reinicia_anualmente = Column(Boolean, nullable=False, server_default="false", default=False)

    # 🆕 Estilo del TÍTULO del documento (el grande, arriba de todo) —
    # independiente de fuente/tamano_pt/justificado, que gobiernan el
    # CUERPO. Antes de esto, `_construir_estilos` lo forzaba siempre a
    # negrita con tamaño=cuerpo+5, sin ningún control; los valores por
    # defecto de estas tres columnas reproducen EXACTAMENTE ese
    # comportamiento anterior, así que ninguna plantilla ya cargada cambia
    # de aspecto hasta que alguien la edite a propósito. El título de cada
    # SECCIÓN (no el del documento) sigue con su estilo fijo de siempre
    # (negrita, cuerpo+1) — configurarlo por sección, uno de 12 tipos
    # posibles, no se pidió explícitamente y multiplicaría la UI sin
    # necesidad real todavía.
    titulo_negrita = Column(Boolean, nullable=False, server_default="true", default=True)
    titulo_cursiva = Column(Boolean, nullable=False, server_default="false", default=False)
    # NULL = usa la fórmula de siempre (tamano_pt + 5). Un valor explícito
    # la reemplaza del todo, nunca se suma a ella.
    titulo_tamano_pt = Column(Integer, nullable=True)

    # 🆕 Tamaño del SUBTÍTULO de cada sección (ej. "ANTECEDENTES FAMILIARES")
    # — hasta ahora fijo en `tamano_pt + 1` dentro de `_construir_estilos`
    # (pdf_generador.py), sin ningún control. Mismo criterio NULL-formula
    # que `titulo_tamano_pt`: NULL reproduce exactamente ese comportamiento
    # de siempre, un valor explícito lo reemplaza del todo. El subtítulo
    # sigue siendo siempre negrita (sin columna propia, igual que antes) —
    # eso nunca se pidió como configurable, a diferencia del tamaño.
    subtitulo_tamano_pt = Column(Integer, nullable=True)
    # 🆕 Fondo de página de la institución (Institucion.fondo_documento_url)
    # — apagado por defecto: una plantilla nueva nunca arranca con fondo
    # encima del texto sin que alguien lo active a propósito, mismo
    # criterio que generar_automaticamente_al_finalizar_examen arriba.
    mostrar_fondo_institucion = Column(Boolean, nullable=False, server_default="false", default=False)

    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PlantillaSeccion(Base):
    """Una sección ordenada dentro de una `PlantillaDocumento`.

    `tipo_seccion` es un conjunto CERRADO — a diferencia de `TipoDocumento`
    (puro dato), este SÍ necesita una función de renderizado propia por
    valor para poder ensamblarse en el PDF, mismo rol que cumple
    `Prueba.modo_calculo` en el motor de puntajes — por eso lleva CHECK
    desde el día uno, igual que `tipo_consentimiento`/`tipo_entrada`
    (columna nueva, sin dato legado que romper). Agregar un tipo de sección
    genuinamente nuevo SÍ es código (y una migración pequeña para el
    CHECK); combinar los tipos ya existentes en una plantilla nueva NUNCA
    lo es.

    `config` (JSON) guarda la configuración propia de cada tipo:
      - encabezado: destinatarios ({nombre, cargo}[]), si muestra año
        oficial, si muestra correlativo.
      - datos_filiacion / datos_familiares: qué campos del bloque mostrar
        (todos por defecto).
      - tabla_dinamica: lista de columnas ({titulo, origen: 'automatico'|
        'libre', campo_automatico?}), y si las filas están ligadas a la
        lista congelada de estudiantes (`filas_desde_lista_estudiantes`,
        bool) o son libres (el profesional agrega filas a mano — ej. el
        "Cuadro de apoyos prioritarios" del informe grupal real).
      - resultados_prueba: qué instrumento describe esta sección (solo
        para distinguirla en la UI cuando hay más de una en el mismo
        documento — a quién referencia realmente lo dice
        DocumentoInstitucionalResultadoPrueba, nunca esta config).
      - resultados_prueba_multiple: a diferencia de 'resultados_prueba' (UN
        vínculo fijo por sección, en su propia tabla
        DocumentoInstitucionalResultadoPrueba), esta sección consolida una
        cantidad VARIABLE de aplicaciones reales de UN mismo estudiante en
        UNA sola sección — pensada para un "informe psicométrico" que junta
        los resultados de varias pruebas ya aplicadas (ej. PHQ-9 + GAD-7)
        sin fijar de antemano cuántas. `config` no tiene campos propios: la
        lista de `inscripcion_id` elegidos vive en
        `DocumentoInstitucionalSeccionContenido.contenido =
        {"inscripcion_ids": [...]}`, escrita SOLO por
        `crud.vincular_resultados_prueba_multiple` (PUT .../resultados-
        prueba-multiple) — nunca por el PUT genérico de contenido de
        sección, porque cada id referencia una Inscripcion real y necesita
        la misma re-validación persona+institución que el vínculo simple.
        Cada resultado incluido respeta el mismo candado de retención
        (informe_liberado — ver decisión de alcance, sesión 2026-10-17, en
        esa función) que 'resultados_prueba' — ver
        `crud._resolver_un_resultado_de_inscripcion`, compartida por ambos
        tipos. Nunca participa del enganche automático
        (`PlantillaDocumento.generar_automaticamente_al_finalizar_examen`),
        que exige EXACTAMENTE una sección 'resultados_prueba' — una
        plantilla con esta sección es, por diseño, siempre de armado manual.
      - grupo_campos: `{"campos": [{"etiqueta": "..."}, ...]}` — la lista de
        preguntas/campos que define quien arma la plantilla (ej. una
        entrevista/anamnesis con preguntas fijas propias de un colegio). El
        contenido por documento (los valores llenados) vive, como siempre,
        en `DocumentoInstitucionalSeccionContenido.contenido` — este tipo no
        necesitó ninguna tabla nueva, solo ampliar este CHECK.
      - firma: `{"lineas_fijas": ["Departamento de Psicología", ...]}` —
        líneas de texto FIJAS por plantilla que se imprimen debajo del
        nombre/cargo del responsable (que sigue viniendo del Usuario, nunca
        de aquí). Opcional — sin config, la firma solo muestra nombre/cargo,
        comportamiento idéntico al de antes de este campo.
      - firma_doble: dos bloques de firma lado a lado y simétricos, para un
        documento que cierra con dos responsables (ej. psicóloga + convivencia
        escolar). `{"izquierda": {"lineas_fijas": [...]}, "derecha":
        {"cargo_fijo": "...", "lineas_fijas": [...]}}` — el lado izquierdo
        SIEMPRE toma nombre/cargo del Usuario responsable del documento
        (igual que 'firma'); el derecho nunca lleva nombre de persona, solo
        `cargo_fijo` (en negrita, ej. "Convivencia escolar") y sus propias
        líneas fijas.
      - firma_triple: igual que 'firma_doble' más un tercer bloque, debajo
        y centrado a todo el ancho (nunca dentro de la tabla de dos
        columnas). `{"izquierda": {...}, "derecha": {...}, "centro":
        {"cargo_fijo": "...", "lineas_fijas": [...]}}` — mismo criterio que
        'derecha': izquierda es siempre el Usuario responsable, derecha y
        centro nunca llevan nombre de persona, solo `cargo_fijo`/
        `lineas_fijas` fijos de la plantilla.
      - ficha_imprimible: un formulario EN BLANCO, pensado para imprimirse y
        llenarse a mano (ej. una ficha de seguimiento diario que completa la
        docente) — a diferencia de todos los demás tipos, NUNCA lee
        `DocumentoInstitucionalSeccionContenido`: lo que define la plantilla
        es exactamente lo que sale impreso, sin ningún paso de "llenar
        contenido" en la app. `config` es un dict con, todas opcionales:
        `campos_encabezado` (lista de etiquetas, cada una con su línea en
        blanco para escribir, ej. ["Estudiante", "Edad", "Grado"]),
        `leyenda` (una línea de texto fija, ej. la escala de valoración),
        `columnas` + `filas` (una tabla de verificación: encabezado de
        columnas + una fila por cada etiqueta de `filas`, con celdas VACÍAS
        con borde — no hay glifo de casillero, el borde vacío ES el
        casillero, para no depender de que la fuente activa soporte un
        carácter Unicode que Times-Roman/Helvetica no tienen), `listas_checkbox`
        (lista de `{"titulo": "...", "opciones": [...]}`, cada opción con un
        "[ ]" literal delante), `preguntas_abiertas` (etiquetas con espacio
        en blanco para responder) y `firmas_en_blanco` (etiquetas con línea
        de firma, sin nombre real — para firmar a mano en el papel).
      - grafico_barras: gráfico de barras embebido como imagen (reusa
        `core.pdf_generator.generar_grafico_barras`, el mismo que ya usa el
        informe psicométrico fijo). Dos fuentes de datos posibles, resueltas
        en ese orden de precedencia por `crud._resolver_grafico_barras`:
        (1) vinculado a una `Inscripcion` real vía
        `DocumentoInstitucionalResultadoPrueba` — mismo mecanismo y mismos
        dos endpoints `PUT/DELETE .../resultados-prueba` que ya usa
        `resultados_prueba` (el CHECK de esos endpoints ahora acepta ambos
        tipos), incluido el mismo candado de retención (`informe_liberado`
        — ver decisión de alcance, sesión 2026-10-17, en
        `crud._resolver_un_resultado_de_inscripcion`) — un gráfico nunca
        puede filtrar un resultado que el profesional todavía no liberó;
        (2) si no hay vínculo, datos manuales en
        `DocumentoInstitucionalSeccionContenido.contenido = {"datos":
        [{"etiqueta": "...", "valor": 12}, ...]}`, escritos por quien llena
        el documento — para instrumentos sin motor de scoring (ej. una
        prueba proyectiva). `config` no tiene campos propios todavía.
      - imagen_anexo: una imagen subida directamente por quien llena el
        documento (dibujo, foto de una prueba gráfica/proyectiva) — nunca
        una URL externa, a diferencia de `Institucion.logo_url` (ver
        `crud.guardar_imagen_seccion`, `POST .../secciones/{id}/imagen`,
        multipart). Mismo criterio "instantánea, no referencia" que el logo
        institucional: `DocumentoInstitucionalSeccionContenido.contenido =
        {"storage_key": "...", "nombre_archivo": "...", "descripcion": "..."}`
        congela solo la key de `core/storage/`, nunca los bytes — el
        renderizador los lee recién al generar cada versión, y cada subida
        nueva obtiene una key única (nunca sobrescribe la anterior), para
        que una versión ya emitida nunca pierda su imagen si se sube una
        nueva para la siguiente. `config` no tiene campos propios todavía.
    """
    __tablename__ = "documentos_plantilla_secciones"
    __table_args__ = (
        CheckConstraint(
            "tipo_seccion IN "
            "('encabezado', 'datos_filiacion', 'datos_familiares', "
            "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', "
            "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo', 'firma_triple', "
            "'resultados_prueba_multiple')",
            name="ck_documentos_plantilla_seccion_tipo_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    plantilla_documento_id = Column(
        Integer, ForeignKey("documentos_plantillas.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    orden = Column(Integer, nullable=False)
    tipo_seccion = Column(String, nullable=False, index=True)
    titulo = Column(String, nullable=True)
    config = Column(JSON, nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CorrelativoDocumento(Base):
    """Contador atómico de numeración, por institución+tipo (+año si la
    plantilla reinicia anualmente). Se incrementa con `SELECT ... FOR
    UPDATE` en el momento de generar cada versión — mismo cuidado de
    concurrencia que ya exigió `finalizar_examen_seguro` (ver CLAUDE.md:
    el bug de identity map/lock de la Fase 1), para que dos emisiones
    simultáneas de la misma institución nunca reciban el mismo número.

    `anio` usa `0` como centinela de "no reinicia anualmente" en vez de
    NULL a propósito: PostgreSQL trata los NULL de un UNIQUE como valores
    distintos entre sí, así que dos filas con `anio IS NULL` para la misma
    institución+tipo NO chocarían — el centinela mantiene la unicidad real.
    """
    __tablename__ = "documentos_correlativos"
    __table_args__ = (
        UniqueConstraint(
            "institucion_id", "tipo_documento_id", "anio",
            name="uq_documentos_correlativo_institucion_tipo_anio",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    tipo_documento_id = Column(Integer, ForeignKey("documentos_tipos.id"), nullable=False, index=True)
    anio = Column(Integer, nullable=False, server_default="0", default=0)
    ultimo_numero = Column(Integer, nullable=False, server_default="0", default=0)


# ==========================================
# DocumentoInstitucional — identidad, patrón `Informe`: esta fila nunca se
# edita para cambiar contenido; cada emisión (incluida cada reemisión) crea
# una DocumentoInstitucionalVersion inmutable nueva.
# ==========================================

class DocumentoInstitucional(Base):
    """Documento institucional/grupal o individual armado con este motor de
    plantillas — distinto del `Informe`/`InformeVersion` psicométrico
    (que sigue siendo 1:1 con una `Inscripcion` y no pasa por aquí).

    `alcance` decide a quién está asociado:
      - 'institucion': toda la institución, sin estudiantes ligados.
      - 'estructura_academica': uno o varios Nivel/Grado/Sección — el
        criterio queda en `DocumentoInstitucionalEstructura`, la lista
        final (siempre congelada) en `DocumentoInstitucionalEstudiante`.
      - 'personas_especificas': selección manual de una o varias Persona,
        pudiendo combinar de secciones/niveles distintos (ej. 29
        estudiantes de varios grados en un solo documento).
      - 'ninguno': plan de trabajo/matriz de intervención institucional,
        sin ningún estudiante ligado.

    `nivel_visibilidad` gobierna SOLO el acceso directo a este documento
    (listados propios, descarga) — 'confidencial_clinico' (por defecto, el
    más restrictivo) o 'compartible_colegio' (habilita al rol 'colegio' a
    abrirlo). No tiene ningún efecto sobre la entrada-puente del expediente
    de cada estudiante incluido: esa sigue la regla estricta de
    `EntradaExpediente` siempre (autor/superadmin, con
    `AutorizacionAccesoColegio` como única excepción posible) — decisión
    explícita para no crear un segundo canal de autorización paralelo hacia
    el mismo expediente. Tampoco existe ningún valor pensado para un rol
    "docente": si un documento debe llegar a un profesor, el colegio
    ('compartible_colegio') lo descarga y lo entrega fuera del sistema.

    `version_actual` es NULL mientras el documento sigue en borrador (su
    contenido vive, editable, en `DocumentoInstitucionalSeccionContenido`)
    y solo pasa a 1 cuando se genera la primera versión real — a diferencia
    de `Informe`, que siempre nace ya con su v1 automática.
    """
    __tablename__ = "documentos_institucionales"
    __table_args__ = (
        CheckConstraint(
            "alcance IN ('institucion', 'estructura_academica', 'personas_especificas', 'ninguno')",
            name="ck_documentos_institucionales_alcance_valido",
        ),
        CheckConstraint(
            "nivel_visibilidad IN ('confidencial_clinico', 'compartible_colegio')",
            name="ck_documentos_institucionales_visibilidad_valida",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    tipo_documento_id = Column(Integer, ForeignKey("documentos_tipos.id"), nullable=False, index=True)
    plantilla_documento_id = Column(Integer, ForeignKey("documentos_plantillas.id"), nullable=False, index=True)

    alcance = Column(String, nullable=False, index=True)
    nivel_visibilidad = Column(
        String, nullable=False, server_default="confidencial_clinico", default="confidencial_clinico", index=True,
    )

    titulo = Column(String, nullable=False)
    version_actual = Column(Integer, nullable=True)

    creado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentoInstitucionalEstructura(Base):
    """Criterio de estructura académica usado para poblar (UNA VEZ) la
    lista congelada de estudiantes — nunca una referencia viva: si el
    documento tiene `alcance='estructura_academica'`, esta tabla registra
    QUÉ se eligió (auditoría de "cómo se armó"), pero quien decide a quién
    aplica el documento es siempre `DocumentoInstitucionalEstudiante`.
    Varias filas pueden combinarse (ej. "Nivel Inicial y Primaria" = dos
    filas de `nivel_educativo_id`, una por nivel).
    """
    __tablename__ = "documentos_institucionales_estructura"
    __table_args__ = (
        CheckConstraint(
            "(nivel_educativo_id IS NOT NULL AND grado_id IS NULL AND seccion_id IS NULL)"
            " OR "
            "(nivel_educativo_id IS NULL AND grado_id IS NOT NULL AND seccion_id IS NULL)"
            " OR "
            "(nivel_educativo_id IS NULL AND grado_id IS NULL AND seccion_id IS NOT NULL)",
            name="ck_documentos_estructura_un_solo_nivel",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    nivel_educativo_id = Column(Integer, ForeignKey("niveles_educativos.id"), nullable=True, index=True)
    grado_id = Column(Integer, ForeignKey("grados.id"), nullable=True, index=True)
    seccion_id = Column(Integer, ForeignKey("secciones.id"), nullable=True, index=True)


class DocumentoInstitucionalEstudiante(Base):
    """La lista CONGELADA de estudiantes de un documento — resultado final
    de cualquier camino de selección (atajo por sección completa o
    selección manual, incluso combinando ambos), nunca una referencia
    viva a `MatriculaAcademica`/`Seccion`. `incluido_via` es solo
    trazabilidad de auditoría, nunca cambia el comportamiento posterior.

    Snapshot al momento de incluir — mismo criterio exacto que
    `Inscripcion.grado_seccion_historico`: si el estudiante se transfiere
    de sección después, esta fila jamás se reescribe.

    Inmutable ENTRE VERSIONES del mismo documento: una reemisión no puede
    tocar esta tabla (se aplica en la capa de endpoints, que esta fase no
    construye — no hay forma barata de expresarlo como constraint de base
    de datos, mismo caso que "solo matricular_persona_en_seccion escribe
    MatriculaAcademica"). Incluir o excluir a alguien siempre es un
    `DocumentoInstitucional` nuevo.
    """
    __tablename__ = "documentos_institucionales_estudiantes"
    __table_args__ = (
        UniqueConstraint(
            "documento_institucional_id", "persona_id",
            name="uq_documentos_institucionales_estudiante",
        ),
        CheckConstraint(
            "incluido_via IN ('seccion', 'manual')",
            name="ck_documentos_institucionales_estudiante_incluido_via_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    incluido_via = Column(String, nullable=False)

    nombre_completo_historico = Column(String, nullable=True)
    seccion_id_historico = Column(Integer, ForeignKey("secciones.id"), nullable=True, index=True)
    grado_seccion_historico = Column(String, nullable=True)

    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentoInstitucionalResultadoPrueba(Base):
    """Qué `Inscripcion` (y por lo tanto qué `Informe`/resultados) concretos
    alimentan UN bloque `resultados_prueba` para UN estudiante, dentro de
    UN documento — reemplaza una columna única de "una sola aplicación por
    documento": un informe individual real puede incluir varios
    instrumentos psicométricos, cada uno con su propia `Inscripcion`, cada
    uno con su propia fila acá. También deja
    listo, sin código adicional, el caso de un futuro informe grupal que
    quisiera mostrar resultados por estudiante.

    Una fila por (documento, sección de plantilla, estudiante) — de ahí el
    único índice compuesto.
    """
    __tablename__ = "documentos_institucionales_resultados_prueba"
    __table_args__ = (
        UniqueConstraint(
            "documento_institucional_id", "plantilla_seccion_id", "persona_id",
            name="uq_documentos_resultado_prueba_seccion_persona",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    plantilla_seccion_id = Column(
        Integer, ForeignKey("documentos_plantilla_secciones.id"), nullable=False, index=True,
    )
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=False, index=True)
    inscripcion_id = Column(Integer, ForeignKey("edu_inscripciones.id"), nullable=False, index=True)


class DocumentoInstitucionalSeccionContenido(Base):
    """Estado ACTUAL (mutable) del contenido de una sección mientras el
    documento sigue en borrador — un espacio de trabajo, nunca un uso
    definitivo de los datos: por eso el consentimiento general (cuando
    `TipoDocumento.requiere_consentimiento_individual` es true) NO se
    valida aquí, solo al generar cada `DocumentoInstitucionalVersion`. Al
    emitir, el contenido vigente de cada sección se congela dentro del
    `contenido_snapshot` de la nueva versión — esta fila sigue existiendo y
    editable después (para la siguiente reemisión), la versión ya emitida
    nunca se ve afectada por ediciones posteriores de aquí.
    """
    __tablename__ = "documentos_institucionales_seccion_contenido"
    __table_args__ = (
        UniqueConstraint(
            "documento_institucional_id", "plantilla_seccion_id",
            name="uq_documentos_seccion_contenido_unica",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    plantilla_seccion_id = Column(
        Integer, ForeignKey("documentos_plantilla_secciones.id"), nullable=False, index=True,
    )
    contenido = Column(JSON, nullable=True)

    editado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=True)
    actualizado_en = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class DocumentoInstitucionalVersion(Base):
    """Un PDF concreto, inmutable una vez creado — mismo patrón exacto que
    `InformeVersion`. `contenido_snapshot` congela TODO el contenido
    ensamblado (secciones, formato de plantilla resuelto, lista de
    estudiantes con sus datos históricos) usado para generar ESE PDF
    exacto; el binario vive en storage (core/storage/), aquí solo la
    metadata para localizarlo y verificarlo.

    El consentimiento general (cuando `TipoDocumento.
    requiere_consentimiento_individual` es true, es decir, cuando
    `alcance='personas_especificas'` con exactamente una Persona en un tipo
    marcado así en el catálogo) se revalida en el momento de crear CADA
    fila nueva de esta tabla, incluidas las reemisiones — decisión
    explícita: a diferencia de la finalización de examen (un hecho
    histórico ya cerrado, que nunca vuelve a chequear consentimiento),
    cada emisión de un documento es un acto nuevo de generar una salida con
    datos personales, en una fecha propia, y si el consentimiento se
    revocó entre versiones no debe poder emitirse una nueva.
    """
    __tablename__ = "documentos_institucionales_versiones"
    __table_args__ = (
        UniqueConstraint(
            "documento_institucional_id", "numero_version",
            name="uq_documentos_institucionales_version_numero",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    numero_version = Column(Integer, nullable=False)

    contenido_snapshot = Column(JSON, nullable=False)

    storage_key = Column(String, nullable=False)
    nombre_archivo = Column(String, nullable=False)
    mime_type = Column(String, nullable=False, server_default="application/pdf", default="application/pdf")
    tamano_bytes = Column(Integer, nullable=False)
    checksum_sha256 = Column(String, nullable=False)

    generado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    generado_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False)
    # Obligatorio solo para reemisiones (v2+); v1 lleva "Emisión inicial".
    motivo_version = Column(Text, nullable=True)


# ==========================================
# Paso 7 — auditoría de lectura, mismo rol que RegistroLecturasExpediente
# (modulos/superadmin/models.py) pero para este motor. Independiente de esa
# tabla: un documento institucional no es una entrada de expediente.
# ==========================================

class RegistroLecturaDocumento(Base):
    """Quién leyó el CONTENIDO COMPLETO de un `DocumentoInstitucional`
    (el borrador de una sección) o descargó el PDF de una versión, y
    cuándo. Append-only — nunca se edita ni se borra, mismo criterio que
    `RegistroLecturasExpediente`/`RegistroCambiosPersona`/
    `RegistroAuditoriaArco`.

    Ver el documento en un LISTADO (`GET /documentos/`), su detalle
    (`GET /documentos/{id}`: título/alcance/nivel_visibilidad/roster de
    estudiantes) o la lista de versiones (`GET .../versiones`) no genera
    una fila aquí — son metadata, no contenido. Solo abrir el contenido
    real de una sección (`GET .../secciones`) o descargar el PDF de una
    versión (`GET .../versiones/{n}/descargar`) lo hace; esa distinción
    vive en la capa de endpoints, no en este esquema, mismo criterio que
    `RegistroLecturasExpediente`.

    `numero_version_leida` solo se llena para `tipo_acceso='descarga_pdf'`
    — el borrador de una sección (`tipo_acceso='contenido'`) no está
    versionado, así que queda NULL ahí, igual que
    `RegistroLecturasExpediente.numero_version_leida` para una entrada
    puente sin versión propia.

    `acceso_via_visibilidad_colegio` deja constancia explícita de que la
    lectura solo fue posible porque `nivel_visibilidad='compartible_colegio'`
    (es decir, `rol_lector='colegio'`, la única vía que abre
    `usuario_puede_ver_documento` para ese rol) — es un snapshot tomado al
    momento de leer, no algo que se recalcule después contra el documento.
    `nivel_visibilidad` gobierna EXCLUSIVAMENTE el acceso directo a este
    documento y no tiene ningún efecto sobre la entrada-puente del
    expediente de los estudiantes incluidos (ver
    `crear_entrada_expediente_documento_institucional` en
    `modulos/superadmin/crud.py`), que sigue su propia regla estricta
    (autor/superadmin, o `AutorizacionAccesoColegio` vigente) sin
    excepción — los dos canales de autorización son y deben seguir siendo
    completamente independientes.
    """
    __tablename__ = "documentos_registro_lecturas"
    __table_args__ = (
        CheckConstraint(
            "tipo_acceso IN ('contenido', 'descarga_pdf')",
            name="ck_documentos_registro_lecturas_tipo_acceso_valido",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    documento_institucional_id = Column(
        Integer, ForeignKey("documentos_institucionales.id"), nullable=False, index=True,
    )
    institucion_id = Column(Integer, ForeignKey("instituciones.id"), nullable=False, index=True)

    leido_por_usuario_id = Column(Integer, ForeignKey("auth_usuarios.id"), nullable=False, index=True)
    rol_lector = Column(String, nullable=True)
    fecha_lectura = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    ip_lectura = Column(String, nullable=True)

    tipo_acceso = Column(String, nullable=False, index=True)
    numero_version_leida = Column(Integer, nullable=True)
    acceso_via_visibilidad_colegio = Column(Boolean, nullable=False, server_default="false", default=False)
