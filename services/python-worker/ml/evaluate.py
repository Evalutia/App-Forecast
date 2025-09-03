from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, r2_score as _r2


def holdout_split(series: pd.Series, k: int = 6) -> Tuple[pd.Series, pd.Series]:
    """
    Divide la serie en train/test con holdout en los últimos k puntos.
    """
    if k <= 0 or k >= len(series):
        raise ValueError("k inválido para holdout_split")
    return series.iloc[:-k].copy(), series.iloc[-k:].copy()


def rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def r2_score(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    u = np.sum((y_true - y_pred) ** 2)
    v = np.sum((y_true - y_true.mean()) ** 2)
    if v <= 0:
        return 0.0  # mismo criterio que usan muchos notebooks si varianza cero
    return 1.0 - (u / v)

