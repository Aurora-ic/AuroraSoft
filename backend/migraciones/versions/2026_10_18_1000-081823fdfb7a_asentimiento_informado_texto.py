"""asentimiento_informado_texto

Revision ID: 081823fdfb7a
Revises: 01f0b91b3907
Create Date: 2026-10-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '081823fdfb7a'
down_revision: Union[str, Sequence[str], None] = '01f0b91b3907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 🆕 Texto versionado del asentimiento informado que ve el alumno al
    # abrir su link de examen — hasta ahora era una constante fija en el
    # frontend (`TEXTO_ASENTIMIENTO_INFORMADO` en examen/[token]/page.tsx),
    # sin snapshot de qué versión vio el alumno al aceptar (solo quedaba el
    # booleano/fecha/IP de la aceptación). Ante una fiscalización, eso no
    # alcanza para probar QUÉ decía el texto que el alumno realmente aceptó
    # si se edita después — mismo problema que ya se cerró para el
    # consentimiento del apoderado/asentimiento pre-registrado
    # (consentimiento_apoderado_id/consentimiento_asentimiento_id en
    # edu_inscripciones), y se cierra aquí con el mismo patrón: una fuente
    # de contenido versionada + una FK de snapshot.
    #
    # institucion_id NULLABLE: NULL es la versión GLOBAL (mismo patrón que
    # PlantillaDocumento "predeterminada" — ver docs/motor-documentos.md),
    # que una institución usa mientras no tenga su propia versión activa.
    # Sin UniqueConstraint(institucion_id, version): Postgres nunca trata dos
    # NULL como iguales en una constraint UNIQUE, así que no serviría para
    # imponer "una sola versión activa a la vez" en el caso global — ese
    # invariante lo mantiene la aplicación (crud.crear_version_asentimiento_
    # texto desactiva la anterior en la misma transacción), igual que ya
    # hace PlantillaDocumento con sus predeterminadas.
    op.create_table(
        'edu_asentimiento_textos',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('institucion_id', sa.Integer(), sa.ForeignKey('instituciones.id'), nullable=True, index=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('contenido', sa.Text(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('creado_en', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('creado_por_usuario_id', sa.Integer(), sa.ForeignKey('auth_usuarios.id'), nullable=True),
    )
    # 🆕 Hallazgo real de concurrencia (tests/test_patron_concurrencia_
    # unitario.py): dos POST /asentimiento-textos simultáneos para la MISMA
    # institución podían calcular el mismo `version` (MAX+1, calculado en
    # Python, no en BD) y terminar con DOS filas activo=True a la vez —
    # justo el invariante que el propio modelo documenta como garantizado
    # por la aplicación. Dos índices únicos PARCIALES (uno no alcanza: un
    # UniqueConstraint normal sobre institucion_id nunca sirve para el caso
    # NULL, Postgres nunca trata dos NULL como iguales) cierran ambos casos
    # de verdad, sin inventar un mecanismo de lock nuevo: el commit que
    # pierde la carrera choca contra el índice y crud.crear_version_
    # asentimiento_texto lo traduce a 409 con commit_o_conflicto (core/
    # concurrencia.py), mismo patrón que el resto del repo.
    op.create_index(
        'uq_edu_asentimiento_textos_institucion_version',
        'edu_asentimiento_textos', ['institucion_id', 'version'],
        unique=True, postgresql_where=sa.text('institucion_id IS NOT NULL'),
    )
    op.create_index(
        'uq_edu_asentimiento_textos_global_version',
        'edu_asentimiento_textos', ['version'],
        unique=True, postgresql_where=sa.text('institucion_id IS NULL'),
    )

    # Snapshot en Inscripcion de qué versión vio y aceptó el alumno —
    # análogo a consentimiento_apoderado_id/consentimiento_asentimiento_id,
    # mismo criterio: se escribe una sola vez, en el momento real de la
    # aceptación (validar_y_registrar_alumno), nunca se vuelve a tocar
    # después aunque el texto activo cambie.
    op.add_column(
        'edu_inscripciones',
        sa.Column(
            'asentimiento_texto_version_id', sa.Integer(),
            sa.ForeignKey('edu_asentimiento_textos.id', name='edu_inscripciones_asentimiento_texto_version_id_fkey'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('edu_inscripciones', 'asentimiento_texto_version_id')
    op.drop_table('edu_asentimiento_textos')
