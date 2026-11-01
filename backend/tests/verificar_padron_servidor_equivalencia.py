"""Equivalencia de los filtros del padrón en el SERVIDOR (sesión 2026-11-01)
contra lo que hacían el Padrón, Nueva campaña y la Agenda en el NAVEGADOR.

Antes esas tres pantallas bajaban el padrón completo (de a 200) y
filtraban/contaban en el cliente. Ahora usan `?estado=&seccion_id=...`,
`/ids` y `/resumen-padron`. Este script reproduce la lógica del cliente en
Python (`_cliente_*`, portada línea por línea del TSX anterior) sobre el
padrón completo traído EXACTAMENTE como lo traía el frontend, y la compara
con las funciones nuevas del servidor — sobre los datos reales de cada
institución MÁS escenarios sintéticos armados dentro de una transacción que
se revierte al final (no deja nada en la BD):

  S1  activo, matriculado en sección X, datos completos, con Dx, consentimiento vigente
  S2  activo = NULL (cuenta como inactivo), matriculado en X
  S3  activo = False, sin matrícula
  S4  activo, género "" (incompleto), sin matrícula, consentimiento REVOCADO
  S5  activo, sin fecha de nacimiento, matrícula CERRADA (fecha_fin) -> sin matrícula
  S6/S7 activos con el MISMO apellido (desempate del orden entre páginas)
  S8  activo, matriculado en sección Y del mismo grado
  S9  activo, consentimiento vigente pero de OTRA institución -> "sin"
  S10 antecedentes con los dos Sí/No en NULL -> sin Dx

    python -m tests.verificar_padron_servidor_equivalencia
"""
import sys
from datetime import datetime

from core.database import SessionLocal
from modulos.superadmin import crud, models

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PREFIJO = "ZZPADEQ"
_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append(bool(condicion))
    print(f"  {'OK ' if condicion else 'FALLO'} {nombre}" + ("" if condicion else f"  -> {detalle}"))


# ----------------------------------------------------------------------
# Lógica del CLIENTE, portada del TSX anterior
# ----------------------------------------------------------------------
def _padron_como_el_frontend(db, inst, incluir_inactivas):
    """getTodasLasPaginas: páginas de 200 hasta completar `total`."""
    todos, skip = [], 0
    while True:
        total, items = crud.obtener_personas_por_institucion(
            db, inst, incluir_inactivas=incluir_inactivas, skip=skip, limit=200
        )
        todos.extend(
            {
                "id": p.id, "nombres": p.nombres, "apellidos": p.apellidos,
                "documento_identidad": p.documento_identidad, "codigo_institucional": p.codigo_institucional,
                "activo": p.activo, "genero": p.genero, "fecha_nacimiento": p.fecha_nacimiento,
                "seccion_actual": p.seccion_actual, "con_diagnostico": p.con_diagnostico,
            }
            for p in items
        )
        skip += 200
        if skip >= total or not items:
            return todos


def _cliente_padron_filtrar(personas, estado, seccion, solo_incompletos, busqueda):
    """estudiantes/page.tsx — personasFiltradas."""
    texto = busqueda.strip().lower()
    out = []
    for p in personas:
        if estado == "activos" and not p["activo"]:
            continue
        if estado == "inactivos" and p["activo"]:
            continue
        if estado == "con_dx" and not (p["activo"] and p["con_diagnostico"]):
            continue
        if seccion == "sin-matricula":
            if p["seccion_actual"]:
                continue
        elif seccion != "todas":
            if not p["seccion_actual"] or p["seccion_actual"]["seccion_id"] != seccion:
                continue
        if solo_incompletos and p["genero"] and p["fecha_nacimiento"]:
            continue
        if texto:
            if not (
                texto in p["nombres"].lower()
                or texto in p["apellidos"].lower()
                or texto in (p["documento_identidad"] or "").lower()
            ):
                continue
        out.append(p["id"])
    return out


def _cliente_resumen(personas):
    activos = [p for p in personas if p["activo"]]
    return {
        "activos": len(activos),
        "inactivos": len(personas) - len(activos),
        "datos_incompletos": len([p for p in activos if not p["genero"] or not p["fecha_nacimiento"]]),
        "sin_matricula": len([p for p in activos if not p["seccion_actual"]]),
        "con_diagnostico": len([p for p in activos if p["con_diagnostico"]]),
    }


