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
from sklearn.linear_model import Ridge
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


@dataclass
class HoldoutResult:
    name: str
    r2_train: Optional[float]
    r2_test: Optional[float]
    mae_train: Optional[float]
    mae_test: Optional[float]
    forecast_future: np.ndarray
    params: Dict
    features: Optional[List[str]] = None
    test_pred: Optional[pd.Series] = None

def _base_xgb_params() -> Dict:
    return {
        "n_estimators": XGB_DEFAULT_N_ESTIMATORS,
        "max_depth": XGB_DEFAULT_MAX_DEPTH,
        "learning_rate": XGB_DEFAULT_LEARNING_RATE,
        "reg_alpha": 0,
        "reg_lambda": XGB_DEFAULT_REG_LAMBDA,
        "min_child_weight": XGB_DEFAULT_MIN_CHILD_WEIGHT,
        "subsample": 0.7,
        "colsample_bytree": 0.7,
        "gamma": 0.15,
        "random_state": 0,
        "objective": "reg:squarederror",
    }

def fit_xgb_insample(train: pd.Series, steps_forecast: int, lags: int = 12, freq: str = "MS") -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend(tr, eff_lags, freq)

        xgb = XGBRegressor(**_base_xgb_params())
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


def _fit_single_xgb_insample_rich(
    train: pd.Series,
    steps_forecast: int,
    lags: int,
    freq: str,
    name: str,
    xgb_params: Dict,
) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend_rich(tr, eff_lags, freq)

        params = dict(_base_xgb_params())
        params.update(xgb_params or {})

        xgb = XGBRegressor(**params)
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
            for w in (3, 6, 12):
                if len(hist) >= w:
                    window_vals = np.asarray(hist[-w:], dtype="float64")
                    data[f"roll_mean_{w}"] = float(np.nanmean(window_vals))
                    data[f"roll_std_{w}"] = float(np.nanstd(window_vals))
            if len(hist) >= 2:
                data["diff_1"] = float(hist[-1] - hist[-2])
            else:
                data["diff_1"] = 0.0

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
            name=name,
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=xgb.get_params(),
            features=feats,
            holdout_pred=xgb_full,
        )
    except Exception:
        return None


def _fit_single_xgb_insample_log(
    train: pd.Series,
    steps_forecast: int,
    lags: int,
    freq: str,
    name: str,
    xgb_params: Dict,
) -> Optional[ModelResult]:
    """Versión XGB que entrena sobre log1p(y) pero evalúa en escala original.

    Apunta a mejorar errores relativos (MAE) y estabilidad en test.
    """
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend(tr, eff_lags, freq)

        y_log = np.log1p(np.asarray(y_rf.values, dtype="float64").ravel())

        params = dict(_base_xgb_params())
        params.update(xgb_params or {})

        xgb = XGBRegressor(**params)
        xgb.fit(X_rf, y_log)

        fit_part_log = pd.Series(xgb.predict(X_rf), index=X_rf.index, dtype="float64")
        fit_part = np.expm1(fit_part_log.values)
        fit_part = pd.Series(fit_part, index=X_rf.index, dtype="float64")
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
            p_log = float(xgb.predict(df_feat)[0])
            p = float(np.expm1(p_log))
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        rmse_full = _rmse(tr.values, xgb_full.values)
        y_arr = np.asarray(y_rf.values, dtype="float64").ravel()
        fit_arr = np.asarray(xgb_full.reindex(y_rf.index).values, dtype="float64").ravel()
        if np.isfinite(y_arr).all() and np.nanstd(y_arr) == 0.0:
            r2_valid = 1.0 if np.allclose(y_arr, fit_arr, equal_nan=True) else 0.0
        else:
            r2_valid = float(_r2(y_arr, fit_arr))

        return ModelResult(
            name=name,
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=xgb.get_params(),
            features=feats,
            holdout_pred=xgb_full,
        )
    except Exception:
        return None


