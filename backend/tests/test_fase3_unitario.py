"""Pruebas unitarias de la Fase 3 — robustez del backend.

    python tests/test_fase3_unitario.py

No necesitan la base de datos ni el servidor. Incluyen un ataque SSRF REAL
contra un servidor HTTP levantado en 127.0.0.1 para demostrar que el
generador de PDF no llega a hacerle ni una sola petición.
"""

import http.server
import io
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from core import url_segura  # noqa: E402
from core.url_segura import UrlNoPermitida, descargar_logo_seguro, validar_url_logo  # noqa: E402
from core.algoritmo import calcular_resultados  # noqa: E402
from core import pdf_generator  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def resolvedor_fijo(*ips):
    """Resolvedor falso: permite probar sin red qué pasa con cada IP."""
    def _resolver(host, puerto, type=None):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 (ip, puerto)) for ip in ips]
    return _resolver


def rechaza(url, resolver=socket.getaddrinfo):
    try:
        validar_url_logo(url, resolver=resolver)
        return False, "aceptada"
    except UrlNoPermitida as exc:
        return True, str(exc)


# ======================================================================
def test_c11_ssrf_validacion():
    print("\nC-11 · Validación anti-SSRF (antes de cualquier petición HTTP)")

    casos_internos = [
        ("https://127.0.0.1/logo.png", "loopback IPv4"),
        ("https://localhost/logo.png", "localhost"),
        ("https://169.254.169.254/latest/meta-data/", "endpoint de metadata de la nube"),
        ("https://[::1]/logo.png", "loopback IPv6"),
        ("https://10.0.0.5/logo.png", "privada 10/8"),
        ("https://172.16.3.4/logo.png", "privada 172.16/12"),
        ("https://192.168.1.10/logo.png", "privada 192.168/16"),
        ("https://100.64.0.1/logo.png", "CGNAT 100.64/10"),
        ("https://0.0.0.0/logo.png", "0.0.0.0"),
        ("https://2130706433/logo.png", "127.0.0.1 en decimal"),
        ("https://[::ffff:127.0.0.1]/logo.png", "loopback disfrazada de IPv6"),
        ("https://[fe80::1]/logo.png", "link-local IPv6"),
    ]
    for url, descripcion in casos_internos:
        ok, motivo = rechaza(url)
        comprobar(f"Rechaza {descripcion}", ok, motivo[:70])

    for url, descripcion in [
        ("http://example.com/logo.png", "http sin cifrar"),
        ("file:///etc/passwd", "file://"),
        ("gopher://example.com/", "gopher://"),
        ("https://example.com:8443/logo.png", "puerto distinto de 443"),
        ("https://usuario:clave@example.com/logo.png", "credenciales en la URL"),
        ("", "URL vacía"),
    ]:
        ok, motivo = rechaza(url, resolver=resolvedor_fijo("93.184.215.14"))
        comprobar(f"Rechaza {descripcion}", ok, motivo[:70])

    ok, motivo = rechaza("https://logo.colegio-ejemplo.pe/escudo.png",
                         resolver=resolvedor_fijo("93.184.215.14"))
    comprobar("ACEPTA una URL https pública", not ok, motivo)
    host, ip, ruta = validar_url_logo("https://logo.colegio-ejemplo.pe/escudo.png?v=2",
                                      resolver=resolvedor_fijo("93.184.215.14"))
    comprobar("Devuelve la IP validada y la ruta para conectar a ella",
              (host, ip, ruta) == ("logo.colegio-ejemplo.pe", "93.184.215.14", "/escudo.png?v=2"))

    ok, motivo = rechaza("https://dominio-trampa.test/logo.png",
                         resolver=resolvedor_fijo("93.184.215.14", "127.0.0.1"))
    comprobar("Rechaza si UNA de las IP resueltas es interna (DNS mixto)", ok, motivo[:60])

    ok, motivo = rechaza("https://metadata.trampa.test/",
                         resolver=resolvedor_fijo("169.254.169.254"))
    comprobar("Rechaza un dominio público que resuelve a la metadata", ok, motivo[:60])


