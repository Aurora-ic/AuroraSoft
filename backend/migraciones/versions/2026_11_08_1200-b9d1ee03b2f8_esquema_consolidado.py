"""Esquema consolidado: reemplaza las 81 migraciones anteriores.

Revision ID: b9d1ee03b2f8
Revises:
Create Date: 2026-11-08 12:00:00

🆕 (sesión 2026-11-08, Tarea 1) Una sola migración base que deja la base
EXACTAMENTE como la dejaba la cadena de 81 migraciones hasta `4ffd2710409b`
(sesiones de usuario con renovación y revocación). Se generó reflejando una
base construida con esa cadena desde cero (no desde los modelos), así que
conserva también lo que los modelos no expresan: el orden físico de las
columnas, los nombres reales de restricciones e índices, los CHECK, los
índices parciales y las secuencias SERIAL. La equivalencia se comprueba con
tests/verificar_consolidacion_migraciones.py (pg_dump --schema-only idéntico
y comparar_esquemas sin diferencias).

Las 81 migraciones viejas se conservan en migraciones/historico/ (Alembic no
las carga: no están en versions/). Sirven solo para llevar a `4ffd2710409b`
una base que estuviera en una revisión intermedia.

Bases que ya existían (en `4ffd2710409b`, o sea, con el esquema completo):
NO se les aplica esta migración — se marca sin tocar el esquema:

    alembic stamp --purge b9d1ee03b2f8

(`--purge` borra la fila de alembic_version que apunta a `4ffd2710409b`,
que ya no existe en versions/, y escribe la nueva.) Ver
docs/arquitectura-backend.md ("Consolidación de migraciones").

Las tres migraciones de la cadena que tocaban datos solo eran UPDATE de
relleno sobre filas existentes (plan_activo, estado de consentimientos,
duracion_minutos); en una base nueva no tienen nada que actualizar.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b9d1ee03b2f8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('documentos_anios_oficiales',
    sa.Column('anio', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('texto', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('anio', name='documentos_anios_oficiales_pkey')
    )
    op.create_table('documentos_tipos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('clave', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('alcances_permitidos', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('visibilidades_permitidas', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('requiere_consentimiento_individual', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('id', name='documentos_tipos_pkey'),
    sa.UniqueConstraint('clave', name='uq_documentos_tipos_clave', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_documentos_tipos_clave', 'documentos_tipos', ['clave'], unique=False)
    op.create_index('ix_documentos_tipos_id', 'documentos_tipos', ['id'], unique=False)
    op.create_table('instituciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('tipo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('direccion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('telefono', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('email_contacto', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_registro', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('limite_pruebas_mensual_por_alumno', sa.INTEGER(), server_default=sa.text('5'), autoincrement=False, nullable=False),
    sa.Column('plan_activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('fecha_vencimiento_licencia', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('logo_url', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('anio_escolar_activo', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('exigir_asentimiento_estudiante', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('logo_pie_pagina_url', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fondo_documento_url', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='instituciones_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_instituciones_id', 'instituciones', ['id'], unique=False)
    op.create_index('ix_instituciones_nombre', 'instituciones', ['nombre'], unique=False)
    op.create_table('registro_tareas_asincronas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tipo_tarea', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('referencia_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('estado', sa.VARCHAR(), server_default=sa.text("'en_progreso'::character varying"), autoincrement=False, nullable=False),
    sa.Column('error_detalle', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('iniciado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('finalizado_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('job_id', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('intentos', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.CheckConstraint("estado IN ('en_progreso', 'exito', 'fallo')", name='ck_registro_tareas_asincronas_estado_valido'),
    sa.PrimaryKeyConstraint('id', name='registro_tareas_asincronas_pkey')
    )
    op.create_index('ix_registro_tareas_asincronas_id', 'registro_tareas_asincronas', ['id'], unique=False)
    op.create_index('ix_registro_tareas_asincronas_job_id', 'registro_tareas_asincronas', ['job_id'], unique=False)
    op.create_index('ix_registro_tareas_asincronas_referencia_id', 'registro_tareas_asincronas', ['referencia_id'], unique=False)
    op.create_index('ix_registro_tareas_asincronas_tipo_tarea', 'registro_tareas_asincronas', ['tipo_tarea'], unique=False)
    op.create_table('auth_usuarios',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('hashed_password', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('nombre_completo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('rol', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('activo', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('fecha_registro', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('token_version', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('cargo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('firma_imagen_url', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.CheckConstraint("rol IN ('superadmin', 'admin', 'psicologo', 'colegio')", name='ck_usuarios_rol_valido'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='auth_usuarios_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='auth_usuarios_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_auth_usuarios_email', 'auth_usuarios', ['email'], unique=True)
    op.create_index('ix_auth_usuarios_id', 'auth_usuarios', ['id'], unique=False)
    op.create_index('ix_auth_usuarios_institucion_id', 'auth_usuarios', ['institucion_id'], unique=False)
    op.create_table('documentos_correlativos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('tipo_documento_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('anio', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('ultimo_numero', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_correlativos_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id'], name='documentos_correlativos_tipo_documento_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_correlativos_pkey'),
    sa.UniqueConstraint('institucion_id', 'tipo_documento_id', 'anio', name='uq_documentos_correlativo_institucion_tipo_anio', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_documentos_correlativos_id', 'documentos_correlativos', ['id'], unique=False)
    op.create_index('ix_documentos_correlativos_institucion_id', 'documentos_correlativos', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_correlativos_tipo_documento_id', 'documentos_correlativos', ['tipo_documento_id'], unique=False)
    op.create_table('edu_campos_socio',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('cliente_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('pregunta', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_respuesta', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('opciones', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('obligatorio', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['cliente_id'], ['instituciones.id'], name='edu_campos_socio_cliente_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_campos_socio_pkey')
    )
    op.create_index('ix_edu_campos_socio_cliente_id', 'edu_campos_socio', ['cliente_id'], unique=False)
    op.create_index('ix_edu_campos_socio_id', 'edu_campos_socio', ['id'], unique=False)
    op.create_table('niveles_educativos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('orden', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='niveles_educativos_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='niveles_educativos_pkey'),
    sa.UniqueConstraint('institucion_id', 'nombre', name='uq_niveles_institucion_nombre', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_niveles_educativos_id', 'niveles_educativos', ['id'], unique=False)
    op.create_index('ix_niveles_educativos_institucion_id', 'niveles_educativos', ['institucion_id'], unique=False)
    op.create_table('personas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('tipo_perfil', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nombres', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('apellidos', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('documento_identidad', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_nacimiento', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('genero', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('grado_seccion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('puesto_postula', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('area_empresa', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('activo', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('fecha_registro', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('codigo_institucional', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('condicion_matricula', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.CheckConstraint("condicion_matricula IN ('retirado', 'trasladado', 'egresado')", name='ck_personas_condicion_matricula_valida'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='personas_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='personas_pkey'),
    sa.UniqueConstraint('institucion_id', 'codigo_institucional', name='uq_personas_institucion_codigo', postgresql_nulls_not_distinct=False),
    sa.UniqueConstraint('institucion_id', 'documento_identidad', name='uq_personas_institucion_documento', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_personas_codigo_institucional', 'personas', ['codigo_institucional'], unique=False)
    op.create_index('ix_personas_documento_identidad', 'personas', ['documento_identidad'], unique=False)
    op.create_index('ix_personas_id', 'personas', ['id'], unique=False)
    op.create_index('ix_personas_institucion_id', 'personas', ['institucion_id'], unique=False)
    op.create_table('auditoria_arco',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('accion', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('ejecutado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('rol_ejecutor', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('ip_solicitante', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('detalle', sa.TEXT(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['ejecutado_por_usuario_id'], ['auth_usuarios.id'], name='auditoria_arco_ejecutado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='auditoria_arco_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='auditoria_arco_pkey')
    )
    op.create_index('ix_auditoria_arco_accion', 'auditoria_arco', ['accion'], unique=False)
    op.create_index('ix_auditoria_arco_fecha', 'auditoria_arco', ['fecha'], unique=False)
    op.create_index('ix_auditoria_arco_id', 'auditoria_arco', ['id'], unique=False)
    op.create_index('ix_auditoria_arco_inscripcion_id', 'auditoria_arco', ['inscripcion_id'], unique=False)
    op.create_index('ix_auditoria_arco_institucion_id', 'auditoria_arco', ['institucion_id'], unique=False)
    op.create_index('ix_auditoria_arco_persona_id', 'auditoria_arco', ['persona_id'], unique=False)
    op.create_table('auth_sesiones',
    sa.Column('id', sa.VARCHAR(length=43), autoincrement=False, nullable=False),
    sa.Column('usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('hash_renovacion', sa.VARCHAR(length=64), autoincrement=False, nullable=False),
    sa.Column('token_version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('creada_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('expira_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('ultimo_uso', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('bloqueada_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('revocada_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('motivo_revocacion', sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    sa.Column('ip', sa.VARCHAR(length=64), autoincrement=False, nullable=True),
    sa.Column('agente', sa.VARCHAR(length=300), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['auth_usuarios.id'], name='auth_sesiones_usuario_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='auth_sesiones_pkey'),
    sa.UniqueConstraint('hash_renovacion', name='auth_sesiones_hash_renovacion_key', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_auth_sesiones_usuario_id', 'auth_sesiones', ['usuario_id'], unique=False)
    op.create_table('auth_tokens_recuperacion',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('token', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_creacion', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('fecha_expiracion', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('usado', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['auth_usuarios.id'], name='auth_tokens_recuperacion_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='auth_tokens_recuperacion_pkey')
    )
    op.create_index('ix_auth_tokens_recuperacion_id', 'auth_tokens_recuperacion', ['id'], unique=False)
    op.create_index('ix_auth_tokens_recuperacion_token', 'auth_tokens_recuperacion', ['token'], unique=True)
    op.create_table('autorizaciones_acceso_colegio',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('otorgado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('rol_otorgante', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('motivo', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('fecha_otorgado', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('vigente', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('fecha_revocado', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('revocado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('rol_revocador', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='autorizaciones_acceso_colegio_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['otorgado_por_usuario_id'], ['auth_usuarios.id'], name='autorizaciones_acceso_colegio_otorgado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='autorizaciones_acceso_colegio_persona_id_fkey'),
    sa.ForeignKeyConstraint(['revocado_por_usuario_id'], ['auth_usuarios.id'], name='autorizaciones_acceso_colegio_revocado_por_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='autorizaciones_acceso_colegio_pkey')
    )
    op.create_index('ix_autorizaciones_acceso_colegio_id', 'autorizaciones_acceso_colegio', ['id'], unique=False)
    op.create_index('ix_autorizaciones_acceso_colegio_institucion_id', 'autorizaciones_acceso_colegio', ['institucion_id'], unique=False)
    op.create_index('ix_autorizaciones_acceso_colegio_persona_id', 'autorizaciones_acceso_colegio', ['persona_id'], unique=False)
    op.create_index('uq_autorizacion_colegio_vigente_por_persona', 'autorizaciones_acceso_colegio', ['persona_id'], unique=True, postgresql_where='(vigente = true)')
    op.create_table('citas_programadas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('psicologo_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('motivo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('fecha_hora', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('estado', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_creacion', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('titulo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_actividad', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('lugar', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('duracion_minutos', sa.INTEGER(), server_default=sa.text('45'), autoincrement=False, nullable=False),
    sa.CheckConstraint("estado IN ('Programada', 'Realizada', 'Cancelada')", name='ck_citas_programadas_estado_valido'),
    sa.CheckConstraint('((duracion_minutos >= 5) AND (duracion_minutos <= 720))', name='ck_citas_programadas_duracion_valida'),
    sa.CheckConstraint('((persona_id IS NOT NULL) OR (titulo IS NOT NULL))', name='ck_citas_programadas_persona_o_titulo'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='citas_programadas_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='citas_programadas_persona_id_fkey'),
    sa.ForeignKeyConstraint(['psicologo_id'], ['auth_usuarios.id'], name='citas_programadas_psicologo_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='citas_programadas_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_citas_programadas_id', 'citas_programadas', ['id'], unique=False)
    op.create_index('ix_citas_programadas_persona_id', 'citas_programadas', ['persona_id'], unique=False)
    op.create_table('contactos_familiares',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('telefono', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('relacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('fecha_registro', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('registrado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='contactos_familiares_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='contactos_familiares_persona_id_fkey'),
    sa.ForeignKeyConstraint(['registrado_por_usuario_id'], ['auth_usuarios.id'], name='contactos_familiares_registrado_por_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='contactos_familiares_pkey')
    )
    op.create_index('ix_contactos_familiares_id', 'contactos_familiares', ['id'], unique=False)
    op.create_index('ix_contactos_familiares_institucion_id', 'contactos_familiares', ['institucion_id'], unique=False)
    op.create_index('ix_contactos_familiares_persona_id', 'contactos_familiares', ['persona_id'], unique=False)
    op.create_table('documentos_plantillas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tipo_documento_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('activa', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('fuente', sa.VARCHAR(), server_default=sa.text("'Arial'::character varying"), autoincrement=False, nullable=False),
    sa.Column('tamano_pt', sa.INTEGER(), server_default=sa.text('11'), autoincrement=False, nullable=False),
    sa.Column('interlineado', sa.NUMERIC(precision=4, scale=2), server_default=sa.text('1.15'), autoincrement=False, nullable=False),
    sa.Column('justificado', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('formato_correlativo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('correlativo_reinicia_anualmente', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('generar_automaticamente_al_finalizar_examen', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('titulo_negrita', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('titulo_cursiva', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('titulo_tamano_pt', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('subtitulo_tamano_pt', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('mostrar_fondo_institucion', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('eliminada_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('eliminada_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('plantilla_origen_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='documentos_plantillas_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['eliminada_por_usuario_id'], ['auth_usuarios.id'], name='documentos_plantillas_eliminada_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_plantillas_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['plantilla_origen_id'], ['documentos_plantillas.id'], name='documentos_plantillas_plantilla_origen_id_fkey'),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id'], name='documentos_plantillas_tipo_documento_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_plantillas_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_documentos_plantillas_id', 'documentos_plantillas', ['id'], unique=False)
    op.create_index('ix_documentos_plantillas_institucion_id', 'documentos_plantillas', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_plantillas_plantilla_origen_id', 'documentos_plantillas', ['plantilla_origen_id'], unique=False)
    op.create_index('ix_documentos_plantillas_tipo_documento_id', 'documentos_plantillas', ['tipo_documento_id'], unique=False)
    op.create_table('edu_asentimiento_textos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('contenido', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tipo_texto', sa.VARCHAR(), server_default=sa.text("'asentimiento'::character varying"), autoincrement=False, nullable=False),
    sa.Column('nivel_educativo_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint("tipo_texto IN ('apoderado', 'asentimiento')", name='ck_edu_asentimiento_textos_tipo_valido'),
    sa.CheckConstraint('((nivel_educativo_id IS NULL) OR (institucion_id IS NOT NULL))', name='ck_edu_asentimiento_textos_nivel_requiere_institucion'),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='edu_asentimiento_textos_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_asentimiento_textos_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['nivel_educativo_id'], ['niveles_educativos.id'], name='edu_asentimiento_textos_nivel_educativo_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_asentimiento_textos_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_asentimiento_textos_id', 'edu_asentimiento_textos', ['id'], unique=False)
    op.create_index('ix_edu_asentimiento_textos_institucion_id', 'edu_asentimiento_textos', ['institucion_id'], unique=False)
    op.create_index('ix_edu_asentimiento_textos_nivel_educativo_id', 'edu_asentimiento_textos', ['nivel_educativo_id'], unique=False)
    op.create_index('uq_edu_textos_consent_global_version', 'edu_asentimiento_textos', ['tipo_texto', 'version'], unique=True, postgresql_where='(institucion_id IS NULL)')
    op.create_index('uq_edu_textos_consent_inst_general_version', 'edu_asentimiento_textos', ['institucion_id', 'tipo_texto', 'version'], unique=True, postgresql_where='((institucion_id IS NOT NULL) AND (nivel_educativo_id IS NULL))')
    op.create_index('uq_edu_textos_consent_inst_nivel_version', 'edu_asentimiento_textos', ['institucion_id', 'tipo_texto', 'nivel_educativo_id', 'version'], unique=True, postgresql_where='((institucion_id IS NOT NULL) AND (nivel_educativo_id IS NOT NULL))')
    op.create_table('edu_pruebas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('nombre_tecnico', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('nombre_publico', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('instrucciones', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('requiere_consentimiento', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('activa', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('escala_minima', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('escala_maxima', sa.INTEGER(), server_default=sa.text('3'), autoincrement=False, nullable=False),
    sa.Column('modo_calculo', sa.VARCHAR(), server_default=sa.text("'likert_suma'::character varying"), autoincrement=False, nullable=False),
    sa.Column('dias_minimos_entre_aplicaciones', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('motivo_consulta_default', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('tecnicas_adicionales', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('modo_interpretacion', sa.VARCHAR(), server_default=sa.text("'rango'::character varying"), autoincrement=False, nullable=False),
    sa.Column('visible_para_clientes', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('informante_tipo', sa.VARCHAR(), server_default=sa.text("'estudiante'::character varying"), autoincrement=False, nullable=False),
    sa.Column('criterio_normativo_activo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('ordenar_dimensiones_por_puntaje', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('agrupar_dimensiones_por_area', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('recomendacion_generica_default', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('observacion_conductual_default', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('nombre_corto', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.CheckConstraint("informante_tipo IN ('estudiante', 'padre_madre', 'docente')", name='ck_pruebas_informante_tipo_valido'),
    sa.CheckConstraint("modo_interpretacion IN ('rango', 'perfil')", name='ck_pruebas_modo_interpretacion_valido'),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='edu_pruebas_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_pruebas_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_pruebas_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_pruebas_id', 'edu_pruebas', ['id'], unique=False)
    op.create_index('ix_edu_pruebas_institucion_id', 'edu_pruebas', ['institucion_id'], unique=False)
    op.create_index('ix_edu_pruebas_nombre_tecnico', 'edu_pruebas', ['nombre_tecnico'], unique=False)
    op.create_table('edu_sesiones_seguimiento',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('psicologo_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('fecha', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('observaciones', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('accion_tomada', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('acuerdos_compromisos', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('proxima_cita', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('estado', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.CheckConstraint("estado IN ('Pendiente', 'En proceso', 'Atendido')", name='ck_sesiones_seguimiento_estado_valido'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_sesiones_seguimiento_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='edu_sesiones_seguimiento_persona_id_fkey'),
    sa.ForeignKeyConstraint(['psicologo_id'], ['auth_usuarios.id'], name='edu_sesiones_seguimiento_psicologo_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_sesiones_seguimiento_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_sesiones_seguimiento_fecha', 'edu_sesiones_seguimiento', ['fecha'], unique=False)
    op.create_index('ix_edu_sesiones_seguimiento_id', 'edu_sesiones_seguimiento', ['id'], unique=False)
    op.create_index('ix_edu_sesiones_seguimiento_institucion_id', 'edu_sesiones_seguimiento', ['institucion_id'], unique=False)
    op.create_index('ix_edu_sesiones_seguimiento_persona_fecha', 'edu_sesiones_seguimiento', ['persona_id', 'fecha'], unique=False)
    op.create_index('ix_edu_sesiones_seguimiento_persona_id', 'edu_sesiones_seguimiento', ['persona_id'], unique=False)
    op.create_table('grados',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nivel_educativo_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('orden', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='grados_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['nivel_educativo_id'], ['niveles_educativos.id'], name='grados_nivel_educativo_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='grados_pkey'),
    sa.UniqueConstraint('nivel_educativo_id', 'nombre', name='uq_grados_nivel_nombre', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_grados_id', 'grados', ['id'], unique=False)
    op.create_index('ix_grados_institucion_id', 'grados', ['institucion_id'], unique=False)
    op.create_index('ix_grados_nivel_educativo_id', 'grados', ['nivel_educativo_id'], unique=False)
    op.create_table('personas_antecedentes_clinicos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('recibe_terapia_psicologica_externa', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('detalle_terapia_psicologica_externa', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('recibe_atencion_psiquiatrica_externa', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('detalle_atencion_psiquiatrica_externa', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('diagnostico_reportado', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('actualizado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['auth_usuarios.id'], name='personas_antecedentes_clinicos_actualizado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='personas_antecedentes_clinicos_persona_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='personas_antecedentes_clinicos_pkey')
    )
    op.create_index('ix_personas_antecedentes_clinicos_id', 'personas_antecedentes_clinicos', ['id'], unique=False)
    op.create_index('ix_personas_antecedentes_clinicos_persona_id', 'personas_antecedentes_clinicos', ['persona_id'], unique=True)
    op.create_table('personas_datos_familiares',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('numero_hermanos', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('vive_con', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('lugar_nacimiento', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('lugar_procedencia', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('actualizado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['auth_usuarios.id'], name='personas_datos_familiares_actualizado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='personas_datos_familiares_persona_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='personas_datos_familiares_pkey')
    )
    op.create_index('ix_personas_datos_familiares_id', 'personas_datos_familiares', ['id'], unique=False)
    op.create_index('ix_personas_datos_familiares_persona_id', 'personas_datos_familiares', ['persona_id'], unique=True)
    op.create_table('procesos_promocion',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('anio_origen', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('anio_destino', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('estado', sa.VARCHAR(), server_default=sa.text("'borrador'::character varying"), autoincrement=False, nullable=False),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('fecha_creacion', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('confirmado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('fecha_confirmacion', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.CheckConstraint("estado IN ('borrador', 'confirmado', 'cancelado')", name='ck_procesos_promocion_estado_valido'),
    sa.ForeignKeyConstraint(['confirmado_por_usuario_id'], ['auth_usuarios.id'], name='procesos_promocion_confirmado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='procesos_promocion_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='procesos_promocion_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='procesos_promocion_pkey')
    )
    op.create_index('ix_procesos_promocion_id', 'procesos_promocion', ['id'], unique=False)
    op.create_index('ix_procesos_promocion_institucion_id', 'procesos_promocion', ['institucion_id'], unique=False)
    op.create_index('uq_proceso_promocion_confirmado', 'procesos_promocion', ['institucion_id', 'anio_origen', 'anio_destino'], unique=True, postgresql_where="((estado)::text = 'confirmado'::text)")
    op.create_table('registro_cambios_persona',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('campo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('valor_anterior', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('valor_nuevo', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('modificado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('rol_modificador', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='registro_cambios_persona_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['modificado_por_usuario_id'], ['auth_usuarios.id'], name='registro_cambios_persona_modificado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='registro_cambios_persona_persona_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='registro_cambios_persona_pkey')
    )
    op.create_index('ix_registro_cambios_persona_fecha', 'registro_cambios_persona', ['fecha'], unique=False)
    op.create_index('ix_registro_cambios_persona_id', 'registro_cambios_persona', ['id'], unique=False)
    op.create_index('ix_registro_cambios_persona_institucion_id', 'registro_cambios_persona', ['institucion_id'], unique=False)
    op.create_index('ix_registro_cambios_persona_persona_id', 'registro_cambios_persona', ['persona_id'], unique=False)
    op.create_table('citas_participantes',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('cita_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['cita_id'], ['citas_programadas.id'], name='citas_participantes_cita_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='citas_participantes_persona_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='citas_participantes_pkey'),
    sa.UniqueConstraint('cita_id', 'persona_id', name='uq_citas_participantes_cita_persona', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_citas_participantes_cita_id', 'citas_participantes', ['cita_id'], unique=False)
    op.create_index('ix_citas_participantes_id', 'citas_participantes', ['id'], unique=False)
    op.create_index('ix_citas_participantes_persona_id', 'citas_participantes', ['persona_id'], unique=False)
    op.create_table('consentimientos_informados',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('otorgado_por_nombre', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_otorgante', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('referencia_documento', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('registrado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('fecha_otorgamiento', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=True),
    sa.Column('revocado', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('fecha_revocacion', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('ip_registro', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('revocado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('ip_revocacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_consentimiento', sa.VARCHAR(), server_default=sa.text("'apoderado'::character varying"), autoincrement=False, nullable=False),
    sa.Column('estado', sa.VARCHAR(), server_default=sa.text("'vigente'::character varying"), autoincrement=False, nullable=False),
    sa.Column('otorgante_apellidos', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('otorgante_documento', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('otorgante_relacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('evidencia_ruta', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('evidencia_nombre_archivo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('evidencia_content_type', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('evidencia_tamano_bytes', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('evidencia_subido_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('evidencia_subido_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('texto_version_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint("estado IN ('vigente', 'revocado')", name='ck_consentimientos_estado_valido'),
    sa.CheckConstraint("tipo_consentimiento IN ('apoderado', 'asentimiento')", name='ck_consentimientos_tipo_valido'),
    sa.ForeignKeyConstraint(['evidencia_subido_por_usuario_id'], ['auth_usuarios.id'], name='fk_consentimientos_evidencia_subido_por_usuario'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='consentimientos_informados_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='consentimientos_informados_persona_id_fkey'),
    sa.ForeignKeyConstraint(['registrado_por_usuario_id'], ['auth_usuarios.id'], name='consentimientos_informados_registrado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['revocado_por_usuario_id'], ['auth_usuarios.id'], name='fk_consentimientos_revocado_por_usuario'),
    sa.ForeignKeyConstraint(['texto_version_id'], ['edu_asentimiento_textos.id'], name='consentimientos_informados_texto_version_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='consentimientos_informados_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_consentimientos_informados_estado', 'consentimientos_informados', ['estado'], unique=False)
    op.create_index('ix_consentimientos_informados_id', 'consentimientos_informados', ['id'], unique=False)
    op.create_index('ix_consentimientos_informados_persona_id', 'consentimientos_informados', ['persona_id'], unique=False)
    op.create_index('ix_consentimientos_informados_tipo_consentimiento', 'consentimientos_informados', ['tipo_consentimiento'], unique=False)
    op.create_index('uq_consentimiento_vigente_por_persona_y_tipo', 'consentimientos_informados', ['persona_id', 'institucion_id', 'tipo_consentimiento'], unique=True, postgresql_where="((estado)::text = 'vigente'::text)")
    op.create_table('documentos_institucionales',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('tipo_documento_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('plantilla_documento_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('alcance', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nivel_visibilidad', sa.VARCHAR(), server_default=sa.text("'confidencial_clinico'::character varying"), autoincrement=False, nullable=False),
    sa.Column('titulo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('version_actual', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('descartado_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('descartado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint("alcance IN ('institucion', 'estructura_academica', 'personas_especificas', 'ninguno')", name='ck_documentos_institucionales_alcance_valido'),
    sa.CheckConstraint("nivel_visibilidad IN ('confidencial_clinico', 'compartible_colegio')", name='ck_documentos_institucionales_visibilidad_valida'),
    sa.CheckConstraint('((descartado_en IS NULL) OR (version_actual IS NULL))', name='ck_documentos_institucionales_descartado_solo_borrador'),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='documentos_institucionales_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['descartado_por_usuario_id'], ['auth_usuarios.id'], name='documentos_institucionales_descartado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_institucionales_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['plantilla_documento_id'], ['documentos_plantillas.id'], name='documentos_institucionales_plantilla_documento_id_fkey'),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['documentos_tipos.id'], name='documentos_institucionales_tipo_documento_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_documentos_institucionales_alcance', 'documentos_institucionales', ['alcance'], unique=False)
    op.create_index('ix_documentos_institucionales_id', 'documentos_institucionales', ['id'], unique=False)
    op.create_index('ix_documentos_institucionales_institucion_id', 'documentos_institucionales', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_institucionales_listado', 'documentos_institucionales', ['institucion_id', 'creado_en'], unique=False, postgresql_where='(descartado_en IS NULL)')
    op.create_index('ix_documentos_institucionales_nivel_visibilidad', 'documentos_institucionales', ['nivel_visibilidad'], unique=False)
    op.create_index('ix_documentos_institucionales_plantilla_documento_id', 'documentos_institucionales', ['plantilla_documento_id'], unique=False)
    op.create_index('ix_documentos_institucionales_tipo_documento_id', 'documentos_institucionales', ['tipo_documento_id'], unique=False)
    op.create_table('documentos_plantilla_secciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('plantilla_documento_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('orden', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('tipo_seccion', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('titulo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('config', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', 'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', 'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo', 'firma_triple', 'resultados_prueba_multiple')", name='ck_documentos_plantilla_seccion_tipo_valido'),
    sa.ForeignKeyConstraint(['plantilla_documento_id'], ['documentos_plantillas.id'], name='documentos_plantilla_secciones_plantilla_documento_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='documentos_plantilla_secciones_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_documentos_plantilla_secciones_id', 'documentos_plantilla_secciones', ['id'], unique=False)
    op.create_index('ix_documentos_plantilla_secciones_plantilla_documento_id', 'documentos_plantilla_secciones', ['plantilla_documento_id'], unique=False)
    op.create_index('ix_documentos_plantilla_secciones_tipo_seccion', 'documentos_plantilla_secciones', ['tipo_seccion'], unique=False)
    op.create_table('edu_dimensiones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('prueba_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('descripcion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('tipo_calculo', sa.VARCHAR(), server_default=sa.text("'items'::character varying"), autoincrement=False, nullable=False),
    sa.Column('conteo_umbral_item', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('contenido_perfil_predominante', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('contenido_perfil_secundaria', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('conclusion_sugerida_perfil', sa.TEXT(), autoincrement=False, nullable=True),
    sa.CheckConstraint("(((tipo_calculo)::text <> 'conteo_sintomas'::text) OR (conteo_umbral_item IS NOT NULL))", name='ck_dimensiones_conteo_umbral_requerido'),
    sa.CheckConstraint("tipo_calculo IN ('items', 'suma_de_dimensiones', 'conteo_sintomas')", name='ck_dimensiones_tipo_calculo_valido'),
    sa.ForeignKeyConstraint(['prueba_id'], ['edu_pruebas.id'], name='edu_dimensiones_prueba_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_dimensiones_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_dimensiones_id', 'edu_dimensiones', ['id'], unique=False)
    op.create_table('edu_evaluaciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('prueba_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('creador_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('nombre_grupo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_creacion', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('activo', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('fecha_fin', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('estado', sa.VARCHAR(), server_default=sa.text("'activa'::character varying"), autoincrement=False, nullable=False),
    sa.Column('fecha_cierre', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('cerrada_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('motivo_cierre', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('alumno_ve_informe', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('tipo', sa.VARCHAR(), server_default=sa.text("'grupal'::character varying"), autoincrement=False, nullable=False),
    sa.CheckConstraint("estado IN ('activa', 'cerrada', 'cancelada')", name='ck_evaluaciones_estado_valido'),
    sa.CheckConstraint("tipo IN ('grupal', 'individual')", name='ck_evaluaciones_tipo_valido'),
    sa.ForeignKeyConstraint(['cerrada_por_usuario_id'], ['auth_usuarios.id'], name='edu_evaluaciones_cerrada_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['creador_id'], ['auth_usuarios.id'], name='edu_evaluaciones_creador_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_evaluaciones_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['prueba_id'], ['edu_pruebas.id'], name='edu_evaluaciones_prueba_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_evaluaciones_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_evaluaciones_id', 'edu_evaluaciones', ['id'], unique=False)
    op.create_index('ix_edu_evaluaciones_institucion_id', 'edu_evaluaciones', ['institucion_id'], unique=False)
    op.create_table('secciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('grado_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nombre', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('turno', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('anio_escolar', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['grado_id'], ['grados.id'], name='secciones_grado_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='secciones_institucion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='secciones_pkey'),
    sa.UniqueConstraint('grado_id', 'nombre', 'anio_escolar', name='uq_secciones_grado_nombre_anio', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_secciones_anio_escolar', 'secciones', ['anio_escolar'], unique=False)
    op.create_index('ix_secciones_grado_id', 'secciones', ['grado_id'], unique=False)
    op.create_index('ix_secciones_id', 'secciones', ['id'], unique=False)
    op.create_index('ix_secciones_institucion_id', 'secciones', ['institucion_id'], unique=False)
    op.create_table('documentos_institucionales_estructura',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('nivel_educativo_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('grado_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('seccion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint('(((nivel_educativo_id IS NOT NULL) AND (grado_id IS NULL) AND (seccion_id IS NULL)) OR ((nivel_educativo_id IS NULL) AND (grado_id IS NOT NULL) AND (seccion_id IS NULL)) OR ((nivel_educativo_id IS NULL) AND (grado_id IS NULL) AND (seccion_id IS NOT NULL)))', name='ck_documentos_estructura_un_solo_nivel'),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_institucionales_estr_documento_institucional_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['grado_id'], ['grados.id'], name='documentos_institucionales_estructura_grado_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_institucionales_estructura_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['nivel_educativo_id'], ['niveles_educativos.id'], name='documentos_institucionales_estructura_nivel_educativo_id_fkey'),
    sa.ForeignKeyConstraint(['seccion_id'], ['secciones.id'], name='documentos_institucionales_estructura_seccion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_estructura_pkey')
    )
    op.create_index('ix_documentos_institucionales_estructura_documento_inst_f131', 'documentos_institucionales_estructura', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estructura_grado_id', 'documentos_institucionales_estructura', ['grado_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estructura_id', 'documentos_institucionales_estructura', ['id'], unique=False)
    op.create_index('ix_documentos_institucionales_estructura_institucion_id', 'documentos_institucionales_estructura', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estructura_nivel_educativo_id', 'documentos_institucionales_estructura', ['nivel_educativo_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estructura_seccion_id', 'documentos_institucionales_estructura', ['seccion_id'], unique=False)
    op.create_table('documentos_institucionales_estudiantes',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('incluido_via', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nombre_completo_historico', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('seccion_id_historico', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('grado_seccion_historico', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("incluido_via IN ('seccion', 'manual')", name='ck_documentos_institucionales_estudiante_incluido_via_valido'),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_institucionales_estu_documento_institucional_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_institucionales_estudiantes_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='documentos_institucionales_estudiantes_persona_id_fkey'),
    sa.ForeignKeyConstraint(['seccion_id_historico'], ['secciones.id'], name='documentos_institucionales_estudiante_seccion_id_historico_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_estudiantes_pkey'),
    sa.UniqueConstraint('documento_institucional_id', 'persona_id', name='uq_documentos_institucionales_estudiante', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_documentos_institucionales_estudiantes_documento_ins_e856', 'documentos_institucionales_estudiantes', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estudiantes_id', 'documentos_institucionales_estudiantes', ['id'], unique=False)
    op.create_index('ix_documentos_institucionales_estudiantes_institucion_id', 'documentos_institucionales_estudiantes', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estudiantes_persona_id', 'documentos_institucionales_estudiantes', ['persona_id'], unique=False)
    op.create_index('ix_documentos_institucionales_estudiantes_seccion_id_historico', 'documentos_institucionales_estudiantes', ['seccion_id_historico'], unique=False)
    op.create_table('documentos_institucionales_seccion_contenido',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('plantilla_seccion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('contenido', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('editado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_institucionales_secc_documento_institucional_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['editado_por_usuario_id'], ['auth_usuarios.id'], name='documentos_institucionales_seccion__editado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['plantilla_seccion_id'], ['documentos_plantilla_secciones.id'], name='documentos_institucionales_seccion_co_plantilla_seccion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_seccion_contenido_pkey'),
    sa.UniqueConstraint('documento_institucional_id', 'plantilla_seccion_id', name='uq_documentos_seccion_contenido_unica', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_documentos_institucionales_seccion_contenido_documen_60fc', 'documentos_institucionales_seccion_contenido', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_institucionales_seccion_contenido_id', 'documentos_institucionales_seccion_contenido', ['id'], unique=False)
    op.create_index('ix_documentos_institucionales_seccion_contenido_plantil_7f29', 'documentos_institucionales_seccion_contenido', ['plantilla_seccion_id'], unique=False)
    op.create_table('documentos_institucionales_versiones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('numero_version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('contenido_snapshot', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('storage_key', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nombre_archivo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('mime_type', sa.VARCHAR(), server_default=sa.text("'application/pdf'::character varying"), autoincrement=False, nullable=False),
    sa.Column('tamano_bytes', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('checksum_sha256', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('generado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('generado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('motivo_version', sa.TEXT(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_institucionales_vers_documento_institucional_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['generado_por_usuario_id'], ['auth_usuarios.id'], name='documentos_institucionales_version_generado_por_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_versiones_pkey'),
    sa.UniqueConstraint('documento_institucional_id', 'numero_version', name='uq_documentos_institucionales_version_numero', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_documentos_institucionales_versiones_documento_insti_26da', 'documentos_institucionales_versiones', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_institucionales_versiones_id', 'documentos_institucionales_versiones', ['id'], unique=False)
    op.create_table('documentos_registro_lecturas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('leido_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('rol_lector', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_lectura', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('ip_lectura', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_acceso', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('numero_version_leida', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('acceso_via_visibilidad_colegio', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.CheckConstraint("tipo_acceso IN ('contenido', 'descarga_pdf')", name='ck_documentos_registro_lecturas_tipo_acceso_valido'),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_registro_lecturas_documento_institucional_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_registro_lecturas_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['leido_por_usuario_id'], ['auth_usuarios.id'], name='documentos_registro_lecturas_leido_por_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_registro_lecturas_pkey')
    )
    op.create_index('ix_documentos_registro_lecturas_documento_institucional_id', 'documentos_registro_lecturas', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_registro_lecturas_fecha_lectura', 'documentos_registro_lecturas', ['fecha_lectura'], unique=False)
    op.create_index('ix_documentos_registro_lecturas_id', 'documentos_registro_lecturas', ['id'], unique=False)
    op.create_index('ix_documentos_registro_lecturas_institucion_id', 'documentos_registro_lecturas', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_registro_lecturas_leido_por_usuario_id', 'documentos_registro_lecturas', ['leido_por_usuario_id'], unique=False)
    op.create_index('ix_documentos_registro_lecturas_tipo_acceso', 'documentos_registro_lecturas', ['tipo_acceso'], unique=False)
    op.create_table('edu_baremos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('dimension_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('edad_min', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('edad_max', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('sexo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('poblacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('puntaje_minimo', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.Column('puntaje_maximo', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.Column('tipo_puntaje', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('valor_convertido', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('nivel', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('interpretacion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('es_alerta', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('conclusion_sugerida', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('recomendacion_sugerida', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('activo', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('criterio_normativo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['dimension_id'], ['edu_dimensiones.id'], name='edu_baremos_dimension_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_baremos_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_baremos_id', 'edu_baremos', ['id'], unique=False)
    op.create_table('edu_dimensiones_componentes',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('dimension_compuesta_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('dimension_componente_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('orden', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.CheckConstraint('(dimension_compuesta_id <> dimension_componente_id)', name='ck_edu_dim_componentes_no_autorreferencia'),
    sa.ForeignKeyConstraint(['dimension_componente_id'], ['edu_dimensiones.id'], name='edu_dimensiones_componentes_dimension_componente_id_fkey'),
    sa.ForeignKeyConstraint(['dimension_compuesta_id'], ['edu_dimensiones.id'], name='edu_dimensiones_componentes_dimension_compuesta_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='edu_dimensiones_componentes_pkey'),
    sa.UniqueConstraint('dimension_compuesta_id', 'dimension_componente_id', name='uq_edu_dim_componentes_par', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_edu_dimensiones_componentes_dimension_componente_id', 'edu_dimensiones_componentes', ['dimension_componente_id'], unique=False)
    op.create_index('ix_edu_dimensiones_componentes_dimension_compuesta_id', 'edu_dimensiones_componentes', ['dimension_compuesta_id'], unique=False)
    op.create_index('ix_edu_dimensiones_componentes_id', 'edu_dimensiones_componentes', ['id'], unique=False)
    op.create_table('edu_inscripciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('evaluacion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('token', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('nombre_completo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('edad', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('sexo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('poblacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('estado', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_resolucion', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('acepto_asentimiento', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('fecha_asentimiento', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('ip_asentimiento', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('is_deleted', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('deleted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('is_anonymized', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('anonymized_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('informe_liberado', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('interpretacion_clinica', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('resultado_visible_alumno', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('revisado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('fecha_revision_informe', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('estado_interpretacion', sa.VARCHAR(), server_default=sa.text("'completa'::character varying"), autoincrement=False, nullable=False),
    sa.Column('dimensiones_sin_baremo', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('seccion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('grado_seccion_historico', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('consentimiento_apoderado_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('consentimiento_asentimiento_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('reglas_con_error', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('motivo_consulta', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('observacion_conductual', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('conclusion_override', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('recomendaciones_override', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('informante_tipo', sa.VARCHAR(), server_default=sa.text("'estudiante'::character varying"), autoincrement=False, nullable=False),
    sa.Column('informante_nombre', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('informante_relacion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('firma_cargo_override', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('tecnicas_override', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('firma_nombre_override', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('firma_dni_override', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('asentimiento_texto_version_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.CheckConstraint("estado IN ('Pendiente', 'En Progreso', 'Finalizado')", name='ck_inscripciones_estado_valido'),
    sa.CheckConstraint("estado_interpretacion IN ('completa', 'incompleta')", name='ck_inscripciones_estado_interpretacion_valido'),
    sa.CheckConstraint("informante_tipo IN ('estudiante', 'padre_madre', 'docente')", name='ck_inscripciones_informante_tipo_valido'),
    sa.ForeignKeyConstraint(['asentimiento_texto_version_id'], ['edu_asentimiento_textos.id'], name='edu_inscripciones_asentimiento_texto_version_id_fkey'),
    sa.ForeignKeyConstraint(['consentimiento_apoderado_id'], ['consentimientos_informados.id'], name='edu_inscripciones_consentimiento_apoderado_id_fkey'),
    sa.ForeignKeyConstraint(['consentimiento_asentimiento_id'], ['consentimientos_informados.id'], name='edu_inscripciones_consentimiento_asentimiento_id_fkey'),
    sa.ForeignKeyConstraint(['evaluacion_id'], ['edu_evaluaciones.id'], name='edu_inscripciones_evaluacion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='edu_inscripciones_persona_id_fkey'),
    sa.ForeignKeyConstraint(['revisado_por_usuario_id'], ['auth_usuarios.id'], name='fk_edu_inscripciones_revisado_por_usuario'),
    sa.ForeignKeyConstraint(['seccion_id'], ['secciones.id'], name='edu_inscripciones_seccion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_inscripciones_pkey'),
    sa.UniqueConstraint('evaluacion_id', 'persona_id', name='uq_edu_inscripciones_evaluacion_persona', postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_inscripciones_consentimiento_apoderado_id', 'edu_inscripciones', ['consentimiento_apoderado_id'], unique=False)
    op.create_index('ix_edu_inscripciones_consentimiento_asentimiento_id', 'edu_inscripciones', ['consentimiento_asentimiento_id'], unique=False)
    op.create_index('ix_edu_inscripciones_estado_interpretacion', 'edu_inscripciones', ['estado_interpretacion'], unique=False)
    op.create_index('ix_edu_inscripciones_id', 'edu_inscripciones', ['id'], unique=False)
    op.create_index('ix_edu_inscripciones_is_deleted', 'edu_inscripciones', ['is_deleted'], unique=False)
    op.create_index('ix_edu_inscripciones_persona_id', 'edu_inscripciones', ['persona_id'], unique=False)
    op.create_index('ix_edu_inscripciones_seccion_id', 'edu_inscripciones', ['seccion_id'], unique=False)
    op.create_index('ix_edu_inscripciones_token', 'edu_inscripciones', ['token'], unique=True)
    op.create_table('edu_preguntas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('prueba_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('dimension_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('texto_pregunta', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('orden', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('es_inverso', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('incluir_en_informe', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('etiqueta_informe', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('escala_minima', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('escala_maxima', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tipo_respuesta', sa.VARCHAR(), server_default=sa.text("'opcion_multiple'::character varying"), autoincrement=False, nullable=False),
    sa.Column('respuesta_correcta_numerica', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.CheckConstraint("(((tipo_respuesta)::text <> 'numerico'::text) OR (respuesta_correcta_numerica IS NOT NULL))", name='ck_preguntas_respuesta_correcta_numerica_requerida'),
    sa.CheckConstraint("tipo_respuesta IN ('opcion_multiple', 'numerico')", name='ck_preguntas_tipo_respuesta_valido'),
    sa.ForeignKeyConstraint(['dimension_id'], ['edu_dimensiones.id'], name='edu_preguntas_dimension_id_fkey'),
    sa.ForeignKeyConstraint(['prueba_id'], ['edu_pruebas.id'], name='edu_preguntas_prueba_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_preguntas_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_edu_preguntas_id', 'edu_preguntas', ['id'], unique=False)
    op.create_table('matriculas_academicas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('seccion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('fecha_inicio', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('fecha_fin', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('registrado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('motivo_apertura', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('motivo_cierre', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('motivo_detalle', sa.TEXT(), autoincrement=False, nullable=True),
    sa.CheckConstraint("((((motivo_apertura)::text IS DISTINCT FROM 'correccion'::text) AND ((motivo_cierre)::text IS DISTINCT FROM 'correccion'::text)) OR (motivo_detalle IS NOT NULL))", name='ck_matriculas_correccion_requiere_motivo'),
    sa.CheckConstraint("motivo_apertura IN ('promocion', 'repitencia', 'ingreso_nuevo', 'cambio_manual', 'correccion')", name='ck_matriculas_motivo_apertura_valido'),
    sa.CheckConstraint("motivo_cierre IN ('promocion', 'retiro', 'traslado', 'egreso', 'correccion')", name='ck_matriculas_motivo_cierre_valido'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='matriculas_academicas_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='matriculas_academicas_persona_id_fkey'),
    sa.ForeignKeyConstraint(['registrado_por_usuario_id'], ['auth_usuarios.id'], name='matriculas_academicas_registrado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['seccion_id'], ['secciones.id'], name='matriculas_academicas_seccion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='matriculas_academicas_pkey')
    )
    op.create_index('ix_matriculas_academicas_id', 'matriculas_academicas', ['id'], unique=False)
    op.create_index('ix_matriculas_academicas_institucion_id', 'matriculas_academicas', ['institucion_id'], unique=False)
    op.create_index('ix_matriculas_academicas_persona_id', 'matriculas_academicas', ['persona_id'], unique=False)
    op.create_index('ix_matriculas_academicas_seccion_id', 'matriculas_academicas', ['seccion_id'], unique=False)
    op.create_index('uq_matricula_activa_por_persona', 'matriculas_academicas', ['persona_id'], unique=True, postgresql_where='(fecha_fin IS NULL)')
    op.create_table('documentos_institucionales_resultados_prueba',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('plantilla_seccion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='documentos_institucionales_resu_documento_institucional_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='documentos_institucionales_resultados_prueb_inscripcion_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='documentos_institucionales_resultados_prueb_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='documentos_institucionales_resultados_prueba_persona_id_fkey'),
    sa.ForeignKeyConstraint(['plantilla_seccion_id'], ['documentos_plantilla_secciones.id'], name='documentos_institucionales_resultados_plantilla_seccion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='documentos_institucionales_resultados_prueba_pkey'),
    sa.UniqueConstraint('documento_institucional_id', 'plantilla_seccion_id', 'persona_id', name='uq_documentos_resultado_prueba_seccion_persona', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_documentos_institucionales_resultados_prueba_documen_e192', 'documentos_institucionales_resultados_prueba', ['documento_institucional_id'], unique=False)
    op.create_index('ix_documentos_institucionales_resultados_prueba_id', 'documentos_institucionales_resultados_prueba', ['id'], unique=False)
    op.create_index('ix_documentos_institucionales_resultados_prueba_inscripcion_id', 'documentos_institucionales_resultados_prueba', ['inscripcion_id'], unique=False)
    op.create_index('ix_documentos_institucionales_resultados_prueba_institucion_id', 'documentos_institucionales_resultados_prueba', ['institucion_id'], unique=False)
    op.create_index('ix_documentos_institucionales_resultados_prueba_persona_id', 'documentos_institucionales_resultados_prueba', ['persona_id'], unique=False)
    op.create_index('ix_documentos_institucionales_resultados_prueba_plantil_a45a', 'documentos_institucionales_resultados_prueba', ['plantilla_seccion_id'], unique=False)
    op.create_table('edu_casos_riesgo',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('origen', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('estado', sa.VARCHAR(), server_default=sa.text("'nuevo'::character varying"), autoincrement=False, nullable=False),
    sa.Column('responsable_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('motivo_cierre', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('cerrado_en', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('cerrado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('creado_en', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.CheckConstraint("(((origen)::text = 'prueba'::text) = (inscripcion_id IS NOT NULL))", name='ck_edu_casos_riesgo_inscripcion_segun_origen'),
    sa.CheckConstraint("estado IN ('nuevo', 'en_atencion', 'derivado', 'en_seguimiento', 'cerrado')", name='ck_edu_casos_riesgo_estado'),
    sa.CheckConstraint("origen IN ('prueba', 'antecedentes')", name='ck_edu_casos_riesgo_origen'),
    sa.ForeignKeyConstraint(['cerrado_por_usuario_id'], ['auth_usuarios.id'], name='edu_casos_riesgo_cerrado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_casos_riesgo_inscripcion_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_casos_riesgo_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='edu_casos_riesgo_persona_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['responsable_usuario_id'], ['auth_usuarios.id'], name='edu_casos_riesgo_responsable_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_casos_riesgo_pkey'),
    sa.UniqueConstraint('inscripcion_id', name='edu_casos_riesgo_inscripcion_id_key', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_edu_casos_riesgo_id', 'edu_casos_riesgo', ['id'], unique=False)
    op.create_index('ix_edu_casos_riesgo_institucion_id', 'edu_casos_riesgo', ['institucion_id'], unique=False)
    op.create_index('ix_edu_casos_riesgo_persona_id', 'edu_casos_riesgo', ['persona_id'], unique=False)
    op.create_index('ix_edu_casos_riesgo_responsable_usuario_id', 'edu_casos_riesgo', ['responsable_usuario_id'], unique=False)
    op.create_index('uq_edu_casos_riesgo_antecedentes_abierto', 'edu_casos_riesgo', ['persona_id'], unique=True, postgresql_where="(((origen)::text = 'antecedentes'::text) AND ((estado)::text <> 'cerrado'::text))")
    op.create_table('edu_informes',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('prueba_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('version_actual', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('actualizado_en', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_informes_inscripcion_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='edu_informes_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='edu_informes_persona_id_fkey'),
    sa.ForeignKeyConstraint(['prueba_id'], ['edu_pruebas.id'], name='edu_informes_prueba_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_informes_pkey'),
    sa.UniqueConstraint('inscripcion_id', name='uq_edu_informes_inscripcion', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_edu_informes_id', 'edu_informes', ['id'], unique=False)
    op.create_index('ix_edu_informes_inscripcion_id', 'edu_informes', ['inscripcion_id'], unique=False)
    op.create_index('ix_edu_informes_institucion_id', 'edu_informes', ['institucion_id'], unique=False)
    op.create_index('ix_edu_informes_persona_id', 'edu_informes', ['persona_id'], unique=False)
    op.create_table('edu_opciones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('pregunta_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('texto_opcion', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('valor_puntuacion', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['pregunta_id'], ['edu_preguntas.id'], name='edu_opciones_pregunta_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_opciones_pkey')
    )
    op.create_index('ix_edu_opciones_id', 'edu_opciones', ['id'], unique=False)
    op.create_table('edu_reglas_interpretacion',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('prueba_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('ambito', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('pregunta_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('dimension_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('operador', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('valor_comparacion', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=False),
    sa.Column('accion', sa.VARCHAR(), server_default=sa.text("'es_alerta'::character varying"), autoincrement=False, nullable=False),
    sa.Column('descripcion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('activa', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('creado_en', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.CheckConstraint("((((ambito)::text <> 'item'::text) OR (pregunta_id IS NOT NULL)) AND (((ambito)::text <> 'dimension'::text) OR (dimension_id IS NOT NULL)))", name='ck_reglas_interpretacion_campos_segun_ambito'),
    sa.CheckConstraint("((accion)::text = 'es_alerta'::text)", name='ck_reglas_interpretacion_accion_valida'),
    sa.CheckConstraint("ambito IN ('item', 'dimension', 'puntaje_total')", name='ck_reglas_interpretacion_ambito_valido'),
    sa.CheckConstraint("operador IN ('>', '>=', '<', '<=', '==', '!=')", name='ck_reglas_interpretacion_operador_valido'),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='edu_reglas_interpretacion_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['dimension_id'], ['edu_dimensiones.id'], name='edu_reglas_interpretacion_dimension_id_fkey'),
    sa.ForeignKeyConstraint(['pregunta_id'], ['edu_preguntas.id'], name='edu_reglas_interpretacion_pregunta_id_fkey'),
    sa.ForeignKeyConstraint(['prueba_id'], ['edu_pruebas.id'], name='edu_reglas_interpretacion_prueba_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_reglas_interpretacion_pkey')
    )
    op.create_index('ix_edu_reglas_interpretacion_id', 'edu_reglas_interpretacion', ['id'], unique=False)
    op.create_index('ix_edu_reglas_interpretacion_prueba_id', 'edu_reglas_interpretacion', ['prueba_id'], unique=False)
    op.create_table('edu_respuestas_socio',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('campo_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('valor', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['campo_id'], ['edu_campos_socio.id'], name='edu_respuestas_socio_campo_id_fkey'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_respuestas_socio_inscripcion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_respuestas_socio_pkey')
    )
    op.create_index('ix_edu_respuestas_socio_id', 'edu_respuestas_socio', ['id'], unique=False)
    op.create_table('edu_resultados_dimensiones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('dimension_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('puntaje_directo', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['dimension_id'], ['edu_dimensiones.id'], name='edu_resultados_dimensiones_dimension_id_fkey'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_resultados_dimensiones_inscripcion_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_resultados_dimensiones_pkey')
    )
    op.create_index('ix_edu_resultados_dimensiones_dimension_id', 'edu_resultados_dimensiones', ['dimension_id'], unique=False)
    op.create_index('ix_edu_resultados_dimensiones_id', 'edu_resultados_dimensiones', ['id'], unique=False)
    op.create_index('ix_edu_resultados_dimensiones_inscripcion_id', 'edu_resultados_dimensiones', ['inscripcion_id'], unique=False)
    op.create_table('procesos_promocion_detalle',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('proceso_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('matricula_origen_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('seccion_propuesta_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tipo_excepcion', sa.VARCHAR(), server_default=sa.text("'ninguna'::character varying"), autoincrement=False, nullable=False),
    sa.Column('seccion_definitiva_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('aplicado', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('matricula_resultante_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('advertencia_mapeo', sa.TEXT(), autoincrement=False, nullable=True),
    sa.CheckConstraint("tipo_excepcion IN ('ninguna', 'repitente', 'retirado', 'trasladado', 'cambio_manual', 'egreso')", name='ck_promocion_detalle_tipo_excepcion_valido'),
    sa.ForeignKeyConstraint(['matricula_origen_id'], ['matriculas_academicas.id'], name='procesos_promocion_detalle_matricula_origen_id_fkey'),
    sa.ForeignKeyConstraint(['matricula_resultante_id'], ['matriculas_academicas.id'], name='procesos_promocion_detalle_matricula_resultante_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='procesos_promocion_detalle_persona_id_fkey'),
    sa.ForeignKeyConstraint(['proceso_id'], ['procesos_promocion.id'], name='procesos_promocion_detalle_proceso_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['seccion_definitiva_id'], ['secciones.id'], name='procesos_promocion_detalle_seccion_definitiva_id_fkey'),
    sa.ForeignKeyConstraint(['seccion_propuesta_id'], ['secciones.id'], name='procesos_promocion_detalle_seccion_propuesta_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='procesos_promocion_detalle_pkey'),
    sa.UniqueConstraint('proceso_id', 'persona_id', name='uq_promocion_detalle_persona_por_proceso', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_procesos_promocion_detalle_id', 'procesos_promocion_detalle', ['id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_matricula_origen_id', 'procesos_promocion_detalle', ['matricula_origen_id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_matricula_resultante_id', 'procesos_promocion_detalle', ['matricula_resultante_id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_persona_id', 'procesos_promocion_detalle', ['persona_id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_proceso_id', 'procesos_promocion_detalle', ['proceso_id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_seccion_definitiva_id', 'procesos_promocion_detalle', ['seccion_definitiva_id'], unique=False)
    op.create_index('ix_procesos_promocion_detalle_seccion_propuesta_id', 'procesos_promocion_detalle', ['seccion_propuesta_id'], unique=False)
    op.create_table('edu_casos_riesgo_eventos',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('caso_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tipo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('estado_anterior', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('estado_nuevo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('responsable_anterior_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('responsable_nuevo_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('nota', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('creado_en', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['caso_id'], ['edu_casos_riesgo.id'], name='edu_casos_riesgo_eventos_caso_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['auth_usuarios.id'], name='edu_casos_riesgo_eventos_usuario_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_casos_riesgo_eventos_pkey')
    )
    op.create_index('ix_edu_casos_riesgo_eventos_caso_id', 'edu_casos_riesgo_eventos', ['caso_id'], unique=False)
    op.create_index('ix_edu_casos_riesgo_eventos_id', 'edu_casos_riesgo_eventos', ['id'], unique=False)
    op.create_table('edu_diagnosticos_alumno',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('dimension_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('nivel', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tipo_puntaje_usado', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('valor_convertido', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('interpretacion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('es_alerta', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('alerta_por', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('regla_activada_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('conclusion_sugerida', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('recomendacion_sugerida', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('rango_minimo', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.Column('rango_maximo', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.Column('baremo_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['baremo_id'], ['edu_baremos.id'], name='edu_diagnosticos_alumno_baremo_id_fkey', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['dimension_id'], ['edu_dimensiones.id'], name='edu_diagnosticos_alumno_dimension_id_fkey'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_diagnosticos_alumno_inscripcion_id_fkey'),
    sa.ForeignKeyConstraint(['regla_activada_id'], ['edu_reglas_interpretacion.id'], name='edu_diagnosticos_alumno_regla_activada_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_diagnosticos_alumno_pkey')
    )
    op.create_index('ix_edu_diagnosticos_alumno_alerta', 'edu_diagnosticos_alumno', ['inscripcion_id'], unique=False, postgresql_where='(es_alerta = true)')
    op.create_index('ix_edu_diagnosticos_alumno_dimension_id', 'edu_diagnosticos_alumno', ['dimension_id'], unique=False)
    op.create_index('ix_edu_diagnosticos_alumno_id', 'edu_diagnosticos_alumno', ['id'], unique=False)
    op.create_index('ix_edu_diagnosticos_alumno_inscripcion_id', 'edu_diagnosticos_alumno', ['inscripcion_id'], unique=False)
    op.create_table('edu_informe_versiones',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('informe_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('numero_version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('resultados_snapshot', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('storage_key', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('nombre_archivo', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('mime_type', sa.VARCHAR(), server_default=sa.text("'application/pdf'::character varying"), autoincrement=False, nullable=False),
    sa.Column('tamano_bytes', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('checksum_sha256', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('generado_en', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.Column('generado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('motivo_version', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('origen', sa.VARCHAR(), server_default=sa.text("'automatica'::character varying"), autoincrement=False, nullable=False),
    sa.Column('retracta_version_previa_liberada', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.CheckConstraint("origen IN ('automatica', 'reemision', 'reproceso')", name='ck_edu_informe_versiones_origen_valido'),
    sa.ForeignKeyConstraint(['generado_por_usuario_id'], ['auth_usuarios.id'], name='edu_informe_versiones_generado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['informe_id'], ['edu_informes.id'], name='edu_informe_versiones_informe_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='edu_informe_versiones_pkey'),
    sa.UniqueConstraint('informe_id', 'numero_version', name='uq_edu_informe_versiones_numero', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_edu_informe_versiones_id', 'edu_informe_versiones', ['id'], unique=False)
    op.create_index('ix_edu_informe_versiones_informe_id', 'edu_informe_versiones', ['informe_id'], unique=False)
    op.create_table('edu_respuestas_alumno',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('inscripcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('pregunta_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('opcion_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('puntaje_obtenido', sa.NUMERIC(precision=12, scale=4), autoincrement=False, nullable=True),
    sa.Column('respuesta_numerica', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.CheckConstraint('((opcion_id IS NOT NULL) <> (respuesta_numerica IS NOT NULL))', name='ck_respuestas_alumno_opcion_xor_numerica'),
    sa.ForeignKeyConstraint(['inscripcion_id'], ['edu_inscripciones.id'], name='edu_respuestas_alumno_inscripcion_id_fkey'),
    sa.ForeignKeyConstraint(['opcion_id'], ['edu_opciones.id'], name='edu_respuestas_alumno_opcion_id_fkey'),
    sa.ForeignKeyConstraint(['pregunta_id'], ['edu_preguntas.id'], name='edu_respuestas_alumno_pregunta_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='edu_respuestas_alumno_pkey')
    )
    op.create_index('ix_edu_respuestas_alumno_id', 'edu_respuestas_alumno', ['id'], unique=False)
    op.create_table('expediente_entradas',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('tipo_entrada', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('autor_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('fecha_entrada', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('version_actual', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('sesion_seguimiento_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('informe_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('contacto_familiar_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('documento_institucional_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('titulo', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('descripcion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('storage_key', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('nombre_archivo_original', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('content_type', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('incluir_en_pdf_informe', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.CheckConstraint("(((tipo_entrada IN ('observacion_conducta', 'derivacion')) AND (sesion_seguimiento_id IS NULL) AND (informe_id IS NULL) AND (contacto_familiar_id IS NULL) AND (documento_institucional_id IS NULL)) OR (((tipo_entrada)::text = 'contacto_apoderado'::text) AND (sesion_seguimiento_id IS NULL) AND (informe_id IS NULL) AND (documento_institucional_id IS NULL)) OR (((tipo_entrada)::text = 'sesion'::text) AND (sesion_seguimiento_id IS NOT NULL) AND (informe_id IS NULL) AND (contacto_familiar_id IS NULL) AND (documento_institucional_id IS NULL)) OR (((tipo_entrada)::text = 'aplicacion_prueba'::text) AND (informe_id IS NOT NULL) AND (sesion_seguimiento_id IS NULL) AND (contacto_familiar_id IS NULL) AND (documento_institucional_id IS NULL)) OR (((tipo_entrada)::text = 'documento_institucional'::text) AND (documento_institucional_id IS NOT NULL) AND (sesion_seguimiento_id IS NULL) AND (informe_id IS NULL) AND (contacto_familiar_id IS NULL)) OR (((tipo_entrada)::text = 'evidencia'::text) AND (storage_key IS NOT NULL) AND (sesion_seguimiento_id IS NULL) AND (contacto_familiar_id IS NULL) AND (documento_institucional_id IS NULL)))", name='ck_expediente_campos_segun_tipo'),
    sa.CheckConstraint("((incluir_en_pdf_informe = false) OR (((tipo_entrada)::text = 'evidencia'::text) AND (informe_id IS NOT NULL)))", name='ck_expediente_incluir_pdf_requiere_evidencia_con_informe'),
    sa.CheckConstraint("tipo_entrada IN ('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', 'aplicacion_prueba', 'documento_institucional', 'evidencia')", name='ck_expediente_tipo_entrada_valido'),
    sa.ForeignKeyConstraint(['autor_usuario_id'], ['auth_usuarios.id'], name='expediente_entradas_autor_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['contacto_familiar_id'], ['contactos_familiares.id'], name='expediente_entradas_contacto_familiar_id_fkey'),
    sa.ForeignKeyConstraint(['documento_institucional_id'], ['documentos_institucionales.id'], name='fk_expediente_entradas_documento_institucional'),
    sa.ForeignKeyConstraint(['informe_id'], ['edu_informes.id'], name='expediente_entradas_informe_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='expediente_entradas_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='expediente_entradas_persona_id_fkey'),
    sa.ForeignKeyConstraint(['sesion_seguimiento_id'], ['edu_sesiones_seguimiento.id'], name='expediente_entradas_sesion_seguimiento_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='expediente_entradas_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_expediente_entradas_autor_usuario_id', 'expediente_entradas', ['autor_usuario_id'], unique=False)
    op.create_index('ix_expediente_entradas_contacto_familiar_id', 'expediente_entradas', ['contacto_familiar_id'], unique=False)
    op.create_index('ix_expediente_entradas_documento_institucional_id', 'expediente_entradas', ['documento_institucional_id'], unique=False)
    op.create_index('ix_expediente_entradas_id', 'expediente_entradas', ['id'], unique=False)
    op.create_index('ix_expediente_entradas_informe_id', 'expediente_entradas', ['informe_id'], unique=False)
    op.create_index('ix_expediente_entradas_institucion_id', 'expediente_entradas', ['institucion_id'], unique=False)
    op.create_index('ix_expediente_entradas_persona_id', 'expediente_entradas', ['persona_id'], unique=False)
    op.create_index('ix_expediente_entradas_sesion_seguimiento_id', 'expediente_entradas', ['sesion_seguimiento_id'], unique=False)
    op.create_index('ix_expediente_entradas_tipo_entrada', 'expediente_entradas', ['tipo_entrada'], unique=False)
    op.create_table('expediente_entradas_version',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('entrada_expediente_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('numero_version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('motivo', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('contenido', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('interpretacion', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('diagnostico_presuntivo', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('creado_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('creado_en', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('motivo_version', sa.TEXT(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['creado_por_usuario_id'], ['auth_usuarios.id'], name='expediente_entradas_version_creado_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['entrada_expediente_id'], ['expediente_entradas.id'], name='expediente_entradas_version_entrada_expediente_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='expediente_entradas_version_pkey'),
    sa.UniqueConstraint('entrada_expediente_id', 'numero_version', name='uq_expediente_version_entrada_numero', postgresql_nulls_not_distinct=False)
    )
    op.create_index('ix_expediente_entradas_version_entrada_expediente_id', 'expediente_entradas_version', ['entrada_expediente_id'], unique=False)
    op.create_index('ix_expediente_entradas_version_id', 'expediente_entradas_version', ['id'], unique=False)
    op.create_table('registro_lecturas_expediente',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('entrada_expediente_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('persona_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('institucion_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('leido_por_usuario_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('rol_lector', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('fecha_lectura', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('ip_lectura', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('numero_version_leida', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('autorizacion_acceso_colegio_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['autorizacion_acceso_colegio_id'], ['autorizaciones_acceso_colegio.id'], name='registro_lecturas_expediente_autorizacion_acceso_colegio_i_fkey'),
    sa.ForeignKeyConstraint(['entrada_expediente_id'], ['expediente_entradas.id'], name='registro_lecturas_expediente_entrada_expediente_id_fkey'),
    sa.ForeignKeyConstraint(['institucion_id'], ['instituciones.id'], name='registro_lecturas_expediente_institucion_id_fkey'),
    sa.ForeignKeyConstraint(['leido_por_usuario_id'], ['auth_usuarios.id'], name='registro_lecturas_expediente_leido_por_usuario_id_fkey'),
    sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], name='registro_lecturas_expediente_persona_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='registro_lecturas_expediente_pkey')
    )
    op.create_index('ix_registro_lecturas_expediente_autorizacion_acceso_colegio_id', 'registro_lecturas_expediente', ['autorizacion_acceso_colegio_id'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_entrada_expediente_id', 'registro_lecturas_expediente', ['entrada_expediente_id'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_fecha_lectura', 'registro_lecturas_expediente', ['fecha_lectura'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_id', 'registro_lecturas_expediente', ['id'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_institucion_id', 'registro_lecturas_expediente', ['institucion_id'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_leido_por_usuario_id', 'registro_lecturas_expediente', ['leido_por_usuario_id'], unique=False)
    op.create_index('ix_registro_lecturas_expediente_persona_id', 'registro_lecturas_expediente', ['persona_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_registro_lecturas_expediente_persona_id', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_leido_por_usuario_id', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_institucion_id', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_id', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_fecha_lectura', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_entrada_expediente_id', table_name='registro_lecturas_expediente')
    op.drop_index('ix_registro_lecturas_expediente_autorizacion_acceso_colegio_id', table_name='registro_lecturas_expediente')
    op.drop_table('registro_lecturas_expediente')
    op.drop_index('ix_expediente_entradas_version_id', table_name='expediente_entradas_version')
    op.drop_index('ix_expediente_entradas_version_entrada_expediente_id', table_name='expediente_entradas_version')
    op.drop_table('expediente_entradas_version')
    op.drop_index('ix_expediente_entradas_tipo_entrada', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_sesion_seguimiento_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_persona_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_institucion_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_informe_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_documento_institucional_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_contacto_familiar_id', table_name='expediente_entradas')
    op.drop_index('ix_expediente_entradas_autor_usuario_id', table_name='expediente_entradas')
    op.drop_table('expediente_entradas')
    op.drop_index('ix_edu_respuestas_alumno_id', table_name='edu_respuestas_alumno')
    op.drop_table('edu_respuestas_alumno')
    op.drop_index('ix_edu_informe_versiones_informe_id', table_name='edu_informe_versiones')
    op.drop_index('ix_edu_informe_versiones_id', table_name='edu_informe_versiones')
    op.drop_table('edu_informe_versiones')
    op.drop_index('ix_edu_diagnosticos_alumno_inscripcion_id', table_name='edu_diagnosticos_alumno')
    op.drop_index('ix_edu_diagnosticos_alumno_id', table_name='edu_diagnosticos_alumno')
    op.drop_index('ix_edu_diagnosticos_alumno_dimension_id', table_name='edu_diagnosticos_alumno')
    op.drop_index('ix_edu_diagnosticos_alumno_alerta', table_name='edu_diagnosticos_alumno', postgresql_where='(es_alerta = true)')
    op.drop_table('edu_diagnosticos_alumno')
    op.drop_index('ix_edu_casos_riesgo_eventos_id', table_name='edu_casos_riesgo_eventos')
    op.drop_index('ix_edu_casos_riesgo_eventos_caso_id', table_name='edu_casos_riesgo_eventos')
    op.drop_table('edu_casos_riesgo_eventos')
    op.drop_index('ix_procesos_promocion_detalle_seccion_propuesta_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_seccion_definitiva_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_proceso_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_persona_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_matricula_resultante_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_matricula_origen_id', table_name='procesos_promocion_detalle')
    op.drop_index('ix_procesos_promocion_detalle_id', table_name='procesos_promocion_detalle')
    op.drop_table('procesos_promocion_detalle')
    op.drop_index('ix_edu_resultados_dimensiones_inscripcion_id', table_name='edu_resultados_dimensiones')
    op.drop_index('ix_edu_resultados_dimensiones_id', table_name='edu_resultados_dimensiones')
    op.drop_index('ix_edu_resultados_dimensiones_dimension_id', table_name='edu_resultados_dimensiones')
    op.drop_table('edu_resultados_dimensiones')
    op.drop_index('ix_edu_respuestas_socio_id', table_name='edu_respuestas_socio')
    op.drop_table('edu_respuestas_socio')
    op.drop_index('ix_edu_reglas_interpretacion_prueba_id', table_name='edu_reglas_interpretacion')
    op.drop_index('ix_edu_reglas_interpretacion_id', table_name='edu_reglas_interpretacion')
    op.drop_table('edu_reglas_interpretacion')
    op.drop_index('ix_edu_opciones_id', table_name='edu_opciones')
    op.drop_table('edu_opciones')
    op.drop_index('ix_edu_informes_persona_id', table_name='edu_informes')
    op.drop_index('ix_edu_informes_institucion_id', table_name='edu_informes')
    op.drop_index('ix_edu_informes_inscripcion_id', table_name='edu_informes')
    op.drop_index('ix_edu_informes_id', table_name='edu_informes')
    op.drop_table('edu_informes')
    op.drop_index('uq_edu_casos_riesgo_antecedentes_abierto', table_name='edu_casos_riesgo', postgresql_where="(((origen)::text = 'antecedentes'::text) AND ((estado)::text <> 'cerrado'::text))")
    op.drop_index('ix_edu_casos_riesgo_responsable_usuario_id', table_name='edu_casos_riesgo')
    op.drop_index('ix_edu_casos_riesgo_persona_id', table_name='edu_casos_riesgo')
    op.drop_index('ix_edu_casos_riesgo_institucion_id', table_name='edu_casos_riesgo')
    op.drop_index('ix_edu_casos_riesgo_id', table_name='edu_casos_riesgo')
    op.drop_table('edu_casos_riesgo')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_plantil_a45a', table_name='documentos_institucionales_resultados_prueba')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_persona_id', table_name='documentos_institucionales_resultados_prueba')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_institucion_id', table_name='documentos_institucionales_resultados_prueba')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_inscripcion_id', table_name='documentos_institucionales_resultados_prueba')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_id', table_name='documentos_institucionales_resultados_prueba')
    op.drop_index('ix_documentos_institucionales_resultados_prueba_documen_e192', table_name='documentos_institucionales_resultados_prueba')
    op.drop_table('documentos_institucionales_resultados_prueba')
    op.drop_index('uq_matricula_activa_por_persona', table_name='matriculas_academicas', postgresql_where='(fecha_fin IS NULL)')
    op.drop_index('ix_matriculas_academicas_seccion_id', table_name='matriculas_academicas')
    op.drop_index('ix_matriculas_academicas_persona_id', table_name='matriculas_academicas')
    op.drop_index('ix_matriculas_academicas_institucion_id', table_name='matriculas_academicas')
    op.drop_index('ix_matriculas_academicas_id', table_name='matriculas_academicas')
    op.drop_table('matriculas_academicas')
    op.drop_index('ix_edu_preguntas_id', table_name='edu_preguntas')
    op.drop_table('edu_preguntas')
    op.drop_index('ix_edu_inscripciones_token', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_seccion_id', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_persona_id', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_is_deleted', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_id', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_estado_interpretacion', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_consentimiento_asentimiento_id', table_name='edu_inscripciones')
    op.drop_index('ix_edu_inscripciones_consentimiento_apoderado_id', table_name='edu_inscripciones')
    op.drop_table('edu_inscripciones')
    op.drop_index('ix_edu_dimensiones_componentes_id', table_name='edu_dimensiones_componentes')
    op.drop_index('ix_edu_dimensiones_componentes_dimension_compuesta_id', table_name='edu_dimensiones_componentes')
    op.drop_index('ix_edu_dimensiones_componentes_dimension_componente_id', table_name='edu_dimensiones_componentes')
    op.drop_table('edu_dimensiones_componentes')
    op.drop_index('ix_edu_baremos_id', table_name='edu_baremos')
    op.drop_table('edu_baremos')
    op.drop_index('ix_documentos_registro_lecturas_tipo_acceso', table_name='documentos_registro_lecturas')
    op.drop_index('ix_documentos_registro_lecturas_leido_por_usuario_id', table_name='documentos_registro_lecturas')
    op.drop_index('ix_documentos_registro_lecturas_institucion_id', table_name='documentos_registro_lecturas')
    op.drop_index('ix_documentos_registro_lecturas_id', table_name='documentos_registro_lecturas')
    op.drop_index('ix_documentos_registro_lecturas_fecha_lectura', table_name='documentos_registro_lecturas')
    op.drop_index('ix_documentos_registro_lecturas_documento_institucional_id', table_name='documentos_registro_lecturas')
    op.drop_table('documentos_registro_lecturas')
    op.drop_index('ix_documentos_institucionales_versiones_id', table_name='documentos_institucionales_versiones')
    op.drop_index('ix_documentos_institucionales_versiones_documento_insti_26da', table_name='documentos_institucionales_versiones')
    op.drop_table('documentos_institucionales_versiones')
    op.drop_index('ix_documentos_institucionales_seccion_contenido_plantil_7f29', table_name='documentos_institucionales_seccion_contenido')
    op.drop_index('ix_documentos_institucionales_seccion_contenido_id', table_name='documentos_institucionales_seccion_contenido')
    op.drop_index('ix_documentos_institucionales_seccion_contenido_documen_60fc', table_name='documentos_institucionales_seccion_contenido')
    op.drop_table('documentos_institucionales_seccion_contenido')
    op.drop_index('ix_documentos_institucionales_estudiantes_seccion_id_historico', table_name='documentos_institucionales_estudiantes')
    op.drop_index('ix_documentos_institucionales_estudiantes_persona_id', table_name='documentos_institucionales_estudiantes')
    op.drop_index('ix_documentos_institucionales_estudiantes_institucion_id', table_name='documentos_institucionales_estudiantes')
    op.drop_index('ix_documentos_institucionales_estudiantes_id', table_name='documentos_institucionales_estudiantes')
    op.drop_index('ix_documentos_institucionales_estudiantes_documento_ins_e856', table_name='documentos_institucionales_estudiantes')
    op.drop_table('documentos_institucionales_estudiantes')
    op.drop_index('ix_documentos_institucionales_estructura_seccion_id', table_name='documentos_institucionales_estructura')
    op.drop_index('ix_documentos_institucionales_estructura_nivel_educativo_id', table_name='documentos_institucionales_estructura')
    op.drop_index('ix_documentos_institucionales_estructura_institucion_id', table_name='documentos_institucionales_estructura')
    op.drop_index('ix_documentos_institucionales_estructura_id', table_name='documentos_institucionales_estructura')
    op.drop_index('ix_documentos_institucionales_estructura_grado_id', table_name='documentos_institucionales_estructura')
    op.drop_index('ix_documentos_institucionales_estructura_documento_inst_f131', table_name='documentos_institucionales_estructura')
    op.drop_table('documentos_institucionales_estructura')
    op.drop_index('ix_secciones_institucion_id', table_name='secciones')
    op.drop_index('ix_secciones_id', table_name='secciones')
    op.drop_index('ix_secciones_grado_id', table_name='secciones')
    op.drop_index('ix_secciones_anio_escolar', table_name='secciones')
    op.drop_table('secciones')
    op.drop_index('ix_edu_evaluaciones_institucion_id', table_name='edu_evaluaciones')
    op.drop_index('ix_edu_evaluaciones_id', table_name='edu_evaluaciones')
    op.drop_table('edu_evaluaciones')
    op.drop_index('ix_edu_dimensiones_id', table_name='edu_dimensiones')
    op.drop_table('edu_dimensiones')
    op.drop_index('ix_documentos_plantilla_secciones_tipo_seccion', table_name='documentos_plantilla_secciones')
    op.drop_index('ix_documentos_plantilla_secciones_plantilla_documento_id', table_name='documentos_plantilla_secciones')
    op.drop_index('ix_documentos_plantilla_secciones_id', table_name='documentos_plantilla_secciones')
    op.drop_table('documentos_plantilla_secciones')
    op.drop_index('ix_documentos_institucionales_tipo_documento_id', table_name='documentos_institucionales')
    op.drop_index('ix_documentos_institucionales_plantilla_documento_id', table_name='documentos_institucionales')
    op.drop_index('ix_documentos_institucionales_nivel_visibilidad', table_name='documentos_institucionales')
    op.drop_index('ix_documentos_institucionales_listado', table_name='documentos_institucionales', postgresql_where='(descartado_en IS NULL)')
    op.drop_index('ix_documentos_institucionales_institucion_id', table_name='documentos_institucionales')
    op.drop_index('ix_documentos_institucionales_id', table_name='documentos_institucionales')
    op.drop_index('ix_documentos_institucionales_alcance', table_name='documentos_institucionales')
    op.drop_table('documentos_institucionales')
    op.drop_index('uq_consentimiento_vigente_por_persona_y_tipo', table_name='consentimientos_informados', postgresql_where="((estado)::text = 'vigente'::text)")
    op.drop_index('ix_consentimientos_informados_tipo_consentimiento', table_name='consentimientos_informados')
    op.drop_index('ix_consentimientos_informados_persona_id', table_name='consentimientos_informados')
    op.drop_index('ix_consentimientos_informados_id', table_name='consentimientos_informados')
    op.drop_index('ix_consentimientos_informados_estado', table_name='consentimientos_informados')
    op.drop_table('consentimientos_informados')
    op.drop_index('ix_citas_participantes_persona_id', table_name='citas_participantes')
    op.drop_index('ix_citas_participantes_id', table_name='citas_participantes')
    op.drop_index('ix_citas_participantes_cita_id', table_name='citas_participantes')
    op.drop_table('citas_participantes')
    op.drop_index('ix_registro_cambios_persona_persona_id', table_name='registro_cambios_persona')
    op.drop_index('ix_registro_cambios_persona_institucion_id', table_name='registro_cambios_persona')
    op.drop_index('ix_registro_cambios_persona_id', table_name='registro_cambios_persona')
    op.drop_index('ix_registro_cambios_persona_fecha', table_name='registro_cambios_persona')
    op.drop_table('registro_cambios_persona')
    op.drop_index('uq_proceso_promocion_confirmado', table_name='procesos_promocion', postgresql_where="((estado)::text = 'confirmado'::text)")
    op.drop_index('ix_procesos_promocion_institucion_id', table_name='procesos_promocion')
    op.drop_index('ix_procesos_promocion_id', table_name='procesos_promocion')
    op.drop_table('procesos_promocion')
    op.drop_index('ix_personas_datos_familiares_persona_id', table_name='personas_datos_familiares')
    op.drop_index('ix_personas_datos_familiares_id', table_name='personas_datos_familiares')
    op.drop_table('personas_datos_familiares')
    op.drop_index('ix_personas_antecedentes_clinicos_persona_id', table_name='personas_antecedentes_clinicos')
    op.drop_index('ix_personas_antecedentes_clinicos_id', table_name='personas_antecedentes_clinicos')
    op.drop_table('personas_antecedentes_clinicos')
    op.drop_index('ix_grados_nivel_educativo_id', table_name='grados')
    op.drop_index('ix_grados_institucion_id', table_name='grados')
    op.drop_index('ix_grados_id', table_name='grados')
    op.drop_table('grados')
    op.drop_index('ix_edu_sesiones_seguimiento_persona_id', table_name='edu_sesiones_seguimiento')
    op.drop_index('ix_edu_sesiones_seguimiento_persona_fecha', table_name='edu_sesiones_seguimiento')
    op.drop_index('ix_edu_sesiones_seguimiento_institucion_id', table_name='edu_sesiones_seguimiento')
    op.drop_index('ix_edu_sesiones_seguimiento_id', table_name='edu_sesiones_seguimiento')
    op.drop_index('ix_edu_sesiones_seguimiento_fecha', table_name='edu_sesiones_seguimiento')
    op.drop_table('edu_sesiones_seguimiento')
    op.drop_index('ix_edu_pruebas_nombre_tecnico', table_name='edu_pruebas')
    op.drop_index('ix_edu_pruebas_institucion_id', table_name='edu_pruebas')
    op.drop_index('ix_edu_pruebas_id', table_name='edu_pruebas')
    op.drop_table('edu_pruebas')
    op.drop_index('uq_edu_textos_consent_inst_nivel_version', table_name='edu_asentimiento_textos', postgresql_where='((institucion_id IS NOT NULL) AND (nivel_educativo_id IS NOT NULL))')
    op.drop_index('uq_edu_textos_consent_inst_general_version', table_name='edu_asentimiento_textos', postgresql_where='((institucion_id IS NOT NULL) AND (nivel_educativo_id IS NULL))')
    op.drop_index('uq_edu_textos_consent_global_version', table_name='edu_asentimiento_textos', postgresql_where='(institucion_id IS NULL)')
    op.drop_index('ix_edu_asentimiento_textos_nivel_educativo_id', table_name='edu_asentimiento_textos')
    op.drop_index('ix_edu_asentimiento_textos_institucion_id', table_name='edu_asentimiento_textos')
    op.drop_index('ix_edu_asentimiento_textos_id', table_name='edu_asentimiento_textos')
    op.drop_table('edu_asentimiento_textos')
    op.drop_index('ix_documentos_plantillas_tipo_documento_id', table_name='documentos_plantillas')
    op.drop_index('ix_documentos_plantillas_plantilla_origen_id', table_name='documentos_plantillas')
    op.drop_index('ix_documentos_plantillas_institucion_id', table_name='documentos_plantillas')
    op.drop_index('ix_documentos_plantillas_id', table_name='documentos_plantillas')
    op.drop_table('documentos_plantillas')
    op.drop_index('ix_contactos_familiares_persona_id', table_name='contactos_familiares')
    op.drop_index('ix_contactos_familiares_institucion_id', table_name='contactos_familiares')
    op.drop_index('ix_contactos_familiares_id', table_name='contactos_familiares')
    op.drop_table('contactos_familiares')
    op.drop_index('ix_citas_programadas_persona_id', table_name='citas_programadas')
    op.drop_index('ix_citas_programadas_id', table_name='citas_programadas')
    op.drop_table('citas_programadas')
    op.drop_index('uq_autorizacion_colegio_vigente_por_persona', table_name='autorizaciones_acceso_colegio', postgresql_where='(vigente = true)')
    op.drop_index('ix_autorizaciones_acceso_colegio_persona_id', table_name='autorizaciones_acceso_colegio')
    op.drop_index('ix_autorizaciones_acceso_colegio_institucion_id', table_name='autorizaciones_acceso_colegio')
    op.drop_index('ix_autorizaciones_acceso_colegio_id', table_name='autorizaciones_acceso_colegio')
    op.drop_table('autorizaciones_acceso_colegio')
    op.drop_index('ix_auth_tokens_recuperacion_token', table_name='auth_tokens_recuperacion')
    op.drop_index('ix_auth_tokens_recuperacion_id', table_name='auth_tokens_recuperacion')
    op.drop_table('auth_tokens_recuperacion')
    op.drop_index('ix_auth_sesiones_usuario_id', table_name='auth_sesiones')
    op.drop_table('auth_sesiones')
    op.drop_index('ix_auditoria_arco_persona_id', table_name='auditoria_arco')
    op.drop_index('ix_auditoria_arco_institucion_id', table_name='auditoria_arco')
    op.drop_index('ix_auditoria_arco_inscripcion_id', table_name='auditoria_arco')
    op.drop_index('ix_auditoria_arco_id', table_name='auditoria_arco')
    op.drop_index('ix_auditoria_arco_fecha', table_name='auditoria_arco')
    op.drop_index('ix_auditoria_arco_accion', table_name='auditoria_arco')
    op.drop_table('auditoria_arco')
    op.drop_index('ix_personas_institucion_id', table_name='personas')
    op.drop_index('ix_personas_id', table_name='personas')
    op.drop_index('ix_personas_documento_identidad', table_name='personas')
    op.drop_index('ix_personas_codigo_institucional', table_name='personas')
    op.drop_table('personas')
    op.drop_index('ix_niveles_educativos_institucion_id', table_name='niveles_educativos')
    op.drop_index('ix_niveles_educativos_id', table_name='niveles_educativos')
    op.drop_table('niveles_educativos')
    op.drop_index('ix_edu_campos_socio_id', table_name='edu_campos_socio')
    op.drop_index('ix_edu_campos_socio_cliente_id', table_name='edu_campos_socio')
    op.drop_table('edu_campos_socio')
    op.drop_index('ix_documentos_correlativos_tipo_documento_id', table_name='documentos_correlativos')
    op.drop_index('ix_documentos_correlativos_institucion_id', table_name='documentos_correlativos')
    op.drop_index('ix_documentos_correlativos_id', table_name='documentos_correlativos')
    op.drop_table('documentos_correlativos')
    op.drop_index('ix_auth_usuarios_institucion_id', table_name='auth_usuarios')
    op.drop_index('ix_auth_usuarios_id', table_name='auth_usuarios')
    op.drop_index('ix_auth_usuarios_email', table_name='auth_usuarios')
    op.drop_table('auth_usuarios')
    op.drop_index('ix_registro_tareas_asincronas_tipo_tarea', table_name='registro_tareas_asincronas')
    op.drop_index('ix_registro_tareas_asincronas_referencia_id', table_name='registro_tareas_asincronas')
    op.drop_index('ix_registro_tareas_asincronas_job_id', table_name='registro_tareas_asincronas')
    op.drop_index('ix_registro_tareas_asincronas_id', table_name='registro_tareas_asincronas')
    op.drop_table('registro_tareas_asincronas')
    op.drop_index('ix_instituciones_nombre', table_name='instituciones')
    op.drop_index('ix_instituciones_id', table_name='instituciones')
    op.drop_table('instituciones')
    op.drop_index('ix_documentos_tipos_id', table_name='documentos_tipos')
    op.drop_index('ix_documentos_tipos_clave', table_name='documentos_tipos')
    op.drop_table('documentos_tipos')
    op.drop_table('documentos_anios_oficiales')
