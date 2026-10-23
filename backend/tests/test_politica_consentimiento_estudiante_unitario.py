"""Pruebas unitarias — Institucion.exigir_asentimiento_estudiante (política
institucional de consentimientos).

    python -m tests.test_politica_consentimiento_estudiante_unitario

Sin BD ni servidor. Cubre: la columna existe con default False (cero cambio
para instituciones existentes), el schema de respuesta refleja ese default,
el request del nuevo endpoint exige el campo explícitamente, el endpoint
está gateado a superadmin/admin (nunca psicologo/colegio), y — por
inspección de código, sin ejecutar nada contra una BD real — que las dos
funciones que deben leer el flag (`matricular_roster_en_campana` y
`consentimiento_vigente_para_inscripcion`) efectivamente lo hacen, y que la
institución se carga UNA sola vez antes del bucle de alumnos (no un N+1).
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pydantic import ValidationError  # noqa: E402

from modulos.instituciones import models, schemas  # noqa: E402
from modulos.educativo import crud as educativo_crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columna_existe_con_default_false():
    print("\nModelo — Institucion.exigir_asentimiento_estudiante existe, NOT NULL, default False")
    columna = models.Institucion.__table__.columns["exigir_asentimiento_estudiante"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es NOT NULL", columna.nullable is False)
    comprobar("Su server_default es 'false' (ninguna institución existente cambia de comportamiento)",
              columna.server_default.arg == "false")


def test_schema_response_default_false():
    print("\nschemas.InstitucionResponse — exigir_asentimiento_estudiante por defecto es False")
    respuesta = schemas.InstitucionResponse(
        id=1, nombre="Colegio X", fecha_registro="2026-01-01T00:00:00",
        plan_activo=True, limite_pruebas_mensual_por_alumno=5,
    )
    comprobar("El default del schema de respuesta es False", respuesta.exigir_asentimiento_estudiante is False)


def test_request_exige_el_campo_explicitamente():
    print("\nschemas.PoliticaConsentimientosRequest — exige el campo, sin default implícito")
    try:
        schemas.PoliticaConsentimientosRequest()
        comprobar("Sin el campo, el schema rechaza (ValidationError)", False)
    except ValidationError:
        comprobar("Sin el campo, el schema rechaza (ValidationError)", True)

    activado = schemas.PoliticaConsentimientosRequest(exigir_asentimiento_estudiante=True)
    comprobar("Acepta True explícito", activado.exigir_asentimiento_estudiante is True)
    desactivado = schemas.PoliticaConsentimientosRequest(exigir_asentimiento_estudiante=False)
    comprobar("Acepta False explícito", desactivado.exigir_asentimiento_estudiante is False)


def test_endpoint_gateado_a_superadmin_y_admin():
    print("\nEndpoint PATCH /instituciones/{id}/politica-consentimientos — solo superadmin/admin")
    import main  # noqa: E402 (import tardío: dispara la carga completa de la app)
    from fastapi.routing import APIRoute

    ruta = None
    for route in main.app.routes:
        if isinstance(route, APIRoute) and route.path == "/api/instituciones/{institucion_id}/politica-consentimientos":
            ruta = route
            break
    comprobar("La ruta existe", ruta is not None)
    if ruta is None:
        return

    llamada_rol = None
    for d in ruta.dependant.dependencies:
        if getattr(d.call, "__qualname__", "") == "requerir_rol.<locals>.verificador":
            llamada_rol = d.call
            break
    comprobar("El endpoint usa Depends(requerir_rol(...))", llamada_rol is not None)
    if llamada_rol is not None:
        roles = set(llamada_rol.__closure__[0].cell_contents)
        comprobar("Los roles permitidos son EXACTAMENTE {superadmin, admin}", roles == {"superadmin", "admin"},
                  f"roles={roles}")


def test_matricular_roster_lee_el_flag_una_sola_vez_antes_del_bucle():
    print("\nmatricular_roster_en_campana — lee el flag antes del bucle de alumnos (nunca dentro, para evitar N+1)")
    fuente = inspect.getsource(educativo_crud.matricular_roster_en_campana)
    comprobar("La función referencia exigir_asentimiento_estudiante", "exigir_asentimiento_estudiante" in fuente)

    pos_bucle = fuente.index("for pid in persona_ids:")
    pos_flag = fuente.index("exigir_asentimiento_estudiante")
    comprobar("El flag se lee ANTES del 'for pid in persona_ids' (una sola carga, no una por alumno)",
              pos_flag < pos_bucle, f"pos_flag={pos_flag}, pos_bucle={pos_bucle}")

    cuerpo_bucle = fuente[pos_bucle:]
    comprobar("Dentro del bucle solo se LEE la variable ya cargada, no se vuelve a consultar Institucion",
              "db.query(inst_models.Institucion)" not in cuerpo_bucle)
    comprobar("El motivo de rechazo del nuevo candado está presente",
              "Sin asentimiento del propio estudiante vigente." in fuente)


def test_consentimiento_vigente_para_inscripcion_lee_el_flag():
    print("\nconsentimiento_vigente_para_inscripcion — lee el flag DESPUÉS de exigir siempre el consentimiento del apoderado")
    fuente = inspect.getsource(educativo_crud.consentimiento_vigente_para_inscripcion)
    comprobar("La función referencia exigir_asentimiento_estudiante", "exigir_asentimiento_estudiante" in fuente)
    comprobar("Los links anónimos (persona_id None) siguen retornando True de inmediato, sin tocar el flag",
              "if not inscripcion.persona_id:\n        return True" in fuente)

    pos_apoderado = fuente.index("superadmin_crud.tiene_consentimiento_vigente(db, inscripcion.persona_id, institucion_id)")
    # Se busca la línea de CÓDIGO real (no la mención en el docstring, que
    # explica el comportamiento antes de mostrarlo) — el `if` que de verdad
    # lee el flag para decidir si exige también el consentimiento del
    # estudiante.
    pos_flag = fuente.index("if institucion and institucion.exigir_asentimiento_estudiante:")
    comprobar("El chequeo de apoderado sigue siendo el primero (nunca se salta aunque el flag esté activo)",
              pos_apoderado < pos_flag)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Institucion.exigir_asentimiento_estudiante")
    print("=" * 72)
    test_columna_existe_con_default_false()
    test_schema_response_default_false()
    test_request_exige_el_campo_explicitamente()
    test_endpoint_gateado_a_superadmin_y_admin()
    test_matricular_roster_lee_el_flag_una_sola_vez_antes_del_bucle()
    test_consentimiento_vigente_para_inscripcion_lee_el_flag()

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
