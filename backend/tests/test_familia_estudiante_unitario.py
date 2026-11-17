"""Pruebas unitarias — Composición familiar del estudiante (registro único por
familiar en `ContactoFamiliar`, 2026-11-16).

    python -m tests.test_familia_estudiante_unitario

No necesitan la base de datos ni el servidor. El recorrido real contra
Postgres y la API está en tests/verificar_familia_estudiante_e2e.py.
"""

import io
import os
import sys
from datetime import date, datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

import inspect  # noqa: E402

from pydantic import ValidationError  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.platypus import SimpleDocTemplate  # noqa: E402

from modulos.superadmin import crud, models, schemas  # noqa: E402
from modulos.superadmin import router as superadmin_router  # noqa: E402
from modulos.documentos import crud as documentos_crud  # noqa: E402
from modulos.documentos import pdf_generador  # noqa: E402

_resultados = []

CAMPOS_NUEVOS = (
    "apellidos", "es_apoderado", "es_contacto", "vive_con_estudiante", "ocupacion",
    "grado_instruccion", "estado_civil", "direccion", "distrito", "fecha_nacimiento",
)


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def _familiar(**kw):
    base = dict(
        id=1, persona_id=10, institucion_id=1, nombre="Rosa", apellidos="Quispe", telefono="999111222",
        relacion="Madre", email="rosa@ejemplo.com", activo=True,
        fecha_registro=datetime(2026, 1, 1, tzinfo=timezone.utc), registrado_por_usuario_id=3,
        es_apoderado=True, es_contacto=True, vive_con_estudiante=True, ocupacion="Docente",
        grado_instruccion="Superior universitario completo", estado_civil="Casado(a)",
        direccion="Av. Los Pinos 123", distrito="San Juan de Lurigancho", fecha_nacimiento=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_modelo_y_esquemas():
    print("\nModelo y esquemas — campos nuevos, todos opcionales")
    for campo in CAMPOS_NUEVOS:
        comprobar(f"ContactoFamiliar.{campo} existe", hasattr(models.ContactoFamiliar, campo))
        comprobar(f"ContactoFamiliarResponse.{campo}", campo in schemas.ContactoFamiliarResponse.model_fields)
    viejo = schemas.ContactoFamiliarCreate(nombre="Ana", telefono="9", relacion="madre")
    comprobar("La forma anterior (solo nombre/teléfono/relación) sigue válida", viejo.nombre == "Ana")
    comprobar("es_apoderado sin enviar queda None (toma el default de la columna)", viejo.es_apoderado is None)
    nuevo = schemas.ContactoFamiliarCreate(
        nombre="Luis", relacion="Hermano", es_contacto=False, fecha_nacimiento="2015-03-02", estado_civil="Soltero(a)",
    )
    comprobar("fecha_nacimiento se lee como fecha", nuevo.fecha_nacimiento == date(2015, 3, 2))
    try:
        schemas.ContactoFamiliarCreate(nombre="")
        comprobar("Nombre vacío rechazado", False)
    except ValidationError:
        comprobar("Nombre vacío rechazado", True)
    try:
        schemas.ContactoFamiliarUpdate(ocupacion="x" * 201)
        comprobar("Ocupación de más de 200 caracteres rechazada", False)
    except ValidationError:
        comprobar("Ocupación de más de 200 caracteres rechazada", True)
    parcial = schemas.ContactoFamiliarUpdate(ocupacion="Chofer")
    comprobar("Update parcial solo marca lo enviado", parcial.model_dump(exclude_unset=True) == {"ocupacion": "Chofer"})
    comprobar("No hay campo de DNI del familiar (decisión del usuario)", "documento_identidad" not in schemas.ContactoFamiliarCreate.model_fields)


def test_vista_colegio():
    print("\nRol colegio — no ve el entorno familiar; el staff ve todo")
    f = _familiar(fecha_nacimiento=date(1985, 5, 1))
    staff = crud.contacto_para_rol(f, "psicologo")
    colegio = crud.contacto_para_rol(f, "colegio")
    for campo in crud.CAMPOS_FAMILIAR_SOLO_STAFF:
        comprobar(f"colegio: {campo} vacío", colegio[campo] is None)
        comprobar(f"psicólogo: {campo} visible", staff[campo] is not None)
    for campo in ("nombre", "apellidos", "relacion", "es_apoderado", "telefono", "email"):
        comprobar(f"colegio: {campo} visible", colegio[campo] == staff[campo])
    comprobar("La lista no tapa datos para admin", crud.contacto_para_rol(f, "admin")["ocupacion"] == "Docente")
    fuente = inspect.getsource(superadmin_router.listar_contactos_familiares_endpoint)
    comprobar("GET /contactos pasa cada familiar por contacto_para_rol", "contacto_para_rol" in fuente)


class _FakeDB:
    def __init__(self, fila=None):
        self.fila = fila
        self.agregado = None

    def add(self, obj):
        self.agregado = obj

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def query(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self.fila


def test_crear_y_actualizar():
    print("\nCrear/actualizar — un booleano obligatorio en null no rompe ni pisa")
    db = _FakeDB()
    persona = SimpleNamespace(id=10, institucion_id=1)
    crud.crear_contacto_familiar(db, persona, schemas.ContactoFamiliarCreate(nombre="Ana", es_apoderado=None, ocupacion="Docente"), 3)
    obj = db.agregado
    comprobar("Se creó con persona e institución del recurso", obj.persona_id == 10 and obj.institucion_id == 1)
    comprobar("Ocupación guardada", obj.ocupacion == "Docente")
    comprobar("es_apoderado=null no se pasa a la columna (queda el default)", obj.es_apoderado is None or obj.es_apoderado is False)
    fila = _familiar(es_contacto=True, ocupacion="Docente")
    db = _FakeDB(fila)
    crud.actualizar_contacto_familiar(db, 1, schemas.ContactoFamiliarUpdate(es_contacto=None, ocupacion=None, distrito="Ate"))
    comprobar("es_contacto=null no pisa el valor (NOT NULL)", fila.es_contacto is True)
    comprobar("ocupacion=null sí la borra", fila.ocupacion is None)
    comprobar("distrito actualizado", fila.distrito == "Ate")


def test_documento_composicion():
    print("\nDocumento — composición familiar sin teléfono, correo ni domicilio")
    madre = _familiar()
    hermano = _familiar(id=2, nombre="Luis", apellidos="Quispe", relacion="Hermano", es_apoderado=False, es_contacto=False,
                        fecha_nacimiento=date(2014, 1, 1), estado_civil=None,
                        fecha_registro=datetime(2025, 1, 1, tzinfo=timezone.utc))
    tia = _familiar(id=3, nombre="Elena", apellidos=None, relacion="Tía", es_apoderado=True)
    padre = _familiar(id=4, nombre="Jorge", relacion="padre", es_apoderado=False,
                      fecha_registro=datetime(2026, 6, 1, tzinfo=timezone.utc))
    orden = sorted([hermano, tia, madre, padre], key=documentos_crud._orden_parentesco)
    comprobar("Orden: padres, apoderado, hermanos", [f.id for f in orden] == [1, 4, 3, 2], str([f.id for f in orden]))
    doc = documentos_crud._familiar_para_documento(madre)
    comprobar("Nombre completo con apellidos", doc["nombre"] == "Rosa Quispe")
    for campo in ("telefono", "email", "direccion", "distrito"):
        comprobar(f"El documento no lleva {campo}", campo not in doc)
    comprobar("Edad calculada", documentos_crud._edad_en_anios(date(2014, 6, 15), hoy=date(2026, 6, 14)) == 11)
    comprobar("Edad el día del cumpleaños", documentos_crud._edad_en_anios(date(2014, 6, 15), hoy=date(2026, 6, 15)) == 12)
    comprobar("Fecha futura no da edad negativa", documentos_crud._edad_en_anios(date(2030, 1, 1), hoy=date(2026, 1, 1)) is None)
    fuente = inspect.getsource(documentos_crud._resolver_datos_familiares)
    comprobar("El resolvedor lista solo familiares activos (sin incluir_inactivos)", "incluir_inactivos" not in fuente and "listar_contactos_de_persona" in fuente)


def _texto_pdf(datos):
    estilos, _, _ = pdf_generador._construir_estilos({})
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4).build(pdf_generador._renderizar_datos_familiares(datos, estilos))
    buffer.seek(0)
    return " ".join(" ".join(p.extract_text() for p in PdfReader(buffer).pages).split())


def test_pdf():
    print("\nPDF — tabla de composición familiar y snapshots anteriores intactos")
    datos = {
        "aplica": True, "numero_hermanos": 1, "vive_con": "ambos padres",
        "composicion_familiar": [
            {"parentesco": "Madre", "nombre": "Rosa Quispe", "edad": None, "ocupacion": "Docente",
             "grado_instruccion": "Superior", "estado_civil": "Casado(a)", "vive_con_estudiante": True, "es_apoderado": True},
            {"parentesco": "Hermano", "nombre": "Luis Quispe", "edad": 12, "ocupacion": None,
             "grado_instruccion": None, "estado_civil": None, "vive_con_estudiante": None, "es_apoderado": False},
        ],
    }
    texto = _texto_pdf(datos)
    comprobar("Título 'Composición familiar'", "Composición familiar" in texto)
    comprobar("Madre marcada como apoderado", "(apoderado)" in texto)
    comprobar("Edad del hermano", "12 años" in texto)
    comprobar("Ocupación y estado civil", "Docente" in texto and "Casado(a)" in texto)
    vacio = _texto_pdf({"aplica": True, "composicion_familiar": []})
    comprobar("Sin familiares: 'Sin familiares registrados.'", "Sin familiares registrados." in vacio)
    viejo = _texto_pdf({"aplica": True, "numero_hermanos": 2})
    comprobar("Snapshot anterior (sin la clave): no aparece la sección nueva", "Composición familiar" not in viejo and "Número de hermanos" in viejo)


if __name__ == "__main__":
    test_modelo_y_esquemas()
    test_vista_colegio()
    test_crear_y_actualizar()
    test_documento_composicion()
    test_pdf()
    total = len(_resultados)
    pasadas = sum(1 for _, ok, _ in _resultados if ok)
    print("\n" + "=" * 72)
    print(f"RESULTADO: {pasadas}/{total} comprobaciones superadas")
    print("=" * 72)
    sys.exit(0 if pasadas == total else 1)
