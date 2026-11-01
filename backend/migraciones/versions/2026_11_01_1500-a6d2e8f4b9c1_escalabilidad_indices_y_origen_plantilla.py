"""escalabilidad: índices de casos pendientes y documentos, origen de plantilla, nombre de índice

Revision ID: a6d2e8f4b9c1
Revises: f3c7a9d1e2b4
Create Date: 2026-11-01 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6d2e8f4b9c1'
down_revision: Union[str, Sequence[str], None] = 'f3c7a9d1e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Casos pendientes de seguimiento (un solo SELECT con NOT EXISTS) ---
    op.create_index(
        'ix_edu_diagnosticos_alumno_alerta', 'edu_diagnosticos_alumno', ['inscripcion_id'],
        unique=False, postgresql_where=sa.text('es_alerta = true'),
    )
    op.create_index(
        'ix_edu_sesiones_seguimiento_persona_fecha', 'edu_sesiones_seguimiento', ['persona_id', 'fecha'], unique=False,
    )

    # --- Listado de documentos: por institución, sin descartados, recientes primero ---
    op.create_index(
        'ix_documentos_institucionales_listado', 'documentos_institucionales', ['institucion_id', 'creado_en'],
        unique=False, postgresql_where=sa.text('descartado_en IS NULL'),
    )

    # --- De qué plantilla se clonó cada una ---
    op.add_column('documentos_plantillas', sa.Column('plantilla_origen_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'documentos_plantillas_plantilla_origen_id_fkey',
        'documentos_plantillas', 'documentos_plantillas', ['plantilla_origen_id'], ['id'],
    )
    op.create_index(op.f('ix_documentos_plantillas_plantilla_origen_id'), 'documentos_plantillas', ['plantilla_origen_id'], unique=False)
    # Backfill CONSERVADOR: solo los clones que conservan el nombre exacto que
    # les pone el clonado ("<predeterminada> (copia)", mismo tipo) y cuya
    # coincidencia es única. Un clon renombrado queda NULL: no se adivina.
    op.execute("""
        UPDATE documentos_plantillas p
        SET plantilla_origen_id = (
            SELECT o.id FROM documentos_plantillas o
            WHERE o.institucion_id IS NULL AND o.tipo_documento_id = p.tipo_documento_id
              AND p.nombre = o.nombre || ' (copia)'
        )
        WHERE p.institucion_id IS NOT NULL AND p.plantilla_origen_id IS NULL
          AND (
            SELECT count(*) FROM documentos_plantillas o
            WHERE o.institucion_id IS NULL AND o.tipo_documento_id = p.tipo_documento_id
              AND p.nombre = o.nombre || ' (copia)'
          ) = 1
    """)

    # --- Drift previo: el modelo espera este nombre desde que la columna se
    # renombró de consentimiento_estudiante_id a consentimiento_asentimiento_id.
    op.execute(
        "ALTER INDEX IF EXISTS ix_edu_inscripciones_consentimiento_estudiante_id "
        "RENAME TO ix_edu_inscripciones_consentimiento_asentimiento_id"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER INDEX IF EXISTS ix_edu_inscripciones_consentimiento_asentimiento_id "
        "RENAME TO ix_edu_inscripciones_consentimiento_estudiante_id"
    )
    op.drop_index(op.f('ix_documentos_plantillas_plantilla_origen_id'), table_name='documentos_plantillas')
    op.drop_constraint('documentos_plantillas_plantilla_origen_id_fkey', 'documentos_plantillas', type_='foreignkey')
    op.drop_column('documentos_plantillas', 'plantilla_origen_id')
    op.drop_index('ix_documentos_institucionales_listado', table_name='documentos_institucionales')
    op.drop_index('ix_edu_sesiones_seguimiento_persona_fecha', table_name='edu_sesiones_seguimiento')
    op.drop_index('ix_edu_diagnosticos_alumno_alerta', table_name='edu_diagnosticos_alumno')