def _cliente_secciones(personas):
    """seccionesDisponibles (todas las personas, activas o no)."""
    mapa = {}
    for p in personas:
        s = p["seccion_actual"]
        if s:
            mapa[s["seccion_id"]] = " · ".join(x for x in [s["nivel_educativo"], s["grado"], s["seccion"]] if x)
    return mapa


def _server_ids(db, inst, **filtros):
    return crud.listar_ids_padron(db, inst, **filtros)


def _server_listado_ids(db, inst, **filtros):
    total, items = crud.obtener_personas_por_institucion(db, inst, skip=0, limit=100000, **filtros)
    return total, [p.id for p in items]


# ----------------------------------------------------------------------
def _verificar_institucion(db, inst, etiqueta):
    print(f"\n· Institución {inst} ({etiqueta})")
    todos = _padron_como_el_frontend(db, inst, incluir_inactivas=True)
    activos_def = _padron_como_el_frontend(db, inst, incluir_inactivas=False)
    comprobar("El recorrido página por página no repite ni salta alumnos",
              len(todos) == len({p["id"] for p in todos}), f"{len(todos)} vs {len({p['id'] for p in todos})}")

    # Sin filtros nuevos: el listado por defecto es el de siempre (solo activos).
    _, ids_def = _server_listado_ids(db, inst)
    comprobar("Sin filtros el listado sigue siendo 'solo activos'",
              set(ids_def) == {p["id"] for p in todos if p["activo"] is True} == {p["id"] for p in activos_def})

    # Padrón: estado × sección × incompletos (+ búsqueda vacía).
    secciones = sorted(_cliente_secciones(todos))
    combinaciones = 0
    diferencias = []
    for estado in ("activos", "inactivos", "todos", "con_dx"):
        for seccion in ["todas", "sin-matricula", *secciones]:
            for incompletos in (False, True):
                esperado = _cliente_padron_filtrar(todos, estado, seccion, incompletos, "")
                filtros = dict(estado=estado, datos_incompletos=incompletos)
                if seccion == "sin-matricula":
                    filtros["sin_matricula"] = True
                elif seccion != "todas":
                    filtros["seccion_id"] = seccion
                total, listado = _server_listado_ids(db, inst, **filtros)
                ids = _server_ids(db, inst, **filtros)
                combinaciones += 1
                if not (set(listado) == set(esperado) and total == len(esperado) and set(ids) == set(esperado) and len(ids) == len(esperado)):
                    diferencias.append((estado, seccion, incompletos, len(esperado), total, len(ids)))
    comprobar(f"Padrón: {combinaciones} combinaciones estado×sección×incompletos idénticas al cliente",
              not diferencias, str(diferencias[:5]))

    # Orden: el servidor respeta el mismo orden (apellidos) que veía el cliente.
    total_t, items_t = crud.obtener_personas_por_institucion(db, inst, estado="todos", skip=0, limit=100000)
    apellidos = [(p.apellidos, p.id) for p in items_t]
    comprobar("Orden por apellidos (como antes) con desempate estable por id", apellidos == sorted(apellidos))

    # Búsqueda: el servidor encuentra TODO lo que encontraba el cliente (y más: código, nombre completo).
    muestras = set()
    for p in todos[:15]:
        muestras.update({p["nombres"][:3], p["apellidos"][-3:], (p["documento_identidad"] or "")[:4]})
    muestras.discard("")
    faltantes = []
    for texto in sorted(muestras):
        esperado = set(_cliente_padron_filtrar(todos, "todos", "todas", False, texto))
        servidor = set(_server_ids(db, inst, estado="todos", busqueda=texto))
        if not esperado <= servidor:
            faltantes.append((texto, esperado - servidor))
    comprobar(f"Búsqueda: {len(muestras)} textos — el servidor nunca pierde un resultado del cliente", not faltantes, str(faltantes[:3]))

    # Resumen (tarjetas KPI) y secciones del desplegable.
    r = crud.resumen_padron(db, inst)
    esperado = _cliente_resumen(todos)
    comprobar("KPIs del resumen idénticos al cliente", all(r[k] == v for k, v in esperado.items()),
              f"{ {k: r[k] for k in esperado} } vs {esperado}")
    cli_secc = _cliente_secciones(todos)
    srv_secc = {s["seccion_id"]: " · ".join(x for x in [s["nivel_educativo"], s["grado"], s["seccion"]] if x) for s in r["secciones"]}
    comprobar("Secciones del desplegable idénticas (ids y etiquetas)", cli_secc == srv_secc, f"{cli_secc} vs {srv_secc}")

    # Agenda "Por salón" / "Todo el colegio" — sobre el padrón por defecto (activos).
    ri = crud.resumen_padron(db, inst, incluir_ids=True)
    por_seccion = {}
    for p in activos_def:
        if p["seccion_actual"]:
            por_seccion.setdefault(p["seccion_actual"]["seccion_id"], set()).add(p["id"])
    srv_por_seccion = {s["seccion_id"]: set(s["persona_ids"]) for s in ri["secciones"] if s["persona_ids"]}
    comprobar("Agenda: ids por sección idénticos a los que armaba el modal", por_seccion == srv_por_seccion)
    comprobar("Agenda: cantidad por sección = ids de esa sección",
              all(s["cantidad"] == len(s["persona_ids"]) for s in ri["secciones"]) and
              [(s["seccion_id"], s["cantidad"]) for s in ri["secciones"]] == [(s["seccion_id"], s["cantidad"]) for s in r["secciones"]])
    comprobar("Agenda: sin matrícula idéntico",
              set(ri["ids_sin_matricula"]) == {p["id"] for p in activos_def if not p["seccion_actual"]})
    comprobar("Agenda: 'Todo el colegio' = /ids por defecto = padrón activo",
              set(_server_ids(db, inst)) == {p["id"] for p in activos_def})

    # Nueva campaña: grado completo y consentimiento.
    grados = {p["seccion_actual"]["grado_id"] for p in activos_def if p["seccion_actual"]}
    malos = [g for g in grados if set(_server_ids(db, inst, grado_id=g)) !=
             {p["id"] for p in activos_def if p["seccion_actual"] and p["seccion_actual"]["grado_id"] == g}]
    comprobar(f"Campaña: preselección por grado ({len(grados)} grados) idéntica", not malos, str(malos))
    sin_consent = {p["id"] for p in activos_def if not crud.tiene_consentimiento_vigente(db, p["id"], inst)}
    comprobar("Campaña: 'sin consentimiento del apoderado' = la consulta por alumno de antes",
              set(_server_ids(db, inst, consentimiento_apoderado="sin")) == sin_consent)
    comprobar("Campaña: vigente ∪ sin = padrón activo, sin solaparse",
              set(_server_ids(db, inst, consentimiento_apoderado="vigente")) == {p["id"] for p in activos_def} - sin_consent)

    # Paginación chica: páginas de 1 cubren todo sin repetir.
    vistos, skip = [], 0
    while True:
        total, items = crud.obtener_personas_por_institucion(db, inst, estado="todos", skip=skip, limit=7)
        vistos.extend(p.id for p in items)
        skip += 7
        if skip >= total or not items:
            break
    comprobar("Páginas de 7 cubren el padrón sin repetir ni saltar", sorted(vistos) == sorted({p["id"] for p in todos}) and len(vistos) == len(todos))
    return todos


