"""Pruebas unitarias — Remediación de permisos: 'colegio' fuera de lo clínico.

    python -m tests.test_permisos_colegio_unitario

Sin BD ni servidor. Este archivo crece junto con el plan de remediación de
permisos (ver CLAUDE.md, "Permission surface: what the matrix test can't
see") — cada paso implementado agrega su propia sección de pruebas aquí,
en vez de un archivo nuevo por paso, porque todos documentan la misma
decisión de producto ("colegio" nunca toca contenido clínico ni configura el
instrumento de evaluación).

Paso 2 — cierre mecánico de rol: los ~24 endpoints listados abajo pasaron de
`Depends(obtener_usuario_actual)` (cualquier rol autenticado) a
`Depends(requerir_staff_clinico)`. Esta prueba no vuelve a levantar la app
contra HTTP (eso lo hace `verificar_permisos_colegio_e2e.py`) — verifica algo
más fuerte y más barato: que la dependencia real de cada endpoint sea, por
identidad de objeto, el mismo `core.deps.requerir_staff_clinico` compartido
— no una tupla de roles reescrita a mano que "por ahora" coincide pero podría
divergir en un futuro cambio de política (agregar un rol al tier sin tocar
estos 24 sitios, por ejemplo).
"""

import inspect
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

import main  # noqa: E402
from core.deps import requerir_staff_clinico  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from modulos.educativo.crud import (  # noqa: E402
    redactar_resultados_dashboard_campana,
    redactar_resultados_dashboard_institucional,
    verificar_puede_ver_informe,
)
from modulos.superadmin.crud import obtener_ficha_completa  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _mapa_rutas():
    mapa = {}
    for route in main.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        for metodo in sorted(route.methods - {"HEAD"}):
            mapa[f"{metodo} {route.path}"] = route
    return mapa


def _dependencia_usuario_actual(route):
    """El objeto real que FastAPI invoca como Depends(...) para el parámetro
    'usuario_actual' de este endpoint (sub-dependencia directa del dependant
    raíz, nunca una de sus propias sub-dependencias anidadas)."""
    for d in route.dependant.dependencies:
        if getattr(d.call, "__qualname__", "") == "requerir_rol.<locals>.verificador":
            return d.call
    return None


# Paso 2: endpoints que deben depender EXACTAMENTE del alias compartido
# requerir_staff_clinico — CRUD de configuración del instrumento, campañas,
# links mágicos, casos pendientes y seguimiento clínico.
_ENDPOINTS_STAFF_CLINICO_PASO2 = [
    "POST /api/educativo/baremos/", "PATCH /api/educativo/baremos/{baremo_id}",
    "DELETE /api/educativo/baremos/{baremo_id}",
    "POST /api/educativo/dimensiones/", "PATCH /api/educativo/dimensiones/{dimension_id}",
    "DELETE /api/educativo/dimensiones/{dimension_id}",
    "POST /api/educativo/opciones/", "PATCH /api/educativo/opciones/{opcion_id}",
    "DELETE /api/educativo/opciones/{opcion_id}",
    "POST /api/educativo/preguntas/", "PATCH /api/educativo/preguntas/{pregunta_id}",
    "DELETE /api/educativo/preguntas/{pregunta_id}",
    "POST /api/educativo/pruebas/", "PATCH /api/educativo/pruebas/{prueba_id}",
    "POST /api/educativo/pruebas/carga-masiva/",
    "POST /api/educativo/pruebas/{prueba_id}/reglas", "PATCH /api/educativo/reglas/{regla_id}",
    "POST /api/educativo/campanas/", "POST /api/educativo/campanas/{evaluacion_id}/matricular-roster",
    "GET /api/educativo/campanas/{evaluacion_id}/links",
    "GET /api/educativo/casos-pendientes",
    "POST /api/educativo/seguimiento/", "GET /api/educativo/seguimiento/{persona_id}",
    "PATCH /api/educativo/seguimiento/{sesion_id}", "DELETE /api/educativo/seguimiento/{sesion_id}",
]

# Endpoints de solo lectura que deben seguir abiertos a 'colegio' (decisión de
# producto explícita, no un descuido) — regresión negativa: si alguien los
# cierra sin querer, esta prueba también debe notarlo.
_ENDPOINTS_CATALOGO_ABIERTOS_A_COLEGIO = [
    "GET /api/educativo/pruebas/", "GET /api/educativo/pruebas/{prueba_id}/completa",
    "GET /api/educativo/pruebas/{prueba_id}/reglas", "GET /api/educativo/baremos/{dimension_id}",
    "GET /api/educativo/campanas/",
]


