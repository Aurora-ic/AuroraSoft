"""check_constraints_estados_libres

Cierra uno de los gaps documentados en docs/gaps-pendientes.md: varias
columnas de "estado" eran String libre con un set fijo de valores reales en
la práctica (confirmados leyendo el código real, nunca inventados), sin
ninguna garantía a nivel de base de datos. Confirmado antes de escribir esto
que ninguna de las tablas tenía datos fuera de ese set (edu_inscripciones,
edu_sesiones_seguimiento y citas_programadas estaban vacías; auth_usuarios
solo tenía superadmin/admin/psicologo).

`alembic revision --autogenerate` no detectó estos CHECK (limitación
conocida de Alembic: no compara constraints CHECK por defecto) — escrito a
mano.

Revision ID: ea0e1784dade
Revises: 5632465ccdd7
Create Date: 2026-10-07 20:28:18.035925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea0e1784dade'
down_revision: Union[str, Sequence[str], None] = '5632465ccdd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_inscripciones_estado_valido",
        "edu_inscripciones",
        "estado IN ('Pendiente', 'En Progreso', 'Finalizado')",
    )
    op.create_check_constraint(
        "ck_inscripciones_estado_interpretacion_valido",
        "edu_inscripciones",
        "estado_interpretacion IN ('completa', 'incompleta')",
    )
    op.create_check_constraint(
        "ck_sesiones_seguimiento_estado_valido",
        "edu_sesiones_seguimiento",
        "estado IN ('Pendiente', 'En proceso', 'Atendido')",
    )
    op.create_check_constraint(
        "ck_citas_programadas_estado_valido",
        "citas_programadas",
        "estado IN ('Programada', 'Realizada', 'Cancelada')",
    )
    op.create_check_constraint(
        "ck_usuarios_rol_valido",
        "auth_usuarios",
        "rol IN ('superadmin', 'admin', 'psicologo', 'colegio')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_usuarios_rol_valido", "auth_usuarios", type_="check")
    op.drop_constraint("ck_citas_programadas_estado_valido", "citas_programadas", type_="check")
    op.drop_constraint("ck_sesiones_seguimiento_estado_valido", "edu_sesiones_seguimiento", type_="check")
    op.drop_constraint("ck_inscripciones_estado_interpretacion_valido", "edu_inscripciones", type_="check")
    op.drop_constraint("ck_inscripciones_estado_valido", "edu_inscripciones", type_="check")
