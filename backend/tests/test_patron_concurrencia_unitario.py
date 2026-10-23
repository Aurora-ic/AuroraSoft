"""Pruebas unitarias — Patrón de concurrencia como convención, no como parche.

    python -m tests.test_patron_concurrencia_unitario

Sin BD: no es un test de comportamiento (eso ya lo cubren los e2e de
concurrencia reales — `verificar_concurrencia_finalizar_e2e.py`, Escenarios
de `verificar_documentos_enganche_automatico_e2e.py`, etc.) sino un **test de
convención**, por inspección de fuente — mismo criterio que
`test_matriz_permisos_unitario.py` ya usa para permisos (ver
`PLAN_REMODELACION_ARQUITECTURA.md`, sección 1.4).

Recorre, con el módulo `ast`, cada función de nivel superior de los
`crud.py` reales (y `importacion_estudiantes.py`) que:

  1. instancia (`Modelo(...)`) al menos un modelo con una restricción de
     unicidad real detrás (`UniqueConstraint`/`Index(unique=True)` en su
     propia definición — parcial o no), Y
  2. hace `db.commit()` ella misma (no un `db.flush()` que delega el commit
     a quien la llama).

Si encuentra una así SIN ninguna de las tres formas de protección que ya
existen en el código real:

  - un `try/except IntegrityError` alrededor (p. ej. `registrar_consentimiento`,
    `otorgar_autorizacion_colegio`),
  - una llamada a `core.concurrencia.commit_o_conflicto` (el helper nuevo de
    esta fase),
  - una llamada a cualquier `bloquear_*`/`_bloquear_*` (el patrón de
    get-or-create-con-lock ya usado por `bloquear_correlativo_para_emision`/
    `_bloquear_o_crear_informe_para_version`/`bloquear_inscripcion_para_*`,
    que resuelve la carrera ANTES del commit, nunca necesita atrapar el
    error después),

...falla, salvo que el sitio esté en `_EXCLUSIONES_REVISADAS` de abajo — cada
entrada ahí fue revisada a mano y su razón documentada, no es una lista para
silenciar hallazgos incómodos. Esto es lo que le faltaba al proyecto: que la
AUSENCIA de este patrón sea un fallo de test, no un descubrimiento posterior
(como lo fueron, uno por uno, los 3+ bugs reales de concurrencia que motivan
este archivo).

Lo que este test NO hace: no decide si una restricción parcial (como
`uq_proceso_promocion_confirmado`, que solo aplica a `estado='confirmado'`)
realmente protege la fila que una función concreta inserta — eso se revisa a
mano una vez (ver `_EXCLUSIONES_REVISADAS`) y queda documentado, no
recalculado en cada corrida.
"""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


MODELOS_FILES = [
    "modulos/auth/models.py",
    "modulos/instituciones/models.py",
    "modulos/superadmin/models.py",
    "modulos/educativo/models.py",
    "modulos/documentos/models.py",
]

CRUD_FILES = [
    "modulos/auth/crud.py",
    "modulos/documentos/crud.py",
    "modulos/educativo/crud.py",
    "modulos/instituciones/crud.py",
    "modulos/superadmin/crud.py",
    "modulos/superadmin/importacion_estudiantes.py",
]

_PATRON_INSTANCIA = re.compile(r"(?:\w*models)\.(\w+)\(")
_PATRON_PROTEGIDO = re.compile(r"bloquear_\w*\(")

# ---------------------------------------------------------------------------
# Exclusiones revisadas a mano — cada una con la razón real por la que el
# hallazgo del escáner no es una carrera explotable, o por qué queda fuera
# del alcance de ESTE test (no de este plan). Clave: "archivo:funcion".
# ---------------------------------------------------------------------------
_EXCLUSIONES_REVISADAS = {
    "modulos/auth/crud.py:crear_token_recuperacion": (
        "TokenRecuperacion.token es secrets.token_urlsafe(32) — una colisión "
        "real es de probabilidad ~2^-256, no la clase de carrera que este "
        "patrón previene (dos escrituras lógicamente iguales compitiendo); "
        "envolverla en try/except sería ruido, no una corrección real."
    ),
    "modulos/superadmin/crud.py:crear_entrada_expediente": (
        "La EntradaExpedienteVersion que crea usa numero_version=1 atado a "
        "entrada.id recién flusheado en la misma función — ningún otro "
        "proceso puede tener una versión previa para un id que no existía "
        "hasta esta llamada, así que uq_expediente_version_entrada_numero "
        "nunca puede chocar aquí. El caso que SÍ puede chocar (agregar una "
        "versión N+1 a una entrada YA existente) es agregar_version_expediente, "
        "que sí está protegida (ver commit_o_conflicto ahí)."
    ),
    "modulos/superadmin/crud.py:iniciar_proceso_promocion": (
        "uq_proceso_promocion_confirmado es un índice único PARCIAL "
        "(postgresql_where=\"estado = 'confirmado'\"); esta función siempre "
        "crea el ProcesoPromocion con estado='borrador', un valor que ese "
        "índice no restringe en absoluto — dos borradores duplicados para "
        "el mismo institución+año_origen+año_destino no violan ninguna "
        "restricción de BD hoy (el precheck es el único candado, igual que "
        "antes de esta fase). Igual para ProcesoPromocionDetalle: su único "
        "campo que importa (proceso_id) es siempre el de un proceso recién "
        "creado en esta misma llamada, nunca uno compartido con otra "
        "transacción. Cerrar la duplicación real de borradores (ampliar el "
        "índice o tomar un lock) es un gap aparte, no el que este test "
        "vigila — ver PLAN_REMODELACION_ARQUITECTURA.md, sección 1."
    ),
}


