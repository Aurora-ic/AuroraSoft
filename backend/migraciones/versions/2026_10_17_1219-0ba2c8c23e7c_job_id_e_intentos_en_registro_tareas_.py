"""job_id_e_intentos_en_registro_tareas_asincronas

Revision ID: 0ba2c8c23e7c
Revises: 191ab27136ea
Create Date: 2026-10-17 12:19:16.457274

Fase 2 de core/models_tareas.py (ver su docstring) — Celery reemplaza
BackgroundTasks como mecanismo real; esta tabla de bitácora se mantiene
igual, solo se le agregan dos columnas para enlazarla con la tarea Celery
real que la escribió: `job_id` (el id que Celery asigna, self.request.id)
e `intentos` (incrementado por tareas/reconciliar_tareas_colgadas.py al
re-encolar una fila colgada — nunca por ejecutar_tarea_registrada en su
camino normal).

`alembic revision --autogenerate` también detectó, de nuevo, el drift NO
relacionado ya documentado en la migración anterior
(2026_10_16_2132-191ab27136ea): el índice
`ix_edu_inscripciones_consentimiento_estudiante_id` sigue con el nombre
viejo tras el rename de esa columna a `consentimiento_asentimiento_id`.
Se deja fuera de nuevo a propósito, por el mismo motivo — cosmético, no
afecta correctness ni performance, y mezclarlo aquí rompería el alcance de
esta migración.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ba2c8c23e7c'
down_revision: Union[str, Sequence[str], None] = '191ab27136ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('registro_tareas_asincronas', sa.Column('job_id', sa.String(), nullable=True))
    op.add_column('registro_tareas_asincronas', sa.Column('intentos', sa.Integer(), server_default='0', nullable=False))
    op.create_index(op.f('ix_registro_tareas_asincronas_job_id'), 'registro_tareas_asincronas', ['job_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_registro_tareas_asincronas_job_id'), table_name='registro_tareas_asincronas')
    op.drop_column('registro_tareas_asincronas', 'intentos')
    op.drop_column('registro_tareas_asincronas', 'job_id')
