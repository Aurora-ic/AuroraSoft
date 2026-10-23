"""Grupos de roles con nombre — fuente única de verdad.

`core/deps.py` sigue siendo el lugar de `obtener_usuario_actual`/
`verificar_acceso_institucion`/`requerir_rol` (la mecánica de autenticación y
autorización). Este módulo guarda SOLO los grupos de roles que ya aparecían
repetidos a mano, uno por uno, en decenas de endpoints reales — no se
inventa ninguna combinación nueva, se catalogan exactamente las cuatro que
ya existían (inventariadas con `grep -rhoE 'requerir_rol\\([^)]*\\)' modulos/
| sort | uniq -c` antes de escribir esto: 21 + 15 + 11 + 4 ocurrencias).

Ver `PLAN_REMODELACION_ARQUITECTURA.md`, sección 2. El valor real de esto no
es ahorrar caracteres: es que un endpoint nuevo que necesite uno de estos
cuatro tiers IMPORTE el nombre en vez de volver a escribir la tupla de roles
a mano — así `tests/test_matriz_permisos_unitario.py` puede marcar como
fallo cualquier `requerir_rol(...)` con una tupla literal que no sea una de
estas cuatro (ver la comprobación nueva de ese archivo), y una política que
cambia (agregar/quitar un rol de un tier) se edita en un solo lugar.

`STAFF_CLINICO` reutiliza el MISMO objeto que ya exportaba `core.deps.
requerir_staff_clinico` (el único alias que existía antes de esta fase) —
nunca se crea una segunda clausura `requerir_rol("superadmin", "admin",
"psicologo")` distinta para lo mismo. Los otros tres no tenían ningún
nombre todavía.
"""

from core.deps import requerir_rol, requerir_staff_clinico

STAFF_CLINICO = requerir_staff_clinico
SOLO_ADMINISTRATIVO = requerir_rol("superadmin", "admin")
SOLO_SUPERADMIN = requerir_rol("superadmin")
GESTION_EXPEDIENTE = requerir_rol("psicologo", "superadmin")

__all__ = ["STAFF_CLINICO", "SOLO_ADMINISTRATIVO", "SOLO_SUPERADMIN", "GESTION_EXPEDIENTE"]
