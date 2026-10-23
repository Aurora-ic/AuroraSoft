"""asentimiento_estudiante_examen_rename

Completa el renombrado que dejó pendiente
2026_10_08_2123-d4c774e7c9cf_asentimiento_estudiante_rename.py: aquella
migración solo tocó el asentimiento/consentimiento PRE-REGISTRADO (el que
carga el staff vía POST /admin/personas/{id}/consentimiento, tabla
`consentimientos_informados`). Se quedaron sin renombrar las tres columnas
de `edu_inscripciones` que registran el clic del PROPIO ESTUDIANTE al abrir
su link de examen — ese es el asentimiento real (figura legal del propio
menor), no el consentimiento del apoderado, y hasta ahora se llamaba igual
que este por descuido de nomenclatura, no por decisión.

RENAME de columna (no DROP+ADD): preserva los datos y las dependencias
existentes (índices, defaults) exactamente igual que el patrón ya usado en
la migración de octubre para el caso pre-registrado.

  edu_inscripciones.acepto_consentimiento -> acepto_asentimiento
  edu_inscripciones.fecha_consentimiento  -> fecha_asentimiento
  edu_inscripciones.ip_consentimiento     -> ip_asentimiento

Revision ID: f3c8a19d6e4b
Revises: c91e5a3f7a2d
Create Date: 2026-10-11 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f3c8a19d6e4b'
down_revision: Union[str, Sequence[str], None] = 'c91e5a3f7a2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('edu_inscripciones', 'acepto_consentimiento', new_column_name='acepto_asentimiento')
    op.alter_column('edu_inscripciones', 'fecha_consentimiento', new_column_name='fecha_asentimiento')
    op.alter_column('edu_inscripciones', 'ip_consentimiento', new_column_name='ip_asentimiento')


def downgrade() -> None:
    op.alter_column('edu_inscripciones', 'acepto_asentimiento', new_column_name='acepto_consentimiento')
    op.alter_column('edu_inscripciones', 'fecha_asentimiento', new_column_name='fecha_consentimiento')
    op.alter_column('edu_inscripciones', 'ip_asentimiento', new_column_name='ip_consentimiento')
