# services/python-worker/ml/evaluate.py
from __future__ import annotations
from sklearn.metrics import mean_squared_error
from typing import Tuple

import numpy as np
import pandas as pd

def holdout_split(series: pd.Series, k: int = 6) -> Tuple[pd.Series, pd.Series]:
    """
    Divide la serie en train/test con holdout en los últimos k puntos (sin corrimientos).
    """
    if k <= 0 or k >= len(series):
        raise ValueError("k inválido para holdout_split")
    s = pd.Series(series.copy()).astype("float64")
    s = s.sort_index()
    return s.iloc[:-k].copy(), s.iloc[-k:].copy()

def rmse(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))

def r2_score(y_true, y_pred) -> float:
    """
    R2 definido como (PearsonCorr(y_true, y_pred))**2 de forma robusta.

    Reglas:
    - Si y_true está vacío -> nan
    - Si varianza(y_true) == 0:
        * Si y_pred == y_true exactamente -> 1.0
        * Si no -> 0.0
    - Se calculan con valores finitos (se ignoran NaN/Inf pares).
    - Si y_pred es constante y no coincide con y_true -> 0.0.
    """
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()

    if y_true.size == 0:
        return float("nan")

    # filtrar valores finitos
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    if not np.any(mask):
        return float("nan")
    yt = y_true[mask]
    yp = y_pred[mask]

    # caso: varianza cero en y_true
    if np.nanstd(yt) == 0.0:
        # si yp coincide con yt exactamente -> 1.0, sino 0.0
        return 1.0 if np.allclose(yt, yp, equal_nan=True) else 0.0

    # si yp constante (sin variación) -> correlación 0 salvo coincidencia exacta
    if np.nanstd(yp) == 0.0:
        return 1.0 if np.allclose(yt, yp, equal_nan=True) else 0.0

    # calcular correlación de Pearson de forma numérica estable
    try:
        cor = np.corrcoef(yt, yp)[0, 1]
        if not np.isfinite(cor):
            return float("nan")
        return float(cor ** 2)
    except Exception:
        return float("nan")
