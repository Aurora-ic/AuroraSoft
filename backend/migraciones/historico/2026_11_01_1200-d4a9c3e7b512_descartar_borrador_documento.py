"""descartar borrador de documento institucional (soft-delete)

Revision ID: d4a9c3e7b512
Revises: c7d2e41f9a3b
Create Date: 2026-11-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a9c3e7b512'
down_revision: Union[str, Sequence[str], None] = 'c7d2e41f9a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Ambas NULL en toda fila existente: ningún documento estaba descartado.
    # Ver DocumentoInstitucional.descartado_en para el porqué del soft-delete.
    op.add_column(
        'documentos_institucionales',
        sa.Column('descartado_en', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'documentos_institucionales',
        sa.Column('descartado_por_usuario_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'documentos_institucionales_descartado_por_usuario_id_fkey',
        'documentos_institucionales', 'auth_usuarios',
        ['descartado_por_usuario_id'], ['id'],
    )
    # Un descartado tuvo que ser borrador: con versión emitida no se descarta.
    op.create_check_constraint(
        'ck_documentos_institucionales_descartado_solo_borrador',
        'documentos_institucionales',
        "descartado_en IS NULL OR version_actual IS NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_documentos_institucionales_descartado_solo_borrador', 'documentos_institucionales', type_='check')
    op.drop_constraint('documentos_institucionales_descartado_por_usuario_id_fkey', 'documentos_institucionales', type_='foreignkey')
    op.drop_column('documentos_institucionales', 'descartado_por_usuario_id')
    op.drop_column('documentos_institucionales', 'descartado_en')
