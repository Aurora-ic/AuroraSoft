"""nombre_corto_prueba

Columna nueva en `edu_pruebas`: `nombre_corto` (nullable). Pensada para la
UI (listado de campañas, catálogo de instrumentos, selects de prueba),
donde `nombre_publico` suele ser demasiado largo para un título ("Escala de
Hamilton — versión de autoinforme (NO es la HDRS-17 clínica heteroaplicada
oficial — ver notas del catálogo)") y `nombre_tecnico` no siempre es un
nombre reconocible para un psicólogo (ej. "HAMILTON_AUTOINFORME",
"VANDERBILT_PADRES" son identificadores internos en mayúsculas/snake_case,
a diferencia de "PHQ-9"/"GAD-7"/"DASS-21", que SÍ funcionan como título
corto tal cual).

NULL por defecto: cuando una prueba no define `nombre_corto`, la UI debe
usar `nombre_tecnico` como respaldo (ya es un título corto razonable para
la mayoría de instrumentos) — este campo es la excepción curada, no la
regla. `nombre_tecnico` NUNCA se renombra para esto: sigue siendo el
identificador ESTABLE que usan los seeds/lookups/documentación; este campo
nuevo es puramente de presentación.

Revision ID: e6b1d4a9c3f5
Revises: d3a7c5f8e912
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e6b1d4a9c3f5'
down_revision: Union[str, Sequence[str], None] = 'd3a7c5f8e912'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_pruebas', sa.Column('nombre_corto', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_pruebas', 'nombre_corto')
