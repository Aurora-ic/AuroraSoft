"""auditoria_lecturas_documentos

Revision ID: c47a2e91f0b6
Revises: 34d35dc8d70e
Create Date: 2026-09-28 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c47a2e91f0b6'
down_revision: Union[str, Sequence[str], None] = '34d35dc8d70e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'documentos_registro_lecturas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('leido_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('rol_lector', sa.String(), nullable=True),
        sa.Column('fecha_lectura', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ip_lectura', sa.String(), nullable=True),
        sa.Column('tipo_acceso', sa.String(), nullable=False),
        sa.Column('numero_version_leida', sa.Integer(), nullable=True),
        sa.Column('acceso_via_visibilidad_colegio', sa.Boolean(), server_default='false', nullable=False),
        sa.CheckConstraint("tipo_acceso IN ('contenido', 'descarga_pdf')", name='ck_documentos_registro_lecturas_tipo_acceso_valido'),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['leido_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documentos_registro_lecturas_id'), 'documentos_registro_lecturas', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_registro_lecturas_documento_institucional_id'), 'documentos_registro_lecturas', ['documento_institucional_id'], unique=False)
    op.create_index(op.f('ix_documentos_registro_lecturas_institucion_id'), 'documentos_registro_lecturas', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_registro_lecturas_leido_por_usuario_id'), 'documentos_registro_lecturas', ['leido_por_usuario_id'], unique=False)
    op.create_index(op.f('ix_documentos_registro_lecturas_fecha_lectura'), 'documentos_registro_lecturas', ['fecha_lectura'], unique=False)
    op.create_index(op.f('ix_documentos_registro_lecturas_tipo_acceso'), 'documentos_registro_lecturas', ['tipo_acceso'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_documentos_registro_lecturas_tipo_acceso'), table_name='documentos_registro_lecturas')
    op.drop_index(op.f('ix_documentos_registro_lecturas_fecha_lectura'), table_name='documentos_registro_lecturas')
    op.drop_index(op.f('ix_documentos_registro_lecturas_leido_por_usuario_id'), table_name='documentos_registro_lecturas')
    op.drop_index(op.f('ix_documentos_registro_lecturas_institucion_id'), table_name='documentos_registro_lecturas')
    op.drop_index(op.f('ix_documentos_registro_lecturas_documento_institucional_id'), table_name='documentos_registro_lecturas')
    op.drop_index(op.f('ix_documentos_registro_lecturas_id'), table_name='documentos_registro_lecturas')
    op.drop_table('documentos_registro_lecturas')
