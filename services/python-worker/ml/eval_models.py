import os
import numpy as np
import pandas as pd

from ml.evaluate import r2_score
from ml.models import (
    fit_xgb_with_holdout_multi,
)
from ioworker.db import DBConfig, get_engine
from ioworker.data import load_series_by_sku_mysql


FREQ = os.getenv("EVAL_FREQ", "QS")
TEST_YEARS = int(os.getenv("EVAL_TEST_YEARS", "1"))
LAGS = int(os.getenv("EVAL_LAGS", "8"))
FORECAST_PERIODS = int(os.getenv("EVAL_FORECAST_PERIODS", "2"))


def main() -> None:
    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)

    # Cargar TODAS las series de SKUs (sin tope de TOP_N)
    series_by_sku = load_series_by_sku_mysql(
        engine, table="ventas_historicas", freq=FREQ, only_skus=None, top_n=None
    )

    rows = []  # filas por (sku, modelo)
    for sku, s in series_by_sku.items():
        try:
            # Solo modelos XGB (features simples) con holdout
            xgb_results = fit_xgb_with_holdout_multi(
                s, freq=FREQ, forecast_periods=FORECAST_PERIODS, lags=LAGS, years_test=TEST_YEARS
            )
            for model_name, xgb_res in xgb_results.items():
                if xgb_res is None:
                    continue
                rows.append(
                    {
                        "sku": sku,
                        "model": model_name,
                        "r2_train": xgb_res.r2_train,
                        "r2_test": xgb_res.r2_test,
                        "mae_train": xgb_res.mae_train,
                        "mae_test": xgb_res.mae_test,
                    }
                )
        except Exception:
            continue

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
