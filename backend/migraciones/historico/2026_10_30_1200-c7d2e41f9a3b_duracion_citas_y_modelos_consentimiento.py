"""duracion de citas y modelos de consentimiento/asentimiento por colegio y nivel

Revision ID: c7d2e41f9a3b
Revises: b85b001b2e64
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2e41f9a3b'
down_revision: Union[str, Sequence[str], None] = 'b85b001b2e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- 1) Duración de las citas ---------------------------------------
    # server_default 45 rellena TODAS las filas existentes; las actividades
    # grupales (persona_id IS NULL) se corrigen a 60 en el mismo paso, mismo
    # criterio que crud.crear_cita usa para una fila nueva sin duración.
    op.add_column(
        'citas_programadas',
        sa.Column('duracion_minutos', sa.Integer(), server_default='45', nullable=False),
    )
    op.execute("UPDATE citas_programadas SET duracion_minutos = 60 WHERE persona_id IS NULL")
    op.create_check_constraint(
        'ck_citas_programadas_duracion_valida',
        'citas_programadas',
        "duracion_minutos BETWEEN 5 AND 720",
    )

    # --- 2) Modelos de texto: tipo + nivel educativo ----------------------
    # Toda fila existente es un texto de ASENTIMIENTO (lo único que la tabla
    # guardaba hasta hoy) y general (sin nivel) — el server_default cubre
    # ambas cosas sin un UPDATE aparte.
    op.add_column(
        'edu_asentimiento_textos',
        sa.Column('tipo_texto', sa.String(), server_default='asentimiento', nullable=False),
    )
    op.add_column(
        'edu_asentimiento_textos',
        sa.Column('nivel_educativo_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'edu_asentimiento_textos_nivel_educativo_id_fkey',
        'edu_asentimiento_textos', 'niveles_educativos',
        ['nivel_educativo_id'], ['id'],
    )
    op.create_index(
        op.f('ix_edu_asentimiento_textos_nivel_educativo_id'),
        'edu_asentimiento_textos', ['nivel_educativo_id'], unique=False,
    )
    op.create_check_constraint(
        'ck_edu_asentimiento_textos_tipo_valido',
        'edu_asentimiento_textos',
        "tipo_texto IN ('apoderado', 'asentimiento')",
    )
    op.create_check_constraint(
        'ck_edu_asentimiento_textos_nivel_requiere_institucion',
        'edu_asentimiento_textos',
        "nivel_educativo_id IS NULL OR institucion_id IS NOT NULL",
    )

    # Los dos índices únicos anteriores numeraban versiones por institución
    # (o global) sin distinguir tipo ni nivel — con dos tipos y N niveles
    # conviviendo, chocarían. Se reemplazan por tres, uno por combinación de
    # NULLs (ver AsentimientoInformadoTexto.__table_args__).
    op.drop_index('uq_edu_asentimiento_textos_institucion_version', table_name='edu_asentimiento_textos')
    op.drop_index('uq_edu_asentimiento_textos_global_version', table_name='edu_asentimiento_textos')
    op.create_index(
        'uq_edu_textos_consent_inst_nivel_version',
        'edu_asentimiento_textos',
        ['institucion_id', 'tipo_texto', 'nivel_educativo_id', 'version'],
        unique=True,
        postgresql_where=sa.text("institucion_id IS NOT NULL AND nivel_educativo_id IS NOT NULL"),
    )
    op.create_index(
        'uq_edu_textos_consent_inst_general_version',
        'edu_asentimiento_textos',
        ['institucion_id', 'tipo_texto', 'version'],
        unique=True,
        postgresql_where=sa.text("institucion_id IS NOT NULL AND nivel_educativo_id IS NULL"),
    )
    op.create_index(
        'uq_edu_textos_consent_global_version',
        'edu_asentimiento_textos',
        ['tipo_texto', 'version'],
        unique=True,
        postgresql_where=sa.text("institucion_id IS NULL"),
    )

    # --- 3) Qué versión del modelo respaldó cada consentimiento registrado --
    op.add_column(
        'consentimientos_informados',
        sa.Column('texto_version_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'consentimientos_informados_texto_version_id_fkey',
        'consentimientos_informados', 'edu_asentimiento_textos',
        ['texto_version_id'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('consentimientos_informados_texto_version_id_fkey', 'consentimientos_informados', type_='foreignkey')
    op.drop_column('consentimientos_informados', 'texto_version_id')

    op.drop_index('uq_edu_textos_consent_global_version', table_name='edu_asentimiento_textos')
    op.drop_index('uq_edu_textos_consent_inst_general_version', table_name='edu_asentimiento_textos')
    op.drop_index('uq_edu_textos_consent_inst_nivel_version', table_name='edu_asentimiento_textos')
    # ⚠️ Volver atrás solo es seguro si la tabla todavía no tiene textos de
    # consentimiento ni por nivel: con ellos, los índices viejos (versión
    # única por institución, sin tipo/nivel) chocarían. Se borran esas filas
    # explícitamente — un downgrade es una acción de desarrollo, nunca de
    # producción con datos reales.
    op.execute(
        "DELETE FROM edu_asentimiento_textos "
        "WHERE tipo_texto <> 'asentimiento' OR nivel_educativo_id IS NOT NULL"
    )
    op.create_index(
        'uq_edu_asentimiento_textos_global_version',
        'edu_asentimiento_textos', ['version'],
        unique=True, postgresql_where=sa.text("institucion_id IS NULL"),
    )
    op.create_index(
        'uq_edu_asentimiento_textos_institucion_version',
        'edu_asentimiento_textos', ['institucion_id', 'version'],
        unique=True, postgresql_where=sa.text("institucion_id IS NOT NULL"),
    )
    op.drop_constraint('ck_edu_asentimiento_textos_nivel_requiere_institucion', 'edu_asentimiento_textos', type_='check')
    op.drop_constraint('ck_edu_asentimiento_textos_tipo_valido', 'edu_asentimiento_textos', type_='check')
    op.drop_index(op.f('ix_edu_asentimiento_textos_nivel_educativo_id'), table_name='edu_asentimiento_textos')
    op.drop_constraint('edu_asentimiento_textos_nivel_educativo_id_fkey', 'edu_asentimiento_textos', type_='foreignkey')
    op.drop_column('edu_asentimiento_textos', 'nivel_educativo_id')
    op.drop_column('edu_asentimiento_textos', 'tipo_texto')

    op.drop_constraint('ck_citas_programadas_duracion_valida', 'citas_programadas', type_='check')
    op.drop_column('citas_programadas', 'duracion_minutos')
