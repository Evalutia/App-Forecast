#!/usr/bin/env bash
# check_disk_space.sh — Chequea espacio libre en el volumen de datos de MySQL
# antes de lanzar un backfill grande (Issue #190). Corre EN LA VM, no en un
# contenedor -- el volumen de datos (mysql_data, dockerd data-root en
# /srv/evalutia/data) no está montado en ningún contenedor de la app, solo
# es visible desde el host.
#
# El incidente de #190: el chequeo de espacio que pedía #188 como criterio de
# aceptación miró el filesystem raíz (/, con 41GB libres de sobra) en vez del
# volumen real de datos -- ese se llenó al 100% a mitad de una corrida de
# varios días (~13GB/día de binlogs bajo carga de backfill, retención de 30
# días sin purga efectiva). Este script apunta al mount correcto.
#
# Uso (antes de lanzar un backfill grande, desde /opt/evalutia en la VM):
#   ./scripts/check_disk_space.sh && docker compose exec etl /bin/bash /app/services/etl/run_backfill_ventas.sh
#
# MIN_AVAIL_GB (override opcional) -- default 10GB. La retención de binlogs
# ya se bajó a 6 horas (SET PERSIST binlog_expire_logs_seconds=21600, ver
# #190), así que un backfill ya no debería acumular los ~38GB que gatillaron
# el incidente original -- este mínimo es margen adicional, no la única
# defensa.
#
# Exit 0 si hay margen suficiente, exit 1 si no, exit 2 si el mount ni
# siquiera existe (config incorrecta) -- pensado para encadenarse con && antes
# del backfill real, este script no lanza nada por sí solo.

set -euo pipefail

DATA_MOUNT="${DATA_MOUNT:-/srv/evalutia/data}"
MIN_AVAIL_GB="${MIN_AVAIL_GB:-10}"

if [[ ! -d "${DATA_MOUNT}" ]]; then
  echo "[ERROR] ${DATA_MOUNT} no existe o no es un directorio -- ¿mount correcto? Ver Issue #190 (el error original chequeó '/' por accidente)." >&2
  exit 2
fi

AVAIL_KB="$(df -Pk "${DATA_MOUNT}" | awk 'NR==2 {print $4}')"
AVAIL_GB=$(( AVAIL_KB / 1024 / 1024 ))

echo "[INFO] ${DATA_MOUNT}: ${AVAIL_GB}GB disponibles (mínimo requerido: ${MIN_AVAIL_GB}GB)"

if (( AVAIL_GB < MIN_AVAIL_GB )); then
  echo "[ERROR] Espacio insuficiente en ${DATA_MOUNT}: ${AVAIL_GB}GB < ${MIN_AVAIL_GB}GB mínimo." >&2
  echo "[ERROR] Antes de reintentar: purgar binlogs viejos (docker compose exec mysql mysql -uroot -p\"\$MYSQL_ROOT_PASSWORD\" -e \"PURGE BINARY LOGS BEFORE NOW() - INTERVAL 1 DAY\") o liberar cache de build (docker builder prune -af)." >&2
  exit 1
fi

echo "[OK] Espacio suficiente para continuar."
exit 0
