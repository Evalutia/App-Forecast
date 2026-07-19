"""Self-check para la agregacion de walk-forward (issue #86).

Corre sin pytest (no es una dependencia de python-worker todavia). Modo
modulo, no como script suelto -- si no, 'ml' no queda en sys.path:
    python3 -m tests.test_eval_walkforward
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.models import _aggregate_walkforward
from ml.eval_walkforward import _json_safe, _build_catalog_row
import json
import math


class _FakeFoldResult:
    def __init__(self, forecast, rmse, r2=0.5, params=None, features=None, holdout_pred=None):
        self.forecast = forecast
        self.rmse = rmse
        self.r2 = r2
        self.params = params if params is not None else {}
        self.features = features if features is not None else []
        self.holdout_pred = holdout_pred


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


def test_last_fold_result_es_el_ultimo_fold_exitoso():
    # Issue #92: WalkForwardResult debe retener el ModelResult del ultimo
    # fold (mayor ventana de entrenamiento) para que _build_catalog_row no
    # tenga que re-fitear sobre la serie completa.
    idx1 = pd.date_range("2024-01-01", periods=10, freq="MS")
    train1 = pd.Series(np.arange(10, dtype="float64"), index=idx1)
    test1 = pd.Series([10.0, 11.0], index=pd.date_range("2024-11-01", periods=2, freq="MS"))

    idx2 = pd.date_range("2024-01-01", periods=12, freq="MS")
    train2 = pd.Series(np.arange(12, dtype="float64"), index=idx2)
    test2 = pd.Series([12.0, 13.0], index=pd.date_range("2025-01-01", periods=2, freq="MS"))

    folds = [(train1, test1), (train2, test2)]

    resultado_fold_1 = _FakeFoldResult(forecast=np.array([11.0, 12.0]), rmse=0.5, params={"fold": 1})
    resultado_fold_2 = _FakeFoldResult(forecast=np.array([12.0, 13.0]), rmse=0.5, params={"fold": 2})

    def fit_one_fold(train, horizon):
        return resultado_fold_1 if len(train) == 10 else resultado_fold_2

    result = _aggregate_walkforward(
        name="TEST", folds=folds, fit_one_fold=fit_one_fold, horizon=2, lags=3
    )

    assert result.last_fold_result is resultado_fold_2, (
        "esperaba el ModelResult del fold con mayor ventana de entrenamiento (train2)"
    )


def test_last_fold_result_ignora_folds_que_fallan():
    # Si el ultimo fold en la lista falla (fit_one_fold devuelve None), el
    # ultimo fold EXITOSO debe seguir siendo el que queda capturado, no None.
    idx1 = pd.date_range("2024-01-01", periods=10, freq="MS")
    train1 = pd.Series(np.arange(10, dtype="float64"), index=idx1)
    test1 = pd.Series([10.0, 11.0], index=pd.date_range("2024-11-01", periods=2, freq="MS"))

    idx2 = pd.date_range("2024-01-01", periods=12, freq="MS")
    train2 = pd.Series(np.arange(12, dtype="float64"), index=idx2)
    test2 = pd.Series([12.0, 13.0], index=pd.date_range("2025-01-01", periods=2, freq="MS"))

    folds = [(train1, test1), (train2, test2)]

    resultado_fold_1 = _FakeFoldResult(forecast=np.array([11.0, 12.0]), rmse=0.5, params={"fold": 1})

    def fit_one_fold(train, horizon):
        return resultado_fold_1 if len(train) == 10 else None

    result = _aggregate_walkforward(
        name="TEST", folds=folds, fit_one_fold=fit_one_fold, horizon=2, lags=3
    )

    assert result.last_fold_result is resultado_fold_1, (
        "el ultimo fold fallo -- last_fold_result debe quedar en el ultimo EXITOSO, no en None"
    )


class _FakeWalkForwardResult:
    def __init__(self, last_fold_result):
        self.name = "RF"
        self.n_folds = 3
        self.r2_test_median = 0.4
        self.rmse_test_median = 1.2
        self.mae_test_median = 0.9
        self.n_train_rows_mean = 8.0
        self.stable = True
        self.last_fold_result = last_fold_result


def test_build_catalog_row_usa_last_fold_result_sin_refit():
    # Issue #92: _build_catalog_row ya no hace un fit extra sobre la serie
    # completa -- toma hiperparametros/features/r2_train/rmse_train
    # directamente del ModelResult que trae wf_result.last_fold_result.
    s = pd.Series(
        np.arange(12, dtype="float64"),
        index=pd.date_range("2024-01-01", periods=12, freq="MS"),
    )
    # holdout_pred del ultimo fold cubre solo train.index (10 primeros
    # puntos), no la serie completa -- asi se ve si el reindex esta bien.
    holdout_idx = s.index[:10]
    holdout_pred = pd.Series(np.arange(10, dtype="float64") + 0.5, index=holdout_idx)

    ref = _FakeFoldResult(
        forecast=np.array([1.0]), rmse=0.3, r2=0.7,
        params={"n_estimators": 200}, features=["lag_1", "lag_2"],
        holdout_pred=holdout_pred,
    )
    wf_result = _FakeWalkForwardResult(last_fold_result=ref)

    row = _build_catalog_row("SKU-TEST", s, wf_result, version="v1")

    assert row["r2_train"] == 0.7
    assert row["rmse_train"] == 0.3
    assert json.loads(row["hiperparametros"]) == {"n_estimators": 200}
    assert json.loads(row["features"]) == ["lag_1", "lag_2"]
    # actual - fitted = 0.5 en cada uno de los 10 puntos cubiertos -> mae 0.5
    assert row["mae_train"] is not None and abs(row["mae_train"] - 0.5) < 1e-9, (
        f"esperaba mae_train=0.5 (reindex correcto contra holdout_pred.index), dio {row['mae_train']}"
    )


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
    test_last_fold_result_es_el_ultimo_fold_exitoso()
    test_last_fold_result_ignora_folds_que_fallan()
    test_build_catalog_row_usa_last_fold_result_sin_refit()
    test_json_safe_replaces_nan_with_none()
    print("OK - test_eval_walkforward.py")
