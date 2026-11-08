"""informante_prueba_e_inscripcion

Revision ID: 486fadd173f0
Revises: b9fb300190a4
Create Date: 2026-09-29 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '486fadd173f0'
down_revision: Union[str, Sequence[str], None] = 'b9fb300190a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Informante — algunas pruebas reales (NICHQ Vanderbilt, SDQ, RCADS,
    # SCARED) NO las responde el propio estudiante, sino un padre/madre o un
    # docente ACERCA de él. El sujeto evaluado (Inscripcion.persona_id) nunca
    # cambia de significado; lo nuevo es registrar QUIÉN llenó el formulario.
    #
    # Prueba.informante_tipo declara qué versión de la batería es esta fila
    # (ej. "NICHQ Vanderbilt — versión docente" y "— versión padres" son DOS
    # Prueba distintas, cada una con sus propios ítems/baremos — mismo
    # patrón de datos que ya usa el catálogo, sin tocar el motor de cálculo).
    # NOT NULL + server_default='estudiante': toda prueba existente (PHQ-9,
    # aptitud técnica...) sigue siendo autorreporte del estudiante, sin
    # ningún cambio de comportamiento.
    op.add_column(
        'edu_pruebas',
        sa.Column('informante_tipo', sa.String(), server_default='estudiante', nullable=False),
    )
    op.create_check_constraint(
        'ck_pruebas_informante_tipo_valido',
        'edu_pruebas',
        "informante_tipo IN ('estudiante', 'padre_madre', 'docente')",
    )

    # Inscripcion.informante_tipo es un snapshot de Prueba.informante_tipo al
    # momento de matricular (mismo criterio que grado_seccion_historico) —
    # nunca se re-lee de Prueba después. informante_nombre/informante_relacion
    # quedan NULL para toda inscripción existente y para cualquier
    # autorreporte de estudiante (informante_tipo='estudiante'); solo se
    # llenan cuando quien responde no es el propio sujeto evaluado.
    op.add_column(
        'edu_inscripciones',
        sa.Column('informante_tipo', sa.String(), server_default='estudiante', nullable=False),
    )
    op.add_column('edu_inscripciones', sa.Column('informante_nombre', sa.String(), nullable=True))
    op.add_column('edu_inscripciones', sa.Column('informante_relacion', sa.String(), nullable=True))
    op.create_check_constraint(
        'ck_inscripciones_informante_tipo_valido',
        'edu_inscripciones',
        "informante_tipo IN ('estudiante', 'padre_madre', 'docente')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_inscripciones_informante_tipo_valido', 'edu_inscripciones', type_='check')
    op.drop_column('edu_inscripciones', 'informante_relacion')
    op.drop_column('edu_inscripciones', 'informante_nombre')
    op.drop_column('edu_inscripciones', 'informante_tipo')
    op.drop_constraint('ck_pruebas_informante_tipo_valido', 'edu_pruebas', type_='check')
    op.drop_column('edu_pruebas', 'informante_tipo')
