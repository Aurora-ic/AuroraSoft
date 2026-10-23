"""firma_cargo_override

Columna nueva en `edu_inscripciones` para que el profesional pueda escribir
su propio cargo/especialidad (ej. "Psicóloga Clínica — COP 12345") en la
FIRMA del informe PDF, en vez de depender de la etiqueta genérica por rol
(_CARGO_POR_ROL en crud.py: "Psicólogo(a)", "Administrador(a)"...). Mismo
patrón "override" que conclusion_override/recomendaciones_override.
Nullable, sin default: toda inscripción existente sigue mostrando la
etiqueta genérica de siempre, cero cambio de comportamiento.

Revision ID: a6d4f82c1e7b
Revises: f3c8a19d6e4b
Create Date: 2026-10-12 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a6d4f82c1e7b'
down_revision: Union[str, Sequence[str], None] = 'f3c8a19d6e4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_inscripciones', sa.Column('firma_cargo_override', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_inscripciones', 'firma_cargo_override')
