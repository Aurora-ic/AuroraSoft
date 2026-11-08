"""El listado de instituciones del superadmin no se trunca en silencio
(sesión 2026-11-08) — ver modulos/instituciones/crud.obtener_instituciones.

Antes devolvía como máximo 100, sin ORDER BY: con 184 instituciones el panel
/master perdía instituciones al azar (una recién creada podía no aparecer, y
/master/clientes/[id] no podía administrarla). Sin servidor ni base de
desarrollo: la tabla real `instituciones` en un SQLite en memoria.

    python -m tests.test_listado_instituciones_unitario
"""
import random
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from modulos.instituciones import crud, models

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


def main():
    print("\n[1] 150 instituciones (más que el tope de 100 de antes)")
    motor = create_engine("sqlite://")
    models.Institucion.__table__.create(motor)
    db = sessionmaker(bind=motor)()
    nombres = [f"{random.choice(['colegio', 'Colegio', 'I.E.', 'academia'])} {i:03d}" for i in range(150)]
    random.Random(7).shuffle(nombres)
    for n in nombres:
        db.add(models.Institucion(nombre=n))
    db.commit()
    ultima = models.Institucion(nombre="ZZ recién creada")
    db.add(ultima)
    db.commit()

    lista = crud.obtener_instituciones(db)
    comprobar("devuelve las 151, no 100", len(lista) == 151, len(lista))
    comprobar("la recién creada está en la lista", any(i.id == ultima.id for i in lista))
    claves = [(i.nombre.lower(), i.id) for i in lista]
    comprobar("ordenadas por nombre sin distinguir mayúsculas", claves == sorted(claves), claves[:3])
    comprobar("la firma ya no acepta skip/limit (nadie puede volver a truncarla por defecto)",
              crud.obtener_instituciones.__code__.co_argcount == 1)

    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO LISTADO DE INSTITUCIONES: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    return 1 if RESULTADOS["fallo"] else 0


if __name__ == "__main__":
    sys.exit(main())
