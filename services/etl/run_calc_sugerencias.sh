#!/usr/bin/env bash
# run_calc_sugerencias.sh - Wrapper no-bloqueante para run_calc_sugerencias.py
# Llamado desde job_etl_diario.kjb después de RUN CALC_PLANILLA.
# Siempre termina con exit 0: un fallo aquí no aborta el job maestro.
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${SELF_DIR}/run_calc_sugerencias.py"
LOG="/tmp/calc_sugerencias.log"

echo "[CALC_SUGERENCIAS] Iniciando cálculo de planilla_sugerencias..."

MYSQL_HOST="${MYSQL_HOST:-mysql}" \
MYSQL_PORT="${MYSQL_PORT:-3306}" \
MYSQL_DB="${MYSQL_DB:?MYSQL_DB requerido}" \
MYSQL_USER="${MYSQL_USER:?MYSQL_USER requerido}" \
MYSQL_PASSWORD="${MYSQL_PASSWORD:?MYSQL_PASSWORD requerido}" \
python3 "${SCRIPT}" 2>&1 | tee "${LOG}"

rc=${PIPESTATUS[0]}

if [[ ${rc} -ne 0 ]]; then
  echo "[CALC_SUGERENCIAS][WARN] El script terminó con código ${rc}. Ver ${LOG}." >&2
  echo "[CALC_SUGERENCIAS][WARN] El fallo de sugerencias no aborta el ETL — continuando."
else
  echo "[CALC_SUGERENCIAS] OK"
fi

exit 0
