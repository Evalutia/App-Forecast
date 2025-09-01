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
    return float(_r2(y_true, y_pred))