def _split_last_year(series: pd.Series, freq: str, years: int = 1, min_margin: int = 2):
    s = pd.Series(series).astype("float64").sort_index()
    if s.empty:
        return None, None, 0
    freq_upper = str(freq).upper()
    if freq_upper.startswith("Q"):
        periods_per_year = 4
    else:
        periods_per_year = 12
    test_len = years * periods_per_year
    if len(s) <= test_len + min_margin:
        return None, None, 0
    train = s.iloc[:-test_len].copy()
    test = s.iloc[-test_len:].copy()
    return train, test, test_len


def fit_rf_with_holdout(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Optional[HoldoutResult]:
    train, test, test_len = _split_last_year(full_series, freq=freq, years=years_test)
    if train is None or test_len <= 0:
        return None
    total_steps = test_len + max(0, int(forecast_periods))
    base = fit_rf_insample(train, steps_forecast=total_steps, lags=lags, freq=freq)
    if base is None or getattr(base, "forecast", None) is None:
        return None
    fc = np.asarray(base.forecast, dtype="float64")
    if len(fc) < test_len:
        return None
    fc_test = fc[:test_len]
    fc_future = fc[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")
    # MAE train: contra la predicción insample almacenada en holdout_pred
    try:
        fitted = base.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
        mae_tr = float(np.mean(np.abs(train.values.astype("float64") - fitted)))
    except Exception:
        mae_tr = None
    try:
        r2_te = float(_r2(test.values, fc_test))
    except Exception:
        r2_te = None
    try:
        mae_te = float(np.mean(np.abs(test.values.astype("float64") - fc_test)))
    except Exception:
        mae_te = None
    return HoldoutResult(
        name=base.name,
        r2_train=base.r2,
        r2_test=r2_te,
        mae_train=mae_tr,
        mae_test=mae_te,
        forecast_future=fc_future,
        params=base.params,
        features=getattr(base, "features", None),
        test_pred=pd.Series(fc_test, index=test.index) if len(fc_test) == len(test) else None,
    )


def fit_lin_with_holdout_multi(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Dict[str, HoldoutResult]:
    train, test, test_len = _split_last_year(full_series, freq=freq, years=years_test)
    if train is None or test_len <= 0:
        return {}
    total_steps = test_len + max(0, int(forecast_periods))
    base_results = fit_lin_insample_multi(train, steps_forecast=total_steps, lags=lags, freq=freq)
    out: Dict[str, HoldoutResult] = {}
    for name, res in base_results.items():
        if res is None or getattr(res, "forecast", None) is None:
            continue
        fc = np.asarray(res.forecast, dtype="float64")
        if len(fc) < test_len:
            continue
        fc_test = fc[:test_len]
        fc_future = fc[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")
        # MAE train desde la predicción insample almacenada
        try:
            fitted = res.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = float(np.mean(np.abs(train.values.astype("float64") - fitted)))
        except Exception:
            mae_tr = None
        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        out[name] = HoldoutResult(
            name=name,
            r2_train=res.r2,
            r2_test=r2_te,
            mae_train=mae_tr,
            mae_test=float(np.mean(np.abs(test.values.astype("float64") - fc_test))) if r2_te is not None else None,
            forecast_future=fc_future,
            params=res.params,
            features=getattr(res, "features", None),
            test_pred=pd.Series(fc_test, index=test.index) if len(fc_test) == len(test) else None,
        )
    return out


def fit_xgb_with_holdout_multi(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Dict[str, HoldoutResult]:
    train, test, test_len = _split_last_year(full_series, freq=freq, years=years_test)
    if train is None or test_len <= 0:
        return {}
    total_steps = test_len + max(0, int(forecast_periods))
    base_results = fit_xgb_insample_multi(train, steps_forecast=total_steps, lags=lags, freq=freq)
    out: Dict[str, HoldoutResult] = {}
    for name, res in base_results.items():
        if res is None or getattr(res, "forecast", None) is None:
            continue
        fc = np.asarray(res.forecast, dtype="float64")
        if len(fc) < test_len:
            continue
        fc_test = fc[:test_len]
        fc_future = fc[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        # MAE train
        try:
            fitted = res.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = float(np.mean(np.abs(train.values.astype("float64") - fitted)))
        except Exception:
            mae_tr = None

        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = float(np.mean(np.abs(test.values.astype("float64") - fc_test)))
        except Exception:
            mae_te = None

        out[name] = HoldoutResult(
            name=name,
            r2_train=res.r2,
            r2_test=r2_te,
            mae_train=mae_tr,
            mae_test=mae_te,
            forecast_future=fc_future,
            params=res.params,
            features=getattr(res, "features", None),
            test_pred=pd.Series(fc_test, index=test.index) if len(fc_test) == len(test) else None,
        )

    # Ensamble simple de los mejores XGB (promedio de predicciones)
    ensemble_members = [
        "XGB_lr_very_low",
        "XGB_lr_very_low_reg",
        "XGB_mid_trees",
    ]
    if all(m in base_results for m in ensemble_members):
        try:
            # Ensamble insample para calcular métricas de train
            fitted_list = []
            for m in ensemble_members:
                res = base_results[m]
                if getattr(res, "holdout_pred", None) is None:
                    fitted_list = []
                    break
                fitted_list.append(res.holdout_pred.loc[train.index].values.astype("float64"))  # type: ignore[union-attr]
            if fitted_list:
                fitted_stack = np.stack(fitted_list, axis=0)
                fitted_ens = fitted_stack.mean(axis=0)

                # Ensamble sobre el horizonte completo (test + futuro)
                fc_list = []
                for m in ensemble_members:
                    res = base_results[m]
                    fc_arr = np.asarray(res.forecast, dtype="float64")
                    if len(fc_arr) < total_steps:
                        fc_list = []
                        break
                    fc_list.append(fc_arr)
                if fc_list:
                    fc_stack = np.stack(fc_list, axis=0)
                    fc_ens = fc_stack.mean(axis=0)
                    fc_test = fc_ens[:test_len]
                    fc_future = fc_ens[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

                    mae_tr_ens = float(np.mean(np.abs(train.values.astype("float64") - fitted_ens)))
                    mae_te_ens = float(np.mean(np.abs(test.values.astype("float64") - fc_test)))
                    r2_tr_ens = float(_r2(train.values, fitted_ens))
                    r2_te_ens = float(_r2(test.values, fc_test))

                    out["XGB_ensemble_top"] = HoldoutResult(
                        name="XGB_ensemble_top",
                        r2_train=r2_tr_ens,
                        r2_test=r2_te_ens,
                        mae_train=mae_tr_ens,
                        mae_test=mae_te_ens,
                        forecast_future=fc_future,
                        params={"members": ensemble_members},
                        features=getattr(next(iter(base_results.values())), "features", None),
                        test_pred=pd.Series(fc_test, index=test.index) if len(fc_test) == len(test) else None,
                    )
        except Exception:
            pass

    return out


def fit_xgb_log_with_holdout_multi(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Dict[str, HoldoutResult]:
    """Holdout para la familia XGB_log* (entrenan en log1p(y))."""
    train, test, test_len = _split_last_year(full_series, freq=freq, years=years_test)
    if train is None or test_len <= 0:
        return {}
    total_steps = test_len + max(0, int(forecast_periods))
    base_results = fit_xgb_insample_log_multi(train, steps_forecast=total_steps, lags=lags, freq=freq)
    out: Dict[str, HoldoutResult] = {}
    for name, res in base_results.items():
        if res is None or getattr(res, "forecast", None) is None:
            continue
        fc = np.asarray(res.forecast, dtype="float64")
        if len(fc) < test_len:
            continue
        fc_test = fc[:test_len]
        fc_future = fc[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        try:
            fitted = res.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = float(np.mean(np.abs(train.values.astype("float64") - fitted)))
        except Exception:
            mae_tr = None

        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = float(np.mean(np.abs(test.values.astype("float64") - fc_test)))
        except Exception:
            mae_te = None

        out[name] = HoldoutResult(
            name=name,
            r2_train=res.r2,
            r2_test=r2_te,
            mae_train=mae_tr,
            mae_test=mae_te,
            forecast_future=fc_future,
            params=res.params,
            features=getattr(res, "features", None),
        )
    return out


def fit_xgb_rich_with_holdout_multi(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Dict[str, HoldoutResult]:
    """Evaluar variantes XGB con features ricas usando holdout.

    Usa _build_lag_month_trend_rich para intentar mejorar r2_test y mae_rel
    respecto a las variantes simples, manteniendo un gap razonable.
    """
    train, test, test_len = _split_last_year(full_series, freq=freq, years=years_test)
    if train is None or test_len <= 0:
        return {}
    total_steps = test_len + max(0, int(forecast_periods))
    base_results = fit_xgb_insample_rich_multi(train, steps_forecast=total_steps, lags=lags, freq=freq)
    out: Dict[str, HoldoutResult] = {}
    for name, res in base_results.items():
        if res is None or getattr(res, "forecast", None) is None:
            continue
        fc = np.asarray(res.forecast, dtype="float64")
        if len(fc) < test_len:
            continue
        fc_test = fc[:test_len]
        fc_future = fc[test_len : test_len + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        try:
            fitted = res.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = float(np.mean(np.abs(train.values.astype("float64") - fitted)))
        except Exception:
            mae_tr = None

        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = float(np.mean(np.abs(test.values.astype("float64") - fc_test)))
        except Exception:
            mae_te = None

        out[name] = HoldoutResult(
            name=name,
            r2_train=res.r2,
            r2_test=r2_te,
            mae_train=mae_tr,
            mae_test=mae_te,
            forecast_future=fc_future,
            params=res.params,
            features=getattr(res, "features", None),
        )
    return out

def fit_lin_insample_multi(
    train: pd.Series,
    steps_forecast: int,
    lags: int = 12,
    freq: str = "MS",
) -> Dict[str, ModelResult]:
    """Prueba varias configuraciones de regresión lineal Ridge.

    Devuelve un dict nombre -> ModelResult para comparar distintas
    intensidades de regularización y variantes sencillas.
    """
    configs = [
        # Baseline con intercepto
        ("LIN", {"alpha": 1.0, "fit_intercept": True}),

        # Variantes que habían mostrado mejor R2_test (sin intercepto)
        ("LIN_no_intercept_0_05", {"alpha": 0.05, "fit_intercept": False}),
        ("LIN_no_intercept_0_1", {"alpha": 0.1, "fit_intercept": False}),
        ("LIN_no_intercept_0_2", {"alpha": 0.2, "fit_intercept": False}),
        ("LIN_no_intercept_0_3", {"alpha": 0.3, "fit_intercept": False}),

        # Variante algo más regularizada con intercepto
        ("LIN_smooth", {"alpha": 2.0, "fit_intercept": True}),
    ]

    results: Dict[str, ModelResult] = {}
    for name, cfg in configs:
        try:
            tr = pd.Series(train).astype("float64").sort_index()
            max_lags_allowed = max(1, len(tr) - 1)
            eff_lags = min(lags, max_lags_allowed)
            X_lin, y_lin, feats = _build_lag_month_trend(tr, eff_lags, freq)

            lin = Ridge(**cfg)
            lin.fit(X_lin, y_lin)

            fit_part = pd.Series(lin.predict(X_lin), index=X_lin.index, dtype="float64")
            lin_full = fit_part.reindex(tr.index).ffill().bfill()

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
                p = float(lin.predict(df_feat)[0])
                oos.append(p)
                hist.append(p)
            y_fc = np.asarray(oos, dtype="float64")

            rmse_full = _rmse(tr.values, lin_full.values)
            y_arr = np.asarray(y_lin.values, dtype="float64").ravel()
            fit_arr = np.asarray(fit_part.values, dtype="float64").ravel()
            if np.isfinite(y_arr).all() and np.nanstd(y_arr) == 0.0:
                r2_valid = 1.0 if np.allclose(y_arr, fit_arr, equal_nan=True) else 0.0
            else:
                r2_valid = float(_r2(y_arr, fit_arr))

            results[name] = ModelResult(
                name=name,
                forecast=y_fc,
                rmse=rmse_full,
                r2=r2_valid,
                params=lin.get_params(),
                features=feats,
                holdout_pred=lin_full,
            )
        except Exception:
            continue

    return results

def _fit_single_xgb_insample(
    train: pd.Series,
    steps_forecast: int,
    lags: int,
    freq: str,
    name: str,
    xgb_params: Dict,
) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_rf, y_rf, feats = _build_lag_month_trend(tr, eff_lags, freq)

        params = dict(_base_xgb_params())
        params.update(xgb_params or {})

        xgb = XGBRegressor(**params)
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
            name=name,
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=xgb.get_params(),
            features=feats,
            holdout_pred=xgb_full,
        )
    except Exception:
        return None

def fit_xgb_insample_multi(
    train: pd.Series,
    steps_forecast: int,
    lags: int = 12,
    freq: str = "MS",
) -> Dict[str, ModelResult]:
    configs = [
        # Base: igual a fit_xgb_insample (punto de partida)
        ("XGB", {}),

        # Menos árboles (más simple, menos riesgo de overfit)
        ("XGB_less_trees", {
            "n_estimators": max(200, XGB_DEFAULT_N_ESTIMATORS // 2),
        }),

        # Compromiso actual (ya dio buen R2_test)
        ("XGB_compromise", {
            "n_estimators": max(250, int(XGB_DEFAULT_N_ESTIMATORS * 0.7)),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.2,
        }),

        # Learning rate más bajo + más árboles (boosting suave alrededor del compromiso)
        ("XGB_lr_low", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.6,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.1),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.4,
        }),

        # Mejor modelo actual: lr muy bajo + más árboles
        ("XGB_lr_very_low", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.3),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.6,
        }),

        # Variante de XGB_lr_very_low con aún más árboles (por si ayuda al test)
        ("XGB_lr_very_low_more_trees", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.6),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.6,
        }),

        # Variante de XGB_lr_very_low con más regularización (intento de bajar gap)
        ("XGB_lr_very_low_reg", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.3),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 2.0,
        }),

        # Variante intermedia entre compromise y less_trees
        ("XGB_mid_trees", {
            "n_estimators": max(220, int(XGB_DEFAULT_N_ESTIMATORS * 0.6)),
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.3,
        }),

        # Variante optimizada a MAE sobre base XGB (misma estructura pero loss abs)
        ("XGB_mae", {
            "objective": "reg:absoluteerror",
        }),

        # Variante de XGB_lr_very_low pero optimizando MAE directamente
        ("XGB_lr_very_low_mae", {
            "objective": "reg:absoluteerror",
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.3),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.6,
        }),
    ]

    results: Dict[str, ModelResult] = {}
    for name, cfg in configs:
        res = _fit_single_xgb_insample(train, steps_forecast, lags, freq, name, cfg)
        if res is not None and getattr(res, "forecast", None) is not None:
            results[name] = res
    return results


def fit_xgb_insample_log_multi(
    train: pd.Series,
    steps_forecast: int,
    lags: int = 12,
    freq: str = "MS",
) -> Dict[str, ModelResult]:
    """Familia de modelos XGB que trabajan en log1p(y).

    Se usan para intentar mejorar r2_test y MAE relativo.
    """
    configs = [
        ("XGB_log", {}),
        ("XGB_log_lr_very_low", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.2),
            "subsample": 0.75,
            "colsample_bytree": 0.75,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.6,
        }),
        ("XGB_log_strong_reg", {
            "max_depth": 4,
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.6,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 0.9),
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 2.0,
            "min_child_weight": XGB_DEFAULT_MIN_CHILD_WEIGHT * 2,
        }),
    ]

    results: Dict[str, ModelResult] = {}
    for name, cfg in configs:
        res = _fit_single_xgb_insample_log(train, steps_forecast, lags, freq, name, cfg)
        if res is not None and getattr(res, "forecast", None) is not None:
            results[name] = res
    return results


