> Parte de `CLAUDE.md`, separada en la fase 8 del plan de remodelación (ver `PLAN_REMODELACION_ARQUITECTURA.md`). Arquitectura general del backend: cómo están organizados los módulos, migraciones, y el historial de la auditoría de concurrencia/lógica.

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


### Migrations: a reproducible chain from an empty database

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

