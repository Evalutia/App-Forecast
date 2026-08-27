#!/usr/bin/env bash
set -uo pipefail
# run_backfill_comparacion.sh - Issue #186: re-extrae ventas/stock con el
# codigo actual del ETL hacia un almacen de comparacion AISLADO
# (ventas_historicas_stage_comparacion/ventas_historicas_comparacion/
# stock_diario_comparacion, ver infra/sql/26-tablas-comparacion.sql) --
# nunca toca ventas_historicas/stock_diario de produccion.
#
# No reimplementa el loop/lock/resumibilidad: exporta la configuracion que
# redirige run_backfill_ventas.sh (mismo script que ya usa el backfill real)
# al almacen de comparacion, y lo ejecuta tal cual. Mismo lock file que el
# backfill real y el cron diario (BACKFILL_LOCK_FILE, sin override aca) a
# proposito -- esta corrida compite por los mismos recursos (WS del cliente,
# CPU/memoria de la VM) que ya tienen historial de quedarse sin memoria en
# corridas grandes (#60/#112/#148), asi que tiene que respetar la misma
# exclusion mutua, no una propia que le permita superponerse.
#
# Uso tipico (rango de prueba, un grupo, antes de la corrida completa):
#   docker compose exec -e GROUPS=42 -e BACKFILL_FROM=2026-08-01 -e BACKFILL_TO=2026-08-07 \
#     etl /bin/bash /app/services/etl/run_backfill_comparacion.sh
#
# Corrida completa de los ultimos ~2 anios (Issue #188, todos los grupos
# incluido el 201 -- a diferencia del backfill real, get_grupos.py no lo
# excluye, ver mas abajo):
#   docker compose exec etl /bin/bash /app/services/etl/run_backfill_comparacion.sh
#
# Al cerrar el ciclo de diagnostico (#188), dropear el almacen de
# comparacion a mano -- ver el comentario de cabecera de
# infra/sql/26-tablas-comparacion.sql para el DROP exacto.

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export TABLA_VENTAS_STAGE="ventas_historicas_stage_comparacion"
export TABLA_VENTAS="ventas_historicas_comparacion"
export TABLA_STOCK_DIARIO="stock_diario_comparacion"
export BACKFILL_SUBTIPO="backfill_comparacion"

# get_grupos.py (lista completa, sin exclusiones) en vez de
# get_grupos_backfill.py (que excluye el grupo 201 -- correcto para el
# backfill real de #44, que ya tiene 10 anios cargados ahi, pero el objetivo
# de #186/#188 es comparar TODO lo que hoy esta en produccion, 201 incluido).
export GRUPOS_SCRIPT="get_grupos.py"

# Ventana de 2 anios por default, mismo mecanismo de override que ya trae
# run_backfill_ventas.sh (BACKFILL_FROM/BACKFILL_TO/BACKFILL_CHUNK_DAYS) --
# no se redeclara aca para no tener dos lugares calculando la misma fecha.

exec "${SELF_DIR}/run_backfill_ventas.sh"
