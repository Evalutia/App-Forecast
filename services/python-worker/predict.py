#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

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
from ml.evaluate import holdout_split, rmse, r2_score
from ml.features import make_lag_matrix, recursive_forecast_tree
from ml.models import (
    fit_ets,
    fit_sarima,
    fit_rf,
    fit_xgb,
    ModelResult,
    CombinedResult,
    combine_by_inverse_rmse,
)
from utils.logging_conf import setup_logging
from utils.versioning import resolve_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Forecasting CLI (SARIMA/ETS/RF/XGB/COMBINADA) y escritura en MySQL."
    )
    parser.add_argument("--csv", type=str, help="Ruta a calendario_ventas.csv")
    parser.add_argument("--freq", type=str, default="MS", help="Frecuencia de resampleo (default MS)")
    parser.add_argument("--periods", type=int, default=6, help="Meses a pronosticar")
    parser.add_argument("--skus", type=str, default=None, help='Lista de SKUs "SKU1,SKU2"')
    parser.add_argument("--min-history", type=int, default=24, help="Mínimo histórico por SKU")
    parser.add_argument("--version", type=str, required=True, help="Versión del modelo a guardar")
    parser.add_argument(
        "--model-set",
        type=str,
        default="full",
        choices=["full", "classic", "tree"],
        help="full=SARIMA+ETS+RF+XGB+COMBINADA; classic=SARIMA+ETS; tree=RF+XGB",
    )
    parser.add_argument("--mysql-host", type=str, default=os.getenv("MYSQL_HOST"))
    parser.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-db", type=str, default=os.getenv("MYSQL_DB", "evalutia"))
    parser.add_argument("--mysql-user", type=str, default=os.getenv("MYSQL_USER", "evalutia"))
    parser.add_argument("--mysql-pass", type=str, default=os.getenv("MYSQL_PASS", "evalutia1234-"))
    parser.add_argument("--start-month", type=str, default=None,
                        help="YYYY-MM del primer mes a pronosticar (default: mes siguiente al último dato)")
    parser.add_argument("--log-level", type=str, default="INFO", help="Nivel de logs")

    # Fuente de datos
    parser.add_argument("--input-source", type=str, default="csv", choices=["csv", "mysql"],
                        help="Origen de datos: csv (por defecto) o mysql")
    parser.add_argument("--mysql-table", type=str, default="ventas_historicas",
                        help="Tabla MySQL con columnas fecha, sku, cantidad (default: ventas_historicas)")
    parser.add_argument("--mysql-schema", type=str, default=None,
                        help="Schema/Base opcional si difiere de MYSQL_DB")

    args = parser.parse_args()
    if args.input_source == "csv" and not args.csv:
        parser.error("--csv es obligatorio cuando --input-source=csv")
    return args



def months_gap(base_next: pd.Timestamp, target_start: pd.Timestamp, freq: str) -> int:
    """Cantidad de meses entre base_next y target_start (si target está después)."""
    if freq not in ("MS", "M"):
        raise ValueError("Solo se contemplan frecuencias mensuales (MS/M).")
    b = pd.Timestamp(base_next).to_period("M")
    t = pd.Timestamp(target_start).to_period("M")
    diff = (t.year - b.year) * 12 + (t.month - b.month)
    return int(diff) if diff > 0 else 0


def forecast_index(start_month: pd.Timestamp, periods: int, freq: str) -> pd.DatetimeIndex:
    return pd.date_range(start=start_month, periods=periods, freq=freq)


def as_decimal2(x: float) -> Decimal:
    return Decimal(f"{x:.2f}")


