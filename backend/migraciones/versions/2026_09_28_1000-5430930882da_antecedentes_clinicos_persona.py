"""antecedentes_clinicos_persona

Revision ID: 5430930882da
Revises: 9f13619766a9
Create Date: 2026-09-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5430930882da'
down_revision: Union[str, Sequence[str], None] = '9f13619766a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'personas_antecedentes_clinicos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('recibe_terapia_psicologica_externa', sa.Boolean(), nullable=True),
        sa.Column('detalle_terapia_psicologica_externa', sa.Text(), nullable=True),
        sa.Column('recibe_atencion_psiquiatrica_externa', sa.Boolean(), nullable=True),
        sa.Column('detalle_atencion_psiquiatrica_externa', sa.Text(), nullable=True),
        sa.Column('diagnostico_reportado', sa.Text(), nullable=True),
        sa.Column('actualizado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_personas_antecedentes_clinicos_id'), 'personas_antecedentes_clinicos', ['id'], unique=False)
    # unique=True en el ÍNDICE (no una UniqueConstraint aparte): así es
    # exactamente como SQLAlchemy emite `Column(..., unique=True, index=True)`
    # — mismo ajuste ya aplicado a personas_datos_familiares tras el drift
    # que detectó `alembic check` en la migración anterior.
    op.create_index(op.f('ix_personas_antecedentes_clinicos_persona_id'), 'personas_antecedentes_clinicos', ['persona_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_personas_antecedentes_clinicos_persona_id'), table_name='personas_antecedentes_clinicos')
    op.drop_index(op.f('ix_personas_antecedentes_clinicos_id'), table_name='personas_antecedentes_clinicos')
    op.drop_table('personas_antecedentes_clinicos')
