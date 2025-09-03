from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .evaluate import rmse as _rmse, r2_score as _r2
from .features import make_lag_matrix, recursive_forecast_tree


@dataclass
class ModelResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    params: Dict
    features: Optional[List[str]] = None
    holdout_pred: Optional[np.ndarray] = None


@dataclass
class CombinedResult:
    name: str
    forecast: np.ndarray
    rmse: Optional[float]
    r2: Optional[float]
    weights: Dict[str, float]


def _fit_sarima_small_grid(y_train: pd.Series):
    """
    Grid chico para estabilidad (mensual con estacionalidad 12).
    """
    best = None
    best_aic = np.inf
    for p in (0, 1):
        for d in (1,):
            for q in (0, 1):
                for P in (0, 1):
                    for D in (1,):
                        for Q in (0, 1):
                            order = (p, d, q)
                            seasonal_order = (P, D, Q, 12)
                            try:
                                with warnings.catch_warnings():
                                    warnings.filterwarnings("ignore", ".*converge.*", ConvergenceWarning)
                                    mod = SARIMAX(
                                        y_train,
                                        order=order,
                                        seasonal_order=seasonal_order,
                                        enforce_stationarity=True,
                                        enforce_invertibility=True,
                                    )
                                    res = mod.fit(disp=False)
                                    if res.aic < best_aic:
                                        best_aic = res.aic
                                        best = (order, seasonal_order, res.params)
                            except Exception:
                                continue
    return best


def fit_sarima(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
) -> Optional[ModelResult]:
    try:
        grid = _fit_sarima_small_grid(train)
        if grid is None:
            return None
        order, seasonal_order, _ = grid
        model = SARIMAX(
            train,
            order=order,
            seasonal_order=seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
        # holdout
        y_pred_eval = model.forecast(steps=steps_eval)
        r = ModelResult(
            name="SARIMA",
            forecast=model.forecast(steps=steps_forecast).values,
            rmse=_rmse(test.values, y_pred_eval.values),
            r2=_r2(test.values, y_pred_eval.values),
            params={"order": order, "seasonal_order": seasonal_order},
            holdout_pred=y_pred_eval.values,
        )
        return r
    except Exception:
        return None


def fit_ets(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
) -> Optional[ModelResult]:
    """
    ETS (Holt-Winters) con:
      - detección de no-positivos -> evita componentes multiplicativos,
      - inicialización 'estimated',
      - use_boxcox=False (evita log con ceros),
      - silenciamiento de warnings conocidos,
      - fallback a suavizamiento simple si falla.
    """
    import warnings
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from statsmodels.tools.sm_exceptions import ConvergenceWarning

    try:
        y = pd.Series(train, dtype="float64").copy()
        seasonal_periods = 12  # mensual con estacionalidad anual
        trend = "add"

        # Evitar multiplicativo si hay valores <= 0
        has_nonpos = (y <= 0).any()

        # Intento 1: multiplicativo (solo si todos > 0)
        seasonal_used = None
        fit = None
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", ".*Optimization failed to converge.*", ConvergenceWarning)
            warnings.filterwarnings("ignore", ".*divide by zero encountered in log.*", RuntimeWarning)

            if (not has_nonpos) and seasonal_periods and seasonal_periods > 1:
                try:
                    model = ExponentialSmoothing(
                        y,
                        trend=trend,
                        seasonal="mul",
                        seasonal_periods=seasonal_periods,
                        initialization_method="estimated",
                    )
                    fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)
                    seasonal_used = "mul"
                except Exception:
                    fit = None  # cae al intento aditivo

            # Intento 2: aditivo
            if fit is None:
                model = ExponentialSmoothing(
                    y,
                    trend=trend,
                    seasonal="add" if seasonal_periods and seasonal_periods > 1 else None,
                    seasonal_periods=seasonal_periods if seasonal_periods and seasonal_periods > 1 else None,
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)
                seasonal_used = "add" if seasonal_periods and seasonal_periods > 1 else None

        # Predicción en holdout (para métricas)
        if steps_eval > 0:
            y_pred_eval = fit.forecast(steps=steps_eval)
            y_true = np.asarray(test.values, dtype="float64")
            y_pred_eval_np = np.asarray(y_pred_eval.values, dtype="float64")
            rmse_val = _rmse(y_true, y_pred_eval_np)
            r2_val = _r2(y_true, y_pred_eval_np)
            holdout_pred = y_pred_eval_np
        else:
            rmse_val = None
            r2_val = None
            holdout_pred = None

        # Forecast futuro
        yhat_forecast = np.asarray(fit.forecast(steps=steps_forecast), dtype="float64")

        return ModelResult(
            name="ETS",
            forecast=yhat_forecast,
            rmse=rmse_val,
            r2=r2_val,
            params={"trend": trend, "seasonal": seasonal_used, "sp": seasonal_periods},
            holdout_pred=holdout_pred,
        )

    except Exception:
        # Fallback final: suavizamiento simple (sin tendencia/estacionalidad)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = ExponentialSmoothing(
                    pd.Series(train, dtype="float64"),
                    initialization_method="estimated",
                )
                fit = model.fit(optimized=True, use_boxcox=False, remove_bias=True)

            if steps_eval > 0:
                y_pred_eval = fit.forecast(steps=steps_eval)
                y_true = np.asarray(test.values, dtype="float64")
                y_pred_eval_np = np.asarray(y_pred_eval.values, dtype="float64")
                rmse_val = _rmse(y_true, y_pred_eval_np)
                r2_val = _r2(y_true, y_pred_eval_np)
                holdout_pred = y_pred_eval_np
            else:
                rmse_val = None
                r2_val = None
                holdout_pred = None

            yhat_forecast = np.asarray(fit.forecast(steps=steps_forecast), dtype="float64")

            return ModelResult(
                name="ETS",
                forecast=yhat_forecast,
                rmse=rmse_val,
                r2=r2_val,
                params={"trend": None, "seasonal": None, "sp": None},
                holdout_pred=holdout_pred,
            )
        except Exception:
            return None



