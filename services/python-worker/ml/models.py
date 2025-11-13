# services/python-worker/ml/models.py
from __future__ import annotations

import warnings
import itertools
import numpy as np
import pandas as pd
import os

from dataclasses import dataclass
from typing import Dict, List, Optional
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from .evaluate import rmse as _rmse, r2_score as _r2

RF_DEFAULT_MAX_DEPTH = int(os.getenv("RF_MAX_DEPTH", "5"))
RF_DEFAULT_MIN_SAMPLES_LEAF = int(os.getenv("RF_MIN_SAMPLES_LEAF", "5"))
RF_DEFAULT_N_ESTIMATORS = int(os.getenv("RF_N_ESTIMATORS", "200"))

XGB_DEFAULT_MAX_DEPTH = int(os.getenv("XGB_MAX_DEPTH", "10"))
XGB_DEFAULT_MIN_CHILD_WEIGHT = int(os.getenv("XGB_MIN_CHILD_WEIGHT", "5"))
XGB_DEFAULT_REG_LAMBDA = float(os.getenv("XGB_REG_LAMBDA", "5"))
XGB_DEFAULT_N_ESTIMATORS = int(os.getenv("XGB_N_ESTIMATORS", "800"))
XGB_DEFAULT_LEARNING_RATE = float(os.getenv("XGB_LEARNING_RATE", "0.022"))

@dataclass
class ModelResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    params: Dict
    features: Optional[List[str]] = None
    holdout_pred: Optional[pd.Series] = None

@dataclass
class CombinedResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    weights: Dict[str, float]

