"""
data_loader.py
Funciones para preparar ventanas (input_length, output_length) para series temporales.
Soporta resample por 'Q' (trimestral) o 'M' (mensual) y permite cambiar fácilmente.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple

def ensure_freq(series: pd.Series, rule: str = "Q", agg: str = "sum", fill: str = "zero") -> pd.Series:
    s = pd.Series(series).astype("float64")
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    if agg == "sum":
        s = s.resample(rule).sum()
    elif agg == "mean":
        s = s.resample(rule).mean()
    elif agg == "first":
        s = s.resample(rule).first()
    elif agg == "last":
        s = s.resample(rule).last()
    else:
        raise ValueError("agg inválido")
    # keep from first sale
    first_sale = s[s > 0].first_valid_index()
    if first_sale is not None:
        s = s.loc[first_sale:]
    if len(s) == 0:
        return s
    if fill in ("zero", "ffill"):
        idx = pd.date_range(s.index.min(), s.index.max(), freq=rule)
        s = s.reindex(idx)
        s = s.fillna(0.0) if fill == "zero" else s.ffill().fillna(0.0)
    return s

def create_windows(series: pd.Series, input_length: int, output_length: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Construye ventanas rolling. Devuelve (X, y) con X.shape = (n_windows, input_length)
    y.shape = (n_windows, output_length)
    """
    x_list = []
    y_list = []
    arr = np.asarray(series.values, dtype="float32")
    total = input_length + output_length
    if len(arr) < total:
        return np.empty((0, input_length), dtype=np.float32), np.empty((0, output_length), dtype=np.float32)
    for start in range(0, len(arr) - total + 1):
        x = arr[start : start + input_length]
        y = arr[start + input_length : start + total]
        x_list.append(x)
        y_list.append(y)
    return np.stack(x_list).astype(np.float32), np.stack(y_list).astype(np.float32)

def prepare_dataset(series_dict: dict, input_length: int = 8, output_length: int = 2, rule: str = "Q"):
    """
    series_dict: {sku: pd.Series}
    Devuelve X_all, y_all, skus_all (concatenados)
    Por defecto usa trimestral (rule='Q') y ventanas input=8 trimestres, output=2 trimestres.
    """
    Xs = []
    Ys = []
    Skus = []
    for sku, ser in series_dict.items():
        s = ensure_freq(ser, rule=rule)
        Xw, Yw = create_windows(s, input_length, output_length)
        if Xw.shape[0] > 0:
            Xs.append(Xw)
            Ys.append(Yw)
            Skus += [sku] * Xw.shape[0]
    if not Xs:
        return None, None, None
    X_all = np.concatenate(Xs, axis=0)
    y_all = np.concatenate(Ys, axis=0)
    return X_all, y_all, Skus
