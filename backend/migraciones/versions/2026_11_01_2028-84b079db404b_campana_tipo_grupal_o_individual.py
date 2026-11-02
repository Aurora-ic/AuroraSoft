"""campaña: tipo grupal o individual (aplicación individual desde el perfil)

Revision ID: 84b079db404b
Revises: f13ae092ec03
Create Date: 2026-11-01 20:28:18.553574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84b079db404b'
down_revision: Union[str, Sequence[str], None] = 'f13ae092ec03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Toda campaña existente es grupal.
    op.add_column('edu_evaluaciones', sa.Column('tipo', sa.String(), server_default='grupal', nullable=False))
    op.create_check_constraint('ck_evaluaciones_tipo_valido', 'edu_evaluaciones', "tipo IN ('grupal', 'individual')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_evaluaciones_tipo_valido', 'edu_evaluaciones', type_='check')
    op.drop_column('edu_evaluaciones', 'tipo')
