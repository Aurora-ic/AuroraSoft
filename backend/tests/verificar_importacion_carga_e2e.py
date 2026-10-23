"""Verificación funcional — importación masiva de estudiantes BAJO CARGA
(tiempo, memoria del servidor, comportamiento con errores/duplicados/filas
vacías). Puramente de verificación: no modifica código de producción.

Cubre:
  1. Un archivo de 5.000 filas es RECHAZADO (el límite documentado es 2.000,
     modulos/superadmin/importacion_estudiantes.py:48) — se mide cuánto tarda
     ese rechazo y si el servidor se resiente de memoria al leerlo igual.
  2. Un archivo EN EL LÍMITE real (2.000 filas: ~1900 altas válidas, 50
     duplicadas dentro del archivo, 30 con un grado inexistente, 20 filas
     completamente vacías intercaladas) se valida y se confirma de verdad,
     midiendo tiempo y memoria del proceso servidor en cada paso.
  3. Verifica que el resultado de /validar y /confirmar clasifica cada fila
     correctamente y que la escritura fue atómica (solo se aplicaron las
     filas 'nuevo', ninguna 'duplicado'/'error' tocó la base).

Uso:
    uvicorn main:app --port 8010          (con EMAIL_USUARIO/EMAIL_PASSWORD vacíos)
    python tests/verificar_importacion_carga_e2e.py
    python tests/verificar_importacion_carga_e2e.py --limpiar
"""

import argparse
import io
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from openpyxl import Workbook
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZXLSCARGA"
API = "http://127.0.0.1:8010/api"
MOTOR = None
_resultados = []


def comprobar(nombre, condicion, endpoint="", detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else "") + (f"   [{endpoint}]" if endpoint else ""))
    return bool(condicion)


def exigir(r, esperado, contexto):
    if r.status_code != esperado:
        print(f"\n!! {contexto}: esperaba {esperado}, recibió {r.status_code}\n   {r.text[:500]}")
        sys.exit(1)
    return r.json() if r.text else None


def sql_uno(consulta, **p):
    with MOTOR.connect() as c:
        return c.execute(text(consulta), p).fetchone()


def pedir(metodo, url, contexto="", **kw):
    for _ in range(8):
        r = metodo(url, timeout=180, **kw)
        if r.status_code != 429 or "/auth/" not in url:
            return r
        print(f"    (429 en {contexto}; esperando 13s)")
        time.sleep(13)
    return r


def login(email, clave):
    return pedir(requests.post, f"{API}/auth/login", "login", data={"username": email, "password": clave})


# ==========================================
# Memoria del PROCESO SERVIDOR (Windows) — sin dependencias nuevas
# ==========================================
def _pid_escuchando_en(puerto):
    salida = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
    for linea in salida.splitlines():
        if f":{puerto}" in linea and "LISTENING" in linea:
            return int(linea.strip().split()[-1])
    return None


def _working_set_mb(pid):
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid}).WorkingSet64"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        return int(salida) / (1024 * 1024)
    except Exception:
        return None


class MonitorMemoria:
    """Muestrea el WorkingSet del proceso servidor cada ~150ms mientras dura
    una petición HTTP en curso, para poder reportar el PICO durante la
    carga, no solo antes/después."""
    def __init__(self, pid):
        self.pid = pid
        self.muestras = []
        self._detener = threading.Event()
        self._hilo = None

    def _loop(self):
        while not self._detener.is_set():
            m = _working_set_mb(self.pid)
            if m is not None:
                self.muestras.append(m)
            time.sleep(0.15)

    def __enter__(self):
        self._hilo = threading.Thread(target=self._loop, daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *a):
        self._detener.set()
        self._hilo.join(timeout=2)

    @property
    def pico_mb(self):
        return max(self.muestras) if self.muestras else None

    @property
    def base_mb(self):
        return self.muestras[0] if self.muestras else None


