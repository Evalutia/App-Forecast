from __future__ import annotations

import warnings
import itertools
import logging
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
from .evaluate import (
    rmse as _rmse,
    r2_score as _r2,
    holdout_split as _holdout_split,
    walk_forward_split as _walk_forward_split,
)

log = logging.getLogger(__name__)

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
    rmse_train: Optional[float] = None


@dataclass
class WalkForwardResult:
    name: str
    n_folds: int
    r2_test_median: Optional[float]
    r2_test_iqr: Optional[float]
    rmse_train_median: Optional[float]
    mae_test_median: Optional[float]
    n_train_rows_mean: Optional[float]
    n_train_rows_min: Optional[int]
    stable: Optional[bool]

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
        log.exception("fit_xgb_insample fallo (lags=%s, freq=%s, n=%s)", lags, freq, len(train))
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
        log.exception("fit_rf_insample fallo (lags=%s, freq=%s, n=%s)", lags, freq, len(train))
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
        log.exception("fit_prophet_insample fallo (sku=%s, lags=%s, freq=%s, n=%s)", sku, lags, freq, len(train))
        return None


# -------------------------------------------------------------------------
# Holdout real (train/test) para los modelos que usa producción (predict.py):
# RF, XGB y Prophet. Cada función entrena sobre 'train' (serie sin los
# últimos k periodos) y evalúa contra 'test' (esos k periodos), a diferencia
# de las *_insample de arriba que solo miden ajuste sobre datos ya vistos.
# -------------------------------------------------------------------------

def _holdout_k(freq: str, years_test: int) -> int:
    periods_per_year = 4 if str(freq).upper().startswith("Q") else 12
    return int(years_test) * periods_per_year


def _mae(y_true, y_pred) -> float:
    return float(np.mean(np.abs(np.asarray(y_true, dtype="float64") - np.asarray(y_pred, dtype="float64"))))


def fit_rf_with_holdout(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Optional[HoldoutResult]:
    try:
        k = _holdout_k(freq, years_test)
        train, test = _holdout_split(full_series, k=k)
        if len(train) < 2:
            return None
        total_steps = k + max(0, int(forecast_periods))
        base = fit_rf_insample(train, steps_forecast=total_steps, lags=lags, freq=freq)
        if base is None or getattr(base, "forecast", None) is None:
            return None
        fc = np.asarray(base.forecast, dtype="float64")
        if len(fc) < k:
            return None
        fc_test = fc[:k]
        fc_future = fc[k : k + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        try:
            fitted = base.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = _mae(train.values, fitted)
        except Exception:
            mae_tr = None
        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = _mae(test.values, fc_test)
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
            rmse_train=base.rmse,
        )
    except Exception:
        return None


def fit_xgb_with_holdout(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
) -> Optional[HoldoutResult]:
    try:
        k = _holdout_k(freq, years_test)
        train, test = _holdout_split(full_series, k=k)
        if len(train) < 2:
            return None
        total_steps = k + max(0, int(forecast_periods))
        base = fit_xgb_insample(train, steps_forecast=total_steps, lags=lags, freq=freq)
        if base is None or getattr(base, "forecast", None) is None:
            return None
        fc = np.asarray(base.forecast, dtype="float64")
        if len(fc) < k:
            return None
        fc_test = fc[:k]
        fc_future = fc[k : k + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        try:
            fitted = base.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = _mae(train.values, fitted)
        except Exception:
            mae_tr = None
        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = _mae(test.values, fc_test)
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
            rmse_train=base.rmse,
        )
    except Exception:
        return None


def fit_prophet_with_holdout(
    full_series: pd.Series,
    freq: str,
    forecast_periods: int,
    lags: int = 12,
    years_test: int = 1,
    *,
    sku: str,
) -> Optional[HoldoutResult]:
    try:
        k = _holdout_k(freq, years_test)
        train, test = _holdout_split(full_series, k=k)
        total_steps = k + max(0, int(forecast_periods))
        base = fit_prophet_insample(sku=sku, train=train, steps_forecast=total_steps, lags=lags, freq=freq)
        if base is None or getattr(base, "forecast", None) is None:
            return None
        fc = np.asarray(base.forecast, dtype="float64")
        if len(fc) < k:
            return None
        fc_test = fc[:k]
        fc_future = fc[k : k + forecast_periods] if forecast_periods > 0 else np.asarray([], dtype="float64")

        try:
            fitted = base.holdout_pred.loc[train.index].values.astype("float64")  # type: ignore[union-attr]
            mae_tr = _mae(train.values, fitted)
        except Exception:
            mae_tr = None
        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            r2_te = None
        try:
            mae_te = _mae(test.values, fc_test)
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
            rmse_train=base.rmse,
        )
    except Exception:
        return None


