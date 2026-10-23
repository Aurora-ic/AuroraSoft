"""firma_imagen_usuario

Agrega `auth_usuarios.firma_imagen_url` — la imagen de firma personal
(escaneada o digital) que el motor de documentos institucionales dibuja en
los tipo_seccion 'firma'/'firma_doble' en vez de la línea de subrayado
genérica. Columna nullable, sin backfill: cero cambio de comportamiento
hasta que cada usuario suba la suya.

Revision ID: c2a94e8d1b37
Revises: f1b8d4c76a92
Create Date: 2026-10-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2a94e8d1b37'
down_revision: Union[str, Sequence[str], None] = 'f1b8d4c76a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('auth_usuarios', sa.Column('firma_imagen_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('auth_usuarios', 'firma_imagen_url')
