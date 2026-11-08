"""promocion_anual_estudiantes

Revision ID: 716c022d49bb
Revises: 9424f38351ae
Create Date: 2026-09-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '716c022d49bb'
down_revision: Union[str, Sequence[str], None] = '9424f38351ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Institucion — única fuente de verdad de "en qué año estamos". Se
    # activa solo con una acción explícita futura (no con esta migración,
    # ni con la confirmación de un ProcesoPromocion) — queda NULL para toda
    # institución existente.
    op.add_column('instituciones', sa.Column('anio_escolar_activo', sa.Integer(), nullable=True))

    # Persona — condición académica tras un cierre de año. Columna nueva
    # sin filas previas que puedan violar el CHECK, así que se agrega desde
    # el día uno (mismo criterio que tipo_consentimiento/estado).
    op.add_column('personas', sa.Column('condicion_matricula', sa.String(), nullable=True))
    op.create_check_constraint(
        'ck_personas_condicion_matricula_valida',
        'personas',
        "condicion_matricula IN ('retirado', 'trasladado', 'egresado')",
    )

    # MatriculaAcademica — por qué se abrió / por qué se cerró cada tramo,
    # más el texto libre obligatorio para toda corrección (decisión de la
    # psicóloga: sin umbral de tiempo, siempre exige motivo).
    op.add_column('matriculas_academicas', sa.Column('motivo_apertura', sa.String(), nullable=True))
    op.add_column('matriculas_academicas', sa.Column('motivo_cierre', sa.String(), nullable=True))
    op.add_column('matriculas_academicas', sa.Column('motivo_detalle', sa.Text(), nullable=True))
    op.create_check_constraint(
        'ck_matriculas_motivo_apertura_valido',
        'matriculas_academicas',
        "motivo_apertura IN "
        "('promocion', 'repitencia', 'ingreso_nuevo', 'cambio_manual', 'correccion')",
    )
    op.create_check_constraint(
        'ck_matriculas_motivo_cierre_valido',
        'matriculas_academicas',
        "motivo_cierre IN ('promocion', 'retiro', 'traslado', 'egreso', 'correccion')",
    )
    op.create_check_constraint(
        'ck_matriculas_correccion_requiere_motivo',
        'matriculas_academicas',
        "(motivo_apertura IS DISTINCT FROM 'correccion' "
        "AND motivo_cierre IS DISTINCT FROM 'correccion') "
        "OR motivo_detalle IS NOT NULL",
    )

    # ProcesoPromocion — cabecera de una corrida de cierre de año.
    op.create_table(
        'procesos_promocion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('anio_origen', sa.Integer(), nullable=False),
        sa.Column('anio_destino', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(), server_default='borrador', nullable=False),
        sa.Column('creado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confirmado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('fecha_confirmacion', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id']),
        sa.ForeignKeyConstraint(['confirmado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "estado IN ('borrador', 'confirmado', 'cancelado')",
            name='ck_procesos_promocion_estado_valido',
        ),
    )
    op.create_index(op.f('ix_procesos_promocion_id'), 'procesos_promocion', ['id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_institucion_id'), 'procesos_promocion', ['institucion_id'], unique=False)
    op.create_index(
        'uq_proceso_promocion_confirmado', 'procesos_promocion',
        ['institucion_id', 'anio_origen', 'anio_destino'],
        unique=True, postgresql_where=sa.text("estado = 'confirmado'"),
    )

    # ProcesoPromocionDetalle — una fila por estudiante dentro del proceso.
    op.create_table(
        'procesos_promocion_detalle',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('proceso_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('matricula_origen_id', sa.Integer(), nullable=False),
        sa.Column('seccion_propuesta_id', sa.Integer(), nullable=True),
        sa.Column('tipo_excepcion', sa.String(), server_default='ninguna', nullable=False),
        sa.Column('seccion_definitiva_id', sa.Integer(), nullable=True),
        sa.Column('aplicado', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('matricula_resultante_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['proceso_id'], ['procesos_promocion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['matricula_origen_id'], ['matriculas_academicas.id']),
        sa.ForeignKeyConstraint(['seccion_propuesta_id'], ['secciones.id']),
        sa.ForeignKeyConstraint(['seccion_definitiva_id'], ['secciones.id']),
        sa.ForeignKeyConstraint(['matricula_resultante_id'], ['matriculas_academicas.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('proceso_id', 'persona_id', name='uq_promocion_detalle_persona_por_proceso'),
        sa.CheckConstraint(
            "tipo_excepcion IN "
            "('ninguna', 'repitente', 'retirado', 'trasladado', 'cambio_manual', 'egreso')",
            name='ck_promocion_detalle_tipo_excepcion_valido',
        ),
    )
    op.create_index(op.f('ix_procesos_promocion_detalle_id'), 'procesos_promocion_detalle', ['id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_proceso_id'), 'procesos_promocion_detalle', ['proceso_id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_persona_id'), 'procesos_promocion_detalle', ['persona_id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_matricula_origen_id'), 'procesos_promocion_detalle', ['matricula_origen_id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_seccion_propuesta_id'), 'procesos_promocion_detalle', ['seccion_propuesta_id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_seccion_definitiva_id'), 'procesos_promocion_detalle', ['seccion_definitiva_id'], unique=False)
    op.create_index(op.f('ix_procesos_promocion_detalle_matricula_resultante_id'), 'procesos_promocion_detalle', ['matricula_resultante_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_procesos_promocion_detalle_matricula_resultante_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_seccion_definitiva_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_seccion_propuesta_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_matricula_origen_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_persona_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_proceso_id'), table_name='procesos_promocion_detalle')
    op.drop_index(op.f('ix_procesos_promocion_detalle_id'), table_name='procesos_promocion_detalle')
    op.drop_table('procesos_promocion_detalle')

    op.drop_index('uq_proceso_promocion_confirmado', table_name='procesos_promocion', postgresql_where=sa.text("estado = 'confirmado'"))
    op.drop_index(op.f('ix_procesos_promocion_institucion_id'), table_name='procesos_promocion')
    op.drop_index(op.f('ix_procesos_promocion_id'), table_name='procesos_promocion')
    op.drop_table('procesos_promocion')

    op.drop_constraint('ck_matriculas_correccion_requiere_motivo', 'matriculas_academicas', type_='check')
    op.drop_constraint('ck_matriculas_motivo_cierre_valido', 'matriculas_academicas', type_='check')
    op.drop_constraint('ck_matriculas_motivo_apertura_valido', 'matriculas_academicas', type_='check')
    op.drop_column('matriculas_academicas', 'motivo_detalle')
    op.drop_column('matriculas_academicas', 'motivo_cierre')
    op.drop_column('matriculas_academicas', 'motivo_apertura')

    op.drop_constraint('ck_personas_condicion_matricula_valida', 'personas', type_='check')
    op.drop_column('personas', 'condicion_matricula')

    op.drop_column('instituciones', 'anio_escolar_activo')
