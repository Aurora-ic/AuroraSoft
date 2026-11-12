"""STORAGE_PREFIJO (sesión 2026-11-12, piloto): dos entornos comparten un
bucket sin pisarse — ver core/storage/object_storage.validar_prefijo.

Sin red ni bucket: boto3.client se reemplaza por uno en memoria.

    python -m tests.test_storage_prefijo_unitario
"""
import sys

import boto3

import core.storage as storage_mod
from core.storage.object_storage import ObjectStorageService, validar_prefijo

RESULTADOS = {"ok": 0, "fallo": 0}


def comprobar(descripcion, condicion, detalle=None):
    if condicion:
        RESULTADOS["ok"] += 1
        print(f"  ✅ {descripcion}")
    else:
        RESULTADOS["fallo"] += 1
        print(f"  ❌ {descripcion}" + (f" — {detalle}" if detalle is not None else ""))


class _ClienteS3:
    def __init__(self):
        self.objetos = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objetos[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if (Bucket, Key) not in self.objetos:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        class _Cuerpo:
            def __init__(self, datos):
                self.datos = datos

            def read(self):
                return self.datos
        return {"Body": _Cuerpo(self.objetos[(Bucket, Key)])}

    def head_object(self, Bucket, Key):
        from botocore.exceptions import ClientError
        if (Bucket, Key) not in self.objetos:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}


CLIENTE = _ClienteS3()
boto3.client = lambda *a, **k: CLIENTE


def main():
    print("\n[1] Validación del prefijo")
    comprobar("sin prefijo -> ''", validar_prefijo(None) == "" and validar_prefijo("") == "")
    comprobar("'piloto/' es válido", validar_prefijo("piloto/") == "piloto/")
    for malo in ("piloto", "/piloto/", "Piloto/", "../", "pi loto/", "piloto/x/"):
        try:
            validar_prefijo(malo)
            rechaza = False
        except RuntimeError:
            rechaza = True
        comprobar(f"{malo!r} se rechaza al arrancar", rechaza)

    print("\n[2] Dos entornos en el mismo bucket no se pisan")
    desarrollo = ObjectStorageService(bucket="compartido")
    piloto = ObjectStorageService(bucket="compartido", prefijo="piloto/")
    clave = "instituciones/1/branding/encabezado"  # el mismo id 1 en las dos bases
    desarrollo.guardar(clave, b"logo-desarrollo", "image/png")
    piloto.guardar(clave, b"logo-piloto", "image/png")
    comprobar("desarrollo lee su propio logo", desarrollo.leer(clave) == b"logo-desarrollo")
    comprobar("el piloto lee el suyo, no el de desarrollo", piloto.leer(clave) == b"logo-piloto")
    comprobar("en el bucket quedan dos objetos distintos",
              set(CLIENTE.objetos) == {("compartido", clave), ("compartido", "piloto/" + clave)}, set(CLIENTE.objetos))
    comprobar("existe() también usa el prefijo",
              piloto.existe(clave) and not piloto.existe("instituciones/2/branding/encabezado"))
    try:
        piloto.leer("instituciones/9/no-existe")
        no_encontrado = False
    except FileNotFoundError as exc:
        no_encontrado = str(exc) == "instituciones/9/no-existe"
    comprobar("FileNotFoundError con la clave SIN prefijo (la que conoce la base)", no_encontrado)

    print("\n[3] La fábrica lee STORAGE_PREFIJO")
    import os
    previas = {k: os.environ.get(k) for k in ("STORAGE_BACKEND", "STORAGE_S3_BUCKET", "STORAGE_PREFIJO")}
    os.environ.update({"STORAGE_BACKEND": "s3", "STORAGE_S3_BUCKET": "compartido", "STORAGE_PREFIJO": "piloto/"})
    storage_mod.resetear_storage_service_cacheado()
    try:
        comprobar("obtener_storage_service() aplica el prefijo", storage_mod.obtener_storage_service().prefijo == "piloto/")
    finally:
        for k, v in previas.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        storage_mod.resetear_storage_service_cacheado()

    total = RESULTADOS["ok"] + RESULTADOS["fallo"]
    print("\n" + "=" * 72)
    print(f"RESULTADO PREFIJO DE STORAGE: {RESULTADOS['ok']}/{total} comprobaciones superadas")
    print("=" * 72)
    return 1 if RESULTADOS["fallo"] else 0


if __name__ == "__main__":
    sys.exit(main())
