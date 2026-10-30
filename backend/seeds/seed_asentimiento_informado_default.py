"""
Carga la versión 1 GLOBAL (institucion_id=None) del texto de asentimiento
informado que el alumno ve al abrir su link de examen — migra al mecanismo
nuevo (`AsentimientoInformadoTexto`, ver docs/gaps-pendientes.md) el texto
que hasta ahora vivía como una constante fija en el frontend
(`TEXTO_ASENTIMIENTO_INFORMADO` en `aurora_ui/app/(examen)/examen/[token]/
page.tsx`), sin perder ni una palabra: es el mismo contenido, solo
reubicado.

Es idempotente: si ya existe una versión GLOBAL activa, no toca nada (para
no pisar un texto que el equipo clínico/legal ya haya revisado y
reemplazado por una versión 2). Para forzar una recarga, desactiva primero
la fila activa de edu_asentimiento_textos con institucion_id IS NULL.

Ejecutar (una sola vez, tras `alembic upgrade head`):
    python -m seeds.seed_asentimiento_informado_default

⚠️ Sigue siendo "texto sugerido, pendiente de validación institucional/
profesional" — exactamente la misma salvedad que ya tenía como constante
del frontend (ver examen/[token]/page.tsx antes de esta sesión). Migrar el
mecanismo no es lo mismo que validar el contenido; eso sigue pendiente del
equipo clínico/legal real.

Una institución que quiera su propio texto (distinto del global) lo hace
con `POST /educativo/asentimiento-textos` (admin de su propia institución,
o superadmin) — ver docs/estudiante-nucleo-y-privacidad.md.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from core.database import SessionLocal
import modulos.auth.models  # noqa: F401 — registra auth_usuarios en Base.metadata (FK de AsentimientoInformadoTexto)
import modulos.instituciones.models  # noqa: F401 — registra instituciones en Base.metadata (FK de AsentimientoInformadoTexto)
from modulos.educativo import models

# Texto literal, migrado tal cual desde TEXTO_ASENTIMIENTO_INFORMADO
# (aurora_ui/app/(examen)/examen/[token]/page.tsx) — un párrafo por línea,
# el mismo criterio que el frontend ya usaba para renderizarlos como viñetas.
PARRAFOS = [
    "Vas a responder un cuestionario de tamizaje psicológico, no un examen con notas: no hay respuestas correctas o incorrectas.",
    "Tus respuestas ayudarán al área de psicología de tu institución a conocer cómo te sientes y, si hace falta, ofrecerte apoyo.",
    "Tus respuestas son confidenciales: solo el personal autorizado de psicología de tu institución podrá ver tu informe, y únicamente después de haber sido revisado.",
    "Es voluntario: puedes decidir no participar o dejar de responder en cualquier momento, sin que eso tenga ninguna consecuencia para ti.",
    "Tu padre, madre o apoderado ya autorizó esta evaluación. Lo que marcas aquí es tu propio asentimiento: que TÚ también estás de acuerdo en participar.",
    "Si en algún momento necesitas hablar con alguien, puedes acercarte al área de psicología de tu institución.",
]


def cargar():
    db = SessionLocal()
    try:
        existente = db.query(models.AsentimientoInformadoTexto).filter(
            models.AsentimientoInformadoTexto.institucion_id.is_(None),
            # 🆕 La tabla ahora también guarda modelos de CONSENTIMIENTO del
            # apoderado — sin este filtro, uno global de ese tipo se
            # confundiría con el asentimiento global.
            models.AsentimientoInformadoTexto.tipo_texto == "asentimiento",
            models.AsentimientoInformadoTexto.activo == True,  # noqa: E712
        ).first()
        if existente:
            print(f"↪️  Ya existe una versión global activa (id={existente.id}, v{existente.version}); no se toca.")
            return

        version = models.AsentimientoInformadoTexto(
            institucion_id=None,
            tipo_texto="asentimiento",
            version=1,
            contenido="\n".join(PARRAFOS),
            activo=True,
            creado_por_usuario_id=None,  # migración de contenido, no una acción de un usuario real
        )
        db.add(version)
        db.commit()
        print(f"✅ Texto de asentimiento informado (global, v1) cargado: id={version.id}, "
              f"{len(PARRAFOS)} párrafo(s). Sigue siendo 'sugerido, pendiente de validación "
              "institucional/profesional' — mismo criterio que tenía como constante del frontend.")
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando el texto de asentimiento informado: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    cargar()
