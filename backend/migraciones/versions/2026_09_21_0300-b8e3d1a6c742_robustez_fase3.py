"""Robustez del backend: C-1, C-4, C-16 y C-17.

C-1  — Puntajes decimales. La cadena valor_puntuacion -> puntaje_obtenido ->
       puntaje_directo -> límites del baremo era Integer de punta a punta, así
       que una prueba con ítems ponderados perdía los decimales en silencio.
       Pasa a NUMERIC(12, 4). La conversión desde integer es exacta: ningún
       valor existente cambia.
C-4  — `auth_usuarios.token_version`, para invalidar los JWT emitidos antes de
       un cambio de contraseña.
C-16 — Claves foráneas que faltaban: edu_evaluaciones.creador_id y
       edu_campos_socio.cliente_id. Antes de crearlas se comprueba que no haya
       referencias huérfanas; si las hay, la migración se detiene y las lista.
C-17 — instituciones.plan_activo y limite_pruebas_mensual_por_alumno pasan a
       NOT NULL. Con NULL, el primero bloqueaba el login de todo el colegio y
       el segundo lanzaba TypeError al matricular. Solo se rellenan los NULL;
       los valores existentes no se tocan.

Revision ID: b8e3d1a6c742
Revises: f7a2c5e91d40
Create Date: 2026-09-21 03:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e3d1a6c742"
down_revision: Union[str, Sequence[str], None] = "f7a2c5e91d40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NUMERICO = sa.Numeric(12, 4)

# (tabla, columna) de toda la cadena de puntuación
COLUMNAS_PUNTAJE = [
    ("edu_opciones", "valor_puntuacion"),
    ("edu_respuestas_alumno", "puntaje_obtenido"),
    ("edu_resultados_dimensiones", "puntaje_directo"),
    ("edu_baremos", "puntaje_minimo"),
    ("edu_baremos", "puntaje_maximo"),
]

# Valores coherentes con lo que el código ya hacía (default del ORM y
# respaldo de puede_aplicar_prueba). No es lógica comercial nueva.
PLAN_ACTIVO_POR_DEFECTO = "true"
LIMITE_MENSUAL_POR_DEFECTO = 5


def _abortar_si_hay_huerfanos(consulta: str, mensaje: str) -> None:
    filas = op.get_bind().execute(sa.text(consulta)).fetchall()
    if filas:
        detalle = "\n".join(f"    - {tuple(f)}" for f in filas[:20])
        raise RuntimeError(
            f"{mensaje}\n  Filas huérfanas (hasta 20):\n{detalle}\n"
            "  Corrígelas o ponlas a NULL y vuelve a ejecutar la migración."
        )


def upgrade() -> None:
    # ---------------- C-1 · puntajes decimales ----------------
    for tabla, columna in COLUMNAS_PUNTAJE:
        op.alter_column(tabla, columna, existing_type=sa.Integer(), type_=NUMERICO)

    # ---------------- C-4 · versión de token ----------------
    # Se conserva el server_default: el modelo también lo declara.
    op.add_column(
        "auth_usuarios",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    # ---------------- C-16 · claves foráneas ----------------
    _abortar_si_hay_huerfanos(
        """
        SELECT e.id, e.creador_id FROM edu_evaluaciones e
        LEFT JOIN auth_usuarios u ON u.id = e.creador_id
        WHERE e.creador_id IS NOT NULL AND u.id IS NULL
        """,
        "C-16: hay campañas cuyo creador_id no corresponde a ningún usuario.",
    )
    _abortar_si_hay_huerfanos(
        """
        SELECT s.id, s.cliente_id FROM edu_campos_socio s
        LEFT JOIN instituciones i ON i.id = s.cliente_id
        WHERE s.cliente_id IS NOT NULL AND i.id IS NULL
        """,
        "C-16: hay campos sociodemográficos de una institución inexistente.",
    )
    # Mismos nombres que asignaría PostgreSQL (y create_all) a una FK sin
    # nombre explícito, para que ambos caminos den el mismo esquema.
    op.create_foreign_key(
        "edu_evaluaciones_creador_id_fkey", "edu_evaluaciones", "auth_usuarios",
        ["creador_id"], ["id"],
    )
    op.create_foreign_key(
        "edu_campos_socio_cliente_id_fkey", "edu_campos_socio", "instituciones",
        ["cliente_id"], ["id"],
    )
    op.create_index("ix_edu_campos_socio_cliente_id", "edu_campos_socio", ["cliente_id"])

    # ---------------- C-17 · licencia coherente ----------------
    op.execute(f"UPDATE instituciones SET plan_activo = {PLAN_ACTIVO_POR_DEFECTO} WHERE plan_activo IS NULL")
    op.alter_column(
        "instituciones", "plan_activo", existing_type=sa.Boolean(),
        nullable=False, server_default=sa.text(PLAN_ACTIVO_POR_DEFECTO),
    )
    op.execute(
        "UPDATE instituciones SET limite_pruebas_mensual_por_alumno = "
        f"{LIMITE_MENSUAL_POR_DEFECTO} WHERE limite_pruebas_mensual_por_alumno IS NULL"
    )
    # Sustituye también el DEFAULT 100 que alguna instalación tenía puesto a
    # mano fuera de las migraciones: el ORM nunca lo usaba (siempre enviaba 5).
    op.alter_column(
        "instituciones", "limite_pruebas_mensual_por_alumno", existing_type=sa.Integer(),
        nullable=False, server_default=sa.text(str(LIMITE_MENSUAL_POR_DEFECTO)),
    )


def downgrade() -> None:
    op.alter_column(
        "instituciones", "limite_pruebas_mensual_por_alumno", existing_type=sa.Integer(),
        nullable=True, server_default=None,
    )
    op.alter_column(
        "instituciones", "plan_activo", existing_type=sa.Boolean(),
        nullable=True, server_default=None,
    )

    op.drop_index("ix_edu_campos_socio_cliente_id", table_name="edu_campos_socio")
    op.drop_constraint("edu_campos_socio_cliente_id_fkey", "edu_campos_socio", type_="foreignkey")
    op.drop_constraint("edu_evaluaciones_creador_id_fkey", "edu_evaluaciones", type_="foreignkey")

    op.drop_column("auth_usuarios", "token_version")

    # Volver a entero redondea: es la pérdida que C-1 corrige. Se usa ROUND
    # explícito para que el resultado sea predecible y no un truncado.
    for tabla, columna in COLUMNAS_PUNTAJE:
        op.alter_column(
            tabla, columna, existing_type=NUMERICO, type_=sa.Integer(),
            postgresql_using=f"ROUND({columna})::integer",
        )
