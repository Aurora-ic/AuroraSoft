"""Familiares en contactos_familiares: registro único por familiar

Agrega a `contactos_familiares` los datos de la composición familiar
(apellidos, apoderado, contacto, vive con el estudiante, ocupación, grado de
instrucción, estado civil, dirección, distrito, fecha de nacimiento).

Solo AGREGA columnas, todas opcionales o con default: ninguna fila existente
cambia de significado (las anteriores eran todas contactos, por eso
`es_contacto` nace en true). El downgrade las quita sin tocar nada más.

Revision ID: d4f1a7c2e9b5
Revises: b9d1ee03b2f8
Create Date: 2026-11-16 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "d4f1a7c2e9b5"
down_revision = "b9d1ee03b2f8"
branch_labels = None
depends_on = None

TABLA = "contactos_familiares"


def upgrade() -> None:
    op.add_column(TABLA, sa.Column("apellidos", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("es_apoderado", sa.Boolean(), server_default="false", nullable=False))
    op.add_column(TABLA, sa.Column("es_contacto", sa.Boolean(), server_default="true", nullable=False))
    op.add_column(TABLA, sa.Column("vive_con_estudiante", sa.Boolean(), nullable=True))
    op.add_column(TABLA, sa.Column("ocupacion", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("grado_instruccion", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("estado_civil", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("direccion", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("distrito", sa.String(), nullable=True))
    op.add_column(TABLA, sa.Column("fecha_nacimiento", sa.Date(), nullable=True))


def downgrade() -> None:
    for columna in (
        "fecha_nacimiento", "distrito", "direccion", "estado_civil", "grado_instruccion",
        "ocupacion", "vive_con_estudiante", "es_contacto", "es_apoderado", "apellidos",
    ):
        op.drop_column(TABLA, columna)
