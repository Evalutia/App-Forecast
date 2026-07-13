import os
import numpy as np
import pandas as pd

from ml.models import (
    fit_rf_with_walkforward,
    fit_xgb_with_walkforward,
    fit_prophet_with_walkforward,
)
from ioworker.db import DBConfig, get_engine
from ioworker.data import load_series_by_sku_mysql


FREQ = os.getenv("EVAL_FREQ", "QS")
LAGS = int(os.getenv("EVAL_LAGS", "8"))
HORIZON = int(os.getenv("EVAL_HORIZON", "4"))
MAX_FOLDS = int(os.getenv("EVAL_MAX_FOLDS", "5"))

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

    series_by_sku = load_series_by_sku_mysql(
        engine, table="ventas_historicas", freq=FREQ, only_skus=ONLY_SKUS, top_n=None
    )

    rows = []  # una fila por (sku, modelo)
    for sku, s in series_by_sku.items():
        for fit_wf, kwargs in (
            (fit_rf_with_walkforward, {}),
            (fit_xgb_with_walkforward, {}),
            (fit_prophet_with_walkforward, {"sku": sku}),
        ):
            try:
                res = fit_wf(s, freq=FREQ, lags=LAGS, horizon=HORIZON, max_folds=MAX_FOLDS, **kwargs)
            except Exception:
                continue
            if res is None:
                continue
            rows.append(
                {
                    "sku": sku,
                    "model": res.name,
                    "n_folds": res.n_folds,
                    "r2_test_median": res.r2_test_median,
                    "r2_test_iqr": res.r2_test_iqr,
                    "rmse_train_median": res.rmse_train_median,
                    "mae_test_median": res.mae_test_median,
                    "n_train_rows_mean": res.n_train_rows_mean,
                    "n_train_rows_min": res.n_train_rows_min,
                    "stable": res.stable,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        print("No se obtuvieron resultados (quizás pocas series).")
        return

    if OUTPUT_CSV:
        df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nDetalle por SKU/modelo volcado a {OUTPUT_CSV}")

    # Resumen por modelo: mediana de r2_test_median entre SKUs, y desglose de confianza
    def _confianza(row):
        if row["n_folds"] <= 1:
            return "1_fold_no_evaluable"
        return "estable" if row["stable"] else "volatil"

    df["confianza"] = df.apply(_confianza, axis=1)

    summary = (
        df.groupby("model")
        .agg(
            n_skus=("sku", "count"),
            mean_n_folds=("n_folds", "mean"),
            median_r2_test=("r2_test_median", "median"),
            mean_r2_test_iqr=("r2_test_iqr", "mean"),
            mean_n_train_rows=("n_train_rows_mean", "mean"),
        )
        .reset_index()
        .sort_values("model")
    )
    print("\n== Resumen por modelo (walk-forward, todas las SKUs) ==")
    print(summary.to_string(index=False, float_format="{:.4f}".format))

    conf_counts = df.groupby(["model", "confianza"]).size().unstack(fill_value=0)
    print("\n== Confianza por modelo (folds efectivos) ==")
    print(conf_counts.to_string())

    # Simulación de la selección real de producción: por SKU, gana el menor rmse_train_median
    valid = df[df["rmse_train_median"].notna() & np.isfinite(df["rmse_train_median"])]
    if valid.empty:
        print("\nNo se pudo simular la selección real de producción (sin rmse_train_median válido).")
        return

    winners = valid.loc[valid.groupby("sku")["rmse_train_median"].idxmin()]
    median_r2_test = winners["r2_test_median"].median()
    pct_negative = (winners["r2_test_median"] < 0).mean() * 100
    pct_volatile = (winners["confianza"] == "volatil").mean() * 100
    pct_one_fold = (winners["confianza"] == "1_fold_no_evaluable").mean() * 100

    print("\n== Selección real de producción (menor RMSE in-sample mediano por SKU) ==")
    print(winners["model"].value_counts().rename("n_skus_elegido").to_string())
    print(f"\nMediana r2_test (walk-forward) del modelo elegido: {median_r2_test:.4f}")
    print(f"% de SKUs con r2_test < 0 (peor que predecir la media): {pct_negative:.1f}%")
    print(f"% de SKUs 'volátiles' entre los elegidos: {pct_volatile:.1f}%")
    print(f"% de SKUs con solo 1 fold (sin poder evaluar estabilidad): {pct_one_fold:.1f}%")

    if median_r2_test >= 0.3 and pct_negative < 25:
        veredicto = "ACEPTABLE - el modelo econometrico generaliza razonablemente, no hace falta rediseñar mas la metodologia."
    elif median_r2_test <= 0 or pct_negative > 40:
        veredicto = "REDISEÑO NECESARIO - señales claras de sobreajuste/memorizacion incluso con walk-forward."
    else:
        veredicto = "ZONA GRIS - no es claramente aceptable ni claramente roto. Documentar y decidir con el cliente."
    print(f"\nVeredicto (walk-forward, reemplaza el de #69, issue #78): {veredicto}")


if __name__ == "__main__":
    main()
