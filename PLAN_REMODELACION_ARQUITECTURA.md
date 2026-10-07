# Plan de remodelación de arquitectura — AuroraSoft

Documento de diseño, no de implementación. Pensado para ejecutarse en otra sesión (de Claude Code o de un ingeniero humano), fase por fase, sin romper nada de lo que ya funciona. Cada fase es aditiva primero, nunca un "big bang".

**Contexto que motiva esto** (ver análisis crítico completo en la conversación que generó este documento, y `CLAUDE.md` para el detalle de cada subsistema): el núcleo del sistema es sólido (motor de scoring genérico, disciplina multi-tenant, separación informe-psicométrico/documentos-institucionales), pero creció **reactivamente** — cada capacidad se agregó cuando un caso real la exigió, nunca diseñada por adelantado. Eso deja huecos de composición y de verificación sistemática que ya produjeron bugs reales (3 condiciones de carrera + 2 bugs de composición del motor, todos corregidos en la sesión previa a este plan). Este documento cierra esos huecos **como patrón**, no caso por caso.

---

## 0. Principios rectores (para no romper nada)

1. **Aditivo primero, deprecar después.** Ninguna función/símbolo público se renombra ni se borra en la misma fase en que se introduce su reemplazo. Se agrega el reemplazo, se migran los call sites uno por uno (verificando tests en cada uno), y solo al final — en una fase separada — se elimina lo viejo si ya no lo usa nadie.
2. **Una fase, un commit, una verificación completa.** Cada fase de las que siguen termina con: la suite completa de tests unitarios (`tests/test_*_unitario.py`) en verde, al menos un e2e real relevante corrido contra Postgres, y `tsc --noEmit` limpio del lado frontend si la fase tocó `aurora_ui`. Nunca se empieza la fase siguiente con la anterior a medias.
3. **Nunca tocar dos subsistemas no relacionados en la misma fase.** Las fases de abajo están ordenadas por independencia — se puede ejecutar la 1 sin la 2, etc. Si algo bloquea, se puede parar entre fases sin dejar nada roto.
4. **Los tres repos (`/`, `backend/`, `aurora_ui/`) son independientes** (ver `CLAUDE.md` raíz) — cada fase que toque más de uno debe commitear por separado en cada repo, nunca un commit mezclado.
5. **Todo lo nuevo sigue las convenciones ya establecidas del propio código** (español en identificadores/comentarios, el estilo de test ya usado — scripts con `comprobar()`, no pytest —, el estilo de commit ya usado). No se introduce un segundo estilo en paralelo.

---

## 1. Backend — Concurrencia como patrón, no como parche

### 1.1 El problema

Cada condición de carrera encontrada hasta ahora (`InformeVersion` sin lock, `registrar_consentimiento` sin capturar `IntegrityError`, el enganche automático de documentos sin atomicidad real, y antes de esta sesión, el bug ya corregido de `finalizar_examen_seguro`) se corrigió **en el sitio**, con su propia solución ad hoc. No existe ningún lugar del código que diga "así es como se escribe una operación segura contra carreras en este proyecto" — es conocimiento tribal repartido en comentarios de docstring.

### 1.2 Diseño: `backend/core/concurrencia.py` (archivo nuevo)

Dos helpers genéricos, extraídos de los patrones que YA existen y funcionan (`bloquear_correlativo_para_emision` en `modulos/documentos/crud.py`, `_bloquear_o_crear_informe_para_version` en `modulos/educativo/crud.py`) — no se inventa nada nuevo, se generaliza lo que ya se escribió dos veces de forma casi idéntica:

