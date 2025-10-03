#!/usr/bin/env bash
set -euo pipefail

# Exportar variables del entorno actual para cron
printenv | grep -E '^(MYSQL_|WS_|PREDICT_|TZ)=' | sed 's/^/export /' > /etc/profile.d/etl-env.sh

# Cronjob: usar "bash -lc" para cargar /etc/profile.d/*
CRON_SPEC="${CRON_SPEC:-0 3 * * *}"   # default 03:00 UTC si no se setea
JOB_CMD='/opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic'

echo "${CRON_SPEC} bash -lc '${JOB_CMD} >> /app/data/etl_job.log 2>&1'" > /etc/cron.d/etl
chmod 0644 /etc/cron.d/etl
crontab /etc/cron.d/etl

service cron start
tail -F /app/data/etl_job.log
