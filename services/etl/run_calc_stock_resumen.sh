#!/usr/bin/env bash
# run_calc_stock_resumen.sh - Wrapper para run_calc_stock_resumen.py.
# Llamado desde job_etl_diario.kjb después de RUN CALC_SUGERENCIAS.
#
# Issue #131: antes este wrapper terminaba SIEMPRE con exit 0, enmascarando
# el codigo de salida real del script. Ahora propaga el exit code real; que
# un fallo aca no aborte el resto de la cadena es una decision que toma el
# hop CONDICIONAL del .kjb (evaluation Y/N -> MARK CALC_STOCK_RESUMEN
# FAILED), no este script.
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
  echo "[CALC_STOCK_RESUMEN][ERROR] El script terminó con código ${rc}. Ver ${LOG}." >&2
else
  echo "[CALC_STOCK_RESUMEN] OK"
fi

exit "${rc}"
