#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ioworker.db import (
    DBConfig,
    get_engine,
    insert_job_start,
    update_job_end,
    upsert_predicciones,
)
from ioworker.data import load_series_by_sku, load_series_by_sku_mysql
from ml.evaluate import rmse, r2_score
from ml.models import (
    fit_sarima_insample,
    fit_ets_insample,
    fit_rf_insample,
    fit_xgb_insample,
    combine_by_inverse_rmse_insample,
    ModelResult,
    CombinedResult,
)
from utils.logging_conf import setup_logging
from utils.versioning import resolve_version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("Forecast CLI (paridad de notebook)")
    p.add_argument("--csv", type=str, help="Ruta a calendario_ventas.csv")
    p.add_argument("--freq", type=str, default="MS")
    p.add_argument("--periods", type=int, default=6)
    p.add_argument("--skus", type=str, default=None)
    p.add_argument("--min-history", type=int, default=24)
    p.add_argument("--version", type=str, required=True)
    p.add_argument("--model-set", type=str, default="full", choices=["full","classic","tree"])
    p.add_argument("--mysql-host", type=str, default=os.getenv("MYSQL_HOST"))
    p.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    p.add_argument("--mysql-db", type=str, default=os.getenv("MYSQL_DB", "evalutia"))
    p.add_argument("--mysql-user", type=str, default=os.getenv("MYSQL_USER", "evalutia"))
    p.add_argument("--mysql-pass", type=str, default=os.getenv("MYSQL_PASS", "evalutia1234-"))
    p.add_argument("--resample-rule", type=str, default="MS", choices=["MS","M"])
    p.add_argument("--resample-agg", type=str, default="sum", choices=["sum","mean","first","last"])
    p.add_argument("--fill-na", type=str, default="zero", choices=["zero","ffill","none"])
    p.add_argument("--input-source", type=str, default="csv", choices=["csv","mysql"])
    p.add_argument("--mysql-table", type=str, default="ventas_historicas")
    p.add_argument("--mysql-schema", type=str, default=None)
    p.add_argument("--debug-dump", action="store_true")
    args = p.parse_args()
    if args.input_source == "csv" and not args.csv:
        p.error("--csv es obligatorio con --input-source=csv")
    args.freq = "MS"  # el notebook usa explícitamente MS
    return args


def ensure_monthly_series(serie: pd.Series, rule: str, agg: str, fill: str) -> pd.Series:
    s = pd.Series(serie).astype("float64")
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    if agg == "sum":
        s = s.resample(rule).sum()
    elif agg == "mean":
        s = s.resample(rule).mean()
    elif agg == "first":
        s = s.resample(rule).first()
    elif agg == "last":
        s = s.resample(rule).last()
    else:
        raise ValueError("agg inválido")

    # cortar desde la primera venta > 0 (igual que notebook)
    first_sale = s[s > 0].first_valid_index()
    if first_sale is not None:
        s = s.loc[first_sale:]

    if fill in ("zero","ffill"):
        idx = pd.date_range(s.index.min(), s.index.max(), freq=rule)
        s = s.reindex(idx)
        s = s.fillna(0.0) if fill == "zero" else s.ffill().fillna(0.0)
    return s

def _sanitize_forecast(a: np.ndarray, min_val: float = 0.0, max_val: float = 1e9) -> np.ndarray:
    """
    Asegura valores válidos para DB:
    - Reemplaza NaN/Inf por 0
    - Recorta negativos a 0
    - Recorta superiores a max_val (por prudencia)
    """
    arr = np.asarray(a, dtype="float64")
    arr = np.where(np.isfinite(arr), arr, 0.0)
    arr = np.clip(arr, min_val, max_val)
    return arr

def safe_metric(val):
    """Devuelve float o None si es None/NaN/Inf (para DB)."""
    return float(round(val,4)) if (val is not None and np.isfinite(val)) else None

def as_decimal2(x: float) -> Decimal:
    return Decimal(f"{x:.2f}")


