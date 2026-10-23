"""seccion_ficha_imprimible

Décimo `tipo_seccion` del motor de documentos institucionales:
'ficha_imprimible' — un formulario en blanco (campos para completar a mano,
tabla de verificación con celdas vacías, listas de opciones con casillero,
líneas de firma en blanco) que NO se llena por la app — a diferencia de
'grupo_campos'/'tabla_dinamica' (que SÍ leen contenido guardado por
documento), este tipo es puro `PlantillaSeccion.config`: lo que ve el
profesional que genera el PDF es exactamente lo que verá impreso, listo
para que la docente/psicóloga lo complete con lápiz. Mismo criterio que
'grupo_campos'/'firma_doble' antes: ensancha el CHECK, no agrega tabla
nueva.

Revision ID: d5e3f82a6c91
Revises: c2a94e8d1b37
Create Date: 2026-10-10 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd5e3f82a6c91'
down_revision: Union[str, Sequence[str], None] = 'c2a94e8d1b37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', "
        "'firma_doble', 'ficha_imprimible')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', 'firma_doble')",
    )
