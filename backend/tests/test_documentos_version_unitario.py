"""Pruebas unitarias — Motor de documentos institucionales, Paso 5
(generación de versión: schemas, ensamblado de tabla_dinamica, tipografía
del PDF). No necesitan la base de datos ni el servidor — todo lo que toca
BD real (gate de consentimiento, correlativo con lock, entrada-puente del
expediente) se verifica en verificar_documentos_version_e2e.py.

    python -m tests.test_documentos_version_unitario
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from types import SimpleNamespace  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from modulos.documentos import schemas, models as docs_models, crud as docs_crud, pdf_generador  # noqa: E402
from modulos.educativo import models as educativo_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def _estudiante(persona_id, nombre, grado_seccion=None):
    return SimpleNamespace(persona_id=persona_id, nombre_completo_historico=nombre, grado_seccion_historico=grado_seccion)


class _FakeQuery:
    """Stub mínimo de una Query de SQLAlchemy: ignora las condiciones de
    filter()/join() (el test controla directamente qué debe devolver cada
    modelo) y solo responde first()/all() con lo pre-configurado."""
    def __init__(self, resultado_first=None, resultado_all=None):
        self._first = resultado_first
        self._all = resultado_all if resultado_all is not None else []

    def filter(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class _FakeDB:
    """db.query(Modelo) o db.query(Modelo, Otro) se resuelve por el PRIMER
    modelo de la llamada -- suficiente para _resolver_resultados_prueba,
    que nunca consulta el mismo modelo dos veces con distinto significado."""
    def __init__(self, primeros=None, todos=None):
        self._primeros = primeros or {}
        self._todos = todos or {}

    def query(self, *modelos):
        clave = modelos[0]
        return _FakeQuery(self._primeros.get(clave), self._todos.get(clave))


# ==========================================
# ReemitirDocumentoRequest — v2+ exige motivo real
# ==========================================
def test_reemitir_exige_motivo_no_vacio():
    print("\nReemitirDocumentoRequest — motivo obligatorio")
    try:
        schemas.ReemitirDocumentoRequest(motivo="")
        comprobar("Rechaza motivo vacío", False)
    except ValidationError:
        comprobar("Rechaza motivo vacío", True)


def test_reemitir_rechaza_motivo_muy_corto():
    print("\nReemitirDocumentoRequest — motivo demasiado corto")
    try:
        schemas.ReemitirDocumentoRequest(motivo="ok")
        comprobar("Rechaza 'ok' (menos de 3 caracteres)", False)
    except ValidationError:
        comprobar("Rechaza 'ok' (menos de 3 caracteres)", True)


def test_reemitir_acepta_motivo_valido():
    print("\nReemitirDocumentoRequest — motivo válido")
    datos = schemas.ReemitirDocumentoRequest(motivo="Corrección solicitada por dirección")
    comprobar("Motivo real aceptado", datos.motivo.startswith("Corrección"))


# ==========================================
# _resolver_tabla_dinamica — pura, sin BD
# ==========================================
def test_tabla_dinamica_filas_desde_lista_estudiantes():
    print("\n_resolver_tabla_dinamica — filas desde la lista congelada (caso de los 29 estudiantes)")
    estudiantes = [
        _estudiante(1, "Ana Torres", "3° A"),
        _estudiante(2, "Luis Paredes", "3° B"),
    ]
    config = {
        "filas_desde_lista_estudiantes": True,
        "columnas": [
            {"titulo": "Estudiante", "origen": "automatico", "campo_automatico": "nombre_completo"},
            {"titulo": "Grado", "origen": "automatico", "campo_automatico": "grado_seccion"},
            {"titulo": "Condición", "origen": "libre"},
        ],
    }
    contenido = {"celdas": {"1": {"Condición": "TDAH"}}}
    resultado = docs_crud._resolver_tabla_dinamica(estudiantes, config, contenido)
    comprobar("2 filas, una por estudiante", len(resultado["filas"]) == 2)
    comprobar("Columna automática 'Estudiante' resuelta desde el snapshot", resultado["filas"][0][0] == "Ana Torres")
    comprobar("Columna 'libre' con dato guardado", resultado["filas"][0][2] == "TDAH")
    comprobar("Columna 'libre' sin dato guardado queda vacía (no revienta)", resultado["filas"][1][2] == "")


def test_tabla_dinamica_libre_no_ligada_a_estudiantes():
    print("\n_resolver_tabla_dinamica — tabla libre (ej. Cuadro de apoyos prioritarios)")
    config = {
        "filas_desde_lista_estudiantes": False,
        "columnas": [{"titulo": "Necesidad"}, {"titulo": "Apoyo sugerido"}],
    }
    contenido = {"filas": [{"Necesidad": "TDAH", "Apoyo sugerido": "Ubicación estratégica"}]}
    resultado = docs_crud._resolver_tabla_dinamica([], config, contenido)
    comprobar("1 fila libre, sin depender de ningún estudiante", resultado["filas"] == [["TDAH", "Ubicación estratégica"]])


def test_tabla_dinamica_sin_config_no_revienta():
    print("\n_resolver_tabla_dinamica — sin config ni contenido")
    resultado = docs_crud._resolver_tabla_dinamica([], None, None)
    comprobar("Devuelve columnas/filas vacías, no lanza excepción", resultado == {"columnas": [], "filas": []})


# ==========================================
# Los "aplica: False" — un documento sin exactamente 1 estudiante nunca
# adivina a quién mostrar.
# ==========================================
def test_datos_filiacion_no_aplica_sin_un_solo_estudiante():
    print("\n_resolver_datos_filiacion — nunca adivina con 0 o >1 estudiantes")
    comprobar("0 estudiantes -> no aplica", docs_crud._resolver_datos_filiacion(None, [], None) == {"aplica": False})
    dos = [_estudiante(1, "A"), _estudiante(2, "B")]
    comprobar("2 estudiantes -> no aplica (documento grupal)", docs_crud._resolver_datos_filiacion(None, dos, None) == {"aplica": False})


def test_datos_familiares_no_aplica_sin_un_solo_estudiante():
    print("\n_resolver_datos_familiares — mismo criterio de 'un solo estudiante'")
    comprobar("0 estudiantes -> no aplica", docs_crud._resolver_datos_familiares(None, []) == {"aplica": False})


def test_resultados_prueba_no_aplica_sin_un_solo_estudiante():
    print("\n_resolver_resultados_prueba — mismo criterio de 'un solo estudiante'")
    resultado = docs_crud._resolver_resultados_prueba(None, documento_id=1, plantilla_seccion_id=1, estudiantes=[])
    comprobar("0 estudiantes -> no aplica", resultado == {"aplica": False})


# ==========================================
# Hallazgo B (ver CLAUDE.md) — resultados_prueba nunca expone un resultado
# que el flujo de revisión profesional todavía retiene, mismo criterio de
# fondo que modulos.educativo.crud.verificar_puede_ver_informe.
# ==========================================
def test_resultados_prueba_informe_no_liberado_queda_retenido():
    print("\n_resolver_resultados_prueba — Hallazgo B: informe_liberado=False nunca expone el resultado real")
    referencia = SimpleNamespace(inscripcion_id=99)
    inscripcion_retenida = SimpleNamespace(informe_liberado=False, resultado_visible_alumno=True)
    db = _FakeDB(primeros={
        docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
        educativo_models.Inscripcion: inscripcion_retenida,
    })
    resultado = docs_crud._resolver_resultados_prueba(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")])
    comprobar("aplica=True (SÍ hay una aplicación vinculada)", resultado.get("aplica") is True)
    comprobar("retenido=True", resultado.get("retenido") is True)
    comprobar("No trae dimensiones/puntajes/nivel real", "dimensiones" not in resultado and "prueba_nombre" not in resultado)


def test_resultados_prueba_liberado_pero_no_visible_para_alumno_ya_no_retiene():
    print("\n_resolver_resultados_prueba — decisión de alcance (sesión 2026-10-17): resultado_visible_alumno=False "
          "YA NO retiene por sí solo si informe_liberado=True — ver docs/gaps-pendientes.md")
    referencia = SimpleNamespace(inscripcion_id=99)
    # resultado_visible_alumno=False a propósito: ese booleano responde "¿lo
    # ve el ALUMNO en su propio portal?", una pregunta ajena a este motor —
    # un plan de intervención/ficha de derivación debe poder usar el
    # resultado real en cuanto el profesional lo liberó clínicamente, sin
    # esperar a que (o aunque nunca) se decida mostrárselo al alumno.
    inscripcion_liberada_no_visible = SimpleNamespace(
        id=99, informe_liberado=True, resultado_visible_alumno=False, evaluacion_id=5, fecha_resolucion=None,
    )
    evaluacion = SimpleNamespace(prueba_id=7)
    prueba = SimpleNamespace(nombre_publico="Prueba de prueba")
    db = _FakeDB(
        primeros={
            docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
            educativo_models.Inscripcion: inscripcion_liberada_no_visible,
            educativo_models.Evaluacion: evaluacion,
            educativo_models.Prueba: prueba,
        },
        todos={educativo_models.DiagnosticoAlumno: []},
    )
    resultado = docs_crud._resolver_resultados_prueba(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")])
    comprobar("retenido=False (informe_liberado=True basta, aunque el alumno no lo vea todavía)",
              resultado.get("retenido") is False)
    comprobar("Trae el resultado real (el motor SÍ puede usarlo)", resultado.get("prueba_nombre") == "Prueba de prueba")


def test_resultados_prueba_liberado_sigue_el_camino_normal():
    print("\n_resolver_resultados_prueba — liberado (ambos True) NO se bloquea, sigue exponiendo el resultado real")
    referencia = SimpleNamespace(inscripcion_id=99)
    inscripcion_liberada = SimpleNamespace(
        id=99, informe_liberado=True, resultado_visible_alumno=True, evaluacion_id=5, fecha_resolucion=None,
    )
    evaluacion = SimpleNamespace(prueba_id=7)
    prueba = SimpleNamespace(nombre_publico="Prueba de prueba")
    db = _FakeDB(
        primeros={
            docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
            educativo_models.Inscripcion: inscripcion_liberada,
            educativo_models.Evaluacion: evaluacion,
            educativo_models.Prueba: prueba,
        },
        todos={educativo_models.DiagnosticoAlumno: []},
    )
    resultado = docs_crud._resolver_resultados_prueba(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")])
    comprobar("aplica=True", resultado.get("aplica") is True)
    comprobar("retenido=False (liberado -> no se degrada)", resultado.get("retenido") is False)
    comprobar("Trae el nombre real de la prueba (el fix no rompió el camino ya liberado)",
              resultado.get("prueba_nombre") == "Prueba de prueba")


def test_renderizador_resultados_prueba_retenido_muestra_placeholder_no_datos():
    print("\npdf_generador._renderizar_resultados_prueba — retenido=True renderiza el placeholder, nunca el dato real")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_resultados_prueba(
        {"aplica": True, "retenido": True, "prueba_nombre": "PHQ-9", "dimensiones": [{"nombre": "X", "nivel": "Alto riesgo", "interpretacion": "y"}]},
        estilos,
    )
    texto_renderizado = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("Renderiza el mensaje de 'pendiente de revisión profesional'",
              "pendiente de revisión profesional" in texto_renderizado.lower())
    comprobar("NO renderiza el nivel real ('Alto riesgo') aunque venga en el dict de entrada",
              "alto riesgo" not in texto_renderizado.lower())
    comprobar("NO renderiza el nombre de la prueba", "phq-9" not in texto_renderizado.lower())


# ==========================================
# _resolver_resultados_prueba_multiple / _renderizar_resultados_prueba_multiple
# — consolida una lista VARIABLE de Inscripcion en una sola sección (ver
# docs/motor-documentos.md). Comparte el candado de "un solo estudiante" y
# el candado de retención (Hallazgo B) con 'resultados_prueba' — ambos ya
# probados arriba vía _resolver_un_resultado_de_inscripcion, extraído de
# _resolver_resultados_prueba precisamente para esto.
# ==========================================
def test_resultados_prueba_multiple_no_aplica_sin_un_solo_estudiante():
    print("\n_resolver_resultados_prueba_multiple — mismo criterio de 'un solo estudiante'")
    resultado = docs_crud._resolver_resultados_prueba_multiple(None, estudiantes=[], contenido_seccion=None)
    comprobar("0 estudiantes -> no aplica", resultado == {"aplica": False})
    dos = [_estudiante(1, "A"), _estudiante(2, "B")]
    resultado_dos = docs_crud._resolver_resultados_prueba_multiple(None, estudiantes=dos, contenido_seccion=None)
    comprobar("2 estudiantes -> no aplica (documento grupal)", resultado_dos == {"aplica": False})


def test_resultados_prueba_multiple_sin_ids_guardados():
    print("\n_resolver_resultados_prueba_multiple — contenido_seccion vacío/None -> aplica=True, resultados=[]")
    resultado = docs_crud._resolver_resultados_prueba_multiple(
        db=_FakeDB(), estudiantes=[_estudiante(1, "A")], contenido_seccion=None,
    )
    comprobar("aplica=True (hay exactamente un estudiante)", resultado.get("aplica") is True)
    comprobar("resultados=[] (nadie vinculó nada todavía)", resultado.get("resultados") == [])


def test_resultados_prueba_multiple_ignora_un_id_que_no_pertenece_a_la_persona():
    print("\n_resolver_resultados_prueba_multiple — un id que no resuelve (persona distinta/borrado) se omite, nunca rompe la sección")
    db = _FakeDB(primeros={educativo_models.Inscripcion: None})  # el filtro persona_id no matchea -> None
    resultado = docs_crud._resolver_resultados_prueba_multiple(
        db=db, estudiantes=[_estudiante(1, "A")], contenido_seccion={"inscripcion_ids": [999]},
    )
    comprobar("aplica=True", resultado.get("aplica") is True)
    comprobar("El id inválido se omitió en silencio, nunca lanza excepción", resultado.get("resultados") == [])


def test_resultados_prueba_multiple_un_id_valido_liberado():
    print("\n_resolver_resultados_prueba_multiple — un id válido y liberado trae el resultado real")
    inscripcion_liberada = SimpleNamespace(
        id=99, persona_id=1, informe_liberado=True, resultado_visible_alumno=True, evaluacion_id=5, fecha_resolucion=None,
    )
    evaluacion = SimpleNamespace(prueba_id=7)
    prueba = SimpleNamespace(nombre_publico="PHQ-9")
    db = _FakeDB(
        primeros={
            educativo_models.Inscripcion: inscripcion_liberada,
            educativo_models.Evaluacion: evaluacion,
            educativo_models.Prueba: prueba,
        },
        todos={educativo_models.DiagnosticoAlumno: []},
    )
    resultado = docs_crud._resolver_resultados_prueba_multiple(
        db=db, estudiantes=[_estudiante(1, "A")], contenido_seccion={"inscripcion_ids": [99]},
    )
    comprobar("Un resultado en la lista", len(resultado.get("resultados") or []) == 1)
    comprobar("Trae el nombre real de la prueba", resultado["resultados"][0].get("prueba_nombre") == "PHQ-9")
    comprobar("retenido=False", resultado["resultados"][0].get("retenido") is False)


def test_renderizador_resultados_prueba_multiple_no_aplica():
    print("\npdf_generador._renderizar_resultados_prueba_multiple — no aplica (0 o 2+ estudiantes)")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_resultados_prueba_multiple({"aplica": False}, estilos)
    texto = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("Placeholder de 'no aplica'", "no aplica" in texto.lower())


def test_renderizador_resultados_prueba_multiple_sin_resultados_vinculados():
    print("\npdf_generador._renderizar_resultados_prueba_multiple — aplica pero sin ninguno vinculado todavía")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_resultados_prueba_multiple({"aplica": True, "resultados": []}, estilos)
    texto = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("Placeholder de 'sin resultados vinculados todavía'", "sin resultados vinculados" in texto.lower())


def test_renderizador_resultados_prueba_multiple_mezcla_liberado_y_retenido():
    print("\npdf_generador._renderizar_resultados_prueba_multiple — un instrumento liberado y otro retenido, cada uno independiente")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_resultados_prueba_multiple(
        {
            "aplica": True,
            "resultados": [
                {"retenido": False, "prueba_nombre": "PHQ-9", "fecha_evaluacion": None, "dimensiones": []},
                {"retenido": True},
            ],
        },
        estilos,
    )
    texto = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("Muestra el nombre real del instrumento liberado", "phq-9" in texto.lower())
    comprobar("Muestra el placeholder de retención para el segundo, sin exponer datos reales de ese",
              "pendiente de revisión profesional" in texto.lower())


# ==========================================
# pdf_generador — despacho por tipo_seccion (nunca por nombre)
# ==========================================
def test_grafico_barras_sin_estudiante_unico_cae_a_manual_o_vacio():
    print("\n_resolver_grafico_barras — sin exactamente 1 estudiante, nunca busca el vínculo automático")
    resultado = docs_crud._resolver_grafico_barras(
        db=_FakeDB(), documento_id=1, plantilla_seccion_id=1, estudiantes=[], contenido_guardado=None,
    )
    comprobar("modo=None sin datos manuales ni estudiante único", resultado.get("modo") is None)


def test_grafico_barras_informe_no_liberado_queda_retenido():
    print("\n_resolver_grafico_barras — mismo Hallazgo B que resultados_prueba: informe_liberado=False nunca expone el puntaje real")
    referencia = SimpleNamespace(inscripcion_id=99)
    inscripcion_retenida = SimpleNamespace(informe_liberado=False, resultado_visible_alumno=True)
    db = _FakeDB(primeros={
        docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
        educativo_models.Inscripcion: inscripcion_retenida,
    })
    resultado = docs_crud._resolver_grafico_barras(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")], contenido_guardado=None)
    comprobar("modo=automatico (SÍ hay un vínculo)", resultado.get("modo") == "automatico")
    comprobar("retenido=True", resultado.get("retenido") is True)
    comprobar("No trae datos/puntajes reales", "datos" not in resultado)


def test_grafico_barras_liberado_pero_no_visible_para_alumno_ya_no_retiene():
    print("\n_resolver_grafico_barras — decisión de alcance (sesión 2026-10-17): resultado_visible_alumno=False "
          "YA NO retiene por sí solo si informe_liberado=True")
    referencia = SimpleNamespace(inscripcion_id=99)
    inscripcion_liberada_no_visible = SimpleNamespace(
        id=99, informe_liberado=True, resultado_visible_alumno=False, evaluacion_id=5,
    )
    evaluacion = SimpleNamespace(prueba_id=7)
    prueba = SimpleNamespace(nombre_publico="Prueba de prueba")
    db = _FakeDB(
        primeros={
            docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
            educativo_models.Inscripcion: inscripcion_liberada_no_visible,
            educativo_models.Evaluacion: evaluacion,
            educativo_models.Prueba: prueba,
        },
        todos={educativo_models.Dimension: []},
    )
    resultado = docs_crud._resolver_grafico_barras(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")], contenido_guardado=None)
    comprobar("modo=automatico, retenido=False (informe_liberado=True basta)",
              resultado.get("modo") == "automatico" and resultado.get("retenido") is False)


def test_grafico_barras_liberado_trae_puntajes_reales_por_dimension():
    print("\n_resolver_grafico_barras — liberado: trae un puntaje numérico (ResultadoDimension.puntaje_directo) por dimensión")
    referencia = SimpleNamespace(inscripcion_id=99)
    inscripcion_liberada = SimpleNamespace(
        id=99, informe_liberado=True, resultado_visible_alumno=True, evaluacion_id=5,
    )
    evaluacion = SimpleNamespace(prueba_id=7)
    prueba = SimpleNamespace(nombre_publico="Prueba de prueba")
    dim_a, dim_b = SimpleNamespace(nombre="Atención"), SimpleNamespace(nombre="Memoria")
    res_a, res_b = SimpleNamespace(puntaje_directo=14), SimpleNamespace(puntaje_directo=9)
    db = _FakeDB(
        primeros={
            docs_models.DocumentoInstitucionalResultadoPrueba: referencia,
            educativo_models.Inscripcion: inscripcion_liberada,
            educativo_models.Evaluacion: evaluacion,
            educativo_models.Prueba: prueba,
        },
        todos={educativo_models.Dimension: [(dim_a, res_a), (dim_b, res_b)]},
    )
    resultado = docs_crud._resolver_grafico_barras(db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")], contenido_guardado=None)
    comprobar("modo=automatico, retenido=False", resultado.get("modo") == "automatico" and resultado.get("retenido") is False)
    comprobar("2 puntos de datos, con el puntaje numérico real", resultado.get("datos") == [
        {"etiqueta": "Atención", "valor": 14.0}, {"etiqueta": "Memoria", "valor": 9.0},
    ])


def test_grafico_barras_sin_vinculo_usa_datos_manuales():
    print("\n_resolver_grafico_barras — sin vínculo automático, usa los datos manuales del contenido guardado")
    db = _FakeDB(primeros={docs_models.DocumentoInstitucionalResultadoPrueba: None})
    resultado = docs_crud._resolver_grafico_barras(
        db, documento_id=1, plantilla_seccion_id=1, estudiantes=[_estudiante(1, "A")],
        contenido_guardado={"datos": [{"etiqueta": "X", "valor": 3}]},
    )
    comprobar("modo=manual", resultado.get("modo") == "manual")
    comprobar("Trae los datos tal cual los escribió quien llenó el documento", resultado.get("datos") == [{"etiqueta": "X", "valor": 3}])


def test_renderizador_grafico_barras_retenido_muestra_placeholder():
    print("\npdf_generador._renderizar_grafico_barras — retenido=True renderiza el placeholder, nunca el gráfico")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_grafico_barras({"modo": "automatico", "retenido": True}, estilos)
    texto_renderizado = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("Renderiza el mensaje de 'pendiente de revisión profesional', nunca una imagen",
              "pendiente de revisión profesional" in texto_renderizado.lower() and len(elementos) == 1)


def test_renderizador_grafico_barras_sin_datos_muestra_placeholder():
    print("\npdf_generador._renderizar_grafico_barras — sin datos (ni manual ni automático) renderiza el placeholder")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_grafico_barras({"modo": None}, estilos)
    texto_renderizado = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("'Sin datos de gráfico configurados todavía'", "sin datos de gráfico" in texto_renderizado.lower())


def test_renderizador_imagen_anexo_sin_storage_key_muestra_placeholder():
    print("\npdf_generador._renderizar_imagen_anexo — sin storage_key renderiza el placeholder, nunca intenta leer storage")
    estilos, _, _ = pdf_generador._construir_estilos({})
    elementos = pdf_generador._renderizar_imagen_anexo({}, estilos)
    texto_renderizado = " ".join(getattr(e, "text", "") for e in elementos)
    comprobar("'Sin imagen/anexo cargado todavía'", "sin imagen" in texto_renderizado.lower())


def test_los_12_tipos_de_seccion_tienen_renderizador():
    print("\npdf_generador — los 14 tipo_seccion cerrados tienen su propio renderizador")
    # 🆕 'grupo_campos' (octavo, antes diferido), 'firma_doble' (noveno, dos
    # firmas simétricas), 'ficha_imprimible' (décimo, formulario en blanco
    # para llenar a mano), 'grafico_barras' y 'imagen_anexo' (undécimo y
    # duodécimo), 'firma_triple' (decimotercero, dos firmas simétricas +
    # una tercera centrada debajo), 'resultados_prueba_multiple'
    # (decimocuarto, consolida una cantidad VARIABLE de aplicaciones reales
    # en una sola sección) — ver docs/motor-documentos.md.
    esperados = {"encabezado", "datos_filiacion", "datos_familiares", "texto_libre",
                 "tabla_dinamica", "resultados_prueba", "firma", "grupo_campos", "firma_doble",
                 "ficha_imprimible", "grafico_barras", "imagen_anexo", "firma_triple",
                 "resultados_prueba_multiple"}
    comprobar("_RENDERIZADORES cubre exactamente los 14 tipos", set(pdf_generador._RENDERIZADORES.keys()) == esperados)


def test_tipografia_cae_a_helvetica_si_la_fuente_no_se_reconoce():
    print("\npdf_generador — una fuente no soportada cae al sustituto sin reventar")
    fuente, _, _ = pdf_generador._resolver_tipografia({"fuente": "Comic Sans MS"})
    comprobar("No lanza excepción y devuelve una fuente registrada real", fuente in ("Arial", "Helvetica"))


def test_tipografia_helvetica_explicita_se_respeta():
    print("\npdf_generador — pedir Helvetica explícitamente se respeta tal cual")
    fuente, fuente_bold, fuente_italica = pdf_generador._resolver_tipografia({"fuente": "Helvetica"})
    comprobar("Fuente=Helvetica, Bold=Helvetica-Bold, Italica=Helvetica-Oblique",
               (fuente, fuente_bold, fuente_italica) == ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique"))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — MOTOR DE DOCUMENTOS INSTITUCIONALES (VERSIÓN)")
    print("=" * 72)
    test_reemitir_exige_motivo_no_vacio()
    test_reemitir_rechaza_motivo_muy_corto()
    test_reemitir_acepta_motivo_valido()
    test_tabla_dinamica_filas_desde_lista_estudiantes()
    test_tabla_dinamica_libre_no_ligada_a_estudiantes()
    test_tabla_dinamica_sin_config_no_revienta()
    test_datos_filiacion_no_aplica_sin_un_solo_estudiante()
    test_datos_familiares_no_aplica_sin_un_solo_estudiante()
    test_resultados_prueba_no_aplica_sin_un_solo_estudiante()
    test_resultados_prueba_informe_no_liberado_queda_retenido()
    test_resultados_prueba_liberado_pero_no_visible_para_alumno_ya_no_retiene()
    test_resultados_prueba_liberado_sigue_el_camino_normal()
    test_renderizador_resultados_prueba_retenido_muestra_placeholder_no_datos()
    test_resultados_prueba_multiple_no_aplica_sin_un_solo_estudiante()
    test_resultados_prueba_multiple_sin_ids_guardados()
    test_resultados_prueba_multiple_ignora_un_id_que_no_pertenece_a_la_persona()
    test_resultados_prueba_multiple_un_id_valido_liberado()
    test_renderizador_resultados_prueba_multiple_no_aplica()
    test_renderizador_resultados_prueba_multiple_sin_resultados_vinculados()
    test_renderizador_resultados_prueba_multiple_mezcla_liberado_y_retenido()
    test_grafico_barras_sin_estudiante_unico_cae_a_manual_o_vacio()
    test_grafico_barras_informe_no_liberado_queda_retenido()
    test_grafico_barras_liberado_pero_no_visible_para_alumno_ya_no_retiene()
    test_grafico_barras_liberado_trae_puntajes_reales_por_dimension()
    test_grafico_barras_sin_vinculo_usa_datos_manuales()
    test_renderizador_grafico_barras_retenido_muestra_placeholder()
    test_renderizador_grafico_barras_sin_datos_muestra_placeholder()
    test_renderizador_imagen_anexo_sin_storage_key_muestra_placeholder()
    test_los_12_tipos_de_seccion_tienen_renderizador()
    test_tipografia_cae_a_helvetica_si_la_fuente_no_se_reconoce()
    test_tipografia_helvetica_explicita_se_respeta()

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
