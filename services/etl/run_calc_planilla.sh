#!/usr/bin/env bash
# run_calc_planilla.sh - Wrapper no-bloqueante para run_calc_planilla.py
# Llamado desde job_etl_diario.kjb después de RUN PREDICT.PY.
# Siempre termina con exit 0: un fallo aquí no aborta el job maestro.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SELF_DIR}/run_calc_planilla.py"
LOG="/tmp/calc_planilla.log"

echo "[CALC_PLANILLA] Iniciando cálculo de planilla_ventas_calculada..."

MYSQL_HOST="${MYSQL_HOST:-mysql}" \
MYSQL_PORT="${MYSQL_PORT:-3306}" \
MYSQL_DB="${MYSQL_DB:?MYSQL_DB requerido}" \
MYSQL_USER="${MYSQL_USER:?MYSQL_USER requerido}" \
MYSQL_PASSWORD="${MYSQL_PASSWORD:?MYSQL_PASSWORD requerido}" \
python3 "${SCRIPT}" 2>&1 | tee "${LOG}"

rc=${PIPESTATUS[0]}

if [[ ${rc} -ne 0 ]]; then
  echo "[CALC_PLANILLA][WARN] El script terminó con código ${rc}. Ver ${LOG}." >&2
  echo "[CALC_PLANILLA][WARN] El fallo de planilla no aborta el ETL — continuando."
else
  echo "[CALC_PLANILLA] OK"
fi

exit 0
