# services/python-worker/ml/evaluate.py
from __future__ import annotations
from sklearn.metrics import mean_squared_error
from typing import List, Tuple

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

def walk_forward_split(
    series: pd.Series, min_train: int = 2, horizon: int = 2, max_folds: int = 5
) -> List[Tuple[pd.Series, pd.Series]]:
    """
    Genera folds walk-forward con ventana de entrenamiento expanding (crece
    con toda la historia disponible, igual que entrena predict.py).

    Cada fold testea 'horizon' puntos. El numero de folds se adapta a la
    historia disponible (minimo min_train, tope max_folds), repartidos
    parejo a lo largo de toda la historia utilizable (no solo los ultimos
    periodos). Si no entra ni un fold, devuelve lista vacia.
    """
    s = pd.Series(series.copy()).astype("float64").sort_index()
    n = len(s)
    max_origin = n - horizon
    if max_origin < min_train:
        return []

    count = max_origin - min_train + 1
    if count <= max_folds:
        origins = list(range(min_train, max_origin + 1))
    else:
        idx = np.linspace(0, count - 1, max_folds)
        origins = sorted({min_train + int(round(i)) for i in idx})

    return [(s.iloc[:origin].copy(), s.iloc[origin:origin + horizon].copy()) for origin in origins]

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