def _modelos_con_restriccion_unica():
    """{nombre_de_clase: True} para cada modelo con UniqueConstraint o
    Index(unique=True) en su propio __table_args__/columnas — leído de la
    fuente real de models.py, nunca de una lista mantenida a mano."""
    resultado = set()
    for rel in MODELOS_FILES:
        ruta = os.path.join(BACKEND, rel)
        with open(ruta, encoding="utf-8") as f:
            src = f.read()
        arbol = ast.parse(src, filename=ruta)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef):
                segmento = ast.get_source_segment(src, nodo) or ""
                if "UniqueConstraint(" in segmento or "unique=True" in segmento:
                    resultado.add(nodo.name)
    return resultado


def _escanear_commits_sin_proteccion():
    """Devuelve [(clave, modelos_riesgosos)] para cada función de un
    crud.py real que instancia un modelo con restricción única, hace su
    PROPIO db.commit(), y no muestra ninguna de las tres formas de
    protección reconocidas (ver docstring del módulo)."""
    unicos = _modelos_con_restriccion_unica()
    hallazgos = []
    for rel in CRUD_FILES:
        ruta = os.path.join(BACKEND, rel)
        with open(ruta, encoding="utf-8") as f:
            src = f.read()
        arbol = ast.parse(src, filename=ruta)
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segmento = ast.get_source_segment(src, nodo) or ""
            if "db.commit()" not in segmento:
                continue  # no hace su propio commit (delega a quien la llama)
            modelos_instanciados = set(_PATRON_INSTANCIA.findall(segmento))
            modelos_riesgosos = sorted(modelos_instanciados & unicos)
            if not modelos_riesgosos:
                continue
            protegido = (
                "except IntegrityError" in segmento
                or "commit_o_conflicto(" in segmento
                or _PATRON_PROTEGIDO.search(segmento) is not None
            )
            if protegido:
                continue
            hallazgos.append((f"{rel}:{nodo.name}", modelos_riesgosos))
    return hallazgos


def test_sin_commits_desprotegidos_fuera_de_lo_ya_revisado():
    print("\n1 · Funciones de crud.py que instancian un modelo con restricción "
          "única y comitean sin try/except IntegrityError, commit_o_conflicto, "
          "o un bloquear_* previo")
    hallazgos = _escanear_commits_sin_proteccion()
    no_excluidos = [(clave, modelos) for clave, modelos in hallazgos if clave not in _EXCLUSIONES_REVISADAS]
    for clave, modelos in hallazgos:
        marca = "excluido (revisado)" if clave in _EXCLUSIONES_REVISADAS else "SIN REVISAR"
        print(f"      - {clave} -> {modelos} [{marca}]")
    comprobar(
        "ninguna función nueva/no revisada queda sin protección",
        not no_excluidos,
        f"{len(no_excluidos)} hallazgo(s) nuevo(s): {[c for c, _ in no_excluidos]}" if no_excluidos else "",
    )


def test_helpers_de_concurrencia_existen_y_son_los_esperados():
    print("\n2 · core.concurrencia expone bloquear_o_crear y commit_o_conflicto")
    import core.concurrencia as concurrencia
    comprobar(
        "bloquear_o_crear es invocable",
        callable(getattr(concurrencia, "bloquear_o_crear", None)),
    )
    comprobar(
        "commit_o_conflicto es invocable",
        callable(getattr(concurrencia, "commit_o_conflicto", None)),
    )


