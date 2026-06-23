#!/usr/bin/env bash
# run_predict.sh - wrapper de predict.py con filtro de SKUs (Issue #43).
#
# RUN PREDICT.PY corria predict.py sin --skus: tomaba TODO ventas_historicas
# sin filtro, corriendo modelos econometricos (SARIMAX/Prophet/XGBoost/RF)
# sobre SKUs que no deberian tenerlos. La lista de SKUs habilitados sale de
# get_skus_modelo.py (articulos JOIN grupos WHERE aplica_modelo_econometrico).
set -euo pipefail

: "${MYSQL_HOST:?missing}"
: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"
: "${PREDICT_PERIODS:?missing}"
: "${PREDICT_RESAMPLE_RULE:?missing}"
: "${PREDICT_MODEL_SET:?missing}"
: "${PREDICT_VERSION:?missing}"

SKUS_LIST="$(python3 /app/services/etl/get_skus_modelo.py)"

if [[ -z "${SKUS_LIST}" ]]; then
  echo "[ERROR] Lista de SKUs vacia (articulos JOIN grupos WHERE aplica_modelo_econometrico=true sin resultados)." >&2
  echo "[ERROR] No se corre predict.py esta noche -- mejor no predecir nada que predecir sobre todo el catalogo sin filtro." >&2
  exit 2
fi

SKUS_COUNT="$(printf '%s' "${SKUS_LIST}" | tr ',' '\n' | wc -l)"
echo "[INFO] SKUs con modelo econometrico habilitado: ${SKUS_COUNT}"

python3 /app/services/python-worker/predict.py \
  --input-source mysql \
  --mysql-host="${MYSQL_HOST}" \
  --mysql-port="${MYSQL_PORT}" \
  --mysql-db="${MYSQL_DB}" \
  --mysql-user="${MYSQL_USER}" \
  --mysql-pass="${MYSQL_PASSWORD}" \
  --periods="${PREDICT_PERIODS}" \
  --resample-rule="${PREDICT_RESAMPLE_RULE}" \
  --model-set="${PREDICT_MODEL_SET}" \
  --version="${PREDICT_VERSION}" \
  --force-end="${FORCE_END:-}" \
  --skus="${SKUS_LIST}"
