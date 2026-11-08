> Parte de `CLAUDE.md`, separada en la fase 8 del plan de remodelación de arquitectura (ver [docs/gaps-pendientes.md](gaps-pendientes.md) para los principios que la guiaron). Arquitectura general del backend: cómo están organizados los módulos, migraciones, y el historial de la auditoría de concurrencia/lógica.

## Backend architecture

`main.py` wires five module routers under `/api`; each module owns its own `models.py` / `schemas.py` / `crud.py` / `router.py` and the router carries its own prefix, so the full path is the mount prefix plus the router prefix:

| Module | Full prefix | Owns |
| --- | --- | --- |
| `modulos/auth` | `/api/auth` | `Usuario` (the only user table), password reset tokens, login |
| `modulos/instituciones` | `/api/instituciones` | `Institucion` — the tenant; licence flags and per-tenant limits |
| `modulos/superadmin` | `/api/personas` | `Persona` (students), the academic structure (`NivelEducativo`/`Grado`/`Seccion`/`MatriculaAcademica`), informed consent (+ its audit trail), ARCO anonymization, scheduled appointments, the clinical expediente timeline, `PersonaDatosFamiliares`/`PersonaAntecedentesClinicos` |
| `modulos/educativo` | `/api/educativo` | tests, dimensions, questions, baremos, campaigns, enrolments, answers, diagnoses, dashboards, follow-up sessions |
| `modulos/documentos` | `/api/documentos` | the institutional-document engine — `TipoDocumento`/`PlantillaDocumento` catalog, `DocumentoInstitucional` and its versions (see "Motor de documentos institucionales" below); also owns `modulos/documentos/pdf_generador.py`, its own PDF renderer, independent of `core/pdf_generator.py` |

Note the mismatch: `superadmin_router` is mounted at `/api/admin` in `main.py` but its own prefix is `/personas`, so persona endpoints live at `/api/admin/personas/...`. `modulos/{clinico,organizacional,seleccion}` are empty placeholders for future verticals.

