"""Añade la URL del logo institucional.

Revision ID: c20bf1d861a4
Revises: b61a3a9db71c
Create Date: 2026-09-17 00:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c20bf1d861a4"
down_revision: Union[str, Sequence[str], None] = "b61a3a9db71c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("instituciones", sa.Column("logo_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("instituciones", "logo_url")