def main() -> None:
    args = parse_args()
    version = resolve_version(args.version)
    setup_logging(level="INFO")
    log = logging.getLogger("predict")

    # DB
    db_cfg = DBConfig(
        host=args.mysql_host or "localhost",
        port=args.mysql_port,
        db=args.mysql_db or "evalutia",
        user=args.mysql_user or "evalutia",
        password=args.mysql_pass or "evalutia",
    )
    engine = get_engine(db_cfg)
    job_id = insert_job_start(engine, tipo_job="forecast")
    log = logging.LoggerAdapter(log, extra={"job_id": job_id})
    t0 = time.time()

    try:
        only_skus = [s.strip() for s in args.skus.split(",")] if args.skus else None
        if args.input_source == "mysql":
            sku_series = load_series_by_sku_mysql(
                engine=engine, table=args.mysql_table, schema=args.mysql_schema, freq=args.freq, only_skus=only_skus
            )
        else:
            sku_series = load_series_by_sku(args.csv, freq=args.freq, only_skus=only_skus)

        rows_buffer: List[Dict] = []
        summary_rows: List[Dict] = []
        processed = 0
        warnings_list: List[str] = []

        for sku, serie in sku_series.items():
            try:
                serie = ensure_monthly_series(serie, rule="MS", agg="sum", fill=args.fill_na)

                if len(serie) < (12 + args.periods):
                    warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(serie)} meses)")
                    continue

                train = serie.copy()

                # Índice de forecast (igual que notebook)
                fidx = pd.date_range(
                    start=train.index[-1] + pd.offsets.MonthBegin(),
                    periods=args.periods,
                    freq="MS"
                )

                results: List[ModelResult] = []

                want_sarima = args.model_set in ("full","classic")
                want_ets    = args.model_set in ("full","classic")
                want_rf     = args.model_set in ("full","tree")
                want_xgb    = args.model_set in ("full","tree")

                if want_sarima:
                    r = fit_sarima_insample(train, steps_forecast=args.periods)
                    if r: results.append(r)
                if want_ets:
                    r = fit_ets_insample(train, steps_forecast=args.periods)
                    if r: results.append(r)
                if want_rf:
                    r = fit_rf_insample(train, steps_forecast=args.periods, lags=12)
                    if r: results.append(r)
                if want_xgb:
                    r = fit_xgb_insample(train, steps_forecast=args.periods, lags=12)
                    if r: results.append(r)

                # === COMBINADA (= notebook) ===
                combined = combine_by_inverse_rmse_insample(results, train, steps=args.periods)

                # in-sample combinado para métricas (suma ponderada de fits)
                base = [m for m in results if m.holdout_pred is not None and m.rmse is not None]
                if base:
                    # alinear fits al índice del train
                    fits = [m.holdout_pred.reindex(train.index) for m in base]
                    weights = np.array([combined.weights[m.name] for m in base], dtype="float64")
                    weights = weights / weights.sum()
                    combined_ins = sum(w * f.values for w, f in zip(weights, fits))
                    combined_ins = pd.Series(combined_ins, index=train.index)

                    # slope hack (primer paso)
                    if len(combined_ins) > 12:
                        n = 12
                        slope = (combined_ins.iloc[-1] - combined_ins.iloc[-1-n]) / n
                    else:
                        slope = 0.0
                    if len(combined.forecast) > 0:
                        alpha = 0.5
                        combined.forecast[0] = float(alpha * (combined_ins.iloc[-1] + slope) + (1 - alpha) * combined.forecast[0])

                    combined.rmse = rmse(train.values, combined_ins.values)
                    combined.r2   = r2_score(train.values, combined_ins.values)

                # --- SANEAR FORECASTS ANTES DE ESCRIBIR ---
                for r in results:
                    r.forecast = _sanitize_forecast(r.forecast)
                if combined is not None:
                    combined.forecast = _sanitize_forecast(combined.forecast)

                # === Guardar filas para DB ===
                for r in results:
                    for h, (dt, yhat) in enumerate(zip(fidx, r.forecast), start=1):
                        rows_buffer.append(
                            {
                                "sku": sku,
                                "fecha_predicha": dt.date(),
                                "cantidad_predicha": as_decimal2(float(yhat)),
                                "modelo": r.name,
                                "version_modelo": version,
                                "horizonte": h,
                                "rmse": safe_metric(r.rmse),
                                "r2":   safe_metric(r.r2),
                            }
                        )
                if combined is not None:
                    for h, (dt, yhat) in enumerate(zip(fidx, combined.forecast), start=1):
                        rows_buffer.append(
                            {
                                "sku": sku,
                                "fecha_predicha": dt.date(),
                                "cantidad_predicha": as_decimal2(float(yhat)),
                                "modelo": "COMBINADA",
                                "version_modelo": version,
                                "horizonte": h,
                                "rmse": safe_metric(combined.rmse),
                                "r2":   safe_metric(combined.r2),
                            }
                        )

                # Resumen
                for r in results + ([combined] if combined else []):
                    summary_rows.append({"sku": sku, "modelo": r.name, "rmse": r.rmse, "r2": r.r2,
                                         "features": getattr(r, "features", None)})

                # Dump debug opcional
                if args.debug_dump:
                    df_dump = pd.DataFrame({"fecha": train.index, "y_true": train.values})
                    for r in results:
                        if r.holdout_pred is not None:
                            df_dump[r.name] = r.holdout_pred.reindex(train.index).values
                    if combined and base:
                        df_dump["COMBINADA"] = combined_ins.values
                    df_dump.to_csv(f"eval_{sku}.csv", index=False)

                processed += 1

            except Exception as e:
                warnings_list.append(f"Error SKU {sku}: {e}")
                continue

        inserted = 0
        if rows_buffer:
            inserted = upsert_predicciones(engine, rows_buffer, job_id=job_id)

        modelos = sorted({r["modelo"] for r in summary_rows})
        detalle = {
            "job_id": job_id,
            "version": version,
            "periods": args.periods,
            "model_set": args.model_set,
            "skus_procesados": processed,
            "modelos": modelos,
            "warnings": warnings_list,
        }
        update_job_end(engine, job_id, estado="exitoso", detalle=detalle)

        # resumen a stdout
        if summary_rows:
            df_sum = pd.DataFrame(summary_rows)
            for c in ["rmse","r2"]:
                df_sum[c] = df_sum[c].apply(lambda x: f"{float(x):.6f}" if x is not None and np.isfinite(x) else "")
            def _feat(f):
                return "lags 1–12 + month + trend" if isinstance(f, list) and len(f)>0 else ""
            if "features" in df_sum.columns:
                df_sum["features"] = df_sum["features"].apply(_feat)
            print("\n=== Resumen por modelo/SKU ===")
            print(df_sum[["sku","modelo","rmse","r2","features"]].sort_values(["sku","modelo"]).to_string(index=False))

    except Exception as e:
        try:
            update_job_end(engine, job_id, estado="fallido", detalle={"error": str(e)})
        except Exception:
            pass
        logging.getLogger("predict").exception("Ejecución fallida")
        sys.exit(1)



if __name__ == "__main__":
    main()
