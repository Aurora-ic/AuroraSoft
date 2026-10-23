"""
Carga la sexta plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia.

Modelo real: "Ficha de monitoreo y seguimiento del estudiante" (formato de
ejemplo real proporcionado por el usuario) — a diferencia de las cinco
anteriores (narrativas o con tablas de filas libres), esta es, en gran
parte, un FORMULARIO: casillas de opción [ ] (frecuencia del monitoreo,
motivo del monitoreo, decisión de seguimiento) y tres firmas en blanco
('firma_triple': Departamento de Psicología / Apoderado / Docente,
coincide exactamente con el shape que motivó ese tipo_seccion). Usa
'ficha_imprimible' SOLO para las 3 listas de casillas — es el único tipo
que las soporta — y 'texto_libre' para todo lo demás (incluidos los dos
"blancos para escribir" largos, ej. "Descripción de la necesidad
identificada"), siguiendo el mismo criterio que las cinco plantillas
anteriores: un campo libre para redactar es 'texto_libre', nunca
'ficha_imprimible.preguntas_abiertas', salvo que la sección entera sea un
formulario de casillas.

🆕 Tercer TipoDocumento nuevo (junto a 'informe_individual_escolar' y
'plan_intervencion_individual') — una ficha de monitoreo PERIÓDICO
(seguimiento repetido en el tiempo) es una clase de documento distinta de
un informe de evaluación puntual o de un plan de intervención hacia
adelante, aunque comparta el mismo alcance/visibilidad/consentimiento.

🔒 Las DOS tablas (IV "Registro periódico de monitoreo", V "Escala de
valoración del progreso") se modelan como 'tabla_dinamica' de filas
libres, NO como la tabla de 'ficha_imprimible' (columnas+filas con
etiquetas fijas) — los 6 "indicadores" de la V del documento real son
explícitamente ilustrativos ("deben seleccionarse según las necesidades
individuales", dice el propio documento), igual de ilustrativos que las
filas de cualquier otra tabla de las plantillas anteriores, así que
reciben el mismo tratamiento: SOLO se cargan los títulos de columna,
ninguna fila de ejemplo (ni las 5 filas en blanco de la IV, ni los 6
indicadores de la V) se carga como contenido — a diferencia de
'ficha_imprimible', cuya tabla si hubiera filas fijas las imprimiría
siempre, sin que la psicóloga pueda agregar/quitar filas por documento.

Reutiliza 'datos_filiacion' + 'datos_familiares' para la sección I, igual
que las cinco plantillas anteriores — "Fecha de inicio del monitoreo" y
"Frecuencia del monitoreo" (checkboxes), que ninguno de los dos resolutores
cubre, se agregan aparte con una sección 'ficha_imprimible' sin título
(fluye como continuación de la misma sección I).

Tipografía: igual que toda plantilla predeterminada — Times New Roman,
cuerpo 11pt, subtítulo de sección 12pt.

Es idempotente: si ya existe una plantilla predeterminada global con este
mismo nombre, no toca nada.

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_ficha_monitoreo
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

CLAVE_TIPO = "ficha_seguimiento_individual"
NOMBRE_TIPO = "Ficha de seguimiento individual"
NOMBRE_PLANTILLA = "Ficha de monitoreo y seguimiento del estudiante (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección, las
# opciones fijas de cada lista de casillas, y únicamente los títulos de
# columna de cada tabla; ninguna fila de ejemplo.
SECCIONES = [
    ("datos_filiacion", "Datos generales", None),
    ("datos_familiares", None, None),
    (
        "ficha_imprimible",
        None,  # continúa la sección I, sin un segundo encabezado
        {
            "campos_encabezado": ["Fecha de inicio del monitoreo"],
            "listas_checkbox": [
                {"titulo": "Frecuencia del monitoreo", "opciones": ["Semanal", "Quincenal", "Mensual"]},
            ],
        },
    ),
    (
        "ficha_imprimible",
        "Motivo del monitoreo",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Atención y concentración",
                        "Rendimiento académico",
                        "Organización y cumplimiento de tareas",
                        "Regulación emocional",
                        "Conducta en el aula",
                        "Interacción con compañeros",
                        "Adaptación escolar",
                        "Seguimiento de intervención psicológica",
                        "Seguimiento posterior a una derivación",
                        "Otro",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Descripción de la necesidad identificada", None),
    ("texto_libre", "Objetivos del seguimiento", None),
    (
        "tabla_dinamica",
        "Registro periódico de monitoreo",
        {
            "columnas": [
                {"titulo": "Fecha", "origen": "libre"},
                {"titulo": "Aspecto monitoreado", "origen": "libre"},
                {"titulo": "Conducta o avance observado", "origen": "libre"},
                {"titulo": "Apoyo proporcionado", "origen": "libre"},
                {"titulo": "Resultado", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    (
        "tabla_dinamica",
        "Escala de valoración del progreso",
        {
            "columnas": [
                {"titulo": "Indicador", "origen": "libre"},
                {"titulo": "Seguimiento 1", "origen": "libre"},
                {"titulo": "Seguimiento 2", "origen": "libre"},
                {"titulo": "Seguimiento 3", "origen": "libre"},
                {"titulo": "Seguimiento 4", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    ("texto_libre", "Apreciación del docente", None),
    ("texto_libre", "Información proporcionada por la familia", None),
    ("texto_libre", "Percepción del estudiante", None),
    ("texto_libre", "Fortalezas y avances identificados", None),
    ("texto_libre", "Dificultades que persisten", None),
    ("texto_libre", "Condiciones que favorecen el progreso", None),
    ("texto_libre", "Apoyos que requieren ajustes", None),
    (
        "ficha_imprimible",
        "Decisión de seguimiento",
        {
            "listas_checkbox": [
                {
                    "titulo": "",
                    "opciones": [
                        "Continuar con las estrategias actuales",
                        "Ajustar las estrategias implementadas",
                        "Ampliar el periodo de monitoreo",
                        "Realizar una entrevista con la familia",
                        "Coordinar con otros profesionales autorizados",
                        "Considerar una derivación externa",
                        "Cerrar el seguimiento por cumplimiento de los objetivos acordados",
                    ],
                },
            ],
        },
    ),
    ("texto_libre", "Justificación de la decisión", None),
    ("texto_libre", "Observaciones finales", None),
    # Tres firmas — izquierda el profesional responsable real, derecha y
    # centro solo rótulos fijos (nunca nombre de una persona), igual al
    # documento de ejemplo real ("Firma del Departamento de psicología" /
    # "Firma del apoderado" / "Firma del Docente"). Primer uso real de
    # 'firma_triple' en una plantilla predeterminada.
    (
        "firma_triple",
        None,
        {
            "izquierda": {"lineas_fijas": ["Departamento de Psicología"]},
            "derecha": {"cargo_fijo": "Apoderado"},
            "centro": {"cargo_fijo": "Docente"},
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
