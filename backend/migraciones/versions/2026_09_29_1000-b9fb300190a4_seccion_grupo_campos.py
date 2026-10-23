"""seccion_grupo_campos

Revision ID: b9fb300190a4
Revises: 847f59008bb9
Create Date: 2026-09-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9fb300190a4'
down_revision: Union[str, Sequence[str], None] = '847f59008bb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Octavo tipo_seccion: 'grupo_campos' — un bloque genérico de pares
    # etiqueta/valor definidos por quien arma la plantilla (en
    # PlantillaSeccion.config: {"campos": [{"etiqueta": "..."}, ...]}),
    # llenado por documento en DocumentoInstitucionalSeccionContenido.contenido
    # (ya JSON libre en ambos casos — no hace falta ninguna tabla nueva). Este
    # era justamente el "octavo tipo diferido" que CLAUDE.md documentaba como
    # pospuesto por falta de un pedido concreto; el caso real es una
    # entrevista/anamnesis con preguntas fijas propias de cada colegio, que no
    # encaja ni en 'texto_libre' (sin estructura) ni en los bloques
    # automáticos existentes (datos_filiacion/datos_familiares/resultados_prueba).
    op.drop_constraint('ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check')
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check')
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma')",
    )
