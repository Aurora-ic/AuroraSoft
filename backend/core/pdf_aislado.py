# core/pdf_aislado.py
#
# 🆕 (sesión 2026-11-05, M1 de la revisión de seguridad previa al piloto)
# Todo PDF que AuroraSoft no generó (evidencia subida por un usuario) se abre
# con pypdf en un PROCESO HIJO, con tiempo máximo y — en Linux — tope de
# memoria. Nunca en el proceso web ni en el worker directamente.
#
# Por qué: pypdf es Python puro y sus avisos de seguridad conocidos son de
# denegación de servicio (bucles infinitos, consumo de memoria) con PDFs
# armados a propósito. Hasta ahora la evidencia PDF se fusionaba con pypdf
# dentro del mismo proceso: en el worker de Celery (sin time_limit) y,
# además, DENTRO de la petición web de `reemitir`/`reprocesar`
# (modulos/educativo/router.py), donde un time_limit de Celery no protege.
# Un PDF malicioso dejaba colgado un hilo del servidor o un worker.
#
# Se usa en dos lugares:
#   - al subir (`validar_pdf_para_subida`): cabecera `%PDF-` y una pasada
#     completa de copia de páginas — lo mismo que hará la fusión —, así un
#     PDF cifrado, vacío, dañado o enorme se rechaza con 400 en el momento.
#   - al fusionar (`inspeccionar_pdf` + `fusionar_pdfs`, desde
#     core/pdf_generator._fusionar_anexos_pdf):
#     cada anexo se revisa por separado; el que no pasa se omite y su
#     portada lo dice, en vez de tumbar el informe entero.
#
# El hijo se lanza con `python -m core.pdf_aislado` (cwd = backend/) y habla
# por stdin/stdout en JSON con los bytes en base64.
import base64
import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("aurorasoft")

DIRECTORIO_BACKEND = Path(__file__).resolve().parent.parent
LIMITE_SEGUNDOS_POR_PDF = 30
LIMITE_SEGUNDOS_FUSION = 90
MAXIMO_PAGINAS_ANEXO = 200
LIMITE_MEMORIA_HIJO_BYTES = 1024 * 1024 * 1024  # 1 GiB (solo se aplica en Linux)
CABECERA_PDF = b"%PDF-"
# Variable de módulo (no constante dentro de la función) para que el test
# pueda reemplazarla por un hijo que se cuelga o se cae a propósito.
COMANDO_HIJO = [sys.executable, "-m", "core.pdf_aislado"]


class PdfNoValido(ValueError):
    """El PDF no se puede usar. El mensaje es apto para el usuario."""


# ------------------------------------------------------------------
# Lado del proceso hijo
# ------------------------------------------------------------------
def _copiar_paginas(writer, datos: bytes) -> int:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(datos))
    if lector.is_encrypted:
        raise PdfNoValido("El PDF está protegido con contraseña. Súbelo sin protección.")
    paginas = len(lector.pages)
    if paginas == 0:
        raise PdfNoValido("El PDF no tiene páginas.")
    if paginas > MAXIMO_PAGINAS_ANEXO:
        raise PdfNoValido(f"El PDF tiene {paginas} páginas. El máximo es {MAXIMO_PAGINAS_ANEXO}.")
    for pagina in lector.pages:
        writer.add_page(pagina)
    return paginas


def _operar(pedido: dict) -> dict:
    from pypdf import PdfWriter

    if pedido["operacion"] == "inspeccionar":
        writer = PdfWriter()
        paginas = _copiar_paginas(writer, base64.b64decode(pedido["pdf"]))
        writer.write(io.BytesIO())  # la misma serialización que hará la fusión
        return {"ok": True, "paginas": paginas}

    if pedido["operacion"] == "fusionar":
        writer = PdfWriter()
        for parte in pedido["partes"]:
            _copiar_paginas_sin_tope(writer, base64.b64decode(parte))
        salida = io.BytesIO()
        writer.write(salida)
        return {"ok": True, "pdf": base64.b64encode(salida.getvalue()).decode()}

    raise ValueError(f"operación desconocida: {pedido['operacion']}")


