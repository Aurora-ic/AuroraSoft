"""ordenar_dimensiones_por_puntaje

Revision ID: 92461c40d56e
Revises: a3be794d45e0
Create Date: 2026-09-30 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92461c40d56e'
down_revision: Union[str, Sequence[str], None] = 'a3be794d45e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 "Diseño A" para pruebas de PERFIL (ver IPIP-RIASEC en CLAUDE.md):
    # cuando es True, el informe PDF ordena las dimensiones por puntaje
    # descendente e imprime un "código de perfil" (top-3) bajo el gráfico de
    # la sección 5.1, en vez del orden de creación fijo de siempre. Pura
    # presentación — no toca Baremo/DiagnosticoAlumno ni la interpretación.
    # NOT NULL + server_default='false': toda prueba existente conserva
    # exactamente el orden que ya tenía, cero cambio de comportamiento.
    op.add_column(
        'edu_pruebas',
        sa.Column('ordenar_dimensiones_por_puntaje', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('edu_pruebas', 'ordenar_dimensiones_por_puntaje')
