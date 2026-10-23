"""motor_documentos_institucionales

Revision ID: 9f13619766a9
Revises: 4e554b5d23e8
Create Date: 2026-09-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f13619766a9'
down_revision: Union[str, Sequence[str], None] = '4e554b5d23e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # PersonaDatosFamiliares — independiente de todo lo demás en esta
    # migración; 1:1 con personas.
    op.create_table(
        'personas_datos_familiares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('numero_hermanos', sa.Integer(), nullable=True),
        sa.Column('vive_con', sa.String(), nullable=True),
        sa.Column('lugar_nacimiento', sa.String(), nullable=True),
        sa.Column('lugar_procedencia', sa.String(), nullable=True),
        sa.Column('actualizado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_personas_datos_familiares_id'), 'personas_datos_familiares', ['id'], unique=False)
    # unique=True aquí (no un UniqueConstraint aparte): así es exactamente
    # como SQLAlchemy emite `Column(..., unique=True, index=True)` — un solo
    # índice único, no un índice más una constraint separada. Con los dos
    # objetos por separado, `alembic check` detecta drift contra el modelo.
    op.create_index(op.f('ix_personas_datos_familiares_persona_id'), 'personas_datos_familiares', ['persona_id'], unique=True)

    # Usuario.cargo — aditiva, nullable, sin efecto en login/JWT/roles.
    op.add_column('auth_usuarios', sa.Column('cargo', sa.String(), nullable=True))

    # ==========================================
    # Catálogo global — TipoDocumento y AnioOficial.
    # ==========================================
    op.create_table(
        'documentos_tipos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clave', sa.String(), nullable=False),
        sa.Column('nombre', sa.String(), nullable=False),
        sa.Column('alcances_permitidos', sa.String(), nullable=False),
        sa.Column('visibilidades_permitidas', sa.String(), nullable=False),
        sa.Column('requiere_consentimiento_individual', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('clave', name='uq_documentos_tipos_clave'),
    )
    op.create_index(op.f('ix_documentos_tipos_id'), 'documentos_tipos', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_tipos_clave'), 'documentos_tipos', ['clave'], unique=False)

    op.create_table(
        'documentos_anios_oficiales',
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('anio'),
    )

    # ==========================================
    # Plantilla por institución.
    # ==========================================
    op.create_table(
        'documentos_plantillas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('tipo_documento_id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(), nullable=False),
        sa.Column('activa', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('fuente', sa.String(), server_default='Arial', nullable=False),
        sa.Column('tamano_pt', sa.Integer(), server_default='11', nullable=False),
        sa.Column('interlineado', sa.Numeric(4, 2), server_default='1.15', nullable=False),
        sa.Column('justificado', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('formato_correlativo', sa.String(), nullable=True),
        sa.Column('correlativo_reinicia_anualmente', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('creado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id']),
        sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_documentos_plantillas_id'), 'documentos_plantillas', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_plantillas_institucion_id'), 'documentos_plantillas', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_plantillas_tipo_documento_id'), 'documentos_plantillas', ['tipo_documento_id'], unique=False)
    op.create_index(
        'uq_documentos_plantilla_activa_por_institucion_y_tipo', 'documentos_plantillas',
        ['institucion_id', 'tipo_documento_id'], unique=True, postgresql_where=sa.text('activa = true'),
    )

    op.create_table(
        'documentos_plantilla_secciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plantilla_documento_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('tipo_seccion', sa.String(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['plantilla_documento_id'], ['documentos_plantillas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "tipo_seccion IN "
            "('encabezado', 'datos_filiacion', 'datos_familiares', "
            "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma')",
            name='ck_documentos_plantilla_seccion_tipo_valido',
        ),
    )
    op.create_index(op.f('ix_documentos_plantilla_secciones_id'), 'documentos_plantilla_secciones', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_plantilla_secciones_plantilla_documento_id'), 'documentos_plantilla_secciones', ['plantilla_documento_id'], unique=False)
    op.create_index(op.f('ix_documentos_plantilla_secciones_tipo_seccion'), 'documentos_plantilla_secciones', ['tipo_seccion'], unique=False)

    op.create_table(
        'documentos_correlativos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('tipo_documento_id', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), server_default='0', nullable=False),
        sa.Column('ultimo_numero', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('institucion_id', 'tipo_documento_id', 'anio', name='uq_documentos_correlativo_institucion_tipo_anio'),
    )
    op.create_index(op.f('ix_documentos_correlativos_id'), 'documentos_correlativos', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_correlativos_institucion_id'), 'documentos_correlativos', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_correlativos_tipo_documento_id'), 'documentos_correlativos', ['tipo_documento_id'], unique=False)

    # ==========================================
    # DocumentoInstitucional y tablas dependientes.
    # ==========================================
    op.create_table(
        'documentos_institucionales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('tipo_documento_id', sa.Integer(), nullable=False),
        sa.Column('plantilla_documento_id', sa.Integer(), nullable=False),
        sa.Column('alcance', sa.String(), nullable=False),
        sa.Column('nivel_visibilidad', sa.String(), server_default='confidencial_clinico', nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('version_actual', sa.Integer(), nullable=True),
        sa.Column('creado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id']),
        sa.ForeignKeyConstraint(['plantilla_documento_id'], ['documentos_plantillas.id']),
        sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "alcance IN ('institucion', 'estructura_academica', 'personas_especificas', 'ninguno')",
            name='ck_documentos_institucionales_alcance_valido',
        ),
        sa.CheckConstraint(
            "nivel_visibilidad IN ('confidencial_clinico', 'compartible_colegio')",
            name='ck_documentos_institucionales_visibilidad_valida',
        ),
    )
    op.create_index(op.f('ix_documentos_institucionales_id'), 'documentos_institucionales', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_institucion_id'), 'documentos_institucionales', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_tipo_documento_id'), 'documentos_institucionales', ['tipo_documento_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_plantilla_documento_id'), 'documentos_institucionales', ['plantilla_documento_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_alcance'), 'documentos_institucionales', ['alcance'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_nivel_visibilidad'), 'documentos_institucionales', ['nivel_visibilidad'], unique=False)

    op.create_table(
        'documentos_institucionales_estructura',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('nivel_educativo_id', sa.Integer(), nullable=True),
        sa.Column('grado_id', sa.Integer(), nullable=True),
        sa.Column('seccion_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['nivel_educativo_id'], ['niveles_educativos.id']),
        sa.ForeignKeyConstraint(['grado_id'], ['grados.id']),
        sa.ForeignKeyConstraint(['seccion_id'], ['secciones.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "(nivel_educativo_id IS NOT NULL AND grado_id IS NULL AND seccion_id IS NULL)"
            " OR "
            "(nivel_educativo_id IS NULL AND grado_id IS NOT NULL AND seccion_id IS NULL)"
            " OR "
            "(nivel_educativo_id IS NULL AND grado_id IS NULL AND seccion_id IS NOT NULL)",
            name='ck_documentos_estructura_un_solo_nivel',
        ),
    )
    op.create_index(op.f('ix_documentos_institucionales_estructura_id'), 'documentos_institucionales_estructura', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estructura_documento_institucional_id'), 'documentos_institucionales_estructura', ['documento_institucional_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estructura_institucion_id'), 'documentos_institucionales_estructura', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estructura_nivel_educativo_id'), 'documentos_institucionales_estructura', ['nivel_educativo_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estructura_grado_id'), 'documentos_institucionales_estructura', ['grado_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estructura_seccion_id'), 'documentos_institucionales_estructura', ['seccion_id'], unique=False)

    op.create_table(
        'documentos_institucionales_estudiantes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('incluido_via', sa.String(), nullable=False),
        sa.Column('nombre_completo_historico', sa.String(), nullable=True),
        sa.Column('seccion_id_historico', sa.Integer(), nullable=True),
        sa.Column('grado_seccion_historico', sa.String(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['seccion_id_historico'], ['secciones.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('documento_institucional_id', 'persona_id', name='uq_documentos_institucionales_estudiante'),
        sa.CheckConstraint(
            "incluido_via IN ('seccion', 'manual')",
            name='ck_documentos_institucionales_estudiante_incluido_via_valido',
        ),
    )
    op.create_index(op.f('ix_documentos_institucionales_estudiantes_id'), 'documentos_institucionales_estudiantes', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estudiantes_documento_institucional_id'), 'documentos_institucionales_estudiantes', ['documento_institucional_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estudiantes_institucion_id'), 'documentos_institucionales_estudiantes', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estudiantes_persona_id'), 'documentos_institucionales_estudiantes', ['persona_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_estudiantes_seccion_id_historico'), 'documentos_institucionales_estudiantes', ['seccion_id_historico'], unique=False)

    op.create_table(
        'documentos_institucionales_resultados_prueba',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('plantilla_seccion_id', sa.Integer(), nullable=False),
        sa.Column('institucion_id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('inscripcion_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plantilla_seccion_id'], ['documentos_plantilla_secciones.id']),
        sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id']),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id']),
        sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('documento_institucional_id', 'plantilla_seccion_id', 'persona_id', name='uq_documentos_resultado_prueba_seccion_persona'),
    )
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_id'), 'documentos_institucionales_resultados_prueba', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_documento_institucional_id'), 'documentos_institucionales_resultados_prueba', ['documento_institucional_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_plantilla_seccion_id'), 'documentos_institucionales_resultados_prueba', ['plantilla_seccion_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_institucion_id'), 'documentos_institucionales_resultados_prueba', ['institucion_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_persona_id'), 'documentos_institucionales_resultados_prueba', ['persona_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_resultados_prueba_inscripcion_id'), 'documentos_institucionales_resultados_prueba', ['inscripcion_id'], unique=False)

    op.create_table(
        'documentos_institucionales_seccion_contenido',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('plantilla_seccion_id', sa.Integer(), nullable=False),
        sa.Column('contenido', sa.JSON(), nullable=True),
        sa.Column('editado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plantilla_seccion_id'], ['documentos_plantilla_secciones.id']),
        sa.ForeignKeyConstraint(['editado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('documento_institucional_id', 'plantilla_seccion_id', name='uq_documentos_seccion_contenido_unica'),
    )
    op.create_index(op.f('ix_documentos_institucionales_seccion_contenido_id'), 'documentos_institucionales_seccion_contenido', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_seccion_contenido_documento_institucional_id'), 'documentos_institucionales_seccion_contenido', ['documento_institucional_id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_seccion_contenido_plantilla_seccion_id'), 'documentos_institucionales_seccion_contenido', ['plantilla_seccion_id'], unique=False)

    op.create_table(
        'documentos_institucionales_versiones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_institucional_id', sa.Integer(), nullable=False),
        sa.Column('numero_version', sa.Integer(), nullable=False),
        sa.Column('contenido_snapshot', sa.JSON(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('nombre_archivo', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), server_default='application/pdf', nullable=False),
        sa.Column('tamano_bytes', sa.Integer(), nullable=False),
        sa.Column('checksum_sha256', sa.String(), nullable=False),
        sa.Column('generado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('generado_por_usuario_id', sa.Integer(), nullable=False),
        sa.Column('motivo_version', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generado_por_usuario_id'], ['auth_usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('documento_institucional_id', 'numero_version', name='uq_documentos_institucionales_version_numero'),
    )
    op.create_index(op.f('ix_documentos_institucionales_versiones_id'), 'documentos_institucionales_versiones', ['id'], unique=False)
    op.create_index(op.f('ix_documentos_institucionales_versiones_documento_institucional_id'), 'documentos_institucionales_versiones', ['documento_institucional_id'], unique=False)

    # ==========================================
    # Entrada-puente en el expediente clínico — extiende expediente_entradas
    # (ya existente) con el sexto tipo_entrada. Va al final porque depende
    # de documentos_institucionales, creada arriba.
    # ==========================================
    op.add_column('expediente_entradas', sa.Column('documento_institucional_id', sa.Integer(), nullable=True))
    op.create_index(
        op.f('ix_expediente_entradas_documento_institucional_id'), 'expediente_entradas',
        ['documento_institucional_id'], unique=False,
    )
    op.create_foreign_key(
        'fk_expediente_entradas_documento_institucional', 'expediente_entradas',
        'documentos_institucionales', ['documento_institucional_id'], ['id'],
    )

    op.drop_constraint('ck_expediente_campos_segun_tipo', 'expediente_entradas', type_='check')
    op.drop_constraint('ck_expediente_tipo_entrada_valido', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_tipo_entrada_valido', 'expediente_entradas',
        "tipo_entrada IN "
        "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', "
        "'aplicacion_prueba', 'documento_institucional')",
    )
    op.create_check_constraint(
        'ck_expediente_campos_segun_tipo', 'expediente_entradas',
        "(tipo_entrada IN ('observacion_conducta', 'derivacion') "
        " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL"
        " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
        " OR "
        "(tipo_entrada = 'contacto_apoderado' "
        " AND sesion_seguimiento_id IS NULL AND informe_id IS NULL AND documento_institucional_id IS NULL)"
        " OR "
        "(tipo_entrada = 'sesion' "
        " AND sesion_seguimiento_id IS NOT NULL AND informe_id IS NULL"
        " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
        " OR "
        "(tipo_entrada = 'aplicacion_prueba' "
        " AND informe_id IS NOT NULL AND sesion_seguimiento_id IS NULL"
        " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)"
        " OR "
        "(tipo_entrada = 'documento_institucional' "
        " AND documento_institucional_id IS NOT NULL AND sesion_seguimiento_id IS NULL"
        " AND informe_id IS NULL AND contacto_familiar_id IS NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_expediente_campos_segun_tipo', 'expediente_entradas', type_='check')
    op.drop_constraint('ck_expediente_tipo_entrada_valido', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_tipo_entrada_valido', 'expediente_entradas',
        "tipo_entrada IN "
        "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', 'aplicacion_prueba')",
    )
    op.create_check_constraint(
        'ck_expediente_campos_segun_tipo', 'expediente_entradas',
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
    )
    op.drop_constraint('fk_expediente_entradas_documento_institucional', 'expediente_entradas', type_='foreignkey')
    op.drop_index(op.f('ix_expediente_entradas_documento_institucional_id'), table_name='expediente_entradas')
    op.drop_column('expediente_entradas', 'documento_institucional_id')

    op.drop_index(op.f('ix_documentos_institucionales_versiones_documento_institucional_id'), table_name='documentos_institucionales_versiones')
    op.drop_index(op.f('ix_documentos_institucionales_versiones_id'), table_name='documentos_institucionales_versiones')
    op.drop_table('documentos_institucionales_versiones')

    op.drop_index(op.f('ix_documentos_institucionales_seccion_contenido_plantilla_seccion_id'), table_name='documentos_institucionales_seccion_contenido')
    op.drop_index(op.f('ix_documentos_institucionales_seccion_contenido_documento_institucional_id'), table_name='documentos_institucionales_seccion_contenido')
    op.drop_index(op.f('ix_documentos_institucionales_seccion_contenido_id'), table_name='documentos_institucionales_seccion_contenido')
    op.drop_table('documentos_institucionales_seccion_contenido')

    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_inscripcion_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_persona_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_institucion_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_plantilla_seccion_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_documento_institucional_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_index(op.f('ix_documentos_institucionales_resultados_prueba_id'), table_name='documentos_institucionales_resultados_prueba')
    op.drop_table('documentos_institucionales_resultados_prueba')

    op.drop_index(op.f('ix_documentos_institucionales_estudiantes_seccion_id_historico'), table_name='documentos_institucionales_estudiantes')
    op.drop_index(op.f('ix_documentos_institucionales_estudiantes_persona_id'), table_name='documentos_institucionales_estudiantes')
    op.drop_index(op.f('ix_documentos_institucionales_estudiantes_institucion_id'), table_name='documentos_institucionales_estudiantes')
    op.drop_index(op.f('ix_documentos_institucionales_estudiantes_documento_institucional_id'), table_name='documentos_institucionales_estudiantes')
    op.drop_index(op.f('ix_documentos_institucionales_estudiantes_id'), table_name='documentos_institucionales_estudiantes')
    op.drop_table('documentos_institucionales_estudiantes')

    op.drop_index(op.f('ix_documentos_institucionales_estructura_seccion_id'), table_name='documentos_institucionales_estructura')
    op.drop_index(op.f('ix_documentos_institucionales_estructura_grado_id'), table_name='documentos_institucionales_estructura')
    op.drop_index(op.f('ix_documentos_institucionales_estructura_nivel_educativo_id'), table_name='documentos_institucionales_estructura')
    op.drop_index(op.f('ix_documentos_institucionales_estructura_institucion_id'), table_name='documentos_institucionales_estructura')
    op.drop_index(op.f('ix_documentos_institucionales_estructura_documento_institucional_id'), table_name='documentos_institucionales_estructura')
    op.drop_index(op.f('ix_documentos_institucionales_estructura_id'), table_name='documentos_institucionales_estructura')
    op.drop_table('documentos_institucionales_estructura')

    op.drop_index(op.f('ix_documentos_institucionales_nivel_visibilidad'), table_name='documentos_institucionales')
    op.drop_index(op.f('ix_documentos_institucionales_alcance'), table_name='documentos_institucionales')
    op.drop_index(op.f('ix_documentos_institucionales_plantilla_documento_id'), table_name='documentos_institucionales')
    op.drop_index(op.f('ix_documentos_institucionales_tipo_documento_id'), table_name='documentos_institucionales')
    op.drop_index(op.f('ix_documentos_institucionales_institucion_id'), table_name='documentos_institucionales')
    op.drop_index(op.f('ix_documentos_institucionales_id'), table_name='documentos_institucionales')
    op.drop_table('documentos_institucionales')

    op.drop_index(op.f('ix_documentos_correlativos_tipo_documento_id'), table_name='documentos_correlativos')
    op.drop_index(op.f('ix_documentos_correlativos_institucion_id'), table_name='documentos_correlativos')
    op.drop_index(op.f('ix_documentos_correlativos_id'), table_name='documentos_correlativos')
    op.drop_table('documentos_correlativos')

    op.drop_index(op.f('ix_documentos_plantilla_secciones_tipo_seccion'), table_name='documentos_plantilla_secciones')
    op.drop_index(op.f('ix_documentos_plantilla_secciones_plantilla_documento_id'), table_name='documentos_plantilla_secciones')
    op.drop_index(op.f('ix_documentos_plantilla_secciones_id'), table_name='documentos_plantilla_secciones')
    op.drop_table('documentos_plantilla_secciones')

    op.drop_index('uq_documentos_plantilla_activa_por_institucion_y_tipo', table_name='documentos_plantillas', postgresql_where=sa.text('activa = true'))
    op.drop_index(op.f('ix_documentos_plantillas_tipo_documento_id'), table_name='documentos_plantillas')
    op.drop_index(op.f('ix_documentos_plantillas_institucion_id'), table_name='documentos_plantillas')
    op.drop_index(op.f('ix_documentos_plantillas_id'), table_name='documentos_plantillas')
    op.drop_table('documentos_plantillas')

    op.drop_table('documentos_anios_oficiales')

    op.drop_index(op.f('ix_documentos_tipos_clave'), table_name='documentos_tipos')
    op.drop_index(op.f('ix_documentos_tipos_id'), table_name='documentos_tipos')
    op.drop_table('documentos_tipos')

    op.drop_column('auth_usuarios', 'cargo')

    op.drop_index(op.f('ix_personas_datos_familiares_persona_id'), table_name='personas_datos_familiares')
    op.drop_index(op.f('ix_personas_datos_familiares_id'), table_name='personas_datos_familiares')
    op.drop_table('personas_datos_familiares')