def fit_xgb_insample_rich_multi(
    train: pd.Series,
    steps_forecast: int,
    lags: int = 12,
    freq: str = "MS",
    ) -> Dict[str, ModelResult]:
    configs = [
        ("XGB_rich", {
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        }),
        ("XGB_rich_strong_reg", {
            "max_depth": 4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 0.8),
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 2.0,
            "min_child_weight": XGB_DEFAULT_MIN_CHILD_WEIGHT * 2,
        }),
        ("XGB_rich_lr_low", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.6,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.1),
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 1.6,
        }),
        ("XGB_rich_very_smooth", {
            "learning_rate": XGB_DEFAULT_LEARNING_RATE * 0.4,
            "n_estimators": int(XGB_DEFAULT_N_ESTIMATORS * 1.3),
            "max_depth": 4,
            "subsample": 0.9,
            "colsample_bytree": 0.9,
            "reg_lambda": XGB_DEFAULT_REG_LAMBDA * 2.2,
            "min_child_weight": XGB_DEFAULT_MIN_CHILD_WEIGHT * 2,
        }),
    ]

    results: Dict[str, ModelResult] = {}
    for name, cfg in configs:
        res = _fit_single_xgb_insample_rich(train, steps_forecast, lags, freq, name, cfg)
        if res is not None and getattr(res, "forecast", None) is not None:
            results[name] = res
    return results

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