def test_endpoints_paso2_usan_el_alias_compartido_requerir_staff_clinico():
    print("\n1 · Los 24 endpoints del paso 2 dependen, por identidad, de core.deps.requerir_staff_clinico")
    rutas = _mapa_rutas()
    for clave in _ENDPOINTS_STAFF_CLINICO_PASO2:
        assert clave in rutas, f"{clave} ya no existe en la app — actualiza esta lista"
        dependencia = _dependencia_usuario_actual(rutas[clave])
        comprobar(f"{clave}: usuario_actual = Depends(requerir_staff_clinico) (mismo objeto, no una copia)",
                  dependencia is requerir_staff_clinico)


def test_catalogo_de_lectura_sigue_abierto_a_colegio():
    print("\n2 · El catálogo de lectura (pruebas/baremos/campañas) sigue sin requerir_rol propio")
    rutas = _mapa_rutas()
    for clave in _ENDPOINTS_CATALOGO_ABIERTOS_A_COLEGIO:
        assert clave in rutas, f"{clave} ya no existe en la app — actualiza esta lista"
        dependencia = _dependencia_usuario_actual(rutas[clave])
        comprobar(f"{clave}: sigue sin requerir_rol propio (colegio puede leerlo)", dependencia is None)


# ---------------------------------------------------------------------------
# Paso 3 — crud.verificar_puede_ver_informe: colegio solo si informe_liberado.
# ---------------------------------------------------------------------------

def _usuario(rol, institucion_id):
    return SimpleNamespace(rol=rol, institucion_id=institucion_id)