# -------------------------------------------------------------------------
# Walk-forward validation (multiples folds, ventana de entrenamiento
# expanding) para RF, XGB y Prophet. A diferencia de fit_*_with_holdout
# (un solo split), esto mide si r2_test/rmse_test son estables o volatiles
# entre folds -- la parte "Estabilidad" de #30 que el holdout simple no
# puede responder con un solo punto de medicion.
# -------------------------------------------------------------------------

def _aggregate_walkforward(
    name: str,
    folds: List,
    fit_one_fold,
    horizon: int,
    lags: int,
) -> Optional[WalkForwardResult]:
    r2_tests: List[float] = []
    rmse_trains: List[Optional[float]] = []
    mae_tests: List[Optional[float]] = []
    n_train_rows_list: List[int] = []

    for train, test in folds:
        base = fit_one_fold(train, horizon)
        if base is None or getattr(base, "forecast", None) is None:
            continue
        fc = np.asarray(base.forecast, dtype="float64")
        if len(fc) < horizon:
            continue
        fc_test = fc[:horizon]
        try:
            r2_te = float(_r2(test.values, fc_test))
        except Exception:
            continue
        try:
            mae_te = _mae(test.values, fc_test)
        except Exception:
            mae_te = None

        eff_lags = min(lags, max(1, len(train) - 1))
        n_train_rows_list.append(len(train) - eff_lags)
        r2_tests.append(r2_te)
        rmse_trains.append(base.rmse)
        mae_tests.append(mae_te)

    if not r2_tests:
        return None

    r2_arr = np.asarray(r2_tests, dtype="float64")
    rmse_valid = [v for v in rmse_trains if v is not None and np.isfinite(v)]
    mae_valid = [v for v in mae_tests if v is not None and np.isfinite(v)]
    n_folds = len(r2_tests)

    return WalkForwardResult(
        name=name,
        n_folds=n_folds,
        r2_test_median=float(np.median(r2_arr)),
        r2_test_iqr=float(np.percentile(r2_arr, 75) - np.percentile(r2_arr, 25)) if n_folds > 1 else 0.0,
        rmse_train_median=float(np.median(rmse_valid)) if rmse_valid else None,
        mae_test_median=float(np.median(mae_valid)) if mae_valid else None,
        n_train_rows_mean=float(np.mean(n_train_rows_list)),
        n_train_rows_min=int(np.min(n_train_rows_list)),
        stable=(bool(np.std(r2_arr) < 0.2) if n_folds > 1 else None),
    )


def fit_rf_with_walkforward(
    full_series: pd.Series,
    freq: str,
    lags: int = 12,
    horizon: int = 2,
    max_folds: int = 5,
) -> Optional[WalkForwardResult]:
    try:
        folds = _walk_forward_split(full_series, min_train=2, horizon=horizon, max_folds=max_folds)
        if not folds:
            return None
        return _aggregate_walkforward(
            name="RF",
            folds=folds,
            fit_one_fold=lambda train, steps: fit_rf_insample(train, steps_forecast=steps, lags=lags, freq=freq),
            horizon=horizon,
            lags=lags,
        )
    except Exception:
        log.exception("fit_rf_with_walkforward fallo (lags=%s, freq=%s, n=%s)", lags, freq, len(full_series))
        return None


def fit_xgb_with_walkforward(
    full_series: pd.Series,
    freq: str,
    lags: int = 12,
    horizon: int = 2,
    max_folds: int = 5,
) -> Optional[WalkForwardResult]:
    try:
        folds = _walk_forward_split(full_series, min_train=2, horizon=horizon, max_folds=max_folds)
        if not folds:
            return None
        return _aggregate_walkforward(
            name="XGB",
            folds=folds,
            fit_one_fold=lambda train, steps: fit_xgb_insample(train, steps_forecast=steps, lags=lags, freq=freq),
            horizon=horizon,
            lags=lags,
        )
    except Exception:
        log.exception("fit_xgb_with_walkforward fallo (lags=%s, freq=%s, n=%s)", lags, freq, len(full_series))
        return None


def fit_prophet_with_walkforward(
    full_series: pd.Series,
    freq: str,
    lags: int = 12,
    horizon: int = 2,
    max_folds: int = 5,
    *,
    sku: str,
) -> Optional[WalkForwardResult]:
    try:
        folds = _walk_forward_split(full_series, min_train=2, horizon=horizon, max_folds=max_folds)
        if not folds:
            return None
        return _aggregate_walkforward(
            name="PROPHET",
            folds=folds,
            fit_one_fold=lambda train, steps: fit_prophet_insample(
                sku=sku, train=train, steps_forecast=steps, lags=lags, freq=freq
            ),
            horizon=horizon,
            lags=lags,
        )
    except Exception:
        log.exception(
            "fit_prophet_with_walkforward fallo (sku=%s, lags=%s, freq=%s, n=%s)", sku, lags, freq, len(full_series)
        )
        return None
