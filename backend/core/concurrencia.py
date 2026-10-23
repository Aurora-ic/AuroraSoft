"""Patrón genérico para escrituras seguras contra condiciones de carrera.

No inventa nada nuevo: generaliza dos mecanismos que ya existían, escritos
casi idénticos en dos sitios distintos del código real —
`modulos.documentos.crud.bloquear_correlativo_para_emision` y
`modulos.educativo.crud._bloquear_o_crear_informe_para_version` — para que
el PRÓXIMO caso (el que viene) use este helper en vez de reinventar el mismo
SAVEPOINT a mano. Ver `PLAN_REMODELACION_ARQUITECTURA.md`, sección 1.

Esta fase deliberadamente NO toca esos dos sitios ya corregidos y probados
— siguen con su propia copia del mecanismo, funcionando. Este módulo es
para código nuevo a partir de ahora.
"""

from typing import Callable, Optional, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")


def bloquear_o_crear(
    db: Session,
    consulta_con_lock: Callable[[], Optional[T]],
    fabrica: Callable[[], T],
) -> T:
    """Get-or-create con lock de fila, seguro contra la carrera de creación
    (dos transacciones ven "no existe" a la vez y ambas intentan crearlo).

    `consulta_con_lock` debe usar `.with_for_update().populate_existing()`
    (o al menos `.with_for_update()`) para que, si la fila ya existe, quede
    bloqueada hasta que quien llama haga commit/rollback — exactamente igual
    que ya hacen `bloquear_correlativo_para_emision`/
    `_bloquear_o_crear_informe_para_version`.

    Si no existe, se crea dentro de un SAVEPOINT (`db.begin_nested()`): la
    transacción que pierde la carrera contra el índice/constraint único
    recibe un `IntegrityError` ahí adentro, lo traga, y vuelve a consultar
    YA con lock — en ese punto la fila existe (la creó la otra transacción
    que ganó) y el lock espera hasta que esa otra libere el suyo.

    No hace ningún `db.commit()` real — el SAVEPOINT se resuelve dentro de
    la transacción exterior que ya esté abierta; quien llama decide cuándo
    confirma todo junto.
    """
    fila = consulta_con_lock()
    if fila is not None:
        return fila

    nested = db.begin_nested()
    try:
        nueva = fabrica()
        db.add(nueva)
        nested.commit()  # flush hacia la transacción exterior, NO un commit real
        return nueva
    except IntegrityError:
        nested.rollback()
        fila = consulta_con_lock()
        if fila is None:
            raise  # no debería pasar; si pasa, es un bug real, no se traga en silencio
        return fila


def commit_o_conflicto(db: Session, mensaje: str) -> None:
    """`db.commit()` envuelto en el mismo `try/except IntegrityError -> 409`
    que ya se repite a mano en `crear_documento_institucional`,
    `vincular_resultado_prueba`, `registrar_consentimiento`,
    `otorgar_autorizacion_colegio`, etc.

    Centraliza SOLO la traducción del error a una respuesta HTTP legible —
    nunca decide si hace falta lock antes (eso lo decide `bloquear_o_crear`,
    o un `.with_for_update()` explícito en el sitio que corresponda).
    """
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=mensaje)