def main():
    db = SessionLocal()
    try:
        inst_ids = [i for (i,) in db.query(models.Persona.institucion_id).distinct().all()]
        if not inst_ids:
            print("No hay personas en la BD.")
            return 1

        print("1 · Datos reales (sin escenarios)")
        for inst in inst_ids:
            _verificar_institucion(db, inst, "real")

        print("\n2 · Datos reales + escenarios sintéticos (transacción que se revierte)")
        inst = inst_ids[0]
        otra = next((i for i in inst_ids if i != inst), None)
        usuario_id = db.execute(__import__("sqlalchemy").text("SELECT id FROM auth_usuarios ORDER BY id LIMIT 1")).scalar()
        nivel = models.NivelEducativo(institucion_id=inst, nombre=f"{PREFIJO} Nivel")
        db.add(nivel); db.flush()
        grado = models.Grado(institucion_id=inst, nivel_educativo_id=nivel.id, nombre="9°")
        db.add(grado); db.flush()
        sx = models.Seccion(institucion_id=inst, grado_id=grado.id, nombre="X", anio_escolar=2026)
        sy = models.Seccion(institucion_id=inst, grado_id=grado.id, nombre="Y", anio_escolar=2026)
        db.add_all([sx, sy]); db.flush()

        def persona(n, apellido=None, activo=True, genero="F", nacimiento=datetime(2012, 5, 1)):
            p = models.Persona(institucion_id=inst, nombres=f"{PREFIJO} S{n}", apellidos=apellido or f"{PREFIJO} Ap{n}",
                               documento_identidad=f"ZZ{n:06d}", activo=activo, genero=genero, fecha_nacimiento=nacimiento)
            db.add(p); db.flush()
            return p

        def matricular(p, seccion, cerrada=False):
            db.add(models.MatriculaAcademica(persona_id=p.id, institucion_id=inst, seccion_id=seccion.id,
                                             fecha_fin=datetime(2026, 3, 1) if cerrada else None))

        def consentimiento(p, institucion=inst, revocado=False):
            db.add(models.ConsentimientoInformado(persona_id=p.id, institucion_id=institucion, tipo_consentimiento="apoderado",
                                                  estado="revocado" if revocado else "vigente", revocado=revocado,
                                                  otorgado_por_nombre="ZZ", tipo_otorgante="apoderado",
                                                  registrado_por_usuario_id=usuario_id))

        s1 = persona(1); matricular(s1, sx); consentimiento(s1)
        db.add(models.PersonaAntecedentesClinicos(persona_id=s1.id, recibe_terapia_psicologica_externa=True))
        s2 = persona(2); matricular(s2, sx)
        # El default del modelo convierte `activo=None` en True: NULL real, a mano.
        db.execute(__import__("sqlalchemy").text("UPDATE personas SET activo = NULL WHERE id = :i"), {"i": s2.id})
        db.expire(s2)
        persona(3, activo=False)
        s4 = persona(4, genero=""); consentimiento(s4, revocado=True)
        s5 = persona(5, nacimiento=None); matricular(s5, sx, cerrada=True)
        persona(6, apellido=f"{PREFIJO} Igual"); persona(7, apellido=f"{PREFIJO} Igual")
        s8 = persona(8); matricular(s8, sy)
        s9 = persona(9)
        if otra:
            consentimiento(s9, institucion=otra)
        s10 = persona(10)
        db.add(models.PersonaAntecedentesClinicos(persona_id=s10.id))
        db.flush()

        _verificar_institucion(db, inst, "real + escenarios")

        print("\n3 · Escenarios puntuales")
        ids = lambda **f: set(_server_ids(db, inst, busqueda=PREFIJO, **f))
        comprobar("S2 (activo NULL) cuenta como inactivo", s2.id in ids(estado="inactivos") and s2.id not in ids())
        comprobar("S5 (matrícula cerrada) está 'sin matrícula'", s5.id in ids(sin_matricula=True))
        comprobar("Sección X activa = solo S1 (S2 inactivo, S5 cerrada)", ids(seccion_id=sx.id) == {s1.id})
        comprobar("Grado completo activo = S1 + S8", ids(grado_id=grado.id) == {s1.id, s8.id})
        comprobar("Con Dx = solo S1 (S10 tiene antecedentes en NULL)", ids(estado="con_dx") == {s1.id})
        comprobar("Incompletos activos = S4 (género vacío) + S5 (sin nacimiento)", ids(datos_incompletos=True) == {s4.id, s5.id})
        sin = ids(consentimiento_apoderado="sin")
        comprobar("Sin consentimiento incluye S4 (revocado) y S9 (de otra institución), no S1", {s4.id, s9.id} <= sin and s1.id not in sin)
        comprobar("Búsqueda por nombre completo encuentra a S1", s1.id in set(_server_ids(db, inst, busqueda=f"{PREFIJO} S1 {PREFIJO} Ap1")))
    finally:
        db.rollback()
        db.close()

    total = len(_resultados)
    ok = sum(_resultados)
    print(f"\n{ok}/{total} comprobaciones OK")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
