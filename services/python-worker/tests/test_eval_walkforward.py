"""Self-check para la agregacion de walk-forward (issue #86).

Corre sin pytest (no es una dependencia de python-worker todavia):
    python3 tests/test_eval_walkforward.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.models import _aggregate_walkforward
from ml.eval_walkforward import _json_safe
import json
import math


class _FakeFoldResult:
    def __init__(self, forecast, rmse):
        self.forecast = forecast
        self.rmse = rmse


def test_rmse_test_median_is_computed_across_folds():
    idx1 = pd.date_range("2024-01-01", periods=10, freq="MS")
    train1 = pd.Series(np.arange(10, dtype="float64"), index=idx1)
    test1 = pd.Series([10.0, 11.0], index=pd.date_range("2024-11-01", periods=2, freq="MS"))

    idx2 = pd.date_range("2024-01-01", periods=12, freq="MS")
    train2 = pd.Series(np.arange(12, dtype="float64"), index=idx2)
    test2 = pd.Series([12.0, 13.0], index=pd.date_range("2025-01-01", periods=2, freq="MS"))

    folds = [(train1, test1), (train2, test2)]

    def fit_one_fold(train, horizon):
        if len(train) == 10:
            # off by 1 en cada punto de test -> rmse_test = 1.0
            return _FakeFoldResult(forecast=np.array([11.0, 12.0]), rmse=0.5)
        # match exacto -> rmse_test = 0.0
        return _FakeFoldResult(forecast=np.array([12.0, 13.0]), rmse=0.5)

    result = _aggregate_walkforward(
        name="TEST", folds=folds, fit_one_fold=fit_one_fold, horizon=2, lags=3
    )

    assert result is not None, "esperaba un WalkForwardResult, no None"
    assert result.rmse_test_median is not None, "rmse_test_median no deberia ser None"
    assert abs(result.rmse_test_median - 0.5) < 1e-9, (
        f"esperaba mediana(1.0, 0.0) = 0.5, dio {result.rmse_test_median}"
    )


def test_rmse_test_median_none_when_no_folds_succeed():
    result = _aggregate_walkforward(
        name="TEST", folds=[], fit_one_fold=lambda train, horizon: None, horizon=2, lags=3
    )
    assert result is None


def test_json_safe_replaces_nan_with_none():
    # Regresion: XGBRegressor.get_params() trae 'missing': float('nan') por
    # default -- json.dumps de eso produce el literal NaN, que MySQL rechaza
    # como JSON invalido.
    params = {"missing": float("nan"), "n_estimators": 800, "nested": {"inf": float("inf")}, "lst": [1.0, float("nan")]}
    safe = _json_safe(params)
    dumped = json.dumps(safe)  # no debe tirar, y no debe contener NaN/Infinity
    assert "NaN" not in dumped
    assert "Infinity" not in dumped
    assert safe["missing"] is None
    assert safe["n_estimators"] == 800
    assert safe["nested"]["inf"] is None
    assert safe["lst"][1] is None


if __name__ == "__main__":
    test_rmse_test_median_is_computed_across_folds()
    test_rmse_test_median_none_when_no_folds_succeed()
    test_json_safe_replaces_nan_with_none()
    print("OK - test_eval_walkforward.py")
