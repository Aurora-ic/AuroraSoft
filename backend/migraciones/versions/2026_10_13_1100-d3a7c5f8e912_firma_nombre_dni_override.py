"""firma_nombre_dni_override

Columnas nuevas en `edu_inscripciones`: `firma_nombre_override` y
`firma_dni_override` — completan el mismo patrón "override" que ya tenía
`firma_cargo_override` (y motivo_consulta/observacion_conductual/
tecnicas_override/conclusion_override/recomendaciones_override).

Antes de esta migración, el bloque de FIRMA del informe PDF imprimía:
  - el NOMBRE siempre derivado automáticamente de `Inscripcion.
    revisado_por_usuario_id` (o del creador de la campaña si nadie había
    revisado) — sin ninguna forma de corregirlo para un caso puntual (ej.
    un supervisor firma en lugar de quien hizo la revisión técnica).
  - el DNI del profesional como un literal fijo "DNI: ____________________"
    siempre en blanco, para llenar a mano después de imprimir.

Nullable, sin default: toda inscripción existente sigue imprimiendo
exactamente lo mismo de siempre (nombre derivado, DNI en blanco) hasta que
un profesional complete estos campos vía
`PATCH /educativo/inscripciones/{id}/revision-informe`.

Revision ID: d3a7c5f8e912
Revises: f4d8a1c6b2e7
Create Date: 2026-10-13 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd3a7c5f8e912'
down_revision: Union[str, Sequence[str], None] = 'f4d8a1c6b2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_inscripciones', sa.Column('firma_nombre_override', sa.Text(), nullable=True))
    op.add_column('edu_inscripciones', sa.Column('firma_dni_override', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_inscripciones', 'firma_dni_override')
    op.drop_column('edu_inscripciones', 'firma_nombre_override')
