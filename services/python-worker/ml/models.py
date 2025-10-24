from __future__ import annotations

import numpy as np
import pandas as pd

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from .evaluate import rmse as _rmse, r2_score as _r2


@dataclass
class ModelResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    params: Dict
    features: Optional[List[str]] = None
    holdout_pred: Optional[pd.Series] = None


def _build_lag_month_trend(series: pd.Series, lags: int) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
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
            n_estimators=100,
            min_samples_leaf=2,
            max_features="sqrt",
            random_state=0
        )
        rf.fit(X_rf, y_rf)

        fit_part = pd.Series(rf.predict(X_rf), index=X_rf.index, dtype="float64")
        rf_full = fit_part.reindex(tr.index).ffill().bfill()

        # rolling one-step-ahead usando predicción autoregresiva
        hist = tr.tolist()[-lags:]
        oos = []
        for i in range(steps_forecast):
            idx = tr.index[-1] + pd.offsets.MonthBegin(i + 1)
            xlags = hist[-lags:][::-1]
            df_feat = pd.DataFrame([xlags], columns=[f"lag_{j+1}" for j in range(lags)])
            df_feat["month"] = idx.month
            df_feat["trend"] = len(tr) + i
            df_feat = df_feat[feats]
            p = float(rf.predict(df_feat)[0])
            oos.append(p)
            hist.append(p)
        y_fc = np.asarray(oos, dtype="float64")

        rmse_full = _rmse(tr.values, rf_full.values)
        r2_valid = _r2(y_rf.values, fit_part.values)

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


def fit_xgb_insample(train: pd.Series, steps_forecast: int, lags: int = 12) -> Optional[ModelResult]:
    try:
        tr = pd.Series(train).astype("float64").sort_index()
        X_rf, y_rf, feats = _build_lag_month_trend(tr, lags)

        xgb = XGBRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.03,
            reg_alpha=1,
            reg_lambda=1,
            min_child_weight=2,
            subsample=0.7,
            colsample_bytree=0.7,
            random_state=0,
            objective="reg:squarederror",
        )
        xgb.fit(X_rf, y_rf)

        fit_part = pd.Series(xgb.predict(X_rf), index=X_rf.index, dtype="float64")
        xgb_full = fit_part.reindex(tr.index).ffill().bfill()

        # rolling one-step-ahead usando predicción autoregresiva
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

        rmse_full = _rmse(tr.values, xgb_full.values)
        r2_valid = _r2(y_rf.values, fit_part.values)

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
