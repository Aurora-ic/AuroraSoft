"""
Carga la cuarta plantilla PREDETERMINADA global del motor de documentos
institucionales — institucion_id=None, el punto de partida que cualquier
colegio puede clonar (POST /documentos/plantillas/{id}/clonar, abierto a
STAFF_CLINICO) y editar como propia.

Modelo real: "Informe psicométrico escolar" (formato de ejemplo real
proporcionado por el usuario) — a diferencia de los tres anteriores
(escolar/padres/docentes, todos narrativos), este consolida los
RESULTADOS CUANTITATIVOS de varias pruebas psicométricas que el mismo
alumno ya rindió (ej. PHQ-9 + GAD-7) en una sola sección.

Usa el tipo_seccion 'resultados_prueba_multiple' (ver migración
2026_10_16_0900-c73e9f1a5b06_seccion_resultados_prueba_multiple.py y
docs/motor-documentos.md) en vez de fijar de antemano cuántas pruebas
consolidar: cada documento real elige, con casillas de selección múltiple
(`EditorResultadosMultiplesVinculables` en aurora_ui), cuáles de las
aplicaciones reales del alumno incluir — nunca una cantidad fija por
plantilla. Cada resultado incluido respeta su propio candado de retención
(informe_liberado/resultado_visible_alumno), de forma independiente.

⚠️ Limitación aceptada, no un bug: esta plantilla NUNCA puede usar
`generar_automaticamente_al_finalizar_examen` (ese enganche exige
EXACTAMENTE una sección 'resultados_prueba' simple) — es, por diseño,
siempre de armado manual: crear el documento, marcar qué pruebas
consolidar, generar la versión.

Reutiliza el MISMO TipoDocumento que las tres plantillas anteriores
('informe_individual_escolar') — mismo alcance/visibilidad/consentimiento.

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
    python -m seeds.seed_plantilla_informe_psicometrico
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
NOMBRE_PLANTILLA = "Informe psicométrico escolar (predeterminado)"

# (tipo_seccion, titulo, config) en el orden real del documento de ejemplo.
# Sin contenido propio — solo el subtítulo real de cada sección; el
# contenido (y, para 'resultados_prueba_multiple', QUÉ pruebas consolidar)
# lo llena cada psicóloga por documento.
SECCIONES = [
    ("datos_filiacion", "Datos generales", None),
    # 🔒 Ver seed_plantilla_informe_escolar.py — 'datos_filiacion' no cubre
    # número de hermanos/vive con/lugar de nacimiento/procedencia, eso vive
    # en 'datos_familiares'. titulo=None: fluye bajo el mismo título "I.
    # DATOS..." de arriba, un solo bloque continuo.
    ("datos_familiares", None, None),
    ("texto_libre", "Motivo de evaluación psicométrica", None),
    ("texto_libre", "Instrumentos aplicados", None),
    ("texto_libre", "Condiciones de aplicación", None),
    ("resultados_prueba_multiple", "Resultados cuantitativos", None),
    ("texto_libre", "Integración de los resultados", None),
    ("texto_libre", "Conclusiones", None),
    ("texto_libre", "Recomendaciones", None),
    # Una sola firma, centrada — igual que el documento de ejemplo real
    # ("Firma del Departamento de psicología" / "Firma y sello").
    ("firma", None, {"lineas_fijas": ["Departamento de Psicología", "Firma y sello"]}),
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
        # MISMO TipoDocumento.
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
            # Nunca aplica a esta plantilla (ver limitación documentada
            # arriba) — explícito, no solo el default de la columna.
            generar_automaticamente_al_finalizar_examen=False,
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