```python
# backend/core/concurrencia.py
from typing import Callable, TypeVar
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

T = TypeVar("T")

def bloquear_o_crear(
    db: Session,
    consulta_con_lock: Callable[[], T | None],   # ej: lambda: db.query(Modelo).filter(...).with_for_update().populate_existing().first()
    fabrica: Callable[[], T],                     # ej: lambda: Modelo(...)
) -> T:
    """Get-or-create con lock de fila, seguro contra la carrera de creación
    (dos transacciones ven "no existe" a la vez). Mismo mecanismo que ya
    usan bloquear_correlativo_para_emision/_bloquear_o_crear_informe_para_version
    — este helper existe para que el PRÓXIMO caso (el que viene) no
    reinvente el mismo SAVEPOINT a mano."""
    fila = consulta_con_lock()
    if fila is not None:
        return fila
    nested = db.begin_nested()
    try:
        nueva = fabrica()
        db.add(nueva)
        nested.commit()
        return nueva
    except IntegrityError:
        nested.rollback()
        fila = consulta_con_lock()
        if fila is None:
            raise  # no debería pasar; si pasa, es un bug real, no lo tragamos
        return fila


def commit_o_conflicto(db: Session, mensaje: str) -> None:
    """db.commit() envuelto en el mismo try/except IntegrityError -> 409
    que ya se repite a mano en crear_documento_institucional,
    vincular_resultado_prueba, registrar_consentimiento, etc. Centraliza
    SOLO la traducción del error — nunca decide si hace falta lock (eso
    lo decide bloquear_o_crear, o un .with_for_update() explícito antes)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=mensaje)
```

### 1.3 Migración (incremental, sin romper nada)

No se tocan las funciones ya corregidas esta sesión (`_bloquear_o_crear_informe_para_version`, `bloquear_correlativo_para_emision`) en esta fase — quedan como están, funcionando. El helper nuevo se usa solo en **código nuevo** a partir de ahora. Opcionalmente, en una fase posterior y separada, se puede reescribir `bloquear_correlativo_para_emision` para que internamente llame a `bloquear_o_crear` (mismo comportamiento, menos código duplicado) — pero eso es limpieza cosmética, no urgente.

Sitios que **sí** conviene auditar con prioridad real (escrituras con un índice único detrás, sin `try/except IntegrityError` todavía, encontrados por `grep -rn "db.commit()" backend/modulos/ backend/core/` y revisando cuáles tienen un `UniqueConstraint`/índice único parcial relevante cerca):
- Cualquier `crear_*` nuevo que toque una tabla con `UniqueConstraint`.
- Revisar en particular `modulos/superadmin/crud.py` (muchas tablas con índices únicos parciales: `MatriculaAcademica`, `ConsentimientoInformado`, `AutorizacionAccesoColegio`) — ya se corrigió `registrar_consentimiento`; **no** se auditó todavía si `matricular_persona_en_seccion` o `otorgar_autorizacion_colegio` tienen el mismo hueco.

### 1.4 Test nuevo: `backend/tests/test_patron_concurrencia_unitario.py`

No es un test de comportamiento (eso ya lo cubren los e2e de concurrencia existentes) sino un **test de convención**, por inspección de fuente — mismo criterio que `test_matriz_permisos_unitario.py` ya usa para permisos: recorre con `inspect.getsource` cada función de `crud.py` que hace `db.add(...)` seguido de `db.commit()` sin pasar por `commit_o_conflicto`, y falla si encuentra una cuyo modelo tiene un `UniqueConstraint`/índice único parcial pero ningún `try/except IntegrityError` alrededor. Esto es lo que le faltaba al proyecto: una forma de que la ausencia de un patrón de seguridad sea un fallo de test, no un descubrimiento posterior.

---

## 2. Backend — Permisos como fuente única de verdad

### 2.1 El problema

`requerir_rol("superadmin", "admin", "psicologo")` (o variaciones) está escrito a mano en decenas de endpoints. `requerir_staff_clinico` es el único alias que existe, y se introdujo recién tras una auditoría que encontró 24+ endpoints donde `colegio` entraba por omisión. El test `test_matriz_permisos_unitario.py` detecta la deriva, pero no la previene — cada endpoint nuevo puede repetir el mismo error hasta que alguien vuelva a auditar.

### 2.2 Diseño: completar `backend/core/permisos.py` (archivo nuevo, separado de `deps.py`)