def test_commit_o_conflicto_traduce_integrity_error_a_409():
    print("\n3 · commit_o_conflicto(db, mensaje) traduce IntegrityError -> HTTPException 409")
    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError
    import core.concurrencia as concurrencia

    class _DBFalsa:
        def __init__(self, fallar):
            self._fallar = fallar
            self.rollback_llamado = False

        def commit(self):
            if self._fallar:
                raise IntegrityError("stmt", {}, Exception("duplicado"))

        def rollback(self):
            self.rollback_llamado = True

    db_ok = _DBFalsa(fallar=False)
    try:
        concurrencia.commit_o_conflicto(db_ok, "no debería fallar")
        ok_pasa_de_largo = True
    except Exception:
        ok_pasa_de_largo = False
    comprobar("sin IntegrityError, no lanza nada", ok_pasa_de_largo)

    db_falla = _DBFalsa(fallar=True)
    lanzo_409 = False
    try:
        concurrencia.commit_o_conflicto(db_falla, "mensaje de prueba")
    except HTTPException as exc:
        lanzo_409 = exc.status_code == 409 and exc.detail == "mensaje de prueba"
    comprobar("con IntegrityError, lanza HTTPException 409 con el mensaje dado", lanzo_409)
    comprobar("y hace rollback antes de lanzar", db_falla.rollback_llamado)


def test_bloquear_o_crear_usa_savepoint_y_recupera_de_la_carrera():
    print("\n4 · bloquear_o_crear: get-or-create con SAVEPOINT, recupera si pierde la carrera")
    from sqlalchemy.exc import IntegrityError
    import core.concurrencia as concurrencia

    class _NestedFalso:
        def __init__(self, fallar):
            self._fallar = fallar
            self.rollback_llamado = False

        def commit(self):
            if self._fallar:
                raise IntegrityError("stmt", {}, Exception("ya existe"))

        def rollback(self):
            self.rollback_llamado = True

    class _DBFalsa:
        def __init__(self, existe_tras_perder_carrera):
            self.added = []
            self._existe_tras_perder_carrera = existe_tras_perder_carrera
            self.nested = None

        def begin_nested(self):
            self.nested = _NestedFalso(fallar=self._existe_tras_perder_carrera)
            return self.nested

        def add(self, obj):
            self.added.append(obj)

    # Caso A: la fila ya existe -> ni siquiera intenta crear.
    db_existe = _DBFalsa(existe_tras_perder_carrera=False)
    fila_existente = object()
    resultado = concurrencia.bloquear_o_crear(
        db_existe, consulta_con_lock=lambda: fila_existente, fabrica=lambda: object(),
    )
    comprobar("si la consulta con lock ya devuelve una fila, no crea nada nuevo", resultado is fila_existente)
    comprobar("y no se tocó db.add", db_existe.added == [])

    # Caso B: no existe, se crea sin problema.
    db_crea = _DBFalsa(existe_tras_perder_carrera=False)
    nueva = object()
    secuencia = iter([None])  # primera consulta: no existe
    resultado = concurrencia.bloquear_o_crear(
        db_crea, consulta_con_lock=lambda: next(secuencia, "no debería volver a consultar"),
        fabrica=lambda: nueva,
    )
    comprobar("si no existe, la crea con fabrica() y la agrega", resultado is nueva and db_crea.added == [nueva])

    # Caso C: no existe, pero pierde la carrera de creación contra otra
    # transacción -> el SAVEPOINT revierte y vuelve a consultar YA con lock,
    # encontrando la fila que ganó la carrera.
    db_pierde = _DBFalsa(existe_tras_perder_carrera=True)
    fila_ganadora = object()
    secuencia = iter([None, fila_ganadora])  # 1ª consulta: no existe; 2ª (tras perder): sí
    resultado = concurrencia.bloquear_o_crear(
        db_pierde, consulta_con_lock=lambda: next(secuencia),
        fabrica=lambda: object(),
    )
    comprobar(
        "si pierde la carrera de creación, recupera la fila de quien ganó en vez de propagar el error",
        resultado is fila_ganadora,
    )
    comprobar("y revirtió el SAVEPOINT antes de volver a consultar", db_pierde.nested.rollback_llamado)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Patrón de concurrencia (convención, no parche)")
    print("=" * 72)
    test_sin_commits_desprotegidos_fuera_de_lo_ya_revisado()
    test_helpers_de_concurrencia_existen_y_son_los_esperados()
    test_commit_o_conflicto_traduce_integrity_error_a_409()
    test_bloquear_o_crear_usa_savepoint_y_recupera_de_la_carrera()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main_tests())
