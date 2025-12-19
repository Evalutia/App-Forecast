#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
import math
import numpy as np
import pandas as pd
import json

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from ioworker.db import (
    DBConfig,
    get_engine,
    insert_job_start,
    update_job_end,
    upsert_predicciones,
)
from sqlalchemy import text
from ioworker.data import load_series_by_sku, load_series_by_sku_mysql
from ml.evaluate import rmse, r2_score
from ml.models import (
    fit_rf_insample,
    fit_xgb_insample,
    fit_prophet_insample,
    ModelResult,
)
from utils.logging_conf import setup_logging
from utils.versioning import resolve_version


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("Forecast CLI (paridad de notebook)")
    p.add_argument("--csv", type=str, help="Ruta a calendario_ventas.csv")
    # permitimos MS/M para mensual o QS/Q para trimestral
    p.add_argument("--resample-rule", type=str, default="MS", choices=["MS", "M", "QS", "Q"])
    p.add_argument(
        "--periods",
        type=int,
        default=6,
        help="Número de periodos en la frecuencia elegida (ej.: meses si MS, trimestres si QS).",
    )
    p.add_argument("--skus", type=str, default=None)
    p.add_argument("--min-history", type=int, default=24, help="Min history en meses (mantener en meses)")
    p.add_argument("--version", type=str, required=True)
    p.add_argument("--model-set", type=str, default="tree", choices=["full","classic","tree","prophet"])
    p.add_argument("--mysql-host", type=str, default=os.getenv("MYSQL_HOST"))
    p.add_argument("--mysql-port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    p.add_argument("--mysql-db", type=str, default=os.getenv("MYSQL_DB", "evalutia"))
    p.add_argument("--mysql-user", type=str, default=os.getenv("MYSQL_USER", "evalutia"))
    p.add_argument("--mysql-pass", type=str, default=os.getenv("MYSQL_PASS", "evalutia1234-"))
    p.add_argument("--resample-agg", type=str, default="sum", choices=["sum","mean","first","last"])
    p.add_argument("--fill-na", type=str, default="zero", choices=["zero","ffill","none"])
    p.add_argument("--input-source", type=str, default="csv", choices=["csv","mysql"])
    p.add_argument("--mysql-table", type=str, default="ventas_historicas")
    p.add_argument("--mysql-schema", type=str, default=None)
    p.add_argument("--debug-dump", action="store_true")
    p.add_argument(
        "--top-n",
        type=int,
        default=0,  # 0 ó negativo => sin límite, procesar todos los SKUs
        help="Considerar solo los N SKUs con mayor venta total histórica. 0 = sin límite.",
    )
    # NUEVO: forzar fecha final (la que usó el ETL). El script predice empezando en (FORCE_END + 1 día)'s period.
    p.add_argument(
        "--force-end",
        type=str,
        default=None,
        help="Fecha límite usada por el ETL (ej. '03/10/2025' o '2025-10-03'). La predicción arrancará en el periodo que contiene FORCE_END + 1 día.",
    )
    # NUEVO compatibilidad: si se pasa, se entrena sin la última fila como antes.
    p.add_argument(
        "--include-current-period",
        action="store_true",
        help="(legacy) Si se establece, el modelo se entrena sin la última fila (último periodo) y la predicción arranca en ese periodo.",
    )

    args = p.parse_args()
    # mantener compatibilidad: args.freq para pasar al loader
    args.freq = args.resample_rule
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

    # arrancar desde la primera venta efectiva dentro de la serie resampleada
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


def _sanitize_forecast(a: np.ndarray, min_val: float = 0.0, max_val: float = 1e9) -> np.ndarray:
    arr = np.asarray(a, dtype="float64")
    arr = np.where(np.isfinite(arr), arr, 0.0)
    arr = np.clip(arr, min_val, max_val)
    return arr


def safe_metric(val):
    return float(round(val, 4)) if (val is not None and np.isfinite(val)) else None


def as_decimal2(x: float) -> Decimal:
    return Decimal(f"{x:.2f}")


def _parse_force_end(force_end_str: str) -> Optional[pd.Timestamp]:
    if not force_end_str:
        return None
    # admitimos 'dd/mm/yyyy' u ISO; asumimos dayfirst=True
    try:
        return pd.to_datetime(force_end_str, dayfirst=True)
    except Exception:
        try:
            return pd.to_datetime(force_end_str)
        except Exception:
            return None


def main() -> None:
    args = parse_args()
    version = resolve_version(args.version)
    setup_logging(level="INFO")
    log = logging.getLogger("predict")

    # silenciar un poco cmdstanpy/prophet en logs
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
    logging.getLogger("prophet").setLevel(logging.WARNING)

    db_cfg = DBConfig(
        host=args.mysql_host or "localhost",
        port=args.mysql_port,
        db=args.mysql_db or "evalutia",
        user=args.mysql_user or "evalutia",
        password=args.mysql_pass or "evalutia1234-",
    )
    engine = get_engine(db_cfg)
    job_id = insert_job_start(engine, tipo_job="forecast")
    log = logging.LoggerAdapter(log, extra={"job_id": job_id})
    t0 = time.time()

    # Comprobar la última ejecución del job para detectar cambios de resample_rule/periods
    try:
        with engine.connect() as conn:
            q = """
                SELECT detalle
                FROM jobs_historial
                WHERE tipo_job = 'forecast' AND id != :job_id AND detalle IS NOT NULL
                ORDER BY fecha_inicio DESC
                LIMIT 1
            """
            res = conn.execute(text(q), {"job_id": job_id})
            row = res.fetchone()
            prev_det = None
            if row is not None and row[0]:
                try:
                    prev_det = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                except Exception:
                    prev_det = None
            if prev_det and isinstance(prev_det, dict):
                prev_rule = prev_det.get("resample_rule")
                prev_periods = prev_det.get("forecast_periods") or prev_det.get("requested_periods")
                if prev_rule and prev_rule.strip():
                    if prev_rule != args.resample_rule:
                        log.warning(
                            "Cambio detectado en resample_rule: ultima ejecución usó '%s' y ahora se pide '%s'. Verifique que '--periods' esté definido correctamente para la nueva frecuencia.",
                            prev_rule,
                            args.resample_rule,
                        )
                # advertencia si periods difiere de lo anterior (puede implicar distinto horizonte en nueva freq)
                if prev_periods is not None:
                    try:
                        prev_p = int(prev_periods)
                        if prev_p != args.periods:
                            log.info("Nota: requested periods cambió de %s a %s", prev_p, args.periods)
                    except Exception:
                        pass
    except Exception:
        # no bloquear la ejecución por fallos en esta comprobación
        log.debug("No se pudo leer jobs_historial para comparar configuración previa.")

    # parse force_end once
    force_end_dt = _parse_force_end(args.force_end)

    # top_n efectivo: 0 o negativo => sin límite
    top_n_effective: Optional[int] = args.top_n if (args.top_n and args.top_n > 0) else None

    try:
        only_skus = [s.strip() for s in args.skus.split(",")] if args.skus else None

        # Cargar series (loader ya hace recorte por primera venta si corresponde)
        if args.input_source == "mysql":
            sku_series = load_series_by_sku_mysql(
                engine=engine,
                table=args.mysql_table,
                schema=args.mysql_schema,
                freq=args.freq,
                only_skus=only_skus,
                top_n=top_n_effective,
            )
        else:
            sku_series = load_series_by_sku(
                args.csv,
                freq=args.freq,
                only_skus=only_skus,
                top_n=top_n_effective,
            )

        rows_buffer: List[Dict] = []
        summary_rows: List[Dict] = []
        processed = 0
        warnings_list: List[str] = []

        # min-history está en meses; convertir a cantidad de periodos según resample
        if args.resample_rule.upper().startswith("Q"):
            min_history_periods = math.ceil(args.min_history / 3.0)
        else:
            min_history_periods = args.min_history

        # forecast_periods := cantidad de periodos en la frecuencia elegida (args.periods ya se interpreta así)
        forecast_periods = args.periods

        # compute run_date once so all SKUs use the same 'today' anchor
        run_date = pd.Timestamp.now().normalize()

        for sku, serie in sku_series.items():
            try:
                # Asegurar series con la regla elegida
                serie = ensure_monthly_series(serie, rule=args.resample_rule, agg=args.resample_agg, fill=args.fill_na)

                if len(serie) == 0:
                    warnings_list.append(f"SKU {sku} omitido: serie vacía")
                    continue

                # Guardamos la serie completa (resampleada)
                train_full = serie.copy()

                # ============================
                # Lógica para decidir el TRAIN y el primer periodo a predecir (fidx_start)
                # ============================
                train = train_full.copy()
                fidx_start = None
                freq_str = None

                if force_end_dt is not None:
                    # Día siguiente a la última venta considerada por el ETL
                    day_after = force_end_dt + pd.Timedelta(days=1)
                    fidx_start = day_after
                    freq_str = "QS" if args.resample_rule.upper().startswith("Q") else "MS"
                    # entrenamos con todos los periodos STRICTAMENTE anteriores a fidx_start
                    train = train_full[train_full.index < fidx_start].copy()
                    if len(train) < min_history_periods:
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train)} periodos tras aplicar force-end)")
                        continue

                elif args.include_current_period:
                    # legacy behavior: quitar la última fila y predecir a partir de esa fila eliminada
                    if len(train_full) <= 1:
                        warnings_list.append(f"SKU {sku} omitido: no hay suficiente historia para --include-current-period")
                        continue
                    train = train_full.iloc[:-1].copy()
                    if args.resample_rule.upper().startswith("Q"):
                        last_sale = train_full[train_full > 0].last_valid_index()
                        if last_sale is None:
                            warnings_list.append(f"SKU {sku} omitido: sin ventas efectivas para calcular inicio trimestral")
                            continue
                        day_after = last_sale + pd.Timedelta(days=1)
                        fidx_start = day_after.to_period("Q").to_timestamp()
                        freq_str = "QS"
                    else:
                        fidx_start = train.index[-1] + pd.offsets.MonthBegin()
                        freq_str = "MS"
                    if len(train) < min_history_periods:
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train)} periodos tras quitar el último periodo)")
                        continue

                else:
                    # comportamiento original: requerimos min_history + horizon sobre la serie completa
                    if len(train_full) < (min_history_periods + forecast_periods):
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train_full)} periodos)")
                        continue
                    # entrenamos con la serie completa y predecimos a partir del periodo siguiente al último observado
                    train = train_full.copy()
                    if args.resample_rule.upper().startswith("Q"):
                        last_sale = train_full[train_full > 0].last_valid_index()
                        if last_sale is None:
                            warnings_list.append(f"SKU {sku} omitido: sin ventas efectivas para calcular inicio trimestral")
                            continue
                        day_after = last_sale + pd.Timedelta(days=1)
                        fidx_start = day_after.to_period("Q").to_timestamp()
                        freq_str = "QS"
                    else:
                        fidx_start = train.index[-1] + pd.offsets.MonthBegin()
                        freq_str = "MS"

                # ahora construimos fidx a partir de fidx_start
                if force_end_dt is not None:
                    if args.resample_rule.upper().startswith("Q"):
                        fidx_model = pd.to_datetime([fidx_start + pd.DateOffset(months=3 * i) for i in range(forecast_periods)])
                    else:
                        fidx_model = pd.to_datetime([fidx_start + pd.DateOffset(months=1 * i) for i in range(forecast_periods)])
                else:
                    fidx_model = pd.date_range(start=fidx_start, periods=forecast_periods, freq=freq_str)

                # determinar lags según frecuencia
                lags = 8 if args.resample_rule.upper().startswith("Q") else 12

                # Entrenamiento de modelos sobre 'train'
                all_results: List[ModelResult] = []

                # Selección explícita de modelos según --model-set
                if args.model_set == "prophet":
                    want_rf = False
                    want_xgb = False
                    want_prophet = True
                elif args.model_set == "tree":
                    want_rf = True
                    want_xgb = True
                    want_prophet = False
                elif args.model_set in ("full", "classic"):
                    # full / classic => RF + XGB + PROPHET
                    want_rf = True
                    want_xgb = True
                    want_prophet = True
                else:
                    # default safety: RF + XGB
                    want_rf = True
                    want_xgb = True
                    want_prophet = False

                if want_rf:
                    r = fit_rf_insample(train, steps_forecast=forecast_periods, lags=lags, freq=args.resample_rule)
                    if r:
                        all_results.append(r)
                if want_xgb:
                    r = fit_xgb_insample(train, steps_forecast=forecast_periods, lags=lags, freq=args.resample_rule)
                    if r:
                        all_results.append(r)

                if want_prophet:
                    try:
                        r = fit_prophet_insample(
                            sku=sku,
                            train=train,
                            steps_forecast=forecast_periods,
                            lags=lags,
                            freq=args.resample_rule,
                        )
                        if r:
                            all_results.append(r)
                    except Exception:
                        log.exception("Prophet error for sku %s", sku)

                if not all_results:
                    warnings_list.append(f"SKU {sku} omitido: ningún modelo produjo resultado")
                    continue

                # Sanitizar forecasts
                for r in all_results:
                    r.forecast = _sanitize_forecast(r.forecast)

                # Elegir el mejor modelo por RMSE
                best_result: Optional[ModelResult] = None
                for r in all_results:
                    if r.rmse is None or not np.isfinite(r.rmse):
                        continue
                    if best_result is None or r.rmse < best_result.rmse:
                        best_result = r
                # Si todas las métricas vienen nulas/NaN, quedarnos con el primero
                if best_result is None:
                    best_result = all_results[0]

                # ----------------------------
                # Construir las fechas que SE VAN A PERSISTIR: la primera fecha es
                # SIEMPRE "run_date" (fecha exacta de ejecución) y las siguientes avancen
                # en meses/trimestres.
                # ----------------------------
                fecha_preds: List = []
                if args.resample_rule.upper().startswith("Q"):
                    for i in range(forecast_periods):
                        fecha_preds.append((run_date + pd.DateOffset(months=3 * i)).date())
                else:
                    for i in range(forecast_periods):
                        fecha_preds.append((run_date + pd.DateOffset(months=1 * i)).date())

                # Persistir filas de predicciones SOLO del mejor modelo
                for h, (dt_model, yhat, fecha_pred) in enumerate(
                    zip(fidx_model, best_result.forecast, fecha_preds), start=1
                ):
                    rows_buffer.append(
                        {
                            "sku": sku,
                            "fecha_predicha": fecha_pred,
                            "cantidad_predicha": as_decimal2(float(yhat)),
                            "modelo": best_result.name,
                            "version_modelo": version,
                            "horizonte": h,
                            "rmse": safe_metric(best_result.rmse),
                            "r2": safe_metric(best_result.r2),
                        }
                    )

                # Resumen por modelo (solo el ganador)
                summary_rows.append(
                    {
                        "sku": sku,
                        "modelo": best_result.name,
                        "rmse": best_result.rmse,
                        "r2": best_result.r2,
                        "features": getattr(best_result, "features", None),
                    }
                )

                # Dump opcional para inspección
                if args.debug_dump:
                    df_dump = pd.DataFrame({"fecha": train_full.index, "y_true": train_full.values})
                    for r in all_results:
                        if r.holdout_pred is not None:
                            df_dump[r.name] = r.holdout_pred.reindex(train_full.index).values
                    df_dump.to_csv(f"eval_{sku}.csv", index=False)

                processed += 1

            except Exception as e:
                warnings_list.append(f"Error SKU {sku}: {e}")
                log.exception("Error procesando SKU %s", sku)
                continue

        inserted = 0
        if rows_buffer:
            inserted = upsert_predicciones(engine, rows_buffer, job_id=job_id)

        modelos = sorted({r["modelo"] for r in summary_rows})
        detalle = {
            "job_id": job_id,
            "version": version,
            "requested_periods": args.periods,
            "forecast_periods": forecast_periods,
            "resample_rule": args.resample_rule,
            "force_end": str(args.force_end),
            "include_current_period": bool(args.include_current_period),
            "skus_procesados": processed,
            "modelos": modelos,
            "warnings": warnings_list,
        }
        update_job_end(engine, job_id, estado="exitoso", detalle=detalle)

        if summary_rows:
            df_sum = pd.DataFrame(summary_rows)
            for c in ["rmse", "r2"]:
                df_sum[c] = df_sum[c].apply(
                    lambda x: f"{float(x):.6f}" if x is not None and np.isfinite(x) else ""
                )

            def _feat(f):
                if isinstance(f, list) and len(f) > 0:
                    nlags = sum(1 for col in f if col.startswith("lag_"))
                    period_name = "quarter" if any(col == "period" for col in f) else "month"
                    return f"lags 1–{nlags} + {period_name} + trend"
                return ""

            if "features" in df_sum.columns:
                df_sum["features"] = df_sum["features"].apply(_feat)

            print("\n=== Resumen por modelo/SKU ===")
            print(
                df_sum[["sku", "modelo", "rmse", "r2", "features"]]
                .sort_values(["sku", "modelo"])
                .to_string(index=False)
            )

    except Exception as e:
        try:
            update_job_end(engine, job_id, estado="fallido", detalle={"error": str(e)})
        except Exception:
            pass
        logging.getLogger("predict").exception("Ejecución fallida")
        sys.exit(1)


if __name__ == "__main__":
    main()