def test_c11_sin_redirecciones():
    print("\nC-11 · La descarga no sigue redirecciones ni acepta no-imágenes")

    class RespuestaFalsa:
        def __init__(self, estado, tipo, cuerpo=b"\x89PNG"):
            self.status, self._tipo, self._cuerpo = estado, tipo, cuerpo
        def getheader(self, nombre, defecto=None):
            if nombre.lower() == "content-type":
                return self._tipo
            if nombre.lower() == "location":
                return "https://169.254.169.254/latest/meta-data/"
            return defecto
        def read(self, n):
            return self._cuerpo[:n]

    class ConexionFalsa:
        def __init__(self, respuesta):
            self.respuesta, self.pedidas = respuesta, []
        def request(self, metodo, ruta, headers=None):
            self.pedidas.append(ruta)
        def getresponse(self):
            return self.respuesta
        def close(self):
            pass

    original = url_segura._abrir_conexion
    try:
        for estado, tipo, cuerpo, esperado, nombre in [
            (302, "text/html", b"", None, "Un 302 hacia la metadata NO se sigue"),
            (200, "text/html", b"<html>", None, "Un Content-Type que no es imagen se descarta"),
            (200, "image/png", b"x" * (url_segura.TAMANO_MAXIMO_LOGO + 10), None,
             "Un logo de más de 2 MiB se descarta"),
            (200, "image/png", b"\x89PNG-ok", b"\x89PNG-ok", "Una imagen válida sí se descarga"),
        ]:
            conexiones = []
            def abrir(host, ip, timeout, _r=RespuestaFalsa(estado, tipo, cuerpo)):
                c = ConexionFalsa(_r)
                conexiones.append((host, ip, c))
                return c
            url_segura._abrir_conexion = abrir
            resultado = descargar_logo_seguro("https://logo.publico.test/a.png",
                                              resolver=resolvedor_fijo("93.184.215.14"))
            comprobar(nombre, resultado == esperado,
                      f"{len(conexiones)} conexión(es), resultado={'bytes' if resultado else None}")
            if conexiones:
                comprobar(f"  ...y se conectó a la IP validada, no al nombre",
                          conexiones[0][1] == "93.184.215.14")
    finally:
        url_segura._abrir_conexion = original


def test_c11_ataque_real_local():
    print("\nC-11 · Ataque REAL: un servidor en 127.0.0.1 que no debe recibir nada")

    peticiones = []

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            peticiones.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"\x89PNG\r\n\x1a\n")
        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manejador)
    puerto = servidor.server_address[1]
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        urls = [
            f"http://127.0.0.1:{puerto}/secreto",
            f"https://127.0.0.1:{puerto}/secreto",
            f"http://localhost:{puerto}/secreto",
        ]
        for url in urls:
            comprobar(f"descargar_logo_seguro devuelve None para {url.split('/secreto')[0]}",
                      descargar_logo_seguro(url) is None)

        # El vector real: el generador de PDF que usa el endpoint PÚBLICO
        pdf = pdf_generator.generar_pdf({
            "institucion": {"nombre": "Colegio", "logo_url": f"http://127.0.0.1:{puerto}/metadata"},
            "nombre_prueba": "Prueba",
            "filiacion": {"apellidos_nombres": "Alumno"},
            "dimensiones": [{"nombre": "Ansiedad", "puntaje": 6.0, "nivel": "Alto", "es_alerta": False}],
        })
        comprobar("El PDF se genera igualmente, sin logo", pdf.getvalue()[:4] == b"%PDF")
        comprobar("El servidor interno NO recibió ninguna petición",
                  peticiones == [], f"peticiones: {peticiones}")
    finally:
        servidor.shutdown()