def main() -> None:
    args = parse_args()

    version = resolve_version(args.version)
    setup_logging(level=args.log_level)

    log = logging.getLogger("predict")
    log.info("Inicializando ejecución", extra={"version": version})

    # Config DB
    db_cfg = DBConfig(
        host=args.mysql_host or "localhost",
        port=args.mysql_port,
        db=args.mysql_db or "evalutia",
        user=args.mysql_user or "evalutia",
        password=args.mysql_pass or "evalutia",
    )
    engine = get_engine(db_cfg)

    # Inserta registro de job al comenzar
    job_id = insert_job_start(engine, tipo_job="forecast")
    log = logging.LoggerAdapter(log, extra={"job_id": job_id})  # inyecta job_id en todos los logs
    t0 = time.time()

    try:
        # Carga datos
        only_skus = None
        if args.skus:
            only_skus = [s.strip() for s in args.skus.split(",") if s.strip()]

        if args.input_source == "mysql":
            sku_series = load_series_by_sku_mysql(
                engine=engine,
                table=args.mysql_table,
                schema=args.mysql_schema,
                freq=args.freq,
                only_skus=only_skus,
            )
        else:
            sku_series = load_series_by_sku(
                csv_path=args.csv,
                freq=args.freq,
                only_skus=only_skus,
            )

        if not sku_series:
            raise RuntimeError("No se cargaron series por SKU. Verifique el CSV y los filtros.")

        # Determina fecha de inicio del forecast
        # Si no se pasa --start-month => mes siguiente al último dato de cada SKU
        start_month_cli = (
            pd.to_datetime(args.start_month, format="%Y-%m").to_period("M").to_timestamp()
            if args.start_month
            else None
        )

        # Selección de modelos
        want_sarima = args.model_set in ("full", "classic")
        want_ets = args.model_set in ("full", "classic")
        want_rf = args.model_set in ("full", "tree")
        want_xgb = args.model_set in ("full", "tree")
        want_comb = args.model_set == "full"

        rf_params = {
            "n_estimators": 400,
            "max_depth": 8,
            "min_samples_leaf": 2,
            "random_state": 42,
            "n_jobs": -1,
        }
        xgb_params = {
            "objective": "reg:squarederror",
            "n_estimators": 600,
            "max_depth": 6,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "n_jobs": -1,
        }

        processed = 0
        rows_buffer: List[Dict] = []
        warnings: List[str] = []
        summary_rows: List[Dict] = []  # para la impresión final

        for sku, serie in sku_series.items():
            try:
                # Filtra por mínimo histórico
                if len(serie.dropna()) < args.min_history:
                    msg = f"SKU {sku} omitido por historial insuficiente ({len(serie)} < {args.min_history})."
                    log.warning(msg)
                    warnings.append(msg)
                    continue

                # Holdout para métricas (asunción: últimos 6 puntos)
                train, test = holdout_split(serie, k=min(6, args.periods))

                # Determina fechas de forecast reales
                last_train_month = train.index.max().to_period("M").to_timestamp()
                desired_start = (
                    start_month_cli
                    if start_month_cli is not None
                    else (serie.index.max().to_period("M").to_timestamp() + pd.offsets.MonthBegin(1))
                )
                base_next = last_train_month + pd.offsets.MonthBegin(1)
                lead_in = months_gap(base_next=base_next, target_start=desired_start, freq=args.freq)

                # Ejecuta modelos
                results: List[ModelResult] = []

                if want_sarima:
                    res = fit_sarima(train, test, steps_eval=len(test), steps_forecast=lead_in + args.periods)
                    if res is not None:
                        # recorta para alinear con desired_start
                        if lead_in:
                            res.forecast = res.forecast[lead_in:]
                        results.append(res)
                        summary_rows.append(
                            {"sku": sku, "modelo": "SARIMA", "rmse": res.rmse, "r2": res.r2, "params": res.params}
                        )

                if want_ets:
                    res = fit_ets(train, test, steps_eval=len(test), steps_forecast=lead_in + args.periods)
                    if res is not None:
                        if lead_in:
                            res.forecast = res.forecast[lead_in:]
                        results.append(res)
                        summary_rows.append(
                            {"sku": sku, "modelo": "ETS", "rmse": res.rmse, "r2": res.r2, "params": res.params}
                        )

                if want_rf:
                    res = fit_rf(
                        train,
                        test,
                        steps_eval=len(test),
                        steps_forecast=lead_in + args.periods,
                        rf_params=rf_params,
                        lags=12,
                    )
                    if res is not None:
                        if lead_in:
                            res.forecast = res.forecast[lead_in:]
                        results.append(res)
                        summary_rows.append(
                            {
                                "sku": sku,
                                "modelo": "RF",
                                "rmse": res.rmse,
                                "r2": res.r2,
                                "params": res.params,
                                "features": res.features,
                            }
                        )

                if want_xgb:
                    res = fit_xgb(
                        train,
                        test,
                        steps_eval=len(test),
                        steps_forecast=lead_in + args.periods,
                        xgb_params=xgb_params,
                        lags=12,
                    )
                    if res is not None:
                        if lead_in:
                            res.forecast = res.forecast[lead_in:]
                        results.append(res)
                        summary_rows.append(
                            {
                                "sku": sku,
                                "modelo": "XGB",
                                "rmse": res.rmse,
                                "r2": res.r2,
                                "params": res.params,
                                "features": res.features,
                            }
                        )

                # COMBINADA (si al menos 2 modelos válidos, o 1 => copia)
                combined: Optional[CombinedResult] = None
                if want_comb and results:
                    combined = combine_by_inverse_rmse(results, steps=args.periods)

                    base = [r for r in results if r.holdout_pred is not None and r.rmse is not None]
                    if base and len(test) > 0:
                        min_len = min(len(r.holdout_pred) for r in base)
                        y_true = test.values[:min_len]
                        y_pred = np.zeros(min_len)
                        for r in base:
                            w = combined.weights.get(r.name, 0.0)
                            y_pred += w * np.asarray(r.holdout_pred[:min_len])
                        combined.rmse = rmse(y_true, y_pred)
                        combined.r2 = r2_score(y_true, y_pred)
                        
                    summary_rows.append(
                        {
                            "sku": sku,
                            "modelo": "COMBINADA",
                            "rmse": combined.rmse,
                            "r2": combined.r2,
                            "params": {"weights": combined.weights},
                        }
                    )

                # Index del forecast final
                fidx = forecast_index(start_month=desired_start, periods=args.periods, freq=args.freq)

                # Construye filas para DB
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
                                "rmse": float(r.rmse) if r.rmse is not None else None,
                                "r2": float(r.r2) if r.r2 is not None else None,
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
                                "rmse": float(combined.rmse) if combined.rmse is not None else None,
                                "r2": float(combined.r2) if combined.r2 is not None else None,
                            }
                        )

                processed += 1

            except Exception as e:
                msg = f"Error procesando SKU {sku}: {e}"
                log.exception(msg)
                warnings.append(msg)
                continue

        # Inserción/upsert a MySQL
        inserted = 0
        if rows_buffer:
            inserted = upsert_predicciones(engine, rows_buffer)

        # Detalle para jobs_historial
        modelos_ejecutados = sorted({r["modelo"] for r in summary_rows})
        detalle = {
            "job_id": job_id,
            "version": version,
            "periods": args.periods,
            "model_set": args.model_set,
            "skus_procesados": processed,
            "modelos": modelos_ejecutados,
            "hiperparam_rf": rf_params if want_rf else None,
            "hiperparam_xgb": xgb_params if want_xgb else None,
            "features_rf": [f"lag_{i}" for i in range(1, 13)] if want_rf else None,
            "features_xgb": [f"lag_{i}" for i in range(1, 13)] if want_xgb else None,
            "warnings": warnings,
        }

        # Finaliza job
        update_job_end(engine, job_id, estado="exitoso", detalle=detalle)

        # --- Resumen tabular requerido ---
        if summary_rows:
            df_sum = pd.DataFrame(summary_rows)
            # Orden de columnas
            cols = ["sku", "modelo", "rmse", "r2", "params", "features"]
            for c in cols:
                if c not in df_sum.columns:
                    df_sum[c] = None
            df_sum = df_sum[cols]
            print("\n=== Resumen por modelo/SKU ===")
            print(df_sum.to_string(index=False))

        dur = time.time() - t0
        print("\n--- RESULTADO ---")
        print(f"Ruta de inserción: MySQL://{db_cfg.user}@{db_cfg.host}:{db_cfg.port}/{db_cfg.db}")
        print(f"job_id: {job_id}")
        print(f"Filas upsert en predicciones: {inserted}")
        print(f"Tiempo total: {dur:.2f}s")

    except Exception as e:
        detalle = {
            "job_id": job_id,
            "error": str(e),
            "warnings": [],
        }
        try:
            update_job_end(engine, job_id, estado="fallido", detalle=detalle)
        except Exception:
            pass
        logging.getLogger("predict").exception("Ejecución fallida")
        sys.exit(1)


if __name__ == "__main__":
    main()
