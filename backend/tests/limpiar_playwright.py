"""Borra los datos que deja la suite de Playwright (aurora_ui/e2e): todo lo
que cuelga, por claves foráneas, de las instituciones/pruebas/tipos de
documento con prefijo ZZPLAYWRIGHT y de los usuarios zzpw.* (sesión
2026-11-02 — antes la limpieza era manual, ver aurora_ui/e2e/README.md).

    python -m tests.limpiar_playwright            # simula: solo cuenta
    python -m tests.limpiar_playwright borrar     # borra, en una transacción

Antes de borrar comprueba que ninguna fila pertenezca a una institución que
NO sea de prueba; si encuentra una, aborta sin tocar nada.
"""
import os
import sys
from collections import defaultdict

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
motor = create_engine(os.getenv("DATABASE_URL"))

RAICES = [
    ("instituciones", "nombre LIKE 'ZZPLAYWRIGHT%'"),
    ("auth_usuarios", "email LIKE 'zzpw.%'"),
    ("edu_pruebas", "nombre_tecnico LIKE 'ZZPLAYWRIGHT%'"),
    ("documentos_tipos", "nombre LIKE 'ZZPLAYWRIGHT%'"),
]


def fks(c):
    hijos = defaultdict(list)  # tabla_padre -> [(tabla_hija, columna_hija)]
    for hija, col, padre in c.execute(text("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'""")):
        hijos[padre].append((hija, col))
    return hijos


def recolectar(c, hijos):
    """Ids a borrar por tabla (cierre transitivo por FK)."""
    ids = defaultdict(set)
    pendientes = []
    for tabla, cond in RAICES:
        nuevos = {r[0] for r in c.execute(text(f"SELECT id FROM {tabla} WHERE {cond}"))}
        ids[tabla] |= nuevos
        pendientes.append((tabla, nuevos))
    while pendientes:
        padre, nuevos = pendientes.pop()
        if not nuevos:
            continue
        for hija, col in hijos.get(padre, []):
            tiene_id = c.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='id'"), {"t": hija}).first()
            if not tiene_id:
                continue
            filas = {r[0] for r in c.execute(text(f"SELECT id FROM {hija} WHERE {col} = ANY(:ids)"), {"ids": list(nuevos)})}
            frescos = filas - ids[hija]
            if frescos:
                ids[hija] |= frescos
                pendientes.append((hija, frescos))
    return ids


def main(modo):
    with motor.begin() as c:
        hijos = fks(c)
        ids = recolectar(c, hijos)
        total = sum(len(v) for v in ids.values())
        for tabla in sorted(ids, key=lambda t: -len(ids[t])):
            if ids[tabla]:
                print(f"  {tabla}: {len(ids[tabla])}")
        print("TOTAL filas:", total)
        # Control: ninguna fila de otra institución real entra en el borrado.
        for tabla in ids:
            tiene_inst = c.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='institucion_id'"), {"t": tabla}).first()
            if tiene_inst and ids[tabla] and tabla != "instituciones":
                ajenas = c.execute(text(
                    f"SELECT count(*) FROM {tabla} WHERE id = ANY(:ids) AND institucion_id IS NOT NULL "
                    f"AND institucion_id NOT IN (SELECT id FROM instituciones WHERE nombre LIKE 'ZZPLAYWRIGHT%')"),
                    {"ids": list(ids[tabla])}).scalar()
                if ajenas:
                    print(f"  !! {tabla}: {ajenas} filas de OTRA institución — se aborta")
                    raise SystemExit(1)
        if modo != "borrar":
            print("(simulación: no se borró nada)")
            return
        # Borra hojas primero: repite hasta que no quede nada (orden por dependencias).
        restantes = {t: set(v) for t, v in ids.items() if v}
        for _ in range(50):
            if not restantes:
                break
            for tabla in list(restantes):
                try:
                    with c.begin_nested():
                        c.execute(text(f"DELETE FROM {tabla} WHERE id = ANY(:ids)"), {"ids": list(restantes[tabla])})
                    del restantes[tabla]
                except Exception:
                    pass  # todavía la referencia otra tabla: siguiente vuelta
        if restantes:
            print("!! no se pudo borrar:", {t: len(v) for t, v in restantes.items()})
            raise SystemExit(1)
        print("Borrado completo.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "simular")
