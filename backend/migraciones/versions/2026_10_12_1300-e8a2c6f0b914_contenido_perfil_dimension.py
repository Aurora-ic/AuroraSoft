"""contenido_perfil_dimension

Tres columnas nuevas en `edu_dimensiones` para el informe de pruebas con
`Prueba.modo_interpretacion='perfil'` (IPIP-RIASEC es la primera en usarlas):
ese modo nunca consulta Baremo, así que `Baremo.interpretacion`/
`conclusion_sugerida`/`recomendacion_sugerida` no tienen ningún tramo al
que anclarse. `contenido_perfil_predominante`/`contenido_perfil_secundaria`
(elegido según si la dimensión queda entre las top-N de esta aplicación) y
`conclusion_sugerida_perfil` cumplen el mismo rol, anclados a la Dimension
en vez de a un Baremo — ver docstring en modulos/educativo/models.py.

Las tres nullable sin default: toda dimensión existente queda exactamente
igual, cero cambio de comportamiento.

Revision ID: e8a2c6f0b914
Revises: d2f7b4a93c58
Create Date: 2026-10-12 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e8a2c6f0b914'
down_revision: Union[str, Sequence[str], None] = 'd2f7b4a93c58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_dimensiones', sa.Column('contenido_perfil_predominante', sa.Text(), nullable=True))
    op.add_column('edu_dimensiones', sa.Column('contenido_perfil_secundaria', sa.Text(), nullable=True))
    op.add_column('edu_dimensiones', sa.Column('conclusion_sugerida_perfil', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_dimensiones', 'conclusion_sugerida_perfil')
    op.drop_column('edu_dimensiones', 'contenido_perfil_secundaria')
    op.drop_column('edu_dimensiones', 'contenido_perfil_predominante')
