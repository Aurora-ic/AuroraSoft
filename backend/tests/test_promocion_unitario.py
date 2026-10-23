"""Pruebas unitarias — Promoción anual de estudiantes (algoritmo de mapeo).

    python -m tests.test_promocion_unitario

No necesitan la base de datos ni el servidor: `_siguiente_por_orden` es una
función pura (solo lee `.orden` de una lista de objetos cualquiera, nunca
hace queries) y el resto son comprobaciones de modelo/esquema en memoria.

Este archivo protege específicamente el bug real encontrado durante la
verificación manual de la fase (ver `resolver_grado_siguiente`,
`resolver_seccion_destino` y las llamadas siguientes en
modulos/superadmin/crud.py): la primera versión del chequeo de ambigüedad
miraba si el 'orden' tenía ALGÚN duplicado en toda la lista de grados de un
nivel (o de niveles de una institución), así que un empate en cualquier
punto de la lista bloqueaba el mapeo automático de TODOS los grados de ese
nivel, incluidos los que no tenían nada que ver con el empate. La versión
corregida acota la ambigüedad al grupo que realmente compite por ser "el
siguiente" de la fila que se está resolviendo — ver el caso
`test_duplicado_lejano_no_bloquea_una_sucesion_clara` más abajo, que es la
regresión de ese bug exacto.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import crud, models, schemas  # noqa: E402
from modulos.superadmin import router as superadmin_router  # noqa: E402
from modulos.instituciones import models as inst_models, router as inst_router  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def _fila(orden):
    """Objeto mínimo que `_siguiente_por_orden` acepta: solo necesita `.orden`."""
    return SimpleNamespace(orden=orden)


# ==========================================
# ALGORITMO — _siguiente_por_orden (función pura, sin BD)
# ==========================================
def test_siguiente_por_orden_caso_normal():
    print("\n_siguiente_por_orden — sucesión normal, sin ambigüedad")
    grados = [_fila(0), _fila(2), _fila(3), _fila(20), _fila(21)]
    siguiente, advertencia = crud._siguiente_por_orden(grados, 2)
    comprobar("Devuelve la fila con 'orden' inmediatamente superior (3)", siguiente is not None and siguiente.orden == 3)
    comprobar("Sin advertencia cuando la sucesión es clara", advertencia is None)


def test_siguiente_por_orden_fin_de_lista():
    print("\n_siguiente_por_orden — no hay nada después (fin de la estructura)")
    grados = [_fila(0), _fila(2), _fila(4)]
    siguiente, advertencia = crud._siguiente_por_orden(grados, 4)
    comprobar("No hay siguiente", siguiente is None)
    comprobar("Sin advertencia — es el caso esperado de egreso, no un error", advertencia is None)


def test_siguiente_por_orden_ambiguedad_real():
    print("\n_siguiente_por_orden — AMBIGÜEDAD REAL: dos filas empatadas por ser 'la siguiente'")
    grados = [_fila(0), _fila(2), _fila(9), _fila(9), _fila(20)]
    siguiente, advertencia = crud._siguiente_por_orden(grados, 2)
    comprobar("No propone ningún destino (nunca adivina)", siguiente is None)
    comprobar("Hay una advertencia explicando la ambigüedad", advertencia is not None)
    comprobar("La advertencia menciona cuántas filas compiten (2)", advertencia is not None and "2" in advertencia)


def test_duplicado_lejano_no_bloquea_una_sucesion_clara():
    """🐛 Regresión del bug real: un 'orden' duplicado en OTRA parte de la
    lista (que no compite por ser la sucesión de la fila que nos interesa)
    NO debe impedir resolver un caso que en realidad es inequívoco."""
    print("\n_siguiente_por_orden — REGRESIÓN DEL BUG: un empate LEJANO no debe contaminar una sucesión clara")
    # 3° (orden=2) -> 4° (orden=3) es una sucesión perfectamente clara, aunque
    # más adelante en la MISMA lista (orden=9) haya dos grados empatados que
    # no tienen nada que ver con el destino de 3°.
    grados = [_fila(0), _fila(2), _fila(3), _fila(9), _fila(9), _fila(20), _fila(21)]
    siguiente, advertencia = crud._siguiente_por_orden(grados, 2)
    comprobar("Resuelve al grado de orden=3, SIN verse afectado por el empate en orden=9", siguiente is not None and siguiente.orden == 3)
    comprobar("Ninguna advertencia — esta fila no compite con el empate lejano", advertencia is None)

    # Y quien SÍ está justo antes del empate (orden=3) sí debe quedar en
    # mapeo manual, porque su propia sucesión es la que está empatada.
    siguiente2, advertencia2 = crud._siguiente_por_orden(grados, 3)
    comprobar("Quien sí está justo antes del empate (orden=3) SÍ queda ambiguo", siguiente2 is None and advertencia2 is not None)


def test_duplicado_en_el_propio_orden_actual_no_afecta():
    """Dos filas compartiendo el 'orden' de la fila ACTUAL (no del destino)
    tampoco es un problema: la búsqueda es sobre `orden > orden_actual`, así
    que un empate exactamente en `orden_actual` queda fuera de la
    comparación por construcción."""
    print("\n_siguiente_por_orden — un empate EN el propio orden actual (no en el destino) no bloquea nada")
    grados = [_fila(2), _fila(2), _fila(5)]
    siguiente, advertencia = crud._siguiente_por_orden(grados, 2)
    comprobar("Resuelve limpiamente al único grado con orden=5", siguiente is not None and siguiente.orden == 5)
    comprobar("Sin advertencia", advertencia is None)


# ==========================================
# CONSTANTES — coherencia entre crud.py y el CHECK de la base de datos
# ==========================================
def test_tipos_de_excepcion_coinciden_con_el_check_constraint():
    print("\nConstantes — TIPOS_EXCEPCION_VALIDOS coincide exactamente con el CHECK de la BD")
    columnas_check = None
    for constraint in models.ProcesoPromocionDetalle.__table__.constraints:
        if getattr(constraint, "name", None) == "ck_promocion_detalle_tipo_excepcion_valido":
            columnas_check = constraint.sqltext.text
    comprobar("El CHECK constraint existe en el modelo", columnas_check is not None)
    for tipo in crud.TIPOS_EXCEPCION_VALIDOS:
        comprobar(f"'{tipo}' aparece en el texto del CHECK", columnas_check is not None and f"'{tipo}'" in columnas_check)
    comprobar(
        "TIPOS_EXCEPCION_VALIDOS son exactamente 6, sin sobras",
        set(crud.TIPOS_EXCEPCION_VALIDOS) == {"ninguna", "repitente", "retirado", "trasladado", "cambio_manual", "egreso"},
    )


def test_tipos_de_excepcion_coinciden_entre_crud_y_schemas():
    """schemas.py no puede importar crud.py (crud.py ya importa schemas.py,
    sería un ciclo) así que `_TIPOS_EXCEPCION_PROMOCION_VALIDOS` está
    duplicado a mano — esta prueba es la que evita que ambas listas
    diverjan silenciosamente."""
    print("\nConstantes — el set duplicado en schemas.py no diverge del de crud.py")
    comprobar(
        "schemas._TIPOS_EXCEPCION_PROMOCION_VALIDOS == crud.TIPOS_EXCEPCION_VALIDOS",
        schemas._TIPOS_EXCEPCION_PROMOCION_VALIDOS == set(crud.TIPOS_EXCEPCION_VALIDOS),
    )


def test_diccionarios_de_motivo_son_coherentes():
    print("\nConstantes — los diccionarios de motivo_apertura/motivo_cierre/condición son coherentes entre sí")
    comprobar(
        "EXCEPCIONES_SIN_MATRICULA_NUEVA es exactamente retirado/trasladado/egreso",
        set(crud.EXCEPCIONES_SIN_MATRICULA_NUEVA) == {"retirado", "trasladado", "egreso"},
    )
    comprobar(
        "MOTIVO_APERTURA_POR_EXCEPCION cubre exactamente las excepciones que SÍ abren matrícula",
        set(crud.MOTIVO_APERTURA_POR_EXCEPCION.keys())
        == set(crud.TIPOS_EXCEPCION_VALIDOS) - set(crud.EXCEPCIONES_SIN_MATRICULA_NUEVA),
    )
    comprobar(
        "MOTIVO_CIERRE_POR_EXCEPCION cubre TODOS los tipos de excepción",
        set(crud.MOTIVO_CIERRE_POR_EXCEPCION.keys()) == set(crud.TIPOS_EXCEPCION_VALIDOS),
    )
    comprobar(
        "CONDICION_MATRICULA_POR_EXCEPCION cubre exactamente retirado/trasladado/egreso",
        set(crud.CONDICION_MATRICULA_POR_EXCEPCION.keys()) == set(crud.EXCEPCIONES_SIN_MATRICULA_NUEVA),
    )
    # Cada valor de estos diccionarios debe ser uno de los que el CHECK de
    # MatriculaAcademica/Persona en la BD realmente acepta.
    checks = {c.name: c.sqltext.text for c in models.MatriculaAcademica.__table__.constraints if getattr(c, "name", None)}
    check_apertura = checks.get("ck_matriculas_motivo_apertura_valido", "")
    check_cierre = checks.get("ck_matriculas_motivo_cierre_valido", "")
    for valor in crud.MOTIVO_APERTURA_POR_EXCEPCION.values():
        comprobar(f"motivo_apertura='{valor}' está permitido por el CHECK de la BD", f"'{valor}'" in check_apertura)
    for valor in crud.MOTIVO_CIERRE_POR_EXCEPCION.values():
        comprobar(f"motivo_cierre='{valor}' está permitido por el CHECK de la BD", f"'{valor}'" in check_cierre)
    check_condicion = None
    for c in models.Persona.__table__.constraints:
        if getattr(c, "name", None) == "ck_personas_condicion_matricula_valida":
            check_condicion = c.sqltext.text
    for valor in crud.CONDICION_MATRICULA_POR_EXCEPCION.values():
        comprobar(f"condicion_matricula='{valor}' está permitida por el CHECK de la BD", check_condicion is not None and f"'{valor}'" in check_condicion)


# ==========================================
# MODELO — columnas y candados nuevos
# ==========================================
def test_modelos_tienen_las_columnas_esperadas():
    print("\nModelos — columnas nuevas de la promoción anual")
    for columna in ("motivo_apertura", "motivo_cierre", "motivo_detalle"):
        comprobar(f"MatriculaAcademica.{columna} existe", columna in models.MatriculaAcademica.__table__.columns)
    comprobar("Persona.condicion_matricula existe", "condicion_matricula" in models.Persona.__table__.columns)
    comprobar(
        "Institucion.anio_escolar_activo existe",
        "anio_escolar_activo" in inst_models.Institucion.__table__.columns,
    )
    for columna in (
        "id", "institucion_id", "anio_origen", "anio_destino", "estado",
        "creado_por_usuario_id", "confirmado_por_usuario_id", "fecha_confirmacion",
    ):
        comprobar(f"ProcesoPromocion.{columna} existe", columna in models.ProcesoPromocion.__table__.columns)
    for columna in (
        "proceso_id", "persona_id", "matricula_origen_id", "seccion_propuesta_id",
        "tipo_excepcion", "seccion_definitiva_id", "aplicado", "matricula_resultante_id",
        "advertencia_mapeo",
    ):
        comprobar(f"ProcesoPromocionDetalle.{columna} existe", columna in models.ProcesoPromocionDetalle.__table__.columns)


def test_correccion_exige_motivo_a_nivel_de_base_de_datos():
    """Decisión de la psicóloga (fase de diseño): corregir una fila ya
    confirmada exige motivo obligatorio SIEMPRE, sin umbral de tiempo — y
    debe estar garantizado por la base de datos, no solo por el endpoint."""
    print("\nModelo — el CHECK de corrección-exige-motivo existe y es el esperado")
    nombres = [c.name for c in models.MatriculaAcademica.__table__.constraints if getattr(c, "name", None)]
    comprobar("ck_matriculas_correccion_requiere_motivo existe", "ck_matriculas_correccion_requiere_motivo" in nombres)
    texto = next(
        c.sqltext.text for c in models.MatriculaAcademica.__table__.constraints
        if getattr(c, "name", None) == "ck_matriculas_correccion_requiere_motivo"
    )
    comprobar("El CHECK menciona motivo_apertura", "motivo_apertura" in texto)
    comprobar("El CHECK menciona motivo_cierre", "motivo_cierre" in texto)
    comprobar("El CHECK exige motivo_detalle IS NOT NULL", "motivo_detalle IS NOT NULL" in texto)


def test_indices_unicos_de_proceso_promocion():
    print("\nModelo — índices únicos de ProcesoPromocion/Detalle")
    nombres_proceso = [ix.name for ix in models.ProcesoPromocion.__table__.indexes]
    comprobar("uq_proceso_promocion_confirmado existe (impide confirmar dos veces la misma promoción)",
              "uq_proceso_promocion_confirmado" in nombres_proceso)
    nombres_detalle = [c.name for c in models.ProcesoPromocionDetalle.__table__.constraints if getattr(c, "name", None)]
    comprobar("uq_promocion_detalle_persona_por_proceso existe (una persona no aparece 2 veces en el mismo proceso)",
              "uq_promocion_detalle_persona_por_proceso" in nombres_detalle)


# ==========================================
# RUTEO — nada de un solo segmento (mismo criterio que el núcleo del estudiante)
# ==========================================
def test_rutas_de_promocion_no_colisionan_con_segmentos_unicos():
    print("\nRuteo — las rutas de promoción/año-escolar-activo tienen 2+ segmentos")
    rutas_superadmin = [r.path for r in superadmin_router.router.routes if "promocion" in r.path]
    esperadas_superadmin = [
        "/personas/promocion/procesos",
        "/personas/promocion/procesos/{proceso_id}",
        "/personas/promocion/procesos/{proceso_id}/detalle",
        "/personas/promocion/procesos/{proceso_id}/confirmar",
        "/personas/promocion/procesos/{proceso_id}/cancelar",
    ]
    faltantes = [r for r in esperadas_superadmin if r not in rutas_superadmin]
    comprobar("Todas las rutas de promoción quedaron registradas", not faltantes, str(faltantes))
    de_un_segmento = [r for r in rutas_superadmin if r.strip("/").count("/") == 0]
    comprobar("Ninguna ruta de promoción es de un solo segmento", not de_un_segmento, str(de_un_segmento))

    rutas_inst = [r.path for r in inst_router.router.routes if "anio-escolar-activo" in r.path]
    comprobar(
        "PATCH /instituciones/{id}/anio-escolar-activo tiene 2 segmentos",
        rutas_inst == ["/instituciones/{institucion_id}/anio-escolar-activo"],
        str(rutas_inst),
    )


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — PROMOCIÓN ANUAL DE ESTUDIANTES")
    print("=" * 72)
    test_siguiente_por_orden_caso_normal()
    test_siguiente_por_orden_fin_de_lista()
    test_siguiente_por_orden_ambiguedad_real()
    test_duplicado_lejano_no_bloquea_una_sucesion_clara()
    test_duplicado_en_el_propio_orden_actual_no_afecta()
    test_tipos_de_excepcion_coinciden_con_el_check_constraint()
    test_tipos_de_excepcion_coinciden_entre_crud_y_schemas()
    test_diccionarios_de_motivo_son_coherentes()
    test_modelos_tienen_las_columnas_esperadas()
    test_correccion_exige_motivo_a_nivel_de_base_de_datos()
    test_indices_unicos_de_proceso_promocion()
    test_rutas_de_promocion_no_colisionan_con_segmentos_unicos()

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