def _no_lanza(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return True
    except HTTPException:
        return False


def _lanza_403(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return False
    except HTTPException as exc:
        return exc.status_code == 403


def test_verificar_puede_ver_informe():
    print("\n3 · crud.verificar_puede_ver_informe — colegio solo si informe_liberado=True")

    superadmin = _usuario("superadmin", institucion_id=None)
    comprobar("superadmin: pasa con informe_liberado=False, institución ajena — siempre pasa",
              _no_lanza(verificar_puede_ver_informe, superadmin, 999, False))

    admin_propia = _usuario("admin", institucion_id=10)
    comprobar("admin de la institución del informe, informe_liberado=False -> pasa (no es colegio)",
              _no_lanza(verificar_puede_ver_informe, admin_propia, 10, False))
    comprobar("admin de OTRA institución -> 403, sin importar informe_liberado",
              _lanza_403(verificar_puede_ver_informe, admin_propia, 20, True))

    psicologo_propia = _usuario("psicologo", institucion_id=10)
    comprobar("psicologo de la institución del informe, informe_liberado=False -> pasa (no es colegio)",
              _no_lanza(verificar_puede_ver_informe, psicologo_propia, 10, False))

    colegio_propia = _usuario("colegio", institucion_id=10)
    comprobar("colegio de la institución del informe, informe_liberado=True -> pasa",
              _no_lanza(verificar_puede_ver_informe, colegio_propia, 10, True))
    comprobar("colegio de la institución del informe, informe_liberado=False -> 403 (todavía en revisión)",
              _lanza_403(verificar_puede_ver_informe, colegio_propia, 10, False))
    comprobar("colegio de OTRA institución, informe_liberado=True -> 403 (institución manda primero)",
              _lanza_403(verificar_puede_ver_informe, colegio_propia, 20, True))


# ---------------------------------------------------------------------------
# Paso 4 — ficha-completa: chequeo estático (la parte que SÍ depende de la
# BD real — que 'colegio' efectivamente reciba listas vacías — se cubre en
# verificar_permisos_colegio_e2e.py, reutilizando la persona/informe que el
# paso 3 ya monta). Esto solo protege contra que alguien borre el `if
# es_colegio` sin tocar ningún test.
# ---------------------------------------------------------------------------

def test_ficha_completa_corta_el_contenido_clinico_antes_de_consultarlo():
    print("\n4 · crud.obtener_ficha_completa corta historial_evaluaciones/sesiones ANTES de consultarlas para colegio")
    fuente = inspect.getsource(obtener_ficha_completa)
    comprobar("Define es_colegio a partir de usuario_actual.rol",
              'es_colegio = usuario_actual.rol == "colegio"' in fuente)
    comprobar("historial_evaluaciones queda [] para colegio (no arma la lista y la descarta después)",
              "if not es_colegio:" in fuente and "historial_evaluaciones = []" in fuente)
    comprobar("sesiones_seguimiento queda [] para colegio",
              '[] if es_colegio else educativo_crud.obtener_historial_de_persona' in fuente)


# ---------------------------------------------------------------------------
# Paso 5 — redacción de dashboards: lógica pura sobre dicts, sin BD. La
# forma de los fixtures replica exactamente lo que devuelven
# crud.obtener_dashboard_campana / crud.obtener_dashboard_proceso.
# ---------------------------------------------------------------------------

_DASHBOARD_CAMPANA_FIXTURE = {
    "evaluacion_id": 1, "nombre_grupo": "3ro B", "nombre_prueba": "PHQ-9",
    "total_inscritos": 2, "total_finalizados": 2, "total_pendientes": 0,
    "distribucion_por_dimension": {"depresion": {"critico": 1, "leve": 1}},
    "alumnos": [
        {"inscripcion_id": 10, "persona_id": 100, "nombre_completo": "Alumno Uno", "estado": "Finalizado",
         "fecha_resolucion": "2026-01-01", "resultados": [{"dimension": "depresion", "puntaje_directo": 27.0, "nivel": "critico"}]},
        {"inscripcion_id": 11, "persona_id": 101, "nombre_completo": "Alumno Dos", "estado": "Finalizado",
         "fecha_resolucion": "2026-01-02", "resultados": [{"dimension": "depresion", "puntaje_directo": 3.0, "nivel": "leve"}]},
    ],
}

_DASHBOARD_INSTITUCIONAL_FIXTURE = {
    "institucion_id": 5,
    "alumnos": [
        {"nombre_completo": "Alumno Uno",
         "pruebas": [{"prueba": "PHQ-9", "estado": "Finalizado",
                      "resultados": [{"dimension": "depresion", "puntaje_directo": 27.0, "nivel": "critico"}]}]},
    ],
}


def test_redaccion_dashboards():
    print("\n5 · redactar_resultados_dashboard_{campana,institucional} — colegio ve participación, no diagnóstico")

    redactado = redactar_resultados_dashboard_campana(_DASHBOARD_CAMPANA_FIXTURE)
    comprobar("Dashboard de campaña: cada alumno queda con resultados=[]",
              all(a["resultados"] == [] for a in redactado["alumnos"]))
    comprobar("Dashboard de campaña: nombre/estado/fecha de cada alumno se conservan",
              all(a["nombre_completo"] and a["estado"] for a in redactado["alumnos"]))
    comprobar("Dashboard de campaña: los conteos agregados (total_*, distribucion_por_dimension) se conservan",
              redactado["total_inscritos"] == 2 and redactado["distribucion_por_dimension"] == {"depresion": {"critico": 1, "leve": 1}})
    comprobar("Dashboard de campaña: el original NO se mutó (misma llamada, dos veces, mismo resultado)",
              _DASHBOARD_CAMPANA_FIXTURE["alumnos"][0]["resultados"] != [])

    redactado_inst = redactar_resultados_dashboard_institucional(_DASHBOARD_INSTITUCIONAL_FIXTURE)
    comprobar("Dashboard institucional: cada prueba de cada alumno queda con resultados=[]",
              all(p["resultados"] == [] for a in redactado_inst["alumnos"] for p in a["pruebas"]))
    comprobar("Dashboard institucional: nombre/prueba/estado se conservan",
              redactado_inst["alumnos"][0]["nombre_completo"] == "Alumno Uno"
              and redactado_inst["alumnos"][0]["pruebas"][0]["prueba"] == "PHQ-9")
    comprobar("Dashboard institucional: el original NO se mutó",
              _DASHBOARD_INSTITUCIONAL_FIXTURE["alumnos"][0]["pruebas"][0]["resultados"] != [])


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Remediación de permisos: 'colegio' fuera de lo clínico")
    print("=" * 72)
    test_endpoints_paso2_usan_el_alias_compartido_requerir_staff_clinico()
    test_catalogo_de_lectura_sigue_abierto_a_colegio()
    test_verificar_puede_ver_informe()
    test_ficha_completa_corta_el_contenido_clinico_antes_de_consultarlo()
    test_redaccion_dashboards()

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
