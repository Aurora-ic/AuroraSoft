"""plantillas de documento: varias activas por institución y tipo

Revision ID: e8b1f2a4c6d3
Revises: d4a9c3e7b512
Create Date: 2026-11-01 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b1f2a4c6d3'
down_revision: Union[str, Sequence[str], None] = 'd4a9c3e7b512'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # "activa" pasa a significar "disponible para generar": las 4 plantillas
    # de informe del catálogo comparten TipoDocumento y una institución debe
    # poder usar varias a la vez (ver la nota en modulos/documentos/crud.py).
    op.drop_index('uq_documentos_plantilla_activa_por_institucion_y_tipo', table_name='documentos_plantillas')


def downgrade() -> None:
    """Downgrade schema."""
    # ⚠️ Volver atrás obliga a elegir UNA activa por institución+tipo: se
    # conserva la más reciente y se desactivan las demás antes de recrear
    # el índice (acción de desarrollo, nunca de producción con datos reales).
    op.execute("""
        UPDATE documentos_plantillas p SET activa = false
        WHERE p.activa = true AND p.institucion_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM documentos_plantillas q
            WHERE q.activa = true AND q.institucion_id = p.institucion_id
              AND q.tipo_documento_id = p.tipo_documento_id AND q.id > p.id
          )
    """)
    op.create_index(
        'uq_documentos_plantilla_activa_por_institucion_y_tipo',
        'documentos_plantillas', ['institucion_id', 'tipo_documento_id'],
        unique=True, postgresql_where=sa.text("activa = true"),
    )
