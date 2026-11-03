"""Casos en riesgo: sincronización fuera de la lectura (sesión 2026-11-02).

BD real, sin servidor ni worker. Todo corre dentro de una transacción
externa que SIEMPRE se revierte (los commit de `sincronizar_casos_riesgo`
solo liberan un savepoint), así que no deja datos.

  1  Equivalencia sobre los datos REALES de cada institución:
     `hay_casos_por_sincronizar` dice True exactamente cuando
     `sincronizar_casos_riesgo` cambia algo (casos o eventos nuevos, o una
     promoción), y después de sincronizar dice False.
  2  Con todo sincronizado, abrir la bandeja (`listar_casos_riesgo`) no
     ejecuta ningún INSERT/UPDATE/DELETE.
  3  Si falta un caso (borrado a mano en la transacción), la bandeja lo
     detecta y lo recrea en el acto: nunca muestra datos viejos aunque la
     tarea de Celery no haya corrido.
  4  La tarea `tarea_sincronizar_casos_riesgo` está registrada, en el
     calendario de beat cada 10 min, y se encola en los cuatro eventos
     (finalizar, reprocesar, sesión de seguimiento, antecedentes).

    python -m tests.verificar_casos_riesgo_sincronizacion
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import event, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from core.cola_tareas import app as celery_app  # noqa: E402
from core.database import engine  # noqa: E402
from modulos.educativo import crud, models  # noqa: E402
from modulos.instituciones import models as inst_models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion):
    _resultados.append(bool(condicion))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}")


def _huella(db, institucion_id):
    C, E = models.CasoRiesgo, models.CasoRiesgoEvento
    casos = db.query(func.count(C.id)).filter(C.institucion_id == institucion_id).scalar()
    eventos = db.query(func.count(E.id)).join(C, C.id == E.caso_id).filter(C.institucion_id == institucion_id).scalar()
    nuevos = db.query(func.count(C.id)).filter(C.institucion_id == institucion_id, C.estado == models.ESTADO_CASO_NUEVO).scalar()
    return casos, eventos, nuevos


def main():
    conexion = engine.connect()
    externa = conexion.begin()
    db = Session(bind=conexion, join_transaction_mode="create_savepoint")
    escrituras = []

    @event.listens_for(conexion, "before_cursor_execute")
    def _espia(conn, cursor, sentencia, parametros, contexto, executemany):
        primera = sentencia.lstrip().split(None, 1)[0].upper()
        if primera in ("INSERT", "UPDATE", "DELETE"):
            escrituras.append(sentencia.lstrip()[:60])

    try:
        print("\n1 · Equivalencia detección ↔ sincronización (datos reales + perturbados)")
        # Se fuerza un pendiente de CADA tipo (en la transacción revertida):
        # un caso de prueba y uno de antecedentes borrados, y un caso en
        # atención devuelto a 'nuevo' (si tenía una sesión posterior, la
        # sincronización debe promoverlo otra vez).
        C = models.CasoRiesgo
        perturbados = []
        for origen in (models.ORIGEN_CASO_PRUEBA, models.ORIGEN_CASO_ANTECEDENTES):
            c = db.query(C).filter(C.origen == origen, C.estado != models.ESTADO_CASO_CERRADO).first()
            if c:
                db.query(models.CasoRiesgoEvento).filter(models.CasoRiesgoEvento.caso_id == c.id).delete()
                db.delete(c)
                perturbados.append(f"borrado caso de {origen} (institución {c.institucion_id})")
        c = db.query(C).filter(C.estado == models.ESTADO_CASO_EN_ATENCION).first()
        if c:
            c.estado = models.ESTADO_CASO_NUEVO
            perturbados.append(f"caso {c.id} devuelto a 'nuevo'")
        db.flush()
        for p in perturbados:
            print("     ·", p)
        ids = [i for (i,) in db.query(inst_models.Institucion.id).order_by(inst_models.Institucion.id).all()]
        discrepancias, pendientes, residuos = [], 0, []
        for iid in ids:
            antes = _huella(db, iid)
            dijo = crud.hay_casos_por_sincronizar(db, iid)
            crud.sincronizar_casos_riesgo(db, iid)
            despues = _huella(db, iid)
            cambio = antes != despues
            if dijo != cambio:
                discrepancias.append((iid, dijo, antes, despues))
            pendientes += int(dijo)
            if crud.hay_casos_por_sincronizar(db, iid):
                residuos.append(iid)
        print(f"     {len(ids)} instituciones, {pendientes} con algo pendiente")
        comprobar("La detección coincide con lo que la sincronización cambia", not discrepancias)
        for d in discrepancias:
            print("       ", d)
        comprobar("Después de sincronizar no queda nada pendiente", not residuos)

        print("\n2 · Abrir la bandeja ya sincronizada no escribe")
        con_casos = [
            iid for (iid,) in db.query(models.CasoRiesgo.institucion_id).distinct().all()
        ]
        escrituras.clear()
        total_filas = 0
        for iid in con_casos or ids[:1]:
            total_filas += len(crud.listar_casos_riesgo(db, iid)["casos"])
        comprobar(f"Cero INSERT/UPDATE/DELETE al abrir {len(con_casos or ids[:1])} bandeja(s) ({total_filas} casos)", not escrituras)
        for e in escrituras[:5]:
            print("       ", e)

        print("\n3 · Un caso que falta se recrea al abrir la bandeja")
        caso = db.query(models.CasoRiesgo).filter(
            models.CasoRiesgo.origen == models.ORIGEN_CASO_PRUEBA,
            models.CasoRiesgo.estado != models.ESTADO_CASO_CERRADO,
        ).first()
        if caso is None:
            print("     (no hay ningún caso de prueba en la BD; corre antes verificar_casos_riesgo_e2e)")
            comprobar("Hay datos para el escenario 3", False)
        else:
            iid, insc = caso.institucion_id, caso.inscripcion_id
            db.query(models.CasoRiesgoEvento).filter(models.CasoRiesgoEvento.caso_id == caso.id).delete()
            db.delete(caso)
            db.flush()
            comprobar("Sin el caso, la detección lo ve pendiente", crud.hay_casos_por_sincronizar(db, iid))
            filas = crud.listar_casos_riesgo(db, iid)["casos"]
            comprobar("La bandeja lo trae igual (recreado en el acto)", any(f.get("inscripcion_id") == insc for f in filas))
            comprobar("…y ya no queda pendiente", not crud.hay_casos_por_sincronizar(db, iid))
    finally:
        db.close()
        externa.rollback()
        conexion.close()

    print("\n4 · Tarea de Celery y disparadores")
    celery_app.loader.import_default_modules()
    comprobar("Tarea registrada", "educativo.sincronizar_casos_riesgo" in celery_app.tasks)
    prog = celery_app.conf.beat_schedule.get("sincronizar-casos-riesgo", {})
    comprobar(
        "En beat cada 10 minutos",
        prog.get("task") == "educativo.sincronizar_casos_riesgo" and prog["schedule"].minute == {0, 10, 20, 30, 40, 50},
    )
    from modulos.educativo import router as edu_router
    from modulos.superadmin import router as sa_router

    fuentes = {
        "finalizar": inspect.getsource(edu_router.finalizar_examen_seguro),
        "reprocesar": inspect.getsource(edu_router.reprocesar_informe_de_inscripcion),
        "registrar una sesión de seguimiento": inspect.getsource(edu_router.registrar_seguimiento),
        "editar antecedentes": inspect.getsource(sa_router.actualizar_antecedentes_clinicos_endpoint),
    }
    for nombre, fuente in fuentes.items():
        comprobar(f"Se encola al {nombre}", "tarea_sincronizar_casos_riesgo" in fuente)

    print(f"\n{sum(_resultados)}/{len(_resultados)} comprobaciones pasaron")
    sys.exit(0 if all(_resultados) else 1)


if __name__ == "__main__":
    main()
