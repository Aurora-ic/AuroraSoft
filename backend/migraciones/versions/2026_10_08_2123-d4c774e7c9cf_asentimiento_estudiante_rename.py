"""asentimiento_estudiante_rename

Cierra el renombrado pedido en docs/gaps-pendientes.md: el valor
`tipo_consentimiento="estudiante"` (y todo lo que lo nombraba) pasa a
llamarse "asentimiento" — la figura legal correcta para el propio menor,
distinta del consentimiento informado que da su apoderado. Quién lo otorga
sigue siendo el estudiante; lo que cambia es cómo se llama la figura.

Escrito a mano (no autogenerate): un rename de columna/valor no se detecta
como tal por `alembic revision --autogenerate` — saldría como DROP+ADD y
perdería los datos existentes.

Tres cambios, en orden (el backfill va ANTES de recrear el CHECK más
restrictivo, porque mientras exista el constraint viejo la fila todavía
puede valer 'estudiante'; intentar escribir 'asentimiento' primero fallaría
contra ese mismo constraint):
  1. `consentimientos_informados.tipo_consentimiento`: drop del CHECK viejo,
     backfill de filas 'estudiante' -> 'asentimiento', CHECK nuevo
     ('apoderado', 'asentimiento'). En este entorno no hay ninguna fila con
     'estudiante' todavía (confirmado antes de escribir esto), pero el
     backfill se deja por si otro entorno sí la tiene.
  2. `edu_inscripciones.consentimiento_estudiante_id` -> `consentimiento_asentimiento_id`,
     RENAME de columna (preserva los datos y el enlace FK) + RENAME del
     nombre del constraint FK para que coincida con el que ya declara
     `Inscripcion` en models.py.
  3. `instituciones.exigir_consentimiento_estudiante` -> `exigir_asentimiento_estudiante`,
     mismo RENAME simple (es un booleano, no necesita backfill).

Revision ID: d4c774e7c9cf
Revises: e0c0768c55fd
Create Date: 2026-10-08 21:23:41.583611

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4c774e7c9cf'
down_revision: Union[str, Sequence[str], None] = 'e0c0768c55fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. tipo_consentimiento: 'estudiante' -> 'asentimiento'
    op.drop_constraint('ck_consentimientos_tipo_valido', 'consentimientos_informados', type_='check')
    op.execute(
        "UPDATE consentimientos_informados SET tipo_consentimiento = 'asentimiento' "
        "WHERE tipo_consentimiento = 'estudiante'"
    )
    op.create_check_constraint(
        'ck_consentimientos_tipo_valido',
        'consentimientos_informados',
        "tipo_consentimiento IN ('apoderado', 'asentimiento')",
    )

    # 2. edu_inscripciones.consentimiento_estudiante_id -> consentimiento_asentimiento_id
    op.alter_column(
        'edu_inscripciones', 'consentimiento_estudiante_id',
        new_column_name='consentimiento_asentimiento_id',
    )
    op.execute(
        "ALTER TABLE edu_inscripciones RENAME CONSTRAINT "
        "edu_inscripciones_consentimiento_estudiante_id_fkey TO "
        "edu_inscripciones_consentimiento_asentimiento_id_fkey"
    )

    # 3. instituciones.exigir_consentimiento_estudiante -> exigir_asentimiento_estudiante
    op.alter_column(
        'instituciones', 'exigir_consentimiento_estudiante',
        new_column_name='exigir_asentimiento_estudiante',
    )


def downgrade() -> None:
    op.alter_column(
        'instituciones', 'exigir_asentimiento_estudiante',
        new_column_name='exigir_consentimiento_estudiante',
    )

    op.execute(
        "ALTER TABLE edu_inscripciones RENAME CONSTRAINT "
        "edu_inscripciones_consentimiento_asentimiento_id_fkey TO "
        "edu_inscripciones_consentimiento_estudiante_id_fkey"
    )
    op.alter_column(
        'edu_inscripciones', 'consentimiento_asentimiento_id',
        new_column_name='consentimiento_estudiante_id',
    )

    op.drop_constraint('ck_consentimientos_tipo_valido', 'consentimientos_informados', type_='check')
    op.execute(
        "UPDATE consentimientos_informados SET tipo_consentimiento = 'estudiante' "
        "WHERE tipo_consentimiento = 'asentimiento'"
    )
    op.create_check_constraint(
        'ck_consentimientos_tipo_valido',
        'consentimientos_informados',
        "tipo_consentimiento IN ('apoderado', 'estudiante')",
    )