def _build_lag_month_trend_rich(series: pd.Series, lags: int, freq: str = "MS") -> tuple[pd.DataFrame, pd.Series, List[str]]:
    df = pd.DataFrame({"y": pd.Series(series).astype("float64").sort_index()})
    for i in range(1, lags + 1):
        df[f"lag_{i}"] = df["y"].shift(i)

    if str(freq).upper().startswith("Q"):
        df["period"] = df.index.quarter
    else:
        df["period"] = df.index.month
    df["trend"] = np.arange(len(df))

    for w in (3, 6, 12):
        if len(df) >= w:
            df[f"roll_mean_{w}"] = df["y"].rolling(window=w, min_periods=w).mean()
            df[f"roll_std_{w}"] = df["y"].rolling(window=w, min_periods=w).std()

    df["diff_1"] = df["y"].diff(1)

    df = df.dropna()
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

def fit_lin_insample(train: pd.Series, steps_forecast: int, lags: int = 12, freq: str = "MS") -> Optional[ModelResult]:
    """Regresión lineal Ridge simple sobre las mismas features que RF.

    Se usa como modelo más simple para comparar contra RF/XGB.
    """
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        max_lags_allowed = max(1, len(tr) - 1)
        eff_lags = min(lags, max_lags_allowed)
        X_lin, y_lin, feats = _build_lag_month_trend(tr, eff_lags, freq)

        lin = Ridge(alpha=1.0, fit_intercept=True, random_state=0)
        lin.fit(X_lin, y_lin)

        fit_part = pd.Series(lin.predict(X_lin), index=X_lin.index, dtype="float64")
        lin_full = fit_part.reindex(tr.index).ffill().bfill()

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
            p = float(lin.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        rmse_full = _rmse(tr.values, lin_full.values)
        y_arr = np.asarray(y_lin.values, dtype="float64").ravel()
        fit_arr = np.asarray(fit_part.values, dtype="float64").ravel()
        if np.isfinite(y_arr).all() and np.nanstd(y_arr) == 0.0:
            r2_valid = 1.0 if np.allclose(y_arr, fit_arr, equal_nan=True) else 0.0
        else:
            r2_valid = float(_r2(y_arr, fit_arr))

        return ModelResult(
            name="LIN",
            forecast=y_fc,
            rmse=rmse_full,
            r2=r2_valid,
            params=lin.get_params(),
            features=feats,
            holdout_pred=lin_full,
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
