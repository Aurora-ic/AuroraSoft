"""Pruebas unitarias — Matriz de permisos endpoint × rol.

    python -m tests.test_matriz_permisos_unitario

Sin BD ni servidor: importa `main.app` (con DATABASE_URL/SECRET_KEY dummy, así
que `create_engine()` nunca conecta de verdad) y recorre `app.routes` para
extraer, de cada endpoint bajo `/api`, cuál de las tres dependencias de
autorización usa realmente FastAPI en su firma:

  - `Depends(requerir_rol(...))`             -> roles explícitos (se leen del
    closure de la clausura `verificador`, nunca de una copia mantenida a mano
    que podría desincronizarse del código real).
  - `Depends(obtener_usuario_actual)`        -> cualquier rol autenticado.
  - `Depends(verificar_acceso_institucion)`  -> cualquier rol autenticado, más
    un candado adicional de institución (marcado aparte como
    `verifica_institucion`, no cambia qué roles llegan al cuerpo).
  - ninguna de las tres                      -> endpoint público (sin JWT).

Esto NO ve autorización aplicada a mano DENTRO del cuerpo del endpoint (un
`if usuario_actual.rol != "superadmin" and ...` inline, o el filtrado de
`nivel_visibilidad`/`AutorizacionAccesoColegio`) — eso no es introspectable
desde `route.dependant` sin ejecutar el código, así que se cubre aparte con
una búsqueda de texto sobre `inspect.getsource()` del propio endpoint (ver
`_ENDPOINTS_DATOS_CLINICOS` más abajo), no con la matriz de dependencias.

La matriz calculada se compara contra el snapshot aprobado
`tests/matriz_permisos_esperada.json`: el test falla si aparece un endpoint
nuevo no declarado ahí, si desaparece uno declarado (JSON desactualizado), o
si los roles/gating de uno cambian sin que alguien haya revisado el diff y
actualizado el JSON a mano — el JSON nunca se regenera solo.
"""

import inspect
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

import main  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

_resultados = []
RUTA_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matriz_permisos_esperada.json")

ROLES = ("admin", "colegio", "psicologo", "superadmin")


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def informar(nombre, detalle=""):
    """Como comprobar(), pero nunca cuenta como fallo — para dejar constancia
    de hallazgos de auditoría (p.ej. 'colegio' sin exclusión explícita) que
    esta tarea pide DOCUMENTAR, no corregir."""
    print(f"  [INFO] {nombre}" + (f" — {detalle}" if detalle else ""))


# ---------------------------------------------------------------------------
# 1) Extracción de la matriz real desde app.routes
# ---------------------------------------------------------------------------

def _dependencias_planas(dependant, vistos=None):
    """Aplana el árbol de sub-dependencias de un endpoint (una dependencia
    puede depender a su vez de otras, p.ej. requerir_rol -> obtener_usuario_
    actual -> HTTPBearer). `vistos` evita recursión infinita/duplicados."""
    if vistos is None:
        vistos = set()
    resultado = []
    for d in dependant.dependencies:
        clave = id(d.call)
        if clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(d.call)
        resultado.extend(_dependencias_planas(d, vistos))
    return resultado


def _endpoints_api():
    """Todas las (metodo, ruta, endpoint_fn) bajo /api, sin duplicar HEAD
    (FastAPI agrega HEAD automáticamente a toda ruta GET)."""
    for route in main.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api"):
            continue
        for metodo in sorted(route.methods - {"HEAD"}):
            yield metodo, route.path, route


def calcular_matriz_actual():
    """Devuelve {'METODO /ruta': {rol: bool, ..., 'sin_autenticar': bool,
    'verifica_institucion': bool}} a partir de las dependencias REALES de
    cada endpoint — nunca de una lista mantenida a mano."""
    matriz = {}
    roles_desconocidos = set()
    for metodo, path, route in _endpoints_api():
        llamadas = _dependencias_planas(route.dependant)
        autenticado = any(getattr(c, "__name__", "") == "obtener_usuario_actual" for c in llamadas)
        verifica_institucion = any(
            getattr(c, "__name__", "") == "verificar_acceso_institucion" for c in llamadas
        )
        llamadas_rol = [
            c for c in llamadas
            if getattr(c, "__qualname__", "") == "requerir_rol.<locals>.verificador"
        ]

        clave = f"{metodo} {path}"
        if not autenticado:
            fila = {rol: False for rol in ROLES}
            fila["sin_autenticar"] = True
            fila["verifica_institucion"] = False
            matriz[clave] = fila
            continue

        if llamadas_rol:
            roles_permitidos = set(llamadas_rol[0].__closure__[0].cell_contents)
            roles_desconocidos |= (roles_permitidos - set(ROLES))
        else:
            roles_permitidos = set(ROLES)  # obtener_usuario_actual / verificar_acceso_institucion: cualquier rol

        fila = {rol: (rol in roles_permitidos) for rol in ROLES}
        fila["sin_autenticar"] = False
        fila["verifica_institucion"] = verifica_institucion
        matriz[clave] = fila

    assert not roles_desconocidos, (
        f"requerir_rol(...) usa roles fuera de {ROLES}: {roles_desconocidos} "
        "(actualiza la constante ROLES de este test, no la ignores)"
    )
    return matriz


