from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def make_lag_matrix(y: pd.Series, lags: int = 12) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Construye matriz de características con rezagos -1..-lags exclusivamente.
    Devuelve (X, y_target, feature_names).
    """
    df = pd.DataFrame({"y": y})
    for i in range(1, lags + 1):
        df[f"lag_{i}"] = df["y"].shift(i)
    df = df.dropna().copy()
    feature_cols = [f"lag_{i}" for i in range(1, lags + 1)]
    X = df[feature_cols]
    y_target = df["y"]
    return X, y_target, feature_cols


def recursive_forecast_tree(
    model,
    train_series: pd.Series,
    steps: int,
    lags: int = 12,
) -> np.ndarray:
    """
    Pronóstico recursivo para modelos de árbol (RF/XGB) usando solo lags 1..lags.
    """
    hist = train_series.copy().astype(float)
    preds = []
    # Creamos un buffer con los últimos 'lags' valores
    buf = list(hist.iloc[-lags:].values)
    for _ in range(steps):
        # Cada paso: la feature es el vector de lags actuales
        X_step = pd.DataFrame([buf[::-1]], columns=[f"lag_{i}" for i in range(1, lags + 1)])  # lag_1 es el más reciente
        yhat = float(model.predict(X_step)[0])
        preds.append(yhat)
        # Actualiza el buffer
        buf = buf[1:] + [yhat]
    return np.array(preds)