def _copiar_paginas_sin_tope(writer, datos: bytes) -> None:
    """Para las partes de la fusión: el informe propio y las portadas no
    tienen tope de páginas, y los anexos ya pasaron `inspeccionar`."""
    from pypdf import PdfReader

    for pagina in PdfReader(io.BytesIO(datos)).pages:
        writer.add_page(pagina)


def _principal() -> int:
    try:
        pedido = json.loads(sys.stdin.buffer.read())
        respuesta = _operar(pedido)
    except PdfNoValido as exc:
        respuesta = {"ok": False, "motivo": str(exc)}
    except Exception as exc:  # noqa: BLE001 — cualquier fallo del parser es "PDF dañado"
        respuesta = {"ok": False, "motivo": "El PDF está dañado o no se puede leer.", "tecnico": repr(exc)[:300]}
    sys.stdout.write(json.dumps(respuesta))
    return 0


# ------------------------------------------------------------------
# Lado del proceso padre
# ------------------------------------------------------------------
def _limitar_memoria_del_hijo():  # pragma: no cover — solo corre en Linux, dentro del hijo
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (LIMITE_MEMORIA_HIJO_BYTES, LIMITE_MEMORIA_HIJO_BYTES))


def _ejecutar_en_hijo(pedido: dict, limite_segundos: int) -> dict:
    try:
        proceso = subprocess.run(
            COMANDO_HIJO,
            input=json.dumps(pedido).encode(),
            capture_output=True,
            timeout=limite_segundos,
            cwd=str(DIRECTORIO_BACKEND),
            preexec_fn=_limitar_memoria_del_hijo if os.name == "posix" else None,
        )
    except subprocess.TimeoutExpired:
        raise PdfNoValido("El PDF tardó demasiado en procesarse; puede estar dañado.")
    try:
        respuesta = json.loads(proceso.stdout or b"{}")
    except ValueError:
        respuesta = {}
    if not respuesta.get("ok"):
        if respuesta.get("tecnico") or not respuesta:
            logger.warning(
                "PDF rechazado por el proceso aislado (código %s): %s %s",
                proceso.returncode, respuesta.get("tecnico", ""), (proceso.stderr or b"")[-300:],
            )
        raise PdfNoValido(respuesta.get("motivo") or "El PDF está dañado o no se puede leer.")
    return respuesta


def inspeccionar_pdf(contenido: bytes) -> int:
    """Devuelve el número de páginas o lanza PdfNoValido."""
    if not contenido.startswith(CABECERA_PDF):
        raise PdfNoValido("El archivo no es un PDF.")
    return _ejecutar_en_hijo(
        {"operacion": "inspeccionar", "pdf": base64.b64encode(contenido).decode()},
        LIMITE_SEGUNDOS_POR_PDF,
    )["paginas"]


def validar_pdf_para_subida(contenido: bytes) -> str:
    """Para los endpoints de subida. Devuelve el content-type con el que se
    guarda ('application/pdf'); 400 si no pasa."""
    from fastapi import HTTPException, status

    try:
        inspeccionar_pdf(contenido)
    except PdfNoValido as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return "application/pdf"


def fusionar_pdfs(partes: list[bytes]) -> bytes:
    """Concatena PDFs (el informe propio, portadas y anexos YA inspeccionados)
    en el proceso hijo. Lanza PdfNoValido si algo falla o se pasa de tiempo."""
    respuesta = _ejecutar_en_hijo(
        {"operacion": "fusionar", "partes": [base64.b64encode(p).decode() for p in partes]},
        LIMITE_SEGUNDOS_FUSION,
    )
    return base64.b64decode(respuesta["pdf"])


if __name__ == "__main__":
    sys.exit(_principal())
