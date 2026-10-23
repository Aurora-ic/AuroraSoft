# core/storage/__init__.py
#
# Punto de entrada único del subsistema de almacenamiento de archivos
# (hoy: solo PDFs de informes). El resto del backend nunca debe importar
# LocalStorageService/ObjectStorageService directamente ni construir una key
# a mano: siempre a través de obtener_storage_service() y construir_storage_key().
import os

from .base import StorageService
from .local import LocalStorageService

_instancia_cacheada: StorageService | None = None


def obtener_storage_service() -> StorageService:
    """Devuelve el backend de storage configurado por entorno (STORAGE_BACKEND).

    "local" (por defecto, para desarrollo/piloto) guarda en disco bajo
    STORAGE_LOCAL_PATH. "s3" apunta a cualquier proveedor compatible con la
    API S3 (AWS S3, Cloudflare R2, MinIO...) vía STORAGE_S3_*. El resto del
    código nunca sabe cuál de los dos está activo: solo ve la interfaz
    StorageService.guardar/leer/existe.

    Cacheado en el módulo (no por request) porque LocalStorageService no
    guarda estado de conexión y ObjectStorageService reutiliza un único
    cliente boto3 igual que se reutiliza `engine` en core/database.py.
    """
    global _instancia_cacheada
    if _instancia_cacheada is not None:
        return _instancia_cacheada

    backend = os.getenv("STORAGE_BACKEND", "local")

    if backend == "local":
        ruta = os.getenv("STORAGE_LOCAL_PATH", "./storage_local")
        _instancia_cacheada = LocalStorageService(ruta)
    elif backend == "s3":
        # Import perezoso: boto3 solo hace falta si de verdad se usa este
        # backend, así que un entorno de desarrollo con STORAGE_BACKEND=local
        # (el default) nunca necesita tenerlo instalado para arrancar.
        from .object_storage import ObjectStorageService

        bucket = os.environ["STORAGE_S3_BUCKET"]
        _instancia_cacheada = ObjectStorageService(
            bucket=bucket,
            endpoint_url=os.getenv("STORAGE_S3_ENDPOINT_URL"),
            region_name=os.getenv("STORAGE_S3_REGION"),
            access_key=os.getenv("STORAGE_S3_ACCESS_KEY"),
            secret_key=os.getenv("STORAGE_S3_SECRET_KEY"),
        )
    else:
        raise RuntimeError(
            f"STORAGE_BACKEND='{backend}' desconocido. Usa 'local' o 's3'."
        )

    return _instancia_cacheada


def resetear_storage_service_cacheado() -> None:
    """Solo para tests: fuerza a releer STORAGE_BACKEND/STORAGE_LOCAL_PATH en la próxima llamada."""
    global _instancia_cacheada
    _instancia_cacheada = None


def construir_storage_key(institucion_id: int | None, informe_id: int, numero_version: int) -> str:
    """Key/ruta del PDF de una versión de informe, aislada por institución y por informe.

    Nunca se construye una key a partir de algo que mande el cliente (ni
    institucion_id ni informe_id llegan aquí desde un request sin pasar antes
    por la resolución de propiedad en crud.py) — ver "MULTI-TENANCY DEL
    ALMACENAMIENTO" en la fase de informes.
    """
    segmento_institucion = str(institucion_id) if institucion_id is not None else "catalogo"
    return f"instituciones/{segmento_institucion}/informes/{informe_id}/v{numero_version}.pdf"


def construir_storage_key_documento(institucion_id: int, documento_institucional_id: int, numero_version: int) -> str:
    """Equivalente a `construir_storage_key()` para el motor de documentos
    institucionales — mismo criterio: nunca se construye a partir de algo
    que mande el cliente, solo desde ids ya resueltos y autorizados en
    `modulos/documentos/crud.py`. Un `DocumentoInstitucional` siempre
    pertenece a una institución (a diferencia de un `Informe`, que puede
    ser de catálogo público), así que aquí no hay caso "catalogo"."""
    return f"instituciones/{institucion_id}/documentos/{documento_institucional_id}/v{numero_version}.pdf"


def construir_storage_key_logo_institucion(institucion_id: int, tipo: str, extension: str) -> str:
    """Key de las imágenes de membrete/pie de página que una institución
    sube para el motor de documentos institucionales (modulos/documentos) —
    `tipo` es 'encabezado' o 'pie', validado por quien llama (modulos/
    instituciones/crud.py), nunca por esta función. Sin versionado, igual
    que la evidencia de consentimiento: una subida nueva reemplaza a la
    anterior en la misma key, porque esto es branding vigente, no un
    documento clínico con historial legal que conservar."""
    return f"instituciones/{institucion_id}/branding/{tipo}{extension}"


def construir_storage_key_firma_usuario(usuario_id: int, extension: str) -> str:
    """Key de la firma personal (imagen) de un usuario — ver
    `Usuario.firma_imagen_url` en modulos/auth/models.py y
    modulos/auth/crud.py:subir_firma_usuario(). Mismo criterio "sin
    versionado" que el branding institucional: una subida nueva reemplaza
    a la anterior."""
    return f"usuarios/{usuario_id}/firma{extension}"


def construir_storage_key_imagen_seccion_documento(
    institucion_id: int, documento_institucional_id: int, plantilla_seccion_id: int, token: str, extension: str,
) -> str:
    """Key de una imagen subida directamente a una sección `imagen_anexo`
    de un `DocumentoInstitucional` (ver modulos/documentos/crud.py:
    guardar_imagen_seccion). A diferencia de branding/firma/evidencia
    (que SOBRESCRIBEN la misma key en cada subida nueva), aquí `token` es
    único por subida (uuid4 hex) — una `DocumentoInstitucionalVersion` ya
    emitida congela el `storage_key` de la imagen vigente en ese momento;
    si se reemplaza la imagen antes de la siguiente versión, la anterior
    nunca debe perder sus bytes."""
    return f"instituciones/{institucion_id}/documentos/{documento_institucional_id}/secciones/{plantilla_seccion_id}/{token}{extension}"


def construir_storage_key_evidencia_consentimiento(
    institucion_id: int, consentimiento_id: int, extension: str
) -> str:
    """Key de la evidencia (documento firmado/escaneado) de un
    `ConsentimientoInformado` — cierre del gap "evidencia_ruta sin usar"
    (docs/gaps-pendientes.md). Mismo criterio que las dos de arriba: solo a
    partir de ids ya resueltos/autorizados en `modulos/superadmin/crud.py`
    (nunca el nombre de archivo crudo que manda el cliente — ver
    `_extension_segura()` en ese módulo, que es quien produce `extension`
    ya saneada antes de llegar aquí). Sin "v{n}": a diferencia de un
    informe, la evidencia no se versiona, una subida nueva reemplaza a la
    anterior en la misma key.
    """
    return f"instituciones/{institucion_id}/consentimientos/{consentimiento_id}/evidencia{extension}"
