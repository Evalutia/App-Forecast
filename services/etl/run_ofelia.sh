#!/usr/bin/env bash
set -euo pipefail

# Issue #44: si hay un backfill historico corriendo (run_backfill_ventas.sh),
# se saltea esta corrida del daily en vez de competir por ventas_historicas_stage
# y por conexiones al WS. Se recupera sola la noche siguiente.
BACKFILL_LOCK_FILE="${BACKFILL_LOCK_FILE:-/app/data/backfill.lock}"
if [[ -e "${BACKFILL_LOCK_FILE}" ]]; then
  echo "[OFELIA] Backfill en curso (${BACKFILL_LOCK_FILE}) — se saltea la corrida diaria de esta noche."
  exit 0
fi

Y=$(date -d "yesterday" +%d/%m/%Y)

exec /opt/pentaho/data-integration/kitchen.sh \
  "-file=/app/services/etl/job_etl_diario.kjb" -level=Basic \
  "-param:WS_URL=http://200.125.29.194:81" "-param:DATE_FMT=dmy" \
  "-param:ID_EMPRESA=1" "-param:S_DEPOSITOS=1,5,8,9,10,11" \
  "-param:MYSQL_HOST=mysql" "-param:MYSQL_DB=evalutia" \
  "-param:MYSQL_USER=evalutia" "-param:MYSQL_PASSWORD=evalutia" "-param:MYSQL_PORT=3306" \
  "-param:PREDICT_PERIODS=2" "-param:PREDICT_MODEL_SET=classic" "-param:PREDICT_RESAMPLE_RULE=QS" "-param:PREDICT_VERSION=mvp-001" \
  "-param:FORCE_START=$Y" "-param:FORCE_END=$Y"
