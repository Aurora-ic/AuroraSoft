"""generar_documento_automatico

Revision ID: 257c42b857f6
Revises: e4ab309bbab8
Create Date: 2026-10-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '257c42b857f6'
down_revision: Union[str, Sequence[str], None] = 'e4ab309bbab8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Enganche motor de pruebas -> motor de documentos: cuando está en
    # True, cada examen finalizado de la institución dueña de esta
    # plantilla genera automáticamente (en segundo plano, tras el commit de
    # finalizar_examen_seguro) un DocumentoInstitucional propio a partir de
    # ESTA plantilla — ver modulos/documentos/crud.py:
    # generar_documentos_automaticos_por_examen. NOT NULL con
    # server_default='false': toda plantilla ya cargada queda exactamente
    # como estaba, cero cambio de comportamiento hasta que un superadmin la
    # activa a propósito en una plantilla concreta.
    op.add_column(
        'documentos_plantillas',
        sa.Column(
            'generar_automaticamente_al_finalizar_examen',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('documentos_plantillas', 'generar_automaticamente_al_finalizar_examen')