`core/deps.py` sigue siendo el lugar de `obtener_usuario_actual`/`verificar_acceso_institucion`/`requerir_rol` (la mecánica). `core/permisos.py` es nuevo y guarda **solo** los grupos de roles con nombre, para que nunca más se escriba una tupla de roles suelta en un router:

```python
# backend/core/permisos.py
from core.deps import requerir_rol

# Un nombre por cada combinación de roles que ya aparece repetida en el
# código real — no se inventan combinaciones nuevas, se catalogan las que
# ya existen (grep -rn 'requerir_rol(' backend/modulos/ para el inventario
# exacto antes de escribir esto).
STAFF_CLINICO = requerir_rol("superadmin", "admin", "psicologo")       # = requerir_staff_clinico, ver nota de migración
SOLO_ADMINISTRATIVO = requerir_rol("superadmin", "admin")               # reprocesar, promoción anual, etc.
SOLO_SUPERADMIN = requerir_rol("superadmin")
GESTION_EXPEDIENTE = requerir_rol("psicologo", "superadmin")            # AutorizacionAccesoColegio
```

### 2.3 Migración (sin romper nada)

`requerir_staff_clinico` en `core/deps.py` **no se borra** — se deja como un alias de `permisos.STAFF_CLINICO` (o al revés, lo que sea menos código) para que ningún import existente se rompa. Los endpoints nuevos importan de `core/permisos`; los viejos se migran router por router, en commits separados, cada uno verificado contra `test_matriz_permisos_unitario.py` (que debe seguir pasando sin tocar el JSON esperado, porque el *comportamiento* no cambia, solo de dónde viene la tupla).

**Extensión real al test de matriz** (esto es lo que cierra el hueco de fondo): agregar una comprobación que falle si un endpoint usa `requerir_rol(...)` con una tupla literal en vez de un nombre importado de `core.permisos` — por inspección de fuente, igual que ya hace para otras cosas. Un endpoint nuevo que copie una tupla a mano en vez de importar el nombre correcto, falla el test inmediatamente, no en la próxima auditoría.

---

## 3. Backend — Confiabilidad de tareas en segundo plano

### 3.1 El problema

Toda generación de PDF (informe psicométrico, documento institucional, el enganche automático) corre vía `BackgroundTasks` de FastAPI: in-process, sin reintento, sin cola, visibilidad cero salvo grep de logs. El bug de atomicidad del enganche automático que se corrigió esta sesión es exactamente la clase de falla que este patrón sigue pudiendo producir en cualquier tarea nueva que se agregue de la misma forma.

### 3.2 Diseño — Fase 1 (aditiva, sin cambiar el modelo de ejecución): tabla de registro

Nueva tabla + migración Alembic, **sin tocar el mecanismo de ejecución** (sigue siendo `BackgroundTasks`, cero riesgo de romper el flujo real):

```python
# backend/core/models_tareas.py (o junto a los modelos que ya tiene core/, a definir según convención del proyecto)
class RegistroTareaAsincrona(Base):
    __tablename__ = "registro_tareas_asincronas"
    id = Column(Integer, primary_key=True)
    tipo_tarea = Column(String, nullable=False)       # "generar_informe", "generar_documento_automatico", ...
    referencia_id = Column(Integer, nullable=False)   # inscripcion_id, documento_id, etc. (sin FK -- el tipo decide a qué tabla)
    estado = Column(String, nullable=False, default="en_progreso")  # en_progreso | exito | fallo
    error_detalle = Column(Text, nullable=True)
    iniciado_en = Column(DateTime, nullable=False, server_default=func.now())
    finalizado_en = Column(DateTime, nullable=True)
```

Helper `core/tareas_async.py`:

```python
def ejecutar_tarea_registrada(db_factory, tipo_tarea: str, referencia_id: int, fn: Callable[[Session], None]) -> None:
    """Envuelve CUALQUIER tarea en segundo plano existente (generar_informe,
    generar_documentos_automaticos_por_examen, etc.) con el mismo registro
    antes/después -- se llama DESDE el wrapper que ya existe
    (tarea_generar_informe_en_segundo_plano, etc.), no lo reemplaza."""
    db = db_factory()
    registro = RegistroTareaAsincrona(tipo_tarea=tipo_tarea, referencia_id=referencia_id)
    db.add(registro); db.commit()
    try:
        fn(db)
        registro.estado = "exito"
    except Exception as exc:
        registro.estado = "fallo"
        registro.error_detalle = str(exc)
        raise
    finally:
        registro.finalizado_en = datetime.utcnow()
        db.commit()
        db.close()
```

Cada `tarea_*_en_segundo_plano` existente se migra para llamar esto **por dentro**, sin cambiar su firma externa — `finalizar_examen_seguro`/`generar_documentos_automaticos_por_examen` no se tocan en absoluto.

Con esto, un operador (o un futuro endpoint `GET /admin/tareas-fallidas`) puede ver qué falló sin grepear logs — primer paso real hacia observabilidad, cero riesgo porque no cambia qué se ejecuta ni cuándo.

### 3.3 Fase 2 (futura, opcional, NO parte de este plan todavía)

Migrar de `BackgroundTasks` a una cola real (RQ es lo más simple de introducir dado que el proyecto ya depende de Redis-like infra... si no la tiene, evaluar; Celery si se necesita algo más robusto). Esto es un cambio de infraestructura real (requiere un worker process nuevo, Redis u otro broker) — **no se recomienda hacerlo ahora**, solo dejarlo señalado como la evolución natural una vez que el volumen real lo justifique. La Fase 1 ya da la visibilidad que falta sin ese costo.

---

## 4. Backend — Matriz de combinaciones del motor de scoring

### 4.1 El problema

`modo_calculo` × `tipo_calculo` (items/suma_de_dimensiones/conteo_sintomas) × `criterio_normativo` × `modo_interpretacion` (rango/perfil) × `informante_tipo` son 5 ejes que se cruzan. Cada eje se agregó reactivamente, nunca se probó la combinatoria completa — y ya se encontraron 2 bugs exactamente en cruces no probados (`conteo_sintomas` × `correcto_incorrecto`; anidamiento de `suma_de_dimensiones` en el cálculo real, no solo en el endpoint).

### 4.2 Diseño: `backend/tests/test_matriz_combinaciones_motor_unitario.py`

No hace falta probar las 5 dimensiones completas (el espacio real es mucho más chico porque varios ejes son independientes entre sí). Sí conviene una matriz explícita, documentada como tabla en el propio test, de las combinaciones que **sí interactúan** entre sí según el código real de `core/algoritmo.py`/`calcular_resultados_dimensiones`:

| `modo_calculo` | `tipo_calculo` | ¿Combinación real probada hoy? |
|---|---|---|
| likert_suma | items | Sí (PHQ-9, todo lo demás) |
| likert_suma | conteo_sintomas | Sí (Vanderbilt) |
| likert_suma | suma_de_dimensiones | Sí (SDQ) |
| correcto_incorrecto | items | Sí (aptitud técnica) |
| correcto_incorrecto | conteo_sintomas | **Recién agregado esta sesión** — mantener el test |
| correcto_incorrecto | suma_de_dimensiones | **No probado — agregar** |

Cada fila de la tabla que diga "No probado" se convierte en un caso de test duck-typed (mismo patrón `_FakeDB`/`_FakeQuerySecuencia` ya usado en `test_dimension_compuesta_unitario.py`/`test_conteo_sintomas_unitario.py`) — no contra Postgres, es lógica pura, así que es rápido de escribir y de correr. El valor de este archivo no es solo los tests que ya pasan hoy: es que la próxima vez que se agregue un sexto eje (y se va a agregar — cada instrumento nuevo cargado hasta ahora agregó uno), la tabla se actualiza primero, y los casos nuevos de la tabla fuerzan a pensar la combinación antes de que un seed real la descubra por accidente.

