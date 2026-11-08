"""modo_interpretacion

Revision ID: bf13b309a06b
Revises: 6b114452d5bc
Create Date: 2026-09-23 12:58:13.490464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf13b309a06b'
down_revision: Union[str, Sequence[str], None] = '6b114452d5bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('edu_pruebas', sa.Column('modo_interpretacion', sa.String(), server_default='rango', nullable=False))
    # Deliberadamente solo permite 'rango': 'perfil' no se declara aquí hasta
    # que exista su algoritmo de interpretación (ver Prueba.modo_interpretacion
    # en modulos/educativo/models.py).
    op.create_check_constraint(
        'ck_pruebas_modo_interpretacion_valido',
        'edu_pruebas',
        "modo_interpretacion IN ('rango')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_pruebas_modo_interpretacion_valido', 'edu_pruebas', type_='check')
    op.drop_column('edu_pruebas', 'modo_interpretacion')
