# python-worker · Forecasting CLI

CLI para ejecutar pronósticos mensuales por SKU con SARIMA, ETS, RandomForest y XGBoost (y combinación por inverse-RMSE), escribir resultados en MySQL y registrar el historial de jobs.

## Variables de entorno

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DB=evalutia
MYSQL_USER=evalutia
MYSQL_PASS=evalutia

## Uso en Docker

Ejemplo con docker compose y servicio python-worker montado en /app:

docker compose exec python-worker python /app/services/python-worker/predict.py \
  --csv /data/calendario_ventas.csv \
  --periods 6 \
  --version v1.0.0

## Uso local

export MYSQL_HOST=localhost MYSQL_DB=evalutia MYSQL_USER=evalutia MYSQL_PASS=evalutia1234-
python -m pip install -r services/python-worker/requirements.txt

### Con Csv en data/
python services/python-worker/predict.py --input-source csv --csv data/calendario_ventas.csv --version v2025.09.03 --model-set full --periods 6 --resample-rule MS --resample-agg sum --fill-na zero --min-history 24 --mysql-db evalutia --mysql-user evalutia --mysql-pass evalutia

### Desde MySQL
python services/python-worker/predict.py --input-source=mysql --mysql-host localhost --mysql-port 3306 --mysql-db evalutia --mysql-user evalutia --mysql-pass 'evalutia' --mysql-table ventas_historicas --periods 6 --model-set full --version v2025.09.04


## Preguntas frecuentes (FAQ)

1) Explicación (casi) línea por línea de predict.py

### Imports y utilitarios

Se importan librerías estándar (argparse, logging, os, time, json, etc.) y científicas (numpy, pandas) más módulos propios (io.db, io.data, ml.*, utils.*).

Razón: separar IO/DB, ML y utilidades para mantener el script principal limpio.

### parse_args()

Define todos los flags pedidos: --csv, --freq, --periods, --skus, --min-history, --version, --model-set, credenciales MySQL, --start-month, --log-level.

choices en --model-set restringe a full|classic|tree.

Defaults de MySQL caen a variables de entorno.

### Helpers

months_gap(base_next, target_start, freq): calcula cuántos pasos mensuales hay que “descartar” si pedís un --start-month posterior al siguiente mes disponible.

forecast_index(start_month, periods, freq): genera el índice de fechas para el horizonte pedido.

as_decimal4(x): formatea la predicción a Decimal con 4 decimales (match con DECIMAL(18,4)).

### main()

Parseo y logging: resuelve version con resolve_version, configura logs JSON (setup_logging).

Conexión DB: crea DBConfig y engine SQLAlchemy (MySQL PyMySQL).

Jobs: inserta fila en jobs_historial con estado ejecutando y guarda job_id.

Carga de datos: load_series_by_sku(...) lee el CSV, resamplea a mensual y retorna dict[sku -> Serie]. Si se pasa --skus, filtra lista.

Fecha de inicio de forecast:

Si hay --start-month, se usa; si no, el mes siguiente al último dato de cada SKU.

lead_in = meses que hay que “consumir” para alinear si pediste un start más adelante.

Selección de modelos:

Flags booleanos want_sarima, want_ets, want_rf, want_xgb, want_comb según --model-set.

Define rf_params y xgb_params con regularización y random_state=42.

Loop por SKU:

Valida --min-history.

Hace holdout con holdout_split(serie, k=min(6, periods)) para evaluar RMSE y R².

Calcula base_next y lead_in para alinear el comienzo real del forecast.

Entrena y evalúa:

fit_sarima, fit_ets, fit_rf, fit_xgb devuelven ModelResult con: forecast, rmse, r2, params y (si aplica) features.

Si hubo lead_in, se recorta cada forecast para arrancar exactamente en --start-month o en el mes posterior al último dato (cuando no se pasa --start-month).

Combinado: combine_by_inverse_rmse(results, steps=periods) arma la COMBINADA con pesos ∝ 1/RMSE.

Armado de filas: para cada modelo, genera N filas con sku, fecha_predicha, cantidad_predicha, modelo, version_modelo, horizonte, rmse, r2.

