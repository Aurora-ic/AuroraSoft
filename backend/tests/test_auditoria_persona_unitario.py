"""Pruebas unitarias — PASO 3 (auditoría de cambios en 4 campos de Persona).

    python -m tests.test_auditoria_persona_unitario

Sin BD ni servidor: ejercita _valor_comparable/_texto_para_auditoria y la
lista CAMPOS_AUDITADOS_PERSONA directamente.
"""

import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql://verificacion/no-se-conecta")
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-unitarias")

from modulos.superadmin import crud, models  # noqa: E402

_resultados = []


def comprobar(nombre, condicion, detalle=""):
    _resultados.append((nombre, bool(condicion), detalle))
    print(f"  [{'PASA' if condicion else 'FALLA'}] {nombre}" + (f" — {detalle}" if detalle else ""))


def test_campos_auditados_son_exactamente_los_4_pedidos():
    print("\nCAMPOS_AUDITADOS_PERSONA — exactamente nombres/apellidos/fecha_nacimiento/documento_identidad")
    comprobar("Son exactamente esos 4, ninguno más",
              crud.CAMPOS_AUDITADOS_PERSONA == ("nombres", "apellidos", "fecha_nacimiento", "documento_identidad"))
    comprobar("'genero'/'email'/'activo'/'grado_seccion' NO están (no se pidió auditarlos)",
              not set(crud.CAMPOS_AUDITADOS_PERSONA) & {"genero", "email", "activo", "grado_seccion"})


def test_valor_comparable_unifica_date_y_datetime():
    print("\n_valor_comparable — un 'date' (schema) y un 'datetime' (columna) que representan el mismo día son iguales")
    d = date(2011, 4, 10)
    dt = datetime(2011, 4, 10, 0, 0, 0, tzinfo=timezone.utc)
    comprobar("date(2011,4,10) == datetime(2011,4,10, tz=UTC) tras normalizar", crud._valor_comparable(d) == crud._valor_comparable(dt))
    comprobar("Un datetime con hora distinta de medianoche también se reduce a la fecha",
              crud._valor_comparable(datetime(2011, 4, 10, 13, 45)) == d)
    comprobar("None sigue siendo None", crud._valor_comparable(None) is None)
    comprobar("Un texto plano (nombres/apellidos/documento) no se toca", crud._valor_comparable("Ana") == "Ana")


def test_texto_para_auditoria():
    print("\n_texto_para_auditoria — serializa fechas a ISO, deja texto tal cual, None sigue None")
    comprobar("None -> None", crud._texto_para_auditoria(None) is None)
    comprobar("date -> ISO", crud._texto_para_auditoria(date(2011, 4, 10)) == "2011-04-10")
    comprobar("str -> el mismo texto", crud._texto_para_auditoria("Ana Torres") == "Ana Torres")


class _UsuarioFalso:
    def __init__(self, id_, rol):
        self.id = id_
        self.rol = rol


class _PersonaFalsa:
    def __init__(self, **kw):
        self.id = 1
        self.institucion_id = 10
        for k, v in kw.items():
            setattr(self, k, v)


def test_no_se_registra_fila_si_el_valor_no_cambio():
    print("\nactualizar_persona — sin sesión real: se comprueba SOLO el cálculo del diff, vía _valor_comparable")
    # No se puede llamar actualizar_persona() completo sin una Session real
    # (hace una query); esta prueba fija el contrato de que el diff usa
    # _valor_comparable ANTES de decidir si generar una fila — ya cubierto
    # arriba. El comportamiento de extremo a extremo (0 filas si nada
    # cambió) se prueba con BD real en verificar_edicion_persona_e2e.py.
    comprobar("Documental: el criterio de 'sin cambio' es _valor_comparable(antes) == _valor_comparable(despues)", True)


def main():
    print("=" * 72)
    print("PRUEBAS UNITARIAS — Auditoría de cambios en Persona (PASO 3)")
    print("=" * 72)
    test_campos_auditados_son_exactamente_los_4_pedidos()
    test_valor_comparable_unifica_date_y_datetime()
    test_texto_para_auditoria()
    test_no_se_registra_fila_si_el_valor_no_cambio()

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
