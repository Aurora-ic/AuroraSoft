"""agrupar_dimensiones_por_area

Dos columnas nuevas en `edu_pruebas` para el informe de pruebas vocacionales
con dimensiones PAREADAS por área (CHASIDE: 7 áreas × Intereses/Aptitudes):

- `agrupar_dimensiones_por_area` (Boolean): cuando es True, la sección 5.2
  del PDF agrupa las dimensiones por área (Intereses / Aptitudes / Áreas
  Vocacionales Compatibles) en vez del listado plano de siempre — ver
  crud._agrupar_dimensiones_por_area().
- `recomendacion_generica_default` (Text): recomendación fija de la prueba,
  independiente del tramo alcanzado — mismo rol que motivo_consulta_default
  pero para la sección 7.

Ambas NOT NULL+server_default='false' / nullable sin default: toda prueba
existente conserva exactamente el comportamiento que ya tenía.

Revision ID: d2f7b4a93c58
Revises: a6d4f82c1e7b
Create Date: 2026-10-12 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd2f7b4a93c58'
down_revision: Union[str, Sequence[str], None] = 'a6d4f82c1e7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'edu_pruebas',
        sa.Column('agrupar_dimensiones_por_area', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'edu_pruebas',
        sa.Column('recomendacion_generica_default', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('edu_pruebas', 'recomendacion_generica_default')
    op.drop_column('edu_pruebas', 'agrupar_dimensiones_por_area')
