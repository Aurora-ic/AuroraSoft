"""tecnicas_override

Columna nueva en `edu_inscripciones`: mismo patrón "override" que
motivo_consulta/observacion_conductual/conclusion_override/recomendaciones_
override/firma_cargo_override — el profesional puede reemplazar, SOLO para
esta aplicación puntual, la lista de técnicas adicionales que por defecto
viene de `Prueba.tecnicas_adicionales` (sección 3 del PDF). El instrumento
mismo (`Prueba.nombre_publico`) nunca se reemplaza por este campo, se sigue
imprimiendo siempre.

Antes de esta migración, "TÉCNICAS E INSTRUMENTO APLICADO" era la única de
las 4 secciones editables (filiación/motivo/técnicas/observación) sin
ningún override por aplicación individual — solo se podía cambiar editando
la plantilla de la Prueba entera (sin UI de administración todavía), lo que
afectaba a TODAS las aplicaciones de esa prueba, no a una sola.

Nullable, sin default: toda inscripción existente sigue mostrando
exactamente las mismas técnicas de siempre (las de `Prueba.
tecnicas_adicionales`), cero cambio de comportamiento.

Revision ID: c92a4f7d5e13
Revises: b71f3e9c2a4d
Create Date: 2026-10-12 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c92a4f7d5e13'
down_revision: Union[str, Sequence[str], None] = 'b71f3e9c2a4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_inscripciones', sa.Column('tecnicas_override', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_inscripciones', 'tecnicas_override')
