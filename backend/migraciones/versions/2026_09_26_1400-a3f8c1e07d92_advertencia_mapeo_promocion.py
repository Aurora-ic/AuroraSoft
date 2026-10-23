"""advertencia_mapeo_promocion

Revision ID: a3f8c1e07d92
Revises: 716c022d49bb
Create Date: 2026-09-26 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c1e07d92'
down_revision: Union[str, Sequence[str], None] = '716c022d49bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'procesos_promocion_detalle',
        sa.Column('advertencia_mapeo', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('procesos_promocion_detalle', 'advertencia_mapeo')
