"""Pruebas unitarias — Ciclo de vida de campaña: editar / cerrar / cancelar.

    python -m tests.test_campanas_ciclo_vida_unitario

Sin BD ni servidor. Cubre: existencia y defaults de las columnas nuevas de
`Evaluacion` (estado/fecha_cierre/cerrada_por_usuario_id/motivo_cierre), el
CHECK de `estado`, las reglas de los schemas (motivo obligatorio solo para
cancelar, ningún schema nuevo acepta institucion_id), y que los tres
endpoints nuevos dependan de `requerir_staff_clinico` (mismo tier de rol que
crear campaña — superadmin/admin/psicólogo, nunca colegio) en vez de un rol
más angosto copiado a mano.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pydantic import ValidationError  # noqa: E402

from modulos.educativo import models, schemas  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columnas_nuevas_de_evaluacion():
    print("\nModelo — Evaluacion: columnas del ciclo de vida")
    tabla = models.Evaluacion.__table__

    estado = tabla.columns["estado"]
    comprobar("estado existe", estado is not None)
    comprobar("estado es NOT NULL", estado.nullable is False)
    comprobar("estado tiene server_default 'activa' (ninguna campaña existente cambia de estado)",
              estado.server_default.arg == "activa")

    for nombre_col in ("fecha_cierre", "cerrada_por_usuario_id", "motivo_cierre"):
        columna = tabla.columns[nombre_col]
        comprobar(f"{nombre_col} existe y es nullable", columna is not None and columna.nullable is True)

    nombres_check = {c.sqltext.text for c in tabla.constraints if c.__class__.__name__ == "CheckConstraint"}
    check_estado = next((t for t in nombres_check if "estado" in t), None)
    comprobar("Existe un CHECK sobre 'estado'", check_estado is not None, str(nombres_check))
    if check_estado:
        for valor in models.ESTADOS_CAMPANA_VALIDOS:
            comprobar(f"El CHECK de 'estado' incluye '{valor}'", valor in check_estado)


def test_activo_no_se_repurpone():
    print("\nModelo — Evaluacion.activo queda intacto (no se repurpona)")
    columna = models.Evaluacion.__table__.columns["activo"]
    comprobar("activo sigue existiendo tal cual (Boolean)", columna.type.python_type is bool)


def test_evaluacion_response_incluye_estado():
    print("\nschemas.EvaluacionResponse — incluye 'estado'")
    comprobar("'estado' está entre los campos del schema", "estado" in schemas.EvaluacionResponse.model_fields)


def test_evaluacion_update_todo_opcional():
    print("\nschemas.EvaluacionUpdate — PATCH parcial, todo opcional")
    vacio = schemas.EvaluacionUpdate()
    comprobar("Se puede instanciar sin ningún campo", vacio.model_dump(exclude_unset=True) == {})

    solo_nombre = schemas.EvaluacionUpdate(nombre_grupo="Nuevo nombre")
    comprobar("exclude_unset solo incluye el campo enviado",
              solo_nombre.model_dump(exclude_unset=True) == {"nombre_grupo": "Nuevo nombre"})

    comprobar("No existe institucion_id en el schema (tenant nunca editable por el cliente)",
              "institucion_id" not in schemas.EvaluacionUpdate.model_fields)


def test_cerrar_motivo_opcional_cancelar_motivo_obligatorio():
    print("\nschemas — motivo opcional al cerrar, obligatorio al cancelar")
    cerrar_sin_motivo = schemas.CerrarCampanaRequest()
    comprobar("CerrarCampanaRequest no exige 'motivo'", cerrar_sin_motivo.motivo is None)

    try:
        schemas.CancelarCampanaRequest()
        fallo_esperado = False
    except ValidationError:
        fallo_esperado = True
    comprobar("CancelarCampanaRequest SÍ exige 'motivo' (ValidationError si se omite)", fallo_esperado)

    try:
        schemas.CancelarCampanaRequest(motivo="ok")  # 2 caracteres: por debajo de min_length=3
        motivo_corto_rechazado = False
    except ValidationError:
        motivo_corto_rechazado = True
    comprobar("CancelarCampanaRequest exige min_length=3 (mismo criterio que ReemitirInformeRequest)",
              motivo_corto_rechazado)

    for esquema in (schemas.CerrarCampanaRequest, schemas.CancelarCampanaRequest):
        comprobar(f"{esquema.__name__} no acepta institucion_id",
                  "institucion_id" not in esquema.model_fields)


def test_endpoints_dependen_de_requerir_staff_clinico():
    print("\nrouter — editar/cerrar/cancelar dependen de requerir_staff_clinico (nunca colegio)")
    fuente = inspect.getsource(__import__("modulos.educativo.router", fromlist=["router"]))

    for nombre_funcion in ("editar_campana", "cerrar_campana", "cancelar_campana"):
        inicio = fuente.index(f"def {nombre_funcion}(")
        fin = fuente.index("\n\n\n", inicio)
        cuerpo = fuente[inicio:fin]
        comprobar(f"{nombre_funcion} depende de requerir_staff_clinico",
                  "Depends(requerir_staff_clinico)" in cuerpo)
        comprobar(f"{nombre_funcion} revalida el tenant contra la fila de BD, no contra el body",
                  "_obtener_campana_de_mi_institucion" in cuerpo)


def test_crud_bloquea_edicion_fuera_de_activa():
    print("\ncrud — actualizar/cerrar/cancelar_campana solo operan sobre estado == 'activa'")
    fuente = inspect.getsource(__import__("modulos.educativo.crud", fromlist=["crud"]))

    for nombre_funcion in ("actualizar_campana", "cerrar_campana", "cancelar_campana"):
        inicio = fuente.index(f"def {nombre_funcion}(")
        fin = fuente.index("\ndef ", inicio + 10)
        cuerpo = fuente[inicio:fin]
        comprobar(f"{nombre_funcion} chequea ESTADO_CAMPANA_ACTIVA antes de mutar nada",
                  "ESTADO_CAMPANA_ACTIVA" in cuerpo)

    inicio_cancelar = fuente.index("def cancelar_campana(")
    fin_cancelar = fuente.index("\ndef ", inicio_cancelar + 10)
    cuerpo_cancelar = fuente[inicio_cancelar:fin_cancelar]
    comprobar("cancelar_campana bloquea si ya hay una Inscripcion 'Finalizado'",
              '"Finalizado"' in cuerpo_cancelar)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Ciclo de vida de campaña (editar/cerrar/cancelar)")
    print("=" * 72)
    test_columnas_nuevas_de_evaluacion()
    test_activo_no_se_repurpone()
    test_evaluacion_response_incluye_estado()
    test_evaluacion_update_todo_opcional()
    test_cerrar_motivo_opcional_cancelar_motivo_obligatorio()
    test_endpoints_dependen_de_requerir_staff_clinico()
    test_crud_bloquea_edicion_fuera_de_activa()

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
