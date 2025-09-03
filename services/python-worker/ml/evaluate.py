from __future__ import annotations
from sklearn.metrics import mean_squared_error, r2_score as _r2
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
    Idéntico a sklearn.metrics.r2_score (misma semántica numérica).
    """
    y_true = np.asarray(y_true, dtype=np.float64).ravel()
    y_pred = np.asarray(y_pred, dtype=np.float64).ravel()
    return float(_r2(y_true, y_pred))
