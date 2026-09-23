"""
Tests de las funciones puras de scripts/comparar_rotacion.py (issue #200).
Mismo patrón que #195/#196/#197/#199: el script vive en scripts/, se agrega
ese directorio al path.

Las fórmulas replicadas acá son las de services/etl/run_calc_planilla.py
(estado_mes, frecuencia_nivel, rotacion_ajustada, rotacion_diaria_
desestacionalizada) y apps/frontend/.../planillaResumen.ts
(rotacionDesestacionalizadaMes, calcularRotDesEstac) -- verificadas leyendo el
código real, no releídas de memoria. Si el pipeline cambia esas fórmulas, este
test es el primero en avisar.

Las funciones de I/O (conexión a MySQL) no se testean acá -- se verifican por
integración contra producción, igual que las anteriores.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from comparar_rotacion import (  # noqa: E402
    MAPEO_ESTADO_CLIENTE,
    bucket_venta,
    clasificar_estado,
    clasificar_frecuencia,
    coincide_dias,
    despejar_dias_con_stock,
    desvio_relativo,
    dias_naturales,
    es_despeje_imposible,
    frecuencia_por_sku,
    promedio_rot_desestac,
    resumen_direccionalidad,
    rotacion_ajustada,
    rotacion_desestac_mes,
    rotacion_diaria_desestacionalizada,
    rotacion_diaria_real,
)


# ── dias_naturales ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("year,month,esperado", [
    (2025, 8, 31), (2026, 2, 28), (2026, 4, 30), (2028, 2, 29),
])
def test_dias_naturales(year, month, esperado):
    assert dias_naturales(year, month) == esperado


# ── clasificar_estado ─────────────────────────────────────────────────────────
#
# Port directo de run_calc_planilla.clasificar_estado -- ESTADO_UMBRAL_NORMAL
# es 100% (cualquier día de quiebre cuenta, #36/#37), sin excepción de "mes de
# referencia": la ventana de #200 es siempre histórica (el archivo del cliente
# ya cerró hace meses cuando se corre este diagnóstico), así que ningún mes
# necesita el trato especial que sí hace falta en una corrida en vivo.

def test_clasificar_estado_sin_stock():
    assert clasificar_estado(0, 31) == "sin_stock"


def test_clasificar_estado_normal_cuando_cubre_todo_el_mes():
    assert clasificar_estado(31, 31) == "normal"


def test_clasificar_estado_quiebre_con_un_solo_dia_sin_stock():
    # Umbral 100%, sin piso -- un solo día de diferencia ya es quiebre.
    assert clasificar_estado(30, 31) == "quiebre_parcial"


# ── clasificar_frecuencia ─────────────────────────────────────────────────────

@pytest.mark.parametrize("n,esperado", [(9, "alta"), (12, "alta"), (3, "baja"), (0, "baja"), (4, "media"), (8, "media")])
def test_clasificar_frecuencia(n, esperado):
    assert clasificar_frecuencia(n) == esperado


# ── frecuencia_por_sku ────────────────────────────────────────────────────────
#
# La regla más delicada de portar: excluye ESTRUCTURALMENTE el último mes de
# la ventana al contar meses con venta (igual que run_calc_planilla.py excluye
# `meses_ordenados[0]` de `meses_con_ventas`), sin importar si ese mes está
# "en curso" -- distinto del criterio de `promedio_rot_desestac`, que sí
# promedia los 13 meses completos. Ver la nota de cabecera del módulo.

VENTANA_3M = [(2025, 8), (2025, 9), (2025, 10)]


def test_frecuencia_excluye_el_ultimo_mes_de_la_ventana():
    # C001 vendió en los 3 meses, pero el último (oct) no cuenta -- sólo
    # ago+sep entran al conteo (2 meses con venta).
    ventas = {"C001": {(2025, 8): 5, (2025, 9): 5, (2025, 10): 5}}
    niveles = frecuencia_por_sku(ventas, VENTANA_3M)
    assert niveles["C001"] == clasificar_frecuencia(2)


def test_frecuencia_venta_solo_en_el_ultimo_mes_no_cuenta():
    ventas = {"C001": {(2025, 8): 0, (2025, 9): 0, (2025, 10): 100}}
    niveles = frecuencia_por_sku(ventas, VENTANA_3M)
    assert niveles["C001"] == clasificar_frecuencia(0)  # "baja"


def test_frecuencia_meses_ausentes_cuentan_como_sin_venta():
    ventas = {"C001": {(2025, 8): 5}}  # sep/oct ni siquiera aparecen
    niveles = frecuencia_por_sku(ventas, VENTANA_3M)
    assert niveles["C001"] == clasificar_frecuencia(1)


def test_frecuencia_por_sku_es_independiente_entre_skus():
    ventas = {"C001": {(2025, 8): 5, (2025, 9): 5}, "C002": {}}
    niveles = frecuencia_por_sku(ventas, VENTANA_3M)
    assert niveles["C001"] == clasificar_frecuencia(2) == "baja"
    assert niveles["C002"] == clasificar_frecuencia(0) == "baja"


# ── rotacion_ajustada ─────────────────────────────────────────────────────────

def test_rotacion_ajustada_alta_usa_dias_con_stock():
    assert rotacion_ajustada(30, 10, 31, "alta") == 3.0


def test_rotacion_ajustada_alta_none_si_sin_stock():
    assert rotacion_ajustada(30, 0, 31, "alta") is None


def test_rotacion_ajustada_baja_usa_dias_naturales():
    assert rotacion_ajustada(31, 10, 31, "baja") == 1.0


def test_rotacion_ajustada_media_promedia_las_dos():
    # r_alta = 30/10=3.0, r_baja=30/31≈0.9677 -> promedio ≈1.9839
    assert rotacion_ajustada(30, 10, 31, "media") == round((3.0 + 30 / 31) / 2, 4)


def test_rotacion_ajustada_media_sin_stock_cae_a_baja():
    assert rotacion_ajustada(31, 0, 31, "media") == round(31 / 31, 4)


# ── rotacion_diaria_real / rotacion_diaria_desestacionalizada ────────────────

def test_rotacion_diaria_real():
    assert rotacion_diaria_real(30, 10) == 3.0


def test_rotacion_diaria_real_none_sin_stock():
    assert rotacion_diaria_real(30, 0) is None


def test_rotacion_diaria_desestacionalizada():
    assert rotacion_diaria_desestacionalizada(3.0, 1.5) == 2.0


def test_rotacion_diaria_desestacionalizada_none_sin_factor():
    assert rotacion_diaria_desestacionalizada(3.0, None) is None
    assert rotacion_diaria_desestacionalizada(3.0, 0) is None


def test_rotacion_diaria_desestacionalizada_none_si_rot_real_none():
    assert rotacion_diaria_desestacionalizada(None, 1.5) is None


# ── rotacion_desestac_mes ─────────────────────────────────────────────────────
#
# Port directo de rotacionDesestacionalizadaMes (planillaResumen.ts).

def test_desestac_mes_normal_usa_directo_el_valor_del_mes():
    assert rotacion_desestac_mes("normal", rot_real=3.0, rot_desestac=2.0, rot_ajustada=None) == 2.0


def test_desestac_mes_sin_stock_da_none():
    assert rotacion_desestac_mes("sin_stock", rot_real=None, rot_desestac=None, rot_ajustada=None) is None


def test_desestac_mes_quiebre_con_venta_real_cero_usa_el_valor_desestac():
    # Issue #134: venta real 0 en un mes con quiebre no se descarta.
    assert rotacion_desestac_mes(
        "quiebre_parcial", rot_real=0.0, rot_desestac=0.0, rot_ajustada=None) == 0.0


def test_desestac_mes_quiebre_con_venta_positiva_escala_la_ajustada():
    # raj * (rde/rot) -- caso real: rot=3.0, rde=2.0 (factor=1.5), raj=1.9839
    r = rotacion_desestac_mes(
        "quiebre_parcial", rot_real=3.0, rot_desestac=2.0, rot_ajustada=1.9839)
    assert r == pytest.approx(1.9839 * (2.0 / 3.0))


def test_desestac_mes_quiebre_sin_desestac_da_none():
    assert rotacion_desestac_mes(
        "quiebre_parcial", rot_real=3.0, rot_desestac=None, rot_ajustada=1.5) is None


def test_desestac_mes_quiebre_venta_real_negativa_excluida():
    # #80: devoluciones netas pueden dejar rot_real<0 -- #134 sólo rescató el
    # caso ==0, un real negativo sigue sin sentido para desestacionalizar.
    assert rotacion_desestac_mes(
        "quiebre_parcial", rot_real=-1.0, rot_desestac=-0.5, rot_ajustada=1.0) is None


# ── promedio_rot_desestac ─────────────────────────────────────────────────────
#
# Port de calcularRotDesEstac -- acá SIEMPRE promedia los 13 meses (a
# diferencia del frontend, que excluye el último sólo si es el mes calendario
# EN CURSO: la ventana de #200 es histórica completa, ningún mes de los 13 es
# "hoy" cuando se corre este diagnóstico).

def test_promedio_rot_desestac_promedia_los_valores_no_nulos():
    assert promedio_rot_desestac([2.0, None, 4.0, None]) == 3.0


def test_promedio_rot_desestac_none_si_todos_nulos():
    assert promedio_rot_desestac([None, None]) is None


def test_promedio_rot_desestac_lista_vacia():
    assert promedio_rot_desestac([]) is None


# ── despejar_dias_con_stock ───────────────────────────────────────────────────

def test_despeje_basico():
    assert despejar_dias_con_stock(venta=30, rotacion_cliente=1.0) == 30.0


def test_despeje_none_si_no_vendio():
    assert despejar_dias_con_stock(venta=None, rotacion_cliente=1.0) is None


def test_despeje_none_si_rotacion_cero():
    # rotación 0 con venta -- no debería pasar en datos reales (si vendió,
    # rotación no puede ser 0), pero no se divide por cero igual.
    assert despejar_dias_con_stock(venta=10, rotacion_cliente=0.0) is None


def test_despeje_none_si_rotacion_none():
    assert despejar_dias_con_stock(venta=10, rotacion_cliente=None) is None


def test_despeje_none_si_venta_negativa():
    # #80: una devolución neta puede dejar la venta del mes en negativo -- caso
    # real visto en el archivo (C00078 2026-06, venta=-1). Dividir un neto
    # negativo por la rotación no tiene una lectura física de "días con
    # stock", a diferencia de un agregado donde sumar negativos sí es válido.
    assert despejar_dias_con_stock(venta=-1, rotacion_cliente=0.0275) is None


# ── coincide_dias ─────────────────────────────────────────────────────────────
#
# Los días con stock son un conteo entero de nuestro lado, pero un valor
# despejado (venta/rotación redondeada a 4 decimales) del lado del cliente --
# se compara redondeando el despejado y permitiendo ±1 día de margen (efectos
# de borde de mes / redondeo de su rotación publicada), no la tolerancia
# relativa de `coincide()` de #127 (pensada para magnitudes de rotación, no
# para un conteo de días).

def test_coincide_dias_exacto():
    assert coincide_dias(30.0, 30) is True


def test_coincide_dias_dentro_del_margen():
    assert coincide_dias(29.6, 30) is True   # redondea a 30
    assert coincide_dias(28.6, 30) is True   # redondea a 29, dentro de ±1


def test_coincide_dias_fuera_del_margen():
    assert coincide_dias(25.0, 30) is False


def test_coincide_dias_none_no_coincide():
    assert coincide_dias(None, 30) is False


# ── desvio_relativo / resumen_direccionalidad ────────────────────────────────
#
# Sirven para distinguir un desvío SISTEMÁTICO (consistente con la brecha de
# venta de depósito 2 ya diagnosticada en #196/#197, que se propaga a la
# rotación por ser venta/días) de uno disperso (que indicaría un bug de
# fórmula en vez de un insumo distinto).

def test_desvio_relativo():
    assert desvio_relativo(nuestro=0.95, cliente=1.0) == pytest.approx(-0.05)


def test_desvio_relativo_none_sin_base():
    assert desvio_relativo(nuestro=1.0, cliente=0) is None
    assert desvio_relativo(nuestro=1.0, cliente=None) is None


def test_resumen_direccionalidad_detecta_sesgo_sistematico_hacia_abajo():
    deltas = [-0.05, -0.045, -0.048, -0.052, -0.001]
    r = resumen_direccionalidad(deltas)
    assert r["bajo"] == 4  # < -1%
    assert r["alto"] == 0
    assert r["mediana"] == pytest.approx(-0.048)


def test_resumen_direccionalidad_promedia_los_dos_centrales_con_n_par():
    # n=4: el del medio verdadero es el promedio de los dos centrales
    # (-0.03 y 0.01 -> -0.01), no ordenados[n//2] (que daría 0.01, positivo --
    # invertiría el sentido del sesgo reportado).
    deltas = [-0.05, -0.03, 0.01, 0.02]
    assert resumen_direccionalidad(deltas)["mediana"] == pytest.approx(-0.01)


def test_resumen_direccionalidad_vacia():
    r = resumen_direccionalidad([])
    assert r == {"n": 0, "mediana": None, "bajo": 0, "alto": 0}


# ── bucket_venta / es_despeje_imposible ──────────────────────────────────────

@pytest.mark.parametrize("venta,esperado", [(0, "venta<5"), (4, "venta<5"), (5, "venta 5-19"),
                                             (19, "venta 5-19"), (20, "venta>=20"), (500, "venta>=20")])
def test_bucket_venta(venta, esperado):
    assert bucket_venta(venta) == esperado


def test_es_despeje_imposible_cuando_supera_los_dias_del_mes():
    # venta=2, rotación publicada=0.0478 -> despejado=41.8, un mes tiene 31
    # días como máximo -- caso real de C00072 mayo/26.
    assert es_despeje_imposible(41.8, dias_naturales=31) is True


def test_es_despeje_imposible_false_dentro_de_rango():
    assert es_despeje_imposible(25.0, dias_naturales=31) is False


# ── MAPEO_ESTADO_CLIENTE ──────────────────────────────────────────────────────

def test_mapeo_estado_cliente_es_explicito():
    assert MAPEO_ESTADO_CLIENTE == {"A": "activo", "D": "discontinuo"}