def _fuente_de(metodo, path):
    for m, p, route in _endpoints_api():
        if m == metodo and p == path:
            return inspect.getsource(route.endpoint)
    raise AssertionError(f"No se encontró el endpoint {metodo} {path}")


# ---------------------------------------------------------------------------
# 2) Único público permitido: examen por token, login, recuperación de clave,
#    y servir (nunca subir) el branding autoalojado de una institución
#    (modulos/instituciones/crud.leer_imagen_branding) — deliberadamente
#    público porque es exactamente la URL que core/url_segura.
#    descargar_logo_seguro() pide SIN credenciales al generar un PDF, igual
#    que pediría el logo externo de cualquier otro colegio. Nunca expone
#    nada sensible: solo la imagen de membrete/pie que ya es pública en el
#    documento generado.
# ---------------------------------------------------------------------------

_PUBLICO_PERMITIDO_PATRONES = [
    re.compile(r"^/api/auth/login$"),
    re.compile(r"^/api/auth/solicitar-recuperacion$"),
    re.compile(r"^/api/auth/resetear-password$"),
    re.compile(r"^/api/educativo/comenzar-test/\{token\}$"),
    re.compile(r"^/api/educativo/examen/\{token\}(/.*)?$"),
    re.compile(r"^/api/instituciones/\{institucion_id\}/branding/\{tipo\}$"),
    # Firma personal — mismo criterio: es la URL que descargar_logo_seguro()
    # pide sin credenciales al generar un PDF (ver modulos/auth/crud.py:
    # leer_firma_usuario()).
    re.compile(r"^/api/auth/usuarios/\{usuario_id\}/firma$"),
]


def test_solo_login_recuperacion_y_examen_por_token_son_publicos():
    print("\n1 · Endpoints sin autenticación — solo login / recuperación / examen por token")
    matriz = calcular_matriz_actual()
    publicos = [clave for clave, fila in matriz.items() if fila["sin_autenticar"]]
    comprobar("Hay al menos un endpoint público (login existe)", len(publicos) > 0)
    for clave in sorted(publicos):
        metodo, path = clave.split(" ", 1)
        permitido = any(p.match(path) for p in _PUBLICO_PERMITIDO_PATRONES)
        comprobar(f"{clave}: público permitido (examen por token / login / recuperación)", permitido)


# ---------------------------------------------------------------------------
# 3) La matriz completa no puede cambiar sin tocar el JSON aprobado a mano
# ---------------------------------------------------------------------------

def test_matriz_coincide_con_snapshot_aprobado():
    print("\n2 · Matriz endpoint × rol vs. snapshot aprobado (matriz_permisos_esperada.json)")
    with open(RUTA_JSON, encoding="utf-8") as f:
        esperado = json.load(f)
    matriz_esperada = esperado["endpoints"]
    matriz_actual = calcular_matriz_actual()

    nuevos = sorted(set(matriz_actual) - set(matriz_esperada))
    comprobar(
        "No hay endpoints nuevos sin declarar en matriz_permisos_esperada.json",
        not nuevos, f"nuevos={nuevos}" if nuevos else "",
    )

    desaparecidos = sorted(set(matriz_esperada) - set(matriz_actual))
    comprobar(
        "No hay endpoints declarados que ya no existen en la app (JSON desactualizado)",
        not desaparecidos, f"desaparecidos={desaparecidos}" if desaparecidos else "",
    )

    cambiados = []
    for clave in sorted(set(matriz_actual) & set(matriz_esperada)):
        if matriz_actual[clave] != matriz_esperada[clave]:
            cambiados.append({"endpoint": clave, "esperado": matriz_esperada[clave], "actual": matriz_actual[clave]})
    comprobar(
        "Ningún endpoint compartido cambió sus roles/gating sin actualizar el JSON",
        not cambiados, json.dumps(cambiados, ensure_ascii=False) if cambiados else "",
    )


