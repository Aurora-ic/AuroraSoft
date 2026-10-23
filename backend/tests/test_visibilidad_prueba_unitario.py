"""Pruebas unitarias — Prueba.visible_para_clientes (catálogo genérico).

    python -m tests.test_visibilidad_prueba_unitario

Sin BD ni servidor. Cubre: la columna existe con default True (cero cambio
para pruebas existentes), el schema por defecto también es True, y el
router que decide catálogo/creación de campañas NUNCA compara por nombre de
prueba — la única fila oculta hoy (la prueba técnica interna) se marca desde
un script de datos (seed_prueba_aptitud_tecnica.py), no desde el motor.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.educativo import models, schemas  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_columna_existe_con_default_true():
    print("\nModelo — Prueba.visible_para_clientes existe, NOT NULL, default True")
    columna = models.Prueba.__table__.columns["visible_para_clientes"]
    comprobar("La columna existe", columna is not None)
    comprobar("Es NOT NULL", columna.nullable is False)
    comprobar("Su server_default es 'true' (toda prueba existente sigue visible)",
              columna.server_default.arg == "true")


def test_schema_default_true():
    print("\nschemas.PruebaBase — visible_para_clientes por defecto es True")
    creada = schemas.PruebaCreate(nombre_tecnico="X", nombre_publico="X")
    comprobar("El default del schema es True", creada.visible_para_clientes is True)
    oculta = schemas.PruebaCreate(nombre_tecnico="X", nombre_publico="X", visible_para_clientes=False)
    comprobar("Se puede pedir explícitamente False", oculta.visible_para_clientes is False)


def test_router_no_usa_logica_por_nombre_de_prueba():
    print("\nGenericidad — el router de catálogo/campañas no compara por nombre de prueba")
    fuente = inspect.getsource(__import__("modulos.educativo.router", fromlist=["router"]))

    # La función que filtra el catálogo y la que crea campañas deben decidir
    # SOLO por la columna visible_para_clientes, nunca por nombre_tecnico ni
    # por el nombre de la prueba técnica interna en particular.
    comprobar("El router no menciona 'APTITUD_TECNICA_INTERNA' en ningún lugar", "APTITUD_TECNICA_INTERNA" not in fuente)

    inicio = fuente.index("def listar_pruebas_disponibles")
    fin = fuente.index("def exportar_dashboard_excel")
    cuerpo_listar = fuente[inicio:fin]
    comprobar("listar_pruebas_disponibles usa visible_para_clientes", "visible_para_clientes" in cuerpo_listar)
    comprobar("listar_pruebas_disponibles no compara nombre_tecnico", "nombre_tecnico" not in cuerpo_listar)

    inicio_campana = fuente.index("def crear_campana_de_test")
    fin_campana = fuente.index("# ==========================================\n# NUEVA RUTA: VER LOS LINKS DE LA CAMPAÑA")
    cuerpo_campana = fuente[inicio_campana:fin_campana]
    comprobar("crear_campana_de_test usa visible_para_clientes", "visible_para_clientes" in cuerpo_campana)
    comprobar("crear_campana_de_test no compara nombre_tecnico", "nombre_tecnico" not in cuerpo_campana)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Prueba.visible_para_clientes")
    print("=" * 72)
    test_columna_existe_con_default_true()
    test_schema_default_true()
    test_router_no_usa_logica_por_nombre_de_prueba()

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
