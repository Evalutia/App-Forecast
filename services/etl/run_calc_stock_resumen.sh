#!/usr/bin/env bash
# run_calc_stock_resumen.sh - Wrapper no-bloqueante para run_calc_stock_resumen.py
# Llamado desde job_etl_diario.kjb después de RUN CALC_SUGERENCIAS.
# Siempre termina con exit 0: un fallo aquí no aborta el job maestro.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SELF_DIR}/run_calc_stock_resumen.py"
LOG="/tmp/calc_stock_resumen.log"

echo "[CALC_STOCK_RESUMEN] Iniciando cálculo de stock_resumen_365..."

MYSQL_HOST="${MYSQL_HOST:-mysql}" \
MYSQL_PORT="${MYSQL_PORT:-3306}" \
MYSQL_DB="${MYSQL_DB:?MYSQL_DB requerido}" \
MYSQL_USER="${MYSQL_USER:?MYSQL_USER requerido}" \
MYSQL_PASSWORD="${MYSQL_PASSWORD:?MYSQL_PASSWORD requerido}" \
python3 "${SCRIPT}" 2>&1 | tee "${LOG}"

rc=${PIPESTATUS[0]}

if [[ ${rc} -ne 0 ]]; then
  echo "[CALC_STOCK_RESUMEN][WARN] El script terminó con código ${rc}. Ver ${LOG}." >&2
  echo "[CALC_STOCK_RESUMEN][WARN] El fallo no aborta el ETL — continuando."
else
  echo "[CALC_STOCK_RESUMEN] OK"
fi

exit 0
