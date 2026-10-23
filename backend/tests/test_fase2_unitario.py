"""Pruebas unitarias de la Fase 2 — integridad, tenencia y privacidad.

    python tests/test_fase2_unitario.py

Incluye la prueba del import circular, que debe poder ejecutarse SIN el
preámbulo de `import modulos.superadmin.crud` que necesitaba la Fase 1.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 👇 Import directo, sin preparar el orden: si el ciclo volviera, esto falla.
from modulos.educativo import crud as edu_crud, models as edu_models  # noqa: E402
from modulos.superadmin import crud as sa_crud, models as sa_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ======================================================================
def test_import_circular():
    print("\nImport circular · cualquier módulo debe poder cargarse primero")

    # Cada módulo en su propio intérprete: así se comprueba el orden de carga
    # de verdad, sin que sys.modules arrastre lo ya importado por este test.
    for modulo in (
        "modulos.educativo.crud",
        "modulos.superadmin.crud",
        "modulos.educativo.router",
        "modulos.superadmin.router",
    ):
        proceso = subprocess.run(
            [sys.executable, "-c", f"import {modulo}"],
            cwd=RAIZ, capture_output=True, text=True,
            env={**os.environ, "SECRET_KEY": "x", "DATABASE_URL": "postgresql://x/y"},
        )
        comprobar(
            f"`import {modulo}` funciona en solitario",
            proceso.returncode == 0,
            (proceso.stderr.strip().splitlines() or [""])[-1][:110],
        )

    # Se analiza el AST, no el texto: los comentarios que documentan la forma
    # antigua no deben contar como si fuera código vivo.
    import ast
    import inspect

    arbol = ast.parse(inspect.getsource(sa_crud))
    importa_modulo = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "modulos.educativo"
        and any(a.name == "crud" for a in n.names)
        for n in ast.walk(arbol)
    )
    importa_nombre_suelto = any(
        isinstance(n, ast.ImportFrom) and n.module == "modulos.educativo.crud"
        for n in ast.walk(arbol)
    )
    comprobar(
        "superadmin.crud enlaza el MÓDULO educativo.crud, no un nombre suelto",
        importa_modulo and not importa_nombre_suelto,
        f"módulo={importa_modulo} nombre_suelto={importa_nombre_suelto}",
    )


# ======================================================================
def test_b7_integridad_respuestas():
    print("\nB-7 · Integridad de respuestas del examen")

    import inspect
    fuente = inspect.getsource(edu_crud.guardar_respuestas_examen)

    comprobar("Existe el constructor de la lista blanca por prueba",
              callable(getattr(edu_crud, "obtener_pares_validos_de_prueba", None)))
    comprobar("La prueba se resuelve desde la inscripción, no del cliente",
              "inscripcion.evaluacion_id" in fuente and "evaluacion.prueba_id" in fuente)
    comprobar("Se valida el par (pregunta, opción) completo",
              "(r.pregunta_id, r.opcion_id) not in pares_validos" in fuente)
    comprobar("La validación ocurre ANTES del DELETE (atomicidad)",
              fuente.index("pares_validos") < fuente.index(".delete("))
    comprobar("Se rechazan dos respuestas para la misma pregunta", "vistos" in fuente)
    comprobar("Hay rollback explícito del lote completo", "db.rollback()" in fuente)
    comprobar("El puntaje se relee de la BD, nunca del cliente",
              "pares_validos[(r.pregunta_id, r.opcion_id)]" in fuente)


# ======================================================================
def test_b8_consentimiento_cruzado():
    print("\nB-8 · Consentimiento acotado a institución")

    import ast
    import inspect
    import textwrap

    fuente = inspect.getsource(sa_crud.registrar_consentimiento)
    comprobar("registrar_consentimiento recibe la persona ya validada",
              "persona" in inspect.signature(sa_crud.registrar_consentimiento).parameters)

    # De nuevo por AST: el docstring de la función MENCIONA datos.persona_id
    # para explicar el fallo antiguo, y no debe confundirse con código vivo.
    arbol = ast.parse(textwrap.dedent(fuente))
    kwargs_modelo = {}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) \
                and nodo.func.attr == "ConsentimientoInformado":
            kwargs_modelo = {kw.arg: ast.unparse(kw.value) for kw in nodo.keywords}

    comprobar("Escribe persona_id del recurso, no del body",
              kwargs_modelo.get("persona_id") == "persona.id",
              f"persona_id={kwargs_modelo.get('persona_id')}")
    comprobar("Escribe institucion_id del recurso, no del body",
              kwargs_modelo.get("institucion_id") == "persona.institucion_id",
              f"institucion_id={kwargs_modelo.get('institucion_id')}")

    firma = inspect.signature(sa_crud.tiene_consentimiento_vigente)
    comprobar("tiene_consentimiento_vigente acepta institucion_id",
              "institucion_id" in firma.parameters)
    comprobar("Existe el helper acotado para inscripciones",
              callable(getattr(edu_crud, "consentimiento_vigente_para_inscripcion", None)))

    fuente_router = inspect.getsource(
        __import__("modulos.educativo.router", fromlist=["router"])
    )
    comprobar("Ningún punto del examen comprueba el consentimiento sin institución",
              "tiene_consentimiento_vigente(db, inscripcion" not in fuente_router)


# ======================================================================
def test_b11_auditoria_consentimiento():
    print("\nB-11 · Auditoría del consentimiento")

    for columna in ("ip_registro", "revocado_por_usuario_id", "ip_revocacion",
                    "fecha_otorgamiento", "fecha_revocacion", "revocado",
                    "otorgado_por_nombre", "tipo_otorgante", "registrado_por_usuario_id"):
        comprobar(f"ConsentimientoInformado registra '{columna}'",
                  hasattr(sa_models.ConsentimientoInformado, columna))

    import inspect
    fuente = inspect.getsource(edu_crud.validar_y_registrar_alumno)
    # 🆕 PLAN_REMODELACION_ARQUITECTURA.md / docs/gaps-pendientes.md — este
    # sitio ya no usa datetime.utcnow() (deprecado), sino el equivalente
    # datetime.now(timezone.utc); mismo comportamiento, misma columna naive.
    comprobar("La aceptación del alumno guarda la fecha",
              "inscripcion.fecha_asentimiento = datetime.now(timezone.utc)" in fuente)
    comprobar("La aceptación del alumno guarda la IP",
              "inscripcion.ip_asentimiento = ip_asentimiento" in fuente)
    comprobar("No se pisa el evento original si vuelve a pasar",
              "if not inscripcion.acepto_asentimiento:" in fuente)

    fuente_rev = inspect.getsource(sa_crud.revocar_consentimiento_de_persona)
    comprobar("La revocación alcanza a TODOS los vigentes, no solo al primero",
              ".all()" in fuente_rev and "for consentimiento in vigentes" in fuente_rev)
    comprobar("La revocación no borra: conserva el historial",
              "db.delete" not in fuente_rev)
    comprobar("Existe la consulta de historial completo",
              callable(getattr(sa_crud, "historial_consentimientos", None)))

    from core.deps import ip_del_cliente
    comprobar("El helper de IP existe y es compartido", callable(ip_del_cliente))


# ======================================================================
def test_b12_arco():
    print("\nB-12 · Anonimización ARCO")

    comprobar("Existe la bitácora RegistroAuditoriaArco",
              hasattr(sa_models, "RegistroAuditoriaArco"))
    for columna in ("accion", "persona_id", "inscripcion_id", "institucion_id",
                    "ejecutado_por_usuario_id", "rol_ejecutor", "fecha",
                    "ip_solicitante", "detalle"):
        comprobar(f"La bitácora registra '{columna}'",
                  hasattr(sa_models.RegistroAuditoriaArco, columna))

    import inspect
    fuente_edu = inspect.getsource(
        __import__("modulos.educativo.router", fromlist=["router"])
    )
    fuente_sa = inspect.getsource(
        __import__("modulos.superadmin.router", fromlist=["router"])
    )
    # 🆕 PLAN_REMODELACION_ARQUITECTURA.md, fase 2 — estos routers ya no
    # escriben la tupla de roles a mano: importan el nombre canónico de
    # core.permisos (misma tupla real, solo que declarada una sola vez).
    comprobar("Anonimizar inscripción exige rol superadmin/admin",
              "permisos.SOLO_ADMINISTRATIVO" in fuente_edu)
    comprobar("Anonimizar persona exige rol superadmin/admin",
              "permisos.SOLO_ADMINISTRATIVO" in fuente_sa)
    comprobar("El soft-delete deja fuera a la cuenta genérica 'colegio'",
              "permisos.STAFF_CLINICO" in fuente_edu)

    fuente_anon = inspect.getsource(sa_crud.anonimizar_persona_arco)
    comprobar("Se audita ANTES de perder los datos",
              fuente_anon.index("registrar_auditoria_arco")
              < fuente_anon.index('persona.nombres = "ANONIMO"'))
    comprobar("Sigue sin ser un borrado físico", "db.delete" not in fuente_anon)


# ======================================================================
def test_c7_c15_restricciones():
    print("\nC-7 y C-15 · Restricciones de unicidad")

    restricciones_persona = {
        c.name: sorted(col.name for col in c.columns)
        for c in sa_models.Persona.__table__.constraints if hasattr(c, "columns")
    }
    comprobar("Persona: unicidad compuesta institución+documento",
              restricciones_persona.get("uq_personas_institucion_documento")
              == ["documento_identidad", "institucion_id"],
              str(restricciones_persona.get("uq_personas_institucion_documento")))
    comprobar("Persona: el documento ya NO es único global",
              sa_models.Persona.__table__.c.documento_identidad.unique is not True)

    restricciones_insc = {
        c.name: sorted(col.name for col in c.columns)
        for c in edu_models.Inscripcion.__table__.constraints if hasattr(c, "columns")
    }
    comprobar("Inscripción: unicidad campaña+persona",
              restricciones_insc.get("uq_edu_inscripciones_evaluacion_persona")
              == ["evaluacion_id", "persona_id"],
              str(restricciones_insc.get("uq_edu_inscripciones_evaluacion_persona")))


# ======================================================================
def test_c8_registros_dados_de_baja():
    print("\nC-8 · Registros eliminados y anonimizados")

    import inspect
    fuente_ficha = inspect.getsource(sa_crud.obtener_ficha_completa)
    comprobar("La ficha excluye inscripciones eliminadas",
              "Inscripcion.is_deleted == False" in fuente_ficha)
    comprobar("La ficha excluye inscripciones anonimizadas",
              "Inscripcion.is_anonymized == False" in fuente_ficha)

    fuente_padron = inspect.getsource(sa_crud.obtener_personas_por_institucion)
    comprobar("El padrón excluye personas inactivas por defecto",
              "incluir_inactivas" in fuente_padron and "Persona.activo == True" in fuente_padron)

    comprobar("Existe la guarda de inscripción activa",
              callable(getattr(edu_crud, "inscripcion_esta_activa", None)))

    class Falsa:
        is_deleted = False
        is_anonymized = False
    activa = Falsa()
    comprobar("Una inscripción normal se considera activa",
              edu_crud.inscripcion_esta_activa(activa) is True)
    activa.is_deleted = True
    comprobar("Una eliminada deja de estar activa",
              edu_crud.inscripcion_esta_activa(activa) is False)
    activa.is_deleted, activa.is_anonymized = False, True
    comprobar("Una anonimizada deja de estar activa",
              edu_crud.inscripcion_esta_activa(activa) is False)

    fuente_router = inspect.getsource(
        __import__("modulos.educativo.router", fromlist=["router"])
    )
    comprobar("Los endpoints del examen aplican la guarda",
              fuente_router.count("inscripcion_esta_activa") >= 7,
              f"{fuente_router.count('inscripcion_esta_activa')} puntos")

    fuente_limite = inspect.getsource(edu_crud.puede_aplicar_prueba)
    comprobar("Una inscripción dada de baja no consume cupo mensual",
              "is_deleted == False" in fuente_limite)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — FASE 2")
    print("=" * 72)

    test_import_circular()
    test_b7_integridad_respuestas()
    test_b8_consentimiento_cruzado()
    test_b11_auditoria_consentimiento()
    test_b12_arco()
    test_c7_c15_restricciones()
    test_c8_registros_dados_de_baja()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    if fallos:
        print("Fallan:")
        for nombre in fallos:
            print(f"  - {nombre}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
