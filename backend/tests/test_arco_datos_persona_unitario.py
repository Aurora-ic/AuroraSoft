"""Pruebas unitarias — ARCO: derecho de acceso (exportar-datos-arco) y
rectificación con trazabilidad (referencia_solicitud_arco en el PATCH de
Persona).

    python -m tests.test_arco_datos_persona_unitario

Sin BD ni servidor. Cubre, por inspección de código y de la app montada
(nunca ejecutando contra una BD real, eso lo hace
verificar_arco_datos_persona_e2e.py):

  - El endpoint de acceso nunca deja pasar a 'colegio' (Depends real, no una
    tupla de roles copiada a mano — misma técnica que
    test_matriz_permisos_unitario.py/test_permisos_colegio_unitario.py).
  - crud.exportar_datos_persona_arco delega SIEMPRE en
    usuario_puede_ver_contenido_completo/obtener_detalle_entrada_expediente
    para el expediente (nunca reimplementa esa regla de acceso a mano), y
    dentro de este mismo bundle nunca toca el motor de documentos
    institucionales ni el PDF binario de un informe (alcance aprobado).
  - actualizar_persona (rectificación) solo escribe una fila en
    auditoria_arco cuando se le pasa referencia_solicitud_arco Y hubo al
    menos un cambio real — una edición rutinaria (sin esa referencia) no
    debe dejar rastro en auditoria_arco.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import crud  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_endpoint_export_gateado_a_staff_clinico():
    print("\nEndpoint GET /admin/personas/{id}/exportar-datos-arco — nunca 'colegio'")
    import main  # noqa: E402
    from core.deps import requerir_staff_clinico
    from fastapi.routing import APIRoute

    ruta = None
    for route in main.app.routes:
        if isinstance(route, APIRoute) and route.path == "/api/admin/personas/{persona_id}/exportar-datos-arco":
            ruta = route
            break
    comprobar("La ruta existe", ruta is not None)
    if ruta is None:
        return

    dependencia_directa = [
        d.call for d in ruta.dependant.dependencies
        if getattr(d.call, "__name__", "") == "requerir_staff_clinico" or d.call is requerir_staff_clinico
    ]
    # requerir_staff_clinico ES requerir_rol("superadmin","admin","psicologo"): mismo
    # objeto de función compartido, no una tupla de roles reescrita a mano.
    comprobar("El endpoint depende EXACTAMENTE del alias compartido requerir_staff_clinico (por identidad)",
              any(d is requerir_staff_clinico for d in dependencia_directa))


def test_export_delega_en_la_regla_de_acceso_del_expediente():
    print("\ncrud.exportar_datos_persona_arco — delega en usuario_puede_ver_contenido_completo, nunca reimplementa el candado")
    fuente = inspect.getsource(crud.exportar_datos_persona_arco)
    comprobar("Usa usuario_puede_ver_contenido_completo para decidir qué entradas incluir",
              "usuario_puede_ver_contenido_completo(db, e, usuario_actual)" in fuente)
    comprobar("Usa obtener_detalle_entrada_expediente (que ya registra RegistroLecturasExpediente)",
              "obtener_detalle_entrada_expediente(" in fuente)
    comprobar("Cuenta las entradas omitidas en vez de listarlas como metadata",
              "expediente_entradas_omitidas" in fuente)


def test_export_fuera_de_alcance_aprobado():
    print("\ncrud.exportar_datos_persona_arco — no incluye documentos institucionales ni PDF binario")
    fuente = inspect.getsource(crud.exportar_datos_persona_arco)
    comprobar("No importa/consulta DocumentoInstitucional", "DocumentoInstitucional" not in fuente)
    comprobar("Solo trae metadata de InformeVersion (listar_versiones_de_informe), nunca el PDF",
              "listar_versiones_de_informe" in fuente and "leer_pdf_de_version" not in fuente)


def test_export_deja_constancia_en_auditoria_arco():
    print("\ncrud.exportar_datos_persona_arco — deja constancia en auditoria_arco con la acción correcta")
    fuente = inspect.getsource(crud.exportar_datos_persona_arco)
    comprobar('Registra accion="acceso_datos_persona"', 'accion="acceso_datos_persona"' in fuente)
    comprobar("Reutiliza registrar_auditoria_arco (nunca construye la fila a mano, dos veces, en dos sitios)",
              "registrar_auditoria_arco(" in fuente)


def test_rectificacion_solo_audita_si_hay_referencia_y_cambio_real():
    print("\ncrud.actualizar_persona — auditoria_arco solo se escribe con referencia_solicitud_arco Y cambio real")
    fuente = inspect.getsource(crud.actualizar_persona)
    comprobar("El parámetro referencia_solicitud_arco existe", "referencia_solicitud_arco" in fuente)
    comprobar('Escribe accion="rectificacion_persona"', 'accion="rectificacion_persona"' in fuente)
    comprobar(
        "La condición exige AMBAS cosas: referencia Y registros_auditoria no vacíos",
        "if referencia_solicitud_arco and registros_auditoria:" in fuente,
    )


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — ARCO: acceso (export) y rectificación con trazabilidad")
    print("=" * 72)
    test_endpoint_export_gateado_a_staff_clinico()
    test_export_delega_en_la_regla_de_acceso_del_expediente()
    test_export_fuera_de_alcance_aprobado()
    test_export_deja_constancia_en_auditoria_arco()
    test_rectificacion_solo_audita_si_hay_referencia_y_cambio_real()

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
