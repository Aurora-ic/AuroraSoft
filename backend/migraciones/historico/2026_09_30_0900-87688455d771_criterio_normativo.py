"""criterio_normativo

Revision ID: 87688455d771
Revises: 486fadd173f0
Create Date: 2026-09-30 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87688455d771'
down_revision: Union[str, Sequence[str], None] = '486fadd173f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Criterio normativo — eje INDEPENDIENTE de Baremo.activo (que sigue
    # significando exclusivamente trazabilidad/corrección, nunca esto).
    # Apareció con GAD-7 (corte clásico ≥10 vs. corte peruano ≥8) y de nuevo
    # con APGAR-FAMILIAR (dos tablas de corte peruanas contradictorias): más
    # de un criterio de interpretación válido y documentado para el mismo
    # rango de puntaje, que antes no se podía cargar simultáneamente porque
    # la validación de solapamiento lo rechazaba con 409.
    #
    # NULL (toda fila existente) significa "el único criterio" — cero cambio
    # de comportamiento. Un valor no-NULL es una etiqueta libre que identifica
    # un lente alternativo: dos tramos con criterio_normativo distinto pueden
    # solaparse en rango de puntaje sin disparar el 409 de solapamiento.
    op.add_column('edu_baremos', sa.Column('criterio_normativo', sa.String(), nullable=True))

    # 🆕 Cuál de los criterios cargados aplica para interpretar ESTA prueba.
    # NULL (toda fila existente) = interpretar contra los tramos con
    # criterio_normativo IS NULL, que es exactamente lo único que existe hoy.
    op.add_column('edu_pruebas', sa.Column('criterio_normativo_activo', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('edu_pruebas', 'criterio_normativo_activo')
    op.drop_column('edu_baremos', 'criterio_normativo')
