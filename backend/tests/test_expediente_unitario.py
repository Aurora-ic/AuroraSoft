"""Pruebas unitarias — Expediente/Seguimiento del Estudiante.

    python -m tests.test_expediente_unitario

No necesitan la base de datos ni el servidor: `usuario_puede_ver_contenido_completo`
se ejercita con objetos en memoria y un `db` falso que solo implementa
query().filter().first() (mismo patrón DBFalso que test_reglas_interpretacion_unitario.py).
El resto son comprobaciones de modelo/esquema/ruteo en memoria.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import crud, models, schemas  # noqa: E402
from modulos.superadmin import router as superadmin_router  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


class _FakeQuery:
    def __init__(self, resultado):
        self._resultado = resultado

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._resultado


class _FakeDB:
    """Duplica solo lo que `obtener_autorizacion_colegio_vigente` necesita
    de una Session: query(Modelo).filter(...).first()."""
    def __init__(self, autorizacion_vigente=None):
        self._autorizacion_vigente = autorizacion_vigente

    def query(self, modelo):
        return _FakeQuery(self._autorizacion_vigente)


def _entrada(autor_usuario_id=1, persona_id=100):
    return SimpleNamespace(autor_usuario_id=autor_usuario_id, persona_id=persona_id)


def _usuario(rol, id_=1):
    return SimpleNamespace(rol=rol, id=id_)


# ==========================================
# LA REGLA DE ACCESO — usuario_puede_ver_contenido_completo
# ==========================================
def test_superadmin_siempre_tiene_acceso():
    print("\nRegla de acceso — superadmin siempre ve el contenido completo")
    entrada = _entrada(autor_usuario_id=999)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(), entrada, _usuario("superadmin", id_=1))
    comprobar("superadmin autorizado aunque no sea el autor", autorizado is True)
    comprobar("sin autorización de colegio de por medio", autorizacion is None)


def test_autor_tiene_acceso():
    print("\nRegla de acceso — el propio autor ve su entrada")
    entrada = _entrada(autor_usuario_id=42)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(), entrada, _usuario("psicologo", id_=42))
    comprobar("autor autorizado", autorizado is True)
    comprobar("sin autorización de colegio de por medio", autorizacion is None)


def test_admin_nunca_tiene_acceso():
    """🔒 Caso de rechazo explícito pedido: 'admin' queda fuera SIEMPRE,
    aunque sea de la misma institución — no hay excepción para admin."""
    print("\nRegla de acceso — RECHAZO: 'admin' nunca tiene acceso, ni siquiera de su propia institución")
    entrada = _entrada(autor_usuario_id=42)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(), entrada, _usuario("admin", id_=7))
    comprobar("admin NO autorizado", autorizado is False)
    comprobar("sin autorización usada", autorizacion is None)


def test_otro_psicologo_no_autor_nunca_tiene_acceso():
    """🔒 Caso de rechazo explícito pedido: otro psicólogo (no autor) queda
    fuera, incluso siendo de la misma institución."""
    print("\nRegla de acceso — RECHAZO: otro psicólogo (no autor) nunca tiene acceso")
    entrada = _entrada(autor_usuario_id=42)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(), entrada, _usuario("psicologo", id_=43))
    comprobar("otro psicólogo NO autorizado", autorizado is False)
    comprobar("sin autorización usada", autorizacion is None)


def test_colegio_sin_autorizacion_no_tiene_acceso():
    print("\nRegla de acceso — 'colegio' sin AutorizacionAccesoColegio vigente: sin acceso")
    entrada = _entrada(autor_usuario_id=42, persona_id=100)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(autorizacion_vigente=None), entrada, _usuario("colegio", id_=7))
    comprobar("colegio NO autorizado sin excepción vigente", autorizado is False)


def test_colegio_con_autorizacion_vigente_tiene_acceso():
    print("\nRegla de acceso — 'colegio' CON AutorizacionAccesoColegio vigente: acceso completo")
    entrada = _entrada(autor_usuario_id=42, persona_id=100)
    autorizacion_falsa = SimpleNamespace(id=555, persona_id=100, vigente=True)
    autorizado, autorizacion = crud.usuario_puede_ver_contenido_completo(_FakeDB(autorizacion_vigente=autorizacion_falsa), entrada, _usuario("colegio", id_=7))
    comprobar("colegio SÍ autorizado con la excepción vigente", autorizado is True)
    comprobar("la autorización usada es la que devolvió la consulta (para trazarla en el registro de lectura)", autorizacion is autorizacion_falsa)


# ==========================================
# CONSTANTES — coherencia entre crud.py, schemas.py y los CHECK de la BD
# ==========================================
def test_tipos_de_entrada_coinciden_con_el_check_constraint():
    print("\nConstantes — TIPOS_ENTRADA_VALIDOS coincide con el CHECK de la BD")
    texto_check = next(
        c.sqltext.text for c in models.EntradaExpediente.__table__.constraints
        if getattr(c, "name", None) == "ck_expediente_tipo_entrada_valido"
    )
    for tipo in crud.TIPOS_ENTRADA_VALIDOS:
        comprobar(f"'{tipo}' aparece en el CHECK", f"'{tipo}'" in texto_check)
    comprobar("Son exactamente 5 tipos, sin sobras", len(crud.TIPOS_ENTRADA_VALIDOS) == 5)
    comprobar(
        "schemas._TIPOS_ENTRADA_EXPEDIENTE_VALIDOS no diverge de crud.TIPOS_ENTRADA_VALIDOS",
        schemas._TIPOS_ENTRADA_EXPEDIENTE_VALIDOS == set(crud.TIPOS_ENTRADA_VALIDOS),
    )


def test_tipos_puente_y_con_contenido_son_complementarios():
    print("\nConstantes — los tipos puente y los tipos con contenido propio se reparten TODOS los tipos, sin solapar")
    comprobar(
        "La unión de ambos es exactamente TIPOS_ENTRADA_VALIDOS",
        set(crud.TIPOS_ENTRADA_CON_CONTENIDO_PROPIO) | set(crud.TIPOS_ENTRADA_PUENTE) == set(crud.TIPOS_ENTRADA_VALIDOS),
    )
    comprobar(
        "No hay ningún tipo en ambos grupos a la vez",
        not (set(crud.TIPOS_ENTRADA_CON_CONTENIDO_PROPIO) & set(crud.TIPOS_ENTRADA_PUENTE)),
    )


# ==========================================
# MODELO — columnas, versionado y candados nuevos
# ==========================================
def test_entrada_expediente_es_pura_identidad():
    print("\nModelo — EntradaExpediente es identidad (sin contenido narrativo propio)")
    columnas = models.EntradaExpediente.__table__.columns
    for campo_removido in ("visibilidad", "motivo", "contenido", "interpretacion", "diagnostico_presuntivo", "resumen_institucional"):
        comprobar(f"EntradaExpediente NO tiene '{campo_removido}' (vive en EntradaExpedienteVersion, o se eliminó)", campo_removido not in columnas)
    for campo in ("id", "persona_id", "institucion_id", "tipo_entrada", "autor_usuario_id", "fecha_entrada", "version_actual",
                  "sesion_seguimiento_id", "informe_id", "contacto_familiar_id"):
        comprobar(f"EntradaExpediente.{campo} existe", campo in columnas)


def test_version_tiene_el_contenido_narrativo():
    print("\nModelo — EntradaExpedienteVersion tiene el contenido narrativo versionado")
    columnas = models.EntradaExpedienteVersion.__table__.columns
    for campo in ("entrada_expediente_id", "numero_version", "motivo", "contenido", "interpretacion",
                  "diagnostico_presuntivo", "creado_por_usuario_id", "creado_en", "motivo_version"):
        comprobar(f"EntradaExpedienteVersion.{campo} existe", campo in columnas)
    nombres = [c.name for c in models.EntradaExpedienteVersion.__table__.constraints if getattr(c, "name", None)]
    comprobar("uq_expediente_version_entrada_numero existe (nunca dos versiones con el mismo número)",
              "uq_expediente_version_entrada_numero" in nombres)


def test_registro_lecturas_tiene_lo_necesario_para_auditar():
    print("\nModelo — RegistroLecturasExpediente")
    columnas = models.RegistroLecturasExpediente.__table__.columns
    for campo in ("entrada_expediente_id", "persona_id", "institucion_id", "leido_por_usuario_id",
                  "rol_lector", "fecha_lectura", "ip_lectura", "numero_version_leida", "autorizacion_acceso_colegio_id"):
        comprobar(f"RegistroLecturasExpediente.{campo} existe", campo in columnas)


def test_autorizacion_colegio_tiene_indice_unico_parcial():
    print("\nModelo — AutorizacionAccesoColegio: como máximo una vigente por persona")
    nombres = [ix.name for ix in models.AutorizacionAccesoColegio.__table__.indexes]
    comprobar("uq_autorizacion_colegio_vigente_por_persona existe", "uq_autorizacion_colegio_vigente_por_persona" in nombres)
    columnas = models.AutorizacionAccesoColegio.__table__.columns
    comprobar("motivo es NOT NULL (obligatorio)", columnas["motivo"].nullable is False)


def test_contacto_familiar_es_soft_delete():
    print("\nModelo — ContactoFamiliar: 'activo' existe para el soft-delete (nunca borrado físico)")
    columnas = models.ContactoFamiliar.__table__.columns
    comprobar("ContactoFamiliar.activo existe", "activo" in columnas)
    for campo in ("persona_id", "institucion_id", "nombre", "telefono", "relacion", "email", "fecha_registro", "registrado_por_usuario_id"):
        comprobar(f"ContactoFamiliar.{campo} existe", campo in columnas)


# ==========================================
# RUTEO — nada de un solo segmento
# ==========================================
def test_rutas_de_expediente_no_colisionan_con_segmentos_unicos():
    print("\nRuteo — las rutas de expediente/contactos/autorización tienen 2+ segmentos")
    rutas = [r.path for r in superadmin_router.router.routes]
    esperadas = [
        "/personas/{persona_id}/expediente",
        "/personas/expediente/{entrada_id}",
        "/personas/expediente/{entrada_id}/versiones",
        "/personas/{persona_id}/contactos",
        "/personas/contactos/{contacto_id}",
        "/personas/{persona_id}/autorizacion-colegio",
        "/personas/autorizacion-colegio/{autorizacion_id}/revocar",
    ]
    faltantes = [r for r in esperadas if r not in rutas]
    comprobar("Todas las rutas nuevas quedaron registradas", not faltantes, str(faltantes))
    de_un_segmento = [r for r in esperadas if r.strip("/").count("/") == 0]
    comprobar("Ninguna es de un solo segmento", not de_un_segmento, str(de_un_segmento))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — EXPEDIENTE / SEGUIMIENTO DEL ESTUDIANTE")
    print("=" * 72)
    test_superadmin_siempre_tiene_acceso()
    test_autor_tiene_acceso()
    test_admin_nunca_tiene_acceso()
    test_otro_psicologo_no_autor_nunca_tiene_acceso()
    test_colegio_sin_autorizacion_no_tiene_acceso()
    test_colegio_con_autorizacion_vigente_tiene_acceso()
    test_tipos_de_entrada_coinciden_con_el_check_constraint()
    test_tipos_puente_y_con_contenido_son_complementarios()
    test_entrada_expediente_es_pura_identidad()
    test_version_tiene_el_contenido_narrativo()
    test_registro_lecturas_tiene_lo_necesario_para_auditar()
    test_autorizacion_colegio_tiene_indice_unico_parcial()
    test_contacto_familiar_es_soft_delete()
    test_rutas_de_expediente_no_colisionan_con_segmentos_unicos()

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
