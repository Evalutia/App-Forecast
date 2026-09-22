"""
Tests de las funciones puras de scripts/medir_deposito2.py (issue #197). Mismo
patrón que #195/#196: el script vive en scripts/, se agrega ese directorio al
path.

Las funciones de I/O (conexión a MySQL, extracción real del WS) no se testean
acá -- se verifican por integración contra producción, vía túnel SSH, igual
que #127/#187/#195/#196.
"""
import os
import sys

import pytest

_RAIZ = os.path.abspath(__file__)
for _ in range(4):  # tests -> etl -> services -> raiz del repo
    _RAIZ = os.path.dirname(_RAIZ)
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))

from comparar_ventas_mensual import (  # noqa: E402
    FilaDiscrepancia,
    totales_mensuales_nuestros,
)
from medir_deposito2 import (  # noqa: E402
    comparar_contra_deficit,
    deficit_mensual,
)


def _fila(sku, year, month, diff_abs, categoria=None):
    if categoria is None:
        categoria = "coincide" if diff_abs == 0 else ("deficit" if diff_abs < 0 else "superavit")
    return FilaDiscrepancia(
        sku=sku, year=year, month=month, cohorte="pre",
        cliente_original=None, cliente_numerico=abs(diff_abs), nuestro=0,
        diff_abs=diff_abs, diff_rel=None, categoria=categoria)


# ── deficit_mensual ──────────────────────────────────────────────────────────

def test_deficit_mensual_suma_solo_las_filas_deficit():
    filas = [
        _fila("C001", 2025, 8, -5),   # deficit
        _fila("C002", 2025, 8, -3),   # deficit
        _fila("C003", 2025, 8, 7),    # superavit, no suma
        _fila("C004", 2025, 8, 0),    # coincide, no suma
    ]
    assert deficit_mensual(filas) == {(2025, 8): 8}


def test_deficit_mensual_reporta_positivo_no_negativo():
    # El déficit es "cuánto nos falta", una magnitud -- no el signo crudo de
    # diff_abs (que es negativo por convención de #196: nuestro - cliente).
    filas = [_fila("C001", 2025, 8, -100)]
    assert deficit_mensual(filas)[(2025, 8)] == 100


def test_deficit_mensual_separa_por_mes():
    filas = [_fila("C001", 2025, 8, -5), _fila("C001", 2025, 9, -2)]
    assert deficit_mensual(filas) == {(2025, 8): 5, (2025, 9): 2}


def test_deficit_mensual_vacio_sin_filas_deficit():
    filas = [_fila("C001", 2025, 8, 3), _fila("C001", 2025, 9, 0)]
    assert deficit_mensual(filas) == {}


# ── comparar_contra_deficit ──────────────────────────────────────────────────

def test_comparar_calcula_pct_explicado_por_mes():
    deposito2 = {(2025, 8): 40, (2025, 9): 10}
    deficit = {(2025, 8): 100, (2025, 9): 50}
    resultado = comparar_contra_deficit(deposito2, deficit)
    assert resultado[(2025, 8)] == {"deposito2": 40, "deficit": 100, "pct_explicado": 40.0}
    assert resultado[(2025, 9)] == {"deposito2": 10, "deficit": 50, "pct_explicado": 20.0}


def test_comparar_incluye_meses_con_deficit_pero_sin_venta_de_deposito2():
    # Si depósito 2 no vendió nada ese mes, el mes igual tiene que aparecer --
    # 0% explicado es una respuesta real, no un mes ausente del reporte.
    resultado = comparar_contra_deficit({}, {(2025, 8): 100})
    assert resultado[(2025, 8)] == {"deposito2": 0, "deficit": 100, "pct_explicado": 0.0}


def test_comparar_incluye_meses_con_venta_de_deposito2_pero_sin_deficit():
    # Caso raro pero real: depósito 2 vendió pero ese mes no había déficit (tal
    # vez otro efecto lo compensó). pct_explicado no tiene denominador -- None,
    # no ZeroDivisionError ni un 0% que sugeriría falsamente "no aporta nada".
    resultado = comparar_contra_deficit({(2025, 8): 15}, {})
    assert resultado[(2025, 8)] == {"deposito2": 15, "deficit": 0, "pct_explicado": None}


def test_comparar_permite_que_deposito2_supere_el_deficit_del_mes():
    # Si depósito 2 vendió más que todo el déficit medido, el % puede pasar de
    # 100 -- es información real (indicio de que compensa otras causas
    # superávit), no hay que clampear.
    resultado = comparar_contra_deficit({(2025, 8): 150}, {(2025, 8): 100})
    assert resultado[(2025, 8)]["pct_explicado"] == 150.0


def test_comparar_totales_mensuales_nuestros_es_reusable_para_deposito2():
    # totales_mensuales_nuestros (#196) es genérica sobre {(sku,y,m):u} ->
    # {(y,m):u} -- sirve igual para el agregado de depósito 2, sin duplicar.
    agregados_dep2 = {("C001", 2025, 8): 10, ("C002", 2025, 8): 5}
    assert totales_mensuales_nuestros(agregados_dep2) == {(2025, 8): 15}
