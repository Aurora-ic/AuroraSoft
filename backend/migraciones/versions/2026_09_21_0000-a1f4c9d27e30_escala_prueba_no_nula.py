"""Rellena y blinda la escala de puntuación de las pruebas (B-4).

La migración 371596cbc96e añadió `escala_minima`, `escala_maxima` y
`modo_calculo` a `edu_pruebas` sin `server_default`, así que toda prueba
anterior quedó con esas columnas en NULL. El motor de cálculo recodifica los
ítems inversos con `(escala_minima + escala_maxima) - valor`, de modo que un
NULL provocaba un TypeError en plena finalización del examen.

Esta migración hace dos cosas:

1. Rellena los NULL existentes. La escala se deduce de las opciones reales de
   cada prueba (MIN/MAX de `valor_puntuacion`), que es el dato correcto, y
   solo cae a 0..3 cuando la prueba todavía no tiene opciones cargadas.
2. Deja las tres columnas como NOT NULL con `server_default`, para que el
   problema no pueda reaparecer al crear pruebas nuevas.

Revision ID: a1f4c9d27e30
Revises: e72c49df46b1
Create Date: 2026-09-21 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1f4c9d27e30"
down_revision: Union[str, Sequence[str], None] = "e72c49df46b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ESCALA_MINIMA_POR_DEFECTO = 0
ESCALA_MAXIMA_POR_DEFECTO = 3
MODO_CALCULO_POR_DEFECTO = "likert_suma"


def upgrade() -> None:
    # 1. Deducir la escala desde las opciones realmente cargadas de cada prueba.
    #    Solo toca las pruebas que tienen algún NULL; las bien configuradas
    #    conservan su escala tal cual.
    op.execute(
        sa.text(
            """
            UPDATE edu_pruebas AS p
            SET escala_minima = COALESCE(p.escala_minima, rangos.min_valor),
                escala_maxima = COALESCE(p.escala_maxima, rangos.max_valor)
            FROM (
                SELECT preg.prueba_id AS prueba_id,
                       MIN(opc.valor_puntuacion) AS min_valor,
                       MAX(opc.valor_puntuacion) AS max_valor
                FROM edu_opciones AS opc
                JOIN edu_preguntas AS preg ON opc.pregunta_id = preg.id
                WHERE opc.valor_puntuacion IS NOT NULL
                GROUP BY preg.prueba_id
            ) AS rangos
            WHERE p.id = rangos.prueba_id
              AND (p.escala_minima IS NULL OR p.escala_maxima IS NULL)
            """
        )
    )

    # 2. Las pruebas que aún no tienen opciones cargadas no permiten deducir
    #    nada: caen al respaldo documentado.
    op.execute(
        sa.text(
            """
            UPDATE edu_pruebas
            SET escala_minima = COALESCE(escala_minima, :minimo),
                escala_maxima = COALESCE(escala_maxima, :maximo),
                modo_calculo  = COALESCE(modo_calculo, :modo)
            WHERE escala_minima IS NULL
               OR escala_maxima IS NULL
               OR modo_calculo IS NULL
            """
        ).bindparams(
            minimo=ESCALA_MINIMA_POR_DEFECTO,
            maximo=ESCALA_MAXIMA_POR_DEFECTO,
            modo=MODO_CALCULO_POR_DEFECTO,
        )
    )

    # 3. Blindaje de esquema: que no vuelva a entrar un NULL.
    op.alter_column(
        "edu_pruebas",
        "escala_minima",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text(str(ESCALA_MINIMA_POR_DEFECTO)),
    )
    op.alter_column(
        "edu_pruebas",
        "escala_maxima",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text(str(ESCALA_MAXIMA_POR_DEFECTO)),
    )
    op.alter_column(
        "edu_pruebas",
        "modo_calculo",
        existing_type=sa.String(),
        nullable=False,
        server_default=sa.text(f"'{MODO_CALCULO_POR_DEFECTO}'"),
    )


def downgrade() -> None:
    # Solo se revierten las restricciones de esquema. Los valores rellenados
    # se quedan: no hay forma de distinguir cuáles eran NULL originalmente,
    # y volver a ponerlos en NULL reintroduciría el TypeError.
    op.alter_column(
        "edu_pruebas",
        "modo_calculo",
        existing_type=sa.String(),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "edu_pruebas",
        "escala_maxima",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "edu_pruebas",
        "escala_minima",
        existing_type=sa.Integer(),
        nullable=True,
        server_default=None,
    )
