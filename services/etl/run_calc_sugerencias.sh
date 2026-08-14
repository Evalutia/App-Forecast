#!/usr/bin/env bash
# run_calc_sugerencias.sh - Wrapper para run_calc_sugerencias.py.
# Llamado desde job_etl_diario.kjb después de RUN CALC_PLANILLA.
#
# Issue #131: antes este wrapper terminaba SIEMPRE con exit 0, enmascarando
# el codigo de salida real del script. Ahora propaga el exit code real; que
# un fallo aca no aborte el resto de la cadena es una decision que toma el
# hop CONDICIONAL del .kjb (evaluation Y/N -> MARK CALC_SUGERENCIAS FAILED),
# no este script.
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
  echo "[CALC_SUGERENCIAS][ERROR] El script terminó con código ${rc}. Ver ${LOG}." >&2
else
  echo "[CALC_SUGERENCIAS] OK"
fi

exit "${rc}"
