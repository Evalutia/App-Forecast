import json
import os
import numpy as np
import pandas as pd

from ml.models import (
    fit_rf_with_walkforward,
    fit_xgb_with_walkforward,
    fit_prophet_with_walkforward,
    fit_ets_with_walkforward,
    _mae,
)
from ioworker.db import DBConfig, get_engine, upsert_elegibilidad_metrics, insert_catalogo_modelos
from ioworker.data import load_series_by_sku_mysql
from utils.versioning import resolve_version


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

# Issue #86: flag separado de EVAL_PERSIST -- catalogo_modelos es puro
# registro historico (nada en produccion lo lee), a diferencia de
# articulos_elegibilidad_econometrico (afecta que modelo recibe cada SKU).
# Perfil de riesgo distinto, se puede construir historial del catalogo sin
# tocar la tabla de elegibilidad y viceversa. Mismo default conservador.
PERSIST_CATALOG = os.getenv("EVAL_PERSIST_CATALOG", "").strip().lower() in ("1", "true", "yes")

# Issue #86: eval_walkforward.py no tenia ningun concepto de version hasta
# ahora -- mismo patron que predict.py (resolve_version), para poder
# filtrar corridas de catalogo_modelos por version de codigo especifica.
EVAL_VERSION = os.getenv("EVAL_VERSION", "eval-catalogo")

# Issue #72 (corrida real sobre el catalogo completo): sin esto, PERSIST/
# PERSIST_CATALOG escriben todo en un solo batch al final del loop -- una
# corrida de horas sobre ~5500 SKUs pierde el 100% del progreso si el
# proceso se corta a mitad de camino. Se flushea cada N SKUs procesados en
# vez de al final.
PERSIST_BATCH_SIZE = int(os.getenv("EVAL_PERSIST_BATCH_SIZE", "100"))


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


def _json_safe(obj):
    """
    Issue #86: XGBRegressor.get_params() trae 'missing': float('nan') por
    default -- json.dumps lo serializa como el literal NaN, que no es JSON
    valido (MySQL rechaza la insercion). Reemplaza NaN/Infinity por None
    recursivamente antes de serializar.
    """
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _finite(x):
    """Issue #86 (code review): mismo saneo de _json_safe pero para floats
    escalares que van directo a columnas DOUBLE (no a JSON) -- pymysql
    rechaza NaN/Infinity con 'nan can not be used with MySQL', confirmado
    empiricamente contra la DB local."""
    try:
        return float(x) if x is not None and np.isfinite(x) else None
    except Exception:
        return None


def _build_catalog_row(sku: str, s: pd.Series, wf_result, version: str) -> dict:
    """
    Issue #92: hiperparametros/features/r2_train/rmse_train salen del
    ModelResult que _aggregate_walkforward ya calculo para el ultimo fold
    (mayor ventana de entrenamiento) -- ver WalkForwardResult.last_fold_result.
    Antes (#86) esto hacia un fit extra sobre la serie completa solo para
    tener estos campos "limpios", duplicando el costo de cada fold (varios
    fits MCMC extra por SKU en Prophet).
    """
    name = wf_result.name
    ref = wf_result.last_fold_result
    if ref is None:
        # No deberia pasar: _build_catalog_row solo se llama cuando
        # wf_result no es None, y eso exige al menos un fold exitoso.
        print(f"[WARN] catalogo_modelos: sin last_fold_result para sku={sku} modelo={name} -- fila queda con campos in-sample en NULL.")

    # mae_train: ni ModelResult ni WalkForwardResult lo calculan -- se arma
    # aca mismo comparando el ajuste in-sample del ultimo fold contra su
    # propia ventana de entrenamiento (mismo tipo de calculo que _mae en
    # ml/models.py). ref.holdout_pred esta alineado a train.index del
    # ultimo fold, NO a s.index completo -- reindexar s hacia abajo (no
    # holdout_pred hacia arriba) evita rellenar con NaN y corromper el promedio.
    mae_train = None
    if ref is not None and ref.holdout_pred is not None:
        try:
            actual = s.reindex(ref.holdout_pred.index).values.astype("float64")
            fitted = ref.holdout_pred.values.astype("float64")
            mae_train = _mae(actual, fitted)
        except Exception:
            mae_train = None

    return {
        "sku": sku,
        "modelo": name,
        "version_modelo": version,
        "freq": FREQ,
        "fecha_primera_obs": s.index.min().date(),
        "fecha_ultima_obs": s.index.max().date(),
        "n_obs_total": int(len(s)),
        "n_obs_train": int(round(wf_result.n_train_rows_mean)),
        "n_obs_test": int(HORIZON),
        "r2_train": _finite(ref.r2) if ref is not None else None,
        "r2_test": _finite(wf_result.r2_test_median),
        "rmse_train": _finite(ref.rmse) if ref is not None else None,
        "rmse_test": _finite(wf_result.rmse_test_median),
        "mae_train": _finite(mae_train),
        "mae_test": _finite(wf_result.mae_test_median),
        "n_folds": int(wf_result.n_folds),
        "estable": wf_result.stable,
        "hiperparametros": json.dumps(_json_safe(ref.params), default=str) if ref is not None and ref.params else None,
        "features": json.dumps(ref.features) if ref is not None and ref.features else None,
    }


