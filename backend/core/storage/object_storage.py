# core/storage/object_storage.py
#
# Backend de producción: cualquier almacenamiento compatible con la API S3
# (AWS S3, Cloudflare R2, MinIO...). Usa boto3 apuntando a `endpoint_url`
# cuando el proveedor no es AWS (R2, MinIO); en AWS real se deja en None.
#
# No se activa por defecto (STORAGE_BACKEND=local es el default) y por eso
# el import de boto3 es perezoso en core/storage/__init__.py — un entorno de
# desarrollo no necesita tener boto3 instalado para arrancar la app.
from .base import StorageService


class ObjectStorageService(StorageService):
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        import boto3  # noqa: PLC0415 — import perezoso a propósito, ver arriba

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def guardar(self, key: str, contenido: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=contenido,
            ContentType=content_type or "application/octet-stream",
        )

    def leer(self, key: str) -> bytes:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            respuesta = self._client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code")
            if codigo in ("NoSuchKey", "404"):
                raise FileNotFoundError(key) from exc
            raise
        return respuesta["Body"].read()

    def existe(self, key: str) -> bool:
        from botocore.exceptions import ClientError  # noqa: PLC0415

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
