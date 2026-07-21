#!/usr/bin/env bash
set -euo pipefail
# run_eval_elegibilidad_mensual.sh - Issue #102: corrida mensual (dry-run) de
# medicion de elegibilidad econometrica (eval_walkforward.py + apply_elegibilidad.py
# sobre el catalogo COMPLETO). Separado del cron diario (run_ofelia.sh) --
# no pasa por Pentaho/kitchen.sh, es un wrapper simple que invoca el
# entrypoint de Python (ml.run_eval_elegibilidad_dry_run), mismo patron que
# run_backfill_ventas.sh (script bash chico + Python real haciendo el trabajo).
#
# Nunca escribe en articulos_elegibilidad_econometrico -- el entrypoint de
# Python solo lee (ver ml/apply_elegibilidad.get_elegibilidad_summary), sin
# ningun codigo que dependa de APPLY_PERSIST. Aplicar el resultado a
# produccion sigue siendo, siempre, una decision humana explicita y manual.
#
# Uso tipico (via Ofelia, ver ofelia.ini):
#   /usr/local/bin/run_eval_elegibilidad_mensual.sh
#
# Uso manual, fuera de la cadencia mensual (ej. justo despues de desplegar
# #98/#99/#101, ver docstring de ml/run_eval_elegibilidad_dry_run.py para el
# detalle completo):
#   docker compose exec etl /bin/bash /app/services/etl/run_eval_elegibilidad_mensual.sh

: "${MYSQL_DB:?missing}"
: "${MYSQL_USER:?missing}"
: "${MYSQL_PASSWORD:?missing}"
# MYSQL_HOST no se exige aca: el .env de este repo no lo define (el
# contenedor etl resuelve "mysql" por nombre de servicio en la red de
# docker compose) y ml/*.py ya default a "mysql" si no esta seteado.

# ml/*.py de este repo leen MYSQL_PASS, no MYSQL_PASSWORD (mismo patron ya
# documentado en CONTEXTO.md para compare_hyperparams/#101) -- el env_file
# del contenedor etl solo expone MYSQL_PASSWORD, asi que se deriva aca.
export MYSQL_PASS="${MYSQL_PASS:-$MYSQL_PASSWORD}"

cd /app/services/python-worker
exec python3 -m ml.run_eval_elegibilidad_dry_run
