"""E2E — URL de la firma con token (A3 de la revisión de seguridad previa al
piloto), contra el servidor real.

    uvicorn main:app --port 8010   (LOGIN_CAPTCHA_OBLIGATORIO=false)
    python -m tests.verificar_firma_token_e2e

Usa la cuenta superadmin de los e2e (E2E_SUPERADMIN_* vía tests/__init__.py):
sube SU PROPIA firma, la reemplaza y al final la borra (PATCH con ""), así
que la cuenta queda como estaba — no deja datos con prefijo que limpiar.
Necesita PUBLIC_BACKEND_URL configurada (sin ella la subida da 503 por
diseño y el test lo informa y termina).
"""

import io
import os
import sys

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

API = "http://127.0.0.1:8010/api"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def _png(color):
    buffer = io.BytesIO()
    Image.new("RGB", (60, 20), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _ruta_local(url_publica):
    """La URL guardada apunta a PUBLIC_BACKEND_URL (el túnel/dominio
    público); aquí se pide la misma ruta al servidor local."""
    return "http://127.0.0.1:8010" + url_publica[url_publica.index("/api/"):]


def main():
    print("=" * 72)
    print("E2E — URL de la firma con token")
    print("=" * 72)
    r = requests.post(f"{API}/auth/login", data={
        "username": os.environ["SUPERADMIN_EMAIL"], "password": os.environ["SUPERADMIN_PASSWORD"],
    }, timeout=30)
    if r.status_code != 200:
        print(f"  No se pudo iniciar sesión ({r.status_code}).")
        return 1
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    yo = requests.get(f"{API}/auth/me", headers=h, timeout=30).json()
    uid = yo["id"]
    firma_original = yo.get("firma_imagen_url")

    azul, rojo = _png((0, 0, 140)), _png((140, 0, 0))
    r1 = requests.post(f"{API}/auth/usuarios/{uid}/firma",
                       files={"archivo": ("firma.png", azul, "image/png")}, headers=h, timeout=30)
    if r1.status_code == 503:
        print("  PUBLIC_BACKEND_URL no está configurada: la subida da 503 por diseño. Nada que probar.")
        return 0
    try:
        comprobar("subir firma -> 200", r1.status_code == 200, r1.text[:200])
        url1 = r1.json()["firma_imagen_url"]
        token1 = url1.rsplit("/", 1)[-1]
        comprobar("la URL guardada lleva /firma/{token de 64 hex}",
                  f"/api/auth/usuarios/{uid}/firma/" in url1 and len(token1) == 64)

        g = requests.get(_ruta_local(url1), timeout=30)
        comprobar("GET sin sesión con el token -> 200 y los mismos bytes",
                  g.status_code == 200 and g.content == azul)
        comprobar("Cache-Control: private, no-store", g.headers.get("cache-control") == "private, no-store")

        viejo = requests.get(f"{API}/auth/usuarios/{uid}/firma", timeout=30)
        comprobar("GET a la ruta vieja (solo id) -> ya no sirve la firma",
                  viejo.status_code in (404, 405) and viejo.content != azul, str(viejo.status_code))
        otro = requests.get(f"{API}/auth/usuarios/{uid}/firma/{'0' * 64}", timeout=30)
        comprobar("token inventado -> 404", otro.status_code == 404)

        r2 = requests.post(f"{API}/auth/usuarios/{uid}/firma",
                           files={"archivo": ("firma.png", rojo, "image/png")}, headers=h, timeout=30)
        url2 = r2.json()["firma_imagen_url"]
        comprobar("re-subir -> 200 con otro token", r2.status_code == 200 and url2 != url1)
        comprobar("la URL anterior deja de servirse -> 404",
                  requests.get(_ruta_local(url1), timeout=30).status_code == 404)
        g2 = requests.get(_ruta_local(url2), timeout=30)
        comprobar("la URL nueva sirve la firma nueva", g2.status_code == 200 and g2.content == rojo)

        b = requests.patch(f"{API}/auth/usuarios/{uid}", json={"firma_imagen_url": ""}, headers=h, timeout=30)
        comprobar("borrar la firma (PATCH con '') -> 200", b.status_code == 200, b.text[:200])
        comprobar("tras borrarla, su URL -> 404", requests.get(_ruta_local(url2), timeout=30).status_code == 404)
    finally:
        # Deja la cuenta como estaba.
        requests.patch(f"{API}/auth/usuarios/{uid}", json={"firma_imagen_url": firma_original or ""},
                       headers=h, timeout=30)

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO E2E FIRMA CON TOKEN: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
