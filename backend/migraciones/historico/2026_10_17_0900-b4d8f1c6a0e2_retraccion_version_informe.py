"""retraccion_version_informe

Riesgo operacional documentado en docs/gaps-pendientes.md: un `reproceso`
que corrige un baremo puede retener de nuevo un informe que ya estaba
`informe_liberado=True`/`resultado_visible_alumno=True` — es decir, un
informe que el alumno ya pudo haber descargado. El sistema no tiene (ni
puede tener, una vez que un PDF salió a un dispositivo ajeno) forma de
invalidar ese archivo en circulación; lo que SÍ puede hacer es dejar
constancia explícita, en la nueva InformeVersion que el reproceso genera,
de que esa reemisión retracta una versión que había estado liberada y
visible — mismo criterio de "nunca inferir" que ya usan `origen`/`es_alerta`
en este mismo motor.

Columna aditiva, server_default=false — ninguna InformeVersion existente
retracta nada retroactivamente (no hay forma de saberlo sin haber corrido
este cálculo en el momento del reproceso original).

Revision ID: b4d8f1c6a0e2
Revises: c73e9f1a5b06
Create Date: 2026-10-17 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b4d8f1c6a0e2'
down_revision: Union[str, Sequence[str], None] = 'c73e9f1a5b06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'edu_informe_versiones',
        sa.Column(
            'retracta_version_previa_liberada', sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
    )
    op.alter_column('edu_informe_versiones', 'retracta_version_previa_liberada', server_default=None)


def downgrade() -> None:
    op.drop_column('edu_informe_versiones', 'retracta_version_previa_liberada')
