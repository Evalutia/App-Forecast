import datetime as dt

import pytest

from run_calc_planilla import (
    calcular_historico,
    clasificar_estado,
    clasificar_estado_mes,
    meses_disponibles_historico,
    valor_ajustado_y_criterio,
    ventana_meses,
)


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


# ── clasificar_estado() — umbral 100%, replica el criterio del cliente ──────
# Issue #36/#37: verificado contra su Excel de referencia (openpyxl) — colorea
# como quiebre el 100% de los meses con al menos 1 día sin stock, sin piso.

@pytest.mark.parametrize(
    "dias_stock,dias_naturales,esperado",
    [
        (0,  30, "sin_stock"),
        (30, 30, "normal"),           # 100% exacto, único caso "normal"
        (29, 30, "quiebre_parcial"),  # 96.7%, un solo día de quiebre — igual cuenta
        (1,  31, "quiebre_parcial"),  # caso real I01089 May/25: 1 día de quiebre sobre 31
        (31, 31, "normal"),
    ],
)
def test_clasificar_estado_mes_cerrado_umbral_100(dias_stock, dias_naturales, esperado):
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
        (30, 30, "normal"),
        (29, 30, "quiebre_parcial"),
    ],
)
def test_mes_cerrado_via_clasificar_estado_mes_delega_sin_cambios(dias_stock, dias_naturales, esperado):
    assert clasificar_estado_mes(dias_stock, dias_naturales, es_mes_referencia=False) == esperado


# ── valor_ajustado_y_criterio() — blending Historico/Promedio/Real (Issue #61/#63) ──
# Los 4 casos son el ejemplo numerico del mail de Rodrigo (2026-06-27), ver
# .claude/CONTEXTO.md sesion 2026-07-14. El Caso 4 usa dias_naturales_mes real
# (30 para junio) en vez del 30.5 que usa el mail en su ejemplo a mano -- da
# 62.5 en vez del 63.125 literal del mail (decision ya tomada, discrepancia
# minima documentada para QA en #64).

def test_caso1_mail_un_ticket_sin_quiebre_usa_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=10, extrapolacion=None, historico=45.0, es_quiebre=False
    )
    assert (valor, criterio) == (45.0, "historico")


def test_caso2_mail_dos_tickets_sin_quiebre_usa_historico_corte_inclusivo():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=2, ventas_real=20, extrapolacion=None, historico=45.0, es_quiebre=False
    )
    assert (valor, criterio) == (45.0, "historico")


def test_caso3_mail_tres_tickets_sin_quiebre_promedia_historico_y_venta_real():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=30, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert (valor, criterio) == (40.0, "promedio")


def test_caso4_mail_tres_tickets_con_quiebre_promedia_historico_y_extrapolacion():
    """
    Mail: Historico=50, Extrapolacion=(30/12)*30.5=76.25 -> (50+76.25)/2=63.125.
    Con dias_naturales_mes real de junio (30, no 30.5): (30/12)*30=75 ->
    (50+75)/2=62.5. Decision tomada en el grill: usar el dia real, no el
    redondeo casual del mail.
    """
    extrapolacion = round((30 / 12) * 30, 2)  # dias_con_stock=12, dias_naturales_mes=30 (junio real)
    assert extrapolacion == 75.0
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=30, extrapolacion=extrapolacion, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (62.5, "promedio")


def test_cuatro_tickets_sigue_en_banda_promedio_no_alto():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=4, ventas_real=40, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert criterio == "promedio"
    assert valor == 45.0


def test_cinco_tickets_sin_quiebre_usa_venta_real_ignora_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=5, ventas_real=99, extrapolacion=None, historico=50.0, es_quiebre=False
    )
    assert (valor, criterio) == (99.0, "real_extrapolado")


def test_cinco_tickets_con_quiebre_usa_extrapolacion_ignora_historico():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=5, ventas_real=10, extrapolacion=80.0, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (80.0, "real_extrapolado")


# ── Fallbacks no cubiertos por el mail (decididos en la sesion de grill-me) ──

def test_sin_stock_extrapolacion_indefinida_cae_a_historico_sin_importar_tickets():
    """sin_stock (dias_con_stock=0) -> Extrapolacion=None. Cae a Historico
    incluso con tickets>=5, donde normalmente no se usaria Historico."""
    valor, criterio = valor_ajustado_y_criterio(
        tickets=10, ventas_real=5, extrapolacion=None, historico=50.0, es_quiebre=True
    )
    assert (valor, criterio) == (50.0, "historico")


def test_sin_stock_y_sin_historico_usa_venta_real_como_ultimo_recurso():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=7, extrapolacion=None, historico=None, es_quiebre=True
    )
    assert (valor, criterio) == (7.0, "real_extrapolado")


def test_sku_nuevo_sin_historico_tickets_bajo_usa_venta_real_sin_promediar():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=1, ventas_real=12, extrapolacion=None, historico=None, es_quiebre=False
    )
    assert (valor, criterio) == (12.0, "real_extrapolado")


def test_sku_nuevo_sin_historico_tickets_medio_usa_venta_real_sin_promediar():
    valor, criterio = valor_ajustado_y_criterio(
        tickets=3, ventas_real=12, extrapolacion=None, historico=None, es_quiebre=False
    )
    assert (valor, criterio) == (12.0, "real_extrapolado")


# ── meses_disponibles_historico() / calcular_historico() — Issue #63 ────────────

def test_meses_disponibles_sin_fec_alta_devuelve_todos():
    meses = [(2026, 5), (2026, 4), (2026, 3)]
    assert meses_disponibles_historico(None, meses) == meses


def test_meses_disponibles_excluye_meses_antes_de_fec_alta():
    meses = [(2026, 5), (2026, 4), (2026, 3)]
    # SKU dado de alta el 15 de abril 2026 -> marzo queda excluido, abril y mayo quedan
    disponibles = meses_disponibles_historico(dt.date(2026, 4, 15), meses)
    assert set(disponibles) == {(2026, 5), (2026, 4)}


def test_calcular_historico_promedia_incluyendo_meses_sin_ventas_como_cero():
    meses_cerrados = [(2026, 3), (2026, 4), (2026, 5)]
    ventas = {("C001", 2026, 3): 30, ("C001", 2026, 5): 30}  # abril sin fila = 0
    historico = calcular_historico("C001", None, meses_cerrados, ventas)
    assert historico == 20.0  # (30 + 0 + 30) / 3


def test_calcular_historico_sin_meses_disponibles_devuelve_none():
    # SKU dado de alta despues del ultimo mes cerrado
    historico = calcular_historico("C002", dt.date(2026, 6, 1), [(2026, 5), (2026, 4)], {})
    assert historico is None
