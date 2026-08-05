#!/usr/bin/env bash
set -euo pipefail

# Issue #111: la corrida nocturna registra su propio estado en jobs_historial
# (tipo_job='etl', detalle.subtipo='cron_diario'). Antes solo dejaban rastro
# los pasos CALC finales, asi que cualquier falla anterior -- truncate del
# staging, extraccion SOAP, merges -- moria en silencio: la unica huella
# quedaba en `docker logs` de ofelia, que se pierde al recrear el contenedor
# (por eso las noches del 24-27/07/2026 quedaron sin diagnostico posible).
#
# El bookkeeping nunca puede voltear la corrida: cada llamada se aisla y su
# fallo solo se loguea. El ETL manda; el registro es observabilidad.
CRON_JOBS="${CRON_JOBS:-/app/services/etl/cron_jobs.py}"
# Overridable solo para poder testear la orquestacion sin Pentaho (ver
# tests/test_run_ofelia.py). En produccion siempre es el kitchen.sh real.
KITCHEN="${KITCHEN:-/opt/pentaho/data-integration/kitchen.sh}"

# Issue #44: si hay un backfill historico corriendo (run_backfill_ventas.sh),
# se saltea esta corrida del daily en vez de competir por ventas_historicas_stage
# y por conexiones al WS. Se recupera sola la noche siguiente.
BACKFILL_LOCK_FILE="${BACKFILL_LOCK_FILE:-/app/data/backfill.lock}"
if [[ -e "${BACKFILL_LOCK_FILE}" ]]; then
  echo "[OFELIA] Backfill en curso (${BACKFILL_LOCK_FILE}) — se saltea la corrida diaria de esta noche."
  python3 "${CRON_JOBS}" skip "backfill en curso (${BACKFILL_LOCK_FILE})" >/dev/null \
    || echo "[OFELIA][WARN] no se pudo registrar la noche salteada en jobs_historial." >&2
  exit 0
fi

# Atraso del dato al entrar a la noche. Sale con codigo 1 cuando hay atraso
# (no es un fallo del chequeo), asi que se ignora el codigo a proposito:
# es informativo y no debe abortar la corrida que justamente viene a arreglarlo.
python3 "${CRON_JOBS}" stale || true

# Solo stdout alimenta JOB_ID (la sustitucion de comandos no captura stderr),
# asi que los avisos del script -- ej. corridas zombi cerradas -- siguen
# llegando al log de ofelia en vez de perderse en /dev/null.
JOB_ID="$(python3 "${CRON_JOBS}" start || true)"
if [[ ! "${JOB_ID}" =~ ^[0-9]+$ ]]; then
  # Sin id valido no se intenta cerrar nada: un id adivinado de un mensaje de
  # error actualizaria la fila equivocada de jobs_historial.
  echo "[OFELIA][WARN] no se pudo registrar el inicio en jobs_historial; la corrida sigue igual." >&2
  JOB_ID=""
fi
T0=${SECONDS}

Y=$(date -d "yesterday" +%d/%m/%Y)
# Mismo "ayer" que arriba, en ISO -- se lo pasamos explicito a `coherencia`
# en vez de dejar que lo recalcule sola despues de KITCHEN. Si una corrida
# alguna vez cruzara la medianoche, dos "yesterday" calculados en momentos
# distintos podrian discrepar y el chequeo mediria el dia equivocado.
Y_ISO=$(date -d "yesterday" +%Y-%m-%d)

set +e
"${KITCHEN}" \
  "-file=/app/services/etl/job_etl_diario.kjb" -level=Basic \
  "-param:WS_URL=https://200.125.29.194:81" "-param:DATE_FMT=dmy" \
  "-param:ID_EMPRESA=1" "-param:S_DEPOSITOS=1,5,8,9,10,11" \
  "-param:MYSQL_HOST=mysql" "-param:MYSQL_DB=evalutia" \
  "-param:MYSQL_USER=evalutia" "-param:MYSQL_PASSWORD=evalutia" "-param:MYSQL_PORT=3306" \
  "-param:PREDICT_PERIODS=2" "-param:PREDICT_MODEL_SET=classic" "-param:PREDICT_RESAMPLE_RULE=QS" "-param:PREDICT_VERSION=mvp-001" \
  "-param:FORCE_START=$Y" "-param:FORCE_END=$Y" \
  "-param:CERT_PATH=${CERT_PATH:-}" "-param:CACERT_PATH=${CACERT_PATH:-}" "-param:CERT_PASSWORD=${CERT_PASSWORD:-}"
RC=$?
set -e

if [[ -n "${JOB_ID}" ]]; then
  python3 "${CRON_JOBS}" end "${JOB_ID}" "${RC}" "$((SECONDS - T0))" >/dev/null \
    || echo "[OFELIA][WARN] no se pudo cerrar el registro ${JOB_ID} en jobs_historial." >&2

  # Issue #115: coherencia venta-vs-stock del dia que se acaba de cargar.
  # Va DESPUES de `end` a proposito -- `end` reescribe todo el detalle de la
  # fila, asi que si corriera antes este resultado se perderia. Igual que
  # `stale`, es informativo: si el chequeo mismo esta roto (DB abajo,
  # consulta rota) no debe frenar una corrida que ya termino.
  python3 "${CRON_JOBS}" coherencia "${JOB_ID}" "${Y_ISO}" || true
fi

exit "${RC}"