---

## 5. Frontend — Capa de datos

### 5.1 El problema

Cada página repite a mano: `useState` para datos + `useState` para loading + `useState` para error + `useEffect` con `apiClient.get(...).then(...).catch(...).finally(...)`. Sin caché, sin deduplicación, sin revalidación automática. Construimos 4 pantallas nuevas esta sesión siguiendo exactamente este patrón porque es la convención — cada pantalla nueva es más copia-pega, no menos.

### 5.2 Decisión a tomar (bifurcación real, hay que elegir antes de ejecutar esta fase)

**Opción A — recomendada: introducir TanStack Query (`@tanstack/react-query`).** Es una sola dependencia nueva, pequeña, mantenida activamente, resuelve caché/dedup/revalidación/loading-state de una vez. El proyecto hoy solo depende de `next`/`react`/`lucide-react` — agregar esta es la primera dependencia de "lógica", no de UI, así que es una decisión real y vale la pena que el usuario la apruebe explícitamente antes de ejecutar esta fase en la otra sesión.

**Opción B — cero dependencias nuevas: extraer un hook propio.** `aurora_ui/lib/hooks/useApi.ts`:

```ts
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  useEffect(() => {
    if (!path) return;
    setCargando(true);
    apiClient.get<T>(path)
      .then(setDatos)
      .catch((err) => setError(err.message))
      .finally(() => setCargando(false));
  }, deps);
  return { datos, error, cargando };
}
```

Esto no da caché ni dedup, pero elimina la repetición de boilerplate en cada página — menor riesgo, menor beneficio. **Si no hay una preferencia explícita, usar la Opción A** — el costo de una dependencia bien elegida es menor que el costo compuesto de seguir repitiendo el patrón manual en cada pantalla nueva.

### 5.3 Migración (sin romper nada)

Ninguna página existente se reescribe en esta fase. Se agrega el proveedor (`QueryClientProvider` en el layout raíz si es Opción A, o simplemente el archivo del hook si es Opción B), y **solo las páginas nuevas que se escriban de ahora en adelante** lo usan. Las páginas ya escritas (`estudiantes/[personaId]/page.tsx`, las 4 de esta sesión) se migran, si se quiere, en una fase de limpieza posterior y separada — nunca junto con la introducción de la herramienta.

---

## 6. Frontend — Componentes compartidos

`aurora_ui/components/ui/` ya tiene `Boton`/`TextoError`/`Badge`/`DimensionBar`. Faltan los que ya se reescribieron a mano más de una vez:

- `components/ui/Campo.tsx` — el componente `Campo({etiqueta, valor})` que hoy vive declarado localmente DENTRO de `estudiantes/[personaId]/page.tsx` (línea ~107 de ese archivo) y se reutilizaría en la ficha de documentos y en cualquier vista de solo-lectura futura. Extraerlo es un corte-y-pega de una función pura, cero riesgo.
- `components/ui/Tabla.tsx` — la tabla `<table>`+`<thead className="bg-mist/70">`+`<th className="text-xs font-semibold uppercase tracking-wide text-ink/50">` se reescribió igual en `estudiantes/page.tsx`, la sección de contactos de la ficha, `estudiantes/importar/page.tsx`, y el dashboard de campaña que se acaba de construir. Un componente `<Tabla columnas={...} filas={...} />` (o al menos `<TheadFila>`/`<Th>` como sub-componentes) elimina 4+ copias idénticas.
- `components/ui/Select.tsx`/`components/ui/Input.tsx` — las clases `rounded-card border border-border px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400` están pegadas a mano en **todos** los formularios del proyecto (conté 30+ ocurrencias solo en los archivos de esta sesión). Envolver `<input>`/`<select>` una vez no cambia ningún comportamiento, solo deja de repetir la cadena de clases.

Migración: estos componentes se crean nuevos y se adoptan **solo en código nuevo** primero (igual criterio que la Fase 5). Migrar el código ya escrito es cosmético y se hace después, archivo por archivo, verificando visualmente que no cambió nada (son los mismos estilos, solo factorizados).

