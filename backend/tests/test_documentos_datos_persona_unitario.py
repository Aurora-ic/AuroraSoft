"""Pruebas unitarias — Motor de documentos institucionales, Paso 2
(PersonaDatosFamiliares / PersonaAntecedentesClinicos, ficha del estudiante).

    python -m tests.test_documentos_datos_persona_unitario

No necesitan la base de datos ni el servidor.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from pydantic import ValidationError  # noqa: E402

from modulos.superadmin import models, schemas  # noqa: E402
from modulos.superadmin import router as superadmin_router  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))
    return bool(condicion)


def test_modelos_existen():
    print("\nModelos — PersonaDatosFamiliares / PersonaAntecedentesClinicos")
    comprobar("PersonaDatosFamiliares existe", hasattr(models, "PersonaDatosFamiliares"))
    comprobar("PersonaAntecedentesClinicos existe", hasattr(models, "PersonaAntecedentesClinicos"))
    for campo in ("numero_hermanos", "vive_con", "lugar_nacimiento", "lugar_procedencia"):
        comprobar(f"PersonaDatosFamiliares.{campo} existe", hasattr(models.PersonaDatosFamiliares, campo))
    for campo in (
        "recibe_terapia_psicologica_externa", "detalle_terapia_psicologica_externa",
        "recibe_atencion_psiquiatrica_externa", "detalle_atencion_psiquiatrica_externa",
        "diagnostico_reportado",
    ):
        comprobar(f"PersonaAntecedentesClinicos.{campo} existe", hasattr(models.PersonaAntecedentesClinicos, campo))


def test_lugar_nacimiento_y_procedencia_son_campos_separados():
    print("\nPersonaDatosFamiliares — nacimiento y procedencia son dos campos, no uno combinado")
    datos = schemas.PersonaDatosFamiliaresUpdate(lugar_nacimiento="Huancayo, Junín", lugar_procedencia="Huancayo")
    comprobar("lugar_nacimiento independiente", datos.lugar_nacimiento == "Huancayo, Junín")
    comprobar("lugar_procedencia independiente", datos.lugar_procedencia == "Huancayo")


def test_numero_hermanos_rechaza_negativo():
    print("\nPersonaDatosFamiliares — numero_hermanos no admite negativos")
    try:
        schemas.PersonaDatosFamiliaresUpdate(numero_hermanos=-1)
        comprobar("Rechaza -1", False)
    except ValidationError:
        comprobar("Rechaza -1", True)


def test_datos_familiares_update_admite_campos_parciales():
    print("\nPersonaDatosFamiliaresUpdate — actualización parcial")
    datos = schemas.PersonaDatosFamiliaresUpdate(vive_con="Padres y hermano")
    comprobar("Solo vive_con, el resto queda None (no se sobreescribe lo demás)",
               datos.numero_hermanos is None and datos.lugar_nacimiento is None)


def test_booleanos_de_antecedentes_no_tienen_default_forzado():
    print("\nPersonaAntecedentesClinicosUpdate — los booleanos no tienen un default que fuerce 'no'")
    datos = schemas.PersonaAntecedentesClinicosUpdate()
    comprobar("recibe_terapia_psicologica_externa por defecto None (no False)",
               datos.recibe_terapia_psicologica_externa is None)
    comprobar("recibe_atencion_psiquiatrica_externa por defecto None (no False)",
               datos.recibe_atencion_psiquiatrica_externa is None)


def test_antecedentes_clinicos_admite_terapia_y_psiquiatria_independientes():
    print("\nPersonaAntecedentesClinicosUpdate — terapia y psiquiatría son independientes")
    datos = schemas.PersonaAntecedentesClinicosUpdate(
        recibe_terapia_psicologica_externa=True,
        detalle_terapia_psicologica_externa="Psicóloga particular, sesiones semanales",
        recibe_atencion_psiquiatrica_externa=False,
    )
    comprobar("Puede llevar terapia SIN psiquiatría", datos.recibe_terapia_psicologica_externa is True
               and datos.recibe_atencion_psiquiatrica_externa is False)
    comprobar("El detalle de psiquiatría queda vacío si no aplica", datos.detalle_atencion_psiquiatrica_externa is None)


def test_diagnostico_reportado_es_texto_libre_independiente():
    print("\nPersonaAntecedentesClinicosUpdate — diagnostico_reportado es su propio campo")
    datos = schemas.PersonaAntecedentesClinicosUpdate(diagnostico_reportado="TDAH (diagnóstico externo, 2024)")
    comprobar("diagnostico_reportado no depende de recibir terapia/psiquiatría",
               datos.diagnostico_reportado == "TDAH (diagnóstico externo, 2024)"
               and datos.recibe_terapia_psicologica_externa is None)


def test_rutas_nuevas_no_colisionan_con_el_segmento_unico_existente():
    print("\nRuteo — las rutas nuevas no quedan atrapadas por GET/{institucion_id} o PATCH/{persona_id}")
    rutas = [(r.path, sorted(r.methods)) for r in superadmin_router.router.routes]
    nuevas = [
        "/personas/{persona_id}/datos-familiares",
        "/personas/{persona_id}/antecedentes-clinicos",
    ]
    faltantes = [r for r in nuevas if r not in [p for p, _ in rutas]]
    comprobar("Ambas rutas nuevas quedaron registradas (GET+PATCH)", not faltantes, str(faltantes))
    de_un_segmento = [r for r in nuevas if r.strip("/").count("/") == 0]
    comprobar("Ninguna ruta nueva es de un solo segmento", not de_un_segmento, str(de_un_segmento))


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — DATOS FAMILIARES / ANTECEDENTES CLÍNICOS DE LA FICHA")
    print("=" * 72)
    test_modelos_existen()
    test_lugar_nacimiento_y_procedencia_son_campos_separados()
    test_numero_hermanos_rechaza_negativo()
    test_datos_familiares_update_admite_campos_parciales()
    test_booleanos_de_antecedentes_no_tienen_default_forzado()
    test_antecedentes_clinicos_admite_terapia_y_psiquiatria_independientes()
    test_diagnostico_reportado_es_texto_libre_independiente()
    test_rutas_nuevas_no_colisionan_con_el_segmento_unico_existente()

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
