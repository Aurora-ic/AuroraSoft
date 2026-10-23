"""escala_por_pregunta

Columnas nuevas en `edu_preguntas`: `escala_minima`/`escala_maxima`
(Integer, nullable). Cierra un hallazgo real de la auditoría de motor de la
sesión 2026-10-12: la fórmula de inversión de ítems
(`(escala_minima+escala_maxima)-valor`) usaba SIEMPRE la escala de
`Prueba` completa, nunca la del ítem individual. Hoy eso es inofensivo
porque los 14 instrumentos cargados mantienen una escala uniforme para
todos sus ítems invertidos (verificado en la auditoría), pero es un
supuesto que ningún código garantiza — un instrumento futuro con escalas
heterogéneas (ej. NICHQ Vanderbilt, que ya mezcla 0-3 y 1-5 aunque hoy no
invierte ningún ítem) podría recodificar con la escala equivocada sin
ningún error ni aviso.

NULL por defecto: cuando una pregunta no define su propia escala,
`core.algoritmo.resolver_escala_item()` usa la escala de la Prueba como
respaldo — exactamente el comportamiento de siempre. Cero cambio para
cualquier pregunta ya cargada.

Revision ID: f4d8a1c6b2e7
Revises: c92a4f7d5e13
Create Date: 2026-10-13 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4d8a1c6b2e7'
down_revision: Union[str, Sequence[str], None] = 'c92a4f7d5e13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_preguntas', sa.Column('escala_minima', sa.Integer(), nullable=True))
    op.add_column('edu_preguntas', sa.Column('escala_maxima', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_preguntas', 'escala_maxima')
    op.drop_column('edu_preguntas', 'escala_minima')
