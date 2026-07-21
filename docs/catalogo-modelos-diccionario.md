# Diccionario de variables de entrada — modelos de forecasting

Explica, una sola vez, qué representa conceptualmente cada variable de entrada (`feature`) usada por los 4 algoritmos de forecasting (RandomForest, XGBoost, Prophet, ETS). Referencia para interpretar la columna `features` de `catalogo_modelos` (issue #86) sin tener que releer `ml/models.py` cada vez.

Fuente: `services/python-worker/ml/models.py`, función `_build_lag_month_trend` y `fit_rf_insample`/`fit_xgb_insample`/`fit_prophet_insample`/`fit_ets_insample`.

## RandomForest y XGBoost

Ambos modelos usan exactamente el mismo conjunto de features, construido por `_build_lag_month_trend`:

| Feature | Significado |
|---|---|
| `lag_N` (ej. `lag_1`, `lag_2`, ..., `lag_12`) | Venta del SKU hace `N` periodos. Un periodo es un mes si `freq="MS"` o un trimestre si `freq` es trimestral — la unidad depende del parámetro `freq` con el que se entrenó ese SKU. |
| `period` | Mes (`1`-`12`, vía `df.index.month`) o trimestre (`1`-`4`, vía `df.index.quarter`) del periodo a predecir, según `freq`. Captura estacionalidad calendario. |
| `trend` | Índice secuencial `0..n` (`np.arange(len(df))`). Captura tendencia lineal a lo largo de la serie. |

**Cantidad efectiva de lags (`eff_lags`).** La cantidad de columnas `lag_N` no es fija en `lags` (default 12): se recorta a `eff_lags = min(lags, max(1, len(train) - 1))`. Si un SKU tiene poca historia, `eff_lags` es menor al `lags` pedido, y por lo tanto tiene menos columnas `lag_N` que otro SKU con historia completa. La columna `features` de `catalogo_modelos` refleja esto — puede variar entre filas de SKUs distintos aunque el `modelo` sea el mismo.

## Prophet

Prophet no usa `lag_N`/`period`/`trend` — su input es directamente la serie de tiempo:

| Input | Significado |
|---|---|
| `ds` | Fecha de cada observación. |
| `y` | Venta del SKU en esa fecha. |

La estacionalidad anual y los changepoints (puntos donde cambia la tendencia) se manejan **internamente** por la librería, no como columnas de features expuestas. Se controlan vía hiperparámetros del modelo (no vía input data):

- `changepoint_prior_scale`
- `seasonality_prior_scale`
- `n_changepoints`
- (además `holidays_prior_scale`, `seasonality_mode`, `changepoint_range` — ver `HIPERPARAMETROS_OPTIMOS`/`HIPERPARAMETROS_GENERICOS` en `ml/models.py`)

Estos valores están hipertuneados por SKU en `HIPERPARAMETROS_OPTIMOS`; para un SKU sin entrada específica se usa `HIPERPARAMETROS_GENERICOS`, calculado como la moda de los valores optimizados existentes.

## ETS (Holt-Winters)

Igual que Prophet, ETS no usa `lag_N`/`period`/`trend` -- su input es directamente la serie de tiempo (`statsmodels.tsa.holtwinters.ExponentialSmoothing` recibe la serie completa, sin construir un `DataFrame` de features). Sus "features" son hiperparámetros del modelo:

| Hiperparámetro | Significado |
|---|---|
| `trend` | Tipo de componente de tendencia. Fijo en `"add"` (aditivo): la tendencia se suma a la serie, a diferencia de `"mul"` (multiplicativo), que la escala. Se usa aditivo porque `ExponentialSmoothing` exige datos estrictamente positivos para componentes multiplicativos, y la serie de entrenamiento puede tener valores negativos reales (notas de crédito, ver issue #81) que no se filtran antes de entrenar. |
| `damped_trend` | Si la tendencia se "amortigua" (se aplana) a medida que el horizonte de pronóstico se aleja, en vez de extrapolarse en línea recta indefinidamente. Fijo en `True` -- más conservador para el forecast futuro. |
| `seasonal` | Tipo de componente estacional. Fijo en `"add"` (aditivo), mismo motivo que `trend`. |
| `seasonal_periods` | Cantidad de periodos en un ciclo estacional completo: `4` si `freq` es trimestral, `12` si es mensual. Determina cuántas observaciones necesita el modelo para aprender el patrón estacional. |

**Historia mínima.** A diferencia de RF/XGB (que dependen de `eff_lags`) o de Prophet (`min_needed=8` trimestral / `12` mensual), ETS necesita al menos **2 ciclos estacionales completos** para estimar el componente estacional (`min_needed = 2 * seasonal_periods`: 8 periodos trimestral, 24 mensual) -- por debajo de eso, `fit_ets_insample` devuelve `None` sin intentar el fit (`statsmodels` tira `ValueError` si se le pide un ajuste estacional sin suficientes ciclos).

## Ver también

- [Issue #84](https://github.com/Evalutia/App-Forecast/issues/84) — tabla `catalogo_modelos`, columna `features` guarda la lista real usada en cada fit.
- [`docs/script-de-prediccion.md`](./script-de-prediccion.md) — detalle línea por línea de `predict.py` y la estructura de `ml/`.
