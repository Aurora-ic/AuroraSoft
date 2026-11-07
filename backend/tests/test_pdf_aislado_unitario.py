"""Pruebas unitarias — PDFs ajenos abiertos en un proceso hijo con tiempo
máximo (M1 de la revisión de seguridad previa al piloto).

    python -m tests.test_pdf_aislado_unitario

Sin BD ni servidor (DATABASE_URL/SECRET_KEY dummy, nunca se conecta). Sí
lanza procesos hijo reales de Python: es justamente lo que se prueba.

El problema que cierra: la evidencia PDF del expediente se fusionaba al final
del informe con pypdf DENTRO del mismo proceso — en el worker de Celery (sin
time_limit) y en la propia petición web de reemitir/reprocesar. pypdf es
Python puro y sus avisos conocidos son de denegación de servicio (bucles,
memoria) con PDFs armados a propósito; y al subir no se miraba ni la
cabecera `%PDF-`. Ahora `core/pdf_aislado.py`:
  - al subir: cabecera + pasada completa de pypdf en un hijo con tope de
    tiempo -> 400 si está cifrado, vacío, dañado, >200 páginas o se cuelga;
  - al fusionar: cada anexo se revisa aparte en un hijo; el que falla se
    omite con un aviso en su portada y el informe se genera igual.
"""

import io
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from fastapi import HTTPException  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from core import pdf_aislado  # noqa: E402
from core.pdf_aislado import PdfNoValido, inspeccionar_pdf  # noqa: E402

