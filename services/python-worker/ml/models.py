from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning

from .evaluate import rmse as _rmse, r2_score as _r2
from .features import make_lag_matrix, recursive_forecast_tree


@dataclass
class ModelResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    params: Dict
    features: Optional[List[str]] = None
    holdout_pred: Optional[np.ndarray] = None


@dataclass
class CombinedResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    weights: Dict[str, float]


def _fit_sarima_small_grid(y_train: pd.Series):
    """
    Grid chico para estabilidad (mensual con estacionalidad 12).
    Homogeneizado con enforce_* = False (igual que el fit final) para paridad numérica.
    """
    best = None
    best_aic = np.inf
    y_train = pd.Series(y_train).astype("float64").sort_index()

    for p in (0, 1):
        for d in (1,):
            for q in (0, 1):
                for P in (0, 1):
                    for D in (1,):
                        for Q in (0, 1):
                            order = (p, d, q)
                            seasonal_order = (P, D, Q, 12)
                            try:
                                with warnings.catch_warnings():
                                    warnings.filterwarnings("ignore", ".*converge.*", ConvergenceWarning)
                                    mod = SARIMAX(
                                        y_train,
                                        order=order,
                                        seasonal_order=seasonal_order,
                                        enforce_stationarity=False,
                                        enforce_invertibility=False,
                                    )
                                    res = mod.fit(disp=False, maxiter=200)
                                    if res.aic < best_aic:
                                        best_aic = res.aic
                                        best = (order, seasonal_order)
                            except Exception:
                                continue
    return best


def fit_sarima(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
) -> Optional[ModelResult]:
    try:
        train = pd.Series(train).astype("float64").sort_index()
        test = pd.Series(test).astype("float64").sort_index()

        grid = _fit_sarima_small_grid(train)
        if grid is None:
            return None
        order, seasonal_order = grid

        model = SARIMAX(
            train,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, maxiter=200)

        # holdout
        y_pred_eval = model.forecast(steps=steps_eval)
        r = ModelResult(
            name="SARIMA",
            forecast=np.asarray(model.forecast(steps=steps_forecast), dtype="float64"),
            rmse=_rmse(test.values, y_pred_eval.values),
            r2=_r2(test.values, y_pred_eval.values),
            params={"order": order, "seasonal_order": seasonal_order},
            holdout_pred=np.asarray(y_pred_eval.values, dtype="float64"),
        )
        return r
    except Exception:
        return None


def fit_ets(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
) -> Optional[ModelResult]:
    """
    ETS (Holt-Winters):
      - trend='add'
      - seasonal='mul' si todo > 0, si no 'add'
      - sp=12 mensual
      - initialization_method='estimated'
      - use_boxcox=False, remove_bias=True
      - warnings silenciados y fallback simple si falla.
    """
    try:
        y = pd.Series(train, dtype="float64").copy().sort_index()
        seasonal_periods = 12
        trend = "add"
        has_nonpos = (y <= 0).any()

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", ".*Optimization failed to converge.*", ConvergenceWarning)
            warnings.filterwarnings("ignore", ".*divide by zero encountered in log.*", RuntimeWarning)

            fit = None
            seasonal_used = None

            if (not has_nonpos) and seasonal_periods > 1:
                try:
                    model = ExponentialSmoothing(
                        y, trend=trend, seasonal="mul",
                        seasonal_periods=seasonal_periods,
                        initialization_method="estimated",
                    )
                    fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)
                    seasonal_used = "mul"
                except Exception:
                    fit = None

            if fit is None:
                model = ExponentialSmoothing(
                    y, trend=trend,
                    seasonal="add" if seasonal_periods > 1 else None,
                    seasonal_periods=seasonal_periods if seasonal_periods > 1 else None,
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)
                seasonal_used = "add" if seasonal_periods > 1 else None

        if steps_eval > 0:
            y_pred_eval = fit.forecast(steps=steps_eval)
            y_true = np.asarray(pd.Series(test).astype("float64").values, dtype="float64")
            y_pred_eval_np = np.asarray(y_pred_eval.values, dtype="float64")
            rmse_val = _rmse(y_true, y_pred_eval_np)
            r2_val = _r2(y_true, y_pred_eval_np)
            holdout_pred = y_pred_eval_np
        else:
            rmse_val = None
            r2_val = None
            holdout_pred = None

        yhat_forecast = np.asarray(fit.forecast(steps=steps_forecast), dtype="float64")

        return ModelResult(
            name="ETS",
            forecast=yhat_forecast,
            rmse=rmse_val,
            r2=r2_val,
            params={"trend": trend, "seasonal": seasonal_used, "sp": seasonal_periods},
            holdout_pred=holdout_pred,
        )

    except Exception:
        # Fallback: suavizamiento simple
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = ExponentialSmoothing(
                    pd.Series(train, dtype="float64").sort_index(),
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)

            if steps_eval > 0:
                y_pred_eval = fit.forecast(steps=steps_eval)
                y_true = np.asarray(pd.Series(test).astype("float64").values, dtype="float64")
                y_pred_eval_np = np.asarray(y_pred_eval.values, dtype="float64")
                rmse_val = _rmse(y_true, y_pred_eval_np)
                r2_val = _r2(y_true, y_pred_eval_np)
                holdout_pred = y_pred_eval_np
            else:
                rmse_val = None
                r2_val = None
                holdout_pred = None

            yhat_forecast = np.asarray(fit.forecast(steps=steps_forecast), dtype="float64")

            return ModelResult(
                name="ETS",
                forecast=yhat_forecast,
                rmse=rmse_val,
                r2=r2_val,
                params={"trend": None, "seasonal": None, "sp": None},
                holdout_pred=holdout_pred,
            )
        except Exception:
            return None


