"""
Tests de las funciones puras de scripts/diagnostico_planillas_cliente.py
(issue #127). El script vive en scripts/ junto a los demás de QA, así que se
agrega ese directorio al path -- no hay paquete que importar.

El script importa openpyxl de forma diferida (dentro de leer_planilla), así que
estos tests corren aunque la librería no esté instalada.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from diagnostico_planillas_cliente import (  # noqa: E402
    clasificar_hipotesis,
    coincide,
    factor_implicito,
    mes_con_stock_incompleto,
    parse_mes,
)


# ── parse_mes ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("etiqueta,esperado", [
    ("Vta.Jul/25", (2025, 7)),
    ("Jul/25", (2025, 7)),
    ("Vta.Ene/26", (2026, 1)),
    ("Dic/25", (2025, 12)),
    ("Ago/26", (2026, 8)),
    ("  Vta.Jul/25  ", (2025, 7)),
])
def test_parse_mes_reconoce_ambas_convenciones(etiqueta, esperado):
    assert parse_mes(etiqueta) == esperado


@pytest.mark.parametrize("etiqueta", [
    "Rotacion DesEstac.", "Rot. Manual", "Estado Art.", "Articulo",
    "C/STK", "TOT STK", "DDSTK", "SIN STOCK",
    None, 42, "", "Vta.", "Xyz/25", "Jul-25",
])
def test_parse_mes_ignora_lo_que_no_es_mes(etiqueta):
    assert parse_mes(etiqueta) is None


# ── coincide — tolerancia relativa ───────────────────────────────────────────

def test_coincide_absorbe_el_redondeo_a_4_decimales():
    assert coincide(0.0967741935, 0.0968)


def test_coincide_escala_con_la_magnitud():
    # un SKU de rotación alta arrastra más error absoluto por el mismo redondeo
    assert coincide(150.0001, 150.0)
    assert not coincide(151.0, 150.0)


def test_coincide_rechaza_valores_distintos():
    assert not coincide(1.0, 2.0)


# ── factor_implicito ─────────────────────────────────────────────────────────

def test_factor_implicito_despeja_el_factor():
    # 30 unidades en 30 días = 1.0/día; si el cliente muestra 0.5, aplicó factor 2.0
    assert factor_implicito(vta=30, rot_cliente=0.5, dias=30) == pytest.approx(2.0)


def test_factor_implicito_factor_neutro():
    assert factor_implicito(vta=30, rot_cliente=1.0, dias=30) == pytest.approx(1.0)


@pytest.mark.parametrize("vta,rot,dias", [
    (30, 0, 30),        # sin rotación publicada
    (30, None, 30),
    (30, 1.0, 0),       # sin denominador
    (0, 1.0, 30),       # venta nula -> factor 0, contaminaría la calibración
    (-5, 1.0, 30),      # venta negativa (notas de crédito, #80)
    (None, 1.0, 30),
])
def test_factor_implicito_none_si_no_se_puede_despejar(vta, rot, dias):
    assert factor_implicito(vta, rot, dias) is None


# ── mes_con_stock_incompleto — la defensa del bug de #127 ────────────────────

def test_mes_cubierto_entero_no_es_incompleto():
    assert mes_con_stock_incompleto(dias_nat=31, dias_observados=31) is False


def test_mes_cubierto_a_medias_es_incompleto():
    # el caso real: stock_diario llegaba al 14 de julio y fabricaba quiebres
    assert mes_con_stock_incompleto(dias_nat=31, dias_observados=14) is True


def test_sin_dato_de_cobertura_no_se_asume_incompleto():
    assert mes_con_stock_incompleto(dias_nat=31, dias_observados=None) is False


# ── clasificar_hipotesis — el corazón del diagnóstico ────────────────────────

def test_detecta_denominador_dias_naturales():
    # 30 uds, 10 días con stock de 30, factor 1.0 -> naturales daría 1.0, con_stock 3.0
    assert clasificar_hipotesis(vta=30, rot_cliente=1.0, dias_con_stock=10,
                                dias_nat=30, factor=1.0) == "naturales"


def test_detecta_denominador_dias_con_stock():
    assert clasificar_hipotesis(vta=30, rot_cliente=3.0, dias_con_stock=10,
                                dias_nat=30, factor=1.0) == "con_stock"


def test_discrimina_tambien_con_factor_estacional_distinto_de_uno():
    # factor 2.0 -> naturales: (30/30)/2 = 0.5 ; con_stock: (30/10)/2 = 1.5
    assert clasificar_hipotesis(30, 0.5, 10, 30, 2.0) == "naturales"
    assert clasificar_hipotesis(30, 1.5, 10, 30, 2.0) == "con_stock"


def test_ambiguo_cuando_no_hubo_quiebre():
    # ds == dn: las dos hipótesis dan el mismo valor, el mes no discrimina
    assert clasificar_hipotesis(vta=30, rot_cliente=1.0, dias_con_stock=30,
                                dias_nat=30, factor=1.0) == "ambiguo"


def test_ninguna_cuando_el_valor_no_se_explica_por_ninguna_hipotesis():
    assert clasificar_hipotesis(vta=30, rot_cliente=99.0, dias_con_stock=10,
                                dias_nat=30, factor=1.0) == "ninguna"


@pytest.mark.parametrize("kwargs", [
    dict(factor=None), dict(factor=0), dict(rot_cliente=None),
    dict(dias_con_stock=0), dict(dias_nat=0),
])
def test_ninguna_ante_datos_insuficientes_sin_reventar(kwargs):
    base = dict(vta=30, rot_cliente=1.0, dias_con_stock=10, dias_nat=30, factor=1.0)
    base.update(kwargs)
    assert clasificar_hipotesis(**base) == "ninguna"


def test_caso_real_de_produccion_con_stock():
    # I01133 2025-08: 10 uds, 5 días con stock de 31, sin factor -> 2.0000
    assert clasificar_hipotesis(vta=10, rot_cliente=2.0, dias_con_stock=5,
                                dias_nat=31, factor=1.0) == "con_stock"


def test_caso_real_de_produccion_con_factor():
    # I01081 2025-12: 9 uds, 16 días con stock de 31, factor 1.4 -> 0.4018
    assert clasificar_hipotesis(vta=9, rot_cliente=0.4018, dias_con_stock=16,
                                dias_nat=31, factor=1.4) == "con_stock"