# ---------------------------------------------------------------------------
# 4) Endpoints con contenido clínico: colegio solo debe entrar si el propio
#    código aplica nivel_visibilidad o AutorizacionAccesoColegio. Donde hoy
#    NO hay ese candado (antecedentes/datos-familiares "por diseño", o los
#    hallazgos de informes/seguimiento/ficha-completa que SÍ son un vacío
#    real) se deja constancia con `informar()`, sin fallar el test — esta
#    tarea es de auditoría/documentación, no de corrección.
# ---------------------------------------------------------------------------

_NIVEL_VISIBILIDAD = "nivel_visibilidad"
_AUTORIZACION_COLEGIO = "autorizacion_colegio"
_INFORME_LIBERADO_CONDICIONAL = "informe_liberado_condicional"  # remediación paso 3
_REDACTADO_PARA_COLEGIO = "redactado_para_colegio"     # remediación paso 4
_POR_DISENO_SIN_GATING = "ninguno_por_diseno"          # documentado en CLAUDE.md como intencional
_SIN_GATING_ACTUAL = "ninguno_actual"                  # hallazgo de esta auditoría, no una decisión documentada

_ENDPOINTS_DATOS_CLINICOS = {
    # -- Motor de documentos institucionales: gateado por nivel_visibilidad --
    "GET /api/documentos/": (_NIVEL_VISIBILIDAD, ("listar_documentos_visibles_para_usuario",)),
    "GET /api/documentos/{documento_id}": (_NIVEL_VISIBILIDAD, ("_obtener_documento_o_404_con_acceso",)),
    "GET /api/documentos/{documento_id}/secciones": (_NIVEL_VISIBILIDAD, ("_obtener_documento_o_404_con_acceso",)),
    "GET /api/documentos/{documento_id}/versiones": (_NIVEL_VISIBILIDAD, ("_obtener_documento_o_404_con_acceso",)),
    "GET /api/documentos/{documento_id}/versiones/{numero_version}/descargar": (
        _NIVEL_VISIBILIDAD, ("_obtener_documento_o_404_con_acceso",)),

    # -- Expediente clínico: gateado por AutorizacionAccesoColegio --
    "GET /api/admin/personas/{persona_id}/expediente": (
        _AUTORIZACION_COLEGIO, ("listar_entradas_expediente_visibles",)),
    "GET /api/admin/personas/expediente/{entrada_id}": (
        _AUTORIZACION_COLEGIO, ("obtener_detalle_entrada_expediente",)),

    # -- Antecedentes/datos familiares: abierto a colegio POR DISEÑO (CLAUDE.md
    # lo documenta explícitamente: "read is open to any authenticated role of
    # the same institución including colegio") — no depende de ninguno de los
    # dos mecanismos anteriores, y no debería.
    "GET /api/admin/personas/{persona_id}/antecedentes-clinicos": (_POR_DISENO_SIN_GATING, ()),
    "GET /api/admin/personas/{persona_id}/datos-familiares": (_POR_DISENO_SIN_GATING, ()),

    # -- Evidencia del consentimiento (cierre de gap, docs/gaps-
    # pendientes.md): mismo criterio POR DISEÑO que el consentimiento
    # mismo — "colegio" ya puede registrar/ver/revocar un consentimiento
    # hoy sin ningún gating especial, así que subir/descargar su evidencia
    # (el documento firmado/escaneado) tampoco lo necesita. No es contenido
    # clínico, es administrativo.
    "GET /api/admin/personas/consentimiento/{consentimiento_id}/evidencia": (_POR_DISENO_SIN_GATING, ()),
    "POST /api/admin/personas/consentimiento/{consentimiento_id}/evidencia": (_POR_DISENO_SIN_GATING, ()),

    # -- Remediación paso 4: historial_evaluaciones/sesiones_seguimiento quedan
    # [] para colegio (nunca se consultan siquiera) dentro de
    # crud.obtener_ficha_completa — la redacción en sí vive en crud.py, no en
    # este router, así que el marcador aquí solo confirma que el router
    # REENVÍA usuario_actual (condición necesaria); la redacción misma la
    # prueba test_permisos_colegio_unitario.py (fuente de crud.py) y el e2e
    # (comportamiento real contra un informe/sesión reales).
    "GET /api/admin/personas/{persona_id}/ficha-completa": (
        _REDACTADO_PARA_COLEGIO, ("usuario_actual=usuario_actual",)),

    # -- Informes (PDF/metadata/historial): remediación paso 3 — colegio solo
    # ve un informe puntual si informe_liberado=True, vía
    # crud.verificar_puede_ver_informe (misma condición que ya protege al
    # propio alumno). El historial (lista) no llama a ese helper directamente
    # -- filtra fila por fila, porque una persona puede tener aplicaciones
    # con distinto informe_liberado cada una -- así que su marcador es el
    # propio filtro, no el nombre del helper.
    "GET /api/educativo/inscripciones/{inscripcion_id}/informe-pdf": (
        _INFORME_LIBERADO_CONDICIONAL, ("verificar_puede_ver_informe",)),
    "GET /api/educativo/inscripciones/{inscripcion_id}/informe": (
        _INFORME_LIBERADO_CONDICIONAL, ("verificar_puede_ver_informe",)),
    "GET /api/educativo/personas/{persona_id}/informes": (
        _INFORME_LIBERADO_CONDICIONAL, ('fila["informe_liberado"]',)),
    # POST /educativo/seguimiento/ y GET /educativo/seguimiento/{persona_id}
    # YA NO viven aquí: se cerraron con requerir_staff_clinico (paso 2 del
    # plan de remediación) — colegio ni siquiera pasa el Depends, así que no
    # hay nada que "gatear" en el cuerpo del endpoint.

    # -- Remediación paso 5: resultados/nivel por alumno quedan [] para colegio,
    # el resto del dashboard (participación, conteos agregados) se conserva.
    "GET /api/educativo/campanas/{evaluacion_id}/dashboard": (
        _REDACTADO_PARA_COLEGIO, ("redactar_resultados_dashboard_campana",)),
    "GET /api/educativo/campanas/{evaluacion_id}/exportar-excel": (
        _REDACTADO_PARA_COLEGIO, ("redactar_resultados_dashboard_campana",)),
    # Mismo candado que el dashboard de campaña — comparte alumnos[].resultados,
    # así que reutiliza la misma función de redacción sin cambios.
    "GET /api/educativo/dashboard/academico": (
        _REDACTADO_PARA_COLEGIO, ("redactar_resultados_dashboard_campana",)),
    # Mismo candado que los tres anteriores — su propio Excel, hasta ahora
    # inexistente para el dashboard por salón/grado.
    "GET /api/educativo/dashboard/academico/exportar-excel": (
        _REDACTADO_PARA_COLEGIO, ("redactar_resultados_dashboard_campana",)),
    "GET /api/educativo/procesos/dashboard": (
        _REDACTADO_PARA_COLEGIO, ("redactar_resultados_dashboard_institucional",)),
}


