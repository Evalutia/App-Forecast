#!/usr/bin/env python3
# Simplified predict.py to use ml_nn for forecasts (quarterly by default)
from __future__ import annotations
import argparse
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
import pandas as pd
import numpy as np
import logging

from ioworker.db import (
    DBConfig,
    get_engine,
    insert_job_start,
    update_job_end,
    upsert_predicciones,
)
from ioworker.data import load_series_by_sku, load_series_by_sku_mysql
from ml_nn.predict import predict_for_sku
from utils.logging_conf import setup_logging
from utils.versioning import resolve_version


def as_decimal2(x: float) -> Decimal:
    return Decimal(f"{x:.2f}")


def safe_metric(val):
    return float(round(val, 4)) if (val is not None and np.isfinite(val)) else None


def _parse_force_end(force_end_str: str):
    if not force_end_str:
        return None
    try:
        return pd.to_datetime(force_end_str, dayfirst=True)
    except Exception:
        try:
            return pd.to_datetime(force_end_str)
        except Exception:
            return None


def ensure_periodic_series(serie: pd.Series, rule: str, agg: str, fill: str):
    # keep compatibility with earlier helper
    s = pd.Series(serie).astype("float64")
    s.index = pd.to_datetime(s.index)
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
    first_sale = s[s > 0].first_valid_index()
    if first_sale is not None:
        s = s.loc[first_sale:]
    if len(s) == 0:
        return s
    if fill in ("zero", "ffill"):
        idx = pd.date_range(s.index.min(), s.index.max(), freq=rule)
        s = s.reindex(idx)
        s = s.fillna(0.0) if fill == "zero" else s.ffill().fillna(0.0)
    return s


def main():
    parser = argparse.ArgumentParser("Forecast CLI (neural)")
    parser.add_argument("--csv", type=str, help="Ruta a calendario_ventas.csv")
    parser.add_argument("--resample-rule", type=str, default="Q", choices=["Q","QS","MS","M","QS"])
    parser.add_argument("--periods", type=int, default=2, help="Horizonte (en periodos de la regla). Default: 2 trimestres")
    parser.add_argument("--version", type=str, required=True)
    parser.add_argument("--input-source", type=str, default="csv", choices=["csv","mysql"])
    parser.add_argument("--mysql-host", type=str, default=os.getenv("MYSQL_HOST"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT","3306")))
    parser.add_argument("--mysql-db", type=str, default=os.getenv("MYSQL_DB","evalutia"))
    parser.add_argument("--mysql-user", type=str, default=os.getenv("MYSQL_USER","evalutia"))
    parser.add_argument("--mysql-pass", type=str, default=os.getenv("MYSQL_PASS","evalutia1234-"))
    parser.add_argument("--debug-dump", action="store_true")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--checkpoint", type=str, default="checkpoints/best_model.pth")
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()
    setup_logging(level="INFO")
    log = logging.getLogger("predict_nn")

    db_cfg = DBConfig(
        host=args.mysql_host or "localhost",
        port=args.mysql_port,
        db=args.mysql_db or "evalutia",
        user=args.mysql_user or "evalutia",
        password=args.mysql_pass or "evalutia1234-",
    )
    engine = get_engine(db_cfg)
    job_id = insert_job_start(engine, tipo_job="forecast_nn")
    log = logging.LoggerAdapter(log, extra={"job_id": job_id})
    t0 = time.time()

    try:
        only_skus = None
        if args.input_source == "mysql":
            sku_series = load_series_by_sku_mysql(engine=engine, table="ventas_historicas", schema=None, freq=args.resample_rule, only_skus=only_skus, top_n=args.top_n)
        else:
            sku_series = load_series_by_sku(args.csv, freq=args.resample_rule, only_skus=only_skus, top_n=args.top_n)

        rows_buffer = []
        summary_rows = []
        processed = 0
        warnings_list = []

        run_date = pd.Timestamp.now().normalize()
        for sku, serie in sku_series.items():
            try:
                s = ensure_periodic_series(serie, rule=args.resample_rule, agg="sum", fill="zero")
                if len(s) == 0:
                    warnings_list.append(f"SKU {sku} omitido: serie vacía")
                    continue
                # pedir predicción a ml_nn (devuelve lista de floats: length = periods)
                preds = predict_for_sku(s, checkpoint_path=args.checkpoint, device=args.device, rule=args.resample_rule)
                # sanitize and clip
                preds = [max(0.0, float(p)) for p in preds][:args.periods]
                # persistir: usaremos fechas empezando en run_date y avanzando por periodos
                fecha_preds = []
                if args.resample_rule.upper().startswith("Q"):
                    for i in range(args.periods):
                        fecha_preds.append((run_date + pd.DateOffset(months=3*i)).date())
                else:
                    for i in range(args.periods):
                        fecha_preds.append((run_date + pd.DateOffset(months=1*i)).date())
                for h, (yhat, fecha_pred) in enumerate(zip(preds, fecha_preds), start=1):
                    rows_buffer.append({
                        "sku": sku,
                        "fecha_predicha": fecha_pred,
                        "cantidad_predicha": as_decimal2(float(yhat)),
                        "modelo": "NBEATS_NN",
                        "version_modelo": resolve_version(args.version),
                        "horizonte": h,
                        "rmse": None,
                        "r2": None,
                    })
                summary_rows.append({
                    "sku": sku,
                    "modelo": "NBEATS_NN",
                    "rmse": None,
                    "r2": None,
                    "features": ["neural_nbeats"]
                })
                processed += 1
            except Exception as e:
                warnings_list.append(f"Error SKU {sku}: {e}")
                log.exception("Error procesando SKU %s", sku)
                continue

        inserted = 0
        if rows_buffer:
            inserted = upsert_predicciones(engine, rows_buffer, job_id=job_id)

        detalle = {
            "job_id": job_id,
            "version": resolve_version(args.version),
            "requested_periods": args.periods,
            "forecast_periods": args.periods,
            "resample_rule": args.resample_rule,
            "skus_procesados": processed,
            "modelos": ["NBEATS_NN"],
            "warnings": warnings_list,
        }
        update_job_end(engine, job_id, estado="exitoso", detalle=detalle)
        print("Predicciones insertadas:", inserted)
    except Exception as e:
        try:
            update_job_end(engine, job_id, estado="fallido", detalle={"error": str(e)})
        except Exception:
            pass
        logging.getLogger("predict_nn").exception("Ejecución fallida")
        sys.exit(1)


if __name__ == "__main__":
    main()
