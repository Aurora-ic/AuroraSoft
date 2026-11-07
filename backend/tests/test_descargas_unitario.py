"""M7 de la revisión de seguridad (sesión 2026-11-07): nombre de descarga
(Content-Disposition, RFC 6266/5987) y tipo de contenido por los bytes —
ver core/descargas.py. Sin BD ni servidor.

    python -m tests.test_descargas_unitario
"""
import io
import os
import re
import sys
from urllib.parse import unquote

from fastapi.responses import StreamingResponse

from core.descargas import LARGO_MAXIMO_NOMBRE, content_disposition, tipo_contenido_por_firma

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def partes(valor):
    ascii_ = re.search(r'filename="([^"]*)"', valor)
    utf8 = re.search(r"filename\*=UTF-8''([^;]*)", valor)
    return (ascii_.group(1) if ascii_ else None), (unquote(utf8.group(1)) if utf8 else None)


def test_nombres():
    print("\n[1] content_disposition con nombres reales y hostiles")
    v = content_disposition("informe_123.pdf")
    comprobar("nombre ASCII simple: solo filename=, sin filename*", v == 'attachment; filename="informe_123.pdf"', v)

    v = content_disposition("informe_José_Peña_v1.pdf")
    a, u = partes(v)
    comprobar("tildes: filename ASCII sin tildes", a == "informe_Jose_Pena_v1.pdf", a)
    comprobar("tildes: filename* conserva el nombre real", u == "informe_José_Peña_v1.pdf", u)

    casos = {
        "apóstrofo tipográfico (antes: 500)": "informe_O’Brien_Ana.pdf",
        "letra fuera de Latin-1 (antes: 500)": "firma_Łukasz.png",
        "emoji": "evidencia 📄 firmada.pdf",
        "comillas": 'acta "firmada" final.pdf',
        "salto de línea (inyección de cabecera)": "acta\r\nSet-Cookie: x=1.pdf",
        "ruta con carpetas": "../../etc/passwd",
        "ruta de Windows": "C:\\Users\\Ana\\Escritorio\\consentimiento.pdf",
        "punto y coma": "a; filename=otro.exe.pdf",
        "vacío": "",
        "None": None,
        "solo puntos": "...",
    }
    for etiqueta, nombre in casos.items():
        v = content_disposition(nombre, "evidencia")
        a, u = partes(v)
        try:
            StreamingResponse(io.BytesIO(b""), headers={"Content-Disposition": v})
            construye = True
        except Exception as exc:  # noqa: BLE001
            construye = repr(exc)
        comprobar(f"{etiqueta}: la respuesta se construye (sin 500)", construye is True, construye)
        comprobar(f"{etiqueta}: la cabecera es ASCII puro", v.isascii(), v)
        comprobar(f"{etiqueta}: sin \\r, \\n ni comillas dentro del nombre",
                  "\r" not in v and "\n" not in v and a is not None and '"' not in a, v)
        comprobar(f"{etiqueta}: sin barras (no hay carpetas)",
                  "/" not in (a or "") and "/" not in (u or "") and "\\" not in (u or ""), (a, u))

    a, u = partes(content_disposition("../../etc/passwd"))
    comprobar("ruta: se queda solo con el último tramo", a == "passwd", a)
    a, u = partes(content_disposition("C:\\Users\\Ana\\Escritorio\\consentimiento.pdf"))
    comprobar("ruta de Windows: solo el nombre", a == "consentimiento.pdf", a)
    a, _ = partes(content_disposition("", "evidencia"))
    comprobar("vacío → nombre por defecto", a == "evidencia", a)
    v = content_disposition("a; filename=otro.exe.pdf")
    a, u = partes(v)
    comprobar("el ';' no abre un parámetro nuevo",
              v.count('filename="') == 1 and ";" not in (a or "") and ";" not in (u or ""), v)
    a, u = partes(content_disposition("ñ" * 400 + ".pdf"))
    comprobar("nombre larguísimo: se recorta y conserva la extensión",
              u is not None and len(u) <= LARGO_MAXIMO_NOMBRE and u.endswith(".pdf"), len(u or ""))
    comprobar("disposición inline cuando se pide",
              content_disposition("x.pdf", disposicion="inline").startswith("inline; "))


def test_tipo_por_firma():
    print("\n[2] tipo_contenido_por_firma: por los bytes, nunca por lo que dijo el cliente")
    comprobar("PDF", tipo_contenido_por_firma(b"%PDF-1.7\n...") == "application/pdf")
    comprobar("PNG", tipo_contenido_por_firma(b"\x89PNG\r\n\x1a\n....") == "image/png")
    comprobar("JPEG", tipo_contenido_por_firma(b"\xff\xd8\xff\xe0....") == "image/jpeg")
    comprobar("HTML → octet-stream", tipo_contenido_por_firma(b"<html><script>alert(1)</script>") == "application/octet-stream")
    comprobar("SVG → octet-stream", tipo_contenido_por_firma(b"<svg onload=alert(1)>") == "application/octet-stream")
    comprobar("PDF con basura delante → octet-stream", tipo_contenido_por_firma(b"<html>%PDF-1.7") == "application/octet-stream")
    comprobar("vacío → octet-stream", tipo_contenido_por_firma(b"") == "application/octet-stream")
    comprobar("None → octet-stream", tipo_contenido_por_firma(None) == "application/octet-stream")


def test_fuentes():
    print("\n[3] Nadie vuelve a armar Content-Disposition a mano")
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    culpables = []
    for carpeta in ("modulos", "core", "tareas"):
        for base, _, archivos in os.walk(os.path.join(raiz, carpeta)):
            for nombre in archivos:
                if nombre.endswith(".py") and nombre != "descargas.py":
                    ruta = os.path.join(base, nombre)
                    with open(ruta, encoding="utf-8") as f:
                        if re.search(r"filename\s*=", f.read()):
                            culpables.append(os.path.relpath(ruta, raiz))
    comprobar("ningún 'filename=' fuera de core/descargas.py", not culpables, culpables)

    with open(os.path.join(raiz, "modulos", "superadmin", "router.py"), encoding="utf-8") as f:
        fuente = f.read()
    comprobar("las dos descargas de evidencia usan el tipo por firma",
              fuente.count("media_type=tipo_contenido_por_firma(contenido)") == 2)
    comprobar("ninguna descarga sirve el content_type guardado",
              "media_type=consentimiento.evidencia_content_type" not in fuente
              and "media_type=entrada.content_type" not in fuente)


if __name__ == "__main__":
    test_nombres()
    test_tipo_por_firma()
    test_fuentes()
    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO DESCARGAS SEGURAS: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(1 if RESULTADOS["fallo"] else 0)
