"""
Carga la quinta plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia.

Modelo real: "Plan de intervención psicológica escolar" (formato de
ejemplo real proporcionado por el usuario) — a diferencia de las cuatro
anteriores (todas informes, siempre dirigidos a describir hallazgos ya
obtenidos), este es un PLAN de trabajo hacia adelante para UN estudiante
puntual: justificación, objetivos, sesiones planificadas, metodología,
indicadores de seguimiento, responsables y resultados esperados.

🆕 Primer TipoDocumento NUEVO desde que se cargó la primera predeterminada
— las cuatro anteriores reutilizaron 'informe_individual_escolar' porque
eran, todas, informes de evaluación del mismo proceso. Un plan de
intervención es una clase de documento genuinamente distinta (no describe
un hallazgo, define un trabajo futuro) aunque comparta el mismo
alcance/visibilidad/consentimiento — se crea 'plan_intervencion_individual'
en vez de reutilizar el tipo existente, consistente con lo que
TipoDocumento representa (ver docstring en models.py): una clase real de
documento, nunca un formato puntual.

🔒 Tres tablas (`tabla_dinamica`, filas libres —
`filas_desde_lista_estudiantes=False`): "Planificación de las sesiones" (4
columnas), "Indicadores de seguimiento" (3 columnas) y "Observaciones y
ajustes" (4 columnas). Mismo criterio ya aplicado a las tablas de las
plantillas anteriores: SOLO se cargan los títulos de columna — ninguna
fila de ejemplo (ni las 8 sesiones ilustrativas de la V, ni las filas
"Sesión 1"..."Sesión 8" en blanco de la XI) se carga como contenido; cada
psicóloga llena sus propias filas por documento.

Reutiliza, en cambio, 'datos_filiacion' + 'datos_familiares' para la
sección I exactamente como las cuatro anteriores (ver seed_plantilla_
informe_escolar.py para la corrección que agregó 'datos_familiares').

Tipografía: igual que toda plantilla predeterminada — Times New Roman,
cuerpo 11pt, subtítulo de sección 12pt.

Es idempotente: si ya existe una plantilla predeterminada global con este
mismo nombre, no toca nada.

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_plan_intervencion
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

CLAVE_TIPO = "plan_intervencion_individual"
NOMBRE_TIPO = "Plan de intervención psicológica"
NOMBRE_PLANTILLA = "Plan de intervención psicológica escolar (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección y, para
# las tablas, únicamente sus columnas; ninguna fila de ejemplo.
SECCIONES = [
    ("datos_filiacion", "Datos generales", None),
    ("datos_familiares", None, None),
    ("texto_libre", "Justificación", None),
    ("texto_libre", "Objetivo general", None),
    ("texto_libre", "Objetivos específicos", None),
    (
        "tabla_dinamica",
        "Planificación de las sesiones",
        {
            "columnas": [
                {"titulo": "Sesión", "origen": "libre"},
                {"titulo": "Objetivo", "origen": "libre"},
                {"titulo": "Actividades", "origen": "libre"},
                {"titulo": "Recursos", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    ("texto_libre", "Metodología de intervención", None),
    (
        "tabla_dinamica",
        "Indicadores de seguimiento",
        {
            "columnas": [
                {"titulo": "Área", "origen": "libre"},
                {"titulo": "Indicador", "origen": "libre"},
                {"titulo": "Medio de verificación", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    ("texto_libre", "Evaluación del proceso", None),
    ("texto_libre", "Responsables y funciones", None),
    ("texto_libre", "Resultados esperados", None),
    (
        "tabla_dinamica",
        "Observaciones y ajustes",
        {
            "columnas": [
                {"titulo": "Sesiones", "origen": "libre"},
                {"titulo": "Avances observados", "origen": "libre"},
                {"titulo": "Dificultades persistentes", "origen": "libre"},
                {"titulo": "Modificaciones al plan", "origen": "libre"},
            ],
            "filas_desde_lista_estudiantes": False,
        },
    ),
    # Dos firmas lado a lado — izquierda siempre el profesional responsable
    # real (Usuario), derecha solo el rótulo fijo "Apoderado" (nunca lleva
    # nombre de una persona), igual que el documento de ejemplo real
    # ("Firma del Departamento de psicología" / "Firma del apoderado").
    (
        "firma_doble",
        None,
        {
            "izquierda": {"lineas_fijas": ["Departamento de Psicología"]},
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