def fit_xgb_insample(train: pd.Series, steps_forecast: int, lags: int = 12, freq: str = "MS") -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend(tr, eff_lags, freq)

        xgb = XGBRegressor(
            n_estimators=XGB_DEFAULT_N_ESTIMATORS,
            max_depth=XGB_DEFAULT_MAX_DEPTH,
            learning_rate=XGB_DEFAULT_LEARNING_RATE,
            reg_alpha=0,
            reg_lambda=XGB_DEFAULT_REG_LAMBDA,
            min_child_weight=XGB_DEFAULT_MIN_CHILD_WEIGHT,
            subsample=0.7,
            colsample_bytree=0.7,
            gamma=0.15,
            random_state=0,
            objective="reg:squarederror",
        )
        xgb.fit(X_rf, y_rf)

        fit_part = pd.Series(xgb.predict(X_rf), index=X_rf.index, dtype="float64")
        xgb_full = fit_part.reindex(tr.index).ffill().bfill()

        hist = list(tr.values[-eff_lags:])
        if len(hist) < eff_lags:
            pad_val = hist[0] if len(hist) > 0 else 0.0
            hist = [pad_val] * (eff_lags - len(hist)) + hist
        oos = []
        for i in range(steps_forecast):
            if str(freq).upper().startswith("Q"):
                idx = tr.index[-1] + pd.offsets.QuarterBegin(i + 1)
                period_val = idx.quarter
            else:
                idx = tr.index[-1] + pd.offsets.MonthBegin(i + 1)
                period_val = idx.month

            xlags = hist[-eff_lags:][::-1]
            data = {}
            for j, val in enumerate(xlags):
                data[f"lag_{j+1}"] = val
            data["period"] = period_val
            data["trend"] = len(tr) + i
            feat_row = {f: data.get(f, 0.0) for f in feats}
            df_feat = pd.DataFrame([feat_row], columns=feats)
            p = float(xgb.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        rmse_full = _rmse(tr.values, xgb_full.values)
        y_arr = np.asarray(y_rf.values, dtype="float64").ravel()
        fit_arr = np.asarray(fit_part.values, dtype="float64").ravel()
        if np.isfinite(y_arr).all() and np.nanstd(y_arr) == 0.0:
            r2_valid = 1.0 if np.allclose(y_arr, fit_arr, equal_nan=True) else 0.0
        else:
            r2_valid = float(_r2(y_arr, fit_arr))

        return ModelResult(
            name="XGB",
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=xgb.get_params(),
            features=feats,
            holdout_pred=xgb_full,
        )
    except Exception:
        return None

def _fit_sarima_aic_grid(y_train: pd.Series):
    best_res = None
    best_aic = np.inf
    y = pd.Series(y_train).astype("float64").sort_index()
    for p, d, q, P, D, Q in itertools.product([0,1],[1],[0,1],[0,1],[1],[0,1]):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mod = SARIMAX(
                    y,
                    order=(p, d, q),
                    seasonal_order=(P, D, Q, 12),
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                res = mod.fit(disp=False)
            if res.aic < best_aic:
                best_aic, best_res = res.aic, res
        except Exception:
            continue
    return best_res

def fit_sarima_insample(train: pd.Series, steps_forecast: int) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        res = _fit_sarima_aic_grid(tr)
        if res is None:
            return None

        y_fit = res.predict(start=tr.index[0], end=tr.index[-1])
        fit_series = pd.Series(np.asarray(y_fit, dtype="float64"), index=tr.index)

        y_fc = res.get_forecast(steps=steps_forecast).predicted_mean
        y_fc = np.asarray(y_fc, dtype="float64")

        return ModelResult(
            name="SARIMA",
            forecast=y_fc,
            rmse=_rmse(tr.values, fit_series.values),
            r2=_r2(tr.values, fit_series.values),
            params={"order": res.model_orders.get("ar", None), "seasonal_order": None},
            holdout_pred=fit_series,
        )
    except Exception:
        return None

def fit_ets_insample(train: pd.Series, steps_forecast: int) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train, dtype="float64").sort_index()
        seasonal_periods = 12
        if len(tr) >= 2 * seasonal_periods:
            model = ExponentialSmoothing(
                tr, trend="add", seasonal="add", seasonal_periods=seasonal_periods
            )
            fit = model.fit()
            fit_series = pd.Series(fit.predict(start=tr.index[0], end=tr.index[-1]), index=tr.index, dtype="float64")
            y_fc = np.asarray(fit.forecast(steps_forecast), dtype="float64")
        else:
            model = ExponentialSmoothing(tr)
            fit = model.fit()
            fit_series = pd.Series(fit.predict(start=tr.index[0], end=tr.index[-1]), index=tr.index, dtype="float64")
            y_fc = np.asarray(fit.forecast(steps_forecast), dtype="float64")

        return ModelResult(
            name="ETS",
            forecast=y_fc,
            rmse=_rmse(tr.values, fit_series.values),
            r2=_r2(tr.values, fit_series.values),
            params={"trend": "add", "seasonal": "add" if len(tr) >= 24 else None, "sp": 12 if len(tr) >= 24 else None},
            holdout_pred=fit_series,
        )
    except Exception:
        return None

def _build_lag_month_trend(series: pd.Series, lags: int, freq: str = "MS") -> tuple[pd.DataFrame, pd.Series, List[str]]:
    df = pd.DataFrame({"y": pd.Series(series).astype("float64").sort_index()})
    for i in range(1, lags + 1):
        df[f"lag_{i}"] = df["y"].shift(i)
    df = df.dropna()
    if str(freq).upper().startswith("Q"):
        df["period"] = df.index.quarter
    else:
        df["period"] = df.index.month
    df["trend"] = np.arange(len(df))
    X = df.drop("y", axis=1)
    y = df["y"]
    feats = list(X.columns)
    return X, y, feats

def fit_rf_insample(train: pd.Series, steps_forecast: int, lags: int = 12, freq: str = "MS") -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend(tr, eff_lags, freq)

        rf = RandomForestRegressor(
            n_estimators=RF_DEFAULT_N_ESTIMATORS,
            max_depth=RF_DEFAULT_MAX_DEPTH,
            min_samples_leaf=RF_DEFAULT_MIN_SAMPLES_LEAF,
            max_features="sqrt",
            random_state=0
        )
        rf.fit(X_rf, y_rf)

        fit_part = pd.Series(rf.predict(X_rf), index=X_rf.index, dtype="float64")
        rf_full = fit_part.reindex(tr.index).ffill().bfill()

        hist = list(tr.values[-eff_lags:])
        if len(hist) < eff_lags:
            pad_val = hist[0] if len(hist) > 0 else 0.0
            hist = [pad_val] * (eff_lags - len(hist)) + hist
        oos = []
        for i in range(steps_forecast):
            if str(freq).upper().startswith("Q"):
                idx = tr.index[-1] + pd.offsets.QuarterBegin(i + 1)
                period_val = idx.quarter
            else:
                idx = tr.index[-1] + pd.offsets.MonthBegin(i + 1)
                period_val = idx.month

            xlags = hist[-eff_lags:][::-1]
            data = {}
            for j, val in enumerate(xlags):
                data[f"lag_{j+1}"] = val
            data["period"] = period_val
            data["trend"] = len(tr) + i
            feat_row = {f: data.get(f, 0.0) for f in feats}
            df_feat = pd.DataFrame([feat_row], columns=feats)
            p = float(rf.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        rmse_full = _rmse(tr.values, rf_full.values)
        y_arr = np.asarray(y_rf.values, dtype="float64").ravel()
        fit_arr = np.asarray(fit_part.values, dtype="float64").ravel()
        if np.isfinite(y_arr).all() and np.nanstd(y_arr) == 0.0:
            r2_valid = 1.0 if np.allclose(y_arr, fit_arr, equal_nan=True) else 0.0
        else:
            r2_valid = float(_r2(y_arr, fit_arr))

        return ModelResult(
            name="RF",
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=rf.get_params(),
            features=feats,
            holdout_pred=rf_full,
        )
    except Exception:
        return None

def combine_by_inverse_rmse_insample(models: List[ModelResult], train: pd.Series, steps: int) -> CombinedResult:
    base = [m for m in models if m.rmse is not None and m.holdout_pred is not None]
    if not base:
        return CombinedResult("COMBINADA", forecast=np.zeros(steps, dtype="float64"), rmse=None, r2=None, weights={})

    inv = [(1.0 / max(m.rmse, 1e-12)) for m in base]
    s = sum(inv)
    weights = {m.name: w / s for m, w in zip(base, inv)}

    combo_fc = np.zeros(steps, dtype="float64")
    for m in base:
        combo_fc += weights[m.name] * np.asarray(m.forecast[:steps], dtype="float64")

    return CombinedResult(name="COMBINADA", forecast=combo_fc, rmse=None, r2=None, weights=weights)