def test_datos_clinicos_colegio_depende_de_los_mecanismos_documentados():
    print("\n3 · Endpoints con datos clínicos donde 'colegio' puede entrar — ¿de qué depende?")
    matriz_actual = calcular_matriz_actual()

    for clave, (mecanismo, marcadores) in sorted(_ENDPOINTS_DATOS_CLINICOS.items()):
        assert clave in matriz_actual, f"{clave} ya no existe en la app — actualiza _ENDPOINTS_DATOS_CLINICOS"
        fila = matriz_actual[clave]
        comprobar(f"{clave}: 'colegio' efectivamente puede llegar al cuerpo del endpoint (Depends)",
                  fila["colegio"] is True, f"fila={fila}")

        metodo, path = clave.split(" ", 1)
        fuente = _fuente_de(metodo, path)

        if mecanismo in (_NIVEL_VISIBILIDAD, _AUTORIZACION_COLEGIO, _INFORME_LIBERADO_CONDICIONAL,
                         _REDACTADO_PARA_COLEGIO):
            encontrado = any(m in fuente for m in marcadores)
            comprobar(f"{clave}: el código SÍ aplica el candado esperado ({mecanismo}: {marcadores[0]})", encontrado)
        elif mecanismo == _POR_DISENO_SIN_GATING:
            informar(f"{clave}: sin nivel_visibilidad/AutorizacionAccesoColegio — POR DISEÑO (CLAUDE.md), "
                     "'colegio' lee esto igual que admin/psicologo de su propia institución")
        elif mecanismo == _SIN_GATING_ACTUAL:
            informar(f"{clave}: sin nivel_visibilidad/AutorizacionAccesoColegio — HALLAZGO DE AUDITORÍA, "
                     "no una decisión documentada; ver reporte de la tarea (sección 4)")


