"""evidencia en expediente clinico

Revision ID: b85b001b2e64
Revises: 1254f6a5062a
Create Date: 2026-10-23 22:09:30.736675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b85b001b2e64'
down_revision: Union[str, Sequence[str], None] = '1254f6a5062a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # (se omite a propósito el rename de índice de edu_inscripciones que el
    # autogenerate detectó como drift -- misma deuda preexistente ya anotada
    # en 1254f6a5062a, sin relación con esta migración; no se toca aquí)
    op.add_column('expediente_entradas', sa.Column('titulo', sa.String(), nullable=True))
    op.add_column('expediente_entradas', sa.Column('descripcion', sa.Text(), nullable=True))
    op.add_column('expediente_entradas', sa.Column('storage_key', sa.String(), nullable=True))
    op.add_column('expediente_entradas', sa.Column('nombre_archivo_original', sa.String(), nullable=True))
    op.add_column('expediente_entradas', sa.Column('content_type', sa.String(), nullable=True))
    op.add_column('expediente_entradas', sa.Column('incluir_en_pdf_informe', sa.Boolean(), server_default='false', nullable=False))

    # 🔧 Alembic no detecta CHECK constraints por autogenerate -- a mano,
    # deben coincidir exactamente con __table_args__ en models.py.
    op.drop_constraint('ck_expediente_tipo_entrada_valido', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_tipo_entrada_valido',
        'expediente_entradas',
        "tipo_entrada IN "
        "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', "
        "'aplicacion_prueba', 'documento_institucional', 'evidencia')",
    )

    op.drop_constraint('ck_expediente_campos_segun_tipo', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_campos_segun_tipo',
        'expediente_entradas',
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
        " AND informe_id IS NULL AND contacto_familiar_id IS NULL)"
        " OR "
        "(tipo_entrada = 'evidencia' "
        " AND storage_key IS NOT NULL AND sesion_seguimiento_id IS NULL"
        " AND contacto_familiar_id IS NULL AND documento_institucional_id IS NULL)",
    )

    op.create_check_constraint(
        'ck_expediente_incluir_pdf_requiere_evidencia_con_informe',
        'expediente_entradas',
        "incluir_en_pdf_informe = false OR (tipo_entrada = 'evidencia' AND informe_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_expediente_incluir_pdf_requiere_evidencia_con_informe', 'expediente_entradas', type_='check')

    op.drop_constraint('ck_expediente_campos_segun_tipo', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_campos_segun_tipo',
        'expediente_entradas',
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

    op.drop_constraint('ck_expediente_tipo_entrada_valido', 'expediente_entradas', type_='check')
    op.create_check_constraint(
        'ck_expediente_tipo_entrada_valido',
        'expediente_entradas',
        "tipo_entrada IN "
        "('observacion_conducta', 'contacto_apoderado', 'derivacion', 'sesion', "
        "'aplicacion_prueba', 'documento_institucional')",
    )

    op.drop_column('expediente_entradas', 'incluir_en_pdf_informe')
    op.drop_column('expediente_entradas', 'content_type')
    op.drop_column('expediente_entradas', 'nombre_archivo_original')
    op.drop_column('expediente_entradas', 'storage_key')
    op.drop_column('expediente_entradas', 'descripcion')
    op.drop_column('expediente_entradas', 'titulo')
