"""conteo_sintomas

Revision ID: e4ab309bbab8
Revises: 3a1f4fcd127d
Create Date: 2026-10-04 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4ab309bbab8'
down_revision: Union[str, Sequence[str], None] = '3a1f4fcd127d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Dimensión 'conteo_sintomas' — una Dimension con preguntas propias
    # (a diferencia de 'suma_de_dimensiones') cuyo puntaje_directo es la
    # CANTIDAD de ítems que alcanzan `conteo_umbral_item`, no la suma de sus
    # valores crudos. Resuelve el hueco real que surgió al cargar NICHQ
    # Vanderbilt (escala de evaluación para padres): su criterio clínico
    # oficial es "6 de 9 ítems con puntuación ≥2", no "sumar y comparar contra
    # un rango" — una suma puede coincidir para distribuciones de respuesta
    # que no cumplen ese conteo, así que no hay forma honesta de expresarlo
    # como un Baremo de suma sin este tipo_calculo nuevo.
    #
    # NOT NULL + server_default='items' en la columna ya existente
    # (tipo_calculo) no cambia — solo se amplía el CHECK para aceptar el
    # tercer valor. conteo_umbral_item es una columna nueva, nullable
    # (solo tiene sentido para 'conteo_sintomas'), así que toda dimensión
    # existente queda con NULL, cero cambio de comportamiento.
    op.drop_constraint('ck_dimensiones_tipo_calculo_valido', 'edu_dimensiones', type_='check')
    op.create_check_constraint(
        'ck_dimensiones_tipo_calculo_valido',
        'edu_dimensiones',
        "tipo_calculo IN ('items', 'suma_de_dimensiones', 'conteo_sintomas')",
    )
    op.add_column(
        'edu_dimensiones',
        sa.Column('conteo_umbral_item', sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        'ck_dimensiones_conteo_umbral_requerido',
        'edu_dimensiones',
        "tipo_calculo != 'conteo_sintomas' OR conteo_umbral_item IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_dimensiones_conteo_umbral_requerido', 'edu_dimensiones', type_='check')
    op.drop_column('edu_dimensiones', 'conteo_umbral_item')
    op.drop_constraint('ck_dimensiones_tipo_calculo_valido', 'edu_dimensiones', type_='check')
    op.create_check_constraint(
        'ck_dimensiones_tipo_calculo_valido',
        'edu_dimensiones',
        "tipo_calculo IN ('items', 'suma_de_dimensiones')",
    )