# ---------------------------------------------------------------------------
# 5) Reporte (no falla el test): endpoints sensibles donde 'colegio' pasa el
#    Depends y NO está en la lista ya revisada como "por diseño" arriba —
#    para decidir, humanamente, si alguno debe cerrarse.
# ---------------------------------------------------------------------------

_COLEGIO_POR_DISENO_CONOCIDO = {
    # Lectura de padrón / estructura académica / agenda / consentimientos:
    # tenant-scoped, no clínico en el sentido de resultado/diagnóstico —
    # documentado en CLAUDE.md como abierto a colegio.
    "POST /api/admin/personas/", "GET /api/admin/personas/{institucion_id}",
    "GET /api/admin/personas/academico/grados/{nivel_educativo_id}",
    "GET /api/admin/personas/academico/niveles/{institucion_id}",
    "GET /api/admin/personas/academico/secciones/{grado_id}",
    "POST /api/admin/personas/citas/", "GET /api/admin/personas/citas/mi-agenda",
    "PATCH /api/admin/personas/citas/{cita_id}", "DELETE /api/admin/personas/citas/{cita_id}",
    "GET /api/admin/personas/por-codigo/{codigo_institucional}",
    "GET /api/admin/personas/promocion/procesos", "GET /api/admin/personas/promocion/procesos/{proceso_id}",
    "PATCH /api/admin/personas/{persona_id}", "GET /api/admin/personas/{persona_id}/citas",
    "POST /api/admin/personas/{persona_id}/consentimiento", "GET /api/admin/personas/{persona_id}/consentimiento",
    "POST /api/admin/personas/{persona_id}/consentimiento/asentimiento",
    "POST /api/admin/personas/{persona_id}/consentimiento/asentimiento/revocar",
    "POST /api/admin/personas/{persona_id}/consentimiento/revocar",
    "GET /api/admin/personas/{persona_id}/consentimientos",
    "GET /api/admin/personas/{persona_id}/contactos",
    "GET /api/admin/personas/{persona_id}/detalle",
    "GET /api/admin/personas/{persona_id}/historial-academico",
    "POST /api/admin/personas/{persona_id}/matricula",
    "GET /api/instituciones/me",
    # 🆕 GET /auth/me — devuelve exactamente lo que el JWT de cualquier rol
    # ya trae decodificado del lado del cliente (email/rol/institucion_id);
    # no expone nada que 'colegio' no tuviera ya.
    "GET /api/auth/me",
    "POST /api/educativo/campos-socio/",
    # Catálogo de pruebas: lectura permitida a colegio POR DISEÑO (decisión de
    # producto explícita, remediación de permisos paso 2/2025) — colegio
    # puede consultar qué instrumentos/baremos/reglas existen, nunca crearlos
    # ni editarlos (eso sí quedó cerrado con requerir_staff_clinico).
    "GET /api/educativo/pruebas/", "GET /api/educativo/pruebas/{prueba_id}/completa",
    "GET /api/educativo/pruebas/{prueba_id}/reglas", "GET /api/educativo/baremos/{dimension_id}",
    "GET /api/educativo/campanas/",
    # Documentos/expediente ya cubiertos arriba (gateados de verdad).
    "GET /api/documentos/", "GET /api/documentos/anios-oficiales", "GET /api/documentos/plantillas",
    "GET /api/documentos/plantillas/{plantilla_id}", "GET /api/documentos/plantillas/{plantilla_id}/secciones",
    "GET /api/documentos/tipos", "GET /api/documentos/tipos/{tipo_id}",
    "GET /api/documentos/{documento_id}", "GET /api/documentos/{documento_id}/secciones",
    "GET /api/documentos/{documento_id}/versiones",
    "GET /api/documentos/{documento_id}/versiones/{numero_version}/descargar",
    "GET /api/admin/personas/{persona_id}/expediente", "GET /api/admin/personas/expediente/{entrada_id}",
    "GET /api/admin/personas/{persona_id}/antecedentes-clinicos", "GET /api/admin/personas/{persona_id}/datos-familiares",
    # 🆕 Firma personal (imagen) — no es dato clínico, es branding propio de
    # la cuenta. 'colegio' pasa el Depends (obtener_usuario_actual, no
    # requerir_rol) pero el candado real vive en el cuerpo de la función
    # (subir_firma_usuario_endpoint): solo puede subir SU PROPIA firma
    # (usuario_actual.id == usuario_id) o un admin/superadmin de su misma
    # institución puede subir la de otro — 'colegio' nunca puede tocar la
    # firma de alguien más. test_permisos_colegio_unitario.py no cubre esto
    # porque no es dato clínico; queda documentado aquí en su lugar.
    "POST /api/auth/usuarios/{usuario_id}/firma",
}


