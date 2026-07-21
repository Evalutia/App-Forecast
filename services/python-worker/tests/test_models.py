"""Self-check para los modelos univariados ETS (issue #98) y SARIMA (issue #99).

Corre sin pytest (mismo patron que los demas tests de este directorio). Modo
modulo, no como script suelto -- si no, 'ml' no queda en sys.path:
    python3 -m tests.test_models
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.models import (
    fit_ets_insample,
    fit_ets_with_walkforward,
    fit_sarima_insample,
    fit_sarima_with_walkforward,
)


def _serie_trimestral_sintetica(n_periodos: int, con_negativo: bool = False) -> pd.Series:
    """Serie trimestral con tendencia + estacionalidad clara, suficiente para
    que ETS estacional (seasonal_periods=4) tenga de donde aprender."""
    idx = pd.date_range("2018-01-01", periods=n_periodos, freq="QS")
    trend = np.linspace(100.0, 100.0 + 5.0 * n_periodos, n_periodos)
    estacional = np.tile([10.0, -5.0, 20.0, -10.0], int(np.ceil(n_periodos / 4)))[:n_periodos]
    valores = trend + estacional
    if con_negativo:
        # Issue #81: una nota de credito real puede dejar la venta neta de un
        # periodo en negativo -- no debe descartarse ni crashear el fit.
        valores[4] = -50.0
    return pd.Series(valores, index=idx)


def test_fit_ets_insample_produce_resultado_valido_con_historia_suficiente():
    train = _serie_trimestral_sintetica(16)  # 4 años, bien por encima del minimo
    result = fit_ets_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")

    assert result is not None, "esperaba un ModelResult, no None"
    assert result.name == "ETS"
    assert len(result.forecast) == 4
    assert np.isfinite(result.forecast).all(), "el forecast no deberia tener NaN/Inf"
    assert result.rmse is not None and np.isfinite(result.rmse)
    assert result.r2 is not None and np.isfinite(result.r2)
    assert result.holdout_pred is not None
    assert len(result.holdout_pred) == len(train), (
        "holdout_pred deberia cubrir todas las filas de train, sin descartar ninguna"
    )


def test_fit_ets_insample_no_crashea_ni_descarta_filas_con_valor_negativo():
    # Issue #81 (lección ya aplicada a Prophet): una nota de credito es un
    # dato de entrenamiento real -- no se filtra antes de entrenar.
    train = _serie_trimestral_sintetica(16, con_negativo=True)
    result = fit_ets_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")

    assert result is not None, "ETS no deberia crashear con un valor negativo en el training"
    assert len(result.holdout_pred) == len(train), (
        "el valor negativo no deberia haberse descartado de la serie de entrenamiento"
    )
    # el forecast futuro si se clampea a no-negativo (igual que Prophet) --
    # pero eso no afecta los datos de entrenamiento en si.
    assert (result.forecast >= 0.0).all()


def test_fit_ets_insample_serie_corta_devuelve_none():
    # Muy por debajo de 2 ciclos estacionales completos (8 trimestres).
    train = _serie_trimestral_sintetica(4)
    result = fit_ets_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")
    assert result is None, "una serie con menos de 2 ciclos estacionales deberia devolver None"


def test_fit_ets_with_walkforward_produce_resultado_con_historia_suficiente():
    train = _serie_trimestral_sintetica(24)  # 6 años, para dejar margen a varios folds
    result = fit_ets_with_walkforward(train, freq="QS", lags=8, horizon=4, max_folds=5, sku="SKU-TEST")
    assert result is not None, "esperaba un WalkForwardResult con historia suficiente"
    assert result.name == "ETS"
    assert result.n_folds >= 1


def test_fit_sarima_insample_produce_resultado_valido_con_historia_suficiente():
    train = _serie_trimestral_sintetica(16)  # 4 años, bien por encima del minimo
    result = fit_sarima_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")

    assert result is not None, "esperaba un ModelResult, no None"
    assert result.name == "SARIMA"
    assert len(result.forecast) == 4
    assert np.isfinite(result.forecast).all(), "el forecast no deberia tener NaN/Inf"
    assert result.rmse is not None and np.isfinite(result.rmse)
    assert result.r2 is not None and np.isfinite(result.r2)
    assert result.holdout_pred is not None
    assert len(result.holdout_pred) == len(train), (
        "holdout_pred deberia cubrir todas las filas de train, sin descartar ninguna"
    )


def test_fit_sarima_insample_no_crashea_ni_descarta_filas_con_valor_negativo():
    # Issue #81 (leccion ya aplicada a Prophet/ETS): una nota de credito es un
    # dato de entrenamiento real -- no se filtra antes de entrenar.
    train = _serie_trimestral_sintetica(16, con_negativo=True)
    result = fit_sarima_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")

    assert result is not None, "SARIMA no deberia crashear con un valor negativo en el training"
    assert len(result.holdout_pred) == len(train), (
        "el valor negativo no deberia haberse descartado de la serie de entrenamiento"
    )
    # el forecast futuro si se clampea a no-negativo (igual que Prophet/ETS) --
    # pero eso no afecta los datos de entrenamiento en si.
    assert (result.forecast >= 0.0).all()


def test_fit_sarima_insample_serie_corta_devuelve_none():
    # Muy por debajo de 2 ciclos estacionales completos (8 trimestres).
    train = _serie_trimestral_sintetica(4)
    result = fit_sarima_insample(sku="SKU-TEST", train=train, steps_forecast=4, lags=8, freq="QS")
    assert result is None, "una serie con menos de 2 ciclos estacionales deberia devolver None"


def test_fit_sarima_with_walkforward_produce_resultado_con_historia_suficiente():
    train = _serie_trimestral_sintetica(24)  # 6 años, para dejar margen a varios folds
    result = fit_sarima_with_walkforward(train, freq="QS", lags=8, horizon=4, max_folds=5, sku="SKU-TEST")
    assert result is not None, "esperaba un WalkForwardResult con historia suficiente"
    assert result.name == "SARIMA"
    assert result.n_folds >= 1


if __name__ == "__main__":
    test_fit_ets_insample_produce_resultado_valido_con_historia_suficiente()
    test_fit_ets_insample_no_crashea_ni_descarta_filas_con_valor_negativo()
    test_fit_ets_insample_serie_corta_devuelve_none()
    test_fit_ets_with_walkforward_produce_resultado_con_historia_suficiente()
    test_fit_sarima_insample_produce_resultado_valido_con_historia_suficiente()
    test_fit_sarima_insample_no_crashea_ni_descarta_filas_con_valor_negativo()
    test_fit_sarima_insample_serie_corta_devuelve_none()
    test_fit_sarima_with_walkforward_produce_resultado_con_historia_suficiente()
    print("OK - test_models.py")
