"""Pruebas unitarias — vista previa del borrador de un documento institucional
(2026-11-18, opción A del plan de Documentos).

    python -m tests.test_vista_previa_documento_unitario

Sin BD ni servidor. Lo que se prueba con el servidor real (sin efectos en la
base, correlativo intacto, permisos) está en
tests/verificar_vista_previa_documento_e2e.py (prefix ZZDOCPREV).
"""
import inspect
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pypdf import PdfReader  # noqa: E402

from modulos.documentos import crud, pdf_generador as g, router  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion)))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def _contenido(**extra):
    base = {
        "documento": {"titulo": "Informe de prueba", "numero_version": 0},
        "plantilla": {},
        "institucion": {},
        "secciones": [{"tipo_seccion": "texto_libre", "titulo": "Motivo", "datos": {"texto": "Texto del borrador."}}],
    }
    base.update(extra)
    return base


def _texto_pdf(buffer):
    return " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(buffer.getvalue())).pages)


def test_marca_de_agua():
    print("\nMarca de agua: solo en la vista previa")
    con = _texto_pdf(g.generar_pdf_documento(_contenido(marca_agua=["BORRADOR", "VISTA PREVIA — NO VÁLIDO"])))
    sin = _texto_pdf(g.generar_pdf_documento(_contenido()))
    comprobar("Con marca_agua el PDF dice BORRADOR", "BORRADOR" in con, con[:200])
    comprobar("La vista previa trae el mismo contenido que se escribió", "Texto del borrador." in con)
    comprobar("Sin marca_agua (versión emitida) NO dice BORRADOR", "BORRADOR" not in sin, sin[:200])
    comprobar("numero_version=0 no imprime una línea de versión", "Versión: v" not in con)


def test_cache_de_logos_solo_en_vista_previa():
    print("\nMembrete: la vista previa lo reutiliza 60 s; la emisión lo descarga siempre")
    llamadas = []
    original = g.descargar_logo_seguro
    g.descargar_logo_seguro = lambda url: llamadas.append(url) or None
    g._CACHE_LOGOS.clear()
    try:
        for _ in range(3):
            g.generar_pdf_documento(_contenido(marca_agua=["BORRADOR"], institucion={"logo_url": "https://x/membrete.png"}))
        comprobar("3 vistas previas → 1 sola descarga", len(llamadas) == 1, f"{len(llamadas)}")
        llamadas.clear()
        for _ in range(2):
            g.generar_pdf_documento(_contenido(institucion={"logo_url": "https://x/membrete.png"}))
        comprobar("2 emisiones → 2 descargas (nunca usan la caché)", len(llamadas) == 2, f"{len(llamadas)}")
    finally:
        g.descargar_logo_seguro = original
        g._CACHE_LOGOS.clear()


def test_crud_sin_efectos():
    print("\ncrud.generar_vista_previa_documento no deja rastro")
    fuente = inspect.getsource(crud.generar_vista_previa_documento)
    cuerpo = fuente.split('"""')[-1]  # sin el docstring
    comprobar("Usa el MISMO armado que una emisión", "construir_contenido_documento(" in cuerpo)
    comprobar("Nunca consume correlativo", "bloquear_correlativo_para_emision" not in cuerpo and "ultimo_numero" not in cuerpo)
    comprobar("No crea versión ni guarda archivo", all(x not in cuerpo for x in ("db.add(", "commit(", ".guardar(", "DocumentoInstitucionalVersion(")))
    comprobar("No crea entradas en el expediente", "crear_entrada_expediente" not in cuerpo)
    comprobar("Hace rollback de la sesión al terminar de leer", "db.rollback()" in cuerpo)
    comprobar("El correlativo se muestra como 'se asigna al emitir'", "emitir" in crud.TEXTO_CORRELATIVO_VISTA_PREVIA)


def test_ruta():
    print("\nRuta GET /documentos/{id}/vista-previa")
    fuente = inspect.getsource(router.vista_previa_documento_endpoint)
    comprobar("Solo staff clínico", "permisos.STAFF_CLINICO" in fuente)
    comprobar("Revisa el acceso al documento (tenant + nivel_visibilidad)", "_obtener_documento_o_404_con_acceso" in fuente)
    comprobar("No se guarda en caché (datos clínicos)", '"Cache-Control": "no-store"' in fuente)
    comprobar("Se abre en el visor, no se descarga", 'disposicion="inline"' in fuente)
    fuente_mod = inspect.getsource(router)
    i = fuente_mod.index("def vista_previa_documento_endpoint")
    comprobar("Tiene límite de frecuencia", "@limiter.limit(" in fuente_mod[i - 300:i])


if __name__ == "__main__":
    test_marca_de_agua()
    test_cache_de_logos_solo_en_vista_previa()
    test_crud_sin_efectos()
    test_ruta()
    total, ok = len(_resultados), sum(1 for _, b in _resultados if b)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {ok}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(0 if ok == total else 1)
