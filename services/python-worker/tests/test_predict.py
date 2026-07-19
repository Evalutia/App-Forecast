"""Self-check para la seleccion de modelo ganador en predict.py (issue #89)
y para el flush incremental de predicciones (issue #96).

Corre sin pytest (mismo patron que test_eval_walkforward.py). Modo modulo,
no como script suelto -- si no, 'predict'/'ml' no quedan en sys.path:
    python3 -m tests.test_predict
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import predict as predict_mod
from predict import elegir_ganador, ScoredModel


class _FakeWalkForwardResult:
    def __init__(self, r2_test_median, stable=True, rmse_test_median=1.0):
        self.r2_test_median = r2_test_median
        self.stable = stable
        self.rmse_test_median = rmse_test_median


def test_elegir_ganador_devuelve_mayor_r2_test():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(0.10)),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.32)),
        ScoredModel("XGB", _FakeWalkForwardResult(0.05)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET", f"esperaba PROPHET (mayor r2_test), dio {name}"
    assert wf.r2_test_median == 0.32


def test_elegir_ganador_ignora_r2_test_none_o_nan():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(None)),
        ScoredModel("XGB", _FakeWalkForwardResult(float("nan"))),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.02)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET", f"esperaba el unico r2_test valido (PROPHET), dio {name}"


def test_elegir_ganador_volatil_igual_puede_ganar():
    # Issue #88: la volatilidad entre folds es solo informativa, no
    # descalifica al ganador -- un modelo volatil con mejor r2_test sigue
    # ganando sobre uno estable con peor r2_test.
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(0.05, stable=True)),
        ScoredModel("PROPHET", _FakeWalkForwardResult(0.32, stable=False)),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "PROPHET"
    assert wf.stable is False


def test_elegir_ganador_cae_al_primero_si_ningun_r2_test_es_valido():
    wf_results = [
        ScoredModel("RF", _FakeWalkForwardResult(None)),
        ScoredModel("XGB", _FakeWalkForwardResult(float("nan"))),
    ]
    name, wf = elegir_ganador(wf_results)
    assert name == "RF", f"esperaba caer al primero (RF), dio {name}"


class _FakeWF:
    """Doble de WalkForwardResult, solo con los campos que lee predict.py."""

    def __init__(self, r2_test_median, rmse_test_median=1.0, stable=True):
        self.r2_test_median = r2_test_median
        self.rmse_test_median = rmse_test_median
        self.stable = stable


class _FakeModelResult:
    """Doble de ModelResult (fit de referencia), solo con los campos que
    predict.py lee/asigna al construir rows_buffer."""

    def __init__(self, forecast):
        self.name = "RF"
        self.forecast = forecast
        self.rmse = 1.0
        self.r2 = 0.5
        self.params = {}
        self.features = ["lag_1"]
        self.holdout_pred = None


def _fake_sku_series(n_skus: int, n_periods: int = 30) -> dict:
    idx = pd.date_range("2022-01-01", periods=n_periods, freq="MS")
    return {
        f"SKU-{i}": pd.Series(np.linspace(10.0, 20.0, n_periods), index=idx)
        for i in range(n_skus)
    }


def test_flush_incremental_predicciones_no_espera_al_final_del_loop():
    """Issue #96: con PREDICT_PERSIST_BATCH_SIZE bajo y varios SKUs, la
    persistencia de 'predicciones' se dispara mas de una vez durante el
    loop (no una sola vez al final), y el total de filas persistidas es
    el mismo que se hubiera persistido en un unico batch final. No
    cambia el comportamiento, solo cuando se escribe (mismo patron de
    verificacion que #72 en eval_walkforward.py).

    Todas las funciones de fit/DB se mockean: no toca MySQL ni entrena
    modelos reales.
    """
    n_skus = 7
    forecast_periods = 2
    fake_series = _fake_sku_series(n_skus)

    flush_calls: list = []

    def fake_upsert_predicciones(engine, rows, job_id=None):
        flush_calls.append(list(rows))
        return len(rows)

    originals = {
        name: getattr(predict_mod, name)
        for name in (
            "PREDICT_PERSIST_BATCH_SIZE",
            "get_engine",
            "insert_job_start",
            "update_job_end",
            "upsert_predicciones",
            "load_series_by_sku",
            "fit_rf_with_walkforward",
            "fit_xgb_with_walkforward",
            "fit_rf_insample",
            "fit_xgb_insample",
        )
    }
    argv_backup = sys.argv

    try:
        predict_mod.PREDICT_PERSIST_BATCH_SIZE = 3  # flush cada 3 SKUs iterados
        predict_mod.get_engine = lambda cfg: object()
        predict_mod.insert_job_start = lambda engine, tipo_job="forecast": 1
        predict_mod.update_job_end = lambda *a, **k: None
        predict_mod.upsert_predicciones = fake_upsert_predicciones
        predict_mod.load_series_by_sku = lambda *a, **k: fake_series
        predict_mod.fit_rf_with_walkforward = lambda *a, **k: _FakeWF(0.5)
        predict_mod.fit_xgb_with_walkforward = lambda *a, **k: _FakeWF(0.3)
        predict_mod.fit_rf_insample = lambda train, steps_forecast, lags, freq: _FakeModelResult(
            np.array([10.0] * steps_forecast)
        )
        predict_mod.fit_xgb_insample = lambda train, steps_forecast, lags, freq: _FakeModelResult(
            np.array([11.0] * steps_forecast)
        )

        sys.argv = [
            "predict.py",
            "--version", "vtest-96",
            "--periods", str(forecast_periods),
            "--min-history", "1",
            "--model-set", "tree",
        ]
        predict_mod.main()
    finally:
        sys.argv = argv_backup
        for name, value in originals.items():
            setattr(predict_mod, name, value)

    assert len(flush_calls) > 1, (
        f"esperaba mas de un flush con PREDICT_PERSIST_BATCH_SIZE=3 y {n_skus} SKUs, "
        f"dio {len(flush_calls)}"
    )

    total_rows = sum(len(c) for c in flush_calls)
    esperado = n_skus * forecast_periods
    assert total_rows == esperado, (
        f"total de filas persistidas via flushes ({total_rows}) no coincide con lo que "
        f"hubiera persistido un unico batch final ({esperado}). El flush incremental "
        f"no deberia cambiar el resultado final, solo cuando se escribe"
    )

    # cadencia esperada: flush cada 3 SKUs (6 filas), mas la cola final de 1 SKU (2 filas)
    assert [len(c) for c in flush_calls] == [6, 6, 2], flush_calls


if __name__ == "__main__":
    test_elegir_ganador_devuelve_mayor_r2_test()
    test_elegir_ganador_ignora_r2_test_none_o_nan()
    test_elegir_ganador_volatil_igual_puede_ganar()
    test_elegir_ganador_cae_al_primero_si_ningun_r2_test_es_valido()
    test_flush_incremental_predicciones_no_espera_al_final_del_loop()
    print("OK - test_predict.py")
