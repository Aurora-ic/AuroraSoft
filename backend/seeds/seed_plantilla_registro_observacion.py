"""
Carga la séptima plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia.

Modelo real: "Registro de observación conductual" (formato de ejemplo real
proporcionado por el usuario) — documenta UNA sesión de observación puntual
(fecha/hora de inicio y término, observador), a diferencia de la ficha de
monitoreo (6ª predeterminada), que registra seguimiento PERIÓDICO a lo largo
del tiempo. Es, en gran parte, un FORMULARIO de casillas (nivel educativo,
lugar y personas presentes, motivo de la observación, frecuencia/intensidad
de la conducta, respuesta del estudiante, orientaciones sugeridas) con una
sola tabla de registro libre y una firma simple al cierre.

🆕 Cuarto TipoDocumento nuevo (junto a 'informe_individual_escolar',
'plan_intervencion_individual' y 'ficha_seguimiento_individual') —
documentar UNA observación conductual puntual es una clase de documento
distinta de un informe de evaluación, un plan de intervención hacia
adelante o una ficha de monitoreo periódico, aunque comparta el mismo
alcance/visibilidad/consentimiento que las tres anteriores.

Reutiliza 'datos_filiacion' + 'datos_familiares' para la sección I, igual
que las seis plantillas anteriores. Todos los demás campos de la sección I
que ninguno de los dos resolutores cubre (Edad, Nivel educativo, Fecha de
observación, Hora de inicio, Hora de término, Observador(a)) se agregan
aparte con secciones 'ficha_imprimible' sin título (fluyen como
continuación de la misma sección I) — 'campos_encabezado' para los campos
en blanco, 'listas_checkbox' para Nivel (Inicial/Primaria/Secundaria).

🔒 Igual que en la ficha de monitoreo: 'ficha_imprimible' se usa SOLO para
listas de casillas (y los campos de línea en blanco que las acompañan en el
mismo bloque del documento real) — es el único tipo_seccion que sabe dibujar
"[ ] opción". Cualquier campo libre para redactar (Actividad que se
realizaba, Descripción del motivo, Descripción de la respuesta del
estudiante, Acciones específicas) se modela como 'texto_libre' individual,
nunca como 'ficha_imprimible.preguntas_abiertas' — ese campo queda
reservado para cuando la sección ENTERA es un formulario de casillas sin
nada más, no para un bloque mixto de casillas + redacción libre.

🔒 El registro de conductas observadas (sección IV del documento real, una
tabla "Fecha y hora" / "Situación o Conducta observable" con muchas filas en
blanco para completar durante varias observaciones) se modela como
'tabla_dinamica' de filas libres, NO como la tabla de 'ficha_imprimible'
(columnas+filas con etiquetas FIJAS) — mismo criterio que las tablas de
las plantillas 2, 3, 5 y 6: solo se cargan los títulos de columna, ninguna
fila de ejemplo.

La nota en cursiva bajo "Intensidad observable" ("La intensidad debe
describirse con criterios observables previamente definidos, cuando
corresponda.") usa 'ficha_imprimible.leyenda' — el mismo campo ya pensado
para una línea fija de catálogo bajo una lista de casillas.

Tipografía: igual que toda plantilla predeterminada — Times New Roman,
cuerpo 11pt, subtítulo de sección 12pt.

Es idempotente: si ya existe una plantilla predeterminada global con este
mismo nombre, no toca nada.

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_registro_observacion
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

CLAVE_TIPO = "registro_observacion_conductual"
NOMBRE_TIPO = "Registro de observación conductual"
NOMBRE_PLANTILLA = "Registro de observación conductual (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección, las
# opciones fijas de cada lista de casillas, y únicamente los títulos de
# columna de la tabla; ninguna fila de ejemplo.
SECCIONES = [
    ("datos_filiacion", "Datos del estudiante", None),
    ("datos_familiares", None, None),
    (
        "ficha_imprimible",
        None,  # continúa la sección I, sin un segundo encabezado
        {
            "campos_encabezado": [
                "Edad",
                "Fecha de observación",
                "Hora de inicio",
                "Hora de término",
                "Observador(a)",
            ],
            "listas_checkbox": [
                {"titulo": "Nivel", "opciones": ["Inicial", "Primaria", "Secundaria"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        "Datos del contexto de observación",
        {
            "listas_checkbox": [
                {
                    "titulo": "Lugar",
                    "opciones": [
                        "Aula de clases",
                        "Patio o recreo",
                        "Aula de tutoría",
                        "Actividad grupal",
                        "Educación física",
                        "Otro",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Actividad que se realizaba", None),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección II, sin un segundo encabezado
        {
            "listas_checkbox": [
                {
                    "titulo": "Personas presentes",
                    "opciones": ["Docente", "Compañeros", "Auxiliar", "Psicólogo(a)", "Otros"],
                },
            ],
        },
    ),
    (
        "ficha_imprimible",
        "Motivo de la observación",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Dificultades de aprendizaje",
                        "Dificultades de atención",
                        "Dificultades de regulación emocional",
                        "Conductas que interfieren con las actividades escolares",
                        "Dificultades de interacción social",
                        "Seguimiento de estrategias de apoyo",
                        "Solicitud del docente",
                        "Otro",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Descripción del motivo", None),
    (
        "tabla_dinamica",
        "Registro de conductas observadas",
        {
            "columnas": [
                {"titulo": "Fecha y hora", "origen": "libre"},
                {"titulo": "Situación o conducta observable", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    (
        "ficha_imprimible",
        "Características de la conducta",
        {
            "listas_checkbox": [
                {"titulo": "Frecuencia observada", "opciones": ["Una vez", "Varias veces", "Repetida durante la observación"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "campos_encabezado": ["Duración aproximada"],
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "listas_checkbox": [
                {"titulo": "Intensidad observable", "opciones": ["Leve", "Moderada", "Alta"]},
            ],
            "leyenda": "La intensidad debe describirse con criterios observables previamente definidos, cuando corresponda.",
        },
    ),
    (
        "ficha_imprimible",
        None,  # continúa la misma sección V, sin un segundo encabezado
        {
            "listas_checkbox": [
                {
                    "titulo": "Actividad en la que se presentó",
                    "opciones": ["Individual", "Grupal", "Académica", "Recreativa", "Transición entre actividades"],
                },
            ],
        },
    ),
    (
        "ficha_imprimible",
        "Respuesta del estudiante ante las indicaciones",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Sigue la instrucción inmediatamente",
                        "Sigue la instrucción después de repetirla",
                        "Requiere acompañamiento individual",
                        "Solicita ayuda",
                        "Interrumpe la actividad",
                        "Abandona temporalmente la tarea",
                        "Otra respuesta observable",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Descripción de la respuesta del estudiante", None),
    (
        "ficha_imprimible",
        "Orientaciones o acciones sugeridas",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Mantener observación en otros contextos",
                        "Coordinar con el docente",
                        "Entrevistar al estudiante",
                        "Entrevistar al padre, madre o apoderado",
                        "Implementar estrategias de apoyo en el aula",
                        "Realizar seguimiento psicológico escolar",
                        "Valorar una derivación, si corresponde",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Acciones específicas", None),
    # Una sola firma, centrada — igual que el documento de ejemplo real
    # ("Firma del Departamento de psicología").
    ("firma", None, {"lineas_fijas": ["Departamento de Psicología"]}),
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
