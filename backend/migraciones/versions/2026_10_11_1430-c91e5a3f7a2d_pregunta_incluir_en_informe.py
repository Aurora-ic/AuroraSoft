"""pregunta_incluir_en_informe

Dos columnas nuevas en `edu_preguntas` para ítems informativos del informe
PDF que no puntúan (típicamente con dimension_id IS NULL, ya ignorados por
core/algoritmo.py:calcular_likert_generico): `incluir_en_informe` marca que
la respuesta debe imprimirse literal en la sección 5.2 del informe,
`etiqueta_informe` es el rótulo bajo el que aparece (ej. "Indicador de
Disfuncionalidad" para el ítem 10 del PHQ-9, que el protocolo clínico pide
reportar pero no puntúa). NOT NULL + server_default='false': cero cambio de
comportamiento para cualquier pregunta ya cargada.

Revision ID: c91e5a3f7a2d
Revises: b84f06e2d751
Create Date: 2026-10-11 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c91e5a3f7a2d'
down_revision: Union[str, Sequence[str], None] = 'b84f06e2d751'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_preguntas', sa.Column('incluir_en_informe', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('edu_preguntas', sa.Column('etiqueta_informe', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_preguntas', 'etiqueta_informe')
    op.drop_column('edu_preguntas', 'incluir_en_informe')
