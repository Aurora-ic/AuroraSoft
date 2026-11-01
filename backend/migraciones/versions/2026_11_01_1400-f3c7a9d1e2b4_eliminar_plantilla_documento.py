"""eliminar plantilla de documento (soft-delete)

Revision ID: f3c7a9d1e2b4
Revises: e8b1f2a4c6d3
Create Date: 2026-11-01 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c7a9d1e2b4'
down_revision: Union[str, Sequence[str], None] = 'e8b1f2a4c6d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NULL en toda fila existente: ninguna plantilla estaba eliminada. Ver
    # PlantillaDocumento.eliminada_en para el porqué del soft-delete.
    op.add_column('documentos_plantillas', sa.Column('eliminada_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('documentos_plantillas', sa.Column('eliminada_por_usuario_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'documentos_plantillas_eliminada_por_usuario_id_fkey',
        'documentos_plantillas', 'auth_usuarios',
        ['eliminada_por_usuario_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('documentos_plantillas_eliminada_por_usuario_id_fkey', 'documentos_plantillas', type_='foreignkey')
    op.drop_column('documentos_plantillas', 'eliminada_por_usuario_id')
    op.drop_column('documentos_plantillas', 'eliminada_en')
