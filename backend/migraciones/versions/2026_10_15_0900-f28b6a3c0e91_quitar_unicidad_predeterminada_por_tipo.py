"""quitar_unicidad_predeterminada_por_tipo

Revierte el índice único parcial
`uq_documentos_plantilla_predeterminada_activa_por_tipo` (agregado en
a1c4f9e27d83_plantillas_predeterminadas_globales) por ser, al usarlo de
verdad, la restricción equivocada.

Esa migración asumió que el catálogo de plantillas PREDETERMINADAS
globales (institucion_id IS NULL) debía seguir el mismo criterio "a lo sumo
una ACTIVA por tipo" que ya rige una institución real — pero el catálogo
global es un MENÚ de puntos de partida, no "la plantilla vigente de este
tipo": AuroraSoft necesita poder ofrecer varias predeterminadas activas
bajo el MISMO TipoDocumento al mismo tiempo (ej. un "Informe psicológico
escolar" y un "Informe psicológico para padres o apoderados", ambos bajo el
tipo "Informe individual" — cada uno un formato distinto para clonar, nunca
compitiendo entre sí). El índice que se quita aquí bloqueaba exactamente
eso con un IntegrityError al intentar cargar el segundo.

El índice ORIGINAL (`uq_documentos_plantilla_activa_por_institucion_y_tipo`,
sin tocar en esta migración) nunca necesitó este ajuste: Postgres no
considera que dos filas con `institucion_id IS NULL` "choquen" en un índice
único (NULL nunca es igual a NULL), así que varias predeterminadas del
mismo tipo ya convivían sin problema en ESE índice — el único índice que
sobraba era el nuevo.

`crud.crear_plantilla_documento`/`actualizar_plantilla_documento` también
se ajustaron (sesión de código, no de esquema) para nunca llamar
`_desactivar_plantillas_activas` cuando `institucion_id is None` — antes de
este fix, crear una segunda predeterminada activa habría desactivado en
silencio a la primera.

Revision ID: f28b6a3c0e91
Revises: a1c4f9e27d83
Create Date: 2026-10-15 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f28b6a3c0e91'
down_revision: Union[str, Sequence[str], None] = 'a1c4f9e27d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        'uq_documentos_plantilla_predeterminada_activa_por_tipo',
        table_name='documentos_plantillas',
        postgresql_where=sa.text('activa = true AND institucion_id IS NULL'),
    )


def downgrade() -> None:
    op.create_index(
        'uq_documentos_plantilla_predeterminada_activa_por_tipo',
        'documentos_plantillas', ['tipo_documento_id'],
        unique=True, postgresql_where=sa.text('activa = true AND institucion_id IS NULL'),
    )
