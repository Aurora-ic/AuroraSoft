"""Pruebas unitarias — Informes (modelo genérico) + Storage + catálogo PHQ-9.

    python -m tests.test_informes_phq9_unitario

No necesitan la base de datos ni el servidor.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models as edu_models  # noqa: E402
from core.storage import construir_storage_key  # noqa: E402
from core.storage.local import LocalStorageService  # noqa: E402
from seeds import seed_phq9  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


# ==========================================
# MODELO Informe / InformeVersion
# ==========================================
def test_modelo_informe():
    print("\nModelos — Informe pertenece a la APLICACIÓN, no al alumno")
    comprobar("Informe.inscripcion_id existe", hasattr(edu_models.Informe, "inscripcion_id"))
    comprobar("Informe.institucion_id existe (denormalizado)", hasattr(edu_models.Informe, "institucion_id"))
    comprobar("Informe.persona_id existe y es opcional (cupos anónimos)",
              edu_models.Informe.__table__.columns["persona_id"].nullable)

    nombres_constraints = [c.name for c in edu_models.Informe.__table__.constraints]
    comprobar(
        "Un solo Informe por inscripción (uq_edu_informes_inscripcion)",
        "uq_edu_informes_inscripcion" in nombres_constraints,
        str(nombres_constraints),
    )


def test_modelo_informe_version():
    print("\nModelos — InformeVersion es inmutable, versionado explícito")
    for columna in ("informe_id", "numero_version", "resultados_snapshot", "storage_key",
                     "tamano_bytes", "checksum_sha256", "generado_en", "motivo_version"):
        comprobar(f"InformeVersion.{columna} existe", columna in edu_models.InformeVersion.__table__.columns)

    nombres_constraints = [c.name for c in edu_models.InformeVersion.__table__.constraints]
    comprobar(
        "No se puede repetir numero_version dentro del mismo informe",
        "uq_edu_informe_versiones_numero" in nombres_constraints,
        str(nombres_constraints),
    )
    comprobar(
        "generado_por_usuario_id es nullable (NULL = generado por el sistema)",
        edu_models.InformeVersion.__table__.columns["generado_por_usuario_id"].nullable,
    )


# ==========================================
# STORAGE — key builder
# ==========================================
def test_construir_storage_key():
    print("\ncore.storage — construir_storage_key aísla por institución y por informe")
    key = construir_storage_key(institucion_id=7, informe_id=42, numero_version=1)
    comprobar("Formato instituciones/{id}/informes/{id}/v{n}.pdf", key == "instituciones/7/informes/42/v1.pdf", key)

    key_publica = construir_storage_key(institucion_id=None, informe_id=1, numero_version=1)
    comprobar("institucion_id=None no produce 'instituciones/None/...'", "None" not in key_publica, key_publica)

    key_v2 = construir_storage_key(institucion_id=7, informe_id=42, numero_version=2)
    comprobar("Cada versión tiene su propia key (v1 != v2)", key != key_v2)


# ==========================================
# STORAGE — LocalStorageService
# ==========================================
def test_local_storage_roundtrip():
    print("\ncore.storage.local — guardar/leer/existe")
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorageService(tmp)
        key = "instituciones/1/informes/1/v1.pdf"

        comprobar("No existe antes de guardar", not storage.existe(key))
        storage.guardar(key, b"%PDF-contenido-de-prueba", "application/pdf")
        comprobar("Existe después de guardar", storage.existe(key))
        comprobar("Lee exactamente lo mismo que se guardó", storage.leer(key) == b"%PDF-contenido-de-prueba")


def test_local_storage_crea_subdirectorios():
    print("\ncore.storage.local — crea automáticamente la jerarquía instituciones/{id}/informes/{id}/")
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorageService(tmp)
        key = construir_storage_key(institucion_id=99, informe_id=5, numero_version=1)
        storage.guardar(key, b"contenido", "application/pdf")
        comprobar("El archivo quedó en la ruta esperada", os.path.isfile(os.path.join(tmp, key.replace("/", os.sep))))


def test_local_storage_archivo_inexistente():
    print("\ncore.storage.local — leer una key inexistente falla explícito, no devuelve None silenciosamente")
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorageService(tmp)
        try:
            storage.leer("instituciones/1/informes/999/v1.pdf")
            comprobar("Lanza FileNotFoundError", False)
        except FileNotFoundError:
            comprobar("Lanza FileNotFoundError", True)


def test_local_storage_bloquea_path_traversal():
    print("\ncore.storage.local — una key que intente escapar del directorio base se rechaza")
    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorageService(tmp)
        try:
            storage.guardar("../../fuera_del_storage.pdf", b"x", "application/pdf")
            comprobar("guardar() rechaza la key maliciosa", False)
        except ValueError:
            comprobar("guardar() rechaza la key maliciosa", True)
        comprobar("existe() no revienta con una key maliciosa (devuelve False)",
                  storage.existe("../../fuera_del_storage.pdf") is False)


# ==========================================
# CATÁLOGO PHQ-9 (seed_phq9.py)
# ==========================================
def test_phq9_tiene_9_items_sin_inversion():
    print("\nseed_phq9 — 9 ítems, escala 0-3, sin ítems inversos (el PHQ-9 estándar no los tiene)")
    comprobar("9 preguntas exactas", len(seed_phq9.PREGUNTAS) == 9, str(len(seed_phq9.PREGUNTAS)))
    comprobar("4 opciones de respuesta", len(seed_phq9.OPCIONES) == 4)
    valores = sorted(v for _, v in seed_phq9.OPCIONES)
    comprobar("Valores de opción son exactamente 0,1,2,3", valores == [0, 1, 2, 3], str(valores))


def test_phq9_baremos_cubren_0_a_27_sin_huecos():
    print("\nseed_phq9 — baremos clínicos cubren 0..27 sin huecos ni solapes")
    tramos = sorted(seed_phq9.BAREMOS, key=lambda t: t[0])
    comprobar("Primer tramo empieza en 0", tramos[0][0] == 0)
    comprobar("Último tramo termina en 27 (máximo posible: 9 ítems x 3)", tramos[-1][1] == 27)
    sin_huecos = all(tramos[i][1] + 1 == tramos[i + 1][0] for i in range(len(tramos) - 1))
    comprobar("No hay huecos entre tramos consecutivos", sin_huecos, str(tramos))


def test_phq9_umbral_de_alerta():
    print("\nseed_phq9 — es_alerta solo desde el tramo 'Moderado' (>=10) en adelante")
    for minimo, maximo, nivel, es_alerta, conclusion, recomendacion in seed_phq9.BAREMOS:
        esperado = minimo >= 10
        comprobar(f"Tramo {minimo}-{maximo} ('{nivel}') es_alerta={esperado}", es_alerta == esperado)
        comprobar(f"Tramo {minimo}-{maximo} tiene conclusión y recomendación configuradas (contenido, no código)",
                  bool(conclusion) and bool(recomendacion))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — INFORMES (modelo genérico) + STORAGE + CATÁLOGO PHQ-9")
    print("=" * 72)
    test_modelo_informe()
    test_modelo_informe_version()
    test_construir_storage_key()
    test_local_storage_roundtrip()
    test_local_storage_crea_subdirectorios()
    test_local_storage_archivo_inexistente()
    test_local_storage_bloquea_path_traversal()
    test_phq9_tiene_9_items_sin_inversion()
    test_phq9_baremos_cubren_0_a_27_sin_huecos()
    test_phq9_umbral_de_alerta()

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
