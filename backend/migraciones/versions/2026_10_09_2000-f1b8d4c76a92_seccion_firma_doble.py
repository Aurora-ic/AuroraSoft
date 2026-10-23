"""seccion_firma_doble

Noveno `tipo_seccion` del motor de documentos institucionales:
'firma_doble' — dos bloques de firma lado a lado y simétricos (ej. "Psicóloga
— Departamento de Psicología" a la izquierda, "Convivencia escolar —
Corporación Cyber" a la derecha, sin solicitante nombrado), para una carta
institucional que cierra con dos responsables distintos en vez de uno solo
(eso ya lo cubre 'firma'). Mismo criterio que la incorporación de
'grupo_campos' (migración 2026_09_29_1000-b9fb300190a4): ensancha el CHECK,
no agrega tabla nueva — el contenido sigue viviendo en
PlantillaSeccion.config (qué líneas fijas lleva cada lado) y en
DocumentoInstitucionalSeccionContenido (nada que llenar por documento: el
lado izquierdo se resuelve del mismo Usuario responsable que ya usa 'firma'
simple, el derecho es texto fijo de plantilla).

Revision ID: f1b8d4c76a92
Revises: a3f7c9b21e04
Create Date: 2026-10-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1b8d4c76a92'
down_revision: Union[str, Sequence[str], None] = 'a3f7c9b21e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', 'firma_doble')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos')",
    )
