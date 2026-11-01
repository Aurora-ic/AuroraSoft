"""Equivalencia de `obtener_casos_pendientes_de_seguimiento` antes/después de
la reescritura de escalabilidad (sesión 2026-11-01): la versión nueva hace UN
SELECT con es_alerta en el WHERE y "sin seguimiento posterior" como NOT
EXISTS; la anterior traía todos los diagnósticos, filtraba en Python y
consultaba SesionSeguimiento una vez por alerta.

La versión anterior está copiada aquí tal cual (`_version_anterior`) y ambas
se corren sobre los MISMOS datos, armados dentro de una transacción que se
revierte al final — no deja nada en la BD. Escenarios (todos en la misma
institución real, más uno en otra para el aislamiento):

  A  alerta sin ninguna sesión                         -> pendiente
  B  alerta con sesión ANTERIOR a la resolución        -> pendiente
  C  alerta con sesión POSTERIOR a la resolución       -> no pendiente
  D  alerta con sesión el MISMO instante (>=)          -> no pendiente
  E  alerta con fecha_resolucion NULL                  -> pendiente (NULL nunca compara).
     La versión ANTERIOR reventaba aquí (500: comparaba `>= None` en
     Python); por eso E se agrega DESPUÉS de comparar las dos versiones
     y solo se verifica contra la nueva.
  F  diagnóstico SIN alerta                            -> no aparece
  G  inscripción dada de baja (is_deleted)             -> no aparece
  H  inscripción anónima (persona_id NULL)             -> no aparece
  I  dos dimensiones en alerta del mismo alumno        -> dos entradas
  J  sesión de OTRA persona después de la resolución   -> sigue pendiente
  K  alerta en otra institución                        -> no aparece aquí

    python -m tests.verificar_casos_pendientes_equivalencia
"""
import sys
from datetime import datetime, timedelta

from core.database import SessionLocal
from modulos.educativo import crud, models
from modulos.superadmin import models as sa_models

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def _version_anterior(db, institucion_id):
    """Copia verbatim del cuerpo de prueba previo a la reescritura (sin la
    parte de antecedentes, que no cambió)."""
    alertas = db.query(
        models.DiagnosticoAlumno, models.Inscripcion, models.Evaluacion, models.Prueba, models.Dimension
    ).join(
        models.Inscripcion, models.DiagnosticoAlumno.inscripcion_id == models.Inscripcion.id
    ).join(
        models.Evaluacion, models.Inscripcion.evaluacion_id == models.Evaluacion.id
    ).outerjoin(
        models.Prueba, models.Evaluacion.prueba_id == models.Prueba.id
    ).outerjoin(
        models.Dimension, models.DiagnosticoAlumno.dimension_id == models.Dimension.id
    ).filter(
        models.Evaluacion.institucion_id == institucion_id,
        models.Inscripcion.persona_id.isnot(None),
        models.Inscripcion.is_deleted == False,  # noqa: E712
    ).all()
    pendientes = []
    for diag, insc, evaluacion, prueba, dimension in alertas:
        if not diag.es_alerta:
            continue
        tiene_seguimiento = db.query(models.SesionSeguimiento).filter(
            models.SesionSeguimiento.persona_id == insc.persona_id,
            models.SesionSeguimiento.fecha >= insc.fecha_resolucion,
        ).first()
        if not tiene_seguimiento:
            pendientes.append({
                "origen": "prueba",
                "persona_id": insc.persona_id,
                "nombre_completo": insc.nombre_completo,
                "nivel_alerta": diag.nivel,
                "fecha_evaluacion": insc.fecha_resolucion,
                "fecha_referencia": insc.fecha_resolucion,
                "inscripcion_id": insc.id,
                "evaluacion_id": evaluacion.id,
                "campana": evaluacion.nombre_grupo,
                "prueba": (prueba.nombre_corto or prueba.nombre_tecnico) if prueba else None,
                "dimension": dimension.nombre if dimension else None,
            })
    return pendientes


def _clave(c):
    return (c["inscripcion_id"], c["nivel_alerta"], c["dimension"])


