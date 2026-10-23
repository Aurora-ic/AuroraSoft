"""Schemas compartidos entre módulos — sin modelo ORM propio.

`RespuestaPaginada` es el envoltorio único para los listados que antes
devolvían una lista plana sin tope (`.order_by(...).all()`): ver
docs/gaps-pendientes.md, hallazgo "Sin paginación real". `skip`/`limit` van
en la query del endpoint, nunca con fallback a "sin límite" si se omiten.
"""
from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class RespuestaPaginada(BaseModel, Generic[T]):
    total: int
    items: List[T]
