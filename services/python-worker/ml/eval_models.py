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

OUTPUT_CSV = os.getenv("EVAL_OUTPUT_CSV", "").strip() or None


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
                    "rmse_train": res.rmse_train,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        print("No se obtuvieron resultados (quizás pocas series).")
        return

    df["gap"] = df["r2_train"] - df["r2_test"]
    df["mae_rel"] = df["mae_test"] / df["mae_train"]

    if OUTPUT_CSV:
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nDetalle por SKU/modelo volcado a {OUTPUT_CSV}")

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

    # Distribución del gap por modelo (no solo el promedio)
    dist = (
        df.groupby("model")["gap"]
        .quantile([0.0, 0.25, 0.5, 0.75, 1.0])
        .unstack()
        .rename(columns={0.0: "min", 0.25: "p25", 0.5: "mediana", 0.75: "p75", 1.0: "max"})
        .reset_index()
    )
    print("\n== Distribución del gap (r2_train - r2_test) por modelo ==")
    print(dist.to_string(index=False, float_format="{:.4f}".format))

    # Simulación de la selección real de producción: por SKU, gana el menor rmse_train
    # (mismo criterio que predict.py usa para elegir el mejor modelo).
    valid = df[df["rmse_train"].notna() & np.isfinite(df["rmse_train"])]
    if valid.empty:
        print("\nNo se pudo simular la selección real de producción (sin rmse_train válido).")
        return

    winners = valid.loc[valid.groupby("sku")["rmse_train"].idxmin()]
    median_r2_test = winners["r2_test"].median()
    pct_negative = (winners["r2_test"] < 0).mean() * 100

    print("\n== Selección real de producción (menor RMSE in-sample por SKU) ==")
    print(winners["model"].value_counts().rename("n_skus_elegido").to_string())
    print(f"\nMediana r2_test del modelo elegido: {median_r2_test:.4f}")
    print(f"% de SKUs con r2_test < 0 (peor que predecir la media): {pct_negative:.1f}%")

    if median_r2_test >= 0.3 and pct_negative < 25:
        veredicto = "ACEPTABLE - el modelo econometrico generaliza razonablemente, no hace falta rediseñar la metodologia ahora."
    elif median_r2_test <= 0 or pct_negative > 40:
        veredicto = "REDISEÑO NECESARIO - señales claras de sobreajuste/memorizacion, evaluar walk-forward validation antes de seguir."
    else:
        veredicto = "ZONA GRIS - no es claramente aceptable ni claramente roto. Documentar y decidir con el cliente antes de avanzar."
    print(f"\nVeredicto (criterio documentado en CONTEXTO.md, issue #69): {veredicto}")


if __name__ == "__main__":
    main()
