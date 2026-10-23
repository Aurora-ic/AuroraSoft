"""
Carga la tercera plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia. Nunca se modifica por el uso de un
colegio: cada clon es una fila independiente desde el momento en que se
crea.

Modelo real: "Informe psicológico para docentes" (formato de ejemplo real
proporcionado por el usuario) — la versión dirigida a la docente del mismo
proceso de evaluación que ya tiene su informe escolar (ver
seed_plantilla_informe_escolar.py) y su carta a la familia (ver
seed_plantilla_informe_padres.py). El CONTENIDO del documento original es
puramente ilustrativo — lo único que se carga aquí son los SUBTÍTULOS
reales de cada sección, en el orden real del documento, más la ESTRUCTURA
de su tabla ("Estrategias pedagógicas sugeridas": 3 columnas fijas, filas
libres que llena la psicóloga por documento — mismo mecanismo que la tabla
de "Acuerdos con la familia" del informe para padres).

Reutiliza el MISMO TipoDocumento que los dos anteriores
('informe_individual_escolar') — mismo alcance/visibilidad/consentimiento;
lo que cambia es el FORMATO (plantilla), no la clase de documento. Varias
predeterminadas activas bajo el mismo tipo conviven sin problema: el
catálogo global es un menú, no "la plantilla vigente de este tipo" (ver
migración f28b6a3c0e91_quitar_unicidad_predeterminada_por_tipo.py).

Ningún tipo_seccion nuevo — 'tabla_dinamica' (filas libres) y 'firma_doble'
ya existían y ya tenían editor propio en el constructor del frontend.

Tipografía: igual que toda plantilla predeterminada — Times New Roman,
cuerpo 11pt, subtítulo de sección 12pt.

🔒 Corrección (sesión de la 5ª plantilla predeterminada): le faltaba
'datos_familiares' para la sección I — ver seed_plantilla_informe_
escolar.py. Si ya habías corrido este seed antes, borra la plantilla
existente y vuelve a correrlo.

Es idempotente: si ya existe una plantilla predeterminada global con este
mismo nombre, no toca nada.

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_informe_docentes
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

CLAVE_TIPO = "informe_individual_escolar"
NOMBRE_TIPO = "Informe psicológico escolar"
NOMBRE_PLANTILLA = "Informe psicológico para docentes (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección (y, para la
# tabla, sus columnas fijas); el contenido/las filas las llena cada
# psicóloga por documento.
SECCIONES = [
    ("datos_filiacion", "Datos del estudiante", None),
    # 🔒 Ver seed_plantilla_informe_escolar.py — 'datos_filiacion' no cubre
    # número de hermanos/vive con/lugar de nacimiento/procedencia, eso vive
    # en 'datos_familiares'. titulo=None: fluye bajo el mismo título "I.
    # DATOS..." de arriba, un solo bloque continuo.
    ("datos_familiares", None, None),
    ("texto_libre", "Objetivo del informe", None),
    ("texto_libre", "Fortalezas y recursos del estudiante", None),
    ("texto_libre", "Necesidades de apoyo en el aula", None),
    (
        "tabla_dinamica",
        "Estrategias pedagógicas sugeridas",
        {
            "columnas": [
                {"titulo": "Necesidad identificada", "origen": "libre"},
                {"titulo": "Estrategia docente", "origen": "libre"},
                {"titulo": "Indicador de seguimiento", "origen": "libre"},
            ],
            # Filas libres (la psicóloga las agrega a mano por documento) —
            # no ligadas a la lista congelada de estudiantes.
            "filas_desde_lista_estudiantes": False,
        },
    ),
    ("texto_libre", "Pautas para la interacción docente", None),
    ("texto_libre", "Coordinación y seguimiento", None),
    # Dos firmas lado a lado — izquierda siempre el profesional responsable
    # real (Usuario), derecha solo el rótulo fijo "Docente" (nunca lleva
    # nombre de una persona), igual que el documento de ejemplo real
    # ("Firma del Departamento de psicología" / "Firma del Docente").
    (
        "firma_doble",
        None,
        {
            "izquierda": {"lineas_fijas": ["Departamento de Psicología"]},
            "derecha": {"cargo_fijo": "Docente"},
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

        # 🔒 Se compara por NOMBRE, no solo por tipo_documento_id — el
        # catálogo global permite varias predeterminadas activas bajo el
        # MISMO TipoDocumento (ver migración
        # f28b6a3c0e91_quitar_unicidad_predeterminada_por_tipo.py).
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
