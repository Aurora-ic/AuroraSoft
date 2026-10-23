"""Comparación estructural ESTRICTA entre dos bases PostgreSQL.

`alembic check` solo compara lo que autogenerate sabe detectar: ignora los
server_default, los nombres de las claves foráneas y otros detalles. Eso ya
dejó pasar una divergencia real (dos FK con nombre distinto según se crease la
base con create_all o con migraciones). Este comparador mira todo:

    columnas (tipo, nullabilidad, server_default), PK, FK (nombre, columnas,
    destino), índices (nombre, columnas, unicidad) y restricciones UNIQUE.

Uso:
    python tests/comparar_esquemas.py URL_A URL_B
Devuelve código 0 si son idénticas y 1 si hay diferencias.
"""

import re
import sys

from sqlalchemy import create_engine, inspect


def _normalizar_default(valor):
    if valor is None:
        return None
    valor = str(valor)
    # Las secuencias SERIAL se llaman igual en ambas bases; se normaliza por
    # si una conserva el cast ::regclass y otra no.
    valor = re.sub(r"::regclass", "", valor)
    return valor


def huella(url):
    insp = inspect(create_engine(url))
    esquema = {}
    for tabla in sorted(insp.get_table_names()):
        if tabla == "alembic_version":
            continue
        columnas = {
            c["name"]: (str(c["type"]), c["nullable"], _normalizar_default(c.get("default")))
            for c in insp.get_columns(tabla)
        }
        pk = tuple(insp.get_pk_constraint(tabla).get("constrained_columns") or [])
        fks = sorted(
            (fk.get("name"), tuple(fk["constrained_columns"]), fk["referred_table"],
             tuple(fk["referred_columns"]))
            for fk in insp.get_foreign_keys(tabla)
        )
        indices = sorted(
            (i["name"], tuple(i["column_names"]), bool(i["unique"]))
            for i in insp.get_indexes(tabla)
        )
        unicos = sorted(
            (u["name"], tuple(u["column_names"]))
            for u in insp.get_unique_constraints(tabla)
        )
        esquema[tabla] = {
            "columnas": columnas, "pk": pk, "fks": fks,
            "indices": indices, "unicos": unicos,
        }
    return esquema


def diferencias(a, b, etiqueta_a="A", etiqueta_b="B"):
    salida = []
    for tabla in sorted(set(a) | set(b)):
        if tabla not in a:
            salida.append(f"tabla '{tabla}' solo existe en {etiqueta_b}")
            continue
        if tabla not in b:
            salida.append(f"tabla '{tabla}' solo existe en {etiqueta_a}")
            continue
        ta, tb = a[tabla], b[tabla]
        for col in sorted(set(ta["columnas"]) | set(tb["columnas"])):
            ca, cb = ta["columnas"].get(col), tb["columnas"].get(col)
            if ca != cb:
                salida.append(f"{tabla}.{col}: {etiqueta_a}={ca} | {etiqueta_b}={cb}")
        for clave in ("pk", "fks", "indices", "unicos"):
            if ta[clave] != tb[clave]:
                sa_, sb_ = set(map(str, ta[clave] if isinstance(ta[clave], list) else [ta[clave]])), \
                           set(map(str, tb[clave] if isinstance(tb[clave], list) else [tb[clave]]))
                for x in sorted(sa_ - sb_):
                    salida.append(f"{tabla} {clave}: solo en {etiqueta_a} -> {x}")
                for x in sorted(sb_ - sa_):
                    salida.append(f"{tabla} {clave}: solo en {etiqueta_b} -> {x}")
    return salida


if __name__ == "__main__":
    url_a, url_b = sys.argv[1], sys.argv[2]
    difs = diferencias(huella(url_a), huella(url_b), "A", "B")
    if difs:
        print(f"{len(difs)} diferencia(s):")
        for d in difs:
            print("  -", d)
        sys.exit(1)
    print("Esquemas estructuralmente IDÉNTICOS.")
    sys.exit(0)
