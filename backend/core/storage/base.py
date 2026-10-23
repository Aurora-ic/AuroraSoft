# core/storage/base.py
from abc import ABC, abstractmethod


class StorageService(ABC):
    """Contrato único para guardar/leer archivos, sin importar el proveedor detrás.

    La base de datos nunca guarda el binario, solo metadata (ver
    InformeVersion en modulos/educativo/models.py) + la `key` que estos
    métodos usan para localizar el archivo real. Quien llama nunca decide la
    key libremente: la key ya viene resuelta por construir_storage_key() a
    partir de datos ya autorizados (institución, informe), nunca de un valor
    que el cliente HTTP pueda mandar directamente.
    """

    @abstractmethod
    def guardar(self, key: str, contenido: bytes, content_type: str) -> None:
        """Escribe (o sobrescribe) el archivo en esa key."""
        raise NotImplementedError

    @abstractmethod
    def leer(self, key: str) -> bytes:
        """Devuelve el contenido binario. Lanza FileNotFoundError si la key no existe."""
        raise NotImplementedError

    @abstractmethod
    def existe(self, key: str) -> bool:
        raise NotImplementedError
