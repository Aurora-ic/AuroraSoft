"""indices_dashboard_y_evaluacion_institucion

Revision ID: 191ab27136ea
Revises: b4d8f1c6a0e2
Create Date: 2026-10-16 21:32:34.866140

Hallazgo de auditoría (sesión 2026-10-16, ver docs/gaps-pendientes.md):
`ResultadoDimension.inscripcion_id`/`.dimension_id` y
`DiagnosticoAlumno.inscripcion_id`/`.dimension_id` son exactamente lo que
`crud._armar_alumnos_y_distribucion` filtra/joinea en cada dashboard de
campaña/académico, y crecen por cada (inscripción × dimensión) de TODOS
los tenants, para siempre. `Evaluacion.institucion_id` es lo que filtra
`listar_campanas_de_institucion`. Ninguna tenía índice — solo la PK.

`alembic revision --autogenerate` también detectó un drift NO relacionado
(un índice con el nombre viejo `ix_edu_inscripciones_consentimiento_
estudiante_id`, que quedó huérfano cuando esa columna se renombró a
`consentimiento_asentimiento_id` en una migración anterior — el nombre
del índice nunca se actualizó). Se dejó fuera a propósito de esta
migración, que se mantiene acotada al hallazgo de escalabilidad; ese
nombre de índice obsoleto es cosmético (mismo índice, misma columna real)
y no afecta correctness ni performance.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '191ab27136ea'
down_revision: Union[str, Sequence[str], None] = 'b4d8f1c6a0e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(op.f('ix_edu_diagnosticos_alumno_dimension_id'), 'edu_diagnosticos_alumno', ['dimension_id'], unique=False)
    op.create_index(op.f('ix_edu_diagnosticos_alumno_inscripcion_id'), 'edu_diagnosticos_alumno', ['inscripcion_id'], unique=False)
    op.create_index(op.f('ix_edu_evaluaciones_institucion_id'), 'edu_evaluaciones', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_edu_resultados_dimensiones_dimension_id'), 'edu_resultados_dimensiones', ['dimension_id'], unique=False)
    op.create_index(op.f('ix_edu_resultados_dimensiones_inscripcion_id'), 'edu_resultados_dimensiones', ['inscripcion_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_edu_resultados_dimensiones_inscripcion_id'), table_name='edu_resultados_dimensiones')
    op.drop_index(op.f('ix_edu_resultados_dimensiones_dimension_id'), table_name='edu_resultados_dimensiones')
    op.drop_index(op.f('ix_edu_evaluaciones_institucion_id'), table_name='edu_evaluaciones')
    op.drop_index(op.f('ix_edu_diagnosticos_alumno_inscripcion_id'), table_name='edu_diagnosticos_alumno')
    op.drop_index(op.f('ix_edu_diagnosticos_alumno_dimension_id'), table_name='edu_diagnosticos_alumno')
