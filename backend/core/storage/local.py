# core/storage/local.py
#
# Backend de desarrollo/piloto: guarda los archivos en una carpeta del
# servidor. No pensado para producción multi-instancia (el disco no se
# comparte entre workers/servidores) — para eso está ObjectStorageService.
from pathlib import Path

from .base import StorageService


class LocalStorageService(StorageService):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _ruta_absoluta(self, key: str) -> Path:
        # 🔒 Anti path-traversal: aunque hoy toda key la construye
        # construir_storage_key() (nunca el cliente), esta comprobación
        # asegura que un "../../etc/passwd" jamás pueda escapar del
        # directorio de storage, ahora o si algo cambia más adelante.
        candidata = (self.base_path / key).resolve()
        if candidata != self.base_path and self.base_path not in candidata.parents:
            raise ValueError(f"Key de storage fuera del directorio permitido: {key!r}")
        return candidata

    def guardar(self, key: str, contenido: bytes, content_type: str) -> None:
        ruta = self._ruta_absoluta(key)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)

    def leer(self, key: str) -> bytes:
        ruta = self._ruta_absoluta(key)
        if not ruta.is_file():
            raise FileNotFoundError(key)
        return ruta.read_bytes()

    def existe(self, key: str) -> bool:
        try:
            return self._ruta_absoluta(key).is_file()
        except ValueError:
            return False
