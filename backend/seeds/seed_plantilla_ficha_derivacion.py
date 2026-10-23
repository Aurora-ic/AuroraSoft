"""
Carga la octava plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia.

Modelo real: "Ficha de derivación externa" (formato de ejemplo real
proporcionado por el usuario) — documenta la derivación de un estudiante a
un profesional o servicio EXTERNO al colegio (evaluación especializada,
terapia de lenguaje, atención médica/neurológica, etc.) y su seguimiento
posterior (si se informó a la familia, si recibió orientación, fecha
prevista de seguimiento, estado). Genuinamente distinta de las siete
plantillas anteriores: no es una evaluación (informe), ni un plan de
trabajo hacia adelante (plan_intervencion), ni un seguimiento periódico
propio del colegio (ficha_seguimiento), ni el registro de una única
observación conductual (registro_observacion) — es la coordinación de una
derivación hacia AFUERA del colegio y su estado.

🆕 Quinto TipoDocumento nuevo (junto a 'informe_individual_escolar',
'plan_intervencion_individual', 'ficha_seguimiento_individual' y
'registro_observacion_conductual').

Reutiliza 'datos_filiacion' + 'datos_familiares' para la sección I, igual
que las siete plantillas anteriores. Los campos de la sección I que ningún
resolutor cubre (Edad, Nombre del padre/madre/apoderado, Teléfono de
contacto, Fecha de derivación, Remitente, y el checkbox Nivel educativo)
se agregan con una sección 'ficha_imprimible' sin título que continúa la
misma sección I — mismo criterio exacto que la séptima plantilla
(registro de observación conductual).

🔒 Mismo criterio de las siete anteriores para lo libre vs. lo fijo:
cualquier campo de redacción (Descripción del motivo de derivación,
Conductas o dificultades identificadas, Tiempo aproximado desde que se
identificó la dificultad, Información proporcionada por la familia,
Información proporcionada por los docentes, Antecedentes escolares
relevantes) es 'texto_libre' individual, nunca
'ficha_imprimible.preguntas_abiertas'. Cada una de las 8 listas de
casillas del documento real (Nivel educativo, Motivo de derivación,
Contextos en los que se presentan, Frecuencia aproximada, Repercusión en
el contexto escolar, y las tres de la sección V de seguimiento — Se
informó a la familia, La familia recibió orientación, Estado) es
'ficha_imprimible.listas_checkbox', repartidas en varias secciones sin
título cuando el documento real intercala casillas y campos en blanco
dentro del mismo apartado, para preservar el orden real (el renderizador
siempre dibuja 'campos_encabezado' → 'listas_checkbox' dentro de una
misma sección, así que un apartado con casillas-blanco-casillas-blanco
necesita más de una sección 'ficha_imprimible' consecutiva).

Cierra con 'firma_doble' (izquierda el profesional responsable real, con
"Firma y sello" como línea fija adicional; derecha solo
cargo_fijo="Apoderado", nunca un nombre de persona) — igual que el
documento real ("Firma del Departamento de psicología" / "Firma y sello" a
la izquierda, "Firma del apoderado" a la derecha).

Tipografía: igual que toda plantilla predeterminada — Times New Roman,
cuerpo 11pt, subtítulo de sección 12pt.

Es idempotente: si ya existe una plantilla predeterminada global con este
mismo nombre, no toca nada.

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_ficha_derivacion
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de PlantillaDocumento)
from modulos.auth import models as auth_models
from modulos.documentos import models

CLAVE_TIPO = "ficha_derivacion_externa"
NOMBRE_TIPO = "Ficha de derivación externa"
NOMBRE_PLANTILLA = "Ficha de derivación externa (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección y las
# opciones fijas de cada lista de casillas.
SECCIONES = [
    ("datos_filiacion", "Datos generales del estudiante", None),
    ("datos_familiares", None, None),
    (
        "ficha_imprimible",
        None,  # continúa la sección I, sin un segundo encabezado
        {
            "campos_encabezado": [
                "Edad",
                "Nombre del padre, madre o apoderado",
                "Teléfono de contacto",
                "Fecha de derivación",
                "Remitente",
            ],
            "listas_checkbox": [
                {"titulo": "Nivel educativo", "opciones": ["Inicial", "Primaria", "Secundaria"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        "Motivo de derivación",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Evaluación psicológica especializada",
                        "Evaluación del desarrollo infantil",
                        "Evaluación de dificultades de aprendizaje",
                        "Evaluación de dificultades atencionales o conductuales",
                        "Atención psicológica por dificultades emocionales",
                        "Evaluación de dificultades en las relaciones sociales",
                        "Evaluación por dificultades en el lenguaje o la comunicación",
                        "Atención médica o neurológica",
                        "Terapia de lenguaje",
                        "Terapia ocupacional",
                        "Otra",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Descripción del motivo de derivación", None),
    ("texto_libre", "Conductas o dificultades identificadas", None),
    (
        "ficha_imprimible",
        "Contextos en los que se presentan",
        {
            "listas_checkbox": [
                {"titulo": "", "opciones": ["Aula", "Recreo", "Actividades grupales", "Hogar", "Otros"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección III, sin un segundo encabezado
        {
            "listas_checkbox": [
                {"titulo": "Frecuencia aproximada", "opciones": ["Ocasional", "Varias veces por semana", "Diaria", "Por determinar"]},
            ],
        },
    ),
    ("texto_libre", "Tiempo aproximado desde que se identificó la dificultad", None),
    (
        "ficha_imprimible",
        "Repercusión en el contexto escolar",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Aprendizaje académico",
                        "Participación en clase",
                        "Regulación emocional",
                        "Relaciones con compañeros",
                        "Autonomía en las actividades",
                        "Asistencia o adaptación escolar",
                        "Otra",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Información proporcionada por la familia", None),
    ("texto_libre", "Información proporcionada por los docentes", None),
    ("texto_libre", "Antecedentes escolares relevantes", None),
    (
        "ficha_imprimible",
        "Seguimiento de la derivación",
        {
            "campos_encabezado": ["Fecha de entrega de la ficha"],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "listas_checkbox": [
                {"titulo": "Se informó a la familia", "opciones": ["Sí", "No"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "listas_checkbox": [
                {"titulo": "La familia recibió orientación", "opciones": ["Sí", "No"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "campos_encabezado": ["Fecha prevista de seguimiento"],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "listas_checkbox": [
                {"titulo": "Estado", "opciones": ["Pendiente", "En proceso", "Atendida", "Requiere seguimiento"]},
            ],
        },
    ),
    # Dos firmas lado a lado — izquierda el profesional responsable real
    # (con "Firma y sello" como línea fija adicional), derecha solo
    # cargo_fijo="Apoderado", nunca un nombre de persona — igual al
    # documento de ejemplo real.
    (
        "firma_doble",
        None,
        {
            "izquierda": {"lineas_fijas": ["Departamento de Psicología", "Firma y sello"]},
            "derecha": {"cargo_fijo": "Apoderado"},
        },
    ),
]


def main() -> None:
    db = SessionLocal()
    try:
        superadmin = db.query(auth_models.Usuario).filter(
            auth_models.Usuario.rol == "superadmin",
        ).first()
        if not superadmin:
            print("❌ No hay ningún usuario superadmin todavía. Corre primero: python -m seeds.seed_superadmin")
            return

        tipo = db.query(models.TipoDocumento).filter(models.TipoDocumento.clave == CLAVE_TIPO).first()
        if not tipo:
            tipo = models.TipoDocumento(
                clave=CLAVE_TIPO,
                nombre=NOMBRE_TIPO,
                alcances_permitidos="personas_especificas",
                visibilidades_permitidas="confidencial_clinico",
                requiere_consentimiento_individual=True,
                activo=True,
            )
            db.add(tipo)
            db.flush()  # necesita tipo.id para la plantilla
            print(f"✅ TipoDocumento '{CLAVE_TIPO}' creado.")
        else:
            print(f"↪️  TipoDocumento '{CLAVE_TIPO}' ya existía, sin cambios.")

        plantilla_existente = db.query(models.PlantillaDocumento).filter(
            models.PlantillaDocumento.institucion_id.is_(None),
            models.PlantillaDocumento.tipo_documento_id == tipo.id,
            models.PlantillaDocumento.nombre == NOMBRE_PLANTILLA,
        ).first()
        if plantilla_existente:
            print(
                f"↪️  Ya existe la plantilla predeterminada '{NOMBRE_PLANTILLA}' "
                f"(id={plantilla_existente.id}) — no se modifica nada. Idempotente: nada más que hacer."
            )
            db.commit()
            return

        plantilla = models.PlantillaDocumento(
            institucion_id=None,  # 🆕 predeterminada global
            tipo_documento_id=tipo.id,
            nombre=NOMBRE_PLANTILLA,
            activa=True,
            fuente="Times New Roman",
            tamano_pt=11,
            subtitulo_tamano_pt=12,
            interlineado=1.15,
            justificado=True,
            titulo_negrita=True,
            titulo_cursiva=False,
            mostrar_fondo_institucion=False,
            creado_por_usuario_id=superadmin.id,
        )
        db.add(plantilla)
        db.flush()  # necesita plantilla.id para sus secciones

        for orden, (tipo_seccion, titulo, config) in enumerate(SECCIONES):
            db.add(models.PlantillaSeccion(
                plantilla_documento_id=plantilla.id,
                orden=orden,
                tipo_seccion=tipo_seccion,
                titulo=titulo,
                config=config,
            ))

        db.commit()
        print(f"✅ Plantilla predeterminada '{NOMBRE_PLANTILLA}' creada (id={plantilla.id}) con {len(SECCIONES)} secciones.")
    except Exception as exc:
        db.rollback()
        print(f"❌ Error al cargar la plantilla predeterminada: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