Captura warnings y continua ante errores por SKU (no se cae el job).

Upsert en predicciones:

upsert_predicciones(engine, rows_buffer) usa INSERT ... ON DUPLICATE KEY UPDATE.

Requiere índice único UNIQUE (sku, modelo, version_modelo, fecha_predicha).

Update del job:

Marca exitoso y persiste detalle con: skus, modelos, periods, versión, hiperparámetros y features efectivas (RF/XGB), y warnings.

Resumen final:

Imprime una tabla con sku, modelo, rmse, r2, params, features.

Muestra job_id, ruta de MySQL, filas insertadas y tiempo total.

Manejo de excepción global:

Si algo falla a nivel general, actualiza el job como fallido con detalle.error y sale con código 1.

En resumen: predict.py orquesta parseo → carga → entrenamiento/evaluación → combinación → upsert → logging/métricas → cierre del job.

2) ¿Por qué la estructura de carpetas dentro de python-worker (ml, io, utils)?

ml/: todo lo que es lógica de modelado (features, entrenamiento, evaluación, combinación). Esto permite testear los modelos sin tocar IO/DB.

io/: entrada/salida de datos: lectura del CSV (limpieza/resampleo) y persistencia (conexión y escritura/lectura en MySQL).

utils/: utilitarios transversales: logging (JSON estructurado con job_id), versionado (resuelve --version o GIT_SHA).

Este desacople hace que:

el CLI sea delgado y fácil de leer,

puedas reusar ml/ en otros flows (batch/backfill),

puedas mockear io/db.py en tests sin tocar el resto.

3) ¿Por qué se dejan vacíos algunos __init__.py en vez de borrarlos?

En Python, un directorio se convierte en paquete cuando tiene __init__.py.

Aunque desde Python 3 se pueden usar namespace packages sin __init__.py, mantenerlo vacío evita ambigüedades, es más compatible con herramientas, y te permite, si querés, inyectar inicialización de paquete a futuro (p.ej., configuración global).

En resumen: lo dejamos intencionalmente para asegurar que from ml import .../from io import ... funcione de forma explícita y estable.

4) ¿Qué define features.py y dónde se llama?

Qué define:

make_lag_matrix(y, lags=12): crea la matriz de rezagos lag_1..lag_12 (solo lags, sin exógenas), devolviendo X, y_target y lista de features.

recursive_forecast_tree(model, train_series, steps, lags=12): hace forecast recursivo para modelos tipo árbol (RF/XGB) usando exclusivamente los lags como entrada.

Dónde se llama:

Desde ml/models.py: fit_rf y fit_xgb utilizan make_lag_matrix para entrenar y recursive_forecast_tree para evaluar/forecastear recursivamente.

predict.py no lo llama directo; lo usa a través de las funciones de models.py.

5) ¿Qué define models.py y dónde se llama? ¿Por qué hay tanto comentario al final? ¿Está bien eso?

Qué define:

ModelResult y CombinedResult (dataclasses) para normalizar la salida de cada modelo.

fit_sarima, fit_ets, fit_rf, fit_xgb: entrenan, generan predicciones de holdout (para RMSE/R²) y forecast para producción.

combine_by_inverse_rmse(models, steps): arma la COMBINADA con pesos normalizados ∝ 1/RMSE usando solo modelos que lograron métrica válida; devuelve forecast combinado y pesos.

Dónde se llama:

Directamente desde predict.py dentro del loop por SKU. Ese script decide qué modelos ejecutar según --model-set y luego arma filas para MySQL.

¿Y los comentarios extensos?
Sí, es intencional. Documentan decisiones críticas:

Por qué el grid de SARIMA es pequeño (estabilidad/tiempo).

Cómo se calculan pesos de la combinada y qué hacer si faltan modelos válidos.

Notas sobre métricas de la COMBINADA (se derivan de las de holdout de los modelos base y se reportan de forma consistente).

En código de producción, documentar claramente la lógica de combinación/validación evita malentendidos futuros y facilita auditoría/revisión. Está bien y es recomendable.