---

## 7. Sincronización de tipos Frontend/Backend

### 7.1 El problema

`aurora_ui/types/api.ts` se mantiene sincronizado a mano contra `backend/modulos/*/schemas.py`, leyendo el Python y transcribiendo campo por campo. Ya es un archivo de 500+ líneas. No hay ningún acoplamiento en tiempo de compilación entre los dos proyectos.

### 7.2 Diseño: generación automática desde el OpenAPI que FastAPI ya expone

FastAPI ya sirve `/openapi.json` completo y correcto (es lo que alimenta Swagger en `/docs`). Agregar:

```json
// aurora_ui/package.json
"scripts": {
  "generar-tipos": "openapi-typescript http://localhost:8000/openapi.json -o types/api.generated.ts"
}
```

(`openapi-typescript` como devDependency — no corre en producción, solo se ejecuta a mano cuando el backend cambia un schema, con el backend corriendo en local.)

### 7.3 Migración (importante: NO es un reemplazo de golpe)

`types/api.ts` (el archivo a mano) **no se borra**. `types/api.generated.ts` se agrega al lado, y los tipos que ya cambian seguido (los más nuevos — `DocumentoInstitucional*`, los del flujo de examen que se acaban de escribir) son los primeros candidatos a migrar a los generados, porque son los que más se van a desincronizar con el tiempo. Los tipos estables de hace mucho (`Persona`, `ContactoFamiliar`) pueden quedarse a mano indefinidamente si nadie los toca — no hay urgencia real ahí. Esta migración es gradual, módulo por módulo, nunca un solo commit que reemplace las 500 líneas.

---

## 8. Documentación — dividir `CLAUDE.md`

### 8.1 El problema

`CLAUDE.md` (raíz) ya es enorme — cientos de líneas de prosa acumulada sesión tras sesión. Es la memoria de arquitectura más valiosa que tiene el proyecto, pero es un solo archivo que nadie puede leer completo con regularidad, y ya se encontraron dos afirmaciones falsas en él en esta misma sesión (quedaron corregidas).

### 8.2 Diseño: `docs/` en la raíz, `CLAUDE.md` como índice

```
docs/
  motor-scoring.md            # "Scoring engine" + todos los tipo_calculo/modo_interpretacion/criterio_normativo
  motor-documentos.md         # Todo "Motor de documentos institucionales" + enganche automático
  multi-tenancy-y-permisos.md # "Multi-tenancy is the central invariant" + "Permission surface"
  informes-psicometricos.md   # "Informes: Informe/InformeVersion, storage..."
  catalogo-pruebas.md         # "Catálogo de pruebas cargadas" (la sección más larga del archivo)
  frontend.md                 # Todo "Frontend architecture"
```

`CLAUDE.md` queda con: la introducción, "Commands", y un índice con un párrafo de 2-3 líneas por tema enlazando al archivo de `docs/` correspondiente. Cada archivo de `docs/` es autocontenido y lo bastante corto para leerse completo en una sesión.

### 8.3 Migración (mecánica, bajo riesgo, pero hacerla con cuidado)

Es un corte-y-pega de secciones ya escritas, no una reescritura de contenido — el riesgo real no es perder información, es romper los enlaces `[archivo.py](ruta)` relativos al mover texto a una carpeta distinta (hay que ajustar las rutas relativas de `docs/*.md` a `../backend/...` donde hoy decían `backend/...`). Hacerlo en un solo commit dedicado, y verificar después que ningún enlace quedó roto (`grep -rn "](backend/\|](aurora_ui/" docs/` para confirmar cuáles rutas hay que ajustar).

**Alternativa más conservadora, si se prefiere no tocar `CLAUDE.md` todavía**: no dividir nada, solo agregar al principio del archivo una tabla de contenido con anchors (`[Motor de scoring](#scoring-engine)`) para que al menos sea navegable sin dividirlo. Mucho más barato, resuelve menos.