def fit_rf(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
    rf_params: Dict,
    lags: int = 12,
) -> Optional[ModelResult]:
    try:
        X_tr, y_tr, feats = make_lag_matrix(train, lags=lags)
        rf = RandomForestRegressor(**rf_params)
        rf.fit(X_tr, y_tr)

        y_pred_eval = recursive_forecast_tree(rf, train, steps=steps_eval, lags=lags)
        y_pred_fc = recursive_forecast_tree(rf, train, steps=steps_forecast, lags=lags)

        return ModelResult(
            name="RF",
            forecast=y_pred_fc,
            rmse=_rmse(pd.Series(test).values, y_pred_eval),
            r2=_r2(pd.Series(test).values, y_pred_eval),
            params=rf.get_params(),
            features=feats,
            holdout_pred=y_pred_eval,
        )
    except Exception:
        return None


def fit_xgb(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
    xgb_params: Dict,
    lags: int = 12,
) -> Optional[ModelResult]:
    try:
        X_tr, y_tr, feats = make_lag_matrix(train, lags=lags)
        xgb = XGBRegressor(**xgb_params)
        xgb.fit(X_tr, y_tr)

        y_pred_eval = recursive_forecast_tree(xgb, train, steps=steps_eval, lags=lags)
        y_pred_fc = recursive_forecast_tree(xgb, train, steps=steps_forecast, lags=lags)

        return ModelResult(
            name="XGB",
            forecast=y_pred_fc,
            rmse=_rmse(pd.Series(test).values, y_pred_eval),
            r2=_r2(pd.Series(test).values, y_pred_eval),
            params=xgb.get_params(),
            features=feats,
            holdout_pred=y_pred_eval,
        )
    except Exception:
        return None


def combine_by_inverse_rmse(models: List[ModelResult], steps: int) -> CombinedResult:
    """
    Pesos ~ 1/RMSE sobre modelos base (no COMBINADA). Normaliza pesos.
    Forecast combinado y holdout combinados por promedio ponderado.
    Las métricas (rmse/r2) se calculan en el caller, que sí conoce y_true.
    """
    base = [m for m in models if m.name != "COMBINADA" and m.rmse is not None and m.holdout_pred is not None]
    if not base:
        for m in models:
            if len(m.forecast) >= steps:
                return CombinedResult(name="COMBINADA", forecast=m.forecast[:steps], rmse=None, r2=None, weights={m.name: 1.0})
        return CombinedResult(name="COMBINADA", forecast=np.zeros(steps, dtype=np.float64), rmse=None, r2=None, weights={})

    inv = [(1.0 / max(m.rmse, 1e-6)) for m in base]
    s = sum(inv)
    weights = {m.name: (w / s if s > 0 else 1.0 / len(base)) for m, w in zip(base, inv)}

    min_len = min(len(m.holdout_pred) for m in base)
    combo_fc = np.zeros(steps, dtype=np.float64)
    for m in base:
        combo_fc += weights[m.name] * np.asarray(m.forecast[:steps], dtype=np.float64)

    return CombinedResult(name="COMBINADA", forecast=combo_fc, rmse=None, r2=None, weights=weights)
