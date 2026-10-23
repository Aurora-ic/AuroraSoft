"""Pruebas unitarias — cierre de los 3 gaps de backend documentados en
docs/gaps-pendientes.md bajo "ARCO" y "evidencia_ruta sin usar":

    python -m tests.test_gaps_arco_evidencia_unitario

Sin BD ni servidor (igual que test_arco_datos_persona_unitario.py): importa
main.app con DATABASE_URL/SECRET_KEY dummy y hace inspección de código/rutas,
nunca ejecuta contra una BD real — eso lo hace verificar_gaps_arco_evidencia_e2e.py.

  1. Vista de comparación histórica entre campañas
     (GET /admin/personas/{id}/historico-campanas): gateada a
     requerir_staff_clinico (nunca 'colegio'), y crud.historico_campanas_de_persona
     filtra is_deleted/is_anonymized igual que obtener_ficha_completa (vista
     de trabajo, no el derecho de acceso ARCO que sí los incluye).
  2. ARCO acotado a un consentimiento puntual (?consentimiento_id= en
     exportar-datos-arco): filtra por consentimiento_apoderado_id/
     consentimiento_asentimiento_id, 404 si no corresponde a la persona, y deja
     fuera expediente/sesiones/citas/datos_familiares/antecedentes/contactos
     (documentado como fuera de alcance, no un olvido).
  3. Evidencia del consentimiento (POST/GET .../consentimiento/{id}/evidencia):
     extensión en lista blanca, tamaño máximo, nunca confía en el nombre de
     archivo crudo para construir la key de storage, y reutiliza
     core.storage (nunca un mecanismo de archivos propio).
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import crud  # noqa: E402
from core import storage  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ---------------------------------------------------------------------------
# 1) Histórico entre campañas
# ---------------------------------------------------------------------------

def test_historico_campanas_gateado_a_staff_clinico():
    print("\n1 · GET /admin/personas/{id}/historico-campanas — nunca 'colegio'")
    import main  # noqa: E402
    from core.deps import requerir_staff_clinico
    from fastapi.routing import APIRoute

    ruta = None
    for route in main.app.routes:
        if isinstance(route, APIRoute) and route.path == "/api/admin/personas/{persona_id}/historico-campanas":
            ruta = route
            break
    comprobar("La ruta existe", ruta is not None)
    if ruta is None:
        return
    dependencia_directa = [d.call for d in ruta.dependant.dependencies]
    comprobar(
        "Depende EXACTAMENTE del alias compartido requerir_staff_clinico (por identidad)",
        any(d is requerir_staff_clinico for d in dependencia_directa),
    )


def test_historico_campanas_filtra_borrados_y_anonimizados():
    print("\ncrud.historico_campanas_de_persona — filtra is_deleted/is_anonymized (vista de trabajo)")
    fuente = inspect.getsource(crud.historico_campanas_de_persona)
    comprobar("Filtra is_deleted == False", "is_deleted == False" in fuente)
    comprobar("Filtra is_anonymized == False", "is_anonymized == False" in fuente)
    comprobar("Ordena ASCENDENTE (línea de tiempo, no el historial descendente de la ficha)",
              ".fecha_resolucion.asc()" in fuente)
    comprobar("Devuelve la forma reagrupada por dimensión para comparar un mismo indicador en el tiempo",
              "comparacion_por_dimension" in fuente)


# ---------------------------------------------------------------------------
# 2) ARCO acotado a un consentimiento puntual
# ---------------------------------------------------------------------------

def test_export_arco_acepta_consentimiento_id():
    print("\ncrud.exportar_datos_persona_arco — acepta consentimiento_id y valida pertenencia")
    firma = inspect.signature(crud.exportar_datos_persona_arco)
    comprobar("El parámetro consentimiento_id existe y es opcional (default None)",
              "consentimiento_id" in firma.parameters and firma.parameters["consentimiento_id"].default is None)

    fuente = inspect.getsource(crud.exportar_datos_persona_arco)
    comprobar(
        "Valida que el consentimiento pertenezca a ESTA persona antes de usarlo como filtro",
        "models.ConsentimientoInformado.persona_id == persona.id" in fuente,
    )
    comprobar("404 explícito si el consentimiento no corresponde (nunca se ignora en silencio)",
              "status.HTTP_404_NOT_FOUND" in fuente)
    comprobar(
        "Filtra inscripciones por consentimiento_apoderado_id U consentimiento_asentimiento_id",
        "consentimiento_apoderado_id == consentimiento_filtro.id" in fuente
        and "consentimiento_asentimiento_id == consentimiento_filtro.id" in fuente,
    )
    comprobar(
        "Recorta informes_data a las inscripciones filtradas (mismo subconjunto, no una query aparte)",
        "f[\"inscripcion_id\"] in ids_inscripciones_filtradas" in fuente,
    )


def test_export_arco_acotado_excluye_lo_no_cubierto_por_un_consentimiento():
    print("\ncrud.exportar_datos_persona_arco — acotado a un consentimiento deja fuera lo que no enlaza a él")
    fuente = inspect.getsource(crud.exportar_datos_persona_arco)
    comprobar(
        "El bloque de expediente/citas/sesiones/familiares/antecedentes/contactos queda "
        "condicionado a 'consentimiento_filtro is None' (no se consulta si el export está acotado)",
        "if consentimiento_filtro is None:" in fuente,
    )
    comprobar(
        "'consentimientos' pasa a ser solo ese registro, no la vista combinada, cuando está acotado",
        "acotado_a_un_consentimiento" in fuente,
    )
    comprobar(
        "La auditoría deja constancia de que el export estuvo acotado",
        "Acotada al consentimiento #" in fuente,
    )


# ---------------------------------------------------------------------------
# 3) Evidencia del consentimiento
# ---------------------------------------------------------------------------

def test_evidencia_nunca_confia_en_el_nombre_de_archivo_crudo():
    print("\ncrud._extension_segura — lista blanca, nunca el nombre de archivo tal cual")
    comprobar("'.pdf' está permitido", ".pdf" in crud.EXTENSIONES_EVIDENCIA_PERMITIDAS)
    comprobar("Una extensión fuera de la lista blanca lanza 400, no se acepta tal cual",
              _lanza_400(lambda: crud._extension_segura("evidencia.exe")))
    comprobar("Sin extensión también lanza 400", _lanza_400(lambda: crud._extension_segura("sin_extension")))
    comprobar("Un intento de path traversal en el nombre no cambia el resultado (solo se usa la extensión)",
              crud._extension_segura("../../etc/passwd.pdf") == ".pdf")


def _lanza_400(fn):
    from fastapi import HTTPException
    try:
        fn()
    except HTTPException as e:
        return e.status_code == 400
    return False


def test_evidencia_tiene_tope_de_tamano():
    print("\ncrud.guardar_evidencia_consentimiento — tope de tamaño antes de tocar storage")
    fuente = inspect.getsource(crud.guardar_evidencia_consentimiento)
    comprobar("Compara len(contenido) contra TAMANO_MAXIMO_EVIDENCIA_BYTES antes de llamar a storage",
              "len(contenido) > TAMANO_MAXIMO_EVIDENCIA_BYTES" in fuente)
    comprobar("El límite es razonable para un PDF/foto escaneados (entre 1 y 50 MB)",
              1 * 1024 * 1024 <= crud.TAMANO_MAXIMO_EVIDENCIA_BYTES <= 50 * 1024 * 1024)


def test_evidencia_reutiliza_core_storage_nunca_un_mecanismo_propio():
    print("\ncrud.guardar_evidencia_consentimiento / leer_evidencia_consentimiento — reutilizan core.storage")
    fuente_guardar = inspect.getsource(crud.guardar_evidencia_consentimiento)
    fuente_leer = inspect.getsource(crud.leer_evidencia_consentimiento)
    comprobar("guardar_evidencia_consentimiento usa obtener_storage_service().guardar(...)",
              "obtener_storage_service().guardar(" in fuente_guardar)
    comprobar("guardar_evidencia_consentimiento construye la key vía construir_storage_key_evidencia_consentimiento",
              "construir_storage_key_evidencia_consentimiento(" in fuente_guardar)
    comprobar("leer_evidencia_consentimiento usa obtener_storage_service().leer(...)",
              "obtener_storage_service().leer(" in fuente_leer)
    comprobar("core.storage expone el builder de key específico de esta evidencia",
              hasattr(storage, "construir_storage_key_evidencia_consentimiento"))


def test_key_de_evidencia_nunca_se_construye_a_mano_fuera_de_crud():
    print("\ncore.storage.construir_storage_key_evidencia_consentimiento — forma de la key")
    key = storage.construir_storage_key_evidencia_consentimiento(7, 42, ".pdf")
    comprobar("La key aísla por institución y por consentimiento, sin versión (una subida reemplaza a la anterior)",
              key == "instituciones/7/consentimientos/42/evidencia.pdf")


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — cierre de gaps: histórico de campañas, ARCO x")
    print("consentimiento, evidencia del consentimiento")
    print("=" * 72)
    test_historico_campanas_gateado_a_staff_clinico()
    test_historico_campanas_filtra_borrados_y_anonimizados()
    test_export_arco_acepta_consentimiento_id()
    test_export_arco_acotado_excluye_lo_no_cubierto_por_un_consentimiento()
    test_evidencia_nunca_confia_en_el_nombre_de_archivo_crudo()
    test_evidencia_tiene_tope_de_tamano()
    test_evidencia_reutiliza_core_storage_nunca_un_mecanismo_propio()
    test_key_de_evidencia_nunca_se_construye_a_mano_fuera_de_crud()

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
