"""plantillas_predeterminadas_globales

Primer paso del catálogo de plantillas PREDETERMINADAS del motor de
documentos institucionales (ver docs/motor-documentos.md y docstring de
PlantillaDocumento en modulos/documentos/models.py):

- `documentos_plantillas.institucion_id` pasa a nullable. Una fila con
  institucion_id IS NULL es una plantilla predeterminada GLOBAL, mantenida
  por AuroraSoft (solo superadmin la crea/edita), pensada para que
  cualquier colegio la clone (POST .../clonar, ya abierto a STAFF_CLINICO)
  y edite su propia copia — las predeterminadas nunca se modifican por el
  uso de un colegio.
- Nuevo índice único parcial `uq_documentos_plantilla_predeterminada_activa_por_tipo`:
  como máximo una predeterminada global ACTIVA por tipo_documento_id. El
  índice único parcial ya existente (institucion_id, tipo_documento_id)
  NO cubre este caso — Postgres trata cada NULL de un índice "normal" como
  distinto de los demás, así que nunca chocaría entre sí.
- `subtitulo_tamano_pt` (Integer, nullable): tamaño del SUBTÍTULO de cada
  sección — hasta ahora fijo en `tamano_pt + 1` dentro de
  `pdf_generador._construir_estilos`, sin ningún control. Mismo criterio
  NULL-formula que `titulo_tamano_pt` (ver esa migración, b84f06e2d751):
  NULL reproduce exactamente el comportamiento de siempre, un valor
  explícito lo reemplaza del todo.
- `mostrar_fondo_institucion` (Boolean, NOT NULL, default false): toggle
  por plantilla para dibujar el fondo de página de la institución — apagado
  por defecto, cero cambio visual para cualquier plantilla ya cargada.
- `instituciones.fondo_documento_url` (String, nullable): la imagen de
  fondo de página COMPLETA de la institución, mismo patrón que
  `logo_url`/`logo_pie_pagina_url` (descarga SSRF-safe,
  core.url_segura.descargar_logo_seguro) pero nunca dibujada por sola
  presencia de la URL — cada plantilla decide con el toggle de arriba.
- `tipo_seccion` gana `'firma_triple'`: igual que 'firma_doble' más un
  tercer bloque de firma centrado debajo, para documentos que cierran con
  tres responsables.

Revision ID: a1c4f9e27d83
Revises: e6b1d4a9c3f5
Create Date: 2026-10-14 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1c4f9e27d83'
down_revision: Union[str, Sequence[str], None] = 'e6b1d4a9c3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('documentos_plantillas', 'institucion_id', existing_type=sa.Integer(), nullable=True)
    op.create_index(
        'uq_documentos_plantilla_predeterminada_activa_por_tipo',
        'documentos_plantillas', ['tipo_documento_id'],
        unique=True, postgresql_where=sa.text('activa = true AND institucion_id IS NULL'),
    )
    op.add_column('documentos_plantillas', sa.Column('subtitulo_tamano_pt', sa.Integer(), nullable=True))
    op.add_column(
        'documentos_plantillas',
        sa.Column('mostrar_fondo_institucion', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('instituciones', sa.Column('fondo_documento_url', sa.String(), nullable=True))

    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', "
        "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo', 'firma_triple')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', "
        "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo')",
    )

    op.drop_column('instituciones', 'fondo_documento_url')
    op.drop_column('documentos_plantillas', 'mostrar_fondo_institucion')
    op.drop_column('documentos_plantillas', 'subtitulo_tamano_pt')
    op.drop_index(
        'uq_documentos_plantilla_predeterminada_activa_por_tipo',
        table_name='documentos_plantillas',
        postgresql_where=sa.text('activa = true AND institucion_id IS NULL'),
    )
    # ⚠️ Solo revertible si ninguna fila quedó con institucion_id NULL (toda
    # predeterminada global creada tendría que borrarse antes) — mismo
    # criterio de downgrade "best effort, no a prueba de datos" que el resto
    # de este directorio.
    op.alter_column('documentos_plantillas', 'institucion_id', existing_type=sa.Integer(), nullable=False)
