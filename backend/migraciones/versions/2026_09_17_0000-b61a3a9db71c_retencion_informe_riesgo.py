"""Añade revisión clínica para informes con riesgo.

Revision ID: b61a3a9db71c
Revises: 020fefe2fbfd
Create Date: 2026-09-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b61a3a9db71c"
down_revision: Union[str, Sequence[str], None] = "020fefe2fbfd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "edu_inscripciones",
        sa.Column("informe_liberado", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "edu_inscripciones",
        sa.Column("interpretacion_clinica", sa.Text(), nullable=True),
    )
    op.alter_column("edu_inscripciones", "informe_liberado", server_default=None)


def downgrade() -> None:
    op.drop_column("edu_inscripciones", "interpretacion_clinica")
    op.drop_column("edu_inscripciones", "informe_liberado")
