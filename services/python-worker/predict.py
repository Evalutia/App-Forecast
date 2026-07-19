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
from typing import Dict, List, NamedTuple, Optional

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
    fit_rf_with_walkforward,
    fit_xgb_with_walkforward,
    fit_prophet_with_walkforward,
    ModelResult,
    WalkForwardResult,
)
from utils.logging_conf import setup_logging
from utils.versioning import resolve_version

# Issue #89: tope de folds walk-forward por SKU al elegir el modelo ganador --
# mismo default que EVAL_MAX_FOLDS en eval_walkforward.py (#72).
PREDICT_MAX_FOLDS = int(os.getenv("PREDICT_MAX_FOLDS", "5"))

# Issue #95: horizonte fijo para la evaluacion walk-forward interna de
# predict.py -- NO usar forecast_periods (la distancia real de forecast,
# PREDICT_PERIODS=2 en produccion) ahi, un fold con solo 2 puntos de test
# hace que r2_score (correlacion de Pearson al cuadrado) de siempre 1.0 sin
# importar la calidad real del ajuste (ver r2_score en ml/evaluate.py).
# Mismo default que EVAL_HORIZON en eval_walkforward.py (#72) -- misma
# metodologia que #70/#72/#73 ya usan para elegibilidad.
PREDICT_EVAL_HORIZON = int(os.getenv("PREDICT_EVAL_HORIZON", "4"))

# Issue #96: mismo problema que tenia eval_walkforward.py antes del fix de
# #72 -- rows_buffer se acumulaba entero en memoria y recien se persistia
# una vez, al final del loop completo. Con el catalogo ampliado (#73/#75)
# y walk-forward mas pesado por SKU (#89/#95), una corrida nocturna real
# que se corte a mitad de camino perderia el 100% del progreso, no solo lo
# que faltaba. Se flushea cada N SKUs iterados en vez de al final.
PREDICT_PERSIST_BATCH_SIZE = int(os.getenv("PREDICT_PERSIST_BATCH_SIZE", "50"))


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


class ScoredModel(NamedTuple):
    name: str
    wf: WalkForwardResult


