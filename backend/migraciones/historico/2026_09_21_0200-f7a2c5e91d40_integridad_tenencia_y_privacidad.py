"""Integridad, tenencia y privacidad: B-11, B-12, C-7 y C-15.

B-11 — Trazabilidad del consentimiento: IP desde la que se registró, y quién
       lo revocó y desde dónde. Antes la revocación no dejaba responsable.
B-12 — Bitácora `auditoria_arco`: las acciones irreversibles sobre datos
       personales pasan a constar por escrito.
C-7  — La unicidad del documento de identidad deja de ser global y pasa a ser
       por institución. Dos colegios pueden tener al mismo alumno (traslado)
       y el conflicto deja de filtrar que ese DNI existe en otro cliente.
C-15 — Un alumno del padrón no puede matricularse dos veces en la misma
       campaña.

Las dos restricciones nuevas se crean solo después de comprobar que no hay
datos en conflicto: si los hubiera, la migración se detiene con un mensaje
accionable en vez de fallar con un error opaco de PostgreSQL.

Revision ID: f7a2c5e91d40
Revises: d3b8e1f05c94
Create Date: 2026-09-21 02:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a2c5e91d40"
down_revision: Union[str, Sequence[str], None] = "d3b8e1f05c94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _abortar_si_hay_conflictos(consulta: str, mensaje: str) -> None:
    filas = op.get_bind().execute(sa.text(consulta)).fetchall()
    if filas:
        detalle = "\n".join(f"    - {tuple(f)}" for f in filas[:20])
        raise RuntimeError(
            f"{mensaje}\n"
            f"  Filas en conflicto (hasta 20):\n{detalle}\n"
            "  Resuélvelas a mano y vuelve a ejecutar la migración."
        )


def upgrade() -> None:
    # ---------------- B-11 · trazabilidad del consentimiento ----------------
    op.add_column("consentimientos_informados", sa.Column("ip_registro", sa.String(), nullable=True))
    op.add_column(
        "consentimientos_informados",
        sa.Column("revocado_por_usuario_id", sa.Integer(), nullable=True),
    )
    op.add_column("consentimientos_informados", sa.Column("ip_revocacion", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_consentimientos_revocado_por_usuario",
        "consentimientos_informados", "auth_usuarios",
        ["revocado_por_usuario_id"], ["id"],
    )

    # ---------------- B-12 · bitácora ARCO ----------------
    op.create_table(
        "auditoria_arco",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("accion", sa.String(), nullable=False),
        # Sin FK a propósito: la anonimización rompe el vínculo y el registro
        # debe sobrevivir al dato que describe.
        sa.Column("persona_id", sa.Integer(), nullable=True),
        sa.Column("inscripcion_id", sa.Integer(), nullable=True),
        sa.Column("institucion_id", sa.Integer(), nullable=True),
        sa.Column("ejecutado_por_usuario_id", sa.Integer(), nullable=False),
        sa.Column("rol_ejecutor", sa.String(), nullable=True),
        sa.Column("fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("ip_solicitante", sa.String(), nullable=True),
        sa.Column("detalle", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["institucion_id"], ["instituciones.id"]),
        sa.ForeignKeyConstraint(["ejecutado_por_usuario_id"], ["auth_usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for columna in ("id", "accion", "persona_id", "inscripcion_id", "institucion_id", "fecha"):
        op.create_index(op.f(f"ix_auditoria_arco_{columna}"), "auditoria_arco", [columna], unique=False)

    # ---------------- C-7 · documento único POR INSTITUCIÓN ----------------
    _abortar_si_hay_conflictos(
        """
        SELECT institucion_id, documento_identidad, count(*)
        FROM personas
        WHERE documento_identidad IS NOT NULL
        GROUP BY 1, 2 HAVING count(*) > 1
        """,
        "C-7: hay personas repetidas dentro de una misma institución con el "
        "mismo documento de identidad.",
    )
    # El índice único global se sustituye por uno normal (se sigue buscando
    # por documento) más la restricción compuesta.
    op.drop_index("ix_personas_documento_identidad", table_name="personas")
    op.create_index("ix_personas_documento_identidad", "personas", ["documento_identidad"], unique=False)
    op.create_unique_constraint(
        "uq_personas_institucion_documento", "personas", ["institucion_id", "documento_identidad"]
    )

    # ---------------- C-15 · una inscripción por alumno y campaña ----------------
    _abortar_si_hay_conflictos(
        """
        SELECT evaluacion_id, persona_id, count(*)
        FROM edu_inscripciones
        WHERE persona_id IS NOT NULL
        GROUP BY 1, 2 HAVING count(*) > 1
        """,
        "C-15: hay alumnos matriculados más de una vez en la misma campaña.",
    )
    op.create_unique_constraint(
        "uq_edu_inscripciones_evaluacion_persona",
        "edu_inscripciones", ["evaluacion_id", "persona_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_edu_inscripciones_evaluacion_persona", "edu_inscripciones", type_="unique"
    )

    op.drop_constraint("uq_personas_institucion_documento", "personas", type_="unique")
    op.drop_index("ix_personas_documento_identidad", table_name="personas")
    op.create_index("ix_personas_documento_identidad", "personas", ["documento_identidad"], unique=True)

    for columna in ("fecha", "institucion_id", "inscripcion_id", "persona_id", "accion", "id"):
        op.drop_index(op.f(f"ix_auditoria_arco_{columna}"), table_name="auditoria_arco")
    op.drop_table("auditoria_arco")

    op.drop_constraint(
        "fk_consentimientos_revocado_por_usuario", "consentimientos_informados", type_="foreignkey"
    )
    op.drop_column("consentimientos_informados", "ip_revocacion")
    op.drop_column("consentimientos_informados", "revocado_por_usuario_id")
    op.drop_column("consentimientos_informados", "ip_registro")
