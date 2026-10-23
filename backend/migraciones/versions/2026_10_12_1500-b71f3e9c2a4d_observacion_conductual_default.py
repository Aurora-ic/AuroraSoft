"""observacion_conductual_default

Columna nueva en `edu_pruebas` (Prueba): mismo mecanismo de fallback que
`motivo_consulta_default`/`tecnicas_adicionales` (fuente "B" del informe),
pero para la sección 4 del PDF (OBSERVACIÓN CONDUCTUAL). Antes de esta
migración esa sección era "SOLO profesional" (Inscripcion.observacion_
conductual, sin ningún valor configurado por la prueba) — decisión de
producto explícita: AuroraSoft estandarizó un texto procedimental (no
clínico) idéntico para esta sección en TODAS las pruebas cargadas, igual
que ya existía para motivo_consulta_default. Inscripcion.observacion_
conductual (el profesional) sigue prevaleciendo siempre que esté presente.

Nullable, sin default a nivel de columna: toda prueba existente sigue sin
esta sección configurada hasta que un seed script la rellene explícitamente
(ver seeds/*.py) — cero cambio de comportamiento para pruebas que no se
vuelvan a sembrar.

Revision ID: b71f3e9c2a4d
Revises: e8a2c6f0b914
Create Date: 2026-10-12 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b71f3e9c2a4d'
down_revision: Union[str, Sequence[str], None] = 'e8a2c6f0b914'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('edu_pruebas', sa.Column('observacion_conductual_default', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('edu_pruebas', 'observacion_conductual_default')
