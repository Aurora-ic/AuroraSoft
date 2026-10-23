"""seccion_resultados_prueba_multiple

Decimocuarto `tipo_seccion` del motor de documentos institucionales:
'resultados_prueba_multiple' — consolida una cantidad VARIABLE de
aplicaciones psicométricas reales de UN mismo estudiante en una sola
sección (ej. un "informe psicométrico" que junta los resultados de las
pruebas que el alumno realmente rindió, PHQ-9 + GAD-7, sin fijar de
antemano cuántas).

A diferencia de 'resultados_prueba' (un solo vínculo fijo por sección, en
su propia tabla `DocumentoInstitucionalResultadoPrueba`), esta sección NO
necesita tabla nueva: la lista de `inscripcion_id` elegidos vive en
`DocumentoInstitucionalSeccionContenido.contenido = {"inscripcion_ids":
[...]}`, escrita exclusivamente por el nuevo endpoint
`PUT .../resultados-prueba-multiple` (`crud.vincular_resultados_prueba_
multiple`) — nunca por el PUT genérico de contenido de sección, porque
cada id referencia una Inscripcion real y necesita la misma
re-validación persona+institución que ya exige el vínculo simple.

Mismo patrón que las migraciones anteriores que ensancharon este mismo
CHECK ('firma_triple', 'grafico_barras'/'imagen_anexo', etc.) — ensancha
el CHECK, no agrega tabla.

Revision ID: c73e9f1a5b06
Revises: f28b6a3c0e91
Create Date: 2026-10-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c73e9f1a5b06'
down_revision: Union[str, Sequence[str], None] = 'f28b6a3c0e91'
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
        "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo', 'firma_triple', "
        "'resultados_prueba_multiple')",
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido', 'documentos_plantilla_secciones', type_='check',
    )
    op.create_check_constraint(
        'ck_documentos_plantilla_seccion_tipo_valido',
        'documentos_plantilla_secciones',
        "tipo_seccion IN ('encabezado', 'datos_filiacion', 'datos_familiares', "
        "'texto_libre', 'tabla_dinamica', 'resultados_prueba', 'firma', 'grupo_campos', "
        "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo', 'firma_triple')",
    )
