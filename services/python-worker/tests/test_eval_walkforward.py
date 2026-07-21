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


def test_folds_con_pocas_filas_utiles_se_excluyen_del_promedio():
    # Issue #97: un fold cuya ventana de entrenamiento, ya restados los
    # lags, deja menos filas utiles que 'lags' no aporta senal real -- el
    # modelo no tiene de donde aprender una relacion, predice casi una
    # constante, y r2_score satura en 0.0/1.0 exacto (degenerado). Con
    # lags=3: train de 4 filas -> eff_lags=3, n_train_rows=1 (<3, se
    # descarta); train de 10 filas -> eff_lags=3, n_train_rows=7 (>=3, cuenta).
    idx_chico = pd.date_range("2024-01-01", periods=4, freq="MS")
    train_chico = pd.Series(np.arange(4, dtype="float64"), index=idx_chico)
    test_chico = pd.Series([4.0, 5.0], index=pd.date_range("2024-05-01", periods=2, freq="MS"))

    idx_grande = pd.date_range("2024-01-01", periods=10, freq="MS")
    train_grande = pd.Series(np.arange(10, dtype="float64"), index=idx_grande)
    test_grande = pd.Series([10.0, 11.0], index=pd.date_range("2024-11-01", periods=2, freq="MS"))

    folds = [(train_chico, test_chico), (train_grande, test_grande)]

    def fit_one_fold(train, horizon):
        if len(train) == 4:
            # constante degenerada -- si este fold contara, r2 seria 0.0/1.0 exacto
            return _FakeFoldResult(forecast=np.array([999.0, 999.0]), rmse=0.5)
        return _FakeFoldResult(forecast=np.array([11.0, 12.0]), rmse=0.5)

    result = _aggregate_walkforward(
        name="TEST", folds=folds, fit_one_fold=fit_one_fold, horizon=2, lags=3
    )

    assert result is not None
    assert result.n_folds == 1, f"esperaba solo el fold grande (n_train_rows=7>=lags), dio n_folds={result.n_folds}"
    assert result.n_train_rows_mean == 7.0, f"esperaba n_train_rows_mean=7 (solo el fold grande), dio {result.n_train_rows_mean}"


def test_walkforward_result_none_si_todos_los_folds_degeneran():
    # Issue #97: si TODOS los folds quedan por debajo del piso de
    # n_train_rows, el WalkForwardResult debe ser None -- mismo
    # comportamiento que cuando ningun fold produce forecast valido hoy.
    idx = pd.date_range("2024-01-01", periods=4, freq="MS")
    train = pd.Series(np.arange(4, dtype="float64"), index=idx)
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-05-01", periods=2, freq="MS"))

    result = _aggregate_walkforward(
        name="TEST",
        folds=[(train, test)],
        fit_one_fold=lambda tr, h: _FakeFoldResult(forecast=np.array([999.0, 999.0]), rmse=0.5),
        horizon=2,
        lags=3,
    )

    assert result is None, "todos los folds degenerados (n_train_rows<lags) -> deberia ser None, no un resultado con senal falsa"


def test_filtro_de_n_train_rows_no_aplica_a_prophet():
    # Issue #97 (hallazgo de /code-review): el piso n_train_rows>=lags viene
    # de como RF/XGB construyen features de lag (_build_lag_month_trend) --
    # fit_prophet_insample recibe 'lags' pero NUNCA lo usa para features,
    # solo chequea internamente len(tr)>=min_needed. Aplicarle el mismo
    # piso a Prophet descartaria folds validos sin ninguna base real.
    # Mismo fold "chico" que en test_walkforward_result_none_si_todos...
    # (n_train_rows=1 < lags=3), pero con name="PROPHET" debe SI contar.
    idx = pd.date_range("2024-01-01", periods=4, freq="MS")
    train = pd.Series(np.arange(4, dtype="float64"), index=idx)
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-05-01", periods=2, freq="MS"))

    result = _aggregate_walkforward(
        name="PROPHET",
        folds=[(train, test)],
        fit_one_fold=lambda tr, h: _FakeFoldResult(forecast=np.array([4.0, 5.0]), rmse=0.0),
        horizon=2,
        lags=3,
    )

    assert result is not None, "Prophet no deberia quedar excluido por el piso de n_train_rows -- no le aplica"
    assert result.n_folds == 1


def test_filtro_de_n_train_rows_no_aplica_a_ets():
    # Issue #98 (mismo trato que Prophet en #97): ETS es univariado, no
    # consume 'lags' como features tabulares (fit_ets_insample recibe
    # 'lags' solo para mantener la misma firma que el resto de los
    # fit_*_insample, pero jamas lo usa para construir columnas lag_N).
    # El piso n_train_rows>=lags viene exclusivamente de como RF/XGB
    # construyen _build_lag_month_trend -- no le aplica a ETS, que tiene
    # su propio gate interno de historia minima (2 ciclos estacionales).
    idx = pd.date_range("2024-01-01", periods=4, freq="MS")
    train = pd.Series(np.arange(4, dtype="float64"), index=idx)
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-05-01", periods=2, freq="MS"))

    result = _aggregate_walkforward(
        name="ETS",
        folds=[(train, test)],
        fit_one_fold=lambda tr, h: _FakeFoldResult(forecast=np.array([4.0, 5.0]), rmse=0.0),
        horizon=2,
        lags=3,
    )

    assert result is not None, "ETS no deberia quedar excluido por el piso de n_train_rows -- no le aplica"
    assert result.n_folds == 1


def test_filtro_de_n_train_rows_no_aplica_a_sarima():
    # Issue #99 (mismo trato que Prophet/ETS): SARIMA es univariado, no
    # consume 'lags' como features tabulares (fit_sarima_insample recibe
    # 'lags' solo para mantener la misma firma que el resto de los
    # fit_*_insample, pero jamas lo usa para construir columnas lag_N).
    # El piso n_train_rows>=lags viene exclusivamente de como RF/XGB
    # construyen _build_lag_month_trend -- no le aplica a SARIMA, que tiene
    # su propio gate interno de historia minima (2 ciclos estacionales).
    idx = pd.date_range("2024-01-01", periods=4, freq="MS")
    train = pd.Series(np.arange(4, dtype="float64"), index=idx)
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-05-01", periods=2, freq="MS"))

    result = _aggregate_walkforward(
        name="SARIMA",
        folds=[(train, test)],
        fit_one_fold=lambda tr, h: _FakeFoldResult(forecast=np.array([4.0, 5.0]), rmse=0.0),
        horizon=2,
        lags=3,
    )

    assert result is not None, "SARIMA no deberia quedar excluido por el piso de n_train_rows -- no le aplica"
    assert result.n_folds == 1


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
    test_folds_con_pocas_filas_utiles_se_excluyen_del_promedio()
    test_walkforward_result_none_si_todos_los_folds_degeneran()
    test_filtro_de_n_train_rows_no_aplica_a_prophet()
    test_filtro_de_n_train_rows_no_aplica_a_ets()
    test_filtro_de_n_train_rows_no_aplica_a_sarima()
    test_json_safe_replaces_nan_with_none()
    print("OK - test_eval_walkforward.py")
