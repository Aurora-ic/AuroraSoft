"""baremo_trazabilidad_y_soft_delete

Revision ID: 62ba95119cdf
Revises: 186e63c7c8d4
Create Date: 2026-09-23 13:49:02.756113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62ba95119cdf'
down_revision: Union[str, Sequence[str], None] = '186e63c7c8d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('edu_baremos', sa.Column('activo', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('edu_baremos', sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True))
    op.add_column('edu_diagnosticos_alumno', sa.Column('baremo_id', sa.Integer(), nullable=True))
    # Nombre explícito (mismo criterio que regla_activada_id en eb5a393806d2 /
    # revisado_por_usuario_id en e72c49df46b1): autogenerate deja el nombre en
    # blanco, y sin nombre el downgrade no puede encontrar la FK para
    # borrarla. Usamos el nombre que Postgres habría generado por defecto
    # (create_all/crear_tablas.py) para que ambos caminos produzcan el mismo
    # esquema.
    op.create_foreign_key(
        'edu_diagnosticos_alumno_baremo_id_fkey',
        'edu_diagnosticos_alumno', 'edu_baremos', ['baremo_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('edu_diagnosticos_alumno_baremo_id_fkey', 'edu_diagnosticos_alumno', type_='foreignkey')
    op.drop_column('edu_diagnosticos_alumno', 'baremo_id')
    op.drop_column('edu_baremos', 'actualizado_en')
    op.drop_column('edu_baremos', 'activo')
