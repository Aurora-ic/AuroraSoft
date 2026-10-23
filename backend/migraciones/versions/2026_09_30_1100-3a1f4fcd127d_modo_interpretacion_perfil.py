"""modo_interpretacion_perfil

Revision ID: 3a1f4fcd127d
Revises: 92461c40d56e
Create Date: 2026-09-30 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a1f4fcd127d'
down_revision: Union[str, Sequence[str], None] = '92461c40d56e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 "perfil" pasa de ser un placeholder declarado-sin-algoritmo a un
    # modo de interpretación real — ver crud.interpretar_perfil_alumno()/
    # crud.interpretar_segun_modo() y "Interpretación por perfil" en
    # CLAUDE.md. Ninguna prueba existente cambia de modo con esta migración
    # (sigue siendo server_default='rango'); esto solo AMPLÍA el CHECK para
    # permitir el segundo valor.
    op.drop_constraint('ck_pruebas_modo_interpretacion_valido', 'edu_pruebas', type_='check')
    op.create_check_constraint(
        'ck_pruebas_modo_interpretacion_valido',
        'edu_pruebas',
        "modo_interpretacion IN ('rango', 'perfil')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_pruebas_modo_interpretacion_valido', 'edu_pruebas', type_='check')
    op.create_check_constraint(
        'ck_pruebas_modo_interpretacion_valido',
        'edu_pruebas',
        "modo_interpretacion IN ('rango')",
    )
