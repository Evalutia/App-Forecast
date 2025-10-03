#!/usr/bin/env bash
set -euo pipefail

HOUR="${PREDICT_SCHEDULE_HOUR:-3}"

# Armamos un crontab para el USUARIO root (sin columna 'user')
cat >/tmp/cronfile <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/pentaho/data-integration

# Ejecutar al iniciar el contenedor para 'catch-up' (opcional, comentar si no lo querés)
@reboot sleep 60 && /opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic >> /app/data/etl_job.log 2>&1

# Ejecutar todos los días a la hora configurada (por defecto 03:00)
0 ${HOUR} * * * /opt/pentaho/data-integration/kitchen.sh -file=/app/services/etl/job_etl_diario.kjb -level=Basic >> /app/data/etl_job.log 2>&1
EOF

# Instalar crontab para root y mostrarlo
crontab /tmp/cronfile
echo "[entrypoint] Crontab instalado:"
crontab -l

# Asegurar archivo de log
mkdir -p /app/data
touch /app/data/etl_job.log

# Ejecutar cron en primer plano
exec cron -f
