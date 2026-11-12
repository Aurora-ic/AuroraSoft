"""Paquete de seeds: se ejecuta antes que cualquier `python -m seeds.<x>`.

🆕 (sesión 2026-11-12) Registra TODOS los modelos en Base.metadata, igual que
main.py, antes de que corra el seed. Antes cada seed importaba solo los
modelos que creía necesitar, y SQLAlchemy configura todos los mappers al
primer uso: una clave foránea hacia una tabla de un módulo no importado
rompía el seed. Lo descubrió el ensayo del piloto sobre una base nueva:
seed_asentimiento_informado_default fallaba con NoReferencedTableError
porque `edu_asentimiento_textos.nivel_educativo_id` apunta a
`niveles_educativos` (modulos.superadmin.models), que ese seed no importaba.
"""
from core import models_tareas  # noqa: F401
from modulos.auth import models as _auth  # noqa: F401
from modulos.documentos import models as _documentos  # noqa: F401
from modulos.educativo import models as _educativo  # noqa: F401
from modulos.instituciones import models as _instituciones  # noqa: F401
from modulos.superadmin import models as _superadmin  # noqa: F401
