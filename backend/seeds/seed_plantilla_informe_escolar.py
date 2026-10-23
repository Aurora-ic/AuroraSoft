"""
Carga la primera plantilla PREDETERMINADA global del motor de documentos
institucionales (modulos/documentos/) — institucion_id=None, el punto de
partida que cualquier colegio puede clonar (POST /documentos/plantillas/
{id}/clonar, abierto a STAFF_CLINICO) y editar como propia. Nunca se
modifica por el uso de un colegio: cada clon es una fila independiente
desde el momento en que se crea.

Modelo real: "Informe psicológico escolar" (formato de ejemplo real
proporcionado por el usuario). El CONTENIDO del documento original es
puramente ilustrativo (nombre ficticio, datos simulados) — lo único que se
carga aquí son los SUBTÍTULOS reales de cada sección, en el orden real del
documento. El contenido lo escribe cada psicóloga, por documento, al
llenarlo.

Tipografía: Times New Roman, cuerpo 11pt, subtítulo de sección 12pt —
"siempre", según el pedido original: estos son los valores por defecto de
TODA plantilla predeterminada que se cargue de aquí en adelante, no algo
específico de este documento. Negrita de subtítulo/título/firma es el
comportamiento fijo de siempre del motor (nunca configurable) — ver
pdf_generador._construir_estilos.

🔒 Corrección (sesión de la 5ª plantilla predeterminada): esta plantilla
originalmente solo tenía 'datos_filiacion' para la sección I — le faltaba
'datos_familiares' (número de hermanos/vive con/lugar de nacimiento/
procedencia, campos reales del documento que 'datos_filiacion' nunca
cubrió). Si ya habías corrido este seed antes de esta corrección, borra la
plantilla existente y vuelve a correrlo (el chequeo de idempotencia no
actualiza una fila ya creada).

Es idempotente: si ya existe una plantilla predeterminada global (
institucion_id IS NULL) con este mismo nombre, no toca nada — nunca pisa una
plantilla que AuroraSoft ya haya ajustado a mano después de la carga
inicial. Para forzar una recarga completa, desactiva o borra la plantilla
existente antes de volver a correr este script. El tipo 'informe_individual_
escolar' puede terminar con MÁS de una predeterminada activa (ver
seed_plantilla_informe_padres.py) — el catálogo global es un menú de
formatos, no "la plantilla vigente de este tipo".

Requiere que ya exista al menos un usuario superadmin (ver seed_superadmin)
— es quien queda como creado_por_usuario_id de la plantilla.

Ejecutar (una sola vez, tras `alembic upgrade head` y `python -m
seeds.seed_superadmin`):
    python -m seeds.seed_plantilla_informe_escolar
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
NOMBRE_PLANTILLA = "Informe psicológico escolar (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección; el
# contenido lo llena cada psicóloga por documento.
SECCIONES = [
    ("datos_filiacion", "Datos de identificación", None),
    # 🔒 Encontrado al construir la 5ª plantilla predeterminada: "Número de
    # hermanos"/"Vive con"/"Lugar de nacimiento"/"Lugar de procedencia" del
    # documento real NO los cubre 'datos_filiacion' (solo nombre/sexo/fecha
    # de nacimiento/documento/grado + los 4 campos nuevos) — viven en su
    # propio tipo_seccion 'datos_familiares' (PersonaDatosFamiliares), que
    # esta plantilla nunca había incluido. titulo=None para que fluya como
    # un solo bloque continuo bajo el título de 'datos_filiacion' de
    # arriba, igual que se ve en el documento de papel real (un solo "I.
    # DATOS..." sin sub-encabezado propio para la parte familiar).
    ("datos_familiares", None, None),
    ("texto_libre", "Antecedentes familiares", None),
    ("texto_libre", "Antecedentes escolares", None),
    ("texto_libre", "Antecedentes personales y socioemocionales", None),
    ("texto_libre", "Técnicas e instrumentos utilizados", None),
    ("texto_libre", "Área cognitiva y atencional", None),
    ("texto_libre", "Área visomotora", None),
    ("texto_libre", "Área emocional", None),
    ("texto_libre", "Área académica y familiar", None),
    ("texto_libre", "Integración e interpretación psicológica", None),
    ("texto_libre", "Conclusiones", None),
    ("texto_libre", "Recomendaciones para el estudiante", None),
    ("texto_libre", "Recomendaciones para la familia", None),
    ("texto_libre", "Recomendaciones para la institución educativa", None),
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

        # 🔒 Se compara por NOMBRE, no solo por tipo_documento_id — desde que
        # el catálogo global permite varias predeterminadas activas bajo el
        # MISMO TipoDocumento (ver migración
        # f28b6a3c0e91_quitar_unicidad_predeterminada_por_tipo.py), filtrar
        # solo por tipo encontraría una predeterminada DISTINTA ya cargada
        # bajo ese mismo tipo (ej. la de "Informe para padres") y se saltaría
        # esta por error, creyéndola ya creada.
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
