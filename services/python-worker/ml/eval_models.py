import os
import numpy as np
import pandas as pd

from ml.evaluate import r2_score
from ml.models import (
    fit_rf_with_holdout,
    fit_xgb_with_holdout,
    fit_prophet_with_holdout,
)
from ioworker.db import DBConfig, get_engine
from ioworker.data import load_series_by_sku_mysql


FREQ = os.getenv("EVAL_FREQ", "QS")
TEST_YEARS = int(os.getenv("EVAL_TEST_YEARS", "1"))
LAGS = int(os.getenv("EVAL_LAGS", "8"))
FORECAST_PERIODS = int(os.getenv("EVAL_FORECAST_PERIODS", "2"))

_only_skus_raw = os.getenv("EVAL_ONLY_SKUS", "").strip()
ONLY_SKUS = [s.strip() for s in _only_skus_raw.split(",") if s.strip()] if _only_skus_raw else None


def main() -> None:
    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    # Cargar series de SKUs (todas por default, o solo EVAL_ONLY_SKUS si se seteó)
    series_by_sku = load_series_by_sku_mysql(
        engine, table="ventas_historicas", freq=FREQ, only_skus=ONLY_SKUS, top_n=None
    )

    rows = []  # filas por (sku, modelo)
    for sku, s in series_by_sku.items():
        for fit_holdout, kwargs in (
            (fit_rf_with_holdout, {}),
            (fit_xgb_with_holdout, {}),
            (fit_prophet_with_holdout, {"sku": sku}),
        ):
            try:
                res = fit_holdout(
                    s, freq=FREQ, forecast_periods=FORECAST_PERIODS, lags=LAGS, years_test=TEST_YEARS, **kwargs
                )
            except Exception:
                continue
            if res is None:
                continue
            rows.append(
                {
                    "sku": sku,
                    "model": res.name,
                    "r2_train": res.r2_train,
                    "r2_test": res.r2_test,
                    "mae_train": res.mae_train,
                    "mae_test": res.mae_test,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        print("No se obtuvieron resultados (quizás pocas series).")
        return

    df["gap"] = df["r2_train"] - df["r2_test"]
    df["mae_rel"] = df["mae_test"] / df["mae_train"]
    # Resumen por modelo (promedio sobre todos los SKUs)
    summary = (
        df.groupby(["model"])
        .agg(
            mean_r2_train=("r2_train", "mean"),
            mean_r2_test=("r2_test", "mean"),
            mean_mae_train=("mae_train", "mean"),
            mean_mae_test=("mae_test", "mean"),
            mean_mae_rel=("mae_rel", "mean"),
            mean_gap=("gap", "mean"),
            n_skus=("r2_test", "count"),
        )
        .reset_index()
        .sort_values(["model"])
    )
    print("\n== Resumen por modelo (promedio sobre todos los SKUs) ==")
    print(summary.to_string(index=False, float_format="{:.4f}".format))


if __name__ == "__main__":
    main()
