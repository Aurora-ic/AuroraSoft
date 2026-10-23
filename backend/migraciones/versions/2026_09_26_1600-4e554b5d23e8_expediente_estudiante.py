"""expediente_estudiante

Revision ID: 4e554b5d23e8
Revises: a3f8c1e07d92
Create Date: 2026-09-26 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e554b5d23e8'
down_revision: Union[str, Sequence[str], None] = 'a3f8c1e07d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ContactoFamiliar — independiente de todo lo demás en esta migración.
    op.create_table(
        'contactos_familiares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(), nullable=False),
        sa.Column('telefono', sa.String(), nullable=True),
        sa.Column('relacion', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('registrado_por_usuario_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['registrado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contactos_familiares_id'), 'contactos_familiares', ['id'], unique=False)
    op.create_index(op.f('ix_contactos_familiares_persona_id'), 'contactos_familiares', ['persona_id'], unique=False)
    op.create_index(op.f('ix_contactos_familiares_institucion_id'), 'contactos_familiares', ['institucion_id'], unique=False)

    # AutorizacionAccesoColegio — antes de expediente_entradas/registro_lecturas
    # porque registro_lecturas_expediente la referencia.
    op.create_table(
        'autorizaciones_acceso_colegio',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('otorgado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('rol_otorgante', sa.String(), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('fecha_otorgado', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('vigente', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('fecha_revocado', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('rol_revocador', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['otorgado_por_usuario_id'], ['auth_usuarios.id']),
        sa.ForeignKeyConstraint(['revocado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_autorizaciones_acceso_colegio_id'), 'autorizaciones_acceso_colegio', ['id'], unique=False)
    op.create_index(op.f('ix_autorizaciones_acceso_colegio_persona_id'), 'autorizaciones_acceso_colegio', ['persona_id'], unique=False)
    op.create_index(op.f('ix_autorizaciones_acceso_colegio_institucion_id'), 'autorizaciones_acceso_colegio', ['institucion_id'], unique=False)
    op.create_index(
        'uq_autorizacion_colegio_vigente_por_persona', 'autorizaciones_acceso_colegio',
        ['persona_id'], unique=True, postgresql_where=sa.text('vigente = true'),
    )

    # EntradaExpediente — identidad únicamente; el contenido narrativo vive
    # en expediente_entradas_version (más abajo). Depende de
    # contactos_familiares (arriba) y de edu_sesiones_seguimiento/
    # edu_informes (ya existentes).
    op.create_table(
        'expediente_entradas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('tipo_entrada', sa.String(), nullable=False),
        sa.Column('autor_usuario_id', sa.Integer(), nullable=False),
        sa.Column('fecha_entrada', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('version_actual', sa.Integer(), nullable=True),
        sa.Column('sesion_seguimiento_id', sa.Integer(), nullable=True),
        sa.Column('informe_id', sa.Integer(), nullable=True),
        sa.Column('contacto_familiar_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['autor_usuario_id'], ['auth_usuarios.id']),
        sa.ForeignKeyConstraint(['sesion_seguimiento_id'], ['edu_sesiones_seguimiento.id']),
        sa.ForeignKeyConstraint(['informe_id'], ['edu_informes.id']),
        sa.ForeignKeyConstraint(['contacto_familiar_id'], ['contactos_familiares.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "tipo_entrada IN "
            "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', 'aplicacion_prueba')",
            name='ck_expediente_tipo_entrada_valido',
        ),
        sa.CheckConstraint(
            "(tipo_entrada IN ('observacion_conducta', 'derivacion') "
            " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL AND contacto_familiar_id IS NULL)"
            " OR "
            "(tipo_entrada = 'contacto_apoderado' "
            " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL)"
            " OR "
            "(tipo_entrada = 'sesion' "
            " AND sesion_seguimiento_id IS NOT NULL AND informe_id IS NULL AND contacto_familiar_id IS NULL)"
            " OR "
            "(tipo_entrada = 'aplicacion_prueba' "
            " AND informe_id IS NOT NULL AND sesion_seguimiento_id IS NULL AND contacto_familiar_id IS NULL)",
            name='ck_expediente_campos_segun_tipo',
        ),
    )
    op.create_index(op.f('ix_expediente_entradas_id'), 'expediente_entradas', ['id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_persona_id'), 'expediente_entradas', ['persona_id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_institucion_id'), 'expediente_entradas', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_tipo_entrada'), 'expediente_entradas', ['tipo_entrada'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_autor_usuario_id'), 'expediente_entradas', ['autor_usuario_id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_sesion_seguimiento_id'), 'expediente_entradas', ['sesion_seguimiento_id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_informe_id'), 'expediente_entradas', ['informe_id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_contacto_familiar_id'), 'expediente_entradas', ['contacto_familiar_id'], unique=False)

    # EntradaExpedienteVersion — snapshot inmutable del contenido narrativo,
    # mismo patrón que InformeVersion. Depende de expediente_entradas.
    op.create_table(
        'expediente_entradas_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entrada_expediente_id', sa.Integer(), nullable=False),
        sa.Column('numero_version', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=True),
        sa.Column('contenido', sa.Text(), nullable=True),
        sa.Column('interpretacion', sa.Text(), nullable=True),
        sa.Column('diagnostico_presuntivo', sa.Text(), nullable=True),
        sa.Column('creado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('motivo_version', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['entrada_expediente_id'], ['expediente_entradas.id']),
        sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entrada_expediente_id', 'numero_version', name='uq_expediente_version_entrada_numero'),
    )
    op.create_index(op.f('ix_expediente_entradas_version_id'), 'expediente_entradas_version', ['id'], unique=False)
    op.create_index(op.f('ix_expediente_entradas_version_entrada_expediente_id'), 'expediente_entradas_version', ['entrada_expediente_id'], unique=False)

    # RegistroLecturasExpediente — depende de expediente_entradas y de
    # autorizaciones_acceso_colegio (ambas ya creadas arriba).
    op.create_table(
        'registro_lecturas_expediente',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entrada_expediente_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('leido_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('rol_lector', sa.String(), nullable=True),
        sa.Column('fecha_lectura', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ip_lectura', sa.String(), nullable=True),
        sa.Column('numero_version_leida', sa.Integer(), nullable=True),
        sa.Column('autorizacion_acceso_colegio_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['entrada_expediente_id'], ['expediente_entradas.id']),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['leido_por_usuario_id'], ['auth_usuarios.id']),
        sa.ForeignKeyConstraint(['autorizacion_acceso_colegio_id'], ['autorizaciones_acceso_colegio.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_registro_lecturas_expediente_id'), 'registro_lecturas_expediente', ['id'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_entrada_expediente_id'), 'registro_lecturas_expediente', ['entrada_expediente_id'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_persona_id'), 'registro_lecturas_expediente', ['persona_id'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_institucion_id'), 'registro_lecturas_expediente', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_leido_por_usuario_id'), 'registro_lecturas_expediente', ['leido_por_usuario_id'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_fecha_lectura'), 'registro_lecturas_expediente', ['fecha_lectura'], unique=False)
    op.create_index(op.f('ix_registro_lecturas_expediente_autorizacion_acceso_colegio_id'), 'registro_lecturas_expediente', ['autorizacion_acceso_colegio_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_registro_lecturas_expediente_autorizacion_acceso_colegio_id'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_fecha_lectura'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_leido_por_usuario_id'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_institucion_id'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_persona_id'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_entrada_expediente_id'), table_name='registro_lecturas_expediente')
    op.drop_index(op.f('ix_registro_lecturas_expediente_id'), table_name='registro_lecturas_expediente')
    op.drop_table('registro_lecturas_expediente')

    op.drop_index(op.f('ix_expediente_entradas_version_entrada_expediente_id'), table_name='expediente_entradas_version')
    op.drop_index(op.f('ix_expediente_entradas_version_id'), table_name='expediente_entradas_version')
    op.drop_table('expediente_entradas_version')

    op.drop_index(op.f('ix_expediente_entradas_contacto_familiar_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_informe_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_sesion_seguimiento_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_autor_usuario_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_tipo_entrada'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_institucion_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_persona_id'), table_name='expediente_entradas')
    op.drop_index(op.f('ix_expediente_entradas_id'), table_name='expediente_entradas')
    op.drop_table('expediente_entradas')

    op.drop_index('uq_autorizacion_colegio_vigente_por_persona', table_name='autorizaciones_acceso_colegio', postgresql_where=sa.text('vigente = true'))
    op.drop_index(op.f('ix_autorizaciones_acceso_colegio_institucion_id'), table_name='autorizaciones_acceso_colegio')
    op.drop_index(op.f('ix_autorizaciones_acceso_colegio_persona_id'), table_name='autorizaciones_acceso_colegio')
    op.drop_index(op.f('ix_autorizaciones_acceso_colegio_id'), table_name='autorizaciones_acceso_colegio')
    op.drop_table('autorizaciones_acceso_colegio')

    op.drop_index(op.f('ix_contactos_familiares_institucion_id'), table_name='contactos_familiares')
    op.drop_index(op.f('ix_contactos_familiares_persona_id'), table_name='contactos_familiares')
    op.drop_index(op.f('ix_contactos_familiares_id'), table_name='contactos_familiares')
    op.drop_table('contactos_familiares')
