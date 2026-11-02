"""campaña: alumno_ve_informe (el estudiante ve su resultado y su PDF al terminar)

Revision ID: b7e3f9a2c4d5
Revises: a6d2e8f4b9c1
Create Date: 2026-11-01 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3f9a2c4d5'
down_revision: Union[str, Sequence[str], None] = 'a6d2e8f4b9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Apagado para toda campaña existente: desde ahora el alumno solo ve su
    # resultado si el psicólogo lo enciende en la campaña.
    op.add_column(
        'edu_evaluaciones',
        sa.Column('alumno_ve_informe', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('edu_evaluaciones', 'alumno_ve_informe')
