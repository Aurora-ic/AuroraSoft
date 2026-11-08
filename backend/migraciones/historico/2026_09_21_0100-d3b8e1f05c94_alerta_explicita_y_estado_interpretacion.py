"""Indicador explícito de alerta y estado de interpretación (B-5, B-6).

B-5 — Hasta ahora la retención de un informe dependía de que el texto libre
`Baremo.nivel` coincidiera exactamente con "alto", "crítico", "critico" o
"riesgo". Un baremo llamado "Alto riesgo" o "Severo" no disparaba nada y el
informe de un alumno en crisis se entregaba solo. Se añade `es_alerta` como
indicador explícito, y se copia a `DiagnosticoAlumno` al interpretar.

B-6 — Una dimensión sin baremo aplicable no generaba diagnóstico, y aguas
arriba "sin diagnósticos" se leía como "sin riesgo". Se añade
`estado_interpretacion` para separar un resultado psicométrico real de un
fallo de configuración.

Compatibilidad: el relleno marca como alerta exactamente los baremos que el
código anterior habría detectado, así que ninguna prueba ya configurada cambia
de comportamiento. Lo mismo para los diagnósticos históricos.

Revision ID: d3b8e1f05c94
Revises: a1f4c9d27e30
Create Date: 2026-09-21 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3b8e1f05c94"
down_revision: Union[str, Sequence[str], None] = "a1f4c9d27e30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mismo conjunto que usaba modulos/educativo/models.NIVELES_DE_ALERTA antes de
# esta migración. Se replica aquí a propósito: una migración debe seguir
# reproduciendo el mismo resultado aunque esa constante cambie más adelante.
NIVELES_DE_ALERTA_HISTORICOS = ("alto", "crítico", "critico", "riesgo")

INTERPRETACION_COMPLETA = "completa"


def upgrade() -> None:
    # ---------------- B-5 · indicador explícito de alerta ----------------
    op.add_column(
        "edu_baremos",
        sa.Column("es_alerta", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "edu_diagnosticos_alumno",
        sa.Column("es_alerta", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Preserva el comportamiento actual: se marcan como alerta exactamente los
    # tramos que la comparación de texto anterior habría detectado.
    op.execute(
        sa.text(
            """
            UPDATE edu_baremos
            SET es_alerta = true
            WHERE nivel IS NOT NULL
              AND lower(btrim(nivel)) IN :niveles
            """
        ).bindparams(sa.bindparam("niveles", value=NIVELES_DE_ALERTA_HISTORICOS, expanding=True))
    )

    # Los diagnósticos ya emitidos conservan su condición histórica.
    op.execute(
        sa.text(
            """
            UPDATE edu_diagnosticos_alumno
            SET es_alerta = true
            WHERE nivel IS NOT NULL
              AND lower(btrim(nivel)) IN :niveles
            """
        ).bindparams(sa.bindparam("niveles", value=NIVELES_DE_ALERTA_HISTORICOS, expanding=True))
    )

    # ---------------- B-6 · estado de la interpretación ----------------
    op.add_column(
        "edu_inscripciones",
        sa.Column(
            "estado_interpretacion", sa.String(), nullable=False,
            server_default=INTERPRETACION_COMPLETA,
        ),
    )
    op.add_column(
        "edu_inscripciones",
        sa.Column("dimensiones_sin_baremo", sa.Text(), nullable=True),
    )

    # Índice para el listado de casos pendientes de revisión: consulta por
    # "retenidos" que el panel del psicólogo hará de forma habitual.
    op.create_index(
        "ix_edu_inscripciones_estado_interpretacion",
        "edu_inscripciones",
        ["estado_interpretacion"],
    )

    # Se retiran los server_default una vez rellenadas las filas existentes:
    # a partir de aquí el valor lo fija explícitamente la aplicación, igual
    # que hacen las migraciones b61a3a9db71c y e72c49df46b1.
    op.alter_column("edu_baremos", "es_alerta", server_default=sa.false())
    op.alter_column("edu_diagnosticos_alumno", "es_alerta", server_default=sa.false())


def downgrade() -> None:
    op.drop_index("ix_edu_inscripciones_estado_interpretacion", table_name="edu_inscripciones")
    op.drop_column("edu_inscripciones", "dimensiones_sin_baremo")
    op.drop_column("edu_inscripciones", "estado_interpretacion")
    op.drop_column("edu_diagnosticos_alumno", "es_alerta")
    op.drop_column("edu_baremos", "es_alerta")
