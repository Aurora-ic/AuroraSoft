"""secciones_grafico_imagen

Dos `tipo_seccion` nuevos del motor de documentos institucionales,
identificados como genuinamente faltantes para informes psicológicos
reales (cuadros/tablas ya cubiertos por 'grupo_campos'/'tabla_dinamica'):

- 'grafico_barras': gráfico de barras embebido como imagen, reusando
  core.pdf_generator.generar_grafico_barras. Datos manuales
  (etiqueta/valor) o, si se vincula a una Inscripcion real vía
  DocumentoInstitucionalResultadoPrueba (mismo mecanismo que
  'resultados_prueba'), automáticos — con el mismo candado de retención.
- 'imagen_anexo': una imagen subida directamente (nunca URL externa) a
  core/storage/, para dibujos/fotos de pruebas gráficas o proyectivas.

Mismo criterio que 'grupo_campos'/'firma_doble'/'ficha_imprimible' antes:
ensancha el CHECK, no agrega tabla nueva (ninguno de los dos necesita
tabla propia — el primero reusa DocumentoInstitucionalResultadoPrueba, el
segundo guarda su storage_key en DocumentoInstitucionalSeccionContenido).

Revision ID: a7c92e14f630
Revises: d5e3f82a6c91
Create Date: 2026-10-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c92e14f630'
down_revision: Union[str, Sequence[str], None] = 'd5e3f82a6c91'
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
        "'firma_doble', 'ficha_imprimible', 'grafico_barras', 'imagen_anexo')",
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
        "'firma_doble', 'ficha_imprimible')",
    )