def main() -> None:
    db_cfg = DBConfig(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        db=os.getenv("MYSQL_DB", "evalutia"),
        user=os.getenv("MYSQL_USER", "evalutia"),
        password=os.getenv("MYSQL_PASS", ""),
    )
    engine = get_engine(db_cfg)
    version = resolve_version(EVAL_VERSION)

    series_by_sku = load_series_by_sku_mysql(
        engine, table="ventas_historicas", freq=FREQ, only_skus=ONLY_SKUS, top_n=None
    )

    meses_historia_map = _load_meses_historia(engine, ONLY_SKUS) if PERSIST else {}

    rows = []  # una fila por (sku, modelo) -- se mantiene completo en memoria para el resumen final
    catalog_rows = []  # issue #86: idem, para el resumen/no se re-lee de DB
    catalog_pending = []  # buffer que se vacia en cada flush
    elegibilidad_pending = []  # buffer que se vacia en cada flush
    n_skus_procesados = 0
    n_cat_total = 0
    n_elegibilidad_total = 0

    def _flush():
        nonlocal catalog_pending, elegibilidad_pending, n_cat_total, n_elegibilidad_total
        if PERSIST_CATALOG and catalog_pending:
            n_cat_total += insert_catalogo_modelos(engine, catalog_pending)
            catalog_pending = []
        if PERSIST and elegibilidad_pending:
            n_elegibilidad_total += upsert_elegibilidad_metrics(engine, elegibilidad_pending)
            elegibilidad_pending = []
        if PERSIST_CATALOG or PERSIST:
            print(f"[PROGRESS] {n_skus_procesados}/{len(series_by_sku)} SKUs -- "
                  f"catalogo_modelos={n_cat_total} elegibilidad={n_elegibilidad_total}")

    for sku, s in series_by_sku.items():
        sku_results = []  # resultados de este SKU (hasta 3, uno por modelo)
        for fit_wf, kwargs in (
            (fit_rf_with_walkforward, {}),
            (fit_xgb_with_walkforward, {}),
            (fit_prophet_with_walkforward, {"sku": sku}),
            (fit_ets_with_walkforward, {"sku": sku}),
        ):
            try:
                res = fit_wf(s, freq=FREQ, lags=LAGS, horizon=HORIZON, max_folds=MAX_FOLDS, **kwargs)
            except Exception:
                continue
            if res is None:
                continue
            row = {
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
            rows.append(row)
            sku_results.append(row)

            if PERSIST_CATALOG:
                try:
                    catalog_row = _build_catalog_row(sku, s, res, version)
                    catalog_rows.append(catalog_row)
                    catalog_pending.append(catalog_row)
                except Exception as e:
                    print(f"[WARN] catalogo_modelos: no se pudo construir la fila para sku={sku} modelo={res.name}: {e}")

        if PERSIST and sku_results:
            valid_sku = [r for r in sku_results if r["rmse_train_median"] is not None and np.isfinite(r["rmse_train_median"])]
            if valid_sku:
                winner = min(valid_sku, key=lambda r: r["rmse_train_median"])
                r2_test = winner["r2_test_median"]
                elegibilidad_pending.append(
                    {
                        "sku": sku,
                        "r2_test": float(r2_test) if pd.notna(r2_test) and np.isfinite(r2_test) else None,
                        "estable": (bool(winner["stable"]) if winner["stable"] is not None else None),
                        "n_folds": int(winner["n_folds"]),
                        "meses_historia": meses_historia_map.get(sku),
                    }
                )

        n_skus_procesados += 1
        if n_skus_procesados % PERSIST_BATCH_SIZE == 0:
            _flush()

    _flush()  # cola final, menor a PERSIST_BATCH_SIZE

    if PERSIST_CATALOG and n_cat_total:
        print(f"\n[PERSIST_CATALOG] {n_cat_total} filas escritas en catalogo_modelos (version={version}).")
    if PERSIST and n_elegibilidad_total:
        print(f"\n[PERSIST] {n_elegibilidad_total} filas escritas en articulos_elegibilidad_econometrico "
              f"(r2_test/estable/n_folds/meses_historia; 'elegible' sin tocar, ver #73).")

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
