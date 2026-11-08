"""registro_cambios_persona

Revision ID: 9424f38351ae
Revises: 62ba95119cdf
Create Date: 2026-09-25 22:29:53.961748

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9424f38351ae'
down_revision: Union[str, Sequence[str], None] = '62ba95119cdf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('registro_cambios_persona',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('persona_id', sa.Integer(), nullable=False),
    sa.Column('institucion_id', sa.Integer(), nullable=False),
    sa.Column('campo', sa.String(), nullable=False),
    sa.Column('valor_anterior', sa.Text(), nullable=True),
    sa.Column('valor_nuevo', sa.Text(), nullable=True),
    sa.Column('modificado_por_usuario_id', sa.Integer(), nullable=False),
    sa.Column('rol_modificador', sa.String(), nullable=True),
    sa.Column('fecha', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], ),
    sa.ForeignKeyConstraint(['modificado_por_usuario_id'], ['auth_usuarios.id'], ),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_registro_cambios_persona_fecha'), 'registro_cambios_persona', ['fecha'], unique=False)
    op.create_index(op.f('ix_registro_cambios_persona_id'), 'registro_cambios_persona', ['id'], unique=False)
    op.create_index(op.f('ix_registro_cambios_persona_institucion_id'), 'registro_cambios_persona', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_registro_cambios_persona_persona_id'), 'registro_cambios_persona', ['persona_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_registro_cambios_persona_persona_id'), table_name='registro_cambios_persona')
    op.drop_index(op.f('ix_registro_cambios_persona_institucion_id'), table_name='registro_cambios_persona')
    op.drop_index(op.f('ix_registro_cambios_persona_id'), table_name='registro_cambios_persona')
    op.drop_index(op.f('ix_registro_cambios_persona_fecha'), table_name='registro_cambios_persona')
    op.drop_table('registro_cambios_persona')