def main():
    db = SessionLocal()
    resultados = []
    try:
        persona = db.query(sa_models.Persona).filter(sa_models.Persona.institucion_id.isnot(None)).first()
        if not persona:
            print("No hay ninguna persona en la BD para armar los escenarios.")
            return 1
        inst = persona.institucion_id
        otras = db.query(sa_models.Persona).filter(sa_models.Persona.institucion_id == inst, sa_models.Persona.id != persona.id).limit(12).all()
        otra_inst = db.query(sa_models.Persona).filter(sa_models.Persona.institucion_id != inst).first()
        prueba = db.query(models.Prueba).first()
        psicologo_id = db.execute(__import__("sqlalchemy").text("SELECT id FROM auth_usuarios ORDER BY id LIMIT 1")).scalar()
        if len(otras) < 11 or not prueba or not psicologo_id:
            print("Faltan datos base (12+ personas en una institución, una prueba y un usuario).")
            return 1

        base = datetime(2026, 1, 15, 10, 0, 0)
        ev = models.Evaluacion(institucion_id=inst, prueba_id=prueba.id, nombre_grupo="ZZEQUIV campaña")
        db.add(ev)
        db.flush()

        def inscripcion(p, fecha=base, borrada=False, anonima=False, evaluacion=ev):
            i = models.Inscripcion(
                evaluacion_id=evaluacion.id, persona_id=None if anonima else p.id, nombre_completo=f"ZZEQUIV {p.id}",
                estado="Finalizado", fecha_resolucion=fecha, is_deleted=borrada,
                acepto_asentimiento=True, is_anonymized=anonima, informe_liberado=False, resultado_visible_alumno=False,
            )
            db.add(i)
            db.flush()
            return i

        def diagnostico(i, alerta=True, nivel="Alto"):
            db.add(models.DiagnosticoAlumno(inscripcion_id=i.id, nivel=nivel, es_alerta=alerta))

        def sesion(p, fecha):
            db.add(models.SesionSeguimiento(persona_id=p.id, psicologo_id=psicologo_id, institucion_id=inst, fecha=fecha, estado="Atendido"))

        a, b, c, d, e, f, g, h, i_, j = otras[:10]
        diagnostico(inscripcion(a))                                             # A
        ib = inscripcion(b); diagnostico(ib); sesion(b, base - timedelta(days=3))  # B
        ic = inscripcion(c); diagnostico(ic); sesion(c, base + timedelta(days=2))  # C
        idd = inscripcion(d); diagnostico(idd); sesion(d, base)                    # D
        diagnostico(inscripcion(f), alerta=False, nivel="Normal")               # F
        diagnostico(inscripcion(g, borrada=True))                               # G
        diagnostico(inscripcion(h, anonima=True))                               # H
        ii = inscripcion(i_); diagnostico(ii, nivel="Alto"); diagnostico(ii, nivel="Muy alto")  # I
        ij = inscripcion(j); diagnostico(ij); sesion(otras[10], base + timedelta(days=5))  # J: la sesión es de OTRA persona
        if otra_inst:
            ev_otra = models.Evaluacion(institucion_id=otra_inst.institucion_id, prueba_id=prueba.id, nombre_grupo="ZZEQUIV otra")
            db.add(ev_otra)
            db.flush()
            diagnostico(inscripcion(otra_inst, evaluacion=ev_otra))            # K
        db.flush()

        antes = sorted(_clave(x) for x in _version_anterior(db, inst))
        nuevas = [x for x in crud.obtener_casos_pendientes_de_seguimiento(db, inst) if x.get("origen") == "prueba"]
        despues = sorted(_clave(x) for x in nuevas)

        def comprobar(nombre, ok, detalle=""):
            resultados.append((nombre, ok))
            print(f"  [{'PASA' if ok else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))

        comprobar("Mismas entradas exactas (inscripción, nivel, dimensión) que la versión anterior", antes == despues, f"{len(antes)} vs {len(despues)}")
        ids = {x["inscripcion_id"] for x in nuevas}
        esperados_pend = {"A": True, "B": True, "C": False, "D": False, "E": True, "F": False, "G": False, "H": False, "J": True}
        reales = {"B": ib.id, "C": ic.id, "D": idd.id, "I": ii.id, "J": ij.id}
        for letra in ["B", "C", "D", "J"]:
            comprobar(f"Escenario {letra}", (reales[letra] in ids) == esperados_pend[letra])
        comprobar("Escenario I: dos dimensiones en alerta = dos entradas", sum(1 for x in nuevas if x["inscripcion_id"] == ii.id) == 2)
        comprobar("Ningún escenario sin alerta, dado de baja, anónimo o de otra institución se cuela",
                  all(x["campana"] == "ZZEQUIV campaña" for x in nuevas if x["nombre_completo"].startswith("ZZEQUIV"))
                  and len([x for x in nuevas if x["nombre_completo"].startswith("ZZEQUIV")]) == 5,  # A, B, I (x2), J
                  str(len([x for x in nuevas if x['nombre_completo'].startswith('ZZEQUIV')])))
        comprobar("Mismo contenido campo por campo en cada entrada",
                  sorted(map(str, sorted((sorted(x.items()) for x in _version_anterior(db, inst)), key=str)))
                  == sorted(map(str, sorted((sorted(x.items()) for x in nuevas), key=str))))

        # E — solo contra la versión nueva (la anterior reventaba).
        ie = inscripcion(e, fecha=None)
        diagnostico(ie)
        db.flush()
        try:
            ids_e = {x["inscripcion_id"] for x in crud.obtener_casos_pendientes_de_seguimiento(db, inst) if x.get("origen") == "prueba"}
            comprobar("Escenario E: fecha_resolucion NULL queda pendiente y ya no revienta", ie.id in ids_e)
        except Exception as exc:  # noqa: BLE001
            comprobar("Escenario E: fecha_resolucion NULL queda pendiente y ya no revienta", False, repr(exc)[:150])
    finally:
        db.rollback()
        db.close()

    fallos = [n for n, ok in resultados if not ok]
    print("\n" + "=" * 72)
    print(f"RESULTADO EQUIVALENCIA CASOS PENDIENTES: {len(resultados) - len(fallos)}/{len(resultados)} comprobaciones superadas (datos revertidos)")
    print("=" * 72)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
