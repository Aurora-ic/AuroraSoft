"""Paquete de tests (plain scripts, `python -m tests.<archivo>`).

🆕 (sesión 2026-11-01) Cuenta superadmin DEDICADA a los e2e. Los ~45
`verificar_*_e2e.py` inician sesión con SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD
del .env, pero la contraseña real del superadmin vive en la BD (la BD manda
si se cambió con "Olvidé mi contraseña" — ver seeds/seed_superadmin.py), así
que en cuanto alguien la cambiaba, TODOS los e2e morían en el login.

Si el .env define E2E_SUPERADMIN_EMAIL y E2E_SUPERADMIN_PASSWORD, este
archivo (que Python ejecuta antes que cualquier `tests.<archivo>`) los pone
en SUPERADMIN_EMAIL/SUPERADMIN_PASSWORD del proceso; el `load_dotenv()` de
cada test no los pisa (no sobreescribe variables ya presentes). Ningún test
cambia y el superadmin real deja de ser una dependencia de la suite. La
cuenta se crea con `python -m seeds.seed_superadmin_e2e` (solo con
ENTORNO=development). Sin esas dos variables, todo sigue igual que antes.
"""
import os

from dotenv import load_dotenv

load_dotenv()

_email_e2e = os.getenv("E2E_SUPERADMIN_EMAIL")
_password_e2e = os.getenv("E2E_SUPERADMIN_PASSWORD")
if _email_e2e and _password_e2e:
    os.environ["SUPERADMIN_EMAIL"] = _email_e2e
    os.environ["SUPERADMIN_PASSWORD"] = _password_e2e
