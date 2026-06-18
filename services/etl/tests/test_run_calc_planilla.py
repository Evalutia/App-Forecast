import datetime as dt

import pytest

from run_calc_planilla import clasificar_estado, clasificar_estado_mes, ventana_meses


# ── ventana_meses() ──────────────────────────────────────────────────────────

def test_ventana_meses_devuelve_n_meses_mas_reciente_primero():
    meses = ventana_meses(13, hoy=dt.date(2026, 2, 17))
    assert len(meses) == 13
    assert meses[0] == (2026, 2)
    assert meses[1] == (2026, 1)


def test_ventana_meses_rollover_de_anio():
    meses = ventana_meses(13, hoy=dt.date(2026, 1, 5))
    assert meses[0] == (2026, 1)
    assert meses[1] == (2025, 12)
    assert meses[-1] == (2025, 1)


def test_ventana_meses_sin_fecha_inyectada_usa_hoy():
    hoy = dt.date.today()
    meses = ventana_meses(1)
    assert meses[0] == (hoy.year, hoy.month)


# ── clasificar_estado() — sin cambios, meses cerrados ────────────────────────

@pytest.mark.parametrize(
    "dias_stock,dias_naturales,esperado",
    [
        (0,  30, "sin_stock"),
        (27, 30, "normal"),         # 90% exacto
        (26, 30, "quiebre_parcial"),  # 86.7%, debajo del umbral
        (31, 31, "normal"),
    ],
)
def test_clasificar_estado_mes_cerrado_sin_cambios(dias_stock, dias_naturales, esperado):
    assert clasificar_estado(dias_stock, dias_naturales) == esperado


# ── clasificar_estado_mes() — el fix ──────────────────────────────────────────

def test_mes_referencia_dia_17_de_30_con_stock_perfecto_ya_no_es_quiebre():
    """Caso exacto reportado en el bug: día 17 de un mes de 30, stock todos los días."""
    assert clasificar_estado_mes(dias_stock=17, dias_naturales=30, es_mes_referencia=True) == "normal"


def test_mes_referencia_dia_1_con_un_solo_dia_de_stock_ya_es_normal():
    assert clasificar_estado_mes(dias_stock=1, dias_naturales=31, es_mes_referencia=True) == "normal"


def test_mes_referencia_sin_ningun_dia_de_stock_sigue_sin_stock():
    assert clasificar_estado_mes(dias_stock=0, dias_naturales=30, es_mes_referencia=True) == "sin_stock"


@pytest.mark.parametrize(
    "dias_stock,dias_naturales,esperado",
    [
        (0,  30, "sin_stock"),
        (27, 30, "normal"),
        (26, 30, "quiebre_parcial"),
    ],
)
def test_mes_cerrado_via_clasificar_estado_mes_delega_sin_cambios(dias_stock, dias_naturales, esperado):
    assert clasificar_estado_mes(dias_stock, dias_naturales, es_mes_referencia=False) == esperado