# ======================================================================
def test_c10_pdf_concurrente():
    print("\nC-10 · Gráficos y PDFs concurrentes sin interferencias")

    conjuntos = [
        {f"Dim{i}-{j}": float(i * 3 + j) + 0.25 * j for j in range(4)}
        for i in range(8)
    ]
    # Referencia generada en serie: lo que DEBE salir para cada conjunto
    referencias = [pdf_generator.generar_grafico_barras(c, f"Perfil {i}").getvalue()
                   for i, c in enumerate(conjuntos)]

    resultados = [None] * len(conjuntos)
    errores = []
    barrera = threading.Barrier(len(conjuntos))

    def generar(i):
        try:
            barrera.wait()
            resultados[i] = pdf_generator.generar_grafico_barras(conjuntos[i], f"Perfil {i}").getvalue()
        except Exception as exc:  # noqa: BLE001
            errores.append(f"{type(exc).__name__}: {exc}")

    hilos = [threading.Thread(target=generar, args=(i,)) for i in range(len(conjuntos))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    comprobar("8 gráficos simultáneos sin excepciones", not errores, "; ".join(errores[:2]))
    iguales = sum(1 for a, b in zip(resultados, referencias) if a == b)
    comprobar("Cada gráfico concurrente es idéntico a su referencia en serie",
              iguales == len(conjuntos), f"{iguales}/{len(conjuntos)} idénticos byte a byte")
    comprobar("Y los 8 gráficos son distintos entre sí (no se mezclaron)",
              len(set(resultados)) == len(conjuntos))

    pdfs, errores_pdf = [None] * 4, []
    barrera_pdf = threading.Barrier(4)

    def generar_pdf(i):
        try:
            barrera_pdf.wait()
            pdfs[i] = pdf_generator.generar_pdf({
                "nombre_prueba": f"Prueba {i}",
                "filiacion": {"apellidos_nombres": f"Alumno {i}"},
                "dimensiones": [{"nombre": k, "puntaje": v, "nivel": None, "es_alerta": False} for k, v in conjuntos[i].items()],
            }).getvalue()
        except Exception as exc:  # noqa: BLE001
            errores_pdf.append(str(exc))

    hilos = [threading.Thread(target=generar_pdf, args=(i,)) for i in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    comprobar("4 PDFs completos simultáneos, todos válidos",
              not errores_pdf and all(p and p[:4] == b"%PDF" for p in pdfs),
              "; ".join(errores_pdf[:2]))

    import ast
    import inspect
    arbol = ast.parse(inspect.getsource(pdf_generator))
    usa_pyplot = any(
        (isinstance(n, ast.ImportFrom) and n.module and "pyplot" in n.module)
        or (isinstance(n, ast.Import) and any("pyplot" in a.name for a in n.names))
        for n in ast.walk(arbol)
    )
    comprobar("pdf_generator ya no importa matplotlib.pyplot", not usa_pyplot)


# ======================================================================
def test_c1_decimales():
    print("\nC-1 · Puntajes decimales")

    class P:
        escala_minima, escala_maxima, modo_calculo, nombre_tecnico = 0, 3, "likert_suma", "P"

    class I:
        def __init__(self, i, inv):
            self.id, self.es_inverso = i, inv

    class R:
        def __init__(self, p, d, v):
            self.pregunta_id, self.dimension, self.valor_raw = p, d, v

    res = calcular_resultados("P", [R(1, 1, 0.5), R(2, 1, 1.25)], [I(1, False), I(2, False)], P())
    comprobar("Suma de ítems ponderados: 0.5 + 1.25 = 1.75",
              abs(res["puntajes_brutos"][1] - 1.75) < 1e-9, str(res["puntajes_brutos"][1]))

    res = calcular_resultados("P", [R(1, 1, 0.75)], [I(1, True)], P())
    comprobar("Inversión con decimales: (0+3) - 0.75 = 2.25",
              abs(res["puntajes_brutos"][1] - 2.25) < 1e-9, str(res["puntajes_brutos"][1]))

    for valor, esperado in [(6.0, "6"), (5.25, "5.25"), (1.7500, "1.75"),
                            (0.3333, "0.3333"), (1234567.5, "1234567.5"), (None, "-")]:
        comprobar(f"El PDF muestra {valor!r} como '{esperado}'",
                  pdf_generator.formatear_puntaje(valor) == esperado,
                  pdf_generator.formatear_puntaje(valor))

    from modulos.educativo import models as m, schemas as s
    for modelo, columna in [(m.OpcionRespuesta, "valor_puntuacion"),
                            (m.RespuestaAlumno, "puntaje_obtenido"),
                            (m.ResultadoDimension, "puntaje_directo"),
                            (m.Baremo, "puntaje_minimo"), (m.Baremo, "puntaje_maximo")]:
        tipo = modelo.__table__.c[columna].type
        comprobar(f"{modelo.__tablename__}.{columna} es NUMERIC(12,4)",
                  type(tipo).__name__ == "Numeric" and (tipo.precision, tipo.scale) == (12, 4))
    comprobar("El schema de resultado admite decimales",
              s.ResultadoDimensionBase(inscripcion_id=1, dimension_id=1, puntaje_directo=1.75).puntaje_directo == 1.75)
    comprobar("El schema de baremo admite límites decimales",
              s.BaremoCreate(dimension_id=1, puntaje_minimo=1.5, puntaje_maximo=1.99, nivel="x").puntaje_maximo == 1.99)


# ======================================================================
def test_c17_institucion():
    print("\nC-17 · Licencia y límites al crear una institución")
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from modulos.instituciones import schemas as s

    por_defecto = s.InstitucionCreate(nombre="Colegio")
    comprobar("Por defecto: plan activo, sin caducidad, límite 5",
              (por_defecto.plan_activo, por_defecto.fecha_vencimiento_licencia,
               por_defecto.limite_pruebas_mensual_por_alumno) == (True, None, 5))

    con_offset = s.InstitucionCreate(nombre="C", fecha_vencimiento_licencia="2027-03-01T00:00:00-05:00")
    comprobar("La fecha de licencia se normaliza a UTC sin zona",
              con_offset.fecha_vencimiento_licencia == datetime(2027, 3, 1, 5, 0))

    for valor in (0, -3):
        try:
            s.InstitucionCreate(nombre="C", limite_pruebas_mensual_por_alumno=valor)
            comprobar(f"Rechaza un límite mensual de {valor}", False)
        except ValidationError:
            comprobar(f"Rechaza un límite mensual de {valor}", True)

    comprobar("La respuesta ya no inventa un límite de 100",
              s.InstitucionResponse.model_fields["limite_pruebas_mensual_por_alumno"].is_required())


def test_c12_limites_declarados():
    print("\nC-12 · Límites declarados en todos los endpoints públicos del examen")
    import inspect
    from core.limiter import LIMITES_EXAMEN
    fuente = inspect.getsource(__import__("modulos.educativo.router", fromlist=["router"]))
    for nombre in LIMITES_EXAMEN:
        comprobar(f"'{nombre}' tiene límite por token y por IP",
                  f'limite_token("{nombre}")' in fuente and f'limite_ip("{nombre}"), scope=ambito_ip("{nombre}")' in fuente)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — FASE 3")
    print("=" * 72)
    test_c11_ssrf_validacion()
    test_c11_sin_redirecciones()
    test_c11_ataque_real_local()
    test_c10_pdf_concurrente()
    test_c1_decimales()
    test_c17_institucion()
    test_c12_limites_declarados()

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