---

## 9. Checklist de cierre — informes psicométricos e individuales/grupales (Cyber)

Esto no es remodelación de arquitectura, es el estado real de negocio que motivó todo lo anterior — para que la próxima sesión no tenga que redescubrirlo:

**Ya cerrado, verificado de punta a punta:**
- Motor de scoring genérico + informe psicométrico fijo — se genera automáticamente al finalizar cualquier examen, para cualquier prueba.
- Motor de documentos institucionales (backend) — `TipoDocumento`/`PlantillaDocumento`/`PlantillaSeccion`, generación/reemisión versionada, enganche automático al finalizar examen.
- Primera pantalla del motor de documentos, embebida en la ficha del alumno — crear, editar `texto_libre`/`grupo_campos`/diagnóstico presuntivo, generar/reemitir, descargar PDF.
- `/pruebas`, `/campanas/nueva`, `/campanas/[id]/dashboard` — catálogo, creación de campaña, matriculación, dashboard, cerrar/cancelar.
- `/examen/[token]` — flujo público completo del alumno, con autoguardado y reanudación.

**Pendiente, con decisión ya tomada (ver conversación previa) pero no ejecutada:**
- Los formatos reales de "Corporación Educativa Cyber" (Huancayo) — individual combinado (psicométrico+entrevista/observación), solo entrevista+observación, pruebas proyectivas, y el formato de informe **grupal** (falta decidir si es `tabla_dinamica` tipo resumen por alumno o `texto_libre` narrativo — pedir el formato real antes de modelar).
- Crear la institución real "Corporación Educativa Cyber" + sus `TipoDocumento`/`PlantillaDocumento` (vía seed script, mismo patrón que `seed_phq9.py` et al. — no hay UI de catálogo todavía, ni la va a haber pronto, es deliberado).

**Pendiente, sin decisión tomada todavía (preguntar antes de ejecutar):**
- Vinculación manual de `resultados_prueba` desde la UI (`PUT/DELETE .../resultados-prueba`) — quedó deliberadamente fuera de la primera pantalla de documentos. Si Cyber necesita combinar resultados de una prueba proyectiva (sin motor de scoring) con un resultado psicométrico real en el mismo documento, esto se vuelve necesario antes de lo esperado.
- Edición de campaña (`PATCH /educativo/campanas/{id}`) y `reprocesar` (`POST /educativo/inscripciones/{id}/reprocesar`) no tienen UI — si el flujo real de Cyber corrige baremos con frecuencia, esto sube de prioridad.

---

## 10. Orden de ejecución recomendado

Pensado para que cada fase sea un punto seguro de parada — ninguna depende de que la siguiente se termine:

1. **Fase 1** (concurrencia) y **Fase 4** (matriz de combinaciones) primero — son las que previenen la próxima clase de bug real, cero riesgo de romper nada visible al usuario.
2. **Fase 2** (permisos) — igual de bajo riesgo, se beneficia de hacerse mientras el código de la Fase 1 todavía está fresco en memoria (mismo tipo de refactor mecánico).
3. **Fase 3** (registro de tareas) — aditiva pura, se puede hacer en cualquier momento, no bloquea ni bloquea a nada.
4. **Decisión del usuario** antes de la Fase 5 (TanStack Query vs. hook propio) — no ejecutar esa fase sin esa decisión tomada explícitamente.
5. **Fases 5 y 6** (frontend: capa de datos + componentes) juntas, porque los componentes nuevos se diseñan mejor sabiendo si hay React Query debajo o no.
6. **Fase 7** (tipos generados) — independiente, se puede hacer en paralelo con cualquier otra.
7. **Fase 8** (dividir CLAUDE.md) — la de menor urgencia técnica, hacerla último o delegarla a un momento de menor carga.
8. **Sección 9** (checklist de Cyber) — no es arquitectura, corre en paralelo con todo lo anterior apenas lleguen los formatos reales.
