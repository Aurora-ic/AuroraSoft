"""tipo_respuesta_numerico

Revision ID: 01f0b91b3907
Revises: 0ba2c8c23e7c
Create Date: 2026-10-17 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01f0b91b3907'
down_revision: Union[str, Sequence[str], None] = '0ba2c8c23e7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Pregunta.tipo_respuesta — cierra el límite #4 de "Cinco límites
    # reales del motor" (ver docs/catalogo-pruebas.md): hasta ahora
    # `guardar_respuestas_examen` solo sabía validar un par (pregunta_id,
    # opcion_id) ya existente en la BD, así que un ítem de respuesta
    # construida (ej. BARSIT "Razonamiento numérico": escribir los dos
    # números que faltan en una serie) no tenía forma de representarse sin
    # inventar alternativas de opción múltiple que ninguna fuente da.
    #
    # NOT NULL + server_default='opcion_multiple': toda Pregunta existente
    # (las 14 pruebas ya cargadas) sigue siendo 'opcion_multiple' sin ningún
    # cambio de comportamiento — cero impacto retroactivo.
    op.add_column(
        'edu_preguntas',
        sa.Column('tipo_respuesta', sa.String(), nullable=False, server_default='opcion_multiple'),
    )
    op.create_check_constraint(
        'ck_preguntas_tipo_respuesta_valido',
        'edu_preguntas',
        "tipo_respuesta IN ('opcion_multiple', 'numerico')",
    )
    # La clave de corrección de un ítem 'numerico' — lista de números
    # esperados en orden (ej. [30, 45] para una serie con dos espacios en
    # blanco). NULL para cualquier Pregunta 'opcion_multiple' (que sigue
    # usando OpcionRespuesta.valor_puntuacion, sin cambios). Mismo patrón
    # que Dimension.conteo_umbral_item: columna nueva nullable + CHECK que
    # la exige solo cuando el tipo de la fila realmente la necesita.
    op.add_column(
        'edu_preguntas',
        sa.Column('respuesta_correcta_numerica', sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        'ck_preguntas_respuesta_correcta_numerica_requerida',
        'edu_preguntas',
        "tipo_respuesta != 'numerico' OR respuesta_correcta_numerica IS NOT NULL",
    )

    # 🆕 RespuestaAlumno.respuesta_numerica — lo que el alumno escribió
    # realmente para un ítem 'numerico', análogo a lo que `opcion_id` ya
    # guarda para uno 'opcion_multiple'. `puntaje_obtenido` se sigue
    # calculando y guardando en el servidor (1/0), nunca se confía en nada
    # que mande el cliente — ver guardar_respuestas_examen.
    op.add_column(
        'edu_respuestas_alumno',
        sa.Column('respuesta_numerica', sa.JSON(), nullable=True),
    )
    # 🆕 Exactamente uno de los dos — toda fila existente ya cumple esto
    # (opcion_id siempre presente, respuesta_numerica recién creada y NULL
    # en todas), así que se agrega sin backfill.
    op.create_check_constraint(
        'ck_respuestas_alumno_opcion_xor_numerica',
        'edu_respuestas_alumno',
        "(opcion_id IS NOT NULL) != (respuesta_numerica IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_respuestas_alumno_opcion_xor_numerica', 'edu_respuestas_alumno', type_='check')
    op.drop_column('edu_respuestas_alumno', 'respuesta_numerica')
    op.drop_constraint('ck_preguntas_respuesta_correcta_numerica_requerida', 'edu_preguntas', type_='check')
    op.drop_column('edu_preguntas', 'respuesta_correcta_numerica')
    op.drop_constraint('ck_preguntas_tipo_respuesta_valido', 'edu_preguntas', type_='check')
    op.drop_column('edu_preguntas', 'tipo_respuesta')