def fit_rf(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
    rf_params: Dict,
    lags: int = 12,
) -> Optional[ModelResult]:
    try:
        X_tr, y_tr, feats = make_lag_matrix(train, lags=lags)

        rf = RandomForestRegressor(**rf_params)
        rf.fit(X_tr, y_tr)

        # Holdout: predicción recursiva sobre k pasos
        y_pred_eval = recursive_forecast_tree(rf, train, steps=steps_eval, lags=lags)

        # Forecast real
        y_pred_fc = recursive_forecast_tree(rf, train, steps=steps_forecast, lags=lags)

        return ModelResult(
            name="RF",
            forecast=y_pred_fc,
            rmse=_rmse(test.values, y_pred_eval),
            r2=_r2(test.values, y_pred_eval),
            params=rf.get_params(),
            features=feats,
            holdout_pred=y_pred_eval,
        )
    except Exception:
        return None


def fit_xgb(
    train: pd.Series,
    test: pd.Series,
    steps_eval: int,
    steps_forecast: int,
    xgb_params: Dict,
    lags: int = 12,
) -> Optional[ModelResult]:
    try:
        X_tr, y_tr, feats = make_lag_matrix(train, lags=lags)
        xgb = XGBRegressor(**xgb_params)
        xgb.fit(X_tr, y_tr)

        y_pred_eval = recursive_forecast_tree(xgb, train, steps=steps_eval, lags=lags)
        y_pred_fc = recursive_forecast_tree(xgb, train, steps=steps_forecast, lags=lags)

        return ModelResult(
            name="XGB",
            forecast=y_pred_fc,
            rmse=_rmse(test.values, y_pred_eval),
            r2=_r2(test.values, y_pred_eval),
            params=xgb.get_params(),
            features=feats,
            holdout_pred=y_pred_eval,
        )
    except Exception:
        return None


def combine_by_inverse_rmse(models: List[ModelResult], steps: int) -> CombinedResult:
    """
    Combina por pesos ~ 1/RMSE sobre los MODELOS NO combinados.
    Si solo hay un modelo, usa peso 1. Normaliza pesos.
    RMSE/R2 de la combinada se calculan sobre las predicciones de holdout.
    """
    base = [m for m in models if m.name != "COMBINADA" and m.rmse is not None and m.holdout_pred is not None]
    if not base:
        # si no hay base, fallback a primer forecast disponible que tenga longitud adecuada
        for m in models:
            if len(m.forecast) >= steps:
                return CombinedResult(name="COMBINADA", forecast=m.forecast[:steps], rmse=None, r2=None, weights={m.name: 1.0})
        return CombinedResult(name="COMBINADA", forecast=np.zeros(steps), rmse=None, r2=None, weights={})

    inv = []
    for m in base:
        val = (1.0 / max(m.rmse, 1e-6)) if m.rmse is not None else 0.0
        inv.append(val)
    s = sum(inv)
    if s <= 0:
        weights = {m.name: 1.0 / len(base) for m in base}
    else:
        weights = {m.name: w / s for m, w in zip(base, inv)}

    # Holdout combinado
    # Alineamos por longitud mínima
    min_len = min(len(m.holdout_pred) for m in base)
    combo_hold = np.zeros(min_len)
    for m in base:
        combo_hold += weights[m.name] * np.asarray(m.holdout_pred[:min_len])

    # Forecast combinado (asume todos tienen al menos 'steps' valores tras recortes previos)
    combo_fc = np.zeros(steps)
    for m in base:
        combo_fc += weights[m.name] * np.asarray(m.forecast[:steps])

    # Para métricas de la combinada necesitamos el y_true del holdout.
    # Tomamos y_true a partir de cualquiera (debería ser idéntico entre modelos)
    # Aquí devolvemos None; la métrica será calculada externamente si se requiere.
    # En este diseño necesitamos que quien llama tenga 'test' para evaluar,
    # así que movemos el cálculo aquí recibiendo y_true… pero para mantener firmas
    # calcularemos aproximado con el primer modelo base y_true de su RMSE (no accesible).
    # => Alternativa: guardamos y_true dentro de ModelResult no estaba; resolvemos en caller.
    # Solución: pedimos que los resultados ya tengan RMSE/R2 de holdout. Para la combinada:
    # no tenemos y_true aquí; devolvemos rmse/r2 como None y el caller las computa si lo desea.
    # En nuestra implementación de CLI sí conocemos 'test', por eso allí recalculamos:
    return CombinedResult(name="COMBINADA", forecast=combo_fc, rmse=None, r2=None, weights=weights)
