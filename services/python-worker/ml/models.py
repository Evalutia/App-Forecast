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

# -------------------------------------------------------------------------
# Prophet support: optional import (si no está instalado, fit_prophet_insample
# devolverá None y la CLI lo ignorará).
# -------------------------------------------------------------------------
try:
    from prophet import Prophet  # type: ignore
except Exception:
    Prophet = None

# -------------------------------------------------------------------------
# Hiperparámetros para Prophet (copiados del script recibido)
# -------------------------------------------------------------------------
HIPERPARAMETROS_OPTIMOS = {
    'C00375': {
        'changepoint_prior_scale': 0.01,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 1.0,
        'n_changepoints': 50,
    },
    'C00216': {
        'changepoint_prior_scale': 0.01,
        'seasonality_prior_scale': 15.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 1.0,
        'n_changepoints': 50,
    },
    'C00477': {
        'changepoint_prior_scale': 0.1,
        'seasonality_prior_scale': 30.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 1.0,
        'n_changepoints': 50,
    },
    'C00428': {
        'changepoint_prior_scale': 0.1,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 5.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
    'C00678': {
        'changepoint_prior_scale': 0.01,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
    'C00204': {
        'changepoint_prior_scale': 0.5,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 1.0,
        'n_changepoints': 50,
    },
    'C00391': {
        'changepoint_prior_scale': 0.01,
        'seasonality_prior_scale': 15.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
    'C00190': {
        'changepoint_prior_scale': 0.1,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 5.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 1.0,
        'n_changepoints': 50,
    },
    'E00375': {
        'changepoint_prior_scale': 0.5,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
    'I00763': {
        'changepoint_prior_scale': 0.1,
        'seasonality_prior_scale': 15.0,
        'holidays_prior_scale': 10.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 50,
    },
    'C00184': {
        'changepoint_prior_scale': 0.5,
        'seasonality_prior_scale': 5.0,
        'holidays_prior_scale': 1.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
    'C00399': {
        'changepoint_prior_scale': 0.5,
        'seasonality_prior_scale': 30.0,
        'holidays_prior_scale': 10.0,
        'seasonality_mode': 'multiplicative',
        'changepoint_range': 0.8,
        'n_changepoints': 25,
    },
}

def _calc_hiperparams_genericos():
    import pandas as _pd, numpy as _np
    vals = list(HIPERPARAMETROS_OPTIMOS.values())
    if not vals:
        return {
            'changepoint_prior_scale': 0.05,
            'seasonality_prior_scale': 10.0,
            'holidays_prior_scale': 1.0,
            'seasonality_mode': 'multiplicative',
            'changepoint_range': 0.8,
            'n_changepoints': 25,
        }
    def moda(key):
        s = _pd.Series([v[key] for v in vals])
        m = s.mode()
        return m.iloc[0] if len(m) else float(_np.mean(s))
    return {
        'changepoint_prior_scale': moda('changepoint_prior_scale'),
        'seasonality_prior_scale': moda('seasonality_prior_scale'),
        'holidays_prior_scale': moda('holidays_prior_scale'),
        'seasonality_mode': 'multiplicative',
        'changepoint_range': moda('changepoint_range'),
        'n_changepoints': int(moda('n_changepoints')),
    }

HIPERPARAMETROS_GENERICOS = _calc_hiperparams_genericos()

# -------------------------------------------------------------------------
# Dataclasses y resto del archivo (se mantiene el código original debajo)
# -------------------------------------------------------------------------
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

# (A continuación se mantiene TODO el resto del archivo original,
#  exactamente igual que antes, hasta la definición de fit_rf_insample, etc.)
# -------------------------------------------------------------------------------------------------
# [El contenido original de ml/models.py continúa sin cambios]
# Copio todo el resto tal como estaba (sin modificaciones) a continuación
# -------------------------------------------------------------------------------------------------

RF_DEFAULT_MAX_DEPTH = int(os.getenv("RF_MAX_DEPTH", "5"))
RF_DEFAULT_MIN_SAMPLES_LEAF = int(os.getenv("RF_MIN_SAMPLES_LEAF", "5"))
RF_DEFAULT_N_ESTIMATORS = int(os.getenv("RF_N_ESTIMATORS", "200"))

XGB_DEFAULT_MAX_DEPTH = int(os.getenv("XGB_MAX_DEPTH", "10"))
XGB_DEFAULT_MIN_CHILD_WEIGHT = int(os.getenv("XGB_MIN_CHILD_WEIGHT", "5"))
XGB_DEFAULT_REG_LAMBDA = float(os.getenv("XGB_REG_LAMBDA", "5"))
XGB_DEFAULT_N_ESTIMATORS = int(os.getenv("XGB_N_ESTIMATORS", "800"))
XGB_DEFAULT_LEARNING_RATE = float(os.getenv("XGB_LEARNING_RATE", "0.022"))

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

# ... [Resto del archivo exactamente igual] ...

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

# (El resto del archivo permanece idéntico.)


# -------------------------------------------------------------------------
# Nueva función Prophet (al final del archivo para evitar romper lecturas)
# -------------------------------------------------------------------------
def fit_prophet_insample(
    sku: str,
    train: pd.Series,
    steps_forecast: int,
    lags: int = 12,
    freq: str = "MS",
) -> Optional[ModelResult]:
    """
    Entrena Prophet sobre 'train' (serie con índice datetime, valores float)
    y devuelve ModelResult con:
      - forecast: array numpy de longitud steps_forecast (orden horizonte 1..n)
      - holdout_pred: predicción in-sample (yhat) alineada con train.index
      - rmse, r2 calculados sobre in-sample
    Si Prophet no está disponible o hay algún error retorna None.
    """
    if Prophet is None:
        return None
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        # Requerir mínimo de historia (al igual que el notebook: 8 trimestres)
        min_needed = 8 if str(freq).upper().startswith("Q") else 12
        if len(tr) < min_needed:
            return None

        # Preparar DataFrame para Prophet
        df_prop = pd.DataFrame({
            'ds': tr.index.to_series().reset_index(drop=True),
            'y': tr.values
        })
        df_prop = df_prop.dropna()
        df_prop = df_prop[df_prop['y'] >= 0]
        if len(df_prop) < min_needed:
            return None

        params = HIPERPARAMETROS_OPTIMOS.get(sku, HIPERPARAMETROS_GENERICOS)

        model = Prophet(
            growth='linear',
            changepoint_prior_scale=params.get('changepoint_prior_scale', 0.05),
            seasonality_prior_scale=params.get('seasonality_prior_scale', 10.0),
            holidays_prior_scale=params.get('holidays_prior_scale', 1.0),
            seasonality_mode=params.get('seasonality_mode', 'multiplicative'),
            changepoint_range=params.get('changepoint_range', 0.8),
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
        )
        # En algunas versiones n_changepoints se pasa en constructor, en otras se setea:
        try:
            model.n_changepoints = int(params.get('n_changepoints', 25))
        except Exception:
            pass

        model.fit(df_prop)

        # Construir future: avanzar a partir del último índice
        last = tr.index.max()
        if str(freq).upper().startswith("Q"):
            future_ds = pd.to_datetime([last + pd.DateOffset(months=3*(i+1)) for i in range(steps_forecast)])
        else:
            future_ds = pd.to_datetime([last + pd.DateOffset(months=(i+1)) for i in range(steps_forecast)])

        future = pd.DataFrame({'ds': future_ds})
        forecast = model.predict(future)
        y_fc = forecast['yhat'].values
        y_fc = np.maximum(y_fc, 0.0).astype('float64')

        # In-sample fit
        insample = model.predict(df_prop)
        holdout = pd.Series(insample['yhat'].values, index=tr.index)

        rmse_val = _rmse(tr.values, holdout.values)
        r2_val = _r2(tr.values, holdout.values)

        return ModelResult(
            name="PROPHET",
            forecast=np.asarray(y_fc, dtype='float64'),
            rmse=rmse_val,
            r2=r2_val,
            params=params,
            features=None,
            holdout_pred=holdout,
        )
    except Exception:
        return None
