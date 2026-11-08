"""Añade visibilidad y auditoría de la revisión de informes.

Revision ID: e72c49df46b1
Revises: c20bf1d861a4
Create Date: 2026-09-17 00:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e72c49df46b1"
down_revision: Union[str, Sequence[str], None] = "c20bf1d861a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "edu_inscripciones",
        sa.Column("resultado_visible_alumno", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "edu_inscripciones",
        sa.Column("revisado_por_usuario_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "edu_inscripciones",
        sa.Column("fecha_revision_informe", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_edu_inscripciones_revisado_por_usuario",
        "edu_inscripciones",
        "auth_usuarios",
        ["revisado_por_usuario_id"],
        ["id"],
    )
    op.alter_column("edu_inscripciones", "resultado_visible_alumno", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_edu_inscripciones_revisado_por_usuario", "edu_inscripciones", type_="foreignkey")
    op.drop_column("edu_inscripciones", "fecha_revision_informe")
    op.drop_column("edu_inscripciones", "revisado_por_usuario_id")
    op.drop_column("edu_inscripciones", "resultado_visible_alumno")