_resultados = []
BACKEND = Path(__file__).resolve().parent.parent


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _pdf(paginas=1, texto="Anexo de prueba"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    for n in range(paginas):
        c.drawString(100, 700, f"{texto} — página {n + 1}")
        c.showPage()
    c.save()
    return buffer.getvalue()


def _pdf_cifrado():
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for pagina in PdfReader(io.BytesIO(_pdf())).pages:
        writer.add_page(pagina)
    writer.encrypt("clave-secreta")
    salida = io.BytesIO()
    writer.write(salida)
    return salida.getvalue()


def _motivo(funcion, *args):
    try:
        funcion(*args)
    except PdfNoValido as exc:
        return str(exc)
    return None


def _contar_hijos(funcion, *args):
    """Cuántos procesos hijo lanza `funcion` (reemplaza subprocess.run)."""
    original = pdf_aislado.subprocess.run
    lanzados = []

    def contador(*a, **k):
        lanzados.append(a)
        return original(*a, **k)

    pdf_aislado.subprocess.run = contador
    try:
        try:
            funcion(*args)
        except (PdfNoValido, HTTPException):
            pass
    finally:
        pdf_aislado.subprocess.run = original
    return len(lanzados)


# ------------------------------------------------------------------
def test_pdf_valido():
    print("\n[1] Un PDF normal pasa")
    comprobar("PDF de 3 páginas -> 3", inspeccionar_pdf(_pdf(3)) == 3)
    comprobar("se revisa en un proceso hijo (1 lanzado)", _contar_hijos(inspeccionar_pdf, _pdf()) == 1)


def test_cabecera():
    print("\n[2] Sin cabecera %PDF- -> rechazo inmediato, sin lanzar ningún hijo")
    for nombre, datos in {
        "PNG llamado .pdf": b"\x89PNG\r\n\x1a\n" + b"\0" * 64,
        "HTML": b"<html><script>alert(1)</script></html>",
        "ejecutable": b"MZ\x90\x00" + b"\0" * 64,
        "vacío": b"",
        "%PDF- tras basura": b"basura%PDF-1.7\n",
    }.items():
        comprobar(f"{nombre} -> 'no es un PDF', 0 hijos",
                  _motivo(inspeccionar_pdf, datos) == "El archivo no es un PDF."
                  and _contar_hijos(inspeccionar_pdf, datos) == 0)


def test_pdfs_que_no_sirven():
    print("\n[3] PDFs que pypdf no puede usar -> PdfNoValido con un mensaje claro")
    motivo = _motivo(inspeccionar_pdf, _pdf_cifrado())
    comprobar("cifrado -> pide subirlo sin contraseña", motivo is not None and "contraseña" in motivo, str(motivo))
    motivo = _motivo(inspeccionar_pdf, b"%PDF-1.7\n" + os.urandom(2048))
    comprobar("cabecera válida + basura -> dañado", motivo is not None and "dañado" in motivo, str(motivo))
    entero = _pdf(5)
    motivo = _motivo(inspeccionar_pdf, entero[: len(entero) // 3])
    comprobar("PDF cortado a un tercio -> dañado", motivo is not None and "dañado" in motivo, str(motivo))
    tope = pdf_aislado.MAXIMO_PAGINAS_ANEXO
    motivo = _motivo(inspeccionar_pdf, _pdf(tope + 1))
    comprobar(f"{tope + 1} páginas -> supera el máximo", motivo is not None and str(tope) in motivo, str(motivo))
    comprobar(f"{tope} páginas -> pasa", inspeccionar_pdf(_pdf(tope)) == tope)


def test_hijo_que_se_cuelga_o_se_cae():
    print("\n[4] El tiempo máximo corta de verdad; un hijo que se cae no tumba al padre")
    original_cmd, original_lim = pdf_aislado.COMANDO_HIJO, pdf_aislado.LIMITE_SEGUNDOS_POR_PDF
    try:
        pdf_aislado.COMANDO_HIJO = [sys.executable, "-c", "import time; time.sleep(30)"]
        pdf_aislado.LIMITE_SEGUNDOS_POR_PDF = 2
        t0 = time.perf_counter()
        motivo = _motivo(inspeccionar_pdf, _pdf())
        duracion = time.perf_counter() - t0
        comprobar("hijo colgado -> 'tardó demasiado'", motivo is not None and "tardó demasiado" in motivo, str(motivo))
        comprobar(f"cortado al tope ({duracion:.1f} s < 6 s), no a los 30 s", duracion < 6)

        pdf_aislado.COMANDO_HIJO = [sys.executable, "-c", "import sys; sys.exit(3)"]
        motivo = _motivo(inspeccionar_pdf, _pdf())
        comprobar("hijo que muere sin responder -> dañado", motivo is not None and "dañado" in motivo, str(motivo))

        pdf_aislado.COMANDO_HIJO = [sys.executable, "-c", "print('no es json')"]
        motivo = _motivo(inspeccionar_pdf, _pdf())
        comprobar("hijo que responde basura -> dañado", motivo is not None and "dañado" in motivo, str(motivo))
    finally:
        pdf_aislado.COMANDO_HIJO, pdf_aislado.LIMITE_SEGUNDOS_POR_PDF = original_cmd, original_lim


def test_fusion_en_el_informe():
    print("\n[5] Fusión de anexos del informe: el válido entra, el inválido deja un aviso")
    from pypdf import PdfReader
    from core.pdf_generator import _fusionar_anexos_pdf

    base = _pdf(2, "Informe")
    anexos = [
        {"titulo": "Dibujo de la familia", "bytes": _pdf(3, "Evidencia buena")},
        {"titulo": "Escaneo roto", "bytes": b"%PDF-1.7\n" + os.urandom(1024)},
        {"titulo": "Ficha cifrada", "bytes": _pdf_cifrado()},
    ]
    resultado = _fusionar_anexos_pdf(io.BytesIO(base), anexos).getvalue()
    lector = PdfReader(io.BytesIO(resultado))
    paginas = len(lector.pages)
    # 2 del informe + (portada + 3) del válido + 1 portada por cada inválido
    comprobar("2 + (1 + 3) + 1 + 1 = 8 páginas", paginas == 8, str(paginas))
    texto = "\n".join(p.extract_text() or "" for p in lector.pages)
    comprobar("las páginas del anexo válido están", texto.count("Evidencia buena") == 3)
    comprobar("la portada del anexo dañado lo avisa",
              "Escaneo roto" in texto and texto.count("No se pudo incluir este anexo") == 2)
    comprobar("el aviso del cifrado dice por qué", "contraseña" in texto)

    hijos = _contar_hijos(_fusionar_anexos_pdf, io.BytesIO(base), anexos[:1])
    comprobar("1 anexo -> 2 hijos (inspección + fusión)", hijos == 2, str(hijos))


def test_subida_de_evidencia():
    print("\n[6] Subida de evidencia (consentimiento y expediente)")
    from modulos.superadmin.crud import _validar_contenido_evidencia

    comprobar("PDF válido declarado como octet-stream -> se guarda como application/pdf",
              _validar_contenido_evidencia(_pdf(), ".pdf", "application/octet-stream") == "application/pdf")
    for nombre, datos in (("HTML llamado .pdf", b"<html></html>"), ("PDF cifrado", _pdf_cifrado()),
                          ("PDF dañado", b"%PDF-1.4\n" + os.urandom(512))):
        try:
            _validar_contenido_evidencia(datos, ".pdf", "application/pdf")
            codigo = None
        except HTTPException as exc:
            codigo = exc.status_code
        comprobar(f"{nombre} -> 400", codigo == 400)


def test_pypdf_solo_en_el_hijo():
    print("\n[7] pypdf solo abre PDFs ajenos dentro de core/pdf_aislado.py")
    sospechosos = []
    for carpeta in ("core", "modulos", "tareas"):
        for archivo in (BACKEND / carpeta).rglob("*.py"):
            if archivo.name == "pdf_aislado.py":
                continue
            for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\b(PdfReader|PdfWriter)\s*\(", linea) and not linea.lstrip().startswith("#"):
                    sospechosos.append(f"{archivo.relative_to(BACKEND)}:{n}")
    comprobar("ningún PdfReader/PdfWriter fuera del hijo", not sospechosos, ", ".join(sospechosos))


def test_topes_de_celery():
    print("\n[8] Celery: ninguna tarea ocupa un worker para siempre")
    from core.cola_tareas import app

    comprobar("tope global blando 300 s / duro 360 s",
              app.conf.task_soft_time_limit == 300 and app.conf.task_time_limit == 360)
    app.loader.import_default_modules()
    tareas = app.tasks
    agenda = tareas["tareas.notificar_agenda_diaria"]
    casos = tareas["educativo.sincronizar_casos_riesgo"]
    comprobar("agenda diaria con tope propio más amplio (1500/1800)",
              (agenda.soft_time_limit, agenda.time_limit) == (1500, 1800))
    comprobar("sincronizar casos en riesgo con tope propio (900/960)",
              (casos.soft_time_limit, casos.time_limit) == (900, 960))
    informe = next(t for n, t in tareas.items() if n.endswith("tarea_generar_informe_en_segundo_plano"))
    comprobar("el informe PDF usa el tope global (sin override)",
              informe.soft_time_limit is None and informe.time_limit is None)


def test_version_pypdf():
    print("\n[9] pypdf en la versión que corrige sus avisos")
    import pypdf

    instalada = tuple(int(p) for p in pypdf.__version__.split(".")[:3])
    comprobar(f"pypdf instalada >= 6.21.4 ({pypdf.__version__})", instalada >= (6, 21, 4))
    requisitos = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    comprobar("requirements.txt fija pypdf==6.21.4", re.search(r"^pypdf==6\.21\.4$", requisitos, re.M) is not None)


def main_tests():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — PDFs ajenos en un proceso hijo con tiempo máximo")
    print("=" * 72)
    test_pdf_valido()
    test_cabecera()
    test_pdfs_que_no_sirven()
    test_hijo_que_se_cuelga_o_se_cae()
    test_fusion_en_el_informe()
    test_subida_de_evidencia()
    test_pypdf_solo_en_el_hijo()
    test_topes_de_celery()
    test_version_pypdf()

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
