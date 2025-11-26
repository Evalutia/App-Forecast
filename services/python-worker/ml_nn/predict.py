"""
predict.py
Funciones para cargar un checkpoint y predecir por SKU.
Exposición principal: predict_for_sku(series, input_length, output_length, device)
"""

import torch
import numpy as np
import pandas as pd
from ml_nn.model import make_model

def load_checkpoint(path="checkpoints/best_model.pth", device='cpu'):
    data = torch.load(path, map_location=device)
    input_length = data.get("input_length", None)
    output_length = data.get("output_length", None)
    model = make_model(input_length=input_length, output_length=output_length, device=device)
    model.load_state_dict(data["model_state"])
    model.eval()
    return model, input_length, output_length

def predict_for_series(model, series: pd.Series, input_length: int, output_length: int, rule='Q'):
    # ensure freq and take last input_length periods
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    if rule == 'Q':
        s = s.resample('Q').sum()
    else:
        s = s.resample(rule).sum()
    s = s.sort_index()
    arr = s.values.astype(np.float32)
    if len(arr) < input_length:
        # pad with zeros at front
        pad = np.zeros(input_length - len(arr), dtype=np.float32)
        arr = np.concatenate([pad, arr])
    x = arr[-input_length:]
    x_t = torch.from_numpy(x.reshape(1, -1))
    with torch.no_grad():
        pred = model(x_t)
    return pred.numpy().ravel()[:output_length]

def predict_for_sku(series: pd.Series, checkpoint_path="checkpoints/best_model.pth", device='cpu', rule='Q'):
    model, input_length, output_length = load_checkpoint(checkpoint_path, device=device)
    yhat = predict_for_series(model, series, input_length, output_length, rule=rule)
    # return as list of floats
    return [float(x) for x in yhat]
