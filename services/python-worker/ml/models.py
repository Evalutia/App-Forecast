from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import warnings
import itertools

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tools.sm_exceptions import ConvergenceWarning

from .evaluate import rmse as _rmse, r2_score as _r2


@dataclass
class ModelResult:
    name: str
    forecast: np.ndarray              # pronóstico OOS (length = steps_forecast)
    rmse: Optional[float]             # RMSE in-sample (como notebook)
    r2: Optional[float]               # R2   in-sample (como notebook)
    params: Dict
    features: Optional[List[str]] = None
    holdout_pred: Optional[pd.Series] = None  # acá guardamos el FIT in-sample alineado a train.index


@dataclass
class CombinedResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    weights: Dict[str, float]


# === SARIMA: grid igual al notebook (p,q,P,Q en {0,1}; d=1, D=1; s=12) ===
def _fit_sarima_aic_grid(y_train: pd.Series):
    best_res = None
    best_aic = np.inf
    y = pd.Series(y_train).astype("float64").sort_index()
    for p, d, q, P, D, Q in itertools.product([0,1],[1],[0,1],[0,1],[1],[0,1]):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # <<< ignora todos los warnings aquí
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

        # FIT in-sample exactamente como el notebook
        y_fit = res.predict(start=tr.index[0], end=tr.index[-1])
        fit_series = pd.Series(np.asarray(y_fit, dtype="float64"), index=tr.index)

        # Forecast OOS
        y_fc = res.get_forecast(steps=steps_forecast).predicted_mean
        y_fc = np.asarray(y_fc, dtype="float64")

        return ModelResult(
            name="SARIMA",
            forecast=y_fc,
            rmse=_rmse(tr.values, fit_series.values),
            r2=_r2(tr.values, fit_series.values),
            params={"order": res.model_orders["ar"], "seasonal_order": res.model_orders.get("seasonal_ar", None)},
            holdout_pred=fit_series,
        )
    except Exception:
        return None


def fit_ets_insample(train: pd.Series, steps_forecast: int) -> Optional[ModelResult]:
    """ETS fijo como notebook: trend='add', seasonal='add', sp=12 (si hay suficiente historia)."""
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
            # Sin estacionalidad si no alcanza
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


def _build_lag_month_trend(series: pd.Series, lags: int) -> tuple[pd.DataFrame, pd.Series, List[str]]:
    df = pd.DataFrame({"y": pd.Series(series).astype("float64").sort_index()})
    for i in range(1, lags + 1):
        df[f"lag_{i}"] = df["y"].shift(i)
    df = df.dropna()
    df["month"] = df.index.month
    df["trend"] = np.arange(len(df))
    X = df.drop("y", axis=1)
    y = df["y"]
    feats = list(X.columns)
    return X, y, feats


def fit_rf_insample(train: pd.Series, steps_forecast: int, lags: int = 12) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        X_rf, y_rf, feats = _build_lag_month_trend(tr, lags)

        rf = RandomForestRegressor(
            n_estimators=100, min_samples_leaf=2,
            max_features="sqrt", random_state=0
        )
        rf.fit(X_rf, y_rf)

        # in-sample (solo donde hay features)
        fit_part = pd.Series(rf.predict(X_rf), index=X_rf.index, dtype="float64")
        # FIX deprecations: .ffill().bfill()
        rf_full = fit_part.reindex(tr.index).ffill().bfill()

        # forecast recursivo multi-step con month/trend
        hist = tr.tolist()[-lags:]
        oos = []
        for i in range(steps_forecast):
            idx = tr.index[-1] + pd.offsets.MonthBegin(i + 1)
            xlags = hist[-lags:][::-1]
            df_feat = pd.DataFrame([xlags], columns=[f"lag_{j+1}" for j in range(lags)])
            df_feat["month"] = idx.month
            df_feat["trend"] = len(tr) + i
            df_feat = df_feat[feats]  # orden idéntico
            p = float(rf.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        return ModelResult(
            name="RF",
            forecast=y_fc,
            rmse=_rmse(tr.values, rf_full.values),
            r2=_r2(tr.values, rf_full.values),
            params=rf.get_params(),
            features=feats,
            holdout_pred=rf_full,
        )
    except Exception:
        return None


def fit_xgb_insample(train: pd.Series, steps_forecast: int, lags: int = 12) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        X_rf, y_rf, feats = _build_lag_month_trend(tr, lags)

        xgb = XGBRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.03,
            reg_alpha=1, reg_lambda=1, min_child_weight=2,
            subsample=0.7, colsample_bytree=0.7, random_state=0,
            objective="reg:squarederror",
        )
        xgb.fit(X_rf, y_rf)

        fit_part = pd.Series(xgb.predict(X_rf), index=X_rf.index, dtype="float64")
        # FIX deprecations: .ffill().bfill()
        xgb_full = fit_part.reindex(tr.index).ffill().bfill()

        # forecast recursivo con month/trend
        hist = tr.tolist()[-lags:]
        oos = []
        for i in range(steps_forecast):
            idx = tr.index[-1] + pd.offsets.MonthBegin(i + 1)
            xlags = hist[-lags:][::-1]
            df_feat = pd.DataFrame([xlags], columns=[f"lag_{j+1}" for j in range(lags)])
            df_feat["month"] = idx.month
            df_feat["trend"] = len(tr) + i
            df_feat = df_feat[feats]
            p = float(xgb.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        return ModelResult(
            name="XGB",
            forecast=y_fc,
            rmse=_rmse(tr.values, xgb_full.values),
            r2=_r2(tr.values, xgb_full.values),
            params=xgb.get_params(),
            features=feats,
            holdout_pred=xgb_full,
        )
    except Exception:
        return None



def combine_by_inverse_rmse_insample(models: List[ModelResult], train: pd.Series, steps: int) -> CombinedResult:
    """
    Pesos por 1/RMSE usando RMSE in-sample de cada modelo, como en el notebook.
    Devuelve forecast combinado (y las métricas se calculan afuera).
    """
    base = [m for m in models if m.rmse is not None and m.holdout_pred is not None]
    if not base:
        return CombinedResult("COMBINADA", forecast=np.zeros(steps, dtype="float64"), rmse=None, r2=None, weights={})

    inv = [(1.0 / max(m.rmse, 1e-12)) for m in base]
    s = sum(inv)
    weights = {m.name: w / s for m, w in zip(base, inv)}

    # Combined forecast = suma ponderada de forecasts
    combo_fc = np.zeros(steps, dtype="float64")
    for m in base:
        combo_fc += weights[m.name] * np.asarray(m.forecast[:steps], dtype="float64")

    return CombinedResult(name="COMBINADA", forecast=combo_fc, rmse=None, r2=None, weights=weights)
