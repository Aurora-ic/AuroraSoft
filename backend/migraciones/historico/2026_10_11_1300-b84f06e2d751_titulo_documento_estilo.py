"""titulo_documento_estilo

Tres columnas nuevas en `documentos_plantillas` para controlar el estilo
del TÍTULO del documento (negrita/cursiva/tamaño), independiente del
cuerpo (fuente/tamano_pt/justificado, sin tocar) — antes `_construir_estilos`
lo forzaba siempre a negrita con tamaño=cuerpo+5. Los defaults reproducen
exactamente ese comportamiento anterior: cero cambio visual para cualquier
plantilla ya cargada hasta que alguien la edite a propósito.

Revision ID: b84f06e2d751
Revises: a7c92e14f630
Create Date: 2026-10-11 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b84f06e2d751'
down_revision: Union[str, Sequence[str], None] = 'a7c92e14f630'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documentos_plantillas', sa.Column('titulo_negrita', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('documentos_plantillas', sa.Column('titulo_cursiva', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('documentos_plantillas', sa.Column('titulo_tamano_pt', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('documentos_plantillas', 'titulo_tamano_pt')
    op.drop_column('documentos_plantillas', 'titulo_cursiva')
    op.drop_column('documentos_plantillas', 'titulo_negrita')