def construir_excel_carga(n_limpias, n_duplicadas, n_error_grado, n_vacias, sello, nivel, grado_ok, seccion_ok, anio):
    """Genera el .xlsx de carga en memoria (nunca se toca disco)."""
    wb = Workbook()
    ws = wb.active
    ws.append(["codigo_institucional", "nombres", "apellidos", "documento_identidad",
               "fecha_nacimiento", "genero", "nivel_educativo", "grado", "seccion",
               "turno", "anio_escolar"])

    codigos_limpios = []
    for i in range(n_limpias):
        codigo = f"{PREFIJO}-{sello}-{i:05d}"
        codigos_limpios.append(codigo)
        ws.append([codigo, "Alumno", f"Carga{i}", f"{sello}{i:06d}", "2011-01-01", "Femenino",
                   nivel, grado_ok, seccion_ok, "", str(anio)])

    for i in range(n_duplicadas):
        # Repite un código YA usado arriba -> "duplicado dentro del archivo".
        codigo_repetido = codigos_limpios[i % len(codigos_limpios)]
        ws.append([codigo_repetido, "Alumno", "Duplicado", "", "", "", "", "", "", "", ""])

    for i in range(n_error_grado):
        ws.append([f"{PREFIJO}-{sello}-ERR-{i:05d}", "Alumno", "ConGradoInexistente", "", "", "",
                   nivel, "99° Grado Inexistente", "Z", "", str(anio)])

    for _ in range(n_vacias):
        ws.append([None, None, None, None, None, None, None, None, None, None, None])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer, codigos_limpios


