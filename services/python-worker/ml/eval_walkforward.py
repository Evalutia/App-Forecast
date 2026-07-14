import os
import numpy as np
import pandas as pd

from ml.models import (
    fit_rf_with_walkforward,
    fit_xgb_with_walkforward,
    fit_prophet_with_walkforward,
)
from ioworker.db import DBConfig, get_engine, upsert_elegibilidad_metrics
from ioworker.data import load_series_by_sku_mysql


FREQ = os.getenv("EVAL_FREQ", "QS")
LAGS = int(os.getenv("EVAL_LAGS", "8"))
HORIZON = int(os.getenv("EVAL_HORIZON", "4"))
MAX_FOLDS = int(os.getenv("EVAL_MAX_FOLDS", "5"))

_only_skus_raw = os.getenv("EVAL_ONLY_SKUS", "").strip()
ONLY_SKUS = [s.strip() for s in _only_skus_raw.split(",") if s.strip()] if _only_skus_raw else None

OUTPUT_CSV = os.getenv("EVAL_OUTPUT_CSV", "").strip() or None

# Issue #72: si esta seteado, persiste metricas crudas por SKU en
# articulos_elegibilidad_econometrico (no toca 'elegible', ver #73).
# Default off para no cambiar el comportamiento de diagnostico puro que ya
# usaban #69/#78 contra DB local.
PERSIST = os.getenv("EVAL_PERSIST", "").strip().lower() in ("1", "true", "yes")


def _load_meses_historia(engine, only_skus) -> dict:
    """
    Span calendario real por SKU (fecha_max - fecha_min + 1 mes), calculado
    directo contra ventas_historicas -- no se deriva de la serie ya
    resampleada de load_series_by_sku_mysql, que trunca desde la primera
    venta con cantidad > 0 y por lo tanto subestimaria la historia real de
    un SKU cuyas filas iniciales fueran solo notas de credito (ver #81).
    """
    q = """
        SELECT sku, TIMESTAMPDIFF(MONTH, MIN(fecha), MAX(fecha)) + 1 AS meses_historia
        FROM ventas_historicas
        GROUP BY sku
    """
    df = pd.read_sql_query(q, con=engine)
    if only_skus:
        only = set(s.strip() for s in only_skus if s and s.strip())
        df = df[df["sku"].isin(only)]
    return dict(zip(df["sku"], df["meses_historia"].astype(int)))


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

    if PERSIST:
        meses_historia_map = _load_meses_historia(engine, ONLY_SKUS)
        rows_to_persist = []
        for _, row in winners.iterrows():
            r2_test = row["r2_test_median"]
            rows_to_persist.append(
                {
                    "sku": row["sku"],
                    "r2_test": float(r2_test) if pd.notna(r2_test) and np.isfinite(r2_test) else None,
                    "estable": (bool(row["stable"]) if row["stable"] is not None else None),
                    "n_folds": int(row["n_folds"]),
                    "meses_historia": meses_historia_map.get(row["sku"]),
                }
            )
        n_persisted = upsert_elegibilidad_metrics(engine, rows_to_persist)
        print(f"\n[PERSIST] {n_persisted} filas escritas en articulos_elegibilidad_econometrico (r2_test/estable/n_folds/meses_historia; 'elegible' sin tocar, ver #73).")


if __name__ == "__main__":
    main()