def elegir_ganador(wf_results: List[ScoredModel]) -> ScoredModel:
    """
    Issue #89: elige el modelo ganador por SKU por mejor r2_test walk-forward
    (issue #88) -- reemplaza el criterio anterior de menor RMSE in-sample,
    demostrado propenso a sobreajuste (#68/#78). `wf_results` ya viene
    filtrada a resultados no-None. La volatilidad entre folds
    (WalkForwardResult.stable) queda solo informativa -- no descalifica al
    ganador, mismo principio de transparencia que #70. Si ningún candidato
    tiene r2_test_median válido, cae al primero (mismo fallback que el
    criterio anterior).
    """
    winner: Optional[ScoredModel] = None
    for candidate in wf_results:
        if candidate.wf.r2_test_median is None or not np.isfinite(candidate.wf.r2_test_median):
            continue
        if winner is None or candidate.wf.r2_test_median > winner.wf.r2_test_median:
            winner = candidate
    return winner if winner is not None else wf_results[0]


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

    # Issue #95: con <3 puntos de test por fold, r2_score (correlacion de
    # Pearson al cuadrado) es matematicamente degenerado (siempre 0.0/1.0,
    # ver docstring en ml/evaluate.py) -- un override de PREDICT_EVAL_HORIZON
    # por debajo de ese piso reintroduce en silencio el bug que motivo #95.
    if PREDICT_EVAL_HORIZON < 3:
        log.warning(
            "PREDICT_EVAL_HORIZON=%s es degenerado para r2_score (necesita >=3 "
            "puntos de test por fold) -- ver issue #95. La seleccion de modelo "
            "y el r2 persistido van a quedar sin sentido.",
            PREDICT_EVAL_HORIZON,
        )

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

        rows_buffer: List[Dict] = []  # buffer que se vacia en cada flush (issue #96)
        summary_rows: List[Dict] = []
        processed = 0
        inserted = 0
        warnings_list: List[str] = []
        n_skus_iterados = 0

        def _flush_predicciones():
            nonlocal rows_buffer, inserted
            if rows_buffer:
                inserted += upsert_predicciones(engine, rows_buffer, job_id=job_id)
                rows_buffer = []
            log.info(
                "[PROGRESS] %d/%d SKUs -- procesados=%d predicciones=%d",
                n_skus_iterados, len(sku_series), processed, inserted,
            )

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
                    # Issue #89/#95: el walk-forward exige len(train) >= horizon + 2
                    # (walk_forward_split, min_train=2), y el horizonte real que se usa
                    # para evaluar es PREDICT_EVAL_HORIZON (#95), no forecast_periods --
                    # el margen tiene que cubrir el mayor de los dos, si no un SKU podia
                    # pasar este gate y aun asi no producir ningun fold, perdiendo el
                    # forecast por completo en vez de solo perder precision.
                    if len(train) < (min_history_periods + max(forecast_periods, PREDICT_EVAL_HORIZON)):
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train)} periodos tras aplicar force-end)")
                        continue

                elif args.include_current_period:
                    # legacy behavior: quitar la última fila y predecir a partir de esa fila eliminada
                    if len(train_full) <= 1:
                        warnings_list.append(f"SKU {sku} omitido: no hay suficiente historia para --include-current-period")
                        continue
                    train = train_full.iloc[:-1].copy()
                    if args.resample_rule.upper().startswith("Q"):
                        # Issue #81: sin filtro de signo -- si el ultimo periodo real es
                        # neto negativo (nota de credito), igual es el punto de corte
                        # correcto. Filtrar por > 0 saltaba hacia atras al ultimo periodo
                        # positivo y corria mal la ventana de pronostico.
                        last_sale = train_full.last_valid_index()
                        if last_sale is None:
                            warnings_list.append(f"SKU {sku} omitido: sin historia real para calcular inicio trimestral")
                            continue
                        day_after = last_sale + pd.Timedelta(days=1)
                        fidx_start = day_after.to_period("Q").to_timestamp()
                        freq_str = "QS"
                    else:
                        fidx_start = train.index[-1] + pd.offsets.MonthBegin()
                        freq_str = "MS"
                    # Issue #89/#95: mismo margen que el path de force-end.
                    if len(train) < (min_history_periods + max(forecast_periods, PREDICT_EVAL_HORIZON)):
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train)} periodos tras quitar el último periodo)")
                        continue

                else:
                    # comportamiento original: requerimos min_history + horizon sobre la
                    # serie completa -- issue #95: horizon es el mayor entre forecast_periods
                    # (fit de referencia) y PREDICT_EVAL_HORIZON (walk-forward).
                    if len(train_full) < (min_history_periods + max(forecast_periods, PREDICT_EVAL_HORIZON)):
                        warnings_list.append(f"SKU {sku} omitido por pocos datos ({len(train_full)} periodos)")
                        continue
                    # entrenamos con la serie completa y predecimos a partir del periodo siguiente al último observado
                    train = train_full.copy()
                    if args.resample_rule.upper().startswith("Q"):
                        # Issue #81: sin filtro de signo -- si el ultimo periodo real es
                        # neto negativo (nota de credito), igual es el punto de corte
                        # correcto. Filtrar por > 0 saltaba hacia atras al ultimo periodo
                        # positivo y corria mal la ventana de pronostico.
                        last_sale = train_full.last_valid_index()
                        if last_sale is None:
                            warnings_list.append(f"SKU {sku} omitido: sin historia real para calcular inicio trimestral")
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

                # Issue #89: el ganador por SKU se elige por r2_test walk-forward real
                # (issue #88) en vez de RMSE in-sample -- este ultimo ya se demostro
                # propenso a sobreajuste (#68/#78), misma metrica que #70 ya usa para
                # elegibilidad.
                #
                # Issue #95 (bug real encontrado en el piloto de #74 contra la VM de
                # produccion): el horizonte de evaluacion NO usa forecast_periods (la
                # distancia real que se predice). PREDICT_PERIODS en produccion es 2,
                # y r2_score = (correlacion de Pearson)^2 -- con exactamente 2 puntos de
                # test por fold, esa correlacion es matematicamente siempre +-1, asi que
                # r2_test da siempre 1.0 sin importar la calidad real de la prediccion
                # (confirmado empiricamente: 9/9 SKUs de un piloto real dieron r2=1.0
                # exacto). Se usa un horizonte fijo no degenerado (PREDICT_EVAL_HORIZON,
                # mismo default que EVAL_HORIZON en eval_walkforward.py/#72) para elegir
                # el ganador -- restaura la misma metodologia que #70/#72/#73 ya usan
                # para elegibilidad, una sola fuente de verdad para "que tan bien
                # generaliza este modelo". El forecast final que se persiste sigue
                # siendo a forecast_periods reales (viene del fit de referencia aparte).
                wf_results: List[ScoredModel] = []
                if want_rf:
                    wf = fit_rf_with_walkforward(
                        train, freq=args.resample_rule, lags=lags, horizon=PREDICT_EVAL_HORIZON, max_folds=PREDICT_MAX_FOLDS
                    )
                    if wf:
                        wf_results.append(ScoredModel("RF", wf))
                if want_xgb:
                    wf = fit_xgb_with_walkforward(
                        train, freq=args.resample_rule, lags=lags, horizon=PREDICT_EVAL_HORIZON, max_folds=PREDICT_MAX_FOLDS
                    )
                    if wf:
                        wf_results.append(ScoredModel("XGB", wf))
                if want_prophet:
                    try:
                        wf = fit_prophet_with_walkforward(
                            train, freq=args.resample_rule, lags=lags, horizon=PREDICT_EVAL_HORIZON,
                            max_folds=PREDICT_MAX_FOLDS, sku=sku,
                        )
                        if wf:
                            wf_results.append(ScoredModel("PROPHET", wf))
                    except Exception:
                        log.exception("Prophet walkforward error for sku %s", sku)

                if not wf_results:
                    warnings_list.append(f"SKU {sku} omitido: ningún modelo produjo resultado")
                    continue

                winner_name, winner_wf = elegir_ganador(wf_results)

                # WalkForwardResult no trae forecast_future (solo metricas) -- una vez
                # elegido el ganador, se hace un fit de referencia in-sample sobre toda
                # la historia disponible para conseguir el forecast real. Mismo patron ya
                # usado en eval_walkforward.py (#86) para catalogo_modelos -- ahi
                # steps_forecast=1 (solo necesita hiperparametros/features), aca
                # steps_forecast=forecast_periods (necesita el forecast real); no cambia
                # las metricas in-sample del fit, solo el largo del array de forecast.
                reference_fitters = {
                    "RF": lambda: fit_rf_insample(train, steps_forecast=forecast_periods, lags=lags, freq=args.resample_rule),
                    "XGB": lambda: fit_xgb_insample(train, steps_forecast=forecast_periods, lags=lags, freq=args.resample_rule),
                    "PROPHET": lambda: fit_prophet_insample(
                        sku=sku, train=train, steps_forecast=forecast_periods, lags=lags, freq=args.resample_rule
                    ),
                }
                best_result: Optional[ModelResult] = reference_fitters[winner_name]()
                if best_result is None:
                    warnings_list.append(f"SKU {sku} omitido: fit de referencia de {winner_name} falló")
                    continue

                best_result.forecast = _sanitize_forecast(best_result.forecast)
                # rmse/r2 persistidos pasan a ser las metricas walk-forward reales del
                # ganador (no el ajuste in-sample del fit de referencia) -- ResultadosService
                # las expone al cliente como "R2 promedio", mismo principio de
                # transparencia que #70 ("el r2_test real se expone al cliente").
                best_result.rmse = winner_wf.rmse_test_median
                best_result.r2 = winner_wf.r2_test_median

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

                # Dump opcional para inspección -- issue #89: ya no hay un ModelResult
                # in-sample por candidato (solo walk-forward + el fit de referencia del
                # ganador), así que el dump queda acotado a ese único fit.
                if args.debug_dump:
                    df_dump = pd.DataFrame({"fecha": train_full.index, "y_true": train_full.values})
                    if best_result.holdout_pred is not None:
                        df_dump[best_result.name] = best_result.holdout_pred.reindex(train_full.index).values
                    df_dump.to_csv(f"eval_{sku}.csv", index=False)

                processed += 1

            except Exception as e:
                warnings_list.append(f"Error SKU {sku}: {e}")
                log.exception("Error procesando SKU %s", sku)
            finally:
                n_skus_iterados += 1
                if n_skus_iterados % PREDICT_PERSIST_BATCH_SIZE == 0:
                    _flush_predicciones()

        _flush_predicciones()  # cola final, menor a PREDICT_PERSIST_BATCH_SIZE

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