`main.py` calls `load_dotenv()` as its very first import-time action, before anything reads an environment variable (including Sentry's `SENTRY_DSN`, read a few lines later) — if you add a new top-of-file `os.getenv(...)` in `main.py` or `migraciones/env.py`, it now works from the first line; before this fix it silently read `None` for anything checked ahead of the `core.database` import, which is where `load_dotenv()` used to run as a side effect.


### 🆕 Consolidación de migraciones: una sola base `b9d1ee03b2f8` (sesión 2026-11-08)

Las 81 migraciones (de `0a1b2c3d4e5f` a `4ffd2710409b`) se reemplazaron por **una sola**, `b9d1ee03b2f8` ([migraciones/versions/2026_11_08_1200-b9d1ee03b2f8_esquema_consolidado.py](../backend/migraciones/versions/2026_11_08_1200-b9d1ee03b2f8_esquema_consolidado.py), `down_revision=None`). Una base vacía llega al esquema completo con `alembic upgrade head` en unos 2 s.

- **Cómo se generó.** No desde los modelos, sino reflejando una base construida con la cadena vieja desde cero. Así conserva lo que los modelos no expresan: el orden físico de las columnas, los nombres reales de restricciones e índices, los 10 índices parciales, las 55 secuencias SERIAL y los 47 `CHECK`. Los `CHECK` salen del texto exacto de `pg_get_constraintdef`, porque la reflexión de SQLAlchemy les quita el primer y el último paréntesis. Los de lista se devuelven a la forma `col IN (...)`: si se le da a PostgreSQL la forma expandida `ANY (ARRAY[...])`, la guarda distinta. Las tres migraciones viejas que tocaban datos solo hacían `UPDATE` de relleno sobre filas existentes y en una base nueva no tienen efecto.
- **Equivalencia comprobada.** `pg_dump --schema-only` de una base hecha con la cadena vieja y de una hecha con la consolidada: 1.909 líneas idénticas, y `comparar_esquemas` sin diferencias. Lo mismo contra el esquema **real** de la base de desarrollo en Neon (solo lectura). `alembic check` sin deriva respecto de los modelos.
- **Las migraciones viejas** se conservan en [migraciones/historico/](../backend/migraciones/historico/). Alembic no las carga, porque no están en `versions/`. Solo sirven para llevar a `4ffd2710409b` una base que estuviera en una revisión intermedia, con un `alembic.ini` que apunte `version_locations` a esa carpeta; después se marca como abajo.
- **Base que ya existía** (en `4ffd2710409b`, con el esquema completo): no se le aplica nada, solo se marca:

  ```bash
  alembic stamp --purge b9d1ee03b2f8
  ```

  `--purge` borra la fila de `alembic_version` que apunta a `4ffd2710409b`, que ya no existe en `versions/`; sin él, Alembic no la reconoce. No toca el esquema ni los datos.
- **Verificación:** `tests/verificar_consolidacion_migraciones.py` trabaja en bases temporales `zz_mig_*` de un servidor PostgreSQL distinto del de la aplicación (`ZZ_MIG_SERVIDOR_URL`, se niega si apunta al mismo) y necesita `pg_dump`/`pg_restore` 16 (`PG_BIN`). Prueba la cadena vieja, la consolidada, su igualdad, `downgrade base`/`upgrade head` y el camino `stamp --purge` sobre una **copia desechable** de la base real, sacada con `pg_dump` (solo lectura): queda en la revisión nueva, `upgrade head` no hace nada, `alembic check` sin deriva, mismo esquema y mismas filas. Resultado: 22/22. La copia se compara con una referencia que pasó por el mismo `pg_dump`/`pg_restore`, porque al restaurar PostgreSQL reescribe la forma de los `CHECK` de lista.
- **Retirado:** `tests/verificar_fase3_migraciones.py`, que probaba migraciones concretas de la cadena vieja (rellenos NOT NULL, la guarda de `personas.institucion_id`, huérfanos de C-16) y clonaba la base de la aplicación con `CREATE DATABASE … TEMPLATE`, cortando sus conexiones. Su garantía central, que una instalación nueva es igual a una existente, la cubre la verificación nueva.
- **Desde ahora**, una migración nueva va como siempre (`alembic revision --autogenerate -m "..."`) y cuelga de `b9d1ee03b2f8`.

### Migrations: a reproducible chain from an empty database (histórico, reemplazado por la consolidación de arriba)

The chain now starts from `0a1b2c3d4e5f` (`down_revision=None`), which builds the schema as it stood before Alembic was introduced — including tables the very next migration drops. A completely empty PostgreSQL database reaches `head` with a plain `alembic upgrade head`, and `alembic check` reports no drift against the models; `tests/comparar_esquemas.py` goes further and confirms a from-scratch install is column-for-column, FK-name-for-FK-name, index-for-index identical to a real migrated database. An existing, already-migrated database is unaffected — it's already past `0a1b2c3d4e5f`'s revision point and never runs it. The one thing that does **not** go through this chain is a database created by `crear_tablas.py`/`create_all()`: stamp it (`alembic stamp head`), don't upgrade it.


### Auditoría posterior: ocho bugs reales de concurrencia/lógica, todos cerrados

Una auditoría dedicada (cinco agentes en paralelo sobre motor de scoring, ciclo de examen/reproceso, módulo superadmin, motor de documentos y seguridad transversal) no encontró ningún bypass de auth ni fuga cross-tenant, pero sí ocho bugs reales — todos corregidos, verificados con 36/36 archivos de tests unitarios (sin regresiones, +7 casos nuevos) y 9 tests e2e reales contra Postgres:

- **`InformeVersion` se generaba sin lock de fila** (`generar_y_almacenar_informe`/`modulos/educativo/crud.py`) — dos llamadas casi simultáneas (doble clic en "Reemitir informe", o una reemisión coincidiendo con la tarea automática post-`/finalizar`) podían calcular el mismo `numero_version+1` y chocar sin manejo contra `uq_edu_informe_versiones_numero`. Cerrado con `_bloquear_o_crear_informe_para_version` — mismo patrón de lock+SAVEPOINT que `bloquear_correlativo_para_emision` ya usaba en `documentos`.
- **`registrar_consentimiento` no capturaba la carrera concurrente** (`modulos/superadmin/crud.py`) — el chequeo previo solo cerraba la ventana secuencial; dos registros simultáneos para la misma persona+tipo producían un `IntegrityError` crudo (500) en vez del 409 explicado que ya existía para el caso secuencial. Cerrado con `try/except IntegrityError` alrededor del commit.
- **El enganche automático de documentos no era realmente atómico** (`modulos/documentos/crud.py`) — `crear_documento_institucional`/`vincular_resultado_prueba`/`generar_version_documento` hacían cada uno su propio commit, pese a que `_generar_documento_automatico_de_plantilla` prometía en su docstring un rollback conjunto. Cerrado con el parámetro `commit: bool` (mismo patrón que `matricular_persona_en_seccion` en la importación Excel) — ahora los tres pasos viven en una sola transacción real.
- **`calcular_correcto_incorrecto` ignoraba `dimensiones_conteo`** (`core/algoritmo.py`) — una `Dimension.tipo_calculo='conteo_sintomas'` dentro de una `Prueba.modo_calculo='correcto_incorrecto'` sumaba en vez de contar, en silencio (sin impacto hoy porque ningún seed carga esa combinación).
- **El guard de anidamiento de dimensiones compuestas solo vivía en el endpoint de escritura**, nunca en el cálculo real (`calcular_resultados_dimensiones`) — un `DimensionComponente` anidado insertado por fuera de `reemplazar_componentes_de_dimension` contribuía 0 en silencio. Ahora se detecta, se excluye del cálculo y se deja constancia en el log.
- **`confirmar_proceso_promocion`**: el `flush()` del bucle de escritura quedaba fuera del `try/except` que solo protegía el commit final — una ventana de carrera real entre dos borradores de promoción concurrentes para el mismo alumno. También se agregó la revalidación de `seccion_definitiva.activo`, que antes no se chequeaba.
- **`aplicar_importacion` propagaba `IntegrityError` crudo** ante una colisión real entre `/validar` y `/confirmar` — ahora se traduce a un 409 legible, mismo patrón que `crear_documento_institucional`.
- **El candado de `fecha_fin` de campaña estaba pegado a mano en 8 sitios** — centralizado en `crud.campana_esta_expirada()`.

