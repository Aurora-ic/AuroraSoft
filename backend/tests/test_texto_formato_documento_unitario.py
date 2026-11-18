"""Pruebas unitarias — formato del texto libre de los documentos institucionales
(2026-11-18, editor con formato; opción B del plan de Documentos).

    python -m tests.test_texto_formato_documento_unitario

Sin BD ni servidor. El texto se guarda como TEXTO con marcas (nunca HTML):
**negrita**, *cursiva*, ++subrayado++, "• "/"- " viñeta, "1. " numerada y 2
espacios por nivel de sangría. El editor del frontend (lib/textoFormato.ts)
lee y escribe este mismo formato.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pypdf import PdfReader  # noqa: E402

from modulos.documentos import pdf_generador as g  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion)))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


def _estilos():
    estilos, _, _ = g._construir_estilos({})
    return estilos


def _parrafos(texto):
    return g._renderizar_texto_libre({"texto": texto}, _estilos())


def _html(p):
    return p.text if hasattr(p, "text") else ""


def test_marcas_en_linea():
    print("\nMarcas dentro de una línea")
    f = g._aplicar_negrita_manual
    comprobar("**negrita** → <b>", f("una **palabra** fuerte") == "una <b>palabra</b> fuerte")
    comprobar("*cursiva* → <i>", f("una *palabra* inclinada") == "una <i>palabra</i> inclinada")
    comprobar("++subrayado++ → <u>", f("una ++palabra++ subrayada") == "una <u>palabra</u> subrayada")
    comprobar("Combinadas", f("**a** *b* ++c++") == "<b>a</b> <i>b</i> <u>c</u>")
    comprobar("'3 * 4 * 5' NO es cursiva", f("3 * 4 * 5") == "3 * 4 * 5")
    comprobar("Un * pegado a letras (a*b*c) NO es cursiva", f("a*b*c") == "a*b*c")
    comprobar("**negrita** no deja restos de cursiva", "<i>" not in f("**fuerte**"))
    comprobar("Ninguna marca cruza de línea", f("**abre\ncierra**") == "**abre\ncierra**")


def test_seguridad():
    print("\nNunca se puede meter HTML real")
    ps = _parrafos("<b>falso</b> y **<script>x</script>**")
    html = _html(ps[0])
    comprobar("Las etiquetas escritas salen escapadas", "&lt;b&gt;falso&lt;/b&gt;" in html, html)
    comprobar("Dentro de **…** también", "<b>&lt;script&gt;x&lt;/script&gt;</b>" in html, html)


def test_compatibilidad():
    print("\nUn texto viejo (solo **negrita** y •) se ve igual")
    ps = _parrafos("Motivo de **consulta**.\nSegunda línea.\n• uno\n- dos")
    comprobar("4 líneas → 1 párrafo + 2 viñetas", len(ps) == 3, f"{len(ps)}")
    comprobar("El párrafo une sus líneas con <br/>", _html(ps[0]) == "Motivo de <b>consulta</b>.<br/>Segunda línea.", _html(ps[0]))
    comprobar("Viñeta con punto", _html(ps[1]).startswith("•&nbsp;&nbsp;uno"))
    comprobar("Las viñetas de nivel 0 tienen la sangría de siempre (14)", ps[1].style.leftIndent == 14 and ps[1].style.firstLineIndent == -14)


def test_listas_y_sangria():
    print("\nListas numeradas y anidadas")
    ps = _parrafos("1. Primero\n2. Segundo\n  • detalle\n    • más adentro")
    comprobar("Numerada imprime su número", _html(ps[0]).startswith("1.&nbsp;&nbsp;Primero"))
    comprobar("Numerada con sangría francesa propia (18)", ps[0].style.leftIndent == 18 and ps[0].style.firstLineIndent == -18)
    comprobar("Nivel 1 más adentro que nivel 0", ps[2].style.leftIndent > ps[1].style.leftIndent - 4)
    comprobar("Nivel 2 más adentro que nivel 1", ps[3].style.leftIndent > ps[2].style.leftIndent)
    ps = _parrafos("Texto normal\n  texto con sangría")
    comprobar("Un párrafo con sangría va aparte y desplazado", len(ps) == 2 and ps[1].style.leftIndent > 0)


def test_vacio_y_pdf_real():
    print("\nVacío y PDF real")
    comprobar("Vacío → 'Pendiente de registro.'", "Pendiente" in _html(_parrafos("")[0]))
    contenido = {
        "documento": {"titulo": "Informe"}, "plantilla": {}, "institucion": {},
        "secciones": [{"tipo_seccion": "texto_libre", "titulo": "Motivo", "datos": {
            "texto": "Párrafo con **negrita**, *cursiva* y ++subrayado++.\n1. Uno\n  • Sub punto",
        }}],
    }
    texto = " ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(g.generar_pdf_documento(contenido).getvalue())).pages)
    comprobar("El PDF se genera y no muestra las marcas", "negrita" in texto and "**" not in texto and "++" not in texto, texto[:200])
    comprobar("Trae la lista numerada y la anidada", "1." in texto and "Sub punto" in texto)


if __name__ == "__main__":
    test_marcas_en_linea()
    test_seguridad()
    test_compatibilidad()
    test_listas_y_sangria()
    test_vacio_y_pdf_real()
    total, ok = len(_resultados), sum(1 for _, b in _resultados if b)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {ok}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(0 if ok == total else 1)
