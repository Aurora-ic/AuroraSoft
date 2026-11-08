"""logo_pie_pagina_institucion

Agrega `instituciones.logo_pie_pagina_url` — la franja/imagen de PIE DE
PÁGINA que el motor de documentos institucionales (modulos/documentos/
pdf_generador.py) ahora dibuja en el marco de cada página, independiente del
`logo_url` ya existente (que sigue siendo el logo de encabezado, compartido
con el informe psicométrico). Columna nullable, sin backfill: toda
institución existente queda sin pie de página propio hasta que alguien lo
configure — cero cambio de comportamiento (el renderizador ya trata un logo
ausente como "no dibujar nada", mismo criterio que logo_url).

Revision ID: a3f7c9b21e04
Revises: d4c774e7c9cf
Create Date: 2026-10-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9b21e04'
down_revision: Union[str, Sequence[str], None] = 'd4c774e7c9cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('instituciones', sa.Column('logo_pie_pagina_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('instituciones', 'logo_pie_pagina_url')
