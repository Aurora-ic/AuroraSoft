"""dimension_compuesta

Revision ID: a3be794d45e0
Revises: 87688455d771
Create Date: 2026-09-30 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3be794d45e0'
down_revision: Union[str, Sequence[str], None] = '87688455d771'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Dimensión compuesta — una Dimension que, en vez de sumar sus propias
    # Pregunta, suma los puntaje_directo YA calculados de otras Dimension
    # (sus "componentes"), y a partir de ahí se comporta exactamente como
    # cualquier otra dimensión (Baremo, DiagnosticoAlumno, ReglaInterpretacion
    # no necesitan saber que existe este concepto). Resuelve el hueco
    # documentado de SCARED (total 0-82) y RCADS-47 (Total Ansiedad, Total
    # Ansiedad+Depresión), que no se podían cargar como Baremo porque
    # Pregunta.dimension_id es una FK única.
    #
    # NOT NULL + server_default='items': toda dimensión existente sigue
    # calculándose exactamente como antes, cero cambio de comportamiento.
    op.add_column(
        'edu_dimensiones',
        sa.Column('tipo_calculo', sa.String(), server_default='items', nullable=False),
    )
    op.create_check_constraint(
        'ck_dimensiones_tipo_calculo_valido',
        'edu_dimensiones',
        "tipo_calculo IN ('items', 'suma_de_dimensiones')",
    )

    # 🆕 Qué dimensiones alimentan a una dimensión compuesta. Deliberadamente
    # sin anidar (validado en crud, no solo documentado): dimension_componente_id
    # nunca es a su vez una dimensión compuesta, así el cálculo queda en dos
    # pasadas simples (ver crud.calcular_resultados_dimensiones) y no hace
    # falta detectar ciclos.
    op.create_table(
        'edu_dimensiones_componentes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dimension_compuesta_id', sa.Integer(), nullable=False),
        sa.Column('dimension_componente_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['dimension_compuesta_id'], ['edu_dimensiones.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['dimension_componente_id'], ['edu_dimensiones.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'dimension_compuesta_id', 'dimension_componente_id',
            name='uq_edu_dim_componentes_par',
        ),
        sa.CheckConstraint(
            'dimension_compuesta_id != dimension_componente_id',
            name='ck_edu_dim_componentes_no_autorreferencia',
        ),
    )
    op.create_index(
        op.f('ix_edu_dimensiones_componentes_id'), 'edu_dimensiones_componentes', ['id'], unique=False,
    )
    op.create_index(
        op.f('ix_edu_dimensiones_componentes_dimension_compuesta_id'),
        'edu_dimensiones_componentes', ['dimension_compuesta_id'], unique=False,
    )
    op.create_index(
        op.f('ix_edu_dimensiones_componentes_dimension_componente_id'),
        'edu_dimensiones_componentes', ['dimension_componente_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_edu_dimensiones_componentes_dimension_componente_id'),
        table_name='edu_dimensiones_componentes',
    )
    op.drop_index(
        op.f('ix_edu_dimensiones_componentes_dimension_compuesta_id'),
        table_name='edu_dimensiones_componentes',
    )
    op.drop_index(op.f('ix_edu_dimensiones_componentes_id'), table_name='edu_dimensiones_componentes')
    op.drop_table('edu_dimensiones_componentes')
    op.drop_constraint('ck_dimensiones_tipo_calculo_valido', 'edu_dimensiones', type_='check')
    op.drop_column('edu_dimensiones', 'tipo_calculo')
