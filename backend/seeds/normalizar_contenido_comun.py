"""
Normaliza (sobrescribe) tres campos de contenido PROCEDIMENTAL — no clínico —
del catálogo PÚBLICO de pruebas (institucion_id IS NULL) al mismo texto
estándar en TODAS: `Prueba.motivo_consulta_default`, `Prueba.
tecnicas_adicionales` (el nombre de la prueba se añade aparte, ya lo hace
crud.py) y `Prueba.observacion_conductual_default`.

Decisión de producto explícita (sesión del 2026-10-12): a diferencia de
`Baremo.conclusion_sugerida`/`recomendacion_sugerida` (contenido clínico,
distinto por prueba y por tramo, adaptado de ejemplares reales — ver
"FUENTES DE CONTENIDO DEL INFORME" en CLAUDE.md), estos tres campos son el
MISMO texto fijo para cualquier prueba:
  - motivo_consulta_default: "Evaluación de tamizaje solicitada por el área
    de psicología del colegio."
  - tecnicas_adicionales: "Entrevista, Observación"
  - observacion_conductual_default: "El estudiante se mostró colaborador
    durante toda la aplicación."

Por eso este script es la ÚNICA excepción deliberada al criterio "nunca
pisar contenido ya cargado" que siguen todos los demás seed_*.py (sus
`_asegurar_contenido_informe_*` son aditivos: solo rellenan si el campo
está vacío). Aquí SÍ se sobrescribe sin condición — es exactamente lo que
se pidió estandarizar, y corre DESPUÉS de cualquier `seed_*.py` individual
(cuyo propio `MOTIVO_CONSULTA_DEFAULT`/`TECNICAS_ADICIONALES` locales
quedaron como documentación histórica de cómo se derivó ese contenido por
instrumento antes de esta estandarización — ver nota en cada docstring).

Alcance: SOLO el catálogo público (institucion_id IS NULL), EXCLUYENDO
"APTITUD_TECNICA_INTERNA" (seed_prueba_aptitud_tecnica.py) — es una prueba
sintética usada solo para ejercitar el motor (visible_para_clientes=False,
nunca aplicada a un estudiante real), no un instrumento clínico/educativo;
darle un "motivo de consulta" de psicología inventaría contexto que no
corresponde. Una prueba propia de una institución (si alguna vez existe)
tampoco se toca aquí.

Requiere la migración `b71f3e9c2a4d_observacion_conductual_default` ya
aplicada (`alembic upgrade head`) — añade esa columna a `edu_pruebas`.

Se puede correr cuantas veces se quiera: es determinista (no "idempotente
aditivo" como el resto), siempre deja el mismo resultado.

Ejecutar:
    python -m seeds.normalizar_contenido_comun
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de Prueba)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de Prueba)
from modulos.educativo import models

MOTIVO_CONSULTA_DEFAULT_COMUN = "Evaluación de tamizaje solicitada por el área de psicología del colegio."
TECNICAS_ADICIONALES_COMUN = "Entrevista, Observación"
OBSERVACION_CONDUCTUAL_DEFAULT_COMUN = "El estudiante se mostró colaborador durante toda la aplicación."


def normalizar():
    db = SessionLocal()
    try:
        pruebas = db.query(models.Prueba).filter(
            models.Prueba.institucion_id.is_(None),
            models.Prueba.nombre_tecnico != "APTITUD_TECNICA_INTERNA",
        ).all()
        if not pruebas:
            print("⚠️  No hay ninguna prueba pública cargada todavía — corre primero los seed_*.py de instrumentos.")
            return

        actualizadas = 0
        for prueba in pruebas:
            cambios = []
            if prueba.motivo_consulta_default != MOTIVO_CONSULTA_DEFAULT_COMUN:
                prueba.motivo_consulta_default = MOTIVO_CONSULTA_DEFAULT_COMUN
                cambios.append("motivo_consulta_default")
            if prueba.tecnicas_adicionales != TECNICAS_ADICIONALES_COMUN:
                prueba.tecnicas_adicionales = TECNICAS_ADICIONALES_COMUN
                cambios.append("tecnicas_adicionales")
            if prueba.observacion_conductual_default != OBSERVACION_CONDUCTUAL_DEFAULT_COMUN:
                prueba.observacion_conductual_default = OBSERVACION_CONDUCTUAL_DEFAULT_COMUN
                cambios.append("observacion_conductual_default")
            if cambios:
                actualizadas += 1
                print(f"✅ {prueba.nombre_tecnico} (id={prueba.id}): {', '.join(cambios)}")

        db.commit()
        print(f"\n{actualizadas} de {len(pruebas)} prueba(s) pública(s) actualizadas; "
              f"{len(pruebas) - actualizadas} ya tenían el contenido estándar.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error normalizando contenido común: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    normalizar()
