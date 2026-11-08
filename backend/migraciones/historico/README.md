# Migraciones históricas (hasta `4ffd2710409b`)

Las 81 migraciones que construyeron el esquema hasta el 2026-11-07. Desde la
sesión 2026-11-08 las reemplaza **una sola**, `b9d1ee03b2f8`
(`../versions/2026_11_08_1200-b9d1ee03b2f8_esquema_consolidado.py`), que deja
la base exactamente igual: `pg_dump --schema-only` idéntico, comprobado por
`tests/verificar_consolidacion_migraciones.py`.

Alembic **no** carga esta carpeta: solo lee `versions/`. Se conservan para:

- consultar por qué el esquema tiene la forma que tiene (cada archivo explica
  su cambio);
- llevar a `4ffd2710409b` una base que hubiera quedado en una revisión
  intermedia. Con un `alembic.ini` cuyo `version_locations` apunte aquí:
  `alembic upgrade 4ffd2710409b`, y después, ya con el `alembic.ini` normal,
  `alembic stamp --purge b9d1ee03b2f8`.

No agregues migraciones nuevas aquí: van en `versions/` y cuelgan de
`b9d1ee03b2f8`. Detalle en `docs/arquitectura-backend.md` ("Consolidación de
migraciones").