def main(url_base):
    global API, MOTOR
    API = url_base.rstrip("/") + "/api"
    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    sello = datetime.utcnow().strftime("%H%M%S")

    pid_servidor = _pid_escuchando_en(int(url_base.rsplit(":", 1)[1]))
    comprobar("[montaje] Se localizó el proceso del servidor (para medir su memoria real)",
              pid_servidor is not None, "netstat -ano (diagnóstico local, no HTTP)", f"pid={pid_servidor}")

    print("\n0 · Montaje")
    tok_super = exigir(login(os.getenv("SUPERADMIN_EMAIL", "admin@aurorasoft.com"),
                             os.getenv("SUPERADMIN_PASSWORD")), 200, "Login superadmin")["access_token"]
    h_super = {"Authorization": f"Bearer {tok_super}"}
    inst = exigir(requests.post(f"{API}/instituciones/", json={
        "nombre": f"{PREFIJO} Colegio {sello}",
        "email_contacto": f"{PREFIJO.lower()}.{sello}@ejemplo.com"},
        headers=h_super, timeout=30), 201, "Institución")
    inst_id = inst["id"]
    correo = f"{PREFIJO.lower()}.admin.{sello}@ejemplo.com"
    exigir(pedir(requests.post, f"{API}/auth/registro", "registro", json={
        "email": correo, "password": "ClaveDePrueba123", "nombre_completo": f"{PREFIJO} Admin",
        "rol": "admin", "institucion_id": inst_id}, headers=h_super), 200, "Registro")
    tok = exigir(login(correo, "ClaveDePrueba123"), 200, "Login")["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    nivel = exigir(requests.post(f"{API}/admin/personas/academico/niveles", json={
        "institucion_id": inst_id, "nombre": "Secundaria"}, headers=h, timeout=30), 200, "Nivel")
    grado = exigir(requests.post(f"{API}/admin/personas/academico/grados", json={
        "nivel_educativo_id": nivel["id"], "nombre": "3°"}, headers=h, timeout=30), 200, "Grado")
    seccion = exigir(requests.post(f"{API}/admin/personas/academico/secciones", json={
        "grado_id": grado["id"], "nombre": "A", "anio_escolar": 2026}, headers=h, timeout=30), 200, "Sección")

    # ==================================================================
    print("\n1 · ARCHIVO DE 5.000 FILAS — debe ser RECHAZADO (límite documentado: 2.000)")
    excel_5000, _ = construir_excel_carga(5000, 0, 0, 0, f"{sello}5K", "Secundaria", "3°", "A", 2026)
    tam_mb = len(excel_5000.getbuffer()) / (1024 * 1024)
    print(f"    Archivo generado: {tam_mb:.2f} MiB, 5000 filas de datos + 1 encabezado.")

    with MonitorMemoria(pid_servidor) as mon:
        t0 = time.perf_counter()
        r_5000 = requests.post(f"{API}/admin/personas/importar/validar",
                               files={"archivo": ("carga_5000.xlsx", excel_5000,
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                               headers=h, timeout=180)
        t1 = time.perf_counter()

    comprobar("[3] 5.000 filas -> 422 (excede FILAS_MAXIMAS=2000), no 500 ni timeout",
              r_5000.status_code == 422, "POST /api/admin/personas/importar/validar", r_5000.text[:300])
    print(f"    Tiempo hasta el rechazo: {t1 - t0:.2f}s. Memoria del servidor — "
          f"antes: {mon.base_mb:.1f} MiB, pico durante la petición: {mon.pico_mb:.1f} MiB."
          if mon.base_mb and mon.pico_mb else "    (no se pudo medir memoria del servidor)")
    comprobar("[3] El rechazo de 5.000 filas es RÁPIDO (no procesa las 5000 antes de rechazar)",
              (t1 - t0) < 15, "POST /api/admin/personas/importar/validar", f"{t1 - t0:.2f}s")
    comprobar("[3] Ninguna de esas 5.000 filas se escribió en la base (archivo rechazado antes de /confirmar)",
              sql_uno(f"select count(*) from personas where codigo_institucional like '{PREFIJO}-{sello}5K%'")[0] == 0)

    # ==================================================================
    print("\n2 · ARCHIVO EN EL LÍMITE (2.000 filas reales: 1900 altas + 50 duplicadas + 30 error-grado + 20 vacías)")
    excel_2000, codigos_limpios = construir_excel_carga(1900, 50, 30, 20, sello, "Secundaria", "3°", "A", 2026)
    tam_mb_2000 = len(excel_2000.getbuffer()) / (1024 * 1024)
    print(f"    Archivo generado: {tam_mb_2000:.2f} MiB, 2000 filas de datos (1980 con contenido + 20 vacías) + encabezado.")

    with MonitorMemoria(pid_servidor) as mon_validar:
        t0 = time.perf_counter()
        r_validar = requests.post(f"{API}/admin/personas/importar/validar",
                                  files={"archivo": ("carga_2000.xlsx", excel_2000,
                                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                                  headers=h, timeout=180)
        t_validar = time.perf_counter() - t0
    resultado_validar = exigir(r_validar, 200, "Validar 2000")
    print(f"    /validar: {t_validar:.2f}s. Memoria servidor — antes: {mon_validar.base_mb:.1f} MiB, "
          f"pico: {mon_validar.pico_mb:.1f} MiB." if mon_validar.base_mb else "")

    comprobar("[1] total_filas descarta las 20 filas vacías (2000 - 20 = 1980)",
              resultado_validar["total_filas"] == 1980, "POST /api/admin/personas/importar/validar",
              str(resultado_validar["total_filas"]))
    comprobar("[1] Clasificación exacta: 1900 nuevos, 0 actualizados, 50 duplicados, 30 errores",
              resultado_validar["resumen"] == {"nuevos": 1900, "actualizados": 0, "duplicados": 50, "errores": 30},
              "POST /api/admin/personas/importar/validar", str(resultado_validar["resumen"]))

    filas_error = [f for f in resultado_validar["filas"] if f["accion"] == "error"]
    comprobar("[1] Las 30 filas de error señalan correctamente 'grado no existe en ese nivel'",
              len(filas_error) == 30 and all(
                  any(e["campo"] == "grado" and "no existe" in e["problema"] for e in f["errores"])
                  for f in filas_error),
              "POST /api/admin/personas/importar/validar", str(filas_error[0]["errores"]) if filas_error else "")

    filas_duplicadas = [f for f in resultado_validar["filas"] if f["accion"] == "duplicado"]
    comprobar("[1] Las 50 filas duplicadas señalan la fila original dentro del mismo archivo",
              len(filas_duplicadas) == 50 and all(
                  "duplicado dentro del archivo" in e["problema"] for f in filas_duplicadas for e in f["errores"]),
              "POST /api/admin/personas/importar/validar")

    comprobar("[1] /validar NO escribió nada en la base (es de solo lectura)",
              sql_uno(f"select count(*) from personas where codigo_institucional like '{PREFIJO}-{sello}-%'")[0] == 0,
              "POST /api/admin/personas/importar/validar (verificación en BD)")

    # --- Confirmar de verdad ---
    excel_2000.seek(0)
    with MonitorMemoria(pid_servidor) as mon_confirmar:
        t0 = time.perf_counter()
        r_confirmar = requests.post(f"{API}/admin/personas/importar/confirmar",
                                    files={"archivo": ("carga_2000.xlsx", excel_2000,
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                                    headers=h, timeout=180)
        t_confirmar = time.perf_counter() - t0
    resultado_confirmar = exigir(r_confirmar, 200, "Confirmar 2000")
    print(f"    /confirmar: {t_confirmar:.2f}s. Memoria servidor — antes: {mon_confirmar.base_mb:.1f} MiB, "
          f"pico: {mon_confirmar.pico_mb:.1f} MiB." if mon_confirmar.base_mb else "")

    comprobar("[1] /confirmar aplicó EXACTAMENTE las 1900 filas válidas, ninguna duplicada/error",
              resultado_confirmar["resumen"]["nuevos"] == 1900 and len(resultado_confirmar["detalle"]) == 1900,
              "POST /api/admin/personas/importar/confirmar", str(resultado_confirmar["resumen"]))

    n_personas_creadas = sql_uno(
        f"select count(*) from personas where institucion_id=:i and codigo_institucional like '{PREFIJO}-{sello}-%'",
        i=inst_id)[0]
    comprobar("[1] Se crearon EXACTAMENTE 1900 personas nuevas (ni las 50 duplicadas ni las 30 con error)",
              n_personas_creadas == 1900, "tabla personas (verificación directa en BD)", str(n_personas_creadas))

    n_matriculas = sql_uno(
        f"select count(*) from matriculas_academicas m join personas p on p.id=m.persona_id "
        f"where p.institucion_id=:i and p.codigo_institucional like '{PREFIJO}-{sello}-%' and m.fecha_fin is null",
        i=inst_id)[0]
    comprobar("[1] Las 1900 personas quedaron matriculadas en la sección correcta",
              n_matriculas == 1900, "tabla matriculas_academicas (verificación directa en BD)", str(n_matriculas))

    # --- Re-subir el MISMO archivo: ahora los 1900 deben verse como 'actualizado', no 'nuevo' ---
    excel_2000.seek(0)
    r_revalidar = requests.post(f"{API}/admin/personas/importar/validar",
                                files={"archivo": ("carga_2000.xlsx", excel_2000,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                                headers=h, timeout=180)
    resultado_revalidar = exigir(r_revalidar, 200, "Re-validar 2000")
    comprobar("[1] Al re-subir el MISMO archivo, las 1900 filas ahora son 'actualizado' (no altas duplicadas)",
              resultado_revalidar["resumen"] == {"nuevos": 0, "actualizados": 1900, "duplicados": 50, "errores": 30},
              "POST /api/admin/personas/importar/validar (segunda subida)", str(resultado_revalidar["resumen"]))

    total = len(_resultados)
    fallos = [n for n, ok, _ in _resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO: {total - len(fallos)}/{total} comprobaciones superadas")
    for n in fallos:
        print(f"  - {n}")
    print("=" * 72)
    return 0 if not fallos else 1


def limpiar():
    with MOTOR.begin() as c:
        c.execute(text(f"""
            delete from matriculas_academicas where persona_id in (
                select id from personas where codigo_institucional like '{PREFIJO}%')"""))
        c.execute(text(f"delete from personas where codigo_institucional like '{PREFIJO}%'"))
        c.execute(text(f"""
            delete from secciones where grado_id in (
                select g.id from grados g join niveles_educativos n on n.id = g.nivel_educativo_id
                where n.institucion_id in (select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"""
            delete from grados where nivel_educativo_id in (
                select id from niveles_educativos where institucion_id in (
                    select id from instituciones where nombre like '{PREFIJO}%'))"""))
        c.execute(text(f"delete from niveles_educativos where institucion_id in (select id from instituciones where nombre like '{PREFIJO}%')"))
        c.execute(text(f"delete from auth_usuarios where email like '{PREFIJO.lower()}%'"))
        c.execute(text(f"delete from instituciones where nombre like '{PREFIJO}%'"))
    print(f"🧹 Datos de prueba {PREFIJO} eliminados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limpiar", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8010")
    args = parser.parse_args()

    MOTOR = create_engine(os.getenv("DATABASE_URL"))
    if args.limpiar:
        limpiar()
        sys.exit(0)

    sys.exit(main(args.url))