def reportar_endpoints_sensibles_sin_exclusion_de_colegio():
    print("\n4 · REPORTE (no falla el test) — endpoints donde 'colegio' pasa el Depends "
          "y no están ya revisados como 'por diseño' arriba")
    matriz = calcular_matriz_actual()
    pendientes = sorted(
        clave for clave, fila in matriz.items()
        if not fila["sin_autenticar"] and fila["colegio"]
        and clave not in _COLEGIO_POR_DISENO_CONOCIDO
        and clave not in _ENDPOINTS_DATOS_CLINICOS
    )
    informar(f"{len(pendientes)} endpoints sin revisión previa donde 'colegio' entra sin requerir_rol propio")
    for clave in pendientes:
        print(f"      - {clave}")
    return pendientes


# ---------------------------------------------------------------------------
# 5) PLAN_REMODELACION_ARQUITECTURA.md, sección 2.3 — ningún endpoint debe
#    escribir una tupla de roles LITERAL en requerir_rol(...): debe importar
#    el nombre correcto de core.permisos (o, para el único alias que ya
#    existía antes de esa fase, requerir_staff_clinico de core.deps — ver
#    core/permisos.py, que reexporta exactamente ese mismo objeto como
#    STAFF_CLINICO). Esto no cambia NINGÚN comportamiento: la tupla real que
#    decide qué rol entra sigue siendo la misma, solo se prohíbe escribirla
#    a mano por segunda vez en un router. Un endpoint nuevo que copie
#    `requerir_rol("superadmin", "admin")` en vez de
#    `permisos.SOLO_ADMINISTRATIVO` falla aquí inmediatamente.
# ---------------------------------------------------------------------------

_LITERAL_REQUERIR_ROL = re.compile(r'requerir_rol\(\s*["\']')

# Los routers de este repo (y sus tests) son los únicos lugares donde un
# `requerir_rol("...")` literal sería un endpoint copiando la tupla a mano.
# `core/deps.py` (la fábrica en sí) y `core/permisos.py` (donde las cuatro
# tuplas canónicas SÍ deben vivir, una sola vez cada una) quedan fuera a
# propósito — prohibirlo ahí also prohibiría el propio catálogo.
_ARCHIVOS_ROUTERS = [
    "modulos/auth/router.py",
    "modulos/documentos/router.py",
    "modulos/educativo/router.py",
    "modulos/instituciones/router.py",
    "modulos/superadmin/router.py",
]


def test_ningun_endpoint_usa_una_tupla_de_roles_literal():
    print("\n5 · Ningún router escribe requerir_rol(\"...\") a mano — todos importan de core.permisos")
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hallazgos = []
    for rel in _ARCHIVOS_ROUTERS:
        ruta = os.path.join(backend, rel)
        with open(ruta, encoding="utf-8") as f:
            for numero_linea, linea in enumerate(f, start=1):
                if _LITERAL_REQUERIR_ROL.search(linea):
                    hallazgos.append(f"{rel}:{numero_linea}: {linea.strip()}")
    comprobar(
        "cero tuplas literales de requerir_rol(...) en los routers reales",
        not hallazgos,
        f"{len(hallazgos)} hallazgo(s): {hallazgos}" if hallazgos else "",
    )


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Matriz de permisos endpoint × rol")
    print("=" * 72)
    test_solo_login_recuperacion_y_examen_por_token_son_publicos()
    test_matriz_coincide_con_snapshot_aprobado()
    test_datos_clinicos_colegio_depende_de_los_mecanismos_documentados()
    reportar_endpoints_sensibles_sin_exclusion_de_colegio()
    test_ningun_endpoint_usa_una_tupla_de_roles_literal()

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
